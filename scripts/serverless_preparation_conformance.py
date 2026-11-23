"""Opt-in independent-process continuation against the existing isolated database."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from multiprocessing import Manager
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from acquisition.bootstrap import build_hosted_preparations
from acquisition.contracts import Conflict
from scripts.hosting_probe import load_environment


def invoke(org,action,values,barrier=None):
    if barrier is not None:barrier.wait(timeout=30)
    began=time.monotonic()
    service=build_hosted_preparations(None,org,remote_storage={
        'url':os.environ['TURSO_DATABASE_URL'],'token':os.environ['TURSO_AUTH_TOKEN'],
        'deadline':time.monotonic()+120})
    result=getattr(service,action)(**values)
    return result,round(time.monotonic()-began,3)


def run(org,report=None):
    report=report if report is not None else {}
    report['phase']='start'
    command={'request_id':'original','profile_key':'fielddesk','budget_pence':10000,'allow_generation':True}
    with Manager() as manager,ProcessPoolExecutor(max_workers=2) as workers:
        barrier=manager.Barrier(2)
        started=list(workers.map(invoke,[org,org],['start','start'],[command,command],[barrier,barrier]))
    assert started[0][0]['receipt']==started[1][0]['receipt']
    jid=started[0][0]['receipt']['journey_id'];times={'start':[v[1] for v in started]}
    for stage in range(7):
        report['phase']='stage_'+str(stage)
        # Each executor is disposed after the request: no process owns continuation.
        with ProcessPoolExecutor(max_workers=1) as worker:
            result,elapsed=worker.submit(invoke,org,'advance',{'journey_id':jid,'expected_stage':stage}).result()
        assert result['progress']['stage']==stage+1,result['progress']['detail']
        times[str(stage)]=elapsed
        with ProcessPoolExecutor(max_workers=1) as worker:
            replay,_=worker.submit(invoke,org,'advance',{'journey_id':jid,'expected_stage':stage}).result()
        assert replay['observation']=='already_advanced'
        assert replay['receipt']==started[0][0]['receipt']
    report['phase']='verify_read_only_and_authority'
    assert result['progress']['status']=='ready'
    from acquisition.adapters.turso import TursoDatabase
    db=TursoDatabase(os.environ['TURSO_DATABASE_URL'],os.environ['TURSO_AUTH_TOKEN'],initialize=False)
    def evidence():
        with db.connect() as connection:
            rows=connection.execute('SELECT payload FROM sequence_journey_events WHERE organization=? ORDER BY id',(org,)).fetchall()
            native=result['progress']['outputs']['initial-run']
            scope=connection.execute('SELECT organization FROM runs WHERE id=?',(native,)).fetchone()[0]
            calls=[tuple(r) for r in connection.execute('SELECT run_id,call_key,status FROM model_calls WHERE organization=? ORDER BY run_id,call_key',(scope,))]
            return rows,calls,scope
    before=evidence();assert len(before[1])==9
    for _ in range(3):invoke(org,'status',{'journey_id':jid})
    after=evidence()
    assert [tuple(r) for r in before[0]]==[tuple(r) for r in after[0]] and before[1]==after[1]
    try:invoke(org,'start',command|{'budget_pence':20000})
    except Conflict:pass
    else:raise AssertionError('Changed command accepted')
    with db.connect() as connection:
        assert connection.execute('SELECT count(*) FROM sequence_journeys WHERE organization=?',(org,)).fetchone()[0]==1
        assert connection.execute('SELECT count(*) FROM channel_preparations WHERE organization=?',(before[2],)).fetchone()[0]==3
        assert connection.execute('SELECT count(*) FROM sequence_review_decisions WHERE organization=?',(before[2],)).fetchone()[0]==0
    return {'organization':org,'journey_id':jid,'status':'ready','authority':'none','fixture_calls':9,
        'unapproved':True,'processes_rebuilt_between_steps':True,'same_stage_replay_read_only':True,
        'status_read_only':True,'changed_input_rejected':True,'seconds':times,'live_model_calls':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();load_environment(args.env_file)
    from acquisition.adapters.turso.transport import endpoint
    if not endpoint(os.environ['TURSO_DATABASE_URL']).startswith('https://acquisition-hosting-probe-'):
        raise ValueError('Use the existing dedicated probe resource')
    report={'schema':'serverless-preparation-conformance/v1','synthetic':True,'passed':False,
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'organization':'hosted_probe_'+uuid4().hex,
        'source_dirty':bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--',
            'src','scripts','config','api','vercel.json'],text=True))}
    try:report['observed']=run(report['organization'],report);report['passed']=True
    except Exception as error:report['error_type']=type(error).__name__
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report));return 0 if report['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
