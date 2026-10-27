import json
import math
import uuid
from dataclasses import asdict
from collections.abc import Callable

from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.runtime import Claim, LeaseLost, Outcome, TaskSpec

from .database import Database, stored_plan_hash


def finite_time(now: float) -> None:
    if type(now) not in {int, float} or not math.isfinite(now):
        raise ValueError("Durable timestamps must be finite numbers")


def event(connection, run_id, task_id, kind, data, now):
    finite_time(now)
    connection.execute("INSERT INTO events(run_id,task_id,kind,data,at) VALUES(?,?,?,?,?)",
                       (run_id, task_id, kind, canonical(data), now))


def scoped_run(connection, organization, run_id):
    row = connection.execute("SELECT * FROM runs WHERE id=? AND organization=?", (run_id, organization)).fetchone()
    if row is None:
        raise NotFound("Run not found in this organization")
    return row


class SqliteTasks:
    def __init__(self, database: Database, retired_capabilities: frozenset[str] = frozenset()):
        self.database = database
        self.retired_capabilities = retired_capabilities

    def _legacy_allowed(self, connection, organization, run_id):
        row = connection.execute("""SELECT a.request_hash FROM legacy_task_admissions a
            JOIN runs r ON r.id=a.run_id AND r.organization=a.organization AND r.request_hash=a.request_hash
            WHERE a.organization=? AND a.run_id=?""", (organization, run_id)).fetchone()
        return row is not None and row["request_hash"] == stored_plan_hash(connection, run_id)

    def create(self, organization: str, request_id: str, specs: list[TaskSpec], now: float) -> str:
        finite_time(now)
        if not organization or not request_id or not 1 <= len(specs) <= 20:
            raise ValueError("Organization, request ID and 1–20 tasks required")
        request_hash = digest([asdict(spec) for spec in specs])
        with self.database.transaction() as connection:
            old = connection.execute("SELECT * FROM runs WHERE organization=? AND request_id=?",
                                     (organization, request_id)).fetchone()
            if old:
                if old["request_hash"] != request_hash:
                    raise Conflict("Idempotency key already binds different inputs")
                if any(s.capability in self.retired_capabilities for s in specs) and not self._legacy_allowed(connection, organization, old["id"]):
                    raise Conflict("Retired capabilities require a preserved legacy admission")
                return old["id"]
            if any(s.capability in self.retired_capabilities for s in specs):
                raise ValueError("Retired capabilities cannot be admitted as new runs")
            run_id = "run_" + uuid.uuid4().hex
            connection.execute("INSERT INTO runs VALUES(?,?,?,?,?,?)",
                               (run_id, organization, request_id, request_hash, "queued", now))
            for position, spec in enumerate(specs):
                connection.execute("""INSERT INTO tasks
                    (id,run_id,position,capability,inputs,status,max_attempts,available_at)
                    VALUES(?,?,?,?,?,'queued',?,?)""",
                    (uuid.uuid4().hex, run_id, position, spec.capability, canonical(spec.inputs), spec.max_attempts, now))
            event(connection, run_id, None, "run_created", {"task_count": len(specs)}, now)
            return run_id

    def find_run(self, organization: str, request_id: str) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT id FROM runs WHERE organization=? AND request_id=?", (organization, request_id)).fetchone()
            return row["id"] if row else None

    def claim(self, organization: str, now: float, lease_seconds: float,
              eligible: Callable[[str, dict], bool] | None = None, run_id: str | None = None) -> Claim | None:
        finite_time(now)
        if not math.isfinite(lease_seconds) or lease_seconds <= 0 or not math.isfinite(now):
            raise ValueError("Lease must be positive")
        finite_time(now + lease_seconds)
        def can_run(connection, row):
            if eligible is not None and not eligible(row["capability"], json.loads(row["inputs"])):
                return False
            if row["capability"] in self.retired_capabilities and not self._legacy_allowed(connection, organization, row["run_id"]):
                raise Conflict("Retired capability has no matching preserved legacy admission")
            return True
        with self.database.transaction() as connection:
            if run_id is not None:
                scoped_run(connection, organization, run_id)
            expired = connection.execute("""SELECT t.* FROM tasks t JOIN runs r ON r.id=t.run_id
                WHERE r.organization=? AND r.status='running' AND t.status='running' AND t.lease_until<=?
                AND (? IS NULL OR r.id=?)""", (organization, now, run_id, run_id)).fetchall()
            for row in expired:
                if not can_run(connection, row):
                    continue
                exhausted = row["attempts"] >= row["max_attempts"]
                connection.execute("UPDATE tasks SET status=?,token=NULL,lease_until=NULL WHERE id=?",
                                   ("failed" if exhausted else "queued", row["id"]))
                if exhausted:
                    connection.execute("UPDATE runs SET status='failed' WHERE id=?", (row["run_id"],))
                event(connection, row["run_id"], row["id"], "lease_exhausted" if exhausted else "lease_recovered", {}, now)
            candidates = connection.execute("""SELECT t.* FROM tasks t JOIN runs r ON r.id=t.run_id
                WHERE r.organization=? AND r.status IN ('queued','running') AND t.status='queued'
                AND t.available_at<=? AND (? IS NULL OR r.id=?) AND NOT EXISTS
                (SELECT 1 FROM tasks p WHERE p.run_id=t.run_id AND p.position<t.position AND p.status!='succeeded')
                ORDER BY r.created_at,r.id,t.position""", (organization, now, run_id, run_id))
            row = next((candidate for candidate in candidates if can_run(connection, candidate)), None)
            if row is None:
                return None
            token = uuid.uuid4().hex
            connection.execute("UPDATE tasks SET status='running',attempts=attempts+1,token=?,lease_until=? WHERE id=?",
                               (token, now + lease_seconds, row["id"]))
            connection.execute("UPDATE runs SET status='running' WHERE id=?", (row["run_id"],))
            event(connection, row["run_id"], row["id"], "task_claimed", {"attempt": row["attempts"] + 1}, now)
            return Claim(organization, row["run_id"], row["id"], row["capability"],
                         json.loads(row["inputs"]), token, row["attempts"] + 1,
                         json.loads(row["resume"]) if row["resume"] else None)

    def _owned(self, connection, claim: Claim, now: float):
        if not math.isfinite(now):
            raise LeaseLost("Attempt requires a finite clock reading")
        run = scoped_run(connection, claim.organization, claim.run_id)
        row = connection.execute("SELECT * FROM tasks WHERE id=? AND run_id=?",
                                 (claim.task_id, claim.run_id)).fetchone()
        if (row is None or run["status"] != "running" or row["status"] != "running"
                or row["token"] != claim.token or row["lease_until"] <= now):
            raise LeaseLost("Attempt expired, cancelled or superseded")
        return row

    def settle(self, claim: Claim, outcome: Outcome, now: float) -> None:
        with self.database.transaction() as connection:
            self._owned(connection, claim, now)
            connection.execute("UPDATE tasks SET status=?,output=?,token=NULL,lease_until=NULL WHERE id=?",
                               (outcome.status, canonical(outcome.data), claim.task_id))
            pending = connection.execute("SELECT COUNT(*) FROM tasks WHERE run_id=? AND status!='succeeded'",
                                         (claim.run_id,)).fetchone()[0]
            status = "waiting" if outcome.status == "waiting" else ("running" if pending else "succeeded")
            connection.execute("UPDATE runs SET status=? WHERE id=?", (status, claim.run_id))
            event(connection, claim.run_id, claim.task_id, "task_" + outcome.status, outcome.data, now)

    def fail(self, claim: Claim, code: str, retry: bool, now: float) -> None:
        with self.database.transaction() as connection:
            row = self._owned(connection, claim, now)
            retry = retry and row["attempts"] < row["max_attempts"]
            finite_time(now + min(30, 2 ** row["attempts"]))
            connection.execute("""UPDATE tasks SET status=?,output=?,token=NULL,lease_until=NULL,available_at=?
                                  WHERE id=?""", ("queued" if retry else "failed", canonical({"error_code": code}),
                                  now + min(30, 2 ** row["attempts"]), claim.task_id))
            if not retry:
                connection.execute("UPDATE runs SET status='failed' WHERE id=?", (claim.run_id,))
            event(connection, claim.run_id, claim.task_id, "task_retry_scheduled" if retry else "task_failed",
                  {"error_code": code}, now)

    def acknowledge(self, organization: str, run_id: str, reference: str, now: float) -> None:
        finite_time(now)
        with self.database.transaction() as connection:
            run = scoped_run(connection, organization, run_id)
            if run["status"] != "waiting":
                raise Conflict("Run is not waiting for acknowledgement")
            row = connection.execute("SELECT * FROM tasks WHERE run_id=? AND status='waiting'", (run_id,)).fetchone()
            if row is None or json.loads(row["output"])["reference"] != reference:
                raise Conflict("Acknowledgement must match the exact waiting reference")
            if row["attempts"] >= row["max_attempts"]:
                raise Conflict("Attempt budget exhausted")
            decision = {"reference": reference, "decision": "acknowledge_dry_run_only"}
            connection.execute("UPDATE tasks SET status='queued',resume=?,available_at=? WHERE id=?",
                               (canonical(decision), now, row["id"]))
            connection.execute("UPDATE runs SET status='running' WHERE id=?", (run_id,))
            event(connection, run_id, row["id"], "checkpoint_acknowledged_no_release_authority", decision, now)

    def cancel(self, organization: str, run_id: str, now: float) -> None:
        finite_time(now)
        with self.database.transaction() as connection:
            run = scoped_run(connection, organization, run_id)
            if run["status"] == "cancelled":
                return
            if run["status"] in {"succeeded", "failed"}:
                raise Conflict("Terminal run cannot be cancelled")
            connection.execute("UPDATE runs SET status='cancelled' WHERE id=?", (run_id,))
            connection.execute("""UPDATE tasks SET status='cancelled',token=NULL,lease_until=NULL
                WHERE run_id=? AND status IN ('queued','running','waiting')""", (run_id,))
            event(connection, run_id, None, "run_cancelled", {}, now)

    def inspect(self, organization: str, run_id: str) -> dict:
        with self.database.connect() as connection:
            connection.execute("BEGIN")  # One read snapshot across run/tasks/events.
            run = dict(scoped_run(connection, organization, run_id))
            tasks = [dict(row) for row in connection.execute("SELECT * FROM tasks WHERE run_id=? ORDER BY position", (run_id,))]
            events = [dict(row) for row in connection.execute("SELECT * FROM events WHERE run_id=? ORDER BY sequence", (run_id,))]
            for row in tasks:
                for key in ("inputs", "output", "resume"):
                    row[key] = json.loads(row[key]) if row[key] else None
                row.pop("token")  # Worker lease tokens are never part of operator read models.
            for row in events:
                row["data"] = json.loads(row["data"])
            return {"run": run, "tasks": tasks, "events": events}
