"""Immutable intake selection joined to native conversation planning and admission."""

import json

from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import INTAKE_SOURCE_SCHEMA, identity, intake_source_message
from .tasks import finite_time


INTAKE_PLANNING = '''
CREATE TABLE IF NOT EXISTS intake_planning_sources (
 organization TEXT NOT NULL, request_id TEXT NOT NULL, inputs TEXT NOT NULL, source TEXT NOT NULL,
 conversation_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
 brief_id TEXT NOT NULL, brief_revision INTEGER NOT NULL,
 company_id TEXT NOT NULL, company_revision INTEGER NOT NULL,
 PRIMARY KEY(organization,request_id), UNIQUE(organization,brief_id,brief_revision),
 UNIQUE(organization,conversation_id,revision),
 FOREIGN KEY(organization,conversation_id) REFERENCES conversations(organization,id),
 FOREIGN KEY(organization,brief_id,brief_revision) REFERENCES intake_brief_revisions(organization,id,revision),
 FOREIGN KEY(organization,company_id,company_revision) REFERENCES intake_company_revisions(organization,id,revision));
CREATE TRIGGER IF NOT EXISTS intake_planning_no_update BEFORE UPDATE ON intake_planning_sources
 BEGIN SELECT RAISE(ABORT,'Intake planning sources are immutable'); END;
CREATE TRIGGER IF NOT EXISTS intake_planning_no_delete BEFORE DELETE ON intake_planning_sources
 BEGIN SELECT RAISE(ABORT,'Intake planning sources are immutable'); END;
CREATE TRIGGER IF NOT EXISTS intake_planning_no_replace BEFORE INSERT ON intake_planning_sources
 WHEN EXISTS(SELECT 1 FROM intake_planning_sources WHERE organization=NEW.organization
 AND (request_id=NEW.request_id OR (brief_id=NEW.brief_id AND brief_revision=NEW.brief_revision)
 OR (conversation_id=NEW.conversation_id AND revision=NEW.revision)))
 BEGIN SELECT RAISE(ABORT,'Intake planning sources are immutable'); END;
PRAGMA user_version=25;
'''


def validate_intake_planning_schema(db):
    db.execute('SELECT organization,request_id,inputs,source,conversation_id,revision,brief_id,brief_revision,'
               'company_id,company_revision FROM intake_planning_sources LIMIT 0')


def snapshot(db, organization, kind, identifier, revision):
    table = {'brief': 'intake_brief_revisions', 'company': 'intake_company_revisions'}[kind]
    row = db.execute(f'SELECT payload FROM {table} WHERE organization=? AND id=? AND revision=?',
                     (organization, identifier, revision)).fetchone()
    if row is None:
        raise NotFound('The selected intake revision is not in this organization')
    return json.loads(row[0])


def bound_source(db, row):
    source = json.loads(row['source'])
    if source.get('schema') != INTAKE_SOURCE_SCHEMA or digest({k:v for k,v in source.items() if k != 'fingerprint'}) != source.get('fingerprint'):
        raise Conflict('Frozen intake source integrity failed')
    for key in ('organization', 'request_id', 'conversation_id', 'revision', 'brief_id', 'brief_revision', 'company_id', 'company_revision'):
        if source[key] != row[key]:
            raise Conflict('Frozen intake source identity differs from its native relation')
    org = source['organization']
    if (source['brief'] != snapshot(db, org, 'brief', source['brief_id'], source['brief_revision'])
            or source['company'] != snapshot(db, org, 'company', source['company_id'], source['company_revision'])
            or (source['brief']['draft']['company_id'], source['brief']['draft']['company_revision']) !=
               (source['company_id'], source['company_revision'])):
        raise Conflict('Frozen intake source differs from its scoped original revisions')
    command = json.loads(row['inputs'])
    if command != {k:source[k] for k in ('actor', 'brief_id', 'brief_revision', 'model_config')}:
        raise Conflict('Frozen intake source differs from its original command')
    store = db.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchone()
    if store is None or source['store_id'] != store[0]:
        raise Conflict('Frozen intake source belongs to another store')
    return source


def planning_source(db, organization, conversation_id, revision):
    # Historical inspection of pre-25 stores must not require the additive table.
    if db.execute("SELECT 1 FROM sqlite_schema WHERE name='intake_planning_sources' AND type='table'").fetchone() is None:
        return None
    row = db.execute('SELECT * FROM intake_planning_sources WHERE organization=? AND conversation_id=? AND revision=?',
                     (organization, conversation_id, revision)).fetchone()
    if row is None:
        return None
    source = bound_source(db, row)
    message = db.execute('SELECT content,request_id FROM conversation_messages '
                         'WHERE organization=? AND conversation_id=? AND revision=?',
                         (organization, conversation_id, revision)).fetchone()
    if message is None or tuple(message) != (intake_source_message(source), source['request_id']):
        raise Conflict('Intake planning message differs from its frozen source')
    return source


def managed(db, organization, conversation_id):
    if db.execute("SELECT 1 FROM sqlite_schema WHERE name='intake_planning_sources' AND type='table'").fetchone() is None:
        return False
    return db.execute('SELECT 1 FROM intake_planning_sources WHERE organization=? AND conversation_id=? LIMIT 1',
                      (organization, conversation_id)).fetchone() is not None


class SqliteIntakePlanning:
    def __init__(self, database):
        self.database = database

    def prepare(self, organization, actor, request_id, brief_id, brief_revision, model_config, now, preflight):
        for value in (organization, actor, request_id, brief_id):
            identity(value)
        if type(brief_revision) is not int or not 1 <= brief_revision <= 1_000_000:
            raise ValueError('Select an exact saved brief revision')
        finite_time(now)
        inputs = canonical({'actor':actor, 'brief_id':brief_id, 'brief_revision':brief_revision, 'model_config':model_config})
        with self.database.transaction() as db:
            old = db.execute('SELECT * FROM intake_planning_sources WHERE organization=? AND request_id=?',
                             (organization, request_id)).fetchone()
            if old:
                if old['inputs'] != inputs:
                    raise Conflict('Planning request already binds different source inputs or model settings')
                return planning_source(db, organization, old['conversation_id'], old['revision'])
            earlier = db.execute('SELECT request_id FROM intake_planning_sources WHERE organization=? AND brief_id=? AND brief_revision=?',
                                 (organization, brief_id, brief_revision)).fetchone()
            if earlier:
                raise Conflict('This saved brief version already has a planning request. Inspect or resume its original request.')
            brief = snapshot(db, organization, 'brief', brief_id, brief_revision)
            current = db.execute('SELECT MAX(revision) FROM intake_brief_revisions WHERE organization=? AND id=?',
                                 (organization, brief_id)).fetchone()[0]
            if current != brief_revision:
                raise Conflict('The saved brief changed. Reload before requesting a new plan.')
            company_id, company_revision = brief['draft']['company_id'], brief['draft']['company_revision']
            company = snapshot(db, organization, 'company', company_id, company_revision)
            native_key = 'intake-brief:' + digest({'brief':brief_id})
            conversation_id = 'conversation_' + digest({'organization':organization, 'request_id':native_key})[:32]
            conversation = db.execute('SELECT revision FROM conversations WHERE organization=? AND id=?',
                                      (organization, conversation_id)).fetchone()
            previous = db.execute('SELECT revision FROM intake_planning_sources WHERE organization=? AND conversation_id=?',
                                  (organization, conversation_id)).fetchall()
            if len(previous) >= 6:
                raise ValueError('This brief has used its six planning requests')
            if conversation is not None and (not previous or conversation[0] != len(previous)):
                raise Conflict('Managed intake conversation differs from its source history')
            if previous and db.execute('SELECT 1 FROM intake_planning_sources s LEFT JOIN conversation_plans p '
                    'ON p.organization=s.organization AND p.conversation_id=s.conversation_id AND p.revision=s.revision '
                    'WHERE s.organization=? AND s.conversation_id=? AND p.request_id IS NULL LIMIT 1',
                    (organization, conversation_id)).fetchone():
                raise Conflict('Resume the original staged intake request before selecting another brief version')
            revision = len(previous) + 1
            source = {'schema':INTAKE_SOURCE_SCHEMA, 'id':'intake_source_'+digest({'organization':organization,'request_id':request_id}),
                      'organization':organization, 'actor':actor, 'request_id':request_id,
                      'brief_id':brief_id, 'brief_revision':brief_revision, 'brief':brief,
                      'company_id':company_id, 'company_revision':company_revision, 'company':company,
                      'conversation_id':conversation_id, 'revision':revision, 'model_config':model_config,
                      'store_id':db.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchone()[0]}
            source['fingerprint'] = digest(source)
            existing_messages = [dict(row) for row in db.execute(
                "SELECT request_id AS id,revision,content,created_at FROM conversation_messages WHERE organization=? AND conversation_id=? ORDER BY revision",
                (organization, conversation_id))]
            future_messages = [row | {'role':'user'} for row in existing_messages] + [
                {'id':request_id,'revision':revision,'role':'user','content':intake_source_message(source),'created_at':now}]
            preflight(source, future_messages)
            if conversation is None:
                db.execute('INSERT INTO conversations VALUES(?,?,?,?,0,?)',
                           (organization, conversation_id, native_key, 'Saved campaign brief planning', now))
            db.execute('INSERT INTO conversation_messages VALUES(?,?,?,?,?,?)',
                       (organization, conversation_id, request_id, revision, intake_source_message(source), now))
            db.execute('UPDATE conversations SET revision=? WHERE organization=? AND id=?',
                       (revision, organization, conversation_id))
            db.execute('INSERT INTO intake_planning_sources VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (organization, request_id, inputs, canonical(source), conversation_id, revision,
                        brief_id, brief_revision, company_id, company_revision))
            return planning_source(db, organization, conversation_id, revision)

    def request(self, organization, request_id):
        identity(organization), identity(request_id)
        with self.database.connect() as db:
            row = db.execute('SELECT * FROM intake_planning_sources WHERE organization=? AND request_id=?',
                             (organization, request_id)).fetchone()
            if row is None:
                raise NotFound('Intake planning request not found in this organization')
            return planning_source(db, organization, row['conversation_id'], row['revision'])

    def listing(self, organization, brief_id):
        identity(organization), identity(brief_id)
        with self.database.connect() as db:
            return [planning_source(db, organization, row['conversation_id'], row['revision']) for row in
                    db.execute('SELECT conversation_id,revision FROM intake_planning_sources WHERE organization=? AND brief_id=? '
                               'ORDER BY revision', (organization, brief_id))]

    def current(self, organization, source):
        identity(organization)
        if source['organization'] != organization:
            raise Conflict('Intake planning source belongs to another organization')
        with self.database.connect() as db:
            return db.execute('SELECT MAX(revision) FROM intake_brief_revisions WHERE organization=? AND id=?',
                              (organization, source['brief_id'])).fetchone()[0] == source['brief_revision']
