"""Offline contextual decisions. No provider, persistence or approval effects."""
from math import isfinite
from random import Random
from re import fullmatch

from acquisition.contracts import digest
from .domain import YouTubeError, identity


DECISION_CONTRACT = 'c7f4129dd6d50e5de4a2c41db4ab0cddf34f31bb6e1829711019ad462df59949'
REWARD = 'qualified-demo-activation/v1'
POLICIES = ('contextual-rules/v2', 'contextual-bayes-epsilon/v2', 'contextual-recorded/v2')
SAMPLING = 'allocation-prefix-sha256/v1'


def check(condition, code):
    if not condition:
        raise YouTubeError(code, code.replace('_', ' '))


def integer(value, minimum=0):
    return type(value) is int and minimum <= value < 2**53


def unique(rows, key):
    found = {}
    for row in rows:
        check(type(row) is dict and type(row.get(key)) is str, 'invalid_evidence_identity')
        identity(row[key])
        check(row[key] not in found or found[row[key]] == row, 'conflicting_evidence')
        found[row[key]] = row
    return list(found.values())


def freeze_decision(scope, view, manifest, contract):
    check(digest(contract) == DECISION_CONTRACT, 'decision_contract_changed')
    campaign = view['campaign']
    check(view['mode'] == 'OFFLINE_AUTHORED' and view['context']['provenance'] == 'authored_synthetic',
          'unsupported_context_source')
    check(manifest['organization'] == scope.organization and manifest['profile_id'] == scope.profile_id,
          'candidate_scope_mismatch')
    check(manifest['id'] == 'candidate_snapshot_' + digest({k: v for k, v in manifest.items() if k != 'id'}),
          'candidate_snapshot_changed')
    check(campaign['context_fingerprint'] == digest(view['context']), 'context_changed')
    contexts = campaign['draft']['contexts']
    rows, seen = [], set()
    for placement in campaign['draft']['placements']:
        check(placement in view['catalogue'] and placement['source'] == 'synthetic'
              and placement['creative'] in contexts, 'unsupported_inventory')
        for creative in manifest['creatives']:
            check(creative['source'] == 'authored_synthetic', 'unsupported_creative_source')
            check(creative['available'] is True and type(creative['asset_digest']) is str
                  and fullmatch(r'[0-9a-f]{64}', creative['asset_digest']), 'asset_unavailable')
            check(type(creative['asset_path']) is str and fullmatch(
                r'examples/youtube-ad-samples/[a-z0-9-]+\.mp4', creative['asset_path']), 'asset_unavailable')
            if creative['context_id'] not in contexts:
                continue
            cell = {'organization': scope.organization, 'profile_id': scope.profile_id,
                    'context_id': placement['creative'], 'placement_id': placement['id'],
                    'placement_title': placement['title'], 'creative_context': creative['context_id'],
                    'creative_version': creative['version'], 'asset_digest': creative['asset_digest'],
                    'asset_path': creative['asset_path'], 'creative_text': creative['text'],
                    'cost_per_batch_pence': creative['cost_per_batch_pence'],
                    'source': 'authored_synthetic'}
            cost = cell['cost_per_batch_pence']
            check(cost is None or integer(cost, 1), 'invalid_cost')
            cell['id'] = 'cell_' + digest(cell)
            check(cell['id'] not in seen, 'duplicate_candidate')
            seen.add(cell['id'])
            rows.append(cell)
    check(0 < len(rows) <= 64, 'candidate_set_unavailable')
    frozen = {'schema': 'youtube-contextual-input/v1', 'organization': scope.organization,
              'profile_id': scope.profile_id, 'campaign_id': campaign['id'],
              'brief_revision': campaign['revision'], 'reviewed_context_id': campaign['context_id'],
              'context_fingerprint': campaign['context_fingerprint'],
              'context_kind': 'authored_fixture_not_grounded_product_facts',
              'goal': campaign['draft']['goal'], 'contract_sha256': DECISION_CONTRACT,
              'reward_version': REWARD, 'candidate_snapshot_id': manifest['id'],
              'candidates': sorted(rows, key=lambda row: row['id'])}
    return frozen | {'id': 'input_' + digest(frozen)}


def rules_ranking(frozen):
    words = set(frozen['goal'].lower().split())
    scores = []
    for cell in frozen['candidates']:
        overlap = len(words & set((cell['creative_text'] + ' ' + cell['placement_title']).lower().split()))
        fit = min(100, 60 + overlap * 5) if cell['context_id'] == cell['creative_context'] else 0
        scores.append({'cell_id': cell['id'], 'fit': fit,
                       'reason': 'Context match and lexical overlap; not a response probability.'})
    return {'schema': 'youtube-contextual-ranking/v1', 'input_id': frozen['id'],
            'ranker': 'contextual-rules/v1', 'model': 'none', 'prompt_version': 'none',
            'provenance': 'deterministic_rules', 'scores': scores}


def checked_ranking(frozen, ranking):
    check(type(ranking) is dict and set(ranking) == {
        'schema', 'input_id', 'ranker', 'model', 'prompt_version', 'provenance', 'scores'},
        'invalid_ranking')
    check(ranking['schema'] == 'youtube-contextual-ranking/v1'
          and ranking['input_id'] == frozen['id'], 'ranking_input_changed')
    check(type(ranking['provenance']) is str
          and ranking['provenance'] in {'deterministic_rules', 'authored_model_fixture'},
          'model_evidence_unavailable')
    expected = (('contextual-rules/v1', 'none', 'none')
                if ranking['provenance'] == 'deterministic_rules'
                else ('authored-ranking-fixture/v1', 'scripted-no-llm', 'contextual-rank/v1'))
    check((ranking['ranker'], ranking['model'], ranking['prompt_version']) == expected,
          'model_evidence_unavailable')
    check(type(ranking['scores']) is list and len(ranking['scores']) <= 64, 'invalid_ranking')
    scores = {}
    for row in ranking['scores']:
        check(type(row) is dict and set(row) == {'cell_id', 'fit', 'reason'}, 'invalid_ranking')
        check(type(row['cell_id']) is str and row['cell_id'] not in scores
              and integer(row['fit']) and row['fit'] <= 100
              and type(row['reason']) is str and 0 < len(row['reason']) <= 280, 'invalid_ranking')
        scores[row['cell_id']] = row
    check(set(scores) == {cell['id'] for cell in frozen['candidates']}, 'ranking_candidate_changed')
    return scores


def history_for(frozen, allocations, cohorts, day):
    check(integer(day) and day < 7, 'planning_period_exhausted')
    check(type(allocations) is list and len(allocations) <= 10000
          and type(cohorts) is list and len(cohorts) <= 10000, 'evidence_limit')
    allocations = unique(allocations, 'id')
    cells = {cell['id']: cell for cell in frozen['candidates']}
    daily, spend, exploration = {}, 0, 0
    for row in allocations:
        check(row['input_id'] == frozen['id'] and row['cell_id'] in cells
              and row['reward_version'] == REWARD and row['policy_version'] in POLICIES
              and row.get('sampling') == SAMPLING
              and type(row.get('decision_id')) is str
              and fullmatch(r'decision_[0-9a-f]{64}', row['decision_id'])
              and type(row['ranking_sha256']) is str and fullmatch(r'[0-9a-f]{64}', row['ranking_sha256'])
              and integer(row['decision_seed']), 'allocation_version_changed')
        check(integer(row['day']) and row['day'] <= day and row['impressions'] == 100
              and type(row['impressions']) is int and type(row['exploration']) is bool, 'invalid_allocation')
        check(integer(row['cost_pence'], 1)
              and row['cost_pence'] == cells[row['cell_id']]['cost_per_batch_pence'], 'allocation_cost_changed')
        probability = row['selection_probability']
        check(type(probability) in (float, int) and isfinite(probability)
              and 0 < probability <= 1, 'invalid_selection_probability')
        daily[row['day']] = daily.get(row['day'], 0) + row['cost_pence']
        spend += row['cost_pence']
        exploration += row['cost_pence'] if row['exploration'] else 0
    check(spend <= 10000 and exploration <= 1000 and all(value <= 2000 for value in daily.values()),
          'budget_exhausted_or_invalid')
    known = {row['id']: row for row in allocations}
    cohorts = unique(cohorts, 'allocation_id')
    for row in cohorts:
        check(row['allocation_id'] in known and row['input_id'] == frozen['id']
              and row['reward_version'] == REWARD and row['source'] == 'authored_synthetic',
              'outcome_lineage_changed')
        check(all(integer(row[key]) for key in ('S', 'F', 'U', 'N', 'assigned_at'))
              and row['S'] + row['F'] + row['U'] == row['N'] <= 100
              and row['assigned_at'] == known[row['allocation_id']]['day'] * 86400,
              'invalid_outcome_counts')
        check(type(row['manifest_complete']) is bool and type(row['coverage_complete']) is bool
              and type(row['exposure_complete']) is bool,
              'invalid_outcome_coverage')
    return allocations, cohorts, daily, spend, exploration


def summarize_cohort(row, now):
    mature = now >= row['assigned_at'] + 2100
    population = mature and row['manifest_complete'] and row['N'] > 0
    complete = population and row['coverage_complete'] and row['U'] == 0
    return {'point': row['S'] / row['N'] if complete else None,
            'bounds': [row['S'] / row['N'], (row['S'] + row['U']) / row['N']] if population else None,
            'posterior_update': complete, 'mature': mature}


def outcome_summary(allocations, cohorts, now):
    observed = {row['allocation_id']: row for row in cohorts}
    covered = {row['id'] for row in allocations} == set(observed)
    s, f, u, n = (sum(row[key] for row in cohorts) for key in ('S', 'F', 'U', 'N'))
    population_known = covered and all(row['manifest_complete'] for row in cohorts)
    known = population_known and n > 0 and all(now >= row['assigned_at'] + 2100 for row in cohorts)
    complete = known and u == 0 and all(row['coverage_complete'] for row in cohorts)
    return {'S': s, 'F': f, 'U': u, 'N': n if population_known else None, 'reported_N': n,
            'counts_scope': 'complete_manifest' if population_known else 'reported_rows_only',
            'all_allocations_reported': covered,
            'point': s / n if complete else None,
            'bounds': [s / n, (s + u) / n] if known else None,
            'comparison_available': complete}


def beliefs_for(frozen, allocations, cohorts, now):
    by_id = {row['id']: row for row in allocations}
    observed = {row['allocation_id']: row for row in cohorts}
    result = {cell['id']: {'partial_reported_impressions': 0, 'partial_reported_arrivals': 0,
                          'partial_counts_scope': 'available_mature_reports_only_not_estimation',
                          'traffic_impressions': 0, 'traffic_arrivals': 0, 'traffic_cohort_ids': [],
                          'alpha': 1, 'beta': 1, 'support': 0, 'cohort_ids': []}
              for cell in frozen['candidates']}
    for row in cohorts:
        allocation = by_id[row['allocation_id']]
        belief = result[allocation['cell_id']]
        # Partial reported counts are visible, but never used for valuation.
        if now >= row['assigned_at'] + 2100:
            belief['partial_reported_impressions'] += allocation['impressions']
            belief['partial_reported_arrivals'] += row['N']
    # Both traffic estimation and response learning use the full frozen
    # cell/day membership. A high-arrival subset must not steer allocation.
    groups = {}
    for allocation in allocations:
        groups.setdefault((allocation['cell_id'], allocation['day']), []).append(allocation['id'])
    for (cell_id, day), members in groups.items():
        if now < (day + 1) * 86400 or any(member not in observed for member in members):
            continue
        rows = [observed[member] for member in members]
        belief = result[cell_id]
        cohort_id = 'cohort_' + digest({
            'input_id': frozen['id'], 'cell_id': cell_id, 'day': day, 'members': sorted(members)})
        if all(row['manifest_complete'] and row['exposure_complete']
               and now >= row['assigned_at'] + 2100 for row in rows):
            belief['traffic_impressions'] += sum(by_id[member]['impressions'] for member in members)
            belief['traffic_arrivals'] += sum(row['N'] for row in rows)
            belief['traffic_cohort_ids'].append(cohort_id)
        if (not all(row['manifest_complete'] and row['coverage_complete'] and row['U'] == 0
                    and now >= row['assigned_at'] + 2100 for row in rows)
                or sum(row['N'] for row in rows) == 0):
            continue
        belief['alpha'] += sum(row['S'] for row in rows)
        belief['beta'] += sum(row['F'] for row in rows)
        belief['support'] += sum(row['N'] for row in rows)
        belief['cohort_ids'].append(cohort_id)
    for belief in result.values():
        a, b = belief['alpha'], belief['beta']
        belief['posterior_mean'] = a / (a + b) if belief['support'] else None
        belief['posterior_sd'] = (a * b / ((a + b) ** 2 * (a + b + 1))) ** .5 if belief['support'] else None
        belief['cohort_ids'].sort()
        belief['traffic_cohort_ids'].sort()
    return result


def allocate_batch(frozen, ranking, allocations, cohorts, *, policy, day, seed):
    check(policy in POLICIES and integer(seed), 'unsupported_decision_policy')
    scores = checked_ranking(frozen, ranking)
    allocations, cohorts, daily, spend, exploration = history_for(frozen, allocations, cohorts, day)
    beliefs = beliefs_for(frozen, allocations, cohorts, day * 86400)
    planned, today, stop_reason = [], daily.get(day, 0), None
    issued_fingerprints = [digest(row) for row in allocations]
    supported = {cell: {key: b[key] for key in ('alpha', 'beta', 'traffic_impressions', 'traffic_arrivals')}
                 for cell, b in beliefs.items()}
    rejected = [{'cell_id': cell['id'], 'reason': 'cost_unavailable'} for cell in frozen['candidates']
                if cell['cost_per_batch_pence'] is None]
    while today < 2000 and spend < 10000:
        eligible = [cell for cell in frozen['candidates'] if scores[cell['id']]['fit'] > 0
                    and cell['cost_per_batch_pence'] is not None
                    and cell['cost_per_batch_pence'] <= min(2000 - today, 10000 - spend)]
        known = [cell for cell in eligible if beliefs[cell['id']]['support'] > 0
                 and beliefs[cell['id']]['traffic_impressions'] > 0]
        def value(cell):
            b = beliefs[cell['id']]
            if policy != 'contextual-bayes-epsilon/v2':
                return scores[cell['id']]['fit']
            qualified = 100 * b['traffic_arrivals'] / b['traffic_impressions'] * b['alpha'] / (b['alpha'] + b['beta'])
            return (500 * qualified - cell['cost_per_batch_pence']) / cell['cost_per_batch_pence']
        known = [cell for cell in known if value(cell) > 0]
        greedy = sorted(known, key=lambda cell: (-value(cell), cell['id']))[0] if known else None
        alternatives = [cell for cell in eligible if cell != greedy
                        and cell['cost_per_batch_pence'] <= 1000 - exploration]
        if greedy is None and not alternatives:
            relevant = [cell for cell in frozen['candidates'] if scores[cell['id']]['fit'] > 0]
            if not relevant:
                stop_reason = 'no_relevant_candidates'
            elif all(cell['cost_per_batch_pence'] is None for cell in relevant):
                stop_reason = 'cost_unavailable'
            elif not eligible:
                stop_reason = 'no_affordable_candidate'
            elif not any(beliefs[cell['id']]['support'] for cell in eligible):
                stop_reason = 'insufficient_evidence_exploration_exhausted'
            elif not any(beliefs[cell['id']]['support'] and beliefs[cell['id']]['traffic_impressions']
                         for cell in eligible):
                stop_reason = 'complete_traffic_evidence_unavailable'
            else:
                stop_reason = 'nonpositive_expected_utility_or_insufficient_exploration_budget'
            break
        epsilon = .1 if alternatives and greedy else 1 if alternatives else 0
        # A per-allocation namespace resumes identically across call partitions.
        # Raw/partial traffic is deliberately excluded from the decision basis.
        decision_id = 'decision_' + digest({
            'sampling': SAMPLING, 'input_id': frozen['id'], 'policy': policy, 'day': day,
            'seed': seed, 'ranking_sha256': digest(ranking), 'supported': supported,
            'issued_fingerprints': sorted(issued_fingerprints)})
        rng = Random(int(decision_id.removeprefix('decision_'), 16))
        exploring = rng.random() < epsilon
        selected = alternatives[rng.randrange(len(alternatives))] if exploring else greedy
        probability = epsilon / len(alternatives) if exploring else 1 - epsilon
        cost = selected['cost_per_batch_pence']
        row = {'input_id': frozen['id'], 'cell_id': selected['id'], 'day': day,
               'sampling': SAMPLING, 'decision_id': decision_id,
               'reward_version': REWARD, 'policy_version': policy,
               'ranking_sha256': digest(ranking), 'decision_seed': seed,
               'cost_pence': cost, 'impressions': 100, 'exploration': exploring,
               'selection_probability': probability}
        row['id'] = 'allocation_' + digest(row)
        planned.append(row)
        issued_fingerprints.append(digest(row))
        spend, today = spend + cost, today + cost
        exploration += cost if exploring else 0
    summary = outcome_summary(allocations, cohorts, day * 86400)
    stop_reason = stop_reason or ('total_budget_exhausted' if spend >= 10000 else 'daily_budget_exhausted')
    payload = {'schema': 'youtube-contextual-recommendation/v2', 'input': frozen, 'ranking': ranking,
               'policy_version': policy, 'reward_version': REWARD, 'day': day, 'seed': seed,
               'status': 'reviewable' if planned else 'blocked',
               'blocker': None if planned else stop_reason, 'stop_reason': stop_reason,
               'approval': 'not_granted', 'authority': 'none', 'mode': 'offline_authored',
               'evidence_class': 'authored_synthetic_only', 'real_participant_support': 0,
               'live_blockers': ['account_targeting_and_report_join_unverified',
                                 'grounded_reviewed_brief_binding_not_installed',
                                 'reference_ads_not_approved_for_generation_destination',
                                 'qualified_generation_and_assignment_not_installed',
                                 'hosted_scope_and_publication_not_verified'],
               'allocations': planned, 'beliefs': beliefs, 'rejected_candidates': rejected,
               'budget': {'currency': 'GBP', 'total_pence': spend, 'today_pence': today,
                          'exploration_pence': exploration, 'authority': 'simulation_only'},
               'historical_outcomes': summary,
               'outcome_comparison_available': summary['comparison_available'],
               'provider_effects': 0, 'response_calibration': 'unavailable_no_real_outcomes',
               'offline_replay_ips_dr': 'unavailable_no_compatible_real_logs'}
    return payload | {'id': 'recommendation_' + digest(payload)}
