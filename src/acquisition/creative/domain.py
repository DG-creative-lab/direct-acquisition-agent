from dataclasses import asdict, dataclass

from acquisition.contracts import digest


def writing_preference(action, expected_revision, segments, preferred, avoid, reason, confirmed):
    """Explicit editorial intent, independent of approval and observed outcomes."""
    if confirmed is not True:
        raise ValueError("Explicit writing preference confirmation required")
    if (type(action) is not str or action not in {"confirm", "correct", "retire"}
            or type(expected_revision) is not int or expected_revision < 0):
        raise ValueError("Select a writing preference action and exact version")
    if (not isinstance(segments, list) or not segments
            or any(type(segment) is not str or segment not in {"inventory", "contractors"} for segment in segments)
            or len(set(segments)) != len(segments)):
        raise ValueError("Select one or both supported audiences")
    for value, required in ((preferred, True), (avoid, False), (reason, True)):
        if (type(value) is not str or len(value) > 600 or (required and not value.strip())
                or any(ord(c) < 32 and c != '\n' for c in value)):
            raise ValueError("Use bounded writing guidance and a reason")
    return {"segments": sorted(segments), "preferred": preferred.strip(), "avoid": avoid.strip(), "reason": reason.strip()}


@dataclass(frozen=True)
class Creative:
    key: str
    segment: str
    arm: str
    opening: str
    status: str = "synthetic_fixture_unapproved"
    headline: str = ""
    locked_block: str = ""
    hypothesis: str = ""
    context_id: str = ""
    model: str = ""
    evidence_ids: tuple[str, ...] = ()
    fact_id: str = ""
    fact_pack_id: str = ""
    claim_check: str = ""

    @property
    def id(self) -> str:
        return self.key + ":" + self.content_hash

    @property
    def content_hash(self) -> str:
        if self.headline or self.locked_block:
            return digest({"headline": self.headline, "opening": self.opening,
                           "locked_block": self.locked_block, "renderer": "plain-text/v2"})
        return digest({"opening": self.opening, "renderer": "plain-text/v1"})


def fixture_catalog() -> tuple[Creative, ...]:
    """Known inputs for day one, never represented as generated or approved copy."""
    return (
        Creative("inventory-A-v1", "inventory", "A", "DEMO: Explore options for your next stock order."),
        Creative("inventory-B-v1", "inventory", "B", "DEMO: Plan working capital around your stock cycle."),
        Creative("contractors-A-v1", "contractors", "A", "DEMO: Explore options for upcoming project costs."),
        Creative("contractors-B-v1", "contractors", "B", "DEMO: Plan around the gap between costs and receipts."),
    )


def creative_record(item: Creative) -> dict:
    """Keep the original v1 fixture serialization stable across additive fields."""
    if not any((item.headline, item.locked_block, item.hypothesis, item.context_id, item.model, item.evidence_ids,
                item.fact_id, item.fact_pack_id, item.claim_check)):
        return {key: getattr(item, key) for key in ("key", "segment", "arm", "opening", "status")}
    result = asdict(item)
    result["evidence_ids"] = list(item.evidence_ids)
    for field in ("fact_id", "fact_pack_id", "claim_check"):
        if not result[field]:
            del result[field]
    return result
