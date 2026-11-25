"""CI sharding must retain coverage and mutation kills must reach a test assertion."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.browser_ci_scope import changed_paths, select_suite
from scripts.check_failure_mutations import CASES, partition
from scripts.run_backend_shard import CASE_SPLIT_CLASSES, TimingResult, cases, split_suite


class CIToolTests(unittest.TestCase):
    def test_mutation_partition_covers_catalogue_exactly_once(self):
        groups = partition(CASES, 4)
        self.assertTrue(all(groups))
        self.assertCountEqual([case[0] for group in groups for case in group],
                              [case[0] for case in CASES])
        self.assertEqual(len({case[0] for case in CASES}), len(CASES))

    def test_backend_shards_preserve_discovery(self):
        loader = unittest.TestLoader()
        discovered = loader.discover('tests')
        self.assertFalse(loader.errors, loader.errors)
        expected = [test.id() for test in cases(discovered)]
        for shards in (2, 4):
            with self.subTest(shards=shards):
                groups, _ = split_suite(discovered, shards)
                self.assertEqual(len(groups), shards)
                self.assertTrue(all(group.countTestCases() for group in groups))
                self.assertCountEqual([test.id() for group in groups for test in cases(group)], expected)
                owners = {}
                class_owners = {}
                split_owners = set()
                for index, group in enumerate(groups):
                    order = []
                    for test in cases(group):
                        module = type(test).__module__
                        name = f'{module}.{type(test).__qualname__}'
                        order.append(name)
                        if name in CASE_SPLIT_CLASSES:
                            split_owners.add(index)
                        else:
                            self.assertEqual(class_owners.setdefault(name, index), index, name)
                        if module != 'test_sequence_journeys':
                            self.assertEqual(owners.setdefault(module, index), index, module)
                    # A runner must never leave a class and enter it again,
                    # which would reconstruct and tear down its template twice.
                    runs = [name for pos, name in enumerate(order) if pos == 0 or name != order[pos - 1]]
                    self.assertEqual(len(runs), len(set(runs)))
                self.assertGreater(len(split_owners), 1)

    def test_case_partition_charges_one_fixture_setup_per_runner(self):
        sample = type('Examples', (unittest.TestCase,), {
            '__module__': 'weighted_fixture',
            'test_a': lambda self: None, 'test_b': lambda self: None, 'test_c': lambda self: None,
        })
        examples = [sample(name) for name in ('test_a', 'test_b', 'test_c')]
        name = 'weighted_fixture.Examples'
        with patch.dict('scripts.run_backend_shard.CASE_SPLIT_CLASSES', {name: 5.0}, clear=True), \
             patch.dict('scripts.run_backend_shard.CASE_SECONDS', {test.id(): 10.0 for test in examples}, clear=True):
            groups, weights = split_suite(unittest.TestSuite([unittest.TestSuite(examples)]), 2)
        self.assertEqual(sum(weights), 40.0)  # Three 10s cases and two 5s class setups.
        self.assertTrue(all(group.countTestCases() for group in groups))
        self.assertCountEqual([test.id() for group in groups for test in cases(group)],
                              [test.id() for test in examples])

    def test_browser_scope_keeps_full_coverage_for_product_and_unknown_changes(self):
        # This contract is independent of the selector's own path lists: deleting
        # an important path there must not silently delete its expected coverage.
        browser_changes = (
            'frontend/tests/new-regression.spec.mjs',
            'frontend/tests/offline-journey.spec.mjs',
            'frontend/tests/fixtures/shared.mjs',
            'frontend/scripts/offline-journey.mjs',
            'frontend/playwright.config.ts', 'frontend/browser-smoke.json',
            'scripts/browser_ci_scope.py', 'scripts/offline_journey_fixture.py',
            '.github/workflows/ci.yml',
            'tests/test_preparations.py', 'tests/test_conversations.py',
            'tests/test_conversation_actions.py', 'tests/test_conversational_copy_revision.py',
            'tests/test_copy_revisions.py', 'tests/test_model_copy.py',
            'tests/prepared_workspace_fixture.py',
            'tests/browser_workspace.py',
        )
        for path in browser_changes + (
            'frontend/src/App.tsx', 'frontend/src/brand/tokens.css', 'frontend/public/logo.svg',
            'frontend/index.html', 'frontend/package.json', 'frontend/pnpm-lock.yaml',
            'frontend/vite.config.ts', 'frontend/tsconfig.json', 'config/product.json',
            'src/acquisition/adapters/http/workspace_server.py',
            'src/acquisition/adapters/sqlite/tasks.py', 'src/acquisition/adapters/turso/transport.py',
            'src/acquisition/application/workspace/service.py', 'src/acquisition/runtime/service.py',
            'src/acquisition/workflows/sequence_journeys.py', 'src/acquisition/bootstrap.py',
            'src/acquisition/entrypoints/workspace.py', 'src/acquisition/workspace_server.py',
            'src/acquisition/conversations/checkpoint_recovery.py',
            'src/acquisition/new_boundary.py', 'pyproject.toml',
        ):
            with self.subTest(path=path):
                self.assertEqual(select_suite('pull_request', [], [path])[0], 'full')
        self.assertEqual(select_suite('pull_request', [], None)[0], 'full')
        self.assertEqual(select_suite('pull_request', ['skip-browser-checks'], None)[0], 'full')
        for path in browser_changes:
            with self.subTest(path=path, label='existing skip label'):
                self.assertEqual(select_suite('pull_request', ['skip-browser-checks'], [path])[0], 'full')
        self.assertEqual(select_suite('pull_request', [], ['README.md', browser_changes[0]])[0], 'full')
        self.assertIsNone(changed_paths('not-a-commit'))
        self.assertEqual(select_suite('pull_request', [], ['README.md', 'tests/test_ci_tools.py'])[0], 'smoke')
        self.assertEqual(select_suite('push', ['skip-browser-checks'], ['README.md'])[0], 'full')
        self.assertEqual(select_suite('pull_request', ['skip-browser-checks'], ['frontend/src/App.tsx'])[0], 'skip')
        self.assertEqual(select_suite('pull_request', ['skip-browser-checks', 'FULL-BROWSER-CHECKS'], [])[0], 'full')

    def test_browser_scope_cli_falls_back_to_full_for_missing_event(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'output'
            subprocess.run([sys.executable, str(root / 'scripts/browser_ci_scope.py')],
                env=dict(os.environ, GITHUB_EVENT_NAME='pull_request',
                         GITHUB_EVENT_PATH=str(Path(directory) / 'missing'), GITHUB_OUTPUT=str(output)),
                check=True, capture_output=True, text=True)
            self.assertIn('suite=full\n', output.read_text())

    def test_product_rename_cannot_hide_the_old_path_from_browser_scope(self):
        script_root = Path(__file__).resolve().parents[1]
        for original in ('frontend/src/example.ts', 'frontend/tests/regression.spec.mjs'):
            with self.subTest(original=original), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                def git(*args):
                    return subprocess.check_output(['git', '-C', directory, *args], stderr=subprocess.DEVNULL, text=True).strip()
                git('init')
                product = root / original
                product.parent.mkdir(parents=True)
                product.write_text('export const example = true;\n')
                git('add', '.')
                git('-c', 'user.name=CI fixture', '-c', 'user.email=ci@example.invalid', 'commit', '-m', 'Initial fixture')
                base = git('rev-parse', 'HEAD')
                moved = root / 'docs/moved-example.txt'
                moved.parent.mkdir()
                product.rename(moved)
                git('add', '-A')
                git('-c', 'user.name=CI fixture', '-c', 'user.email=ci@example.invalid', 'commit', '-m', 'Move fixture')
                code = 'from scripts.browser_ci_scope import changed_paths; import json; print(json.dumps(changed_paths("' + base + '")))'
                result = subprocess.check_output([sys.executable, '-c', code], cwd=root,
                    env=dict(os.environ, PYTHONPATH=str(script_root)), text=True)
                paths = json.loads(result)
                self.assertIn(original, paths)
                self.assertIn('docs/moved-example.txt', paths)
                self.assertEqual(select_suite('pull_request', [], paths)[0], 'full')

    def test_timing_preserves_test_identity_when_fixture_assigns_id(self):
        class UsesSubjectId(unittest.TestCase):
            def setUp(self):
                self.id = 'fixture-subject'

            def runTest(self):
                self.assertEqual(self.id, 'fixture-subject')

        case = UsesSubjectId()
        expected = unittest.TestCase.id(case)
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=TimingResult).run(case)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual([entry['id'] for entry in result.timings], [expected])
        self.assertGreaterEqual(result.timings[0]['seconds'], 0)

    def test_mutation_target_rejects_fixture_and_harness_failures(self):
        root = Path(__file__).resolve().parents[1]
        source = '''import unittest
class Examples(unittest.TestCase):
    def setUp(self):
        if self._testMethodName == "test_setup": raise AssertionError("fixture")
        if self._testMethodName == "test_error": raise RuntimeError("fixture")
    def tearDown(self):
        if self._testMethodName == "test_teardown": raise AssertionError("fixture")
    def test_setup(self): pass
    def test_teardown(self): pass
    def test_error(self): pass
    def test_killed(self): self.fail("behavior")
    def test_body_error(self): raise RuntimeError("behavior")
    def test_subtest_error(self):
        with self.subTest(case=1): raise RuntimeError("behavior")
    def test_survived(self): pass
'''
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'examples.py').write_text(source)
            env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(root), directory)))
            for target, expected in [('test_setup', 1), ('test_teardown', 1), ('test_error', 1),
                                     ('test_killed', 0), ('test_body_error', 1), ('test_subtest_error', 1),
                                     ('test_survived', 1),
                                     ('missing', 1)]:
                with self.subTest(target=target):
                    result = subprocess.run([sys.executable, '-m', 'scripts.mutation_target',
                                             'examples.Examples.' + target],
                                            cwd=root, env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, expected, result.stderr)
