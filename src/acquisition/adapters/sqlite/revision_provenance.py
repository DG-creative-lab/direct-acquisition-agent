"""Fence paid revision calls and proposal publication at their transactions."""

import json

from datetime import datetime, timezone
from acquisition.contracts import Conflict, digest
from acquisition.creative import validate_fact_pack
from acquisition.runtime import LeaseLost
from .actors import require_actor
from .conversation_provenance import require_current_conversation


def require_revision_current(db, organization, inputs, run_id=None, now=None):
    command = db.execute("SELECT receipt FROM review_commands WHERE organization=? AND request_id=?",
                         (organization, inputs["admission_request_id"])).fetchone()
    receipt = json.loads(command[0]) if command else {}
    expected = receipt.get("task_inputs", {})
    if "context_id" in inputs:
        expected = expected | {"context_id": "context_" + digest({"organization": organization, **receipt.get("context", {})})}
    if receipt.get("kind") != "copy_revision_admission" or expected != inputs:
        raise Conflict("Copy revision lacks its exact original admission")
    if run_id is not None:
        run = db.execute("SELECT request_id FROM runs WHERE organization=? AND id=?", (organization, run_id)).fetchone()
        if run is None or run[0] != receipt["id"]:
            raise Conflict("Copy revision cannot be dispatched in another run")
    actor = require_actor(db, organization, inputs["actor"], "operator")
    if actor["generation"] != inputs["operator_generation"]:
        raise Conflict("Revision operator authority changed")
    case = db.execute("SELECT * FROM review_cases WHERE organization=? AND id=?", (organization, inputs["case_id"])).fetchone()
    if case is None or case["current_subject"] != inputs["expected_subject"]:
        raise Conflict("The copy revision refers to an older subject")
    original_run = db.execute("SELECT status FROM runs WHERE organization=? AND id=?", (organization, case["run_id"])).fetchone()
    if original_run is None or original_run[0] not in {"waiting", "succeeded"}:
        raise Conflict("Original campaign run is no longer reviewable")
    authority = db.execute("SELECT * FROM review_authorities WHERE organization=?", (organization,)).fetchone()
    if authority is None or (authority["audience_epoch"], authority["evidence_epoch"]) != (inputs["audience_epoch"], inputs["evidence_epoch"]):
        raise Conflict("Evidence or suppressions changed during copy revision")
    if now is not None:
        validate_fact_pack(json.loads(authority["pack"]), datetime.fromtimestamp(now, timezone.utc).date())
    if db.execute("SELECT 1 FROM simulated_agency_jobs WHERE organization=? AND case_id=?", (organization, inputs["case_id"])).fetchone():
        raise Conflict("Accepted campaigns cannot be revised")
    require_current_conversation(db, inputs["brief"])


def require_revision_lease(db, organization, claim, now):
    task = db.execute("SELECT t.*,r.status AS run_status,r.organization FROM tasks t JOIN runs r ON r.id=t.run_id WHERE t.id=? AND t.run_id=?",
                      (claim.task_id, claim.run_id)).fetchone()
    if (task is None or task["organization"] != organization or claim.organization != organization
            or task["run_status"] != "running" or task["status"] != "running"
            or task["capability"] != "reviews.publish_copy_revision.v3" or claim.capability != task["capability"]
            or task["token"] != claim.token or task["lease_until"] <= now
            or json.loads(task["inputs"]) != claim.inputs):
        raise LeaseLost("Copy revision publication requires its active exact task lease")
