"""Local interactive sandbox facade. Domain services retain decision authority."""

import csv
import io
import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from acquisition.bootstrap import build, build_preparations
from acquisition.conversations import ACTIVE_PREPARATION
from acquisition.adapters.environment import openrouter_key
from acquisition.adapters.openrouter import OpenRouter
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.learning import identifier
from acquisition.reasoning import ModelConfig
from acquisition.creative import validate_fact_pack
from acquisition.reviews import ReviewPolicy, text


REVISION_BLOCKS = {
    "evidence_unavailable": "Product evidence is unavailable or outside its review window. Review verified evidence and prepare a current campaign before requesting another revision. This request keeps its frozen inputs.",
    "configuration_unavailable": "Restore the server-side OpenRouter key and the original model settings. This saved request will resume automatically when its configuration is available. Do not submit another revision to retry it.",
    "continuation_unavailable": "Revision continuation is unavailable. Inspect the original run and server storage. The server will recheck this saved request; it will not repeat an uncertain provider call.",
}


class Workspace:
    def __init__(self, root, real_clock=time.time):
        self.real_clock = real_clock
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.control() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS commands(session_id TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, done INTEGER NOT NULL, PRIMARY KEY(session_id,request_id))")
            db.execute("CREATE TABLE IF NOT EXISTS conversation_draft_requests(conversation_id TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, session_id TEXT NOT NULL, PRIMARY KEY(conversation_id,request_id))")
            db.execute("CREATE TABLE IF NOT EXISTS copy_revision_blocks(organization TEXT NOT NULL, revision_id TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY(organization,revision_id))")
        self.preparations = build_preparations(self.root / "workspace.sqlite", self)
        self.pack = json.loads((Path(__file__).resolve().parents[2] / "config/iwoca-product-facts-v1.json").read_text())

    @contextmanager
    def control(self):
        db = sqlite3.connect(self.root / "workspace.sqlite", timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def _save(self, session):
        with self.control() as db:
            db.execute("UPDATE sessions SET payload=? WHERE id=?", (canonical(session), session["id"]))

    def _session(self, identity):
        identifier(identity)
        with self.control() as db:
            row = db.execute("SELECT payload FROM sessions WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise NotFound("Campaign not found in this workspace")
        return json.loads(row[0])

    def _app(self, session, with_model=False):
        gateway, config = None, None
        if with_model and session["mode"] == "model":
            validate_fact_pack(self.pack, datetime.fromtimestamp(self.real_clock(), timezone.utc).date())
            gateway = OpenRouter(openrouter_key(Path(".env.local")))
            config = ModelConfig("openai/gpt-oss-120b", max_calls=10, force_tool_choice=True)
        # Each sandbox has its own durable clock. Live generation starts at real
        # time; explicit outcome simulation alone can advance the sandbox clock.
        conversation_db = session.get("database_scope") == "conversations" or session.get("conversation_plan") or session["organization"] == "local-conversations"
        database = self.root / "conversations.sqlite" if conversation_db else self.root / session["organization"] / "campaign.sqlite"
        return build(database, clock=lambda: max(self.real_clock(), session["clock"]) if session.get("clock_mode") == "REAL" else session["clock"], gateway=gateway, model_config=config)

    def listing(self):
        with self.control() as db:
            sessions = [json.loads(r[0]) for r in db.execute("SELECT payload FROM sessions ORDER BY rowid DESC LIMIT 50")]
        return {"sessions": [{k: s[k] for k in ("id", "name", "mode", "created_at", "case_id")} for s in sessions],
                "mode": "LOCAL_SYNTHETIC_SANDBOX", "hosted_authentication": False}

    def _conversation_app(self, with_model=False):
        # Scope and database location are server-owned, never model/browser input.
        gateway = OpenRouter(openrouter_key(Path(".env.local"))) if with_model else None
        config = ModelConfig("openai/gpt-oss-120b", max_calls=2, force_tool_choice=True) if with_model else None
        return build(self.root / "conversations.sqlite", clock=self.real_clock, gateway=gateway, model_config=config)

    def conversations(self):
        return {"conversations": self._conversation_app().conversations.store.listing("local-conversations")}

    def knowledge(self):
        config = Path(__file__).resolve().parents[2] / "config"
        playbooks = json.loads((config / "campaign-playbooks-v1.json").read_text())
        editorial = json.loads((config / "editorial-v3.json").read_text())
        return {"playbooks": playbooks, "product_facts": self.pack,
                "editorial": {"version": editorial["version"], "rules": editorial["rules"],
                              "situations": editorial["situations"]},
                "learning": "Synthetic outcome memory is scoped to each campaign and is advisory. Inspect it in Learning."}

    def conversation(self, conversation_id):
        view = self._conversation_app().conversations.view("local-conversations", conversation_id)
        with self.control() as db:
            sessions = [json.loads(r[0]) for r in db.execute("SELECT payload FROM sessions ORDER BY rowid DESC")]
        return view | {"preparations": self.preparation_progress(conversation_id), "campaigns": [{"session_id": s["id"], "plan_id": s["conversation_plan"]["id"],
                                      "revision": s["conversation_plan"]["revision"], "case_id": s["case_id"],
                                      "generation": self._generation(s)}
                                     for s in sessions if s.get("conversation_plan", {}).get("conversation_id") == conversation_id]}

    def _generation(self, session):
        app = self._app(session)
        scope = session["organization"]
        run = session["run_id"] or app.tasks.find_run(scope, session["id"])
        if run is None:
            return {"run_id": None, "status": "admitted", "failed_tasks": [], "provider_error": None,
                    "outcome_uncertain": False, "unresolved_calls": []}
        return self._run_generation(app, scope, run)

    @staticmethod
    def _run_generation(app, scope, run):
        state = app.tasks.inspect(scope, run)
        failures = [{"capability": task["capability"], "error_code": (task["output"] or {}).get("error_code")}
                    for task in state["tasks"] if task["status"] == "failed"]
        # Only explicit public codes leave the journal. Provider response bodies and task messages stay private.
        receipts = app.calls.inspect(scope, run)
        codes = [r["error"] for r in receipts if r["error"]]
        provider_error = next((code for code in reversed(codes) if re.fullmatch(r"provider_http_[1-5][0-9]{2}", code)
                               or code in {"provider_outcome_unknown", "provider_request_failed"}), None)
        definitive_rejections = {"provider_http_400", "provider_http_401", "provider_http_403", "provider_http_404", "provider_http_422"}
        unresolved = [{"key": r["key"], "status": r["status"]} for r in receipts
                      if r["status"] == "reserved" or (r["status"] == "unknown" and r["error"] not in definitive_rejections)]
        return {"run_id": run, "status": state["run"]["status"], "failed_tasks": failures, "provider_error": provider_error,
                "outcome_uncertain": bool(unresolved), "unresolved_calls": unresolved,
                "steps": [{"capability": t["capability"], "status": t["status"]} for t in state["tasks"]]}

    def create_conversation(self, request_id, title):
        return self._conversation_app().conversations.create("local-conversations", request_id, title)

    @staticmethod
    def _preparation_scope(organization):
        if organization != "local-conversations":
            raise NotFound("Conversation organization is not available in this workspace")

    def freeze_preparation_plan(self, organization, conversation_id, request_id, revision, fixture):
        self._preparation_scope(organization)
        app = self._conversation_app(with_model=not fixture)
        return app.conversations.planning_context(organization, conversation_id, request_id, revision, fixture)

    def admit_preparation_plan(self, organization, row):
        self._preparation_scope(organization)
        inputs = row["inputs"]
        app = self._conversation_app(with_model=not inputs["fixture"])
        plan = app.conversations.plan_fixture if inputs["fixture"] else app.conversations.plan
        return plan(organization, inputs["conversation_id"], row["plan_request_id"], inputs["revision"],
                    frozen_context=row["planning_context"])

    def preparation_source(self, organization, conversation_id):
        self._preparation_scope(organization)
        return self._conversation_app().conversations.view(organization, conversation_id)

    def step_preparation_plan(self, organization, row):
        self._preparation_scope(organization)
        with self.lock:
            app = self._conversation_app(with_model=not row["inputs"]["fixture"])
            app.worker.tick(organization, run_id=row["run_id"])
            return self._run_generation(app, organization, row["run_id"])

    def step_preparation_campaign(self, organization, row, plan):
        self._preparation_scope(organization)
        return self.draft_conversation(row["inputs"]["conversation_id"], row["id"] + ":draft",
                                       row["inputs"]["revision"], plan["id"], partial=True)

    def preparation_generation(self, organization, row):
        self._preparation_scope(organization)
        with self.control() as db:
            match = db.execute("SELECT session_id FROM conversation_draft_requests WHERE conversation_id=? AND request_id=?",
                               (row["inputs"]["conversation_id"], row["id"] + ":draft")).fetchone()
        if match:
            return self._generation(self._session(match[0]))
        app = self._conversation_app()
        run_id = row["run_id"]
        if run_id is None:
            source = app.conversations.view(organization, row["inputs"]["conversation_id"])
            plan = next((p for p in source["plans"] if p["request_id"] == row["plan_request_id"]), None)
            run_id = plan["run_id"] if plan else None
        return self._run_generation(app, organization, run_id) if run_id else None

    def start_preparation(self, conversation_id, request_id, expected_revision, fixture, allow_model_copy):
        self.preparations.admit("local-conversations", conversation_id, request_id, expected_revision, fixture, allow_model_copy)
        return self.conversation(conversation_id)

    def preparation_progress(self, conversation_id):
        source = self.preparation_source("local-conversations", conversation_id)
        values = []
        for row in self.preparations.store.listing("local-conversations", conversation_id):
            generation = self.preparation_generation("local-conversations", row)
            # Frozen model inputs remain server-side. The plan's existing guidance
            # projection is the public inspection surface for that content.
            public = {k: v for k, v in row.items() if k != "planning_context"}
            values.append(public | {"current": source["revision"] == row["inputs"]["revision"], "generation": generation})
        return values

    def advance_preparations(self):
        for row in self.preparations.store.listing("local-conversations"):
            if row["status"] in ACTIVE_PREPARATION:
                self.preparations.step("local-conversations", row["id"])
        self.advance_copy_revisions()

    def request_copy_revision(self, identity, request_id, expected_subject, target_id, feedback, allow_model_copy):
        if allow_model_copy is not True:
            raise ValueError("Explicit model-copy permission is required for a revision")
        with self.lock:
            session = self._session(identity)
            if session["mode"] != "model" or not session["case_id"]:
                raise Conflict("Prepare a grounded model campaign before revising copy")
            app = self._app(session)
            prior = app.reviews.store.revision_request(session["organization"], request_id)
            if prior is None:
                app = self._app(session, with_model=True)
            app.revisions.admit(session["organization"], session["case_id"], request_id, expected_subject, target_id, feedback, allow_model_copy)
            return self.view(identity) | {"command_replayed": prior is not None}

    def _copy_revision_progress(self, app, scope, case):
        rows = app.revisions.view(scope, case)
        for row in rows:
            generation = self._run_generation(app, scope, row["run_id"]) if row["run_id"] else None
            row["generation"] = generation
            with self.control() as db:
                block = db.execute("SELECT code FROM copy_revision_blocks WHERE organization=? AND revision_id=?", (scope, row["id"])).fetchone()
            code = block[0] if block and block[0] in REVISION_BLOCKS else None
            row["block"] = {"code": code, "detail": REVISION_BLOCKS[code]} if code else None
            if code and row["status"] in {"admitted", "queued", "running"}:
                row["status"] = "blocked"
            if generation and generation["outcome_uncertain"] and row["status"] not in {"queued", "running"}:
                row["status"] = "uncertain"
        return rows

    def _set_revision_block(self, scope, revision_id, code):
        with self.control() as db:
            if code is None:
                db.execute("DELETE FROM copy_revision_blocks WHERE organization=? AND revision_id=?", (scope, revision_id))
            else:
                if code not in REVISION_BLOCKS:
                    raise ValueError("Use a public revision blocker code")
                db.execute("INSERT INTO copy_revision_blocks VALUES(?,?,?) ON CONFLICT(organization,revision_id) DO UPDATE SET code=excluded.code WHERE code<>excluded.code", (scope, revision_id, code))

    def recover_copy_revisions(self):
        with self.control() as db:
            sessions = [json.loads(r[0]) for r in db.execute("SELECT payload FROM sessions")]
        for session in sessions:
            if not session["case_id"]:
                continue
            app, scope = self._app(session), session["organization"]
            for row in app.revisions.view(scope, session["case_id"]):
                if row["run_id"] and app.tasks.inspect(scope, row["run_id"])["run"]["status"] not in {"failed", "cancelled", "succeeded"} and self._run_generation(app, scope, row["run_id"])["outcome_uncertain"]:
                    app.tasks.cancel(scope, row["run_id"], app.clock())

    def advance_copy_revisions(self):
        with self.control() as db:
            sessions = [json.loads(r[0]) for r in db.execute("SELECT payload FROM sessions")]
        for session in sessions:
            if not session["case_id"]:
                continue
            app, scope = self._app(session), session["organization"]
            for row in app.revisions.view(scope, session["case_id"]):
                blocker = "continuation_unavailable"
                try:
                    if row["status"] == "stale":
                        if row["run_id"]:
                            app.tasks.cancel(scope, row["run_id"], app.clock())
                        continue
                    if row["status"] not in {"admitted", "queued", "running", "complete"}:
                        continue
                    if row["status"] == "complete" and app.tasks.inspect(scope, row["run_id"])["run"]["status"] in {"succeeded", "failed", "cancelled"}:
                        continue
                    with self.lock:
                        receipt = app.reviews.store.revision_request(scope, row["request_id"])
                        blocker = "evidence_unavailable"
                        today = datetime.fromtimestamp(app.clock(), timezone.utc).date()
                        for pack in (self.pack, receipt["context"]["product_facts"], app.reviews.store.evidence(scope)["pack"]):
                            validate_fact_pack(pack, today)
                        blocker = "configuration_unavailable"
                        configured = self._app(session, with_model=True)
                        run = configured.revisions.reconcile(scope, receipt)
                        blocker = "continuation_unavailable"
                        # Configuration is restored before dispatch. Do not let
                        # its old blocker relabel a live reserved call as uncertain.
                        self._set_revision_block(scope, row["id"], None)
                        configured.worker.tick(scope, run_id=run)
                except Exception:
                    # Projection metadata is not task authority. Keep original
                    # admission/consent, leases and inference journals intact.
                    # Raw configuration/provider errors never leave this boundary.
                    self._set_revision_block(scope, row["id"], blocker)

    def message_conversation(self, conversation_id, request_id, expected_revision, content):
        return self._conversation_app().conversations.message("local-conversations", conversation_id, request_id, expected_revision, content)

    def plan_conversation(self, conversation_id, request_id, expected_revision):
        with self.lock:
            app = self._conversation_app(with_model=True)
            run_id = app.conversations.plan("local-conversations", conversation_id, request_id, expected_revision)
            app.worker.drain("local-conversations", run_id=run_id)
            return app.conversations.view("local-conversations", conversation_id)

    def plan_conversation_fixture(self, conversation_id, request_id, expected_revision):
        with self.lock:
            app = self._conversation_app()
            run_id = app.conversations.plan_fixture("local-conversations", conversation_id, request_id, expected_revision)
            app.worker.drain(organization="local-conversations", run_id=run_id)
            return app.conversations.view("local-conversations", conversation_id)

    def draft_conversation(self, conversation_id, request_id, expected_revision, plan_id, *, partial=False):
        identifier(conversation_id), identifier(request_id), identifier(plan_id)
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("Select a current conversation revision")
        fingerprint = digest({"conversation_id": conversation_id, "revision": expected_revision, "plan_id": plan_id})
        session_id = "workspace_" + digest({"conversation_id": conversation_id, "plan_id": plan_id})[:24]
        with self.lock:
            with self.control() as db:
                prior_draft = db.execute("SELECT * FROM conversation_draft_requests WHERE conversation_id=? AND request_id=?", (conversation_id, request_id)).fetchone()
                if prior_draft:
                    if prior_draft["request_hash"] != fingerprint:
                        raise Conflict("Draft request already binds different proposal inputs")
                    return self.prepare(prior_draft["session_id"], partial=partial)
            view = self._conversation_app().conversations.view("local-conversations", conversation_id)
            current = view["current_plan"]
            plan = current["result"] if current and current["status"] == "succeeded" else None
            if view["revision"] != expected_revision or not plan or plan["id"] != plan_id or plan["outcome"] != "brief_proposal":
                raise Conflict("Select the exact current completed brief proposal")
            model_copy = plan["copy_mode"] == "model"
            start = self.real_clock() if model_copy else datetime.fromisoformat(self.pack["checked_on"]).replace(tzinfo=timezone.utc).timestamp() + 43200
            if model_copy:
                validate_fact_pack(self.pack, datetime.fromtimestamp(start, timezone.utc).date())
            session = {"id": session_id, "name": "Conversation / " + plan["objective"][:70], "mode": plan["copy_mode"],
                       "organization": session_id, "database_scope": "conversations", "clock": start, "parent_id": None,
                       "clock_mode": "REAL" if model_copy else "SIMULATED", "created_at": self.real_clock(), "run_id": None,
                       "case_id": None, "cohort_id": None, "conversation_plan": plan}
            with self.control() as db:
                db.execute("BEGIN IMMEDIATE")
                try:
                    replay = db.execute("SELECT * FROM conversation_draft_requests WHERE conversation_id=? AND request_id=?", (conversation_id, request_id)).fetchone()
                    if replay is not None and (replay["request_hash"] != fingerprint or replay["session_id"] != session_id):
                        raise Conflict("Draft request already binds different proposal inputs")
                    existing = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
                    if existing is not None and existing["request_hash"] != fingerprint:
                        raise Conflict("Campaign identity already binds different proposal inputs")
                    if existing is None:
                        db.execute("INSERT INTO sessions VALUES(?,?,?)", (session_id, fingerprint, canonical(session)))
                    if replay is None:
                        db.execute("INSERT INTO conversation_draft_requests VALUES(?,?,?,?)", (conversation_id, request_id, fingerprint, session_id))
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise
            return self.prepare(session_id, partial=partial)

    def create(self, request_id, mode, parent_id=None):
        identifier(request_id)
        if type(mode) is not str or mode not in {"fixture", "model"}:
            raise ValueError("Choose fixture or model copy")
        identity = "workspace_" + digest({"request_id": request_id})[:24]
        fingerprint = digest({"mode": mode, "parent_id": parent_id})
        with self.lock:
            with self.control() as db:
                old = db.execute("SELECT * FROM sessions WHERE id=?", (identity,)).fetchone()
                if old and old["request_hash"] != fingerprint:
                    raise Conflict("Campaign request already binds another copy mode")
                if old is None:
                    parent = self._session(parent_id) if parent_id else None
                    if parent and (not parent["cohort_id"] or self._app(parent).learning.store.view(parent["organization"], parent["cohort_id"])["status"] != "finalized"):
                        raise Conflict("Only finalized learning can seed the next experiment")
                    start = (datetime.fromisoformat(self.pack["checked_on"]).replace(tzinfo=timezone.utc).timestamp() + 43200
                             if mode == "fixture" else self.real_clock())
                    if parent:
                        start = max(start, parent["clock"])
                    session = {"id": identity, "name": "Working capital / " + ("model copy" if mode == "model" else "offline demo"),
                        "mode": mode, "organization": parent["organization"] if parent else identity, "clock": start,
                        "parent_id": parent_id, "database_scope": (parent.get("database_scope") or ("conversations" if parent.get("conversation_plan") or parent["organization"] == "local-conversations" else "campaign")) if parent else "campaign", "clock_mode": "SIMULATED" if parent or mode == "fixture" else "REAL", "created_at": self.real_clock(), "run_id": None,
                        "case_id": None, "cohort_id": None}
                    db.execute("INSERT INTO sessions VALUES(?,?,?)", (identity, fingerprint, canonical(session)))
            return self.prepare(identity)

    def prepare(self, identity, *, partial=False):
        with self.lock:
            session = self._session(identity)
            if session["case_id"]:
                return self.view(identity)
            app = self._app(session, with_model=True)
            store = app.reviews.store
            scope = session["organization"]
            store.initialize_actor(scope, "local-operator", ("operator",))
            store.initialize_actor(scope, "local-reviewer", ("reviewer",))
            if store.evidence(scope) is None:
                store.activate(scope, "local-operator", "initial-evidence", self.pack, ReviewPolicy())
            start = app.start_model if session["mode"] == "model" else app.start
            # Resume the admitted plan, including after a lost metadata write.
            # Recomputing context here could conflict with newly learned memory.
            run = session["run_id"] or app.tasks.find_run(scope, identity)
            if session.get("conversation_plan") and session["mode"] == "model":
                source = session["conversation_plan"]
                current = app.conversations.view("local-conversations", source["conversation_id"])
                if current["revision"] != source["revision"] or not current["current_plan"] or current["current_plan"]["result"] != source:
                    raise Conflict("Conversation changed before campaign preparation")
            if run is None:
                if session.get("conversation_plan"):
                    source = session["conversation_plan"]
                    current = app.conversations.view("local-conversations", source["conversation_id"])
                    if current["revision"] != source["revision"] or not current["current_plan"] or current["current_plan"]["result"] != source:
                        raise Conflict("Conversation changed before campaign preparation")
                    run = app.start_conversation(scope, identity, source, datetime.fromtimestamp(session["clock"], timezone.utc).date().isoformat())
                else:
                    run = start(scope, identity, as_of=datetime.fromtimestamp(session["clock"], timezone.utc).date().isoformat())
            session["run_id"] = run
            self._save(session)
            if session["mode"] == "model":
                today = datetime.fromtimestamp(self.real_clock(), timezone.utc).date()
                validate_fact_pack(store.evidence(scope)["pack"], today)
                admitted = app.tasks.inspect(scope, run)
                for context_id in admitted["tasks"][0]["inputs"]["context_ids"].values():
                    validate_fact_pack(app.memory.get_context(scope, context_id)["product_facts"], today)
            app.worker.drain(scope, max_tasks=1 if partial else 20, run_id=run)
            state = app.tasks.inspect(scope, run)
            if state["run"]["status"] not in {"waiting", "succeeded"}:
                if partial:
                    return self.view(identity)
                raise Conflict("Preparation has not reached review. Inspect the task status before resuming.")
            case = store.open_case(scope, run, "local-operator")
            session["case_id"] = case["case_id"]
            self._save(session)
            return self.view(identity)

    def view(self, identity, *, _attempt=0):
        session = self._session(identity)
        app = self._app(session)
        scope = session["organization"]
        public = {k: v for k, v in session.items() if k != "organization"}
        public["clock"] = app.clock()
        if not session["case_id"]:
            return {"session": public, "review": None, "audience": [], "learning": None,
                    "tasks": app.tasks.inspect(scope, session["run_id"]) if session["run_id"] else None}
        review = app.reviews.store.view(session["organization"], session["case_id"])
        draft = app.drafts.get(session["organization"], review["subject"]["draft_id"])
        snapshot = app.audiences.get(scope, review["subject"]["snapshot_id"])
        assignments = {r["business_id"]: r for r in csv.DictReader(io.StringIO(draft.assignments_csv))}
        population = [{"id": r.business_id, "segment": r.segment, "country": r.country,
            "entity_type": r.entity_type, "suppressed": r.suppressed or r.business_id in review["suppressions"],
            "arm": assignments.get(r.business_id, {}).get("arm", "excluded"),
            "score": r.propensity_ppm, "address": r.address} for r in snapshot.records]
        revisions = self._copy_revision_progress(app, scope, session["case_id"])
        # Admission can reject an approval without changing the subject. Recheck
        # the whole transactional review projection, including decisions and
        # current authority, after reading progress. Only the read time may vary.
        current_review = app.reviews.store.view(scope, session["case_id"])
        if {k: v for k, v in current_review.items() if k != "as_of"} != {k: v for k, v in review.items() if k != "as_of"}:
            if _attempt >= 3:
                raise Conflict("Campaign changed while loading; refresh the review")
            return self.view(identity, _attempt=_attempt + 1)
        return {"session": public, "review": review, "audience": population,
            "copy_revisions": revisions,
            "learning": app.learning.store.view(scope, session["cohort_id"]) if session["cohort_id"] else None,
            "tasks": app.tasks.inspect(scope, session["run_id"])}

    def action(self, identity, action, payload):
        with self.lock:
            session = self._session(identity)
            app = self._app(session)
            scope, case = session["organization"], session["case_id"]
            if not case:
                raise Conflict("Prepare this campaign before recording a decision")
            fields = {"approve": {"subject_id", "reason"}, "reject": {"subject_id", "reason"},
                "refresh": {"subject_id"}, "revoke": {"approval_id", "reason"},
                "suppress": {"business_id", "reason"}, "handoff": {"approval_id"},
                "open-learning": set(), "observe": set(), "finalize": set()}
            if action not in fields or set(payload) != fields[action] | {"request_id"}:
                raise ValueError("Use the exact fields for this workspace action")
            for field in fields[action]:
                text(payload[field]) if field == "reason" else identifier(payload[field])
            request_id = payload["request_id"]
            identifier(request_id)
            fingerprint = digest({"action": action, "payload": payload})
            with self.control() as db:
                old = db.execute("SELECT * FROM commands WHERE session_id=? AND request_id=?", (identity, request_id)).fetchone()
                if old:
                    if old["request_hash"] != fingerprint:
                        raise Conflict("Workspace request already binds different action inputs")
                    if old["done"]:
                        return self.view(identity) | {"command_replayed": True}
                else:
                    db.execute("INSERT INTO commands VALUES(?,?,?,0)", (identity, request_id, fingerprint))
            store = app.reviews.store
            if action in {"approve", "reject"}:
                store.decide(scope, case, payload["subject_id"], "local-reviewer", action, request_id, payload["reason"], 86400)
            elif action == "refresh":
                app.reviews.refresh(scope, case, payload["subject_id"], "local-operator", request_id)
            elif action == "revoke":
                store.revoke(scope, case, payload["approval_id"], "local-reviewer", request_id, payload["reason"])
            elif action == "suppress":
                # A suppression is an independent operator instruction, never
                # an approval. The domain invalidates affected authority.
                store.suppress(scope, "local-operator", request_id, payload["business_id"], payload["reason"])
            elif action == "handoff":
                store.handoff(scope, case, payload["approval_id"], "local-operator", request_id)
            elif action == "open-learning":
                receipt = app.learning.open(scope, case, "local-operator", request_id)
                session["cohort_id"] = receipt["cohort_id"]
                self._save(session)
            elif action in {"observe", "finalize"}:
                if not session["cohort_id"]:
                    raise Conflict("Open an outcome window first")
                cohort = app.learning.source.accepted(scope, case)
                target = cohort["window_start"] + 7 * 86400 if action == "observe" else cohort["window_end"]
                session["clock"] = max(session["clock"], target)
                session["clock_mode"] = "SIMULATED"
                self._save(session)
                # The existing app's clock closes over this session dictionary.
                rows = []
                for member in cohort["members"]:
                    response = int(digest({"business": member["business_id"], "seed": 81})[:8], 16) % 1000 < {"A": 220, "B": 35, "no_mail": 20}[member["arm"]]
                    if response or action == "finalize":
                        rows.append(member | {"response": response, "observed_at": cohort["window_start"] + 7 * 86400 if response else cohort["window_end"]})
                if rows:
                    app.learning.store.ingest(scope, "local-operator", request_id + ":import", session["cohort_id"],
                        {"schema": "synthetic-outcomes/v1", "mode": "SYNTHETIC_ONLY", "cohort_id": session["cohort_id"], "outcomes": rows})
                if action == "finalize":
                    app.learning.store.finalize(scope, "local-operator", request_id, session["cohort_id"], cohort["window_end"])
            else:
                raise ValueError("Unknown workspace action")
            with self.control() as db:
                db.execute("UPDATE commands SET done=1 WHERE session_id=? AND request_id=?", (identity, request_id))
            return self.view(identity)

    def artifact(self, identity, kind, expected_subject):
        with self.lock:
            session = self._session(identity)
            app = self._app(session)
            review = app.reviews.store.view(session["organization"], session["case_id"])
            if review["subject"]["id"] != expected_subject:
                raise Conflict("Campaign revision changed before download; refresh the workspace")
            draft = app.drafts.get(session["organization"], review["subject"]["draft_id"])
            if kind == "handoff":
                receipt = review["handoff"]
                if receipt is None:
                    raise Conflict("This campaign has no accepted simulated handoff")
                if receipt["subject_id"] != expected_subject or receipt["draft_id"] != draft.id:
                    raise Conflict("Acceptance receipt does not match the displayed subject")
                return canonical(receipt).encode(), "application/json", "handoff.json"
            if kind == "manifest":
                return canonical(draft.manifest).encode(), "application/json", "manifest.json"
            if kind in {"mailing", "assignments"}:
                return getattr(draft, kind + "_csv").encode(), "text/csv; charset=utf-8", kind + ".csv"
            raise NotFound("Unknown artifact")
