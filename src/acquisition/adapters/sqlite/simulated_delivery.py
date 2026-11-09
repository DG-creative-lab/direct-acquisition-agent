"""A transaction-bound local provider with a durable draft and result."""

import json

from acquisition.contracts import Conflict, canonical, digest
from acquisition.reviews import DELIVERY_MODE, delivery_summary


class SqliteSimulatedDelivery:
    def __init__(self, db):
        self.db = db

    def _row(self, organization, case_id, approval_id):
        return self.db.execute(
            """SELECT * FROM simulated_deliveries
            WHERE organization=? AND case_id=? AND approval_id=?""",
            (organization, case_id, approval_id),
        ).fetchone()

    def prepare(self, plan, simulation):
        if simulation == "partial" and len(plan["recipient_ids"]) < 2:
            raise ValueError("Partial simulation requires at least two approved recipients")
        keys = (plan["organization"], plan["case_id"], plan["approval_id"])
        binding = digest({"plan": plan, "simulation": simulation})
        identity = "local_dispatch_" + digest(keys)
        row = self._row(*keys)
        if row is None:
            self.db.execute(
                """INSERT INTO simulated_deliveries
                (organization,case_id,approval_id,id,simulation,binding,provider_draft) VALUES(?,?,?,?,?,?,?)""",
                (*keys, identity, simulation, binding, canonical(plan)),
            )
        elif (row["id"], row["simulation"], row["binding"]) != (identity, simulation, binding):
            raise Conflict("Delivery already binds a different approved draft or simulation")
        return identity

    def dispatch(self, plan, simulation, now):
        keys = (plan["organization"], plan["case_id"], plan["approval_id"])
        row = self._row(*keys)
        binding = digest({"plan": plan, "simulation": simulation})
        if row is None or row["binding"] != binding or row["provider_draft"] != canonical(plan):
            raise Conflict("Provider draft differs from the approved recipients or content")
        if row["result"] is not None:
            raise Conflict("Reconcile the original provider result before dispatch")
        intended = plan["recipient_ids"]
        rejected = intended if simulation == "reject" else intended[-1:] if simulation == "partial" else []
        accepted = intended[:len(intended) - len(rejected)]
        status = "partially_accepted" if accepted and rejected else "accepted" if accepted else "rejected"
        result = {
            "id": row["id"], "organization": keys[0], "case_id": keys[1], "approval_id": keys[2],
            "mode": DELIVERY_MODE, "status": status, "intended_recipients": len(intended),
            "control_count": plan["control_count"], "accepted_recipients": len(accepted),
            "rejected_recipients": len(rejected), "accepted_recipient_ids": accepted,
            "rejected_recipient_ids": rejected, "recorded_at": now,
            "sent": None, "delivered": None, "responded": None, "binding": binding,
        }
        self.db.execute(
            """UPDATE simulated_deliveries SET result=?,result_hash=?
            WHERE organization=? AND case_id=? AND approval_id=? AND result IS NULL""",
            (canonical(result), digest(result), *keys),
        )
        return result

    def reconcile(self, organization, case_id, approval_id, simulation=None):
        if self.db.execute('PRAGMA user_version').fetchone()[0] < 16:
            return None  # Historical checkpoints are opened without migration.
        row = self._row(organization, case_id, approval_id)
        if row is None:
            return None
        if simulation is not None and row["simulation"] != simulation:
            raise Conflict("Delivery already binds a different simulation")
        if row["result"] is None:
            return None
        result = json.loads(row["result"])
        keys = (organization, case_id, approval_id)
        if (digest(result) != row["result_hash"]
                or (result["organization"], result["case_id"], result["approval_id"]) != keys
                or result["binding"] != row["binding"]
                or result["id"] != row["id"] or row["id"] != "local_dispatch_" + digest(keys)):
            raise Conflict("Saved provider result failed integrity checks")
        return result

    def inspect(self, organization, case_id, approval_id):
        if self.db.execute('PRAGMA user_version').fetchone()[0] < 16:
            return None
        row = self._row(organization, case_id, approval_id)
        if row is None:
            return None
        if row['result'] is None:
            return {"id": row["id"], "mode": DELIVERY_MODE, "status": "prepared"}
        return self.reconcile(organization, case_id, approval_id)


def require_provider_result(provider, organization, receipt, simulation=None):
    if "delivery" in receipt:
        result = provider.reconcile(organization, receipt["case_id"], receipt["approval_id"], simulation)
        if result is None or delivery_summary(result) != receipt["delivery"]:
            raise Conflict("Acceptance differs from the original provider result")
