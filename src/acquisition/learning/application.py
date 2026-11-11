from acquisition.contracts import NotFound

from .outcomes import identifier
from .ports import CohortSource, LearningStore, ReportMonitoringStore, ReportSource


class LearningService:
    def __init__(self, store: LearningStore, source: CohortSource, reports: ReportSource,
                 monitoring: ReportMonitoringStore):
        self.store, self.source, self.reports = store, source, reports
        self.monitoring = monitoring

    def open(self, organization, case_id, actor, request_id):
        proposal = self.source.accepted(organization, case_id)
        return self.store.open(organization, actor, request_id, proposal)

    def ingest_report(self, organization, actor, request_id, cohort_id, path):
        return self.store.ingest_report(organization, actor, request_id, cohort_id, self.reports.read(path))

    def schedule_reports(self, organization, actor, request_id, cohort_id, first_check, interval, paths):
        if not 1 <= len(paths) <= 12:
            raise ValueError("Choose 1 to 12 recorded reports")
        return self.monitoring.start(organization, actor, request_id, cohort_id, first_check, interval,
                                     [self.reports.read(path) for path in paths])

    def check_reports(self, organization, cohort_id, *, standalone=False, expected_position=None):
        identifier(cohort_id)
        token = self.monitoring.claim(organization, cohort_id, standalone=standalone, expected_position=expected_position)
        if token is not None:
            try:
                if self.monitoring.import_claim(organization, cohort_id, token):
                    self.monitoring.finish(organization, cohort_id, token)
            except (ValueError, NotFound) as error:
                self.monitoring.block(organization, cohort_id, token, str(error))
