"""Append-only company and campaign intake using the selected application database."""

import json

from acquisition.contracts import Conflict, NotFound, canonical, digest


INTAKE = """
CREATE TABLE IF NOT EXISTS intake_company_revisions (
 organization TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
 payload TEXT NOT NULL, PRIMARY KEY(organization,id,revision));
CREATE TABLE IF NOT EXISTS intake_brief_revisions (
 organization TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
 company_id TEXT NOT NULL, company_revision INTEGER NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,id,revision),
 FOREIGN KEY(organization,company_id,company_revision)
 REFERENCES intake_company_revisions(organization,id,revision));
CREATE TABLE IF NOT EXISTS intake_requests (
 organization TEXT NOT NULL, request_id TEXT NOT NULL, inputs TEXT NOT NULL, receipt TEXT NOT NULL,
 PRIMARY KEY(organization,request_id));
"""
for _table in ('intake_company_revisions', 'intake_brief_revisions', 'intake_requests'):
    INTAKE += f"""
CREATE TRIGGER IF NOT EXISTS {_table}_no_update BEFORE UPDATE ON {_table}
 BEGIN SELECT RAISE(ABORT,'Intake history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS {_table}_no_delete BEFORE DELETE ON {_table}
 BEGIN SELECT RAISE(ABORT,'Intake history is immutable'); END;
"""
    _key = 'id=NEW.id AND revision=NEW.revision' if _table != 'intake_requests' else 'request_id=NEW.request_id'
    INTAKE += f"""
CREATE TRIGGER IF NOT EXISTS {_table}_no_replace BEFORE INSERT ON {_table}
 WHEN EXISTS(SELECT 1 FROM {_table} WHERE organization=NEW.organization AND {_key})
 BEGIN SELECT RAISE(ABORT,'Intake history is immutable'); END;
"""
INTAKE += 'PRAGMA user_version=24;'


def validate_intake_schema(db):
    db.execute('SELECT organization,id,revision,payload FROM intake_company_revisions LIMIT 0')
    db.execute('SELECT organization,id,revision,company_id,company_revision,payload FROM intake_brief_revisions LIMIT 0')
    db.execute('SELECT organization,request_id,inputs,receipt FROM intake_requests LIMIT 0')


def table_for(kind):
    return {'company': 'intake_company_revisions', 'brief': 'intake_brief_revisions'}[kind]


class SqliteCampaignIntake:
    def __init__(self, database, *, read_only=False):
        self.database, self.read_only = database, read_only

    def save(self, organization, request_id, inputs, now):
        if self.read_only:
            raise Conflict('Intake was opened for inspection only')
        # JSON freezes mutable caller-owned values before the writer lock.
        serialized = canonical(inputs)
        inputs = json.loads(serialized)
        kind, draft = inputs['kind'], inputs['draft']
        table = table_for(kind)
        with self.database.transaction() as db:
            old = db.execute('SELECT inputs,receipt FROM intake_requests WHERE organization=? AND request_id=?',
                             (organization, request_id)).fetchone()
            if old is not None:
                if old['inputs'] != serialized:
                    raise Conflict('Intake request already binds different inputs')
                return json.loads(old['receipt']) | {'replayed': True}
            identity = inputs['id'] or 'intake_' + kind + '_' + digest({'organization': organization, 'request_id': request_id})
            current = db.execute(f'SELECT MAX(revision) FROM {table} WHERE organization=? AND id=?',
                                 (organization, identity)).fetchone()[0]
            if inputs['id'] is not None and current is None:
                raise NotFound('Intake draft not found in this organization')
            if (current or 0) != inputs['expected_revision']:
                raise Conflict('Intake draft changed; reload before saving')
            if inputs['expected_revision'] >= 1_000_000:
                raise Conflict('Intake draft reached its revision limit')
            if kind == 'brief':
                self._company_revision(db, organization, draft['company_id'], draft['company_revision'])
            revision = inputs['expected_revision'] + 1
            snapshot = {'schema': 'intake-' + kind + '-revision/v1', 'organization': organization,
                        'id': identity, 'revision': revision, 'actor': inputs['actor'],
                        'request_id': request_id, 'saved_at': now, 'draft': draft,
                        'provenance': 'user_supplied_unverified', 'authority': 'none',
                        'execution_readiness': 'not_assessed'}
            if kind == 'company':
                db.execute('INSERT INTO intake_company_revisions VALUES(?,?,?,?)',
                           (organization, identity, revision, canonical(snapshot)))
            else:
                db.execute('INSERT INTO intake_brief_revisions VALUES(?,?,?,?,?,?)',
                           (organization, identity, revision, draft['company_id'], draft['company_revision'], canonical(snapshot)))
            receipt = {'schema': 'intake-save/v1', 'request_id': request_id, 'snapshot': snapshot}
            db.execute('INSERT INTO intake_requests VALUES(?,?,?,?)',
                       (organization, request_id, serialized, canonical(receipt)))
            return receipt | {'replayed': False}

    @staticmethod
    def _company_revision(db, organization, identity, revision):
        row = db.execute('SELECT payload FROM intake_company_revisions WHERE organization=? AND id=? AND revision=?',
                         (organization, identity, revision)).fetchone()
        if row is None:
            raise NotFound('Company revision not found in this organization')
        return json.loads(row['payload'])

    def get(self, organization, kind, identity, revision):
        table = table_for(kind)
        with self.database.connect() as db:
            row = db.execute(f'''SELECT payload FROM {table} WHERE organization=? AND id=?
                AND (? IS NULL OR revision=?) ORDER BY revision DESC LIMIT 1''',
                             (organization, identity, revision, revision)).fetchone()
            if row is None:
                raise NotFound('Intake revision not found in this organization')
            return json.loads(row['payload'])

    def listing(self, organization, kind, after_id, limit):
        table = table_for(kind)
        with self.database.connect() as db:
            return [json.loads(row['payload']) for row in db.execute(f'''
                SELECT r.payload FROM {table} r WHERE r.organization=? AND r.id>?
                AND r.revision=(SELECT MAX(v.revision) FROM {table} v WHERE v.organization=r.organization AND v.id=r.id)
                ORDER BY r.id LIMIT ?''', (organization, after_id, limit))]
