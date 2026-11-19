"""Frozen preparation, current evidence and atomic channel artifact/task publication."""

from dataclasses import asdict
from datetime import datetime, timezone
import json

from acquisition.campaigns import contact_readiness_boundaries
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import ExecutionOwnership
from acquisition.creative import (ChannelContentRequest, PAUSED_CHANNEL_ADMISSION, channel_source_payloads, channel_tool_contracts,
    validate_channel_context, channel_recipient_wording, recipient_fact_from, validate_rendered_channel,
    validate_channel_screen, channel_arguments, synthetic_channel_policy, channel_readiness_boundaries,
    recipient_readiness_boundaries, CHANNEL_CONTENT_CAPABILITY as CAPABILITY, CHANNEL_FRAMES as FRAMES)
from acquisition.reasoning import source_manifest, freeze_assets
from acquisition.runtime import TaskSpec, Outcome, LeaseLost
from .creative import read_context
from .tasks import SqliteTasks, event, admission_paused
from .database import stored_plan_hash
from .admissions import commit_admission, persist_workflow_request
from .admission_guard import (
    CHANNEL_OWNERSHIP_EVENT, CHANNEL_OWNERSHIP_KEY, binding, channel_reconciliation,
    read_channel_run, require_channel_run, verified_required,
)


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
    def __init__(self, recipients, profiles, profile_key, catalogue, memory, config, clock, compose_admission, *,
                 read_only=False):
        self.recipients, self.profiles, self.profile_key = recipients, profiles, profile_key
        self.database = recipients.contacts.database
        self.compose_admission = compose_admission
        self.catalogue, self.memory, self.config, self.clock, self.read_only = catalogue, memory, config, clock, read_only

    def _now(self): return self.recipients.contacts._now()
    def _writable(self, db):
        if self.read_only or verified_required(db): raise Conflict('Channel preparation has no verified execution capability; execution stays paused')

    def _recipients(self, db, organization, command, *, lineage=None, now=None, boundaries=None):
        result = []
        for request_id in command.recipient_requests:
            view = self.recipients._inspection(db,organization,request_id,now=now)
            if not view['currently_applicable']: raise Conflict('Recipient context is historical or no longer applicable')
            saved = view['saved']; basis = saved['basis']; context = view['current']
            if not basis['eligible'] or basis['channel']!=command.channel: raise Conflict('Recipient has no current channel readiness')
            source, report, profile = self.recipients.contacts.decision_evidence(db,organization,basis['assessment_id'],now=now)
            if profile.key!=command.profile_key: raise Conflict('Recipient belongs to a different product profile')
            person = next(p for p in source.contacts if p.ref.id==saved['request']['contact_id'])
            account = next(a for a in source.accounts if a.ref.id==person.accounts[0].id)
            row = db.execute('SELECT * FROM recipient_context_sources WHERE organization=? AND id=?',
                             (organization,saved['manifest_id'])).fetchone()
            manifest = self.recipients._manifest(row,organization,attest=True)
            if boundaries is not None:
                boundaries.extend(contact_readiness_boundaries((source,)))
                boundaries.extend(recipient_readiness_boundaries((manifest,)))
            if lineage is not None:
                assessment = self.recipients.contacts.assessment(db,organization,basis['assessment_id'])
                if assessment['request']['source_id']!=source.id:
                    raise Conflict('Channel admission requires assessment of the exact current source version')
                assessment_keys = self._assessment_keys(db,organization,basis['assessment_id'],assessment)
                lineage.append({'request_id':request_id,'context_id':view['context_id'],
                                'assessment_id':basis['assessment_id'],'assessment_request_ids':assessment_keys,
                                'source_id':source.id,
                                'connection_id':source.connection.id,'source_version':source.version,
                                'manifest_id':saved['manifest_id']})
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

    @staticmethod
    def _assessment_keys(db, organization, assessment_id, assessment):
        receipt = {'kind':'contact_assessment_prepared','assessment_id':assessment_id,'report':assessment['report']}
        keys = [r[0] for r in db.execute("""SELECT request_id FROM contact_commands
            WHERE organization=? AND inputs=? AND receipt=? ORDER BY request_id""",
            (organization,canonical(assessment['request']),canonical(receipt)))]
        if not keys:
            raise Conflict('Channel ownership requires the original native assessment receipt')
        return keys

    def _current(self, db, organization, context, *, lineage=None, verified_origin=False, now=None, boundaries=None):
        from .sequence_journeys import require_channel_context_origin
        now = self._now() if now is None else now
        validate_channel_context(context,organization,datetime.fromtimestamp(now,timezone.utc).date())
        origins = [] if lineage is not None else None
        if not verified_origin:
            require_channel_context_origin(db,organization,context,recipient_origins=origins)
        command = ChannelContentRequest(**(context['command'] | {'recipient_requests':tuple(context['command']['recipient_requests'])}))
        profile = self.profiles.campaign_profile(organization,command.profile_key,'v1')
        product = self.profiles.product_profile(organization,profile.product_profile_id)
        if (profile.id!=context['campaign_profile_id'] or canonical(asdict(product))!=canonical(context['product_profile'])
                or self.profiles.product_material(organization,product.id)['pack']!=context['product_facts']
                or self._recipients(db,organization,command,lineage=lineage,now=now,boundaries=boundaries)!=context['recipients']):
            raise Conflict('Channel sources changed from the exact frozen inputs')
        if lineage is not None:
            for record, origin in zip(lineage,origins,strict=True):
                record['origin']=origin

    def _artifact(self, db, organization, identity):
        row = db.execute('SELECT payload FROM channel_artifacts WHERE organization=? AND id=?',(organization,identity)).fetchone()
        if row is None: raise NotFound('Channel artifact is unavailable in this organization')
        value = json.loads(row[0])
        if value['organization']!=organization or identity!='channel_bundle_'+digest(value): raise Conflict('Channel artifact integrity failure')
        return value

    @staticmethod
    def _owner(organization, request_id, origin):
        if origin is not None:
            return ExecutionOwnership('conversation',origin['organization'],origin['conversation_id'],origin['revision'])
        root = 'channel_operation_'+digest({'organization':organization,'request_id':request_id})
        return ExecutionOwnership('standalone',organization,root)

    def _parent_proof(self, db, organization, artifact_id, ancestors=()):
        # Legacy rewrites have no declared standalone root. Prove each original
        # parent in order and retain the initial operation as the root.
        if artifact_id in ancestors or len(ancestors)>=20:
            raise Conflict('Channel rewrite ancestry is cyclic or too deep')
        artifact = self._artifact(db,organization,artifact_id)
        row = db.execute("""SELECT p.*, r.request_hash, r.request_id AS runtime_key
            FROM channel_artifacts a JOIN channel_preparations p
                ON p.organization=a.organization AND p.run_id=a.run_id
            JOIN runs r ON r.organization=p.organization AND r.id=p.run_id
            JOIN tasks t ON t.run_id=r.id AND t.position=0
            WHERE a.organization=? AND a.id=? AND r.status='succeeded' AND t.status='succeeded'
                AND t.capability=? AND json_extract(t.output,'$.artifact_id')=?""",
            (organization,artifact_id,CAPABILITY,artifact_id)).fetchone()
        if (row is None or row['context_id']!=artifact['context_id']
                or row['runtime_key']!='channel:'+row['request_id']
                or row['request_hash']!=stored_plan_hash(db,row['run_id'])):
            raise Conflict('Rewrite requires the exact completed parent channel run')
        context = read_context(db,organization,row['context_id'])
        lineage = []
        self._current(db,organization,context,lineage=lineage)
        admitted = binding(db,organization,row['run_id'])
        if admitted is not None:
            owner = admitted.ownership
        else:
            inputs = {'workflow_version':'channel-content/v1','context_id':row['context_id'],
                      'model_config':context['model_config']}
            origin = context.get('journey')
            if origin is not None:
                inputs['journey']=origin
            if (row['request_hash']!=digest([asdict(TaskSpec(CAPABILITY,inputs,max_attempts=3))])
                    or row['request_id']!=context['preparation_request_id']
                    or row['inputs']!=canonical(context['command'])):
                raise Conflict('Legacy parent differs from its exact channel preparation')
            owner = self._owner(organization,row['request_id'],origin)
            link = db.execute('SELECT owner_organization,conversation_id,revision FROM execution_runs '
                              'WHERE organization=? AND run_id=?',(organization,row['run_id'])).fetchone()
            expected_link = (owner.organization,owner.scope_id,owner.revision) if origin else None
            if (tuple(link) if link else None)!=expected_link:
                raise Conflict('Parent accounting link differs from its ownership')
            prior = context['command']['parent_id']
            if prior is not None:
                older = ExecutionOwnership(**self._parent_proof(db,organization,prior,ancestors+(artifact_id,))['owner'])
                if older.kind!=owner.kind or (origin and older!=owner):
                    raise Conflict('Legacy rewrite differs from its parent ownership')
                owner = older
        return {'run_id':row['run_id'],'plan_fingerprint':row['request_hash'],'artifact_id':artifact_id,
                'context_id':row['context_id'],'owner':asdict(owner)}

    def _admission_source(self, db, organization, request_id, command, context, lineage):
        from acquisition.conversations import journey_commands
        from .sequence_journeys import require_journey
        if context['model_config']!=self.config.payload():
            raise Conflict('Channel model settings changed before admission commit')
        origin = context.get('journey')
        owner = self._owner(organization,request_id,origin)
        parent = self._parent_proof(db,organization,command.parent_id) if command.parent_id else None
        if parent is not None:
            inherited = ExecutionOwnership(**parent['owner'])
            if inherited.kind!=owner.kind or (origin is not None and inherited!=owner):
                raise Conflict('Channel inputs and parent have different execution owners')
            owner = inherited
        permission = {'mode':'SYNTHETIC_ONLY','request_id':request_id,'command_fingerprint':digest(context['command']),
                      'model_config':context['model_config']}
        if origin is not None:
            journey = require_journey(db,origin['organization'],origin['journey_id'])['inputs']
            if (journey['mode']!='SYNTHETIC_ONLY' or journey['model_config']!=context['model_config']):
                raise Conflict('Channel configuration differs from the original journey consent')
            commands = journey_commands(origin['journey_id'])
            key = commands['email-assessment' if command.channel=='email' else 'call-assessment']
            if any(key not in item['assessment_request_ids'] for item in lineage):
                raise Conflict('Channel inputs differ from the original journey assessment receipts')
            permission['journey_id']=origin['journey_id']
        return {'schema':'paused-channel-source/v1','organization':organization,'owner':asdict(owner),
                'recipients':lineage,'parent':parent,'permission':permission}

    def _admit_owned(self, db, organization, request_id, command, context, identity, lineage, inputs):
        source = self._admission_source(db,organization,request_id,command,context,lineage)
        intent = self.compose_admission(organization,request_id,source,identity,context)
        # The validated native receipt and source are positive evidence for
        # each recipient. A bound input must identify the original revision.
        owner = ExecutionOwnership(**source['owner'])
        recipient_owners = [self._owner(organization,request_id,item['origin']) if item['origin']
                            else owner if owner.kind=='standalone' else None for item in lineage]
        intent.validate_source_ownership(recipient_owners)
        if source['parent'] is not None:
            parent = source['parent']
            intent.validate_parent(organization=organization,run_id=parent['run_id'],
                                   ownership=ExecutionOwnership(**parent['owner']))
        if db.execute('SELECT 1 FROM runs WHERE organization=? AND request_id=?',
                      (organization,'channel:'+request_id)).fetchone():
            raise Conflict('Existing channel work retains its original admission')
        now = self._now()
        kind = 'paused-channel' if intent.workflow_version==PAUSED_CHANNEL_ADMISSION else 'synthetic-channel'
        persist_workflow_request(db,intent,{'kind':kind,'operation_key':'channel:'+request_id,
                                           'command':json.loads(inputs)},source,now)
        receipt = commit_admission(db,intent,now)
        db.execute('INSERT INTO channel_preparations VALUES(?,?,?,?,?)',
                   (organization,request_id,inputs,receipt.run_id,identity))
        if binding(db,organization,receipt.run_id)!=intent:
            raise Conflict('Channel ownership was not committed with its preparation')
        current_lineage = []
        self._current(db,organization,context,lineage=current_lineage)
        if self._admission_source(db,organization,request_id,command,context,current_lineage)!=source:
            raise Conflict('Channel provenance changed before admission commit')
        return receipt.run_id

    def admit(self, organization, request_id, command):
        from .sequence_journeys import journey_command, channel_journey_origin
        from acquisition.audiences import bounded
        bounded(request_id)
        inputs = canonical(asdict(command))
        with self.database.transaction() as db:
            self._writable(db)
            old = db.execute('SELECT * FROM channel_preparations WHERE organization=? AND request_id=?',
                             (organization,request_id)).fetchone()
            if old:
                if old['inputs']!=inputs: raise Conflict('Channel request already binds different exact inputs')
                if binding(db,organization,old['run_id']) is None:
                    if channel_reconciliation(db,organization,old['run_id']) is not None:
                        read_channel_run(db,organization,old['run_id'],old['context_id'])
                    else:
                        journey_command(db,organization,request_id)
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
            origin=channel_journey_origin(db,organization,request_id,command)
            if origin is not None:context['journey']=origin
            kinds = {'guidance':'authored_guidance','product':'product_evidence','recipients':'recipient_evidence',
                     'policy':'channel_policy','preferences':'reviewer_preference'}
            payloads = channel_source_payloads(context)
            sources = [source_manifest(organization,key,kind,payloads[key],'v1','Frozen channel preparation.',
                'Rechecked at artifact creation.') for key,kind in kinds.items()]
            skill = 'contextual-email/v1' if command.channel=='email' else 'call-guidance/v1'
            context['agent_assets'] = freeze_assets(organization,self.catalogue,channel_tool_contracts(command.channel),[skill],sources,
                                                   model_projection='channel-context/v1')
            lineage = []
            self._current(db,organization,context,lineage=lineage)
            identity = 'context_'+digest({'organization':organization,**context})
            existing = db.execute('SELECT payload FROM creative_contexts WHERE organization=? AND id=?',(organization,identity)).fetchone()
            if existing is None: db.execute('INSERT INTO creative_contexts VALUES(?,?,?)',(organization,identity,canonical(context)))
            elif existing[0]!=canonical(context): raise Conflict('Channel context identity collision')
            run_id = self._admit_owned(db,organization,request_id,command,context,identity,lineage,inputs)
            self._writable(db)
            return run_id

    def load(self, organization, context_id, *, run_id=None):
        with self.database.connect() as db:
            db.execute('BEGIN')
            if run_id is None:
                context = read_context(db,organization,context_id)
                preparation = db.execute('SELECT run_id FROM channel_preparations WHERE organization=? AND request_id=?',
                                         (organization,context['preparation_request_id'])).fetchone()
                if preparation is None:
                    raise Conflict('Channel context has no admitted preparation')
                run_id = preparation['run_id']
            return self._current_run(db,organization,run_id,context_id)

    def _current_run(self, db, organization, run_id, context_id):
        context = require_channel_run(db,organization,run_id,context_id)
        self._current(db,organization,context,verified_origin=True)
        return context

    def require_execution(self, db, organization, run_id, context_id):
        self._writable(db)
        context = require_channel_run(db,organization,run_id,context_id,execution_config=self.config)
        checked_at = self._now()
        boundaries = list(channel_readiness_boundaries((context,)))
        self._current(db,organization,context,verified_origin=True,now=checked_at,boundaries=boundaries)
        starts = max(point for point in boundaries if point<=checked_at)
        ends = min(point for point in boundaries if point>checked_at)
        return context, (starts,ends)

    def recheck_evidence(self, db, organization, checked, now):
        context, (starts,ends) = checked
        # The same SQLite transaction holds the checked sources. Only crossing
        # a time boundary can change their validity at this later timestamp.
        if not starts<=now<ends:
            self._current(db,organization,context,verified_origin=True,now=now)

    def publish(self, db, claim, result):
        context_id = claim.inputs['context_id']
        context, _ = self.require_execution(db,claim.organization,claim.run_id,context_id)
        validate_rendered_channel(context,context_id,result['proposals'],result['rendered'])
        validate_channel_screen(result['screen'],result['rendered'])
        if type(result['attempt']) is not int or result['attempt'] not in (0,1): raise Conflict('Invalid repair attempt')
        for stage, tool_name, expected in (('proposal','submit_contextual_email' if context['command']['channel']=='email' else 'submit_call_guidance',
                {'context_id':context_id,'rows':result['proposals']}),('screen','record_channel_screen',result['screen'])):
            row = db.execute('SELECT status,response FROM model_calls WHERE organization=? AND run_id=? AND call_key=?',
                (claim.organization,claim.run_id,context_id+':channel:'+stage+':'+str(result['attempt']))).fetchone()
            if row is None or row['status']!='recorded': raise Conflict('Channel content lacks its completed inference receipts')
            actual = channel_arguments(json.loads(row['response']),tool_name)
            if stage=='proposal': actual['rows'] = sorted(actual['rows'],key=lambda r:r['recipient_context_id'])
            if actual!=expected: raise Conflict('Channel result differs from recorded model observations')
        payload = {'schema':'channel-bundle/v1','mode':'SYNTHETIC_ONLY','organization':claim.organization,
            'context_id':context_id,'rendered':result['rendered'],'screen':result['screen'],
            'screen_status':'passed_advisory_not_approval','status':'validated_unapproved','parent_id':context['command']['parent_id'],
            'approval':'not_granted','outcome_support':'none','execution':'not_performed','authority':'none'}
        identity = 'channel_bundle_'+digest(payload)
        db.execute('INSERT INTO channel_artifacts VALUES(?,?,?,?)',(claim.organization,identity,claim.run_id,canonical(payload)))
        self._current_run(db,claim.organization,claim.run_id,context_id)
        return {'artifact_id':identity,'status':'validated_unapproved','authority':'none'}

    def _historical_ownership(self, db, organization, run_id, ancestors=()):
        from .sequence_journeys import require_channel_context_origin, saved_journey

        if run_id in ancestors or len(ancestors)>=20:
            raise Conflict('Channel rewrite ancestry is cyclic or too deep')
        preparation,context,intent = read_channel_run(db,organization,run_id)
        if intent is not None:
            return intent.ownership, {'admission_id':intent.id,'fingerprint':intent.fingerprint}
        require_channel_context_origin(db,organization,context,current=False)
        command = context['command']
        lineage = []
        contacts = self.recipients.contacts
        for key,recipient in zip(command['recipient_requests'],context['recipients'],strict=True):
            receipt = db.execute('SELECT inputs,receipt FROM recipient_context_commands '
                                 'WHERE organization=? AND request_id=?',(organization,key)).fetchone()
            if receipt is None or key!=recipient['request_id']:
                raise Conflict('Restore the original channel recipient request')
            context_id = recipient['context_id']
            saved = self.recipients._saved(db,organization,context_id)
            expected = {'kind':'recipient_context_prepared','context_id':context_id,
                        'context':saved['context'],'source_selection':saved['source_selection']}
            if (json.loads(receipt['receipt'])!=expected
                    or json.loads(receipt['inputs'])!={'kind':'recipient-context-prepare/v1','request':saved['request']}
                    or saved['basis']['channel']!=command['channel']
                    or saved['request']['contact_id']!=recipient['contact_id']):
                raise Conflict('Historical channel recipient differs from its native receipt')
            assessment_id = saved['request']['assessment_id']
            assessment = contacts.assessment(db,organization,assessment_id)
            source = db.execute('SELECT * FROM contact_sources WHERE organization=? AND id=?',
                                (organization,assessment['request']['source_id'])).fetchone()
            if source is None:
                raise Conflict('Restore the original contact source')
            snapshot = contacts._snapshot(source,organization,assessment['connection_key'])
            if snapshot.id!=contacts.source.identity(organization,snapshot.connection.key,snapshot.version):
                raise Conflict('Historical channel source differs from its installed attestation')
            keys = self._assessment_keys(db,organization,assessment_id,assessment)
            lineage.append({'request_id':key,'context_id':context_id,'assessment_id':assessment_id,
                            'assessment_requests':keys,'source_id':snapshot.id,'connection_id':snapshot.connection.id})
        if not lineage:
            raise Conflict('Channel ownership needs its original recipient evidence')

        origin = context.get('journey')
        if origin is not None:
            from acquisition.conversations import journey_commands
            journey = saved_journey(db,origin['organization'],origin['journey_id'])['inputs']
            journey_keys = journey_commands(origin['journey_id'])
            assessment = journey_keys['email-assessment' if command['channel']=='email' else 'call-assessment']
            if (journey['model_config']!=context['model_config']
                    or any(assessment not in recipient['assessment_requests'] for recipient in lineage)):
                raise Conflict('Historical channel inputs differ from the original journey consent or receipts')
        owner = self._owner(organization,preparation['request_id'],origin)
        parent_proof = None
        if command['parent_id'] is not None:
            parent = self._artifact(db,organization,command['parent_id'])
            row = db.execute("""SELECT a.run_id,p.context_id FROM channel_artifacts a JOIN runs r
                ON r.organization=a.organization AND r.id=a.run_id
                JOIN channel_preparations p ON p.organization=a.organization AND p.run_id=a.run_id
                JOIN tasks t ON t.run_id=r.id AND t.position=0
                WHERE a.organization=? AND a.id=? AND r.status='succeeded' AND t.status='succeeded'
                    AND json_extract(t.output,'$.artifact_id')=a.id""",
                (organization,command['parent_id'])).fetchone()
            if row is None or row['context_id']!=parent['context_id']:
                raise Conflict('Restore the original completed channel parent')
            inherited,proof = self._historical_ownership(db,organization,row['run_id'],ancestors+(run_id,))
            if inherited.kind!=owner.kind or (origin is not None and inherited!=owner):
                raise Conflict('Channel parent has different historical ownership')
            owner = inherited
            parent_proof = {'artifact_id':command['parent_id'],'context_id':parent['context_id'],
                            'run_id':row['run_id'],'proof':digest(proof)}
        account_proof = None
        if origin is not None:
            from .execution import require_account_evidence
            account = require_account_evidence(db,owner.organization,owner.scope_id,repair_links=True)
            if account.row is None:
                raise Conflict('Restore the original conversation execution account')
            account_proof = {'policy':account.row['policy'],'call_limit':account.row['call_limit'],
                             'stopped_through':account.recorded_stop,'current_revision':account.revision}
        proof = {'preparation':dict(preparation),'lineage':lineage,'origin':origin,
                 'parent':parent_proof,'account':account_proof}
        return owner,proof

    def _ownership_report(self, db, organization, run_id):
        run = db.execute('SELECT * FROM runs WHERE organization=? AND id=?',(organization,run_id)).fetchone()
        if run is None or not run['request_id'].startswith('channel:'):
            raise NotFound('Channel run is unavailable in this organization')
        report = {'schema':'channel-ownership-inspection/v1','organization':organization,'run_id':run_id,
                  'authority':'none'}
        try:
            owner,proof = self._historical_ownership(db,organization,run_id)
            resolved = channel_reconciliation(db,organization,run_id)
            if resolved is not None and resolved['ownership']!=asdict(owner):
                raise Conflict('Channel reconciliation differs from the proven original owner')
        except (Conflict,NotFound,KeyError,TypeError,ValueError):
            return report | {'status':'unresolved','ownership':None,'fingerprint':None}
        tasks = [dict(row) for row in db.execute('SELECT * FROM tasks WHERE run_id=? ORDER BY position',(run_id,))]
        calls = [dict(row) for row in db.execute('SELECT * FROM model_calls WHERE organization=? AND run_id=? '
                                                'ORDER BY call_key',(organization,run_id))]
        store = db.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchone()
        if store is None:
            return report | {'status':'unresolved','ownership':None,'fingerprint':None}
        evidence = {'store_id':store[0],'run':dict(run),'tasks':tasks,'calls':calls,'proof':proof,'owner':asdict(owner)}
        status = 'bound' if 'admission_id' in proof else 'legacy_reconciled' if resolved else 'legacy_proven'
        return report | {'status':status,'ownership':asdict(owner),'fingerprint':digest(evidence)}

    def ownership(self, organization, run_id):
        with self.database.connect() as db:
            db.execute('BEGIN')
            return self._ownership_report(db,organization,run_id)

    def reconcile_ownership(self, organization, run_id, fingerprint):
        with self.database.transaction() as db:
            self._writable(db)
            report = self._ownership_report(db,organization,run_id)
            previous = channel_reconciliation(db,organization,run_id)
            if previous is not None:
                if report['status']!='legacy_reconciled' or previous['fingerprint']!=fingerprint:
                    raise Conflict('Channel reconciliation differs from its original inspected evidence')
                return previous
            if report['status']!='legacy_proven' or report['fingerprint']!=fingerprint:
                raise Conflict('Inspect the exact proven legacy channel run before reconciliation')
            if db.execute("""SELECT 1 FROM tasks WHERE run_id=? AND status='running'
                UNION ALL SELECT 1 FROM model_calls WHERE organization=? AND run_id=? AND status='reserved'""",
                (run_id,organization,run_id)).fetchone():
                raise Conflict('Quiesce the run and record in-flight observations before reconciliation')
            row = db.execute("""SELECT p.context_id,r.request_hash FROM channel_preparations p
                JOIN runs r ON r.organization=p.organization AND r.id=p.run_id
                WHERE p.organization=? AND p.run_id=?""",(organization,run_id)).fetchone()
            store = db.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchone()
            receipt = {'schema':'channel-ownership-reconciliation/v1','organization':organization,'run_id':run_id,
                       'store_id':store[0],'fingerprint':fingerprint,'ownership':report['ownership'],
                       'context_id':row['context_id'],'plan_fingerprint':row['request_hash'],'authority':'none'}
            request = {'run_id':run_id,'fingerprint':fingerprint}
            db.execute('INSERT INTO execution_commands VALUES(?,?,?,?)',
                       (organization,CHANNEL_OWNERSHIP_KEY+run_id,canonical(request),canonical(receipt)))
            event(db,run_id,None,CHANNEL_OWNERSHIP_EVENT,receipt,self._now())
            confirmed = self._ownership_report(db,organization,run_id)
            if confirmed!=report | {'status':'legacy_reconciled'}:
                raise Conflict('Channel ownership evidence changed before reconciliation commit')
            self._writable(db)
            return receipt

    def inspect(self, organization, request_id):
        with self.database.connect() as db:
            db.execute('BEGIN')
            row = db.execute('SELECT * FROM channel_preparations WHERE organization=? AND request_id=?',(organization,request_id)).fetchone()
            if row is None: raise NotFound('Channel preparation is unavailable in this organization')
            run = db.execute('SELECT status FROM runs WHERE organization=? AND id=?',(organization,row['run_id'])).fetchone()
            artifact = db.execute('SELECT id FROM channel_artifacts WHERE organization=? AND run_id=?',(organization,row['run_id'])).fetchone()
            value = self._artifact(db,organization,artifact['id']) if artifact else None
            try:
                self._current_run(db,organization,row['run_id'],row['context_id'])
                applicable=True
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

    def _admission_paused(self, db, organization, run_id):
        return admission_paused(db,organization,run_id,channel_config=self.content.config)

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
            checked = self.content.require_execution(db,claim.organization,claim.run_id,claim.inputs['context_id'])
            publication_time = self.content._now()
            if publication_time>=row['lease_until']: raise LeaseLost('Channel publication lease expired before commit')
            self.content.recheck_evidence(db,claim.organization,checked,publication_time)
