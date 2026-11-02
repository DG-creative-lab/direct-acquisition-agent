"""Bind a chat confirmation to a native copy admission in the same transaction."""

import json

from acquisition.contracts import Conflict, NotFound, canonical
from acquisition.conversations import ACTION_CAPABILITY, identity, validate_action, pending_copy_clarification


def _result(db, organization, frozen):
    task = db.execute('''SELECT t.output,t.inputs FROM runs r JOIN tasks t ON t.run_id=r.id
        WHERE r.organization=? AND r.request_id=? AND r.status='succeeded' AND t.status='succeeded' AND t.capability=?''',
        (organization, frozen['run_request_id'], frozen.get('capability', ACTION_CAPABILITY))).fetchone()
    if task is None:raise Conflict('A completed copy-edit proposal is required')
    result = json.loads(task['output'])
    if (result.get('kind') != 'revise_copy' or json.loads(task['inputs']) != frozen
            or validate_action({'action': 'revise_copy'}, frozen) != result):
        raise Conflict('Copy-edit proposal differs from its original task')
    return result


def check_copy_confirmation(db, organization, inputs, revision_request_id, confirmation_request_id):
    reference = inputs['conversation_action']
    if set(reference) != {'organization', 'conversation_id', 'action_id', 'result_id', 'revision'}:
        raise Conflict('Use the exact saved conversation action reference')
    for key in ('organization', 'conversation_id', 'action_id', 'result_id'):
        identity(reference[key])
    identity(confirmation_request_id)
    command = {'kind': 'copy_revision_confirmation', 'reference': reference,
               'revision_request_id': revision_request_id, 'inputs': inputs}
    previous = db.execute('SELECT inputs,receipt FROM conversation_action_commands WHERE organization=? AND request_id=?',
                          (reference['organization'], confirmation_request_id)).fetchone()
    if previous and json.loads(previous['inputs']) != command:
        raise Conflict('Confirmation request already binds different copy inputs')
    row = db.execute('SELECT rowid AS admission_sequence,* FROM conversation_actions WHERE organization=? AND id=? AND conversation_id=? AND revision=?',
                     (reference['organization'], reference['action_id'], reference['conversation_id'], reference['revision'])).fetchone()
    if row is None:raise NotFound('Copy-edit proposal not found in this conversation')
    frozen = json.loads(row['payload'])
    result = _result(db, reference['organization'], frozen)
    proposal = result['copy_revision']
    target = proposal['target']
    if (result['id'] != reference['result_id'] or proposal['status'] != 'ready' or not target
            or target['organization'] != organization or target['case_id'] != inputs['case_id']
            or target['subject_id'] != inputs['expected_subject'] or target['id'] != inputs['target_id']
            or proposal['feedback'] != inputs['feedback'] or inputs['allow_model_copy'] is not True):
        raise Conflict('Copy confirmation differs from the exact displayed target and feedback')
    confirmed = json.loads(row['confirmed']) if row['confirmed'] else None
    if confirmed is None:
        source = db.execute('SELECT revision FROM conversations WHERE organization=? AND id=?',
                            (reference['organization'], reference['conversation_id'])).fetchone()
        if source is None or source['revision'] != reference['revision']:
            raise Conflict('The copy-edit proposal belongs to an earlier brief')
        sequence = None
        for entry in proposal['messages'][:-1]:
            parent = db.execute('SELECT rowid AS admission_sequence,* FROM conversation_actions WHERE organization=? AND id=? AND conversation_id=? AND revision=?',
                (reference['organization'], entry['action_id'], reference['conversation_id'], reference['revision'])).fetchone()
            if (parent is None or parent['confirmed'] or parent['admission_sequence'] >= row['admission_sequence']
                    or (sequence is not None and parent['admission_sequence'] <= sequence)):
                raise Conflict('Copy clarification differs from its scoped admission order')
            sequence = parent['admission_sequence']
            parent_frozen = json.loads(parent['payload'])
            parent_target = parent_frozen['context']['copy_revision_targets']
            if (parent_target.get('subject_id') != target['subject_id']
                    or parent_target.get('session_id') != target['session_id']):
                raise Conflict('Copy clarification belongs to another draft')
            parent_result = _result(db, reference['organization'], parent_frozen)
            parent_proposal=parent_result['copy_revision']
            if not pending_copy_clarification(parent_proposal):
                legacy_same_target=(frozen['context']['dialogue'].get('version')=='routing-dialogue/v3'
                                    and parent_proposal['status']=='ready' and parent_proposal['target']
                                    and parent_proposal['target']['id']==target['id'])
                if not legacy_same_target:
                    raise Conflict('This saved edit carries an unrelated or invalid earlier proposal. Request a new copy edit.')
            expected = {'action_id': entry['action_id'], 'content': parent_frozen['inputs']['content'],
                        'response': {k: parent_result[k] for k in ('id', 'kind', 'text')}}
            if entry != expected:raise Conflict('Copy clarification differs from its exact saved exchange')
    return {'row': row, 'reference': reference, 'command': command, 'previous': previous,
            'confirmed': confirmed, 'target': target, 'confirmation_request_id': confirmation_request_id}


def record_copy_confirmation(db, checked, receipt, now):
    target, reference = checked['target'], checked['reference']
    if checked['confirmed']:
        confirmation = checked['confirmed']
        if (confirmation.get('kind') != 'copy_revision_confirmation' or confirmation['revision_id'] != receipt['id']
                or confirmation['revision_request_id'] != receipt['request_id']):
            raise Conflict('Saved confirmation refers to another copy admission')
    else:
        confirmation = {'kind': 'copy_revision_confirmation', 'action_id': reference['action_id'],
            'result_id': reference['result_id'], 'conversation_id': reference['conversation_id'],
            'revision': reference['revision'], 'session_id': target['session_id'], 'organization': target['organization'],
            'case_id': target['case_id'], 'base_subject_id': target['subject_id'], 'target_id': target['id'],
            'revision_id': receipt['id'], 'revision_request_id': receipt['request_id'], 'confirmed_at': now}
        db.execute('UPDATE conversation_actions SET confirmed=? WHERE organization=? AND id=?',
                   (canonical(confirmation), reference['organization'], reference['action_id']))
    if checked['previous']:
        if json.loads(checked['previous']['receipt']) != confirmation:
            raise Conflict('Saved copy confirmation receipt differs from its original effect')
    else:
        db.execute('INSERT INTO conversation_action_commands VALUES(?,?,?,?)',
                   (reference['organization'], checked['confirmation_request_id'], canonical(checked['command']), canonical(confirmation)))
