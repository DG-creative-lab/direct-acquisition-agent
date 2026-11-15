"""Exact multichannel review. Every effect revalidates within its writer transaction."""

import json
from uuid import uuid4

from acquisition.campaigns import SequenceRequest, validate_sequence_proposal, contact_readiness_boundaries
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.creative import (validate_channel_bundle, channel_arguments, CHANNEL_CONTENT_CAPABILITY,
    recipient_readiness_boundaries, channel_readiness_boundaries)
from acquisition.reviews import (SEQUENCE_PURPOSE, SEQUENCE_CHECKS, sequence_subject, sequence_validation,
    sequence_summary, validate_sequence_output, text, readiness_window)
from .actors import require_actor
from .creative import read_context


SEQUENCE_REVIEWS = '''
CREATE TABLE IF NOT EXISTS sequence_review_subjects (
 organization TEXT NOT NULL,id TEXT NOT NULL,proposal_id TEXT NOT NULL,payload TEXT NOT NULL,
 PRIMARY KEY(organization,id), FOREIGN KEY(organization,proposal_id) REFERENCES sequence_proposals(organization,id));
CREATE TABLE IF NOT EXISTS sequence_review_decisions (
 organization TEXT NOT NULL,id TEXT NOT NULL,subject_id TEXT NOT NULL,proposal_id TEXT NOT NULL,payload TEXT NOT NULL,
 PRIMARY KEY(organization,id), FOREIGN KEY(organization,subject_id) REFERENCES sequence_review_subjects(organization,id));
CREATE TABLE IF NOT EXISTS sequence_review_revocations (
 organization TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(organization,id),
 FOREIGN KEY(organization,id) REFERENCES sequence_review_decisions(organization,id));
CREATE TABLE IF NOT EXISTS sequence_review_commands (
 organization TEXT NOT NULL,request_id TEXT NOT NULL,inputs TEXT NOT NULL,receipt TEXT NOT NULL,
 PRIMARY KEY(organization,request_id));
CREATE TABLE IF NOT EXISTS sequence_review_events (
 organization TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS sequence_simulation_approvals (
 organization TEXT NOT NULL,id TEXT NOT NULL,approval_id TEXT NOT NULL,PRIMARY KEY(organization,id),
 FOREIGN KEY(organization,id) REFERENCES engagement_simulations(organization,id),
 FOREIGN KEY(organization,approval_id) REFERENCES sequence_review_decisions(organization,id));
'''
for _table, _key in (('sequence_review_subjects','id'),('sequence_review_decisions','id'),
        ('sequence_review_revocations','id'),('sequence_review_commands','request_id'),
        ('sequence_review_events','id'),('sequence_simulation_approvals','id')):
    SEQUENCE_REVIEWS += f'''
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_update BEFORE UPDATE ON {_table} BEGIN SELECT RAISE(ABORT,'Immutable sequence review'); END;
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_delete BEFORE DELETE ON {_table} BEGIN SELECT RAISE(ABORT,'Immutable sequence review'); END;
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_replace BEFORE INSERT ON {_table}
 WHEN EXISTS(SELECT 1 FROM {_table} WHERE organization=NEW.organization AND {_key}=NEW.{_key})
 BEGIN SELECT RAISE(ABORT,'Immutable sequence review'); END;
'''
SEQUENCE_REVIEWS += 'PRAGMA user_version=22;'


def validate_sequence_review_schema(db):
    for table, columns in {
        'sequence_review_subjects':'organization,id,proposal_id,payload',
        'sequence_review_decisions':'organization,id,subject_id,proposal_id,payload',
        'sequence_review_revocations':'organization,id,payload',
        'sequence_review_commands':'organization,request_id,inputs,receipt',
        'sequence_review_events':'organization,id,payload',
        'sequence_simulation_approvals':'organization,id,approval_id'
    }.items(): db.execute('SELECT '+columns+' FROM '+table+' LIMIT 0')


class SqliteSequenceReviews:
    def __init__(self, proposals):
        self.proposals, self.database = proposals, proposals.database

    def _event(self, db, organization, kind, value):
        db.execute('INSERT INTO sequence_review_events VALUES(?,?,?)',
            (organization,'sequence_review_event_'+uuid4().hex,canonical({'kind':kind,'at':self.proposals._now(),'data':value})))

    def _command(self, db, organization, key, inputs, receipt=None):
        text(key,200)
        row = db.execute('SELECT inputs,receipt FROM sequence_review_commands WHERE organization=? AND request_id=?',(organization,key)).fetchone()
        if row:
            if row['inputs'] != canonical(inputs): raise Conflict('Review request already binds different exact inputs')
            return json.loads(row['receipt'])
        if receipt is not None:
            db.execute('INSERT INTO sequence_review_commands VALUES(?,?,?,?)',(organization,key,canonical(inputs),canonical(receipt)))
        return None

    def _basis(self, db, organization):
        # Immutable history prevents authorization resurrection after a source-head rewind.
        basis = {}
        for table in ('contact_sources','recipient_context_sources','contact_objections'):
            basis[table] = [r[0] for r in db.execute('SELECT id FROM '+table+' WHERE organization=? ORDER BY id',(organization,))]
        basis['global_stops'] = [r[0] for r in db.execute('SELECT id FROM engagement_stops WHERE organization=? AND simulation_id IS NULL ORDER BY id',(organization,))]
        basis['suppressions'] = [dict(r) for r in db.execute('SELECT * FROM review_suppressions WHERE organization=? ORDER BY business_id',(organization,))]
        authority = db.execute('SELECT * FROM review_authorities WHERE organization=?',(organization,)).fetchone()
        basis['review_authority'] = dict(authority) if authority else None
        return basis

    def _subject(self, db, organization, identity):
        row = db.execute('SELECT * FROM sequence_review_subjects WHERE organization=? AND id=?',(organization,identity)).fetchone()
        if row is None: raise NotFound('Sequence review subject unavailable in this organization')
        saved = json.loads(row['payload'])
        if (saved != sequence_subject(organization,row['proposal_id'],saved['sequence'],saved['basis'])
                or saved['id'] != identity): raise Conflict('Sequence review subject integrity failure')
        return saved

    def _identity(self, db, organization, subject):
        proposal = self.proposals.get(db,organization,subject['proposal_id'])
        if subject['sequence'] != proposal: raise Conflict('Subject differs from saved exact sequence')
        command = db.execute('SELECT * FROM sequence_commands WHERE organization=? AND request_id=?',(organization,proposal['request_id'])).fetchone()
        if (command is None or command['proposal_id'] != subject['proposal_id']
                or command['inputs'] != canonical(proposal['request'])): raise Conflict('Sequence differs from its admitted request')
        return proposal

    def _payloads(self, db, organization, proposal):
        materials = {}
        for stage, key in (('initial','initial_content'),('call','call_content'),('followup','followup_content')):
            request_key = proposal['request'][key]
            row = db.execute('SELECT * FROM channel_preparations WHERE organization=? AND request_id=?',(organization,request_key)).fetchone()
            if row is None: raise NotFound('Sequence content preparation unavailable')
            artifact = db.execute('SELECT id FROM channel_artifacts WHERE organization=? AND run_id=?',(organization,row['run_id'])).fetchone()
            if artifact is None: raise Conflict('Every payload must be materialized before review')
            bundle = self.proposals.channels._artifact(db,organization,artifact['id'])
            context = read_context(db,organization,row['context_id'])
            run = db.execute('SELECT status FROM runs WHERE organization=? AND id=?',(organization,row['run_id'])).fetchone()
            tasks = db.execute('SELECT capability,inputs,output,status FROM tasks WHERE run_id=? ORDER BY position',(row['run_id'],)).fetchall()
            if (run is None or run['status'] != 'succeeded' or len(tasks)!=1
                    or tasks[0]['capability'] != CHANNEL_CONTENT_CAPABILITY or tasks[0]['status']!='succeeded'
                    or json.loads(tasks[0]['inputs'])!={'workflow_version':'channel-content/v1',
                        'context_id':row['context_id'],'model_config':context['model_config']}
                    or json.loads(tasks[0]['output']).get('artifact_id')!=artifact['id']):
                raise Conflict('Content lacks its exact completed source run')
            matched = False
            for attempt in (0,1):
                calls = {}
                for name, tool in (('proposal','submit_contextual_email' if context['command']['channel']=='email' else 'submit_call_guidance'),('screen','record_channel_screen')):
                    call = db.execute('SELECT status,response FROM model_calls WHERE organization=? AND run_id=? AND call_key=?',
                        (organization,row['run_id'],row['context_id']+':channel:'+name+':'+str(attempt))).fetchone()
                    if call and call['status']=='recorded': calls[name] = channel_arguments(json.loads(call['response']),tool)
                if set(calls)=={'proposal','screen'} and calls['screen']==bundle['screen']:
                    if calls['proposal']['context_id']!=row['context_id']: raise Conflict('Model proposal targets another context')
                    validate_channel_bundle(context,row['context_id'],calls['proposal']['rows'],bundle)
                    matched = True
                    break
            if not matched: raise Conflict('Content lacks its exact recorded proposal and advisory screen')
            materials[stage] = self.proposals._material(db,organization,request_key)
        return materials

    def _campaign(self, db, organization, proposal):
        decision, identities = self.proposals._decision(db,organization,proposal['request']['decision_request'])
        materials = {stage:self.proposals._material(db,organization,proposal['request'][key]) for stage,key in
            (('initial','initial_content'),('call','call_content'),('followup','followup_content'))}
        validate_sequence_proposal(proposal,decision,materials,self.proposals.connections,identities)
        self.proposals.current(db,organization,proposal)

    def _readiness_window(self, db, organization, subject, started_at):
        # Match the conservative organization-wide evidence scope of _basis.
        snapshots = self.proposals.contacts._history(db,organization)
        recipients = self.proposals.channels.recipients
        manifests = [recipients._manifest(row,organization) for row in db.execute(
            'SELECT * FROM recipient_context_sources WHERE organization=? ORDER BY id',(organization,))]
        contexts = []
        for key in ('initial_content','call_content','followup_content'):
            row = db.execute('SELECT context_id FROM channel_preparations WHERE organization=? AND request_id=?',
                (organization,subject['sequence']['request'][key])).fetchone()
            if row is None: raise NotFound('Readiness context is unavailable in this organization')
            contexts.append(read_context(db,organization,row['context_id']))
        boundaries = (contact_readiness_boundaries(snapshots)+recipient_readiness_boundaries(manifests)
            +channel_readiness_boundaries(contexts))
        return readiness_window(subject,boundaries,started_at)

    def _report(self, db, organization, subject):
        proposal = subject['sequence']
        started_at = self.proposals._now()
        def epochs():
            if self._basis(db,organization)!=subject['basis']: raise Conflict('Evidence or suppression epoch changed')
            return self._readiness_window(db,organization,subject,started_at)
        checks = []
        validators = {'artifact_identity':lambda:self._identity(db,organization,subject),
            'audience_permissions':lambda:self.proposals._decision(db,organization,proposal['request']['decision_request']),
            'recipient_payloads':lambda:self._payloads(db,organization,proposal),
            'sequence_contract':lambda:self._campaign(db,organization,proposal), 'current_epochs':epochs}
        for name in sorted(SEQUENCE_CHECKS):
            metadata = {}
            try:
                result = validators[name]()
                if name=='current_epochs': metadata['validity'] = result
                status, detail = 'passed', 'Required domain validation passed.'
            except (Conflict,NotFound,ValueError):
                status, detail = 'failed', 'Saved inputs failed current domain validation.'
            except Exception:
                status, detail = 'unknown', 'Checker unavailable. No readiness or execution authority.'
            checks.append({'id':name,'required':True,'status':status,'detail':detail} | metadata)
        checks.append({'id':'semantic_screen','required':False,'status':'passed' if next(c for c in checks if c['id']=='recipient_payloads')['status']=='passed' else 'not_evaluated',
            'detail':'Recorded semantic screening is advisory, never accountable approval.'})
        return sequence_validation(subject,checks,self.proposals._now())

    def _ready(self, db, organization, subject):
        report = self._report(db,organization,subject)
        if not report['review_ready']: raise Conflict('Exact sequence validation is incomplete or no longer current')
        return report

    def open(self, organization, request_id, proposal_id, actor):
        inputs = {'kind':'sequence_review_open/v1','proposal_id':proposal_id,'actor':actor}
        with self.database.transaction() as db:
            self.proposals.writable(db); require_actor(db,organization,actor,'operator')
            replay = self._command(db,organization,request_id,inputs)
            if replay: return replay | {'observation':'historical_receipt'}
            proposal = self.proposals.get(db,organization,proposal_id)
            subject = sequence_subject(organization,proposal_id,proposal,self._basis(db,organization))
            self._ready(db,organization,subject)
            old = db.execute('SELECT payload FROM sequence_review_subjects WHERE organization=? AND id=?',(organization,subject['id'])).fetchone()
            if old is None:
                db.execute('INSERT INTO sequence_review_subjects VALUES(?,?,?,?)',(organization,subject['id'],proposal_id,canonical(subject)))
            receipt = {'subject_id':subject['id'],'proposal_id':proposal_id,'purpose':SEQUENCE_PURPOSE,'authority':'none'}
            self._event(db,organization,'sequence_review_opened',receipt)
            self._command(db,organization,request_id,inputs,receipt)
            self._ready(db,organization,subject); self.proposals.writable(db)
            return receipt

    def decide(self, organization, request_id, subject_id, actor, decision, reason, ttl_seconds):
        text(reason)
        if decision not in {'approve','reject'} or type(ttl_seconds) is not int or not 1<=ttl_seconds<=14*86400:
            raise ValueError('Choose approve/reject and a lifetime of one second to fourteen days')
        inputs = {'kind':'sequence_review_decide/v1','subject_id':subject_id,'actor':actor,'decision':decision,'reason':reason,'ttl_seconds':ttl_seconds}
        with self.database.transaction() as db:
            self.proposals.writable(db); reviewer = require_actor(db,organization,actor,'reviewer')
            replay = self._command(db,organization,request_id,inputs)
            if replay: return replay | {'observation':'historical_receipt'}
            subject = self._subject(db,organization,subject_id)
            if decision=='approve': self._ready(db,organization,subject)
            now = self.proposals._now()
            expiry = min(now+ttl_seconds,subject['sequence']['request']['expires_at'],
                *(s['content']['valid_until'] for m in subject['sequence']['population'] for s in m['steps']))
            if expiry<=now: raise Conflict('Sequence approval has no remaining validity window')
            value = {'schema':'sequence-review-decision/v1','organization':organization,'purpose':SEQUENCE_PURPOSE,
                'request_id':request_id,
                'subject_id':subject_id,'proposal_id':subject['proposal_id'],'actor':actor,'actor_generation':reviewer['generation'],
                'decision':decision,'reason':reason,'at':now,'expires_at':expiry}
            value = value | {'id':'sequence_approval_'+digest(value)}
            db.execute('INSERT INTO sequence_review_decisions VALUES(?,?,?,?,?)',(organization,value['id'],subject_id,subject['proposal_id'],canonical(value)))
            self._event(db,organization,'sequence_review_'+decision,value)
            self._command(db,organization,request_id,inputs,value)
            if decision=='approve': self.authorize(db,organization,subject['proposal_id'],value['id'])
            self.proposals.writable(db)
            return value

    def revoke(self, organization, request_id, approval_id, actor, reason):
        text(reason)
        inputs = {'kind':'sequence_review_revoke/v1','approval_id':approval_id,'actor':actor,'reason':reason}
        with self.database.transaction() as db:
            self.proposals.writable(db); require_actor(db,organization,actor,'reviewer')
            replay = self._command(db,organization,request_id,inputs)
            if replay: return replay | {'observation':'historical_receipt'}
            self._decision(db,organization,approval_id)
            old = db.execute('SELECT payload FROM sequence_review_revocations WHERE organization=? AND id=?',(organization,approval_id)).fetchone()
            value = json.loads(old[0]) if old else {'approval_id':approval_id,'actor':actor,'reason':reason,'at':self.proposals._now(),'purpose':SEQUENCE_PURPOSE}
            if old is None: db.execute('INSERT INTO sequence_review_revocations VALUES(?,?,?)',(organization,approval_id,canonical(value)))
            self._event(db,organization,'sequence_approval_revoked',value)
            self._command(db,organization,request_id,inputs,value); self.proposals.writable(db)
            return value

    def _decision(self, db, organization, approval_id):
        row = db.execute('SELECT * FROM sequence_review_decisions WHERE organization=? AND id=?',(organization,approval_id)).fetchone()
        if row is None: raise NotFound('Exact sequence approval unavailable in this organization and purpose')
        saved = json.loads(row['payload'])
        if (saved['id']!='sequence_approval_'+digest({k:v for k,v in saved.items() if k!='id'})
                or saved['organization']!=organization or saved['purpose']!=SEQUENCE_PURPOSE
                or saved['subject_id']!=row['subject_id'] or saved['proposal_id']!=row['proposal_id'] or saved['id']!=approval_id):
            raise Conflict('Sequence decision integrity failure')
        return saved

    def authorize(self, db, organization, proposal_id, approval_id):
        approval = self._decision(db,organization,approval_id)
        now = self.proposals._now()
        if (approval['decision']!='approve' or approval['proposal_id']!=proposal_id
                or not approval['at']<=now<approval['expires_at']): raise Conflict('Approval does not authorize this exact sequence now')
        reviewer = require_actor(db,organization,approval['actor'],'reviewer')
        if reviewer['generation']!=approval['actor_generation']: raise Conflict('Reviewer generation changed')
        latest = db.execute('SELECT id FROM sequence_review_decisions WHERE organization=? AND proposal_id=? ORDER BY rowid DESC LIMIT 1',(organization,proposal_id)).fetchone()
        if latest[0]!=approval_id or db.execute('SELECT 1 FROM sequence_review_revocations WHERE organization=? AND id=?',(organization,approval_id)).fetchone():
            raise Conflict('Sequence approval revoked or superseded')
        subject = self._subject(db,organization,approval['subject_id'])
        self._ready(db,organization,subject)
        if (not approval['at']<=self.proposals._now()<approval['expires_at']
                or self._basis(db,organization)!=subject['basis']
                or require_actor(db,organization,approval['actor'],'reviewer')['generation']!=approval['actor_generation']):
            raise Conflict('Sequence authority changed while validation was running')
        return approval

    def authorize_simulation(self, db, organization, simulation_id, proposal_id):
        row = db.execute('SELECT approval_id FROM sequence_simulation_approvals WHERE organization=? AND id=?',(organization,simulation_id)).fetchone()
        if row is None: raise Conflict('Historical unapproved simulation cannot admit new effects')
        return self.authorize(db,organization,proposal_id,row[0])

    def bind(self, db, organization, simulation_id, proposal_id, approval_id):
        self.authorize(db,organization,proposal_id,approval_id)
        db.execute('INSERT INTO sequence_simulation_approvals VALUES(?,?,?)',(organization,simulation_id,approval_id))

    def status(self, db, organization, simulation_id, proposal_id):
        if db.execute('PRAGMA user_version').fetchone()[0]<22:
            return {'approval_id':None,'purpose':SEQUENCE_PURPOSE,'current':False,
                'observation':'historical_pre_review_schema','live_outbound_authority':'none'}
        row = db.execute('SELECT approval_id FROM sequence_simulation_approvals WHERE organization=? AND id=?',(organization,simulation_id)).fetchone()
        current = False
        if row:
            try:
                self.authorize(db,organization,proposal_id,row[0])
                current = True
            except (ValueError,NotFound): pass
        return {'approval_id':row[0] if row else None,'purpose':SEQUENCE_PURPOSE,'current':current,
            'observation':'current_transaction_check','live_outbound_authority':'none'}

    def preview(self, organization, proposal_id):
        with self.database.connect() as db:
            db.execute('BEGIN')
            if db.execute('PRAGMA user_version').fetchone()[0]<22: raise Conflict('Migrate the live store before reviewing sequences')
            proposal = self.proposals.get(db,organization,proposal_id)
            subject = sequence_subject(organization,proposal_id,proposal,self._basis(db,organization))
            return self._view(db,organization,subject)

    def _view(self, db, organization, subject):
        report = self._report(db,organization,subject)
        latest = db.execute('SELECT id FROM sequence_review_decisions WHERE organization=? AND proposal_id=? ORDER BY rowid DESC LIMIT 1',
            (organization,subject['proposal_id'])).fetchone()
        approval = self._decision(db,organization,latest[0]) if latest else None
        valid = False
        if approval and approval['subject_id']==subject['id']:
            try:
                self.authorize(db,organization,subject['proposal_id'],approval['id'])
                valid = True
            except (ValueError,NotFound): pass
        # Approval inspection can itself cross an expiry boundary after _report.
        report = sequence_validation(subject,report['checks'],self.proposals._now())
        valid = bool(valid and report['review_ready'] and approval['at']<=report['evaluated_at']<approval['expires_at'])
        summary = sequence_summary(subject,report) if report['review_ready'] else None
        return {'subject_id':subject['id'],'proposal_id':subject['proposal_id'],'validation':report,
            'sequence':subject['sequence'] if report['review_ready'] else None,'summary':summary,
            'content_withheld':not report['review_ready'],'authority':'none','purpose':SEQUENCE_PURPOSE,
            'approval':approval,'approval_valid':valid}

    def view(self, organization, subject_id):
        with self.database.connect() as db:
            db.execute('BEGIN'); subject = self._subject(db,organization,subject_id)
            return self._view(db,organization,subject)

    def validate_output(self, organization, subject_id, output):
        with self.database.connect() as db:
            db.execute('BEGIN'); subject = self._subject(db,organization,subject_id)
            return validate_sequence_output(subject,self._ready(db,organization,subject),output)
