from .ports import CohortSource, LearningStore


class LearningService:
    def __init__(self, store: LearningStore, source: CohortSource):
        self.store, self.source = store, source

    def open(self, organization, case_id, actor, request_id):
        proposal = self.source.accepted(organization, case_id)
        return self.store.open(organization, actor, request_id, proposal)
