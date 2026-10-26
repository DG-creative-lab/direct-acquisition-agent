import json
import math

from acquisition.contracts import Conflict, canonical
from acquisition.reasoning import CallScope, ModelError
from acquisition.runtime import LeaseLost

from .database import Database
from .tasks import scoped_run


class SqliteCalls:
    def __init__(self, database: Database):
        self.database = database

    def reserve(self, scope: CallScope, key: str, request_hash: str, limit: int, now: float) -> dict | None:
        if not math.isfinite(now):
            raise LeaseLost("Inference requires a finite clock reading")
        with self.database.transaction() as connection:
            run = scoped_run(connection, scope.organization, scope.run_id)
            task = connection.execute("SELECT * FROM tasks WHERE id=? AND run_id=?", (scope.task_id, scope.run_id)).fetchone()
            if (task is None or run["status"] != "running" or task["status"] != "running"
                    or task["token"] != scope.lease_token or task["lease_until"] <= now):
                raise LeaseLost("Inference attempt has no active task lease")
            row = connection.execute("SELECT * FROM model_calls WHERE organization=? AND run_id=? AND call_key=?",
                                     (scope.organization, scope.run_id, key)).fetchone()
            if row:
                if row["request_hash"] != request_hash:
                    raise Conflict("Inference replay has different inputs")
                if row["status"] != "recorded":
                    raise ModelError("previous_inference_failed_or_unknown_no_retry")
                return json.loads(row["response"])
            count = connection.execute("SELECT COUNT(*) FROM model_calls WHERE organization=? AND run_id=?",
                                       (scope.organization, scope.run_id)).fetchone()[0]
            if count >= limit:
                raise ModelError("run_request_budget_exhausted")
            connection.execute("INSERT INTO model_calls VALUES(?,?,?,?,?,?,'reserved',NULL,NULL)",
                               (scope.organization, scope.run_id, key, scope.task_id, scope.lease_token, request_hash))
        return None

    def record(self, scope: CallScope, key: str, response: dict | None, error: str | None) -> None:
        with self.database.transaction() as connection:
            # A late observation may record usage after cancellation; it grants no task authority.
            cursor = connection.execute("""UPDATE model_calls SET status=?,response=?,error=?
                WHERE organization=? AND run_id=? AND call_key=? AND lease_token=? AND status='reserved'""",
                ("rejected" if response is not None and error else "recorded" if response is not None else "unknown",
                 canonical(response) if response is not None else None,
                 error, scope.organization, scope.run_id, key, scope.lease_token))
            if cursor.rowcount != 1:
                raise Conflict("Inference receipt no longer matches its reservation")

    def inspect(self, organization: str, run_id: str) -> list[dict]:
        with self.database.connect() as connection:
            scoped_run(connection, organization, run_id)
            rows = connection.execute("SELECT * FROM model_calls WHERE organization=? AND run_id=? ORDER BY call_key",
                                      (organization, run_id)).fetchall()
        return [{"key": row["call_key"], "status": row["status"], "error": row["error"],
                 "receipt": json.loads(row["response"]) if row["response"] else None} for row in rows]
