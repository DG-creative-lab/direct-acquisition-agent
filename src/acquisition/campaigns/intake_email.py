"""Public offline email preparation API, independent of approval and delivery."""
from .ports import IntakeEmailStore
from .intake import intake_identity
from .preparation_eligibility import GroundedPreparationRequest


class IntakeEmails:
    def __init__(self,store: IntakeEmailStore,clock):self.store,self.clock=store,clock
    def preview(self,organization,context_request_id):
        for v in (organization,context_request_id):intake_identity(v)
        return self.store.preview(organization,context_request_id,self.clock())
    def prepare(self,organization,actor,request_id,request):
        for v in (organization,actor,request_id):intake_identity(v)
        if type(request) is not GroundedPreparationRequest:raise ValueError('Use an exact email source review')
        return self.store.prepare(organization,actor,request_id,request)
    def request(self,organization,request_id):
        for v in (organization,request_id):intake_identity(v)
        return self.store.request(organization,request_id,self.clock())
    def not_committed(self,organization,request_id):
        for v in (organization,request_id):intake_identity(v)
        return self.store.not_committed(organization,request_id)
