"""Atomic contact evidence and preparation assessments in the application store."""

from dataclasses import asdict
import json

from acquisition.audiences import (contact_snapshot_from, related_identities, channel_purpose, bounded,
                                  timestamp, contact_evidence_conflicts)
from acquisition.campaigns import contact_eligibility
from acquisition.contracts import Conflict, NotFound, canonical, digest
from .admission_guard import verified_required


CONTACT_DIRECTORY = """
CREATE TABLE IF NOT EXISTS contact_sources (
 organization TEXT NOT NULL, id TEXT NOT NULL, connection_key TEXT NOT NULL, version INTEGER NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY(organization,id), UNIQUE(organization,connection_key,version));
CREATE TABLE IF NOT EXISTS contact_source_heads (
 organization TEXT NOT NULL, connection_key TEXT NOT NULL, source_id TEXT NOT NULL,
 PRIMARY KEY(organization,connection_key), FOREIGN KEY(organization,source_id) REFERENCES contact_sources(organization,id));
CREATE TABLE IF NOT EXISTS contact_objections (organization TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS contact_assessments (organization TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS contact_commands (organization TEXT NOT NULL,request_id TEXT NOT NULL,inputs TEXT NOT NULL,receipt TEXT NOT NULL,
 PRIMARY KEY(organization,request_id));
"""
for _table, _key in (('contact_sources','id'), ('contact_objections','id'),
                     ('contact_assessments','id'), ('contact_commands','request_id')):
    CONTACT_DIRECTORY += f"""
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_update BEFORE UPDATE ON {_table} BEGIN SELECT RAISE(ABORT,'Immutable contact history'); END;
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_delete BEFORE DELETE ON {_table} BEGIN SELECT RAISE(ABORT,'Immutable contact history'); END;
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_replace BEFORE INSERT ON {_table}
 WHEN EXISTS(SELECT 1 FROM {_table} WHERE organization=NEW.organization AND {_key}=NEW.{_key})
 BEGIN SELECT RAISE(ABORT,'Immutable contact history'); END;
"""
CONTACT_DIRECTORY += 'PRAGMA user_version=18;'


def validate_contact_schema(db):
    db.execute('SELECT organization,id,connection_key,version,payload FROM contact_sources LIMIT 0')
    db.execute('SELECT organization,connection_key,source_id FROM contact_source_heads LIMIT 0')
    for table in ('contact_objections','contact_assessments'):
        db.execute('SELECT organization,id,payload FROM ' + table + ' LIMIT 0')
    db.execute('SELECT organization,request_id,inputs,receipt FROM contact_commands LIMIT 0')


class SqliteContactDirectory:
    def __init__(self, database, source, profiles, profile_key, profile_version, clock, *, read_only=False):
        self.database, self.source, self.profiles = database, source, profiles
        self.profile_key, self.profile_version, self.clock = profile_key, profile_version, clock
        self.read_only = read_only

    def _now(self):
        value = self.clock(); timestamp(value)
        return value

    def _writable(self, db):
        if self.read_only or verified_required(db):
            raise Conflict('Contact preparation has no verified execution capability; execution stays paused')

    def _profile(self, organization):
        return self.profiles.campaign_profile(organization, self.profile_key, self.profile_version)

    def _replay(self, db, organization, request_id, inputs):
        bounded(request_id)
        old = db.execute('SELECT inputs,receipt FROM contact_commands WHERE organization=? AND request_id=?',
                         (organization, request_id)).fetchone()
        if old:
            if old['inputs'] != canonical(inputs):
                raise Conflict('Contact request already binds different exact inputs')
            return json.loads(old['receipt']) | {'observation':'historical_receipt','authority':'none'}

    def _record(self, db, organization, request_id, inputs, receipt):
        db.execute('INSERT INTO contact_commands VALUES(?,?,?,?)',
                   (organization,request_id,canonical(inputs),canonical(receipt)))
        return receipt | {'observation':'committed','authority':'none'}

    def _snapshot(self, row, organization, connection_key=None):
        snapshot = contact_snapshot_from(json.loads(row['payload']))
        if (snapshot.id != row['id'] or snapshot.connection.organization != organization
                or snapshot.connection.key != row['connection_key'] or snapshot.version != row['version']
                or (connection_key is not None and snapshot.connection.key != connection_key)):
            raise Conflict('Stored contact source integrity failure')
        return snapshot

    def _history(self, db, organization, connection_key=None):
        query = 'SELECT * FROM contact_sources WHERE organization=?'
        args = (organization,)
        if connection_key is not None:
            query += ' AND connection_key=?'; args += (connection_key,)
        return tuple(self._snapshot(row,organization,connection_key) for row in db.execute(query+' ORDER BY connection_key,version',args))

    def _current(self, db, organization, connection_key):
        row = db.execute('''SELECT s.* FROM contact_source_heads h JOIN contact_sources s
            ON s.organization=h.organization AND s.id=h.source_id
            WHERE h.organization=? AND h.connection_key=?''',(organization,connection_key)).fetchone()
        if row is None:
            raise NotFound('No current source in this organization and connection')
        snapshot = self._snapshot(row, organization, connection_key)
        latest = db.execute('SELECT max(version) FROM contact_sources WHERE organization=? AND connection_key=?',
                            (organization,connection_key)).fetchone()[0]
        if snapshot.version != latest:
            raise Conflict('A current source head cannot rewind immutable contact history')
        if snapshot.id != self.source.identity(organization,connection_key,snapshot.version):
            raise Conflict('Stored contact source differs from its installed attestation')
        return snapshot

    def _install(self, db, organization, snapshot):
        key = snapshot.connection.key
        if (snapshot.connection.organization != organization or snapshot.profile_id != self._profile(organization).id
                or snapshot.id != self.source.identity(organization,key,snapshot.version)):
            raise Conflict('Contact source differs from its scoped installed attestation')
        if snapshot.observed_at > self._now():
            raise Conflict('Contact source is future-dated')
        history = self._history(db,organization,key)
        if history:
            current = self._current(db,organization,key)
            if snapshot.connection.id != current.connection.id:
                raise Conflict('A connection key cannot switch provider accounts')
            if snapshot.version == current.version and snapshot.id == current.id:
                return
            if snapshot.version != current.version + 1:
                raise Conflict('A contact refresh cannot skip or rewind source versions')
            if snapshot.observed_at < current.observed_at:
                raise Conflict('Contact source observations cannot move backward')
        elif snapshot.version != 1:
            raise Conflict('Install the first contact source version before refreshing')
        accounts = {a.ref.id:a for a in snapshot.accounts}
        records = {r.ref.id:r for r in (*snapshot.accounts,*snapshot.contacts)}
        if snapshot.complete and any(r.ref.id not in records for old in history for r in (*old.accounts,*old.contacts)):
            raise Conflict('A complete refresh must retain known identities or explicit tombstones')
        permissions = {(p.contact.id,p.channel,p.purpose):p for p in snapshot.permissions}
        for old in history:
            for prior in old.permissions:
                current_permission = permissions.get((prior.contact.id,prior.channel,prior.purpose))
                if current_permission is not None and current_permission.observed_at < prior.observed_at:
                    raise Conflict('Contact permission observations cannot move backward')
        for old in self._history(db,organization):
            for prior in (*old.accounts,*old.contacts):
                replacement = records.get(prior.ref.id)
                if replacement and replacement.ref.role != prior.ref.role:
                    raise Conflict('A mapping revision cannot reinterpret an existing native identity role')
                if replacement and prior.state != 'active' and (
                        replacement.state != prior.state
                        or getattr(replacement.merged_into,'id',None) != getattr(prior.merged_into,'id',None)):
                    raise Conflict('Deleted or merged native identities cannot be resurrected or redirected')
            for prior in old.accounts:
                if prior.ref.id in accounts and accounts[prior.ref.id].business_id != prior.business_id:
                    raise Conflict('A known account cannot substitute its experiment identity')
        db.execute('INSERT INTO contact_sources VALUES(?,?,?,?,?)',
                   (organization,snapshot.id,key,snapshot.version,canonical(asdict(snapshot))))
        db.execute('INSERT INTO contact_source_heads VALUES(?,?,?) ON CONFLICT(organization,connection_key) DO UPDATE SET source_id=excluded.source_id',
                   (organization,key,snapshot.id))
        if self._current(db,organization,key) != snapshot:
            raise Conflict('Current contact source changed during publication')

    def _report(self, db, organization, key, channel, purpose):
        snapshot = self._current(db,organization,key)
        history = self._history(db,organization)
        blocked = set()
        for row in db.execute('SELECT * FROM contact_objections WHERE organization=?',(organization,)):
            value = json.loads(row['payload'])
            if 'objection_' + digest(value) != row['id'] or value['organization'] != organization:
                raise Conflict('Stored objection integrity failure')
            if value['channel'] in {channel,'all'} and value['purpose'] in {purpose,'all'}:
                blocked.update(related_identities(value['contact_id'],history))
        # Existing review-owned business suppressions remain an independent hard exclusion.
        suppressed = {row[0] for row in db.execute('SELECT business_id FROM review_suppressions WHERE organization=?',(organization,))}
        relevant = {r.ref.id for r in (*snapshot.accounts,*snapshot.contacts)}
        retired = {r.ref.id for source in history for r in (*source.accounts,*source.contacts)
                   if r.state != 'active' and r.ref.id in relevant}
        blocked &= {r.ref.id for r in snapshot.contacts}
        permission_conflicts, pressure_conflicts = contact_evidence_conflicts(snapshot,history,channel,purpose)
        report = contact_eligibility(snapshot,self._profile(organization),channel,purpose,self._now(),blocked,suppressed,
                                     retired,permission_conflicts,pressure_conflicts)
        authority = db.execute('SELECT audience_epoch FROM review_authorities WHERE organization=?',(organization,)).fetchone()
        report['basis']['review_audience_epoch'] = authority[0] if authority else None
        return report

    def refresh(self, organization, request_id, snapshot):
        inputs = {'kind':'contact-refresh/v1','source_id':snapshot.id}
        with self.database.transaction() as db:
            self._writable(db)
            replay = self._replay(db,organization,request_id,inputs)
            if replay: return replay
            self._install(db,organization,snapshot)
            receipt = {'kind':'contact_source_recorded','source_id':snapshot.id,'connection_key':snapshot.connection.key}
            result = self._record(db,organization,request_id,inputs,receipt)
            if self._current(db,organization,snapshot.connection.key) != snapshot:
                raise Conflict('Source changed before refresh commit')
            return result

    def prepare(self, organization, request_id, snapshot, channel, purpose):
        channel_purpose(channel,purpose)
        inputs = {'kind':'contact-prepare/v1','source_id':snapshot.id,'channel':channel,'purpose':purpose,
                  'profile_id':self._profile(organization).id}
        with self.database.transaction() as db:
            self._writable(db)
            replay = self._replay(db,organization,request_id,inputs)
            if replay: return replay
            self._install(db,organization,snapshot)
            report = self._report(db,organization,snapshot.connection.key,channel,purpose)
            payload = {'organization':organization,'request':inputs,'connection_key':snapshot.connection.key,
                       'checked_at':self._now(),'report':report}
            identity = 'contact_assessment_' + digest(payload)
            existing = db.execute('SELECT payload FROM contact_assessments WHERE organization=? AND id=?',
                                  (organization,identity)).fetchone()
            if existing is not None and existing[0] != canonical(payload):
                raise Conflict('Assessment identity already binds different immutable bytes')
            if existing is None:
                db.execute('INSERT INTO contact_assessments VALUES(?,?,?)',(organization,identity,canonical(payload)))
            receipt = {'kind':'contact_assessment_prepared','assessment_id':identity,'report':report}
            result = self._record(db,organization,request_id,inputs,receipt)
            if self._report(db,organization,snapshot.connection.key,channel,purpose) != report:
                raise Conflict('Contact evidence changed before assessment commit')
            return result

    def object(self, organization, request_id, contact_id, channel, purpose, reason):
        channel_purpose('email' if channel=='all' else channel, 'acquisition' if purpose=='all' else purpose)
        bounded(contact_id); bounded(reason,600)
        inputs = {'kind':'contact-objection/v1','contact_id':contact_id,'channel':channel,'purpose':purpose,'reason':reason}
        with self.database.transaction() as db:
            self._writable(db)
            replay = self._replay(db,organization,request_id,inputs)
            if replay: return replay
            if not any(p.ref.id==contact_id for source in self._history(db,organization) for p in source.contacts):
                raise NotFound('Contact is unavailable in this organization')
            payload = inputs | {'organization':organization,'recorded_at':self._now()}
            identity = 'objection_' + digest(payload)
            old = db.execute('SELECT payload FROM contact_objections WHERE organization=? AND id=?',(organization,identity)).fetchone()
            if old is None:
                db.execute('INSERT INTO contact_objections VALUES(?,?,?)',(organization,identity,canonical(payload)))
            return self._record(db,organization,request_id,inputs,{'kind':'contact_objection_recorded','objection_id':identity})

    def inspect(self, organization, assessment_id):
        with self.database.connect() as db:
            db.execute('BEGIN')
            row = db.execute('SELECT payload FROM contact_assessments WHERE organization=? AND id=?',
                             (organization,assessment_id)).fetchone()
            if row is None: raise NotFound('Assessment is unavailable in this organization')
            payload = json.loads(row[0])
            if payload['organization'] != organization or 'contact_assessment_' + digest(payload) != assessment_id:
                raise Conflict('Stored contact assessment integrity failure')
            try:
                current = self._report(db,organization,payload['connection_key'],payload['report']['channel'],payload['report']['purpose'])
            except NotFound:
                return {'assessment_id':assessment_id,'saved':payload,'current':None,
                        'currently_applicable':False,'current_ready_for_proposal':False,
                        'reason':'source_unavailable','authority':'none'}
            return {'assessment_id':assessment_id,'saved':payload,'current':current,
                    'currently_applicable':current==payload['report'],
                    'current_ready_for_proposal':current==payload['report'] and current['ready_for_proposal'], 'authority':'none'}
