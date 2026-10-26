"""Run four bounded harmful mutations in temporary copies, never in the checkout."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("task-finite-clock", "adapters/sqlite/tasks.py",
     '        if not math.isfinite(now):\n            raise LeaseLost("Attempt requires a finite clock reading")\n', "",
     "test_nonfinite_clock_cannot_settle_fail_or_admit_a_paid_request"),
    ("inference-finite-clock", "adapters/sqlite/inference.py",
     '        if not math.isfinite(now):\n            raise LeaseLost("Inference requires a finite clock reading")\n', "",
     "test_nonfinite_clock_cannot_settle_fail_or_admit_a_paid_request"),
    ("inference-budget", "adapters/sqlite/inference.py", "            if count >= limit:", "            if False:",
     "test_concurrent_reservations_cannot_oversubscribe_a_one_call_budget"),
    ("uncertain-call-retry", "adapters/sqlite/inference.py",
     '                    raise ModelError("previous_inference_failed_or_unknown_no_retry")', "                    return None",
     "test_unknown_gateway_failure_is_sanitized_and_never_dispatched_again"),
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
            result = subprocess.run([sys.executable, "-m", "unittest", "test_failure_boundaries.FailureBoundaryTests." + test],
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
