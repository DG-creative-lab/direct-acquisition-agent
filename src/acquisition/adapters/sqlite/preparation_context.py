"""Immutable reviewed selections, committed with their exact original command."""

import json
from dataclasses import asdict

from acquisition.campaigns import PreparationReview, preparation_preview, reviewed_preparation
from acquisition.contracts import Conflict, NotFound, canonical
from .intake_planning import snapshot


PREPARATION_CONTEXTS = '''
CREATE TABLE IF NOT EXISTS preparation_contexts (
 organization TEXT NOT NULL, brief_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
 request_id TEXT NOT NULL, brief_revision INTEGER NOT NULL,
 company_id TEXT NOT NULL, company_revision INTEGER NOT NULL, company_head_revision INTEGER NOT NULL,
 inputs TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,brief_id,revision), UNIQUE(organization,request_id),
 FOREIGN KEY(organization,brief_id,brief_revision) REFERENCES intake_brief_revisions(organization,id,revision),
 FOREIGN KEY(organization,company_id,company_revision) REFERENCES intake_company_revisions(organization,id,revision),
 FOREIGN KEY(organization,company_id,company_head_revision) REFERENCES intake_company_revisions(organization,id,revision));
CREATE TRIGGER IF NOT EXISTS preparation_context_no_update BEFORE UPDATE ON preparation_contexts
 BEGIN SELECT RAISE(ABORT,'Preparation context history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS preparation_context_no_delete BEFORE DELETE ON preparation_contexts
 BEGIN SELECT RAISE(ABORT,'Preparation context history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS preparation_context_no_replace BEFORE INSERT ON preparation_contexts
 WHEN EXISTS(SELECT 1 FROM preparation_contexts WHERE organization=NEW.organization
 AND (request_id=NEW.request_id OR (brief_id=NEW.brief_id AND revision=NEW.revision)))
 BEGIN SELECT RAISE(ABORT,'Preparation context history is immutable'); END;
PRAGMA user_version=26;
'''


def validate_preparation_context_schema(db):
    db.execute('SELECT organization,brief_id,revision,request_id,brief_revision,company_id,company_revision,'
               'company_head_revision,inputs,payload FROM preparation_contexts LIMIT 0')


def latest(db, table, organization, identifier):
    return db.execute(f'SELECT MAX(revision) FROM {table} WHERE organization=? AND id=?',
                      (organization, identifier)).fetchone()[0]


def context_table(db):
    return db.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name='preparation_contexts'").fetchone() is not None


class SqlitePreparationContexts:
    def __init__(self, database, *, read_only=False):
        self.database, self.read_only = database, read_only

    @staticmethod
    def _preview(db, organization, brief_id, brief_revision):
        brief = snapshot(db, organization, 'brief', brief_id, brief_revision)
        if latest(db, 'intake_brief_revisions', organization, brief_id) != brief_revision:
            raise Conflict('The saved brief changed. Reload its preparation preview.')
        company_id, company_revision = brief['draft']['company_id'], brief['draft']['company_revision']
        company = snapshot(db, organization, 'company', company_id, company_revision)
        head = latest(db, 'intake_company_revisions', organization, company_id)
        revision = (db.execute('SELECT COALESCE(MAX(revision),0) FROM preparation_contexts '
                               'WHERE organization=? AND brief_id=?', (organization, brief_id)).fetchone()[0]
                    if context_table(db) else 0)
        identity = db.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchone()[0]
        return preparation_preview(company, brief, identity, head, revision)

    def preview(self, organization, brief_id, brief_revision):
        with self.database.connect() as db:
            return self._preview(db, organization, brief_id, brief_revision) | {
                'read_only':self.read_only or self.database.inspection_only}

    @staticmethod
    def _context(db, row):
        try:
            command, payload = json.loads(row['inputs']), json.loads(row['payload'])
            data = command['review']
            review = PreparationReview(**(data | {'selected_claim_ids':tuple(data['selected_claim_ids']),
                                                 'issues':tuple(data['issues'])}))
            company = snapshot(db, row['organization'], 'company', row['company_id'], row['company_revision'])
            brief = snapshot(db, row['organization'], 'brief', row['brief_id'], row['brief_revision'])
            store = db.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchone()[0]
            preview = preparation_preview(company, brief, store, row['company_head_revision'], row['revision']-1)
            expected = reviewed_preparation(preview, review, command['actor'], row['request_id'], payload['reviewed_at'])
            if (canonical(expected) != canonical(payload) or review.brief_id != row['brief_id'] or review.brief_revision != row['brief_revision']):
                raise Conflict('Reviewed preparation context differs from its original command or source evidence')
            return payload
        except (ValueError, TypeError, KeyError) as error:
            raise Conflict('Preparation context integrity failed against its original source evidence') from error

    @classmethod
    def _view(cls, db, row, now, replayed=False):
        context = cls._context(db, row)
        reasons = []
        current = db.execute('SELECT MAX(revision) FROM preparation_contexts WHERE organization=? AND brief_id=?',
                             (row['organization'], row['brief_id'])).fetchone()[0]
        if current != row['revision']:reasons.append('A later input review exists.')
        if latest(db, 'intake_brief_revisions', row['organization'], row['brief_id']) != row['brief_revision']:
            reasons.append('The campaign brief changed after this review.')
        if latest(db, 'intake_company_revisions', row['organization'], row['company_id']) != row['company_head_revision']:
            reasons.append('Company information changed after this review.')
        if not context['reviewed_at'] <= now < context['review_expires_at']:
            reasons.append('The preparation input review is expired or future-dated.')
        return {'request_id':row['request_id'], 'store_id':context['store_id'], 'context':context,
                'replayed':replayed, 'current':not reasons, 'review_required':reasons,
                'authority':'none', 'generation':'unavailable'}

    def confirm(self, organization, actor, request_id, review, now):
        if self.read_only:raise Conflict('Preparation contexts were opened for inspection only')
        inputs = canonical({'actor':actor, 'review':asdict(review)})
        with self.database.transaction() as db:
            old = db.execute('SELECT * FROM preparation_contexts WHERE organization=? AND request_id=?',
                             (organization, request_id)).fetchone()
            if old is not None:
                if old['inputs'] != inputs:raise Conflict('Preparation review request already binds different exact inputs')
                return self._view(db, old, now, True)
            preview = self._preview(db, organization, review.brief_id, review.brief_revision)
            if review.preview_id != preview['id'] or review.expected_context_revision != preview['context_revision']:
                raise Conflict('The displayed preparation sources or review changed. Reload before confirming.')
            if review.expected_context_revision >= 1_000_000:
                raise Conflict('This brief reached its preparation review revision limit')
            payload = reviewed_preparation(preview, review, actor, request_id, now)
            db.execute('INSERT INTO preparation_contexts VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (organization, review.brief_id, payload['revision'], request_id, review.brief_revision,
                        preview['company']['id'], preview['company']['revision'], preview['company_head_revision'],
                        inputs, canonical(payload)))
            row = db.execute('SELECT * FROM preparation_contexts WHERE organization=? AND request_id=?',
                             (organization, request_id)).fetchone()
            return self._view(db, row, now)

    def request(self, organization, request_id, now):
        with self.database.connect() as db:
            if not context_table(db):raise NotFound('This historical store has no preparation context records')
            row = db.execute('SELECT * FROM preparation_contexts WHERE organization=? AND request_id=?',
                             (organization, request_id)).fetchone()
            if row is None:raise NotFound('Preparation context request not found in this organization')
            return self._view(db, row, now)

    def history(self, organization, brief_id, now):
        with self.database.connect() as db:
            if not context_table(db):return []
            rows = db.execute('SELECT * FROM preparation_contexts WHERE organization=? AND brief_id=? '
                              'ORDER BY revision DESC LIMIT 20', (organization, brief_id)).fetchall()
            return [self._view(db, row, now) for row in rows]

    def not_committed(self, organization, request_id):
        if self.read_only or self.database.inspection_only:return False
        with self.database.connect() as db:
            return db.execute('SELECT 1 FROM preparation_contexts WHERE organization=? AND request_id=?',
                              (organization, request_id)).fetchone() is None
