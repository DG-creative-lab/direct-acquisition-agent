"""Run a module-level shard of the standard backend discovery suite."""

import argparse
import json
import os
import time
import unittest


# Module case + class setup durations on Python 3.14 in main Actions run
# 45011234477 (5e37b25, 22 November 2026). Retain all measured modules so
# expensive new workflows cannot disappear into a cheap per-case fallback.
# These guide partitioning, not performance assertions; new modules use fallback.
MODULE_SECONDS = {
    'test_admission_contracts': 0.005,
    'test_admission_entrypoints': 10.131,
    'test_admission_workflow_coverage': 22.08,
    'test_agent_assets': 2.581,
    'test_architecture': 15.7,
    'test_atomic_admissions': 3.078,
    'test_audience_catalogue': 0.198,
    'test_audience_strategies': 3.684,
    'test_boundary_evaluation': 3.819,
    'test_budget_clarification': 22.078,
    'test_channel_content': 18.24,
    'test_checkpoint_reconciliation': 4.659,
    'test_ci_tools': 0.314,
    'test_contacts': 3.903,
    'test_conversation_actions': 40.763,
    'test_conversation_audiences': 38.584,
    'test_conversation_campaign': 16.161,
    'test_conversation_handoff': 4.634,
    'test_conversation_learning': 5.869,
    'test_conversational_copy_revision': 35.436,
    'test_conversational_evaluation': 1.333,
    'test_conversations': 2.148,
    'test_copy_revisions': 43.453,
    'test_cutover_review_regressions': 2.579,
    'test_database_initialization': 1.14,
    'test_domain': 0.056,
    'test_execution_authority_model': 3.869,
    'test_execution_controls': 82.135,
    'test_failure_boundaries': 0.371,
    'test_fixture_activation': 50.092,
    'test_followup_hypotheses': 1.213,
    'test_followups': 27.717,
    'test_grounding': 1.192,
    'test_hosting_probe': 1.248,
    'test_knowledge': 0.149,
    'test_learning': 23.876,
    'test_learning_cli': 1.727,
    'test_legacy_action_replay': 8.739,
    'test_legacy_followup_scope': 11.054,
    'test_legacy_inventory': 19.23,
    'test_legacy_migration': 6.821,
    'test_model_copy': 0.971,
    'test_offline_journey_evaluation': 0.039,
    'test_openrouter_catalogue': 0.001,
    'test_persistence': 1.818,
    'test_planning_request_scope': 1.245,
    'test_pre_entrypoint_recovery': 9.16,
    'test_preparations': 33.148,
    'test_profiles': 1.717,
    'test_recipient_context': 3.647,
    'test_recovery_commands': 0.002,
    'test_requested_scope': 10.661,
    'test_review_cli': 2.961,
    'test_review_regressions': 0.894,
    'test_reviews': 10.421,
    'test_sequence_journeys': 229.047,
    'test_sequence_reviews': 110.464,
    'test_sequences': 186.317,
    'test_turso_storage': 10.977,
    'test_typed_chat_routing': 20.053,
    'test_validation_reports': 4.087,
    'test_workspace': 24.921,
    'test_workspace_authority': 15.904,
    'test_workspace_checkpoint': 12.707,
    'test_workspace_composition': 1.148,
    'test_workspace_control': 0.131,
    'test_workspace_projection': 9.749,
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
