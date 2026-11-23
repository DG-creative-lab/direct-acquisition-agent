"""Partition backend discovery, keeping fixtures whole unless explicitly opted in."""

import argparse
import json
import os
import time
import unittest


# Case + class setup costs from successful Actions run 45129497433 (3f057dc).
# Weights guide allocation, not performance assertions. All cases still run.
MODULE_SECONDS = {
    'test_admission_contracts': 0.006,
    'test_admission_entrypoints': 14.284,
    'test_admission_workflow_coverage': 20.78,
    'test_agent_assets': 3.836,
    'test_architecture': 21.74,
    'test_atomic_admissions': 4.495,
    'test_audience_catalogue': 0.247,
    'test_audience_strategies': 2.33,
    'test_boundary_evaluation': 5.831,
    'test_budget_clarification': 31.335,
    'test_channel_content': 16.84,
    'test_checkpoint_reconciliation': 5.168,
    'test_ci_tools': 0.459,
    'test_contacts': 3.462,
    'test_conversation_actions': 35.693,
    'test_conversation_audiences': 44.294,
    'test_conversation_campaign': 16.758,
    'test_conversation_handoff': 6.777,
    'test_conversation_learning': 4.983,
    'test_conversational_copy_revision': 33.026,
    'test_conversational_evaluation': 1.308,
    'test_conversations': 2.388,
    'test_copy_revisions': 36.138,
    'test_cutover_review_regressions': 3.285,
    'test_database_initialization': 0.937,
    'test_domain': 0.046,
    'test_execution_authority_model': 4.986,
    'test_execution_controls': 51.488,
    'test_failure_boundaries': 0.344,
    'test_fixture_activation': 39.877,
    'test_followup_hypotheses': 0.648,
    'test_followups': 32.779,
    'test_grounding': 1.388,
    'test_hosting_probe': 1.633,
    'test_knowledge': 0.167,
    'test_learning': 23.822,
    'test_learning_cli': 2.091,
    'test_legacy_action_replay': 10.044,
    'test_legacy_followup_scope': 16.492,
    'test_legacy_inventory': 16.603,
    'test_legacy_migration': 9.926,
    'test_model_copy': 0.924,
    'test_offline_journey_evaluation': 0.026,
    'test_openrouter_catalogue': 0.001,
    'test_persistence': 2.658,
    'test_planning_request_scope': 1.456,
    'test_pre_entrypoint_recovery': 9.124,
    'test_preparations': 23.695,
    'test_profiles': 1.465,
    'test_recipient_context': 4.364,
    'test_recovery_commands': 0.003,
    'test_requested_scope': 7.384,
    'test_review_cli': 1.755,
    'test_review_regressions': 0.953,
    'test_reviews': 12.793,
    'test_sequence_journeys': 350.861,
    'test_sequence_reviews': 130.545,
    'test_sequences': 164.715,
    'test_turso_storage': 10.638,
    'test_typed_chat_routing': 17.492,
    'test_validation_reports': 2.452,
    'test_workspace': 22.66,
    'test_workspace_authority': 14.139,
    'test_workspace_checkpoint': 12.832,
    'test_workspace_composition': 1.155,
    'test_workspace_control': 0.201,
    'test_workspace_projection': 6.334,
}
# Only this expensive class opts into case partitioning. Each case copies a
# closed template into its own temporary SQLite root. Each runner still builds
# the real class fixture once; account for that repeated cost explicitly.
CASE_SPLIT_CLASSES = {
    'test_sequence_journeys.SequenceJourneyTests': 15.108,
}
CLASS_SECONDS = {
    'test_sequence_journeys.SequenceIntentTests': 0.036,
    'test_sequence_journeys.SequenceJourneyTests': 347.969,
    'test_sequence_journeys.SequenceRoutingTests': 2.855,
}
CASE_SECONDS = {
    'test_sequence_journeys.SequenceJourneyTests.test_atomic_message_admission_consent_and_exact_replay': 0.076,
    'test_sequence_journeys.SequenceJourneyTests.test_both_companies_one_confirmation_completes_and_reads_never_repeat_effects': 117.524,
    'test_sequence_journeys.SequenceJourneyTests.test_earlier_detached_run_rechecks_source_before_resume_reservation_and_publication': 1.858,
    'test_sequence_journeys.SequenceJourneyTests.test_frozen_journey_finds_receipts_after_task_origin_index_and_account_loss': 0.087,
    'test_sequence_journeys.SequenceJourneyTests.test_interruption_or_unknown_call_keeps_original_usage_without_publication': 7.561,
    'test_sequence_journeys.SequenceJourneyTests.test_lost_acknowledgement_restart_uses_original_approval_and_simulation_commands': 5.841,
    'test_sequence_journeys.SequenceJourneyTests.test_material_edit_obsoletes_ready_approval_and_prevents_detached_native_work': 1.528,
    'test_sequence_journeys.SequenceJourneyTests.test_paused_journey_channel_binds_original_owner_and_rechecks_stop_at_commit': 3.931,
    'test_sequence_journeys.SequenceJourneyTests.test_reassessment_keeps_frozen_source_ownership_and_standalone_sources_remain_usable': 1.023,
    'test_sequence_journeys.SequenceJourneyTests.test_reply_pauses_only_its_account_and_recovers_original_observation': 79.891,
    'test_sequence_journeys.SequenceJourneyTests.test_schema_22_upgrade_preserves_exact_history_and_cutoff': 0.045,
    'test_sequence_journeys.SequenceJourneyTests.test_standalone_admission_precedes_later_journey_without_losing_its_run': 39.178,
    'test_sequence_journeys.SequenceJourneyTests.test_stop_after_confirmation_and_disabled_reviewer_cannot_dispatch': 1.111,
    'test_sequence_journeys.SequenceJourneyTests.test_unfinished_call_only_holds_its_own_followup_across_restart': 72.385,
    'test_sequence_journeys.SequenceJourneyTests.test_verified_admissions_remain_paused_before_message_or_task_commit': 0.057,
    'test_sequence_journeys.SequenceJourneyTests.test_workspace_routes_questions_without_revision_or_model_changes': 0.764,
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
        discovered_cases = list(cases(suite))
        if not discovered_cases:
            continue
        module = type(discovered_cases[0]).__module__
        class_names = [f'{type(test).__module__}.{type(test).__qualname__}'
                       for test in discovered_cases]
        if not any(name in CASE_SPLIT_CLASSES for name in class_names):
            weight = MODULE_SECONDS.get(module, len(discovered_cases) * SECONDS_PER_CASE)
            weighted.append((weight, (index, 0), suite, None))
            continue
        # Preserve discovery order and one setup/teardown lifecycle for each
        # class on a runner. Other classes in the module remain whole.
        position = 0
        while position < len(discovered_cases):
            name = class_names[position]
            end = position + 1
            while end < len(discovered_cases) and class_names[end] == name:
                end += 1
            if name in CASE_SPLIT_CLASSES:
                for offset in range(position, end):
                    test = discovered_cases[offset]
                    weight = CASE_SECONDS.get(unittest.TestCase.id(test), SECONDS_PER_CASE)
                    weighted.append((weight, (index, offset), unittest.TestSuite([test]), name))
            else:
                group = unittest.TestSuite(discovered_cases[position:end])
                weight = CLASS_SECONDS.get(name, (end - position) * SECONDS_PER_CASE)
                weighted.append((weight, (index, position), group, None))
            position = end

    groups = [[] for _ in range(shards)]
    weights = [0.0] * shards
    fixtures = [set() for _ in range(shards)]
    for weight, index, suite, fixture in sorted(weighted, key=lambda entry: (-entry[0], entry[1])):
        def cost(group):
            return weight + (CASE_SPLIT_CLASSES[fixture]
                             if fixture and fixture not in fixtures[group] else 0)
        group = min(range(shards), key=lambda group: weights[group] + cost(group))
        groups[group].append((index, suite))
        weights[group] += cost(group)
        if fixture:
            fixtures[group].add(fixture)
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
