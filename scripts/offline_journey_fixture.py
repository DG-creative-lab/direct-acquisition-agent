"""Isolated fixtures and process faults for the issue-23 offline evaluation."""

import argparse
from contextlib import ExitStack, contextmanager
import csv
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import sys
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "tests")]
NOW = 1792972800.0
NETWORK_EVENTS = frozenset({"socket.connect", "socket.sendto", "socket.sendmsg",
                            "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr",
                            "socket.getnameinfo"})
_network_logs = ()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def append(path, value):
    with path.open("a") as stream:
        stream.write(json.dumps(value, allow_nan=False) + "\n")


def _audit_network(event, args):
    # CPython audits connect and connect_ex through the same event. This also
    # catches saved aliases and calls from server workers before any socket I/O.
    logs = _network_logs
    if logs and event in NETWORK_EVENTS:
        for path in logs:
            append(path, {"kind": "blocked_external_attempt", "event": event})
        raise AssertionError("External network disabled in the offline evaluation")


sys.addaudithook(_audit_network)


@contextmanager
def offline_network(log):
    global _network_logs
    previous = _network_logs
    _network_logs = previous + (log,)
    try:
        yield
    finally:
        _network_logs = previous


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def serve(root, port, generation):
    from acquisition.bootstrap import build_workspace
    from acquisition.entrypoints.workspace import WorkspaceServer
    from acquisition.adapters.sqlite.report_monitoring import SqliteReportMonitoring
    from test_preparations import CombinedModel
    from test_conversations import proposal

    root.mkdir(parents=True, exist_ok=True)
    model = CombinedModel(proposal(budget_pence=60000, segments=["contractors"], copy_mode="fixture"))
    complete = model.complete

    def recorded(request):
        append(root / "provider.jsonl", {"kind": "scripted_model_call", "sha256": sha(request),
                                        "tool": request["tools"][0]["function"]["name"]})
        return complete(request)

    def forbidden(*args, **kwargs):
        append(root / "provider.jsonl", {"kind": "blocked_external_attempt"})
        raise AssertionError("External network and live inference are disabled in this evaluation")

    initialize = SqliteReportMonitoring.__init__
    finish = SqliteReportMonitoring.finish

    def leased(store, *args, **kwargs):
        initialize(store, *args, **kwargs)
        store.lease_clock = lambda: 1000 + generation * 31

    def finish_or_exit(store, organization, cohort, token):
        trigger = root / "crash-after-import"
        if trigger.exists():
            trigger.unlink()
            with store.database.connect() as db:
                observations = db.execute("SELECT COUNT(*) FROM learning_outcomes WHERE organization=? AND cohort_id=?",
                                          (organization, cohort)).fetchone()[0]
            write_json(root / "import-before-crash.json", {
                "pid": os.getpid(), "generation": generation, "observations": observations,
                "progress": store.status(organization, cohort)})
            os._exit(91)
        return finish(store, organization, cohort, token)

    with ExitStack() as stack:
        stack.enter_context(offline_network(root / "provider.jsonl"))
        stack.enter_context(patch.object(model, "complete", side_effect=recorded))
        stack.enter_context(patch("acquisition.adapters.openrouter.OpenRouter.complete", side_effect=forbidden))
        stack.enter_context(patch.object(SqliteReportMonitoring, "__init__", leased))
        stack.enter_context(patch.object(SqliteReportMonitoring, "finish", finish_or_exit))
        # HTTPServer asks for its own display name while binding. No DNS is
        # needed for this fixed loopback fixture; outbound lookups stay blocked.
        with patch.object(socket, "getfqdn", return_value="localhost"):
            server = WorkspaceServer(port, build_workspace(root, real_clock=lambda: NOW,
                                     gateway_factory=lambda: model), ROOT / "frontend/dist")
        append(root / "processes.jsonl", {"pid": os.getpid(), "generation": generation, "port": server.server_port})
        signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
        print(json.dumps({"url": "http://127.0.0.1:" + str(server.server_port), "pid": os.getpid()}), flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()


def recordings(assignments, cohort_path, directory):
    with assignments.open(newline="") as stream:
        members = list(csv.DictReader(stream))
    cohort = json.loads(cohort_path.read_text())
    if len(members) < 4 or len({member["business_id"] for member in members}) != len(members):
        raise ValueError("The exported assignment population must contain four distinct fixture businesses")
    responders = {member["business_id"] for member in sorted(members, key=lambda row: row["business_id"])[:4]}
    early_time = cohort["window_start"] + 7 * 86400
    outcomes = [
        member | {"response": member["business_id"] in responders,
                  "observed_at": early_time - 1 if member["business_id"] in responders else cohort["window_end"]}
        for member in members
    ]
    for report_id, rows, watermark, final in (
            ("early", [row for row in outcomes if row["response"]], early_time, False),
            ("final", outcomes, cohort["window_end"], True)):
        report = {key: cohort[key] for key in ("organization", "job_id", "metric", "window_start", "window_end")}
        report |= {"schema": "synthetic-provider-report/v1", "mode": "SYNTHETIC_ONLY", "cohort_id": cohort["id"],
                   "report_id": report_id, "watermark": watermark, "final": final, "page_count": 1,
                   "pages": [{"report_id": report_id, "number": 1, "events": [
                       {"event_id": "synthetic_event_" + sha({"business_id": row["business_id"], "cohort_id": cohort["id"]}),
                        "outcome": row} for row in rows]}]}
        write_json(directory / (report_id + ".json"), report)
    expected = {"observations": len(members), "successes": 4,
                "controls": sum(member["arm"] == "no_mail" for member in members),
                "business_ids": sorted(member["business_id"] for member in members),
                "early_time": early_time, "end": cohort["window_end"]}
    write_json(directory / "expected.json", expected)
    return expected


def audit(root):
    with sqlite3.connect(root / "conversations.sqlite") as db:
        db.row_factory = sqlite3.Row
        return {
            "schedules": [dict(row) for row in db.execute(
                "SELECT organization,cohort_id,revision,status,position,report_count FROM report_monitoring")],
            "sources": db.execute("SELECT COUNT(*) FROM report_monitoring_sources").fetchone()[0],
            "outcomes": db.execute("SELECT COUNT(*) FROM learning_outcomes").fetchone()[0],
            "model_calls": db.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0],
            "imports": [json.loads(row[0]) for row in db.execute(
                "SELECT payload FROM learning_events WHERE kind='provider_report_imported' ORDER BY sequence")],
        }


def native_cases(directory):
    from scripts.evaluate_conversational_agent import run_case, verified_boundary, uncertain_restart

    corpus = json.loads((ROOT / "config/conversation-offline-evaluation-v1.json").read_text())
    supported = next(case for case in corpus["cases"]
                     if case["expected"].get("review_ready") and case["expected"].get("segments") == ["contractors"])
    results = []
    for identity, operation in (
            ("revision-and-amendment", lambda: run_case(supported)),
            ("verified-fixture-and-restore", verified_boundary),
            ("uncertain-stop-restart", uncertain_restart),
            ("missing-controls-block-learning", lambda: incomplete_controls(directory))):
        try:
            result = operation() | {"id": identity}
        except Exception as error:
            result = {"id": identity, "passed": False, "error": type(error).__name__ + ": " + str(error)}
        results.append(result)
    write_json(directory / "native-results.json", results)
    return results


def incomplete_controls(directory):
    from acquisition.bootstrap import build
    from acquisition.contracts import Conflict
    from acquisition.review_demo import run_review_demo

    now = NOW
    root = directory / "missing-controls"
    root.mkdir()
    app = build(root / "application.sqlite", clock=lambda: now)
    demo = run_review_demo(app, "coverage-evaluation", "fixture", root / "exports", str(root / "application.sqlite"))
    scope, actor = demo["organization"], "demo-operator"
    opened = app.learning.open(scope, demo["case_id"], actor, "open")
    cohort = app.learning.source.accepted(scope, demo["case_id"])
    now = opened["window_end"]
    mailed = [member for member in cohort["members"] if member["arm"] != "no_mail"]
    controls = len(cohort["members"]) - len(mailed)
    if controls <= 0:
        raise AssertionError("The negative coverage fixture needs no-mail controls")
    report = {key: cohort[key] for key in ("organization", "job_id", "metric", "window_start", "window_end")}
    report |= {"schema": "synthetic-provider-report/v1", "mode": "SYNTHETIC_ONLY", "cohort_id": cohort["id"],
               "report_id": "missing-controls", "watermark": now, "final": True, "page_count": 1,
               "pages": [{"report_id": "missing-controls", "number": 1, "events": [
                   {"event_id": "synthetic_event_" + sha({"business_id": member["business_id"], "cohort_id": cohort["id"]}),
                    "outcome": member | {"response": False, "observed_at": now}} for member in mailed]}]}
    path = root / "report.json"
    write_json(path, report)
    app.learning.schedule_reports(scope, actor, "schedule", cohort["id"], now, 60, [path])
    app.learning.check_reports(scope, cohort["id"])
    try:
        app.learning.store.finalize(scope, actor, "finalize", cohort["id"], now)
    except Conflict as error:
        if "including controls" not in str(error):
            raise AssertionError("Finalization failed for a different reason") from error
    else:
        raise AssertionError("Missing control outcomes were counted")
    view = app.learning.store.view(scope, cohort["id"])
    if view["missing"] != controls or view["beliefs"] or view["status"] == "finalized":
        raise AssertionError("Incomplete coverage changed counted beliefs")
    return {"passed": True, "controls_missing": controls, "observations": view["received"],
            "counted_groups": len(view["beliefs"]), "fake_provider_calls": 0, "live_provider_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    server = commands.add_parser("serve")
    server.add_argument("--root", type=Path, required=True)
    server.add_argument("--port", type=int, default=0)
    server.add_argument("--generation", type=int, default=0)
    reports = commands.add_parser("recordings")
    reports.add_argument("--assignments", type=Path, required=True)
    reports.add_argument("--cohort", type=Path, required=True)
    reports.add_argument("--directory", type=Path, required=True)
    inspect = commands.add_parser("audit")
    inspect.add_argument("--root", type=Path, required=True)
    native = commands.add_parser("native")
    native.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "serve":
        serve(args.root, args.port, args.generation)
    elif args.command == "recordings":
        print(json.dumps(recordings(args.assignments, args.cohort, args.directory)))
    elif args.command == "audit":
        print(json.dumps(audit(args.root)))
    else:
        with offline_network(args.directory / "blocked-native-network.jsonl"):
            results = native_cases(args.directory)
        if (args.directory / "blocked-native-network.jsonl").exists():
            results.append({"id": "blocked-native-network", "passed": False,
                            "error": "A native case attempted an external connection"})
            write_json(args.directory / "native-results.json", results)
        print(json.dumps(results))
        return int(not all(row["passed"] for row in results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
