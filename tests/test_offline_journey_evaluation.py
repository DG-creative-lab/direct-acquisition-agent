"""Acceptance evidence must be complete, independently counted and attributable."""

from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
import copy
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import evaluate_offline_journey as evaluation
from scripts import offline_journey_fixture as fixture


def browser_rows():
    return [{"id": identity, "passed": True, "external_requests": [], "page_errors": [],
             "viewport": {"width": 1440 if identity == "desktop-journey" else 390, "height": 1000},
             "lost_schedule_response": "after_commit" if identity == "desktop-journey" else "before_dispatch",
             "fake_provider_calls": 1, "blocked_external_attempts": 0,
             "checks": [{"id": check, "passed": True, "observed": copy.deepcopy(evaluation.EXPECTED_BROWSER[check]) |
                        ({"original_pid": 11, "recovered_pid": 12} if check == "process-restart-after-import" else {}) |
                        ({"subject_id": "subject", "approval_id": "approval", "handoff_id": "handoff"}
                         if check in {"exact-review-and-money", "exact-exports"} else {})}
                        for check in evaluation.BROWSER_CHECKS]}
            for identity in ("desktop-journey", "mobile-journey")]


def native_rows():
    return [
        {"id": "revision-and-amendment", "passed": True, "live_provider_calls": 0,
         "journey": {"replay_added_calls": 0, "inspection_added_calls": 0, "confirmed_amendment_budget_pence": 51200}},
        {"id": "verified-fixture-and-restore", "passed": True, "live_provider_calls": 0,
         "fake_provider_calls": 0, "restored_bytes_unchanged": True},
        {"id": "uncertain-stop-restart", "passed": True, "live_provider_calls": 0,
         "fake_provider_calls": 1, "replay_added_calls": 0, "used": 1},
        {"id": "missing-controls-block-learning", "passed": True, "live_provider_calls": 0,
         "controls_missing": 74, "observations": 680, "counted_groups": 0},
    ]


class OfflineJourneyEvidenceTests(unittest.TestCase):
    def test_incomplete_duplicate_and_empty_browser_results_cannot_pass(self):
        self.assertTrue(all(row["passed"] for row in evaluation.grade(browser_rows(), native_rows())))
        for changed in ([], [browser_rows()[0]], browser_rows() + [browser_rows()[0]], [{"id": "desktop-journey", "passed": True}]):
            with self.subTest(changed=changed):
                self.assertFalse(all(row["passed"] for row in evaluation.grade(changed, native_rows())))
        browser = browser_rows()
        browser[0]["checks"].pop()
        self.assertFalse(evaluation.grade(browser, native_rows())[0]["passed"])

    def test_success_flags_cannot_hide_recounts_missing_controls_or_a_same_process_restart(self):
        for check, field, changed in (
                ("process-restart-after-import", "observations_after", 8),
                ("process-restart-after-import", "recovered_pid", 11),
                ("mature-learning-counted-once", "controls", 0),
                ("mature-learning-counted-once", "observations", 78),
                ("mature-learning-counted-once", "finalization_events", 2),
                ("lost-schedule-response-and-reload", "schedules", 2),
                ("independent-followup-needs-fresh-approval", "approved", True),
                ("exact-exports", "subject_id", "another-subject"),
                ("exact-exports", "approval_id", "another-approval"),
                ("exact-exports", "handoff_id", "another-handoff"),
                ("exact-review-and-money", "cost_pence", 60001)):
            with self.subTest(check=check, field=field):
                browser = browser_rows()
                target = next(row for row in browser[0]["checks"] if row["id"] == check)
                target["observed"][field] = changed
                self.assertFalse(evaluation.grade(browser, native_rows())[0]["passed"])
        native = native_rows()
        native[-1]["controls_missing"] = 0
        self.assertFalse(all(row["passed"] for row in evaluation.grade(browser_rows(), native)))

    def test_external_attempts_and_page_failures_invalidate_browser_evidence(self):
        for field, value in (("external_requests", ["https://example.invalid"]),
                             ("page_errors", ["fixture failure"]), ("blocked_external_attempts", 1),
                             ("viewport", {"width": 390, "height": 1000}), ("lost_schedule_response", None)):
            browser = browser_rows()
            browser[0][field] = value
            self.assertFalse(evaluation.grade(browser, native_rows())[0]["passed"])

    def test_missing_executable_is_recorded_as_an_infrastructure_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "missing.log"
            result = evaluation.command([str(Path(folder) / "no-executable")], log)
            self.assertEqual(result["exit_code"], 127)
            self.assertIn("No such file", log.read_text())

    def test_a_caught_network_attempt_still_fails_the_native_run(self):
        # Save the C-level alias before entering the guard, as a library could do.
        connect_ex = socket.socket.connect_ex
        def worker_connect(connection):
            with ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(connect_ex, connection, ("127.0.0.1", 1)).result()

        operations = {
            "connect": lambda s: s.connect(("127.0.0.1", 1)),
            "connect_ex": lambda s: connect_ex(s, ("127.0.0.1", 1)),
            "connect_ex_worker": worker_connect,
            "sendto": lambda s: s.sendto(b"offline", ("127.0.0.1", 1)),
            "getaddrinfo": lambda s: socket.getaddrinfo("localhost", 1),
            "gethostbyname": lambda s: socket.gethostbyname("localhost"),
            "gethostbyname_ex": lambda s: socket.gethostbyname_ex("localhost"),
            "gethostbyaddr": lambda s: socket.gethostbyaddr("127.0.0.1"),
            "getnameinfo": lambda s: socket.getnameinfo(("127.0.0.1", 1), 0),
        }
        if hasattr(socket.socket, "sendmsg"):
            operations["sendmsg"] = lambda s: s.sendmsg([b"offline"], [], 0, ("127.0.0.1", 1))
        for name, operation in operations.items():
            with self.subTest(entry=name):
                def caught_attempt(directory):
                    with socket.socket(type=socket.SOCK_DGRAM) as connection:
                        with self.assertRaisesRegex(AssertionError, "External network"):
                            operation(connection)
                    return native_rows()

                with (
                    tempfile.TemporaryDirectory() as folder,
                    patch.object(sys, "argv", ["fixture", "native", "--directory", folder]),
                    patch.object(fixture, "native_cases", side_effect=caught_attempt),
                    redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(fixture.main(), 1)
                    rows = json.loads((Path(folder) / "native-results.json").read_text())
                    self.assertEqual(rows[-1]["id"], "blocked-native-network")
                    attempts = (Path(folder) / "blocked-native-network.jsonl").read_text().splitlines()
                    self.assertEqual(len(attempts), 1)
                    self.assertEqual(json.loads(attempts[0])["kind"], "blocked_external_attempt")
                    self.assertFalse(all(row["passed"] for row in evaluation.grade(browser_rows(), rows)))
                    if name == "connect_ex_worker":
                        class ServerProbeComplete(Exception):
                            pass

                        def server_probe(*args):
                            caught_attempt(Path(folder))
                            raise ServerProbeComplete()

                        # Exercise serve's own guard, not only the native wrapper.
                        # Stop before opening a listening socket or starting workers.
                        with (
                            patch("acquisition.workspace_server.WorkspaceServer", side_effect=server_probe),
                            self.assertRaises(ServerProbeComplete),
                        ):
                            fixture.serve(Path(folder), 0, 0)
                        logged = (Path(folder) / "provider.jsonl").read_text().splitlines()
                        self.assertEqual(len(logged), 1)
                        self.assertEqual(json.loads(logged[0])["event"], "socket.connect")

    def test_main_writes_both_reports_and_fails_for_missing_evidence_or_source_drift(self):
        malformed = browser_rows()
        malformed[0]["checks"][0] = None
        missing_observations = browser_rows()
        missing_observations[0]["checks"][0]["observed"] = []
        missing_counts = browser_rows()
        missing_counts[0]["checks"][1]["observed"]["counts"] = []
        for browser, drift in (([], False), (browser_rows(), True), (browser_rows(), False),
                               (malformed, False), (missing_observations, False), (missing_counts, False)):
            with self.subTest(browser=browser, drift=drift), tempfile.TemporaryDirectory() as folder:
                expected = not drift and all(row["passed"] for row in evaluation.grade(browser, native_rows()))
                output = Path(folder)
                before = {"head_commit": "fixture-head", "files_sha256": "original", "files": {},
                          "worktree_dirty": False}
                after = before | ({"files_sha256": "changed"} if drift else {})
                with (
                    patch.object(evaluation, "source_state", side_effect=[before, after]),
                    patch.object(evaluation, "command", return_value={"exit_code": 0}),
                    patch.object(evaluation, "artifacts", return_value={"fixture": {"sha256": "recorded", "bytes": 1}}),
                    patch.object(evaluation, "read_results", side_effect=[browser, native_rows()]),
                    patch.object(sys, "argv", ["evaluate", "--output-dir", folder]),
                    redirect_stdout(io.StringIO()),
                ):
                    code = evaluation.main()
                self.assertEqual(code, int(not expected))
                result = json.loads((output / "results.json").read_text())
                self.assertEqual(result["passed"], expected)
                self.assertEqual(result["source_state_stable"], not drift)
                self.assertIn("PASS" if expected else "FAIL", (output / "evidence.md").read_text())

    def test_existing_evidence_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "evidence.md"
            path.write_text("Original evidence")
            with patch.object(sys, "argv", ["evaluate", "--output-dir", folder]), redirect_stdout(io.StringIO()),                  patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit) as raised:
                evaluation.main()
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(path.read_text(), "Original evidence")
