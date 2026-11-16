"""Bounded preparation steps composed from public conversation/campaign APIs."""
from acquisition.contracts import NotFound


class WorkspacePreparationHost:
    def __init__(self, conversation_app, draft_campaign, draft_generation, run_generation, models, lock):
        self.conversation_app = conversation_app
        self.draft_campaign = draft_campaign
        self.draft_generation = draft_generation
        self.run_generation = run_generation
        self.models = models
        self.lock = lock

    @staticmethod
    def _scope(organization):
        if organization != 'local-conversations':
            raise NotFound('Conversation organization is not available in this workspace')

    def freeze_preparation_plan(self, organization, conversation_id, request_id, revision, fixture, model_config=None):
        self._scope(organization)
        app = self.conversation_app(with_model=not fixture, model_config=model_config)
        return app.conversations.planning_context(organization, conversation_id, request_id, revision, fixture)


    def admit_preparation_plan(self, organization, row):
        self._scope(organization)
        inputs = row["inputs"]
        config = row['planning_context'].get('model_config')
        app = self.conversation_app(with_model=not inputs["fixture"], model_config=self.models.frozen(config))
        plan = app.conversations.plan_fixture if inputs["fixture"] else app.conversations.plan
        return plan(organization, inputs["conversation_id"], row["plan_request_id"], inputs["revision"],
                    frozen_context=row["planning_context"])


    def preparation_source(self, organization, conversation_id):
        self._scope(organization)
        app = self.conversation_app()
        return app.conversations.view(organization, conversation_id) | {'execution':app.execution.view(organization,conversation_id)}


    def step_preparation_plan(self, organization, row):
        self._scope(organization)
        with self.lock:
            config = row['planning_context'].get('model_config')
            app = self.conversation_app(with_model=not row["inputs"]["fixture"], model_config=self.models.frozen(config))
            app.worker.tick(organization, run_id=row["run_id"])
            return self.run_generation(app, organization, row["run_id"])


    def step_preparation_campaign(self, organization, row, plan):
        self._scope(organization)
        return self.draft_campaign(row["inputs"]["conversation_id"], row["id"] + ":draft",
                                       row["inputs"]["revision"], plan["id"], partial=True)


    def preparation_audience_selected(self, organization, row, plan):
        self._scope(organization)
        selected = self.conversation_app().conversation_audiences.store.get(organization, row['inputs']['conversation_id'], row['inputs']['revision'])
        return selected is not None and selected['plan_id'] == plan['id']


    def preparation_uses_catalogue(self, organization, row):
        self._scope(organization)
        inputs = row['inputs']
        return bool(inputs.get('use_audience_catalogue') or (
            inputs['fixture'] and row['request_id'].startswith('typed_effect_')
            and self.conversation_app().actions.store.is_typed_fixture_preparation(
                organization, inputs['conversation_id'], inputs['revision'], row['request_id'])))


    def preparation_generation(self, organization, row):
        self._scope(organization)
        generation = self.draft_generation(row['inputs']['conversation_id'], row['id']+':draft')
        if generation is not None:return generation
        app=self.conversation_app();run_id=row['run_id']
        if run_id is None:
            source=app.conversations.view(organization,row['inputs']['conversation_id'])
            plan=next((p for p in source['plans'] if p['request_id']==row['plan_request_id']),None)
            run_id=plan['run_id'] if plan else None
        return self.run_generation(app,organization,run_id) if run_id else None
