from acquisition.audiences import AudienceStore
from acquisition.contracts import digest
from acquisition.creative import Creative, creative_record

from .domain import Brief, build_draft
from .ports import DraftStore


class CampaignService:
    def __init__(self, audiences: AudienceStore, drafts: DraftStore, creatives: tuple[Creative, ...]):
        self.audiences, self.drafts, self.creatives = audiences, drafts, creatives

    @property
    def catalogue_hash(self) -> str:
        return digest([creative_record(item) for item in self.creatives])

    def prepare(self, organization: str, snapshot_id: str, brief: Brief, operation_id: str) -> dict:
        return self.prepare_with_catalogue(organization, snapshot_id, brief, operation_id, tuple(c for c in self.creatives if not hasattr(brief, "segments") or c.segment in brief.segments))

    def prepare_with_catalogue(self, organization: str, snapshot_id: str, brief: Brief,
                               operation_id: str, creatives: tuple[Creative, ...]) -> dict:
        snapshot = self.audiences.get(organization, snapshot_id)
        draft = build_draft(snapshot, brief, creatives)
        draft_id = self.drafts.put(organization, operation_id, draft)
        return {"draft_id": draft_id, "manifest_hash": draft_id.removeprefix("draft_"),
                "counts": draft.manifest["counts"], "variable_cost_pence": draft.manifest["variable_cost_pence"]}
