"""One command surface for workspace clients and bounded agent tools."""
from .domain import (YouTubeScope, YouTubeError, CONTRACT, PERMISSIONS, identity,
                     revision, text, fields)
from .ports import YouTubeStore


class YouTubeCampaigns:
    def __init__(self, store: YouTubeStore, scope: YouTubeScope, actor: str, *, reviewer: str | None = None):
        self.store, self.scope, self.actor = store, scope, identity(actor)
        self.reviewer = identity(reviewer) if reviewer is not None else self.actor

    def store_identity(self):
        return self.store.store_identity()

    def interactions(self, conversation_id):
        return self.store.interactions(self.scope, self.actor, identity(conversation_id))

    def message(self, command):
        fields(command, {'request_id', 'conversation_id', 'expected_revision', 'content', 'draft_permission'})
        identity(command['request_id']), identity(command['conversation_id'])
        revision(command['expected_revision'], create=True), text(command['content'], 2000)
        if command['draft_permission'] not in PERMISSIONS:
            raise ValueError('Use an explicit draft permission')
        return self.store.message(self.scope, self.actor, command)

    def read(self, campaign_id):
        return self.store.read(self.scope, self.actor, identity(campaign_id))

    def preview(self, context, fingerprint):
        return self.store.preview(self.scope, self.actor, context, fingerprint)

    def media(self, name, fingerprint):
        return self.store.media(self.scope, self.actor, name, fingerprint)

    def resume_command(self, operation_id, conversation_id):
        return self.store.resume_command(self.scope, self.actor, identity(operation_id), identity(conversation_id))

    def command(self, operation, command):
        keys = {'request_id', 'campaign_id'}
        if operation == 'save':
            keys |= {'expected_revision', 'draft'}
        elif operation in {'approve', 'export'}:
            keys |= {'subject'}
            if operation == 'export':
                keys |= {'approval_id'}
        elif operation == 'revoke':
            keys |= {'approval_id'}
        else:
            raise YouTubeError('capability_unavailable', 'This YouTube operation is not installed')
        fields(command, keys)
        identity(command['request_id']), identity(command['campaign_id'])
        if 'approval_id' in command:
            identity(command['approval_id'])
        if operation == 'save':
            revision(command['expected_revision'])
            fields(command['draft'], {'title', 'goal', 'contexts', 'placements'})
            text(command['draft']['title'], 120), text(command['draft']['goal'], 500)
        return self.store.command(self.scope, self.reviewer if operation in {'approve', 'revoke'} else self.actor, operation, command)


class YouTubeTools:
    """Agent entry point excludes human approval, revocation and download commands."""
    def __init__(self, campaigns: YouTubeCampaigns, permission='none', recommendations=None):
        self.campaigns, self.permission = campaigns, permission
        self.recommendations = recommendations

    def recommend_contextual_batch(self, campaign_id, expected_revision, **settings):
        if self.recommendations is None or self.recommendations.campaigns is not self.campaigns:
            raise YouTubeError('capability_unavailable', 'Offline recommendations are not installed here.')
        return self.recommendations.prepare(campaign_id, expected_revision, **settings)

    def read_campaign(self, campaign_id):
        return self.campaigns.read(campaign_id)

    def save_placement_draft(self, command):
        if self.permission != 'placements':
            raise YouTubeError('draft_permission_required', 'Allow a placement draft for this request')
        return self.campaigns.command('save', command)
