"""Run one of two module-level shards of the standard backend discovery suite."""

import argparse
import json
import os
import time
import unittest


# Initial sequence/review weights use the local review measurements recorded in
# docs/test-suite-performance.md. Other modules use Actions run 42200956130.
# Refresh from CI timing artifacts; mixed-machine estimates are approximate.
SLOW_MODULE_SECONDS = {
    'test_sequences': 423.0,
    'test_sequence_reviews': 273.0,
    'test_execution_controls': 134.2,
    'test_conversation_actions': 76.9,
    'test_copy_revisions': 72.8,
    'test_conversational_copy_revision': 63.6,
    'test_followups': 36.2,
    'test_conversation_audiences': 32.8,
    'test_learning': 29.1,
    'test_workspace': 24.5,
}
SECONDS_PER_CASE = 0.43


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


def split_suite(discovered):
    weighted = []
    for index, suite in enumerate(discovered):
        count = suite.countTestCases()
        if count:
            module = type(next(cases(suite))).__module__
            weight = SLOW_MODULE_SECONDS.get(module, count * SECONDS_PER_CASE)
            weighted.append((weight, index, suite))

    groups = [[], []]
    weights = [0, 0]
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
        super().startTest(test)

    def stopTest(self, test):
        self.timings.append({'id': test.id(), 'seconds': time.monotonic() - self.started})
        super().stopTest(test)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('shard', type=int, choices=(1, 2))
    args = parser.parse_args()
    loader = unittest.TestLoader()
    discovered = loader.discover('tests')
    if loader.errors:
        parser.exit(1, '\n'.join(loader.errors) + '\n')
    groups, weights = split_suite(discovered)
    if any(not group.countTestCases() for group in groups):
        parser.exit(1, 'Backend discovery must produce two non-empty shards.\n')
    selected = groups[args.shard - 1]
    predicted = weights[args.shard - 1]
    print(f'Backend shard {args.shard}/2: {selected.countTestCases()} tests, estimated {predicted:.1f}s', flush=True)
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
