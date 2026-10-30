"""Composition root: the only place that selects and wires concrete adapters."""

import time
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from datetime import datetime, timezone

from acquisition.adapters.files import export_draft
from acquisition.adapters.sqlite.audiences import SqliteAudiences
from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.drafts import SqliteDrafts
from acquisition.adapters.sqlite.tasks import SqliteTasks
from acquisition.adapters.synthetic import generate
from acquisition.adapters.sqlite.creative import SqliteCreative
from acquisition.adapters.sqlite.inference import SqliteCalls
from acquisition.campaigns import Brief, ConversationBrief, CampaignService
from acquisition.creative import fixture_catalog, validate_fact_pack
from acquisition.runtime import TaskStore, Worker
from acquisition.reasoning import Inference, ModelConfig, ModelGateway
from acquisition.workflows.monthly_mail import MonthlyMail, ConversationMail, conversation_task_plan, task_plan
from acquisition.workflows.model_mail import ModelMonthlyMail, ConversationModelMail, model_task_plan, conversation_model_task_plan
from acquisition.adapters.sqlite.reviews import SqliteReviews
from acquisition.reviews import ReviewService, CopyRevisionService
from acquisition.workflows.copy_revision import CopyRevisionWorkflow
from acquisition.workflows.review import ReviewProposalBuilder
from acquisition.learning import LearningService
from acquisition.adapters.sqlite.learning import SqliteLearning
from acquisition.workflows.learning import AcceptedCohortSource
from acquisition.adapters.sqlite.conversations import SqliteConversations
from acquisition.conversations import ConversationService, CAPABILITY as PLANNER_CAPABILITY, FIXTURE_CAPABILITY
from acquisition.workflows.conversation import ConversationPlanner
from acquisition.adapters.sqlite.preparations import SqlitePreparations
from acquisition.conversations import PreparationCoordinator


def build_preparations(path, host):
    return PreparationCoordinator(SqlitePreparations(path), host)


@dataclass
class Application:
    tasks: TaskStore
    audiences: SqliteAudiences
    drafts: SqliteDrafts
    worker: Worker
    clock: Callable[[], float]
    catalogue_hash: str
    memory: SqliteCreative
    calls: SqliteCalls
    inference: Inference | None
    reviews: ReviewService
    learning: LearningService
    conversations: ConversationService
    revisions: CopyRevisionService

    def start(self, organization: str, request_id: str, size: int = 1000, seed: int = 42,
              budget_pence: int = 85000, as_of: str = "2026-10-25", campaign_id: str | None = None) -> str:
        snapshot_id = self.audiences.put(generate(organization, size, seed, as_of))
        brief = Brief(campaign_id=campaign_id or request_id, budget_pence=budget_pence)
        return self.tasks.create(organization, request_id, task_plan(snapshot_id, brief, self.catalogue_hash), self.clock())

    def start_model(self, organization: str, request_id: str, size: int = 1000, seed: int = 42,
                    budget_pence: int = 85000, as_of: str = "2026-10-25", campaign_id: str | None = None,
                    conversation_brief: ConversationBrief | None = None, objective: str | None = None) -> str:
        if self.inference is None:
            raise ValueError("Configure a model adapter before starting a model run")
        snapshot = generate(organization, size, seed, as_of)
        snapshot_id = self.audiences.put(snapshot)
        config_root = Path(__file__).resolve().parents[2] / "config"
        guidance = json.loads((config_root / "editorial-v3.json").read_text())
        product_facts = json.loads((config_root / "iwoca-product-facts-v1.json").read_text())
        current = self.reviews.store.evidence(organization)
        if current is not None:
            product_facts = current["pack"]
        validate_fact_pack(product_facts, datetime.fromtimestamp(self.clock(), timezone.utc).date())
        contexts = {}
        segments = conversation_brief.segments if conversation_brief else ("inventory", "contractors")
        learning_memory = self.learning.store.memory_snapshot(organization, segments)
        for segment in segments:
            example = guidance["reviewer_examples"][segment]
            # Seed examples are explicitly reviewer preferences, never outcome evidence.
            if not self.memory.examples(organization, segment):
                self.memory.remember(organization, segment, **example)
            context = {"segment": segment, "guidance": guidance, "product_facts": product_facts,
                       "memory": self.memory.examples(organization, segment),
                       "audience_summary": {"input_records": sum(row.segment == segment for row in snapshot.records),
                           "model_version": snapshot.model_version, "snapshot_id": snapshot.id,
                           "situation_hypothesis": guidance["situations"][segment],
                           "outcome_evidence": learning_memory[segment]}}
            if conversation_brief:
                context["campaign_brief"] = {"objective": objective, "budget_pence": conversation_brief.budget_pence,
                                             "segments": list(segments), "plan_id": conversation_brief.plan_id}
            contexts[segment] = self.memory.put_context(organization, context)
        specs = (conversation_model_task_plan(snapshot_id, conversation_brief, contexts, self.inference) if conversation_brief
                 else model_task_plan(snapshot_id, Brief(campaign_id or request_id, budget_pence), contexts, self.inference))
        return self.tasks.create(organization, request_id, specs, self.clock())

    def start_conversation(self, organization, request_id, plan, as_of):
        brief = ConversationBrief(campaign_id=request_id, budget_pence=plan["budget_pence"],
                                  segments=tuple(plan["segments"]), conversation_id=plan["conversation_id"],
                                  conversation_revision=plan["revision"], plan_id=plan["id"])
        if plan["copy_mode"] == "model":
            return self.start_model(organization, request_id, as_of=as_of, conversation_brief=brief, objective=plan["objective"])
        snapshot_id = self.audiences.put(generate(organization, 1000, 42, as_of))
        return self.tasks.create(organization, request_id, conversation_task_plan(snapshot_id, brief, self.catalogue_hash), self.clock())

    def export(self, organization: str, run_id: str, directory: Path) -> Path:
        state = self.tasks.inspect(organization, run_id)
        outputs = [task["output"] for task in state["tasks"] if task["output"] and task["output"].get("draft_id")]
        if not outputs:
            raise ValueError("No committed draft receipt exists yet")
        draft = self.drafts.get(organization, outputs[-1]["draft_id"])
        return self._export_draft(organization, draft, directory)

    def export_review(self, organization: str, case_id: str, directory: Path, expected_subject: str | None = None) -> Path:
        view = self.reviews.store.view(organization, case_id)
        if expected_subject is not None and view["subject"]["id"] != expected_subject:
            from acquisition.contracts import Conflict
            raise Conflict("Review changed before export; request a fresh report")
        draft = self.drafts.get(organization, view["subject"]["draft_id"])
        return self._export_draft(organization, draft, directory)

    def _export_draft(self, organization, draft, directory):
        context_ids = {item["context_id"] for item in draft.manifest["creatives"] if item.get("fact_pack_id")}
        contexts = tuple(self.memory.get_context(organization, identity) for identity in sorted(context_ids))
        return export_draft(draft, directory, contexts)


def build(path: str | Path, clock: Callable[[], float] = time.time,
          gateway: ModelGateway | None = None, model_config: ModelConfig | None = None) -> Application:
    database = Database(path)
    audiences, drafts = SqliteAudiences(database), SqliteDrafts(database)
    tasks = SqliteTasks(database, retired_capabilities=ModelMonthlyMail.legacy_capabilities())
    campaigns = CampaignService(audiences, drafts, fixture_catalog())
    workflow = MonthlyMail(audiences, campaigns)
    memory, calls = SqliteCreative(database), SqliteCalls(database)
    inference = Inference(gateway, calls, model_config, clock) if gateway is not None and model_config is not None else None
    model_workflow = ModelMonthlyMail(audiences, campaigns, memory, inference)
    conversation_model = ConversationModelMail(audiences, campaigns, memory, inference)
    planner_config = replace(model_config, max_calls=2, force_tool_choice=True) if model_config else None
    planner_inference = Inference(gateway, calls, planner_config, clock) if gateway is not None and planner_config else None
    planner = ConversationPlanner(planner_inference)
    def planning_guidance():
        return json.loads((Path(__file__).resolve().parents[2] / "config/campaign-playbooks-v1.json").read_text())
    conversations = ConversationService(SqliteConversations(database), tasks, calls, clock,
                                        planner_config if planner_inference else None, planner.preflight, planning_guidance)
    reviews = SqliteReviews(database, clock)
    revision_config = replace(model_config, max_calls=5, force_tool_choice=True) if model_config else None
    revision_inference = Inference(gateway, calls, revision_config, clock) if inference else None
    revision_workflow = CopyRevisionWorkflow(campaigns, drafts, memory, revision_inference, reviews)
    revision_service = CopyRevisionService(reviews, drafts, memory, tasks, clock, revision_config)
    capabilities = revision_workflow.capabilities() | workflow.capabilities() | ConversationMail(audiences, campaigns).capabilities() | model_workflow.capabilities() | conversation_model.capabilities() | {PLANNER_CAPABILITY: planner.plan, FIXTURE_CAPABILITY: planner.fixture_plan}
    return Application(tasks, audiences, drafts, Worker(tasks, capabilities, clock, lease_seconds=180 if inference else 60,
                       eligible=lambda capability, inputs: model_workflow.eligible(capability, inputs) and conversation_model.eligible(capability, inputs) and planner.eligible(capability, inputs) and revision_workflow.eligible(capability, inputs)), clock,
                       campaigns.catalogue_hash, memory, calls, inference,
                       ReviewService(reviews, ReviewProposalBuilder(audiences, drafts, campaigns)),
                       LearningService(SqliteLearning(database, clock), AcceptedCohortSource(reviews, drafts)), conversations, revision_service)
