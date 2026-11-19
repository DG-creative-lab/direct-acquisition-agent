"""Independent current-source reconstruction and immutable sequence publication."""

from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import json

from acquisition.campaigns import SequenceRequest, build_sequence_proposal, sequence_text, sequence_time
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.creative import recipient_target_from
from .admission_guard import verified_required
from .engagement_stops import native_engagement_stop


SEQUENCES='''
CREATE TABLE IF NOT EXISTS sequence_proposals (
 organization TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS sequence_commands (
 organization TEXT NOT NULL,request_id TEXT NOT NULL,inputs TEXT NOT NULL,proposal_id TEXT NOT NULL,
 PRIMARY KEY(organization,request_id));
CREATE TABLE IF NOT EXISTS engagement_simulations (
 organization TEXT NOT NULL,id TEXT NOT NULL,proposal_id TEXT NOT NULL,configuration TEXT NOT NULL,
 PRIMARY KEY(organization,id),UNIQUE(organization,proposal_id));
CREATE TABLE IF NOT EXISTS engagement_enrollments (
 organization TEXT NOT NULL,id TEXT NOT NULL,simulation_id TEXT NOT NULL,experiment_unit TEXT NOT NULL,
 contact_id TEXT NOT NULL,account_id TEXT NOT NULL,arm TEXT NOT NULL,
 PRIMARY KEY(organization,id),UNIQUE(organization,simulation_id,experiment_unit));
CREATE TABLE IF NOT EXISTS engagement_steps (
 organization TEXT NOT NULL,id TEXT NOT NULL,simulation_id TEXT NOT NULL,enrollment_id TEXT NOT NULL,
 ordinal INTEGER NOT NULL,channel TEXT NOT NULL,contact_id TEXT NOT NULL,account_id TEXT NOT NULL,
 due_at REAL NOT NULL,status TEXT NOT NULL,token TEXT,lease_until REAL,intent TEXT NOT NULL,
 PRIMARY KEY(organization,id),UNIQUE(organization,enrollment_id,ordinal));
CREATE TABLE IF NOT EXISTS engagement_dispatches (
 organization TEXT NOT NULL,step_id TEXT NOT NULL,effect_key TEXT NOT NULL,request_hash TEXT NOT NULL,
 token TEXT NOT NULL,reserved_at REAL NOT NULL,receipt TEXT,
 PRIMARY KEY(organization,step_id),UNIQUE(organization,effect_key));
CREATE TABLE IF NOT EXISTS engagement_observations (
 organization TEXT NOT NULL,id TEXT NOT NULL,simulation_id TEXT NOT NULL,step_id TEXT NOT NULL,
 kind TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(organization,id),UNIQUE(organization,step_id,kind));
CREATE TABLE IF NOT EXISTS engagement_stops (
 organization TEXT NOT NULL,id TEXT NOT NULL,simulation_id TEXT,scope TEXT NOT NULL,subject_id TEXT NOT NULL,
 action TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS engagement_commands (
 organization TEXT NOT NULL,request_id TEXT NOT NULL,inputs TEXT NOT NULL,receipt TEXT NOT NULL,
 PRIMARY KEY(organization,request_id));
CREATE TABLE IF NOT EXISTS engagement_events (
 organization TEXT NOT NULL,id TEXT NOT NULL,simulation_id TEXT NOT NULL,payload TEXT NOT NULL,
 PRIMARY KEY(organization,id));
'''
for _table,_key in (('sequence_proposals','id'),('sequence_commands','request_id'),('engagement_simulations','id'),
    ('engagement_enrollments','id'),('engagement_observations','id'),('engagement_stops','id'),
    ('engagement_commands','request_id'),('engagement_events','id')):
    SEQUENCES+=f'''
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_update BEFORE UPDATE ON {_table} BEGIN SELECT RAISE(ABORT,'Immutable sequence history'); END;
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_delete BEFORE DELETE ON {_table} BEGIN SELECT RAISE(ABORT,'Immutable sequence history'); END;
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_replace BEFORE INSERT ON {_table}
 WHEN EXISTS(SELECT 1 FROM {_table} WHERE organization=NEW.organization AND {_key}=NEW.{_key})
 BEGIN SELECT RAISE(ABORT,'Immutable sequence history'); END;
'''
SEQUENCES+='''
CREATE TRIGGER IF NOT EXISTS engagement_step_inputs_immutable BEFORE UPDATE ON engagement_steps
 WHEN NEW.organization!=OLD.organization OR NEW.id!=OLD.id OR NEW.simulation_id!=OLD.simulation_id
 OR NEW.enrollment_id!=OLD.enrollment_id OR NEW.ordinal!=OLD.ordinal OR NEW.channel!=OLD.channel
 OR NEW.contact_id!=OLD.contact_id OR NEW.account_id!=OLD.account_id OR NEW.due_at!=OLD.due_at OR NEW.intent!=OLD.intent
 BEGIN SELECT RAISE(ABORT,'Immutable engagement step inputs'); END;
CREATE TRIGGER IF NOT EXISTS engagement_steps_immutable_delete BEFORE DELETE ON engagement_steps
 BEGIN SELECT RAISE(ABORT,'Immutable engagement step history'); END;
CREATE TRIGGER IF NOT EXISTS engagement_steps_immutable_replace BEFORE INSERT ON engagement_steps
 WHEN EXISTS(SELECT 1 FROM engagement_steps WHERE organization=NEW.organization AND
 (id=NEW.id OR (enrollment_id=NEW.enrollment_id AND ordinal=NEW.ordinal)))
 BEGIN SELECT RAISE(ABORT,'Immutable engagement step history'); END;
CREATE TRIGGER IF NOT EXISTS engagement_dispatch_inputs_immutable BEFORE UPDATE ON engagement_dispatches
 WHEN NEW.organization!=OLD.organization OR NEW.step_id!=OLD.step_id OR NEW.effect_key!=OLD.effect_key
 OR NEW.request_hash!=OLD.request_hash OR NEW.token!=OLD.token OR NEW.reserved_at!=OLD.reserved_at
 OR (OLD.receipt IS NOT NULL AND NEW.receipt IS NOT OLD.receipt)
 BEGIN SELECT RAISE(ABORT,'Immutable simulated dispatch observation'); END;
CREATE TRIGGER IF NOT EXISTS engagement_dispatches_immutable_delete BEFORE DELETE ON engagement_dispatches
 BEGIN SELECT RAISE(ABORT,'Immutable simulated dispatch history'); END;
CREATE TRIGGER IF NOT EXISTS engagement_dispatches_immutable_replace BEFORE INSERT ON engagement_dispatches
 WHEN EXISTS(SELECT 1 FROM engagement_dispatches WHERE organization=NEW.organization AND
 (step_id=NEW.step_id OR effect_key=NEW.effect_key))
 BEGIN SELECT RAISE(ABORT,'Immutable simulated dispatch history'); END;
PRAGMA user_version=21;
'''


def validate_sequence_schema(db):
    for table,columns in {
        'sequence_proposals':'organization,id,payload','sequence_commands':'organization,request_id,inputs,proposal_id',
        'engagement_simulations':'organization,id,proposal_id,configuration',
        'engagement_enrollments':'organization,id,simulation_id,experiment_unit,contact_id,account_id,arm',
        'engagement_steps':'organization,id,simulation_id,enrollment_id,ordinal,channel,contact_id,account_id,due_at,status,token,lease_until,intent',
        'engagement_dispatches':'organization,step_id,effect_key,request_hash,token,reserved_at,receipt',
        'engagement_observations':'organization,id,simulation_id,step_id,kind,payload',
        'engagement_stops':'organization,id,simulation_id,scope,subject_id,action,payload',
        'engagement_commands':'organization,request_id,inputs,receipt','engagement_events':'organization,id,simulation_id,payload'
    }.items(): db.execute('SELECT '+columns+' FROM '+table+' LIMIT 0')


class SqliteSequenceProposals:
    def __init__(self, channels, decisions, connections, clock, *, read_only=False):
        self.channels,self.decisions,self.connections,self.clock=channels,decisions,connections,clock
        self.database,self.contacts,self.read_only=channels.database,channels.recipients.contacts,read_only

    def _now(self):
        now=self.clock(); sequence_time(now); return now

    def writable(self, db):
        if self.read_only or verified_required(db): raise Conflict('Sequence simulation has no verified execution capability; execution stays paused')

    def _decision(self, db, organization, key):
        row=db.execute('SELECT * FROM contact_commands WHERE organization=? AND request_id=?',(organization,key)).fetchone()
        if row is None or json.loads(row['inputs']).get('kind')!='audience-decision/v1': raise NotFound('Audience decision is unavailable in this organization')
        decision=self.decisions._receipt(db,row,organization)['decision']
        source,report,profile=self.contacts.decision_evidence(db,organization,decision['request']['assessment_id'])
        batch=decision['feature_batch']
        if source.id!=batch['source_id'] or profile.id!=batch['profile_id'] or digest(report)!=batch['readiness_digest']:
            raise Conflict('Audience decision is historical')
        accounts={a.ref.id:a for a in source.accounts}; identities={}
        for person in source.contacts:
            if len(person.accounts)==1 and person.accounts[0].id in accounts:
                account=accounts[person.accounts[0].id]
                identities[person.ref.id]={'account_id':account.ref.id,'experiment_unit':account.experiment_unit,
                    'source_connection':asdict(person.ref.connection),'segment':account.segment}
        return decision,identities

    def _material(self, db, organization, key):
        row=db.execute('SELECT context_id,run_id FROM channel_preparations WHERE organization=? AND request_id=?',(organization,key)).fetchone()
        if row is None: raise NotFound('Channel preparation is unavailable in this organization')
        artifact=db.execute('SELECT id FROM channel_artifacts WHERE organization=? AND run_id=?',(organization,row['run_id'])).fetchone()
        if artifact is None: raise Conflict('Every channel needs completed validated content')
        bundle=self.channels._artifact(db,organization,artifact['id'])
        context=self.channels._current_run(db,organization,row['run_id'],row['context_id'])
        result=[]
        for rendered in bundle['rendered']:
            recipient=next(r for r in context['recipients'] if r['context_id']==rendered['recipient_context_id'])
            saved=self.channels.recipients._inspection(db,organization,recipient['request_id'])['saved']
            target=recipient_target_from(saved['basis']['target'])
            source,_,_=self.contacts.decision_evidence(db,organization,saved['basis']['assessment_id'])
            manifest_row=db.execute('SELECT * FROM recipient_context_sources WHERE organization=? AND id=?',
                (organization,saved['manifest_id'])).fetchone()
            manifest=self.channels.recipients._manifest(manifest_row,organization,attest=True)
            review_end=(datetime.fromisoformat(context['product_facts']['review_by']).replace(tzinfo=timezone.utc)+timedelta(days=1)).timestamp()
            windows=[source.expires_at,manifest['expires_at'],review_end]
            windows.extend(f['expires_at'] for f in recipient['facts'])
            windows.extend(p.expires_at for p in source.permissions if p.contact.id==target.contact.id
                           and p.channel==rendered['channel'] and p.purpose=='acquisition')
            windows.extend(p.expires_at for p in source.pressure if p.contact.id==target.contact.id)
            result.append({'bundle_id':artifact['id'],'context_id':row['context_id'],'rendered':rendered,
                'valid_until':min(windows),
                'target':{'contact_id':target.contact.id,'account_id':target.account.id,'experiment_unit':target.experiment_unit,
                          'profile_id':target.profile_id,'source_connection':asdict(target.contact.connection)}})
        return result

    def _assemble(self, db, organization, request_id, request):
        if request.profile_key!=self.channels.profile_key: raise Conflict('Use the installed scoped sequence profile')
        decision,identities=self._decision(db,organization,request.decision_request)
        # Compose engagement-owned native stops without changing frozen strategy assignments.
        for member in decision['plan']['allocations']:
            if member['arm']=='no_contact': continue
            account=identities[member['contact_id']]['account_id']
            if native_engagement_stop(db,self.contacts,organization,None,member['contact_id'],account)=='stopped':
                raise Conflict('Frozen treatment population contains an objected native recipient or account')
        materials={stage:self._material(db,organization,key) for stage,key in (
            ('initial',request.initial_content),('call',request.call_content),('followup',request.followup_content))}
        from .sequence_journeys import sequence_journey_origin
        sequence_journey_origin(db,organization,request_id,request)
        return build_sequence_proposal(organization,request_id,request,decision,materials,self.connections,identities)

    def get(self, db, organization, identity):
        sequence_text(identity)
        row=db.execute('SELECT payload FROM sequence_proposals WHERE organization=? AND id=?',(organization,identity)).fetchone()
        if row is None: raise NotFound('Sequence proposal is unavailable in this organization')
        value=json.loads(row[0])
        if value['organization']!=organization or identity!='sequence_proposal_'+digest(value): raise Conflict('Sequence proposal integrity failure')
        return value

    def current(self, db, organization, proposal):
        request=SequenceRequest(**proposal['request'])
        if self._now()>=request.expires_at: raise Conflict('Sequence schedule has expired')
        if self._assemble(db,organization,proposal['request_id'],request)!=proposal:
            raise Conflict('Sequence material differs from current exact sources')

    def current_step(self, db, organization, proposal, step):
        request=SequenceRequest(**proposal['request'])
        if self._now()>=request.expires_at: raise Conflict('Sequence schedule has expired')
        channel=step['channel']
        if asdict(self.connections[channel])!=step['connection']: raise Conflict('Sequence connection capability changed')
        key={'initial':request.initial_content,'call':request.call_content,'followup':request.followup_content}[step['stage']]
        materials=self._material(db,organization,key)
        if step['content'] not in materials: raise Conflict('Step content is no longer current for the exact recipient')

    def prepare(self, organization, request_id, request):
        from .sequence_journeys import journey_transaction
        sequence_text(request_id)
        with journey_transaction(self.database,organization,request_id) as db:
            self.writable(db)
            old=db.execute('SELECT * FROM sequence_commands WHERE organization=? AND request_id=?',(organization,request_id)).fetchone()
            if old:
                if old['inputs']!=canonical(asdict(request)): raise Conflict('Sequence request already binds different exact inputs')
                return {'proposal_id':old['proposal_id'],'saved':self.get(db,organization,old['proposal_id']),'observation':'historical_proposal','authority':'none'}
            proposal=self._assemble(db,organization,request_id,request); self.current(db,organization,proposal)
            identity='sequence_proposal_'+digest(proposal)
            db.execute('INSERT INTO sequence_proposals VALUES(?,?,?)',(organization,identity,canonical(proposal)))
            db.execute('INSERT INTO sequence_commands VALUES(?,?,?,?)',(organization,request_id,canonical(asdict(request)),identity))
            self.current(db,organization,proposal); self.writable(db)
            return {'proposal_id':identity,'saved':proposal,'observation':'prepared_proposal','authority':'none'}

    def inspect(self, organization, proposal_id):
        with self.database.connect() as db:
            db.execute('BEGIN'); proposal=self.get(db,organization,proposal_id)
            try: self.current(db,organization,proposal); applicable=True
            except (Conflict,NotFound,ValueError): applicable=False
            return {'proposal_id':proposal_id,'saved':proposal,'currently_applicable':applicable,'authority':'none'}
