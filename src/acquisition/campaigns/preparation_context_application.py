"""Review saved intake through one atomic store; no model or campaign capability."""

from .intake import intake_identity, intake_revision
from .preparation_context import PreparationReview, context_time
from .ports import PreparationContextStore


class ReviewedPreparation:
    def __init__(self, store: PreparationContextStore, clock):
        self.store, self.clock = store, clock

    def preview(self, organization, brief_id, brief_revision):
        for value in (organization, brief_id):intake_identity(value)
        intake_revision(brief_revision, positive=True)
        return self.store.preview(organization, brief_id, brief_revision)

    def confirm(self, organization, actor, request_id, review: PreparationReview):
        for value in (organization, actor, request_id):intake_identity(value)
        if type(review) is not PreparationReview:raise ValueError('Use an exact preparation input review')
        now = self.clock();context_time(now)
        return self.store.confirm(organization, actor, request_id, review, now)

    def request(self, organization, request_id):
        for value in (organization, request_id):intake_identity(value)
        now = self.clock();context_time(now)
        return self.store.request(organization, request_id, now)

    def history(self, organization, brief_id):
        for value in (organization, brief_id):intake_identity(value)
        now = self.clock();context_time(now)
        return self.store.history(organization, brief_id, now)

    def not_committed(self, organization, request_id):
        for value in (organization, request_id):intake_identity(value)
        return self.store.not_committed(organization, request_id)
