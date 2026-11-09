"""The approved plan and provider evidence for local postal delivery simulation."""

import csv
import io

from acquisition.contracts import Conflict, digest


DELIVERY_SIMULATIONS = ("accept", "partial", "reject", "timeout-after-acceptance")
DELIVERY_MODE = "SYNTHETIC_NO_PRINT_NO_SEND"
DELIVERY_DESTINATION = "local_simulated_agency"


def delivery_plan(organization, proposal, approval_id, draft):
    recipients = sorted(row["business_id"] for row in csv.DictReader(io.StringIO(draft.mailing_csv)))
    counts = draft.manifest["counts"]
    if len(recipients) != counts["mailed"] or len(set(recipients)) != len(recipients):
        raise Conflict("Delivery recipients differ from the approved mailing")
    return {
        "organization": organization, "case_id": proposal["case_id"],
        "subject_id": proposal["id"], "approval_id": approval_id, "draft_id": draft.id,
        "mode": DELIVERY_MODE, "channel": "direct_mail", "destination": DELIVERY_DESTINATION,
        "mailing_sha256": draft.manifest["mailing_sha256"],
        "assignments_sha256": draft.manifest["assignments_sha256"],
        "creatives": draft.manifest["creatives"],
        "variable_cost_pence": draft.manifest["variable_cost_pence"],
        "budget_pence": draft.manifest["brief"]["budget_pence"],
        "recipient_ids": recipients, "control_count": counts["holdout"],
    }


def delivery_summary(result):
    keys = ("id", "mode", "status", "intended_recipients", "control_count",
            "accepted_recipients", "rejected_recipients", "recorded_at")
    return {key: result[key] for key in keys} | {"result_hash": digest(result)}


def validate_delivery_result(plan, result):
    accepted, rejected = result["accepted_recipient_ids"], result["rejected_recipient_ids"]
    status = "partially_accepted" if accepted and rejected else "accepted" if accepted else "rejected"
    if (any(result[key] != plan[key] for key in ("organization", "case_id", "approval_id", "mode", "control_count"))
            or sorted(accepted + rejected) != plan["recipient_ids"]
            or result["status"] != status or result["intended_recipients"] != len(plan["recipient_ids"])
            or result["accepted_recipients"] != len(accepted) or result["rejected_recipients"] != len(rejected)
            or any(result[key] is not None for key in ("sent", "delivered", "responded"))):
        raise Conflict("Provider result differs from the approved population or simulation")
