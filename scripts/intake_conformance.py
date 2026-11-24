"""Opt-in synthetic intake checks on the existing isolated Turso resource."""

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import json
from multiprocessing import Manager
from pathlib import Path
from uuid import uuid4

from acquisition.adapters.sqlite.intake import SqliteCampaignIntake
from acquisition.adapters.turso import TursoDatabase, CommitUncertain
from acquisition.adapters.turso.transport import RemoteUnavailable, endpoint
from acquisition.bootstrap import build, build_intake
from acquisition.adapters.openrouter import normalize
from acquisition.reasoning import ModelConfig
from acquisition.campaigns import CampaignBriefDraft, CampaignIntake
from acquisition.contracts import Conflict, NotFound
from acquisition.creative import CompanyDraft
from scripts.evaluation_evidence import source_state
from scripts.hosting_probe import load_environment
from scripts.remote_storage_conformance import storage


class SyntheticPlanner:
    """In-process response only; this gateway cannot dispatch paid inference."""
    def __init__(self):
        self.calls = 0

    def complete(self, request):
        self.calls += 1
        candidate = {'outcome':'proposal', 'summary':'Explore the supplied synthetic brief.',
                     'approach':['Compare two qualified messages for the requested audience.'],
                     'questions':[], 'limitations':['User company assertions remain unverified.']}
        return normalize({'id':'synthetic-intake', 'model':request['model'], 'provider':'synthetic',
            'choices':[{'finish_reason':'tool_calls', 'message':{'tool_calls':[{
                'id':'synthetic-call', 'type':'function', 'function':{
                    'name':'submit_intake_plan', 'arguments':json.dumps(candidate)}}]}}],
            'usage':{'prompt_tokens':100, 'completion_tokens':100, 'total_tokens':200, 'cost':0}})


def independent_save(settings, organization, company_id, index, barrier):
    database = TursoDatabase(settings['url'], settings['token'], initialize=False)
    app = CampaignIntake(SqliteCampaignIntake(database), lambda:123.)
    barrier.wait(timeout=30)
    try:
        return app.save_company(organization,'writer','edit-'+str(index),CompanyDraft(company_name='Synthetic '+str(index)),
                                company_id=company_id,expected_revision=1)
    except Conflict:
        return 'conflict'


def run(settings):
    organization = 'intake_conformance_' + uuid4().hex
    app = build_intake(None, remote_storage=settings, clock=lambda:123.)
    company = app.save_company(organization,'writer','company',CompanyDraft(company_name='Synthetic intake check'))['snapshot']
    with Manager() as manager, ProcessPoolExecutor(max_workers=2) as pool:
        barrier = manager.Barrier(2)
        futures = [pool.submit(independent_save,settings,organization,company['id'],i,barrier) for i in range(2)]
        results = [f.result(timeout=90) for f in futures]
    assert results.count('conflict') == 1
    assert app.company(organization,company['id'])['revision'] == 2
    assert app.company(organization,company['id'],1) == company
    draft = CampaignBriefDraft(company['id'],1,objective='Synthetic persistence only',country='France',
                                currency='EUR',channels=('video',),budget_minor=12345)
    original = app.store.database.send
    def lose_ack(payload):
        result = original(payload)
        if any(step.get('stmt',{}).get('sql')=='COMMIT' for request in payload['requests'] for step in request.get('batch',{}).get('steps',[])):
            raise RemoteUnavailable('Synthetic lost acknowledgement')
        return result
    app.store.database.send = lose_ack
    try:
        try:app.save_brief(organization,'writer','brief',draft)
        except CommitUncertain:pass
        else:raise AssertionError('Lost acknowledgement was not surfaced')
    finally:app.store.database.send = original
    # Independent remote session reconciles only by exact original command.
    restarted = CampaignIntake(SqliteCampaignIntake(TursoDatabase(settings['url'],settings['token'],initialize=False)),lambda:999.)
    receipt = restarted.save_brief(organization,'writer','brief',draft)
    assert receipt['replayed'] and receipt['snapshot']['saved_at'] == 123.
    assert restarted.brief(organization,receipt['snapshot']['id']) == receipt['snapshot']
    assert restarted.briefs(organization) == [receipt['snapshot']]
    try:restarted.save_brief(organization,'writer','brief',replace(draft,budget_minor=23456))
    except Conflict:pass
    else:raise AssertionError('Changed inputs accepted')
    for action in (lambda:restarted.company('foreign',company['id']),
                   lambda:restarted.brief('foreign',receipt['snapshot']['id']),
                   lambda:restarted.save_brief('foreign','writer',organization,draft)):
        try:action()
        except NotFound:pass
        else:raise AssertionError('Foreign organization accepted')
    with app.store.database.connect() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 25
        for table in ('runs','tasks','model_calls','drafts','review_decisions'):
            if table == 'tasks':
                count = db.execute('SELECT count(*) FROM tasks JOIN runs ON runs.id=tasks.run_id WHERE organization=?',(organization,)).fetchone()[0]
            else:
                count = db.execute('SELECT count(*) FROM '+table+' WHERE organization=?',(organization,)).fetchone()[0]
            assert count == 0
        assert db.execute('SELECT count(*) FROM intake_company_revisions WHERE organization=?',(organization,)).fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM intake_brief_revisions WHERE organization=?',(organization,)).fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM intake_requests WHERE organization=?',(organization,)).fetchone()[0] == 3
    # A separate saved source exercises additive planning persistence and the
    # native admission path. Existing verified execution pauses stay in force.
    planned_company = app.save_company(organization,'writer','planning-company',CompanyDraft(
        company_name='Synthetic consultancy',description='Synthetic unverified source'))['snapshot']
    planned_brief = app.save_brief(organization,'writer','planning-brief',CampaignBriefDraft(
        planned_company['id'],1,objective='Explore a synthetic campaign',audience='UK retailers',
        country='UK',currency='GBP',channels=('email',),budget_minor=12345))['snapshot']
    gateway = SyntheticPlanner()
    config = ModelConfig('synthetic/intake:free',max_calls=2,force_tool_choice=True,
                         max_prompt_usd_per_million=0,max_completion_usd_per_million=0)
    planner = build(None,remote_storage=settings,gateway=gateway,model_config=config,clock=lambda:123.)
    run_id = planner.intake_planning.request(organization,'writer','plan',planned_brief['id'],1)
    planner.worker.drain(organization,run_id=run_id)
    view = planner.intake_planning.view(organization,'plan')
    assert view['source']['company'] == planned_company
    assert view['source']['brief'] == planned_brief
    assert view['plan']['status'] in {'queued','succeeded'}, view['plan']['status']
    if view['plan']['status'] == 'succeeded':
        assert gateway.calls == 1
        assert view['plan']['result']['authority'] == 'none'
        assert view['plan']['result']['requirements'] == planned_brief['draft']
    else:
        assert gateway.calls == 0
    reopened_gateway = SyntheticPlanner()
    reopened = build(None,remote_storage=settings,gateway=reopened_gateway,model_config=config,clock=lambda:124.)
    assert reopened.intake_planning.request(organization,'writer','plan',planned_brief['id'],1) == run_id
    assert reopened.intake_planning.view(organization,'plan')['source'] == view['source']
    try:reopened.intake_planning.request(organization,'writer','replacement-plan',planned_brief['id'],1)
    except Conflict:pass
    else:raise AssertionError('A replacement planning request repeated the original source')
    assert reopened_gateway.calls == 0
    with planner.tasks.database.connect() as db:
        assert db.execute('SELECT count(*) FROM intake_planning_sources WHERE organization=?',(organization,)).fetchone()[0] == 1
        for table in ('drafts','review_decisions'):
            assert db.execute('SELECT count(*) FROM '+table+' WHERE organization=?',(organization,)).fetchone()[0] == 0
    return {'organization':organization,'company_revisions':3,'brief_revisions':2,'receipts':5,
            'competing_processes':2,'stale_edit_rejected':True,'lost_commit_ack_replayed':True,
            'foreign_scope_rejected':True,'changed_input_rejected':True,'company_revision_pinned':True,
            'synthetic_model_calls':gateway.calls,'paid_model_calls':0,'campaign_runs':0,'schema':25,
            'planning_status':view['plan']['status'],'original_plan_replayed':True,
            'replacement_plan_rejected':True,'planning_sources':1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists():raise ValueError('Preserve existing evidence; choose a new output')
    load_environment(args.env_file)
    settings = storage()
    if not endpoint(settings['url']).startswith('https://acquisition-hosting-probe-'):
        raise ValueError('Use the existing dedicated acquisition-hosting-probe resource')
    before = source_state()
    report = {'schema':'intake-conformance/v1','synthetic':True,'passed':False,'source':before}
    try:
        report['observed'] = run(settings)
        report['source_stable'] = source_state() == before
        report['passed'] = report['source_stable']
    except Exception as error:
        report['error_type'] = type(error).__name__
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key != 'source'}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
