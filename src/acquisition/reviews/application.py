from .ports import ReviewStore


class ReviewService:
    def __init__(self, store: ReviewStore):
        self.store = store

    def refresh(self, organization: str, case_id: str, expected_subject: str, actor: str, request_id: str) -> dict:
        return self.store.refresh(organization, case_id, expected_subject, actor, request_id)

    def replace(self, organization: str, case_id: str, expected_subject: str, draft_id: str, actor: str, request_id: str) -> dict:
        authority = self.store.evidence(organization)
        if authority is None:
            raise ValueError("Activate evidence first")
        return self.store.propose(organization, case_id, expected_subject, draft_id, actor, request_id,
                                  authority["audience_epoch"], authority["evidence_epoch"])
