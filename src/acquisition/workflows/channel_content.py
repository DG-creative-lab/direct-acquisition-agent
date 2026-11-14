"""Explicit content-only orchestration over creative, reasoning and runtime public APIs."""

from acquisition.creative import (ChannelContentRequest, ChannelContentAgent, ChannelContentStore, CHANNEL_CONTENT_CAPABILITY)
from acquisition.reasoning import CallScope, ModelError
from acquisition.runtime import Outcome


class ChannelContentWorkflow:
    def __init__(self, store: ChannelContentStore, inference): self.store, self.inference = store, inference

    def eligible(self, capability, inputs):
        return capability==CHANNEL_CONTENT_CAPABILITY and inputs.get('model_config')==self.inference.config.payload()

    def generate(self, claim):
        if (not self.eligible(claim.capability,claim.inputs) or claim.inputs.get('workflow_version')!='channel-content/v1'):
            raise ModelError('configure_original_channel_model_and_limits')
        context = self.store.load(claim.organization,claim.inputs['context_id'])
        from datetime import datetime, timezone
        today = datetime.fromtimestamp(self.inference.clock(),timezone.utc).date()
        result = ChannelContentAgent(self.inference).generate(CallScope(claim.organization,claim.run_id,claim.task_id,claim.token),
            claim.inputs['context_id'],context,today)
        return Outcome('succeeded',result)


class ChannelPreparation:
    def __init__(self, store: ChannelContentStore, worker, tasks, inference):
        self.store, self.worker, self.tasks, self.inference = store, worker, tasks, inference

    def start(self, organization, request_id, profile_key, recipient_requests, channel, *, style='explore', parent_id=None):
        return self.store.admit(organization,request_id,ChannelContentRequest(profile_key,tuple(recipient_requests),channel,style,parent_id))

    def prepare(self, organization, request_id, profile_key, recipient_requests, channel, *, style='explore', parent_id=None):
        run_id = self.start(organization,request_id,profile_key,recipient_requests,channel,style=style,parent_id=parent_id)
        self.worker.drain(organization,run_id=run_id)
        return self.store.inspect(organization,request_id)

    def inspect(self, organization, request_id): return self.store.inspect(organization,request_id)
