"""Evidence inventory and proposed migration steps. Never an execution grant."""
from collections import Counter
from acquisition.contracts import Conflict, digest
from .legacy_migration_report import public_file, public_record
from .ports import LegacyMigrationSource

MIGRATION_PLAN_SCHEMA = 'legacy-migration-plan/v1'


def classify_inventory(snapshot):
    records = {r['id']: r for r in snapshot['records']}
    resolved = {}

    def resolve(key, ancestors=()):
        if key in resolved:
            return resolved[key]
        row = records[key]
        conflicts, missing, uncertain = (list(row[k]) for k in ('conflicts', 'missing', 'uncertain'))
        owners = {tuple(v) for v in row['owners']}
        if key in ancestors or len(ancestors) >= 20:
            return {'classification': 'conflicting', 'reasons': ['cyclic_or_overlong_parentage'], 'owners': []}
        for parent in row['parents']:
            if parent not in records:
                missing.append('original_parent_is_unavailable')
                continue
            value = resolve(parent, ancestors + (key,))
            owners.update(tuple(v) for v in value['owners'])
            if value['classification'] == 'conflicting':
                conflicts.append('parent_evidence_conflicts')
            elif value['classification'] in {'incomplete', 'uncertain'}:
                missing.append('parent_requires_reconciliation')
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
        reasons = sorted(set(conflicts + missing + uncertain))
        classification = ('conflicting' if conflicts else 'uncertain' if uncertain else 'incomplete' if missing else 'supported')
        result = {'classification': classification, 'reasons': reasons, 'owners': sorted(map(list, owners),key=repr),
                  'dependencies': row['parents']}
        resolved[key] = result
        return result

    output = []
    for key, record in sorted(records.items()):
        result = resolve(key)
        value = public_record(record, result)
        value['proposed_step'] = ('rebuild_disposable_projection' if record['format'] == 'projection' and result['classification'] == 'supported'
                                  else 'retain_verified_paused_record' if record['format'] == 'verified' and result['classification'] == 'supported'
                                  else 'review_supported_binding' if result['classification'] == 'supported'
                                  else 'preserve_and_reconcile')
        value['executable'] = False
        output.append(value)
    counts = Counter(r['classification'] for r in output)
    plan = {'schema': MIGRATION_PLAN_SCHEMA, 'source_fingerprint': snapshot['fingerprint'],
            'scope': 'canonical-root-and-explicit-journal-or-catalogue-references',
            'support_scope': 'historical-binding-evidence-only',
            'apply_available': False, 'execution_activation': False, 'legacy_certification': False,
            'migration_ready': False,
            'inspection_state': 'has_unresolved_sources' if snapshot['issues'] else 'observed_sources_read',
            'billing_verified': False, 'backup_completeness_verified': False,
            'files': [public_file(source) for source in snapshot['files']],
            'issues': [{'source': issue['source'], 'code': issue['code']} for issue in snapshot['issues']],
            'records': output,
            'summary': {k: counts[k] for k in ('supported', 'conflicting', 'incomplete', 'uncertain')},
            'required_next_gates': ['review_exact_evidence', 'transactional_migration', 'supported_backup_and_restore',
                                    'explicit_activation_and_offline_journey'],
            'limits': ['A journal identity or root witness does not prove complete ancestry.',
                       'Classification does not replace migration source validation or current authorization.',
                       'Missing parentage is not evidence of standalone ownership.',
                       'Historical permission and receipts do not authorize current execution.',
                       'Unregistered files are not scanned. Source fingerprints are not backup manifests.']}
    return plan | {'plan_id': 'migration_plan_' + digest(plan)}


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
