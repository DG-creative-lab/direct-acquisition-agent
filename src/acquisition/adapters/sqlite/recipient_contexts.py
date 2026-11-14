"""Scoped recipient evidence manifests and atomic immutable context publication."""

from dataclasses import asdict
import json

from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.creative import (RecipientTarget, RecipientContextBasis, RecipientContextGuidance,
    RecipientContextRequest, RecipientEvidence, recipient_target_from, recipient_fact_from,
    select_recipient_context, reconstruct_saved_recipient_context, validate_recipient_assertions)
from .admission_guard import verified_required


RECIPIENT_CONTEXTS = '''
CREATE TABLE IF NOT EXISTS recipient_context_sources (
 organization TEXT NOT NULL,id TEXT NOT NULL,target_id TEXT NOT NULL,source_key TEXT NOT NULL,
 version INTEGER NOT NULL,source_id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(organization,id),
 UNIQUE(organization,target_id,source_key,version));
CREATE TABLE IF NOT EXISTS recipient_context_heads (
 organization TEXT NOT NULL,target_id TEXT NOT NULL,source_key TEXT NOT NULL,manifest_id TEXT NOT NULL,
 PRIMARY KEY(organization,target_id,source_key),
 FOREIGN KEY(organization,manifest_id) REFERENCES recipient_context_sources(organization,id));
CREATE TABLE IF NOT EXISTS recipient_contexts (
 organization TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS recipient_context_commands (
 organization TEXT NOT NULL,request_id TEXT NOT NULL,inputs TEXT NOT NULL,receipt TEXT NOT NULL,
 PRIMARY KEY(organization,request_id));
'''
for _table, _key in (('recipient_context_sources','id'),('recipient_contexts','id'),('recipient_context_commands','request_id')):
    RECIPIENT_CONTEXTS += f'''
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_update BEFORE UPDATE ON {_table} BEGIN SELECT RAISE(ABORT,'Immutable recipient context history'); END;
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_delete BEFORE DELETE ON {_table} BEGIN SELECT RAISE(ABORT,'Immutable recipient context history'); END;
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_replace BEFORE INSERT ON {_table}
 WHEN EXISTS(SELECT 1 FROM {_table} WHERE organization=NEW.organization AND {_key}=NEW.{_key})
 BEGIN SELECT RAISE(ABORT,'Immutable recipient context history'); END;
'''
RECIPIENT_CONTEXTS += 'PRAGMA user_version=19;'


def validate_recipient_context_schema(db):
    db.execute('SELECT organization,id,target_id,source_key,version,source_id,payload FROM recipient_context_sources LIMIT 0')
    db.execute('SELECT organization,target_id,source_key,manifest_id FROM recipient_context_heads LIMIT 0')
    db.execute('SELECT organization,id,payload FROM recipient_contexts LIMIT 0')
    db.execute('SELECT organization,request_id,inputs,receipt FROM recipient_context_commands LIMIT 0')


class SqliteRecipientContexts:
    def __init__(self, contacts, source, guidance, *, read_only=False):
        self.contacts, self.source, self.guidance, self.read_only = contacts, source, guidance, read_only

    def _writable(self, db):
        if self.read_only or verified_required(db):
            raise Conflict('Recipient context has no verified execution capability; execution stays paused')

    def _inputs(self, request): return {'kind':'recipient-context-prepare/v1','request':asdict(request)}

    def _replay(self, db, organization, request_id, request):
        from acquisition.audiences import bounded
        bounded(request_id)
        old = db.execute('SELECT inputs,receipt FROM recipient_context_commands WHERE organization=? AND request_id=?',
                         (organization,request_id)).fetchone()
        if old:
            if old['inputs']!=canonical(self._inputs(request)): raise Conflict('Recipient request already binds different exact inputs')
            receipt = json.loads(old['receipt'])
            saved = self._saved(db,organization,receipt['context_id'])
            if (canonical(saved['request'])!=canonical(asdict(request)) or receipt['context']!=saved['context']
                    or receipt['source_selection']!=saved['source_selection'] or receipt['kind']!='recipient_context_prepared'):
                raise Conflict('Stored recipient receipt differs from its exact request and context')
            return receipt | {'observation':'historical_receipt','authority':'none'}

    def replay(self, organization, request_id, request):
        with self.contacts.database.connect() as db:
            self._writable(db)
            return self._replay(db,organization,request_id,request)

    def _capture(self, db, organization, request):
        snapshot, report, profile = self.contacts.decision_evidence(db,organization,request.assessment_id)
        person = next((p for p in snapshot.contacts if p.ref.id==request.contact_id),None)
        if person is None: raise NotFound('Contact is unavailable in this scoped assessment')
        account = next((a for a in snapshot.accounts if len(person.accounts)==1 and a.ref.id==person.accounts[0].id),None)
        if account is None: raise Conflict('Resolve the contact/account association before retrieving context')
        target = RecipientTarget(organization,profile.id,person.ref,account.ref,account.experiment_unit)
        basis = RecipientContextBasis(target,request.assessment_id,snapshot.id,digest(report),report['channel'],
                                      report['purpose'],request.contact_id in report['eligible'])
        # Attestation is local metadata. Neither source material nor instructions can choose another target.
        self.source.manifest(organization,request.source_key,request.source_version,target)
        return basis

    def capture(self, organization, request):
        with self.contacts.database.connect() as db:
            db.execute('BEGIN'); self._writable(db)
            return self._capture(db,organization,request)

    def _manifest(self, row, organization, *, attest=False):
        value = json.loads(row['payload']); target = recipient_target_from(value['target'])
        if (row['organization']!=organization or target.organization!=organization or target.id!=row['target_id']
                or value['target_id']!=target.id or row['id']!='recipient_manifest_'+digest(value)
                or value['source_id']!=row['source_id'] or value['source_key']!=row['source_key'] or value['version']!=row['version']):
            raise Conflict('Stored recipient evidence integrity failure')
        if attest and value!=self.source.manifest(organization,value['source_key'],value['version'],target):
            raise Conflict('Stored recipient evidence differs from installed attestation')
        return value

    def _history(self, db, organization, target):
        result = []
        for row in db.execute('SELECT * FROM recipient_context_sources WHERE organization=? ORDER BY id',(organization,)):
            value = self._manifest(row,organization)
            if any(i['fact']['subject_id'] in {target.contact.id,target.account.id} for i in value['facts']):
                result.append((row['id'],value))
        return result

    def _current(self, db, organization, target, key):
        row = db.execute('''SELECT s.* FROM recipient_context_heads h JOIN recipient_context_sources s
            ON s.organization=h.organization AND s.id=h.manifest_id
            WHERE h.organization=? AND h.target_id=? AND h.source_key=?''',(organization,target.id,key)).fetchone()
        if row is None: return None
        value = self._manifest(row,organization,attest=True)
        latest = db.execute('SELECT max(version) FROM recipient_context_sources WHERE organization=? AND target_id=? AND source_key=?',
                            (organization,target.id,key)).fetchone()[0]
        if value['target_id']!=target.id or value['source_key']!=key or value['version']!=latest:
            raise Conflict('A recipient source head cannot rewind or substitute known evidence')
        return value

    def _install(self, db, organization, request, basis, evidence):
        if (type(evidence) is not RecipientEvidence or evidence.target!=basis.target
                or evidence.source_key!=request.source_key or evidence.version!=request.source_version
                or evidence.observed_at>self.contacts._now()
                or json.loads(canonical(evidence.manifest()))!=self.source.manifest(organization,request.source_key,request.source_version,basis.target)):
            raise Conflict('Recipient evidence differs from installed scoped attestation')
        value = json.loads(canonical(evidence.manifest()))
        current = self._current(db,organization,basis.target,request.source_key)
        if current is not None:
            if current['source_id']==value['source_id']: return value
            if value['version']!=current['version']+1 or value['observed_at']<current['observed_at']:
                raise Conflict('Recipient source versions cannot skip, rewind or move observations backward')
        elif value['version']!=1: raise Conflict('Install the first recipient evidence version before refreshing')
        history = self._history(db,organization,basis.target)
        for _, prior in history:
            if prior['source_key']!=value['source_key'] or prior['target_id']!=value['target_id']: continue
            for old in prior['facts']:
                for new in value['facts']:
                    if ((old['fact']['subject_id'],old['fact']['slot'])==(new['fact']['subject_id'],new['fact']['slot'])
                            and new['fact']['observed_at']<old['fact']['observed_at']):
                        raise Conflict('Recipient fact observations cannot move backward')
        identity = 'recipient_manifest_'+digest(value)
        db.execute('INSERT INTO recipient_context_sources VALUES(?,?,?,?,?,?,?)',
                   (organization,identity,basis.target.id,value['source_key'],value['version'],value['source_id'],canonical(value)))
        db.execute('INSERT INTO recipient_context_heads VALUES(?,?,?,?) ON CONFLICT(organization,target_id,source_key) DO UPDATE SET manifest_id=excluded.manifest_id',
                   (organization,basis.target.id,value['source_key'],identity))
        return value

    def _projection(self, db, organization, request, basis, guidance, manifest):
        history = self._history(db,organization,basis.target)
        context = select_recipient_context(basis.target,request,guidance,manifest,[v for _,v in history],
                                           basis.channel,basis.purpose,self.contacts._now(),basis.eligible)
        return context, [identity for identity,_ in history]

    def _record(self, db, organization, request_id, request, receipt):
        db.execute('INSERT INTO recipient_context_commands VALUES(?,?,?,?)',
                   (organization,request_id,canonical(self._inputs(request)),canonical(receipt)))

    def publish(self, organization, request_id, request, basis, guidance, evidence):
        with self.contacts.database.transaction() as db:
            self._writable(db)
            replay = self._replay(db,organization,request_id,request)
            if replay: return replay
            if guidance!=self.guidance or self._capture(db,organization,request)!=basis:
                raise Conflict('Recipient context differs from independently reconstructed inputs')
            manifest = self._install(db,organization,request,basis,evidence) if evidence is not None else None
            context, history = self._projection(db,organization,request,basis,guidance,manifest)
            payload = json.loads(canonical({'schema':'recipient-context-artifact/v2','organization':organization,
                'request':asdict(request),'basis':asdict(basis),'guidance':asdict(guidance),
                'source_selection':{'source_key':request.source_key,'version':request.source_version,
                    'source_id':self.source.manifest(organization,request.source_key,request.source_version,basis.target)['source_id']},
                'manifest_id':'recipient_manifest_'+digest(manifest) if manifest else None,
                'history_ids':history,'checked_at':self.contacts._now(),'context':context}))
            identity = 'recipient_context_'+digest(payload)
            old = db.execute('SELECT payload FROM recipient_contexts WHERE organization=? AND id=?',(organization,identity)).fetchone()
            if old is None: db.execute('INSERT INTO recipient_contexts VALUES(?,?,?)',(organization,identity,canonical(payload)))
            elif old[0]!=canonical(payload): raise Conflict('Recipient context identity already binds different bytes')
            receipt = {'kind':'recipient_context_prepared','context_id':identity,'context':context,'source_selection':payload['source_selection']}
            self._record(db,organization,request_id,request,receipt)
            self._writable(db)
            if (self._capture(db,organization,request)!=basis
                    or self._projection(db,organization,request,basis,guidance,manifest)!=(context,history)
                    or (manifest is not None and self._current(db,organization,basis.target,request.source_key)!=manifest)):
                raise Conflict('Recipient evidence changed before context commit')
            return receipt | {'observation':'committed','authority':'none'}

    def _saved(self, db, organization, context_id):
        row = db.execute('SELECT payload FROM recipient_contexts WHERE organization=? AND id=?',(organization,context_id)).fetchone()
        if row is None: raise NotFound('Recipient context is unavailable in this organization')
        payload = json.loads(row[0])
        if payload['organization']!=organization or context_id!='recipient_context_'+digest(payload):
            raise Conflict('Stored recipient context integrity failure')
        request = RecipientContextRequest(**(payload['request'] | {'slots':tuple(payload['request']['slots'])}))
        basis = RecipientContextBasis(**(payload['basis'] | {'target':recipient_target_from(payload['basis']['target'])}))
        guidance = RecipientContextGuidance(**(payload['guidance'] | {'priority':tuple(payload['guidance']['priority'])}))
        manifests = {}
        for identity in payload['history_ids']:
            row = db.execute('SELECT * FROM recipient_context_sources WHERE organization=? AND id=?',
                             (organization,identity)).fetchone()
            if row is None: raise Conflict('Frozen recipient evidence is unavailable')
            manifests[identity] = self._manifest(row,organization)
        manifest = manifests.get(payload['manifest_id'])
        # An empty source has no facts to enter history, but its immutable manifest is still required.
        if payload['manifest_id'] is not None and manifest is None:
            row = db.execute('SELECT * FROM recipient_context_sources WHERE organization=? AND id=?',
                             (organization,payload['manifest_id'])).fetchone()
            if row is None: raise Conflict('Frozen recipient source is unavailable')
            manifest = self._manifest(row,organization)
        expected = reconstruct_saved_recipient_context(basis.target,request,guidance,manifest,list(manifests.values()),
            basis.channel,basis.purpose,payload['checked_at'],basis.eligible,payload['schema'])
        if (basis.target.organization!=organization
                or basis.target.contact.id!=request.contact_id or basis.assessment_id!=request.assessment_id
                or payload['source_selection']['source_key']!=request.source_key
                or payload['source_selection']['version']!=request.source_version
                or (manifest is not None and manifest['source_id']!=payload['source_selection']['source_id'])
                or expected!=payload['context']):
            raise Conflict('Stored recipient context differs from its frozen evidence')
        return payload

    def _inspection(self, db, organization, request_id):
        row = db.execute('SELECT inputs,receipt FROM recipient_context_commands WHERE organization=? AND request_id=?',
                         (organization,request_id)).fetchone()
        if row is None: raise NotFound('Recipient context request is unavailable in this organization')
        receipt = json.loads(row['receipt']); saved = self._saved(db,organization,receipt['context_id'])
        request = RecipientContextRequest(**(saved['request'] | {'slots':tuple(saved['request']['slots'])}))
        if (row['inputs']!=canonical(self._inputs(request)) or receipt['context']!=saved['context']
                or receipt['source_selection']!=saved['source_selection'] or receipt['kind']!='recipient_context_prepared'):
            raise Conflict('Stored recipient receipt differs from its frozen request')
        try:
            basis = self._capture(db,organization,request)
            guidance = RecipientContextGuidance(**(saved['guidance'] | {'priority':tuple(saved['guidance']['priority'])}))
            manifest = self._current(db,organization,basis.target,request.source_key)
            current, history = self._projection(db,organization,request,basis,guidance,manifest)
            applicable = (asdict(basis)==saved['basis'] and manifest is not None
                and manifest['source_id']==saved['source_selection']['source_id']
                and current==saved['context'])
        except (Conflict,NotFound):
            current, applicable = None, False
        return {'context_id':receipt['context_id'],'saved':saved,'current':current,'currently_applicable':applicable,'authority':'none'}

    def inspect(self, organization, request_id):
        with self.contacts.database.connect() as db:
            db.execute('BEGIN')
            return self._inspection(db,organization,request_id)

    def validate(self, organization, request_id, assertions):
        with self.contacts.database.connect() as db:
            db.execute('BEGIN')
            view = self._inspection(db,organization,request_id)
            if not view['currently_applicable']: raise Conflict('Recipient context is historical, incomplete or no longer applicable')
            return validate_recipient_assertions(view['current'],assertions)
