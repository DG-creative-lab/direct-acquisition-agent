"""Explicit content-only orchestration over creative, reasoning and runtime public APIs."""

from acquisition.creative import (ChannelContentRequest, ChannelContentAgent, ChannelContentStore, CHANNEL_CONTENT_CAPABILITY)
from acquisition.contracts import digest
from acquisition.conversations import AdmissionIntent, ExecutionOwnership
from acquisition.reasoning import CallScope, ModelConfig, ModelError
from acquisition.runtime import Outcome, TaskSpec


def compose_paused_channel_admission(organization, request_id, source, context_id, context):
    admission_key='channel_admission_'+digest({'request_id':request_id})
    marker='admission_'+digest({'organization':organization,'request_id':admission_key})
    config=ModelConfig(**context['model_config'])
    inputs={'workflow_version':'channel-content/v1','context_id':context_id,'model_config':config.payload(),
            'run_request_id':'channel:'+request_id,'execution_admission_id':marker}
    if 'journey' in context:
        inputs['journey']=context['journey']
    parent=source['parent']
    return AdmissionIntent.from_tasks(organization=organization,request_id=admission_key,
        workflow_version='paused-channel-admission/v1',ownership=ExecutionOwnership(**source['owner']),
        source_id=context_id,source_fingerprint=digest(source),context_fingerprint=digest(context),
        parent_run_id=parent['run_id'] if parent else None,consent_id='consent_'+digest(source['permission']),
        model_config=config,tasks=[TaskSpec(CHANNEL_CONTENT_CAPABILITY,inputs,max_attempts=3)])


class ChannelContentWorkflow:
    def __init__(self, store: ChannelContentStore, inference): self.store, self.inference = store, inference

    def eligible(self, capability, inputs):
        return capability==CHANNEL_CONTENT_CAPABILITY and inputs.get('model_config')==self.inference.config.payload()

    def generate(self, claim):
        if (not self.eligible(claim.capability,claim.inputs) or claim.inputs.get('workflow_version')!='channel-content/v1'):
            raise ModelError('configure_original_channel_model_and_limits')
        context = self.store.load(claim.organization,claim.inputs['context_id'],run_id=claim.run_id)
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

    def ownership(self, organization, run_id): return self.store.ownership(organization,run_id)

    def reconcile_ownership(self, organization, run_id, fingerprint):
        return self.store.reconcile_ownership(organization,run_id,fingerprint)
