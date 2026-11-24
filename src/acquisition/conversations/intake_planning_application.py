"""Saved intake interpretation over native planning, with no preparation capability."""

from acquisition.contracts import Conflict, NotFound
from .ports import IntakePlanningStore
from acquisition.reasoning import ModelError


class IntakePlanningRejected(Conflict):
    """The original request has no staged source, admission or inference."""


class IntakePlanning:
    def __init__(self, store: IntakePlanningStore, conversations, clock):
        self.store, self.conversations, self.clock = store, conversations, clock

    def request(self, organization, actor, request_id, brief_id, brief_revision):
        config = self.conversations.config
        if config is None:
            raise ValueError('Connect a planner before explicitly requesting interpretation')
        try:
            source = self.store.prepare(organization, actor, request_id, brief_id, brief_revision,
                                        config.payload(), self.clock(), self.conversations.intake_context)
            return self.conversations.plan_intake(source)
        except (ValueError, NotFound, ModelError) as error:
            try:
                self.store.request(organization, request_id)
            except NotFound:
                raise IntakePlanningRejected(str(error)) from error
            raise

    def view(self, organization, request_id):
        source = self.store.request(organization, request_id)
        native = self.conversations.view(organization, source['conversation_id'])
        plan = next((p for p in native['plans'] if p['request_id'] == request_id), None)
        if plan and plan['revision'] != source['revision']:
            raise Conflict('Intake result differs from its original source revision')
        return {'request_id':request_id, 'source':source, 'current':self.store.current(organization, source),
                'plan':plan, 'authority':'none', 'execution':'unavailable', 'store_id':source['store_id']}

    def listing(self, organization, brief_id):
        return [self.view(organization, row['request_id']) for row in self.store.listing(organization, brief_id)]
