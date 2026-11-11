"""Evidence inventory and proposed migration steps. Never an execution grant."""
from collections import Counter
import re
from acquisition.contracts import Conflict, digest
from .domain import EXECUTION_POLICY
from .legacy_migration_report import public_file, public_record
from .ports import LegacyMigrationSource

MIGRATION_PLAN_SCHEMA = 'legacy-migration-plan/v1'
MIGRATION_RECEIPT_SCHEMA = 'legacy-ownership-migration/v1'
MIGRATION_STORE = 'conversations.sqlite'
CLASSIFICATIONS = ('supported', 'conflicting', 'incomplete', 'uncertain')


def require_plan_id(plan_id):
    if type(plan_id) is not str or re.fullmatch(r'migration_plan_[0-9a-f]{64}', plan_id) is None:
        raise ValueError('Supply the exact plan ID from inspection')


def receipt_for_plan(receipt, plan_id):
    def reference(value, prefix):
        return type(value) is str and re.fullmatch(prefix + r'[0-9a-f]{64}', value) is not None

    if type(receipt) is dict:
        records, summary = receipt.get('bound_records'), receipt.get('inventory_summary')
        if (receipt.get('schema') == MIGRATION_RECEIPT_SCHEMA and receipt.get('plan_id') == plan_id
                and receipt.get('execution_activation') is False and receipt.get('status') == 'applied'
                and reference(receipt.get('source_fingerprint'), '') and type(records) is list and records
                and all(reference(record_id, 'inventory_') for record_id in records)
                and records == sorted(set(records)) and type(summary) is dict and set(summary) == set(CLASSIFICATIONS)
                and all(type(value) is int and value >= 0 for value in summary.values())
                and len(records) <= summary['supported']):
            return {key: receipt[key] for key in ('schema', 'plan_id', 'source_fingerprint', 'execution_activation',
                                                  'status', 'bound_records', 'inventory_summary')}
    raise Conflict('Stored migration receipt is invalid')


def migration_plan(snapshot):
    records = {r['id']: r for r in snapshot['records']}
    resolved = {}
    target = next((source for source in snapshot['files'] if source['key'] == MIGRATION_STORE), {})
    sealed = target.get('recorded_policy') == 'verified-paused/v1'
    accounts = {(org, conversation) for org, conversation, policy, limit, stopped in snapshot.get('migration_accounts', [])
                if policy == EXECUTION_POLICY and type(limit) is int and limit > 0 and type(stopped) is int and stopped >= 0}

    def resolve(key, ancestors=()):
        if key in resolved:
            return resolved[key]
        row = records[key]
        conflicts, missing, uncertain = (list(row[k]) for k in ('conflicts', 'missing', 'uncertain'))
        owners = {tuple(v) for v in row['owners']}
        depth = 0
        if key in ancestors or len(ancestors) >= 20:
            return {'classification': 'conflicting', 'reasons': ['cyclic_or_overlong_parentage'], 'owners': []}
        for parent in row['parents']:
            if parent not in records:
                missing.append('original_parent_is_unavailable')
                continue
            value = resolve(parent, ancestors + (key,))
            depth = max(depth, value.get('depth', 0) + 1)
            owners.update(tuple(v) for v in value['owners'])
            if value['classification'] == 'conflicting':
                conflicts.append('parent_evidence_conflicts')
            elif value['classification'] in {'incomplete', 'uncertain'}:
                missing.append('parent_requires_reconciliation')
        if depth >= 20:
            conflicts.append('cyclic_or_overlong_parentage')
        if len(owners) > 1:
            conflicts.append('ownership_sources_disagree')
        if row['kind'] == 'run':
            if not owners:
                missing.append('positive_ownership_evidence_is_missing')
            if row.get('index_owner') and owners and tuple(row['index_owner']) not in owners:
                conflicts.append('recorded_account_differs_from_source')
            if row.get('journal_owner') and owners and tuple(row['journal_owner']) not in owners:
                conflicts.append('journal_claim_differs_from_source')
            if not row['permission_recorded']:
                missing.append('original_generation_permission_requires_review')
            if sealed and row['store'] == MIGRATION_STORE and row['format'] == 'legacy':
                if not row.get('journal_bound_before_history'):
                    missing.append('original_journal_binding_requires_reconciliation')
                if row.get('origin_pending') or not row.get('index_owner'):
                    missing.append('execution_origin_requires_reconciliation')
                if any(kind == 'conversation' and (org, scope) not in accounts for org, kind, scope, _ in owners):
                    missing.append('original_execution_account_requires_reconciliation')
        reasons = sorted(set(conflicts + missing + uncertain))
        classification = ('conflicting' if conflicts else 'uncertain' if uncertain else 'incomplete' if missing else 'supported')
        result = {'classification': classification, 'reasons': reasons, 'owners': sorted(map(list, owners),key=repr),
                  'dependencies': row['parents'], 'depth': depth}
        resolved[key] = result
        return result

    output, bindings = [], []
    for key, record in sorted(records.items()):
        result = resolve(key)
        value = public_record(record, result)
        value['proposed_step'] = ('rebuild_disposable_projection' if record['format'] == 'projection' and result['classification'] == 'supported'
                                  else 'retain_verified_paused_record' if record['format'] == 'verified' and result['classification'] == 'supported'
                                  else 'review_supported_binding' if result['classification'] == 'supported'
                                  else 'preserve_and_reconcile')
        value['executable'] = False
        if (sealed and record['kind'] == 'run' and record['format'] == 'legacy' and record['store'] == MIGRATION_STORE
                and result['classification'] == 'supported' and len(result['owners']) == 1
                and result['owners'][0][1] == 'conversation'):
            if record.get('migration_recorded'):
                value['proposed_step'] = 'retain_migrated_paused_binding'
            else:
                value['proposed_step'] = 'migrate_paused_ownership'
                bindings.append({'record_id': key, 'organization': record['organization'], 'run_id': record['key'],
                                 'owner': result['owners'][0], 'task_plan': record['preserve']['task_plan_fingerprint'],
                                 'evidence_fingerprint': digest(record['evidence']), 'dependencies': result['dependencies']})
        output.append(value)
    applicable = bool(bindings and not snapshot['issues'] and target.get('schema_version') in {14, 15, 16, 17} and sealed)
    counts = Counter(r['classification'] for r in output)
    plan = {'schema': MIGRATION_PLAN_SCHEMA, 'source_fingerprint': snapshot['fingerprint'],
            'scope': 'canonical-root-and-explicit-journal-or-catalogue-references',
            'support_scope': 'historical-binding-evidence-only',
            'apply_available': applicable, 'execution_activation': False, 'legacy_certification': False,
            'migration_ready': False,
            'inspection_state': 'has_unresolved_sources' if snapshot['issues'] else 'observed_sources_read',
            'billing_verified': False, 'backup_completeness_verified': False,
            'files': [public_file(source) for source in snapshot['files']],
            'issues': [{'source': issue['source'], 'code': issue['code']} for issue in snapshot['issues']],
            'records': output,
            'summary': {k: counts[k] for k in CLASSIFICATIONS},
            'required_next_gates': ['review_exact_evidence', 'transactional_migration', 'supported_backup_and_restore',
                                    'explicit_activation_and_offline_journey'],
            'limits': ['A journal identity or root witness does not prove complete ancestry.',
                       'Classification does not replace migration source validation or current authorization.',
                       'Missing parentage is not evidence of standalone ownership.',
                       'Historical permission and receipts do not authorize current execution.',
                       'Unregistered files are not scanned. Source fingerprints are not backup manifests.']}
    return plan | {'plan_id': 'migration_plan_' + digest(plan)}, bindings


def classify_inventory(snapshot):
    return migration_plan(snapshot)[0]


class LegacyMigrationInventory:
    def __init__(self, source: LegacyMigrationSource):
        self.source = source

    def inspect(self):
        with self.source.exclusive():
            snapshot = self.source.snapshot()
            plan = classify_inventory(snapshot)
            if self.source.snapshot()['fingerprint'] != snapshot['fingerprint']:
                raise Conflict('Inventory changed during inspection. Stop all writers and inspect again.')
            return plan

    def receipt(self, plan_id):
        require_plan_id(plan_id)
        previous = self.source.receipt(plan_id)
        if previous is None:
            raise Conflict('No committed migration receipt exists for this plan ID')
        return receipt_for_plan(previous, plan_id)

    def apply(self, expected_plan):
        require_plan_id(expected_plan)
        previous = self.source.receipt(expected_plan)
        if previous is not None:
            return receipt_for_plan(previous, expected_plan)
        with self.source.exclusive(), self.source.transaction() as transaction:
            previous = transaction.receipt(expected_plan)
            if previous is not None:
                return receipt_for_plan(previous, expected_plan)
            plan, bindings = migration_plan(transaction.snapshot())
            if plan['plan_id'] != expected_plan:
                raise Conflict('Migration evidence changed. Stop writers and inspect again.')
            if not plan['apply_available']:
                raise Conflict('Apply requires a sealed schema-14 through schema-17 conversation store, readable sources and supported legacy bindings.')
            receipt = {'schema': MIGRATION_RECEIPT_SCHEMA, 'plan_id': expected_plan,
                       'source_fingerprint': plan['source_fingerprint'], 'execution_activation': False,
                       'status': 'applied', 'bound_records': [binding['record_id'] for binding in bindings],
                       'inventory_summary': plan['summary']}
            transaction.save(bindings, receipt)
            return receipt
