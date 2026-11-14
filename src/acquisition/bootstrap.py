"""Composition root: the only place that selects and wires concrete adapters."""

import time
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from functools import partial
from datetime import datetime, timezone

from acquisition.adapters.sqlite.followups import SqliteFollowups
from acquisition.campaigns import FollowupStore
from acquisition.adapters.files import export_draft
from acquisition.adapters.sqlite.audiences import SqliteAudiences
from acquisition.adapters.sqlite.database import Database
from acquisition.local_root import inspection_only, require_live_root, workspace_root_lock
from acquisition.adapters.sqlite.drafts import SqliteDrafts
from acquisition.adapters.sqlite.tasks import SqliteTasks
from acquisition.adapters.synthetic import generate, generated_snapshot_identity
from acquisition.adapters.local_audiences import LocalAudienceSource
from acquisition.audiences import AudienceDiscovery
from acquisition.workflows.audience_discovery import audience_tool_contracts
from acquisition.adapters.sqlite.creative import SqliteCreative
from acquisition.adapters.sqlite.inference import SqliteCalls
from acquisition.contracts import Conflict, canonical, digest
from acquisition.campaigns import Brief, ConversationBrief, SourcedConversationBrief, FollowupBrief, CampaignService, brief_from, conversation_brief_from_plan, conversation_copy_brief
from acquisition.creative import fixture_catalog, validate_fact_pack, grounded_tool_contracts, copy_source_payloads
from acquisition.runtime import TaskSpec, TaskStore, Worker
from acquisition.reasoning import Inference, ModelConfig, ModelGateway, freeze_assets, source_manifest
from acquisition.workflows.monthly_mail import MonthlyMail, ConversationMail, conversation_task_plan, task_plan
from acquisition.workflows.model_mail import ModelMonthlyMail, ConversationModelMail, model_task_plan, conversation_model_task_plan
from acquisition.adapters.sqlite.reviews import SqliteReviews
from acquisition.adapters.sqlite.simulated_delivery import SqliteSimulatedDelivery
from acquisition.reviews import ReviewService, CopyRevisionService
from acquisition.workflows.copy_revision import CopyRevisionWorkflow
from acquisition.learning import LearningService
from acquisition.adapters.local_reports import LocalSyntheticReports
from acquisition.adapters.sqlite.learning import SqliteLearning
from acquisition.adapters.sqlite.report_monitoring import SqliteReportMonitoring
from acquisition.workflows.learning import AcceptedCohortSource
from acquisition.adapters.sqlite.conversations import SqliteConversations
from acquisition.conversations import ConversationService, CAPABILITY as PLANNER_CAPABILITY, FIXTURE_CAPABILITY
from acquisition.workflows.conversation import ConversationPlanner, planner_tool_contracts
from acquisition.adapters.sqlite.preparations import SqlitePreparations
from acquisition.conversations import PreparationCoordinator, ConversationAudiences, ConversationActions, ACTION_CAPABILITY, COPY_ACTION_CAPABILITY, TYPED_ACTION_CAPABILITY, ACTION_ALIASES, TYPED_ACTION_ALIASES
from acquisition.adapters.sqlite.conversation_actions import SqliteConversationActions
from acquisition.workflows.conversational_actions import ConversationRouter, action_tool_contracts
from acquisition.adapters.sqlite.audience_selections import SqliteAudienceSelections
from acquisition.adapters.sqlite.execution import SqliteExecution
from acquisition.adapters.sqlite.workspace_ancestry import bind_workspace_journal
from acquisition.conversations import ConversationExecution, WorkflowAdmissions
from acquisition.adapters.sqlite.admissions import SqliteAdmissions
from acquisition.workflows.conversation import validate_planning_assets


def build_contact_directory(path, organization, profile_key, clock=time.time, *, read_only=False):
    """Installed synthetic contact evidence only, without campaign or execution authority."""
    if not read_only:
        require_live_root(path)
    from acquisition.adapters.local_profiles import LocalProfiles
    from acquisition.adapters.contact_fixtures import RecordedContactSource, synthetic_contact_snapshots
    from acquisition.adapters.sqlite.contacts import SqliteContactDirectory
    from acquisition.adapters.sqlite.admission_guard import verified_required
    from acquisition.audiences import ContactDirectory
    profiles = LocalProfiles(organization, profile_key, Path(__file__).resolve().parents[2] / 'config/profiles')
    profile = profiles.campaign_profile(organization,profile_key,'v1')
    database = Database.existing(path) if read_only else Database(path)
    with database.connect() as db:
        if db.execute('PRAGMA user_version').fetchone()[0] < 18:
            raise Conflict('Migrate the live application store before inspecting contact evidence')
        if not read_only and verified_required(db):
            raise Conflict('Contact preparation has no verified execution capability; execution stays paused')
    source = RecordedContactSource(organization,tuple(synthetic_contact_snapshots(organization,profile)))
    store = SqliteContactDirectory(database,source,profiles,profile_key,'v1',clock,read_only=read_only)
    return ContactDirectory(source,store)


def build_profile_preparation(path, organization, profile_key, clock=time.time):
    """Explicit unapproved fixture preparation. No tasks, model or release capabilities."""
    require_live_root(path)
    from acquisition.adapters.local_profiles import LocalProfiles, SyntheticProfileAudience
    from acquisition.adapters.sqlite.profile_drafts import SqliteProfileDrafts
    from acquisition.creative import ProfileCopyService
    from acquisition.workflows.profile_preparation import ProfilePreparation
    profiles = LocalProfiles(organization, profile_key, Path(__file__).resolve().parents[2] / 'config/profiles')
    database = Database(path)
    # Do not write any intermediate inputs into paused/verified or restored stores.
    from acquisition.adapters.sqlite.admission_guard import verified_required
    with database.connect() as connection:
        if verified_required(connection):
            raise Conflict('Profile preparation has no verified admission capability; execution stays paused')
    require_live_root(database.path)
    audiences = SqliteAudiences(database)
    copy = ProfileCopyService(profiles)
    source = SyntheticProfileAudience()
    drafts = SqliteProfileDrafts(database, profiles, copy, source, clock)
    return ProfilePreparation(profiles, source, copy,
                              CampaignService(audiences, SqliteDrafts(database, clock), ()), drafts, clock)



def agent_catalogue():
    skills = json.loads((Path(__file__).resolve().parents[2] / "config/agent-skills-v1.json").read_text())
    return skills | {"tools": planner_tool_contracts() + grounded_tool_contracts() + audience_tool_contracts() + action_tool_contracts() + action_tool_contracts(True) + action_tool_contracts(typed=True),
                     "authority": "none", "status": "installed_contracts_not_dynamic_dispatch"}


def planning_assets(organization, knowledge):
    catalogue = agent_catalogue()
    payloads = {"planning": {k:v for k,v in knowledge.items() if k != "playbooks"}, "playbooks": knowledge["playbooks"]}
    sources = [source_manifest(organization, key, "authored_guidance", value, value["version"],
                              "project-authored planning guidance", {"basis": "frozen_at_admission"})
               for key,value in payloads.items()]
    return freeze_assets(organization, catalogue, planner_tool_contracts(), ["prepare-campaign/v1"], sources)


def copy_assets(organization, context, *, revision=False):
    payloads = copy_source_payloads(context)
    pack = context["product_facts"]
    specs = {
        "editorial": ("authored_guidance", context["guidance"]["version"], "project-authored editorial guidance", {"basis":"frozen_at_admission"}),
        "product_facts": ("product_evidence", pack["version"], pack["verification"],
                          {"basis":"existing_fact_pack_validation", "checked_on":pack["checked_on"], "review_by":pack["review_by"]}),
        "preferences": ("reviewer_preference", "reviewer-preferences/v1", "scoped local reviewer examples, not outcome evidence", {"basis":"frozen_at_admission"}),
        "outcomes": ("synthetic_observation", "synthetic-learning-memory/v1", "scoped mature synthetic cohort memory, advisory only", {"basis":"frozen_learning_snapshot"}),
        "audience": ("audience_summary", "synthetic-audience-summary/v1", "bounded synthetic snapshot summary, not verified customer need", {"basis":"frozen_audience_snapshot"}),
    }
    sources = [source_manifest(organization, key, kind, payloads[key], version, provenance, freshness)
               for key,(kind,version,provenance,freshness) in specs.items()]
    assets = freeze_assets(organization, agent_catalogue(), grounded_tool_contracts(),
                           ["revise-grounded-copy/v1" if revision else "grounded-copy/v1"], sources, model_projection="copy-context/v1")
    return context | {"agent_assets": assets}

def routing_assets(organization, context):
    catalogue=agent_catalogue()
    modern=context['schema']=='routing-context/v2'
    typed = context['schema'] == 'routing-context/v3'
    skill_id = 'route-followup/v3' if typed else 'route-followup/v2' if modern else 'route-followup/v1'
    skill=next(s for s in catalogue['skills'] if s['id']==skill_id)
    guidance={'version':'routing-guidance/v1','skill':skill,'aliases':ACTION_ALIASES | TYPED_ACTION_ALIASES if typed else ACTION_ALIASES}
    state={k:v for k,v in context.items() if k not in {'id','agent_assets','routing_guidance'}}
    sources=[source_manifest(organization,'routing','authored_guidance',guidance,'v1','project-authored routing skill and aliases',{'basis':'frozen_at_admission'}),
             source_manifest(organization,'task_state','task_observation',state,'v1','saved local task and campaign observations',{'basis':'observed_at','at':context['observed_at']})]
    value=state|{'routing_guidance':guidance,'agent_assets':freeze_assets(organization,catalogue,action_tool_contracts(modern, typed=typed),[skill_id],sources)}
    return value|{'id':'action_context_'+digest(value)}


def build_preparations(path, host, *, authoritative=False):
    if authoritative:
        from acquisition.adapters.sqlite.preparation_intents import SqlitePreparationIntents
        return PreparationCoordinator(SqlitePreparationIntents(Database(path)),host)
    return PreparationCoordinator(SqlitePreparations(path), host)


def build_workspace_state(root,clock=time.time):
    from acquisition.adapters.sqlite.workspace_state import SqliteWorkspaceState
    from acquisition.adapters.sqlite.workspace_sources import environment_source
    from acquisition.workflows.workspace_state import validate_environment, validate_environment_run
    from acquisition.conversations import WorkspaceState, EnvironmentIntent, environment_time
    pack=json.loads((Path(__file__).resolve().parents[2]/'config/iwoca-product-facts-v1.json').read_text())
    fixture_clock=datetime.fromisoformat(pack['checked_on']).replace(tzinfo=timezone.utc).timestamp()+43200
    def validate(db,session,kind,inputs,now,request_id):
        source=environment_source(db,session,kind,store.read);environment_time(now)
        session=dict(session);session['created_at']=now
        if session['parent_id']:
            session['clock']=max(source['parent']['clock'],now);session['clock_mode']='SIMULATED'
        else:
            session['clock']=now if session['mode']=='model' else max(fixture_clock,now) if session.get('audience_selection') else fixture_clock
            session['clock_mode']='REAL' if session['mode']=='model' else 'SIMULATED'
        validate_environment(session,kind,inputs,source,now,request_id,fixture_clock)
        return EnvironmentIntent.freeze(session)
    run_policy=partial(validate_environment_run,synthetic_snapshot_id=generated_snapshot_identity)
    store=SqliteWorkspaceState(root,Database.existing(Path(root)/'conversations.sqlite'),clock,validate,run_policy)
    return WorkspaceState(store)


def build_workspace_checkpoint():
    from acquisition.adapters.sqlite.workspace_checkpoint import SqliteWorkspaceCheckpoint
    return SqliteWorkspaceCheckpoint()

def initialize_fixture_workspace(root, clock=time.time):
    """Explicit local initialization, serialized against the workspace server."""
    root = Path(root)
    require_live_root(root)
    if root.is_symlink():
        raise Conflict('Use a fresh local fixture workspace directory')
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with workspace_root_lock(root):
        if any(path.name != 'server.lock' for path in root.iterdir()):
            raise Conflict('Fixture execution requires a fresh workspace root')
        database = root / 'conversations.sqlite'
        database.touch(mode=0o600, exist_ok=False)
        Database(database, verified_admissions=True, clock=clock, fixture_execution=True)

def build_checkpoint_reconciliation():
    from acquisition.adapters.sqlite.checkpoint_reconciliation import SqliteCheckpointReconciliation
    return SqliteCheckpointReconciliation()


def build_workspace_projection(root):
    """Offline reconstruction only. Never create, seal, migrate or execute source stores."""
    from acquisition.adapters.sqlite.workspace_projection import ReadOnlyDatabase, SqliteWorkspaceProjection
    from acquisition.adapters.sqlite.workspace_state import SqliteWorkspaceState
    from acquisition.workflows.workspace_state import validate_environment_run
    from acquisition.conversations import WorkspaceProjectionRebuild
    root=Path(root)
    if not (root/'conversations.sqlite').resolve().is_relative_to(root.resolve()):
        raise Conflict('The authoritative source must remain inside its server-owned root')
    source=SqliteWorkspaceState(root,ReadOnlyDatabase.existing(root/'conversations.sqlite'),None,None,
                               partial(validate_environment_run,synthetic_snapshot_id=generated_snapshot_identity))
    return WorkspaceProjectionRebuild(source,SqliteWorkspaceProjection(root))


def build_legacy_migration_inventory(root):
    """Offline legacy ownership migration, without workspace startup or providers."""
    from acquisition.adapters.sqlite.legacy_migration import SqliteLegacyMigration
    from acquisition.adapters.sqlite.workspace_state import SqliteWorkspaceState
    from acquisition.workflows.workspace_state import validate_environment_run
    from acquisition.conversations import LegacyMigrationInventory
    # read() uses the inventory's already pinned read-only connection. Its
    # complete link checks are shared with normal workspace and rebuild reads.
    environments=SqliteWorkspaceState(root,None,None,None,
        partial(validate_environment_run,synthetic_snapshot_id=generated_snapshot_identity))
    return LegacyMigrationInventory(SqliteLegacyMigration(root,environments.read))


def verified_admission_mode(path):
    from acquisition.adapters.sqlite.admission_guard import read_admission_policy
    return read_admission_policy(path)


def build_admissions(path, clock=time.time, *, _database=None, verified_admissions=False):
    """Compose admissions, selecting the paused format at database opening when requested."""
    from acquisition.adapters.sqlite.admission_sources import load_source
    from acquisition.workflows.admission_coverage import campaign_brief, coverage_intent
    def workflow_source(db, organization, kind, references, now):
        return load_source(db,organization,kind,references,now,campaign_brief)
    def preflight(frozen, organization, fixture, config):
        if 'agent_assets' not in frozen['knowledge']:
            raise ValueError('New admissions require versioned planning assets')
        validate_planning_assets(frozen,organization)
        if frozen.get('knowledge_id')!='knowledge_'+digest(frozen['knowledge']):
            raise ValueError('Frozen planning guidance failed integrity checks')
        if fixture:
            ConversationPlanner.preflight_fixture(frozen,organization)
        else:
            # prepare_request only sizes/validates the envelope. No provider or
            # journal is available to this deliberately paused storage API.
            ConversationPlanner(Inference(None,None,config,clock)).preflight(frozen)
    if _database is not None and verified_admissions:
        raise ValueError('Select verified admissions while opening the database')
    return SqliteAdmissions(_database or Database(path,verified_admissions=verified_admissions,clock=clock),preflight,clock,
                            workflow_source=workflow_source,workflow_intent=coverage_intent)


@dataclass
class Application:
    tasks: TaskStore
    audiences: SqliteAudiences
    drafts: SqliteDrafts
    worker: Worker
    clock: Callable[[], float]
    catalogue_hash: str
    memory: SqliteCreative
    calls: SqliteCalls
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
                legacy=self._legacy_campaign(organization,request_id,generate(organization,size,seed,as_of).id,brief,parent_run_id=parent_run_id)
                if legacy is not None:return legacy
            command={'method':'start','size':size,'seed':seed,'as_of':as_of,'brief':asdict(brief),
                     'campaign_id':campaign_id,'parent_run_id':parent_run_id}
            def references():
                refs={'brief':asdict(brief),'snapshot_id':self.audiences.put(generate(organization,size,seed,as_of)),
                      'runtime_request_id':request_id}
                if parent_run_id:refs['parent_run_id']=parent_run_id
                return refs
            return self.admissions.workflow(organization,request_id,'manual-descendant' if parent_run_id else 'standalone-campaign',
                command,references,allow_model=False,config=None)
        if parent_run_id:raise ValueError('Explicit parent-run creation requires verified admission cutover')
        snapshot_id = self.audiences.put(generate(organization, size, seed, as_of))
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
                snapshot=snapshot_override or generate(organization,size,seed,as_of)
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
        snapshot = snapshot_override or generate(organization, size, seed, as_of)
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
            config_root = Path(__file__).resolve().parents[2] / "config"
            guidance = json.loads((config_root / "editorial-v3.json").read_text())
            product_facts = json.loads((config_root / "iwoca-product-facts-v1.json").read_text())
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
                contexts[segment] = self.memory.put_context(organization, copy_assets(organization, context))
        return snapshot_id, contexts

    def followup_population(self, organization, as_of):
        return generate(organization, 2000, 42, as_of)

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
        root = Path(__file__).resolve().parents[2] / "config"
        guidance = json.loads((root / "editorial-v3.json").read_text())
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
            contexts[segment] = self.memory.put_context(organization,copy_assets(organization, context))
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
                snapshot_id=frozen['snapshot_id'] if selection else generate(organization,1000,42,as_of).id
                return self._legacy_campaign(organization,request_id,snapshot_id,brief,
                    model=plan['copy_mode']=='model',objective=plan['objective'])
        if self.admissions.required() and plan['copy_mode']=='fixture':
            def references():
                if selected_audience:
                    snapshot,_=self.conversation_audiences.materialize('local-conversations',plan['conversation_id'],plan['revision'],plan['id'],organization)
                else:snapshot=generate(organization,1000,42,as_of)
                return {'plan_id':plan['id'],'snapshot_id':self.audiences.put(snapshot)}
            return self.admissions.workflow(organization,request_id,'conversation-campaign',
                {'method':'start-conversation','plan':plan,'as_of':as_of,'selected_audience':selected_audience},
                references,allow_model=False,config=None)
        snapshot, selection = self.conversation_audiences.materialize("local-conversations", plan["conversation_id"], plan["revision"], plan["id"], organization) if selected_audience else (None, None)
        brief = conversation_brief_from_plan(plan, request_id, selection)
        if plan["copy_mode"] == "model":
            return self.start_model(organization, request_id, as_of=as_of, conversation_brief=brief, objective=plan["objective"], snapshot_override=snapshot)
        snapshot_id = self.audiences.put(snapshot if snapshot is not None else generate(organization, 1000, 42, as_of))
        return self.tasks.create(organization, request_id, conversation_task_plan(snapshot_id, brief, self.catalogue_hash), self.clock())

    def export(self, organization: str, run_id: str, directory: Path) -> Path:
        state = self.tasks.inspect(organization, run_id)
        outputs = [task["output"] for task in state["tasks"] if task["output"] and task["output"].get("draft_id")]
        if not outputs:
            raise ValueError("No committed draft receipt exists yet")
        draft = self.drafts.get(organization, outputs[-1]["draft_id"])
        return self._export_draft(organization, draft, directory)

    def export_review(self, organization: str, case_id: str, directory: Path, expected_subject: str | None = None) -> Path:
        view = self.reviews.store.view(organization, case_id)
        if expected_subject is not None and view["subject"]["id"] != expected_subject:
            from acquisition.contracts import Conflict
            raise Conflict("Review changed before export; request a fresh report")
        draft = self.drafts.get(organization, view["subject"]["draft_id"])
        return self._export_draft(organization, draft, directory)

    def _export_draft(self, organization, draft, directory):
        context_ids = {item["context_id"] for item in draft.manifest["creatives"] if item.get("fact_pack_id")}
        contexts = tuple(self.memory.get_context(organization, identity) for identity in sorted(context_ids))
        return export_draft(draft, directory, contexts)


def build(path: str | Path, clock: Callable[[], float] = time.time,
          gateway: ModelGateway | None = None, model_config: ModelConfig | None = None,
          workspace_organization: str | None = None, *, verified_admissions=False,
          execution_clock: Callable[[], float] | None = None,
          preference_organization: str | None = None) -> Application:
    if type(verified_admissions) is not bool:raise ValueError('Choose an explicit admission mode')
    database = Database(path,verified_admissions=verified_admissions,clock=clock)
    admission_store=build_admissions(path,clock,_database=database)
    admissions=WorkflowAdmissions(admission_store,clock)
    if workspace_organization is not None and not inspection_only(path) and not admissions.required():
        bind_workspace_journal(database,workspace_organization)
    execution_clock = execution_clock or clock
    audiences, drafts = SqliteAudiences(database), SqliteDrafts(database, clock, execution_clock=execution_clock)
    tasks = SqliteTasks(database, retired_capabilities=ModelMonthlyMail.legacy_capabilities(), execution_clock=execution_clock)
    campaigns = CampaignService(audiences, drafts, fixture_catalog())
    workflow = MonthlyMail(audiences, campaigns)
    memory, calls = SqliteCreative(database, preference_organization), SqliteCalls(database, clock)
    inference = Inference(gateway, calls, model_config, clock) if gateway is not None and model_config is not None else None
    model_workflow = ModelMonthlyMail(audiences, campaigns, memory, inference)
    conversation_model = ConversationModelMail(audiences, campaigns, memory, inference)
    planner_config = replace(model_config, max_calls=2, force_tool_choice=True) if model_config else None
    planner_inference = Inference(gateway, calls, planner_config, clock) if planner_config and (gateway is not None or admissions.required()) else None
    planner = ConversationPlanner(planner_inference)
    router_config = replace(model_config,max_calls=1,force_tool_choice=True) if model_config else ModelConfig("openai/gpt-oss-120b",max_calls=1,force_tool_choice=True)
    router_inference = Inference(gateway,calls,router_config,clock)
    router = ConversationRouter(router_inference)
    actions = ConversationActions(SqliteConversationActions(database,clock),tasks,clock,router_config,router.preflight,routing_assets,admissions)
    def planning_guidance():
        return json.loads((Path(__file__).resolve().parents[2] / "config/campaign-playbooks-v1.json").read_text())
    conversations = ConversationService(SqliteConversations(database), tasks, calls, clock,
                                        planner_config if (planner_inference or admissions.required()) else None, planner.preflight, planning_guidance, planning_assets,admissions)
    reviews = SqliteReviews(database, clock, SqliteSimulatedDelivery)
    revision_config = replace(model_config, max_calls=5, force_tool_choice=True) if model_config else None
    revision_inference = Inference(gateway, calls, revision_config, clock) if inference else None
    revision_workflow = CopyRevisionWorkflow(campaigns, drafts, memory, revision_inference, reviews)
    def revision_admission(organization,receipt,config):
        if not admissions.required():return None
        if canonical(reviews.revision_request(organization,receipt['request_id']))!=canonical(receipt):
            raise Conflict('Revision continuation differs from its saved source admission')
        def legacy_plan():
            context_id='context_'+digest({'organization':organization,**receipt['context']})
            if canonical(memory.get_context(organization,context_id))!=canonical(receipt['context']):
                raise Conflict('Legacy revision context differs from its native receipt')
            inputs=receipt['task_inputs']|{'context_id':context_id}
            return [TaskSpec('creative.revise_copy.v3',inputs),TaskSpec('reviews.publish_copy_revision.v3',inputs)]
        legacy=admissions.legacy_workflow(organization,receipt['id'],legacy_plan)
        if legacy is not None:return legacy
        refs={'revision_request_id':receipt['request_id']}
        request=admissions.source_request_id(organization,'copy-revision',receipt['id'],receipt['request_id'],refs)
        return admissions.workflow(organization,request,'copy-revision',
            refs,lambda:refs,
            allow_model=True,config=config)
    revision_service = CopyRevisionService(reviews, drafts, memory, tasks, clock, revision_config, copy_assets,revision_admission)
    discovery = AudienceDiscovery(LocalAudienceSource(Path(__file__).resolve().parents[2] / "config/audience-catalogue"), clock)
    learning_store = SqliteLearning(database, clock)
    learning = LearningService(learning_store, AcceptedCohortSource(reviews, drafts),
                               LocalSyntheticReports(), SqliteReportMonitoring(learning_store))
    capabilities = revision_workflow.capabilities() | workflow.capabilities() | ConversationMail(audiences, campaigns).capabilities() | model_workflow.capabilities() | conversation_model.capabilities() | {PLANNER_CAPABILITY: planner.plan, FIXTURE_CAPABILITY: planner.fixture_plan, ACTION_CAPABILITY:router.route, COPY_ACTION_CAPABILITY:router.route, TYPED_ACTION_CAPABILITY:router.route}
    return Application(tasks, audiences, drafts, Worker(tasks, capabilities, execution_clock, lease_seconds=180 if inference else 60,
                       eligible=lambda capability, inputs: model_workflow.eligible(capability, inputs) and conversation_model.eligible(capability, inputs) and planner.eligible(capability, inputs) and revision_workflow.eligible(capability, inputs) and router.eligible(capability, inputs)), clock,
                       campaigns.catalogue_hash, memory, calls, inference,
                       ReviewService(reviews),
                       learning, conversations, revision_service, SqliteFollowups(database),
                       discovery, ConversationAudiences(conversations, discovery, SqliteAudienceSelections(database, clock), audiences, clock), actions,
                       ConversationExecution(SqliteExecution(database), clock),admissions,model_config)
