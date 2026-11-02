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

from .domain import identity, text


ADMISSION_SCHEMA = 'execution-admission/v1'
MAX_TASK_PLAN_BYTES = 1_048_576


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
