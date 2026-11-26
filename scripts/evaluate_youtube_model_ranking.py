"""Prepare an immutable, opt-in LLM ranking sample; default operation makes no calls."""
import argparse
from decimal import Decimal
from getpass import getpass
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from scripts.evaluation_evidence import source_state
from scripts.evaluate_youtube_contextual import CORPUS, CORPUS_SHA256, grade_ranking
from scripts.youtube_contextual_fixture import native_campaign
from acquisition.adapters.environment import openrouter_key
from acquisition.adapters.openrouter import OpenRouter
from acquisition.adapters.youtube_decision_inputs import RecordedModelRanking
from acquisition.bootstrap import build, build_youtube_ranking_evaluation, build_youtube_recommendations
from acquisition.contracts import canonical, digest
from acquisition.reasoning import Inference, ModelConfig
from acquisition.runtime import TaskSpec
from acquisition.workflows.youtube_ranking import (reported_cost, request_ceiling,
                                                  RANKING_FINALIZATION, EvaluationSourceChanged)
from acquisition.youtube import (RANKING_EVALUATION, RANKING_PROMPT, YouTubeError,
                                 ranking_request, ranking_response, rules_ranking)

IMPORTED_SOURCE = source_state()['files_sha256']
BATCH_ID = r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}'


def make_plan(model, budget='0.25', case_ids=None):
    corpus = json.loads(CORPUS.read_text())
    if digest(corpus) != CORPUS_SHA256:
        raise ValueError('Benchmark corpus changed')
    selected = set(case_ids) if case_ids is not None else {c['id'] for c in corpus['tasks']}
    cases = [c for c in corpus['tasks'] if c['id'] in selected]
    if not cases or len(cases) != len(selected) or (case_ids is not None and len(selected) != len(case_ids)):
        raise ValueError('Choose distinct installed task IDs')
    config = ModelConfig(model, max_calls=len(cases), max_output_tokens=2400,
                         max_input_bytes=32000, force_tool_choice=True)
    ceiling = request_ceiling(config) * len(cases)
    budget = Decimal(str(budget))
    if not budget.is_finite() or not ceiling <= budget <= 1:
        raise ValueError('Budget must cover the conservative batch estimate and be at most $1')
    inference = Inference(None, None, config, time.time)
    frozen_cases = []
    before = source_state()['files_sha256']
    if before != IMPORTED_SOURCE:
        raise ValueError('Restart the evaluator after source changes')
    for case in cases:
        with native_campaign(case['brief']) as (_, cid, _, service):
            frozen = service.prepare(cid, 1)['input']
        messages, tools = ranking_request(frozen)
        request = inference.prepare_request(messages, tools)
        frozen_cases.append({'case_id': case['id'], 'split': case['split'], 'frozen': frozen,
                             'positive_pairs': case['positive_pairs'], 'messages': messages, 'tools': tools,
                             'request_sha256': digest(request)})
    if source_state()['files_sha256'] != before:
        raise ValueError('Source changed during preparation')
    plan = {'schema': 'youtube-model-ranking-plan/v2', 'corpus_sha256': CORPUS_SHA256,
            'source_commit': source_state()['head_commit'],
            'source_sha256': before, 'prompt_version': RANKING_PROMPT,
            'model_config': config.payload(), 'budget_usd': str(budget),
            'conservative_batch_estimate_usd': str(ceiling), 'cases': frozen_cases,
            'scope': 'authored_campaign_relevance_only_no_real_response_or_spend_authority'}
    return plan | {'id': 'ranking_plan_' + digest(plan)}


def validate_plan(plan):
    # Reproduce the public prepared contract before credentials or inference.
    expected = make_plan(plan['model_config']['model'], plan['budget_usd'],
                         [c['case_id'] for c in plan['cases']])
    if canonical(expected) != canonical(plan):
        raise ValueError('Plan changed or source differs; use the original checkout or prepare a new sample')
    return ModelConfig(**plan['model_config'])


def task_specs(plan, gateway_kind):
    return [TaskSpec(RANKING_EVALUATION, case | {
        'model_config': plan['model_config'], 'plan_id': plan['id'], 'gateway_kind': gateway_kind,
        'budget_usd': plan['budget_usd'], 'source_sha256': plan['source_sha256']}, max_attempts=2)
        for case in plan['cases']] + [TaskSpec(RANKING_FINALIZATION, {
            'plan_id': plan['id'], 'source_sha256': plan['source_sha256'],
            'gateway_kind': gateway_kind}, max_attempts=2)]


def admit(app, plan, batch_id, gateway_kind='test_double'):
    if not re.fullmatch(BATCH_ID, batch_id):
        raise ValueError('Use a bounded batch identity')
    if app.inference.config.payload() != plan['model_config']:
        raise ValueError('Evaluation model settings differ from the plan')
    organization = 'youtube-ranking-evaluation:' + batch_id
    run = app.tasks.create(organization, 'ranking-sample', task_specs(plan, gateway_kind), app.clock())
    return organization, run


def verify_case(case, ranking):
    with native_campaign(case['frozen']['goal']) as (native, cid, _, _):
        view = build_youtube_recommendations(native.campaigns, ranker=RecordedModelRanking(ranking))
        proposal = view.prepare(cid, 1, policy='contextual-recorded/v2')
        if proposal['input'] != case['frozen']:
            raise ValueError('Native recommendation inputs changed')
    return {'native_recommendation_id': proposal['id'], 'native_status': proposal['status'],
            'model_relevance': grade_ranking(case['frozen'], ranking, case['positive_pairs'])}


def verify_source(inputs):
    observed = source_state()['files_sha256']
    if observed != inputs['source_sha256']:
        raise EvaluationSourceChanged('Evaluation source differs from the pinned plan')
    return {'expected_sha256': inputs['source_sha256'], 'observed_sha256': observed}


def report(app, plan, organization, run, *, gateway_kind):
    state = app.tasks.inspect(organization, run)
    tasks = state['tasks'][:len(plan['cases'])]
    finalization = state['tasks'][len(plan['cases']):]
    expected_validation = {'expected_sha256': plan['source_sha256'], 'observed_sha256': plan['source_sha256']}
    unstable = any((task['output'] or {}).get('error_code') == EvaluationSourceChanged.__name__
                   for task in state['tasks'])
    validated = (len(finalization) == 1 and finalization[0]['capability'] == RANKING_FINALIZATION
                 and finalization[0]['status'] == 'succeeded'
                 and finalization[0]['output'] == {'plan_id': plan['id'], 'source_validation': expected_validation}
                 and all((task['output'] or {}).get('source_validation') == expected_validation for task in tasks))
    source_stable = False if unstable else True if validated else None
    calls = app.calls.inspect(organization, run)
    by_key = {call['key']: call for call in calls}
    rows, costs, unknown_cost = [], [], 0
    for case, task in zip(plan['cases'], tasks, strict=True):
        row = {'case_id': case['case_id'], 'split': case['split'], 'input_id': case['frozen']['id'],
               'status': 'not_run', 'model_relevance': None, 'ranking': None,
               'rules_relevance': grade_ranking(case['frozen'], rules_ranking(case['frozen']), case['positive_pairs'])}
        call = by_key.get(case['case_id'])
        if call:
            response = call['receipt']
            try:
                cost = reported_cost(response)
                costs.append(cost)
                if cost > request_ceiling(ModelConfig(**plan['model_config'])):
                    row['failure'] = 'reported_cost_exceeded_ceiling'
            except YouTubeError:
                unknown_cost += 1
                row['failure'] = 'billing_unknown'
            row['call_status'], row['provider_error'] = call['status'], call['error']
            if call['status'] == 'recorded':
                try:
                    ranking = ranking_response(case['frozen'], response, plan['model_config']['model'], case['request_sha256'])
                    if task['status'] == 'succeeded' and task['output']['ranking'] == ranking:
                        row.update(status='completed', ranking=ranking, **task['output']['verification'])
                    else:
                        row['status'] = 'execution_error' if task['status'] == 'failed' else 'receipt_pending_commit'
                except YouTubeError as error:
                    row.update(status='invalid_ranking', failure=error.code)
            else:
                row['status'] = 'execution_error'
        elif task['status'] == 'failed':
            row['status'] = 'execution_error'
        row['runtime_status'], row['runtime_output'] = task['status'], task['output']
        rows.append(row)
    complete = (source_stable is True and state['run']['status'] == 'succeeded' and not unknown_cost
                and all(c['status'] == 'completed' and 'failure' not in c for c in rows))
    mean = lambda key: sum(c['model_relevance'][key] for c in rows) / len(rows) if complete else None
    latencies = [t['output']['inference_wall_seconds'] for t in tasks if t['status'] == 'succeeded']
    return {'schema': 'youtube-model-ranking-evaluation/v2', 'plan_id': plan['id'],
            'source_stable': source_stable,
            'source_validation': {'status': 'unstable' if unstable else 'validated' if validated else 'unavailable',
                                  'finalization': finalization[0] if len(finalization) == 1 else None},
            'source_commit': plan['source_commit'],
            'corpus_sha256': plan['corpus_sha256'], 'source_sha256': plan['source_sha256'],
            'model_config': plan['model_config'], 'prompt_version': plan['prompt_version'],
            'gateway_kind': gateway_kind, 'organization': organization, 'run_id': run,
            'runtime_status': state['run']['status'], 'complete': complete, 'cases': rows,
            'model_calls': len(calls), 'calls_without_reported_cost': unknown_cost,
            'reported_cost_usd': str(sum(costs, Decimal(0))) if not unknown_cost else None,
            'known_reported_cost_usd': str(sum(costs, Decimal(0))),
            'mean_precision_at_1': mean('precision_at_1'), 'mean_ndcg_at_3': mean('ndcg_at_3'),
            'mean_inference_wall_seconds': sum(latencies) / len(latencies)
                if complete and all(v is not None for v in latencies) else None,
            'relevance_summary': [{
                'split': split, 'cases': sum(c['split'] == split for c in rows),
                'complete': source_stable is True and all(c['status'] == 'completed' for c in rows if c['split'] == split),
                'mean_precision_at_1': (sum(c['model_relevance']['precision_at_1'] for c in rows
                    if c['split'] == split) / sum(c['split'] == split for c in rows))
                    if source_stable is True and all(c['status'] == 'completed' for c in rows if c['split'] == split) else None}
                for split in sorted({c['split'] for c in rows})],
            'budget_usd': plan['budget_usd'], 'provider_receipts': calls,
            'limits': 'Small authored relevance corpus. No audience response calibration, causal lift or production promotion.'}


def execute(plan, database, batch_id, gateway, *, clock=time.time, gateway_kind='test_double'):
    config = validate_plan(plan)
    app = build_youtube_ranking_evaluation(database, config, gateway, verify_case, clock, verify_source=verify_source)
    organization, run = admit(app, plan, batch_id, gateway_kind)
    for _ in task_specs(plan, gateway_kind):
        if not app.worker.tick(organization, run_id=run):
            break
    return report(app, plan, organization, run, gateway_kind=gateway_kind)


def inspect_sample(plan, database, batch_id):
    validate_plan(plan)
    if not Path(database).is_file():
        raise ValueError('No saved evaluation database')
    app = build(database)
    organization = 'youtube-ranking-evaluation:' + batch_id
    run = app.tasks.find_run(organization, 'ranking-sample')
    if run is None:
        raise ValueError('No saved evaluation for this batch')
    state = app.tasks.inspect(organization, run)
    kind = state['tasks'][0]['inputs']['gateway_kind']
    if [t['inputs'] for t in state['tasks']] != [s.inputs for s in task_specs(plan, kind)]:
        raise ValueError('Saved evaluation differs from this plan')
    return report(app, plan, organization, run, gateway_kind=kind)


def compare(reports):
    if len(reports) < 2:
        raise ValueError('Compare at least two model reports')
    if any(r.get('schema') != 'youtube-model-ranking-evaluation/v2' for r in reports):
        raise ValueError('Comparison requires source-validated v2 evaluation reports')
    signature = lambda r: (r['corpus_sha256'], r['source_sha256'], r['prompt_version'],
                            {k: v for k, v in r['model_config'].items() if k != 'model'},
                            [(c['case_id'], c['input_id']) for c in r['cases']])
    if any(signature(r) != signature(reports[0]) for r in reports[1:]):
        raise ValueError('Comparison requires identical frozen tasks, corpus, source and prompt')
    models = []
    for r in reports:
        model = {key: r[key] for key in ('model_config', 'gateway_kind', 'complete',
                 'mean_precision_at_1', 'mean_ndcg_at_3', 'reported_cost_usd', 'calls_without_reported_cost')}
        model['complete'] = r['complete'] and r.get('source_stable') is True
        if not model['complete']:
            model.update(mean_precision_at_1=None, mean_ndcg_at_3=None)
        models.append(model)
    return {'schema': 'youtube-model-ranking-comparison/v1',
            'complete': all(model['complete'] for model in models),
            'models': models, 'production_promotion': 'blocked',
            'limits': 'Relevance on the same small authored corpus only; incomplete reports have no aggregate score.'}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--model')
    parser.add_argument('--budget-usd')
    parser.add_argument('--case', action='append', dest='cases')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--batch-id')
    parser.add_argument('--compare', type=Path, nargs='+')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.compare:
        result = compare([json.loads(p.read_text()) for p in args.compare])
    elif args.live or args.inspect:
        if args.live and args.inspect:
            parser.error('Choose --live or --inspect')
        if (not args.plan or not args.batch_id or args.model or args.cases
                or args.budget_usd is not None):
            parser.error('--live/--inspect need --plan and --batch-id; model, tasks and budget come only from that plan')
        plan = json.loads(args.plan.read_text())
        validate_plan(plan)
        if not re.fullmatch(BATCH_ID, args.batch_id):
            parser.error('Invalid batch ID')
        directory = ROOT / '.local/evaluations/youtube-model-ranking' / args.batch_id
        # CLI state is dedicated to this evaluation, never an application/customer store.
        if args.inspect:
            result = inspect_sample(plan, directory / 'application.sqlite', args.batch_id)
        else:
            key = openrouter_key(ROOT / '.env.local') or getpass('OpenRouter key (hidden): ')
            result = execute(plan, directory / 'application.sqlite', args.batch_id,
                             OpenRouter(key), gateway_kind='openrouter')
        args.output = args.output or directory / 'report.json'
    else:
        if not args.model or not args.plan:
            parser.error('Prepare with --model and --plan; preparation makes zero provider calls')
        result = make_plan(args.model, '0.25' if args.budget_usd is None else args.budget_usd, args.cases)
        args.output = args.plan
    if args.output:
        write_json(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k in {
        'schema', 'id', 'complete', 'conservative_batch_estimate_usd', 'reported_cost_usd',
        'mean_precision_at_1', 'mean_ndcg_at_3', 'model_calls'}}, indent=2))
    if result.get('complete') is False:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
