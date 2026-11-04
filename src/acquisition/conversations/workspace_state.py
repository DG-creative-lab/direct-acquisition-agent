"""Application-owned sandbox intent, routing and time. These are not approvals."""
import json
import math
from dataclasses import dataclass
from acquisition.contracts import Conflict, canonical, digest
from .domain import identity
from .ports import WorkspaceStateStore

WORKSPACE_OWNER='local-workspace'
ENVIRONMENT_SCHEMA='campaign-environment/v1'


def environment_time(value):
    try:valid=type(value) in {int,float} and math.isfinite(value) and 0<=value<253402300800
    except OverflowError:valid=False
    if not valid:raise ValueError('Use a finite supported UTC sandbox timestamp')
    return value


@dataclass(frozen=True)
class EnvironmentIntent:
    organization: str
    session_json: str

    def __post_init__(self):
        identity(self.organization)
        if type(self.session_json) is not str or len(self.session_json.encode())>1_048_576:
            raise ValueError('Sandbox intent exceeds its envelope')
        session=json.loads(self.session_json)
        required={'id','name','mode','organization','database_scope','clock','clock_mode','created_at','parent_id','run_id','case_id','cohort_id'}
        if type(session) is not dict or required-set(session) or set(session)-required-{'conversation_plan','audience_selection','followup_id'}:
            raise ValueError('Use the exact supported sandbox intent fields')
        for key in ('id','organization'):identity(session[key])
        if self.organization!=session['organization'] or type(session['name']) is not str or not 1<=len(session['name'])<=160:
            raise ValueError('Sandbox scope and name are required')
        if session['mode'] not in {'fixture','model'} or session['database_scope'] not in {'conversations','campaign'}:
            raise ValueError('Unsupported sandbox mode or storage scope')
        if session['clock_mode'] not in {'REAL','SIMULATED'} or (session['mode']=='fixture' and session['clock_mode']!='SIMULATED'):
            raise ValueError('Choose an explicit compatible clock mode')
        environment_time(session['clock']);environment_time(session['created_at'])
        if session['parent_id'] is not None:identity(session['parent_id'])
        if any(session[k] is not None for k in ('run_id','case_id','cohort_id')):
            raise ValueError('Bind actual domain results after creating sandbox intent')
        if canonical(session)!=self.session_json:raise ValueError('Use canonical sandbox intent')

    @classmethod
    def freeze(cls,session):return cls(session['organization'],canonical(session))

    @property
    def session(self):return json.loads(self.session_json)

    @property
    def fingerprint(self):return digest({'schema':ENVIRONMENT_SCHEMA,'organization':self.organization,'session':self.session})


def preparation_record(organization,request_id,value):
    if type(value) is not dict or set(value)!={'id','inputs','planning_context','planning_context_id','plan_request_id','run_id','status','detail'}:
        raise ValueError('Use the exact preparation intent fields')
    identity(organization);identity(request_id);identity(value['id'])
    identity(value['plan_request_id'])
    inputs=value['inputs'];revision=inputs['revision']
    identity(inputs['conversation_id'])
    if type(revision) is not int or revision<1 or type(inputs['fixture']) is not bool or type(inputs['allow_model_copy']) is not bool:
        raise ValueError('A preparation requires exact revision and generation choices')
    if inputs['fixture'] and inputs['allow_model_copy']:raise ValueError('Fixture preparation cannot allow model copy')
    if set(inputs)-{'conversation_id','revision','fixture','allow_model_copy','use_audience_catalogue'}:
        raise ValueError('Unexpected preparation inputs')
    if 'use_audience_catalogue' in inputs and inputs['use_audience_catalogue'] is not True:
        raise ValueError('Use an explicit audience source choice')
    if value['status']!='admitting' or value['run_id'] is not None or value['detail'] is not None:
        raise ValueError('A new preparation must begin as unadmitted intent')
    if digest(value['planning_context'])!=value['planning_context_id']:
        raise Conflict('Frozen preparation context failed integrity checks')
    if len(canonical(value).encode())>1_048_576:raise ValueError('Preparation intent exceeds its envelope')
    return json.loads(canonical(value|{'request_id':request_id,'epoch':0}))


class WorkspaceState:
    def __init__(self,store:WorkspaceStateStore):self.store=store
    def get(self,key):
        identity(key)
        return self.store.get(key)
    def listing(self):return self.store.listing()
    def request(self,kind,scope,request_id,*,parent_id=None):
        identity(scope);identity(request_id)
        if parent_id is not None:identity(parent_id)
        return self.store.request(kind,scope,request_id,parent_id=parent_id)
    def create(self,session,kind,scope,request_id,inputs):
        identity(scope);identity(request_id)
        if len(canonical(inputs).encode())>65536:raise ValueError('Sandbox creation command exceeds its envelope')
        return self.store.create(EnvironmentIntent.freeze(session),kind,scope,request_id,json.loads(canonical(inputs)))
    def save(self,session):return self.store.save_links(session['id'],session)
    def clock(self,identity,real_time):return self.store.clock(identity,environment_time(real_time))
    def begin(self,key,action,payload):
        identity(key)
        if action not in {'approve','reject','refresh','revoke','suppress','handoff','open-learning','observe','finalize'}:
            raise ValueError('Unsupported sandbox command')
        identity(payload['request_id'])
        if len(canonical(payload).encode())>65536:raise ValueError('Sandbox command exceeds its envelope')
        return self.store.begin_command(key,action,json.loads(canonical(payload)))
    def complete(self,identity,request_id):return self.store.complete_command(identity,request_id)
