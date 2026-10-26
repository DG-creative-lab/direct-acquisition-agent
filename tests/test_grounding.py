import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from acquisition.bootstrap import build
from acquisition.contracts import Conflict, canonical
from acquisition.creative import fact_pack_id, validate_fact_pack, validate_grounded_catalogue
from acquisition.creative.grounding import validate_framing
from acquisition.reasoning import ModelConfig, ModelError
from test_model_copy import FakeModel, reply


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1792886400.0
        self.model = FakeModel()
        self.config = ModelConfig("test/model", max_calls=10)
        self.app = build(self.root / "grounded.sqlite", lambda: self.now, self.model, self.config)
        self.run = self.app.start_model("one", "grounded", size=100)
        self.context_id = self.app.tasks.inspect("one", self.run)["tasks"][0]["inputs"]["context_ids"]["inventory"]
        self.context = self.app.memory.get_context("one", self.context_id)

    def catalogue(self):
        self.app.worker.drain("one", 3)
        return self.app.memory.get_catalogue("one", self.run + ":copy:" + self.context_id)

    def test_exact_sourced_wording_and_all_qualifications_survive_persistence_and_export(self):
        self.app.worker.drain("one")
        state = self.app.tasks.inspect("one", self.run)
        self.assertEqual(state["run"]["status"], "waiting")
        variants = self.app.memory.get_catalogue("one", self.run + ":copy:" + self.context_id)
        self.assertIn("iwoca does not charge an early repayment fee on its Flexi-Loan.", variants[0].opening)
        self.assertIn("this does not mean the loan is free.", variants[0].opening)
        self.assertIn("Loans longer than twelve months may also incur an additional fee.", variants[1].opening)
        for item in variants:
            self.assertIn("Lending is subject to assessment.", item.opening)
            self.assertEqual(item.fact_pack_id, fact_pack_id(self.context["product_facts"]))
            self.assertEqual(item.status, "generated_unreviewed")
            self.assertEqual(json.loads(item.claim_check)["a_verdict"], "pass")
        restarted = build(self.root / "grounded.sqlite", lambda: self.now)
        exported = restarted.export("one", self.run, self.root / "exports")
        evidence = json.loads((exported / "product-evidence.json").read_text())
        self.assertEqual(set(evidence["packs"]), {variants[0].fact_pack_id})
        self.assertEqual(evidence["packs"][variants[0].fact_pack_id]["sources"][0]["url"], "https://www.iwoca.co.uk/flexi-loan")
        self.assertIn(variants[0].opening, (exported / "letters.txt").read_text())

    def test_fact_pack_relationship_and_freshness_mutations_fail(self):
        original = self.context["product_facts"]
        for mutate in (
            lambda p: p.update(sources=[]),
            lambda p: p.update(facts=[]),
            lambda p: p["facts"][0].update(source_id="invented"),
            lambda p: p["facts"][0].update(qualification=""),
            lambda p: p["sources"][0].update(url="https://www.iwoca.co.uk.evil.test/flexi-loan"),
            lambda p: p["sources"][0].update(checked_on="2026-10-24"),
            lambda p: p.update(review_by="2027-10-25"),
            lambda p: p["facts"].append(p["facts"][0].copy()),
        ):
            pack = json.loads(json.dumps(original)); mutate(pack)
            with self.subTest(pack=pack), self.assertRaises(ValueError):
                validate_fact_pack(pack, date(2026, 10, 25))
        validate_fact_pack(original, date(2026, 11, 24))
        for today in (date(2026, 10, 24), date(2026, 11, 25)):
            with self.assertRaises(ValueError):
                validate_fact_pack(original, today)

    def test_generated_product_and_outcome_claims_are_blocked_before_semantic_screen(self):
        invalid = ["A tailored solution for project costs.", "A flexible option for your stock order.",
                   "Get approved for your next project.", "Project funding at £100.",
                   "Stock finance at zero percent.", "Your project will stay on schedule.",
                   "Keep jobs on schedule.", "We know you need stock.",
                   "Would this improve project cash flow?", "Could this give you more control over project costs?",
                   "Project costs with ｆｒｅｅ support.", "Project costs with fr\u200bee support."]
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_framing("Planning project costs?", text, "contractors")
        with self.assertRaises(ValueError):
            validate_framing("Planning your stock order?", "Considering a supplier payment?", "contractors")
        with self.assertRaises(ValueError):
            validate_framing("Planning project costs?", "Project costs " + chr(0x2014) + " when are they due?", "contractors")

    def test_whole_pair_check_cannot_be_reused_after_copy_evidence_or_qualification_changes(self):
        variants = self.catalogue()
        validate_grounded_catalogue(variants, self.context, date(2026, 10, 25))
        for altered in (
            replace(variants[0], headline="Planning a different stock purchase?"),
            replace(variants[0], fact_pack_id="facts_invented"),
            replace(variants[0], fact_id="invented"),
            replace(variants[0], opening=variants[0].opening.replace("this does not mean the loan is free.", "the loan is free.")),
            replace(variants[0], locked_block="Approved for use"),
            replace(variants[0], evidence_ids=()),
            replace(variants[0], claim_check="{}"),
            replace(variants[0], status="approved"),
        ):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                validate_grounded_catalogue((altered, variants[1]), self.context, date(2026, 10, 25))
        verdict = json.loads(variants[0].claim_check); verdict["candidate_hash"] = "other-copy"
        both = tuple(replace(v, claim_check=canonical(verdict)) for v in variants)
        with self.assertRaises(ValueError):
            validate_grounded_catalogue(both, self.context, date(2026, 10, 25))

    def test_semantic_rejection_never_persists_a_catalogue_or_draft(self):
        class Rejecting(FakeModel):
            def complete(self, request):
                result = super().complete(request)
                if request["tools"][0]["function"]["name"] == "record_claim_check":
                    args = json.loads(result["message"]["tool_calls"][0]["function"]["arguments"])
                    args.update(a_verdict="reject", a_reason="Unsupported implication in framing.")
                    return reply("record_claim_check", args)
                return result
        app = build(self.root / "reject.sqlite", lambda: self.now, Rejecting(), self.config)
        run = app.start_model("one", "rejected", size=100)
        app.worker.drain("one")
        state = app.tasks.inspect("one", run)
        self.assertEqual(state["run"]["status"], "failed")
        self.assertEqual(len(app.calls.inspect("one", run)), 5)
        self.assertFalse(any(t["output"] and t["output"].get("draft_id") for t in state["tasks"]))
        context_id = state["tasks"][1]["inputs"]["context_ids"]["contractors"]
        self.assertIsNone(app.memory.get_catalogue("one", run + ":copy:" + context_id))

    def test_missing_or_swapped_semantic_coverage_fails_closed(self):
        class WrongCheck(FakeModel):
            def complete(self, request):
                result = super().complete(request)
                if request["tools"][0]["function"]["name"] == "record_claim_check":
                    args = json.loads(result["message"]["tool_calls"][0]["function"]["arguments"])
                    args["candidate_hash"] = "a-different-valid-candidate"
                    return reply("record_claim_check", args)
                return result
        app = build(self.root / "swap.sqlite", lambda: self.now, WrongCheck(), self.config)
        run = app.start_model("one", "swap", size=100); app.worker.drain("one")
        self.assertEqual(app.tasks.inspect("one", run)["run"]["status"], "failed")

    def test_expiry_between_generation_and_draft_blocks_persistence(self):
        self.catalogue()
        self.now += 31 * 86400
        self.app.worker.drain("one")
        state = self.app.tasks.inspect("one", self.run)
        self.assertEqual(state["run"]["status"], "failed")
        self.assertFalse(any(t["output"] and t["output"].get("draft_id") for t in state["tasks"]))
        self.assertEqual(len(self.model.requests), 6)

    def test_partial_inference_recovery_reuses_critic_receipt_without_another_call(self):
        from acquisition.creative import GroundedCopyAgent
        from acquisition.reasoning import CallScope
        self.app.worker.tick("one")
        claim = self.app.tasks.claim("one", self.now, 180)
        original = self.app.memory.put_catalogue
        def crash(*args):
            raise OSError("Simulated failure before creative persistence")
        self.app.memory.put_catalogue = crash
        context_id = claim.inputs["context_ids"]["contractors"]
        with self.assertRaises(OSError):
            GroundedCopyAgent(self.app.inference, self.app.memory).generate(
                CallScope("one", self.run, claim.task_id, claim.token), context_id, date(2026, 10, 25))
        self.app.memory.put_catalogue = original
        self.now += 181
        self.app.worker.drain("one")
        self.assertEqual(self.app.tasks.inspect("one", self.run)["run"]["status"], "waiting")
        self.assertEqual(len(self.model.requests), 6)

    def test_legacy_generated_serialization_omits_new_fields(self):
        from acquisition.creative import Creative, creative_record
        old = Creative("legacy", "inventory", "A", "Opening", headline="Headline", evidence_ids=("old",))
        self.assertFalse({"fact_id", "fact_pack_id", "claim_check"} & creative_record(old).keys())
        self.assertIn("fact_id", creative_record(replace(old, fact_id="new")))

    def test_default_model_commands_use_gpt_oss_with_required_tools_and_bounded_calls(self):
        from acquisition.__main__ import main
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        with patch("acquisition.__main__.OpenRouter", return_value=self.model), \
             patch("acquisition.__main__.openrouter_key", return_value="fake-not-a-key"), \
             patch("acquisition.__main__.build", side_effect=lambda path, **kwargs: build(path, clock=lambda: self.now, **kwargs)), \
             patch("sys.argv", ["acquisition", "--db", str(self.root / "cli.sqlite"), "create-model", "--size", "100"]), \
             redirect_stdout(StringIO()) as output:
            main()
        run = json.loads(output.getvalue())["run_id"]
        app = build(self.root / "cli.sqlite")
        config = app.tasks.inspect("demo-org", run)["tasks"][0]["inputs"]["model_config"]
        self.assertEqual(config["model"], "openai/gpt-oss-120b")
        self.assertEqual(config["max_calls"], 10)
        self.assertTrue(config["force_tool_choice"])

    def test_a_v3_capability_cannot_downgrade_its_inputs_to_skip_grounding(self):
        from acquisition.runtime import TaskSpec
        inputs = self.app.tasks.inspect("one", self.run)["tasks"][0]["inputs"]
        inputs["workflow_version"] = "monthly-mail/v2"
        run = self.app.tasks.create("two", "downgrade", [TaskSpec("audiences.inspect_model.v3", inputs)], self.now)
        self.app.worker.drain("two")
        self.assertEqual(self.app.tasks.inspect("two", run)["run"]["status"], "failed")
        self.assertEqual(self.model.requests, [])

    def test_legacy_v2_runs_remain_explicitly_ungrounded_and_replayable(self):
        from acquisition.runtime import TaskSpec
        state = self.app.tasks.inspect("one", self.run)
        specs = [TaskSpec(t["capability"].replace(".v3", ".v2"), t["inputs"] | {"workflow_version": "monthly-mail/v2"})
                 for t in state["tasks"]]
        self.app.tasks.cancel("one", self.run, self.now)
        run = self.app.tasks.create("one", "legacy-v2", specs, self.now)
        self.app.worker.drain("one")
        final = self.app.tasks.inspect("one", run)
        self.assertEqual(final["run"]["status"], "waiting")
        self.assertEqual(len(self.model.requests), 4)
        draft = self.app.drafts.get("one", final["tasks"][-1]["output"]["draft_id"])
        self.assertTrue(all("fact_pack_id" not in c for c in draft.manifest["creatives"]))

    def test_critic_evaluation_reports_failures_and_still_executes_independent_cases(self):
        from scripts.evaluate_claim_screen import main
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch
        from datetime import datetime, timezone
        class FirstUnavailable(FakeModel):
            def complete(self, request):
                if not self.requests:
                    self.requests.append(request)
                    raise ModelError("provider_request_failed")
                return super().complete(request)
        model = FirstUnavailable()
        with patch("scripts.evaluate_claim_screen.OpenRouter", return_value=model), \
             patch("scripts.evaluate_claim_screen.openrouter_key", return_value="fixture-not-a-key"), \
             patch("scripts.evaluate_claim_screen.datetime") as clock, \
             patch("sys.argv", ["evaluate", "--db", str(self.root / "eval.sqlite")]), \
             redirect_stdout(StringIO()) as output:
            clock.now.return_value = datetime(2026, 10, 25, tzinfo=timezone.utc)
            with self.assertRaises(SystemExit) as exit:
                main()
            self.assertEqual(exit.exception.code, 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(len(model.requests), 4)
        self.assertEqual(len(report["incomplete_cases"]), 1)
        self.assertEqual(len(report["cases"]), 3)
        self.assertEqual(report["calls_without_reported_cost"], 1)
