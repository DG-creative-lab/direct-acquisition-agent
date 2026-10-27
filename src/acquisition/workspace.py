"""Local interactive sandbox facade. Domain services retain decision authority."""

import csv
import io
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from acquisition.bootstrap import build
from acquisition.adapters.environment import openrouter_key
from acquisition.adapters.openrouter import OpenRouter
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.learning import identifier
from acquisition.reasoning import ModelConfig
from acquisition.creative import validate_fact_pack
from acquisition.reviews import ReviewPolicy, text


class Workspace:
    def __init__(self, root, real_clock=time.time):
        self.real_clock = real_clock
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.control() as db:
            db.execute("CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS commands(session_id TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, done INTEGER NOT NULL, PRIMARY KEY(session_id,request_id))")
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
        return build(self.root / session["organization"] / "campaign.sqlite", clock=lambda: max(self.real_clock(), session["clock"]) if session.get("clock_mode") == "REAL" else session["clock"], gateway=gateway, model_config=config)

    def listing(self):
        with self.lock, self.control() as db:
            sessions = [json.loads(r[0]) for r in db.execute("SELECT payload FROM sessions ORDER BY rowid DESC LIMIT 50")]
        return {"sessions": [{k: s[k] for k in ("id", "name", "mode", "created_at", "case_id")} for s in sessions],
                "mode": "LOCAL_SYNTHETIC_SANDBOX", "hosted_authentication": False}

    def _conversation_app(self, with_model=False):
        # Scope and database location are server-owned, never model/browser input.
        gateway = OpenRouter(openrouter_key(Path(".env.local"))) if with_model else None
        config = ModelConfig("openai/gpt-oss-120b", max_calls=2, force_tool_choice=True) if with_model else None
        return build(self.root / "conversations.sqlite", clock=self.real_clock, gateway=gateway, model_config=config)

    def conversations(self):
        with self.lock:
            return {"conversations": self._conversation_app().conversations.store.listing("local-conversations")}

    def conversation(self, conversation_id):
        with self.lock:
            return self._conversation_app().conversations.view("local-conversations", conversation_id)

    def create_conversation(self, request_id, title):
        with self.lock:
            return self._conversation_app().conversations.create("local-conversations", request_id, title)

    def message_conversation(self, conversation_id, request_id, expected_revision, content):
        with self.lock:
            return self._conversation_app().conversations.message("local-conversations", conversation_id, request_id, expected_revision, content)

    def plan_conversation(self, conversation_id, request_id, expected_revision):
        with self.lock:
            app = self._conversation_app(with_model=True)
            run_id = app.conversations.plan("local-conversations", conversation_id, request_id, expected_revision)
            app.worker.drain("local-conversations", run_id=run_id)
            return app.conversations.view("local-conversations", conversation_id)

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
                        "parent_id": parent_id, "clock_mode": "SIMULATED" if parent or mode == "fixture" else "REAL", "created_at": self.real_clock(), "run_id": None,
                        "case_id": None, "cohort_id": None}
                    db.execute("INSERT INTO sessions VALUES(?,?,?)", (identity, fingerprint, canonical(session)))
            return self.prepare(identity)

    def prepare(self, identity):
        with self.lock:
            session = self._session(identity)
            if session["case_id"]:
                return self.view(identity)
            app = self._app(session, with_model=True)
            store = app.reviews.store
            scope = session["organization"]
            store.register_actor(scope, "local-operator", ("operator",))
            store.register_actor(scope, "local-reviewer", ("reviewer",))
            if store.evidence(scope) is None:
                store.activate(scope, "local-operator", "initial-evidence", self.pack, ReviewPolicy())
            start = app.start_model if session["mode"] == "model" else app.start
            # Resume the admitted plan, including after a lost metadata write.
            # Recomputing context here could conflict with newly learned memory.
            run = session["run_id"] or app.tasks.find_run(scope, identity)
            if run is None:
                run = start(scope, identity, as_of=datetime.fromtimestamp(session["clock"], timezone.utc).date().isoformat())
            session["run_id"] = run
            self._save(session)
            if session["mode"] == "model":
                today = datetime.fromtimestamp(self.real_clock(), timezone.utc).date()
                validate_fact_pack(store.evidence(scope)["pack"], today)
                admitted = app.tasks.inspect(scope, run)
                for context_id in admitted["tasks"][0]["inputs"]["context_ids"].values():
                    validate_fact_pack(app.memory.get_context(scope, context_id)["product_facts"], today)
            app.worker.drain(scope)
            state = app.tasks.inspect(scope, run)
            if state["run"]["status"] not in {"waiting", "succeeded"}:
                raise Conflict("Preparation has not reached review. Inspect the task status before resuming.")
            case = store.open_case(scope, run, "local-operator")
            session["case_id"] = case["case_id"]
            self._save(session)
            return self.view(identity)

    def view(self, identity):
        with self.lock:
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
            return {"session": public, "review": review, "audience": population,
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
            if kind == "manifest":
                return canonical(draft.manifest).encode(), "application/json", "manifest.json"
            if kind in {"mailing", "assignments"}:
                return getattr(draft, kind + "_csv").encode(), "text/csv; charset=utf-8", kind + ".csv"
            raise NotFound("Unknown artifact")
