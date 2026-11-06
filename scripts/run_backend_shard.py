"""Run one of two module-level shards of the standard backend discovery suite."""

import argparse
import unittest


# Approximate wall seconds from the Python 3.11 job in Actions run 42200956130.
# Use the average per case for the remaining modules and new tests.
SLOW_MODULE_SECONDS = {
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
    return [unittest.TestSuite(suite for _, suite in sorted(group)) for group in groups]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('shard', type=int, choices=(1, 2))
    args = parser.parse_args()
    loader = unittest.TestLoader()
    discovered = loader.discover('tests')
    if loader.errors:
        parser.exit(1, '\n'.join(loader.errors) + '\n')
    groups = split_suite(discovered)
    if any(not group.countTestCases() for group in groups):
        parser.exit(1, 'Backend discovery must produce two non-empty shards.\n')
    selected = groups[args.shard - 1]
    print(f'Backend shard {args.shard}/2: {selected.countTestCases()} tests', flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(selected)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
