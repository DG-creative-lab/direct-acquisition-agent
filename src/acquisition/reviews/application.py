from .ports import ProposalBuilder, ReviewStore


class ReviewService:
    def __init__(self, store: ReviewStore, builder: ProposalBuilder):
        self.store, self.builder = store, builder

    def refresh(self, organization: str, case_id: str, expected_subject: str, actor: str, request_id: str) -> dict:
        view = self.store.prepare(organization, case_id, expected_subject, actor, request_id)
        if "receipt" in view:
            return view["receipt"]
        # Preparation may leave an unreferenced immutable artifact if another
        # revision wins. Only the store's compare-and-swap publishes a proposal.
        draft_id = self.builder.refresh(organization, view["subject"]["draft_id"],
                                       tuple(view["suppressions"]), case_id + ":refresh:" + request_id)
        return self.store.propose(organization, case_id, expected_subject, draft_id, actor, request_id,
                                  view["authority"]["audience_epoch"], view["authority"]["evidence_epoch"], kind="refresh")

    def replace(self, organization: str, case_id: str, expected_subject: str, draft_id: str, actor: str, request_id: str) -> dict:
        authority = self.store.evidence(organization)
        if authority is None:
            raise ValueError("Activate evidence first")
        return self.store.propose(organization, case_id, expected_subject, draft_id, actor, request_id,
                                  authority["audience_epoch"], authority["evidence_epoch"])
