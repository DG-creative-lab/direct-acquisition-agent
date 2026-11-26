"""Native read boundaries, frozen evidence and independently known simulation cases."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from acquisition.bootstrap import build_youtube_recommendations
from acquisition.adapters.youtube_decision_inputs import BundledDecisionInputs, AuthoredRankingReceipts
from acquisition.contracts import digest
from acquisition.youtube import (YouTubeError, YouTubeTools, allocate_batch, rules_ranking,
                                 history_for, beliefs_for, summarize_cohort, outcome_summary)
from scripts.youtube_contextual_fixture import native_campaign
from scripts import evaluate_youtube_contextual as evaluation


class AlteredSource:
    def __init__(self, source, change):
        self.source, self.change = source, change

    def load(self, scope):
        value = self.source.load(scope)
        self.change(value)
        manifest = value['manifest']
        manifest['id'] = 'candidate_snapshot_' + digest({k: v for k, v in manifest.items() if k != 'id'})
        return value


class ChangedRanking:
    def __init__(self, change):
        self.change = change

    def rank(self, frozen):
        result = AuthoredRankingReceipts().rank(frozen)
        self.change(result)
        return result


class ContextualDecisionTests(unittest.TestCase):
    def setUp(self):
        self.app, self.cid, self.authority, self.service = self.enterContext(native_campaign(
            'Prepare YouTube placements for video editing and audiobook narration.'))
        self.result = self.service.prepare(self.cid, 1)
        self.frozen, self.ledger = self.result['input'], self.result['allocations']

    def cohort(self, allocation=None, **values):
        allocation = allocation or self.ledger[0]
        return {'allocation_id': allocation['id'], 'input_id': self.frozen['id'],
                'reward_version': 'qualified-demo-activation/v1', 'source': 'authored_synthetic',
                'assigned_at': allocation['day'] * 86400, 'S': 1, 'F': 1, 'U': 0, 'N': 2,
                'manifest_complete': True, 'coverage_complete': True, 'exposure_complete': True, **values}

    def error(self, code, function):
        with self.assertRaises(YouTubeError) as denied:
            function()
        self.assertEqual(denied.exception.code, code)

    def test_native_tool_and_command_replay_are_read_only_unapproved_exact_artifacts(self):
        before = self.app.campaigns.read(self.cid)
        tool = YouTubeTools(self.app.campaigns, recommendations=self.service)
        again = tool.recommend_contextual_batch(self.cid, 1)
        self.assertEqual(again, self.result)
        self.assertEqual(before, self.app.campaigns.read(self.cid))
        self.assertEqual(again['input']['brief_revision'], 1)
        self.assertEqual(again['input']['reviewed_context_id'], before['campaign']['context_id'])
        self.assertEqual(again['approval'], 'not_granted')
        self.assertEqual(again['authority'], 'none')
        self.assertEqual(again['provider_effects'], 0)
        self.assertEqual(again['budget']['exploration_pence'], 1000)
        self.assertEqual(evaluation.constraint_failures(self.frozen, self.ledger), [])

    def test_revocation_blocks_before_loading_inputs_and_during_ranker_callback(self):
        self.authority.enabled = False
        with patch.object(self.service.source, 'load', side_effect=AssertionError('must not read assets')):
            with self.assertRaises(PermissionError):
                self.service.prepare(self.cid, 1)
        self.authority.enabled = True
        def revoke(result):
            self.authority.enabled = False
        service = build_youtube_recommendations(self.app.campaigns, ranker=ChangedRanking(revoke))
        with self.assertRaises(PermissionError):
            service.prepare(self.cid, 1, policy='contextual-recorded/v2')

    def test_existing_manual_approval_never_approves_an_adaptive_recommendation(self):
        view = self.app.campaigns.read(self.cid)
        self.app.campaigns.command('approve', {'request_id': 'approve-original', 'campaign_id': self.cid,
                                              'subject': view['review']['subject']})
        result = self.service.prepare(self.cid, 1)
        self.assertIsNotNone(self.app.campaigns.read(self.cid)['approval'])
        self.assertEqual((result['approval'], result['authority']), ('not_granted', 'none'))
        self.assertEqual(result['real_participant_support'], 0)
        self.assertTrue(result['live_blockers'])

    def test_foreign_scope_invalid_asset_and_changed_contract_are_specific_blocks(self):
        changes = (
            ('candidate_scope_mismatch', lambda v: v['manifest'].update(organization='other')),
            ('asset_unavailable', lambda v: v['manifest']['creatives'][0].update(available=False)),
            ('asset_unavailable', lambda v: v['manifest']['creatives'][0].update(asset_digest='x' * 64)),
            ('asset_unavailable', lambda v: v['manifest']['creatives'][0].update(asset_path='/private/secret.mp4')),
            ('invalid_cost', lambda v: v['manifest']['creatives'][0].update(cost_per_batch_pence=True)),
            ('decision_contract_changed', lambda v: v['contract']['simulation'].update(period_days=8)),
        )
        for code, change in changes:
            service = build_youtube_recommendations(
                self.app.campaigns, source=AlteredSource(self.service.source, change))
            with self.subTest(code=code):
                self.error(code, lambda: service.prepare(self.cid, 1))

    def test_actual_modified_media_bytes_fail_adapter_admission(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(evaluation.ROOT / 'examples/youtube-ad-samples', root / 'examples/youtube-ad-samples')
            (root / 'examples/youtube-ad-samples/editing-a.mp4').write_bytes(b'changed bytes')
            source = BundledDecisionInputs(root)
            self.error('asset_unavailable', lambda: source.load(self.app.campaigns.scope))

    def test_native_revision_change_and_asset_change_during_ranking_fence_the_result(self):
        before = self.app.campaigns.read(self.cid)
        def change_revision(result):
            self.app.campaigns.command('save', {
                'request_id': 'new-revision', 'campaign_id': self.cid, 'expected_revision': 1,
                'draft': before['campaign']['draft'] | {'title': 'Changed while ranking'}})
        service = build_youtube_recommendations(self.app.campaigns, ranker=ChangedRanking(change_revision))
        self.error('recommendation_inputs_changed',
                   lambda: service.prepare(self.cid, 1, policy='contextual-recorded/v2'))
        self.error('campaign_changed', lambda: self.service.prepare(self.cid, 1))

    def test_untrusted_ranking_cannot_add_candidates_budget_authority_or_claim_live_quality(self):
        changes = (
            ('ranking_candidate_changed', lambda r: r['scores'][0].update(cell_id='foreign')),
            ('invalid_ranking', lambda r: r['scores'].append(r['scores'][0])),
            ('invalid_ranking', lambda r: r['scores'][0].update(fit=True)),
            ('invalid_ranking', lambda r: r['scores'][0].update(cell_id=[])),
            ('invalid_ranking', lambda r: r.update(budget=999999)),
            ('model_evidence_unavailable', lambda r: r.update(model='a-real-model-claim')),
            ('model_evidence_unavailable', lambda r: r.update(provenance={})),
        )
        for code, change in changes:
            with self.subTest(code=code):
                service = build_youtube_recommendations(self.app.campaigns, ranker=ChangedRanking(change))
                self.error(code, lambda: service.prepare(self.cid, 1, policy='contextual-recorded/v2'))

    def test_missing_recorded_model_and_unknown_prices_do_not_silently_fallback(self):
        self.error('model_evidence_unavailable',
                   lambda: self.service.prepare(self.cid, 1, policy='contextual-recorded/v2'))
        def missing_prices(value):
            for row in value['manifest']['creatives']:
                row['cost_per_batch_pence'] = None
        service = build_youtube_recommendations(
            self.app.campaigns, source=AlteredSource(self.service.source, missing_prices))
        result = service.prepare(self.cid, 1)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['blocker'], 'cost_unavailable')
        self.assertEqual(result['allocations'], [])
        self.assertTrue(result['rejected_candidates'])

    def test_one_success_and_one_unknown_has_bounds_and_no_response_posterior(self):
        row = self.cohort(F=0, U=1, coverage_complete=False)
        summary = summarize_cohort(row, 2100)
        self.assertIsNone(summary['point'])
        self.assertEqual(summary['bounds'], [.5, 1.])
        self.assertFalse(summary['posterior_update'])
        belief = beliefs_for(self.frozen, self.ledger, [row], 86400)[self.ledger[0]['cell_id']]
        self.assertEqual((belief['alpha'], belief['beta'], belief['support']), (1, 1, 0))
        self.assertIsNone(belief['posterior_mean'])

    def test_maturity_coverage_manifest_and_empty_counts_gate_learning_separately(self):
        row = self.cohort()
        self.assertFalse(summarize_cohort(row, 2099)['posterior_update'])
        self.assertTrue(summarize_cohort(row, 2100)['posterior_update'])
        for change in ({'coverage_complete': False}, {'manifest_complete': False}, {'N': 0, 'S': 0, 'F': 0}):
            with self.subTest(change=change):
                self.assertFalse(summarize_cohort(row | change, 86400)['posterior_update'])
        self.assertIsNone(summarize_cohort(row | {'manifest_complete': False}, 86400)['bounds'])
        self.assertIsNone(summarize_cohort(row | {'N': 0, 'S': 0, 'F': 0}, 86400)['bounds'])

    def test_empty_arrival_report_still_counts_exposures_without_inventing_reward_support(self):
        row = self.cohort(S=0, F=0, U=0, N=0)
        belief = beliefs_for(self.frozen, self.ledger[:1], [row], 86400)[self.ledger[0]['cell_id']]
        self.assertEqual((belief['traffic_impressions'], belief['traffic_arrivals']), (100, 0))
        self.assertEqual(belief['support'], 0)
        self.assertIsNone(belief['posterior_mean'])

    def test_duplicate_receipts_count_once_and_conflicting_receipts_fail(self):
        row = self.cohort()
        allocations, cohorts, *_ = history_for(self.frozen, self.ledger[:1] * 2, [row, row], 1)
        belief = beliefs_for(self.frozen, allocations, cohorts, 86400)[self.ledger[0]['cell_id']]
        self.assertEqual((belief['alpha'], belief['beta'], belief['support']), (2, 2, 2))
        self.error('conflicting_evidence', lambda: history_for(
            self.frozen, self.ledger, [row, row | {'S': 2, 'F': 0}], 1))

    def test_response_learning_cannot_select_only_complete_batches_in_a_cell_day(self):
        first = self.ledger[0]
        second = first | {'id': 'another-issued-batch'}
        rows = [self.cohort(first), self.cohort(second, S=0, F=0, U=1, N=1, coverage_complete=False)]
        belief = beliefs_for(self.frozen, [first, second], rows, 86400)[first['cell_id']]
        self.assertEqual((belief['alpha'], belief['beta'], belief['support']), (1, 1, 0))
        missing = beliefs_for(self.frozen, [first, second], rows[:1], 86400)[first['cell_id']]
        self.assertEqual(missing['support'], 0)
        complete = [self.cohort(first), self.cohort(second)]
        belief = beliefs_for(self.frozen, [first, second], complete, 86400)[first['cell_id']]
        self.assertEqual((belief['alpha'], belief['beta'], belief['support']), (3, 3, 4))
        self.assertEqual(len(belief['cohort_ids']), 1)

    def test_partial_traffic_reports_cannot_change_an_earlier_complete_traffic_estimate(self):
        older = self.ledger[0]
        high = older | {'id': 'high-arrival-report', 'day': 1}
        missing = older | {'id': 'unreported-peer', 'day': 1}
        rows = [self.cohort(older), self.cohort(high, S=50, F=50, N=100)]
        belief = beliefs_for(self.frozen, [older, high, missing], rows, 2 * 86400)[older['cell_id']]
        self.assertEqual((belief['traffic_impressions'], belief['traffic_arrivals']), (100, 2))
        self.assertEqual((belief['partial_reported_impressions'], belief['partial_reported_arrivals']), (200, 102))
        self.assertEqual((belief['alpha'], belief['beta']), (2, 2))

    def test_partial_traffic_cannot_unlock_exploitation_after_exploration_is_spent(self):
        base = self.ledger[0]
        high = base | {'id': 'high-arrivals-day-one', 'day': 1, 'exploration': False}
        missing = base | {'id': 'missing-day-one', 'day': 1, 'exploration': False}
        rows = [self.cohort(allocation=row, exposure_complete=False) for row in self.ledger]
        rows.append(self.cohort(high, S=50, F=50, N=100))
        result = allocate_batch(self.frozen, rules_ranking(self.frozen),
                                self.ledger + [high, missing], rows,
                                policy='contextual-bayes-epsilon/v2', day=2, seed=31)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['allocations'], [])
        self.assertEqual(result['blocker'], 'complete_traffic_evidence_unavailable')

    def test_traffic_groups_require_every_manifest_and_exposure_report_but_not_response_success(self):
        older = self.ledger[0]
        high = older | {'id': 'high-report', 'day': 1}
        zero = older | {'id': 'zero-arrivals-peer', 'day': 1}
        ledger = [older, high, zero]
        complete = [self.cohort(older), self.cohort(high, S=50, F=50, N=100),
                    self.cohort(zero, S=0, F=0, N=0)]
        for key in ('manifest_complete', 'exposure_complete'):
            rows = deepcopy(complete);rows[2][key] = False
            belief = beliefs_for(self.frozen, ledger, rows, 2 * 86400)[older['cell_id']]
            with self.subTest(flag=key):
                self.assertEqual((belief['traffic_impressions'], belief['traffic_arrivals']), (100, 2))
                self.assertEqual(len(belief['traffic_cohort_ids']), 1)
        belief = beliefs_for(self.frozen, ledger, complete, 86400 + 2100)[older['cell_id']]
        self.assertEqual((belief['traffic_impressions'], belief['traffic_arrivals']), (100, 2))
        rows = deepcopy(complete);rows[1].update(S=0, F=0, U=100, coverage_complete=False)
        belief = beliefs_for(self.frozen, ledger, rows, 2 * 86400)[older['cell_id']]
        self.assertEqual((belief['traffic_impressions'], belief['traffic_arrivals']), (300, 102))
        self.assertEqual((belief['alpha'], belief['beta']), (2, 2))

    def test_partial_counts_cannot_change_draws_or_exploitation_using_supported_history(self):
        older = self.ledger[0]
        high = older | {'id': 'partial-high', 'day': 1, 'exploration': False}
        missing = older | {'id': 'still-unreported', 'day': 1, 'exploration': False}
        ledger = [older, high, missing]
        kwargs = {'policy': 'contextual-bayes-epsilon/v2', 'day': 2, 'seed': 31}
        ranking = rules_ranking(self.frozen)
        before = allocate_batch(self.frozen, ranking, ledger, [self.cohort(older)], **kwargs)
        after = allocate_batch(self.frozen, ranking, ledger, [
            self.cohort(older), self.cohort(high, S=50, F=50, N=100)], **kwargs)
        self.assertEqual(after['allocations'], before['allocations'])

    def test_same_day_continuation_preserves_conditional_choices_and_probabilities(self):
        ranking = rules_ranking(self.frozen)
        older, row = self.ledger[:1], self.cohort()
        full = allocate_batch(self.frozen, ranking, older, [row],
                              policy='contextual-bayes-epsilon/v2', day=1, seed=31)
        for count in (1, 4, 7):
            with self.subTest(prefix=count):
                resumed = allocate_batch(self.frozen, ranking, older + full['allocations'][:count], [row],
                                         policy='contextual-bayes-epsilon/v2', day=1, seed=31)
                def choice(allocation):
                    return (allocation['cell_id'], allocation['exploration'], allocation['selection_probability'])
                self.assertEqual(choice(resumed['allocations'][0]), choice(full['allocations'][count]))
                self.assertEqual(resumed['allocations'], full['allocations'][count:])
                canonical = allocate_batch(self.frozen, ranking,
                                           list(reversed(older + full['allocations'][:count])) + older, [row],
                                           policy='contextual-bayes-epsilon/v2', day=1, seed=31)
                self.assertEqual(canonical['allocations'], resumed['allocations'])
                self.assertNotEqual(full['allocations'][0]['decision_id'], resumed['allocations'][0]['decision_id'])

    def test_draw_namespace_binds_receipt_contents_even_if_an_authored_id_is_reused(self):
        ranking = rules_ranking(self.frozen)
        history = self.ledger[:1]
        first = allocate_batch(self.frozen, ranking, history, [self.cohort()],
                               policy='contextual-bayes-epsilon/v2', day=1, seed=31)
        changed = deepcopy(history);changed[0]['exploration'] = False
        second = allocate_batch(self.frozen, ranking, changed, [self.cohort()],
                                policy='contextual-bayes-epsilon/v2', day=1, seed=31)
        self.assertNotEqual(first['allocations'][0]['decision_id'], second['allocations'][0]['decision_id'])

    def test_version_reward_source_and_impossible_count_substitutions_fail(self):
        row = self.cohort()
        for code, change in (
            ('outcome_lineage_changed', {'reward_version': 'instruction-beta-v1'}),
            ('outcome_lineage_changed', {'source': 'participant'}),
            ('outcome_lineage_changed', {'input_id': 'old-version'}),
            ('invalid_outcome_counts', {'S': True}),
            ('invalid_outcome_counts', {'N': 3}),
            ('invalid_outcome_counts', {'assigned_at': 1}),
        ):
            with self.subTest(change=change):
                self.error(code, lambda: history_for(self.frozen, self.ledger, [row | change], 1))
        old = deepcopy(self.ledger)
        old[0]['input_id'] = 'previous-creative-version'
        self.error('allocation_version_changed', lambda: history_for(self.frozen, old, [], 1))

    def test_missing_outcomes_never_refund_exploration_or_enable_a_point_estimate(self):
        result = allocate_batch(self.frozen, rules_ranking(self.frozen), self.ledger, [],
                                policy='contextual-bayes-epsilon/v2', day=1, seed=9)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['blocker'], 'insufficient_evidence_exploration_exhausted')
        self.assertEqual(result['budget']['total_pence'], 1000)
        self.assertEqual(result['budget']['exploration_pence'], 1000)
        self.assertIsNone(result['historical_outcomes']['point'])
        self.assertFalse(result['historical_outcomes']['all_allocations_reported'])
        self.assertIsNone(result['historical_outcomes']['N'])

    def test_complete_reports_resume_allocation_with_known_probabilities_and_daily_caps(self):
        rows = [self.cohort(allocation=row) for row in self.ledger]
        result = allocate_batch(self.frozen, rules_ranking(self.frozen), self.ledger, rows,
                                policy='contextual-bayes-epsilon/v2', day=1, seed=9)
        self.assertEqual(result['budget']['today_pence'], 2000)
        self.assertEqual(result['budget']['total_pence'], 3000)
        self.assertEqual(result['budget']['exploration_pence'], 1000)
        self.assertTrue(all(row['selection_probability'] == 1 for row in result['allocations']))
        self.assertEqual(evaluation.constraint_failures(self.frozen, self.ledger + result['allocations']), [])
        altered = deepcopy(self.ledger)
        altered[0]['cost_pence'] = 20001
        self.assertIn('budget_violation', evaluation.constraint_failures(self.frozen, altered))

    def test_partial_history_exposes_exact_epsilon_and_uniform_choice_probabilities(self):
        seen = set()
        for seed in range(128):
            result = allocate_batch(self.frozen, rules_ranking(self.frozen), self.ledger[:1],
                                    [self.cohort()], policy='contextual-bayes-epsilon/v2', day=1, seed=seed)
            first = result['allocations'][0]
            seen.add(first['exploration'])
            self.assertAlmostEqual(first['selection_probability'], .1 / 7 if first['exploration'] else .9)
            resumed = allocate_batch(self.frozen, rules_ranking(self.frozen),
                                     self.ledger[:1] + [first], [self.cohort()],
                                     policy='contextual-bayes-epsilon/v2', day=1, seed=seed)
            second = resumed['allocations'][0]
            self.assertAlmostEqual(second['selection_probability'], .1 / 7 if second['exploration'] else .9)
            self.assertEqual(second, result['allocations'][1])
            if seen == {False, True}:
                break
        self.assertEqual(seen, {False, True})

    def test_v1_sampling_receipts_are_not_silently_reinterpreted_as_v2(self):
        legacy = deepcopy(self.ledger)
        legacy[0]['policy_version'] = 'contextual-bayes-epsilon/v1'
        self.error('allocation_version_changed', lambda: history_for(self.frozen, legacy, [], 1))
        missing = deepcopy(self.ledger);del missing[0]['decision_id']
        self.error('allocation_version_changed', lambda: history_for(self.frozen, missing, [], 1))
        self.error('unsupported_decision_policy', lambda: allocate_batch(
            self.frozen, rules_ranking(self.frozen), [], [],
            policy='contextual-bayes-epsilon/v1', day=0, seed=31))

    def test_changed_asset_snapshot_after_ranking_never_returns_a_current_recommendation(self):
        source = self.service.source
        calls = []
        class Changing:
            def load(self, scope):
                value = source.load(scope)
                calls.append(1)
                if len(calls) > 1:
                    value['manifest']['creatives'][0]['cost_per_batch_pence'] = 75
                    value['manifest']['id'] = 'candidate_snapshot_' + digest({
                        k: v for k, v in value['manifest'].items() if k != 'id'})
                return value
        service = build_youtube_recommendations(self.app.campaigns, source=Changing())
        self.error('recommendation_inputs_changed', lambda: service.prepare(self.cid, 1))

    def test_unexpected_simulation_error_stops_remaining_trials_and_fails_the_report(self):
        with patch.object(evaluation, 'simulate', side_effect=RuntimeError('unexpected')) as fake:
            result = evaluation.run()
        self.assertEqual(fake.call_count, 1)
        self.assertFalse(result['passed'])
        self.assertEqual(result['execution_error'], 'RuntimeError')
        self.assertEqual(result['not_run_trials'], 576)

    def test_trial_summary_cannot_report_a_rate_from_only_complete_replicates(self):
        row = {'scenario': 'missing-feedback', 'policy': 'contextual-rules/v2',
               'outcomes': {'point': .5}, 'expected_utility_pence': 0, 'expected_regret_pence': 1,
               'spend_pence': 1, 'blocked_days': [], 'latency_seconds': 0, 'constraint_failures': []}
        result = evaluation.aggregate([row, row | {'outcomes': {'point': None}}])[0]
        self.assertEqual(result['complete_rate_trials'], 1)
        self.assertIsNone(result['mean_activation_rate'])

    def test_missing_report_blocks_population_bounds_even_when_reported_outcomes_are_complete(self):
        row = self.cohort()
        summary = outcome_summary(self.ledger, [row], 86400)
        self.assertIsNone(summary['point'])
        self.assertIsNone(summary['bounds'])
        summary = outcome_summary(self.ledger[:1], [row], 86400)
        self.assertEqual(summary['point'], .5)

    def test_independent_relevance_grader_catches_a_valid_but_wrong_context_ranking(self):
        ranking = AuthoredRankingReceipts().rank(self.frozen)
        cells = {cell['id']: cell for cell in self.frozen['candidates']}
        for row in ranking['scores']:
            cell = cells[row['cell_id']]
            row['fit'] = 100 if cell['context_id'] != cell['creative_context'] else 0
        positives = [['video-editing', 'editing-a'], ['video-editing', 'editing-b'],
                     ['audiobook', 'audiobook-a'], ['audiobook', 'audiobook-b']]
        grade = evaluation.grade_ranking(self.frozen, ranking, positives)
        self.assertEqual(grade['precision_at_1'], 0)
        self.assertEqual(grade['ndcg_at_3'], 0)

    def test_known_truth_oracle_is_exact_and_can_choose_to_spend_nothing(self):
        corpus = json.loads(evaluation.CORPUS.read_text())
        stationary = corpus['scenarios'][0]
        self.assertAlmostEqual(evaluation.oracle_utility(self.frozen, stationary), 20000.)
        negative = next(s for s in corpus['scenarios'] if s['id'] == 'negative-utility')
        self.assertEqual(evaluation.oracle_utility(self.frozen, negative), 0.)

    def test_simulator_is_repeatable_and_keeps_truth_out_of_native_input(self):
        scenario = json.loads(evaluation.CORPUS.read_text())['scenarios'][0]
        ranking = rules_ranking(self.frozen)
        first = evaluation.simulate(self.frozen, ranking, scenario, 'contextual-bayes-epsilon/v2', 100)
        second = evaluation.simulate(self.frozen, ranking, scenario, 'contextual-bayes-epsilon/v2', 100)
        self.assertEqual(first | {'latency_seconds': 0}, second | {'latency_seconds': 0})
        self.assertGreaterEqual(first['expected_regret_pence'], -1e-8)
        self.assertNotIn('arrival_probability', json.dumps(self.frozen))
        self.assertEqual(first['constraint_failures'], [])
        self.assertEqual(self.result['offline_replay_ips_dr'], 'unavailable_no_compatible_real_logs')
