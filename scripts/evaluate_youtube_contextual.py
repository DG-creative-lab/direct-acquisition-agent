"""Zero-provider contextual ranking and allocation benchmark.

Authored ranking responses test conformance, not LLM quality. Truth and expected
rankings stay in this evaluator, outside the native recommendation command.
"""
import argparse
from collections import defaultdict
from copy import deepcopy
import json
from math import log2
from pathlib import Path
from random import Random
import socket
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from scripts.evaluation_evidence import source_state
IMPORTED_SOURCE = source_state()
from scripts.youtube_contextual_fixture import native_campaign
from acquisition.bootstrap import build_youtube_recommendations
from acquisition.adapters.youtube_decision_inputs import AuthoredRankingReceipts
from acquisition.contracts import digest
from acquisition.youtube import (YouTubeError, DECISION_CONTRACT, REWARD, allocate_batch,
                                 rules_ranking, outcome_summary, history_for)


CORPUS = ROOT / 'config/youtube-contextual-benchmark-v1.json'
CORPUS_SHA256 = '9a82400b1695f5fcf0fd489c8f64d556cd07becb74c456f51a4f0f3948ec8b36'


class MissingCosts:
    def __init__(self, source):
        self.source = source

    def load(self, scope):
        value = self.source.load(scope)
        for cell in value['manifest']['creatives']:
            cell['cost_per_batch_pence'] = None
        manifest = value['manifest']
        manifest['id'] = 'candidate_snapshot_' + digest({k: v for k, v in manifest.items() if k != 'id'})
        return value


def creative_name(cell):
    return cell['creative_version'].rsplit('-', 1)[0]


def grade_ranking(frozen, ranking, positive_pairs):
    """Independent authored labels are never supplied to the candidate ranker."""
    positives = {tuple(pair) for pair in positive_pairs}
    scores = {row['cell_id']: row['fit'] for row in ranking['scores']}
    ordered = sorted(frozen['candidates'], key=lambda cell: (-scores[cell['id']], cell['id']))
    relevant = [int((cell['context_id'], creative_name(cell)) in positives) for cell in ordered]
    ideal = sorted(relevant, reverse=True)
    dcg = sum(value / log2(index + 2) for index, value in enumerate(relevant[:3]))
    idcg = sum(value / log2(index + 2) for index, value in enumerate(ideal[:3]))
    return {'precision_at_1': relevant[0] if relevant else 0,
            'ndcg_at_3': dcg / idcg if idcg else None,
            'candidate_count': len(ordered), 'positive_candidates': sum(relevant)}


def constraint_failures(frozen, ledger):
    failures, days, total, exploration, ids = [], defaultdict(int), 0, 0, set()
    cells = {cell['id']: cell for cell in frozen['candidates']}
    for row in ledger:
        if row['id'] in ids:
            failures.append('duplicate_allocation')
        ids.add(row['id'])
        cell = cells.get(row['cell_id'])
        if row['input_id'] != frozen['id'] or cell is None:
            failures.append('foreign_action')
        if cell is None or row['cost_pence'] != cell['cost_per_batch_pence']:
            failures.append('unverified_cost')
        days[row['day']] += row['cost_pence']
        total += row['cost_pence']
        exploration += row['cost_pence'] if row['exploration'] else 0
        if not 0 < row['selection_probability'] <= 1:
            failures.append('invalid_local_probability')
    if total > 10000 or exploration > 1000 or any(value > 2000 for value in days.values()):
        failures.append('budget_violation')
    return failures


def truth_for(cell, scenario, day):
    """Hidden authored two-stage response, never an inferred audience model."""
    a, b = scenario['matched_a'], scenario['matched_b']
    if day >= scenario.get('switch_day', 8):
        a, b = b, a
    q = (a if creative_name(cell).endswith('-a') else b) if (
        cell['context_id'] == cell['creative_context']) else scenario['mismatched']
    cost = 50 if creative_name(cell).endswith('-a') else 100
    return scenario['arrival_probability'], q, cost


def oracle_utility(frozen, scenario):
    """Exact finite-horizon known-truth knapsack; 50-pence authored price grid."""
    previous = [0.] * 201
    for day in range(7):
        choices = [(truth_for(cell, scenario, day)[2] // 50,
                    100 * truth_for(cell, scenario, day)[0] * truth_for(cell, scenario, day)[1] * 500
                    - truth_for(cell, scenario, day)[2]) for cell in frozen['candidates']]
        daily = [0.] * 41
        for cap in range(1, 41):
            daily[cap] = max([daily[cap - 1]] + [
                daily[cap - cost] + value for cost, value in choices if cost <= cap])
        previous = [max(previous[budget - amount] + daily[amount]
                        for amount in range(min(40, budget) + 1)) for budget in range(201)]
    return previous[200]


def generated_cohort(row, cell, scenario, seed, pull):
    # Common random numbers are keyed by cell/day/pull, not policy or result.
    rng = Random(int(digest([seed, scenario['id'], cell['id'], row['day'], pull]), 16))
    arrival, response, _ = truth_for(cell, scenario, row['day'])
    counts = {'S': 0, 'F': 0, 'U': 0, 'N': 0}
    for _ in range(100):
        if rng.random() >= arrival:
            continue
        counts['N'] += 1
        success = rng.random() < response
        missing = rng.random() < scenario['unknown_fraction']
        counts['U' if missing else 'S' if success else 'F'] += 1
    return {'allocation_id': row['id'], 'input_id': row['input_id'], 'reward_version': REWARD,
            'source': 'authored_synthetic', 'assigned_at': row['day'] * 86400,
            'manifest_complete': True, 'coverage_complete': counts['U'] == 0,
            'exposure_complete': True, **counts}


def simulate(frozen, ranking, scenario, policy, seed, *, retain_trace=False):
    observed = frozen
    ledger, pending, cohorts, stops, trace = [], [], [], [], []
    pulls, expected_utility, actions, elapsed = defaultdict(int), 0., 0, 0.
    cells = {cell['id']: cell for cell in observed['candidates']}
    for day in range(7):
        cohorts = [row for available, row in pending if available <= day]
        started = time.perf_counter()
        batch = allocate_batch(observed, ranking, ledger, cohorts, policy=policy, day=day, seed=seed + day)
        elapsed += time.perf_counter() - started
        if batch['status'] == 'blocked':
            stops.append({'day': day, 'reason': batch['blocker']})
        trace.append({'day': day, 'budget': batch['budget'], 'recommendation_id': batch['id']})
        for row in batch['allocations']:
            cell = cells[row['cell_id']]
            arrival, response, true_cost = truth_for(cell, scenario, day)
            expected_utility += 100 * arrival * response * 500 - true_cost
            key = (cell['id'], day)
            outcome = generated_cohort(row, cell, scenario, seed, pulls[key])
            pulls[key] += 1
            pending.append((day + 1 + scenario['delay_days'], outcome))
            actions += outcome['S']  # only observed successes, no imputed unknowns
            ledger.append(row)
    cohorts = [row for available, row in pending if available <= 7]
    history_for(observed, ledger, cohorts, 6)
    summary = outcome_summary(ledger, cohorts, 7 * 86400 + 2100)
    violations = constraint_failures(observed, ledger)
    oracle = oracle_utility(frozen, scenario)
    return {'scenario': scenario['id'], 'policy': policy, 'seed': seed,
            'expected_utility_pence': expected_utility, 'oracle_expected_utility_pence': oracle,
            'expected_regret_pence': oracle - expected_utility,
            'observed_utility_pence': summary['S'] * 500 - sum(r['cost_pence'] for r in ledger)
                                      if summary['comparison_available'] else None,
            'outcomes': summary, 'spend_pence': sum(r['cost_pence'] for r in ledger),
            'exploration_pence': sum(r['cost_pence'] for r in ledger if r['exploration']),
            'constraint_failures': violations, 'blocked_days': stops,
            'latency_seconds': elapsed, 'allocations': len(ledger),
            'trace_sha256': digest(ledger), 'daily': trace,
            'sample_allocations': ledger if retain_trace else None,
            'interpretation': 'authored_simulation_not_commercial_performance'}


def task_result(task):
    with native_campaign(task['brief']) as (app, cid, authority, service):
        before = app.campaigns.read(cid)
        with app.campaigns.store.database.connect() as db:
            model_calls = db.execute('SELECT COUNT(*) FROM model_calls').fetchone()[0]
        if model_calls != 0:
            raise AssertionError('An authored task admitted model inference')
        started = time.perf_counter()
        result = service.prepare(cid, 1)
        elapsed = time.perf_counter() - started
        model = build_youtube_recommendations(app.campaigns, ranker=AuthoredRankingReceipts())
        fixture = model.prepare(cid, 1, policy='contextual-recorded/v1')
        after = app.campaigns.read(cid)
        with app.campaigns.store.database.connect() as db:
            if db.execute('SELECT COUNT(*) FROM model_calls').fetchone()[0] != 0:
                raise AssertionError('Ranking admitted model inference')
        if before != after:
            raise AssertionError('Recommendation changed the native campaign or approval')
        return {'id': task['id'], 'split': task['split'],
                'rules_relevance': grade_ranking(result['input'], result['ranking'], task['positive_pairs']),
                'fixture_conformance': grade_ranking(fixture['input'], fixture['ranking'], task['positive_pairs']),
                'model_semantic_quality': 'not_evaluated_authored_response_only',
                'latency_seconds': elapsed, 'native_state_unchanged': True,
                'recorded_model_calls': model_calls,
                'recommendation': result}


def aggregate(trials):
    groups = defaultdict(list)
    for row in trials:
        groups[(row['scenario'], row['policy'])].append(row)
    result = []
    for (scenario, policy), rows in sorted(groups.items()):
        rates = [row['outcomes']['point'] for row in rows if row['outcomes']['point'] is not None]
        result.append({'scenario': scenario, 'policy': policy, 'trials': len(rows),
                       'mean_expected_utility_pence': sum(r['expected_utility_pence'] for r in rows) / len(rows),
                       'mean_expected_regret_pence': sum(r['expected_regret_pence'] for r in rows) / len(rows),
                       'mean_activation_rate': sum(rates) / len(rates) if rates and len(rates) == len(rows) else None,
                       'complete_rate_trials': len(rates),
                       'constraint_violations': sum(len(r['constraint_failures']) for r in rows),
                       'mean_spend_pence': sum(r['spend_pence'] for r in rows) / len(rows),
                       'mean_blocked_days': sum(len(r['blocked_days']) for r in rows) / len(rows),
                       'mean_latency_seconds': sum(r['latency_seconds'] for r in rows) / len(rows)})
    return result


def run():
    before = source_state()
    corpus = json.loads(CORPUS.read_text())
    if corpus['contract_sha256'] != DECISION_CONTRACT or digest(corpus) != CORPUS_SHA256:
        raise ValueError('Benchmark contract changed')
    attempts = []
    def denied(*args, **kwargs):
        attempts.append('network_attempt')
        raise AssertionError('Network disabled in contextual benchmark')
    with patch.object(socket.socket, 'connect', denied), patch.object(socket, 'getaddrinfo', denied):
        tasks, trials, execution_error = [], [], None
        try:
            for task in corpus['tasks']:
                tasks.append(task_result(task))
            base = next(row for row in tasks if row['id'] == 'two-contexts-development')['recommendation']
            with native_campaign(base['input']['goal']) as (app, cid, authority, service):
                masked = build_youtube_recommendations(app.campaigns, source=MissingCosts(service.source))
                missing = masked.prepare(cid, 1)['input']
            for scenario in corpus['scenarios']:
                frozen = missing if scenario.get('hide_costs') else base['input']
                for policy in corpus['policies']:
                    ranking = (AuthoredRankingReceipts().rank(frozen) if policy == 'contextual-recorded/v1'
                               else rules_ranking(frozen))
                    for seed in corpus['seeds']:
                        trials.append(simulate(frozen, ranking, scenario, policy, seed,
                                               retain_trace=scenario['id'] == 'stationary'
                                               and seed == corpus['seeds'][0]))
        except Exception as error:
            # An unexpected runner error is not an expected capability blocker.
            # Stop immediately and preserve only attributable completed trials.
            execution_error = type(error).__name__
    after = source_state()
    summaries = aggregate(trials)
    stationary = {row['policy']: row for row in summaries if row['scenario'] == 'stationary'}
    rules, bayes = stationary.get('contextual-rules/v1'), stationary.get('contextual-bayes-epsilon/v1')
    complete = bool(rules and bayes and rules['complete_rate_trials']
                    == bayes['complete_rate_trials'] == len(corpus['seeds']))
    improvement = ((bayes['mean_activation_rate'] - rules['mean_activation_rate']) * 10000
                   if complete else None)
    candidate = (complete and improvement >= 200
                 and bayes['mean_expected_utility_pence'] > rules['mean_expected_utility_pence']
                 and bayes['mean_expected_regret_pence'] < rules['mean_expected_regret_pence'])
    failures = [reason for row in trials for reason in row['constraint_failures']]
    if any(row['expected_regret_pence'] < -1e-8 for row in trials):
        failures.append('invalid_oracle_comparison')
    if any(row['rules_relevance']['precision_at_1'] != 1
           or row['rules_relevance']['ndcg_at_3'] != 1 for row in tasks):
        failures.append('authored_relevance_expectation_failed')
    if any(row['fixture_conformance']['precision_at_1'] != 1
           or row['fixture_conformance']['ndcg_at_3'] != 1 for row in tasks):
        failures.append('authored_model_fixture_conformance_failed')
    if execution_error:
        failures.append('execution_error')
    if attempts or before != after or before != IMPORTED_SOURCE:
        failures.append('source_changed_or_network_attempt')
    return {'schema': 'youtube-contextual-evaluation/v1', 'contract_sha256': DECISION_CONTRACT,
            'corpus_sha256': digest(corpus), 'source': before, 'source_stable': before == after,
            'imported_source_matches': before == IMPORTED_SOURCE,
            'network_attempts': len(attempts), 'provider_effects': 0, 'model_calls': 0,
            'passed': not failures, 'failures': failures, 'tasks': tasks,
            'execution_error': execution_error,
            'not_run_trials': len(corpus['scenarios']) * len(corpus['policies']) * len(corpus['seeds']) - len(trials),
            'trials': trials, 'summary': summaries,
            'decision': {'scope': 'next_offline_iteration_only',
                         'baseline': 'candidate_bayes' if candidate and not failures else 'retain_rules',
                         'stationary_activation_lift_bps': improvement,
                         'production_promotion': 'blocked',
                         'model_semantic_quality': 'not_evaluated_no_live_or_genuine_recorded_model',
                         'real_response_calibration': 'unavailable',
                         'offline_replay_ips_dr': 'unavailable_no_compatible_real_logs',
                         'rollback': 'Any constraint failure, changed contract/corpus, or worse held-out utility.',
                         'measurement_handoff': 'docs/youtube-contextual-benchmark.md'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.local/evaluations/youtube-contextual-v1.json')
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'passed': result['passed'], 'trials': len(result['trials']),
                      'network_attempts': result['network_attempts'], 'decision': result['decision'],
                      'output': str(args.output)}, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
