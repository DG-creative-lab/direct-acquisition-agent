"""Shared inference accounting and stop fences in the authoritative domain DB."""

import json
from decimal import Decimal

from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import EXECUTION_POLICY, CONVERSATION_CALL_LIMIT
from acquisition.reasoning import ModelError
from .workspace_ancestry import workspace_ancestry_guard, workspace_ancestry, verify_workspace_binding, pre_history_binding


DEFINITIVE_REJECTIONS = frozenset({'provider_http_400', 'provider_http_401', 'provider_http_403',
                                 'provider_http_404', 'provider_http_422'})
DESCENDANT_PREFIX = 'descendant:'
INDEPENDENT_PREFIX = 'independent:'
RESOLUTION_PREFIX = 'resolution:'
REVIEW_CHECKPOINTS = frozenset({'campaigns.review_checkpoint.v1','campaigns.review_conversation.v1',
    'campaigns.model_review_checkpoint.v2','campaigns.model_review_checkpoint.v3',
    'campaigns.model_review_checkpoint_conversation.v3'})


def descendant_parent(db, organization, campaign_id):
    row = db.execute('SELECT inputs,receipt FROM execution_commands WHERE organization=? AND request_id=?',
                     (organization,DESCENDANT_PREFIX+campaign_id)).fetchone()
    if row is None:
        return None
    inputs,receipt=json.loads(row['inputs']),json.loads(row['receipt'])
    if inputs.get('kind')!='descendant_admission' or inputs.get('campaign_id')!=campaign_id or receipt!=inputs:
        raise Conflict('Descendant execution ancestry differs from its original admission')
    parent=db.execute('SELECT id FROM runs WHERE organization=? AND id=?',
                      (organization,inputs['parent_run_id'])).fetchone()
    if parent is None:
        raise Conflict('Descendant parent run is unavailable in this organization')
    return parent[0]


def campaign_parent(db, organization, campaign_id, run_id=None):
    """CLI --campaign-id references the original scoped campaign admission."""
    parent=db.execute('SELECT id FROM runs WHERE organization=? AND request_id=?',
                      (organization,campaign_id)).fetchone()
    if parent is None or parent[0]==run_id:
        return None
    # A coincidental request key (for example a planner request) is not a
    # campaign reference. Require the original admission's frozen brief too.
    campaigns={json.loads(t[0]).get('brief',{}).get('campaign_id') for t in
               db.execute('SELECT inputs FROM tasks WHERE run_id=?',(parent[0],))}
    return parent[0] if campaigns=={campaign_id} else None


def independent_resolution(db, organization, run_id):
    from .database import stored_plan_hash
    row=db.execute('SELECT inputs,receipt FROM execution_commands WHERE organization=? AND request_id=?',
                   (organization,INDEPENDENT_PREFIX+run_id)).fetchone()
    if row is None:
        return None
    if not pre_history_binding(db,organization):
        return None  # Preserve a historical weak receipt without treating it as permission.
    inputs,receipt=json.loads(row['inputs']),json.loads(row['receipt'])
    run=db.execute('SELECT request_hash FROM runs WHERE organization=? AND id=?',(organization,run_id)).fetchone()
    if (receipt.get('kind')!='independent_execution_resolution' or receipt.get('inputs')!=inputs
            or inputs.get('run_id')!=run_id or run is None or receipt.get('request_hash')!=run[0]
            or stored_plan_hash(db,run_id)!=run[0]):
        raise Conflict('Independent execution resolution differs from its original run')
    return receipt


def origin_inspection(db, organization, run_id, guard):
    from .tasks import scoped_run
    from .database import stored_plan_hash
    run=scoped_run(db,organization,run_id)
    journal_id=verify_workspace_binding(db,organization,guard)
    if stored_plan_hash(db,run_id)!=run['request_hash']:
        raise Conflict('Restore the original admitted task inputs before resolving ancestry')
    calls=[dict(r) for r in db.execute('SELECT * FROM model_calls WHERE organization=? AND run_id=? ORDER BY rowid',
                                      (organization,run_id))]
    tasks=[dict(r) for r in db.execute('SELECT * FROM tasks WHERE run_id=? ORDER BY position',(run_id,))]
    ancestry=workspace_ancestry(guard,organization,run,tasks)
    fingerprint=digest({'run':dict(run),'tasks':tasks,'calls':calls,'workspace_ancestry':ancestry,'journal_id':journal_id})
    return {'organization':organization,'run_id':run_id,'request_id':run['request_id'],
            'request_hash':run['request_hash'],'status':run['status'],'known_calls':len(calls),
            'fingerprint':fingerprint,'journal_id':journal_id,'workspace_ancestry':ancestry,'campaign_ids':sorted({json.loads(t['inputs']).get('brief',{}).get('campaign_id')
                for t in tasks if json.loads(t['inputs']).get('brief',{}).get('campaign_id')})}


def reached_review_checkpoint(db, organization, run_id):
    task=db.execute('''SELECT * FROM tasks WHERE run_id=? AND status='waiting'
        AND position=(SELECT MAX(position) FROM tasks WHERE run_id=?)''',(run_id,run_id)).fetchone()
    if task is None or task['capability'] not in REVIEW_CHECKPOINTS:
        return False
    if db.execute("SELECT 1 FROM tasks WHERE run_id=? AND position<? AND status!='succeeded'",(run_id,task['position'])).fetchone():
        return False
    output=json.loads(task['output'] or '{}')
    return (output.get('release_authority') is False and output.get('draft_id')
        and output.get('reference')==output['draft_id'] and db.execute(
            'SELECT 1 FROM drafts WHERE organization=? AND id=?',(organization,output['draft_id'])).fetchone() is not None)


def account(db, organization, conversation_id):
    source = db.execute('SELECT revision FROM conversations WHERE organization=? AND id=?',
                        (organization, conversation_id)).fetchone()
    if source is None:
        raise NotFound('Conversation not found in this organization')
    db.execute('INSERT OR IGNORE INTO conversation_execution VALUES(?,?,?,?,0)',
               (organization, conversation_id, EXECUTION_POLICY, CONVERSATION_CALL_LIMIT))
    row = db.execute('SELECT * FROM conversation_execution WHERE organization=? AND conversation_id=?',
                     (organization, conversation_id)).fetchone()
    if row['policy'] != EXECUTION_POLICY:
        raise Conflict('Restore the original execution policy before continuing')
    return row


def run_origin(db, organization, run_id, ancestors=(), memo=None):
    """Resolve original scoped provenance, never a browser-supplied account ID."""
    if run_id in ancestors or len(ancestors) >= 10:
        raise Conflict('Execution ancestry is cyclic or too deep')
    memo = {} if memo is None else memo
    if (organization, run_id) in memo:
        return memo[organization, run_id]
    origins = set()
    for row in db.execute('SELECT capability,inputs FROM tasks WHERE run_id=?', (run_id,)):
        inputs = json.loads(row['inputs'])
        if row['capability'] in {'conversations.plan.v1', 'conversations.fixture_plan.v1'}:
            origin = (organization, inputs['conversation_id'], inputs['revision'])
        elif row['capability'] in {'conversations.route.v1', 'conversations.route.v2'}:
            origin = (organization, inputs['inputs']['conversation_id'], inputs['inputs']['revision'])
        elif inputs.get('brief', {}).get('conversation_id'):
            brief = inputs['brief']
            origin = ('local-conversations', brief['conversation_id'], brief['conversation_revision'])
        elif inputs.get('brief', {}).get('followup_id'):
            proposal = db.execute('SELECT receipt FROM review_commands WHERE organization=? AND request_id=?',
                                  (organization, inputs['brief']['followup_id'])).fetchone()
            parent = db.execute('SELECT id FROM runs WHERE organization=? AND request_id=?',
                                (organization, json.loads(proposal[0])['parent_id'])).fetchone() if proposal else None
            origin = run_origin(db, organization, parent[0], ancestors+(run_id,), memo) if parent else None
            if origin is None:
                continue
        elif inputs.get('brief',{}).get('campaign_id'):
            parent=descendant_parent(db,organization,inputs['brief']['campaign_id'])
            if parent is None:
                parent=campaign_parent(db,organization,inputs['brief']['campaign_id'],run_id)
            origin=run_origin(db,organization,parent,ancestors+(run_id,),memo) if parent else None
            if origin is None:
                continue
        else:
            continue
        origins.add(origin)
    if len(origins) > 1:
        raise Conflict('A run cannot consume multiple conversation allowances')
    origin = next(iter(origins), None)
    memo[organization, run_id] = origin
    return origin


def bind_run(db, organization, run_id, *, historical=False):
    origin = run_origin(db, organization, run_id)
    old = db.execute('SELECT owner_organization,conversation_id,revision FROM execution_runs WHERE organization=? AND run_id=?',
                     (organization, run_id)).fetchone()
    if independent_resolution(db,organization,run_id):
        if origin is not None or old:
            raise Conflict('An independently resolved run cannot acquire a conversation parent')
        return None
    if old and tuple(old) != origin:
        raise Conflict('Execution scope differs from the original run admission')
    if origin is None:
        return None
    owner, conversation_id, revision = origin
    a = account(db, owner, conversation_id)
    if not historical and revision <= a['stopped_through']:
        raise ModelError('conversation_execution_cancelled')
    if old is None:
        db.execute('INSERT INTO execution_runs VALUES(?,?,?,?,?)',
                   (organization, run_id, owner, conversation_id, revision))
    # Schema-v9 backfill precedes creation of this table during an upgrade.
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='execution_pending_origins' AND type='table'").fetchone():
        db.execute('DELETE FROM execution_pending_origins WHERE organization=? AND run_id=?',(organization,run_id))
    return a


def unresolved_scopes(db, owner, conversation_id):
    return [dict(r) for r in db.execute('''SELECT DISTINCT p.organization,p.run_id FROM execution_pending_origins p
        JOIN execution_runs e ON e.organization=p.organization
        WHERE e.owner_organization=? AND e.conversation_id=?''',(owner,conversation_id))]


def unresolved_runs(db, owner, conversation_id):
    return [r['run_id'] for r in unresolved_scopes(db,owner,conversation_id)]


def ancestry_pending(db, organization, run_id):
    if db.execute('SELECT 1 FROM execution_pending_origins WHERE organization=? AND run_id=?',(organization,run_id)).fetchone():
        return True
    link=db.execute('SELECT owner_organization,conversation_id FROM execution_runs WHERE organization=? AND run_id=?',
                    (organization,run_id)).fetchone()
    return bool(link and unresolved_runs(db,*link))


def require_resolved_ancestry(db, organization, run_id):
    if ancestry_pending(db,organization,run_id):
        raise ModelError('conversation_ancestry_recovery_required')


def require_active(db, owner, conversation_id, revision):
    row = db.execute('SELECT stopped_through FROM conversation_execution WHERE organization=? AND conversation_id=?',
                     (owner, conversation_id)).fetchone()
    if row and revision <= row[0]:
        raise Conflict('This brief was stopped. Send a new brief to start new work; the shared allowance does not reset.')


def require_brief_active(db, organization, brief):
    if brief.get('conversation_id'):
        require_active(db, 'local-conversations', brief['conversation_id'], brief['conversation_revision'])
    elif brief.get('followup_id'):
        proposal = db.execute('SELECT receipt FROM review_commands WHERE organization=? AND request_id=?',
                              (organization, brief['followup_id'])).fetchone()
        parent = db.execute('SELECT id FROM runs WHERE organization=? AND request_id=?',
                            (organization, json.loads(proposal[0])['parent_id'])).fetchone() if proposal else None
        origin = run_origin(db, organization, parent[0]) if parent else None
        if origin:
            require_active(db, *origin)
    elif brief.get('campaign_id'):
        parent=descendant_parent(db,organization,brief['campaign_id'])
        if parent is None:
            parent=campaign_parent(db,organization,brief['campaign_id'])
        origin=run_origin(db,organization,parent) if parent else None
        if origin:
            require_active(db,*origin)


def reserve_execution(db, scope):
    require_resolved_ancestry(db,scope.organization,scope.run_id)
    a = bind_run(db, scope.organization, scope.run_id)
    if a is None:
        return
    count = db.execute('''SELECT COUNT(*) FROM model_calls c JOIN execution_runs e
        ON c.organization=e.organization AND c.run_id=e.run_id
        WHERE e.owner_organization=? AND e.conversation_id=?''',
        (a['organization'], a['conversation_id'])).fetchone()[0]
    if count >= a['call_limit']:
        raise ModelError('conversation_request_budget_exhausted')


def backfill_execution(db):
    for run in db.execute('SELECT organization,id FROM runs').fetchall():
        bind_run(db, run['organization'], run['id'], historical=True)


def quarantine_old_origins(db):
    """No inference may classify an ambiguous old run by missing metadata."""
    backfill_execution(db)
    for run in db.execute('''SELECT r.organization,r.id FROM runs r WHERE NOT EXISTS
        (SELECT 1 FROM execution_runs e WHERE e.organization=r.organization AND e.run_id=r.id)
        AND EXISTS (SELECT 1 FROM execution_runs e WHERE e.organization=r.organization)''').fetchall():
        if not independent_resolution(db,run['organization'],run['id']) and any(json.loads(t[0]).get('brief',{}).get('campaign_id') for t in db.execute('SELECT inputs FROM tasks WHERE run_id=?',(run['id'],))):
            db.execute('INSERT OR IGNORE INTO execution_pending_origins VALUES(?,?)',(run['organization'],run['id']))


def recover_pending_origins(db):
    """Reconcile an already-upgraded journal using only durable provenance."""
    for row in db.execute("SELECT organization,request_id,inputs FROM execution_commands WHERE request_id LIKE 'independent:%'").fetchall():
        if pre_history_binding(db,row['organization']):
            continue
        inputs=json.loads(row['inputs']);run_id=inputs.get('run_id')
        if row['request_id']!=INDEPENDENT_PREFIX+str(run_id):
            continue
        if db.execute('''SELECT 1 FROM runs r WHERE organization=? AND id=? AND NOT EXISTS
            (SELECT 1 FROM execution_runs e WHERE e.organization=r.organization AND e.run_id=r.id)''',
            (row['organization'],run_id)).fetchone():
            db.execute('INSERT OR IGNORE INTO execution_pending_origins VALUES(?,?)',(row['organization'],run_id))
    for run in db.execute('SELECT organization,run_id FROM execution_pending_origins').fetchall():
        # Keep one conflicting history quarantined without preventing recovery
        # of another campaign. No requests, receipts or artifact bytes change.
        db.execute('SAVEPOINT recover_execution_origin')
        try:
            bind_run(db,run['organization'],run['run_id'],historical=True)
        except (Conflict,NotFound):
            db.execute('ROLLBACK TO recover_execution_origin')
        finally:
            db.execute('RELEASE recover_execution_origin')


class SqliteExecution:
    def __init__(self, database):
        self.database = database

    def for_run(self, organization, run_id):
        with self.database.connect() as db:
            row = db.execute('SELECT owner_organization,conversation_id,revision FROM execution_runs WHERE organization=? AND run_id=?',
                             (organization, run_id)).fetchone()
        return self.view(row['owner_organization'],row['conversation_id']) | {'run_revision':row['revision']} if row else None

    def pending(self, organization, run_id):
        with self.database.connect() as db:
            return ancestry_pending(db,organization,run_id)

    def unresolved(self, organization):
        with self.database.connect() as db:
            if db.execute('SELECT 1 FROM execution_pending_origins WHERE organization=? LIMIT 1',(organization,)).fetchone() is None:
                return []
        with workspace_ancestry_guard(self.database.path) as guard, self.database.transaction() as db:
            return [origin_inspection(db,organization,r[0],guard) for r in db.execute(
                'SELECT run_id FROM execution_pending_origins WHERE organization=? ORDER BY rowid',(organization,)).fetchall()]

    def resolve_independent(self, organization, request_id, inputs, now):
        from .actors import require_actor
        from .tasks import finite_time, event, scoped_run
        finite_time(now)
        key=RESOLUTION_PREFIX+request_id
        # Exact replay observes historical work and needs no current authority.
        with self.database.connect() as db:
            prior=db.execute('SELECT inputs,receipt FROM execution_commands WHERE organization=? AND request_id=?',(organization,key)).fetchone()
            if prior:
                if json.loads(prior['inputs'])!=inputs:
                    raise Conflict('Resolution request already binds different inputs')
                return json.loads(prior['receipt'])
        with workspace_ancestry_guard(self.database.path) as guard, self.database.transaction() as db:
            # A competing request may have committed while the locks were held.
            prior=db.execute('SELECT inputs,receipt FROM execution_commands WHERE organization=? AND request_id=?',(organization,key)).fetchone()
            if prior:
                if json.loads(prior['inputs'])!=inputs:
                    raise Conflict('Resolution request already binds different inputs')
                return json.loads(prior['receipt'])
            run_id=inputs['run_id']
            scoped_run(db,organization,run_id)
            previous=independent_resolution(db,organization,run_id)
            if previous:
                if previous['inputs']!=inputs:
                    raise Conflict('This run already has an immutable independent resolution')
                db.execute('INSERT INTO execution_commands VALUES(?,?,?,?)',(organization,key,canonical(inputs),canonical(previous)))
                return previous
            actor=require_actor(db,organization,inputs['actor'],'operator')
            if db.execute('SELECT 1 FROM execution_pending_origins WHERE organization=? AND run_id=?',(organization,run_id)).fetchone() is None:
                raise Conflict('Only a quarantined legacy run can be resolved independently')
            inspected=origin_inspection(db,organization,run_id,guard)
            if any(r.get('parent_id') or r.get('followup_id') or r.get('conversation_plan') for r in inspected['workspace_ancestry']):
                raise Conflict('Workspace ancestry records a campaign relationship. Restore that relationship instead of declaring independence')
            if inspected['fingerprint']!=inputs['fingerprint']:
                raise Conflict('The run changed. Inspect it again before resolving ancestry')
            if (run_origin(db,organization,run_id) is not None or db.execute(
                    'SELECT 1 FROM execution_runs WHERE organization=? AND run_id=?',(organization,run_id)).fetchone()):
                raise Conflict('A proven conversation origin cannot be resolved as independent')
            if db.execute("SELECT 1 FROM tasks WHERE run_id=? AND status='running'",(run_id,)).fetchone():
                raise Conflict('Stop or finish the active run before resolving ancestry')
            receipt={'kind':'independent_execution_resolution','inputs':inputs,'request_hash':inspected['request_hash'],
                     'known_calls':inspected['known_calls'],'actor_generation':actor['generation'],'at':now}
            for command_key in (key,INDEPENDENT_PREFIX+run_id):
                db.execute('INSERT INTO execution_commands VALUES(?,?,?,?)',(organization,command_key,canonical(inputs),canonical(receipt)))
            db.execute('DELETE FROM execution_pending_origins WHERE organization=? AND run_id=?',(organization,run_id))
            event(db,run_id,None,'execution_origin_resolved',receipt,now)
            return receipt

    def descendant(self, organization, campaign_id, parent_run_id):
        inputs={'kind':'descendant_admission','campaign_id':campaign_id,'parent_run_id':parent_run_id}
        with self.database.transaction() as db:
            previous=descendant_parent(db,organization,campaign_id)
            if previous is not None and previous!=parent_run_id:
                raise Conflict('Campaign already binds another execution parent')
            if db.execute('SELECT 1 FROM runs WHERE organization=? AND id=?',(organization,parent_run_id)).fetchone() is None:
                raise NotFound('Parent run not found in this organization')
            if previous is None:
                db.execute('INSERT INTO execution_commands VALUES(?,?,?,?)',
                    (organization,DESCENDANT_PREFIX+campaign_id,canonical(inputs),canonical(inputs)))
            # Old runs may predate execution ancestry. Attach their existing journals
            # without rewriting requests, artifact bytes or provider receipts.
            run=db.execute('SELECT id FROM runs WHERE organization=? AND request_id=?',(organization,campaign_id)).fetchone()
            if run:
                bind_run(db,organization,run[0],historical=True)
            for row in db.execute('SELECT id FROM runs WHERE organization=?',(organization,)).fetchall():
                bind_run(db,organization,row[0],historical=True)
        return inputs

    def stopped_checkpoints(self, organization):
        with self.database.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT receipt FROM execution_commands WHERE organization=? ORDER BY rowid',(organization,))
                    if json.loads(r[0]).get('kind')=='execution_stopped' and json.loads(r[0]).get('checkpoint_runs')]

    def view(self, organization, conversation_id):
        with self.database.transaction() as db:
            a = account(db, organization, conversation_id)
            revision = db.execute('SELECT revision FROM conversations WHERE organization=? AND id=?',
                                  (organization, conversation_id)).fetchone()[0]
            rows = db.execute('''SELECT c.*,r.status AS run_status,e.revision,t.capability FROM execution_runs e
                JOIN runs r ON r.id=e.run_id AND r.organization=e.organization
                JOIN model_calls c ON c.organization=e.organization AND c.run_id=e.run_id
                JOIN tasks t ON t.id=c.task_id AND t.run_id=c.run_id
                WHERE e.owner_organization=? AND e.conversation_id=? ORDER BY c.rowid''',
                (organization, conversation_id)).fetchall()
            active = db.execute('''SELECT r.id,r.status,e.revision FROM execution_runs e JOIN runs r
                ON r.organization=e.organization AND r.id=e.run_id
                WHERE e.owner_organization=? AND e.conversation_id=? AND r.status IN ('queued','running')''',
                (organization, conversation_id)).fetchall()
            scopes=unresolved_scopes(db,organization,conversation_id)
            unresolved=[r['run_id'] for r in scopes]
        calls, cost, reported = [], Decimal(0), 0
        for row in rows:
            status = row['status']
            outcome = ('in_progress' if status == 'reserved' and row['run_status'] == 'running' else
                       'uncertain' if status == 'reserved' or (status == 'unknown' and row['error'] not in DEFINITIVE_REJECTIONS) else
                       'rejected' if status in {'unknown', 'rejected'} else 'completed')
            receipt = json.loads(row['response']) if row['response'] else {}
            usage = receipt.get('usage', {})
            value = usage.get('cost')
            if type(value) in {int, float}:
                amount = Decimal(str(value))
                if amount.is_finite() and amount >= 0:
                    cost += amount
                    reported += 1
            calls.append({'run_id':row['run_id'], 'key':row['call_key'], 'capability':row['capability'],
                          'revision':row['revision'], 'status':outcome})
        counts = {s:sum(c['status'] == s for c in calls) for s in ('in_progress', 'uncertain', 'rejected', 'completed')}
        stopped = revision > 0 and revision <= a['stopped_through']
        return {'policy':a['policy'], 'limit':a['call_limit'], 'used':len(calls),
                'accounting_complete':not unresolved,'unresolved_runs':unresolved,
                'recovery_scopes':scopes,
                'remaining':None if unresolved else max(0, a['call_limit']-len(calls)), 'counts':counts,
                'stopped':stopped, 'stopped_through':a['stopped_through'], 'calls':calls,
                'active_runs':[dict(r) for r in active],
                'status':'cancelled' if stopped else 'blocked' if unresolved else 'budget_exhausted' if len(calls)>=a['call_limit'] else
                         'running' if active else 'uncertain' if counts['uncertain'] else 'idle',
                'reported_cost_usd':str(cost), 'cost_reported_calls':reported,
                'pending_receipts':sum(r['status']=='reserved' for r in rows),
                'cost_complete':not unresolved and reported == len(calls), 'billing_verified':False}

    def stop(self, organization, conversation_id, request_id, revision, now):
        from .tasks import finite_time, event
        finite_time(now)
        inputs = {'conversation_id':conversation_id, 'revision':revision}
        with self.database.transaction() as db:
            a = account(db, organization, conversation_id)
            previous = db.execute('SELECT inputs,receipt FROM execution_commands WHERE organization=? AND request_id=?',
                                  (organization, request_id)).fetchone()
            if previous:
                if json.loads(previous['inputs']) != inputs:
                    raise Conflict('Stop request already binds different inputs')
                return json.loads(previous['receipt'])
            if request_id.startswith((DESCENDANT_PREFIX,INDEPENDENT_PREFIX,RESOLUTION_PREFIX,'workspace:')):
                raise ValueError('Use a stop request identity outside the internal execution namespaces')
            current = db.execute('SELECT revision FROM conversations WHERE organization=? AND id=?',
                                 (organization, conversation_id)).fetchone()[0]
            if current != revision:
                raise Conflict('The brief changed. Stop the exact displayed revision.')
            db.execute('UPDATE conversation_execution SET stopped_through=MAX(stopped_through,?) WHERE organization=? AND conversation_id=?',
                       (revision, organization, conversation_id))
            runs = db.execute('''SELECT r.id,r.organization,r.status FROM execution_runs e JOIN runs r ON r.id=e.run_id AND r.organization=e.organization
                WHERE e.owner_organization=? AND e.conversation_id=? AND e.revision<=?
                AND r.status IN ('queued','running','waiting')''',
                (organization, conversation_id, revision)).fetchall()
            checkpoints=[];cancelled=[]
            for row in runs:
                if row['status']=='waiting' and reached_review_checkpoint(db,row['organization'],row['id']):
                    checkpoints.append({'organization':row['organization'],'run_id':row['id']})
                    continue
                db.execute("UPDATE runs SET status='cancelled' WHERE id=?", (row['id'],))
                db.execute("UPDATE tasks SET status='cancelled',token=NULL,lease_until=NULL WHERE run_id=? AND status IN ('queued','running','waiting')", (row['id'],))
                event(db, row['id'], None, 'conversation_execution_stopped', inputs, now)
                cancelled.append(row['id'])
            receipt = inputs | {'kind':'execution_stopped', 'at':now, 'run_ids':cancelled,'checkpoint_runs':checkpoints}
            db.execute('INSERT INTO execution_commands VALUES(?,?,?,?)', (organization, request_id, canonical(inputs), canonical(receipt)))
            return receipt
