"""Evaluation conclusions require meaningful outcomes and attributable inputs."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import evaluate_conversational_agent as evaluation


def state(status, outcome=None, response='', error=None):
    return {'preparations': [{'status': status}], 'campaigns': [],
            'current_plan': {'status': 'failed' if status == 'failed' else 'succeeded', 'error': error,
                             'result': {'outcome': outcome, 'question': response, 'unsupported_reason': response} if outcome else None}}


class ConversationalEvaluationTests(unittest.TestCase):
    def case(self, identity):
        corpus = json.loads((evaluation.ROOT / 'config/conversation-offline-evaluation-v1.json').read_text())
        return next(c for c in corpus['cases'] if c['id'] == identity)

    def test_terminal_failures_never_satisfy_negative_outcomes(self):
        expected = self.case('unsupported-email')['expected']
        for status in ('failed', 'blocked', 'cancelled', 'stale', 'uncertain', 'needs_consent', 'needs_input'):
            with self.subTest(status=status):
                self.assertFalse(evaluation.assess_outcome(expected, state(status))['passed'])
        planner = evaluation.assess_outcome(expected, state('failed', error={'error_code': 'ModelError'}))
        provider = evaluation.assess_outcome(expected, state('failed', error={'error_code': 'ModelError', 'provider_error': 'provider_http_401'}))
        self.assertEqual(planner['outcome_category'], 'planner_failure')
        self.assertEqual(provider['outcome_category'], 'infrastructure_failure')
        self.assertFalse(planner['false_rejection'])

    def test_clarification_and_unsupported_need_the_expected_outcome_and_reason(self):
        expected = self.case('missing-budget')['expected']
        self.assertTrue(evaluation.assess_outcome(expected, state('needs_input', 'clarification', 'What total budget should I use?'))['passed'])
        for outcome, response in [('clarification', ''), ('clarification', 'Which font?'), ('unsupported', 'No budget')]:
            with self.subTest(outcome=outcome, response=response):
                self.assertFalse(evaluation.assess_outcome(expected, state('needs_input', outcome, response))['passed'])
        expected = self.case('unsupported-email')['expected']
        self.assertTrue(evaluation.assess_outcome(expected, state('needs_input', 'unsupported', 'Email is not supported.'))['passed'])
        self.assertFalse(evaluation.assess_outcome(expected, state('needs_input', 'clarification', 'Which email list?'))['passed'])
        dirty = state('needs_input', 'unsupported', 'Email is not supported.')
        dirty['campaigns'] = [{'session_id': 'unexpected-artifact'}]
        self.assertFalse(evaluation.assess_outcome(expected, dirty)['passed'])

    def test_unrelated_preparation_failure_does_not_pass_a_negative_case(self):
        original = evaluation.Workspace.start_preparation

        def fail_before_dispatch(workspace, cid, *args, **kwargs):
            original(workspace, cid, *args, **kwargs)
            row = workspace.preparations.store.listing('local-conversations')[0]
            workspace.preparations.store.update('local-conversations', row, 'failed', 'Injected infrastructure failure')
            return workspace.conversation(cid)

        with patch.object(evaluation.Workspace, 'start_preparation', fail_before_dispatch):
            result = evaluation.run_case(self.case('unsupported-email'))
        self.assertFalse(result['passed'])
        self.assertEqual(result['fake_provider_calls'], 0)
        self.assertEqual(result['outcome_category'], 'infrastructure_failure')

    def test_real_budget_clarification_and_invalid_planner_output_are_distinct(self):
        missing = evaluation.run_case(self.case('missing-budget'))
        ambiguous = evaluation.run_case(self.case('ambiguous-budget'))
        self.assertTrue(missing['passed'])
        self.assertEqual(missing['outcome_category'], 'expected_clarification')
        self.assertTrue(ambiguous['passed'])
        self.assertEqual(ambiguous['outcome_category'], 'expected_clarification')
        self.assertEqual(ambiguous['fake_provider_calls'], 0)
        # Preserve the old failure oracle with an actually invalid planner,
        # rather than treating every negative terminal status as success.
        invalid = self.case('missing-budget')
        invalid['id'] = 'injected-invalid-planner'
        invalid['scripted_brief'] = {'budget_pence': 60000, 'segments': ['contractors'], 'copy_mode': 'fixture'}
        failed = evaluation.run_case(invalid)
        self.assertFalse(failed['passed'])
        self.assertEqual(failed['outcome_category'], 'planner_failure')
        self.assertEqual(failed['fake_provider_calls'], 2)

    def repository(self, root):
        for folder in ('src', 'tests', 'config', 'scripts'):
            (root / folder).mkdir()
        for name in ('src/domain.py', 'tests/provider.py', 'config/guidance.json', 'scripts/evaluate_conversational_agent.py'):
            (root / name).write_text('original\n')
        for args in [('init', '-q'), ('add', '.'), ('-c', 'user.name=Offline test', '-c', 'user.email=offline@example.invalid', 'commit', '-qm', 'Fixture')]:
            subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)

    def test_source_and_fixture_changes_cannot_hide_behind_the_same_head(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.repository(root)
            baseline = evaluation.source_state(root)
            self.assertFalse(baseline['worktree_dirty'])
            for name in ('src/domain.py', 'tests/provider.py', 'config/guidance.json'):
                with self.subTest(path=name):
                    path = root / name
                    path.write_text('changed\n')
                    changed = evaluation.source_state(root)
                    self.assertEqual(changed['head_commit'], baseline['head_commit'])
                    self.assertNotEqual(changed['files_sha256'], baseline['files_sha256'])
                    self.assertNotEqual(changed['files'][name], baseline['files'][name])
                    self.assertEqual(changed['files'][name]['sha256'], hashlib.sha256(b'changed\n').hexdigest())
                    self.assertTrue(changed['worktree_dirty'])
                    path.write_text('original\n')
            subprocess.run(['git', 'update-index', '--assume-unchanged', 'src/domain.py'], cwd=root, check=True)
            (root / 'src/domain.py').write_text('hidden change\n')
            hidden = evaluation.source_state(root)
            self.assertEqual(hidden['git_status'], [])
            self.assertTrue(hidden['worktree_dirty'])
            self.assertIn('src/domain.py', hidden['changes_to_head'])
            (root / 'src/domain.py').write_text('original\n')
            subprocess.run(['git', 'update-index', '--no-assume-unchanged', 'src/domain.py'], cwd=root, check=True)
            added = root / 'tests/new_provider.py'
            added.write_text('new fixture\n')
            self.assertIn('tests/new_provider.py', evaluation.source_state(root)['files'])
            added.unlink()
            (root / 'src/domain.py').unlink()
            self.assertIsNone(evaluation.source_state(root)['files']['src/domain.py']['sha256'])

    def test_changed_source_during_execution_invalidates_an_otherwise_passing_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.repository(root)
            before = evaluation.source_state(root)
            (root / 'src/domain.py').write_text('changed during evaluation\n')
            after = evaluation.source_state(root)
            output = root / 'result.json'
            passed = lambda c: {'id': c['id'], 'passed': True}
            with patch.object(evaluation, 'IMPORTED_SOURCE_STATE', before), patch.object(evaluation, 'source_state', return_value=after), \
                    patch.object(evaluation, 'run_case', side_effect=passed), \
                    patch.object(evaluation, 'verified_boundary', return_value={'id': 'verified', 'passed': True}), \
                    patch.object(evaluation, 'uncertain_restart', return_value={'id': 'uncertain', 'passed': True}), \
                    patch.object(sys, 'argv', ['evaluate', '--output', str(output)]), redirect_stdout(io.StringIO()):
                code = evaluation.main()
            report = json.loads(output.read_text())
            self.assertEqual(report['passed'], report['total'])
            self.assertEqual(code, 1)
            self.assertFalse(report['source_state_stable'])
            self.assertIn('src/domain.py', report['changed_source_files'])
            self.assertEqual(report['source_state']['head_commit'], before['head_commit'])
            self.assertIsNone(report['evaluated_commit'])
            with patch.object(evaluation, 'IMPORTED_SOURCE_STATE', after), patch.object(evaluation, 'source_state', return_value=after), \
                    patch.object(evaluation, 'run_case', side_effect=passed), \
                    patch.object(evaluation, 'verified_boundary', return_value={'id': 'verified', 'passed': True}), \
                    patch.object(evaluation, 'uncertain_restart', return_value={'id': 'uncertain', 'passed': True}), \
                    patch.object(sys, 'argv', ['evaluate', '--output', str(output)]), redirect_stdout(io.StringIO()):
                self.assertEqual(evaluation.main(), 0)
            dirty_report = json.loads(output.read_text())
            self.assertTrue(dirty_report['source_state_stable'])
            self.assertTrue(dirty_report['source_state']['worktree_dirty'])
            self.assertIsNone(dirty_report['evaluated_commit'])
            self.assertEqual(dirty_report['base_commit'], before['head_commit'])
            self.assertEqual(dirty_report['source_state']['files']['src/domain.py'], after['files']['src/domain.py'])
