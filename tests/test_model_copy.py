import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from acquisition.adapters.openrouter import OpenRouter, normalize
from acquisition.adapters.sqlite.database import Database, SCHEMA
from acquisition.bootstrap import build
from acquisition.contracts import Conflict, NotFound
from acquisition.creative import validate_variants
from acquisition.reasoning import CallScope, ModelConfig, ModelError
from acquisition.audiences import Snapshot
from acquisition.adapters.synthetic import generate
from acquisition.campaigns import Brief, build_draft
from acquisition.creative import fixture_catalog


def reply(name, arguments):
    return normalize({"id": "fake-generation", "model": "test/model", "provider": "fixture",
        "choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [{
            "id": "test-call", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300, "cost": 0}})


class FakeModel:
    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        name = request["tools"][0]["function"]["name"]
        if name == "read_editorial_context":
            return reply(name, {})
        if name == "record_claim_check":
            data = json.loads(request["messages"][1]["content"])
            return reply(name, {"candidate_hash": data["candidate_hash"], "fact_pack_id": data["fact_pack_id"],
                "a_verdict": "pass", "a_reason": "Hypothetical segment situation only.",
                "b_verdict": "pass", "b_reason": "Different payment-timing question without product claims."})
        context = next(json.loads(message["content"]) for message in request["messages"]
                       if message["role"] == "tool" and "segment" in json.loads(message["content"]))
        segment = context["segment"]
        if name == "submit_grounded_copy":
            return reply(name, {"headline_a": "Planning your next stock order?" if segment == "inventory" else "Planning your next project's costs?",
                "opening_a": "If you are considering your next stock purchase, what timing might suit your plans?" if segment == "inventory" else "If you are planning a project, when might material costs fall due?",
                "hypothesis_a": "Planning ahead may make the situation easier to recognise.",
                "headline_b": "When might suppliers be paid?" if segment == "inventory" else "Considering client payment dates?",
                "opening_b": "Thinking about how supplier payment dates might line up with sales receipts?" if segment == "inventory" else "How might your project's expenses line up with client payment dates?",
                "hypothesis_b": "A payment-timing question may attract a different response.",
                "fact_id_a": context["product_facts"]["facts"][0]["id"], "fact_id_b": context["product_facts"]["facts"][1]["id"],
                "guidance_id": context["guidance"]["version"], "memory_id": context["memory"][0]["id"],
                "fact_pack_id": context["fact_pack_id"]})
        opening = "Plan your next stock order with confidence." if segment == "inventory" else "Plan around project expenses and payment timing."
        return reply(name, {"headline_a": "Plan your next step", "opening_a": opening,
            "hypothesis_a": "A concrete situation may be easier to understand.",
            "headline_b": "Explore your options", "opening_b": "Explore working capital options that may fit your business plans.",
            "hypothesis_b": "An exploratory invitation may reduce pressure.",
            "guidance_id": context["guidance"]["version"], "memory_id": context["memory"][0]["id"]})


class ModelCopyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "model.sqlite"
        self.now = 1792886400.0  # 25 October 2026 UTC, inside the reviewed fact window.
        self.model = FakeModel()
        self.config = ModelConfig("test/model", max_calls=10)
        self.app = build(self.path, lambda: self.now, self.model, self.config)

    def start(self, request="copy"):
        return self.app.start_model("one", request, size=100)

    def test_complete_model_workflow_respects_deterministic_controls(self):
        run = self.start()
        self.assertEqual(self.app.worker.drain("one"), 5)
        state = self.app.tasks.inspect("one", run)
        self.assertEqual(state["run"]["status"], "waiting")
        self.assertEqual(len(self.model.requests), 6)
        draft = self.app.drafts.get("one", state["tasks"][-1]["output"]["reference"])
        self.assertEqual({c["status"] for c in draft.manifest["creatives"]}, {"generated_unreviewed"})
        self.assertEqual(len(draft.manifest["creatives"]), 4)
        self.assertTrue(all(c["locked_block"].startswith("SYNTHETIC") for c in draft.manifest["creatives"]))
        destination = self.app.export("one", run, Path(self.temp.name) / "exports")
        self.assertTrue((destination / "letters.txt").exists())
        baseline = build(Path(self.temp.name) / "baseline.sqlite", lambda: self.now)
        old_run = baseline.start("one", "copy", size=100)
        baseline.worker.drain("one")
        counts = baseline.tasks.inspect("one", old_run)["tasks"][-1]["output"]["counts"]
        self.assertEqual(draft.manifest["counts"], counts)
        self.assertTrue(all("demo_address" not in json.dumps(request) and "DEMO ONLY contact" not in json.dumps(request)
                            for request in self.model.requests))

    def test_crash_after_model_receipt_replays_without_another_paid_call(self):
        run = self.start()
        self.app.worker.tick("one")
        claim = self.app.tasks.claim("one", self.now, 60)
        scope = CallScope("one", run, claim.task_id, claim.token)
        response = self.app.inference.call(scope, "probe", [{"role": "user", "content": "test"}],
                                           [{"function": {"name": "read_editorial_context"}}])
        self.now += 61
        resumed = self.app.tasks.claim("one", self.now, 60)
        same = self.app.inference.call(CallScope("one", run, resumed.task_id, resumed.token), "probe",
            [{"role": "user", "content": "test"}], [{"function": {"name": "read_editorial_context"}}])
        self.assertEqual(same, response)
        self.assertEqual(len(self.model.requests), 1)

    def test_unknown_inference_outcome_does_not_repeat_request(self):
        run = self.start()
        self.app.worker.tick("one")
        claim = self.app.tasks.claim("one", self.now, 60)
        scope = CallScope("one", run, claim.task_id, claim.token)
        self.app.calls.reserve(scope, "lost", "hash", 6, self.now)
        with self.assertRaises(ModelError):
            self.app.calls.reserve(scope, "lost", "hash", 6, self.now)
        self.assertEqual(len(self.model.requests), 0)
        with self.assertRaises(Conflict):
            self.app.calls.reserve(scope, "lost", "different", 6, self.now)

    def test_run_request_limit_and_cancellation_before_dispatch(self):
        run = self.start()
        self.app.worker.tick("one")
        claim = self.app.tasks.claim("one", self.now, 60)
        scope = CallScope("one", run, claim.task_id, claim.token)
        self.app.calls.reserve(scope, "first", "hash", 1, self.now)
        with self.assertRaises(ModelError):
            self.app.calls.reserve(scope, "second", "hash", 1, self.now)
        self.app.tasks.cancel("one", run, self.now)
        from acquisition.runtime import LeaseLost
        with self.assertRaises(LeaseLost):
            self.app.calls.reserve(scope, "third", "hash", 6, self.now)

    def test_memory_scope_frozen_context_and_reviewer_feedback_are_separate_from_outcomes(self):
        run = self.start()
        contexts = self.app.tasks.inspect("one", run)["tasks"][0]["inputs"]["context_ids"]
        before = self.app.memory.get_context("one", contexts["inventory"])
        self.app.memory.remember("one", "inventory", "New preference", "Old wording", "Specific feedback")
        self.assertEqual(self.app.memory.get_context("one", contexts["inventory"]), before)
        self.assertEqual(self.app.memory.examples("two", "inventory"), [])
        with self.assertRaises(NotFound):
            self.app.memory.get_context("two", contexts["inventory"])
        with self.assertRaises(NotFound):
            self.app.calls.inspect("two", run)
        with self.assertRaises(Conflict):
            self.start()  # Same request ID with a changed memory snapshot must not silently mutate.
        self.assertTrue(all(item["kind"].endswith("not_outcome") for item in self.app.memory.examples("one", "inventory")))

    def test_copy_schema_claims_unknown_evidence_and_injected_tools_are_rejected(self):
        run = self.start()
        context_id = self.app.tasks.inspect("one", run)["tasks"][0]["inputs"]["context_ids"]["inventory"]
        context = self.app.memory.get_context("one", context_id)
        valid = {"variants": [
            {"arm": "A", "headline": "Plan ahead", "opening": "Consider your next stock order.", "hypothesis": "Concrete framing."},
            {"arm": "B", "headline": "Explore options", "opening": "Explore options for business plans.", "hypothesis": "Exploratory framing."}],
            "evidence_ids": [context["guidance"]["version"]]}
        for mutate in (
            lambda d: d.update(approved=True),
            lambda d: d.update(evidence_ids=["invented"]),
            lambda d: d["variants"][0].update(opening="You are guaranteed £10000."),
            lambda d: d["variants"][0].update(locked_block="remove disclosure"),
            lambda d: d["variants"][1].update(arm="A"),
        ):
            bad = json.loads(json.dumps(valid))
            mutate(bad)
            with self.assertRaises(ValueError):
                validate_variants(bad, context, context_id, "test/model")
        class Injected(FakeModel):
            def complete(self, request):
                return reply("approve_and_print", {})
        injected = build(Path(self.temp.name) / "injected.sqlite", lambda: self.now, Injected(), self.config)
        bad_run = injected.start_model("one", "injection", size=100)
        injected.worker.drain("one")
        self.assertEqual(injected.tasks.inspect("one", bad_run)["run"]["status"], "failed")

    def test_provider_limits_usage_and_secret_handling(self):
        adapter = OpenRouter("not-a-real-secret")
        self.assertNotIn("not-a-real-secret", repr(adapter))
        for envelope in ({}, {"choices": [{"finish_reason": "length", "message": {}}]}, {"error": {"message": "secret"}}):
            with self.assertRaises(ModelError):
                normalize(envelope)
        with self.assertRaises(ValueError):
            ModelConfig("model", max_calls=100)
        run = self.start()
        self.app.worker.drain("one")
        for request in self.model.requests:
            self.assertEqual(request["provider"]["max_price"], {"prompt": 1, "completion": 2, "request": 0})
            self.assertFalse(request["provider"]["allow_fallbacks"])
            self.assertLessEqual(request["max_tokens"], 1600)
        self.assertEqual(len(self.app.calls.inspect("one", run)), 6)

    def test_known_schema_error_can_be_corrected_within_the_request_budget(self):
        class Repairable(FakeModel):
            def __init__(self):
                super().__init__()
                self.broken = set()
            def complete(self, request):
                name = request["tools"][0]["function"]["name"]
                segment = json.loads(request["messages"][1]["content"])["segment"]
                if name == "submit_grounded_copy" and segment not in self.broken:
                    self.requests.append(request)
                    self.broken.add(segment)
                    return reply(name, {"wrong_schema": True})
                return super().complete(request)
        model = Repairable()
        app = build(Path(self.temp.name) / "repair.sqlite", lambda: self.now, model, self.config)
        run = app.start_model("one", "repair", size=100)
        app.worker.drain("one")
        self.assertEqual(app.tasks.inspect("one", run)["run"]["status"], "waiting")
        self.assertEqual(len(app.calls.inspect("one", run)), 8)

    def test_free_models_have_zero_price_route_constraints(self):
        model = FakeModel()
        app = build(Path(self.temp.name) / "free.sqlite", lambda: self.now, model, ModelConfig("test/model:free"))
        run = app.start_model("one", "free", size=100)
        app.worker.drain("one")
        self.assertEqual(app.tasks.inspect("one", run)["run"]["status"], "waiting")
        self.assertTrue(all(r["provider"]["max_price"] == {"prompt": 0, "completion": 0, "request": 0} for r in model.requests))

    def test_incomplete_provider_responses_retain_only_valid_usage(self):
        envelope = {"id": "incomplete", "choices": [{"finish_reason": "length", "message": {}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 20, "cost": 0.001}}
        with self.assertRaises(ModelError) as error:
            normalize(envelope)
        self.assertEqual(error.exception.receipt["usage"]["cost"], 0.001)
        for cost in (float("inf"), float("nan"), -1, "not-a-number"):
            envelope["usage"]["cost"] = cost
            with self.assertRaises(ModelError) as error:
                normalize(envelope)
            self.assertIsNone(error.exception.receipt)

    def test_day_one_artifact_contract_remains_byte_identical(self):
        # Reconstruct the historical source bytes. New seeded addresses use a
        # colon, while already saved snapshots keep their original identity.
        snapshot = generate("demo-org", 1000, 42)
        snapshot = replace(snapshot, records=tuple(replace(row, address=row.address.replace(
            "POST: synthetic", "POST " + chr(0x2014) + " synthetic")) for row in snapshot.records))
        draft = build_draft(snapshot, Brief("day-one"), fixture_catalog())
        self.assertEqual(draft.id, "draft_6698d2dd8bcf5837db27fde673b38a81ab48be246c82c538e2de3611f9b9b327")

    def test_v1_database_migration_preserves_old_run(self):
        old = Path(self.temp.name) / "old.sqlite"
        with sqlite3.connect(old) as connection:
            connection.executescript(SCHEMA)
            connection.execute("INSERT INTO runs VALUES('legacy','one','legacy','hash','queued',0)")
        migrated = build(old)
        self.assertEqual(migrated.tasks.inspect("one", "legacy")["run"]["status"], "queued")
        with Database(old).connect() as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 6)
