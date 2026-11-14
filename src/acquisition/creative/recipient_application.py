"""Bounded offline retrieval. Source content cannot select tools, targets or effects."""

from .recipient_context import RecipientContextRequest, RecipientContextGuidance
from .ports import RecipientContextSource, RecipientContextStore


class RecipientContexts:
    def __init__(self, source: RecipientContextSource, store: RecipientContextStore,
                 guidance: RecipientContextGuidance):
        self.source, self.store, self.guidance = source, store, guidance

    def prepare(self, organization, request_id, assessment_id, contact_id, source_key, source_version,
                *, slots=('contact_role','prior_interaction'), max_facts=2):
        request = RecipientContextRequest(assessment_id,contact_id,source_key,source_version,slots,max_facts)
        replay = self.store.replay(organization,request_id,request)
        if replay is not None: return replay
        basis = self.store.capture(organization,request)
        evidence = None
        if basis.eligible:
            try:
                evidence = self.source.read(organization,source_key,source_version,basis.target)
            except Exception:
                # No raw exception or uncertain-effect retry. Installed adapters perform no paid I/O.
                pass
        return self.store.publish(organization,request_id,request,basis,self.guidance,evidence)

    def inspect(self, organization, request_id):
        return self.store.inspect(organization,request_id)

    def validate(self, organization, request_id, assertions):
        return self.store.validate(organization,request_id,assertions)
