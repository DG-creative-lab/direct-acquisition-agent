"""Persistent continuation to an unapproved campaign, never release authority."""

from threading import Lock

from acquisition.contracts import Conflict, digest
from acquisition.reasoning import ModelError
from .domain import identity, revision_number
from .ports import PreparationHost, PreparationStore


ACTIVE_PREPARATION = frozenset({"admitting", "planning", "preparing"})


class PreparationCoordinator:
    def __init__(self, store: PreparationStore, host: PreparationHost):
        self.store, self.host = store, host
        self.execution = Lock()

    def admit(self, organization, conversation_id, request_id, expected_revision, fixture, allow_model_copy):
        identity(organization), identity(conversation_id), identity(request_id), revision_number(expected_revision)
        if expected_revision < 1 or type(fixture) is not bool or type(allow_model_copy) is not bool or (fixture and allow_model_copy):
            raise ValueError("Choose a current brief and explicit generation permissions")
        inputs = {"conversation_id": conversation_id, "revision": expected_revision,
                  "fixture": fixture, "allow_model_copy": allow_model_copy}
        old = self.store.request(organization, request_id)
        if old:
            if old["inputs"] != inputs:
                raise Conflict("Preparation request already binds different inputs or consent")
            return old
        if self.store.for_revision(organization, conversation_id, expected_revision):
            raise Conflict("This revision already has a preparation request; inspect its original progress")
        preparation_id = "preparation_" + digest({"organization": organization, **inputs})[:32]
        plan_request = preparation_id + ":plan"
        context = self.host.freeze_preparation_plan(organization, conversation_id, plan_request, expected_revision, fixture)
        # Persist consent and frozen inputs first. Startup can discover this row
        # even if plan/task admission or its metadata write is interrupted.
        row = self.store.create(organization, request_id, {"id": preparation_id, "inputs": inputs,
            "planning_context": context, "planning_context_id": digest(context),
            "plan_request_id": plan_request, "run_id": None, "status": "admitting", "detail": None})
        return self._admit_plan(organization, row)

    def _admit_plan(self, organization, row):
        if row["status"] != "admitting":
            return row
        if digest(row["planning_context"]) != row["planning_context_id"]:
            raise Conflict("Saved preparation context failed integrity checks")
        run_id = self.host.admit_preparation_plan(organization, row)
        return self.store.update(organization, row, "planning", None, run_id=run_id)

    def step(self, organization, preparation_id):
        # The supported local deployment has one executor. Runtime leases and
        # inference reservations remain authoritative for each downstream task.
        with self.execution:
            row = self.store.get(organization, preparation_id)
            if row["status"] not in ACTIVE_PREPARATION:
                return row
            inputs = row["inputs"]
            # Storage interruptions during reconciliation must leave admitting
            # work discoverable, rather than converting it to a terminal failure.
            if row["status"] == "admitting":
                source = self.host.preparation_source(organization, inputs["conversation_id"])
                if source["revision"] != inputs["revision"]:
                    return self._stale(organization, row)
                try:
                    return self._admit_plan(organization, row)
                except (Conflict, ValueError, ModelError):
                    source = self.host.preparation_source(organization, inputs["conversation_id"])
                    if source["revision"] != inputs["revision"]:
                        return self._stale(organization, row)
                    return self.store.update(organization, row, "blocked", "Planning admission stopped. Inspect the original inputs and server configuration.")
            try:
                source = self.host.preparation_source(organization, inputs["conversation_id"])
                if source["revision"] != inputs["revision"]:
                    return self._stale(organization, row)
                if row["status"] == "planning":
                    state = self.host.step_preparation_plan(organization, row)
                    source = self.host.preparation_source(organization, inputs["conversation_id"])
                    if source["revision"] != inputs["revision"]:
                        return self._stale(organization, row)
                    plan = source["current_plan"]
                    if state["status"] in {"failed", "cancelled"}:
                        return self._failed(organization, row, state)
                    if not plan or plan["status"] != "succeeded":
                        return row
                    result = plan["result"]
                    if result["outcome"] != "brief_proposal":
                        return self.store.update(organization, row, "needs_input", "Answer the agent or revise the request to continue.")
                    if result["copy_mode"] == "model" and not inputs["allow_model_copy"]:
                        return self.store.update(organization, row, "needs_consent", "Enable model copy and send a new message to continue. No copy has been generated.")
                    return self.store.update(organization, row, "preparing", None)
                plan = source["current_plan"]
                if not plan or plan["request_id"] != row["plan_request_id"] or not plan["result"]:
                    raise Conflict("The original proposal is unavailable")
                campaign = self.host.step_preparation_campaign(organization, row, plan["result"])
                source = self.host.preparation_source(organization, inputs["conversation_id"])
                if source["revision"] != inputs["revision"]:
                    return self._stale(organization, row)
                if campaign["review"]:
                    valid = campaign["review"]["candidate_valid"]
                    return self.store.update(organization, row, "review_ready" if valid else "blocked",
                                             "Unapproved synthetic campaign ready for human review." if valid else "Campaign validation blocked review. Inspect the campaign.")
                generation = self.host.preparation_generation(organization, row)
                if generation and generation["status"] in {"failed", "cancelled"}:
                    return self._failed(organization, row, generation)
                return row
            except Exception:
                # Domain/runtime records own diagnostic evidence. Never persist raw
                # provider exceptions, credentials or untrusted response bodies here.
                source = self.host.preparation_source(organization, inputs["conversation_id"])
                if source["revision"] != inputs["revision"]:
                    return self._stale(organization, row)
                generation = self.host.preparation_generation(organization, row)
                if generation and (generation["outcome_uncertain"] or generation["status"] in {"failed", "cancelled"}):
                    return self._failed(organization, row, generation)
                return self.store.update(organization, row, "blocked", "Preparation stopped. Inspect the original run and server configuration before continuing.")

    def _stale(self, organization, row):
        generation = self.host.preparation_generation(organization, row)
        uncertain = generation and generation["outcome_uncertain"]
        return self.store.update(organization, row, "uncertain" if uncertain else "stale",
            "The brief changed. The provider may have processed and charged for this request. Inspect the original run before requesting another generation."
            if uncertain else "The brief changed. This preparation will not continue.")

    def _failed(self, organization, row, generation):
        uncertain = generation["outcome_uncertain"]
        return self.store.update(organization, row, "uncertain" if uncertain else "failed",
            "The provider may have processed and charged for this request. Inspect the original run before requesting another generation."
            if uncertain else "The saved run failed. Inspect its status and configuration before sending a revised request.")

    def recover(self, organization):
        """Call only after acquiring the deployment's exclusive executor lock."""
        for row in self.store.listing(organization):
            if row["status"] not in ACTIVE_PREPARATION:
                continue
            source = self.host.preparation_source(organization, row["inputs"]["conversation_id"])
            if source["revision"] != row["inputs"]["revision"]:
                self._stale(organization, row)
                continue
            generation = self.host.preparation_generation(organization, row)
            if generation and generation["outcome_uncertain"]:
                self._failed(organization, row, generation)
