"""Authoritative workflow facts loaded inside the admission write transaction.

Workspace projections and caller-supplied ownership are deliberately absent.
Unknown legacy ancestry is a blocker, never evidence of independence.
"""
import json
from dataclasses import asdict
from datetime import datetime, timezone

from acquisition.audiences import Business, Snapshot
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import AdmissionIntent, ExecutionOwnership
from acquisition.conversations import CAPABILITY, FIXTURE_CAPABILITY
from .actors import require_actor
from .conversations import scoped_conversation
from .database import stored_plan_hash
from .execution import require_active
from .followups import require_followup
from .revision_provenance import require_revision_current
from .selected_audience import require_selected_audience
from .tasks import scoped_run


def row_json(db, table, column, organization, identity, key='id'):
    # Table/column names are fixed adapter literals, never request fields.
    row = db.execute(f'SELECT {column} FROM {table} WHERE organization=? AND {key}=?', (organization, identity)).fetchone()
    if row is None:
        raise NotFound('Admission source not found in this organization')
    return json.loads(row[0])


def require_owner(db, owner):
    owner = ExecutionOwnership(**owner)
    if owner.kind == 'conversation':
        current = scoped_conversation(db, owner.organization, owner.scope_id)
        if current['revision'] != owner.revision:
            raise Conflict('Conversation changed before workflow admission')
        require_active(db, owner.organization, owner.scope_id, owner.revision)


def parent_source(db, organization, run_id):
    run = scoped_run(db, organization, run_id)
    if run['request_hash'] != stored_plan_hash(db, run_id) or run['status'] in {'failed', 'cancelled'}:
        raise Conflict('Parent campaign is unavailable or its task plan changed')
    rows = db.execute('SELECT capability,inputs FROM tasks WHERE run_id=? ORDER BY position', (run_id,)).fetchall()
    tasks = [json.loads(r['inputs']) for r in rows]
    inspectors = {'monthly-mail/v1':'audiences.inspect.v1', 'conversation-mail/v1':'audiences.inspect_conversation.v1',
                  'monthly-mail/v2':'audiences.inspect_model.v2', 'monthly-mail/v3':'audiences.inspect_model.v3',
                  'conversation-model-mail/v3':'audiences.inspect_model_conversation.v3'}
    version = tasks[0].get('workflow_version') if tasks else None
    if (version not in inspectors or rows[0]['capability'] != inspectors[version] or
            any(t.get('workflow_version') != version for t in tasks)):
        raise Conflict('Parent must be a registered campaign workflow, not a planner, router or revision run')
    briefs = [t.get('brief') for t in tasks]
    if not briefs or not briefs[0] or any(b != briefs[0] for b in briefs):
        raise Conflict('Parent must be an actual campaign run')
    admitted = db.execute('SELECT payload,fingerprint FROM execution_admissions WHERE organization=? AND run_id=?', (organization, run_id)).fetchone()
    if admitted:
        intent = AdmissionIntent.from_payload(json.loads(admitted['payload']))
        if intent.fingerprint != admitted['fingerprint'] or digest(json.loads(intent.task_plan_json)) != run['request_hash']:
            raise Conflict('Parent admission integrity failure')
        owner = asdict(intent.ownership)
    else:
        link = db.execute('SELECT owner_organization,conversation_id,revision FROM execution_runs WHERE organization=? AND run_id=?', (organization, run_id)).fetchone()
        if link is None:
            raise Conflict('Parent needs verified domain ownership before it can have descendants')
        owner = asdict(ExecutionOwnership('conversation', *tuple(link)))
    require_owner(db, owner)
    return {'run_id': run_id, 'request_hash': run['request_hash'], 'brief': briefs[0], 'owner': owner}


def source_keys(references, required, optional=()):
    if type(references) is not dict or set(references) - set(required) - set(optional) or set(required) - set(references):
        raise ValueError('Use the exact source references for this workflow')


def conversation_source(db,organization,plan_id):
    plans = db.execute('''SELECT p.organization,p.payload,t.output,t.inputs,t.capability,r.id,r.request_hash FROM conversation_plans p
        JOIN runs r ON r.organization=p.organization AND r.request_id=json_extract(p.payload,'$.run_request_id')
        JOIN tasks t ON t.run_id=r.id AND t.position=0 AND t.status='succeeded'
        WHERE p.organization='local-conversations' AND r.status='succeeded' AND json_extract(t.output,'$.id')=?''', (plan_id,)).fetchall()
    if len(plans) != 1:
        raise NotFound('A successful saved conversation proposal is required')
    plan, frozen = json.loads(plans[0]['output']), json.loads(plans[0]['payload'])
    expected_capability = FIXTURE_CAPABILITY if frozen.get('fixture') else CAPABILITY
    if (plans[0]['capability'] != expected_capability or json.loads(plans[0]['inputs']) != frozen or
            plans[0]['request_hash'] != stored_plan_hash(db,plans[0]['id'])):
        raise Conflict('Saved plan differs from its admitted runtime operation')
    destination = 'workspace_' + digest({'conversation_id': plan['conversation_id'], 'plan_id': plan['id']})[:24]
    if organization != destination:
        raise Conflict('Conversation campaign belongs to a different campaign scope')
    selection = db.execute('SELECT payload FROM conversation_audiences WHERE organization=? AND conversation_id=? AND revision=?',
        ('local-conversations', plan['conversation_id'], plan['revision'])).fetchone()
    return dict(plan=plan, planning_inputs=frozen, selection=json.loads(selection[0]) if selection else None,
        owner=asdict(ExecutionOwnership('conversation', 'local-conversations', plan['conversation_id'], plan['revision'])))


def load_source(db, organization, kind, references, now, brief_builder):
    """Return facts for a trusted workflow composer, never caller-provided tasks."""
    source = {'kind': kind, 'organization': organization}
    if kind == 'routing':
        source_keys(references, ('action_id',))
        action = row_json(db, 'conversation_actions', 'payload', organization, references['action_id'])
        if action['organization'] != organization or action['id'] != references['action_id']:
            raise Conflict('Routing source scope changed')
        source.update(action=action, owner=asdict(ExecutionOwnership('conversation', organization,
            action['inputs']['conversation_id'], action['inputs']['revision'])))
    elif kind == 'copy-revision':
        source_keys(references, ('revision_request_id',))
        receipt = row_json(db, 'review_commands', 'receipt', organization, references['revision_request_id'], 'request_id')
        if receipt.get('kind') != 'copy_revision_admission' or receipt['request_id'] != references['revision_request_id']:
            raise Conflict('Copy source is not an authorized revision admission')
        require_revision_current(db, organization, receipt['task_inputs'], now=now)
        reviewer = require_actor(db, organization, receipt['inputs']['reviewer'], 'reviewer')
        case = db.execute('SELECT run_id FROM review_cases WHERE organization=? AND id=?', (organization, receipt['inputs']['case_id'])).fetchone()
        parent = parent_source(db, organization, case[0])
        context_id = 'context_' + digest({'organization': organization, **receipt['context']})
        db.execute('INSERT OR IGNORE INTO creative_contexts VALUES(?,?,?)', (organization, context_id, canonical(receipt['context'])))
        if row_json(db,'creative_contexts','payload',organization,context_id) != receipt['context']:
            raise Conflict('Revision context identity already binds different bytes')
        source.update(revision=receipt, context_id=context_id, reviewer_generation=reviewer['generation'],
            parent=parent, parent_run_id=parent['run_id'], owner=parent['owner'], contexts={'revision': receipt['context']},
            selection=receipt['task_inputs']['brief'].get('audience_source'))
    elif kind == 'conversation-campaign':
        source_keys(references, ('plan_id', 'snapshot_id'), ('context_ids',))
        # Conversation proposals live in their domain scope. The deterministic
        # campaign scope is the only cross-organization destination permitted.
        source.update(conversation_source(db,organization,references['plan_id']))
    elif kind == 'learning-followup':
        source_keys(references, ('proposal_id',))
        p = row_json(db, 'review_commands', 'receipt', organization, references['proposal_id'], 'request_id')
        if p.get('kind') != 'followup_proposal' or p['id'] != references['proposal_id'] or not p['eligible']:
            raise Conflict('A saved eligible follow-up proposal is required')
        cohort = db.execute('SELECT job_id,finalization FROM learning_cohorts WHERE organization=? AND id=?', (organization, p['source_cohort'])).fetchone()
        if cohort is None or json.loads(cohort['finalization'] or 'null') != p['learning']['finalization']:
            raise Conflict('Follow-up requires its exact finalized independent outcomes')
        job = row_json(db, 'simulated_agency_jobs', 'payload', organization, cohort['job_id'])
        case = db.execute('SELECT run_id FROM review_cases WHERE organization=? AND id=?', (organization, job['case_id'])).fetchone()
        if case is None:
            raise Conflict('Follow-up parent campaign is unavailable')
        parent = parent_source(db, organization, case[0])
        if p['parent_id'] != parent['brief']['campaign_id']:
            raise Conflict('Learning proposal differs from its actual parent campaign')
        source.update(proposal=p, owner=parent['owner'], parent=parent, parent_run_id=parent['run_id'])
    elif kind in {'manual-descendant', 'standalone-campaign'}:
        source_keys(references, ('snapshot_id', 'brief') + (('parent_run_id',) if kind == 'manual-descendant' else ()), ('context_ids','runtime_request_id'))
        if kind == 'manual-descendant':
            parent = parent_source(db, organization, references['parent_run_id'])
            if parent['brief']['campaign_id'] == references['brief'].get('campaign_id'):
                raise Conflict('A descendant requires a new campaign identity')
            source.update(parent=parent, owner=parent['owner'], parent_run_id=parent['run_id'])
        else:
            campaign_id = references['brief'].get('campaign_id')
            # A new explicit root cannot erase positive campaign ancestry.
            if db.execute('''SELECT 1 FROM runs r JOIN tasks t ON t.run_id=r.id WHERE r.organization=?
                AND json_extract(t.inputs,'$.brief.campaign_id')=?''', (organization, campaign_id)).fetchone() or db.execute(
                'SELECT 1 FROM execution_commands WHERE organization=? AND request_id=?', (organization, 'descendant:' + str(campaign_id))).fetchone():
                raise Conflict('Existing campaigns must use their verified parent path')
            source['owner'] = asdict(ExecutionOwnership('standalone', organization, campaign_id))
    else:
        raise ValueError('Unsupported workflow admission')
    require_owner(db, source['owner'])
    if kind not in {'routing', 'copy-revision'}:
        brief = brief_builder(kind, references, source)
        snapshot_id = source['proposal']['snapshot_id'] if kind == 'learning-followup' else references['snapshot_id']
        value = row_json(db, 'audiences', 'payload', organization, snapshot_id)
        snapshot = Snapshot(**(value | {'records': tuple(Business(**r) for r in value['records'])}))
        if snapshot.organization != organization or snapshot.id != snapshot_id or not snapshot.complete:
            raise Conflict('Admission requires its exact complete scoped audience')
        if snapshot.score_semantics != 'synthetic_response_propensity_not_uplift':
            raise ValueError('Unsupported audience score semantics')
        contexts = source['proposal']['contexts'] if kind == 'learning-followup' else references.get('context_ids', {})
        source.update(snapshot_id=snapshot_id, context_ids=contexts, contexts={}, audience_facts={
            'model_version':snapshot.model_version,
            'segment_counts':{segment:sum(r.segment==segment for r in snapshot.records) for segment in ('inventory','contractors')}})
        for segment, context_id in contexts.items():
            context = row_json(db, 'creative_contexts', 'payload', organization, context_id)
            if context_id != 'context_' + digest({'organization': organization, **context}):
                raise Conflict('Frozen copy context integrity failure')
            source['contexts'][segment] = context
        if kind == 'conversation-campaign':
            require_selected_audience(db, organization, asdict(brief), snapshot_id, now)
        if kind == 'learning-followup':
            require_actor(db, organization, 'local-operator', 'operator')
            require_followup(db, organization, {'brief': asdict(brief), 'snapshot_id': snapshot_id,
                **({'context_ids': contexts} if contexts else {})})
    return source


def freshness_fence(source, now):
    """Cheap final deadline check after all validation and before durable effects."""
    today = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
    dates = [c['product_facts']['review_by'] for c in source.get('contexts', {}).values()]
    if source.get('selection'):
        dates.append(source['selection']['source']['review_by'])
    if dates and any(today > deadline for deadline in dates):
        raise Conflict('Admission source expired during validation; refresh before requesting again')
