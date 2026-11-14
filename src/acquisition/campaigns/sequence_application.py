from .ports import SequenceProposalStore
from .sequences import SequenceRequest


class SequenceCampaigns:
    def __init__(self, store: SequenceProposalStore): self.store=store
    def prepare(self, organization, request_id, request: SequenceRequest):
        if type(request) is not SequenceRequest: raise ValueError('Use the exact typed sequence request')
        return self.store.prepare(organization,request_id,request)
    def inspect(self, organization, proposal_id): return self.store.inspect(organization,proposal_id)
