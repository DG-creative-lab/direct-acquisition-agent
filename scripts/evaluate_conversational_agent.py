"""Offline issue-25 control evaluation. Never constructs a live provider.

Run from the repository root:
  python3 scripts/evaluate_conversational_agent.py --output /tmp/agent-evaluation.json

The independent corpus expectations are withheld from the scripted provider.
Fake responses exercise orchestration and fault handling, not semantic accuracy.
Exit 1 means an acceptance expectation failed; results are still written.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]


def source_state(root=ROOT):
    """Record actual import/configuration inputs, including uncommitted files."""
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE).decode()

    prefixes = ('src', 'tests', 'config', 'scripts')
    head = git('rev-parse', 'HEAD').strip()
    tracked = {entry.split('\t', 1)[1]: entry.split('\t', 1)[0].split()[2]
               for entry in git('ls-tree', '-r', '-z', 'HEAD', '--', *prefixes).split('\0') if entry}
    object_format = git('rev-parse', '--show-object-format').strip()
    paths = set(tracked)
    for prefix in prefixes:
        paths.update(p.relative_to(root).as_posix() for p in (root / prefix).rglob('*')
                     if (p.is_file() or p.is_symlink()) and '__pycache__' not in p.parts
                     and p.suffix not in {'.pyc', '.pyo'})
    files = {}
    changes_to_head = []
    for relative in sorted(paths):
        path = root / relative
        content = path.read_bytes() if path.is_file() else None
        record = {'sha256': hashlib.sha256(content).hexdigest() if content is not None else None}
        blob = hashlib.new(object_format, b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest() if content is not None else None
        if blob != tracked.get(relative) or relative not in tracked or path.is_symlink():
            changes_to_head.append(relative)
        if path.is_symlink():
            record['symlink_target'] = str(path.readlink())
        files[relative] = record
    status = list(filter(None, git('status', '--porcelain=v1', '-z', '--untracked-files=all', '--', *prefixes).split('\0')))
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'head_commit': head, 'worktree_dirty': bool(status or changes_to_head),
            'git_status': status, 'changes_to_head': changes_to_head, 'files_sha256': digest, 'files': files}


# Capture before importing production modules or test providers. A later
# snapshot detects edits during import or execution instead of attributing a
# mixture of code to an unchanged commit.
try:
    IMPORTED_SOURCE_STATE = source_state()
except subprocess.CalledProcessError:
    # Pure grading helpers can be imported in isolated test copies. A real
    # evaluation still requires attributable Git metadata below.
    IMPORTED_SOURCE_STATE = None

from acquisition.contracts import Conflict, canonical
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.reasoning import ModelError
from acquisition.workspace import Workspace
from acquisition.bootstrap import initialize_fixture_workspace
from test_conversations import proposal
from test_conversational_copy_revision import CopyRoutingModel


NOW = 1792972800.


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class RecordedFake:
    def __init__(self, brief):
        self.delegate = CopyRoutingModel()
        self.delegate.planner.results = [proposal(**brief)]
        self.trace = []
        self.uncertain = False

    def complete(self, request):
        self.trace.append({'tool': request['tools'][0]['function']['name'],
                           'request_sha256': hashlib.sha256(canonical(request).encode()).hexdigest(),
                           'request_bytes': len(canonical(request).encode())})
        if self.uncertain:
            raise ModelError('provider_request_failed')
        return self.delegate.complete(request)


def fake_provider(stack, model):
    stack.enter_context(patch('acquisition.workspace.openrouter_key', return_value='offline-sentinel'))
    stack.enter_context(patch('acquisition.workspace.OpenRouter', return_value=model))
    # Fail closed if a future refactor bypasses the injected provider. These
    # direct-workspace scenarios need neither remote nor loopback connections.
    stack.enter_context(patch.object(socket.socket, 'connect', side_effect=AssertionError('Network disabled in evaluation')))


def advance(w, conversation_id):
    for _ in range(12):
        w.advance_preparations()
        state = w.conversation(conversation_id)
        row = state['preparations'][-1]
        if row['status'] not in {'admitting', 'planning', 'preparing'}:
            return state
    raise AssertionError('Preparation exceeded twelve coordinator observations')


def select_and_finish(w, conversation_id, state):
    row = state['preparations'][-1]
    if row['status'] == 'selecting_audience':
        entry = row['audience_candidates']['entries'][0]
        w.select_conversation_audience(conversation_id, request_id='confirm-audience-' + str(state['revision']),
            expected_revision=state['revision'], plan_id=state['current_plan']['result']['id'],
            **{key: entry[key] for key in ('dataset_id', 'version', 'checksum')}, manifest_id=entry['id'])
        return advance(w, conversation_id)
    return state


def assess_outcome(expected, state):
    """A non-ready result is not itself evidence of the expected rejection."""
    status = state['preparations'][-1]['status']
    plan = state.get('current_plan') or {}
    planned = plan.get('result') or {}
    outcome = planned.get('outcome')
    result = {'passed': False, 'observed_status': status, 'observed_planning_outcome': outcome,
              'false_acceptance': False, 'false_rejection': False,
              'planner_error': plan.get('error')}
    if status == 'review_ready':
        result['passed'] = expected['review_ready']
        result['false_acceptance'] = not expected['review_ready']
        category = 'accepted' if result['passed'] else 'false_acceptance'
    elif status == 'uncertain':
        category = 'provider_uncertainty'
    elif status == 'failed' and plan.get('status') == 'failed':
        error = plan.get('error') or {}
        category = ('planner_failure' if error.get('error_code') == 'ModelError' and not error.get('provider_error')
                    else 'infrastructure_failure')
    elif status in {'failed', 'blocked', 'cancelled', 'stale'}:
        category = 'infrastructure_failure'
    elif status == 'needs_input' and outcome in {'clarification', 'unsupported'}:
        field = 'question' if outcome == 'clarification' else 'unsupported_reason'
        response = planned.get(field, '')
        matches = (not expected['review_ready'] and outcome == expected.get('planning_outcome')
                   and bool(response.strip()) and not state.get('campaigns')
                   and all(term.casefold() in response.casefold() for term in expected.get('response_contains', [])))
        result['passed'] = matches
        result['observed_response'] = response
        result['false_rejection'] = expected['review_ready']
        category = 'expected_' + outcome if matches else 'false_rejection' if result['false_rejection'] else 'unexpected_outcome'
    else:
        category = 'unexpected_outcome'
    return result | {'outcome_category': category}


def preference_journey(w, cid, sid, review, segment):
    target = next(c for c in review['manifest']['creatives'] if c['segment'] == segment and c['arm'] == 'B')
    saved = w.comment_artifact(cid, sid, review['subject']['id'], target['id'], 1,
                               'Prefer a concrete question about payment timing.', 'variant-comment')
    comment = next(c for c in saved['artifact_comments'] if c['request_id'] == 'variant-comment')
    require(comment['target_id'] == target['id'], 'Comment lost its exact variant')
    require(not saved['writing_preferences'], 'A comment silently wrote a preference')
    args = dict(conversation_id=cid, session_id=sid, comment_id='variant-comment', preference_id='',
                action='confirm', expected_revision=0, segments=[segment], preferred='Use a concrete timing question.',
                avoid='Do not imply guaranteed demand.', reason='Confirmed editorial guidance.', confirmed=True)
    first = w.change_writing_preference(**args, request_id='remember')['preference_receipt']
    changed = args | dict(preference_id=first['id'], action='correct', expected_revision=1,
                         preferred='Keep timing questions short and conditional.')
    second = w.change_writing_preference(**changed, request_id='correct')['preference_receipt']
    session = w._session(sid)
    memory = w._app(session).memory
    require(memory.examples(session['organization'], segment)[0]['preferred'] == second['preferred'], 'Correction was not applied')
    other = 'inventory' if segment == 'contractors' else 'contractors'
    require(not any(e['id'].startswith(first['id']) for e in memory.examples(session['organization'], other)),
            'Preference crossed its audience scope')
    return changed, second


def complete_journey(w, cid, state, model):
    sid = state['campaigns'][-1]['session_id']
    view = w.view(sid)
    review = view['review']
    require(not review['approval_valid'] and review['handoff'] is None, 'Readiness granted authority')
    required = [c for c in review['validation_report']['checks'] if c['required']]
    require(len(required) == 7 and all(c['status'] == 'passed' for c in required), 'Required validation missing')
    before = len(model.trace)
    for key, content in [('status', 'status?'), ('audience', 'which audience are we using?'),
                         ('validation', 'explain validation'), ('praise', 'looks good')]:
        w.route_followup(cid, key, 1, content, False)
    unchanged = w.conversation(cid)
    require(unchanged['revision'] == 1 and len(model.trace) == before, 'Inspection repeated inference or changed the brief')
    require(not w.view(sid)['review']['approval_valid'], 'Praise silently approved the campaign')
    segments = review['manifest']['brief']['segments']
    segment = 'contractors' if 'contractors' in segments else segments[0]
    preference, confirmed = preference_journey(w, cid, sid, review, segment)
    require(len(model.trace) == before, 'Preference operations invoked inference')
    if segment == 'contractors':
        w.route_followup(cid, 'copy-edit', 1, 'Make contractors variant B more direct. Keep the audience unchanged.', False)
        w.advance_actions()
        action = w.conversation(cid)['actions'][-1]
        require(action['result']['copy_revision']['status'] == 'ready', 'Explicit copy target unnecessarily clarified')
        try:
            w.confirm_copy_followup(cid, action['id'], 'no-consent', action['result']['id'], 1, False)
        except ValueError:
            pass
        else:
            raise AssertionError('Revision proceeded without consent')
        w.confirm_copy_followup(cid, action['id'], 'copy-confirm', action['result']['id'], 1, True)
        for _ in range(5):
            w.advance_copy_revisions()
        revised = w.view(sid)['review']
        require(revised['subject']['id'] != review['subject']['id'], 'Revision reused the old subject')
        require(not revised['approval_valid'], 'Revision inherited approval')
        require(revised['manifest']['counts'] == review['manifest']['counts'], 'Copy edit changed population')
        old_subject = review['subject']['id']
        try:
            w.action(sid, 'approve', {'request_id': 'obsolete-review', 'subject_id': old_subject, 'reason': 'Stale review'})
        except Conflict:
            pass
        else:
            raise AssertionError('An old subject could approve the revision')
        review = revised
    approved = w.action(sid, 'approve', {'request_id': 'review', 'subject_id': review['subject']['id'],
                                       'reason': 'Reviewed the exact offline artifact.'})
    require(approved['review']['handoff'] is None, 'Approval silently simulated acceptance')
    accepted = w.action(sid, 'handoff', {'request_id': 'handoff', 'approval_id': approved['review']['approval']['id']})
    require(accepted['review']['handoff']['mode'] == 'SYNTHETIC_NO_PRINT_NO_SEND', 'Acceptance was not explicitly synthetic')
    w.action(sid, 'open-learning', {'request_id': 'open'})
    early = w.action(sid, 'observe', {'request_id': 'observe'})
    require(early['learning']['missing'] > 0 and not early['learning']['beliefs'], 'Missing outcomes became observations')
    final = w.action(sid, 'finalize', {'request_id': 'finalize'})
    require(final['learning']['missing'] == 0 and final['learning']['status'] == 'finalized', 'Incomplete cohort finalized')
    cohort = final['learning']['cohort']['id']
    p = w.propose_followup(sid, 'next-experiment', cohort)
    session = w._session(sid)
    app = w._app(session)
    frozen = {s: app.memory.get_context(session['organization'], identity) for s, identity in p['contexts'].items()}
    require(any(e.get('preferred') == confirmed['preferred'] for e in frozen[segment]['memory']), 'Confirmed preference omitted from follow-up')
    retired = w.change_writing_preference(**(preference | dict(action='retire', expected_revision=2)),
                                           request_id='retire')['preference_receipt']
    require(retired['status'] == 'retired', 'Preference retirement was lost')
    require(not any(e['id'].startswith(confirmed['id']) for e in app.memory.examples(session['organization'], segment)),
            'Retired preference remained active')
    for s, identity in p['contexts'].items():
        require(app.memory.get_context(session['organization'], identity) == frozen[s], 'Retirement rewrote a frozen context')
    replay = Workspace(w.root, real_clock=lambda: NOW).propose_followup(sid, 'next-experiment', cohort)
    require(replay == p, 'Restart or lost-response retry changed the proposal')
    require(w.conversation(cid)['execution']['used'] == len(model.trace), 'Trace and shared reservations disagree')
    before_edit = len(model.trace)
    model.delegate.action = 'amend_brief'
    w.route_followup(cid, 'budget-correction', 1, 'Set the total campaign budget to £512 instead. Keep the same audiences and use offline fixture copy.', False)
    w.advance_actions()
    amendment = w.conversation(cid)['actions'][-1]
    require(w.conversation(cid)['revision'] == 1, 'Unconfirmed amendment changed the brief')
    model.delegate.planner.results = [proposal(budget_pence=51200, segments=segments, copy_mode='fixture')]
    w.confirm_followup(cid, amendment['id'], 'confirm-budget', amendment['result']['target']['id'], 1)
    amended = select_and_finish(w, cid, advance(w, cid))
    require(amended['revision'] == 2 and amended['preparations'][-1]['status'] == 'review_ready', 'Confirmed amendment did not complete')
    current_campaign = next(c for c in amended['campaigns'] if c['revision'] == amended['revision'])
    new_review = w.view(current_campaign['session_id'])['review']
    require(new_review['manifest']['brief']['budget_pence'] == 51200, 'Amendment did not bind the confirmed absolute budget')
    old_view = w.view(sid)['review']
    require(not old_view['candidate_valid'], 'Old campaign remained current after a material amendment')
    require(old_view['handoff'] == accepted['review']['handoff'], 'Amendment rewrote accepted history')
    w.confirm_followup(cid, amendment['id'], 'confirm-budget', amendment['result']['target']['id'], 1)
    require(len(model.trace) == before_edit + 2, 'Amendment replay repeated routing or planning')
    require(w.conversation(cid)['execution']['used'] == len(model.trace), 'Amended task lost shared accounting')
    questions = sum(p['result'] is not None and p['result']['outcome'] == 'clarification'
                    for p in w.conversation(cid)['plans'])
    require(questions == 0, 'A complete supported brief was unnecessarily clarified')
    return {'subject_id': review['subject']['id'], 'cohort_id': cohort, 'followup_id': p['id'],
            'hypotheses': [{'segment': h['segment'], 'status': h['evidence_status'], 'authority': h['authority']}
                           for h in p['hypotheses']], 'preference_history_revisions': retired['revision'],
            'replay_added_calls': 0, 'inspection_added_calls': 0, 'unnecessary_planner_clarifications': questions,
            'confirmed_amendment_budget_pence': 51200}


def run_case(case):
    model = RecordedFake(case['scripted_brief'])
    started = time.perf_counter()
    result = {'id': case['id'], 'expected': case['expected'], 'passed': False}
    try:
        with tempfile.TemporaryDirectory(prefix='issue25-offline-') as root, ExitStack() as stack:
            fake_provider(stack, model)
            w = Workspace(root, real_clock=lambda: NOW)
            cid = w.create_conversation('chat', case['id'])['id']
            for revision, message in enumerate(case['messages']):
                w.message_conversation(cid, 'message-' + str(revision), revision, message)
            revision = len(case['messages'])
            w.start_preparation(cid, 'prepare', revision, False, case['scripted_brief']['copy_mode'] == 'model', True)
            state = select_and_finish(w, cid, advance(w, cid))
            result.update(assess_outcome(case['expected'], state))
            ready = result['observed_status'] == 'review_ready'
            if ready:
                view = w.view(state['campaigns'][-1]['session_id'])
                require(view['review']['validation_report']['review_ready'], 'Progress contradicted validation')
                result['required_checks'] = {c['id']: c['status'] for c in view['review']['validation_report']['checks'] if c['required']}
                result['approval_valid'] = view['review']['approval_valid']
                if case['expected']['review_ready']:
                    brief = view['review']['manifest']['brief']
                    require(brief['budget_pence'] == case['expected']['budget_pence'], 'Budget differs from independent expectation')
                    require(sorted(brief['segments']) == case['expected']['segments'], 'Audience differs from independent expectation')
                    result['journey'] = complete_journey(w, cid, state, model)
    except Exception as error:
        result.update(passed=False, outcome_category='journey_failure' if isinstance(error, AssertionError) else 'infrastructure_failure',
                      error=type(error).__name__ + ': ' + str(error))
    result.update(elapsed_seconds=round(time.perf_counter() - started, 3),
                  fake_provider_calls=len(model.trace), request_bytes=sum(t['request_bytes'] for t in model.trace),
                  trace=model.trace, live_provider_calls=0)
    return result


def verified_boundary():
    started = time.perf_counter()
    model = RecordedFake({})
    with tempfile.TemporaryDirectory(prefix='issue25-verified-') as parent, ExitStack() as stack:
        fake_provider(stack, model)
        root = Path(parent) / 'fresh'
        initialize_fixture_workspace(root, clock=lambda: NOW)
        w = Workspace(root, real_clock=lambda: NOW)
        cid = w.create_conversation('chat', 'Verified offline journey')['id']
        w.message_conversation(cid, 'brief', 0, FIXTURE_MESSAGE)
        w.start_preparation(cid, 'prepare', 1, True, False, True)
        state = select_and_finish(w, cid, advance(w, cid))
        require(state['preparations'][-1]['status'] == 'review_ready', 'Verified fixture did not reach review')
        require(not model.trace, 'Verified fixture dispatched a model call')
        paid = w.create_conversation('paused', 'Paid inference stays paused')['id']
        w.message_conversation(paid, 'paid-brief', 0, 'Prepare a £437 UK inventory campaign.')
        planned = w.plan_conversation(paid, 'paid-plan', 1)
        run = planned['current_plan']['run_id']
        app = w._conversation_app(with_model=True)
        require(app.worker.drain('local-conversations', run_id=run) == 0, 'Verified paid worker executed')
        require(app.tasks.inspect('local-conversations', run)['admission']['status'] == 'paused', 'Paid run lost its pause')
        from acquisition.bootstrap import build, build_workspace_checkpoint
        checkpoint = build_workspace_checkpoint()
        bundle, restored = Path(parent) / 'bundle', Path(parent) / 'restored'
        manifest = checkpoint.create(root, bundle)
        checkpoint.restore(bundle, restored, manifest['checkpoint_id'])
        from test_workspace_checkpoint import tree
        before = tree(restored)
        inspection = build(restored / 'conversations.sqlite', clock=lambda: NOW)
        inspection.tasks.inspect('local-conversations', run)
        try:
            Workspace(restored, real_clock=lambda: NOW).message_conversation(cid, 'forbidden', 1, 'Use £700 instead.')
        except Conflict:
            pass
        else:
            raise AssertionError('Restored workspace accepted a write')
        require(tree(restored) == before, 'Inspection changed restored bytes')
        return {'id': 'verified-fixture-and-restore', 'passed': True, 'outcome_category': 'boundary_pass', 'live_provider_calls': 0,
                'fake_provider_calls': len(model.trace), 'restored_bytes_unchanged': True,
                'elapsed_seconds': round(time.perf_counter() - started, 3)}


def uncertain_restart():
    started = time.perf_counter()
    model = RecordedFake({'budget_pence': 55300, 'copy_mode': 'fixture'})
    model.uncertain = True
    with tempfile.TemporaryDirectory(prefix='issue25-uncertain-') as root, ExitStack() as stack:
        fake_provider(stack, model)
        w = Workspace(root, real_clock=lambda: NOW)
        cid = w.create_conversation('chat', 'Unknown planner response')['id']
        w.message_conversation(cid, 'brief', 0, 'Prepare a £553 UK contractor postal response experiment.')
        w.start_preparation(cid, 'prepare', 1, False, False, True)
        state = advance(w, cid)
        require(state['preparations'][-1]['status'] == 'uncertain', 'Unknown response was not exposed as uncertain')
        require(not state['campaigns'] and len(model.trace) == 1, 'Uncertain inference continued or retried')
        used = state['execution']['used']
        w.stop_execution(cid, 'stop', 1)
        w = Workspace(root, real_clock=lambda: NOW)
        w.start_preparation(cid, 'prepare', 1, False, False, True)
        w.recover_execution()
        w.advance_preparations()
        current = w.conversation(cid)
        require(len(model.trace) == 1 and current['execution']['used'] == used, 'Restart repeated uncertain inference')
        require(current['execution']['counts']['uncertain'] == 1, 'Stopping lost unresolved accounting')
        require(not current['campaigns'], 'A cancelled uncertain attempt created a campaign')
        return {'id': 'uncertain-stop-restart', 'passed': True, 'outcome_category': 'boundary_pass', 'live_provider_calls': 0,
                'fake_provider_calls': 1, 'replay_added_calls': 0, 'used': used,
                'elapsed_seconds': round(time.perf_counter() - started, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if IMPORTED_SOURCE_STATE is None:
        parser.error('Run the evaluation from an attributable Git checkout')
    corpus_path = ROOT / 'config/conversation-offline-evaluation-v1.json'
    corpus_bytes = corpus_path.read_bytes()
    corpus = json.loads(corpus_bytes)
    before = IMPORTED_SOURCE_STATE
    results = []
    for case in corpus['cases']:
        row = run_case(case)
        results.append(row)
        print(row['id'] + ': ' + ('PASS' if row['passed'] else 'FAIL') + (' ' + row['error'] if row.get('error') else ''), flush=True)
    for identity, run in [('verified-fixture-and-restore', verified_boundary), ('uncertain-stop-restart', uncertain_restart)]:
        try:
            boundary = run()
        except Exception as error:
            boundary = {'id': identity, 'passed': False, 'outcome_category': 'journey_failure' if isinstance(error, AssertionError) else 'infrastructure_failure',
                        'error': type(error).__name__ + ': ' + str(error)}
        results.append(boundary)
        print(boundary['id'] + ': ' + ('PASS' if boundary['passed'] else 'FAIL') + (' ' + boundary['error'] if boundary.get('error') else ''), flush=True)
    after = source_state()
    stable = before['files_sha256'] == after['files_sha256'] and before['head_commit'] == after['head_commit']
    changed = {p: {'before': before['files'].get(p), 'after': after['files'].get(p)}
               for p in before['files'].keys() | after['files'].keys() if before['files'].get(p) != after['files'].get(p)}
    report = {'schema': 'conversation-offline-evaluation-result/v2', 'base_commit': before['head_commit'],
              'evaluated_commit': before['head_commit'] if not before['worktree_dirty'] and stable else None,
              'source_state': before, 'source_state_after': {k: v for k, v in after.items() if k != 'files'},
              'changed_source_files': changed, 'source_state_stable': stable,
              'evaluated_at': datetime.now(timezone.utc).isoformat(),
              'corpus_sha256': hashlib.sha256(corpus_bytes).hexdigest(),
              'runner_sha256': before['files']['scripts/evaluate_conversational_agent.py']['sha256'],
              'limits': ['Scripted responses do not measure model intent recognition or editorial quality.',
                         'Latency is local harness wall time, not provider or production latency.',
                         'No real provider price or customer-performance measurement.',
                         'Paid inference remains paused; fake-model journeys use disposable test stores.'],
              'results': results, 'passed': sum(r['passed'] for r in results), 'total': len(results),
              'false_acceptances': sum(r.get('false_acceptance', False) for r in results),
              'false_rejections': sum(r.get('false_rejection', False) for r in results),
              'planner_failures': sum(r.get('outcome_category') == 'planner_failure' for r in results),
              'infrastructure_failures': sum(r.get('outcome_category') == 'infrastructure_failure' for r in results),
              'live_provider_calls': 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{report['passed']}/{report['total']} passed; {report['false_acceptances']} false acceptances; 0 live calls", flush=True)
    print(f"{report['planner_failures']} planner failures; {report['infrastructure_failures']} infrastructure failures; source stable: {stable}", flush=True)
    if not stable:
        print('Source inputs changed during import or evaluation; this evidence is invalid.', flush=True)
    return int(not stable or report['passed'] != report['total'])


if __name__ == '__main__':
    raise SystemExit(main())
