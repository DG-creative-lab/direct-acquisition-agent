from .ports import CohortSource, LearningStore, ReportSource


class LearningService:
    def __init__(self, store: LearningStore, source: CohortSource, reports: ReportSource):
        self.store, self.source, self.reports = store, source, reports

    def open(self, organization, case_id, actor, request_id):
        proposal = self.source.accepted(organization, case_id)
        return self.store.open(organization, actor, request_id, proposal)

    def ingest_report(self, organization, actor, request_id, cohort_id, path):
        return self.store.ingest_report(organization, actor, request_id, cohort_id, self.reports.read(path))
