"""CI sharding must retain coverage and mutation kills must reach a test assertion."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.check_failure_mutations import CASES, partition
from scripts.run_backend_shard import cases, split_suite


class CIToolTests(unittest.TestCase):
    def test_mutation_partition_covers_catalogue_exactly_once(self):
        groups = partition(CASES, 4)
        self.assertTrue(all(groups))
        self.assertCountEqual([case[0] for group in groups for case in group],
                              [case[0] for case in CASES])
        self.assertEqual(len({case[0] for case in CASES}), len(CASES))

    def test_backend_shards_preserve_discovery(self):
        discovered = unittest.defaultTestLoader.discover('tests')
        expected = [test.id() for test in cases(discovered)]
        groups, _ = split_suite(discovered)
        self.assertTrue(all(group.countTestCases() for group in groups))
        self.assertCountEqual([test.id() for group in groups for test in cases(group)], expected)

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
                                     ('test_killed', 0), ('test_body_error', 0), ('test_subtest_error', 0),
                                     ('test_survived', 1),
                                     ('missing', 1)]:
                with self.subTest(target=target):
                    result = subprocess.run([sys.executable, '-m', 'scripts.mutation_target',
                                             'examples.Examples.' + target],
                                            cwd=root, env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, expected, result.stderr)
