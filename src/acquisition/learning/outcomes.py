"""Synthetic response evidence, independent of preferences and model scores."""

import csv
import io
import math
from collections import Counter

from acquisition.contracts import Conflict, digest
from .domain import BetaBelief


WINDOW_SECONDS = 28 * 86400
PRIOR_ALPHA, PRIOR_BETA = 1, 19


def finite(value):
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError("Learning time must be finite")


def identifier(value):
    if (type(value) is not str or not 1 <= len(value) <= 160 or value != value.strip()
            or any(ord(c) < 32 for c in value) or chr(0x2014) in value):
        raise ValueError("A bounded plain identifier is required")


def cohort_proposal(organization, receipt, draft):
    if (receipt.get("mode") != "SYNTHETIC_NO_PRINT_NO_SEND" or receipt.get("draft_id") != draft.id
            or draft.manifest["organization"] != organization
            or receipt["mailing_sha256"] != draft.manifest["mailing_sha256"]
            or receipt["assignments_sha256"] != draft.manifest["assignments_sha256"]):
        raise Conflict("Cohort requires an exact accepted synthetic draft")
    finite(receipt["accepted_at"])
    end = receipt["accepted_at"] + WINDOW_SECONDS
    finite(end)
    members = list(csv.DictReader(io.StringIO(draft.assignments_csv)))
    expected = draft.manifest["arm_counts"]
    counts = Counter(r["segment"] + ":" + r["arm"] for r in members)
    if (not members or len(members) > 400_000 or len({r["business_id"] for r in members}) != len(members)
            or dict(counts) != expected or len(members) != receipt["recipients"] + draft.manifest["counts"]["holdout"]):
        raise Conflict("Cohort membership does not reconcile with the accepted experiment")
    creatives = {(c["segment"], c["arm"]): c["id"] for c in draft.manifest["creatives"]}
    for row in members:
        identifier(row["business_id"])
        if row["segment"] not in {"inventory", "contractors"} or row["arm"] not in {"A", "B", "no_mail"}:
            raise Conflict("Unknown experiment assignment")
        if row["creative_id"] != ("" if row["arm"] == "no_mail" else creatives[(row["segment"], row["arm"])]):
            raise Conflict("Creative assignment does not match the accepted catalogue")
    payload = {"schema": "synthetic-response-cohort/v1", "organization": organization,
        "case_id": receipt["case_id"], "job_id": receipt["id"], "draft_id": draft.id,
        "assignments_sha256": receipt["assignments_sha256"], "window_start": receipt["accepted_at"],
        "window_end": end, "metric": "synthetic_response_within_28_days", "mode": "SYNTHETIC_ONLY",
        "members": sorted(members, key=lambda r: r["business_id"])}
    return payload | {"id": "cohort_" + digest(payload)}


def validate_outcome(row, member, cohort, now):
    required = {"business_id", "segment", "arm", "creative_id", "response", "observed_at"}
    if type(row) is not dict or set(row) != required or type(row["response"]) is not bool:
        raise ValueError("Outcome must have the exact synthetic response schema")
    if any(row[k] != member[k] for k in ("business_id", "segment", "arm", "creative_id")):
        raise Conflict("Outcome does not match the frozen business assignment")
    finite(row["observed_at"])
    start, end = cohort["window_start"], cohort["window_end"]
    if row["observed_at"] > now:
        raise ValueError("Future observations cannot be imported")
    if row["response"]:
        if not start <= row["observed_at"] < end:
            raise ValueError("Response is outside the half-open observation window")
    elif row["observed_at"] != end:
        raise ValueError("A non-response must attest the entire closed window")


def counts_for(members, outcomes):
    if set(outcomes) != {r["business_id"] for r in members}:
        raise Conflict("Every enrolled business, including controls, needs an explicit outcome")
    groups = {}
    for member in members:
        key = (member["segment"], member["arm"], member["creative_id"])
        trials, successes = groups.get(key, (0, 0))
        groups[key] = trials + 1, successes + int(outcomes[member["business_id"]]["response"])
    return [posterior(segment, arm, creative, n, s) for (segment, arm, creative), (n, s) in sorted(groups.items())]


def posterior(segment, arm, creative_id, trials, successes):
    belief = BetaBelief(PRIOR_ALPHA, PRIOR_BETA).observe(trials, successes)
    mean = belief.alpha / (belief.alpha + belief.beta)
    variance = belief.alpha * belief.beta / ((belief.alpha + belief.beta) ** 2 * (belief.alpha + belief.beta + 1))
    return {"segment": segment, "arm": arm, "creative_id": creative_id, "trials": trials, "successes": successes,
        "alpha": belief.alpha, "beta": belief.beta, "mean": mean, "standard_deviation": math.sqrt(variance)}
