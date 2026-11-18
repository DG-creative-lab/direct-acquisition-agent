"""Compose existing public capabilities for one revision-bound synthetic journey."""

from dataclasses import dataclass
from collections.abc import Callable
from acquisition.audiences import ContactDirectory, AudienceDecisions
from acquisition.creative import RecipientContexts
from .channel_content import ChannelPreparation
from .sequences import SequenceSimulation

from acquisition.campaigns import SequenceRequest
from acquisition.contracts import Conflict, NotFound, digest
from acquisition.conversations import journey_commands, JOURNEY_STAGES


@dataclass(frozen=True)
class JourneyCapabilities:
    directory: ContactDirectory
    audiences: AudienceDecisions
    contexts: RecipientContexts
    channels: ChannelPreparation
    sequence: SequenceSimulation
    initialize_reviewers: Callable[[], None]


class SequenceJourneyWorkflow:
    def __init__(self,store,catalogue_source,capabilities):
        self.store,self.catalogue_source,self.capabilities=store,catalogue_source,capabilities

    def catalogue(self,organization):return self.catalogue_source(organization)

    def step(self,organization,row):
        frozen=row['inputs'];native=frozen['native_organization'];commands=journey_commands(row['id'])
        app=self.capabilities(frozen,False)
        if app.channels.inference.config.payload()!=frozen['model_config']:
            raise Conflict('Restore the original installed generation model and limits')
        outputs=dict(row['outputs']);profile=frozen['interpretation']['profile_key']
        if row['status']=='approving':
            intent=self.store.approval_intent(organization,row['id'])
            decision=app.sequence.reviews.decide(native,commands['review-approve'],intent['subject_id'],
                'local-reviewer','approve',intent['reason'],7*86400)
            return {'status':'approved','outputs':outputs|{'approval_id':decision['id']}}
        if row['status'] in {'approved','simulating'}:
            return self._simulate(organization,row,app)
        stage=JOURNEY_STAGES[row['stage']]
        if stage=='contacts':
            selected=next(p for p in frozen['catalogue']['profiles'] if p['key']==profile)
            connection=next(c for c in selected['connections'] if c['key']==frozen['interpretation']['connection_key'])
            source=app.directory.source.read(native,connection['key'],connection['version'])
            if source.id!=connection['source_id']:raise Conflict('The installed source differs from its frozen discovery identity')
            for channel,key in (('email','email-assessment'),('human_call','call-assessment')):
                report=app.directory.prepare(native,commands[key],connection['key'],connection['version'],channel)
                if not report['report']['ready_for_proposal']:raise Conflict('Current audience evidence is incomplete for '+channel)
                outputs[key]=report['assessment_id']
                outputs[channel+'-eligible']=report['report']['eligible']
        elif stage=='audience':
            budget=frozen['interpretation']['budget_pence']
            decision=app.audiences.prepare(native,commands['decision'],outputs['email-assessment'],
                budget_pence=budget,unit_cost_pence=104,max_candidates=min(6,budget//104),seed=42)
            if decision['decision']['plan']['status']!='complete':raise Conflict('The installed audience strategy could not produce a complete proposal')
            outputs['decision_id']=decision['decision_id']
        elif stage=='contexts':
            for channel,assessment in (('email','email-assessment'),('human_call','call-assessment')):
                eligible=sorted(outputs[channel+'-eligible'])
                if not 1<=len(eligible)<=6:raise Conflict('The complete source needs one to six eligible contacts per channel')
                keys=[]
                for index,contact_id in enumerate(eligible):
                    key=commands[channel+'-context-'+str(index)]
                    prepared=app.contexts.prepare(native,key,outputs[assessment],contact_id,'reviewed-context-a',1)
                    if prepared['context']['status'] not in {'ready','partial'}:
                        raise Conflict('Recipient context is unavailable for a required channel')
                    keys.append(key)
                outputs[channel+'-contexts']=keys
        elif stage in {'initial','call','followup'}:
            channel='human_call' if stage=='call' else 'email'
            parent=outputs.get('initial-artifact') if stage=='followup' else None
            run=app.channels.start(native,commands[stage],profile,outputs[channel+'-contexts'],channel,
                parent_id=parent,style='practical' if stage=='followup' else 'explore')
            view=app.channels.inspect(native,commands[stage])
            if not view['ready_for_review']:
                if any(c['status']=='unknown' for c in view['model_calls']):
                    raise Conflict('A generation outcome is unknown. The original paid-call fence prevents automatic repetition.')
                app.channels.worker.tick(native,run_id=run)
                view=app.channels.inspect(native,commands[stage])
            outputs[stage+'-run']=run
            if not view['ready_for_review']:
                if view['run_status'] in {'failed','cancelled'} or (view['run_status']!='running' and any(c['status'] in {'unknown','reserved'} for c in view['model_calls'])):
                    raise Conflict('Generation failed or remains uncertain. Inspect its original run; no replacement is admitted.')
                return {'outputs':outputs}
            outputs[stage+'-artifact']=view['artifact_id']
        elif stage=='review':
            request=SequenceRequest(profile,commands['decision'],commands['initial'],commands['call'],commands['followup'],
                frozen['created_at'],frozen['created_at']+7*86400,frozen['interpretation']['budget_pence'],6,18)
            proposal=app.sequence.campaigns.prepare(native,commands['sequence'],request)
            app.initialize_reviewers()
            opened=app.sequence.reviews.open(native,commands['review-open'],proposal['proposal_id'],'local-operator')
            review=app.sequence.reviews.view(native,opened['subject_id'])
            if not review['validation']['review_ready']:raise Conflict('The exact complete sequence is not ready for accountable review')
            outputs|={'proposal_id':proposal['proposal_id'],'subject_id':opened['subject_id']}
            return {'status':'ready','stage':row['stage']+1,'outputs':outputs}
        return {'stage':row['stage']+1,'outputs':outputs}

    def approve(self,organization,journey_id,request_id,revision,subject_id,reason):
        self.store.begin_approval(organization,journey_id,request_id,revision,subject_id,reason)
        # The durable confirmation owns continuation, even if the HTTP acknowledgement is lost.
        return {'journey_id':journey_id,'observation':'confirmation_saved','authority':'none'}

    def observe_task(self,organization,journey_id,request_id,revision,step_id):
        row=self.store.current(organization,journey_id)
        app=self.capabilities(row['inputs'],True)
        simulation=app.sequence.engagements.inspect(row['inputs']['native_organization'],row['outputs']['simulation_id'])
        step=next((s for s in simulation['steps'] if s['id']==step_id),None)
        if not step or step['channel']!='human_call' or not step['submission'] or step['submission']['status']!='accepted':
            raise Conflict('Record completion only for the exact accepted synthetic human task')
        self.store.begin_task_observation(organization,journey_id,request_id,revision,step_id)
        return {'journey_id':journey_id,'observation':'task_observation_saved','authority':'none'}

    def _simulate(self,organization,row,app):
        native=row['inputs']['native_organization'];outputs=dict(row['outputs'])
        if 'simulation_id' not in outputs:
            started=app.sequence.engagements.start(native,row['id']+':simulation',outputs['proposal_id'],outputs['approval_id'])
            return {'status':'simulating','outputs':outputs|{'simulation_id':started['simulation_id']}}
        simulation_id=outputs['simulation_id']
        view=app.sequence.engagements.inspect(native,simulation_id)
        completed=set(outputs.get('task_observations',[]))
        for intent in self.store.task_intents(organization,row['id']):
            if intent['request_id'] in completed:continue
            step=next(s for s in view['steps'] if s['id']==intent['step_id'])
            app.sequence.engagements.observe(native,row['id']+':task:'+digest(intent['request_id'])[:24],simulation_id,
                step['id'],step['submission']['provider_effect_id'],'task_completed',intent['occurred_at'])
            completed.add(intent['request_id'])
        if completed:outputs['task_observations']=sorted(completed)
        view=app.sequence.engagements.advance(native,simulation_id,max_steps=6)
        if view['status'] in {'submissions_complete','historical_submissions_complete'}:
            return {'status':'complete','outputs':outputs,'detail':'Bounded synthetic submissions completed. Recipient replies and real calls were not fabricated.'}
        if view['status'] in {'paused','stopped'}:
            return {'status':'blocked','outputs':outputs,'detail':'The native simulation is '+view['status']+'. Inspect its saved state before any continuation.'}
        if any(s['status'] in {'unknown','partial','blocked'} for s in view['steps']):
            return {'status':'blocked','outputs':outputs,'detail':'The simulation is blocked or uncertain; no automatic repeat is permitted.'}
        # Native dependency rules determine when every remaining step needs a human observation.
        if view['status']=='waiting_for_human_completion':
            return {'status':'awaiting_human','outputs':outputs,'detail':'Accepted synthetic human call tasks need an explicit completion observation.'}
        self.store.advance_time(organization,row['id'])
        return {'status':'simulating','outputs':outputs,'detail':None}

    def inspect(self,organization,row):
        frozen=row['inputs'];current=self.store.current(organization,row['id'])['current']
        result={k:row[k] for k in ('id','status','stage','detail')}
        result|={'schema':'conversation-sequence-view/v1','conversation_id':frozen['conversation_id'],
            'revision':frozen['revision'],'request_id':frozen['request_id'],'current':current,
            'profile_key':frozen['interpretation']['profile_key'],'mode':'SYNTHETIC_ONLY',
            'interpretation':frozen['interpretation'],'allow_generation':frozen['allow_generation'],
            'outputs':row['outputs'],'authority':'none','review':None,'simulation':None,
            'clock':'Persisted synthetic simulation time, never live delivery authority.',
            'pending_task_steps':[i['step_id'] for i in self.store.task_intents(organization,row['id'])
                if i['request_id'] not in row['outputs'].get('task_observations',[])]}
        profile=next((p for p in frozen['catalogue']['profiles'] if p['key']==result['profile_key']),None)
        result['source']=next((c for c in profile['connections'] if c['key']==frozen['interpretation']['connection_key']),None) if profile else None
        if not current:
            if row['status'] not in {'clarification','unsupported','consent_required','blocked','cancelled'}:result['status']='historical'
            return result
        if not row['outputs'].get('subject_id'):return result
        app=self.capabilities(frozen,True);native=frozen['native_organization']
        review=app.sequence.reviews.view(native,row['outputs']['subject_id'])
        result['review']=review
        if review['validation']['review_ready']:
            commands=journey_commands(row['id'])
            # The exact review already exposes the selected executable payloads.
            # Do not duplicate full bundles for unselected contacts in chat.
            decision=app.audiences.inspect(native,commands['decision'])['saved']['decision']
            result['audience']=app.directory.inspect(native,decision['request']['assessment_id'])
        if row['outputs'].get('simulation_id'):
            result['simulation']=app.sequence.engagements.inspect(native,row['outputs']['simulation_id'])
        return result
