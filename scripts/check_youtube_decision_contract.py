"""Validate the offline #143 handoff, without loading providers or product state."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "config/youtube-decision-contract-v1.json"
FROZEN_SIMULATION_V1 = {
    "currency": "GBP",
    "money_unit": "pence",
    "period_days": 7,
    "total_budget_pence": 10000,
    "daily_cap_pence": 2000,
    "exploration_cap_pence": 1000,
    "utility_value_per_qualified_action_pence": 500,
    "minimum_worthwhile_activation_lift_basis_points": 200,
    "utility": "qualified_actions_times_500_minus_cost_pence",
    "interpretation": "authored_benchmark_tradeoff_not_revenue_or_spending_authority",
}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate contract field: " + key)
        result[key] = value
    return result


def load_contract(path=DEFAULT):
    return json.loads(Path(path).read_text(), object_pairs_hook=unique_object,
                      parse_constant=reject_nonfinite)


def reject_nonfinite(value):
    raise ValueError("Non-finite contract number: " + value)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(contract):
    """Pin semantic boundaries for this offline version, not runtime readiness."""
    require(type(contract) is dict and set(contract) == {
        "schema", "decision_date", "disposition", "objective", "route", "action",
        "reward", "data", "simulation", "handoff"}, "Use the exact feasibility contract fields")
    require(contract["schema"] == "youtube-decision-feasibility/v1", "Unsupported feasibility contract")
    require(contract["disposition"] == "offline_only", "This contract cannot promote a live route")
    require(contract["objective"] == "qualified_product_demo_actions", "Do not substitute a proxy objective")
    route, action, reward, data, sim, handoff = (
        contract[key] for key in ("route", "action", "reward", "data", "simulation", "handoff"))
    require(all(type(value) is dict for value in (route, action, reward, data, sim, handoff)),
            "Contract sections must be objects")
    require(route.get("selected") == "authored_context_creative_recommendation"
            and route.get("future_handoff") == "manual_export_conditional_on_verified_placement_setup"
            and all(route.get(key) is False for key in (
                "account_verified", "exact_targeting_write_verified", "delivery_verified", "live_execution_allowed")),
            "Documented capability is not account or delivery verification")
    require(action.get("unit") == "context_creative_cell"
            and action.get("selection") == "recommendation_batch"
            and type(action.get("decision_interval_seconds")) is int
            and action["decision_interval_seconds"] == 86400
            and action.get("allowed_effects") == ["offline_evaluation", "unapproved_recommendation"],
            "Recommendations cannot grant campaign execution authority")
    require(set(action.get("required_identity", [])) >= {
        "organization", "reviewed_context_id", "brief_revision", "candidate_snapshot_id",
        "context_id", "creative_version", "asset_digest", "reward_version", "policy_version"},
        "The action must retain scoped brief, candidate, asset and policy identity")
    require(reward.get("version") == "qualified-demo-activation/v1"
            and reward.get("positive_event") == "server_verified_demo_task_succeeded"
            and reward.get("task") == "explicitly_request_and_receive_a_playable_generated_voice_sample",
            "A button, preference or prerecorded clip is not a qualified product task")
    require(reward.get("unit") == "eligible_demo_assignment"
            and reward.get("denominator") == "mature_eligible_assigned_demo_arrivals"
            and type(reward.get("maximum_successes_per_assignment")) is int
            and reward["maximum_successes_per_assignment"] == 1
            and reward.get("attribution") == "server_bound_campaign_cell_link_only",
            "Bind one outcome to one eligible attributed assignment")
    require(reward.get("observation_window_seconds") == 1800
            and reward.get("ingestion_grace_seconds") == 300
            and set(reward.get("zero_requires", [])) == {
                "mature_window", "complete_coverage", "no_uncertain_task"}
            and reward.get("missing_outcome") == "unknown",
            "Incomplete or immature outcomes must stay unknown")
    require(reward.get("estimation") == {
        "point_estimate_requires": [
            "nonempty_mature_cohort", "known_complete_assignment_manifest",
            "complete_coverage", "zero_unknown_outcomes"],
        "incomplete_cohort": "bounds_only_no_posterior_update",
        "empty_cohort": "unavailable",
        "bounds_require": "known_complete_assignment_manifest",
        "bounds": "[S/N,(S+U)/N]",
        "comparison_requires": "complete_cohorts_at_same_frozen_cutoff",
    }, "Unknown outcomes require bounds; point estimates and posterior updates need complete cohorts")
    require(set(reward.get("excluded_sources", [])) >= {
        "fixture", "rehearsal", "staff", "unknown", "llm_simulation"}
        and set(reward.get("insufficient_events", [])) >= {
            "page_view", "recording_preference", "prerecorded_playback",
            "generate_button_click", "client_only_success", "export_of_prerecorded_clip"},
        "Keep synthetic and proxy signals outside qualified outcome counts")
    require(reward.get("claim") == "post_click_demo_activation_not_ad_impression_conversion_or_sales"
            and type(reward.get("current_live_events")) is int and reward["current_live_events"] == 0,
            "No live qualified-action evidence exists for this contract")
    require(data.get("public_api_data_ranker_permission") == "not_established"
            and data.get("offline_replay_identifiable") is False
            and all(data.get(key) == "unavailable" for key in (
                "real_audience_labels", "real_campaign_outcomes", "real_selection_propensities")),
            "Unavailable labels or propensities cannot establish predictive or counterfactual value")
    require(set(data.get("permitted_offline_sources", [])) == {
        "authored_synthetic", "creator_supplied_with_permission", "licensed_with_permission"},
        "Retain the source permission boundary for model inputs")
    require(set(sim) == set(FROZEN_SIMULATION_V1)
            and all(type(sim[key]) is type(value) and sim[key] == value
                    for key, value in FROZEN_SIMULATION_V1.items()),
            "Frozen v1 simulation assumptions changed; use a separately identified sensitivity contract")
    require(handoff.get("next_issue") == 144 and handoff.get("measurement_issue") == 133
            and handoff.get("instruction_policy") == "preserve_instruction-beta-v1_separately"
            and handoff.get("shadow_ready") is False
            and set(handoff.get("live_blockers", [])) >= {
                "account_targeting_and_effective_expansion_readback",
                "eligible_inventory_and_approved_creatives",
                "server_verified_product_demo_task_and_attribution",
                "compatible_exposure_spend_outcome_report_join",
                "current_hosted_scope_and_participant_access",
                "separately_authorized_budget_and_execution"},
            "Retain the original instruction policy and explicit live promotion gates")
    return {"status": "offline_contract_valid", "disposition": contract["disposition"],
            "objective": contract["objective"], "reward_version": reward["version"],
            "live_ready": False, "next_issue": handoff["next_issue"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT)
    args = parser.parse_args()
    try:
        contract = load_contract(args.contract)
        result = validate(contract)
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, str(error) + "\n")
    result["contract_sha256"] = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
