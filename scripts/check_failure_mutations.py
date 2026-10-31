"""Run selected harmful mutations in temporary copies, never in the checkout."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("legacy-copy-envelope-boundary", "creative/grounding.py",
     '        if projected:\n            exchange = editorial_read_exchange(context, pack_id)',
     '        if True:\n            exchange = editorial_read_exchange(context, pack_id)',
     "test_agent_assets.AgentAssetTests.test_recorded_legacy_read_replays_at_exact_original_input_limit"),

    ("copy-full-envelope-preflight", "creative/grounding.py",
     '        self.inference.prepare_request(messages + exchange, [submit])', '        pass',
     "test_agent_assets.AgentAssetTests.test_over_budget_full_copy_envelope_is_rejected_before_read_or_reservation"),
    ("followup-frozen-contexts", "bootstrap.py",
     '        if contexts_override is not None:', '        if False:',
     "test_followups.FollowupTests.test_saved_model_proposal_ignores_changed_or_unavailable_current_assets"),

    ("asset-installed-tool-schema", "reasoning/catalogue.py",
     'if installed_tools is not None and canonical(tools) != canonical(installed_tools):', 'if False:',
     "test_agent_assets.AgentAssetTests.test_changed_wire_schema_and_missing_source_coverage_rejected"),
    ("asset-tool-membership", "reasoning/catalogue.py",
     "not set(s['tool_ids']) <= set(ids)", 'False',
     "test_agent_assets.AgentAssetTests.test_unknown_skill_tool_and_missing_source_fail_before_admission"),

    ("task-lease-expiry", "adapters/sqlite/tasks.py",
     '                or row["token"] != claim.token or row["lease_until"] <= now):',
     '                or row["token"] != claim.token):',
     "test_persistence.PersistenceTests.test_expired_attempt_cannot_commit_before_or_after_reclaim"),
    ("inference-finite-clock", "adapters/sqlite/inference.py",
     '        if not math.isfinite(now):\n            raise LeaseLost("Inference requires a finite clock reading")\n', "",
     "test_nonfinite_clock_cannot_settle_fail_or_admit_a_paid_request"),
    ("inference-budget", "adapters/sqlite/inference.py", "            if count >= limit:", "            if False:",
     "test_concurrent_reservations_cannot_oversubscribe_a_one_call_budget"),
    ("uncertain-call-retry", "adapters/sqlite/inference.py",
     '                    raise ModelError("previous_inference_failed_or_unknown_no_retry")', "                    return None",
     "test_unknown_gateway_failure_is_sanitized_and_never_dispatched_again"),
    ("worker-configuration-preflight", "runtime/application.py",
     'eligible=self.eligible, run_id=run_id)', 'eligible=None, run_id=run_id)',
     "test_review_regressions.ReviewRegressions.test_incompatible_workers_do_not_claim_consume_attempts_or_fail_a_run"),
    ("retired-workflow-admission", "adapters/sqlite/tasks.py",
     '            if any(s.capability in self.retired_capabilities for s in specs):\n                raise ValueError("Retired capabilities cannot be admitted as new runs")\n', '',
     "test_grounding.GroundingTests.test_new_v2_runs_cannot_be_admitted"),
    ("durable-timestamp-validation", "adapters/sqlite/tasks.py",
     '    if type(now) not in {int, float} or not math.isfinite(now):\n        raise ValueError("Durable timestamps must be finite numbers")',
     '    return None',
     "test_review_regressions.ReviewRegressions.test_nonfinite_creation_acknowledgement_and_cancellation_are_atomic"),
    ("migration-write-transaction", "adapters/sqlite/database.py",
     '        with self.transaction() as connection:\n            # Version discovery',
     '        with self.connect() as connection:\n            # Version discovery',
     "test_database_initialization.DatabaseInitializationTests.test_failure_rolls_back_all_migration_steps_and_version_changes"),
    ("approval-expiry", "adapters/sqlite/reviews.py",
     '        if now < approval["at"] or now >= approval["expires_at"]:', '        if False:',
     "test_reviews.ReviewTests.test_expiry_is_enforced_at_the_exact_boundary"),
    ("approval-reviewer-authority", "adapters/sqlite/reviews.py",
     '        if (reviewer is None or not reviewer["enabled"] or "reviewer" not in json.loads(reviewer["roles"])\n                or reviewer["generation"] != approval["actor_generation"]):',
     '        if False:',
     "test_reviews.ReviewTests.test_reviewer_disable_and_reenable_cannot_revive_old_authority"),
    ("approval-current-evidence", "reviews/domain.py",
     'if proposal[key] != current[key]]', 'if False]',
     "test_reviews.ReviewTests.test_evidence_aba_does_not_revive_old_approval"),
    ("approval-atomic-decision", "adapters/sqlite/reviews.py",
     '        with self.database.transaction() as db:\n            now = self._now()\n            reviewer = self._actor',
     '        with self.database.connect() as db:\n            now = self._now()\n            reviewer = self._actor',
     "test_reviews.ReviewTests.test_decision_and_event_are_atomic"),
    ("learning-maturity", "adapters/sqlite/learning.py",
     'complete_through != cohort["window_end"] or now < cohort["window_end"]',
     'complete_through != cohort["window_end"]',
     "test_learning.LearningTests.test_complete_early_responses_still_cannot_finalize_before_maturity"),
    ("learning-population-completeness", "adapters/sqlite/learning.py",
     'groups = counts_for(cohort["members"], outcomes)',
     'groups = counts_for([m for m in cohort["members"] if m["business_id"] in outcomes], outcomes)',
     "test_learning.LearningTests.test_absent_results_and_missing_control_are_pending_not_failures"),
    ("learning-assignment-binding", "learning/outcomes.py",
     'if any(row[k] != member[k] for k in ("business_id", "segment", "arm", "creative_id")):',
     'if False:',
     "test_learning.LearningTests.test_assignment_scope_and_schema_substitution_are_rejected"),
    ("learning-immutable-outcome", "adapters/sqlite/learning.py",
     'if old[0] != canonical(row):', 'if False:',
     "test_learning.LearningTests.test_changed_or_duplicate_outcomes_and_request_reuse_are_rejected"),
    ("learning-atomic-finalization", "adapters/sqlite/learning.py",
     '        with self.database.transaction() as db:\n            now = self._now()\n            require_actor(db, organization, actor, "operator")\n            fingerprint, cached = self._cached(db, organization, actor, request_id, "finalize",',
     '        with self.database.connect() as db:\n            now = self._now()\n            require_actor(db, organization, actor, "operator")\n            fingerprint, cached = self._cached(db, organization, actor, request_id, "finalize",',
     "test_learning.LearningTests.test_finalize_event_failure_rolls_back_counts_and_receipt"),
    ("learning-run-snapshot", "bootstrap.py",
     'learning_memory = self.learning.store.memory_snapshot(organization, segments)',
     'learning_memory = {segment: self.learning.store.memory(organization, segment) for segment in segments}',
     "test_learning.LearningTests.test_model_run_freezes_all_segments_before_concurrent_finalization"),
    ("learning-finalization-replay-event", "adapters/sqlite/learning.py",
     'return self._command(db, organization, request_id, fingerprint, json.loads(row["finalization"]))',
     'return self._record(db, organization, request_id, fingerprint, json.loads(row["finalization"]), actor, now)',
     "test_learning.LearningTests.test_finalization_replay_preserves_original_actor_time_and_single_effect_event"),
    ("workspace-origin", "workspace_server.py",
     'if mutation and self.headers.get("Origin") != "http://" + host:', 'if False:',
     "test_workspace.WorkspaceHttpTests.test_host_token_and_origin_guard_every_mutation"),
    ("workspace-command-identity", "workspace.py",
     'if old["request_hash"] != fingerprint:', 'if False:',
     "test_workspace.WorkspaceTests.test_request_reuse_cannot_advance_clock_or_change_action"),
    ("workspace-artifact-subject", "workspace.py",
     'if review["subject"]["id"] != expected_subject:', 'if False:',
     "test_workspace.WorkspaceTests.test_artifact_download_cannot_substitute_a_newer_subject"),
    ("planner-budget-provenance", "conversations/domain.py",
     '        if evidence is None or budget != evidence["budget_pence"]:', '        if False:',
     "test_conversations.ConversationTests.test_invented_or_stale_budget_and_extra_authority_fail_before_success"),
    ("planner-current-revision", "conversations/application.py",
     '"current": admission["revision"] == snapshot["revision"],', '"current": True,',
     "test_conversations.ConversationTests.test_message_during_inference_keeps_the_late_result_historical"),
    ("conversation-organization-scope", "adapters/sqlite/conversations.py",
     'SELECT * FROM conversations WHERE organization=? AND id=?', 'SELECT * FROM conversations WHERE ? IS NOT NULL AND id=?',
     "test_conversations.ConversationTests.test_message_revision_idempotency_scope_and_history"),
    ("planner-targeted-worker", "workspace.py",
     'app.worker.drain("local-conversations", run_id=run_id)', 'app.worker.drain("local-conversations", run_id=None)',
     "test_workspace.WorkspaceHttpTests.test_replaying_a_completed_plan_does_not_execute_another_conversation"),
    ("planner-unparseable-currency-correction", "conversations/domain.py",
     'if any(not any(marker.start() == match.start() for match in matches) for marker in currency):', 'if False:',
     "test_conversations.ConversationTests.test_later_unparseable_budget_correction_cannot_reuse_an_older_amount"),
    ("planner-relative-budget-adjustment", "conversations/domain.py",
     'if any(relative_amount(content, match) for match in matches):', 'if False:',
     "test_conversations.ConversationTests.test_relative_budget_amount_is_not_accepted_as_a_new_total"),
    ("targeted-worker-expired-recovery", "adapters/sqlite/tasks.py",
     'AND (? IS NULL OR r.id=?)""", (organization, now, run_id, run_id)).fetchall()',
     'AND (? IS NULL OR ? IS NOT NULL)""", (organization, now, run_id, run_id)).fetchall()',
     "test_persistence.PersistenceTests.test_targeted_worker_only_recovers_and_claims_the_requested_run"),
    ("continuous-copy-consent", "conversations/preparation.py",
     'if result["copy_mode"] == "model" and not inputs["allow_model_copy"]:', 'if False:',
     "test_preparations.PreparationTests.test_explicit_copy_consent_cannot_be_expanded_by_replay_or_new_key"),
    ("continuous-unknown-classification", "conversations/preparation.py",
     'uncertain = generation["outcome_uncertain"]', 'uncertain = False',
     "test_preparations.PreparationTests.test_unknown_provider_result_is_terminal_and_never_retried"),
    ("continuous-interrupted-reservation", "conversations/preparation.py",
     'if generation and generation["outcome_uncertain"]:', 'if False:',
     "test_preparations.PreparationTests.test_interrupted_reservation_is_reported_on_restart_before_dispatch"),
    ("planner-reservation-revision", "adapters/sqlite/inference.py",
     'if source is None or source[0] != inputs["revision"]:', 'if False:',
     "test_preparations.PreparationTests.test_edit_before_planner_repair_prevents_a_second_provider_call"),
    ("continuous-stale-uncertainty", "conversations/preparation.py",
     'uncertain = generation and generation["outcome_uncertain"]', 'uncertain = False',
     "test_preparations.PreparationTests.test_stale_briefs_keep_uncertain_planner_and_copy_journals_after_restart"),
    ("continuous-terminal-journal-projection", "workspace.py",
     '"generation": generation})', '"generation": generation if row["status"] == "planning" else None})',
     "test_preparations.PreparationTests.test_stale_briefs_keep_uncertain_planner_and_copy_journals_after_restart"),
    ("continuous-coordinator-admission-order", "conversations/preparation.py",
     '        row = self.store.create(organization, request_id, {"id": preparation_id, "inputs": inputs,',
     '        self.host.admit_preparation_plan(organization, {"inputs": inputs, "plan_request_id": plan_request, "planning_context": context})\n        row = self.store.create(organization, request_id, {"id": preparation_id, "inputs": inputs,',
     "test_preparations.PreparationTests.test_failed_coordinator_write_cannot_leave_a_plan_or_task"),
    ("revision-call-source-fence", "adapters/sqlite/inference.py",
     'require_revision_current(connection, scope.organization, inputs, scope.run_id, now)', 'None',
     "test_copy_revisions.CopyRevisionTests.test_source_changes_during_inference_fence_later_calls_and_publication"),
    ("revision-paid-run-binding", "adapters/sqlite/revision_provenance.py",
     'if run is None or run[0] != receipt["id"]:', 'if False:',
     "test_copy_revisions.CopyRevisionTests.test_another_run_cannot_reuse_a_paid_revision_admission"),
    ("revision-publication-commit-lease", "adapters/sqlite/reviews.py",
     '                now = self._now()\n                require_revision_lease(db, organization, claim, now)',
     '                now = self._now()',
     "test_copy_revisions.CopyRevisionTests.test_publication_rechecks_the_lease_after_validation"),
    ("revision-copy-only-scope", "campaigns/domain.py",
     '        if key != target:', '        if False:',
     "test_copy_revisions.CopyRevisionTests.test_copy_scope_validator_rejects_an_untargeted_letter_change"),
    ("revision-approval-invalidation", "adapters/sqlite/reviews.py",
     '            db.execute("INSERT INTO review_decisions(organization,id,case_id,subject_id,payload) VALUES(?,?,?,?,?)",\n                       (organization, decision["id"], inputs["case_id"], proposal["id"], canonical(decision)))', '',
     "test_copy_revisions.CopyRevisionTests.test_revision_preserves_population_other_letter_product_wording_and_money"),
    ("revision-review-projection-consistency", "workspace.py",
     'if {k: v for k, v in current_review.items() if k != "as_of"} != {k: v for k, v in review.items() if k != "as_of"}:',
     'if current_review["subject"]["id"] != review["subject"]["id"]:',
     "test_copy_revisions.CopyRevisionTests.test_read_packet_cannot_combine_old_approval_with_an_admitted_revision"),
    ("revision-blocked-projection", "workspace.py",
     'if code and row["status"] in {"admitted", "queued", "running"}:', 'if False:',
     "test_copy_revisions.CopyRevisionTests.test_missing_key_blocks_admitted_revision_durably_and_resumes_original_request"),
    ("revision-failure-isolation", "workspace.py",
     '                    self._set_revision_block(scope, row["id"], blocker)', '                    raise',
     "test_copy_revisions.CopyRevisionTests.test_expired_evidence_blocks_one_revision_without_starving_a_later_campaign"),
    ("revision-clear-blocker-before-dispatch", "workspace.py",
     '                        self._set_revision_block(scope, row["id"], None)\n                        configured.worker.tick(scope, run_id=run)',
     '                        configured.worker.tick(scope, run_id=run)\n                        self._set_revision_block(scope, row["id"], None)',
     "test_copy_revisions.CopyRevisionTests.test_restored_configuration_exposes_running_progress_during_a_delayed_provider_call"),
    ("chat-learning-acceptance-binding", "workspace.py",
     'if accepted["job_id"] != payload["handoff_id"]:', 'if False:',
     "test_conversation_learning.ConversationLearningTests.test_bound_commands_reject_unaccepted_or_substituted_job_and_cohort_before_mutation"),
    ("chat-learning-cohort-binding", "workspace.py",
     'if action != "open-learning" and (payload["cohort_id"] != session["cohort_id"] or payload["cohort_id"] != accepted["id"]):', 'if False:',
     "test_conversation_learning.ConversationLearningTests.test_bound_commands_reject_unaccepted_or_substituted_job_and_cohort_before_mutation"),
    ("followup-independent-population", "adapters/sqlite/followups.py",
     "if set(p['population']) & excluded_businesses(db, organization, own_draft):", "if False:",
     "test_followups.FollowupTests.test_later_population_allocation_blocks_review_and_cannot_be_removed_from_brief"),
    ("followup-source-cannot-be-stripped", "adapters/sqlite/reviews.py",
     'if source_brief.get("followup_id") and canonical(source_brief) != canonical(bundle[0].manifest["brief"]):', 'if False:',
     "test_followups.FollowupTests.test_later_population_allocation_blocks_review_and_cannot_be_removed_from_brief"),
]


def run():
    detected = 0
    for label, relative, before, after, test in CASES:
        with tempfile.TemporaryDirectory(prefix="acquisition-mutation-") as temporary:
            directory = Path(temporary)
            for name in ("src", "tests", "config", "scripts"):
                shutil.copytree(ROOT / name, directory / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            path = directory / "src/acquisition" / relative
            source = path.read_text()
            if source.count(before) != 1:
                raise RuntimeError("Mutation no longer has exactly one target: " + label)
            mutated = source.replace(before, after)
            compile(mutated, str(path), "exec")
            path.write_text(mutated)
            target = test if "." in test else "test_failure_boundaries.FailureBoundaryTests." + test
            result = subprocess.run([sys.executable, "-m", "unittest", target],
                cwd=directory, env=dict(os.environ, PYTHONPATH=os.pathsep.join(("src", "tests"))),
                capture_output=True, text=True, timeout=30)
            # Import/syntax failures are invalid experiments, never killed mutants.
            valid = "Ran 1 test" in result.stderr and "Failed to import test module" not in result.stderr
            killed = valid and result.returncode != 0
            print(label + ": " + ("detected" if killed else "SURVIVED OR INVALID"))
            detected += killed
    print(f"Detected {detected}/{len(CASES)} declared harmful mutations")
    return 0 if detected == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(run())
