from dataclasses import asdict

from acquisition.audiences import AudienceStore
from acquisition.campaigns import Brief, CampaignService, brief_from
from acquisition.creative import fixture_catalog
from acquisition.runtime import Claim, Outcome, TaskSpec


def task_plan(snapshot_id: str, brief: Brief, catalogue_hash: str) -> list[TaskSpec]:
    inputs = {"snapshot_id": snapshot_id, "brief": asdict(brief), "workflow_version": "monthly-mail/v1",
              "creative_catalogue_hash": catalogue_hash}
    return [TaskSpec("audiences.inspect.v1", inputs), TaskSpec("campaigns.build_draft.v1", inputs),
            TaskSpec("campaigns.review_checkpoint.v1", inputs, max_attempts=5)]


class MonthlyMail:
    def __init__(self, audiences: AudienceStore, campaigns: CampaignService):
        self.audiences, self.campaigns = audiences, campaigns

    def _check_version(self, claim: Claim) -> None:
        if (claim.inputs.get("workflow_version") != "monthly-mail/v1"
                or claim.inputs.get("creative_catalogue_hash") != self.campaigns.catalogue_hash):
            raise ValueError("Workflow or creative catalogue changed; create a new run")

    def inspect(self, claim: Claim) -> Outcome:
        self._check_version(claim)
        snapshot = self.audiences.get(claim.organization, claim.inputs["snapshot_id"])
        if not snapshot.complete:
            raise ValueError("Audience batch is incomplete")
        return Outcome("succeeded", {"snapshot_id": snapshot.id, "rows": len(snapshot.records),
                                     "mode": "synthetic", "complete": snapshot.complete})

    def prepare(self, claim: Claim) -> Outcome:
        self._check_version(claim)
        return Outcome("succeeded", self._draft(claim))

    def _draft(self, claim: Claim) -> dict:
        return self.campaigns.prepare(claim.organization, claim.inputs["snapshot_id"],
                                      Brief(**claim.inputs["brief"]), claim.run_id + ":draft")

    def review(self, claim: Claim) -> Outcome:
        self._check_version(claim)
        # Recompute through idempotent preparation: safe even if a previous process
        # died after committing draft bytes and before committing a task receipt.
        result = self._draft(claim)
        if claim.resume:
            if claim.resume != {"reference": result["draft_id"], "decision": "acknowledge_dry_run_only"}:
                raise ValueError("Checkpoint acknowledgement differs from exact artifact")
            return Outcome("succeeded", result | {"release_authority": False, "mode": "dry_run_complete"})
        return Outcome("waiting", result | {"reference": result["draft_id"], "release_authority": False,
                                            "message": "Review the synthetic draft; acknowledgement permits no send or print."})

    def capabilities(self):
        return {"audiences.inspect.v1": self.inspect, "campaigns.build_draft.v1": self.prepare,
                "campaigns.review_checkpoint.v1": self.review}


def conversation_task_plan(snapshot_id, brief, catalogue_hash):
    inputs = {"snapshot_id": snapshot_id, "brief": asdict(brief), "workflow_version": "conversation-mail/v1",
              "creative_catalogue_hash": catalogue_hash}
    return [TaskSpec("audiences.inspect_conversation.v1", inputs),
            TaskSpec("campaigns.build_conversation.v1", inputs),
            TaskSpec("campaigns.review_conversation.v1", inputs, max_attempts=5)]


class ConversationMail(MonthlyMail):
    def _check_version(self, claim):
        if (claim.inputs.get("workflow_version") != "conversation-mail/v1"
                or claim.inputs.get("creative_catalogue_hash") != self.campaigns.catalogue_hash):
            raise ValueError("Conversation workflow or fixture catalogue changed")

    def _draft(self, claim):
        brief = brief_from(claim.inputs["brief"])
        creatives = tuple(c for c in fixture_catalog() if c.segment in brief.segments)
        return self.campaigns.prepare_with_catalogue(claim.organization, claim.inputs["snapshot_id"],
                                                      brief, claim.run_id + ":draft", creatives)

    def capabilities(self):
        return {"audiences.inspect_conversation.v1": self.inspect,
                "campaigns.build_conversation.v1": self.prepare,
                "campaigns.review_conversation.v1": self.review}
