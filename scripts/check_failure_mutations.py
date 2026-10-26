"""Run selected harmful mutations in temporary copies, never in the checkout."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = [
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
     'eligible=self.eligible)', 'eligible=None)',
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
