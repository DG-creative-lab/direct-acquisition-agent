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
