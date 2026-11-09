"""Compare scoped historical evidence without opening a writable store."""
import json
import math
import sqlite3
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from acquisition.contracts import Conflict, NotFound
from acquisition.conversations import EXECUTION_POLICY, identity
from .admission_guard import binding
from .database import stored_plan_hash
from .execution import account_evidence, run_origin
from .workspace_checkpoint import JOURNAL, ROOT, directory, open_checkpoint


MAX_OBSERVATIONS = 100
REVIEW_EFFECTS = {'review_revocation', 'simulated_acceptance'}
CORROBORATED_HISTORY = REVIEW_EFFECTS | {'model_call'}

# The leading columns are the native key, in the same order as SQLite's
# binary sort. Include opaque historical fields in equality, never in reports.
HISTORY = {
    'writing_preference': (2, '''SELECT id,printf('%020d',revision),request_id,fingerprint,payload
        FROM writing_preference_versions WHERE organization=?1 ORDER BY id,revision'''),
    'run': (2, '''SELECT r.organization,r.id,r.request_id,r.request_hash,r.created_at
        FROM runs r LEFT JOIN execution_runs e ON e.organization=r.organization AND e.run_id=r.id
        WHERE r.organization=?1 OR e.owner_organization=?1 ORDER BY r.organization,r.id'''),
    'task': (2, '''SELECT r.organization,t.id,t.run_id,t.position,t.capability,t.inputs,t.max_attempts
        FROM tasks t JOIN runs r ON r.id=t.run_id
        LEFT JOIN execution_runs e ON e.organization=r.organization AND e.run_id=r.id
        WHERE r.organization=?1 OR e.owner_organization=?1 ORDER BY r.organization,t.id'''),
    'execution_link': (2, '''SELECT organization,run_id,owner_organization,conversation_id,revision
        FROM execution_runs WHERE organization=?1 OR owner_organization=?1 ORDER BY organization,run_id'''),
    'execution_account': (1, '''SELECT conversation_id,policy,call_limit,stopped_through
        FROM conversation_execution WHERE organization=?1 ORDER BY conversation_id'''),
    'execution_command': (1, '''SELECT request_id,inputs,receipt FROM execution_commands
        WHERE organization=?1 ORDER BY request_id'''),
    'model_call': (3, '''SELECT c.organization,c.run_id,c.call_key,c.task_id,c.lease_token,c.request_hash,
        c.status,c.response,c.error,e.owner_organization,e.conversation_id,e.revision
        FROM model_calls c LEFT JOIN execution_runs e ON e.organization=c.organization AND e.run_id=c.run_id
        WHERE c.organization=?1 OR e.owner_organization=?1 ORDER BY c.organization,c.run_id,c.call_key'''),
    'review_case': (1, '''SELECT id,run_id FROM review_cases WHERE organization=?1 ORDER BY id'''),
    'review_subject': (1, '''SELECT id,case_id,revision,payload,created_at FROM review_subjects
        WHERE organization=?1 ORDER BY id'''),
    'review_decision': (1, '''SELECT id,case_id,subject_id,payload,sequence FROM review_decisions
        WHERE organization=?1 ORDER BY id'''),
    'review_revocation': (1, '''SELECT approval_id,actor,reason,at FROM review_revocations
        WHERE organization=?1 ORDER BY approval_id'''),
    'simulated_acceptance': (1, '''SELECT case_id,id,approval_id,subject_id,payload FROM simulated_agency_jobs
        WHERE organization=?1 ORDER BY case_id'''),
}


def history_key(value):
    # Compatibility stores also contain opaque legacy keys. Keep their exact
    # spelling while bounding the metadata that can appear in the report.
    if type(value) is not str or not 1 <= len(value) <= 160 or not value.isprintable():
        raise ValueError('Use a bounded, printable organization or record key')
    return value


def keyed_rows(db, query, organization, key_size):
    if 'FROM writing_preference_versions' in query and db.execute(
            "SELECT 1 FROM sqlite_schema WHERE name='writing_preference_versions'").fetchone() is None:
        return
    for row in db.execute(query, (organization,)):
        key = tuple(history_key(value) for value in row[:key_size])
        yield key, tuple(row)


def history_changes(before, later, organization, kind):
    key_size, query = HISTORY[kind]
    old_rows = iter(keyed_rows(before, query, organization, key_size))
    new_rows = iter(keyed_rows(later, query, organization, key_size))
    old = next(old_rows, None)
    for new_key, row in new_rows:
        if old is not None and old[0] < new_key:
            raise Conflict('earlier_record_missing')
        if old is None or new_key < old[0]:
            yield None, row
        else:
            if old[1] != row or kind in CORROBORATED_HISTORY:
                yield old[1], row
            old = next(old_rows, None)
    if old is not None:
        raise Conflict('earlier_record_missing')


def recorded_time(value):
    if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value < 253402300800:
        raise Conflict('invalid_recorded_time')
    return value


def call_origin(db, organization, run_id):
    admission = binding(db, organization, run_id)
    if admission is not None:
        owner = admission.ownership
        return (owner.organization, owner.scope_id, owner.revision) if owner.kind == 'conversation' else None
    # Resolve from frozen legacy task inputs and their native parent records.
    # Check the plan of every visited run, including any inherited parent.
    visited = {}
    origin = run_origin(db, organization, run_id, memo=visited)
    for scope, visited_run in visited:
        original = db.execute('SELECT request_hash FROM runs WHERE organization=? AND id=?',
                              (scope, visited_run)).fetchone()
        if original is None or stored_plan_hash(db, visited_run) != original[0]:
            raise Conflict('model_call_run_plan_mismatch')
    return origin


def model_observation(db, row):
    run_org, run_id, call_key, task_id, _, _, status, response, _, owner, conversation, revision = row
    if not db.execute('''SELECT 1 FROM runs r JOIN tasks t ON t.run_id=r.id
            WHERE r.organization=? AND r.id=? AND t.id=?''', (run_org, run_id, task_id)).fetchone():
        raise Conflict('model_call_scope_mismatch')
    recorded = (owner, conversation, revision) if owner is not None else None
    origin = call_origin(db, run_org, run_id)
    if recorded != origin or (origin is not None and (type(origin[2]) is not int or origin[2] < 1)):
        raise Conflict('model_call_ownership_mismatch')
    if status not in {'recorded', 'rejected', 'unknown'} or (response is None) != (status == 'unknown'):
        raise Conflict('invalid_model_observation')
    receipt = json.loads(response) if response is not None else {}
    usage = receipt.get('usage', {})
    cost = usage.get('cost') if isinstance(usage, dict) else None
    reported = None
    if type(cost) in {int, float}:
        value = Decimal(str(cost))
        if value.is_finite() and value >= 0:
            reported = str(value)
    account = None
    if owner is not None:
        account = {'organization': history_key(owner), 'conversation_id': identity(conversation), 'revision': revision}
    return {'kind': 'model_call', 'run_organization': run_org, 'run_id': run_id,
            'task_id': identity(task_id), 'call_key': call_key, 'status': status, 'provider_reported_cost_usd': reported,
            'conversation_account': account}


def stop_observation(db, organization, row):
    request_id, inputs, receipt = row
    receipt = json.loads(receipt)
    if receipt.get('kind') != 'execution_stopped':
        return None
    conversation = identity(receipt['conversation_id'])
    revision = receipt['revision']
    fence = db.execute('''SELECT e.stopped_through,c.revision FROM conversation_execution e
        JOIN conversations c ON c.organization=e.organization AND c.id=e.conversation_id
        WHERE e.organization=? AND e.conversation_id=?''', (organization, conversation)).fetchone()
    if (type(revision) is not int or json.loads(inputs) != {'conversation_id': conversation, 'revision': revision}
            or fence is None or not 0 < revision <= fence[0] <= fence[1]):
        raise Conflict('stop_receipt_differs_from_fence')
    return {'kind': 'execution_stop', 'request_id': request_id, 'conversation_id': conversation,
            'revision': revision, 'recorded_at': recorded_time(receipt['at'])}


def review_observation(db, organization, kind, row):
    approval = row[0] if kind == 'review_revocation' else row[2]
    decision = db.execute('''SELECT d.case_id,d.subject_id,d.payload FROM review_decisions d
        JOIN review_subjects s ON s.organization=d.organization AND s.id=d.subject_id AND s.case_id=d.case_id
        JOIN review_cases c ON c.organization=d.organization AND c.id=d.case_id
        JOIN runs r ON r.organization=c.organization AND r.id=c.run_id
        WHERE d.organization=? AND d.id=?''', (organization, approval)).fetchone()
    if decision is None:
        raise Conflict('review_decision_scope_mismatch')
    case, subject, payload = decision
    payload = json.loads(payload)
    if (payload.get('id'), payload.get('case_id'), payload.get('subject_id')) != (approval, case, subject):
        raise Conflict('review_decision_identity_mismatch')
    record = {'kind': kind, 'decision_id': approval, 'case_id': identity(case), 'subject_id': identity(subject)}
    if kind == 'review_revocation':
        at = recorded_time(row[3])
        receipt = {'kind': 'approval_revoked', 'case_id': case, 'approval_id': approval, 'actor': row[1], 'at': at}
        require_review_commit(db, organization, case, 'approval_revoked', receipt, at)
        return record | {'recorded_at': at}
    accepted = json.loads(row[4])
    if (payload.get('decision') != 'approve' or (row[0], row[3]) != (case, subject)
            or (accepted.get('case_id'), accepted.get('id'), accepted.get('approval_id'), accepted.get('subject_id'))
            != (case, row[1], approval, subject)
            or accepted.get('kind') != 'simulated_agency_acceptance'
            or accepted.get('mode') != 'SYNTHETIC_NO_PRINT_NO_SEND'):
        raise Conflict('simulated_acceptance_identity_mismatch')
    at = recorded_time(accepted['accepted_at'])
    require_review_commit(db, organization, case, 'simulated_handoff_accepted', accepted, at)
    delivery = accepted.get('delivery')
    if delivery:
        from .simulated_delivery import SqliteSimulatedDelivery, require_provider_result
        require_provider_result(SqliteSimulatedDelivery(db), organization, accepted)
        record = record | {'delivery_status': delivery['status']}
    return record | {'job_id': identity(row[1]), 'mode': 'SYNTHETIC_NO_PRINT_NO_SEND', 'recorded_at': at}


def require_review_commit(db, organization, case, event, receipt, at):
    rows = db.execute('''SELECT e.payload FROM review_events e
        WHERE e.organization=? AND e.case_id=? AND e.kind=? AND e.at=?
          AND EXISTS (SELECT 1 FROM review_commands c WHERE c.organization=e.organization AND c.receipt=e.payload)''',
                      (organization, case, event, at))
    if not any(json.loads(row[0]) == receipt for row in rows):
        raise Conflict('review_effect_lacks_audit_or_receipt')


def observation(db, organization, kind, old, row):
    if old is not None and old != row and kind != 'execution_account':
        raise Conflict('earlier_record_changed')
    if kind == 'execution_account':
        conversation, policy, limit, fence = row
        if (policy != EXECUTION_POLICY or type(limit) is not int or limit < 1
                or type(fence) is not int or fence < 0
                or (old is not None and (old[:3] != row[:3] or fence < old[3]))):
            raise Conflict('execution_account_changed')
        if fence and account_evidence(db, organization, conversation).recorded_stop != fence:
            raise Conflict('stop_fence_lacks_matching_receipt')
    if kind == 'execution_command':
        return stop_observation(db, organization, row)
    if kind == 'model_call':
        return model_observation(db, row)
    if kind in REVIEW_EFFECTS:
        return review_observation(db, organization, kind, row)
    return None


def compare_store(before, later, organization):
    counts, observations = Counter(), []
    for kind in HISTORY:
        try:
            for old, row in history_changes(before, later, organization, kind):
                if old == row and kind in REVIEW_EFFECTS:
                    review_observation(before, organization, kind, old)
                result = observation(later, organization, kind, old, row)
                if old is None and result is not None:
                    counts[result['kind']] += 1
                    if len(observations) < MAX_OBSERVATIONS:
                        observations.append(result)
        except Conflict as error:
            return {'status': 'conflicting_evidence', 'evidence': kind, 'reason': str(error)}
        except (NotFound, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError, sqlite3.Error):
            return {'status': 'conflicting_evidence', 'evidence': kind, 'reason': 'unreadable_scoped_history'}
    return {'status': 'compared', 'observation_counts': dict(counts), 'observations': observations,
            'observations_omitted': sum(counts.values()) - len(observations)}


def application_keys(manifest):
    return set(manifest['stores']) - {JOURNAL}


def checkpoint_pair(before, later):
    if any(before['stores'][key]['identity'] != later['stores'][key]['identity'] for key in (ROOT, JOURNAL)):
        return 'workspace_identity_mismatch'
    if datetime.fromisoformat(later['created_at']) <= datetime.fromisoformat(before['created_at']):
        return 'later_checkpoint_not_newer'
    return None


class SqliteCheckpointReconciliation:
    def inspect(self, bundle, checkpoint_id, organization, *, later_bundle=None, later_checkpoint_id=None):
        history_key(organization)
        if (later_bundle is None) != (later_checkpoint_id is None):
            raise Conflict('Supply the later bundle and its exact checkpoint identity together')
        report = {'schema': 'workspace-checkpoint-reconciliation/v1', 'organization': organization,
                  'checkpoint_id': checkpoint_id, 'later_checkpoint_id': later_checkpoint_id,
                  'mode': 'inspection-only', 'execution': 'paused', 'activation_allowed': False,
                  'external_coverage': 'unknown', 'billing_verified': False}
        with open_checkpoint(directory(Path(bundle))) as (before, before_dbs):
            if checkpoint_id != before['checkpoint_id']:
                raise Conflict('The baseline differs from the requested checkpoint identity')
            if later_bundle is None:
                return report | {'status': 'missing_evidence', 'stores': [
                    {'path': key, 'status': 'missing_evidence', 'reason': 'later_checkpoint_unavailable'}
                    for key in sorted(application_keys(before))
                ]}
            with open_checkpoint(directory(Path(later_bundle))) as (later, later_dbs):
                if later_checkpoint_id != later['checkpoint_id']:
                    raise Conflict('The later bundle differs from the requested checkpoint identity')
                blocker = checkpoint_pair(before, later)
                if blocker:
                    return report | {'status': 'conflicting_evidence', 'reason': blocker, 'stores': []}
                stores = []
                for key in sorted(application_keys(before) | application_keys(later)):
                    prior, current = before['stores'].get(key), later['stores'].get(key)
                    if key not in before_dbs:
                        result = {'status': 'later_only', 'reason': 'no_baseline_store'}
                    elif key not in later_dbs:
                        result = {'status': 'missing_evidence', 'reason': 'later_store_unavailable'}
                    elif prior['identity'] != current['identity']:
                        result = {'status': 'conflicting_evidence', 'reason': 'application_store_identity_mismatch'}
                    elif prior['recorded_policy'] == 'verified-paused/v1' and current['recorded_policy'] != prior['recorded_policy']:
                        result = {'status': 'conflicting_evidence', 'reason': 'application_policy_downgraded'}
                    else:
                        result = compare_store(before_dbs[key], later_dbs[key], organization)
                    stores.append({'path': key} | result)
        statuses = {store['status'] for store in stores}
        status = next((value for value in ('conflicting_evidence', 'missing_evidence') if value in statuses), 'compared')
        return report | {'status': status, 'stores': stores}
