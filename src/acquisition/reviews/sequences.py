"""Exact sequence review and truthful projections. Reports never grant authority."""

from acquisition.contracts import Conflict, digest
from acquisition.campaigns import validate_sequence_window
from .domain import timestamp


SEQUENCE_PURPOSE = 'simulated_multichannel_sequence/v1'
SEQUENCE_CHECKS = frozenset({'artifact_identity', 'audience_permissions', 'recipient_payloads',
                             'sequence_contract', 'current_epochs'})


def readiness_window(subject, boundaries, now):
    """A conservative interval for the complete checked basis, never execution authority."""
    timestamp(now)
    boundaries = tuple(boundaries)
    for point in boundaries: timestamp(point)
    future = [point for point in boundaries if point>now]
    if not future: raise Conflict('The complete readiness basis has no known validity interval')
    return {'subject_id':subject['id'],'from':now,'until':min(future)}


def sequence_subject(organization, proposal_id, proposal, basis):
    if proposal_id != 'sequence_proposal_' + digest(proposal) or proposal['organization'] != organization:
        raise Conflict('Review must bind the exact scoped sequence')
    payload = {'schema':'sequence-review-subject/v1', 'organization':organization,
        'purpose':SEQUENCE_PURPOSE, 'proposal_id':proposal_id, 'sequence':proposal, 'basis':basis}
    return payload | {'id':'sequence_subject_' + digest(payload)}


def sequence_validation(subject, checks, now):
    timestamp(now)
    if len({c['id'] for c in checks}) != len(checks):
        raise ValueError('Duplicate sequence validation check')
    indexed = {c['id']:c for c in checks}
    for name in SEQUENCE_CHECKS - indexed.keys():
        indexed[name] = {'id':name, 'status':'not_evaluated', 'required':True}
    for name, check in indexed.items():
        if (check['status'] not in {'passed','failed','unknown','not_evaluated'}
                or type(check['required']) is not bool or check['required'] != (name in SEQUENCE_CHECKS)):
            raise ValueError('Validation requirements cannot be downgraded')
    if indexed['current_epochs']['status']=='passed':
        window = indexed['current_epochs'].get('validity')
        try:
            if (type(window) is not dict or set(window)!={'subject_id','from','until'}
                    or window['subject_id']!=subject['id']): raise ValueError('Unbound readiness interval')
            timestamp(window['from']); timestamp(window['until'])
            if window['from']>=window['until']: raise ValueError('Empty readiness interval')
        except (ValueError,KeyError,TypeError):
            indexed['current_epochs'] = {k:v for k,v in indexed['current_epochs'].items() if k!='validity'} | {'status':'unknown',
                'detail':'Complete readiness time basis is unavailable or invalid.'}
        else:
            if not window['from']<=now<window['until']:
                indexed['current_epochs'] = indexed['current_epochs'] | {'status':'failed',
                    'detail':'The complete checked readiness basis crossed a time boundary. Revalidate it.'}
    if indexed['sequence_contract']['status']=='passed':
        try:
            validate_sequence_window(subject['sequence'],now)
        except (ValueError,KeyError,TypeError):
            indexed['sequence_contract'] = indexed['sequence_contract'] | {'status':'failed',
                'detail':'Sequence or frozen evidence validity window is invalid or expired at evaluation time.'}
    payload = {'schema':'sequence-validation/v1', 'organization':subject['organization'],
        'subject_id':subject['id'], 'proposal_id':subject['proposal_id'], 'evaluated_at':now,
        'purpose':'review_readiness_only', 'authority':'none',
        'checks':[indexed[name] for name in sorted(indexed)],
        'review_ready':all(indexed[name]['status']=='passed' for name in SEQUENCE_CHECKS)}
    return payload | {'id':'sequence_validation_' + digest(payload)}


def sequence_summary(subject, report):
    """A bounded operator output built solely from the exact validated saved facts."""
    if (report['subject_id'] != subject['id'] or report['proposal_id'] != subject['proposal_id']
            or not report['review_ready'] or not sequence_validation(subject,report['checks'],report['evaluated_at']) == report):
        raise Conflict('Substantive sequence output requires complete current validation')
    proposal = subject['sequence']
    return {'schema':'sequence-operator-summary/v1', 'organization':subject['organization'],
        'subject_id':subject['id'], 'proposal_id':subject['proposal_id'], 'mode':'SYNTHETIC_ONLY',
        'purpose':SEQUENCE_PURPOSE, 'counts':proposal['counts'], 'limits':proposal['limits'],
        'schedule':{'starts_at':proposal['request']['starts_at'], 'expires_at':proposal['request']['expires_at']},
        'stop_scope':proposal['request']['stop_scope'], 'authority':'none',
        'review_status':'ready_for_accountable_review', 'execution':'not_authorized_by_this_summary'}


def validate_sequence_output(subject, report, output):
    if output != sequence_summary(subject,report):
        raise Conflict('Operator output differs from exact validated sequence facts')
    return output
