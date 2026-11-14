"""Immutable synthetic strategy proposals. Campaigns owns population, assignment and limits."""

from dataclasses import asdict, dataclass
import json
import math

from acquisition.contracts import Conflict, canonical, digest


def sequence_text(value):
    if (type(value) is not str or not 1<=len(value)<=200 or value!=value.strip()
            or not value.isprintable() or chr(0x2014) in value): raise ValueError('Use bounded sequence identities')


def sequence_time(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value<0: raise ValueError('Use a finite sequence timestamp')


@dataclass(frozen=True)
class SequenceConnection:
    organization: str
    profile_key: str
    channel: str
    provider: str
    account: str
    destination: str
    reply_to: str
    version: str = 'v1'
    mode: str = 'SYNTHETIC_ONLY'

    def __post_init__(self):
        for value in asdict(self).values(): sequence_text(value)
        if self.channel not in {'email','human_call'} or self.mode!='SYNTHETIC_ONLY': raise ValueError('Only synthetic sequence connections are installed')

    @property
    def id(self): return 'sequence_connection_'+digest(asdict(self))


@dataclass(frozen=True)
class SequenceRequest:
    profile_key: str
    decision_request: str
    initial_content: str
    call_content: str
    followup_content: str
    starts_at: float
    expires_at: float
    budget_pence: int
    call_capacity: int
    step_capacity: int
    email_cost_pence: int = 2
    call_cost_pence: int = 100
    call_delay_seconds: int = 86400
    followup_delay_seconds: int = 259200
    arm_b_call_delay_seconds: int = 172800
    arm_b_followup_delay_seconds: int = 345600
    stop_scope: str = 'account'

    def __post_init__(self):
        for value in (self.profile_key,self.decision_request,self.initial_content,self.call_content,self.followup_content): sequence_text(value)
        sequence_time(self.starts_at); sequence_time(self.expires_at)
        if not self.starts_at<self.expires_at<=self.starts_at+14*86400: raise ValueError('Bound sequence lifetime to fourteen days')
        for value,high in ((self.budget_pence,10**9),(self.call_capacity,6),(self.step_capacity,18),
                           (self.email_cost_pence,10**6),(self.call_cost_pence,10**6)):
            if type(value) is not int or not 0<=value<=high: raise ValueError('Use bounded integer synthetic costs and capacity')
        for call,followup in ((self.call_delay_seconds,self.followup_delay_seconds),
                             (self.arm_b_call_delay_seconds,self.arm_b_followup_delay_seconds)):
            if (type(call) is not int or type(followup) is not int or not 0<call<followup<14*86400
                    or self.starts_at+followup>=self.expires_at): raise ValueError('Declare ordered bounded steps for both arms')
        if self.stop_scope not in {'contact','account'}: raise ValueError('Declare an explicit stop scope')
        if (self.call_delay_seconds,self.followup_delay_seconds)==(self.arm_b_call_delay_seconds,self.arm_b_followup_delay_seconds):
            raise ValueError('The two strategy arms require distinct declared cadences')


def build_sequence_proposal(organization, request_id, request, decision, materials, connections, identities):
    """Inputs are attested by the proposal-store port, not self-certified strategy output."""
    sequence_text(organization); sequence_text(request_id)
    plan=decision['plan']; batch=decision['feature_batch']
    if (decision['organization']!=organization or plan['status']!='complete' or plan['mode']!='SYNTHETIC_ONLY'
            or batch['channel']!='email' or batch['purpose']!='acquisition'
            or len(plan['allocations'])>6): raise Conflict('Use a complete bounded acquisition decision')
    allocations=plan['allocations']
    if len({r['experiment_unit'] for r in allocations})!=len(allocations): raise Conflict('One assignment per experiment unit')
    if set(materials)!={'initial','call','followup'} or set(connections)!={'email','human_call'}:
        raise Conflict('Freeze all three content stages and both connections')
    for channel, connection in connections.items():
        if (type(connection) is not SequenceConnection or connection.organization!=organization
                or connection.profile_key!=request.profile_key or connection.channel!=channel): raise Conflict('Connection scope differs from sequence')
    strategies={'A':{'email':0,'human_call':request.call_delay_seconds,'followup':request.followup_delay_seconds},
                'B':{'email':0,'human_call':request.arm_b_call_delay_seconds,'followup':request.arm_b_followup_delay_seconds}}
    population=[]
    for allocation in allocations:
        if allocation['arm'] not in {'A','B','no_contact'}: raise Conflict('Unknown strategy arm')
        person=allocation['contact_id']; entry={k:allocation[k] for k in ('contact_id','experiment_unit','arm')}
        if person not in identities or identities[person]['experiment_unit']!=entry['experiment_unit']:
            raise Conflict('Assignment differs from attested native account identity')
        entry|=identities[person]
        steps=[]
        if allocation['arm']!='no_contact':
            cadence=strategies[allocation['arm']]
            for index,(stage,channel,delay,cost) in enumerate((('initial','email',0,request.email_cost_pence),
                ('call','human_call',cadence['human_call'],request.call_cost_pence),
                ('followup','email',cadence['followup'],request.email_cost_pence))):
                selected=[row for row in materials[stage] if row['rendered']['contact_id']==person]
                if len(selected)!=1: raise Conflict('Materialize every intended treatment recipient exactly once')
                material=selected[0]; row=material['rendered']; target=material['target']; connection=connections[channel]
                if request.starts_at+delay>=material['valid_until']:
                    raise Conflict('A scheduled step exceeds the known evidence validity window')
                if (row['channel']!=channel or row['mode']!='SYNTHETIC_ONLY' or row['approval']!='not_granted'
                        or target['experiment_unit']!=entry['experiment_unit'] or target['contact_id']!=person
                        or target['account_id']!=entry['account_id'] or target['profile_id']!=batch['profile_id']):
                    raise Conflict('Content differs from exact frozen assignment')
                if channel=='email' and (row['email']['from']!=connection.destination or row['email']['reply_to']!=connection.reply_to):
                    raise Conflict('Email content differs from the selected sender capability')
                steps.append({'ordinal':index,'stage':stage,'channel':channel,'due_at':request.starts_at+delay,
                    'unit_cost_pence':cost,'connection':asdict(connection),'connection_id':connection.id,
                    'assignee':connection.destination if channel=='human_call' else None,
                    'content':material,'stop_scope':request.stop_scope,'expires_at':request.expires_at})
            if len({s['content']['target']['account_id'] for s in steps})!=1: raise Conflict('One treatment history must retain its exact account')
        population.append(entry|{'steps':steps})
    treatment=sum(r['arm']!='no_contact' for r in population); cost=treatment*(2*request.email_cost_pence+request.call_cost_pence)
    if cost>request.budget_pence or treatment>request.call_capacity or 3*treatment>request.step_capacity:
        raise Conflict('Sequence exceeds the declared budget or capacity')
    payload={'schema':'sequence-proposal/v1','mode':'SYNTHETIC_ONLY','organization':organization,'request_id':request_id,
        'request':asdict(request),'profile_id':batch['profile_id'],'objective':batch['objective'],
        'decision_id':'audience_decision_'+digest(decision),'population':population,'strategy_arms':strategies,
        'counts':{'enrolled':len(population),'controls':len(population)-treatment,'treatment':treatment,
                  'email_steps':2*treatment,'call_tasks':treatment,'steps':3*treatment},
        'limits':{'currency':'GBP','cost_basis':'user_supplied_synthetic_estimate','maximum_cost_pence':cost,
            'budget_pence':request.budget_pence,'call_capacity':request.call_capacity,'step_capacity':request.step_capacity},
        'approval':'not_granted','authority':'none','execution':'not_performed'}
    return json.loads(canonical(payload))
