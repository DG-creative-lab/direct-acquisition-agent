"""Run the issue-23 offline acceptance journey and retain attributable evidence.

python3 scripts/evaluate_offline_journey.py --output-dir .local/journey-evidence
The destination must be empty. Python, installed frontend dependencies and the
Playwright Chromium browser are required. All application data is synthetic.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluation_evidence import source_state

PREFIXES = ("src", "tests", "config", "scripts", "frontend/src", "frontend/tests", "frontend/scripts", "frontend/public",
            "frontend/package.json", "frontend/pnpm-lock.yaml", "frontend/playwright.config.ts",
            "frontend/tsconfig.json", "frontend/vite.config.ts", "frontend/index.html")
BROWSER_CHECKS = ("incomplete-and-corrected-brief", "exact-review-and-money", "exact-exports",
                  "lost-schedule-response-and-reload", "cadence-pause-and-resume", "process-restart-after-import",
                  "mature-learning-counted-once", "independent-followup-needs-fresh-approval")
NATIVE_CASES = ("revision-and-amendment", "verified-fixture-and-restore", "uncertain-stop-restart",
                "missing-controls-block-learning")
EXPECTED_BROWSER = {
    "incomplete-and-corrected-brief": {"revisions": [1, 2], "budget_pence": 60000, "clarification_calls": 0},
    "exact-review-and-money": {"counts": {"input": 100, "excluded": 23, "eligible_unselected": 0,
                                         "mailed": 70, "holdout": 7}, "cost_pence": 5950, "budget_pence": 60000},
    "exact-exports": {"mailed": 70, "enrolled": 77},
    "lost-schedule-response-and-reload": {"attempts": 2, "schedules": 1, "sources": 2, "observations": 0},
    "cadence-pause-and-resume": {"revision": 4, "interval_seconds": 1800, "original_due": 1793577600},
    "process-restart-after-import": {"observations_before": 4, "observations_after": 4, "report_imports": 1,
                                    "lease_clock_advance_seconds": 31},
    "mature-learning-counted-once": {"observations": 77, "successes": 4, "controls": 7, "finalization_events": 1},
    "independent-followup-needs-fresh-approval": {"shared_businesses": 0, "approved": False, "accepted": False},
}


def read_results(path):
    try:
        value = json.loads(path.read_text())
        if type(value) is not list:
            raise ValueError("Expected a scenario list")
        return value
    except (OSError, ValueError) as error:
        return [{"id": "unreadable-results", "passed": False, "error": str(error)}]


def grade(browser, native):
    """Missing, repeated or incomplete evidence cannot pass the suite."""
    rows = []
    for identity in ("desktop-journey", "mobile-journey"):
        matches = [row for row in browser if type(row) is dict and row.get("id") == identity]
        row = matches[0] if len(matches) == 1 else {}
        checks = row.get("checks", [])
        valid = (type(checks) is list and len(checks) == len(BROWSER_CHECKS)
                 and all(type(check) is dict for check in checks)
                 and [check.get("id") for check in checks] == list(BROWSER_CHECKS)
                 and all(check.get("passed") is True for check in checks)
                 and all(type(check.get("observed")) is dict and all(
                     check["observed"].get(key) == expected
                     for key, expected in EXPECTED_BROWSER[check["id"]].items()) for check in checks)
                 and row.get("passed") is True and row.get("external_requests") == []
                 and row.get("page_errors") == []
                 and row.get("viewport") == {"width": 1440 if identity == "desktop-journey" else 390, "height": 1000}
                 and row.get("lost_schedule_response") == ("after_commit" if identity == "desktop-journey" else "before_dispatch")
                 and type(row.get("fake_provider_calls")) is int and row["fake_provider_calls"] == 1
                 and type(row.get("blocked_external_attempts")) is int and row["blocked_external_attempts"] == 0)
        if valid:
            restarted = next(check["observed"] for check in checks if check["id"] == "process-restart-after-import")
            reviewed = next(check["observed"] for check in checks if check["id"] == "exact-review-and-money")
            exported = next(check["observed"] for check in checks if check["id"] == "exact-exports")
            valid = (type(restarted.get("original_pid")) is int and type(restarted.get("recovered_pid")) is int
                     and restarted["original_pid"] > 0 and restarted["recovered_pid"] > 0
                     and restarted["original_pid"] != restarted["recovered_pid"]
                     and all(type(reviewed.get(key)) is str and bool(reviewed[key])
                             and exported.get(key) == reviewed[key]
                             for key in ("subject_id", "approval_id", "handoff_id")))
        rows.append({"id": identity, "passed": valid, "evidence": row,
                     "error": None if valid else "Missing, failed or inconsistent browser evidence"})
    for identity in NATIVE_CASES:
        matches = [row for row in native if type(row) is dict and row.get("id") == identity]
        row = matches[0] if len(matches) == 1 else {}
        valid = (row.get("passed") is True and type(row.get("live_provider_calls")) is int
                 and row["live_provider_calls"] == 0)
        if identity == "missing-controls-block-learning":
            valid = valid and row.get("controls_missing") == 74 and row.get("observations") == 680 and row.get("counted_groups") == 0
        elif identity == "verified-fixture-and-restore":
            valid = valid and row.get("restored_bytes_unchanged") is True and row.get("fake_provider_calls") == 0
        elif identity == "uncertain-stop-restart":
            valid = valid and row.get("fake_provider_calls") == 1 and row.get("replay_added_calls") == 0 and row.get("used") == 1
        else:
            journey = row.get("journey", {})
            valid = (valid and type(journey) is dict and journey.get("replay_added_calls") == 0 and journey.get("inspection_added_calls") == 0
                     and journey.get("confirmed_amendment_budget_pence") == 51200)
        rows.append({"id": identity, "passed": valid, "evidence": row,
                     "error": None if valid else "Missing or failed native evidence"})
    unexpected = [row for row in browser + native
                  if type(row) is not dict or row.get("id") not in ("desktop-journey", "mobile-journey", *NATIVE_CASES)]
    if unexpected:
        rows.append({"id": "unexpected-results", "passed": False, "evidence": unexpected})
    return rows


def command(args, log, *, cwd=ROOT, timeout=360):
    started = time.monotonic()
    environment = dict(os.environ, OPENROUTER_API_KEY="offline-tests-must-not-use-live-credentials",
                       PYTHONPATH=str(ROOT / "src") + os.pathsep + str(ROOT / "tests"),
                       JOURNEY_PYTHON=sys.executable, COREPACK_ENABLE_NETWORK="0")
    with log.open("w") as stream:
        try:
            process = subprocess.Popen(args, cwd=cwd, env=environment, stdout=stream, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        except OSError as error:
            stream.write(str(error) + "\n")
            return {"command": args, "exit_code": 127, "log": log.name, "error": str(error)}
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            stream.write("\nEvaluation subprocess exceeded its time limit.\n")
            code = 124
    return {"command": args, "exit_code": code, "elapsed_seconds": round(time.monotonic() - started, 3),
            "log": log.name}


def artifacts(directory):
    records = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name not in {"results.json", "evidence.md"}:
            raw = path.read_bytes()
            records[path.relative_to(directory).as_posix()] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return records


def readable(report):
    outcome = "PASS" if report["passed"] else "FAIL"
    lines = ["# Offline journey evidence", "", f"Overall result **{outcome}**.",
             "", "This run uses synthetic businesses, scripted planning responses, simulated acceptance and recorded outcomes.",
             "Model interpretation, editorial quality and production provider behavior require separate evaluation.",
             "", f"Base commit `{report['source_state']['head_commit']}`.",
             f"Source stable during execution **{report['source_state_stable']}**.",
             f"Inputs differ from the base commit **{report['source_state']['worktree_dirty']}**.",
             "", "## Acceptance results", "", "| Scenario | Result |", "| --- | --- |"]
    for row in report["results"]:
        lines.append(f"| {row['id']} | {'PASS' if row['passed'] else 'FAIL'} |")
    for row in report["results"]:
        lines.extend(["", "## " + row["id"], ""])
        evidence = row.get("evidence", {})
        if type(evidence) is dict and type(evidence.get("checks")) is list:
            for check in evidence["checks"]:
                if type(check) is not dict:
                    lines.append("- **FAIL**. Required structured check evidence is missing.")
                    continue
                lines.append(f"- **{'PASS' if check.get('passed') else 'FAIL'}**. "
                             + check.get("id", "unknown check").replace("-", " ").capitalize()
                             + ". " + describe_check(check))
        else:
            lines.append(describe_native(row))
    lines.extend(["", "## Usability scope", "",
                  "Passing browser cases mean the required actions were reachable at 1440px and 390px, with no uncaught page errors.",
                  "The final follow-up view must fit the document width. Screenshots retain the review, monitoring and recovery views.",
                  "The mobile review and learning page requires substantial vertical scrolling. This suite does not measure discoverability or assistive-technology usability.",
                  "", "## Evidence files", "", "The JSON result contains a SHA-256 inventory of every retained evidence file.", ""])
    for path in report["artifacts"]:
        if path.endswith((".png", ".csv", ".sqlite", "state.json", "learning.json", "expected.json", ".log")):
            lines.append(f"- [{path}]({path})")
    lines.extend(["", "## Boundaries", "",
                  "- Browser requests are restricted to the fixture's loopback origin.",
                  "- The fixture replaces the provider with a scripted model and blocks external socket connections.",
                  "- The restart fault exits the actual server process after import commit. Recovery advances only the fixture lease clock.",
                  "- Missing native or browser evidence and source changes cause a failing exit status.",
                  "- Measured time describes this local harness. It is separate from production latency or live model cost.", ""])
    return "\n".join(lines)


def describe_check(check):
    if check.get("passed") is not True:
        return str(check.get("error", "Required evidence is missing")).replace("\n", " ")
    observed = check.get("observed", {})
    if type(observed) is not dict:
        return "Required structured observations are missing."
    identity = check.get("id")
    if identity == "incomplete-and-corrected-brief":
        return f"Revisions {observed.get('revisions')}. Budget {observed.get('budget_pence')} pence. Clarification used {observed.get('clarification_calls')} model calls."
    if identity == "exact-review-and-money":
        counts = observed.get("counts", {})
        if type(counts) is not dict:
            return "Required population counts are missing."
        return (f"{counts.get('input')} source records, {counts.get('excluded')} exclusions, "
                f"{counts.get('mailed')} mailed assignments and {counts.get('holdout')} controls. "
                f"Cost {observed.get('cost_pence')} pence within a {observed.get('budget_pence')}-pence budget.")
    if identity == "exact-exports":
        return (f"Downloaded manifest and receipt match displayed subject {observed.get('subject_id')}, "
                f"approval {observed.get('approval_id')} and handoff {observed.get('handoff_id')}. "
                f"CSV hashes match. Mailing rows {observed.get('mailed')}, enrolled assignments {observed.get('enrolled')}.")
    if identity == "lost-schedule-response-and-reload":
        return (f"{observed.get('attempts')} attempts share request `{observed.get('request_id')}`. "
                f"Stored schedules {observed.get('schedules')}, sources {observed.get('sources')}, observations {observed.get('observations')}.")
    if identity == "cadence-pause-and-resume":
        return f"Schedule revision {observed.get('revision')}, cadence {observed.get('interval_seconds')} seconds. The original due check is preserved."
    if identity == "process-restart-after-import":
        return (f"Process {observed.get('original_pid')} exits after import. Process {observed.get('recovered_pid')} recovers it. "
                f"Observations stay at {observed.get('observations_before')} before and {observed.get('observations_after')} after recovery. "
                f"Import receipts {observed.get('report_imports')}.")
    if identity == "mature-learning-counted-once":
        return (f"{observed.get('observations')} independent observations, {observed.get('successes')} synthetic successes, "
                f"{observed.get('controls')} controls and {observed.get('finalization_events')} finalization event.")
    return f"Shared parent businesses {observed.get('shared_businesses')}. Child approved {observed.get('approved')}, accepted {observed.get('accepted')}."


def describe_native(row):
    evidence = row.get("evidence", {})
    if not row["passed"] or type(evidence) is not dict:
        return str(evidence.get("error", row.get("error", "Required evidence is missing"))
                   if type(evidence) is dict else evidence).replace("\n", " ")
    if row["id"] == "revision-and-amendment":
        journey = evidence["journey"]
        return (f"Targeted copy consent, new-subject review and preference history checks passed. "
                f"The confirmed amendment uses {journey['confirmed_amendment_budget_pence']} pence. "
                f"Additional replay calls {journey['replay_added_calls']}, inspection calls {journey['inspection_added_calls']}.")
    if row["id"] == "verified-fixture-and-restore":
        return f"Fixture model calls {evidence['fake_provider_calls']}. Restored bytes unchanged {evidence['restored_bytes_unchanged']}."
    if row["id"] == "uncertain-stop-restart":
        return f"Uncertain scripted calls {evidence['fake_provider_calls']}, additional replay calls {evidence['replay_added_calls']}, accounted allowance use {evidence['used']}."
    return f"Stored treatment observations {evidence['observations']}. Unknown controls {evidence['controls_missing']}. Counted belief groups {evidence['counted_groups']}."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / ".local" / ("offline-journey-" + uuid4().hex[:12]))
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        parser.error("Use a new or empty evidence directory")
    # Capture before application imports, the frontend build or child processes.
    before = source_state(ROOT, PREFIXES)
    destination.mkdir(parents=True, exist_ok=True)
    stages = []
    stages.append(command(["pnpm", "run", "build"], destination / "build.log", cwd=ROOT / "frontend"))
    built = artifacts(ROOT / "frontend/dist") if stages[-1]["exit_code"] == 0 else {}
    if stages[-1]["exit_code"] == 0:
        stages.append(command(["node", str(ROOT / "frontend/scripts/offline-journey.mjs"), str(destination)],
                              destination / "browser.log", cwd=ROOT / "frontend"))
    stages.append(command([sys.executable, str(ROOT / "scripts/offline_journey_fixture.py"), "native",
                           "--directory", str(destination)], destination / "native.log"))
    browser = read_results(destination / "browser-results.json")
    native = read_results(destination / "native-results.json")
    results = grade(browser, native)
    after = source_state(ROOT, PREFIXES)
    stable = before["head_commit"] == after["head_commit"] and before["files_sha256"] == after["files_sha256"]
    assets_stable = bool(built) and built == artifacts(ROOT / "frontend/dist")
    passed = stable and assets_stable and all(stage["exit_code"] == 0 for stage in stages) and all(row["passed"] for row in results)
    report = {"schema": "offline-journey-evaluation/v1", "evaluated_at": datetime.now(timezone.utc).isoformat(),
              "passed": passed, "source_state": before,
              "source_state_after": {key: value for key, value in after.items() if key != "files"},
              "source_state_stable": stable,
              "frontend_build": {"files": built, "stable_during_execution": assets_stable},
              "evaluated_commit": before["head_commit"] if stable and not before["worktree_dirty"] else None,
              "changed_source_files": sorted(key for key in before["files"].keys() | after["files"].keys()
                                             if before["files"].get(key) != after["files"].get(key)),
              "stages": stages, "results": results, "artifacts": artifacts(destination),
              "limits": ["Synthetic-only control evidence", "Scripted planning does not measure live model quality",
                         "No real delivery, customer performance or production capacity measurement"]}
    text = readable(report)
    (destination / "evidence.md").write_text(text)
    report["readable_report_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    (destination / "results.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(("PASS" if passed else "FAIL") + " " + str(destination / "results.json"))
    print(destination / "evidence.md")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
