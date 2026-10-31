"""Approval rules. A decision authorizes only a local simulated handoff."""

import csv
import io
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from acquisition.audiences import Snapshot
from acquisition.campaigns import ConversationBrief, FollowupBrief, Draft, brief_from, build_draft
from acquisition.contracts import Conflict, digest
from acquisition.creative import Creative, fact_pack_id, fixture_catalog, validate_fact_pack, validate_grounded_catalogue


def text(value: str, maximum: int = 500) -> None:
    if (type(value) is not str or not 1 <= len(value.strip()) <= maximum or value != value.strip()
            or any(ord(c) < 32 for c in value) or chr(0x2014) in value):
        raise ValueError("Use bounded plain text without control characters or em dashes")


def timestamp(now: float) -> None:
    if type(now) not in {int, float} or not math.isfinite(now):
        raise ValueError("Review timestamps must be finite")


@dataclass(frozen=True)
class ReviewPolicy:
    version: str = "synthetic-review/v1"
    max_approval_seconds: int = 86400
    allow_fixtures: bool = True

    def __post_init__(self):
        if (self.version != "synthetic-review/v1" or type(self.max_approval_seconds) is not int
                or not 1 <= self.max_approval_seconds <= 86400 or type(self.allow_fixtures) is not bool):
            raise ValueError("Unsupported review policy or approval lifetime")

    @property
    def id(self):
        return "policy_" + digest(asdict(self))


def creatives_from(draft: Draft) -> tuple[Creative, ...]:
    return tuple(Creative(**({k: v for k, v in item.items() if k not in {"id", "content_hash", "evidence_ids"}}
                            | {"evidence_ids": tuple(item.get("evidence_ids", []))})) for item in draft.manifest["creatives"])


def validate_population(draft: Draft, snapshot: Snapshot, suppressions: set[str]) -> None:
    creatives = creatives_from(draft)
    if snapshot.organization != draft.manifest.get("organization") or snapshot.id != draft.manifest.get("snapshot_id"):
        raise Conflict("Draft does not bind its audience snapshot")
    brief = brief_from(draft.manifest["brief"])
    if build_draft(snapshot, brief, creatives) != draft:
        raise Conflict("Draft is not the exact result of its recorded inputs")
    mailed = {row["business_id"] for row in csv.DictReader(io.StringIO(draft.mailing_csv))}
    if mailed & suppressions:
        raise Conflict("Current suppressions affect this draft; rebuild before review")


def validate_copy(draft: Draft, contexts: dict[str, dict], pack: dict, policy: ReviewPolicy, now: float) -> None:
    timestamp(now)
    today = datetime.fromtimestamp(now, timezone.utc).date()
    creatives = creatives_from(draft)
    brief = brief_from(draft.manifest["brief"])
    if all(c.status == "synthetic_fixture_unapproved" for c in creatives):
        expected = tuple(c for c in fixture_catalog() if not isinstance(brief, (ConversationBrief, FollowupBrief)) or c.segment in brief.segments)
        if not policy.allow_fixtures or set(creatives) != set(expected):
            raise Conflict("Only the known synthetic fixtures are permitted in fixture mode")
    elif all(c.status == "generated_unreviewed" and c.fact_pack_id == fact_pack_id(pack) for c in creatives):
        segments = brief.segments if isinstance(brief, (ConversationBrief, FollowupBrief)) else ("inventory", "contractors")
        if {c.segment for c in creatives} != set(segments):
            raise Conflict("Grounded copy must cover exactly the selected segments")
        for segment in segments:
            group = tuple(sorted((c for c in creatives if c.segment == segment), key=lambda c: c.arm))
            if len({c.context_id for c in group}) != 1 or not group or group[0].context_id not in contexts:
                raise Conflict("Grounded copy requires its exact frozen context")
            if isinstance(brief, ConversationBrief):
                frozen_brief = contexts[group[0].context_id].get("campaign_brief", {})
                if any(frozen_brief.get(key) != value for key, value in {
                    "plan_id": brief.plan_id, "budget_pence": brief.budget_pence, "segments": list(brief.segments)}.items()):
                    raise Conflict("Grounded copy context differs from the conversation brief")
            validate_grounded_catalogue(group, contexts[group[0].context_id], today)
    else:
        raise Conflict("Copy must use current grounded evidence or the explicit synthetic fixtures")


def validate_candidate(draft: Draft, snapshot: Snapshot, contexts: dict[str, dict], pack: dict,
                       policy: ReviewPolicy, suppressions: set[str], now: float) -> None:
    timestamp(now)
    validate_fact_pack(pack, datetime.fromtimestamp(now, timezone.utc).date())
    validate_population(draft, snapshot, suppressions)
    validate_copy(draft, contexts, pack, policy, now)


def subject(case_id: str, revision: int, draft: Draft, authority: dict) -> dict:
    payload = {"schema": "review-subject/v1", "organization": draft.manifest["organization"],
        "case_id": case_id, "revision": revision, "draft_id": draft.id,
        "snapshot_id": draft.manifest["snapshot_id"], "evidence_epoch": authority["evidence_epoch"],
        "audience_epoch": authority["audience_epoch"], "fact_pack_id": fact_pack_id(authority["pack"]),
        "policy_id": ReviewPolicy(**authority["policy"]).id, "purpose": "simulated_agency_handoff"}
    return payload | {"id": "subject_" + digest(payload)}


def current_reasons(proposal: dict, authority: dict) -> list[str]:
    current = authority | {"fact_pack_id": fact_pack_id(authority["pack"]), "policy_id": ReviewPolicy(**authority["policy"]).id}
    return [label for key, label in (("evidence_epoch", "Product evidence or policy changed"),
        ("audience_epoch", "Suppression state changed"), ("fact_pack_id", "Product pack changed"),
        ("policy_id", "Review policy changed")) if proposal[key] != current[key]]


REQUIRED_VALIDATION_CHECKS = frozenset({"artifact_integrity", "source_run", "source_provenance",
                                      "current_epochs", "product_evidence", "population_budget", "copy_contract"})


def validation_report(proposal, authority, checks, contexts, now, brief):
    """Read-time evidence, never an approval grant or a cached execution guard."""
    timestamp(now)
    if len({c["id"] for c in checks}) != len(checks) or not REQUIRED_VALIDATION_CHECKS <= {c["id"] for c in checks}:
        raise ValueError("Validation report is missing required checks")
    for check in checks:
        if check["status"] not in {"passed", "failed", "unknown", "not_evaluated"}:
            raise ValueError("Unknown validation status")
        if check["required"] != (check["id"] in REQUIRED_VALIDATION_CHECKS):
            raise ValueError("Validation requirement cannot be downgraded")
    payload = {"schema":"campaign-validation/v1", "checker_version":"campaign-readiness/v1",
               "organization":proposal["organization"], "subject_id":proposal["id"], "draft_id":proposal["draft_id"],
               "snapshot_id":proposal["snapshot_id"], "brief":brief, "evaluated_at":now, "purpose":"review_readiness_only", "authority":"none",
               "basis":{"evidence_epoch":authority["evidence_epoch"], "audience_epoch":authority["audience_epoch"],
                        "fact_pack_id":fact_pack_id(authority["pack"]), "policy_id":ReviewPolicy(**authority["policy"]).id},
               "reasoning_assets":[{"context_id":identity, "asset_id":context.get("agent_assets",{}).get("id"),
                    "editorial_version":context.get("guidance",{}).get("version"),
                    "product_pack_version":context.get("product_facts",{}).get("version"),
                    "sources":[{k:s[k] for k in ("id","key","kind","version","content_hash")}
                               for s in context.get("agent_assets",{}).get("sources",[])],
                    "skill_ids":[s["id"] for s in context.get("agent_assets",{}).get("skills",[])],
                    "source_ids":[s["id"] for s in context.get("agent_assets",{}).get("sources",[])]}
                    for identity,context in sorted(contexts.items())],
               "checks":checks,
               "review_ready":all(c["status"] == "passed" for c in checks if c["required"])}
    return payload | {"id":"validation_" + digest(payload)}
