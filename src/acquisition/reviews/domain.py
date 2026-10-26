"""Approval rules. A decision authorizes only a local simulated handoff."""

import csv
import io
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from acquisition.audiences import Snapshot
from acquisition.campaigns import Brief, Draft, build_draft
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


def validate_candidate(draft: Draft, snapshot: Snapshot, contexts: dict[str, dict], pack: dict,
                       policy: ReviewPolicy, suppressions: set[str], now: float) -> None:
    timestamp(now)
    today = datetime.fromtimestamp(now, timezone.utc).date()
    validate_fact_pack(pack, today)
    if snapshot.organization != draft.manifest.get("organization") or snapshot.id != draft.manifest.get("snapshot_id"):
        raise Conflict("Draft does not bind its audience snapshot")
    creatives = creatives_from(draft)
    if build_draft(snapshot, Brief(**draft.manifest["brief"]), creatives) != draft:
        raise Conflict("Draft is not the exact result of its recorded inputs")
    mailed = {row["business_id"] for row in csv.DictReader(io.StringIO(draft.mailing_csv))}
    if mailed & suppressions:
        raise Conflict("Current suppressions affect this draft; rebuild before review")
    if all(c.status == "synthetic_fixture_unapproved" for c in creatives):
        if not policy.allow_fixtures or set(creatives) != set(fixture_catalog()):
            raise Conflict("Only the known synthetic fixtures are permitted in fixture mode")
    elif all(c.status == "generated_unreviewed" and c.fact_pack_id == fact_pack_id(pack) for c in creatives):
        for segment in ("inventory", "contractors"):
            group = tuple(sorted((c for c in creatives if c.segment == segment), key=lambda c: c.arm))
            if len({c.context_id for c in group}) != 1 or not group or group[0].context_id not in contexts:
                raise Conflict("Grounded copy requires its exact frozen context")
            validate_grounded_catalogue(group, contexts[group[0].context_id], today)
    else:
        raise Conflict("Copy must use current grounded evidence or the explicit synthetic fixtures")


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
