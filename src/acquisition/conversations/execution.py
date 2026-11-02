"""Conversation-wide limits supplement each capability's existing permission."""

from .domain import identity, revision_number
from .ports import ExecutionStore


class ConversationExecution:
    def __init__(self, store: ExecutionStore, clock):
        self.store, self.clock = store, clock

    def view(self, organization, conversation_id):
        identity(organization), identity(conversation_id)
        return self.store.view(organization, conversation_id)

    def stop(self, organization, conversation_id, request_id, expected_revision):
        identity(organization), identity(conversation_id), identity(request_id), revision_number(expected_revision)
        if expected_revision < 1:
            raise ValueError('Select a saved brief before stopping work')
        return self.store.stop(organization, conversation_id, request_id, expected_revision, self.clock())

    def for_run(self, organization, run_id):
        return self.store.for_run(organization, run_id)

    def pending(self, organization, run_id):
        return self.store.pending(organization,run_id)

    def descendant(self, organization, campaign_id, parent_run_id):
        identity(organization), identity(campaign_id), identity(parent_run_id)
        return self.store.descendant(organization,campaign_id,parent_run_id)

    def stopped_checkpoints(self, organization):
        identity(organization)
        return self.store.stopped_checkpoints(organization)

    def unresolved(self, organization):
        identity(organization)
        return self.store.unresolved(organization)

    def resolve_independent(self, organization, request_id, run_id, fingerprint, actor, reason):
        for value in (organization,request_id,run_id,actor):identity(value)
        if not isinstance(fingerprint,str) or len(fingerprint)!=64 or any(c not in '0123456789abcdef' for c in fingerprint):
            raise ValueError('Use the exact inspection fingerprint')
        if not isinstance(reason,str) or not 1<=len(reason.strip())<=500:
            raise ValueError('Provide an independent-run attestation of 1 to 500 characters')
        inputs={'run_id':run_id,'fingerprint':fingerprint,'actor':actor,'reason':reason.strip()}
        return self.store.resolve_independent(organization,request_id,inputs,self.clock())
