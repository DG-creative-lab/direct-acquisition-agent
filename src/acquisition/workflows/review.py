from dataclasses import replace

from acquisition.audiences import AudienceStore
from acquisition.campaigns import brief_from, CampaignService, DraftStore
from acquisition.reviews import creatives_from


class ReviewProposalBuilder:
    def __init__(self, audiences: AudienceStore, drafts: DraftStore, campaigns: CampaignService):
        self.audiences, self.drafts, self.campaigns = audiences, drafts, campaigns

    def refresh(self, organization: str, draft_id: str, suppressions: tuple[str, ...], operation: str) -> str:
        draft = self.drafts.get(organization, draft_id)
        snapshot = self.audiences.get(organization, draft.manifest["snapshot_id"])
        blocked = set(suppressions)
        updated = replace(snapshot, records=tuple(replace(row, suppressed=True) if row.business_id in blocked else row
                                                  for row in snapshot.records))
        snapshot_id = self.audiences.put(updated)
        return self.campaigns.prepare_with_catalogue(organization, snapshot_id, brief_from(draft.manifest["brief"]),
                                                      operation, creatives_from(draft))["draft_id"]
