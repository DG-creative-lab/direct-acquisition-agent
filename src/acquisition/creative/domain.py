from dataclasses import asdict, dataclass

from acquisition.contracts import digest


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
