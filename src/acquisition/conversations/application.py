from collections.abc import Callable
import re

from acquisition.contracts import Conflict, NotFound, digest
from acquisition.reasoning import CallJournal, ModelConfig
from acquisition.runtime import TaskSpec, TaskStore

from .domain import CAPABILITY, FIXTURE_CAPABILITY, FIXTURE_MESSAGE, KNOWLEDGE
from .ports import ConversationStore
from .scope import requested_scope
from .budgets import BUDGET_POLICY
from .intake_planning import INTAKE_KNOWLEDGE, bind_intake_source
from .company_context import LEGACY_COMPANY_CONTRACT, validate_company_contract, require_company_source


class MessageRejectedConflict(Conflict):
    pass


class MessageRejectedInvalid(ValueError):
    pass


class MessageRejectedNotFound(NotFound):
    pass


class ConversationService:
    def __init__(self, store: ConversationStore, tasks: TaskStore, calls: CallJournal, clock: Callable[[], float],
                 config: ModelConfig | None, preflight: Callable[[dict], None], guidance: Callable[[], dict] | None = None, assets: Callable[[str, dict], dict] | None = None,
                 admissions=None):
        self.store, self.tasks, self.calls, self.clock, self.config, self.preflight = store, tasks, calls, clock, config, preflight
        self.guidance, self.assets = guidance, assets
        self.admissions=admissions

    def _knowledge(self, organization, conversation_id, request_id):
        snapshot = self.store.snapshot(organization, conversation_id)
        admissions = snapshot["admissions"]
        old = next((item for item in admissions if item["request_id"] == request_id), None)
        if old:
            return old["knowledge"]
        selected = snapshot.get('intake_source')
        require_company_source(snapshot.get('product_contract', LEGACY_COMPANY_CONTRACT), selected)
        knowledge = (INTAKE_KNOWLEDGE | {'playbooks': {'version': 'intake-interpretation/v1', 'guidance': INTAKE_KNOWLEDGE['procedures']}}
                     if selected else KNOWLEDGE | ({"playbooks": self.guidance()} if self.guidance else {}))
        return knowledge | {"agent_assets": self.assets(organization, knowledge)} if self.assets else knowledge

    def create(self, organization: str, request_id: str, title: str = "New campaign conversation", *,
               product_contract=LEGACY_COMPANY_CONTRACT) -> dict:
        validate_company_contract(product_contract)
        conversation = self.store.create(organization, request_id, title, self.clock(), product_contract=product_contract)
        return self.view(organization, conversation)

    def message(self, organization: str, conversation_id: str, request_id: str, expected_revision: int, content: str) -> dict:
        try:
            receipt = self.store.append(organization, conversation_id, request_id, expected_revision, content, self.clock())
        except (Conflict, NotFound, ValueError) as error:
            kind = MessageRejectedConflict if isinstance(error, Conflict) else MessageRejectedNotFound if isinstance(error, NotFound) else MessageRejectedInvalid
            raise kind(str(error)) from error
        return self.view(organization, conversation_id) | {"message_receipt": receipt}

    def reply_budget(self, organization, conversation_id, request_id, expected_revision, plan_id, content):
        try:
            receipt = self.store.reply_budget(organization, conversation_id, request_id, expected_revision, plan_id, content, self.clock())
        except (Conflict, NotFound, ValueError) as error:
            kind = MessageRejectedConflict if isinstance(error, Conflict) else MessageRejectedNotFound if isinstance(error, NotFound) else MessageRejectedInvalid
            raise kind(str(error)) from error
        return self.view(organization, conversation_id) | {'message_receipt': receipt}

    def planning_context(self, organization, conversation_id, request_id, expected_revision, fixture):
        """Freeze bounded planning inputs without admitting a task or inference."""
        source = self.view(organization, conversation_id)
        require_company_source(source.get('product_contract', LEGACY_COMPANY_CONTRACT), source.get('intake_source'))
        if source.get('intake_source'):
            raise Conflict('Use the saved brief planning action; intake cannot authorize campaign preparation')
        if source["revision"] != expected_revision or expected_revision < 1:
            raise Conflict("Conversation changed before preparation admission")
        existing = next((p for p in source["plans"] if p["revision"] == expected_revision), None)
        if existing and existing["request_id"] != request_id:
            raise Conflict("This revision already has a planning request; inspect its original progress")
        if len(source["plans"]) >= 6 and existing is None:
            raise ValueError("Conversation planning budget exhausted")
        knowledge = self._knowledge(organization, conversation_id, request_id)
        context = {"knowledge": knowledge, "knowledge_id": "knowledge_" + digest(knowledge),
                   "messages": source["messages"], "previous_results": [] if fixture else [p["result"] for p in source["plans"] if p["result"]],
                   "model_config": None if fixture else self.config.payload() if self.config else None}
        context['budget_policy'] = BUDGET_POLICY
        context['requested_scope'] = requested_scope(organization, conversation_id, expected_revision, source['messages'])
        if fixture:
            context["fixture"] = "offline-example/v1"
            self._fixture_preflight(context)
        else:
            if self.config is None:
                raise ValueError("Configure the planner before admitting preparation")
            if source.get('confirmed_action_exchanges'):
                context['confirmed_action_exchanges']=source['confirmed_action_exchanges']
            self.preflight(context)
        return context

    def intake_context(self, source, messages=None):
        organization, conversation_id, request_id = source['organization'], source['conversation_id'], source['request_id']
        if messages is None:
            snapshot = self.store.snapshot(organization, conversation_id)
            messages = [m for m in snapshot['messages'] if m['revision'] <= source['revision']]
            knowledge = self._knowledge(organization, conversation_id, request_id)
        else:
            knowledge = INTAKE_KNOWLEDGE | {'playbooks': {'version': 'intake-interpretation/v1', 'guidance': INTAKE_KNOWLEDGE['procedures']}}
            if self.assets:
                knowledge = knowledge | {'agent_assets': self.assets(organization, knowledge)}
        context = {'knowledge': knowledge, 'knowledge_id': 'knowledge_' + digest(knowledge),
                   'model_config': self.config.payload() if self.config else None,
                   'intake_source': source, 'previous_results': [], 'messages': messages,
                   'budget_policy': BUDGET_POLICY}
        bind_intake_source(context, organization)
        self.preflight(context)
        return context

    def plan_intake(self, source):
        actual = self.store.intake_source(source['organization'], source['conversation_id'], source['revision'])
        if actual != source:
            raise Conflict('Intake interpretation differs from its original source selection')
        return self.plan(source['organization'], source['conversation_id'], source['request_id'], source['revision'], _intake=True)

    def plan(self, organization: str, conversation_id: str, request_id: str, expected_revision: int, *, frozen_context=None, _intake=False) -> str:
        if self.config is None:
            raise ValueError("Configure the planner model before explicitly requesting generation")
        selected = self.store.intake_source(organization, conversation_id, expected_revision)
        if bool(selected) != _intake:
            raise Conflict('Use the explicit saved intake planning action for this source')
        if self.admissions and self.admissions.required():
            return self.admissions.planning(organization,conversation_id,request_id,expected_revision,
                fixture=False,config=self.config,frozen_context=frozen_context,
                context_factory=lambda:self.intake_context(selected) if selected else self.planning_context(organization,conversation_id,request_id,expected_revision,False))
        if selected and frozen_context is None:
            frozen_context = self.intake_context(selected)
        if frozen_context is None:
            source=self.view(organization, conversation_id)
            previous = [p["result"] for p in source["plans"] if p["result"]]
            knowledge = self._knowledge(organization, conversation_id, request_id)
            context = {"knowledge": knowledge, "knowledge_id": "knowledge_" + digest(knowledge), "model_config": self.config.payload(),
                       "previous_results": previous}
            if source.get('confirmed_action_exchanges'):
                context['confirmed_action_exchanges']=source['confirmed_action_exchanges']
        else:
            context = frozen_context
            if context["model_config"] != self.config.payload():
                raise ValueError("Restore the original planner settings before admission")
        frozen = self.store.admit(organization, conversation_id, request_id, expected_revision, context, self.clock(), self.preflight)
        if frozen.get("fixture"):
            raise Conflict("Planning request already binds another mode")
        return self.tasks.create(organization, frozen["run_request_id"], [TaskSpec(CAPABILITY, frozen)], self.clock())

    @staticmethod
    def _fixture_preflight(frozen):
        if len(frozen["messages"]) != 1 or frozen["messages"][0]["content"] != FIXTURE_MESSAGE:
            raise ValueError("The offline example requires its exact synthetic example message")

    def plan_fixture(self, organization: str, conversation_id: str, request_id: str, expected_revision: int, *, frozen_context=None) -> str:
        if self.store.intake_source(organization, conversation_id, expected_revision):
            raise Conflict('Intake interpretation cannot use the fixed offline example')
        if self.admissions and self.admissions.required():
            return self.admissions.planning(organization,conversation_id,request_id,expected_revision,
                fixture=True,config=None,frozen_context=frozen_context,
                context_factory=lambda:self.planning_context(organization,conversation_id,request_id,expected_revision,True))
        if frozen_context is None:
            knowledge = self._knowledge(organization, conversation_id, request_id)
            context = {"knowledge": knowledge, "knowledge_id": "knowledge_" + digest(knowledge),
                       "model_config": None, "previous_results": [], "fixture": "offline-example/v1"}
        else:
            context = frozen_context
        frozen = self.store.admit(organization, conversation_id, request_id, expected_revision, context, self.clock(), self._fixture_preflight)
        if frozen.get("fixture") != "offline-example/v1":
            raise Conflict("Planning request already binds another mode")
        return self.tasks.create(organization, frozen["run_request_id"], [TaskSpec(FIXTURE_CAPABILITY, frozen)], self.clock())

    def view(self, organization: str, conversation_id: str) -> dict:
        snapshot = self.store.snapshot(organization, conversation_id)
        plans = []
        for admission in snapshot.pop("admissions"):
            if admission.get("knowledge_id") != "knowledge_" + digest(admission["knowledge"]):
                raise Conflict("Frozen planning guidance failed integrity checks")
            run = self.tasks.find_run(organization, admission["run_request_id"])
            state = self.tasks.inspect(organization, run) if run else None
            task = state["tasks"][0] if state else None
            error = task["output"] if task and task["status"] == "failed" else None
            if error and error.get("error_code") == "ModelError":
                receipts = self.calls.inspect(organization, run)
                code = next((r["error"] for r in reversed(receipts) if r["error"]), None)
                if code and (re.fullmatch(r"provider_http_[1-5][0-9]{2}", code) or code in {"provider_request_failed", "provider_outcome_unknown"}):
                    error = error | {"provider_error": code}
            plans.append({"request_id": admission["request_id"], "revision": admission["revision"], "run_id": run,
                          "guidance": {"id": admission["knowledge_id"], "content": admission["knowledge"]},
                          "mode": "fixture" if admission.get("fixture") else "model",
                          "status": state["run"]["status"] if state else "admitted",
                          "current": admission["revision"] == snapshot["revision"],
                          "result": task["output"] if task and task["status"] == "succeeded" else None,
                          "error": error})
        current = next((p for p in reversed(plans) if p["current"]), None)
        return snapshot | {"plans": plans, "current_plan": current, "mode": "SYNTHETIC_PLANNING_ONLY"}
