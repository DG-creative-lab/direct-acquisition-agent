"""Authored YouTube preparation on the existing runtime, with zero model calls."""
from acquisition.contracts import Conflict, NotFound, digest
from acquisition.conversations import (AdmissionIntent, ExecutionOwnership, MessageRejectedConflict,
                                      MessageRejectedInvalid, MessageRejectedNotFound)
from acquisition.runtime import TaskSpec, Outcome
from acquisition.youtube import CAPABILITY, YouTubeError, authored_draft


def compose_youtube_admission(scope, operation_id, frozen):
    inputs = {'workflow_version': 'youtube-preparation/v1', 'operation_id': operation_id,
              'context_fingerprint': frozen['context_fingerprint']}
    return AdmissionIntent.from_tasks(
        organization=scope.organization, request_id=operation_id, workflow_version='youtube-preparation/v1',
        ownership=ExecutionOwnership('conversation', scope.organization, frozen['command']['conversation_id'], frozen['source_revision']),
        source_id=operation_id, source_fingerprint=digest(frozen), context_fingerprint=frozen['context_fingerprint'],
        tasks=[TaskSpec(CAPABILITY, inputs, max_attempts=3)])


class YouTubePreparation:
    def __init__(self, campaigns, tasks, worker, *, initialize_authority=None):
        self.campaigns, self.tasks, self.worker = campaigns, tasks, worker
        self.initialize_authority = initialize_authority

    def message(self, command):
        if self.initialize_authority is not None:
            self.initialize_authority()
        # Only the atomic admission can prove that this attempt saved no message.
        # Worker/publication/read failures below retain the original request.
        try:
            receipt = self.campaigns.message(command)
        except YouTubeError as error:
            raise YouTubeError(error.code, str(error), message_not_saved=True) from error
        except (Conflict, NotFound, ValueError) as error:
            kind = MessageRejectedConflict if isinstance(error, Conflict) else MessageRejectedNotFound if isinstance(error, NotFound) else MessageRejectedInvalid
            raise kind(str(error)) from error
        run = receipt['result']['run_id']
        if run:
            self.worker.drain(self.campaigns.scope.organization, run_id=run, max_tasks=1)
        return receipt

    def resume(self, operation_id, conversation_id):
        return self.message(self.campaigns.resume_command(operation_id, conversation_id))


class AuthoredYouTubeHandler:
    def __init__(self, store, fixture):
        self.store, self.fixture = store, fixture

    def prepare(self, claim):
        source = self.store.load_operation(claim.organization, claim.inputs['operation_id'])
        frozen = source['frozen']
        if source['admission']['tasks'][0]['inputs'] != claim.inputs or frozen['context_fingerprint'] != digest(self.fixture):
            raise YouTubeError('source_changed', 'The authored request changed')
        return Outcome('succeeded', {'draft': authored_draft(frozen, self.fixture)})
