"""Campaign use cases over public services, frozen assets and narrow effects."""
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from acquisition.audiences import AudienceStore, AudienceDiscovery
from acquisition.campaigns import (Brief, ConversationBrief, SourcedConversationBrief, FollowupBrief, FollowupStore,
    DraftStore, brief_from, conversation_brief_from_plan, conversation_copy_brief)
from acquisition.creative import CreativeMemory, validate_fact_pack
from acquisition.contracts import Conflict, canonical
from acquisition.reasoning import Inference, ModelConfig, CallJournal
from acquisition.runtime import TaskStore, Worker
from acquisition.reviews import ReviewService, CopyRevisionService
from acquisition.learning import LearningService
from acquisition.conversations import (ConversationService, ConversationAudiences, ConversationActions,
    ConversationExecution, WorkflowAdmissions, IntakePlanning)
from .monthly_mail import task_plan, conversation_task_plan
from .model_mail import model_task_plan, conversation_model_task_plan


@dataclass
class Application:
    tasks: TaskStore
    audiences: AudienceStore
    drafts: DraftStore
    worker: Worker
    clock: Callable[[], float]
    catalogue_hash: str
    memory: CreativeMemory
    calls: CallJournal
    inference: Inference | None
    reviews: ReviewService
    learning: LearningService
    conversations: ConversationService
    revisions: CopyRevisionService
    followups: FollowupStore
    audience_discovery: AudienceDiscovery
    conversation_audiences: ConversationAudiences
    actions: ConversationActions
    execution: ConversationExecution
    admissions: WorkflowAdmissions
    model_config: ModelConfig | None
    population: Callable
    assets: Callable[[], dict]
    copy_assets: Callable
    draft_exporter: Callable
    learning_reporter: Callable
    review_reporter: Callable
    intake_planning: IntakePlanning | None = None

    def _legacy_campaign(self, organization, request_id, snapshot_id, brief, *, model=False,
                         contexts_override=None, objective=None, parent_run_id=None):
        """Observe exact pre-cutover plans. No input writes, freshness checks or adoption."""
        old=self.admissions.store.legacy_tasks(organization,request_id)
        if old is None:return None
        frozen=old[1][0].inputs
        if parent_run_id is not None:
            raise Conflict('Legacy replay cannot introduce a new execution parent')
        conversation=isinstance(brief,ConversationBrief)
        if model:
            if self.model_config is None or frozen.get('model_config')!=self.model_config.payload():
                raise Conflict('Legacy model replay requires its original settings')
            contexts=frozen.get('context_ids')
            if not isinstance(contexts,dict) or (contexts_override is not None and contexts_override!=contexts):
                raise Conflict('Legacy replay differs from its frozen contexts')
            for segment,context_id in contexts.items():
                context=self.memory.get_context(organization,context_id)
                if context['segment']!=segment or context['audience_summary']['snapshot_id']!=snapshot_id:
                    raise Conflict('Legacy context differs from its original audience')
                if conversation and context.get('campaign_brief') != conversation_copy_brief(brief, objective):
                    raise Conflict('Legacy replay differs from its original objective')
            factory=conversation_model_task_plan if conversation else model_task_plan
            specs=factory(snapshot_id,brief,contexts,Inference(None,None,self.model_config,self.clock))
            if not conversation and frozen.get('workflow_version')=='monthly-mail/v2':
                # Observation of an already persisted v2 plan grants no new v2 admission.
                specs=[replace(t,capability=t.capability.replace('.v3','.v2'),
                               inputs=t.inputs|{'workflow_version':'monthly-mail/v2'}) for t in specs]
        else:
            factory=conversation_task_plan if conversation else task_plan
            specs=factory(snapshot_id,brief,frozen.get('creative_catalogue_hash'))
        return self.admissions.store.replay_legacy(organization,request_id,specs)

    def start(self, organization: str, request_id: str, size: int = 1000, seed: int = 42,
              budget_pence: int = 85000, as_of: str = "2026-10-25", campaign_id: str | None = None, *, parent_run_id=None) -> str:
        if self.admissions.required():
            brief=Brief(campaign_id or request_id,budget_pence)
            if self.admissions.store.legacy_tasks(organization,request_id) is not None:
                legacy=self._legacy_campaign(organization,request_id,self.population(organization,size,seed,as_of).id,brief,parent_run_id=parent_run_id)
                if legacy is not None:return legacy
            command={'method':'start','size':size,'seed':seed,'as_of':as_of,'brief':asdict(brief),
                     'campaign_id':campaign_id,'parent_run_id':parent_run_id}
            def references():
                refs={'brief':asdict(brief),'snapshot_id':self.audiences.put(self.population(organization,size,seed,as_of)),
                      'runtime_request_id':request_id}
                if parent_run_id:refs['parent_run_id']=parent_run_id
                return refs
            return self.admissions.workflow(organization,request_id,'manual-descendant' if parent_run_id else 'standalone-campaign',
                command,references,allow_model=False,config=None)
        if parent_run_id:raise ValueError('Explicit parent-run creation requires verified admission cutover')
        snapshot_id = self.audiences.put(self.population(organization, size, seed, as_of))
        brief = Brief(campaign_id=campaign_id or request_id, budget_pence=budget_pence)
        return self.tasks.create(organization, request_id, task_plan(snapshot_id, brief, self.catalogue_hash), self.clock())

    def start_model(self, organization: str, request_id: str, size: int = 1000, seed: int = 42,
                    budget_pence: int = 85000, as_of: str = "2026-10-25", campaign_id: str | None = None,
                    conversation_brief: ConversationBrief | None = None, objective: str | None = None,
                    snapshot_override=None, brief_override=None, contexts_override=None, *, parent_run_id=None) -> str:
        if self.admissions.required():
            if self.model_config is None:raise ValueError('Configure frozen model settings before admission')
            if conversation_brief and (brief_override or parent_run_id):raise ValueError('Choose one campaign source')
            brief=brief_override or conversation_brief or Brief(campaign_id or request_id,budget_pence)
            if self.admissions.store.legacy_tasks(organization,request_id) is not None:
                snapshot=snapshot_override or self.population(organization,size,seed,as_of)
                if snapshot.organization!=organization:raise Conflict('Legacy replay requires its original organization')
                legacy=self._legacy_campaign(organization,request_id,snapshot.id,brief,model=True,
                    contexts_override=contexts_override,objective=objective,parent_run_id=parent_run_id)
                if legacy is not None:return legacy
            kind=('conversation-campaign' if conversation_brief else 'learning-followup' if isinstance(brief,FollowupBrief)
                  else 'manual-descendant' if parent_run_id else 'standalone-campaign')
            command={'method':'start-model','size':size,'seed':seed,'as_of':as_of,'budget_pence':budget_pence,
                     'campaign_id':campaign_id,'brief':asdict(brief),'objective':objective,
                     'snapshot_override':snapshot_override.id if snapshot_override else None,
                     'contexts_override':contexts_override,'parent_run_id':parent_run_id}
            def references():
                snapshot_id,contexts=self._model_inputs(organization,request_id,size,seed,budget_pence,as_of,campaign_id,
                    conversation_brief,objective,snapshot_override,brief_override,contexts_override)
                if kind=='conversation-campaign':
                    return {'plan_id':brief.plan_id,'snapshot_id':snapshot_id,'context_ids':contexts}
                if kind=='learning-followup':
                    p=self.followups.get(organization,brief.followup_id)
                    if (canonical(asdict(brief))!=canonical(p['brief']|{'campaign_id':request_id,'followup_id':p['id']}) or
                            snapshot_id!=p['snapshot_id'] or contexts!=p['contexts']):
                        raise Conflict('Follow-up command differs from its frozen proposal')
                    return {'proposal_id':p['id']}
                refs={'brief':asdict(brief),'snapshot_id':snapshot_id,'context_ids':contexts,'runtime_request_id':request_id}
                if parent_run_id:refs['parent_run_id']=parent_run_id
                return refs
            return self.admissions.workflow(organization,request_id,kind,command,references,allow_model=True,config=self.model_config)
        if self.inference is None:raise ValueError('Configure a model adapter before starting a model run')
        if parent_run_id:raise ValueError('Explicit parent-run creation requires verified admission cutover')
        snapshot_id,contexts=self._model_inputs(organization,request_id,size,seed,budget_pence,as_of,campaign_id,
            conversation_brief,objective,snapshot_override,brief_override,contexts_override)
        specs=(conversation_model_task_plan(snapshot_id,conversation_brief,contexts,self.inference) if conversation_brief
               else model_task_plan(snapshot_id,brief_override or Brief(campaign_id or request_id,budget_pence),contexts,self.inference))
        return self.tasks.create(organization,request_id,specs,self.clock())

    def _model_inputs(self, organization: str, request_id: str, size: int = 1000, seed: int = 42,
                    budget_pence: int = 85000, as_of: str = "2026-10-25", campaign_id: str | None = None,
                    conversation_brief: ConversationBrief | None = None, objective: str | None = None,
                    snapshot_override=None, brief_override=None, contexts_override=None) -> str:
        snapshot = snapshot_override or self.population(organization, size, seed, as_of)
        snapshot_id = self.audiences.put(snapshot)
        segments = (brief_override or conversation_brief).segments if (brief_override or conversation_brief) else ("inventory", "contractors")
        if contexts_override is not None:
            contexts = dict(contexts_override)
            if set(contexts) != set(segments):
                raise ValueError("Frozen copy contexts must cover the exact selected segments")
            for segment, context_id in contexts.items():
                context = self.memory.get_context(organization, context_id)
                if context["segment"] != segment:
                    raise ValueError("Frozen copy context has a different segment")
                validate_fact_pack(context["product_facts"], datetime.fromtimestamp(self.clock(), timezone.utc).date())
        else:
            assets = self.assets()
            guidance = assets['editorial']
            product_facts = assets['product_facts']
            current = self.reviews.store.evidence(organization)
            if current is not None:
                product_facts = current["pack"]
            validate_fact_pack(product_facts, datetime.fromtimestamp(self.clock(), timezone.utc).date())
            contexts = {}
            learning_memory = self.learning.store.memory_snapshot(organization, segments)
            editorial_memory = self.memory.examples_snapshot(organization, segments, guidance['reviewer_examples'])
            for segment in segments:
                context = {"segment": segment, "guidance": guidance, "product_facts": product_facts,
                           "memory": editorial_memory[segment],
                           "audience_summary": {"input_records": sum(row.segment == segment for row in snapshot.records),
                               "model_version": snapshot.model_version, "snapshot_id": snapshot.id,
                               "situation_hypothesis": guidance["situations"][segment],
                               "outcome_evidence": learning_memory[segment]}}
                if conversation_brief:
                    context["campaign_brief"] = conversation_copy_brief(conversation_brief, objective)
                if conversation_brief and isinstance(conversation_brief, SourcedConversationBrief):
                    selection = conversation_brief.audience_source
                    context['audience_summary']['dataset_source'] = {
                        'selection_id':selection['id'], 'manifest_id':selection['manifest_id'],
                        'dataset_id':selection['source']['dataset_id'], 'version':selection['source']['version'],
                        'checksum':selection['source']['checksum'], 'source_snapshot_id':selection['source_snapshot_id']}
                contexts[segment] = self.memory.put_context(organization, self.copy_assets(organization, context))
        return snapshot_id, contexts

    def followup_population(self, organization, as_of):
        return self.population(organization, 2000, 42, as_of)

    def start_followup(self, organization, identity, snapshot_id, brief):
        if self.admissions.required():
            legacy=self._legacy_campaign(organization,identity,snapshot_id,brief)
            if legacy is not None:return legacy
            p=self.followups.get(organization,brief.followup_id)
            if canonical(asdict(brief))!=canonical(p['brief']|{'campaign_id':identity,'followup_id':p['id']}) or snapshot_id!=p['snapshot_id']:
                raise Conflict('Follow-up command differs from its frozen proposal')
            return self.admissions.workflow(organization,identity,'learning-followup',
                {'method':'start-followup','snapshot_id':snapshot_id,'brief':asdict(brief)},
                lambda:{'proposal_id':p['id']},allow_model=False,config=None)
        return self.tasks.create(organization,identity,task_plan(snapshot_id,brief,self.catalogue_hash),self.clock())

    def followup_contexts(self, organization, snapshot, segments, learning_memory, hypothesis):
        guidance = self.assets()['editorial']
        facts = self.reviews.store.evidence(organization)["pack"]
        contexts = {}
        editorial_memory = self.memory.examples_snapshot(organization, segments, guidance['reviewer_examples'])
        for segment in segments:
            context = {"segment":segment, "guidance":guidance, "product_facts":facts,
                "memory":editorial_memory[segment], "audience_summary":{
                    "input_records":sum(r.segment == segment for r in snapshot.records),
                    "model_version":snapshot.model_version, "snapshot_id":snapshot.id,
                    "situation_hypothesis":guidance["situations"][segment], "outcome_evidence":learning_memory[segment],
                    "followup_hypothesis":hypothesis[segment] if isinstance(hypothesis, dict) else hypothesis}}
            contexts[segment] = self.memory.put_context(organization,self.copy_assets(organization, context))
        return contexts

    def start_conversation(self, organization, request_id, plan, as_of, *, selected_audience=False):
        if self.admissions.required():
            old=self.admissions.store.legacy_tasks(organization,request_id)
            if old is not None:
                frozen=old[1][0].inputs
                original=brief_from(frozen.get('brief',{}))
                selection=getattr(original,'audience_source',None)
                if bool(selection)!=selected_audience:
                    raise Conflict('Legacy replay differs from its original audience source mode')
                brief = conversation_brief_from_plan(plan, request_id, selection)
                snapshot_id=frozen['snapshot_id'] if selection else self.population(organization,1000,42,as_of).id
                return self._legacy_campaign(organization,request_id,snapshot_id,brief,
                    model=plan['copy_mode']=='model',objective=plan['objective'])
        if self.admissions.required() and plan['copy_mode']=='fixture':
            def references():
                if selected_audience:
                    snapshot,_=self.conversation_audiences.materialize('local-conversations',plan['conversation_id'],plan['revision'],plan['id'],organization)
                else:snapshot=self.population(organization,1000,42,as_of)
                return {'plan_id':plan['id'],'snapshot_id':self.audiences.put(snapshot)}
            return self.admissions.workflow(organization,request_id,'conversation-campaign',
                {'method':'start-conversation','plan':plan,'as_of':as_of,'selected_audience':selected_audience},
                references,allow_model=False,config=None)
        snapshot, selection = self.conversation_audiences.materialize("local-conversations", plan["conversation_id"], plan["revision"], plan["id"], organization) if selected_audience else (None, None)
        brief = conversation_brief_from_plan(plan, request_id, selection)
        if plan["copy_mode"] == "model":
            return self.start_model(organization, request_id, as_of=as_of, conversation_brief=brief, objective=plan["objective"], snapshot_override=snapshot)
        snapshot_id = self.audiences.put(snapshot if snapshot is not None else self.population(organization, 1000, 42, as_of))
        return self.tasks.create(organization, request_id, conversation_task_plan(snapshot_id, brief, self.catalogue_hash), self.clock())

    def export(self, organization: str, run_id: str, directory):
        state = self.tasks.inspect(organization, run_id)
        outputs = [task["output"] for task in state["tasks"] if task["output"] and task["output"].get("draft_id")]
        if not outputs:
            raise ValueError("No committed draft receipt exists yet")
        draft = self.drafts.get(organization, outputs[-1]["draft_id"])
        return self._export_draft(organization, draft, directory)

    def export_review(self, organization: str, case_id: str, directory, expected_subject: str | None = None):
        view = self.reviews.store.view(organization, case_id)
        if expected_subject is not None and view["subject"]["id"] != expected_subject:
            from acquisition.contracts import Conflict
            raise Conflict("Review changed before export; request a fresh report")
        draft = self.drafts.get(organization, view["subject"]["draft_id"])
        return self._export_draft(organization, draft, directory)

    def _export_draft(self, organization, draft, directory):
        context_ids = {item["context_id"] for item in draft.manifest["creatives"] if item.get("fact_pack_id")}
        contexts = tuple(self.memory.get_context(organization, identity) for identity in sorted(context_ids))
        return self.draft_exporter(draft, directory, contexts)
