"""Independent failure oracles for lease, paid-call and HTTP boundaries."""

import io
import json
import sqlite3
import tempfile
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from acquisition.adapters.openrouter import NoRedirect, OpenRouter
from acquisition.adapters.sqlite.database import Database
from acquisition.bootstrap import build
from acquisition.contracts import Conflict
from acquisition.reasoning import CallScope, ModelConfig, ModelError
from acquisition.runtime import LeaseLost, Outcome
from test_model_copy import FakeModel, reply


class FailureBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "failure.sqlite"
        self.now = 1792886400.0
        self.model = FakeModel()
        self.app = build(self.path, lambda: self.now, self.model, ModelConfig("test/model", max_calls=10))
        self.run = self.app.start_model("one", "boundary", size=100)
        self.app.worker.tick("one")
        self.claim = self.app.tasks.claim("one", self.now, 60)
        self.scope = CallScope("one", self.run, self.claim.task_id, self.claim.token)

    def test_nonfinite_clock_cannot_settle_fail_or_admit_a_paid_request(self):
        for now in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(now=now):
                with self.assertRaises(LeaseLost):
                    self.app.tasks.settle(self.claim, Outcome("succeeded", {"unsafe": True}), now)
                with self.assertRaises(LeaseLost):
                    self.app.tasks.fail(self.claim, "unsafe", False, now)
                with self.assertRaises(LeaseLost):
                    self.app.calls.reserve(self.scope, "unsafe", "hash", 1, now)
        state = self.app.tasks.inspect("one", self.run)
        self.assertEqual(state["tasks"][1]["status"], "running")
        self.assertIsNone(state["tasks"][1]["output"])
        self.assertEqual(self.app.calls.inspect("one", self.run), [])

    def test_concurrent_reservations_cannot_oversubscribe_a_one_call_budget(self):
        barrier = Barrier(2)
        def reserve(key):
            barrier.wait()
            try:
                self.app.calls.reserve(self.scope, key, key, 1, self.now)
                return "reserved"
            except ModelError:
                return "blocked"
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(reserve, ("first", "second")))
        self.assertCountEqual(outcomes, ["reserved", "blocked"])
        self.assertEqual(len(self.app.calls.inspect("one", self.run)), 1)

    def test_cancel_during_inference_keeps_usage_but_blocks_followup_and_task_commit(self):
        app = self.app
        class CancelDuringCall:
            def complete(_, request):
                app.tasks.cancel("one", self.run, self.now)
                return reply("read_editorial_context", {})
        app.inference.gateway = CancelDuringCall()
        app.inference.call(self.scope, "in-flight", [], [])
        records = app.calls.inspect("one", self.run)
        self.assertEqual(records[0]["status"], "recorded")
        self.assertEqual(records[0]["receipt"]["usage"]["total_tokens"], 300)
        with self.assertRaises(LeaseLost):
            app.inference.call(self.scope, "followup", [], [])
        with self.assertRaises(LeaseLost):
            app.tasks.settle(self.claim, Outcome("succeeded", {}), self.now)
        self.assertEqual(app.tasks.inspect("one", self.run)["run"]["status"], "cancelled")
        self.assertEqual(len(app.calls.inspect("one", self.run)), 1)

    def test_unknown_gateway_failure_is_sanitized_and_never_dispatched_again(self):
        calls = []
        class Unknown:
            def complete(_, request):
                calls.append(request)
                raise OSError("sensitive-provider-body-and-credential")
        self.app.inference.gateway = Unknown()
        for _ in range(2):
            with self.assertRaises(ModelError) as error:
                self.app.inference.call(self.scope, "uncertain", [], [])
            self.assertNotIn("sensitive", str(error.exception))
        records = self.app.calls.inspect("one", self.run)
        self.assertEqual(len(calls), 1)
        self.assertEqual(records[0]["status"], "unknown")
        self.assertNotIn("sensitive", json.dumps(records))

    def test_lost_receipt_after_success_does_not_repeat_the_external_effect(self):
        with Database(self.path).connect() as db:
            db.execute("CREATE TRIGGER fail_receipt BEFORE UPDATE ON model_calls BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.app.inference.call(self.scope, "paid-once", [], [{"function": {"name": "read_editorial_context"}}])
        with Database(self.path).connect() as db:
            db.execute("DROP TRIGGER fail_receipt")
        with self.assertRaises(ModelError):
            self.app.inference.call(self.scope, "paid-once", [], [{"function": {"name": "read_editorial_context"}}])
        self.assertEqual(len(self.model.requests), 1)
        self.assertEqual(self.app.calls.inspect("one", self.run)[0]["status"], "reserved")

    def test_input_envelope_limit_blocks_before_reservation_and_network(self):
        with self.assertRaises(ModelError):
            self.app.inference.call(self.scope, "oversize", [{"role": "user", "content": "x" * 24001}], [])
        self.assertEqual(self.model.requests, [])
        self.assertEqual(self.app.calls.inspect("one", self.run), [])

    def test_mismatched_receipt_token_cannot_overwrite_a_reservation(self):
        self.app.calls.reserve(self.scope, "receipt", "hash", 1, self.now)
        wrong = CallScope("one", self.run, self.claim.task_id, "another-token")
        with self.assertRaises(Conflict):
            self.app.calls.record(wrong, "receipt", reply("read_editorial_context", {}), None)
        self.assertEqual(self.app.calls.inspect("one", self.run)[0]["status"], "reserved")


class TransportBoundaryTests(unittest.TestCase):
    def adapter(self, outcome):
        adapter = OpenRouter("fixture-secret-do-not-log")
        class Opener:
            def open(_, request, timeout):
                self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/chat/completions")
                self.assertEqual(timeout, 25)
                self.assertEqual(request.get_header("Authorization"), "Bearer fixture-secret-do-not-log")
                if isinstance(outcome, BaseException):
                    raise outcome
                return io.BytesIO(outcome)
        adapter._opener = Opener()
        return adapter

    def test_http_and_timeout_errors_never_expose_provider_body_or_key(self):
        for failure, code in ((urllib.error.HTTPError("https://provider", 429, "secret body", {}, io.BytesIO(b"secret")), "provider_http_429"),
                              (urllib.error.URLError("secret"), "provider_request_failed"),
                              (TimeoutError("secret"), "provider_request_failed")):
            with self.subTest(code=code), self.assertRaises(ModelError) as error:
                self.adapter(failure).complete({"model": "fixture"})
            self.assertEqual(str(error.exception), code)

    def test_response_limit_and_redirect_policy_are_enforced(self):
        with self.assertRaises(ModelError) as error:
            self.adapter(b"x" * 128001).complete({})
        self.assertEqual(str(error.exception), "provider_response_too_large")
        with self.assertRaises(ModelError):
            NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other-host.invalid")
