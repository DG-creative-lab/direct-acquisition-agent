import csv
import io
import math
import unittest
from dataclasses import replace

from acquisition.adapters.synthetic import generate
from acquisition.audiences import Business, Snapshot
from acquisition.campaigns import Brief, build_draft
from acquisition.creative import fixture_catalog
from acquisition.learning import BetaBelief


def business(number, **changes):
    return replace(Business(str(number), str(number), "inventory", "UK", "LTD", "DEMO ONLY contact",
                            True, False, 0, None, 10000), **changes)


class DomainTests(unittest.TestCase):
    def test_population_and_exclusions_against_handwritten_reference(self):
        rows = [business(i) for i in range(10)] + [
            business(10, suppressed=True), business(11, country="DE"), business(12, deliverable=False),
            business(13, propensity_ppm=None), business(14, contacts_last_90_days=2),
            business(15, last_contact="2026-10-24"), business(16, business_id="duplicate"),
            business(17, business_id="duplicate", suppressed=True),
        ]
        snapshot = Snapshot("one", "2026-10-25", tuple(rows), 42)
        draft = build_draft(snapshot, Brief("test"), fixture_catalog())
        self.assertEqual(draft.manifest["counts"], {"input": 18, "excluded": 8,
                         "eligible_unselected": 0, "holdout": 1, "mailed": 9})
        self.assertEqual(draft.manifest["exclusion_reasons"], {"duplicate_business": 2, "suppressed": 1,
                         "product_scope": 1, "unusable_demo_address": 1, "missing_score": 1,
                         "contact_cap": 1, "contact_cooldown": 1})
        assignments = list(csv.DictReader(io.StringIO(draft.assignments_csv)))
        mailed = list(csv.DictReader(io.StringIO(draft.mailing_csv)))
        self.assertEqual({row["business_id"] for row in assignments}, {str(i) for i in range(10)})
        holdouts = {row["business_id"] for row in assignments if row["arm"] == "no_mail"}
        self.assertTrue(holdouts.isdisjoint({row["business_id"] for row in mailed}))
        self.assertEqual(draft.manifest["variable_cost_pence"], 9 * 85)

    def test_budget_and_conservation_across_seeds_and_boundaries(self):
        for seed in (0, 7, 99):
            for size in (1, 20, 101):
                for budget in (0, 84, 85, 850):
                    with self.subTest(seed=seed, size=size, budget=budget):
                        draft = build_draft(generate("one", size, seed), Brief("test", budget), fixture_catalog())
                        counts = draft.manifest["counts"]
                        self.assertEqual(counts["input"], sum(v for k, v in counts.items() if k != "input"))
                        self.assertLessEqual(draft.manifest["variable_cost_pence"], budget)
                        self.assertEqual(len(list(csv.DictReader(io.StringIO(draft.mailing_csv)))), counts["mailed"])

    def test_generation_and_assignments_are_reproducible_and_order_independent(self):
        snapshot = generate("one", 1000, 42)
        self.assertEqual(snapshot, generate("one", 1000, 42))
        first = build_draft(snapshot, Brief("test"), fixture_catalog())
        second = build_draft(replace(snapshot, records=tuple(reversed(snapshot.records))), Brief("test"), fixture_catalog())
        self.assertEqual(first.mailing_csv, second.mailing_csv)
        self.assertEqual(first.assignments_csv, second.assignments_csv)

    def test_holdout_is_randomized_after_score_based_enrollment(self):
        records = tuple(business(i, propensity_ppm=i) for i in range(30))
        draft = build_draft(Snapshot("one", "2026-10-25", records, 42), Brief("test", max_candidates=10), fixture_catalog())
        assignments = list(csv.DictReader(io.StringIO(draft.assignments_csv)))
        # Both control and treatment come from the same top ten score population.
        self.assertEqual({int(row["business_id"]) for row in assignments}, set(range(20, 30)))
        self.assertEqual(sum(row["arm"] == "no_mail" for row in assignments), 1)

    def test_missing_batch_and_unknown_contracts_fail_closed(self):
        snapshot = generate("one", 20)
        with self.assertRaises(ValueError):
            build_draft(replace(snapshot, complete=False), Brief("test"), fixture_catalog())
        with self.assertRaises(ValueError):
            replace(snapshot, schema_version="audience/v2")
        with self.assertRaises(ValueError):
            build_draft(snapshot, Brief("test"), fixture_catalog()[:-1])
        with self.assertRaises(ValueError):
            build_draft(replace(snapshot, score_semantics="uplift"), Brief("test"), fixture_catalog())

    def test_invalid_money_counts_and_attestations(self):
        for kwargs in ({"budget_pence": -1}, {"budget_pence": True}, {"unit_cost_pence": 0}, {"max_candidates": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Brief("test", **kwargs)
        with self.assertRaises(ValueError):
            business(1, suppressed="false")
        with self.assertRaises(ValueError):
            business(1, propensity_ppm=math.nan)

    def test_copy_changes_create_new_identity_and_manifest(self):
        originals = fixture_catalog()
        revised = (replace(originals[0], opening="DEMO: different wording"),) + originals[1:]
        self.assertNotEqual(originals[0].id, revised[0].id)
        snapshot = generate("one", 100)
        self.assertNotEqual(build_draft(snapshot, Brief("test"), originals).id,
                            build_draft(snapshot, Brief("test"), revised).id)

    def test_bayesian_counts_are_exact_and_composable(self):
        prior = BetaBelief(1, 99)
        self.assertEqual(prior.observe(1000, 18), BetaBelief(19, 1081))
        self.assertEqual(prior.observe(500, 9).observe(500, 9), prior.observe(1000, 18))
        self.assertEqual(prior.observe(0, 0), prior)
        for trials, successes in ((10, 11), (10, -1), (-1, 0), (True, 0), (10, 1.1)):
            with self.assertRaises(ValueError):
                prior.observe(trials, successes)
