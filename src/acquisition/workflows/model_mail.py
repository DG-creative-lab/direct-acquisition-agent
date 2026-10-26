from dataclasses import asdict
from datetime import datetime, timezone

from acquisition.campaigns import Brief
from acquisition.creative import CopyAgent, CreativeMemory, GroundedCopyAgent, validate_grounded_catalogue
from acquisition.reasoning import CallScope, Inference, ModelError
from acquisition.runtime import Claim, Outcome, TaskSpec

from .monthly_mail import MonthlyMail


def model_task_plan(snapshot_id: str, brief: Brief, contexts: dict[str, str], inference: Inference) -> list[TaskSpec]:
    shared = {"snapshot_id": snapshot_id, "brief": asdict(brief), "workflow_version": "monthly-mail/v3",
              "context_ids": contexts, "model_config": asdict(inference.config)}
    return [TaskSpec("audiences.inspect_model.v3", shared)] + [
        TaskSpec("creative.generate.v3", shared | {"segment": segment}) for segment in sorted(contexts)
    ] + [TaskSpec("campaigns.build_model_draft.v3", shared),
         TaskSpec("campaigns.model_review_checkpoint.v3", shared, max_attempts=5)]


class ModelMonthlyMail(MonthlyMail):
    def __init__(self, audiences, campaigns, memory: CreativeMemory, inference: Inference | None):
        super().__init__(audiences, campaigns)
        self.memory, self.inference = memory, inference

    @staticmethod
    def legacy_capabilities() -> frozenset[str]:
        return frozenset(("audiences.inspect_model.v2", "creative.generate.v2",
                          "campaigns.build_model_draft.v2", "campaigns.model_review_checkpoint.v2"))

    def eligible(self, capability: str, inputs: dict) -> bool:
        if capability not in self.capabilities():
            return True
        version = inputs.get("workflow_version")
        if version not in {"monthly-mail/v2", "monthly-mail/v3"} or not capability.endswith("." + version.rsplit("/", 1)[-1]):
            return True  # Invalid protocol is a task error, not a worker configuration mismatch.
        return self.inference is not None and inputs.get("model_config") == asdict(self.inference.config)

    def _check_version(self, claim: Claim) -> None:
        if (self.inference is None or claim.inputs.get("workflow_version") not in {"monthly-mail/v2", "monthly-mail/v3"}
                or not claim.capability.endswith("." + claim.inputs["workflow_version"].rsplit("/", 1)[-1])
                or claim.inputs.get("model_config") != asdict(self.inference.config)):
            raise ModelError("configure_the_original_model_and_limits_before_resuming")

    def generate(self, claim: Claim) -> Outcome:
        self._check_version(claim)
        scope = CallScope(claim.organization, claim.run_id, claim.task_id, claim.token)
        context_id = claim.inputs["context_ids"][claim.inputs["segment"]]
        if claim.inputs["workflow_version"] == "monthly-mail/v3":
            variants = GroundedCopyAgent(self.inference, self.memory).generate(scope, context_id, self._today())
        else:
            variants = CopyAgent(self.inference, self.memory).generate(scope, context_id)
        return Outcome("succeeded", {"segment": claim.inputs["segment"], "context_id": context_id,
                                     "creative_ids": [item.id for item in variants], "status": "generated_unreviewed"})

    def _draft(self, claim: Claim) -> dict:
        self._check_version(claim)
        variants = []
        for context_id in claim.inputs["context_ids"].values():
            catalogue = self.memory.get_catalogue(claim.organization, claim.run_id + ":copy:" + context_id)
            if catalogue is None:
                raise ModelError("required_creative_result_missing")
            if claim.inputs["workflow_version"] == "monthly-mail/v3":
                context = self.memory.get_context(claim.organization, context_id)
                if any(item.context_id != context_id for item in catalogue):
                    raise ModelError("creative_context_mismatch")
                validate_grounded_catalogue(catalogue, context, self._today())
            variants.extend(catalogue)
        return self.campaigns.prepare_with_catalogue(claim.organization, claim.inputs["snapshot_id"],
            Brief(**claim.inputs["brief"]), claim.run_id + ":draft", tuple(variants))

    def capabilities(self):
        return {**{f"audiences.inspect_model.{version}": self.inspect for version in ("v2", "v3")},
                **{f"creative.generate.{version}": self.generate for version in ("v2", "v3")},
                **{f"campaigns.build_model_draft.{version}": self.prepare for version in ("v2", "v3")},
                **{f"campaigns.model_review_checkpoint.{version}": self.review for version in ("v2", "v3")}}

    def _today(self):
        return datetime.fromtimestamp(self.inference.clock(), timezone.utc).date()
