"""Real journal/runtime recovery and zero-provider contextual model evaluation."""
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch

from acquisition.adapters.openrouter import normalize
from acquisition.bootstrap import build_youtube_ranking_evaluation
from acquisition.contracts import Conflict, digest
from acquisition.reasoning import CallScope
from acquisition.youtube import YouTubeError, ranking_request, ranking_response
from scripts import evaluate_youtube_model_ranking as evaluation


class RankingGateway:
    def __init__(self, change=None, error=None, *, frozen=None):
        self.requests, self.change, self.error = [], change, error
        self.scores = {c['id']: 90 if c['context_id'] == c['creative_context'] else 0
                       for c in frozen['candidates']} if frozen else None

    def complete(self, request):
        self.requests.append(deepcopy(request))
        if self.error:
            raise self.error
        data = json.loads(request['messages'][1]['content'])
        value = {'input_id': data['input_id'], 'scores': [
            {'cell_id': c['id'], 'fit': self.scores[c['id']] if self.scores else 90,
             'reason': 'Authored gateway response for conformance only.'} for c in data['candidates']]}
        response = normalize({'id': 'generation_' + str(len(self.requests)), 'model': request['model'] + '-resolved',
            'provider': 'authored-test-gateway', 'usage': {'cost': 0, 'total_tokens': 100},
            'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
                'id': 'ranking-tool', 'type': 'function', 'function': {
                    'name': 'record_contextual_ranking', 'arguments': json.dumps(value)}}]}}]})
        if self.change:
            self.change(response)
        return response


class ModelRankingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'evaluation.sqlite'
        self.now = 1795687200.
        self.plan = evaluation.make_plan('test/ranker', '0.25', ['editing-development', 'books-development'])
        self.config = evaluation.validate_plan(self.plan)

    def app(self, gateway):
        return build_youtube_ranking_evaluation(self.path, self.config, gateway,
                                                evaluation.verify_case, clock=lambda: self.now)

    def run_sample(self, gateway):
        return evaluation.execute(self.plan, self.path, 'comparison', gateway, clock=lambda: self.now)

    def test_prepare_is_credential_free_and_hides_labels_prices_and_outcomes_from_model(self):
        self.assertEqual(self.plan['conservative_batch_estimate_usd'], '0.0736')
        for case in self.plan['cases']:
            payload = json.loads(case['messages'][1]['content'])
            self.assertEqual(set(payload), {'input_id', 'goal', 'candidates'})
            self.assertNotIn('positive_pairs', json.dumps(payload))
            self.assertNotIn('cost_per_batch_pence', json.dumps(payload))
            self.assertTrue(all(set(c) == {'id', 'placement_title', 'creative_text'}
                                for c in payload['candidates']))
            changed = deepcopy(case['frozen']);changed['hidden_truth'] = 'never supplied'
            changed['id'] = 'input_' + digest({k: v for k, v in changed.items() if k != 'id'})
            messages, _ = ranking_request(changed)
            self.assertNotIn('never supplied', messages[1]['content'])
        with self.assertRaises(ValueError):
            evaluation.make_plan('test/ranker', '0.01', ['editing-development'])
        free = evaluation.make_plan('test/ranker:free', '0', ['editing-development'])
        self.assertEqual(free['conservative_batch_estimate_usd'], '0')

    def test_complete_sample_records_actual_identity_cost_grades_and_native_proposals(self):
        gateway = RankingGateway()
        result = self.run_sample(gateway)
        self.assertTrue(result['complete'])
        self.assertEqual(result['gateway_kind'], 'test_double')
        self.assertEqual(result['model_calls'], 2)
        self.assertEqual(result['reported_cost_usd'], '0')
        self.assertEqual(result['mean_precision_at_1'], 1)
        self.assertEqual(result['mean_ndcg_at_3'], 1)
        for row in result['cases']:
            self.assertEqual(row['native_status'], 'reviewable')
            receipt = row['ranking']['receipt']
            self.assertEqual(receipt['requested_model'], 'test/ranker')
            self.assertEqual(receipt['resolved_model'], 'test/ranker-resolved')
            self.assertFalse(row['runtime_output']['receipt_recovered'])
        replay = self.run_sample(gateway)
        self.assertEqual(replay['cases'], result['cases'])
        self.assertEqual(len(gateway.requests), 2)
        inspected = evaluation.inspect_sample(self.plan, self.path, 'comparison')
        self.assertEqual(inspected['cases'], result['cases'])
        self.assertEqual(inspected['gateway_kind'], 'test_double')

    def test_cli_rejects_budget_overrides_and_traversing_batch_ids_before_credentials(self):
        path = Path(self.temp.name) / 'plan.json'
        path.write_text(json.dumps(self.plan))
        for batch, extra in (('safe-id', ['--budget-usd', '0.01']), ('..', []), ('.', [])):
            with self.subTest(batch=batch, extra=extra), patch.object(sys, 'argv', [
                'evaluate-ranking', '--live', '--plan', str(path), '--batch-id', batch, *extra
            ]), patch.object(sys, 'stderr', StringIO()), patch.object(evaluation, 'openrouter_key') as key:
                with self.assertRaises(SystemExit) as error:
                    evaluation.main()
                self.assertEqual(error.exception.code, 2)
                key.assert_not_called()

    def test_crash_after_provider_receipt_recovers_on_fresh_app_without_another_call(self):
        gateway = RankingGateway()
        app = self.app(gateway)
        organization, run = evaluation.admit(app, self.plan, 'crash')
        claim = app.tasks.claim(organization, self.now, 60, run_id=run)
        saved = claim.inputs
        response = app.inference.call(CallScope(organization, run, claim.task_id, claim.token),
                                      saved['case_id'], saved['messages'], saved['tools'])
        self.assertEqual(len(gateway.requests), 1)
        self.now += 61
        resumed = self.app(gateway)
        self.assertTrue(resumed.worker.tick(organization, run_id=run))
        task = resumed.tasks.inspect(organization, run)['tasks'][0]
        self.assertEqual(task['output']['response_sha256'], digest(response))
        self.assertTrue(task['output']['receipt_recovered'])
        self.assertIsNone(task['output']['inference_wall_seconds'])
        self.assertEqual(len(gateway.requests), 1)

    def test_unknown_outcome_stops_remaining_cases_and_cannot_retry_after_restart(self):
        gateway = RankingGateway(error=TimeoutError('must not expose credentials'))
        result = self.run_sample(gateway)
        self.assertFalse(result['complete'])
        self.assertEqual([r['status'] for r in result['cases']], ['execution_error', 'not_run'])
        self.assertIsNone(result['reported_cost_usd'])
        self.assertIsNone(result['mean_precision_at_1'])
        self.assertEqual(result['cases'][0]['provider_error'], 'provider_outcome_unknown')
        self.assertNotIn('credentials', json.dumps(result))
        again = self.run_sample(gateway)
        self.assertEqual(again['runtime_status'], 'failed')
        self.assertEqual(len(gateway.requests), 1)

    def test_known_billing_invalid_result_stops_batch_without_falling_back_to_rules(self):
        def wrong_input(response):
            value = json.loads(response['message']['tool_calls'][0]['function']['arguments'])
            value['input_id'] = 'different-input'
            response['message']['tool_calls'][0]['function']['arguments'] = json.dumps(value)
        gateway = RankingGateway(wrong_input)
        result = self.run_sample(gateway)
        self.assertEqual(result['reported_cost_usd'], '0')
        self.assertEqual(result['cases'][0]['failure'], 'ranking_input_changed')
        self.assertEqual(result['cases'][1]['status'], 'not_run')
        self.assertEqual(len(gateway.requests), 1)

    def test_known_billing_unexpected_native_verification_error_stops_remaining_paid_cases(self):
        gateway = RankingGateway()
        with patch.object(evaluation, 'verify_case', side_effect=RuntimeError('no raw exception text')):
            result = self.run_sample(gateway)
        self.assertFalse(result['complete'])
        self.assertEqual(result['reported_cost_usd'], '0')
        self.assertEqual(result['cases'][0]['status'], 'execution_error')
        self.assertEqual(result['cases'][1]['status'], 'not_run')
        self.assertEqual(len(gateway.requests), 1)
        self.assertNotIn('raw exception text', json.dumps(result))

    def test_missing_or_excess_billing_and_missing_provider_identity_stop_remaining_cases(self):
        for change, reason in (
            (lambda r: r['usage'].pop('cost'), 'billing_unknown'),
            (lambda r: r['usage'].update(cost=1), 'reported_cost_exceeded_ceiling'),
            (lambda r: r.update(provider=None), 'missing_provider_identity'),
        ):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as directory:
                gateway = RankingGateway(change)
                result = evaluation.execute(self.plan, Path(directory) / 'app.sqlite', reason,
                                            gateway, clock=lambda: self.now)
                self.assertFalse(result['complete'])
                self.assertEqual(result['cases'][0]['failure'], reason)
                self.assertEqual(result['cases'][1]['status'], 'not_run')
                self.assertEqual(len(gateway.requests), 1)

    def test_malformed_duplicate_unknown_and_authority_fields_in_output_are_rejected(self):
        case = self.plan['cases'][0]
        gateway = RankingGateway()
        app = self.app(gateway)
        request = app.inference.prepare_request(case['messages'], case['tools'])
        response = gateway.complete(request)
        for transform in (
            lambda v: v.update(approved=True),
            lambda v: v['scores'].append(v['scores'][0]),
            lambda v: v['scores'][0].update(fit=True),
            lambda v: v['scores'][0].update(cell_id='foreign'),
            lambda v: v['scores'][0].update(fit=101),
        ):
            altered = deepcopy(response)
            value = json.loads(altered['message']['tool_calls'][0]['function']['arguments'])
            transform(value)
            altered['message']['tool_calls'][0]['function']['arguments'] = json.dumps(value)
            with self.assertRaises(YouTubeError):
                ranking_response(case['frozen'], altered, 'test/ranker', digest(request))
        response['message']['tool_calls'][0]['function']['arguments'] = '{"scores":[],"scores":[]}'
        with self.assertRaises(YouTubeError):
            ranking_response(case['frozen'], response, 'test/ranker', digest(request))

    def test_changed_plan_settings_request_or_case_cannot_reuse_admission(self):
        gateway = RankingGateway()
        app = self.app(gateway)
        evaluation.admit(app, self.plan, 'frozen')
        changed = deepcopy(self.plan);changed['cases'][0]['messages'][0]['content'] += 'changed'
        with self.assertRaises(ValueError):
            evaluation.execute(changed, self.path, 'frozen', gateway)
        changed = deepcopy(self.plan);changed['cases'][0]['request_sha256'] = '0' * 64
        with self.assertRaises(Conflict):
            evaluation.admit(app, changed, 'frozen')
        self.assertEqual(len(gateway.requests), 0)

    def test_unknown_recorded_reservation_blocks_recovery_without_provider_dispatch(self):
        gateway = RankingGateway()
        app = self.app(gateway)
        organization, run = evaluation.admit(app, self.plan, 'reserved')
        claim = app.tasks.claim(organization, self.now, 60, run_id=run)
        app.calls.reserve(CallScope(organization, run, claim.task_id, claim.token),
                          claim.inputs['case_id'], claim.inputs['request_sha256'], 2, self.now)
        self.now += 61
        self.app(gateway).worker.drain(organization, run_id=run)
        self.assertEqual(app.tasks.inspect(organization, run)['run']['status'], 'failed')
        self.assertEqual(len(gateway.requests), 0)

    def test_comparison_rejects_different_tasks_and_never_averages_incomplete_results(self):
        result = self.run_sample(RankingGateway())
        other = deepcopy(result);other['model_config']['model'] = 'test/other'
        other['complete'] = False  # Even stale aggregate fields cannot become a partial-sample score.
        comparison = evaluation.compare([result, other])
        self.assertFalse(comparison['complete'])
        self.assertIsNone(comparison['models'][1]['mean_precision_at_1'])
        other['cases'][0]['input_id'] = 'other-input'
        with self.assertRaises(ValueError):
            evaluation.compare([result, other])

    def test_valid_but_wrong_context_rankings_get_low_quality_scores_without_becoming_runner_errors(self):
        plan = evaluation.make_plan('test/ranker', '0.25', ['mixed-held-out'])
        def invert(response):
            function = response['message']['tool_calls'][0]['function']
            value = json.loads(function['arguments'])
            for row in value['scores']:
                row['fit'] = 100 - row['fit']
            function['arguments'] = json.dumps(value)
        result = evaluation.execute(plan, self.path, 'wrong-context',
                                    RankingGateway(invert, frozen=plan['cases'][0]['frozen']), clock=lambda: self.now)
        self.assertTrue(result['complete'])
        self.assertEqual(result['mean_precision_at_1'], 0)
        self.assertEqual(result['mean_ndcg_at_3'], 0)
        self.assertEqual(result['cases'][0]['rules_relevance']['precision_at_1'], 1)


if __name__ == '__main__':
    unittest.main()
