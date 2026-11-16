"""Run a module-level shard of the standard backend discovery suite."""

import argparse
import json
import os
import time
import unittest


# Module case + class setup durations on Python 3.14 in Actions run
# 43849270917 (PR #96). Source and limits: docs/ci-performance.md.
# These guide partitioning, not performance assertions; new modules use fallback.
MODULE_SECONDS = {
    'test_admission_workflow_coverage': 20.9,
    'test_architecture': 14.6,
    'test_budget_clarification': 26.4,
    'test_channel_content': 15.4,
    'test_conversation_actions': 104.6,
    'test_conversation_audiences': 45.5,
    'test_conversation_campaign': 15.5,
    'test_conversational_copy_revision': 85.6,
    'test_copy_revisions': 69.4,
    'test_execution_controls': 144.6,
    'test_fixture_activation': 58.3,
    'test_followups': 55.0,
    'test_learning': 30.4,
    'test_legacy_inventory': 16.9,
    'test_preparations': 28.3,
    'test_sequence_reviews': 169.2,
    'test_sequences': 283.5,
    'test_typed_chat_routing': 24.6,
    'test_workspace': 29.7,
    'test_workspace_authority': 20.7,
    'test_workspace_checkpoint': 15.9,
}
SECONDS_PER_CASE = 0.43


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


def split_suite(discovered, shards=2):
    weighted = []
    for index, suite in enumerate(discovered):
        count = suite.countTestCases()
        if count:
            module = type(next(cases(suite))).__module__
            weight = MODULE_SECONDS.get(module, count * SECONDS_PER_CASE)
            weighted.append((weight, index, suite))

    groups = [[] for _ in range(shards)]
    weights = [0] * shards
    # Place the largest modules first, then run each group in discovery order.
    for weight, index, suite in sorted(weighted, key=lambda entry: (-entry[0], entry[1])):
        group = min(range(len(groups)), key=weights.__getitem__)
        groups[group].append((index, suite))
        weights[group] += weight
    return [unittest.TestSuite(suite for _, suite in sorted(group)) for group in groups], weights


class TimingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timings = []

    def startTest(self, test):
        self.started = time.monotonic()
        self.test_id = unittest.TestCase.id(test)
        super().startTest(test)

    def stopTest(self, test):
        self.timings.append({'id': self.test_id, 'seconds': time.monotonic() - self.started})
        super().stopTest(test)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('shard', type=int)
    parser.add_argument('--shards', type=int, default=2, choices=(2, 4))
    args = parser.parse_args()
    if not 1 <= args.shard <= args.shards:
        parser.error('shard must be between 1 and --shards')
    loader = unittest.TestLoader()
    discovered = loader.discover('tests')
    if loader.errors:
        parser.exit(1, '\n'.join(loader.errors) + '\n')
    groups, weights = split_suite(discovered, args.shards)
    if any(not group.countTestCases() for group in groups):
        parser.exit(1, 'Backend discovery must produce non-empty shards.\n')
    selected = groups[args.shard - 1]
    predicted = weights[args.shard - 1]
    print(f'Backend shard {args.shard}/{args.shards}: {selected.countTestCases()} tests, estimated {predicted:.1f}s', flush=True)
    fixture_timings = []
    original_setup = unittest.TestSuite._handleClassSetUp

    def timed_setup(suite, test, result):
        previous = getattr(result, '_previousTestClass', None)
        start = time.monotonic()
        try:
            return original_setup(suite, test, result)
        finally:
            if test.__class__ != previous:
                fixture_timings.append({'class': f'{test.__class__.__module__}.{test.__class__.__qualname__}',
                                        'seconds': time.monotonic() - start})

    unittest.TestSuite._handleClassSetUp = timed_setup
    start = time.monotonic()
    try:
        result = unittest.TextTestRunner(verbosity=2, resultclass=TimingResult).run(selected)
    finally:
        unittest.TestSuite._handleClassSetUp = original_setup
    actual = time.monotonic() - start
    print(f'Backend shard {args.shard}: estimated {predicted:.1f}s, actual {actual:.1f}s', flush=True)
    output = os.environ.get('BACKEND_TIMINGS')
    if output:
        with open(output, 'w', encoding='utf-8') as stream:
            json.dump({'shard': args.shard, 'estimated_seconds': predicted,
                       'actual_seconds': actual, 'tests': result.timings,
                       'class_setup': fixture_timings}, stream, indent=2)
            stream.write('\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
