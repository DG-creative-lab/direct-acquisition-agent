from acquisition.campaigns import DraftStore
from acquisition.contracts import Conflict
from acquisition.learning import cohort_proposal
from acquisition.reviews import ReviewStore


class AcceptedCohortSource:
    def __init__(self, reviews: ReviewStore, drafts: DraftStore):
        self.reviews, self.drafts = reviews, drafts

    def accepted(self, organization, case_id):
        view = self.reviews.view(organization, case_id)
        if not view["handoff"]:
            raise Conflict("Learning requires an accepted simulated campaign")
        draft = self.drafts.get(organization, view["handoff"]["draft_id"])
        return cohort_proposal(organization, view["handoff"], draft)
