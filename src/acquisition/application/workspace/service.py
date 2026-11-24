"""Local interactive sandbox facade. Domain services retain decision authority."""

import csv
from io import StringIO
import json
import re
import threading
import time
from datetime import datetime, timezone

from acquisition.conversations import ACTIVE_PREPARATION, AudienceSelectionRejected, ActionNotSaved, pending_copy_clarification, EnvironmentIntent, FIXTURE_MESSAGE, TYPED_ACTION_ALIASES, action_alias
from acquisition.conversations import MessageRejectedConflict, MessageRejectedInvalid, MessageRejectedNotFound, postal_request, sequence_language
from .ports import WorkspaceStorageUnavailable, WorkspaceApplications, WorkspaceModelSessions
from .state import WorkspaceStateAccess
from .intake import WorkspaceIntake
from acquisition.youtube import route_youtube
from .views import WorkspaceViews, REVISION_BLOCKS, CHECKPOINT_BLOCKS, _partial_delivery
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.learning import finite, identifier
from acquisition.reasoning import ModelConfig
from acquisition.creative import validate_fact_pack, fixture_catalog, historical_hook
from acquisition.learning import followup_hypotheses
from acquisition.campaigns import FollowupBrief, build_draft, brief_from
from dataclasses import replace
from acquisition.reviews import ReviewPolicy, text, ActorUnavailable


class MonitoringRejected(ValueError):
    """A monitoring command was rejected before its domain transaction committed."""
    def __init__(self, message, not_saved=False):
        super().__init__(message)
        self.not_saved = not_saved


class Workspace(WorkspaceViews):
    def __init__(self, root, real_clock, *, applications: WorkspaceApplications, state_access: WorkspaceStateAccess, models: WorkspaceModelSessions, assets, lock,
                 legacy_preparations, owned_preparations, preparation_host, sequence_journeys, verified_admissions=False):
        if type(verified_admissions) is not bool:raise ValueError('Choose an explicit admission mode')
        self._requested_verified = verified_admissions
        self.real_clock = real_clock
        self.root = root
        self.lock = lock
        self.models = models
        self._applications = applications
        self._browser_tick = threading.Lock()
        self._state_access = state_access
        self.control_store = state_access.control
        self._storage_faults = state_access.storage_faults
        self._legacy_preparations = legacy_preparations
        self._owned_preparation_factory = owned_preparations
        self._owned_preparations = None
        self._sequence_journey_factory = sequence_journeys
        self._sequence_journeys = None
        self.preparation_host = preparation_host
        self._authority = None
        self.pack = assets['product_facts']
        self._knowledge = assets['knowledge']
        self.youtube_origin = 'http://127.0.0.1:8768'

    @property
    def authority(self):
        if self._authority is None:
            if self._requested_verified:self._verified_mode()
            self._authority=self._state_access.authority()
        return self._authority

    @property
    def preparations(self):
        if not self._verified_mode():return self._legacy_preparations
        if self._owned_preparations is None:
            self._owned_preparations=self._owned_preparation_factory()
        return self._owned_preparations

    def _sessions(self,*,reverse=False):
        verified=self._verified_mode()
        owned={s['id']:s for s in self.authority.listing()} if verified else {}
        rows = self.control_store.sessions(reverse=reverse)
        sessions=[]
        for row in rows:
            if row['id'] in owned:continue
            if not verified:
                sessions.append(json.loads(row['payload']))
                continue
            # Disposable rows cannot block or impersonate application-owned state.
            try:
                value=json.loads(row['payload'])
                if type(value) is not dict or value.get('id')!=row['id']:continue
                initial=value|{'run_id':None,'case_id':None,'cohort_id':None}
                initial.setdefault('database_scope','conversations' if value.get('conversation_plan') or value.get('organization')=='local-conversations' else 'campaign')
                EnvironmentIntent.freeze(initial)
                for key in ('run_id','case_id','cohort_id'):
                    if value[key] is not None:identifier(value[key])
                if 'conversation_plan' in value:
                    plan=value['conversation_plan']
                    if type(plan) is not dict:continue
                    for key in ('id','conversation_id'):identifier(plan[key])
                    if type(plan['revision']) is not int or plan['revision']<1:continue
                if 'audience_selection' in value and type(value['audience_selection']) is not dict:continue
            except (ValueError,TypeError,KeyError,OverflowError,RecursionError):continue
            sessions.append(value)
        if verified:
            rows={s['id']:s for s in sessions}
            rows.update(owned)
            sessions=sorted(rows.values(),key=lambda s:(s['created_at'],s['id']),reverse=reverse)
        return sessions

    def _project_session(self, session):
        self.control_store.project_session(session)

    def _legacy_collision(self, identity):
        if self.authority.get(identity) is None and self.control_store.session(identity) is not None:
            raise Conflict('Legacy sandbox intent requires explicit migration before verified creation')

    def _save(self, session):
        if self._verified_mode() and self.authority.get(session['id']) is not None:
            current=self.authority.save(session)
            self._project_session(current)
            return
        self.control_store.save_session(session)

    def _session(self, identity):
        identifier(identity)
        if self._verified_mode():
            current=self.authority.get(identity)
            if current is not None:return current
        row = self.control_store.session(identity)
        if row is None:
            raise NotFound("Campaign not found in this workspace")
        return json.loads(row["payload"])

    def _model_gateway(self, config):
        return self.models.gateway(config)

    def _app(self, session, with_model=False, *, revision_admission=False, model_config=None):
        verified=self._verified_mode()
        authoritative=self.authority.get(session['id']) if verified else None
        if authoritative is not None:session=authoritative
        gateway, config = None, None
        if (with_model or revision_admission) and session["mode"] == "model":
            validate_fact_pack(self.pack, datetime.fromtimestamp(self.real_clock(), timezone.utc).date())
            config = model_config or ModelConfig("openai/gpt-oss-120b", max_calls=10, force_tool_choice=True)
            if with_model and not verified:
                gateway = self._model_gateway(config)
        # Each sandbox has its own durable clock. Live generation starts at real
        # time; explicit outcome simulation alone can advance the sandbox clock.
        conversation_db = session.get("database_scope") == "conversations" or session.get("conversation_plan") or session["organization"] == "local-conversations"
        if verified and authoritative is None:
            if session['organization']!='local-conversations' and not re.fullmatch(r'workspace_[0-9a-f]{24}',session['organization']):
                raise Conflict('Legacy application scope is unavailable')
        clock=(lambda:self.authority.clock(session['id'],self.real_clock())) if authoritative is not None else self.real_clock if verified else (lambda:max(self.real_clock(),session['clock']) if session.get('clock_mode')=='REAL' else session['clock'])
        return self._applications.campaign(session['organization'], 'conversations' if conversation_db else 'campaign', clock,
                    verified=verified, legacy=authoritative is None, gateway=gateway, model_config=config)

    def _verified_mode(self):
        verified = self._applications.verified_mode(select=self._requested_verified)
        self._requested_verified = False
        return verified

    def listing(self):
        sessions=self._sessions(reverse=True)[:50]
        return {"sessions": [{k: s[k] for k in ("id", "name", "mode", "created_at", "case_id")} for s in sessions],
                "mode": "LOCAL_SYNTHETIC_SANDBOX", "hosted_authentication": False}

    def _conversation_app(self, with_model=False, *, model_config=None):
        # Scope and database location are server-owned, never model/browser input.
        verified=self._verified_mode()
        config = model_config or (self.models.selected(2) if with_model else None)
        gateway = self._model_gateway(config) if with_model and not verified else None
        return self._applications.conversation(verified=verified, gateway=gateway, model_config=config)

    @property
    def intake(self):
        return WorkspaceIntake(self._applications.intake(verified=self._verified_mode()))

    @property
    def youtube(self):
        return self._applications.youtube(verified=self._verified_mode(), origin=self.youtube_origin)

    def youtube_message(self, conversation_id, request_id, expected_revision, content, draft_permission='none'):
        receipt = self.youtube.message({'conversation_id': conversation_id, 'request_id': request_id,
            'expected_revision': expected_revision, 'content': content, 'draft_permission': draft_permission})
        return self.conversation(conversation_id) | {'message_receipt': receipt['result']['message_receipt']}

    def youtube_command(self, operation, command):
        app = self.youtube.campaigns
        receipt = app.command(operation, command)
        return app.read(command['campaign_id']) | {'command_receipt': receipt}

    def youtube_resume(self, operation_id, conversation_id):
        self.youtube.resume(operation_id, conversation_id)
        return self.conversation(conversation_id)

    def _is_youtube_request(self, conversation_id, revision, content):
        # Invalid legacy requests must retain their existing rejection contract.
        if type(content) is not str or not content.strip() or len(content) > 2000:
            return False
        try:
            rows = self.youtube.campaigns.interactions(conversation_id)
        except NotFound:
            return False
        return route_youtube(content, bound=bool(rows and rows[-1]['revision'] == revision)) != 'other'

    @property
    def sequence_journeys(self):
        if self._sequence_journeys is None:
            self._sequence_journeys = self._sequence_journey_factory()
        return self._sequence_journeys

    def _sequence_rows(self,conversation_id):
        return self.sequence_journeys.store.listing('local-conversations',conversation_id)

    def _sequence_message(self,conversation_id,request_id,expected_revision,content,allow_generation=True):
        rows=[row for row in self._sequence_rows(conversation_id) if row['inputs']['revision']==expected_revision]
        if postal_request(content) or (not rows and not sequence_language(content)):return None
        # These exact questions inspect the same proposal. Other text is a material
        # revision and cannot carry an earlier proposal's confirmation forward.
        stopping=bool(re.fullmatch(r'(?:stop|cancel)(?: (?:this|the) sequence)?[.! ]*',content.strip(),re.I))
        if rows and (stopping or re.fullmatch(r"(?:what(?:'s| is) (?:the )?status|status|show(?: me)?(?: the)? (?:proposal|sequence|progress)|inspect|help|approve|approve it)[?.! ]*",content.strip(),re.I)):
            self.sequence_journeys.store.interaction('local-conversations',conversation_id,rows[-1]['id'],
                request_id,expected_revision,content,stop=stopping)
            return self.conversation(conversation_id)
        row=self.sequence_journeys.send('local-conversations',conversation_id,request_id,expected_revision,content,allow_generation)
        return self.conversation(conversation_id)|{'message_receipt':{'id':request_id,'revision':row['inputs']['revision']}}

    def sequence_command(self,conversation_id,kind,journey_id,request_id,expected_revision,**fields):
        row=self.sequence_journeys.store.get('local-conversations',journey_id)
        if row['inputs']['conversation_id']!=conversation_id:raise NotFound('Sequence belongs to another conversation')
        if kind=='sequence-approve':
            self.sequence_journeys.approve('local-conversations',journey_id,request_id,expected_revision,**fields)
        elif kind=='sequence-stop':
            self.sequence_journeys.stop('local-conversations',journey_id,request_id,expected_revision)
        elif kind=='sequence-task-completed':
            self.sequence_journeys.observe_task('local-conversations',journey_id,request_id,expected_revision,**fields)
        elif kind=='sequence-replied':
            self.sequence_journeys.observe_reply('local-conversations',journey_id,request_id,expected_revision,**fields)
        else:raise ValueError('Unsupported sequence command')
        return self.conversation(conversation_id)

    def conversations(self):
        return {"conversations": self._conversation_app().conversations.store.listing("local-conversations")}

    def audience_catalogue(self, campaign_key=None):
        return self._conversation_app().audience_discovery.discover("local-conversations", campaign_key)

    def audience_dataset(self, dataset_id, version, checksum, manifest_id):
        return self._conversation_app().audience_discovery.inspect("local-conversations", dataset_id, version, checksum, manifest_id)

    def knowledge(self):
        return self._knowledge()

    def conversation(self, conversation_id):
        self._ensure_descendant_links()
        application = self._conversation_app()
        # Completion may publish a review mapping while progress is read. Sample
        # campaigns afterwards so a completed action cannot stop browser polling
        # with an older campaign row that still lacks its case.
        actions = self.action_progress(conversation_id)
        sessions=self._sessions(reverse=True)
        comments = []
        for session in sessions:
            if session.get('conversation_plan', {}).get('conversation_id') == conversation_id and session['case_id']:
                comments.extend(comment | {'session_id': session['id']} for comment in
                                application.reviews.store.comments(session['organization'], session['case_id']))
        # Observe preparation first. A fast zero-call clarification can finish
        # between reads; a terminal preparation must include its saved question.
        preparations = self.preparation_progress(conversation_id)
        view = application.conversations.view("local-conversations", conversation_id)
        return view | {"youtube_interactions": self.youtube.campaigns.interactions(conversation_id),
                       "sequence_journeys": self.sequence_journeys.listing("local-conversations",conversation_id),
                       "sequence_interactions": self.sequence_journeys.store.interactions("local-conversations",conversation_id),
                       "typed_action_shortcuts": list(TYPED_ACTION_ALIASES), "writing_preferences": application.memory.preferences('local-conversations'),
                       "artifact_comments": comments, "execution":application.execution.view('local-conversations',conversation_id), "actions":actions, "preparations": preparations, "campaigns": [{"session_id": s["id"], "plan_id": s["conversation_plan"]["id"],
                                      "revision": s["conversation_plan"]["revision"], "case_id": s["case_id"],
                                      "generation": self._generation(s)}
                                     for s in sessions if s.get("conversation_plan", {}).get("conversation_id") == conversation_id]}

    def comment_artifact(self, conversation_id, session_id, expected_subject, target_id, expected_revision, feedback, request_id):
        try:
            session = self._session(session_id)
            if session.get('conversation_plan', {}).get('conversation_id') != conversation_id or not session['case_id']:
                raise Conflict('Select an artifact from this conversation')
            self._app(session).reviews.store.comment(session['organization'], session['case_id'], expected_subject,
                target_id, conversation_id, expected_revision, feedback, 'local-operator', request_id)
        except Conflict as error:
            raise MessageRejectedConflict(str(error)) from error
        except NotFound as error:
            raise MessageRejectedNotFound(str(error)) from error
        except ValueError as error:
            raise MessageRejectedInvalid(str(error)) from error
        return self.conversation(conversation_id)

    def change_writing_preference(self, conversation_id, session_id, comment_id, preference_id, action,
                                  expected_revision, segments, preferred, avoid, reason, confirmed, request_id):
        try:
            session = self._session(session_id)
            if session.get('conversation_plan', {}).get('conversation_id') != conversation_id:
                raise Conflict('Select the original comment conversation')
            receipt = self._app(session).memory.change_preference('local-conversations', session['organization'],
                conversation_id, comment_id, preference_id, action, expected_revision, segments,
                preferred, avoid, reason, confirmed, 'local-operator', request_id, self.real_clock())
        except Conflict as error:
            raise MessageRejectedConflict(str(error)) from error
        except NotFound as error:
            raise MessageRejectedNotFound(str(error)) from error
        except ValueError as error:
            raise MessageRejectedInvalid(str(error)) from error
        return self.conversation(conversation_id) | {'preference_receipt': receipt}

    def action_context(self, conversation_id, expected_revision):
        app=self._conversation_app();source=app.conversations.view('local-conversations',conversation_id)
        if source['revision']!=expected_revision:raise Conflict('The brief changed before action admission')
        plan=source['current_plan']['result'] if source['current_plan'] else None
        sessions=self._sessions(reverse=True)
        session=next((s for s in sessions if s.get('conversation_plan',{}).get('conversation_id')==conversation_id
                      and s['conversation_plan']['revision']==expected_revision),None)
        review=self._app(session).reviews.store.view(session['organization'],session['case_id']) if session and session['case_id'] else None
        preparation=self.preparations.store.for_revision('local-conversations',conversation_id,expected_revision)
        partial = _partial_delivery(review)
        phase=preparation['status'] if preparation else 'not_started'
        if review and not review['validation_report']['review_ready']:phase='blocked'
        if review and review['handoff']:phase='simulated_accepted'
        if partial:phase='simulated_partially_accepted'
        labels={'selecting_audience':'awaiting audience confirmation','planning':'interpreting the brief',
                'preparing':'preparing the campaign','review_ready':'ready for human review','not_started':'not started',
                'admitting':'saving the preparation request','needs_input':'waiting for clarification',
                'needs_consent':'waiting for generation permission','blocked':'blocked pending inspection',
                'failed':'stopped after a failure','uncertain':'awaiting provider reconciliation',
                'stale':'stopped after a brief change','simulated_accepted':'accepted by the local handoff simulator',
                'simulated_partially_accepted':'partially accepted by the local handoff simulator'}
        refs={'plan_id':plan['id'] if plan else None,'session_id':session['id'] if session else None,
              'subject_id':review['subject']['id'] if review else None,'draft_id':review['subject']['draft_id'] if review else None}
        answers={'inspect_progress':{'text':'Preparation was '+labels.get(phase,phase.replace('_',' '))+' when this snapshot was recorded.',
                    'evidence':refs|{'status':phase,'preparation_id':preparation['id'] if preparation else None}}}
        if partial:
            answers['inspect_progress']['evidence']['delivery'] = partial
        selected=(review['manifest']['brief'].get('audience_source') if review else
                  app.conversation_audiences.store.get('local-conversations',conversation_id,expected_revision))
        counts=review['manifest']['counts'] if review else None
        if selected:
            audience_text=f"The confirmed synthetic audience is {selected['source']['title']}, version {selected['source']['version']}, with {selected['source']['record_count']} input records. Its segments match the proposed brief."
        elif review:
            audience_text=f"This campaign uses its original generated synthetic audience, with {counts['input']} input records."
        else:audience_text='A source audience has not been confirmed for this brief.'
        if counts:audience_text+=f" The validated draft has {counts['mailed']} mailed assignments and {counts['holdout']} no-mail controls."
        answers['explain_audience']={'text':audience_text,'evidence':refs|{'selection':selected,'counts':counts}}
        reasons=review['manifest']['exclusion_reasons'] if review else None
        explanation='The validated draft is not available yet, so exclusion counts have not been established.'
        if counts:
            explanation=f"The draft excluded {counts['excluded']} input records. "
            reason_labels={'duplicate_business':'duplicate business identity','suppressed':'suppression','product_scope':'outside supported country or entity type',
                'unusable_demo_address':'unusable demo address','missing_score':'missing supplied score','contact_cap':'contact frequency limit',
                'contact_cooldown':'recent contact cooldown','outside_selected_segment':'outside selected segment'}
            explanation+='Recorded reasons: '+', '.join(f"{reason_labels.get(k,k.replace('_',' '))}: {v}" for k,v in sorted(reasons.items()))+'.' if reasons else 'No exclusion reasons were recorded.'
        answers['explain_exclusions']={'text':explanation,'evidence':refs|{'counts':counts,'exclusion_reasons':reasons}}
        report=review['validation_report'] if review else None
        validation='No exact-draft validation report is available yet.'
        if report:
            blocked=[c['label'] for c in report['checks'] if c['required'] and c['status']!='passed']
            validation=('At the recorded check, required machine checks passed and the draft was ready for human review. Approval remains a separate decision.'
                        if report['review_ready'] else 'At the recorded check, review was blocked by: '+', '.join(blocked)+'.')
            if partial and report['review_ready']:
                validation = 'Required machine checks passed for the draft that received partial simulated acceptance.'
        answers['explain_validation']={'text':validation,'evidence':refs|{'report':report}}
        target={'organization':'local-conversations','conversation_id':conversation_id,'revision':expected_revision}
        target['id']='brief_target_'+digest(target)[:32]
        context={'schema':'routing-context/v3','target':target,'observed_at':self.real_clock(),'answers':answers,
                 'brief':{k:plan[k] for k in ('objective','segments','budget_pence','copy_mode')} if plan else None}
        copy_targets={'available':False,'reason':'Prepare a grounded model campaign before requesting copy revisions.', 'creatives':[]}
        if review and session['mode']=='model':
            revisions=self._app(session).revisions.view(session['organization'],session['case_id'])
            reason=('Accepted simulated campaigns cannot be revised.' if review['handoff'] or partial else
                    'Restore current evidence and a valid campaign before requesting a revision.' if not review['candidate_valid'] else
                    'A saved revision already owns this subject, or the three-revision limit was reached. Inspect the original request.'
                    if len(revisions)>=3 or any(r['base_subject_id']==review['subject']['id'] for r in revisions) else '')
            copy_targets|={'available':not reason,'reason':reason,'session_id':session['id'],'organization':session['organization'],
                'case_id':session['case_id'],'subject_id':review['subject']['id'],'draft_id':review['subject']['draft_id'],
                'creatives':[{k:c[k] for k in ('id','segment','arm','headline','opening')} for c in review['manifest']['creatives']]}
        context['copy_revision_targets']=copy_targets
        latest_response=next((p for p in reversed(source['plans']) if p['result']),None)
        action_exchange=[]
        for row in app.actions.store.listing('local-conversations',conversation_id):
            if row['inputs']['revision']!=expected_revision or row['confirmed']:continue
            action=app.actions.view('local-conversations',row)
            if action['result']:
                action_exchange.append({'action_id':row['id'],'content':row['inputs']['content'],
                    'response':{k:action['result'][k] for k in ('id','kind','text')}})
        clarifications=[]
        for exchange in reversed(action_exchange):
            if exchange['response']['kind']=='unsupported':break
            if exchange['response']['kind'] in {'clarify','amend_brief'}:clarifications.insert(0,exchange)
        copy_exchange=[]
        for row in app.actions.store.listing('local-conversations',conversation_id):
            if row['confirmed'] or row['inputs']['revision']!=expected_revision:continue
            old_targets=row['context'].get('copy_revision_targets',{})
            if not old_targets.get('subject_id') or old_targets.get('subject_id')!=copy_targets.get('subject_id'):continue
            action=app.actions.view('local-conversations',row)
            if action['result'] and action['result']['kind']=='revise_copy':
                if not pending_copy_clarification(action['result']['copy_revision']):
                    copy_exchange=[]
                else:
                    copy_exchange.append({'action_id':row['id'],'content':row['inputs']['content'],
                        'response':{k:action['result'][k] for k in ('id','kind','text')}})
        context['dialogue']={
            'version':'routing-dialogue/v4',
            'messages':[{k:m[k] for k in ('id','revision','role','content')} for m in source['messages'][-2:]],
            'action_exchange':action_exchange[-2:],
            'clarification_exchange':clarifications,
            'copy_exchange':copy_exchange,
            'planner_response':({'current':latest_response['revision']==expected_revision,
                **{k:latest_response['result'][k] for k in ('id','revision','outcome','question','unsupported_reason')}}
                if latest_response else None),
        }
        prepare_target = self._prepare_target(conversation_id, source, sessions)
        experiment = self._experiment_target(source, sessions)
        context['action_targets'] = {
            'prepare_campaign': {'target': prepare_target,
                'text': 'Confirm preparation of the saved brief.' if prepare_target else
                        'This brief already has preparation or needs more information. Inspect its saved progress.'},
            'propose_next_experiment': {'target': experiment,
                'text': 'Confirm a separate experiment proposal for ' + experiment['label'] + '.' if experiment else
                        'A next experiment needs one current campaign with finalized synthetic learning. Open its review to check the source.'},
        }
        return context|{'id':'action_context_'+digest(context)}

    def _prepare_target(self, conversation_id, source, sessions):
        revision = source['revision']
        if self.preparations.store.for_revision('local-conversations', conversation_id, revision):
            return None
        if any(s.get('conversation_plan', {}).get('conversation_id') == conversation_id
               and s['conversation_plan']['revision'] == revision for s in sessions):
            return None
        message_hash = digest(source['messages'])
        current_plan = source['current_plan']
        if not current_plan:
            fixture = [m['content'] for m in source['messages']] == [FIXTURE_MESSAGE]
            return {'messages_hash': message_hash, 'mode': 'fixture' if fixture else 'planning'}
        plan = current_plan['result']
        if current_plan['status'] == 'succeeded' and plan and plan['outcome'] == 'brief_proposal':
            return {'messages_hash': message_hash, 'mode': plan['copy_mode'], 'plan_id': plan['id']}
        return None

    def _experiment_target(self, source, sessions):
        plan = (source['current_plan'] or {}).get('result')
        if not plan or plan['outcome'] != 'brief_proposal':
            return None
        candidates = [s for s in sessions if s.get('conversation_plan', {}).get('id') == plan['id']
                      and s['conversation_plan']['conversation_id'] == plan['conversation_id']
                      and s['conversation_plan']['revision'] == source['revision']]
        if len(candidates) != 1:
            return None
        session = candidates[0]
        if not session['cohort_id'] or not session['case_id']:
            return None
        app, organization = self._app(session), session['organization']
        try:
            learning = app.learning.store.view(organization, session['cohort_id'])
        except (NotFound, Conflict):
            return None
        cohort = learning['cohort']
        if (learning['status'] != 'finalized' or cohort['case_id'] != session['case_id']
                or cohort['id'] != session['cohort_id']):
            return None
        return {
            'messages_hash': digest(source['messages']), 'session_id': session['id'], 'organization': organization,
            'label': session['name'], 'cohort_id': cohort['id'], 'case_id': cohort['case_id'],
            'draft_id': cohort['draft_id'], 'job_id': cohort['job_id'],
            'finalization_hash': digest(learning['finalization']),
        }

    def route_followup(self, conversation_id, request_id, expected_revision, content, allow_model_copy):
        if self._is_youtube_request(conversation_id, expected_revision, content):
            return self.youtube_message(conversation_id, request_id, expected_revision, content)
        try:
            postal_transition=postal_request(content) and (
                any(row['inputs']['revision']==expected_revision for row in self._sequence_rows(conversation_id))
                or any(row['revision']==expected_revision for row in self.youtube.campaigns.interactions(conversation_id)))
            sequence=None if postal_transition else self._sequence_message(conversation_id,request_id,expected_revision,content,allow_generation=True)
        except (Conflict,ValueError,NotFound) as error:raise ActionNotSaved(str(error)) from error
        if postal_transition:return self.message_conversation(conversation_id,request_id,expected_revision,content)
        if sequence is not None:return sequence
        app=self._conversation_app();old=app.actions.store.request('local-conversations',conversation_id,request_id)
        try:
            context=old['context'] if old else self.action_context(conversation_id,expected_revision)
            if self.models.binding and old is None and type(content) is str:
                shortcut = action_alias(content, typed=context['schema'] == 'routing-context/v3')
                target = context.get('action_targets', {}).get('prepare_campaign', {}).get('target')
                if shortcut is None or (shortcut == 'prepare_campaign' and target and target['mode'] == 'planning'):
                    app = self._conversation_app(model_config=self.models.selected(1))
            row=app.actions.admit('local-conversations',conversation_id,request_id,expected_revision,content,allow_model_copy,context)
        except (Conflict,ValueError,NotFound) as error:raise ActionNotSaved(str(error)) from error
        # Admission is durable before any task or provider request. Recovery can
        # reconcile the same identity if this next write is interrupted.
        if old is None and not row['alias']:app.actions.reconcile('local-conversations',row)
        return self.conversation(conversation_id)|{'action_receipt':{'id':row['id'],'revision':row['inputs']['revision']}}

    def confirm_followup(self, conversation_id, action_id, request_id, target_id, expected_revision):
        app=self._conversation_app();row=app.actions.store.get('local-conversations',action_id)
        if row['inputs']['conversation_id']!=conversation_id:raise NotFound('Action belongs to another conversation')
        receipt=app.actions.store.confirm('local-conversations',action_id,request_id,target_id,expected_revision,self.real_clock())
        self._continue_confirmed_action(receipt, row['model_config'])
        return self.conversation(conversation_id)|{'action_confirmation':receipt}

    def confirm_typed_action(self, conversation_id, action_id, request_id, result_id, expected_revision):
        with self.lock:
            app = self._conversation_app()
            row = app.actions.store.get('local-conversations', action_id)
            if row['inputs']['conversation_id'] != conversation_id:
                raise NotFound('Action belongs to another conversation')
            confirmed = row['confirmed']
            target = confirmed['target'] if confirmed and confirmed.get('action') == 'prepare_campaign' else None
            if not row['confirmed']:
                result = app.actions.view('local-conversations', row)['result']
                if not result or result['id'] != result_id or not result['requires_confirmation']:
                    raise Conflict('Confirm the exact displayed action proposal')
                source = app.conversations.view('local-conversations', conversation_id)
                sessions = self._sessions()
                if result['kind'] == 'propose_next_experiment':
                    if self._experiment_target(source, sessions) != result['evidence']:
                        raise Conflict('The confirmed source experiment is no longer current')
                elif result['kind'] == 'prepare_campaign':
                    if self._prepare_target(conversation_id, source, sessions) != result['evidence']:
                        raise Conflict('The confirmed preparation target is no longer current')
                    target = result['evidence']
            config = self._typed_preparation_config(app, conversation_id, expected_revision, target, row['model_config'])
            receipt = app.actions.store.confirm_typed(
                'local-conversations', conversation_id, action_id, request_id, result_id, expected_revision)
            self._continue_typed_action(app, receipt, config)
        return self.conversation(conversation_id) | {'action_confirmation': receipt}

    def _typed_effect(self, app, receipt):
        request, target = receipt['effect_request_id'], receipt['target']
        if receipt['action'] == 'prepare_campaign':
            if 'plan_id' not in target:
                row = self.preparations.store.request('local-conversations', request)
                if row:
                    expected = self._typed_preparation_inputs(receipt)
                    # Early typed fixture receipts froze the same brief and consent
                    # without recording the catalogue flag in the preparation intent.
                    if expected['fixture'] and 'use_audience_catalogue' not in row['inputs']:
                        del expected['use_audience_catalogue']
                    if row['inputs'] != expected:
                        raise Conflict('Saved preparation differs from the confirmed brief or consent')
                return {'preparation_id': row['id']} if row else None
            sid = self._draft_session_id(receipt['conversation_id'], request)
            if sid:
                session = self._session(sid)
                plan = session.get('conversation_plan', {})
                if (plan.get('id'), plan.get('conversation_id'), plan.get('revision')) != (
                        target['plan_id'], receipt['conversation_id'], receipt['revision']):
                    raise Conflict('Saved draft differs from the confirmed brief')
                if session['case_id']:
                    return {'session_id': sid}
                generation = self._generation(session)
                if generation['outcome_uncertain'] or generation['status'] in {'failed', 'cancelled'}:
                    return {'session_id': sid, 'stopped': True}
            return None
        try:
            proposal = app.followups.get(target['organization'], 'followup-request:' + request)
        except NotFound:
            return None
        if (proposal['parent_id'], proposal['source_cohort']) != (target['session_id'], target['cohort_id']):
            raise Conflict('Saved proposal differs from the confirmed experiment')
        return {'session_id': target['session_id'], 'proposal_id': proposal['id']}

    @staticmethod
    def _typed_preparation_inputs(receipt):
        fixture = receipt['target']['mode'] == 'fixture'
        return {'conversation_id': receipt['conversation_id'], 'revision': receipt['revision'],
                'fixture': fixture, 'allow_model_copy': not fixture and receipt['allow_model_copy'],
                'use_audience_catalogue': True}

    def _typed_preparation_config(self, app, conversation_id, revision, target, routing_config):
        if target is None or target['mode'] == 'fixture':
            return None
        if 'plan_id' not in target:
            return routing_config
        source = app.conversations.view('local-conversations', conversation_id)
        plan = next((p for p in source['plans'] if p['revision'] == revision
                     and p['result'] and p['result']['id'] == target['plan_id']), None)
        if not plan or not plan['run_id']:
            raise Conflict('The original campaign plan is unavailable.')
        config = self._planning_copy_config(app, plan['run_id'])
        return config.payload() if config else None

    def _continue_typed_action(self, app, receipt, frozen_config=None):
        if not self.models.matches(frozen_config):
            return
        if self._typed_effect(app, receipt):
            return
        organization, conversation_id = 'local-conversations', receipt['conversation_id']
        revision, target = receipt['revision'], receipt['target']
        request = receipt['effect_request_id']
        app.actions.store.validate_typed_confirmation(organization, receipt)
        if receipt['action'] == 'prepare_campaign':
            if 'plan_id' in target:
                selection = app.conversation_audiences.store.get(organization, conversation_id, revision)
                if selection and selection['plan_id'] == target['plan_id']:
                    self.draft_conversation(conversation_id, request, revision, target['plan_id'], partial=True)
            else:
                inputs = self._typed_preparation_inputs(receipt)
                self.preparations.admit(organization, conversation_id, request, revision,
                                        inputs['fixture'], inputs['allow_model_copy'], inputs['use_audience_catalogue'],
                                        model_config=self.models.frozen(frozen_config, max_calls=2))
        else:
            source = app.conversations.view(organization, conversation_id)
            if self._experiment_target(source, self._sessions()) != target:
                raise Conflict('The confirmed source experiment is no longer current')
            self.propose_followup(target['session_id'], request, target['cohort_id'], conversation_action=receipt)

    def confirm_copy_followup(self, conversation_id, action_id, request_id, result_id, expected_revision, allow_model_copy):
        if allow_model_copy is not True:raise ValueError('Allow up to five model calls for this exact revision before confirming')
        app=self._conversation_app()
        row=app.actions.store.get('local-conversations',action_id)
        if row['inputs']['conversation_id']!=conversation_id:raise NotFound('Copy action belongs to another conversation')
        value=app.actions.view('local-conversations',row)
        result=value['result']
        if (type(expected_revision) is not int or expected_revision!=row['inputs']['revision'] or not result
                or result['id']!=result_id or result['kind']!='revise_copy' or result['copy_revision']['status']!='ready'):
            raise Conflict('Confirm the exact completed copy-edit proposal')
        proposal=result['copy_revision'];target=proposal['target']
        session=self._session(target['session_id'])
        source=session.get('conversation_plan',{})
        if (source.get('conversation_id')!=conversation_id or source.get('revision')!=expected_revision
                or session['case_id']!=target['case_id'] or session['organization']!=target['organization']):
            raise Conflict('Copy target differs from its original conversation campaign')
        revision_request_id=action_id+':copy'
        native=self._app(session)
        if native.reviews.store.revision_request(session['organization'],revision_request_id) is None:
            config = self.models.selected(5)
            native=self._app(session, with_model=bool(config.browser_binding),
                             revision_admission=True, model_config=config)
        reference={'organization':'local-conversations','conversation_id':conversation_id,'action_id':action_id,
                   'result_id':result_id,'revision':expected_revision}
        native.revisions.admit(session['organization'],session['case_id'],revision_request_id,target['subject_id'],
            target['id'],proposal['feedback'],True,conversation_action=reference,confirmation_request_id=request_id)
        return self.conversation(conversation_id)

    def _continue_confirmed_action(self, receipt, frozen_config):
        if not self.models.matches(frozen_config):
            return
        source=self.preparation_source('local-conversations',receipt['conversation_id'])
        revision=receipt['message_receipt']['revision']
        if source['revision']!=revision or len(source['plans'])>=6:return
        try:
            # Recovery uses the routing request's credential binding and model.
            config = self.models.frozen(frozen_config, max_calls=2)
            self.preparations.admit('local-conversations',receipt['conversation_id'],receipt['preparation_request_id'],revision,False,receipt['allow_model_copy'],True,
                                    model_config=config)
        except (ValueError,Conflict,NotFound):
            # The confirmed amendment and consent remain discoverable for restart
            # or configuration recovery. Never choose a replacement request ID.
            return


    def recover_actions(self):
        # Only call after obtaining the deployment's exclusive server lock.
        # A reserved call from the previous executor is uncertain, not a retry.
        app=self._conversation_app()
        for row in app.actions.store.listing('local-conversations'):
            run=app.tasks.find_run('local-conversations',row['run_request_id']) if not row['alias'] else None
            if run:
                generation=self._run_generation(app,'local-conversations',run)
                if generation['status']=='running' and generation['outcome_uncertain']:
                    app.tasks.cancel('local-conversations',run,self.real_clock())

    def advance_actions(self):
        app=self._conversation_app()
        for row in app.actions.store.listing('local-conversations'):
            try:
                if row['confirmed']:
                    if row['confirmed'].get('kind') == 'typed_action_confirmation':
                        receipt = row['confirmed']
                        target = receipt['target'] if receipt['action'] == 'prepare_campaign' else None
                        with self.lock:
                            config = self._typed_preparation_config(app, receipt['conversation_id'], receipt['revision'],
                                                                    target, row['model_config'])
                            self._continue_typed_action(app, receipt, config)
                    elif row['confirmed'].get('kind') != 'copy_revision_confirmation':
                        self._continue_confirmed_action(row['confirmed'], row['model_config'])
                    continue
                if row['alias'] or not self.models.matches(row['model_config']):continue
                source=app.conversations.view('local-conversations',row['inputs']['conversation_id'])
                if source['revision']!=row['inputs']['revision']:continue
                current=app.actions.view('local-conversations',row)
                if current['status'] not in {'admitted','queued','running'}:continue
                with self.lock:
                    configured=self._conversation_app(with_model=True, model_config=self.models.frozen(row['model_config']))
                    run=configured.actions.reconcile('local-conversations',row)
                    configured.worker.tick('local-conversations',run_id=run)
            except Exception:
                # The durable admission/runtime journal owns recovery. Do not
                # repeat unknown inference or let one unavailable action starve others.
                continue


    def create_conversation(self, request_id, title):
        return self._conversation_app().conversations.create("local-conversations", request_id, title)

    @staticmethod
    def _preparation_scope(organization):
        if organization != "local-conversations":
            raise NotFound("Conversation organization is not available in this workspace")

    def freeze_preparation_plan(self, organization, conversation_id, request_id, revision, fixture, model_config=None):
        return self.preparation_host.freeze_preparation_plan(organization, conversation_id, request_id, revision, fixture, model_config)

    def admit_preparation_plan(self, organization, row):
        return self.preparation_host.admit_preparation_plan(organization, row)

    def preparation_source(self, organization, conversation_id):
        return self.preparation_host.preparation_source(organization, conversation_id)

    def stop_execution(self, conversation_id, request_id, expected_revision):
        # Deliberately independent of the executor lock: a provider call may be in flight.
        self._ensure_descendant_links()
        receipt = self._conversation_app().execution.stop('local-conversations',conversation_id,request_id,expected_revision)
        for row in self.preparations.store.listing('local-conversations',conversation_id):
            if row['inputs']['revision'] <= receipt['revision'] and row['status'] in ACTIVE_PREPARATION | {'blocked','needs_consent'}:
                self.preparations.store.update('local-conversations',row,'cancelled','Stopped by you. Send a new brief to start new work; the shared allowance does not reset.')
        self._restore_checkpoint_reviews(receipt)
        return self.conversation(conversation_id) | {'execution_receipt':receipt}

    def _ensure_descendant_links(self, strict_session_id=None):
        if self._verified_mode():return  # New ancestry must exist before task creation, never be reconstructed here.
        sessions=self._sessions()
        required=set()
        if strict_session_id:
            current=self._session(strict_session_id)
            while current.get('parent_id'):
                if current['id'] in required or len(required)>=10:
                    raise Conflict('Descendant ancestry is cyclic or too deep')
                required.add(current['id'])
                current=self._session(current['parent_id'])
        for session in sessions:
            if not session.get('parent_id') or session.get('followup_id'):
                continue
            try:
                parent=self._session(session['parent_id'])
                if parent['organization']!=session['organization']:
                    raise Conflict('Descendant campaign differs from its parent organization')
                app=self._app(parent)
                run=parent['run_id'] or app.tasks.find_run(parent['organization'],parent['id'])
                if run is None:
                    raise Conflict('Descendant campaign requires its original parent run')
                app.execution.descendant(parent['organization'],session['id'],run)
            except Exception:
                if session['id'] in required:
                    raise
                # Domain migration fences unresolved old ancestry. One unavailable
                # control record cannot stop unrelated conversations.
                continue

    def _checkpoint_block(self, organization, run_id):
        code = self.control_store.checkpoint_block(organization, run_id)
        return {'code': code, 'detail': CHECKPOINT_BLOCKS[code]} if code in CHECKPOINT_BLOCKS else None

    def _set_checkpoint_block(self, organization, run_id, code):
        self.control_store.set_checkpoint_block(organization, run_id, code)

    def _restore_checkpoint_reviews(self, receipt):
        checkpoints={(r['organization'],r['run_id']) for r in receipt.get('checkpoint_runs',[])}
        if not checkpoints:
            return
        sessions=self._sessions()
        for session in sessions:
            scope=session['organization'];run=session['run_id']
            try:
                with self._storage_faults.guard():
                    app=self._app(session)
                    run=run or app.tasks.find_run(scope,session['id'])
                    if (scope,run) not in checkpoints:
                        continue
                    self._restore_checkpoint_case(session,app,run)
                    self._set_checkpoint_block(scope,run,None)
            except Exception as error:
                if (scope,run) not in checkpoints:
                    continue
                code=('checkpoint_authority_unavailable' if isinstance(error,(Conflict,ActorUnavailable)) else
                      'checkpoint_storage_unavailable' if isinstance(error,OSError) else
                      'checkpoint_validation_unavailable' if isinstance(error,ValueError) else 'checkpoint_recovery_unavailable')
                try:self._set_checkpoint_block(scope,run,code)
                except Exception:pass  # The original domain stop remains discoverable.

    def _restore_checkpoint_case(self, session, app, run):
        scope=session['organization']
        # Case creation grants no approval. Existing cases still need their
        # presentation journal reconciled after a partial restoration.
        case=({'case_id':session['case_id']} if session['case_id'] else app.reviews.store.open_case(scope,run,'local-operator'))
        review=app.reviews.store.view(scope,case['case_id'])
        if review['run_id']!=run:
            raise Conflict('Checkpoint case differs from its original run')
        if self._verified_mode() and self.authority.get(session['id']) is not None:
            current=self.authority.get(session['id'])
            if current['case_id'] and current['case_id']!=case['case_id']:
                raise Conflict('Checkpoint sandbox already refers to another case')
            self._save(current|{'run_id':run,'case_id':case['case_id']})
        else:
            self.control_store.restore_case_links(scope, session['id'], run, case['case_id'])
        source=session.get('conversation_plan')
        if source:
            row=self.preparations.store.for_revision('local-conversations',source['conversation_id'],source['revision'])
            if row:
                valid=review['validation_report']['review_ready']
                status='review_ready' if valid else 'blocked'
                detail='Completed draft preserved for human review.' if valid else 'Completed draft preserved; current validation blocks review.'
                if row['status']!=status or row['detail']!=detail:
                    self.preparations.store.update('local-conversations',row,status,detail)

    def recover_execution(self):
        # Only call on exclusive startup or from the supported local executor.
        self._ensure_descendant_links()
        for receipt in self._conversation_app().execution.stopped_checkpoints('local-conversations'):
            self._restore_checkpoint_reviews(receipt)

    def step_preparation_plan(self, organization, row):
        return self.preparation_host.step_preparation_plan(organization, row)

    def step_preparation_campaign(self, organization, row, plan):
        return self.preparation_host.step_preparation_campaign(organization, row, plan)

    def preparation_audience_selected(self, organization, row, plan):
        return self.preparation_host.preparation_audience_selected(organization, row, plan)

    def preparation_uses_catalogue(self, organization, row):
        return self.preparation_host.preparation_uses_catalogue(organization, row)

    def select_conversation_audience(self, conversation_id, **inputs):
        try:
            receipt = self._conversation_app().conversation_audiences.select('local-conversations', conversation_id, **inputs)
        except (Conflict, ValueError, NotFound) as error:
            raise AudienceSelectionRejected(str(error)) from error
        row = self.preparations.store.for_revision('local-conversations', conversation_id, receipt['revision'])
        # A browser tick can advance the row immediately after selection commits.
        # Leave the whole continuation to the executor that holds its credential.
        if (row and row['status'] == 'selecting_audience'
                and not self.models.frozen(row['planning_context'].get('model_config'))):
            self.preparations.step('local-conversations', row['id'])
        return self.conversation(conversation_id) | {'audience_receipt':receipt}

    def _draft_session_id(self,conversation_id,request_id):
        if self._verified_mode():
            row=self.authority.request('conversation',conversation_id,request_id)
            return row['session_id'] if row else None
        row = self.control_store.draft_request(conversation_id, request_id)
        return row['session_id'] if row else None

    def draft_generation(self, conversation_id, request_id):
        session_id = self._draft_session_id(conversation_id, request_id)
        return self._generation(self._session(session_id)) if session_id else None

    def preparation_generation(self, organization, row):
        return self.preparation_host.preparation_generation(organization, row)

    def start_preparation(self, conversation_id, request_id, expected_revision, fixture, allow_model_copy, use_audience_catalogue=False):
        self.preparations.admit("local-conversations", conversation_id, request_id, expected_revision, fixture, allow_model_copy, use_audience_catalogue)
        return self.conversation(conversation_id)

    @staticmethod
    def _preparation_audience_choice(app, conversation_id, revision, plan_id):
        audiences = app.conversation_audiences
        selection = audiences.store.get('local-conversations', conversation_id, revision)
        if selection:
            if selection['plan_id'] != plan_id:
                raise Conflict('Selected audience belongs to another proposal')
            return {'audience_selection': selection}
        try:
            return {'audience_selection': None, 'audience_candidates': audiences.candidates('local-conversations', conversation_id, revision, plan_id)}
        except (ValueError, Conflict, NotFound, OSError):
            return {'audience_selection': None, 'audience_error': 'The audience catalogue is unavailable. Restore the source and refresh this conversation.'}


    def advance_browser_model(self):
        # The browser lends its key for one bounded pass. No server scheduler
        # retains it between requests or adopts work from a different session.
        if self._browser_tick.acquire(blocking=False):
            try:
                self.advance_preparations()
            finally:
                self._browser_tick.release()

    def advance_preparations(self):
        if not self.models.binding:
            self.recover_execution()
        self.advance_actions()
        for row in self.preparations.store.listing("local-conversations"):
            if row["status"] in ACTIVE_PREPARATION and self.models.matches(row['planning_context'].get('model_config')):
                self.preparations.step("local-conversations", row["id"])
        self.advance_copy_revisions()
        for journey_id in self.sequence_journeys.store.pending('local-conversations'):
            try:
                with self._storage_faults.guard():
                    self.sequence_journeys.advance('local-conversations',journey_id)
            except (OSError,NotFound):continue

    def advance_report_monitoring(self):
        with self.lock:
            sessions = self.authority.listing() if self._verified_mode() else self._sessions()
            for session in sessions:
                cohort = session["cohort_id"]
                if not cohort:
                    continue
                try:
                    with self._storage_faults.guard():
                        app = self._app(session)
                        scope = session["organization"]
                        plan = app.learning.monitoring.status(scope, cohort)
                        if plan and plan["status"] == "scheduled" and plan["next_due"] <= app.clock():
                            app.learning.check_reports(scope, cohort)
                except (ValueError, NotFound, WorkspaceStorageUnavailable):
                    # A store interruption leaves the check reclaimable when its lease expires.
                    continue

    def request_copy_revision(self, identity, request_id, expected_subject, target_id, feedback, allow_model_copy):
        if allow_model_copy is not True:
            raise ValueError("Explicit model-copy permission is required for a revision")
        with self.lock:
            session = self._session(identity)
            if session["mode"] != "model" or not session["case_id"]:
                raise Conflict("Prepare a grounded model campaign before revising copy")
            app = self._app(session)
            prior = app.reviews.store.revision_request(session["organization"], request_id)
            if self._verified_mode() and self.authority.get(identity) is None and prior is None:
                raise Conflict('Legacy sandbox environment requires migration before new revision intent')
            if prior is None:
                app = self._app(session, with_model=True, model_config=self.models.selected(5))
            app.revisions.admit(session["organization"], session["case_id"], request_id, expected_subject, target_id, feedback, allow_model_copy)
            return self.view(identity) | {"command_replayed": prior is not None}


    def _set_revision_block(self, scope, revision_id, code):
        if code is not None and code not in REVISION_BLOCKS:
            raise ValueError("Use a public revision blocker code")
        self.control_store.set_revision_block(scope, revision_id, code)

    def recover_copy_revisions(self):
        sessions=self._sessions()
        for session in sessions:
            if not session["case_id"]:
                continue
            app, scope = self._app(session), session["organization"]
            for row in app.revisions.view(scope, session["case_id"]):
                if row["run_id"] and app.tasks.inspect(scope, row["run_id"])["run"]["status"] not in {"failed", "cancelled", "succeeded"} and self._run_generation(app, scope, row["run_id"])["outcome_uncertain"]:
                    app.tasks.cancel(scope, row["run_id"], app.clock())

    def advance_copy_revisions(self):
        sessions=self._sessions()
        for session in sessions:
            if not session["case_id"]:
                continue
            app, scope = self._app(session), session["organization"]
            for row in app.revisions.view(scope, session["case_id"]):
                blocker = "continuation_unavailable"
                try:
                    if row["status"] == "stale":
                        if row["run_id"]:
                            app.tasks.cancel(scope, row["run_id"], app.clock())
                        continue
                    if row["status"] not in {"admitted", "queued", "running", "complete"}:
                        continue
                    if row["status"] == "complete" and app.tasks.inspect(scope, row["run_id"])["run"]["status"] in {"succeeded", "failed", "cancelled"}:
                        continue
                    with self.lock:
                        receipt = app.reviews.store.revision_request(scope, row["request_id"])
                        frozen = receipt['task_inputs']['model_config']
                        if not self.models.matches(frozen):
                            continue
                        blocker = "evidence_unavailable"
                        today = datetime.fromtimestamp(app.clock(), timezone.utc).date()
                        for pack in (self.pack, receipt["context"]["product_facts"], app.reviews.store.evidence(scope)["pack"]):
                            validate_fact_pack(pack, today)
                        blocker = "browser_configuration_unavailable" if frozen.get('browser_binding') else "configuration_unavailable"
                        configured = self._app(session, with_model=True, model_config=self.models.frozen(frozen))
                        run = configured.revisions.reconcile(scope, receipt)
                        blocker = "continuation_unavailable"
                        # Configuration is restored before dispatch. Do not let
                        # its old blocker relabel a live reserved call as uncertain.
                        self._set_revision_block(scope, row["id"], None)
                        configured.worker.tick(scope, run_id=run)
                except Exception:
                    # Projection metadata is not task authority. Keep original
                    # admission/consent, leases and inference journals intact.
                    # Raw configuration/provider errors never leave this boundary.
                    self._set_revision_block(scope, row["id"], blocker)

    def message_conversation(self, conversation_id, request_id, expected_revision, content):
        if self._is_youtube_request(conversation_id, expected_revision, content):
            return self.youtube_message(conversation_id, request_id, expected_revision, content)
        try:sequence=self._sequence_message(conversation_id,request_id,expected_revision,content)
        except (Conflict,NotFound,ValueError) as error:
            kind=MessageRejectedConflict if isinstance(error,Conflict) else MessageRejectedNotFound if isinstance(error,NotFound) else MessageRejectedInvalid
            raise kind(str(error)) from error
        if sequence is not None:return sequence
        return self._conversation_app().conversations.message("local-conversations", conversation_id, request_id, expected_revision, content)

    def reply_budget_conversation(self, conversation_id, request_id, expected_revision, plan_id, content):
        return self._conversation_app().conversations.reply_budget('local-conversations', conversation_id, request_id,
                                                                  expected_revision, plan_id, content)

    def plan_conversation(self, conversation_id, request_id, expected_revision, *, replay_only=False):
        with self.lock:
            scope = "local-conversations"
            native = self._conversation_app()
            admissions = native.admissions.store
            staged_key = admissions.request_for_planning(scope, conversation_id, request_id)
            saved = admissions.request_inputs(scope, staged_key) if staged_key else None
            if saved is None:
                saved = next((p for p in native.conversations.store.snapshot(scope, conversation_id)['admissions']
                              if p['request_id'] == request_id), None)
            if replay_only and not saved:
                raise Conflict("The saved planning request is unavailable.")
            if saved and (saved['revision'] != expected_revision or not saved.get('model_config')):
                raise Conflict("Planning command differs from its saved admission.")
            config = ModelConfig(**saved['model_config']) if saved else None
            app = self._conversation_app(with_model=True, model_config=config)
            run_id = app.conversations.plan("local-conversations", conversation_id, request_id, expected_revision)
            app.worker.drain("local-conversations", run_id=run_id)
            return app.conversations.view("local-conversations", conversation_id)

    def plan_conversation_fixture(self, conversation_id, request_id, expected_revision):
        with self.lock:
            app = self._conversation_app()
            run_id = app.conversations.plan_fixture("local-conversations", conversation_id, request_id, expected_revision)
            app.worker.drain(organization="local-conversations", run_id=run_id)
            return app.conversations.view("local-conversations", conversation_id)

    def draft_conversation(self, conversation_id, request_id, expected_revision, plan_id, *, partial=False):
        identifier(conversation_id), identifier(request_id), identifier(plan_id)
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("Select a current conversation revision")
        fingerprint = digest({"conversation_id": conversation_id, "revision": expected_revision, "plan_id": plan_id})
        session_id = "workspace_" + digest({"conversation_id": conversation_id, "plan_id": plan_id})[:24]
        with self.lock:
            if self._verified_mode():
                old=self.authority.request('conversation',conversation_id,request_id)
                if old:
                    if old['inputs']!={'conversation_id':conversation_id,'revision':expected_revision,'plan_id':plan_id}:
                        raise Conflict('Draft request already binds different proposal inputs')
                    return self.prepare(old['session_id'],partial=partial)
            prior_draft = self.control_store.draft_request(conversation_id, request_id)
            if prior_draft:
                if self._verified_mode():raise Conflict('Legacy draft request requires explicit migration')
                if prior_draft["request_hash"] != fingerprint:
                    raise Conflict("Draft request already binds different proposal inputs")
                return self.prepare(prior_draft["session_id"], partial=partial)
            app = self._conversation_app()
            view = app.conversations.view("local-conversations", conversation_id)
            current = view["current_plan"]
            plan = current["result"] if current and current["status"] == "succeeded" else None
            if view["revision"] != expected_revision or not plan or plan["id"] != plan_id or plan["outcome"] != "brief_proposal":
                raise Conflict("Select the exact current completed brief proposal")
            selection = app.conversation_audiences.store.get('local-conversations', conversation_id, expected_revision)
            preparation = self.preparations.store.for_revision('local-conversations', conversation_id, expected_revision)
            requires_audience = selection is not None or bool(preparation and self.preparation_uses_catalogue('local-conversations', preparation))
            if requires_audience and selection is None:
                raise Conflict('Confirm an exact audience dataset before campaign preparation')
            model_copy = plan["copy_mode"] == "model"
            start = self.real_clock() if model_copy else datetime.fromisoformat(self.pack["checked_on"]).replace(tzinfo=timezone.utc).timestamp() + 43200
            if model_copy:
                if preparation and preparation['inputs']['allow_model_copy'] is not True:
                    raise Conflict("The saved preparation does not authorize model copy.")
                config = self._planning_copy_config(app, current['run_id'])
                if config:
                    if self._verified_mode():
                        raise Conflict("Browser model copy is paused in this verified workspace.")
                    self.models.gateway(config)
                validate_fact_pack(self.pack, datetime.fromtimestamp(start, timezone.utc).date())
            if requires_audience:
                start = max(start, self.real_clock())
            session = {"id": session_id, "name": "Conversation / " + plan["objective"][:70], "mode": plan["copy_mode"],
                       "organization": session_id, "database_scope": "conversations", "clock": start, "parent_id": None,
                       "clock_mode": "REAL" if model_copy else "SIMULATED", "created_at": self.real_clock(), "run_id": None,
                       "case_id": None, "cohort_id": None, "conversation_plan": plan, **({"audience_selection":selection} if requires_audience else {})}
            if self._verified_mode():
                self._legacy_collision(session_id)
                current=self.authority.create(session,'conversation',conversation_id,request_id,
                    {'conversation_id':conversation_id,'revision':expected_revision,'plan_id':plan_id})
                self._project_session(current)
                return self.prepare(session_id,partial=partial)
            with app.actions.store.fence_campaign_creation('local-conversations', plan, selection, request_id):
                self.control_store.admit_draft(conversation_id, request_id, fingerprint, session)
            return self.prepare(session_id, partial=partial)


    def propose_followup(self, identity, request_id, cohort_id, *, conversation_action=None):
        identifier(request_id), identifier(cohort_id)
        with self.lock:
            parent = self._session(identity)
            if self._verified_mode() and self.authority.get(identity) is None:
                raise Conflict('Legacy parent environment requires explicit migration before verified continuation')
            app, scope = self._app(parent), parent["organization"]
            try:
                old = app.followups.get(scope, "followup-request:" + request_id)
                if old["parent_id"] != identity or old["source_cohort"] != cohort_id:
                    raise Conflict("Follow-up request already binds different source inputs")
                return old
            except NotFound:
                pass
            if parent["cohort_id"] != cohort_id:
                raise Conflict("Select the displayed source cohort")
            source = app.learning.store.hypothesis_source(scope, cohort_id)
            if source["status"] != "finalized":
                raise Conflict("Finalize complete mature learning before proposing a follow-up")
            view = app.reviews.store.view(scope, parent["case_id"])
            segments = tuple(sorted({c["segment"] for c in view["manifest"]["creatives"]}))
            if source['cohort']['case_id'] != parent['case_id']:
                raise Conflict('Source learning belongs to another campaign')
            source_draft = app.drafts.get(scope, source['cohort']['draft_id'])
            source_creatives = [c | {'hook': historical_hook(c, app.memory.get_context(scope, c['context_id'])
                                if c.get('fact_pack_id') else None)} for c in source_draft.manifest['creatives']]
            hypotheses = followup_hypotheses(scope, source, source_creatives, segments)
            budget = view["manifest"]["brief"]["budget_pence"]
            snapshot = app.followup_population(scope, datetime.fromtimestamp(app.clock(), timezone.utc).date().isoformat())
            excluded = app.followups.excluded(scope)
            snapshot = replace(snapshot, records=tuple(r for r in snapshot.records if r.business_id not in excluded))
            preview_brief = FollowupBrief("preview",budget,segments=segments,followup_id="followup_preview")
            creatives = tuple(c for c in fixture_catalog() if c.segment in segments)
            preview = build_draft(snapshot, preview_brief, creatives)
            hypothesis = ' '.join(h['segment'] + ': ' + h['hypothesis'] for h in hypotheses)
            memory = app.learning.store.memory_snapshot(scope, segments)
            p = {"parent_id":identity, "source_cohort":cohort_id, "learning":source,
                "model_config":ModelConfig("openai/gpt-oss-120b",max_calls=10,force_tool_choice=True).payload(), "memory":memory, "brief":{"budget_pence":budget,"unit_cost_pence":85,"max_candidates":1000,"policy_version":"demo-marketing/v1","segments":list(segments)},
                "hypothesis":hypothesis, "hypotheses":hypotheses, "snapshot_id":app.audiences.put(snapshot),
                "population":sorted({r["business_id"] for r in csv.DictReader(StringIO(preview.assignments_csv))}),
                "contexts":app.followup_contexts(scope,snapshot,segments,memory,{h['segment']: h for h in hypotheses}),
                "epochs":[view["authority"]["evidence_epoch"],view["authority"]["audience_epoch"]],
                "counts":preview.manifest["counts"], "cost_pence":preview.manifest["variable_cost_pence"],
                "eligible":preview.manifest["counts"]["mailed"] > 0 and preview.manifest["counts"]["holdout"] > 0,
                "source_label":"SYNTHETIC_ONLY: bounded 2,000-record inventory, preserving original business identities"}
            if 'requested_scope' in source_draft.manifest['brief']:
                p['brief']['requested_scope'] = source_draft.manifest['brief']['requested_scope']
            return app.followups.put(scope, request_id, p, conversation_action=conversation_action)

    def prepare_followup(self, identity, request_id, proposal_id, mode, allow_model_copy):
        identifier(request_id), identifier(proposal_id)
        if mode not in {"fixture","model"} or type(allow_model_copy) is not bool or (mode == "model" and not allow_model_copy) or (mode == "fixture" and allow_model_copy):
            raise ValueError("Choose fixture copy or explicit model-copy permission")
        with self.lock:
            parent = self._session(identity)
            if self._verified_mode() and self.authority.get(identity) is None:
                raise Conflict('Legacy parent environment requires explicit migration before verified continuation')
            app = self._app(parent)
            p = app.followups.get(parent["organization"],proposal_id)
            if p["parent_id"] != identity or not p["eligible"]:
                raise Conflict("This proposal belongs to another campaign or has insufficient independent population")
            sid = "workspace_" + digest({"followup":proposal_id})[:24]
            fingerprint = digest({"parent":identity,"proposal":proposal_id,"mode":mode,"allow_model_copy":allow_model_copy})
            session_fingerprint = digest({"proposal":proposal_id,"mode":mode,"allow_model_copy":allow_model_copy})
            if self._verified_mode():
                old=self.authority.request('followup','followup-prepare',request_id,parent_id=identity)
                inputs={'parent':identity,'proposal':proposal_id,'mode':mode,'allow_model_copy':allow_model_copy}
                if old:
                    if old['inputs']!=inputs:raise Conflict('Follow-up preparation request already binds different inputs')
                    return self.prepare(old['session_id'])
                self._legacy_collision(sid)
                child={'id':sid,'name':'Follow-up experiment','mode':mode,'organization':parent['organization'],
                    'clock':max(parent['clock'],self.real_clock()),'clock_mode':'SIMULATED','created_at':self.real_clock(),
                    'parent_id':identity,'database_scope':parent.get('database_scope','campaign'),
                    'run_id':None,'case_id':None,'cohort_id':None,'followup_id':proposal_id}
                current=self.authority.create(child,'followup','followup-prepare',request_id,inputs)
                self._project_session(current)
                return self.prepare(sid)
            child = None
            if self.control_store.session(sid) is None:
                app.followups.check(parent["organization"],p,sid)
                child = {"id":sid,"name":"Follow-up experiment","mode":mode,"organization":parent["organization"],
                    "clock":max(parent["clock"],self.real_clock()),"clock_mode":"SIMULATED","created_at":self.real_clock(),
                    "parent_id":identity,"database_scope":parent.get("database_scope","campaign"),
                    "run_id":None,"case_id":None,"cohort_id":None,"followup_id":proposal_id}
            self.control_store.admit_followup(parent['organization'], request_id, fingerprint,
                                               sid, session_fingerprint, child)
            return self.prepare(sid)

    def create(self, request_id, mode, parent_id=None):
        identifier(request_id)
        if type(mode) is not str or mode not in {"fixture", "model"}:
            raise ValueError("Choose fixture or model copy")
        identity = "workspace_" + digest({"request_id": request_id})[:24]
        fingerprint = digest({"mode": mode, "parent_id": parent_id})
        if self._verified_mode():
            with self.lock:
                self._legacy_collision(identity)
                parent=self.authority.get(parent_id) if parent_id else None
                if parent_id and parent is None:raise Conflict('Legacy parent environment requires explicit migration')
                start=(datetime.fromisoformat(self.pack['checked_on']).replace(tzinfo=timezone.utc).timestamp()+43200 if mode=='fixture' else self.real_clock())
                session={'id':identity,'name':'Working capital / '+('model copy' if mode=='model' else 'offline demo'),
                    'mode':mode,'organization':parent['organization'] if parent else identity,
                    'database_scope':parent['database_scope'] if parent else 'campaign','parent_id':parent_id,
                    'clock':max(start,parent['clock']) if parent else start,'clock_mode':'SIMULATED' if parent or mode=='fixture' else 'REAL',
                    'created_at':self.real_clock(),'run_id':None,'case_id':None,'cohort_id':None}
                current=self.authority.create(session,'root','root',request_id,{'mode':mode,'parent_id':parent_id})
                self._project_session(current)
                return self.prepare(identity)
        with self.lock:
            session = None
            if self.control_store.session(identity) is None:
                parent = self._session(parent_id) if parent_id else None
                if parent and (not parent["cohort_id"] or self._app(parent).learning.store.view(parent["organization"], parent["cohort_id"])["status"] != "finalized"):
                    raise Conflict("Only finalized learning can seed the next experiment")
                start = (datetime.fromisoformat(self.pack["checked_on"]).replace(tzinfo=timezone.utc).timestamp() + 43200
                         if mode == "fixture" else self.real_clock())
                if parent:
                    start = max(start, parent["clock"])
                session = {"id": identity, "name": "Working capital / " + ("model copy" if mode == "model" else "offline demo"),
                    "mode": mode, "organization": parent["organization"] if parent else identity, "clock": start,
                    "parent_id": parent_id, "database_scope": (parent.get("database_scope") or ("conversations" if parent.get("conversation_plan") or parent["organization"] == "local-conversations" else "campaign")) if parent else "campaign", "clock_mode": "SIMULATED" if parent or mode == "fixture" else "REAL", "created_at": self.real_clock(), "run_id": None,
                    "case_id": None, "cohort_id": None}
            self.control_store.create_session(identity, fingerprint, session)
            return self.prepare(identity)

    def _planning_copy_config(self, app, run_id):
        state = app.tasks.inspect('local-conversations', run_id)
        return self.models.frozen(state['tasks'][0]['inputs'].get('model_config'), max_calls=10)

    def prepare(self, identity, *, partial=False):
        with self.lock:
            self._ensure_descendant_links(strict_session_id=identity)
            session = self._session(identity)
            if session["case_id"]:
                return self.view(identity)
            if self._verified_mode() and self.authority.get(identity) is None:
                raise Conflict('Legacy sandbox environment is inspectable; migrate it before verified preparation')
            config = None
            if session['mode'] == 'model' and session.get('conversation_plan'):
                plan = session['conversation_plan']
                planner = self._conversation_app()
                source = planner.conversations.view('local-conversations', plan['conversation_id'])
                original = next((p for p in source['plans'] if p['result'] == plan), None)
                if original and original['run_id']:
                    config = self._planning_copy_config(planner, original['run_id'])
            app = self._app(session, with_model=True, model_config=config)
            store = app.reviews.store
            scope = session["organization"]
            store.initialize_actor(scope, "local-operator", ("operator",))
            store.initialize_actor(scope, "local-reviewer", ("reviewer",))
            if store.evidence(scope) is None:
                store.activate(scope, "local-operator", "initial-evidence", self.pack, ReviewPolicy())
            start = app.start_model if session["mode"] == "model" else app.start
            # Resume the admitted plan, including after a lost metadata write.
            # Recomputing context here could conflict with newly learned memory.
            run = session["run_id"] or app.tasks.find_run(scope, identity)
            if session.get("conversation_plan") and session["mode"] == "model":
                source = session["conversation_plan"]
                current = app.conversations.view("local-conversations", source["conversation_id"])
                if current["revision"] != source["revision"] or not current["current_plan"] or current["current_plan"]["result"] != source:
                    raise Conflict("Conversation changed before campaign preparation")
            if run is None:
                if session.get("followup_id"):
                    p = app.followups.get(scope,session["followup_id"])
                    app.followups.check(scope,p,identity)
                    brief = brief_from(p["brief"] | {"campaign_id":identity,"followup_id":p["id"]})
                    if session["mode"] == "model":
                        if app.inference.config.payload() != p["model_config"]:
                            raise Conflict("Restore the model settings frozen in this follow-up proposal")
                        run = app.start_model(scope, identity, snapshot_override=app.audiences.get(scope,p["snapshot_id"]),brief_override=brief,contexts_override=p["contexts"])
                    else:
                        run = app.start_followup(scope,identity,p["snapshot_id"],brief)
                elif session.get("conversation_plan"):
                    source = session["conversation_plan"]
                    current = app.conversations.view("local-conversations", source["conversation_id"])
                    if current["revision"] != source["revision"] or not current["current_plan"] or current["current_plan"]["result"] != source:
                        raise Conflict("Conversation changed before campaign preparation")
                    run = app.start_conversation(scope, identity, source, datetime.fromtimestamp(session["clock"], timezone.utc).date().isoformat(),
                                                 selected_audience=bool(session.get('audience_selection')))
                else:
                    parent_run=None
                    if app.admissions.required() and session.get('parent_id'):
                        parent=self._session(session['parent_id'])
                        parent_run=parent['run_id'] or app.tasks.find_run(scope,parent['id'])
                        if parent_run is None:raise Conflict('A verified parent run is required before descendant creation')
                    run = start(scope, identity, as_of=datetime.fromtimestamp(session["clock"], timezone.utc).date().isoformat(),
                                **({'parent_run_id':parent_run} if parent_run else {}))
            session["run_id"] = run
            self._save(session)
            if app.tasks.inspect(scope,run).get('admission',{}).get('status')=='paused':
                return self.view(identity)
            if session["mode"] == "model":
                today = datetime.fromtimestamp(self.real_clock(), timezone.utc).date()
                validate_fact_pack(store.evidence(scope)["pack"], today)
                admitted = app.tasks.inspect(scope, run)
                for context_id in admitted["tasks"][0]["inputs"]["context_ids"].values():
                    validate_fact_pack(app.memory.get_context(scope, context_id)["product_facts"], today)
            app.worker.drain(scope, max_tasks=1 if partial else 20, run_id=run)
            state = app.tasks.inspect(scope, run)
            if state["run"]["status"] not in {"waiting", "succeeded"}:
                if partial:
                    return self.view(identity)
                raise Conflict("Preparation has not reached review. Inspect the task status before resuming.")
            case = store.open_case(scope, run, "local-operator")
            session["case_id"] = case["case_id"]
            self._save(session)
            return self.view(identity)


    def monitoring_command(self, identity, action, payload):
        with self.lock:
            app, scope = None, None
            try:
                session = self._session(identity)
                if self._verified_mode() and self.authority.get(identity) is None:
                    raise Conflict("Migrate this legacy campaign before configuring monitoring")
                app = self._app(session)
                scope, case = session["organization"], session["case_id"]
                fields = {"request_id", "handoff_id", "cohort_id"}
                if action == "monitoring-start":
                    fields |= {"reports", "first_check", "interval_seconds"}
                elif action == "monitoring-update":
                    fields |= {"revision", "status", "interval_seconds"}
                else:
                    raise ValueError("Use a supported monitoring command")
                if type(payload) is not dict or set(payload) != fields:
                    raise ValueError("Use the exact fields for this monitoring command")
                for key in ("request_id", "handoff_id", "cohort_id"):
                    identifier(payload[key])
                if not case or not session["cohort_id"]:
                    raise Conflict("Open the accepted campaign's outcome window before monitoring")
                accepted = app.learning.source.accepted(scope, case)
                if (payload["handoff_id"] != accepted["job_id"] or payload["cohort_id"] != session["cohort_id"]
                        or payload["cohort_id"] != accepted["id"]):
                    raise Conflict("Monitoring must bind the displayed accepted job and cohort")
                if action == "monitoring-start":
                    receipt = app.learning.schedule_uploaded_reports(
                        scope, "local-operator", payload["request_id"], payload["cohort_id"],
                        payload["first_check"], payload["interval_seconds"], payload["reports"])
                else:
                    receipt = app.learning.monitoring.update(
                        scope, "local-operator", payload["request_id"], payload["cohort_id"],
                        payload["revision"], payload["status"], payload["interval_seconds"])
            except (ValueError, NotFound) as error:
                fenced = False
                if app is not None and type(payload) is dict:
                    try:
                        identifier(payload.get("request_id"))
                        fenced = app.learning.monitoring.reject(scope, "local-operator", payload["request_id"], payload)
                    except ValueError:
                        pass
                raise MonitoringRejected(str(error), fenced) from error
            # Projection failure after the domain commit keeps the browser request pending.
            return self.view(identity) | {"monitoring_receipt": receipt}

    def action(self, identity, action, payload):
        with self.lock:
            session = self._session(identity)
            app = self._app(session)
            scope, case = session["organization"], session["case_id"]
            if not case:
                raise Conflict("Prepare this campaign before recording a decision")
            fields = {"approve": {"subject_id", "reason"}, "reject": {"subject_id", "reason"},
                "refresh": {"subject_id"}, "revoke": {"approval_id", "reason"},
                "suppress": {"business_id", "reason"}, "handoff": {"approval_id"},
                "open-learning": set(), "observe": set(), "finalize": set(),
                "advance-report-check": {"handoff_id", "cohort_id", "position", "next_due"},
                "finalize-report-learning": {"handoff_id", "cohort_id"}}
            # Chat binds each explicit simulation decision to the displayed
            # accepted job/cohort. Retain the existing workspace payloads.
            bound_learning = action in {"open-learning", "observe", "finalize"} and "handoff_id" in payload
            if bound_learning:
                fields[action] = {"handoff_id"} if action == "open-learning" else {"handoff_id", "cohort_id"}
            recorded_learning = action in {"advance-report-check", "finalize-report-learning"}
            if action not in fields or set(payload) != fields[action] | {"request_id"}:
                raise ValueError("Use the exact fields for this workspace action")
            for field in fields[action] - {"position", "next_due"}:
                text(payload[field]) if field == "reason" else identifier(payload[field])
            if action == "advance-report-check":
                finite(payload["next_due"])
                if type(payload["position"]) is not int or session["mode"] != "fixture":
                    raise ValueError("Advance a displayed report check in a fixture campaign")
            if bound_learning or recorded_learning:
                accepted = app.learning.source.accepted(scope, case)
                if accepted["job_id"] != payload["handoff_id"]:
                    raise Conflict("Learning request refers to a different accepted job")
                if action != "open-learning" and (payload["cohort_id"] != session["cohort_id"] or payload["cohort_id"] != accepted["id"]):
                    raise Conflict("Learning request refers to a different outcome cohort")
            request_id = payload["request_id"]
            identifier(request_id)
            fingerprint = digest({"action": action, "payload": payload})
            owned=self._verified_mode()
            if owned:
                if self.authority.begin(identity,action,payload):return self.view(identity)|{'command_replayed':True}
                session=self.authority.get(identity);app=self._app(session)
            if not owned:
                old = self.control_store.command(scope, identity, request_id)
                if old:
                    if old['request_hash'] != fingerprint:
                        raise Conflict("Workspace request already binds different action inputs")
                    if old['done']:
                        return self.view(identity) | {"command_replayed": True}
                elif action == 'advance-report-check':
                    with app.learning.monitoring.fixture_check(scope, "local-operator", session["cohort_id"], case,
                                                              payload["handoff_id"], payload["position"], payload["next_due"]):
                        admitted = self.control_store.begin_command(scope, identity, request_id, fingerprint,
                                                                    next_due=payload['next_due'])
                        session['clock'] = admitted['clock']
                    if admitted['done']:
                        return self.view(identity) | {"command_replayed": True}
                else:
                    admitted = self.control_store.begin_command(scope, identity, request_id, fingerprint)
                    if admitted['done']:
                        return self.view(identity) | {"command_replayed": True}
            store = app.reviews.store
            if action in {"approve", "reject"}:
                store.decide(scope, case, payload["subject_id"], "local-reviewer", action, request_id, payload["reason"], 86400)
            elif action == "refresh":
                app.reviews.refresh(scope, case, payload["subject_id"], "local-operator", request_id)
            elif action == "revoke":
                store.revoke(scope, case, payload["approval_id"], "local-reviewer", request_id, payload["reason"])
            elif action == "suppress":
                # A suppression is an independent operator instruction, never
                # an approval. The domain invalidates affected authority.
                store.suppress(scope, "local-operator", request_id, payload["business_id"], payload["reason"])
            elif action == "handoff":
                store.handoff(scope, case, payload["approval_id"], "local-operator", request_id)
            elif action == "open-learning":
                receipt = app.learning.open(scope, case, "local-operator", request_id)
                session["cohort_id"] = receipt["cohort_id"]
                self._save(session)
            elif action == "advance-report-check":
                app.learning.check_reports(scope, session["cohort_id"], expected_position=payload["position"])
            elif action == "finalize-report-learning":
                plan = app.learning.monitoring.status(scope, session["cohort_id"])
                if not plan or plan["status"] != "complete":
                    raise Conflict("Finish checking the recorded reports before finalizing learning")
                app.learning.store.finalize(scope, "local-operator", request_id, session["cohort_id"],
                                            accepted["window_end"])
            elif action in {"observe", "finalize"}:
                if not session["cohort_id"]:
                    raise Conflict("Open an outcome window first")
                if app.learning.monitoring.status(scope, session["cohort_id"]):
                    raise Conflict("Use the recorded report controls for this cohort")
                cohort = app.learning.source.accepted(scope, case)
                target = cohort["window_start"] + 7 * 86400 if action == "observe" else cohort["window_end"]
                if not owned:
                    session["clock"] = max(session["clock"], target)
                    session["clock_mode"] = "SIMULATED"
                    self._save(session)
                # The existing app's clock closes over this session dictionary.
                rows = []
                for member in cohort["members"]:
                    response = int(digest({"business": member["business_id"], "seed": 81})[:8], 16) % 1000 < {"A": 220, "B": 35, "no_mail": 20}[member["arm"]]
                    if response or action == "finalize":
                        rows.append(member | {"response": response, "observed_at": cohort["window_start"] + 7 * 86400 if response else cohort["window_end"]})
                if rows:
                    app.learning.store.ingest(scope, "local-operator", request_id + ":import", session["cohort_id"],
                        {"schema": "synthetic-outcomes/v1", "mode": "SYNTHETIC_ONLY", "cohort_id": session["cohort_id"], "outcomes": rows},
                        simulate=True)
                if action == "finalize":
                    app.learning.store.finalize(scope, "local-operator", request_id, session["cohort_id"], cohort["window_end"])
            else:
                raise ValueError("Unknown workspace action")
            if owned:self.authority.complete(identity,request_id)
            else:
                self.control_store.complete_command(scope, identity, request_id)
            return self.view(identity)

    def artifact(self, identity, kind, expected_subject):
        with self.lock:
            session = self._session(identity)
            app = self._app(session)
            review = app.reviews.store.view(session["organization"], session["case_id"])
            if review["subject"]["id"] != expected_subject:
                raise Conflict("Campaign revision changed before download; refresh the workspace")
            draft = app.drafts.get(session["organization"], review["subject"]["draft_id"])
            if kind == "handoff":
                receipt = review["handoff"]
                if receipt is None:
                    raise Conflict("This campaign has no accepted simulated handoff")
                if receipt["subject_id"] != expected_subject or receipt["draft_id"] != draft.id:
                    raise Conflict("Acceptance receipt does not match the displayed subject")
                return canonical(receipt).encode(), "application/json", "handoff.json"
            if kind == "manifest":
                return canonical(draft.manifest).encode(), "application/json", "manifest.json"
            if kind in {"mailing", "assignments"}:
                return getattr(draft, kind + "_csv").encode(), "text/csv; charset=utf-8", kind + ".csv"
            raise NotFound("Unknown artifact")
