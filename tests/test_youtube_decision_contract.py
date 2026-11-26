"""The #143 handoff must not silently become a live or proxy-reward policy."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.check_youtube_decision_contract import load_contract, validate


class YouTubeDecisionContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_contract()

    def test_selected_objective_is_an_offline_qualified_action_contract(self):
        result = validate(self.contract)
        self.assertEqual(result["objective"], "qualified_product_demo_actions")
        self.assertEqual(result["reward_version"], "qualified-demo-activation/v1")
        self.assertEqual(result["next_issue"], 144)
        self.assertFalse(result["live_ready"])

    def test_account_and_execution_claims_cannot_be_promoted_from_documentation(self):
        for section, field, value in (
            ("route", "account_verified", True),
            ("route", "exact_targeting_write_verified", True),
            ("route", "delivery_verified", True),
            ("route", "live_execution_allowed", True),
            ("route", "future_handoff", "automatic_write"),
            ("action", "allowed_effects", ["campaign_write"]),
            ("action", "decision_interval_seconds", 1),
            ("handoff", "shadow_ready", True),
        ):
            changed = deepcopy(self.contract)
            changed[section][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(changed)

    def test_proxy_reward_and_incomplete_outcomes_do_not_become_successes_or_zeros(self):
        for field, value in (
            ("positive_event", "recording_preference"),
            ("positive_event", "client_only_success"),
            ("denominator", "ad_impressions"),
            ("maximum_successes_per_assignment", True),
            ("missing_outcome", "failure"),
            ("zero_requires", ["mature_window"]),
            ("excluded_sources", ["fixture"]),
            ("current_live_events", 1000),
        ):
            changed = deepcopy(self.contract)
            changed["reward"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(changed)

    def test_unknown_model_data_cannot_support_replay_or_real_response_accuracy(self):
        for field, value in (
            ("offline_replay_identifiable", True),
            ("real_selection_propensities", "inferred_from_google_reports"),
            ("real_campaign_outcomes", "llm_generated"),
            ("public_api_data_ranker_permission", "assumed_public"),
            ("permitted_offline_sources", ["arbitrary_public_transcripts"]),
        ):
            changed = deepcopy(self.contract)
            changed["data"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(changed)

    def test_missing_asset_and_scope_identity_is_rejected(self):
        for key in ("organization", "asset_digest", "reward_version", "candidate_snapshot_id"):
            changed = deepcopy(self.contract)
            changed["action"]["required_identity"].remove(key)
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate(changed)

    def test_boolean_and_inconsistent_money_and_utility_are_rejected(self):
        for field, value in (
            ("total_budget_pence", True),
            ("daily_cap_pence", 10001),
            ("exploration_cap_pence", 10001),
            ("total_budget_pence", 15000),
            ("utility_value_per_qualified_action_pence", 600),
            ("minimum_worthwhile_activation_lift_basis_points", 10000),
        ):
            changed = deepcopy(self.contract)
            changed["simulation"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(changed)

    def test_unknown_version_and_duplicate_json_cannot_hide_a_changed_reward(self):
        changed = deepcopy(self.contract)
        changed["schema"] = "youtube-decision-feasibility/v2"
        with self.assertRaises(ValueError):
            validate(changed)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"objective":"recording_preference","objective":"qualified_product_demo_actions"}')
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                load_contract(path)
            path.write_text('{"value":NaN}')
            with self.assertRaisesRegex(ValueError, "Non-finite"):
                load_contract(path)

    def test_cli_rejects_bad_contract_instead_of_emitting_a_validity_receipt(self):
        changed = deepcopy(self.contract)
        changed["reward"]["missing_outcome"] = "zero"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(changed))
            result = subprocess.run(
                [sys.executable, "scripts/check_youtube_decision_contract.py", "--contract", str(path)],
                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("unknown", result.stderr)
