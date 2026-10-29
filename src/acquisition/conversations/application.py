from collections.abc import Callable
from dataclasses import asdict
import re

from acquisition.contracts import Conflict, NotFound, digest
from acquisition.reasoning import CallJournal, ModelConfig
from acquisition.runtime import TaskSpec, TaskStore

from .domain import CAPABILITY, FIXTURE_CAPABILITY, FIXTURE_MESSAGE, KNOWLEDGE
from .ports import ConversationStore


class MessageRejectedConflict(Conflict):
    pass


class MessageRejectedInvalid(ValueError):
    pass


class MessageRejectedNotFound(NotFound):
    pass


class ConversationService:
    def __init__(self, store: ConversationStore, tasks: TaskStore, calls: CallJournal, clock: Callable[[], float],
                 config: ModelConfig | None, preflight: Callable[[dict], None], guidance: Callable[[], dict] | None = None):
        self.store, self.tasks, self.calls, self.clock, self.config, self.preflight = store, tasks, calls, clock, config, preflight
        self.guidance = guidance

    def _knowledge(self, organization, conversation_id, request_id):
        admissions = self.store.snapshot(organization, conversation_id)["admissions"]
        old = next((item for item in admissions if item["request_id"] == request_id), None)
        if old:
            return old["knowledge"]
        return KNOWLEDGE | ({"playbooks": self.guidance()} if self.guidance else {})

    def create(self, organization: str, request_id: str, title: str = "New campaign conversation") -> dict:
        conversation = self.store.create(organization, request_id, title, self.clock())
        return self.view(organization, conversation)

    def message(self, organization: str, conversation_id: str, request_id: str, expected_revision: int, content: str) -> dict:
        try:
            receipt = self.store.append(organization, conversation_id, request_id, expected_revision, content, self.clock())
        except (Conflict, NotFound, ValueError) as error:
            kind = MessageRejectedConflict if isinstance(error, Conflict) else MessageRejectedNotFound if isinstance(error, NotFound) else MessageRejectedInvalid
            raise kind(str(error)) from error
        return self.view(organization, conversation_id) | {"message_receipt": receipt}

    def plan(self, organization: str, conversation_id: str, request_id: str, expected_revision: int) -> str:
        if self.config is None:
            raise ValueError("Configure the planner model before explicitly requesting generation")
        previous = [p["result"] for p in self.view(organization, conversation_id)["plans"] if p["result"]]
        knowledge = self._knowledge(organization, conversation_id, request_id)
        context = {"knowledge": knowledge, "knowledge_id": "knowledge_" + digest(knowledge), "model_config": asdict(self.config),
                   "previous_results": previous}
        frozen = self.store.admit(organization, conversation_id, request_id, expected_revision, context, self.clock(), self.preflight)
        if frozen.get("fixture"):
            raise Conflict("Planning request already binds another mode")
        return self.tasks.create(organization, frozen["run_request_id"], [TaskSpec(CAPABILITY, frozen)], self.clock())

    def plan_fixture(self, organization: str, conversation_id: str, request_id: str, expected_revision: int) -> str:
        knowledge = self._knowledge(organization, conversation_id, request_id)
        context = {"knowledge": knowledge, "knowledge_id": "knowledge_" + digest(knowledge),
                   "model_config": None, "previous_results": [], "fixture": "offline-example/v1"}
        def preflight(frozen):
            if len(frozen["messages"]) != 1 or frozen["messages"][0]["content"] != FIXTURE_MESSAGE:
                raise ValueError("The offline example requires its exact synthetic example message")
        frozen = self.store.admit(organization, conversation_id, request_id, expected_revision, context, self.clock(), preflight)
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
