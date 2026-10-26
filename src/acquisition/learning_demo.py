"""Isolated, explicitly simulated timeline. Never changes the operator's clock."""

import json
from datetime import datetime, timezone
from pathlib import Path

from acquisition.adapters.learning_report import write_learning
from acquisition.contracts import Conflict, digest
from acquisition.review_demo import run_review_demo


def run_learning_demo(database_path, organization, request_id, output):
    # Deliberate simulated timeline anchored inside the checked fixture window.
    # This function touches only its deterministic demonstration organization.
    from acquisition.bootstrap import build
    pack = json.loads((Path(__file__).resolve().parents[2] / "config/iwoca-product-facts-v1.json").read_text())
    now = datetime.fromisoformat(pack["checked_on"]).replace(tzinfo=timezone.utc).timestamp() + 43200
    app = build(database_path, clock=lambda: now)
    output = Path(output)
    demo = run_review_demo(app, "learning-demo:" + organization, request_id, output / "review", database_path)
    scope, case = demo["organization"], demo["case_id"]
    opened = app.learning.open(scope, case, "demo-operator", "open-learning")
    cohort_id = opened["cohort_id"]
    # Synthetic labels deliberately produce a strong A versus B/control signal.
    proposal = app.learning.source.accepted(scope, case)
    rows = []
    for member in proposal["members"]:
        threshold = {"A": 220, "B": 35, "no_mail": 20}[member["arm"]]
        response = int(digest({"business": member["business_id"], "seed": 81})[:8], 16) % 1000 < threshold
        rows.append(member | {"response": response, "observed_at": opened["window_start"] + 7 * 86400 if response else opened["window_end"]})
    batch = {"schema": "synthetic-outcomes/v1", "mode": "SYNTHETIC_ONLY", "cohort_id": cohort_id, "outcomes": rows}
    if app.learning.store.view(scope, cohort_id)["status"] != "finalized":
        now = opened["window_start"] + 7 * 86400
        positive = batch | {"outcomes": [r for r in rows if r["response"]]}
        if positive["outcomes"]:
            app.learning.store.ingest(scope, "demo-operator", "early-responses", cohort_id, positive)
        write_learning(app.learning.store.view(scope, cohort_id) | {"clock_mode": "SIMULATED"}, output / "pending.html")
        try:
            app.learning.store.finalize(scope, "demo-operator", "too-early", cohort_id, opened["window_end"])
        except Conflict:
            pass
        else:
            raise AssertionError("Immature cohort unexpectedly finalized")
    now = opened["window_end"]
    app.learning.store.ingest(scope, "demo-operator", "complete-responses", cohort_id, batch)
    receipt = app.learning.store.finalize(scope, "demo-operator", "finalize", cohort_id, opened["window_end"])
    replay = app.learning.store.finalize(scope, "demo-operator", "finalize", cohort_id, opened["window_end"])
    assert receipt == replay
    view = app.learning.store.view(scope, cohort_id) | {"clock_mode": "SIMULATED"}
    output.mkdir(parents=True, exist_ok=True)
    (output / "outcomes.json").write_text(json.dumps(batch, indent=2), encoding="utf-8")
    (output / "learning.json").write_text(json.dumps(view, indent=2), encoding="utf-8")
    return {"mode": "SIMULATED_CLOCK_SYNTHETIC_OUTCOMES", "organization": scope, "case_id": case, "cohort_id": cohort_id,
        "receipt": receipt, "replay_same_receipt": receipt == replay, "recommendations": view["recommendations"],
        "learning_html": str(write_learning(view, output / "learning.html")),
        "limitations": ["Scripted review and simulated agency.", "Synthetic outcomes and a simulated 28-day clock; no real campaign performance."]}
