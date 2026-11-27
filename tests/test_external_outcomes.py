"""Independent literal counts, authoritative frozen membership and real SQLite recovery."""
import copy
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing,contextmanager
from pathlib import Path
from unittest.mock import patch

from acquisition.bootstrap import build_outcomes
from acquisition.adapters.sqlite.reviews import SqliteReviews
from acquisition.contracts import Conflict,NotFound,canonical

NOW=1795694400.


def manifest(org='one',campaign='external-campaign',data_class='recorded_fixture',channel='email'):
    assignments=[]
    for i,arm in enumerate(('A','A','B','B','holdout','holdout')):
        h=hashlib.sha256(('Exact '+arm+' content').encode()).hexdigest() if arm!='holdout' else None
        assignments.append({'business_id':'business-'+str(i),'segment':'retail','arm':arm,'creative_sha256':h,
            'outcome_record_id':'crm-'+str(i),'dispatch':None if arm=='holdout' else
            {'id':'message-'+str(i),'status':'sent','at':NOW-50,'content_sha256':h}})
    return {'schema':'external-campaign-registration/v1','mode':'EXTERNAL_OPERATOR_ATTESTED','data_class':data_class,
        'organization':org,'campaign_id':campaign,'channel':channel,'metric':'qualified_enquiry/v1',
        'assignment_design':'observational','qualification_rule':'A recorded request to discuss this product, excluding automatic and unsubscribe replies.',
        'window_start':NOW-100,'window_end':NOW+100,'prior':{'alpha':1,'beta':19},
        'sources':[{'id':'send','role':'dispatch','system':'email-platform' if channel=='email' else 'postal-platform','account_id':'account-one'},
                   {'id':'crm','role':'outcomes','system':'crm','account_id':'crm-one'}],
        'assignments':assignments,'attestation':{'confirmed':True,'note':'Recorded fixture only. External operator asserts the original source and assignments.',
            'evidence_ref':'original-manifest','evidence_sha256':hashlib.sha256(b'fixture-manifest').hexdigest()}}


def identical_manifest():
    value=manifest();value['assignment_design']='operator_attested_randomized'
    members=[];creative=value['assignments'][0]['creative_sha256']
    for arm,total,index in [('A',30,0),('B',30,2),('holdout',10,4)]:
        for i in range(total):
            m=copy.deepcopy(value['assignments'][index]);identity=arm+'-'+str(i)
            m['business_id']='business-'+identity;m['outcome_record_id']='crm-'+identity
            if m['dispatch']:
                m['creative_sha256']=creative;m['dispatch'].update(id='message-'+identity,content_sha256=creative)
            members.append(m)
    value['assignments']=members
    return value


def event(m,kind,at=None,event_id=None):
    return {'event_id':event_id or kind+'-'+m['business_id'],'business_id':m['business_id'],'arm':m['arm'],
        'creative_sha256':m['creative_sha256'],'record_id':m['outcome_record_id'] if kind in {'qualified_enquiry','no_qualified_enquiry'} else m['dispatch']['id'],
        'kind':kind,'occurred_at':at if at is not None else NOW,'evidence_ref':'source-event-'+m['business_id']}


def report(c,rows,*,source='crm',identity='report',final=False,watermark=None):
    return {'schema':'external-outcome-report/v1','mode':c['mode'],'data_class':c['data_class'],'organization':c['organization'],
        'cohort_id':c['id'],'report_id':identity,'source_id':source,'watermark':watermark if watermark is not None else c['window_end'] if final else NOW,
        'final':final,'page_count':1,'pages':[{'number':1,'events':rows}],
        'attestation':{'confirmed':True,'note':'Operator attests these recorded source observations and stated coverage.',
            'evidence_ref':'report-source','evidence_sha256':hashlib.sha256(canonical(rows).encode()).hexdigest()}}


class ExternalOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)/'app.sqlite';self.now=NOW
        self.app=build_outcomes(self.path,clock=lambda:self.now);self.db=self.app.store.database
        self.roles=SqliteReviews(self.db,lambda:self.now,None);self.roles.register_actor('one','operator',('operator',))
        self.m=manifest()
    def register(self,key='register',value=None):
        r=self.app.register('one','operator',key,value or self.m);self.c=self.app.view('one',r['cohort_id'])['cohort'];return r
    def ingest(self,p,key=None):return self.app.ingest('one','operator',key or p['report_id'],self.c['id'],p)
    def complete(self):
        self.now=self.c['window_end']
        rows=[event(m,'qualified_enquiry' if i in (0,4) else 'no_qualified_enquiry',NOW if i in (0,4) else self.now) for i,m in enumerate(self.c['assignments'])]
        self.ingest(report(self.c,rows,identity='final-report',final=True));return rows
    def counts(self):
        with self.db.connect() as db:return {t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('learning_commands','learning_events','learning_cohorts','learning_beliefs','model_calls','runs')}
    def test_observations_are_not_trials_and_literal_posteriors_require_complete_maturity(self):
        self.register();m=self.c['assignments'][0]
        rows=[event(m,'opened',event_id='open-'+str(i)) for i in range(20)]+[event(m,'clicked')]
        self.ingest(report(self.c,rows,source='send',identity='diagnostics'))
        v=self.app.view('one',self.c['id']);self.assertEqual(v['missing'],6);self.assertEqual(v['posterior_groups'],[])
        self.assertEqual(v['event_counts']['opened'],20);self.assertEqual(v['business_counts']['opened'],1)
        self.ingest(report(self.c,[event(m,'qualified_enquiry')],identity='early'))
        with self.assertRaises(Conflict):self.app.finalize('one','operator','too-soon',self.c['id'])
        self.complete();self.assertEqual(self.app.view('one',self.c['id'])['status'],'ready_to_finalize')
        result=self.app.finalize('one','operator','final',self.c['id'])
        groups={g['arm']:g for g in result['groups']}
        self.assertEqual((groups['A']['trials'],groups['A']['successes'],groups['A']['alpha'],groups['A']['beta']),(2,1,2,20))
        self.assertEqual((groups['B']['alpha'],groups['B']['beta']),(1,21));self.assertEqual((groups['holdout']['alpha'],groups['holdout']['beta']),(2,20))
        self.assertAlmostEqual(groups['A']['mean'],1/11)
        self.assertEqual(result['comparisons'][0]['authority'],'ADVISORY_REQUIRES_NEW_PROPOSAL_AND_APPROVAL')
        self.assertEqual(result['data_class'],'recorded_fixture')
        self.assertEqual({k:self.counts()[k] for k in ('learning_cohorts','learning_beliefs','model_calls','runs')},dict.fromkeys(('learning_cohorts','learning_beliefs','model_calls','runs'),0))
    def test_missing_assignments_and_missing_pages_never_become_negative_outcomes(self):
        self.register();self.now=self.c['window_end'];rows=[event(m,'no_qualified_enquiry',self.now) for m in self.c['assignments'][:-1]]
        p=report(self.c,rows,final=True);self.ingest(p)
        v=self.app.view('one',self.c['id']);self.assertEqual(v['missing'],1);self.assertFalse(v['coverage_complete'])
        with self.assertRaises(Conflict):self.app.finalize('one','operator','missing',self.c['id'])
        bad=copy.deepcopy(p);bad['report_id']='pages';bad['page_count']=2
        before=self.counts()
        with self.assertRaises(ValueError):self.ingest(bad)
        self.assertEqual(self.counts(),before)
        changed=copy.deepcopy(self.m);changed['assignments'].pop()
        with self.assertRaises(Conflict):self.app.register('one','operator','shrink',changed)
    def test_duplicate_events_pages_and_reports_do_not_add_support_or_extend_time(self):
        first=self.register();self.assertEqual(self.register('another-register'),first)
        m=self.c['assignments'][0];e=event(m,'qualified_enquiry');p=report(self.c,[e,e])
        r=self.ingest(p);self.assertEqual(r['added_events'],1)
        self.assertEqual(self.ingest(p,'new-command'),r)
        next_report=report(self.c,[e],identity='snapshot-two');self.assertEqual(self.ingest(next_report)['added_events'],0)
        self.assertEqual(self.app.view('one',self.c['id'])['received'],1)
        p['pages'][0]['events'][0]['evidence_ref']='different'
        with self.assertRaises(Conflict):self.ingest(p)
    def test_conflicting_event_or_outcome_rolls_back_the_entire_snapshot(self):
        self.register();m=self.c['assignments'][0];self.ingest(report(self.c,[event(m,'qualified_enquiry')]))
        self.now=self.c['window_end'];p=report(self.c,[event(self.c['assignments'][1],'qualified_enquiry'),event(m,'no_qualified_enquiry',self.now)],identity='contradiction',final=True)
        before=self.counts()
        with self.assertRaises(Conflict):self.ingest(p)
        self.assertEqual(self.counts(),before);self.assertEqual(self.app.view('one',self.c['id'])['received'],1)
        changed=event(m,'qualified_enquiry');changed['evidence_ref']='changed'
        with self.assertRaises(Conflict):self.ingest(report(self.c,[changed],identity='changed-id'))
    def test_scope_source_assignment_mode_and_engagement_cannot_substitute_for_outcomes(self):
        self.register();m=self.c['assignments'][0];p=report(self.c,[event(m,'qualified_enquiry')]);before=self.counts()
        mutations=[('organization','foreign'),('data_class','operator_attested_external'),('source_id','send'),('mode','SYNTHETIC_ONLY')]
        for k,v in mutations:
            bad=copy.deepcopy(p);bad[k]=v
            with self.subTest(field=k),self.assertRaises(ValueError):self.ingest(bad)
        for k,v in [('business_id','foreign'),('record_id','crm-foreign'),('arm','B'),('creative_sha256','f'*64),('kind','model_score')]:
            bad=copy.deepcopy(p);bad['pages'][0]['events'][0][k]=v
            with self.subTest(field=k),self.assertRaises(ValueError):self.ingest(bad)
        with self.assertRaises(NotFound):self.app.view('foreign',self.c['id'])
        self.assertEqual(self.counts(),before)
    def test_report_watermarks_bounds_and_explicit_negative_rules(self):
        self.register();m=self.c['assignments'][0]
        for final,at,watermark in [(False,self.c['window_end'],NOW),(True,self.c['window_end'],self.c['window_end']), (False,NOW+1,NOW)]:
            p=report(self.c,[event(m,'no_qualified_enquiry' if at==self.c['window_end'] else 'qualified_enquiry',at)],final=final,watermark=watermark)
            with self.assertRaises(ValueError):self.ingest(p)
        self.now=self.c['window_end'];p=report(self.c,[event(m,'qualified_enquiry',self.now)],final=True)
        with self.assertRaises(ValueError):self.ingest(p)
    def test_native_dispatch_and_crm_identities_cannot_be_reused_under_other_business_names(self):
        self.register()
        for mutate in ('business','crm','dispatch'):
            p=copy.deepcopy(self.m);p['campaign_id']='second'
            for m in p['assignments']:
                m['business_id']='new-'+m['business_id']
                if mutate!='crm':m['outcome_record_id']='new-'+m['outcome_record_id']
                if m['dispatch'] and mutate!='dispatch':m['dispatch']['id']='new-'+m['dispatch']['id']
            if mutate=='business':p['assignments'][0]['business_id']=self.m['assignments'][0]['business_id']
            with self.subTest(reuse=mutate),self.assertRaises(Conflict):self.app.register('one','operator','reuse-'+mutate,p)
    def test_roles_rechecked_after_writes_and_cached_commands_do_not_bypass_disable(self):
        self.register();p=report(self.c,[event(self.c['assignments'][0],'qualified_enquiry')]);store=self.app.store;real=store.command;before=self.counts()
        def disable(*args,**kwargs):
            result=real(*args,**kwargs)
            if kwargs.get('value') is not None or len(args)>=7:
                args[0].execute("UPDATE review_actors SET enabled=0,generation=generation+1 WHERE organization='one' AND id='operator'")
            return result
        with patch.object(store,'command',side_effect=disable),self.assertRaises(ValueError):self.ingest(p)
        self.assertEqual(self.counts(),before)
        self.ingest(p);self.roles.register_actor('one','operator',('operator',),False)
        with self.assertRaises(ValueError):self.ingest(p)
        self.assertEqual(self.app.receipt('one','operator','import','report')['observation'],'HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY')
    def test_registration_report_and_finalization_faults_are_atomic(self):
        store=self.app.store;real=store.audit
        def fail(*args):real(*args);raise OSError('after audit before commit')
        before=self.counts()
        with patch.object(store,'audit',side_effect=fail),self.assertRaises(OSError):self.register()
        self.assertEqual(self.counts(),before)
        self.register();before=self.counts()
        with patch.object(store,'audit',side_effect=fail),self.assertRaises(OSError):self.ingest(report(self.c,[event(self.c['assignments'][0],'qualified_enquiry')]))
        self.assertEqual(self.counts(),before)
        self.complete();before=self.counts()
        with patch.object(store,'audit',side_effect=fail),self.assertRaises(OSError):self.app.finalize('one','operator','final',self.c['id'])
        self.assertEqual(self.counts(),before);self.assertEqual(self.app.view('one',self.c['id'])['posterior_groups'],[])
    def test_lost_acknowledgements_reconcile_original_receipts_without_recounting(self):
        real=self.db.transaction
        @contextmanager
        def lost():
            with real() as db:yield db
            raise OSError('lost acknowledgement after commit')
        with patch.object(self.db,'transaction',lost),self.assertRaises(OSError):self.app.register('one','operator','register',self.m)
        self.register();p=report(self.c,[event(self.c['assignments'][0],'qualified_enquiry')])
        with patch.object(self.db,'transaction',lost),self.assertRaises(OSError):self.ingest(p)
        replay=self.ingest(p);saved=self.app.receipt('one','operator','import','report');saved.pop('observation')
        self.assertEqual(replay,saved);self.assertEqual(self.app.view('one',self.c['id'])['received'],1)
        self.complete()
        with patch.object(self.db,'transaction',lost),self.assertRaises(OSError):self.app.finalize('one','operator','final',self.c['id'])
        original=self.app.view('one',self.c['id'])['finalization'];self.now+=100
        self.assertEqual(self.app.finalize('one','operator','final-again',self.c['id']),original)
        with self.db.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM learning_events WHERE kind='external_finalization'").fetchone()[0],1)
    def test_two_first_admissions_and_finalizations_converge(self):
        def register(i):return build_outcomes(self.path,clock=lambda:NOW).register('one','operator','register-'+str(i),self.m)
        with ThreadPoolExecutor(max_workers=2) as pool:receipts=list(pool.map(register,range(2)))
        self.assertEqual(receipts[0],receipts[1]);self.c=self.app.view('one',receipts[0]['cohort_id'])['cohort'];self.complete()
        def finalize(i):return build_outcomes(self.path,clock=lambda:self.now).finalize('one','operator','final-'+str(i),self.c['id'])
        with ThreadPoolExecutor(max_workers=2) as pool:values=list(pool.map(finalize,range(2)))
        self.assertEqual(values[0].get('original_receipt',values[0]),values[1].get('original_receipt',values[1]))
        self.assertEqual(sum(v.get('observation')=='HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY' for v in values),1)
        with self.db.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM learning_events WHERE kind='external_registration'").fetchone()[0],1)
    def test_new_process_readonly_and_finalized_late_changes_preserve_history(self):
        self.register();self.complete();self.app.finalize('one','operator','final',self.c['id'])
        before=self.app.view('one',self.c['id'])
        code="from acquisition.bootstrap import build_outcomes;import json,sys;print(json.dumps(build_outcomes(sys.argv[1],read_only=True,clock=lambda:float(sys.argv[3])).view('one',sys.argv[2])))"
        p=subprocess.run([sys.executable,'-c',code,str(self.path),self.c['id'],str(self.now)],capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout),before)
        readonly=build_outcomes(self.path,clock=lambda:self.now,read_only=True)
        with self.assertRaises(Conflict):readonly.finalize('one','operator','new',self.c['id'])
        p=report(self.c,[event(self.c['assignments'][0],'clicked')],source='send',identity='late',watermark=self.now)
        with self.assertRaises(Conflict):self.ingest(p)
        self.assertEqual(self.app.view('one',self.c['id']),before)
    def test_saved_report_survives_source_loss_and_tampering_fails_closed(self):
        self.register();p=report(self.c,[event(self.c['assignments'][0],'qualified_enquiry')]);self.ingest(p)
        snap=self.app.snapshot('one',self.c['id'],'report');self.assertEqual(snap['snapshot'],p)
        with self.db.transaction() as db:db.execute("DELETE FROM learning_events WHERE kind='external_report'")
        with self.assertRaises(Conflict):self.app.snapshot('one',self.c['id'],'report')
    def test_fixture_and_external_data_never_enter_synthetic_memory(self):
        self.m['data_class']='operator_attested_external';self.register();self.complete();self.app.finalize('one','operator','final',self.c['id'])
        from acquisition.adapters.sqlite.learning import SqliteLearning
        self.assertEqual(SqliteLearning(self.db,lambda:self.now).memory('one','inventory')['groups'],[])
        self.assertEqual(self.app.view('one',self.c['id'])['finalization']['data_class'],'operator_attested_external')
        bad=copy.deepcopy(self.m);bad['mode']='SYNTHETIC_ONLY'
        with self.assertRaises(ValueError):self.app.register('one','operator','synthetic',bad)
    def test_cli_files_are_bounded_duplicate_safe_and_do_not_load_a_gateway(self):
        from acquisition.adapters.external_reports import ExternalOutcomeFiles
        files=ExternalOutcomeFiles()
        for raw in (b'{"x":1,"x":2}',b'{"x":{"y":1,"y":2}}',b'{"x":NaN}',b'[]',b'x'*(4*1024*1024+1)):
            with self.assertRaises(ValueError):files.parse(raw)
        path=Path(self.temp.name)/'manifest.json';path.write_text(json.dumps(self.m))
        p=subprocess.run([sys.executable,'-m','acquisition','--db',str(self.path),'--organization','one','outcomes-register','--actor','operator','--request-id','cli','--file',str(path)],capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,0,p.stderr);cid=json.loads(p.stdout)['cohort_id']
        p=subprocess.run([sys.executable,'-m','acquisition','--db',str(self.path),'--organization','one','outcomes-show','--cohort',cid],capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['missing'],6)


    def test_checkpoint_restores_exact_evidence_but_no_write_authority(self):
        from acquisition.bootstrap import build_workspace,build_workspace_checkpoint
        self.register();self.complete();self.app.finalize('one','operator','final',self.c['id'])
        parent=Path(self.temp.name);root=parent/'source';root.mkdir()
        with self.db.connect() as source,closing(sqlite3.connect(root/'conversations.sqlite')) as target:source.backup(target)
        build_outcomes(root/'conversations.sqlite',clock=lambda:self.now,verified_admissions=True)
        build_workspace(root,real_clock=lambda:self.now,verified_admissions=True)
        checkpoints=build_workspace_checkpoint();m=checkpoints.create(root,parent/'bundle')
        checkpoints.restore(parent/'bundle',parent/'restored',m['checkpoint_id'])
        path=parent/'restored'/'conversations.sqlite';before=path.read_bytes()
        restored=build_outcomes(path,clock=lambda:self.now)
        self.assertEqual(restored.view('one',self.c['id'])['finalization'],self.app.view('one',self.c['id'])['finalization'])
        with self.assertRaises(Conflict):restored.finalize('one','operator','restored',self.c['id'])
        self.assertEqual(path.read_bytes(),before)

    def test_member_native_binding_and_audit_deletions_cannot_shrink_the_denominator(self):
        from acquisition.adapters.sqlite.external_outcomes import member_key,record_key
        self.register();before=self.counts()
        with self.db.transaction() as db:
            db.execute('DELETE FROM learning_commands WHERE organization=? AND request_id=?',('one',member_key('business-0')))
        with self.assertRaises(Conflict):self.app.view('one',self.c['id'])
        self.assertEqual(self.counts()['learning_events'],before['learning_events'])

    def test_external_and_legacy_cohorts_share_the_business_independence_fence(self):
        from acquisition.bootstrap import build
        from acquisition.entrypoints.review_demo import run_review_demo
        for first in ('external','synthetic'):
            with self.subTest(first=first),tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'legacy.sqlite';clock=1792886400.
                native=build(path,clock=lambda:clock)
                demo=run_review_demo(native,'independence','fixture',Path(folder)/'review',str(path))
                org=demo['organization'];proposal=native.learning.source.accepted(org,demo['case_id'])
                app=build_outcomes(path,clock=lambda:NOW);m=manifest(org)
                for row,member in zip(m['assignments'],proposal['members']):row['business_id']=member['business_id']
                if first=='external':
                    app.register(org,'demo-operator','external',m)
                    with self.assertRaises(Conflict):native.learning.open(org,demo['case_id'],'demo-operator','legacy')
                else:
                    native.learning.open(org,demo['case_id'],'demo-operator','legacy')
                    with self.assertRaises(Conflict):app.register(org,'demo-operator','external',m)

    def test_postal_and_email_keep_channel_evidence_distinct_and_invalid_shapes_do_not_write(self):
        self.m['channel']='postal';self.m['sources'][0]['system']='postal-platform';self.register()
        p=report(self.c,[event(self.c['assignments'][0],'opened')],source='send')
        before=self.counts()
        with self.assertRaises(ValueError):self.ingest(p)
        for mutation in (lambda m:m.update(prior={'alpha':True,'beta':19}),lambda m:m.update(assignments=m['assignments'][:2]),
                         lambda m:m.update(attestation={'confirmed':False,'note':'bad','evidence_ref':'source','evidence_sha256':'0'*64})):
            bad=copy.deepcopy(self.m);mutation(bad)
            with self.assertRaises(ValueError):self.app.register('one','operator','invalid',bad)
        self.assertEqual(self.counts(),before)


    def test_clock_regression_after_last_write_rolls_back_and_future_history_is_labeled(self):
        self.register();store=self.app.store;command=store.command
        self.now=NOW-1;self.assertFalse(self.app.view('one',self.c['id'])['current'])
        with self.assertRaises(Conflict):self.ingest(report(self.c,[],watermark=NOW-1))
        self.now=NOW
        p=report(self.c,[event(self.c['assignments'][0],'qualified_enquiry')]);before=self.counts()
        def backwards(*args,**kwargs):
            value=command(*args,**kwargs)
            if len(args)>=7:self.now=NOW-1
            return value
        with patch.object(store,'command',side_effect=backwards),self.assertRaises(Conflict):self.ingest(p)
        self.now=NOW;self.assertEqual(self.counts(),before)
        self.complete();self.app.finalize('one','operator','final',self.c['id']);self.now=NOW
        view=self.app.view('one',self.c['id']);self.assertFalse(view['current']);self.assertEqual(view['posterior_groups'],[])
        self.assertEqual(view['status'],'historical_evidence_after_current_clock')

    def test_native_identities_are_independent_between_organizations(self):
        self.register();self.complete();one=self.app.finalize('one','operator','final',self.c['id'])
        self.roles.register_actor('two','operator',('operator',))
        two=self.app.register('two','operator','register',manifest(org='two'))
        self.assertNotEqual(two['cohort_id'],self.c['id'])
        self.assertEqual(self.app.view('two',two['cohort_id'])['missing'],6)
        with self.assertRaises(NotFound):self.app.view('two',self.c['id'])
        with self.assertRaises(NotFound):self.app.receipt('two','operator','finalize','final')
        self.assertEqual(self.app.view('one',self.c['id'])['finalization']['original_receipt'],one)

    def test_cohort_report_cap_is_atomic_and_existing_replay_remains_available(self):
        self.register();first=None
        for i in range(32):
            p=report(self.c,[],identity='bounded-'+str(i));r=self.ingest(p)
            if i==0:first=(p,r)
        before=self.counts()
        with self.assertRaises(Conflict):self.ingest(report(self.c,[],identity='overflow'))
        self.assertEqual(self.counts(),before)
        self.assertEqual(self.ingest(first[0],'replay-at-cap'),first[1])
        self.assertEqual(len(self.app.view('one',self.c['id'])['reports']),32)

    def complete_identical_cohort(self):
        self.register(value=identical_manifest());self.now=self.c['window_end']
        rows=[event(m,'qualified_enquiry' if m['arm']=='A' else 'no_qualified_enquiry',NOW if m['arm']=='A' else self.now) for m in self.c['assignments']]
        self.ingest(report(self.c,rows,identity='identical-final',final=True))

    def test_identical_creatives_keep_literal_counts_without_a_variant_winner(self):
        self.complete_identical_cohort();final=self.app.finalize('one','operator','final',self.c['id'])
        self.assertEqual([(g['arm'],g['trials'],g['successes']) for g in final['groups']],[('A',30,30),('B',30,0),('holdout',10,0)])
        comparison=final['comparisons'][0]
        self.assertEqual(comparison['action'],'no_creative_contrast')
        for key in ('candidate_arm','probability_beats_other','probability_beats_holdout'):self.assertIsNone(comparison[key])
        reopened=build_outcomes(self.path,clock=lambda:self.now,read_only=True)
        self.assertEqual(reopened.view('one',self.c['id'])['comparisons'],final['comparisons'])
        self.assertEqual(reopened.snapshot('one',self.c['id'],'identical-final')['snapshot']['pages'][0]['events'][0]['kind'],'qualified_enquiry')
        distinct=identical_manifest();distinct['organization']='two'
        for member in distinct['assignments']:
            if member['arm']=='B':
                member['creative_sha256']=self.m['assignments'][2]['creative_sha256']
                member['dispatch']['content_sha256']=member['creative_sha256']
        self.roles.register_actor('two','operator',('operator',))
        r=self.app.register('two','operator','register',distinct);c=self.app.view('two',r['cohort_id'])['cohort']
        rows=[event(m,'qualified_enquiry' if m['arm']=='A' else 'no_qualified_enquiry',NOW if m['arm']=='A' else self.now) for m in c['assignments']]
        self.app.ingest('two','operator','complete',c['id'],report(c,rows,identity='distinct-final',final=True))
        comparison=self.app.finalize('two','operator','final',c['id'])['comparisons'][0]
        self.assertEqual(comparison['action'],'consider_next_experiment');self.assertEqual(comparison['candidate_arm'],'A')
        self.assertGreaterEqual(comparison['probability_beats_other'],.9);self.assertGreaterEqual(comparison['probability_beats_holdout'],.95)

    def test_old_identical_creative_winner_is_historical_not_a_current_recommendation(self):
        self.complete_identical_cohort()
        legacy={'segment':'retail','candidate_arm':'A','action':'consider_next_experiment','probability_beats_other':1.,'probability_beats_holdout':1.,
                'intervals_90':{'A':[.4,.8],'B':[0.,.1],'holdout':[0.,.2]},'authority':'ADVISORY_REQUIRES_NEW_PROPOSAL_AND_APPROVAL',
                'policy':'external-advisory/v1','assignment_design':'operator_attested_randomized','limitation':'Historical v1 comparison.'}
        with patch('acquisition.adapters.sqlite.external_outcomes.external_comparisons',return_value=[legacy]):
            original=self.app.finalize('one','operator','old-final',self.c['id'])
        before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        reopened=build_outcomes(self.path,clock=lambda:self.now,read_only=True);view=reopened.view('one',self.c['id'])
        self.assertEqual(view['finalization']['original_receipt'],original)
        self.assertEqual(view['finalization']['observation'],'HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY')
        self.assertEqual(view['comparisons'][0]['action'],'no_creative_contrast')
        self.assertIsNone(view['comparisons'][0]['candidate_arm']);self.assertIsNone(view['comparisons'][0]['probability_beats_other'])
        self.assertEqual(view['comparisons'][0]['intervals_90'],legacy['intervals_90'])
        receipt=reopened.receipt('one','operator','finalize','old-final')
        self.assertEqual(receipt['comparisons'],[legacy]);self.assertEqual(receipt['observation'],'HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY')
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)
        for request_id in ('new-finalize','old-final','new-finalize'):
            replay=self.app.finalize('one','operator',request_id,self.c['id'])
            self.assertEqual(replay['observation'],'HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY')
            self.assertEqual(replay['original_receipt'],original)
            self.assertEqual(replay['comparisons'][0]['action'],'no_creative_contrast')
            self.assertIsNone(replay['comparisons'][0]['candidate_arm'])
        with self.db.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM learning_events WHERE kind='external_finalization'").fetchone()[0],1)
        cli=subprocess.run([sys.executable,'-m','acquisition','--db',str(self.path),'--organization','one','outcomes-finalize',
            '--cohort',self.c['id'],'--actor','operator','--request-id','cli-new-key'],capture_output=True,text=True,timeout=20)
        self.assertEqual(cli.returncode,0,cli.stderr);observed=json.loads(cli.stdout)
        self.assertEqual(observed['observation'],'HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY')
        self.assertEqual(observed['original_receipt'],original);self.assertEqual(observed['comparisons'][0]['action'],'no_creative_contrast')
        self.roles.register_actor('one','operator',('operator',),False);before=self.counts()
        with self.assertRaises(ValueError):self.app.finalize('one','operator','disabled-replay',self.c['id'])
        self.assertEqual(self.counts(),before)

    def save_legacy_report(self,payload,key):
        from acquisition.learning import external_report
        def old_validator(value,cohort,now):
            valid=copy.deepcopy(value);members={m['business_id']:m for m in cohort['assignments']}
            for page in valid['pages']:
                for row in page['events']:
                    if row['kind'] not in {'qualified_enquiry','no_qualified_enquiry'}:
                        row['occurred_at']=max(row['occurred_at'],members[row['business_id']]['dispatch']['at'])
            external_report(valid,cohort,now)
            return value,list({row['event_id']:row for page in value['pages'] for row in page['events']}.values())
        with patch('acquisition.adapters.sqlite.external_outcomes.external_report',side_effect=old_validator):return self.ingest(payload,key)

    def test_legacy_pre_send_snapshot_is_inspectable_with_excluded_current_diagnostics(self):
        self.register();member=self.c['assignments'][0];sent=member['dispatch']['at']
        original=report(self.c,[event(member,'opened',sent-1)],source='send',identity='legacy-early')
        imported=self.save_legacy_report(original,'legacy-import')
        before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        reopened=build_outcomes(self.path,clock=lambda:self.now,read_only=True)
        saved=reopened.snapshot('one',self.c['id'],'legacy-early')
        self.assertEqual(saved['snapshot'],original)
        self.assertEqual(saved['observation'],'HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY')
        self.assertEqual(saved['reconciliation']['status'],'needs_reconciliation')
        self.assertEqual(saved['reconciliation']['excluded_diagnostics'],1)
        self.assertEqual(saved['reconciliation']['issues'][0]['occurred_at'],sent-1)
        view=reopened.view('one',self.c['id'])
        self.assertEqual(view['event_counts'],{});self.assertEqual(view['business_counts'],{})
        self.assertEqual(view['status'],'needs_reconciliation')
        self.assertEqual(reopened.receipt('one','operator','import','legacy-import'),imported|{'observation':'HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY'})
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)
        result=subprocess.run([sys.executable,'-m','acquisition','--db',str(self.path),'--organization','one','outcomes-show-report',
            '--cohort',self.c['id'],'--report','legacy-early'],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['snapshot'],original)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before)
        for key in ('legacy-import','new-observation-key'):
            replay=self.ingest(original,key)
            self.assertEqual(replay['original_receipt'],imported);self.assertEqual(replay['observation'],'HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY')
        forged=copy.deepcopy(original);forged['report_id']='new-invalid-report';counts=self.counts()
        with self.assertRaisesRegex(ValueError,'predate'):self.ingest(forged,'new-invalid')
        self.assertEqual(self.counts(),counts)
        with self.assertRaises(Conflict):self.ingest(report(self.c,[event(member,'opened',sent)],source='send',identity='changed-event'))
        self.ingest(report(self.c,[event(member,'opened',sent,event_id='new-valid-open')],source='send',identity='valid-open'))
        self.assertEqual(self.app.view('one',self.c['id'])['event_counts'],{'opened':1})
        self.complete();final=self.app.finalize('one','operator','final',self.c['id'])
        self.assertEqual(final['reconciliation']['excluded_diagnostics'],1)
        self.assertEqual([(g['trials'],g['successes']) for g in final['groups']],[(2,1),(2,0),(2,1)])
        replay=self.app.finalize('one','operator','replay',self.c['id'])
        self.assertEqual(replay['original_receipt'],final);self.assertEqual(replay['reconciliation']['status'],'needs_reconciliation')
        with self.db.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM learning_events WHERE kind='external_finalization'").fetchone()[0],1)
        self.assertEqual(reopened.snapshot('one',self.c['id'],'legacy-early')['snapshot'],original)

    def test_snapshot_checks_only_its_bound_evidence_and_still_rejects_tampering(self):
        self.register();first=report(self.c,[event(self.c['assignments'][0],'qualified_enquiry')],identity='first')
        self.ingest(first);self.ingest(report(self.c,[event(self.c['assignments'][1],'qualified_enquiry')],identity='other'))
        with self.db.transaction() as db:
            db.execute("DELETE FROM learning_events WHERE organization=? AND kind='external_report' AND json_extract(payload,'$.payload.snapshot.report_id')=?",('one','other'))
        with self.assertRaises(Conflict):self.app.view('one',self.c['id'])
        self.assertEqual(self.app.snapshot('one',self.c['id'],'first')['snapshot'],first)
        with self.assertRaises(Conflict):self.app.snapshot('one',self.c['id'],'other')
        with self.assertRaises(NotFound):self.app.snapshot('foreign',self.c['id'],'first')
        with self.db.transaction() as db:
            db.execute("DELETE FROM learning_commands WHERE organization=? AND json_extract(receipt,'$.kind')='event' AND json_extract(receipt,'$.payload.event.event_id')=?",('one',first['pages'][0]['events'][0]['event_id']))
        with self.assertRaises(Conflict):self.app.snapshot('one',self.c['id'],'first')

    def test_legacy_diagnostic_reconciliation_deduplicates_and_bounds_issue_samples(self):
        self.register();member=self.c['assignments'][0];sent=member['dispatch']['at']
        rows=[event(member,'opened',sent-1,event_id='legacy-'+str(i)) for i in range(101)]
        first=report(self.c,rows,source='send',identity='legacy-many');self.save_legacy_report(first,'many')
        second=report(self.c,rows+rows,source='send',identity='legacy-cumulative');self.save_legacy_report(second,'cumulative')
        view=self.app.view('one',self.c['id']);r=view['reconciliation']
        self.assertEqual(r['excluded_diagnostics'],101);self.assertEqual(len(r['issues']),100);self.assertTrue(r['issues_truncated'])
        self.assertEqual(r['affected_reports'],['legacy-cumulative','legacy-many']);self.assertEqual(view['event_counts'],{})
        self.assertTrue(all(i['report_ids']==['legacy-cumulative','legacy-many'] for i in r['issues']))
        self.assertEqual(self.app.snapshot('one',self.c['id'],'legacy-cumulative')['snapshot'],second)

    def test_dispatch_diagnostics_reject_pre_send_events_atomically_and_accept_send_boundary(self):
        for channel,org in [('email','one'),('postal','two')]:
            if org!='one':self.roles.register_actor(org,'operator',('operator',))
            registered=self.app.register(org,'operator','register',manifest(org=org,channel=channel))
            cohort=self.app.view(org,registered['cohort_id'])['cohort'];member=cohort['assignments'][0];sent=member['dispatch']['at']
            kinds=['delivered','bounced','clicked','reply']+(['opened'] if channel=='email' else [])
            accepted=[]
            for kind in kinds:
                bad=report(cohort,[event(member,kind,sent,event_id=kind+'-valid'),event(member,kind,sent-1,event_id=kind+'-early')],source='send',identity=kind+'-report')
                before=self.counts()
                with self.subTest(channel=channel,kind=kind),self.assertRaises(ValueError):self.app.ingest(org,'operator',kind,cohort['id'],bad)
                self.assertEqual(self.counts(),before)
                with self.assertRaises(NotFound):self.app.snapshot(org,cohort['id'],bad['report_id'])
                accepted.extend([event(member,kind,sent,event_id=kind+'-valid'),event(member,kind,sent+1,event_id=kind+'-after')])
            self.app.ingest(org,'operator','accepted',cohort['id'],report(cohort,accepted,source='send',identity='accepted'))
            view=self.app.view(org,cohort['id']);self.assertEqual(view['event_counts'],dict.fromkeys(kinds,2))
            self.assertEqual(view['received'],0);self.assertEqual(view['posterior_groups'],[])
            # CRM records can observe organic enquiries anywhere in the frozen window.
            self.app.ingest(org,'operator','organic',cohort['id'],report(cohort,[event(member,'qualified_enquiry',sent-1)],identity='organic'))
            self.assertEqual(self.app.view(org,cohort['id'])['received'],1)

    def test_advisory_comparison_does_not_choose_a_treatment_that_loses_to_holdout(self):
        from acquisition.learning import external_registration,external_comparisons
        c=external_registration(self.m,'one',NOW)
        groups=[{'segment':'retail','arm':a,'creative_sha256':a,'trials':100,'successes':s,'alpha':1+s,'beta':119-s,'mean':(1+s)/120} for a,s in [('A',50),('B',10),('holdout',95)]]
        c['assignment_design']='operator_attested_randomized'
        comparison=external_comparisons(c,groups)[0]
        self.assertEqual(comparison['action'],'collect_more_evidence');self.assertLess(comparison['probability_beats_holdout'],.01)


class RemoteExternalOutcomeTests(unittest.TestCase):
    def test_hrana_commit_loss_and_new_connection_preserve_reports_and_count_once(self):
        from test_turso_storage import Wire
        from acquisition.adapters.turso import CommitUncertain
        from acquisition.adapters.turso.transport import RemoteUnavailable
        with tempfile.TemporaryDirectory() as folder:
            wire=Wire(Path(folder)/'wire.sqlite')
            try:
                db=wire.database(True)
                with patch('acquisition.bootstrap.build_database',return_value=db):app=build_outcomes(None,clock=lambda:NOW)
                SqliteReviews(db,lambda:NOW,None).register_actor('one','operator',('operator',))
                r=app.register('one','operator','register',manifest());c=app.view('one',r['cohort_id'])['cohort']
                app.store.clock=lambda:c['window_end'];rows=[event(m,'no_qualified_enquiry',c['window_end']) for m in c['assignments']]
                p=report(c,rows,final=True);send=db.send
                def lose(payload):
                    result=send(payload)
                    if any(s.get('stmt',{}).get('sql')=='COMMIT' for r in payload['requests'] for s in r.get('batch',{}).get('steps',[])):
                        raise RemoteUnavailable('Lost report COMMIT acknowledgement')
                    return result
                db.send=lose
                with self.assertRaises(CommitUncertain):app.ingest('one','operator','report',c['id'],p)
                db.send=send
                with patch('acquisition.bootstrap.build_database',return_value=wire.database()):reopened=build_outcomes(None,clock=lambda:c['window_end'])
                receipt=reopened.ingest('one','operator','report',c['id'],p);self.assertEqual(receipt['added_events'],6)
                final=reopened.finalize('one','operator','final',c['id'])
                self.assertEqual([(g['trials'],g['successes'],g['alpha'],g['beta']) for g in final['groups']],[(2,0,1,21)]*3)
                replay=reopened.finalize('one','operator','replay',c['id'])
                self.assertEqual(replay['original_receipt'],final);self.assertEqual(replay['observation'],'HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY')
                self.assertEqual(reopened.snapshot('one',c['id'],p['report_id'])['reconciliation']['status'],'clean')
                with reopened.store.database.connect() as conn:
                    self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],27)
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM model_calls').fetchone()[0],0)
            finally:wire.close()
