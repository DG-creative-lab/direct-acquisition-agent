"""Real checkpoints can corroborate scoped local effects without granting authority."""
import json
import os
import shutil
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from acquisition.bootstrap import build, build_checkpoint_reconciliation
from acquisition.contracts import Conflict
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.reasoning import CallScope, ModelConfig
from acquisition.reviews import ReviewPolicy
from acquisition.workspace import Workspace
import test_workspace_checkpoint as checkpoint_tests
from test_conversations import PlannerModel


ORG = 'local-conversations'
LEGACY = 'workspace_' + '1' * 24 + '/campaign.sqlite'


class CheckpointReconciliationTests(TestCase):
    setUp = checkpoint_tests.WorkspaceCheckpointTests.setUp
    cli = checkpoint_tests.WorkspaceCheckpointTests.cli
    command = checkpoint_tests.WorkspaceCheckpointTests.command

    def conversation(self):
        cid = self.workspace.create_conversation('chat', 'Historical campaign')['id']
        self.workspace.message_conversation(cid, 'brief', 0, FIXTURE_MESSAGE)
        return cid

    def later(self, name='later'):
        path = self.parent / name
        return path, self.checkpoint.create(self.source, path)['checkpoint_id']

    def report(self, first, second=None, *, organization=ORG):
        bundle, checkpoint_id = first
        kwargs = {} if second is None else dict(later_bundle=second[0], later_checkpoint_id=second[1])
        return build_checkpoint_reconciliation().inspect(bundle, checkpoint_id, organization, **kwargs)

    def baseline(self):
        return self.bundle, self.checkpoint.create(self.source, self.bundle)['checkpoint_id']

    def legacy(self):
        return build(self.source / LEGACY, clock=lambda: int(self.now))

    def approvals(self, legacy, *keys):
        reviews = legacy.reviews.store
        reviews.register_actor(ORG, 'operator', ('operator',))
        reviews.register_actor(ORG, 'reviewer', ('reviewer',))
        pack = json.loads(Path('config/iwoca-product-facts-v1.json').read_text())
        reviews.activate(ORG, 'operator', 'evidence', pack, ReviewPolicy())
        results = []
        for key in keys:
            run = legacy.start(ORG, key, size=400)
            legacy.worker.drain(ORG, run_id=run)
            case = reviews.open_case(ORG, run, 'operator')
            results.append(reviews.decide(ORG, case['case_id'], case['subject_id'], 'reviewer', 'approve',
                                          key + '-approve', 'Approved synthetic fixture'))
        return results

    def model_receipts(self, legacy, organization, request, values):
        run = legacy.start(organization, request, size=20)
        return self.record_calls(legacy, organization, run, values)

    def record_calls(self, legacy, organization, run, values):
        claim = legacy.tasks.claim(organization, self.now, 60, run_id=run)
        scope = CallScope(organization, run, claim.task_id, claim.token)
        for key, response in values:
            legacy.calls.reserve(scope, key, 'exact-request-hash', 6, self.now)
            error = 'provider_request_failed' if response is None else None
            legacy.calls.record(scope, key, response, error)
        legacy.tasks.cancel(organization, run, self.now)
        return run

    @staticmethod
    def by_store(report):
        return {store['path']: store for store in report['stores']}

    def test_later_evidence_is_scoped_and_restored_root_stays_read_only(self):
        cid = self.conversation()
        legacy = self.legacy()
        revoke, accept = self.approvals(legacy, 'revoke-case', 'accept-case')
        first = self.baseline()
        self.checkpoint.restore(first[0], self.restore, first[1])

        self.workspace.stop_execution(cid, 'stop-after-checkpoint', 1)
        legacy.reviews.store.revoke(ORG, revoke['case_id'], revoke['id'], 'reviewer', 'revoke', 'Private reason')
        accepted = legacy.reviews.store.handoff(ORG, accept['case_id'], accept['id'], 'operator', 'handoff')
        run = self.model_receipts(legacy, ORG, 'new-call', (
            ('known', {'usage': {'cost': 0.012}, 'private_response': 'private-provider-payload'}),
            ('unknown', None),
        ))
        other = self.model_receipts(legacy, 'another-org', 'other-call', (
            ('known', {'usage': {'cost': 0.99}}),
        ))
        second = self.later()
        original = [checkpoint_tests.tree(path) for path in (self.restore, first[0], second[0])]

        report = self.command('reconcile', '--bundle', self.restore, '--checkpoint-id', first[1],
                              '--organization', ORG, '--later-bundle', second[0], '--later-checkpoint-id', second[1])
        self.assertEqual(report, self.report((self.restore, first[1]), second))
        self.assertEqual(report['status'], 'compared')
        self.assertEqual(report['execution'], 'paused')
        self.assertFalse(report['activation_allowed'])
        self.assertFalse(report['billing_verified'])
        self.assertEqual(report['external_coverage'], 'unknown')
        stores = self.by_store(report)
        stop, = stores['conversations.sqlite']['observations']
        self.assertEqual((stop['kind'], stop['conversation_id'], stop['revision']), ('execution_stop', cid, 1))
        rows = stores[LEGACY]['observations']
        self.assertEqual(stores[LEGACY]['observation_counts'], {
            'model_call': 2, 'review_revocation': 1, 'simulated_acceptance': 1,
        })
        calls = {row['call_key']: row for row in rows if row['kind'] == 'model_call'}
        self.assertEqual(calls['known']['provider_reported_cost_usd'], '0.012')
        self.assertEqual(calls['known']['run_id'], run)
        self.assertEqual(calls['unknown']['status'], 'unknown')
        self.assertIsNone(calls['unknown']['provider_reported_cost_usd'])
        self.assertIn(revoke['id'], {row.get('decision_id') for row in rows if row['kind'] == 'review_revocation'})
        self.assertIn(accepted['id'], {row.get('job_id') for row in rows if row['kind'] == 'simulated_acceptance'})
        self.assertNotIn(other, json.dumps(report))
        self.assertNotIn('private-provider-payload', json.dumps(report))
        self.assertNotIn('Private reason', json.dumps(report))

        result = self.cli('--db', self.restore / LEGACY, '--organization', ORG, 'work', module='acquisition')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('inspection-only', result.stderr)
        self.assertEqual([checkpoint_tests.tree(path) for path in (self.restore, first[0], second[0])], original)

    def test_missing_evidence_stays_unknown_and_later_only_stores_are_not_attributed(self):
        self.legacy()
        first = self.baseline()
        missing = self.report(first)
        self.assertEqual(missing['status'], 'missing_evidence')
        self.assertEqual(missing['external_coverage'], 'unknown')
        self.assertFalse(missing['activation_allowed'])
        self.assertTrue(all(store['status'] == 'missing_evidence' for store in missing['stores']))

        shutil.rmtree((self.source / LEGACY).parent)
        new_key = 'workspace_' + '2' * 24 + '/campaign.sqlite'
        build(self.source / new_key)
        later = self.report(first, self.later())
        stores = self.by_store(later)
        self.assertEqual(stores[LEGACY]['reason'], 'later_store_unavailable')
        self.assertEqual(stores[new_key]['status'], 'later_only')
        self.assertEqual(stores['conversations.sqlite']['observations'], [])
        self.assertEqual(later['external_coverage'], 'unknown')
        self.assertFalse(later['activation_allowed'])

    def test_later_call_follows_recorded_conversation_account_across_run_scope(self):
        legacy = self.legacy()
        conversation = legacy.conversations.create(ORG, 'owner')['id']
        legacy.conversations.message(ORG, conversation, 'brief', 0, FIXTURE_MESSAGE)
        plan_run = legacy.conversations.plan_fixture(ORG, conversation, 'fixture-plan', 1)
        legacy.worker.drain(ORG, run_id=plan_run)
        plan = legacy.conversations.view(ORG, conversation)['current_plan']['result']
        first = self.baseline()
        run_org = 'Legacy run scope'
        run = legacy.start_conversation(run_org, 'later-run', plan, '2026-10-25')
        self.record_calls(legacy, run_org, run, (('paid call', {'usage': {'cost': 0.01}}),))
        second = self.later()
        for scope in (ORG, run_org):
            with self.subTest(scope=scope):
                call, = self.by_store(self.report(first, second, organization=scope))[LEGACY]['observations']
                self.assertEqual(call['run_organization'], run_org)
                self.assertEqual(call['call_key'], 'paid call')
                self.assertEqual(call['conversation_account'], {
                    'organization': ORG, 'conversation_id': conversation, 'revision': 1,
                })

    def test_substituted_planner_account_cannot_supply_a_call_to_either_scope(self):
        model = PlannerModel()
        legacy = build(self.source / LEGACY, clock=lambda: self.now, gateway=model,
                       model_config=ModelConfig('test/planner', force_tool_choice=True))

        def conversation(scope, key):
            cid = legacy.conversations.create(scope, key)['id']
            legacy.conversations.message(scope, cid, 'brief-' + key, 0, 'Plan a £600 contractor experiment.')
            return cid

        actual = conversation(ORG, 'actual')
        decoys = {scope: conversation(scope, 'decoy') for scope in (ORG, 'another-org')}
        for scope, cid in decoys.items():
            legacy.execution.stop(scope, cid, 'initialize-decoy', 1)
        first = self.baseline()
        run = legacy.conversations.plan(ORG, actual, 'paid-plan', 1)
        legacy.worker.drain(ORG, run_id=run)
        self.assertEqual(len(model.requests), 1)
        self.assertEqual(len(legacy.calls.inspect(ORG, run)), 1)
        for scope, cid in decoys.items():
            with self.subTest(substituted_scope=scope):
                with legacy.tasks.database.transaction() as db:
                    db.execute('''UPDATE execution_runs SET owner_organization=?,conversation_id=?
                                  WHERE organization=? AND run_id=?''', (scope, cid, ORG, run))
                later = self.later('substitution-' + scope)
                for report_scope in {ORG, scope}:
                    report = self.report(first, later, organization=report_scope)
                    store = self.by_store(report)[LEGACY]
                    self.assertEqual(store['status'], 'conflicting_evidence')
                    self.assertEqual(store['reason'], 'model_call_ownership_mismatch')
                    self.assertNotIn('observations', store)
                    self.assertFalse(report['activation_allowed'])

    def test_replaced_store_and_unrelated_or_older_checkpoint_do_not_supply_evidence(self):
        self.legacy()
        first = self.baseline()
        old = self.report(first, first)
        self.assertEqual(old['reason'], 'later_checkpoint_not_newer')
        other_root = self.parent / 'other-source'
        Workspace(other_root, verified_admissions=True)._verified_mode()
        other = self.parent / 'other-bundle'
        unrelated = other, self.checkpoint.create(other_root, other)['checkpoint_id']
        conflict = self.report(first, unrelated)
        self.assertEqual(conflict['reason'], 'workspace_identity_mismatch')
        self.assertEqual(conflict['stores'], [])

        shutil.rmtree((self.source / LEGACY).parent)
        self.legacy()
        second = self.later()
        report = self.report(first, second)
        self.assertEqual(self.by_store(report)[LEGACY]['reason'], 'application_store_identity_mismatch')
        self.assertFalse(report['activation_allowed'])
        with self.assertRaisesRegex(Conflict, 'later bundle differs'):
            self.report(first, (second[0], first[1]))
        with self.assertRaisesRegex(Conflict, 'baseline differs'):
            self.report((first[0], second[1]), second)

    def test_later_history_loss_blocks_affected_store_even_if_another_effect_is_present(self):
        cid = self.conversation()
        legacy = self.legacy()
        historical = self.model_receipts(legacy, ORG, 'earlier-call', (('call', {'usage': {'cost': 0.05}}),))
        first = self.baseline()
        self.workspace.stop_execution(cid, 'real-stop', 1)
        self.model_receipts(legacy, ORG, 'another-call', (('call', {'usage': {'cost': 0.01}}),))
        with legacy.tasks.database.transaction() as db:
            row = tuple(db.execute('SELECT * FROM model_calls WHERE organization=? AND run_id=?',
                                   (ORG, historical)).fetchone())
            db.execute('DELETE FROM model_calls WHERE organization=? AND run_id=?', (ORG, historical))
        report = self.report(first, self.later())
        self.assertEqual(report['status'], 'conflicting_evidence')
        stores = self.by_store(report)
        self.assertEqual(stores[LEGACY], {'path': LEGACY, 'status': 'conflicting_evidence',
                                         'evidence': 'model_call', 'reason': 'earlier_record_missing'})
        self.assertEqual(stores['conversations.sqlite']['observations'][0]['kind'], 'execution_stop')
        self.assertFalse(report['activation_allowed'])

        with legacy.tasks.database.transaction() as db:
            changed = row[:7] + ('{"usage":{"cost":0.15}}', row[8])
            db.execute('INSERT INTO model_calls VALUES(?,?,?,?,?,?,?,?,?)', changed)
        report = self.report(first, self.later('changed-history'))
        self.assertEqual(self.by_store(report)[LEGACY]['reason'], 'earlier_record_changed')

    def test_simulated_acceptance_without_corresponding_audit_is_a_conflict(self):
        legacy = self.legacy()
        approve, = self.approvals(legacy, 'case')
        first = self.baseline()
        legacy.reviews.store.handoff(ORG, approve['case_id'], approve['id'], 'operator', 'handoff')
        with legacy.tasks.database.transaction() as db:
            db.execute("DELETE FROM review_events WHERE organization=? AND kind='simulated_handoff_accepted'", (ORG,))
        report = self.report(first, self.later())
        self.assertEqual(self.by_store(report)[LEGACY]['reason'], 'review_effect_lacks_audit_or_receipt')
        self.assertFalse(report['activation_allowed'])

    def test_retained_acceptance_losing_audit_or_receipt_blocks_later_findings(self):
        legacy = self.legacy()
        approve, = self.approvals(legacy, 'case')
        legacy.reviews.store.handoff(ORG, approve['case_id'], approve['id'], 'operator', 'handoff')
        first = self.baseline()
        self.model_receipts(legacy, ORG, 'later-call', (('call', {'usage': {'cost': 0.01}}),))
        intact = self.by_store(self.report(first, self.later('intact-history')))[LEGACY]
        self.assertEqual(intact['observation_counts'], {'model_call': 1})
        for table, predicate, placeholders in (
            ('review_events', "kind='simulated_handoff_accepted'", '?,?,?,?,?,?'),
            ('review_commands', "request_id='handoff'", '?,?,?,?'),
        ):
            with self.subTest(table=table):
                with legacy.tasks.database.transaction() as db:
                    row = tuple(db.execute(f'SELECT * FROM {table} WHERE organization=? AND {predicate}', (ORG,)).fetchone())
                    db.execute(f'DELETE FROM {table} WHERE organization=? AND {predicate}', (ORG,))
                report = self.report(first, self.later('lost-' + table))
                store = self.by_store(report)[LEGACY]
                self.assertEqual(store['status'], 'conflicting_evidence')
                self.assertEqual(store['reason'], 'review_effect_lacks_audit_or_receipt')
                self.assertNotIn('observations', store)
                self.assertFalse(report['activation_allowed'])
                with legacy.tasks.database.transaction() as db:
                    db.execute(f'INSERT INTO {table} VALUES({placeholders})', row)

    def test_bounded_observations_still_count_all_local_calls(self):
        legacy = self.legacy()
        first = self.baseline()
        self.model_receipts(legacy, ORG, 'later-calls', (('first', {'usage': {'cost': 0}}), ('second', None)))
        with patch('acquisition.adapters.sqlite.checkpoint_reconciliation.MAX_OBSERVATIONS', 1):
            store = self.by_store(self.report(first, self.later()))[LEGACY]
        self.assertEqual(store['observation_counts'], {'model_call': 2})
        self.assertEqual(store['observations'][0]['provider_reported_cost_usd'], '0')
        self.assertEqual(store['observations_omitted'], 1)

    def test_input_modified_during_comparison_prevents_a_report(self):
        from acquisition.adapters.sqlite import checkpoint_reconciliation as storage

        first, second = self.baseline(), self.later()
        compare = storage.compare_store
        path = second[0] / 'conversations.sqlite'

        def touch_input(*args):
            result = compare(*args)
            stamp = path.stat()
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000_000))
            return result

        with patch.object(storage, 'compare_store', side_effect=touch_input):
            with self.assertRaisesRegex(Conflict, 'changed during inspection'):
                self.report(first, second)
