from .followups import require_followup
import json
import math

from acquisition.contracts import Conflict, canonical
from acquisition.reasoning import CallScope, ModelError
from acquisition.runtime import LeaseLost

from .database import Database
from .tasks import scoped_run
from .conversation_provenance import require_current_conversation
from .revision_provenance import require_revision_current


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
            inputs = json.loads(task["inputs"])
            if inputs.get("workflow_version") == "copy-revision/v3":
                try:
                    require_revision_current(connection, scope.organization, inputs, scope.run_id, now)
                except (Conflict, ValueError):
                    raise ModelError("copy_revision_source_changed") from None
            if task["capability"] == "conversations.plan.v1":
                source = connection.execute("SELECT revision FROM conversations WHERE organization=? AND id=?",
                                            (scope.organization, inputs["conversation_id"])).fetchone()
                if source is None or source[0] != inputs["revision"]:
                    raise ModelError("conversation_changed_before_inference")
            if inputs.get("workflow_version") == "conversation-model-mail/v3":
                try:
                    require_current_conversation(connection, inputs["brief"])
                except Conflict:
                    raise ModelError("conversation_changed_before_inference") from None
            row = connection.execute("SELECT * FROM model_calls WHERE organization=? AND run_id=? AND call_key=?",
                                     (scope.organization, scope.run_id, key)).fetchone()
            if row:
                if row["request_hash"] != request_hash:
                    raise Conflict("Inference replay has different inputs")
                if row["status"] != "recorded":
                    raise ModelError("previous_inference_failed_or_unknown_no_retry")
                return json.loads(row["response"])
            task_inputs = json.loads(task["inputs"])
            require_followup(connection, scope.organization, task_inputs)
            if task_inputs.get("brief",{}).get("followup_id") and "context_ids" in task_inputs and run["request_id"] != task_inputs["brief"]["campaign_id"]:
                raise ModelError("followup_run_identity_changed")
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
