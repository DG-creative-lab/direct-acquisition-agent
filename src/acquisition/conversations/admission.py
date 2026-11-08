"""Versioned admission proposals. Values and receipts are never execution grants.

Persistence must verify the source, consent, parent and current policy before
committing a proposal with its tasks. This contract does not perform that I/O.
"""

import json
import math
from dataclasses import asdict, dataclass

from acquisition.contracts import Conflict, canonical, digest
from acquisition.reasoning import ModelConfig
from acquisition.runtime import TaskSpec

from .domain import identity, text, CAPABILITY, FIXTURE_CAPABILITY
from .scope import requested_scope
from .budgets import BUDGET_POLICY, SUPPORTED_BUDGET_POLICIES


ADMISSION_SCHEMA = 'execution-admission/v1'
PLANNING_ADMISSION = 'conversation-planning/v1'
FIXTURE_PLANNING_ADMISSION = 'conversation-fixture-planning/v1'
MAX_TASK_PLAN_BYTES = 1_048_576


CAMPAIGN_ADMISSION_KINDS = frozenset({'conversation-campaign', 'standalone-campaign', 'manual-descendant', 'learning-followup'})
WORKFLOW_ADMISSION_KINDS = frozenset({'routing', 'conversation-campaign', 'standalone-campaign',
                           'manual-descendant', 'learning-followup', 'copy-revision'})


def workflow_permission(kind, allow_model, config):
    if kind not in WORKFLOW_ADMISSION_KINDS or type(allow_model) is not bool:
        raise ValueError('Choose a supported admission and explicit generation permission')
    if allow_model != (config is not None):
        raise ValueError('Model settings require explicit permission; fixtures cannot authorize model calls')
    if config is not None:
        if type(config) is not ModelConfig or not config.force_tool_choice:
            raise ValueError('Use validated model settings with forced typed tools')
        limit = 1 if kind == 'routing' else 5 if kind == 'copy-revision' else 12
        if config.max_calls > limit:
            raise ValueError('Model-call limit exceeds this workflow contract')
    if kind in {'routing', 'copy-revision'} and not allow_model:
        raise ValueError('This workflow requires its own explicit model permission')


def fingerprint(value):
    if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Use an exact SHA-256 fingerprint')
    return value


@dataclass(frozen=True)
class ExecutionOwnership:
    kind: str
    organization: str
    scope_id: str
    revision: int | None = None

    def __post_init__(self):
        identity(self.organization), identity(self.scope_id)
        if type(self.kind) is not str or self.kind not in {'conversation','standalone'}:
            raise ValueError('Declare conversation or standalone execution ownership')
        if self.kind=='conversation':
            if type(self.revision) is not int or self.revision<1:
                raise ValueError('Conversation ownership requires its original positive revision')
        elif self.revision is not None:
            raise ValueError('Standalone ownership cannot claim a conversation revision')

    @property
    def account_key(self):
        # A later brief revision must never create another allowance.
        return self.kind,self.organization,self.scope_id


@dataclass(frozen=True)
class AdmissionIntent:
    organization: str
    request_id: str
    workflow_version: str
    ownership: ExecutionOwnership
    source_id: str
    source_fingerprint: str
    context_fingerprint: str
    task_plan_json: str
    parent_run_id: str | None = None
    consent_id: str | None = None
    model_config: ModelConfig | None = None

    def __post_init__(self):
        for value in (self.organization,self.request_id,self.source_id):identity(value)
        text(self.workflow_version,160)
        if type(self.ownership) is not ExecutionOwnership:
            raise ValueError('An admission must declare explicit execution ownership')
        fingerprint(self.source_fingerprint), fingerprint(self.context_fingerprint)
        if self.parent_run_id is not None:identity(self.parent_run_id)
        if (self.consent_id is None)!=(self.model_config is None):
            raise ValueError('Model settings and exact generation-consent reference must be supplied together')
        if self.model_config is not None:
            identity(self.consent_id)
            if type(self.model_config) is not ModelConfig:
                raise ValueError('Freeze validated model settings, not provider credentials')
        if type(self.task_plan_json) is not str or len(self.task_plan_json.encode())>MAX_TASK_PLAN_BYTES:
            raise ValueError('The frozen task plan must fit the admission envelope')
        try:
            plan=json.loads(self.task_plan_json)
            if type(plan) is not list or not 1<=len(plan)<=20:
                raise ValueError('An admission requires 1 to 20 runtime tasks')
            for task in plan:
                if type(task) is not dict or set(task)!={'capability','inputs','max_attempts'} or type(task['inputs']) is not dict:
                    raise ValueError('Use exact runtime task fields and object inputs')
                text(task['capability'],160)
                TaskSpec(**task)
            if canonical(plan)!=self.task_plan_json:
                raise ValueError('Use the canonical frozen task plan')
        except (TypeError,KeyError) as error:
            raise ValueError('Invalid frozen runtime task plan') from error

    @classmethod
    def from_tasks(cls, *, tasks, **values):
        if type(tasks) not in {tuple,list} or any(type(task) is not TaskSpec for task in tasks):
            raise ValueError('Freeze an explicit list of runtime TaskSpec values')
        return cls(task_plan_json=canonical([asdict(task) for task in tasks]),**values)

    @property
    def tasks(self):
        # Decode fresh copies. TaskSpec.inputs is otherwise a mutable dictionary.
        return tuple(TaskSpec(**task) for task in json.loads(self.task_plan_json))

    @property
    def id(self):
        return 'admission_'+digest({'organization':self.organization,'request_id':self.request_id})

    def payload(self):
        value=asdict(self)
        value.pop('task_plan_json')
        value['schema']=ADMISSION_SCHEMA
        value['tasks']=json.loads(self.task_plan_json)
        return value

    @property
    def fingerprint(self):
        return digest(self.payload())

    @classmethod
    def from_payload(cls, value):
        fields={'schema','organization','request_id','workflow_version','ownership','source_id','source_fingerprint',
                'context_fingerprint','tasks','parent_run_id','consent_id','model_config'}
        if type(value) is not dict or set(value)!=fields or value['schema']!=ADMISSION_SCHEMA:
            raise ValueError('Use the exact supported admission schema')
        data=dict(value)
        data.pop('schema')
        tasks=data.pop('tasks')
        try:
            data['ownership']=ExecutionOwnership(**data['ownership'])
            if data['model_config'] is not None:data['model_config']=ModelConfig(**data['model_config'])
            return cls(task_plan_json=canonical(tasks),**data)
        except TypeError as error:
            raise ValueError('Invalid admission contract values') from error

    def validate_parent(self, *, organization, run_id, ownership):
        """Compare facts loaded by the store, under its admission transaction."""
        if self.parent_run_id is None or run_id!=self.parent_run_id:
            raise Conflict('Load the exact declared parent before admitting a descendant')
        if organization!=self.organization or ownership!=self.ownership:
            raise Conflict('A descendant must preserve parent organization, account and source revision')


@dataclass(frozen=True)
class AdmissionReceipt:
    organization: str
    admission_id: str
    run_id: str
    fingerprint: str
    created_at: float

    def __post_init__(self):
        for value in (self.organization,self.admission_id,self.run_id):identity(value)
        fingerprint(self.fingerprint)
        try:
            finite=type(self.created_at) in {int,float} and math.isfinite(self.created_at)
        except OverflowError:
            finite=False
        if not finite:
            raise ValueError('Admission timestamps must be finite numbers')


def planning_permission(fixture, allow_model, config):
    if type(fixture) is not bool or type(allow_model) is not bool:
        raise ValueError('Use explicit planning generation decisions')
    if fixture:
        if allow_model or config is not None:raise ValueError('Fixture planning cannot grant model consent')
    elif not allow_model or type(config) is not ModelConfig or config.max_calls>2 or not config.force_tool_choice:
        raise ValueError('Explicitly allow bounded planner settings before saving model intent')


def planning_capacity(revision, prior, staged, own_request=None, *, admission_request_id=None):
    """Facts must be loaded by the persistence port under its admission lock."""
    if own_request is not None and any(r['request_id']==own_request for r in prior):
        raise Conflict('A legacy planning admission already owns this request key')
    outer=admission_request_id if admission_request_id is not None else own_request
    if own_request is not None and any(r.get('native_request_id',r['request_id'])==own_request and r['request_id']!=outer for r in staged):
        raise Conflict('This native planning request already has a staged admission')
    if (any(r['revision']==revision and r['request_id']!=own_request for r in prior) or
            any(r['revision']==revision and r['request_id']!=outer for r in staged)):
        raise Conflict('This revision already has a planning request')
    if any(r['revision']==revision for r in prior):
        raise Conflict('This revision already has a legacy planning admission')
    revisions={r['revision'] for r in list(prior)+list(staged)}
    if revision not in revisions and len(revisions)>=6:raise ValueError('Conversation planning budget exhausted')


def planning_intent(organization, request_id, source, context, history, *, fixture, allow_model, config, native_request_id=None):
    """Build from independently loaded source facts, never model-owned identity."""
    planning_permission(fixture,allow_model,config)
    if source['organization']!=organization:raise Conflict('Planning source belongs to another organization')
    allowed={'knowledge','knowledge_id','model_config','previous_results','fixture','messages','confirmed_action_exchanges','requested_scope','budget_policy'}
    if type(context) is not dict or set(context)-allowed:raise ValueError('Unsupported planning context fields')
    if context.get('model_config')!=(asdict(config) if config else None):
        raise Conflict('Planning context and permitted model settings differ')
    if context.get('previous_results')!=([] if fixture else history):
        raise Conflict('Planning history differs from authoritative results')
    if 'messages' in context and context['messages']!=source['messages']:
        raise Conflict('Planning messages differ from the current source')
    if context.get('confirmed_action_exchanges',[])!=source['confirmed_action_exchanges']:
        raise Conflict('Planning clarification exchanges differ from the current source')
    if ((fixture and context.get('fixture')!='offline-example/v1') or (not fixture and 'fixture' in context)):
        raise Conflict('Planning mode differs from its frozen context')
    conversation_id=source['conversation_id'];revision=source['revision']
    native_request=request_id if native_request_id is None else native_request_id
    identity(native_request)
    admission_id='admission_'+digest({'organization':organization,'request_id':request_id})
    frozen=context|{'conversation_id':conversation_id,'revision':revision,'request_id':native_request,
        'messages':source['messages'],'run_request_id':'conversation-plan:'+digest({'conversation':conversation_id,'request':native_request}),
        'execution_admission_id':admission_id}
    scope = requested_scope(organization, conversation_id, revision, source['messages'])
    if 'requested_scope' in context and context['requested_scope'] != scope:
        raise Conflict('Requested scope changed before planning admission')
    if context.get('budget_policy', BUDGET_POLICY) not in SUPPORTED_BUDGET_POLICIES:
        raise Conflict('Budget policy differs from the installed planning contract')
    frozen['budget_policy'] = BUDGET_POLICY
    frozen['requested_scope'] = scope
    if source['confirmed_action_exchanges']:frozen['confirmed_action_exchanges']=source['confirmed_action_exchanges']
    context_hash=digest(frozen)
    consent_id=None if fixture else 'consent_'+digest({'organization':organization,'request':request_id,'context':context_hash})
    return AdmissionIntent.from_tasks(organization=organization,request_id=request_id,
        workflow_version=FIXTURE_PLANNING_ADMISSION if fixture else PLANNING_ADMISSION,
        ownership=ExecutionOwnership('conversation',organization,conversation_id,revision),
        source_id=conversation_id,source_fingerprint=digest(source),context_fingerprint=context_hash,
        tasks=[TaskSpec(FIXTURE_CAPABILITY if fixture else CAPABILITY,frozen)],consent_id=consent_id,model_config=config)


def planning_binding(intent, expected, source):
    if intent!=expected:raise Conflict('Admission differs from its verified request or generation consent')
    if intent.workflow_version not in {PLANNING_ADMISSION,FIXTURE_PLANNING_ADMISSION}:
        raise ValueError('This admission adapter supports planning only')
    owner=intent.ownership
    if (owner.kind!='conversation' or owner.organization!=intent.organization or
        owner.scope_id!=intent.source_id or intent.parent_run_id is not None):
        raise Conflict('Planning requires its own scoped conversation source, without a parent run')
    if digest(source)!=intent.source_fingerprint:raise Conflict('Admission source changed after consent')
    fixture=intent.workflow_version==FIXTURE_PLANNING_ADMISSION
    specs=intent.tasks
    if (len(specs)!=1 or specs[0].capability!=(FIXTURE_CAPABILITY if fixture else CAPABILITY) or
        digest(specs[0].inputs)!=intent.context_fingerprint or (intent.model_config is None)!=fixture):
        raise Conflict('Registered planning task, context or model requirements differ')
    return fixture
