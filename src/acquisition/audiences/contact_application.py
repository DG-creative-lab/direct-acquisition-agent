"""Agent-consumable preparation API. No campaign, approval or external-effect capability."""

from .ports import ContactDirectoryStore, ContactSource


class ContactDirectory:
    def __init__(self, source: ContactSource, store: ContactDirectoryStore):
        self.source, self.store = source, store

    def refresh(self, organization, request_id, connection_key, version):
        return self.store.refresh(organization, request_id, self.source.read(organization, connection_key, version))

    def prepare(self, organization, request_id, connection_key, version, channel, purpose='acquisition'):
        snapshot = self.source.read(organization, connection_key, version)
        return self.store.prepare(organization, request_id, snapshot, channel, purpose)

    def object(self, organization, request_id, contact_id, channel, purpose, reason):
        return self.store.object(organization, request_id, contact_id, channel, purpose, reason)

    def inspect(self, organization, assessment_id):
        return self.store.inspect(organization, assessment_id)
