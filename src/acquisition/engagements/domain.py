"""Synthetic enrollment, dispatch and observation contracts. No outbound authority."""

from dataclasses import asdict, dataclass

from acquisition.contracts import Conflict, digest
from acquisition.campaigns import SequenceConnection, sequence_text, sequence_time


@dataclass(frozen=True)
class DispatchClaim:
    organization: str
    simulation_id: str
    step_id: str
    token: str
    lease_until: float
    intent: dict


@dataclass(frozen=True)
class SimulationReceipt:
    effect_key: str
    request_hash: str
    connection_id: str
    status: str
    provider_effect_id: str | None
    confirmed_cost_pence: int | None
    mode: str = 'SYNTHETIC_ONLY'

    def __post_init__(self):
        for value in (self.effect_key,self.request_hash,self.connection_id): sequence_text(value)
        if self.provider_effect_id is not None: sequence_text(self.provider_effect_id)
        if self.mode!='SYNTHETIC_ONLY' or self.status not in {'accepted','rejected','partial','unknown'}: raise ValueError('Use an explicit synthetic submission result')
        if self.confirmed_cost_pence is not None and (type(self.confirmed_cost_pence) is not int or self.confirmed_cost_pence<0):
            raise ValueError('Use integer observed cost or explicit uncertainty')


def validate_simulation_receipt(intent, receipt):
    if (type(receipt) is not SimulationReceipt or receipt.effect_key!=intent['effect_key']
            or receipt.request_hash!=digest(intent) or receipt.connection_id!=intent['step']['connection_id']):
        raise Conflict('Submission observation differs from exact reserved intent')
    if receipt.status=='accepted':
        if receipt.provider_effect_id is None or receipt.confirmed_cost_pence!=intent['step']['unit_cost_pence']:
            raise Conflict('Acceptance requires exact effect identity and cost')
    elif receipt.status=='rejected':
        if receipt.provider_effect_id is not None or receipt.confirmed_cost_pence!=0: raise Conflict('Rejection cannot claim an effect or charge')
    elif receipt.confirmed_cost_pence is not None: raise Conflict('Partial and unknown submissions retain uncertain cost')


def make_intent(organization, simulation_id, proposal_id, member, step):
    payload={'schema':'simulation-intent/v1','mode':'SYNTHETIC_ONLY','organization':organization,
        'simulation_id':simulation_id,'proposal_id':proposal_id,'contact_id':member['contact_id'],
        'experiment_unit':member['experiment_unit'],'arm':member['arm'],'step':step}
    return payload|{'effect_key':'simulated_effect_'+digest(payload)}


OBSERVATIONS={'email':{'delivered','bounced','replied','objected'},'human_call':{'task_completed','replied','objected'}}


TRANSITIONS={
    'pending':frozenset({'dispatching','paused','stopped','blocked'}),
    'dispatching':frozenset({'accepted','rejected','partial','unknown','paused','stopped','blocked'}),
    'paused':frozenset({'stopped'}),
}


def validate_step_transition(before, after):
    if after not in TRANSITIONS.get(before,()): raise Conflict('Illegal engagement step transition')


def applicable_stop(stops, simulation_id, contact_id, account_id):
    actions=[]
    for stop in stops:
        if stop['simulation_id'] is not None and stop['simulation_id']!=simulation_id:continue
        if stop['scope'] not in {'simulation','contact','account'} or stop['action'] not in {'pause','stop'}:
            raise Conflict('Unsupported engagement stop policy')
        subject={'simulation':simulation_id,'contact':contact_id,'account':account_id}[stop['scope']]
        if stop['subject_id']==subject:actions.append(stop['action'])
    return 'stopped' if 'stop' in actions else 'paused' if 'pause' in actions else None


def step_wait_reason(step, previous, completed_task, now):
    sequence_time(now)
    if step['ordinal']:
        if previous is None:raise Conflict('Incomplete frozen treatment history')
        if previous['status'] not in {'accepted','rejected'}:return 'prior_step_'+previous['status']
        if previous['channel']=='human_call' and previous['status']=='accepted' and not completed_task:
            return 'human_task_completion'
    return 'schedule' if step['due_at']>now else 'due'


def validate_observation(intent, receipt, kind, occurred_at, now):
    sequence_time(occurred_at); sequence_time(now)
    validate_simulation_receipt(intent,receipt)
    if (receipt.status!='accepted' or kind not in OBSERVATIONS[intent['step']['channel']]
            or not intent['step']['due_at']<=occurred_at<=now): raise Conflict('Observation must bind a previously accepted exact effect')


def simulation_totals(proposal, rows, observations):
    by_id={row['id']:row for row in rows}
    for observation in observations:
        row=by_id.get(observation['step_id'])
        if row is None or not row['submission'] or observation['provider_effect_id']!=row['submission']['provider_effect_id']:
            raise Conflict('Observation differs from its frozen accepted treatment step')
        validate_observation(row['intent'],SimulationReceipt(**row['submission']),observation['kind'],
                             observation['occurred_at'],observation['occurred_at'])
    states={state:sum(row['status']==state for row in rows) for state in
        ('pending','dispatching','accepted','rejected','partial','unknown','paused','stopped','blocked')}
    for row in rows:
        if row['submission']: validate_simulation_receipt(row['intent'],SimulationReceipt(**row['submission']))
    confirmed=sum(row['submission']['confirmed_cost_pence'] or 0 for row in rows if row['submission'])
    unresolved=sum(row['unit_cost_pence'] for row in rows if
        (row['submission'] and row['submission']['status'] in {'partial','unknown'}) or
        (row['status'] in {'dispatching','partial','unknown'} and not row['submission']))
    if len(rows)!=proposal['counts']['steps'] or confirmed+unresolved>proposal['limits']['maximum_cost_pence']:
        raise Conflict('Simulation accounting differs from frozen assignments')
    return {'states':states,'confirmed_cost_pence':confirmed,'unresolved_maximum_cost_pence':unresolved,
        'maximum_cost_pence':proposal['limits']['maximum_cost_pence'],
        'accepted':sum(bool(r['submission']) and r['submission']['status']=='accepted' for r in rows),
        'delivered':sum(o['kind']=='delivered' for o in observations),
        'responded':len({by_id[o['step_id']]['intent']['experiment_unit'] for o in observations if o['kind']=='replied'}),
        'response_observations':sum(o['kind']=='replied' for o in observations),
        'completed_call_tasks':sum(o['kind']=='task_completed' for o in observations),
        'accepted_call_tasks':sum(bool(r['submission']) and r['submission']['status']=='accepted' and r['channel']=='human_call' for r in rows),
        'reserved_call_capacity':proposal['counts']['call_tasks'],'reserved_step_capacity':len(rows)}
