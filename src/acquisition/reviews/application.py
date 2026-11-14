from .ports import ReviewStore, SequenceReviewStore


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


class SequenceReviews:
    """Agent-callable exact review operations; ordinary checks need no user clicks."""
    def __init__(self, store: SequenceReviewStore):
        self.store = store

    def preview(self, organization, proposal_id): return self.store.preview(organization,proposal_id)

    def open(self, organization, request_id, proposal_id, actor):
        return self.store.open(organization,request_id,proposal_id,actor)

    def view(self, organization, subject_id): return self.store.view(organization,subject_id)

    def decide(self, organization, request_id, subject_id, actor, decision, reason, ttl_seconds=86400):
        return self.store.decide(organization,request_id,subject_id,actor,decision,reason,ttl_seconds)

    def revoke(self, organization, request_id, approval_id, actor, reason):
        return self.store.revoke(organization,request_id,approval_id,actor,reason)

    def validate_output(self, organization, subject_id, output):
        return self.store.validate_output(organization,subject_id,output)
