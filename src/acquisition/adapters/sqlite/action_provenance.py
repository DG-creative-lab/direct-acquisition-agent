"""A routing reservation must belong to its exact durable user admission."""
import json
from acquisition.contracts import Conflict, canonical


def require_action_admission(db, organization, inputs, run):
    row=db.execute('SELECT payload FROM conversation_actions WHERE organization=? AND id=?',
                   (organization,inputs.get('id'))).fetchone()
    admitted=json.loads(row[0]) if row else None
    if (admitted is None or admitted.get('alias') is not None or canonical(admitted)!=canonical(inputs)
            or run['request_id']!=admitted['run_request_id']):
        raise Conflict('Routing inference requires its original scoped action admission')
