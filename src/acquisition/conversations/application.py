from collections.abc import Callable
from dataclasses import asdict
import re

from acquisition.contracts import digest
from acquisition.reasoning import CallJournal, ModelConfig
from acquisition.runtime import TaskSpec, TaskStore

from .domain import CAPABILITY, KNOWLEDGE
from .ports import ConversationStore


class ConversationService:
    def __init__(self, store: ConversationStore, tasks: TaskStore, calls: CallJournal, clock: Callable[[], float],
                 config: ModelConfig | None, preflight: Callable[[dict], None]):
        self.store, self.tasks, self.calls, self.clock, self.config, self.preflight = store, tasks, calls, clock, config, preflight

    def create(self, organization: str, request_id: str, title: str = "New campaign conversation") -> dict:
        conversation = self.store.create(organization, request_id, title, self.clock())
        return self.view(organization, conversation)

    def message(self, organization: str, conversation_id: str, request_id: str, expected_revision: int, content: str) -> dict:
        receipt = self.store.append(organization, conversation_id, request_id, expected_revision, content, self.clock())
        return self.view(organization, conversation_id) | {"message_receipt": receipt}

    def plan(self, organization: str, conversation_id: str, request_id: str, expected_revision: int) -> str:
        if self.config is None:
            raise ValueError("Configure the planner model before explicitly requesting generation")
        previous = [p["result"] for p in self.view(organization, conversation_id)["plans"] if p["result"]]
        context = {"knowledge": KNOWLEDGE, "knowledge_id": "knowledge_" + digest(KNOWLEDGE), "model_config": asdict(self.config),
                   "previous_results": previous}
        frozen = self.store.admit(organization, conversation_id, request_id, expected_revision, context, self.clock(), self.preflight)
        return self.tasks.create(organization, frozen["run_request_id"], [TaskSpec(CAPABILITY, frozen)], self.clock())

    def view(self, organization: str, conversation_id: str) -> dict:
        snapshot = self.store.snapshot(organization, conversation_id)
        plans = []
        for admission in snapshot.pop("admissions"):
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
                          "status": state["run"]["status"] if state else "admitted",
                          "current": admission["revision"] == snapshot["revision"],
                          "result": task["output"] if task and task["status"] == "succeeded" else None,
                          "error": error})
        current = next((p for p in reversed(plans) if p["current"]), None)
        return snapshot | {"plans": plans, "current_plan": current, "mode": "SYNTHETIC_PLANNING_ONLY"}
