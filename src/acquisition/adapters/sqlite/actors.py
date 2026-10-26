"""Shared local-role lookup inside the caller's transaction. Not authentication."""
import json


def require_actor(db, organization, actor, role):
    row = db.execute("SELECT * FROM review_actors WHERE organization=? AND id=?", (organization, actor)).fetchone()
    if row is None or not row["enabled"] or role not in json.loads(row["roles"]):
        raise ValueError("Active local " + role + " identity required in this organization")
    return row
