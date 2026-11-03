"""Compose existing workflow contracts from verified, scoped source records.

No persistence, provider access or approval authority lives in this composition.
The storage adapter reloads the source under its admission transaction.
"""
from dataclasses import asdict, replace
from datetime import datetime, timezone

from acquisition.contracts import Conflict, digest
from acquisition.conversations import CAMPAIGN_ADMISSION_KINDS, AdmissionIntent, ExecutionOwnership, ACTION_CAPABILITY, COPY_ACTION_CAPABILITY, validate_result, workflow_permission
from acquisition.campaigns import Brief, ConversationBrief, SourcedConversationBrief, brief_from
from acquisition.creative import fixture_catalog, GroundedCopyAgent, validate_copy_assets, validate_fact_pack
from acquisition.reasoning import Inference
from acquisition.runtime import TaskSpec
from .monthly_mail import task_plan, conversation_task_plan
from .model_mail import model_task_plan, conversation_model_task_plan
from .conversational_actions import ConversationRouter


def campaign_brief(kind, references, source):
    """Derive conversation and learning briefs from saved results, not user attestations."""
    if kind == 'conversation-campaign':
        frozen, result = source['planning_inputs'], source['plan']
        candidate = {key: result[key] for key in ('outcome', 'objective', 'budget_pence', 'segments',
                    'copy_mode', 'question', 'assumptions', 'unsupported_reason')}
        if validate_result(candidate, frozen, source['owner']['organization']) != result or result['outcome'] != 'brief_proposal':
            raise Conflict('Campaign requires its exact successful saved brief proposal')
        campaign_id = 'workspace_' + digest({'conversation_id': result['conversation_id'], 'plan_id': result['id']})[:24]
        selection = source['selection']
        cls = SourcedConversationBrief if selection else ConversationBrief
        return cls(campaign_id=campaign_id, budget_pence=result['budget_pence'], segments=tuple(result['segments']),
            conversation_id=result['conversation_id'], conversation_revision=result['revision'], plan_id=result['id'],
            **({'audience_source': selection} if selection else {}))
    if kind == 'learning-followup':
        p = source['proposal']
        return brief_from(p['brief'] | {'campaign_id': 'workspace_' + digest({'followup': p['id']})[:24], 'followup_id': p['id']})
    # Only these explicit server-side commands may specify a new root/child brief.
    brief = brief_from(references['brief'])
    if type(brief) is not Brief:
        raise ValueError('Use the saved conversation or learning source for derived briefs')
    return brief


def coverage_plan(kind, references, source, config, organization, now):
    """Build and preflight the complete frozen plan without reserving a call."""
    inference = Inference(None, None, config, lambda: now) if config else None
    if kind == 'routing':
        frozen = source['action']
        if frozen.get('alias') or frozen['model_config'] != asdict(config):
            raise Conflict('Routing requires its original model admission; aliases need no task')
        if frozen.get('capability',ACTION_CAPABILITY) not in {ACTION_CAPABILITY,COPY_ACTION_CAPABILITY}:
            raise Conflict('Routing source has an unsupported capability')
        ConversationRouter(inference).preflight(frozen)
        return [TaskSpec(frozen.get('capability', ACTION_CAPABILITY), frozen)], frozen['run_request_id'], frozen['id']
    if kind == 'copy-revision':
        receipt = source['revision']
        if receipt['task_inputs']['model_config'] != asdict(config) or receipt['inputs']['allow_model_copy'] is not True:
            raise Conflict('Copy revision requires its exact original generation permission and settings')
        context = receipt['context']
        _copy_preflight(context, organization, inference, now)
        inputs = receipt['task_inputs'] | {'context_id': source['context_id']}
        return [TaskSpec('creative.revise_copy.v3', inputs), TaskSpec('reviews.publish_copy_revision.v3', inputs)], receipt['id'], receipt['id']
    brief = campaign_brief(kind, references, source)
    if kind == 'conversation-campaign' and source['plan']['copy_mode'] != ('model' if config else 'fixture'):
        raise Conflict('Campaign copy mode differs from the saved proposal')
    contexts = source['contexts']
    if config:
        if kind == 'learning-followup' and asdict(config) != source['proposal']['model_config']:
            raise Conflict('Follow-up requires the proposal\'s exact frozen model settings')
        segments = set(getattr(brief, 'segments', ('inventory', 'contractors')))
        if set(contexts) != segments:
            raise ValueError('Frozen contexts must cover exactly the requested segments')
        for segment, context in contexts.items():
            summary = context['audience_summary']
            if (context['segment'] != segment or summary['snapshot_id'] != source['snapshot_id'] or
                    summary['model_version'] != source['audience_facts']['model_version'] or
                    summary['input_records'] != source['audience_facts']['segment_counts'][segment]):
                raise Conflict('Copy context differs from its segment or audience snapshot')
            if kind == 'conversation-campaign' and context.get('campaign_brief') != {
                'objective': source['plan']['objective'], 'budget_pence': brief.budget_pence,
                'segments': list(brief.segments), 'plan_id': brief.plan_id}:
                raise Conflict('Copy context differs from the saved campaign objective')
            if kind == 'conversation-campaign' and source['selection']:
                selection = source['selection']
                if summary.get('dataset_source') != {
                    'selection_id':selection['id'], 'manifest_id':selection['manifest_id'],
                    'dataset_id':selection['source']['dataset_id'], 'version':selection['source']['version'],
                    'checksum':selection['source']['checksum'], 'source_snapshot_id':selection['source_snapshot_id']}:
                    raise Conflict('Copy context differs from the confirmed dataset version')
            _copy_preflight(context, organization, inference, now)
        factory = conversation_model_task_plan if kind == 'conversation-campaign' else model_task_plan
        tasks = factory(source['snapshot_id'], brief, source['context_ids'], inference)
    else:
        if contexts and kind != 'learning-followup':
            raise ValueError('Fixture requests cannot include model contexts')
        # The catalogue identity uses the same serialized public records as build().
        from acquisition.creative import creative_record
        catalogue_hash = digest([creative_record(c) for c in fixture_catalog()])
        factory = conversation_task_plan if kind == 'conversation-campaign' else task_plan
        tasks = factory(source['snapshot_id'], brief, catalogue_hash)
    runtime_key=references.get('runtime_request_id',brief.campaign_id)
    return tasks, runtime_key, brief.campaign_id


def _copy_preflight(context, organization, inference, now):
    validate_copy_assets(context, organization)
    validate_fact_pack(context['product_facts'], datetime.fromtimestamp(now, timezone.utc).date())
    # New admissions use the stable transcript projection. Historical v3 runs
    # retain their original transcript and remain on the legacy entry points.
    if context.get('agent_assets', {}).get('model_projection') != 'copy-context/v1':
        raise ValueError('New copy admissions require the versioned context projection')
    GroundedCopyAgent(inference, None).preflight(context)


def coverage_intent(organization, request_id, kind, references, source, allow_model, config, now):
    workflow_permission(kind, allow_model, config)
    specs, runtime_key, operation_id = coverage_plan(kind, references, source, config, organization, now)
    owner = ExecutionOwnership(**source['owner'])
    marker = 'admission_' + digest({'organization': organization, 'request_id': request_id})
    tasks = [replace(s, inputs=s.inputs | {'execution_admission_id': marker, 'run_request_id': runtime_key}) for s in specs]
    intent = AdmissionIntent.from_tasks(organization=organization, request_id=request_id,
        workflow_version=kind + '-admission/v1', ownership=owner, source_id=operation_id,
        source_fingerprint=digest(source), context_fingerprint=digest(source.get('contexts', source)),
        parent_run_id=source.get('parent_run_id'), consent_id=('consent_' + digest({'request': marker, 'source': source, 'config': asdict(config)})) if config else None,
        model_config=config, tasks=tasks)
    return intent, ('campaign' if kind in CAMPAIGN_ADMISSION_KINDS else kind) + ':' + operation_id
