import csv
import hashlib
import io
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date

from acquisition.audiences import Snapshot
from acquisition.contracts import canonical, digest
from acquisition.creative import Creative, creative_record


@dataclass(frozen=True)
class Brief:
    campaign_id: str
    budget_pence: int = 85000
    unit_cost_pence: int = 85
    max_candidates: int = 1000
    policy_version: str = "demo-marketing/v1"

    def __post_init__(self) -> None:
        if not self.campaign_id or self.policy_version != "demo-marketing/v1":
            raise ValueError("Unknown campaign or policy")
        for value in (self.budget_pence, self.unit_cost_pence, self.max_candidates):
            if type(value) is not int:
                raise ValueError("Money and counts must be integers")
        if self.budget_pence < 0 or self.unit_cost_pence <= 0 or not 0 < self.max_candidates <= 400_000:
            raise ValueError("Invalid budget, unit cost or candidate limit")


@dataclass(frozen=True)
class ConversationBrief(Brief):
    segments: tuple[str, ...] = ()
    conversation_id: str = ""
    conversation_revision: int = 0
    plan_id: str = ""

    def __post_init__(self) -> None:
        super().__post_init__()
        if (type(self.segments) is not tuple or not self.segments or len(set(self.segments)) != len(self.segments)
                or any(segment not in {"inventory", "contractors"} for segment in self.segments)
                or not self.conversation_id.startswith("conversation_") or not self.plan_id.startswith("brief_")
                or type(self.conversation_revision) is not int or self.conversation_revision < 1):
            raise ValueError("A conversation brief requires supported segments and exact proposal provenance")


def brief_from(payload: dict) -> Brief:
    if "segments" not in payload:
        return Brief(**payload)
    return ConversationBrief(**(payload | {"segments": tuple(payload["segments"])}))


@dataclass(frozen=True)
class Draft:
    manifest: dict
    mailing_csv: str
    assignments_csv: str

    @property
    def id(self) -> str:
        return "draft_" + digest(self.manifest)


def _csv(headers: tuple[str, ...], rows: list[tuple]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue()


def build_draft(snapshot: Snapshot, brief: Brief, creatives: tuple[Creative, ...]) -> Draft:
    """Complete batch computation, fixed experiment, no model or I/O."""
    if not snapshot.complete:
        raise ValueError("Incomplete audience snapshot")
    if snapshot.score_semantics != "synthetic_response_propensity_not_uplift":
        raise ValueError("Unsupported score semantics")
    catalogue = {(item.segment, item.arm): item for item in creatives}
    if len(catalogue) != len(creatives) or len({item.id for item in creatives}) != len(creatives):
        raise ValueError("Duplicate creative identity or segment/arm")
    segments = brief.segments if isinstance(brief, ConversationBrief) else ("inventory", "contractors")
    if set(catalogue) != {(s, a) for s in segments for a in ("A", "B")}:
        raise ValueError("Incomplete creative catalogue")
    identity_counts = Counter(row.business_id for row in snapshot.records)
    reasons: Counter[str] = Counter()
    eligible = []
    as_of = date.fromisoformat(snapshot.as_of)
    for row in snapshot.records:
        reason = None
        if identity_counts[row.business_id] > 1:
            reason = "duplicate_business"
        elif row.suppressed:
            reason = "suppressed"
        elif row.country != "UK" or row.entity_type not in {"LTD", "LLP"}:
            reason = "product_scope"
        elif not row.deliverable or not row.address.startswith("DEMO ONLY"):
            reason = "unusable_demo_address"
        elif row.propensity_ppm is None:
            reason = "missing_score"
        elif row.contacts_last_90_days >= 2:
            reason = "contact_cap"
        elif row.last_contact and (as_of - date.fromisoformat(row.last_contact)).days < 30:
            reason = "contact_cooldown"
        elif isinstance(brief, ConversationBrief) and row.segment not in segments:
            reason = "outside_selected_segment"
        if reason:
            reasons[reason] += 1
        else:
            eligible.append(row)
    eligible.sort(key=lambda row: (-row.propensity_ppm, row.business_id))
    # Enroll first, then randomize inside the same cohort. Conservative budget:
    # even if every enrolled business were mailed the cap would be respected.
    limit = min(brief.max_candidates, brief.budget_pence // brief.unit_cost_pence)
    cohort = eligible[:limit]
    assignment_rows, mailing_rows = [], []
    arm_counts: Counter[str] = Counter()
    for segment in segments:
        group = sorted((row for row in cohort if row.segment == segment), key=lambda row: digest({
            "algorithm": "hash-randomization/v1", "seed": snapshot.seed,
            "campaign": brief.campaign_id, "business": row.business_id,
        }))
        holdout = len(group) // 10
        for index, row in enumerate(group):
            arm = "no_mail" if index < holdout else ("A" if (index - holdout) % 2 == 0 else "B")
            creative = None if arm == "no_mail" else catalogue[(segment, arm)]
            arm_counts[f"{segment}:{arm}"] += 1
            assignment_rows.append((row.business_id, segment, arm, creative.id if creative else ""))
            if creative:
                mailing_rows.append((row.business_id, segment, arm, creative.id, row.address))
    mailing = _csv(("business_id", "segment", "arm", "creative_id", "demo_address"), sorted(mailing_rows))
    assignments = _csv(("business_id", "segment", "arm", "creative_id"), sorted(assignment_rows))
    selected = len(mailing_rows)
    held = len(cohort) - selected
    counts = {"input": len(snapshot.records), "excluded": sum(reasons.values()),
              "eligible_unselected": len(eligible) - len(cohort), "holdout": held, "mailed": selected}
    if counts["input"] != sum(value for key, value in counts.items() if key != "input"):
        raise AssertionError("Population did not reconcile")
    brief_data = asdict(brief)
    if isinstance(brief, ConversationBrief):
        brief_data["segments"] = list(brief.segments)
    manifest = {
        "schema": "draft/v1", "mode": "SYNTHETIC_DRY_RUN_UNAPPROVED",
        "organization": snapshot.organization, "snapshot_id": snapshot.id,
        "as_of": snapshot.as_of, "model_version": snapshot.model_version,
        "score_semantics": snapshot.score_semantics, "forecast_basis": "response_not_incremental_value",
        "brief": brief_data, "counts": counts, "exclusion_reasons": dict(sorted(reasons.items())),
        "assignment_algorithm": "hash-randomization/v1", "seed": snapshot.seed,
        "arm_counts": dict(sorted(arm_counts.items())),
        "variable_cost_pence": selected * brief.unit_cost_pence,
        "mailing_sha256": hashlib.sha256(mailing.encode()).hexdigest(),
        "assignments_sha256": hashlib.sha256(assignments.encode()).hexdigest(),
        "creatives": [creative_record(item) | {"id": item.id, "content_hash": item.content_hash}
                      for item in sorted(creatives, key=lambda c: c.id)],
        "limitations": ["No authority to print or send",
                        "Copy is generated and unreviewed" if any(item.status == "generated_unreviewed" for item in creatives)
                        else "Copy is fixed unapproved fixture content",
                        "Budget conservatively includes potential holdouts", "Small strata may have no holdout",
                        "Rows with missing scores are explicitly excluded; no complete scoring claim"],
    }
    canonical(manifest)  # Reject non-serializable/non-finite content before persistence.
    return Draft(manifest, mailing, assignments)
