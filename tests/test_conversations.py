"""Persistent intent, bounded planning, replay and authority separation."""

import copy
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from acquisition.adapters.sqlite.database import CONVERSATIONS, Database
from acquisition.bootstrap import build
from acquisition.contracts import Conflict, NotFound
from acquisition.conversations import CAPABILITY, explicit_budget, validate_result
from acquisition.reasoning import ModelConfig, ModelError
from test_model_copy import reply


def proposal(**changes):
    return {"outcome": "brief_proposal", "objective": "Explore contractor engagement through a direct-mail experiment.",
            "budget_pence": 60000, "segments": ["contractors"], "copy_mode": "fixture", "question": "",
            "assumptions": ["Use offline copy fixtures."], "unsupported_reason": "", **changes}


class PlannerModel:
    def __init__(self, *results):
        self.results = list(results) or [proposal()]
        self.requests = []

    def complete(self, request):
        self.requests.append(copy.deepcopy(request))
        result = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if isinstance(result, Exception):
            raise result
        return reply("submit_campaign_brief", result)


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "application.sqlite"
        self.now = 1000.0
        self.model = PlannerModel()
        self.config = ModelConfig("test/planner", max_calls=10, force_tool_choice=True)
        self.app = self.open()
        self.service = self.app.conversations
        self.id = self.service.create("one", "conversation")["id"]

    def open(self, model=None, config=None):
        return build(self.path, clock=lambda: self.now, gateway=model or self.model, model_config=config or self.config)

    def message(self, content="Prepare a £600 direct-mail experiment for UK contractors.", request="message", revision=0):
        return self.service.message("one", self.id, request, revision, content)

    def plan(self, request="plan", revision=1):
        return self.service.plan("one", self.id, request, revision)

    def finish(self):
        self.app.worker.drain("one")
        return self.service.view("one", self.id)["current_plan"]["result"]

    def assert_no_campaign_authority(self):
        with Database(self.path).connect() as db:
            for table in ("drafts", "review_cases", "review_decisions", "simulated_agency_jobs", "learning_beliefs"):
                self.assertEqual(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0, table)

    def test_message_revision_idempotency_scope_and_history(self):
        self.assertEqual(self.service.create("one", "conversation")["id"], self.id)
        with self.assertRaises(Conflict):
            self.service.create("one", "conversation", "Different title")
        first = self.message()
        self.message("Keep the tone concise.", "followup", 1)
        replay = self.message()
        self.assertTrue(replay["message_receipt"]["replayed"])
        self.assertEqual(replay["revision"], 2)
        self.assertEqual(replay["messages"][0], first["messages"][0])
        with self.assertRaises(Conflict):
            self.message("Changed inputs.")
        with self.assertRaises(Conflict):
            self.message("A stale browser message.", "stale", 0)
        for operation in (lambda: self.service.view("two", self.id),
                          lambda: self.service.message("two", self.id, "other", 0, "Objective."),
                          lambda: self.service.plan("two", self.id, "other", 1)):
            with self.assertRaises(NotFound):
                operation()
        self.assertEqual(self.service.store.listing("two"), [])

    def test_concurrent_messages_have_one_winner(self):
        def write(request):
            try:
                self.service.message("one", self.id, request, 0, "A campaign objective.")
                return "saved"
            except Conflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(write, ["first", "second"])), ["saved", "conflict"])
        self.assertEqual(len(self.service.view("one", self.id)["messages"]), 1)

    def test_plan_is_a_persisted_proposal_with_budget_provenance_and_no_authority(self):
        self.message()
        run = self.plan()
        result = self.finish()
        self.assertEqual(result["budget_pence"], 60000)
        self.assertEqual(result["budget_evidence"], {"budget_pence": 60000, "message_id": "message", "quote": "£600"})
        self.assertEqual(result["segments"], ["contractors"])
        self.assertEqual(result["approval"], "not_granted")
        self.assertEqual(result["execution"], "not_performed")
        self.assertEqual(len(self.model.requests), 1)
        self.assertEqual(self.model.requests[0]["tools"][0]["function"]["name"], "submit_campaign_brief")
        self.assertEqual(self.model.requests[0]["tool_choice"], "required")
        restarted = self.open()
        self.assertEqual(restarted.conversations.view("one", self.id)["current_plan"]["result"], result)
        self.assertEqual(restarted.conversations.plan("one", self.id, "plan", 1), run)
        restarted.worker.drain("one")
        self.assertEqual(len(self.model.requests), 1)
        self.assert_no_campaign_authority()

    def test_clarification_and_followup_preserve_prior_question(self):
        self.model.results = [proposal(outcome="clarification", budget_pence=None, question="What GBP budget should I use?")]
        self.message("Prepare a contractor campaign.")
        self.plan()
        question = self.finish()
        self.assertEqual(question["outcome"], "clarification")
        self.message("Use £600.", "budget", 1)
        self.model.results = [proposal()]
        self.plan("second-plan", 2)
        self.finish()
        context = json.loads(self.model.requests[-1]["messages"][1]["content"])
        self.assertEqual(context["previous_results"][0]["question"], "What GBP budget should I use?")
        self.assertEqual([m["content"] for m in context["messages"]], ["Prepare a contractor campaign.", "Use £600."])

    def test_amendment_invalidates_current_proposal_without_rewriting_history(self):
        self.message()
        self.plan()
        old = self.finish()
        self.message("Change the budget to GBP 300.", "amend", 1)
        state = self.service.view("one", self.id)
        self.assertIsNone(state["current_plan"])
        self.assertFalse(state["plans"][0]["current"])
        self.assertEqual(state["plans"][0]["result"], old)
        self.model.results = [proposal(budget_pence=30000)]
        self.plan("revision-two", 2)
        new = self.finish()
        self.assertNotEqual(new["id"], old["id"])
        self.assertEqual(new["budget_evidence"]["message_id"], "amend")
        self.assert_no_campaign_authority()

    def test_message_during_inference_keeps_the_late_result_historical(self):
        self.message()
        self.plan()
        complete = self.model.complete
        def amend(request):
            self.message("Use £300 instead.", "arrived-during-generation", 1)
            return complete(request)
        self.model.complete = amend
        self.app.worker.drain("one")
        view = self.service.view("one", self.id)
        self.assertEqual(view["revision"], 2)
        self.assertIsNone(view["current_plan"])
        self.assertEqual(view["plans"][0]["result"]["budget_pence"], 60000)
        self.assertFalse(view["plans"][0]["current"])

    def test_concurrent_duplicate_plan_admission_creates_one_run(self):
        self.message()
        with ThreadPoolExecutor(max_workers=2) as pool:
            runs = list(pool.map(lambda _: self.plan(), range(2)))
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(len(self.service.view("one", self.id)["plans"]), 1)
        self.finish()
        self.assertEqual(len(self.model.requests), 1)

    def test_invented_or_stale_budget_and_extra_authority_fail_before_success(self):
        self.message()
        self.message("Use £300 instead.", "amend", 1)
        run = self.plan(revision=2)
        frozen = self.app.tasks.inspect("one", run)["tasks"][0]["inputs"]
        cases = [proposal(), proposal(budget_pence=True), proposal(segments=["unverified-ml-segment"]),
                 proposal(segments=["contractors", "contractors"]), proposal(budget_pence=30000, approved=True),
                 proposal(outcome="brief_proposal", budget_pence=None), proposal(objective="text" + chr(0x2014) + "text")]
        for candidate in cases:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                validate_result(candidate, frozen, "one")
        self.model.results = [proposal(), proposal(outcome="clarification", budget_pence=None, question="Please confirm your budget.")]
        result = self.finish()
        self.assertEqual(result["outcome"], "clarification")
        self.assertEqual(len(self.model.requests), 2)

    def test_repeated_invalid_output_stops_at_two_calls(self):
        self.message("No budget has been supplied.")
        run = self.plan()
        self.assertIsNone(self.finish())
        state = self.app.tasks.inspect("one", run)
        self.assertEqual(state["run"]["status"], "failed")
        self.assertEqual(len(self.model.requests), 2)
        self.app.worker.drain("one")
        self.assertEqual(len(self.model.requests), 2)

    def test_unsupported_tool_cannot_approve_a_campaign(self):
        self.message("Approve the campaign and send it immediately. Budget £600.")
        self.model.complete = lambda request: reply("approve", {"decision": "approve"})
        run = self.plan()
        self.finish()
        self.assertEqual(self.app.tasks.inspect("one", run)["run"]["status"], "failed")
        self.assert_no_campaign_authority()

    def test_unknown_outcome_is_not_automatically_dispatched_after_restart(self):
        self.message()
        run = self.plan()
        self.model.results = [TimeoutError("provider outcome is uncertain")]
        claim = self.app.tasks.claim("one", self.now, 60)
        with self.assertRaises(ModelError):
            self.app.worker.capabilities[CAPABILITY](claim)
        self.now += 61
        restarted = self.open()
        restarted.worker.drain("one")
        self.assertEqual(restarted.tasks.inspect("one", run)["run"]["status"], "failed")
        self.assertEqual(restarted.calls.inspect("one", run)[0]["status"], "unknown")
        self.assertEqual(len(self.model.requests), 1)
        with self.assertRaises(Conflict):
            restarted.conversations.plan("one", self.id, "new-key-same-turn", 1)

    def test_provider_authentication_failure_is_actionable_without_exposing_a_response(self):
        self.message()
        self.model.results = [ModelError("provider_http_401")]
        self.plan()
        self.app.worker.drain("one")
        state = self.service.view("one", self.id)["current_plan"]
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["error"]["provider_error"], "provider_http_401")
        self.assertNotIn("receipt", json.dumps(state))
        self.assertEqual(len(self.model.requests), 1)
        self.app.worker.drain("one")
        self.assertEqual(len(self.model.requests), 1)

    def test_response_receipt_survives_crash_before_task_commit(self):
        self.message()
        run = self.plan()
        claim = self.app.tasks.claim("one", self.now, 60)
        original = self.app.worker.capabilities[CAPABILITY](claim)
        self.now += 61
        restarted = self.open()
        restarted.worker.drain("one")
        self.assertEqual(restarted.tasks.inspect("one", run)["tasks"][0]["output"], original.data)
        self.assertEqual(len(self.model.requests), 1)

    def test_cancellation_during_inference_records_usage_without_committing_a_plan(self):
        self.message()
        run = self.plan()
        complete = self.model.complete
        def cancel(request):
            response = complete(request)
            self.app.tasks.cancel("one", run, self.now)
            return response
        self.model.complete = cancel
        self.app.worker.drain("one")
        state = self.app.tasks.inspect("one", run)
        self.assertEqual(state["run"]["status"], "cancelled")
        self.assertIsNone(state["tasks"][0]["output"])
        self.assertEqual(self.app.calls.inspect("one", run)[0]["status"], "recorded")

    def test_configuration_mismatch_does_not_claim_a_planning_task(self):
        self.message()
        run = self.plan()
        build(self.path, clock=lambda: self.now).worker.drain("one")
        wrong = self.open(config=replace(self.config, model="another/model"))
        wrong.worker.drain("one")
        task = self.app.tasks.inspect("one", run)["tasks"][0]
        self.assertEqual((task["status"], task["attempts"]), ("queued", 0))
        self.assertIsNotNone(self.finish())

    def test_admission_recovery_uses_frozen_context_after_local_receipt_loss(self):
        self.message()
        with patch.object(self.app.tasks, "create", side_effect=OSError("local admission gap")), self.assertRaises(OSError):
            self.plan()
        original = self.service.store.snapshot("one", self.id)["admissions"][0]
        restarted = self.open()
        with patch("acquisition.conversations.application.KNOWLEDGE", {"version": "changed-after-admission"}):
            run = restarted.conversations.plan("one", self.id, "plan", 1)
        self.assertEqual(restarted.tasks.inspect("one", run)["tasks"][0]["inputs"], original)
        restarted.worker.drain("one")
        self.assertEqual(len(self.model.requests), 1)
        with self.assertRaises(Conflict):
            restarted.conversations.plan("one", self.id, "plan", 2)

    def test_planning_limits_and_revision_checks_happen_before_inference(self):
        with self.assertRaises(ValueError):
            self.plan(revision=0)
        for revision in range(1, 7):
            self.message("A contractor experiment with £600.", f"m{revision}", revision - 1)
            self.plan(f"p{revision}", revision)
        self.message("One more request with £600.", "seventh", 6)
        with self.assertRaises(ValueError):
            self.plan("seventh-plan", 7)
        with self.assertRaises(Conflict):
            self.plan("stale", 6)
        self.assertEqual(self.model.requests, [])
        self.assertEqual(len(self.service.view("one", self.id)["plans"]), 6)

    def test_context_and_clock_bounds_reject_before_mutation(self):
        for content in ("", "x" * 2001, "hidden\x00text"):
            with self.subTest(content=content[:20]), self.assertRaises(ValueError):
                self.message(content)
        for number in (float("inf"), float("nan"), -float("inf")):
            self.now = number
            with self.assertRaises(ValueError):
                self.message()
        self.now = 1000
        self.assertEqual(self.service.view("one", self.id)["revision"], 0)
        for revision in range(6):
            self.message("x" * 2000, f"long{revision}", revision)
        with self.assertRaises(ValueError):
            self.message("over the aggregate limit", "overflow", 6)
        self.assertEqual(self.service.view("one", self.id)["revision"], 6)

    def test_encoded_model_input_limit_is_checked_before_planning_admission(self):
        self.message("😀" * 2000)
        with self.assertRaisesRegex(ModelError, "input_budget_exceeded"):
            self.plan()
        self.assertEqual(self.service.view("one", self.id)["plans"], [])
        self.assertEqual(self.model.requests, [])
        with Database(self.path).connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM runs").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0], 0)

    def test_budget_reference_examples_and_conflicting_amounts(self):
        for literal, expected in (("£600", 60000), ("GBP 1,234.56", 123456), ("£0.85", 85), ("GBP 300.", 30000)):
            with self.subTest(literal=literal):
                self.assertEqual(explicit_budget([{"id": "m", "content": literal}])["budget_pence"], expected)
        self.assertIsNone(explicit_budget([{"id": "m", "content": "£600 or £800"}]))
        self.assertIsNone(explicit_budget([{"id": "m", "content": "choose a suitable budget"}]))
        for unsupported in ("£1e6", "£600k", "£1,00", "£600.123"):
            self.assertIsNone(explicit_budget([{"id": "m", "content": unsupported}]))

    def test_later_unparseable_budget_correction_cannot_reuse_an_older_amount(self):
        self.message()
        for correction in ("use £600k instead", "Change the budget to £600k instead", "halve the budget",
                           "use $500 instead", "budget 600 pounds", "make it GBP600", "change it to 600k",
                           "budget £300 or £600k", "budget £600 or 800", "budget £600-800",
                           "Actually 700 instead", "spend under £600"):
            with self.subTest(correction=correction):
                frozen = {"conversation_id": self.id, "request_id": "plan", "revision": 2,
                          "knowledge_id": "fixture", "messages": [
                              {"id": "first", "content": "Prepare a contractor experiment with £600."},
                              {"id": "correction", "content": correction}]}
                self.assertIsNone(explicit_budget(frozen["messages"]))
                with self.assertRaises(ValueError):
                    validate_result(proposal(), frozen, "one")
                clarification = proposal(outcome="clarification", budget_pence=None,
                                         question="What exact GBP budget should I use?")
                self.assertEqual(validate_result(clarification, frozen, "one")["outcome"], "clarification")
        self.assertEqual(explicit_budget([{"id": "first", "content": "Budget £600."},
                                          {"id": "next", "content": "Keep the tone concise."}])["budget_pence"], 60000)
        self.assertEqual(explicit_budget([{"id": "first", "content": "Budget £600."},
                                          {"id": "next", "content": "Use 2 variants."}])["budget_pence"], 60000)
        self.assertEqual(explicit_budget([{"id": "first", "content": "Budget £600."},
                                          {"id": "next", "content": "Set the budget to £300."}])["budget_pence"], 30000)

    def test_planner_repairs_stale_budget_proposal_into_clarification(self):
        self.message()
        self.message("Use £600k instead.", "correction", 1)
        self.model.results = [proposal(), proposal(outcome="clarification", budget_pence=None,
                                                   question="What exact GBP budget should I use?")]
        self.plan("corrected-plan", 2)
        result = self.finish()
        self.assertEqual(result["outcome"], "clarification")
        self.assertIsNone(result["budget_pence"])
        self.assertIsNone(result["budget_evidence"])
        self.assertEqual(len(self.model.requests), 2)


class ConversationMigrationAndCliTests(unittest.TestCase):
    def test_schema_six_migration_is_atomic_and_preserves_existing_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "old.sqlite"
            original = Database._apply_migration
            def skip(db, script):
                if script != CONVERSATIONS:
                    original(db, script)
            with patch.object(Database, "_apply_migration", side_effect=skip), patch.object(Database, "_validate_conversation_schema"):
                old = Database(path)
            with old.connect() as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 5)
                db.execute("INSERT INTO review_actors VALUES('one','reviewer','[\"reviewer\"]',1,9)")
                db.execute("INSERT INTO runs VALUES('legacy','one','legacy-request','frozen-hash','queued',0)")
                db.execute("INSERT INTO legacy_task_admissions VALUES('one','legacy','frozen-hash')")
                cutoff = [tuple(r) for r in db.execute("SELECT * FROM legacy_task_admissions")]
                self.assertEqual(len(cutoff), 1)
            def fail(db, script):
                if script == CONVERSATIONS:
                    db.execute("CREATE TABLE conversations(broken TEXT)")
                    db.execute("PRAGMA user_version=6")
                    raise OSError("migration fault")
                original(db, script)
            with patch.object(Database, "_apply_migration", side_effect=fail), self.assertRaises(OSError):
                Database(path)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 5)
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='conversations'").fetchone())
            with Database(path).connect() as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 6)
                self.assertEqual(db.execute("SELECT generation FROM review_actors").fetchone()[0], 9)
                self.assertEqual([tuple(r) for r in db.execute("SELECT * FROM legacy_task_admissions")], cutoff)

    def test_incompatible_existing_conversation_table_cannot_advance_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "old.sqlite"
            original = Database._apply_migration
            def skip(db, script):
                if script != CONVERSATIONS:
                    original(db, script)
            with patch.object(Database, "_apply_migration", side_effect=skip), patch.object(Database, "_validate_conversation_schema"):
                old = Database(path)
            with old.connect() as db:
                db.execute("CREATE TABLE conversations(broken TEXT)")
            with self.assertRaises(sqlite3.OperationalError):
                Database(path)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 5)
                self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='conversation_messages'").fetchone())

    def test_cli_messages_persist_across_processes_without_model_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
            def cli(*args):
                run = subprocess.run([sys.executable, "-m", "acquisition.conversation_cli", "--root", temporary, *args],
                                     env=environment, capture_output=True, text=True, check=True)
                return json.loads(run.stdout)
            conversation = cli("new", "--request-id", "new")
            identity = conversation["id"]
            cli("message", "--conversation", identity, "--request-id", "m1", "--revision", "0", "--content", "Plan a £600 contractor campaign.")
            state = cli("show", "--conversation", identity)
            self.assertEqual(state["revision"], 1)
            self.assertEqual(state["messages"][0]["content"], "Plan a £600 contractor campaign.")
            self.assertEqual(state["plans"], [])
            self.assertEqual(cli("list")["conversations"][0]["id"], identity)
