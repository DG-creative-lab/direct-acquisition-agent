"""Composition root: the only place that selects and wires concrete adapters."""

import time
import json
from collections.abc import Callable
from dataclasses import dataclass
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
from acquisition.campaigns import Brief, CampaignService
from acquisition.creative import fixture_catalog, validate_fact_pack
from acquisition.runtime import TaskStore, Worker
from acquisition.reasoning import Inference, ModelConfig, ModelGateway
from acquisition.workflows.monthly_mail import MonthlyMail, task_plan
from acquisition.workflows.model_mail import ModelMonthlyMail, model_task_plan
from acquisition.adapters.sqlite.reviews import SqliteReviews
from acquisition.reviews import ReviewService
from acquisition.workflows.review import ReviewProposalBuilder


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

    def start(self, organization: str, request_id: str, size: int = 1000, seed: int = 42,
              budget_pence: int = 85000, as_of: str = "2026-10-25", campaign_id: str | None = None) -> str:
        snapshot_id = self.audiences.put(generate(organization, size, seed, as_of))
        brief = Brief(campaign_id=campaign_id or request_id, budget_pence=budget_pence)
        return self.tasks.create(organization, request_id, task_plan(snapshot_id, brief, self.catalogue_hash), self.clock())

    def start_model(self, organization: str, request_id: str, size: int = 1000, seed: int = 42,
                    budget_pence: int = 85000, as_of: str = "2026-10-25", campaign_id: str | None = None) -> str:
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
        for segment in ("inventory", "contractors"):
            example = guidance["reviewer_examples"][segment]
            # Seed examples are explicitly reviewer preferences, never outcome evidence.
            if not self.memory.examples(organization, segment):
                self.memory.remember(organization, segment, **example)
            context = {"segment": segment, "guidance": guidance, "product_facts": product_facts,
                       "memory": self.memory.examples(organization, segment),
                       "audience_summary": {"input_records": sum(row.segment == segment for row in snapshot.records),
                           "model_version": snapshot.model_version, "snapshot_id": snapshot.id,
                           "situation_hypothesis": guidance["situations"][segment],
                           "outcome_evidence": "No mature campaign evidence is available in day two."}}
            contexts[segment] = self.memory.put_context(organization, context)
        specs = model_task_plan(snapshot_id, Brief(campaign_id or request_id, budget_pence), contexts, self.inference)
        return self.tasks.create(organization, request_id, specs, self.clock())

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
    capabilities = workflow.capabilities() | model_workflow.capabilities()
    return Application(tasks, audiences, drafts, Worker(tasks, capabilities, clock, lease_seconds=180 if inference else 60,
                       eligible=model_workflow.eligible), clock,
                       campaigns.catalogue_hash, memory, calls, inference,
                       ReviewService(SqliteReviews(database, clock), ReviewProposalBuilder(audiences, drafts, campaigns)))
