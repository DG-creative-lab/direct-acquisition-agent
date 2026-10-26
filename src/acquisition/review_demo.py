"""Scripted synthetic reviewer decisions, never represented as a real person."""

import csv
import io
import json
from pathlib import Path

from acquisition.contracts import Conflict, digest
from acquisition.reviews import ReviewPolicy
from acquisition.adapters.review_report import write_review


def run_review_demo(app, organization: str, request_id: str, output: Path, database_path: str) -> dict:
    scope = "scripted_" + digest({"organization": organization, "request_id": request_id})[:20]
    store = app.reviews.store
    store.register_actor(scope, "demo-operator", ("operator",))
    store.register_actor(scope, "scripted-reviewer", ("reviewer",))
    if store.evidence(scope) is None:
        pack = json.loads((Path(__file__).resolve().parents[2] / "config/iwoca-product-facts-v1.json").read_text())
        store.activate(scope, "demo-operator", "initial-evidence", pack, ReviewPolicy())
    # Fixture inputs remain stable across calendar days and process restarts.
    run_id = app.start(scope, request_id)
    app.worker.drain(scope)
    opened = store.open_case(scope, run_id, "demo-operator")
    case_id = opened["case_id"]
    view = store.view(scope, case_id)
    output.mkdir(parents=True, exist_ok=True)
    if view["handoff"]:
        exported = app.export_review(scope, case_id, output / "artifacts", view["subject"]["id"])
        view["export_directory"] = str(exported.resolve())
        return {"mode": "SCRIPTED_SYNTHETIC_REVIEW", "organization": scope, "case_id": case_id,
                "receipt": view["handoff"], "already_completed": True,
                "export_directory": str(exported.resolve()),
                "review_html": str(write_review(view, database_path, output / "review.html"))}
    earlier = [e["payload"] for e in view["events"] if e["kind"] == "review_approve"
               and e["payload"]["reason"] == "Scripted demonstration: first review."]
    if earlier:
        first = earlier[0]
    else:
        if not view["candidate_valid"]:
            app.reviews.refresh(scope, case_id, view["subject"]["id"], "demo-operator", "initial-refresh")
            view = store.view(scope, case_id)
        write_review(view, database_path, output / "before-approval.html")
        first = store.decide(scope, case_id, view["subject"]["id"], "scripted-reviewer", "approve", "first-decision",
                             "Scripted demonstration: first review.")
    first_subject = next(s for s in store.view(scope, case_id)["revisions"] if s["id"] == first["subject_id"])
    draft = app.drafts.get(scope, first_subject["draft_id"])
    business = next(csv.DictReader(io.StringIO(draft.mailing_csv)))["business_id"]
    store.suppress(scope, "demo-operator", "late-suppression", business, "Synthetic late suppression for the demonstration.")
    blocked = store.view(scope, case_id)
    write_review(blocked, database_path, output / "suppression-blocked.html")
    try:
        store.handoff(scope, case_id, first["id"], "demo-operator", "blocked-old-handoff")
    except Conflict as error:
        blocked_reason = str(error)
    else:
        raise AssertionError("Old approval unexpectedly authorized a simulated handoff")
    revised = app.reviews.refresh(scope, case_id, first["subject_id"], "demo-operator", "rebuild-after-suppression")
    final = store.decide(scope, case_id, revised["subject_id"], "scripted-reviewer", "approve", "revised-decision",
                         "Scripted demonstration: reviewed the revised synthetic draft.")
    receipt = store.handoff(scope, case_id, final["id"], "demo-operator", "simulated-handoff")
    # Treat the first response as lost. A repeated request observes the same job.
    replay = store.handoff(scope, case_id, final["id"], "demo-operator", "simulated-handoff")
    assert receipt == replay
    view = store.view(scope, case_id)
    exported = app.export_review(scope, case_id, output / "artifacts", view["subject"]["id"])
    view["export_directory"] = str(exported.resolve())
    path = write_review(view, database_path, output / "review.html")
    return {"mode": "SCRIPTED_SYNTHETIC_REVIEW", "organization": scope, "case_id": case_id,
            "original_subject": first["subject_id"], "revised_subject": revised["subject_id"],
            "suppressed_business": business, "old_handoff_blocked": blocked_reason, "receipt": receipt,
            "replay_same_receipt": receipt == replay, "changes": view["changes"],
            "review_html": str(path), "export_directory": str(exported.resolve()),
            "limitations": ["Scripted reviewer decisions, not a real human approval.", "Local simulated agency; nothing printed or sent."]}
