"""Independent counts, real SQLite faults, scope, maturity and recovery probes."""
import copy
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from unittest.mock import patch
from pathlib import Path
from threading import Barrier

from acquisition.bootstrap import build
from acquisition.contracts import Conflict, NotFound, digest
from acquisition.learning import counts_for, posterior, recommend, WINDOW_SECONDS
from acquisition.review_demo import run_review_demo
from acquisition.adapters.learning_report import render_learning
from acquisition.reasoning import ModelConfig
from test_model_copy import FakeModel


class LearningDomainTests(unittest.TestCase):
    def test_literal_counts_and_prior_are_not_model_scores(self):
        members = [{"business_id": "one", "segment": "inventory", "arm": "A", "creative_id": "copy"},
                   {"business_id": "two", "segment": "inventory", "arm": "A", "creative_id": "copy"},
                   {"business_id": "three", "segment": "inventory", "arm": "no_mail", "creative_id": ""}]
        outcomes = {"one": {"response": True}, "two": {"response": False}, "three": {"response": False}}
        groups = counts_for(members, outcomes)
        a, control = groups
        self.assertEqual((a["trials"], a["successes"], a["alpha"], a["beta"]), (2, 1, 2, 20))
        self.assertEqual((control["trials"], control["successes"], control["alpha"], control["beta"]), (1, 0, 1, 20))
        self.assertAlmostEqual(a["mean"], 1 / 11)
        self.assertEqual(counts_for(list(reversed(members)), outcomes), groups)
        for changed in ({"one": outcomes["one"], "two": outcomes["two"]}, outcomes | {"extra": {"response": True}}):
            with self.assertRaises(Conflict):
                counts_for(members, changed)

    def test_prior_sampling_matches_analytic_beta_quantiles(self):
        groups = [posterior("inventory", arm, arm, 0, 0) for arm in ("A", "B", "no_mail")]
        result = recommend("analytic-prior", groups)[0]
        for low, high in result["response_intervals_90"].values():
            # Beta(1,19) CDF is 1-(1-x)^19, giving exact reference quantiles.
            self.assertAlmostEqual(low, 1 - .95 ** (1 / 19), delta=.003)
            self.assertAlmostEqual(high, 1 - .05 ** (1 / 19), delta=.01)
        self.assertEqual(result["action"], "collect_more_evidence")

    def test_recommendation_uses_control_and_reports_uncertainty_reproducibly(self):
        groups = [posterior("inventory", arm, arm, 200, success) for arm, success in (("A", 65), ("B", 4), ("no_mail", 3))]
        first = recommend("frozen-cohort", groups)
        self.assertEqual(first, recommend("frozen-cohort", groups))
        inventory, missing = first
        self.assertEqual(inventory["candidate_arm"], "A")
        self.assertEqual(inventory["action"], "propose_next_experiment")
        self.assertGreater(inventory["lift_interval_90"][0], 0)
        self.assertEqual(missing["action"], "collect_more_evidence")
        small = [posterior("inventory", arm, arm, 9, success) for arm, success in (("A", 9), ("B", 0), ("no_mail", 0))]
        self.assertEqual(recommend("small", small)[0]["action"], "collect_more_evidence")
        # A beats B but loses to the control: no recommendation to use A.
        poor = [posterior("inventory", arm, arm, 200, success) for arm, success in (("A", 50), ("B", 1), ("no_mail", 100))]
        self.assertEqual(recommend("negative-lift", poor)[0]["action"], "collect_more_evidence")


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "learning.sqlite"
        self.now = 1792886400.0
        self.app = build(self.path, lambda: self.now)
        demo = run_review_demo(self.app, "learning-tests", "fixture", self.root / "review", str(self.path))
        self.scope, self.case = demo["organization"], demo["case_id"]
        self.actor = "demo-operator"
        self.store = self.app.learning.store
        self.opened = self.app.learning.open(self.scope, self.case, self.actor, "open")
        self.cohort = self.opened["cohort_id"]
        self.proposal = self.app.learning.source.accepted(self.scope, self.case)
        self.rows = [member | {"response": i % 10 == 0, "observed_at": self.now + 1 if i % 10 == 0 else self.opened["window_end"]}
                     for i, member in enumerate(self.proposal["members"])]

    def batch(self, rows=None):
        return {"schema": "synthetic-outcomes/v1", "mode": "SYNTHETIC_ONLY", "cohort_id": self.cohort,
                "outcomes": self.rows if rows is None else rows}

    def ingest(self, rows=None, key="ingest"):
        return self.store.ingest(self.scope, self.actor, key, self.cohort, self.batch(rows))

    def mature(self):
        self.now = self.opened["window_end"]
        self.ingest()

    def finalize(self, key="finalize"):
        return self.store.finalize(self.scope, self.actor, key, self.cohort, self.opened["window_end"])

    def count(self, table):
        with self.store.database.connect() as db:
            return db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]

    def test_only_accepted_campaign_can_open_and_members_include_controls(self):
        self.assertEqual(self.opened["members"], 754)
        self.assertEqual(self.opened["window_end"] - self.opened["window_start"], WINDOW_SECONDS)
        self.assertEqual(sum(m["arm"] == "no_mail" for m in self.proposal["members"]), 74)
        run = self.app.start(self.scope, "unaccepted")
        self.app.worker.drain(self.scope)
        case = self.app.reviews.store.open_case(self.scope, run, self.actor)
        with self.assertRaises(Conflict):
            self.app.learning.open(self.scope, case["case_id"], self.actor, "not-accepted")
        self.assertEqual(self.count("learning_cohorts"), 1)

    def test_coordinated_membership_omission_cannot_define_its_own_denominator(self):
        forged = copy.deepcopy(self.proposal)
        forged["members"] = [m for m in forged["members"] if m["arm"] != "no_mail"]
        forged["id"] = "cohort_" + digest({k: v for k, v in forged.items() if k != "id"})
        with self.assertRaises(Conflict):
            self.store.open(self.scope, self.actor, "omitted-controls", forged)
        self.assertEqual(self.count("learning_cohorts"), 1)
        self.assertEqual(self.count("learning_members"), 754)

    def test_early_responses_do_not_update_beliefs_or_close_the_window(self):
        self.now += 1
        positives = [r for r in self.rows if r["response"]]
        self.ingest(positives)
        view = self.store.view(self.scope, self.cohort)
        self.assertEqual(view["status"], "observing")
        self.assertEqual(view["beliefs"], [])
        self.assertEqual(view["recommendations"], [])
        self.assertEqual(self.store.memory(self.scope, "inventory")["groups"], [])
        with self.assertRaises(Conflict):
            self.finalize()
        with self.assertRaises(ValueError):
            self.ingest([r for r in self.rows if not r["response"]], "early-negatives")
        self.assertEqual(self.count("learning_beliefs"), 0)

    def test_complete_early_responses_still_cannot_finalize_before_maturity(self):
        self.now += 1
        all_positive = [r | {"response": True, "observed_at": self.now} for r in self.rows]
        self.ingest(all_positive)
        self.assertEqual(self.store.view(self.scope, self.cohort)["missing"], 0)
        with self.assertRaises(Conflict):
            self.finalize()
        self.assertEqual(self.count("learning_beliefs"), 0)
        self.now = self.opened["window_end"]
        receipt = self.finalize()
        self.assertEqual((receipt["observations"], receipt["successes"]), (754, 754))

    def test_absent_results_and_missing_control_are_pending_not_failures(self):
        self.now = self.opened["window_end"]
        treatments = [r for r in self.rows if r["arm"] != "no_mail"]
        self.ingest(treatments)
        with self.assertRaises(Conflict):
            self.finalize()
        view = self.store.view(self.scope, self.cohort)
        self.assertEqual(view["missing"], 74)
        self.assertEqual(view["status"], "awaiting_complete_outcomes")
        self.assertFalse(view["beliefs"])
        self.ingest([r for r in self.rows if r["arm"] == "no_mail"], "controls")
        self.finalize()
        self.assertEqual(sum(g["trials"] for g in self.store.view(self.scope, self.cohort)["beliefs"]), 754)

    def test_complete_mature_counts_survive_restart_and_replay_once(self):
        self.mature()
        first = self.finalize()
        reopened = build(self.path, lambda: self.now)
        same = reopened.learning.store.finalize(self.scope, self.actor, "finalize", self.cohort, self.opened["window_end"])
        different_key = self.finalize("new-finalize-key")
        self.assertEqual(first, same)
        self.assertEqual(first, different_key)
        self.assertEqual(first["observations"], 754)
        self.assertEqual(first["successes"], 76)
        self.assertEqual(self.count("learning_beliefs"), 6)
        view = self.store.view(self.scope, self.cohort)
        for group in view["beliefs"]:
            members = [r for r in self.rows if r["segment"] == group["segment"] and r["arm"] == group["arm"]]
            successes = sum(r["response"] for r in members)
            self.assertEqual((group["trials"], group["successes"], group["alpha"], group["beta"]),
                             (len(members), successes, 1 + successes, 19 + len(members) - successes))

    def test_finalization_replay_preserves_original_actor_time_and_single_effect_event(self):
        self.mature()
        first = self.finalize()
        original = self.store.view(self.scope, self.cohort)["events"]
        self.now += 10
        self.app.reviews.store.register_actor(self.scope, "second-operator", ("operator",))
        replay = self.store.finalize(self.scope, "second-operator", "observe-finalized", self.cohort, self.opened["window_end"])
        self.assertEqual(replay, first)
        self.assertEqual(self.store.view(self.scope, self.cohort)["events"], original)
        finalized = [e for e in original if e["kind"] == "cohort_finalized"]
        self.assertEqual(len(finalized), 1)
        self.assertEqual(finalized[0]["payload"]["actor"], self.actor)
        self.assertEqual(finalized[0]["at"], first["finalized_at"])
        with self.store.database.connect() as db:
            cached = json.loads(db.execute("SELECT receipt FROM learning_commands WHERE organization=? AND request_id='observe-finalized'", (self.scope,)).fetchone()[0])
        self.assertEqual(cached, first)
        reopened = build(self.path, lambda: self.now)
        self.assertEqual(reopened.learning.store.finalize(self.scope, "second-operator", "observe-finalized", self.cohort, self.opened["window_end"]), first)
        self.assertEqual(reopened.learning.store.view(self.scope, self.cohort)["events"], original)
        with self.assertRaises(Conflict):
            self.store.finalize(self.scope, "second-operator", "observe-finalized", self.cohort, self.opened["window_end"] + 1)
        self.assertEqual(self.count("learning_beliefs"), 6)

    def test_dedup_across_batches_and_keys_never_inflates_counts(self):
        self.mature()
        original = self.ingest()
        reordered = self.ingest(list(reversed(self.rows)))
        again = self.ingest(key="new-batch-key")
        self.assertEqual(original, reordered)
        self.assertEqual(again["added"], 0)
        self.assertEqual(again["duplicates"], 754)
        self.finalize()
        self.ingest(key="after-finalization-identical")
        self.assertEqual(self.count("learning_outcomes"), 754)
        self.assertEqual(self.finalize()["observations"], 754)

    def test_changed_or_duplicate_outcomes_and_request_reuse_are_rejected(self):
        self.mature()
        changed = copy.deepcopy(self.rows)
        changed[0]["observed_at"] += 1
        for key in ("ingest", "conflicting-fresh-key"):
            with self.assertRaises(Conflict):
                self.ingest(changed, key)
        with self.assertRaises(Conflict):
            self.ingest([self.rows[0], self.rows[0]], "duplicates")
        self.assertEqual(self.count("learning_outcomes"), 754)

    def test_assignment_scope_and_schema_substitution_are_rejected(self):
        self.now = self.opened["window_end"]
        mutations = {"business_id": "outsider", "segment": "other", "arm": "B" if self.rows[0]["arm"] == "A" else "A", "creative_id": "other-copy"}
        for field, value in mutations.items():
            with self.subTest(field=field), self.assertRaises(Conflict):
                self.ingest([self.rows[0] | {field: value}], "bad-" + field)
        with self.assertRaises(ValueError):
            self.ingest([self.rows[0] | {"response": 1}], "integer-score")
        with self.assertRaises(ValueError):
            self.store.ingest(self.scope, self.actor, "real-data", self.cohort, self.batch() | {"mode": "REAL"})
        self.app.reviews.store.register_actor("other", self.actor, ("operator",))
        with self.assertRaises(NotFound):
            self.store.view("other", self.cohort)
        with self.assertRaises(NotFound):
            self.store.ingest("other", self.actor, "cross-scope", self.cohort, self.batch())
        self.app.reviews.store.register_actor(self.scope, "reviewer-only", ("reviewer",))
        with self.assertRaises(ValueError):
            self.store.ingest(self.scope, "reviewer-only", "wrong-role", self.cohort, self.batch())
        self.assertEqual(self.count("learning_outcomes"), 0)

    def test_observation_window_boundaries_and_complete_through(self):
        self.now = self.opened["window_end"]
        row = self.rows[0]
        for at in (self.opened["window_start"] - 1, self.opened["window_end"], float("nan"), float("inf")):
            with self.subTest(at=at), self.assertRaises(ValueError):
                self.ingest([row | {"response": True, "observed_at": at}], "bad-time")
        with self.assertRaises(ValueError):
            self.ingest([row | {"response": False, "observed_at": self.opened["window_end"] - 1}], "partial-negative")
        self.mature()
        for through in (self.opened["window_end"] - 1, self.opened["window_end"] + 1):
            with self.assertRaises(Conflict):
                self.store.finalize(self.scope, self.actor, "wrong-through", self.cohort, through)
        self.finalize()

    def test_finalize_event_failure_rolls_back_counts_and_receipt(self):
        self.mature()
        with self.store.database.connect() as db:
            db.execute("CREATE TRIGGER fail_final BEFORE INSERT ON learning_events WHEN NEW.kind='cohort_finalized' BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.finalize()
        self.assertEqual(self.count("learning_beliefs"), 0)
        self.assertIsNone(self.store.view(self.scope, self.cohort)["finalization"])
        with self.store.database.connect() as db:
            db.execute("DROP TRIGGER fail_final")
        self.finalize()
        self.assertEqual(self.count("learning_beliefs"), 6)

    def test_partial_ingest_failure_rolls_back_all_rows(self):
        self.now = self.opened["window_end"]
        second = sorted(self.rows, key=lambda r: r["business_id"])[1]["business_id"]
        with self.store.database.connect() as db:
            db.execute("CREATE TRIGGER fail_ingest BEFORE INSERT ON learning_outcomes WHEN NEW.business_id='" + second + "' BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.ingest()
        self.assertEqual(self.count("learning_outcomes"), 0)
        with self.store.database.connect() as db:
            db.execute("DROP TRIGGER fail_ingest")
        self.mature()

    def test_concurrent_finalization_never_duplicates_beliefs(self):
        self.mature()
        barrier = Barrier(2)
        def finalize(key):
            barrier.wait()
            return self.finalize(key)
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(finalize, ("one-finalizer", "two-finalizers")))
        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(self.count("learning_beliefs"), 6)
        self.assertEqual(self.finalize()["observations"], 754)

    def test_cohort_open_replay_and_overlapping_businesses(self):
        self.assertEqual(self.opened, self.app.learning.open(self.scope, self.case, self.actor, "open"))
        self.assertEqual(self.opened, self.app.learning.open(self.scope, self.case, self.actor, "observe-open"))
        events = self.store.view(self.scope, self.cohort)["events"]
        self.assertEqual(len([e for e in events if e["kind"] == "cohort_opened"]), 1)
        run = self.app.start(self.scope, "second-campaign")
        self.app.worker.drain(self.scope)
        review = self.app.reviews.store
        case = review.open_case(self.scope, run, self.actor)
        revised = self.app.reviews.refresh(self.scope, case["case_id"], case["subject_id"], self.actor, "fresh-second")
        approval = review.decide(self.scope, case["case_id"], revised["subject_id"], "scripted-reviewer", "approve", "approve-second", "Synthetic second campaign.")
        review.handoff(self.scope, case["case_id"], approval["id"], self.actor, "accept-second")
        with self.assertRaises(Conflict):
            self.app.learning.open(self.scope, case["case_id"], self.actor, "overlapping")
        self.assertEqual(self.count("learning_cohorts"), 1)
        self.assertEqual(self.count("learning_members"), 754)

    def test_read_only_report_escapes_untrusted_values(self):
        view = self.store.view(self.scope, self.cohort)
        view["limitations"].append('<script>alert("x")</script>')
        report = render_learning(view)
        self.assertNotIn("<script>", report)
        self.assertIn("&lt;script&gt;", report)
        self.assertNotIn(chr(0x2014), report)

    def test_learning_memory_is_scoped_frozen_and_cannot_approve(self):
        model = FakeModel()
        app = build(self.path, lambda: self.now, model, ModelConfig("test/model"))
        before = app.start_model(self.scope, "before-learning", size=100)
        prior = app.tasks.inspect(self.scope, before)["tasks"][0]["inputs"]["context_ids"]
        self.mature()
        self.finalize()
        # This fixture closes inside the product evidence review window.
        self.now = self.proposal["window_start"] + WINDOW_SECONDS
        after = app.start_model(self.scope, "after-learning", size=100)
        current = app.tasks.inspect(self.scope, after)["tasks"][0]["inputs"]["context_ids"]
        for segment in prior:
            frozen = app.memory.get_context(self.scope, prior[segment])
            fresh = app.memory.get_context(self.scope, current[segment])
            self.assertFalse(frozen["audience_summary"]["outcome_evidence"]["groups"])
            self.assertTrue(fresh["audience_summary"]["outcome_evidence"]["groups"])
            self.assertEqual(fresh["audience_summary"]["outcome_evidence"]["mode"], "SYNTHETIC_ONLY")
        self.assertEqual(self.store.memory("other", "inventory")["groups"], [])
        self.assertEqual(len(model.requests), 0)
        self.assertEqual(self.count("review_decisions"), 2)

    def test_model_run_freezes_all_segments_before_concurrent_finalization(self):
        self.mature()
        model = FakeModel()
        app = build(self.path, lambda: self.now, model, ModelConfig("test/model"))
        database = app.learning.store.database
        connect = database.connect
        finalized = []

        class Cursor:
            def __init__(cursor_self, cursor):
                cursor_self.cursor = cursor

            def fetchall(cursor_self):
                rows = cursor_self.cursor.fetchall()
                if not finalized:
                    # Writer commits after the reader has established its WAL
                    # snapshot, before any later segment can be frozen.
                    finalized.append(self.finalize())
                return rows

        class Connection:
            def __init__(connection_self, connection):
                connection_self.connection = connection

            def __getattr__(connection_self, name):
                return getattr(connection_self.connection, name)

            def execute(connection_self, sql, *args):
                cursor = connection_self.connection.execute(sql, *args)
                if "SELECT b.* FROM learning_beliefs" in sql:
                    self.assertTrue(connection_self.connection.in_transaction)
                    return Cursor(cursor)
                return cursor

        @contextmanager
        def observed_connect():
            with connect() as db:
                yield Connection(db)

        with patch.object(database, "connect", observed_connect):
            run = app.start_model(self.scope, "concurrent-learning-freeze", size=100)
        self.assertEqual(len(finalized), 1)
        context_ids = app.tasks.inspect(self.scope, run)["tasks"][0]["inputs"]["context_ids"]
        for segment, identity in context_ids.items():
            frozen = app.memory.get_context(self.scope, identity)["audience_summary"]["outcome_evidence"]
            self.assertEqual(frozen["groups"], [], segment)
            self.assertEqual(len(app.learning.store.memory(self.scope, segment)["groups"]), 3)
        self.assertEqual(len(model.requests), 0)

    def test_learning_memory_does_not_leak_future_finalized_evidence(self):
        original_time = self.now
        self.mature()
        self.finalize()
        self.assertTrue(self.store.memory(self.scope, "inventory")["groups"])
        self.now = original_time
        self.assertEqual(self.store.memory(self.scope, "inventory")["groups"], [])

    def test_concurrent_conflicting_imports_have_one_immutable_winner(self):
        self.now = self.opened["window_end"]
        one = self.rows[0] | {"response": True, "observed_at": self.opened["window_start"]}
        two = self.rows[0] | {"response": False, "observed_at": self.opened["window_end"]}
        barrier = Barrier(2)
        def ingest(pair):
            key, row = pair
            barrier.wait()
            try:
                self.ingest([row], key)
                return row
            except Conflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(ingest, (("positive", one), ("negative", two))))
        winners = [r for r in results if r is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(self.count("learning_outcomes"), 1)
        with self.store.database.connect() as db:
            self.assertEqual(json.loads(db.execute("SELECT payload FROM learning_outcomes").fetchone()[0]), winners[0])

    def test_nonfinite_clock_rejects_mutation_before_state_changes(self):
        for bad in (float("inf"), float("-inf"), float("nan")):
            self.now = bad
            with self.assertRaises(ValueError):
                self.ingest()
            with self.assertRaises(ValueError):
                self.finalize()
        self.assertEqual(self.count("learning_outcomes"), 0)
        self.assertEqual(self.count("learning_beliefs"), 0)
