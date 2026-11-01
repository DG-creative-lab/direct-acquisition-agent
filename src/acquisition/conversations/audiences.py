"""Exact audience confirmation for a current, completed conversation proposal."""
from dataclasses import asdict, replace
import json
from datetime import datetime, timezone

from acquisition.audiences import AudienceDiscovery, AudienceStore, DatasetVersion, validate_dataset
from acquisition.contracts import Conflict, digest, canonical
from .domain import identity, revision_number
from .ports import AudienceSelectionStore


class AudienceSelectionRejected(Conflict):
    """The selection command was definitively rejected before commitment."""


class ConversationAudiences:
    def __init__(self, conversations, discovery: AudienceDiscovery, selections: AudienceSelectionStore,
                 snapshots: AudienceStore, clock):
        self.conversations, self.discovery, self.store = conversations, discovery, selections
        self.snapshots, self.clock = snapshots, clock

    def _plan(self, organization, conversation_id, revision, plan_id):
        view = self.conversations.view(organization, conversation_id)
        plan = view['current_plan']
        result = plan['result'] if plan and plan['status'] == 'succeeded' else None
        if view['revision'] != revision or not result or result['id'] != plan_id or result['outcome'] != 'brief_proposal':
            raise Conflict('Select an audience for the exact current completed proposal')
        return result

    def candidates(self, organization, conversation_id, revision, plan_id):
        plan = self._plan(organization, conversation_id, revision, plan_id)
        result = self.discovery.discover(organization)
        entries = [e for e in result['entries'] if set(e['segments']) == set(plan['segments'])]
        return result | {'entries': entries, 'resolution': 'none' if not entries else 'single' if len(entries)==1 else 'ambiguous',
                         'plan_id':plan_id, 'revision':revision}

    def select(self, organization, conversation_id, request_id, expected_revision, plan_id,
               dataset_id, version, checksum, manifest_id):
        for value in (organization, conversation_id, request_id, plan_id): identity(value)
        revision_number(expected_revision)
        inputs = dict(conversation_id=conversation_id, revision=expected_revision, plan_id=plan_id,
                      dataset_id=dataset_id, version=version, checksum=checksum, manifest_id=manifest_id)
        prior = self.store.request(organization, request_id)
        if prior:
            if prior['inputs'] != inputs:
                raise Conflict('Audience request already binds different selection inputs')
            return prior['receipt']
        plan = self._plan(organization, conversation_id, expected_revision, plan_id)
        manifest, snapshot = self.discovery.read(organization, dataset_id, version, checksum, manifest_id)
        if set(manifest.segments) != set(plan['segments']):
            raise Conflict('Dataset coverage does not match the proposed segments')
        receipt = {'organization':organization, 'conversation_id':conversation_id, 'revision':expected_revision,
                   'plan_id':plan_id, 'source':asdict(manifest), 'manifest_id':manifest.id,
                   'source_snapshot_id':snapshot.id, 'authority':'none'}
        receipt['id'] = 'selection_' + digest(receipt)
        receipt = json.loads(canonical(receipt))
        return self.store.select(organization, request_id, inputs, receipt, snapshot, self.clock())

    def materialize(self, organization, conversation_id, revision, plan_id, campaign_organization):
        selection = self.store.get(organization, conversation_id, revision)
        if selection is None or selection['plan_id'] != plan_id:
            raise Conflict('Confirm an exact audience dataset before campaign preparation')
        self._plan(organization, conversation_id, revision, plan_id)
        snapshot = self.snapshots.get(organization, selection['source_snapshot_id'])
        source = selection['source'] | {'segments':tuple(selection['source']['segments'])}
        validate_dataset(DatasetVersion(**source), snapshot, organization,
                         datetime.fromtimestamp(self.clock(),timezone.utc).date())
        return replace(snapshot, organization=campaign_organization), selection
