"""Public inventory metadata. Matching and classification use the original facts."""
import math
import re

from acquisition.contracts import digest
from .domain import EXECUTION_POLICY


_NATIVE_ID = (
    r'(?:workspace_[0-9a-f]{24}|(?:run|conversation|conversation_action|preparation|store|journal)_[0-9a-f]{32}'
    r'|(?:case|cohort|admission|consent|inventory)_[0-9a-f]{64})'
)
_STORE_PATH = r'(?:conversations\.sqlite|workspace\.sqlite|workspace_[0-9a-f]{24}/campaign\.sqlite)'
_REQUEST_TABLES = {'conversation_plans', 'review_commands', 'admission_requests'}


def _opaque(value):
    return None if value is None else 'opaque_' + digest(repr(value))


def _reference(value, pattern=_NATIVE_ID):
    if type(value) is str and re.fullmatch(pattern, value):
        return value
    return _opaque(value)


def _organization(value):
    return value if value == 'local-conversations' else _opaque(value)


def _enum(value, *choices):
    return value if type(value) is str and value in choices else 'unsupported'


def _scalars(source, fields, kind):
    return {field: source[field] for field in fields
            if field in source and (source[field] is None or type(source[field]) is kind)}


def _preserved(source):
    result = _scalars(source, ('revision', 'current_revision', 'recorded_calls', 'remaining_allowance'), int)
    result.update(_scalars(source, ('billing_verified', 'historical_independence_receipt'), bool))
    clock = source.get('clock')
    if type(clock) in (int, float) and 0 <= clock < 253402300800 and math.isfinite(clock):
        result['clock'] = clock
    for field in ('request_id', 'native_request_id'):
        if field in source:
            result[field] = _opaque(source[field])
    for field, pattern in (('run_id', r'run_[0-9a-f]{32}'), ('case_id', r'case_[0-9a-f]{64}'),
                           ('cohort_id', r'cohort_[0-9a-f]{64}'), ('parent_id', r'workspace_[0-9a-f]{24}')):
        if field in source:
            result[field] = _reference(source[field], pattern)
    for field in ('task_plan_fingerprint', 'intent_fingerprint', 'frozen_context_fingerprint',
                  'legacy_cutoff_fingerprint', 'model_config_fingerprint'):
        if field in source:
            result[field] = _reference(source[field], r'[0-9a-f]{64}')
    if 'consent_fingerprint' in source:
        result['consent_fingerprint'] = _reference(source['consent_fingerprint'], r'consent_[0-9a-f]{64}')
    for field, choices in (
        ('mode', ('fixture', 'model')), ('clock_mode', ('REAL', 'SIMULATED')),
        ('permission_scope', ('fixture_only', 'routing_only', 'exact_copy_revision_only')),
        ('journal_association', ('identity_match_completeness_unproven', 'identity_mismatch_or_missing')),
    ):
        if field in source:
            result[field] = _enum(source[field], *choices)
    if 'generation_choices_observed' in source:
        choices = source['generation_choices_observed']
        result['generation_choices_observed'] = {
            key: choices[key] for key in ('fixture', 'allow_model_copy', 'use_audience_catalogue')
            if type(choices.get(key)) is bool
        }
    if 'recorded_execution_account' in source:
        account = source['recorded_execution_account']
        result['recorded_execution_account'] = (None if account is None else {
            **_scalars(account, ('call_limit', 'stopped_through'), int),
            'policy': _enum(account.get('policy'), EXECUTION_POLICY),
        })
    if 'provider_observations' in source:
        result['provider_observations'] = [
            {'call_key': _opaque(call['call_key']),
             'state': _enum(call['state'], 'recorded', 'rejected', 'reserved', 'unknown'),
             'definitive_rejection': call.get('definitive_rejection') is True}
            for call in source['provider_observations']
        ]
    return result


def public_record(record, resolution):
    """Select report fields explicitly so new source metadata stays private."""
    result = {
        'id': record['id'], 'kind': record['kind'], 'format': record['format'],
        'store': _reference(record['store'], _STORE_PATH),
        'organization': _organization(record['organization']),
        'key': _reference(record['key']),
        'evidence': [
            {'store': _reference(ref['store'], _STORE_PATH), 'table': ref['table'],
             'key': _opaque(ref['key']) if ref['table'] in _REQUEST_TABLES else _reference(ref['key']),
             'fingerprint': _reference(ref['fingerprint'], r'[0-9a-f]{64}'),
             **({'organization': _organization(ref['organization'])} if 'organization' in ref else {})}
            for ref in record['evidence']
        ],
        'preserve': _preserved(record['preserve']),
        'classification': resolution['classification'], 'reasons': resolution['reasons'],
        'dependencies': resolution['dependencies'],
        'owners': [
            [_organization(organization), kind,
             _opaque(scope) if kind == 'standalone' else _reference(scope, r'conversation_[0-9a-f]{32}'), revision]
            for organization, kind, scope, revision in resolution['owners']
        ],
    }
    if 'native_request_id' in record:
        result['native_request_id'] = _opaque(record['native_request_id'])
    if 'state' in record:
        result['state'] = _enum(record['state'], 'queued', 'running', 'waiting', 'succeeded', 'failed', 'cancelled')
    return result


def public_file(source):
    result = {'key': _reference(source['key'], _STORE_PATH), 'role': source['role'], 'state': source['state']}
    result.update(_scalars(source, ('schema_version',), int))
    if 'store_identity' in source:
        result['store_identity'] = _reference(source['store_identity'], r'store_[0-9a-f]{32}')
    if 'recorded_policy' in source:
        result['recorded_policy'] = _enum(source['recorded_policy'], 'unsealed', 'verified-paused/v1')
    if 'journal_identity' in source:
        journal = source['journal_identity']
        result['journal_identity'] = {'singleton': 1, 'journal_id': _reference(journal['journal_id'], r'journal_[0-9a-f]{32}'),
                                      'origin': _enum(journal['origin'], 'fresh', 'legacy')}
    return result
