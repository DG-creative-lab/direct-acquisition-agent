from dataclasses import asdict
from datetime import datetime, timezone

from acquisition.campaigns import brief_from, validate_copy_revision
from acquisition.creative import GroundedCopyAgent
from acquisition.reasoning import CallScope, ModelError
from acquisition.reviews import creatives_from
from acquisition.runtime import Outcome


class CopyRevisionWorkflow:
    def __init__(self, campaigns, drafts, memory, inference, reviews):
        self.campaigns, self.drafts, self.memory, self.inference, self.reviews = campaigns, drafts, memory, inference, reviews

    def eligible(self, capability, inputs):
        return capability not in self.capabilities() or inputs.get("workflow_version") != "copy-revision/v3" or (self.inference is not None and inputs.get("model_config") == asdict(self.inference.config))

    def _check(self, claim):
        if claim.inputs.get("workflow_version") != "copy-revision/v3" or not self.eligible(claim.capability, claim.inputs):
            raise ModelError("Restore the original copy revision configuration")

    def capabilities(self):
        return {"creative.revise_copy.v3": self.generate, "reviews.publish_copy_revision.v3": self.publish}

    def generate(self, claim):
        self._check(claim)
        variants = GroundedCopyAgent(self.inference, self.memory).generate(
            CallScope(claim.organization, claim.run_id, claim.task_id, claim.token), claim.inputs["context_id"],
            datetime.fromtimestamp(self.inference.clock(), timezone.utc).date())
        draft_id = self._draft(claim, variants)
        return Outcome("succeeded", {"draft_id": draft_id})

    def _draft(self, claim, variants):
        base = self.drafts.get(claim.organization, claim.inputs["base_draft_id"])
        catalogue = tuple(c for c in creatives_from(base) if c.segment != claim.inputs["segment"]) + tuple(variants)
        result = self.campaigns.prepare_with_catalogue(claim.organization, base.manifest["snapshot_id"],
            brief_from(base.manifest["brief"]), claim.inputs["revision_id"] + ":draft", catalogue)
        candidate = self.drafts.get(claim.organization, result["draft_id"])
        validate_copy_revision(base, candidate, claim.inputs["target_id"])
        return candidate.id

    def publish(self, claim):
        self._check(claim)
        variants = self.memory.get_catalogue(claim.organization, claim.run_id + ":copy:" + claim.inputs["context_id"])
        if variants is None:
            raise ValueError("The validated copy result is unavailable")
        prior = self.reviews.revision_publication(claim.organization, claim.inputs["revision_id"])
        draft_id = prior["draft_id"] if prior else self._draft(claim, variants)
        receipt = self.reviews.propose(claim.organization, claim.inputs["case_id"], claim.inputs["expected_subject"],
            draft_id, claim.inputs["actor"], claim.inputs["revision_id"] + ":publish",
            claim.inputs["audience_epoch"], claim.inputs["evidence_epoch"], claim=claim)
        return Outcome("succeeded", receipt)
