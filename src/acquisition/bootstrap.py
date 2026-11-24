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
from acquisition.adapters.learning_report import write_learning
from acquisition.adapters.review_report import write_review
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


def build_contact_directory(path, organization, profile_key, clock=time.time, *, read_only=False, remote_storage=None, _database=None):
    """Installed synthetic contact evidence only, without campaign or execution authority."""
    if not read_only and remote_storage is None:
        require_live_root(path)
    from acquisition.adapters.local_profiles import LocalProfiles
    from acquisition.adapters.contact_fixtures import RecordedContactSource, synthetic_contact_snapshots
    from acquisition.adapters.sqlite.contacts import SqliteContactDirectory
    from acquisition.adapters.sqlite.admission_guard import verified_required
    from acquisition.audiences import ContactDirectory
    profiles = LocalProfiles(organization, profile_key, Path(__file__).resolve().parents[2] / 'config/profiles')
    profile = profiles.campaign_profile(organization,profile_key,'v1')
    database = _database or build_database(path, clock=clock, remote_storage=remote_storage, read_only=read_only)
    with database.connect() as db:
        if db.execute('PRAGMA user_version').fetchone()[0] < 18:
            raise Conflict('Migrate the live application store before inspecting contact evidence')
        if not read_only and verified_required(db):
            raise Conflict('Contact preparation has no verified execution capability; execution stays paused')
    source = RecordedContactSource(organization,tuple(synthetic_contact_snapshots(organization,profile)))
    store = SqliteContactDirectory(database,source,profiles,profile_key,'v1',clock,read_only=read_only)
    return ContactDirectory(source,store)


def build_audience_decisions(path, organization, profile_key, strategy='taxonomy-order', clock=time.time, *, read_only=False, remote_storage=None, _database=None):
    """Offline advisory strategies and deterministic constraints; no campaign/outbound authority."""
    from acquisition.adapters.audience_strategies import (DeclaredSegmentCategorizer, TaxonomyOrderDecision,
                                                         ReverseTaxonomyDecision)
    from acquisition.adapters.sqlite.audience_decisions import SqliteAudienceDecisions
    from acquisition.audiences import AudienceDecisions
    if strategy not in {'taxonomy-order','reverse-taxonomy-test'}:
        raise ValueError('Select an installed offline audience strategy')
    contacts = build_contact_directory(path,organization,profile_key,clock,read_only=read_only,remote_storage=remote_storage,_database=_database)
    profile = contacts.store._profile(organization)
    categorizer = DeclaredSegmentCategorizer(profile.taxonomy,profile.objective)
    decision = (TaxonomyOrderDecision if strategy=='taxonomy-order' else ReverseTaxonomyDecision)(profile.taxonomy,profile.objective)
    store = SqliteAudienceDecisions(contacts.store,categorizer.spec,decision.spec)
    return AudienceDecisions(categorizer,decision,store)


def build_recipient_contexts(path, organization, profile_key, clock=time.time, *, guidance=None, read_only=False, remote_storage=None, _database=None):
    """Reviewed synthetic context only. No raw document prompts, inference or outbound authority."""
    from acquisition.adapters.recipient_fixtures import RecordedRecipientContextSource, synthetic_recipient_evidence
    from acquisition.adapters.sqlite.recipient_contexts import SqliteRecipientContexts
    from acquisition.creative import RecipientContexts, RecipientContextGuidance
    contacts = build_contact_directory(path,organization,profile_key,clock,read_only=read_only,remote_storage=remote_storage,_database=_database)
    with contacts.store.database.connect() as db:
        if db.execute('PRAGMA user_version').fetchone()[0]<19:
            raise Conflict('Migrate the live application store before inspecting recipient context')
    evidence = tuple(item for suffix in ('a','b') for item in synthetic_recipient_evidence(
        contacts.source.read(organization,profile_key+'-crm-'+suffix,1)))
    source = RecordedRecipientContextSource(organization,evidence)
    selected_guidance = guidance if guidance is not None else RecipientContextGuidance()
    if type(selected_guidance) is not RecipientContextGuidance: raise ValueError('Use typed frozen context guidance')
    store = SqliteRecipientContexts(contacts.store,source,selected_guidance,read_only=read_only)
    return RecipientContexts(source,store,selected_guidance)


def build_channel_preparation(path, organization, profile_key, clock=time.time, *, gateway=None, read_only=False,
                              stage_ownership=False, remote_storage=None, _database=None):
    """Installed offline model simulation only; no paid model, sender or review capability."""
    from acquisition.adapters.channel_fixtures import OfflineChannelModel
    from acquisition.adapters.sqlite.channel_content import SqliteChannelContent, SqliteChannelTasks
    from acquisition.workflows.channel_content import ChannelContentWorkflow, ChannelPreparation, compose_channel_admission
    from acquisition.reasoning import ModelConfig
    from acquisition.creative import CHANNEL_CONTENT_CAPABILITY, PAUSED_CHANNEL_ADMISSION, SYNTHETIC_CHANNEL_ADMISSION
    recipients = build_recipient_contexts(path,organization,profile_key,clock,read_only=read_only,remote_storage=remote_storage,_database=_database)
    with recipients.store.contacts.database.connect() as db:
        if db.execute('PRAGMA user_version').fetchone()[0]<20:
            raise Conflict('Migrate the live store before inspecting channel artifacts')
    config = ModelConfig('offline/channel-content-v1',max_calls=5,max_output_tokens=2400,max_input_bytes=32000,
        max_prompt_usd_per_million=0,max_completion_usd_per_million=0,force_tool_choice=True)
    catalogue = json.loads((Path(__file__).resolve().parents[2]/'config/channel-skills-v1.json').read_text())
    database = recipients.store.contacts.database
    admission_version = PAUSED_CHANNEL_ADMISSION if stage_ownership else SYNTHETIC_CHANNEL_ADMISSION
    store = SqliteChannelContent(recipients.store,recipients.store.contacts.profiles,profile_key,catalogue,
        SqliteCreative(database),config,clock,partial(compose_channel_admission,workflow_version=admission_version),
        read_only=read_only)
    tasks = SqliteChannelTasks(store)
    inference = Inference(gateway if gateway is not None else OfflineChannelModel(),
                          SqliteCalls(database,clock,channel=store),config,clock)
    workflow = ChannelContentWorkflow(store,inference)
    worker = Worker(tasks,{CHANNEL_CONTENT_CAPABILITY:workflow.generate},clock,lease_seconds=180,eligible=workflow.eligible)
    return ChannelPreparation(store,worker,tasks,inference)


def build_sequence_simulation(path, organization, profile_key, clock=time.time, *,
                              email_scenario='success', call_scenario='success', read_only=False, remote_storage=None, _database=None):
    """Exact reviewed synthetic sequences only. No live provider or outbound authority."""
    from acquisition.adapters.simulated_engagements import synthetic_sequence_connections, SyntheticEngagementTransport
    from acquisition.adapters.sqlite.sequence_proposals import SqliteSequenceProposals
    from acquisition.adapters.sqlite.engagements import SqliteEngagements
    from acquisition.adapters.sqlite.sequence_reviews import SqliteSequenceReviews
    from acquisition.reviews import SequenceReviews
    from acquisition.campaigns import SequenceCampaigns
    from acquisition.engagements import EngagementSimulator
    from acquisition.workflows.sequences import SequenceSimulation
    channels=build_channel_preparation(path,organization,profile_key,clock,read_only=read_only,remote_storage=remote_storage,_database=_database)
    decisions=build_audience_decisions(path,organization,profile_key,clock=clock,read_only=read_only,remote_storage=remote_storage,_database=_database)
    with channels.store.database.connect() as db:
        if db.execute('PRAGMA user_version').fetchone()[0]<(21 if read_only else 22):
            raise Conflict('Migrate the live store before reviewing sequences')
    connections=synthetic_sequence_connections(organization,profile_key)
    proposals=SqliteSequenceProposals(channels.store,decisions.store,connections,clock,read_only=read_only)
    reviews=SqliteSequenceReviews(proposals)
    simulator=EngagementSimulator(SqliteEngagements(proposals,reviews),
        SyntheticEngagementTransport(connections['email'],email_scenario),
        SyntheticEngagementTransport(connections['human_call'],call_scenario))
    return SequenceSimulation(SequenceCampaigns(proposals),simulator,SequenceReviews(reviews))


def build_sequence_journeys(path,clock=time.time,*,stage_ownership=False, remote_storage=None, read_only=False, _database=None, _gateway=None, _preparation_clock=False):
    """Wire bounded conversation continuation to installed synthetic module APIs."""
    from acquisition.adapters.local_profiles import LocalProfiles
    from acquisition.adapters.contact_fixtures import synthetic_contact_snapshots
    from acquisition.adapters.sequence_interpreter import OfflineSequenceInterpreter
    from acquisition.adapters.sqlite.sequence_journeys import SqliteSequenceJourneys
    from acquisition.conversations import SequenceJourneys
    from acquisition.workflows.sequence_journey import JourneyCapabilities, SequenceJourneyWorkflow
    database=_database or build_database(path,clock=clock,remote_storage=remote_storage,read_only=read_only)
    store=SqliteSequenceJourneys(database,clock)
    config_root=Path(__file__).resolve().parents[2]/'config/profiles'
    def catalogue(organization):
        profiles=[]
        for key in ('iwoca','fielddesk'):
            native='sequence_scope_'+digest({'owner_organization':organization,'profile_key':key})[:40]
            installed=LocalProfiles(native,key,config_root)
            profile=installed.campaign_profile(native,key,'v1')
            connections=[]
            for snapshot in synthetic_contact_snapshots(native,profile):
                if snapshot.version!=1:continue
                primary=snapshot.connection.key.endswith('-a')
                connections.append({'key':snapshot.connection.key,'version':snapshot.version,
                    'source_id':snapshot.id,'connection_id':snapshot.connection.id,'primary':primary,
                    'label':('Primary' if primary else 'Secondary')+' synthetic CRM',
                    'aliases':['primary crm','crm a'] if primary else ['secondary crm','crm b']})
            profiles.append({'key':key,'organization':native,'profile_id':profile.id,
                'product_profile_id':installed.product.id,'label':installed.product.brand_name,
                'aliases':['iwoca','flexi loan','flexi-loan'] if key=='iwoca' else ['fielddesk','field desk'],
                'connections':connections,'segments':[{'key':s.key,'label':s.label} for s in profile.taxonomy.segments]})
        return {'schema':'installed-conversational-sequences/v1','organization':organization,'profiles':profiles,
            **({'preparation_clock':'real-invocation/v1','preparation_cadence':'synthetic-hourly/v1'} if _preparation_clock else {}),
            'mode':'SYNTHETIC_ONLY','strategy':'taxonomy-order','channels':['email','human_call','followup'],
            'model_config':ModelConfig('offline/channel-content-v1',max_calls=5,max_output_tokens=2400,
                max_input_bytes=32000,max_prompt_usd_per_million=0,max_completion_usd_per_million=0,
                force_tool_choice=True).payload(),
            'max_content_runs':3,'max_calls':15,'shared_conversation_call_limit':48,'authority':'none'}
    def capabilities(frozen,inspection):
        native=frozen['native_organization'];key=frozen['interpretation']['profile_key']
        scoped_clock=clock if frozen['catalogue'].get('preparation_clock')=='real-invocation/v1' else lambda:store.simulation_time(frozen['organization'],frozen['id'])
        directory=build_contact_directory(path,native,key,scoped_clock,read_only=inspection,remote_storage=remote_storage,_database=database)
        audiences=build_audience_decisions(path,native,key,clock=scoped_clock,read_only=inspection,remote_storage=remote_storage,_database=database)
        contexts=build_recipient_contexts(path,native,key,scoped_clock,read_only=inspection,remote_storage=remote_storage,_database=database)
        channels=build_channel_preparation(path,native,key,scoped_clock,read_only=inspection,
                                           stage_ownership=stage_ownership,remote_storage=remote_storage,_database=database,gateway=_gateway)
        sequence=build_sequence_simulation(path,native,key,scoped_clock,read_only=inspection,remote_storage=remote_storage,_database=database)
        def initialize_reviewers():
            roles=SqliteReviews(sequence.campaigns.store.database,scoped_clock,SqliteSimulatedDelivery)
            roles.initialize_actor(native,'local-operator',('operator',))
            roles.initialize_actor(native,'local-reviewer',('reviewer',))
        return JourneyCapabilities(directory,audiences,contexts,channels,sequence,initialize_reviewers)
    host=SequenceJourneyWorkflow(store,catalogue,capabilities)
    return SequenceJourneys(store,host,OfflineSequenceInterpreter(),clock)


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



def channel_agent_catalogue():
    """Content-only skill/tool discovery, separately versioned from historical postal assets."""
    from acquisition.creative import channel_tool_contracts
    catalogue = json.loads((Path(__file__).resolve().parents[2]/'config/channel-skills-v1.json').read_text())
    tools = {tool['id']:tool for channel in ('email','human_call') for tool in channel_tool_contracts(channel)}
    return catalogue | {'tools':list(tools.values()),'authority':'none','status':'installed_contracts_not_dynamic_dispatch'}


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


def build_workspace_state(root, clock=time.time):
    """Compose compatibility storage now and authoritative state only on demand."""
    from acquisition.application.workspace import WorkspaceStateAccess
    from acquisition.adapters.sqlite.workspace_control import SqliteWorkspaceControl, SqliteWorkspaceFaults
    faults = SqliteWorkspaceFaults()
    return WorkspaceStateAccess(SqliteWorkspaceControl(root, faults),
                                lambda: _build_workspace_authority(root, clock), faults)


def _build_workspace_authority(root,clock=time.time):
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


def build_database(path, *, clock=time.time, verified_admissions=False, remote_storage=None, read_only=False):
    """Explicit storage selection; remote credentials never enter domain values."""
    if read_only and verified_admissions:raise ValueError('Cannot select execution policy through a read-only opening')
    if remote_storage is None:
        return Database.existing(path) if read_only else Database(path, verified_admissions=verified_admissions, clock=clock)
    if path is not None:
        raise ValueError('Remote storage cannot replace a local root implicitly')
    from acquisition.adapters.turso import TursoDatabase
    return TursoDatabase(remote_storage['url'], remote_storage['token'], clock=clock,
                         verified_admissions=verified_admissions, initialize=not read_only, deadline=remote_storage.get('deadline'))


def build_intake(path, clock=time.time, *, remote_storage=None, read_only=False, verified_admissions=False):
    """Internal intake API; the caller supplies trusted organization and actor scope.

    No hosted access or inferred campaign capability is activated here.
    """
    from acquisition.campaigns import CampaignIntake
    from acquisition.adapters.sqlite.intake import SqliteCampaignIntake
    database = build_database(path, clock=clock, remote_storage=remote_storage, read_only=read_only,
                              verified_admissions=verified_admissions)
    return CampaignIntake(SqliteCampaignIntake(database, read_only=read_only), clock)


def build_youtube(path, clock=time.time, *, organization='local-conversations', actor='local-operator',
                  origin='http://127.0.0.1:8768', read_only=False, verified_admissions=False,
                  remote_storage=None, authority=None, assets=None):
    """Install one explicit zero-provider authored capability in a local live store."""
    from acquisition.youtube import YouTubeScope, YouTubeCampaigns, CAPABILITY, PROFILE
    from acquisition.adapters.youtube_fixture import FIXTURE, BundledComparisonAssets
    from acquisition.adapters.sqlite.youtube import SqliteYouTube, SqliteYouTubeTasks, SqliteYouTubeAuthority
    from acquisition.workflows.youtube_preparation import (compose_youtube_admission,
                                                         AuthoredYouTubeHandler, YouTubePreparation)
    database = build_database(path, clock=clock, remote_storage=remote_storage, read_only=read_only,
                              verified_admissions=verified_admissions)
    reviewer = actor if authority is not None else 'local-reviewer'
    initialize_authority = None
    if authority is None:
        authority = SqliteYouTubeAuthority(database, organization, PROFILE, actor, reviewer)
        def initialize_authority():
            # Configure trusted local defaults only at an explicit submission.
            # Reads never create authority; missing roles in existing native
            # history cannot be silently reinstated by reopening or replay.
            if read_only:
                return
            from acquisition.adapters.sqlite.admission_guard import verified_required
            with database.connect() as connection:
                if verified_required(connection) or connection.execute(
                    'SELECT 1 FROM youtube_requests WHERE organization=? LIMIT 1', (organization,)).fetchone():
                    return
            roles = SqliteReviews(database, clock, None)
            roles.initialize_actor(organization, actor, ('operator',))
            roles.initialize_actor(organization, reviewer, ('reviewer',))
    assets = assets or BundledComparisonAssets(Path(__file__).resolve().parents[2] / 'examples/youtube-media', origin)
    store = SqliteYouTube(database, authority, assets, FIXTURE, clock, compose_youtube_admission, read_only=read_only)
    campaigns = YouTubeCampaigns(store, YouTubeScope(organization), actor, reviewer=reviewer)
    tasks = SqliteYouTubeTasks(database, store, clock)
    handler = AuthoredYouTubeHandler(store, FIXTURE)
    worker = Worker(tasks, {CAPABILITY: handler.prepare}, clock,
                    eligible=lambda capability, inputs: capability == CAPABILITY)
    return YouTubePreparation(campaigns, tasks, worker, initialize_authority=initialize_authority)


def build_admissions(path, clock=time.time, *, _database=None, verified_admissions=False, remote_storage=None):
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
    if remote_storage is not None and _database is not None:
        raise ValueError('Select one storage composition')
    database = _database or build_database(path, clock=clock, verified_admissions=verified_admissions,
                                           remote_storage=remote_storage)
    from acquisition.adapters.turso import TursoDatabase, TursoAdmissions
    adapter = TursoAdmissions if isinstance(database, TursoDatabase) else SqliteAdmissions
    return adapter(database,preflight,clock,
                            workflow_source=workflow_source,workflow_intent=coverage_intent)


from acquisition.workflows.campaign_application import Application


def build(path: str | Path, clock: Callable[[], float] = time.time,
          gateway: ModelGateway | None = None, model_config: ModelConfig | None = None,
          workspace_organization: str | None = None, *, verified_admissions=False,
          execution_clock: Callable[[], float] | None = None,
          preference_organization: str | None = None, remote_storage=None) -> Application:
    if type(verified_admissions) is not bool:raise ValueError('Choose an explicit admission mode')
    if remote_storage is not None and workspace_organization is not None:
        raise ValueError('Hosted workspace identity requires its own composition')
    database = build_database(path, clock=clock, verified_admissions=verified_admissions, remote_storage=remote_storage)
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
    from acquisition.youtube import CAPABILITY as YOUTUBE_CAPABILITY
    capabilities = revision_workflow.capabilities() | workflow.capabilities() | ConversationMail(audiences, campaigns).capabilities() | model_workflow.capabilities() | conversation_model.capabilities() | {PLANNER_CAPABILITY: planner.plan, FIXTURE_CAPABILITY: planner.fixture_plan, ACTION_CAPABILITY:router.route, COPY_ACTION_CAPABILITY:router.route, TYPED_ACTION_CAPABILITY:router.route}
    return Application(tasks, audiences, drafts, Worker(tasks, capabilities, execution_clock, lease_seconds=180 if inference else 60,
                       eligible=lambda capability, inputs: capability != YOUTUBE_CAPABILITY and model_workflow.eligible(capability, inputs) and conversation_model.eligible(capability, inputs) and planner.eligible(capability, inputs) and revision_workflow.eligible(capability, inputs) and router.eligible(capability, inputs)), clock,
                       campaigns.catalogue_hash, memory, calls, inference,
                       ReviewService(reviews),
                       learning, conversations, revision_service, SqliteFollowups(database),
                       discovery, ConversationAudiences(conversations, discovery, SqliteAudienceSelections(database, clock), audiences, clock), actions,
                       ConversationExecution(SqliteExecution(database), clock),admissions,model_config,
                       generate, _campaign_assets, lambda *a, **k: copy_assets(*a, **k),
                       lambda draft, directory, contexts: export_draft(draft, Path(directory), contexts),
                       write_learning, write_review)


def _campaign_assets():
    config = Path(__file__).resolve().parents[2] / 'config'
    return {'product_facts': json.loads((config / 'iwoca-product-facts-v1.json').read_text()),
            'editorial': json.loads((config / 'editorial-v3.json').read_text())}


def _workspace_knowledge(facts):
    config = Path(__file__).resolve().parents[2] / 'config'
    editorial = json.loads((config / 'editorial-v3.json').read_text())
    return {'agent_catalogue': agent_catalogue(),
            'playbooks': json.loads((config / 'campaign-playbooks-v1.json').read_text()),
            'product_facts': facts,
            'editorial': {key: editorial[key] for key in ('version', 'rules', 'situations')},
            'learning': 'Synthetic outcome memory is scoped to each campaign and is advisory. Inspect it in Learning.'}


def _workspace_assets():
    facts = json.loads((Path(__file__).resolve().parents[2] / 'config/iwoca-product-facts-v1.json').read_text())
    return {'product_facts': facts, 'knowledge': lambda: _workspace_knowledge(facts)}


def workspace_key(path=None):
    from acquisition.adapters.environment import openrouter_key
    return openrouter_key(Path('.env.local') if path is None else path)


def workspace_key_available():
    return bool(workspace_key())


def workspace_gateway(key):
    from acquisition.adapters.openrouter import OpenRouter
    return OpenRouter(key)


class ScopedWorkspaceApplications:
    """Bounded construction for server-resolved workspace scopes, not a container."""
    def __init__(self, root, real_clock):
        self.root, self.real_clock = root, real_clock
        self._youtube_apps = {}

    def verified_mode(self, *, select=False):
        path = self.root / 'conversations.sqlite'
        if select: build_admissions(path, self.real_clock, verified_admissions=True)
        return path.exists() and verified_admission_mode(path)

    def intake(self, *, verified):
        return build_intake(self.root / 'conversations.sqlite', self.real_clock, verified_admissions=verified)

    def youtube(self, *, verified, origin):
        if origin not in self._youtube_apps:
            self._youtube_apps[origin] = build_youtube(self.root / 'conversations.sqlite', self.real_clock, origin=origin,
                                                       verified_admissions=verified)
        return self._youtube_apps[origin]

    def campaign(self, organization, database_scope, clock, *, verified, legacy, gateway, model_config):
        if database_scope not in {'campaign', 'conversations'}:
            raise ValueError('Use a server-resolved workspace store scope')
        path = self.root / 'conversations.sqlite' if database_scope == 'conversations' else self.root / organization / 'campaign.sqlite'
        if verified and legacy and (not path.is_file() or not path.resolve().is_relative_to(self.root.resolve())):
            raise Conflict('Restore the original legacy application store before inspection')
        return build(path, clock=clock, gateway=gateway, model_config=model_config,
                     workspace_organization=organization, verified_admissions=verified,
                     preference_organization='local-conversations' if database_scope == 'conversations' else None,
                     **({'execution_clock': self.real_clock} if verified else {}))

    def conversation(self, *, verified, gateway, model_config):
        return build(self.root / 'conversations.sqlite', clock=self.real_clock, gateway=gateway,
                     model_config=model_config, workspace_organization='local-conversations', verified_admissions=verified)


def build_workspace(root, real_clock=time.time, *, verified_admissions=False, model_sessions=None, gateway_factory=None):
    from threading import RLock
    from acquisition.application.workspace import Workspace
    from acquisition.adapters.models.workspace_sessions import WorkspaceSessions
    from acquisition.workflows.preparation_host import WorkspacePreparationHost
    if type(verified_admissions) is not bool:raise ValueError('Choose an explicit admission mode')
    root = Path(root)
    require_live_root(root)
    root.mkdir(parents=True, exist_ok=True)
    state = build_workspace_state(root, real_clock)
    models = model_sessions if model_sessions is not None else WorkspaceSessions(gateway_factory or (lambda: workspace_gateway(workspace_key())),
        legacy_available=(lambda: True) if gateway_factory else (lambda: workspace_key_available()))
    lock = RLock()
    host = WorkspacePreparationHost(
        lambda *a, **k: workspace._conversation_app(*a, **k),
        lambda *a, **k: workspace.draft_conversation(*a, **k),
        lambda *a, **k: workspace.draft_generation(*a, **k),
        Workspace._run_generation, models, lock)
    legacy = build_preparations(root / 'workspace.sqlite', host)
    workspace = Workspace(root, real_clock, applications=ScopedWorkspaceApplications(root, real_clock),
                          state_access=state, models=models, assets=_workspace_assets(), lock=lock,
                          legacy_preparations=legacy,
                          owned_preparations=lambda: build_preparations(root / 'conversations.sqlite', host, authoritative=True),
                          preparation_host=host, sequence_journeys=lambda: build_sequence_journeys(root / "conversations.sqlite", real_clock), verified_admissions=verified_admissions)
    return workspace


def model_catalogue():
    from acquisition.adapters.openrouter import inexpensive_models
    return inexpensive_models()


def build_cli_application(path, *, model=None, max_calls=10, tool_choice=None, env_file=None, verified_admissions=False):
    store = build_admissions(path, verified_admissions=verified_admissions)
    gateway = workspace_gateway(workspace_key(env_file)) if model and not inspection_only(path) and not store.required() else None
    force_tools = tool_choice == 'required' if tool_choice else model == 'openai/gpt-oss-120b'
    config = ModelConfig(model, max_calls=max_calls, force_tool_choice=force_tools) if model else None
    return build(path, gateway=gateway, model_config=config)


def build_workspace_http(port, workspace, assets):
    """Select the inbound adapter after startup has acquired the root lock."""
    from acquisition.adapters.http.workspace_server import WorkspaceHTTPServer
    return WorkspaceHTTPServer(port, workspace, assets)


def build_recovery_error_boundary():
    """Normalize storage failures without importing SQLite in command startup."""
    from acquisition.adapters.sqlite.errors import recovery_storage_errors
    return recovery_storage_errors()


def build_hosted_preparations(path, organization, clock=time.time, *, remote_storage=None, _database=None, _gateway=None):
    """Open an already migrated store. Per-request composition never initializes or repairs it."""
    from acquisition.conversations import HostedPreparations
    database=_database or build_database(path,clock=clock,remote_storage=remote_storage,read_only=True)
    from acquisition.adapters.turso import TursoDatabase
    if isinstance(database,TursoDatabase):database.memoize_transactions=True
    journeys=build_sequence_journeys(path,clock,remote_storage=remote_storage,_database=database,_gateway=_gateway,_preparation_clock=True)
    return HostedPreparations(organization,SqliteConversations(database),journeys,clock)


def build_serverless_preparation_handler():
    """Server-owned operator identity and credentials. No local store or worker fallback."""
    import os
    from acquisition.adapters.http.serverless_preparation import preparation_handler
    token=os.environ.get('PREPARATION_OPERATOR_TOKEN','')
    hosts=os.environ.get('PREPARATION_ALLOWED_HOSTS','').split(',')
    if os.environ.get('VERCEL_URL'):hosts.append(os.environ['VERCEL_URL'])
    origins=os.environ.get('PREPARATION_ALLOWED_ORIGINS','').split(',')
    def factory():
        remote={'url':os.environ['TURSO_DATABASE_URL'],'token':os.environ['TURSO_AUTH_TOKEN'],
                'deadline':time.monotonic()+120}
        return build_hosted_preparations(None,os.environ['PREPARATION_ORGANIZATION'],remote_storage=remote)
    return preparation_handler(factory,token,[h.strip() for h in hosts if h.strip()],[o.strip() for o in origins if o.strip()])
