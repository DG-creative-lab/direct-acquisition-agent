"""Frozen preparation, current evidence and atomic channel artifact/task publication."""

from dataclasses import asdict
from datetime import datetime, timezone
import json

from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.creative import (ChannelContentRequest, channel_source_payloads, channel_tool_contracts,
    validate_channel_context, channel_recipient_wording, recipient_fact_from, validate_rendered_channel,
    validate_channel_screen, channel_arguments, synthetic_channel_policy, CHANNEL_CONTENT_CAPABILITY as CAPABILITY, CHANNEL_FRAMES as FRAMES)
from acquisition.reasoning import source_manifest, freeze_assets
from acquisition.runtime import TaskSpec, Outcome, LeaseLost
from .creative import read_context
from .tasks import SqliteTasks, insert_run
from .execution import bind_run
from .admission_guard import verified_required


CHANNEL_CONTENT = '''
CREATE TABLE IF NOT EXISTS channel_preparations (
 organization TEXT NOT NULL,request_id TEXT NOT NULL,inputs TEXT NOT NULL,run_id TEXT NOT NULL,
 context_id TEXT NOT NULL,PRIMARY KEY(organization,request_id),UNIQUE(organization,run_id));
CREATE TABLE IF NOT EXISTS channel_artifacts (
 organization TEXT NOT NULL,id TEXT NOT NULL,run_id TEXT NOT NULL,payload TEXT NOT NULL,
 PRIMARY KEY(organization,id),UNIQUE(organization,run_id));
'''
for _table,_key in (('channel_preparations','request_id'),('channel_artifacts','id')):
    CHANNEL_CONTENT += f'''
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_update BEFORE UPDATE ON {_table} BEGIN SELECT RAISE(ABORT,'Immutable channel history'); END;
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_delete BEFORE DELETE ON {_table} BEGIN SELECT RAISE(ABORT,'Immutable channel history'); END;
CREATE TRIGGER IF NOT EXISTS {_table}_immutable_replace BEFORE INSERT ON {_table}
 WHEN EXISTS(SELECT 1 FROM {_table} WHERE organization=NEW.organization AND {_key}=NEW.{_key})
 BEGIN SELECT RAISE(ABORT,'Immutable channel history'); END;
'''
CHANNEL_CONTENT += 'PRAGMA user_version=20;'


def validate_channel_schema(db):
    db.execute('SELECT organization,request_id,inputs,run_id,context_id FROM channel_preparations LIMIT 0')
    db.execute('SELECT organization,id,run_id,payload FROM channel_artifacts LIMIT 0')


class SqliteChannelContent:
    def __init__(self, recipients, profiles, profile_key, catalogue, memory, config, clock, *, read_only=False):
        self.recipients, self.profiles, self.profile_key = recipients, profiles, profile_key
        self.database = recipients.contacts.database
        self.catalogue, self.memory, self.config, self.clock, self.read_only = catalogue, memory, config, clock, read_only

    def _now(self): return self.recipients.contacts._now()
    def _today(self): return datetime.fromtimestamp(self._now(),timezone.utc).date()
    def _writable(self, db):
        if self.read_only or verified_required(db): raise Conflict('Channel preparation has no verified execution capability; execution stays paused')

    def _recipients(self, db, organization, command):
        result = []
        for request_id in command.recipient_requests:
            view = self.recipients._inspection(db,organization,request_id)
            if not view['currently_applicable']: raise Conflict('Recipient context is historical or no longer applicable')
            saved = view['saved']; basis = saved['basis']; context = view['current']
            if not basis['eligible'] or basis['channel']!=command.channel: raise Conflict('Recipient has no current channel readiness')
            source, report, profile = self.recipients.contacts.decision_evidence(db,organization,basis['assessment_id'])
            if profile.key!=command.profile_key: raise Conflict('Recipient belongs to a different product profile')
            person = next(p for p in source.contacts if p.ref.id==saved['request']['contact_id'])
            account = next(a for a in source.accounts if a.ref.id==person.accounts[0].id)
            row = db.execute('SELECT * FROM recipient_context_sources WHERE organization=? AND id=?',
                             (organization,saved['manifest_id'])).fetchone()
            manifest = self.recipients._manifest(row,organization,attest=True)
            selected = []
            for item in context['selected']:
                observation = next(i for i in manifest['facts'] if i['fact_id']==item['fact_id'])
                fact = recipient_fact_from(observation['fact'])
                if fact.review_id!=item['review_id']: raise Conflict('Recipient provenance differs from selected observation')
                selected.append(item | {'wording':channel_recipient_wording(fact)})
            result.append({'request_id':request_id,'context_id':view['context_id'],'target_id':context['target_id'],
                'profile_id':profile.id,'contact_id':person.ref.id,'channel':command.channel,'segment':account.segment,
                'email':person.email,'phone':person.phone,'facts':selected,'context_status':context['status']})
        if len({r['contact_id'] for r in result})!=len(result): raise Conflict('One content payload per intended native recipient')
        return result

    def _current(self, db, organization, context):
        validate_channel_context(context,organization,self._today())
        command = ChannelContentRequest(**(context['command'] | {'recipient_requests':tuple(context['command']['recipient_requests'])}))
        profile = self.profiles.campaign_profile(organization,command.profile_key,'v1')
        product = self.profiles.product_profile(organization,profile.product_profile_id)
        if (profile.id!=context['campaign_profile_id'] or canonical(asdict(product))!=canonical(context['product_profile'])
                or self.profiles.product_material(organization,product.id)['pack']!=context['product_facts']
                or self._recipients(db,organization,command)!=context['recipients']):
            raise Conflict('Channel sources changed from the exact frozen inputs')

    def _artifact(self, db, organization, identity):
        row = db.execute('SELECT payload FROM channel_artifacts WHERE organization=? AND id=?',(organization,identity)).fetchone()
        if row is None: raise NotFound('Channel artifact is unavailable in this organization')
        value = json.loads(row[0])
        if value['organization']!=organization or identity!='channel_bundle_'+digest(value): raise Conflict('Channel artifact integrity failure')
        return value

    def admit(self, organization, request_id, command):
        from acquisition.audiences import bounded
        bounded(request_id)
        inputs = canonical(asdict(command))
        with self.database.transaction() as db:
            self._writable(db)
            old = db.execute('SELECT inputs,run_id FROM channel_preparations WHERE organization=? AND request_id=?',
                             (organization,request_id)).fetchone()
            if old:
                if old['inputs']!=inputs: raise Conflict('Channel request already binds different exact inputs')
                return old['run_id']
            if command.profile_key!=self.profile_key: raise Conflict('Use the installed scoped channel profile')
            profile = self.profiles.campaign_profile(organization,command.profile_key,'v1')
            product = self.profiles.product_profile(organization,profile.product_profile_id)
            recipients = self._recipients(db,organization,command)
            if command.parent_id is not None:
                parent = self._artifact(db,organization,command.parent_id)
                old_context = read_context(db,organization,parent['context_id'])
                if (old_context['campaign_profile_id']!=profile.id or old_context['command']['channel']!=command.channel
                        or {r['contact_id'] for r in old_context['recipients']}!={r['contact_id'] for r in recipients}):
                    raise Conflict('Rewrite must preserve its exact scoped recipient population and product')
            context = {'schema':'creative-context/v5','organization':organization,'preparation_request_id':request_id,
                'command':asdict(command),'campaign_profile_id':profile.id,'product_profile':asdict(product),
                'product_facts':self.profiles.product_material(organization,product.id)['pack'],
                'recipients':recipients,'channel_policy':synthetic_channel_policy(profile.key,product),
                'guidance':{'version':'grounded-channel/v1','frames':FRAMES,'authority':'none'},
                'preferences':self.memory.examples_snapshot(organization,tuple(sorted({r['segment'] for r in recipients}))),
                'model_config':self.config.payload()}
            context = json.loads(canonical(context))
            kinds = {'guidance':'authored_guidance','product':'product_evidence','recipients':'recipient_evidence',
                     'policy':'channel_policy','preferences':'reviewer_preference'}
            payloads = channel_source_payloads(context)
            sources = [source_manifest(organization,key,kind,payloads[key],'v1','Frozen channel preparation.',
                'Rechecked at artifact creation.') for key,kind in kinds.items()]
            skill = 'contextual-email/v1' if command.channel=='email' else 'call-guidance/v1'
            context['agent_assets'] = freeze_assets(organization,self.catalogue,channel_tool_contracts(command.channel),[skill],sources,
                                                   model_projection='channel-context/v1')
            self._current(db,organization,context)
            identity = 'context_'+digest({'organization':organization,**context})
            existing = db.execute('SELECT payload FROM creative_contexts WHERE organization=? AND id=?',(organization,identity)).fetchone()
            if existing is None: db.execute('INSERT INTO creative_contexts VALUES(?,?,?)',(organization,identity,canonical(context)))
            elif existing[0]!=canonical(context): raise Conflict('Channel context identity collision')
            spec = TaskSpec(CAPABILITY,{'workflow_version':'channel-content/v1','context_id':identity,'model_config':self.config.payload()},max_attempts=3)
            run_id = insert_run(db,organization,'channel:'+request_id,[spec],self._now())
            bind_run(db,organization,run_id,new_run=True)
            db.execute('INSERT INTO channel_preparations VALUES(?,?,?,?,?)',(organization,request_id,inputs,run_id,identity))
            self._current(db,organization,context)
            self._writable(db)
            return run_id

    def load(self, organization, context_id):
        with self.database.connect() as db:
            db.execute('BEGIN')
            context = read_context(db,organization,context_id)
            self._current(db,organization,context)
            return context

    def publish(self, db, claim, result):
        preparation = db.execute('SELECT context_id FROM channel_preparations WHERE organization=? AND run_id=?',
                                 (claim.organization,claim.run_id)).fetchone()
        if preparation is None or preparation['context_id']!=claim.inputs['context_id']: raise Conflict('Channel task differs from its admission')
        self._writable(db)
        context = read_context(db,claim.organization,preparation['context_id']); self._current(db,claim.organization,context)
        validate_rendered_channel(context,preparation['context_id'],result['proposals'],result['rendered'])
        validate_channel_screen(result['screen'],result['rendered'])
        if type(result['attempt']) is not int or result['attempt'] not in (0,1): raise Conflict('Invalid repair attempt')
        for stage, tool_name, expected in (('proposal','submit_contextual_email' if context['command']['channel']=='email' else 'submit_call_guidance',
                {'context_id':preparation['context_id'],'rows':result['proposals']}),('screen','record_channel_screen',result['screen'])):
            row = db.execute('SELECT status,response FROM model_calls WHERE organization=? AND run_id=? AND call_key=?',
                (claim.organization,claim.run_id,preparation['context_id']+':channel:'+stage+':'+str(result['attempt']))).fetchone()
            if row is None or row['status']!='recorded': raise Conflict('Channel content lacks its completed inference receipts')
            actual = channel_arguments(json.loads(row['response']),tool_name)
            if stage=='proposal': actual['rows'] = sorted(actual['rows'],key=lambda r:r['recipient_context_id'])
            if actual!=expected: raise Conflict('Channel result differs from recorded model observations')
        payload = {'schema':'channel-bundle/v1','mode':'SYNTHETIC_ONLY','organization':claim.organization,
            'context_id':preparation['context_id'],'rendered':result['rendered'],'screen':result['screen'],
            'screen_status':'passed_advisory_not_approval','status':'validated_unapproved','parent_id':context['command']['parent_id'],
            'approval':'not_granted','outcome_support':'none','execution':'not_performed','authority':'none'}
        identity = 'channel_bundle_'+digest(payload)
        db.execute('INSERT INTO channel_artifacts VALUES(?,?,?,?)',(claim.organization,identity,claim.run_id,canonical(payload)))
        self._current(db,claim.organization,context)
        return {'artifact_id':identity,'status':'validated_unapproved','authority':'none'}

    def inspect(self, organization, request_id):
        with self.database.connect() as db:
            db.execute('BEGIN')
            row = db.execute('SELECT * FROM channel_preparations WHERE organization=? AND request_id=?',(organization,request_id)).fetchone()
            if row is None: raise NotFound('Channel preparation is unavailable in this organization')
            run = db.execute('SELECT status FROM runs WHERE organization=? AND id=?',(organization,row['run_id'])).fetchone()
            artifact = db.execute('SELECT id FROM channel_artifacts WHERE organization=? AND run_id=?',(organization,row['run_id'])).fetchone()
            value = self._artifact(db,organization,artifact['id']) if artifact else None
            try: self._current(db,organization,read_context(db,organization,row['context_id'])); applicable=True
            except (Conflict,NotFound,ValueError): applicable=False
            return {'run_id':row['run_id'],'run_status':run['status'],'context_id':row['context_id'],
                'artifact_id':artifact['id'] if artifact else None,'saved':value,'currently_applicable':applicable,
                'ready_for_review':bool(value) and applicable,'authority':'none',
                'model_calls':[dict(r) for r in db.execute('SELECT call_key,status,error FROM model_calls WHERE organization=? AND run_id=?',
                    (organization,row['run_id']))]}


class SqliteChannelTasks(SqliteTasks):
    def __init__(self, store):
        super().__init__(store.database,execution_clock=store.clock); self.content = store

    def claim(self, *args, **kwargs):
        if self.content.read_only: raise Conflict('Channel inspection cannot claim work')
        return super().claim(*args,**kwargs)

    def cancel(self, *args, **kwargs):
        if self.content.read_only: raise Conflict('Channel inspection cannot cancel work')
        return super().cancel(*args,**kwargs)

    def settle(self, claim, outcome, now):
        with self.database.transaction() as db:
            row, _ = self._owned(db,claim,self.content._now())
            if (outcome.status!='succeeded' or row['capability']!=CAPABILITY or claim.capability!=CAPABILITY
                    or row['inputs']!=canonical(claim.inputs)):
                raise Conflict('Channel completion differs from the exact owned task')
            result = self.content.publish(db,claim,outcome.data)
            self.settle_in_transaction(db,claim,Outcome('succeeded',result),self.content._now())
            self.content._writable(db)
            self.content._current(db,claim.organization,read_context(db,claim.organization,claim.inputs['context_id']))
            if self.content._now()>=row['lease_until']: raise LeaseLost('Channel publication lease expired before commit')
