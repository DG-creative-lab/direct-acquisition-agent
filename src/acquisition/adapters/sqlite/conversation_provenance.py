"""Check local conversation authority inside the caller's write transaction."""

from acquisition.contracts import Conflict


def require_current_conversation(connection, brief):
    if "conversation_id" not in brief:
        return
    row = connection.execute("SELECT revision FROM conversations WHERE organization=? AND id=?",
                             ("local-conversations", brief["conversation_id"])).fetchone()
    if row is None or row[0] != brief["conversation_revision"]:
        raise Conflict("Conversation changed before campaign generation completed")
