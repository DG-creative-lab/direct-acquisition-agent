"""Check local conversation authority inside the caller's write transaction."""

import json
from dataclasses import asdict

from acquisition.contracts import Conflict
from acquisition.campaigns import CampaignScope, validate_requested_scope
from acquisition.conversations import requested_scope, bind_requested_scope, validate_result
from .execution import require_active


_UNSET = object()


def require_current_conversation(connection, brief, campaign_scope=_UNSET):
    if "conversation_id" not in brief:
        return
    row = connection.execute("SELECT revision FROM conversations WHERE organization=? AND id=?",
                             ("local-conversations", brief["conversation_id"])).fetchone()
    if row is None or row[0] != brief["conversation_revision"]:
        raise Conflict("Conversation changed before campaign generation completed")
    require_active(connection, 'local-conversations', brief['conversation_id'], brief['conversation_revision'])
    require_requested_scope(connection, brief, campaign_scope)


def require_requested_scope(connection, brief, campaign_scope=_UNSET):
    if 'conversation_id' not in brief:
        return
    from .conversations import messages
    owner = 'local-conversations'
    row = connection.execute('SELECT payload FROM conversation_plans WHERE organization=? AND conversation_id=? AND revision=?',
                             (owner, brief['conversation_id'], brief['conversation_revision'])).fetchone()
    if row is None:
        raise Conflict('Original conversation plan is unavailable for scope verification')
    frozen = json.loads(row[0])
    original = connection.execute('SELECT t.inputs,t.output,t.status,r.status AS run_status FROM tasks t JOIN runs r ON r.id=t.run_id '
                                  'WHERE r.organization=? AND r.request_id=? AND t.position=0',
                                  (owner, frozen['run_request_id'])).fetchone()
    if original is None or json.loads(original[0]).get('requested_scope') != frozen.get('requested_scope'):
        raise Conflict('Requested scope differs from its original planning task')
    scope = frozen.get('requested_scope')
    if scope != brief.get('requested_scope'):
        raise Conflict('Campaign dropped or substituted its requested scope')
    current_revision = connection.execute('SELECT revision FROM conversations WHERE organization=? AND id=?',
                                           (owner, brief['conversation_id'])).fetchone()
    if current_revision is None or current_revision[0] != brief['conversation_revision']:
        raise Conflict('Conversation changed after its requested scope was frozen')
    if scope is None:
        # Preserve old bytes and IDs, but never grant fresh authority for a
        # historically substituted unsupported request. Receipt replay is earlier.
        current = [m for m in messages(connection, owner, brief['conversation_id'])
                   if m['revision'] <= brief['conversation_revision']]
        for source in (frozen['messages'], current):
            if requested_scope(owner, brief['conversation_id'], brief['conversation_revision'], source)['status'] != 'supported':
                raise Conflict('Historical request requires a supported scope before new campaign effects')
        return
    try:
        bind_requested_scope(frozen, owner)
        validate_requested_scope(scope)
        result = json.loads(original['output'] or 'null')
        fields = ('outcome', 'objective', 'budget_pence', 'segments', 'copy_mode', 'question', 'assumptions', 'unsupported_reason')
        if (original['status'] != 'succeeded' or original['run_status'] != 'succeeded' or not result
                or result['id'] != brief['plan_id'] or result['outcome'] != 'brief_proposal'
                or result['budget_pence'] != brief['budget_pence'] or result['segments'] != list(brief['segments'])
                or validate_result({k: result[k] for k in fields}, frozen, owner) != result):
            raise ValueError('Campaign differs from its scoped planning result')
    except (KeyError, ValueError, TypeError) as error:
        raise Conflict('Requested campaign scope is invalid') from error
    current = messages(connection, owner, brief['conversation_id'])
    current = [m for m in current if m['revision'] <= brief['conversation_revision']]
    if requested_scope(owner, brief['conversation_id'], brief['conversation_revision'], current) != scope:
        raise Conflict('Requested scope source messages changed')
    if campaign_scope is not _UNSET and campaign_scope != asdict(CampaignScope()):
        raise Conflict('Delivered product, channel, country or objective differs from requested scope')


def require_inherited_scope(connection, scope):
    """A follow-up retains its original requested scope, never new authority."""
    row = connection.execute('SELECT t.output FROM conversation_plans p JOIN runs r '
        "ON r.organization=p.organization AND r.request_id=json_extract(p.payload,'$.run_request_id') "
        'JOIN tasks t ON t.run_id=r.id AND t.position=0 WHERE p.organization=? AND p.conversation_id=? AND p.revision=?',
        ('local-conversations', scope['conversation_id'], scope['revision'])).fetchone()
    result = json.loads(row[0] or 'null') if row else None
    if not result:
        raise Conflict('Inherited requested scope has no original planning result')
    brief = {'conversation_id': scope['conversation_id'], 'conversation_revision': scope['revision'],
             'plan_id': result['id'], 'budget_pence': result['budget_pence'], 'segments': result['segments'], 'requested_scope': scope}
    require_requested_scope(connection, brief, asdict(CampaignScope()))
