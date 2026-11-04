"""Offline reconstruction of presentation indexes, never execution authority."""
from acquisition.contracts import Conflict, canonical, digest
from .ports import WorkspaceProjectionStore, WorkspaceProjectionSource

PROJECTION_SCHEMA = 'workspace-projection/v1'


def projection_rows(snapshot):
    """Only positively owned identities may replace existing projection rows."""
    sessions = {s['id']: s for s in snapshot['sessions']}
    result = {name: [] for name in ('sessions', 'commands', 'conversation_draft_requests', 'followup_prepare_requests')}
    for key, session in sorted(sessions.items()):
        if session['parent_id'] is not None:
            parent=sessions.get(session['parent_id'])
            if parent is None or any(parent[k]!=session[k] for k in ('organization','database_scope')):
                raise Conflict('Projection child is missing its original scoped parent')
        result['sessions'].append((key, digest({'projection': key}), canonical(session)))
    for request in snapshot['requests']:
        session = sessions[request['environment_id']]
        inputs = request['inputs']
        if request['environment_organization'] != session['organization']:
            raise Conflict('Projection request differs from its environment scope')
        if request['kind'] == 'conversation':
            plan = session.get('conversation_plan', {})
            expected = {'conversation_id': plan.get('conversation_id'), 'revision': plan.get('revision'), 'plan_id': plan.get('id')}
            if inputs != expected or request['organization'] != 'local-conversations' or request['scope'] != plan.get('conversation_id'):
                raise Conflict('Projection request differs from its original conversation')
            if session['id']!='workspace_'+digest({'conversation_id':inputs['conversation_id'],'plan_id':inputs['plan_id']})[:24]:
                raise Conflict('Projection campaign identity differs from its original conversation request')
            result['conversation_draft_requests'].append((inputs['conversation_id'], request['request_id'], digest(inputs), session['id']))
        elif request['kind'] == 'followup':
            expected = {'parent': session['parent_id'], 'proposal': session.get('followup_id'),
                        'mode': session['mode'], 'allow_model_copy': session['mode'] == 'model'}
            if inputs != expected or request['organization'] != session['organization'] or request['scope'] != 'followup-prepare':
                raise Conflict('Projection request differs from its original experiment')
            if session['id']!='workspace_'+digest({'followup':inputs['proposal']})[:24]:
                raise Conflict('Projection experiment identity differs from its original proposal')
            result['followup_prepare_requests'].append((request['organization'], request['request_id'], digest(inputs), session['id']))
        elif (request['kind'] != 'root' or request['organization'] != session['organization'] or request['scope'] != 'root'
              or inputs != {'mode': session['mode'], 'parent_id': session['parent_id']}
              or session['id']!='workspace_'+digest({'request_id':request['request_id']})[:24]):
            raise Conflict('Unsupported original workspace creation request')
    for command in snapshot['commands']:
        session = sessions[command['environment_id']]
        if command['organization'] != session['organization']:
            raise Conflict('Projection command differs from its environment scope')
        result['commands'].append((session['id'], command['request_id'], digest(command['inputs']), command['done']))
    return {'rows': {table: sorted(rows) for table, rows in result.items()}, 'diagnostics': snapshot['diagnostics']}


class WorkspaceProjectionRebuild:
    def __init__(self, source: WorkspaceProjectionSource, projection: WorkspaceProjectionStore):
        self.source, self.projection = source, projection

    def run(self, *, apply=False, expected_plan=None):
        if type(apply) is not bool:
            raise ValueError('Choose inspection or explicit projection rebuild')
        with self.projection.exclusive():
            snapshot = self.source.projection()
            rows = projection_rows(snapshot)
            inventory = self.projection.inspect(rows)
            plan = digest({'schema': PROJECTION_SCHEMA, 'source': snapshot['fingerprint'], 'projection': inventory['fingerprint']})
            if expected_plan is not None and expected_plan != plan:
                raise Conflict('Projection inspection changed; inspect the current plan before rebuilding')
            result = {'schema': PROJECTION_SCHEMA, 'plan_id': plan, 'source_fingerprint': snapshot['fingerprint'],
                      'execution_policy': 'verified-paused/v1', 'legacy_migration': False,
                      'scope': 'registered-new-format-environments-only',
                      'warnings': ['Legacy-only workspace authority cannot be reconstructed. Keep its original journal; this operation does not migrate or activate it.'],
                      'sessions': sorted(s['id'] for s in snapshot['sessions']),
                      'preparations': len(snapshot['preparations']), 'pending_locations': snapshot['pending_locations'],
                      'stores': snapshot['stores'], **inventory}
            if apply:
                if inventory['blocked']:
                    raise Conflict('Projection rebuild is blocked: ' + '; '.join(inventory['blocked']))
                self.projection.rebuild(rows, inventory['fingerprint'], snapshot['fingerprint'], self.source.projection)
                result |= {'status': 'rebuilt'}
            else:
                result |= {'status': 'blocked' if inventory['blocked'] else 'inspected'}
            return result
