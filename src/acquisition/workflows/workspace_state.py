"""Compose public source contracts for sandbox intent, never execution grants."""
import json
from dataclasses import asdict
from datetime import datetime, timezone
from acquisition.contracts import Conflict, digest, canonical
from acquisition.conversations import environment_time, ExecutionOwnership
from acquisition.campaigns import Brief
from acquisition.reasoning import ModelConfig
from .admission_coverage import campaign_brief


def validate_environment_run(session,creation,admitted,command,source,parent,*,synthetic_snapshot_id):
    """Check frozen admissions against original intent and audience identity."""
    sid=session['id'];model=session['mode']=='model';kind=creation['kind']
    workflow={'root':'manual-descendant' if session['parent_id'] else 'standalone-campaign',
              'conversation':'conversation-campaign','followup':'learning-followup'}.get(kind)
    if workflow is None or command.get('kind')!=workflow or admitted.workflow_version!=workflow+'-admission/v1':
        raise Conflict('Sandbox run has a different admitted source kind')
    permission=ModelConfig('openai/gpt-oss-120b',max_calls=10,force_tool_choice=True).payload() if model else None
    as_of=datetime.fromtimestamp(session['clock'],timezone.utc).date().isoformat()
    parent_run=parent['run_id'] if parent else None
    inputs=json.loads(creation['inputs'])
    expected_snapshot=source.get('snapshot_id')
    if kind=='root' or (kind=='conversation' and not session.get('audience_selection')):
        expected_snapshot=synthetic_snapshot_id(session['organization'],1000,42,as_of)
        if (source.get('snapshot_id')!=expected_snapshot or
                admitted.tasks[0].inputs.get('snapshot_id')!=expected_snapshot):
            raise Conflict('Sandbox audience differs from its original synthetic generation command')
    if kind=='root':
        workflow='manual-descendant' if session['parent_id'] else 'standalone-campaign'
        if inputs!={'mode':session['mode'],'parent_id':session['parent_id']}:
            raise Conflict('Sandbox creation command differs from its immutable intent')
        if session['parent_id'] and parent_run is None:raise Conflict('Sandbox parent run is unavailable')
        brief=asdict(Brief(sid))
        owner=source['parent']['owner'] if parent else asdict(ExecutionOwnership('standalone',session['organization'],sid))
        refs={'brief':brief,'snapshot_id':expected_snapshot,'runtime_request_id':sid}
        if parent:refs['parent_run_id']=parent_run
        entry={'method':'start','size':1000,'seed':42,'as_of':as_of,'brief':brief,'campaign_id':None,'parent_run_id':parent_run}
    elif kind=='conversation':
        workflow='conversation-campaign';plan=session['conversation_plan']
        if (inputs!={'conversation_id':plan['conversation_id'],'revision':plan['revision'],'plan_id':plan['id']} or
                source['plan']!=plan or source['selection']!=session.get('audience_selection')):
            raise Conflict('Sandbox run differs from its frozen conversation source')
        brief=asdict(campaign_brief(workflow,{},source));owner=asdict(ExecutionOwnership('conversation','local-conversations',plan['conversation_id'],plan['revision']))
        refs={'plan_id':plan['id'],'snapshot_id':expected_snapshot}
        entry={'method':'start-conversation','plan':plan,'as_of':as_of,'selected_audience':bool(session.get('audience_selection'))}
    elif kind=='followup':
        workflow='learning-followup';p=source['proposal']
        if (inputs!={'parent':session['parent_id'],'proposal':session['followup_id'],'mode':session['mode'],'allow_model_copy':model} or
                parent is None or p['id']!=session['followup_id'] or p['parent_id']!=parent['id'] or p['source_cohort']!=parent['cohort_id']):
            raise Conflict('Sandbox run differs from its frozen learning source')
        brief=asdict(campaign_brief(workflow,{},source));owner=source['parent']['owner']
        if model:permission=p['model_config']
        refs={'proposal_id':p['id']}
        entry={'method':'start-followup','snapshot_id':p['snapshot_id'],'brief':brief}
    else:raise Conflict('Unsupported sandbox creation command')
    if model:
        if kind!='followup':refs['context_ids']=source['context_ids']
        entry={'method':'start-model','size':1000,'seed':42,'as_of':as_of if kind!='followup' else '2026-10-25',
            'budget_pence':85000,'campaign_id':None,'brief':brief,
            'objective':session['conversation_plan']['objective'] if kind=='conversation' else None,
            'snapshot_override':source['snapshot_id'] if kind=='followup' or session.get('audience_selection') else None,
            'contexts_override':source['proposal']['contexts'] if kind=='followup' else None,
            'parent_run_id':parent_run if kind=='root' else None}
    expected_parent=parent_run if parent else None
    if (admitted.workflow_version!=workflow+'-admission/v1' or admitted.source_id!=sid or
            admitted.parent_run_id!=expected_parent or asdict(admitted.ownership)!=owner or
            (admitted.model_config.payload() if admitted.model_config else None)!=permission or
            command.get('kind')!=workflow or command.get('allow_model') is not model or command.get('model_config')!=permission or
            canonical(command.get('entrypoint'))!=canonical(entry) or canonical(command.get('references'))!=canonical(refs) or
            canonical(admitted.tasks[0].inputs.get('brief'))!=canonical(brief)):
        raise Conflict('Sandbox run differs from its immutable mode, source, parent or creation command')


def validate_environment(session,kind,inputs,source,now,request_id,fixture_clock):
    environment_time(now);environment_time(fixture_clock)
    if kind=='root':
        if set(inputs)!={'mode','parent_id'} or inputs!={k:session[k] for k in inputs}:
            raise Conflict('Sandbox creation differs from its original command')
        expected='workspace_'+digest({'request_id':request_id})[:24]
        if session['id']!=expected:raise Conflict('Sandbox identity differs from its native creation request')
        if session['parent_id'] is None:
            if session['organization']!=expected or session['database_scope']!='campaign':
                raise Conflict('A root sandbox needs its own server-owned campaign scope')
        elif session['organization']!=source['parent']['organization'] or session['database_scope']!=source['parent']['database_scope']:
            raise Conflict('A child cannot change its parent organization or store')
    elif kind=='conversation':
        brief=campaign_brief('conversation-campaign',{},source)
        plan=source['plan']
        if inputs!={'conversation_id':plan['conversation_id'],'revision':plan['revision'],'plan_id':plan['id']}:
            raise Conflict('Sandbox command differs from its saved conversation proposal')
        if (session['id']!=brief.campaign_id or session['conversation_plan']!=plan or session['mode']!=plan['copy_mode'] or
            session['database_scope']!='conversations' or session['parent_id'] is not None or
            session.get('audience_selection')!=source['selection']):
            raise Conflict('Sandbox intent differs from its authoritative proposal or audience')
    elif kind=='followup':
        p=source['proposal'];parent=source['parent']
        if (p.get('kind')!='followup_proposal' or p['id']!=session['followup_id'] or not p['eligible'] or
            p['parent_id']!=parent['id'] or p['source_cohort']!=parent['cohort_id'] or p['learning']['finalization']!=source['finalization']):
            raise Conflict('Follow-up intent differs from its finalized parent learning')
        if inputs!={'parent':parent['id'],'proposal':p['id'],'mode':session['mode'],'allow_model_copy':session['mode']=='model'}:
            raise Conflict('Follow-up command differs from its copy permission or source')
        if session['id']!='workspace_'+digest({'followup':p['id']})[:24] or session['database_scope']!=parent['database_scope']:
            raise Conflict('Follow-up identity or storage differs from its parent')
    else:raise ValueError('Unsupported sandbox source kind')
    if session['parent_id']:
        if session['clock_mode']!='SIMULATED' or session['clock']<max(source['parent']['clock'],now):
            raise Conflict('A child environment must preserve its parent simulation time')
    else:
        initial=now if session['mode']=='model' else fixture_clock
        if session.get('audience_selection'):initial=max(initial,now)
        # Model clocks progress with real time; the initial sample may predate
        # the transaction. It must not be a caller-supplied future clock.
        if session['mode']=='model':
            if session['clock_mode']!='REAL' or session['clock']>now:raise Conflict('Invalid initial real-time environment')
        elif session['clock_mode']!='SIMULATED' or session['clock']!=initial:
            raise Conflict('Fixture time differs from the server-owned initial environment')
