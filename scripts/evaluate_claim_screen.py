"""Opt-in live, labelled critic check. No customer data, sending or draft approval."""

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from acquisition.adapters.environment import openrouter_key
from acquisition.adapters.openrouter import OpenRouter
from acquisition.bootstrap import build
from acquisition.creative import claim_screen_request, validate_fact_pack
from acquisition.reasoning import CallScope, ModelConfig, ModelError
from acquisition.runtime import Outcome, TaskSpec


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=".local/claim-screen-eval.sqlite")
    parser.add_argument("--request-id", default="claim-screen-v1")
    parser.add_argument("--env-file", type=Path, default=Path(".env.local"))
    parser.add_argument("--model", default="openai/gpt-oss-120b")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cases = json.loads((root / "config/claim-screen-cases-v1.json").read_text())
    pack = json.loads((root / "config/iwoca-product-facts-v1.json").read_text())
    validate_fact_pack(pack, datetime.now(timezone.utc).date())
    if not 1 <= len(cases) <= 12:
        raise ValueError("Evaluation is limited to twelve paired cases")
    config = ModelConfig(args.model, max_calls=1, force_tool_choice=args.model == "openai/gpt-oss-120b")
    app = build(args.db, gateway=OpenRouter(openrouter_key(args.env_file)), model_config=config)
    specs = []
    for case in cases:
        variants = [{"arm": arm.upper(), "fact_id": pack["facts"][i % len(pack["facts"])]["id"],
                     "hypothesis": "This framing may change engagement with the message.", **case[arm]}
                    for i, arm in enumerate(("a", "b"))]
        messages, tools = claim_screen_request(variants, {"segment": "inventory", "product_facts": pack})
        specs.append(TaskSpec("creative.claim_screen_eval.v1", {"case_id": case["id"], "expected": case["expected"],
                         "messages": messages, "tools": tools, "model_config": asdict(config)}, max_attempts=1))
    organization = "claim-screen-evaluation:" + args.request_id
    runs = [app.tasks.create(organization, spec.inputs["case_id"], [spec], app.clock()) for spec in specs]

    def evaluate(claim):
        scope = CallScope(claim.organization, claim.run_id, claim.task_id, claim.token)
        response = app.inference.call(scope, claim.inputs["case_id"], claim.inputs["messages"], claim.inputs["tools"])
        call = response["message"]["tool_calls"][0]["function"]
        if call["name"] != "record_claim_check":
            raise ModelError("unexpected_evaluation_tool")
        result = json.loads(call["arguments"])
        payload = json.loads(claim.inputs["messages"][1]["content"])
        if (set(result) != {"candidate_hash", "fact_pack_id", "a_verdict", "a_reason", "b_verdict", "b_reason"}
                or any(result[f"{arm}_verdict"] not in {"pass", "reject"} for arm in ("a", "b"))
                or result["candidate_hash"] != payload["candidate_hash"] or result["fact_pack_id"] != payload["fact_pack_id"]):
            raise ModelError("invalid_evaluation_verdict")
        observed = [result["a_verdict"], result["b_verdict"]]
        return Outcome("succeeded", {"case_id": claim.inputs["case_id"], "expected": claim.inputs["expected"],
            "observed": observed, "matched": observed == claim.inputs["expected"], "screen": result})

    app.worker.capabilities["creative.claim_screen_eval.v1"] = evaluate
    # A campaign fails as a unit. These cases are independent and each gets its
    # own one-call run, so an unavailable critic does not hide remaining cases.
    app.worker.drain(organization)
    states = [app.tasks.inspect(organization, run) for run in runs]
    tasks = [task for state in states for task in state["tasks"]]
    calls = [call for run in runs for call in app.calls.inspect(organization, run)]
    costs = [(call.get("receipt") or {}).get("usage", {}).get("cost") for call in calls]
    results = [task["output"] for task in tasks if task["output"] and "matched" in task["output"]]
    incomplete = [{"case_id": task["inputs"]["case_id"], "status": task["status"], "output": task["output"]}
                  for task in tasks if not task["output"] or "matched" not in task["output"]]
    status = "succeeded" if all(state["run"]["status"] == "succeeded" for state in states) else "incomplete"
    report = {"run_ids": runs, "model": args.model, "status": status,
        "cases": results, "pairs_matched": sum(item["matched"] for item in results), "pairs_expected": len(cases),
        "incomplete_cases": incomplete,
        "reported_cost_usd": str(sum((Decimal(str(c)) for c in costs if c is not None), Decimal(0))),
        "calls_without_reported_cost": sum(c is None for c in costs), "model_calls": calls,
        "limitation": "Small labelled regression corpus; not a reliability estimate or approval of customer-facing copy."}
    print(json.dumps(report, indent=2))
    if status != "succeeded" or report["pairs_matched"] != len(cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
