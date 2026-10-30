"""Bounded copy feedback. Immutable admissions precede task/model effects."""

from dataclasses import asdict
from acquisition.contracts import Conflict
from acquisition.runtime import TaskSpec, TaskStore
from acquisition.campaigns import DraftStore
from acquisition.creative import CreativeMemory
from .ports import ReviewStore
from .domain import text


class CopyRevisionService:
    def __init__(self, store: ReviewStore, drafts: DraftStore, memory: CreativeMemory, tasks: TaskStore, clock, config):
        self.store, self.drafts, self.memory, self.tasks = store, drafts, memory, tasks
        self.clock, self.config = clock, config

    def admit(self, organization, case_id, request_id, expected_subject, target_id, feedback, allow_model_copy,
              actor="local-operator", reviewer="local-reviewer"):
        if allow_model_copy is not True:
            raise ValueError("Explicit model-copy permission is required")
        for value in (organization, case_id, request_id, expected_subject, target_id):
            text(value, 300)
        text(feedback)
        inputs = {"case_id": case_id, "expected_subject": expected_subject, "target_id": target_id,
                  "feedback": feedback, "allow_model_copy": True, "actor": actor, "reviewer": reviewer}
        old = self.store.revision_request(organization, request_id)
        if old:
            if old["inputs"] != inputs:
                raise Conflict("Copy request already binds different feedback or subject")
            return old
        if self.config is None:
            raise ValueError("Configure the copy model before requesting a revision")
        view = self.store.view(organization, case_id)
        if view["subject"]["id"] != expected_subject or not view["candidate_valid"] or view["handoff"]:
            raise Conflict("Select a current valid, unaccepted campaign for revision")
        base = self.drafts.get(organization, view["subject"]["draft_id"])
        target = next((c for c in base.manifest["creatives"] if c["id"] == target_id), None)
        if target is None or not target.get("fact_pack_id"):
            raise Conflict("Copy revision requires grounded model copy")
        original_context = self.memory.get_context(organization, target["context_id"])
        context = original_context | {"copy_revision": {"base_draft_id": base.id, "base_subject_id": expected_subject,
            "arm": target["arm"], "feedback": feedback,
            "base_variants": sorted([c for c in base.manifest["creatives"] if c["segment"] == target["segment"]], key=lambda c: c["arm"])}}
        return self.store.admit_revision(organization, request_id, inputs, context, asdict(self.config))

    def reconcile(self, organization, receipt):
        if self.config is None or asdict(self.config) != receipt["task_inputs"]["model_config"]:
            raise ValueError("Restore the original copy revision configuration")
        context_id = self.memory.put_context(organization, receipt["context"])
        inputs = receipt["task_inputs"] | {"context_id": context_id}
        return self.tasks.create(organization, receipt["id"], [TaskSpec("creative.revise_copy.v3", inputs),
            TaskSpec("reviews.publish_copy_revision.v3", inputs)], self.clock())

    def view(self, organization, case_id):
        values = []
        for receipt in self.store.revision_requests(organization, case_id):
            run = self.tasks.find_run(organization, receipt["id"])
            state = self.tasks.inspect(organization, run) if run else None
            publication = self.store.revision_publication(organization, receipt["id"])
            if publication and publication["case_id"] != case_id:
                raise Conflict("Revision publication belongs to another case")
            current = self.store.revision_current(organization, receipt)
            status = "complete" if publication else state["run"]["status"] if state else "admitted"
            if not current and not publication and status not in {"failed", "cancelled"}:
                status = "stale"
            values.append({"id": receipt["id"], "request_id": receipt["request_id"], "run_id": run,
                "status": status, "current": current, "base_subject_id": receipt["inputs"]["expected_subject"],
                "target_id": receipt["inputs"]["target_id"], "feedback": receipt["inputs"]["feedback"],
                "published_subject_id": publication["subject_id"] if publication else None})
        return values
