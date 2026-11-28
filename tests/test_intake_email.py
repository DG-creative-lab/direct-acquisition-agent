"""Exact intake-owned email material, review-only export authority and recovery."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
import hashlib,json,os,subprocess,sys
from pathlib import Path
import unittest
from unittest.mock import patch
import test_intake_preparation as foundation
NOW=foundation.NOW
from acquisition.bootstrap import build_intake
from acquisition.contracts import Conflict,NotFound,canonical,digest
from acquisition.adapters.sqlite.reviews import SqliteReviews


class IntakeEmailTests(unittest.TestCase):
    seed=foundation.IntakePreparationTests.seed
    review_inputs=foundation.IntakePreparationTests.review_inputs
    command=foundation.IntakePreparationTests.command
    def setUp(self):
        foundation.IntakePreparationTests.setUp(self)
        self.app.save_brief('one','operator','email-brief',replace(self.brief_draft,channels=('email',)),brief_id=self.brief['id'],expected_revision=1)
        self.context_request='email-review';self.review_inputs(2)
        self.roles=SqliteReviews(self.app.store.database,lambda:self.now,None)
        self.roles.initialize_actor('one','operator',('operator',))
        self.roles.initialize_actor('one','reviewer',('reviewer',))
    def preview(self):return self.app.emails.preview(self.organization,self.context_request)
    def prepare(self,key='email',request=None):return self.app.emails.prepare(self.organization,'operator',key,request or self.command())
    def view(self,key='email'):return self.app.email_reviews.view(self.organization,key)
    def approve(self,key='approve',request='email',subject=None,ttl=3600):
        return self.app.email_reviews.decide(self.organization,'reviewer',key,request,subject or self.view(request)['subject']['id'],'approve','Reviewed the exact complete synthetic email batch.',ttl)['value']
    def export(self,key='export',request='email',approval=None,subject=None):
        a=approval or self.approve();return self.app.email_reviews.export(self.organization,'operator',key,request,subject or self.view(request)['subject']['id'],a['id'])
    def counts(self):
        with self.app.store.database.connect() as db:
            return {t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('intake_requests','review_commands','model_calls','runs','simulated_agency_jobs','engagement_simulations')}

    def test_own_selected_facts_permission_evidence_exact_rendering_and_approved_export(self):
        before=self.counts();p=self.preview();self.assertEqual(p['blockers'],[]);self.assertEqual(self.counts(),before)
        self.assertEqual(p['settings']['size'],6)
        r=self.prepare();batch=r['batch'];self.assertEqual(batch['profile']['channel'],'email')
        self.assertEqual(batch['binding']['requirements']['channels'],['email'])
        self.assertEqual(batch['cost_minor'],12)
        self.assertEqual(len(batch['content']['rows']),6)
        self.assertNotIn('UNSELECTED',canonical(batch));self.assertNotIn('iwoca.co.uk',canonical(batch))
        for row in batch['content']['rows']:
            email=row['email'];self.assertIn('Aster offers a retail advice package.\n\nSubject to the published terms.',email['text'])
            self.assertEqual(email['cta_url'],'https://aster.invalid/terms')
            self.assertIn('Read Aster terms.',email['text']);self.assertIn('https://aster.invalid/terms',email['html'])
            self.assertTrue(email['to'].endswith('.invalid'));self.assertTrue(email['from'].endswith('.invalid'))
            self.assertIn('unsubscribe',email['unsubscribe_url'])
            self.assertEqual(row['recipient_facts'],[])
        view=self.view();self.assertTrue(view['review_ready']);self.assertFalse(view['approval_valid'])
        with self.assertRaises(Conflict):self.app.email_reviews.export('one','operator','bad','email',view['subject']['id'],'postal-approval')
        approval=self.approve();receipt=self.export(approval=approval)
        data=self.app.email_reviews.download('one','operator','export',view['subject']['id'])
        self.assertEqual(hashlib.sha256(data).hexdigest(),receipt['value']['content_sha256'])
        exported=json.loads(data);self.assertEqual(exported['emails'],batch['content']['rows'])
        self.assertEqual(exported['live_send_authority'],'none')
        self.assertEqual(exported['approval']['purpose'],'synthetic_intake_email_export/v1')
        self.assertEqual(self.export(approval=approval),receipt)
        for table in ('model_calls','runs','simulated_agency_jobs','engagement_simulations'):self.assertEqual(self.counts()[table],0,table)

    def test_exact_source_confirmation_actor_scope_and_changed_request(self):
        command=self.command();self.prepare(request=command)
        with self.assertRaises(Conflict):self.prepare(request=replace(command,evidence=replace(command.evidence,note='Changed exact input.')))
        with self.assertRaises(Conflict):self.prepare('another-key',command)
        with self.assertRaises(NotFound):self.app.emails.request('foreign','email')
        with self.assertRaises((NotFound,ValueError)):self.app.emails.prepare('foreign','operator','email',command)
        with self.assertRaises(ValueError):self.app.email_reviews.decide('one','operator','bad','email',self.view()['subject']['id'],'approve','Wrong role.',60)
        with self.assertRaises(Conflict):self.approve(subject='another-subject')
        with self.assertRaises(Conflict):self.prepare('missing',replace(command,evidence=replace(command.evidence,reference_ids=('foreign',))))

    def test_expiry_revocation_supersession_and_actor_generation_block_even_cached_exports(self):
        self.prepare();a=self.approve();self.export(approval=a);subject=self.view()['subject']['id']
        self.app.email_reviews.revoke('one','reviewer','revoke','email',a['id'],'Withdraw exact export authority.')
        for f in (lambda:self.export(approval=a),lambda:self.app.email_reviews.download('one','operator','export',subject)):
            with self.assertRaises(Conflict):f()
        a=self.approve('new-approve');self.export('new-export',approval=a)
        self.roles.register_actor('one','reviewer',('reviewer',),False)
        with self.assertRaises(ValueError):self.app.email_reviews.download('one','operator','new-export',self.view()['subject']['id'])
        self.roles.register_actor('one','reviewer',('reviewer',),True)
        a=self.approve('fresh-approve',ttl=1);subject=self.view()['subject']['id'];self.export('fresh-export',approval=a)
        self.now+=1
        with self.assertRaises(Conflict):self.app.email_reviews.download('one','operator','fresh-export',subject)
        self.assertFalse(self.view()['approval_valid'])

    def test_source_edits_stale_review_and_exact_original_preparation_remains_inspectable(self):
        command=self.command();first=self.prepare(request=command);a=self.approve();self.export(approval=a);subject=self.view()['subject']['id']
        self.app.save_company('one','operator','edit',replace(self.company_draft,description='Changed source assertion.'),company_id=self.company['id'],expected_revision=1)
        with self.assertRaises(Conflict):self.app.email_reviews.download('one','operator','export',subject)
        self.assertFalse(self.view()['review_ready'])
        historical=self.prepare(request=command);self.assertEqual(historical['batch'],first['batch']);self.assertFalse(historical['current'])
        with self.assertRaises(Conflict):self.approve('stale',subject=subject)

    def test_suppression_and_stop_epoch_changes_require_review_and_never_export_ineligible_recipients(self):
        self.prepare();a=self.approve();self.export(approval=a);subject=self.view()['subject']['id']
        account=self.view()['batch']['contacts']['accounts'][0]
        with self.app.store.database.transaction() as db:
            db.execute('INSERT INTO review_suppressions VALUES(?,?,?,?,?)',('one',account['business_id'],'reviewer','Synthetic suppression',self.now))
        self.assertFalse(self.view()['review_ready'])
        with self.assertRaises(Conflict):self.app.email_reviews.download('one','operator','export',subject)

    def test_preparation_rollback_lost_ack_two_contenders_and_process_reopen_preserve_original(self):
        command=self.command();db=self.app.store.database;real=db.transaction
        @contextmanager
        def lose_ack():
            with real() as c:yield c
            raise OSError('lost commit acknowledgement')
        with patch.object(db,'transaction',lose_ack),self.assertRaises(OSError):self.prepare(request=command)
        first=self.prepare(request=command);self.assertTrue(first['replayed'])
        def work(_):return build_intake(self.path,clock=lambda:NOW).emails.prepare('one','operator','email',command)
        with ThreadPoolExecutor(max_workers=2) as pool:values=list(pool.map(work,range(2)))
        self.assertEqual(values[0]['batch'],values[1]['batch'])
        program="from acquisition.bootstrap import build_intake;import json,sys;print(json.dumps(build_intake(sys.argv[1],read_only=True,clock=lambda:float(sys.argv[2])).emails.request('one','email')))"
        child=subprocess.run([sys.executable,'-c',program,str(self.path),str(self.now)],env=dict(os.environ,PYTHONPATH='src'),capture_output=True,text=True,timeout=20)
        self.assertEqual(child.returncode,0,child.stderr);self.assertEqual(json.loads(child.stdout)['batch'],first['batch'])
        self.assertEqual(self.counts()['model_calls'],0)

    def test_two_authored_companies_keep_distinct_email_material_and_approval_subjects(self):
        first=self.prepare();first_approval=self.approve()
        self.seed('Birch',suffix='-birch')
        self.app.save_brief('one','operator','birch-email',replace(self.brief_draft,channels=('email',)),brief_id=self.brief['id'],expected_revision=1)
        self.context_request='birch-email-review';self.review_inputs(2)
        second=self.prepare('birch')
        self.assertNotEqual(first['batch']['id'],second['batch']['id'])
        self.assertNotIn('Aster',canonical(second['batch']))
        self.assertIn('Birch offers a retail advice package.',canonical(second['batch']))
        with self.assertRaises(Conflict):self.export('cross',request='birch',approval=first_approval)
        a=self.approve('birch-approval',request='birch');self.export('birch-export',request='birch',approval=a)
        self.assertEqual(self.counts()['model_calls'],0)

    def test_final_expiry_and_failed_review_insert_roll_back_all_receipts(self):
        store=self.app.emails.store;original=store.view;before=self.counts()
        def expired(db,org,key,now,replayed=True):return original(db,org,key,self.context['review_expires_at'],replayed)
        with patch.object(store,'view',side_effect=expired),self.assertRaises(Conflict):self.prepare()
        self.assertEqual(self.counts(),before)
        self.prepare();review_store=self.app.email_reviews.store;command=review_store.command;before=self.counts()
        def fail_after_write(*args,**kwargs):
            command(*args,**kwargs);raise OSError('after review receipt before commit')
        with patch.object(review_store,'command',side_effect=fail_after_write),self.assertRaises(OSError):self.approve()
        self.assertEqual(self.counts(),before)
        self.assertFalse(self.view()['approval_valid'])
        approval=self.approve();subject=self.view()['subject']['id'];before=self.counts()
        with patch.object(review_store,'command',side_effect=fail_after_write),self.assertRaises(OSError):self.export(approval=approval)
        self.assertEqual(self.counts(),before)
        self.export(approval=approval)
        authorize=review_store.authorize;calls=0
        def expire_before_bytes(*args):
            nonlocal calls
            calls+=1
            if calls==2:self.now=approval['expires_at']
            return authorize(*args)
        with patch.object(review_store,'authorize',side_effect=expire_before_bytes),self.assertRaises(Conflict):
            self.app.email_reviews.download('one','operator','export',subject)

    def test_review_and_export_lost_ack_reconcile_original_without_renewing_expiry(self):
        self.prepare();database=self.app.store.database;real=database.transaction
        @contextmanager
        def lose_ack():
            with real() as c:yield c
            raise OSError('committed but acknowledgement lost')
        with patch.object(database,'transaction',lose_ack),self.assertRaises(OSError):self.approve()
        original=self.view()['approval'];self.now+=10
        replay=self.approve();self.assertEqual(replay,original)
        with patch.object(database,'transaction',lose_ack),self.assertRaises(OSError):self.export(approval=original)
        self.now+=10
        self.export(approval=original)
        self.assertEqual(self.view()['approval']['expires_at'],original['expires_at'])

    def test_readonly_verified_store_missing_role_and_changed_review_commands_fail_closed(self):
        self.prepare();a=self.approve();self.export(approval=a);subject=self.view()['subject']['id']
        inspection=build_intake(self.path,clock=lambda:self.now,read_only=True)
        with self.assertRaises(Conflict):inspection.email_reviews.download('one','operator','export',subject)
        with self.assertRaises(Conflict):self.app.email_reviews.decide('one','reviewer','approve','email',subject,'reject','Changed existing command.',3600)
        build_intake(self.path,verified_admissions=True,clock=lambda:self.now)
        with self.assertRaises(Conflict):self.app.email_reviews.download('one','operator','export',subject)
        self.assertEqual(self.app.emails.request('one','email')['batch']['id'],self.view()['batch']['id'])

    def test_email_profile_preserves_postal_contract_and_roles_are_not_recreated_after_history(self):
        from acquisition.campaigns import CampaignProfile,EmailCampaignProfile,campaign_profile_from
        self.prepare();profile=campaign_profile_from(self.view()['batch']['profile'])
        self.assertIs(type(profile),EmailCampaignProfile)
        with self.assertRaises(ValueError):CampaignProfile(profile.key,profile.version,profile.company,profile.product_key,profile.product_profile_id,profile.taxonomy,channel='email')
        self.roles.register_actor('one','local-reviewer',('reviewer',),False)
        self.app.initialize_email_defaults('one')
        with self.app.store.database.transaction() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM review_actors WHERE organization='one' AND id='local-operator'").fetchone())
            self.assertEqual(db.execute("SELECT enabled FROM review_actors WHERE organization='one' AND id='local-reviewer'").fetchone()[0],0)
            db.execute("DELETE FROM review_actors WHERE organization='one' AND id='reviewer'")
        with self.assertRaises(ValueError):self.approve()
        self.assertFalse(self.view()['approval_valid'])


    def test_real_checkpoint_preserves_email_history_without_export_authority(self):
        import sqlite3
        from acquisition.bootstrap import build_workspace,build_workspace_checkpoint
        self.prepare();a=self.approve();self.export(approval=a);subject=self.view()['subject']['id']
        parent=Path(self.temp.name);root=parent/'source';root.mkdir()
        with self.app.store.database.connect() as source,sqlite3.connect(root/'conversations.sqlite') as target:
            source.backup(target)
        build_intake(root/'conversations.sqlite',clock=lambda:self.now,verified_admissions=True)
        build_workspace(root,real_clock=lambda:self.now,verified_admissions=True)
        checkpoints=build_workspace_checkpoint();manifest=checkpoints.create(root,parent/'bundle')
        checkpoints.restore(parent/'bundle',parent/'restored',manifest['checkpoint_id'])
        restored=build_intake(parent/'restored'/'conversations.sqlite',clock=lambda:self.now)
        self.assertEqual(restored.emails.request('one','email')['batch'],self.view()['batch'])
        self.assertFalse(restored.email_reviews.view('one','email')['approval_valid'])
        with self.assertRaises(Conflict):restored.email_reviews.download('one','operator','export',subject)
        with self.assertRaises(Conflict):restored.email_reviews.decide('one','reviewer','new','email',subject,'approve','Restored history is not authority.',60)


class IntakeEmailHttpTests(unittest.TestCase):
    import test_workspace as workspace_module
    setUp=workspace_module.WorkspaceHttpTests.setUp
    stop=workspace_module.WorkspaceHttpTests.stop
    request=workspace_module.WorkspaceHttpTests.request
    seed=foundation.IntakePreparationTests.seed
    review_inputs=foundation.IntakePreparationTests.review_inputs
    def test_exact_workspace_prepare_review_and_download_with_trusted_scope(self):
        self.now=NOW;self.app=build_intake(self.root/'data'/'conversations.sqlite',clock=lambda:self.now)
        self.seed(organization='local-conversations')
        self.app.save_brief(self.organization,'operator','email-brief',replace(self.brief_draft,channels=('email',)),brief_id=self.brief['id'],expected_revision=1)
        self.context_request='email-review';self.review_inputs(2)
        status,body,_=self.request('/api/intake/emails/eligibility?context_request_id=email-review')
        self.assertEqual(status,200,body);p=json.loads(body);self.assertEqual(p['blockers'],[])
        command={'request_id':'email:test','context_request_id':'email-review','preview_id':p['id'],
            'evidence':{'reference_ids':[r['id'] for r in p['references']],'checked_on':p['checked_on'],'review_days':1,
             'note':'Checked exact official wording and qualifications.','confirmed_official_sources':True,'confirmed_exact_wording':True},
             'confirmed_synthetic_preparation':True}
        h={'X-Intake-Store':p['store_id']}
        for bad in ({'Origin':'https://attacker.invalid'},{'X-Workspace-Token':''},{'Host':'attacker.invalid'}):
            self.assertEqual(self.request('/api/intake/emails/prepare',command,h|bad)[0],403)
        self.assertEqual(self.request('/api/intake/emails/prepare',command,h|{'X-Intake-Store':'other'})[0],409)
        for field in ('organization','actor','model'):
            self.assertEqual(self.request('/api/intake/emails/prepare',command|{field:'substitute'},h)[0],409)
        status,body,_=self.request('/api/intake/emails/prepare',command,h);self.assertEqual(status,200,body)
        status,body,_=self.request('/api/intake/emails/requests/email%3Atest');self.assertEqual(status,200,body);v=json.loads(body)
        decision={'request_id':'approve','preparation_request_id':'email:test','subject_id':v['subject']['id'],'decision':'approve','reason':'Reviewed every email and permission.','ttl_seconds':3600}
        status,body,_=self.request('/api/intake/emails/decision',decision,h);self.assertEqual(status,200,body);approval=json.loads(body)['value']['id']
        export={'request_id':'export','preparation_request_id':'email:test','subject_id':v['subject']['id'],'approval_id':approval}
        status,body,_=self.request('/api/intake/emails/export',export,h);self.assertEqual(status,200,body);r=json.loads(body)
        self.assertNotIn('content',r['value'])
        path='/api/intake/emails/exports/export?subject_id='+v['subject']['id']
        status,body,headers=self.request(path);self.assertEqual(status,200,body)
        self.assertIn('attachment',headers['Content-Disposition']);self.assertEqual(json.loads(body)['emails'],v['batch']['content']['rows'])
        status,body,_=self.request('/api/intake/emails/commands/export/export');self.assertEqual(status,200,body)
        self.assertNotIn('content',json.loads(body)['value'])
        revoke={'request_id':'revoke','preparation_request_id':'email:test','approval_id':approval,'reason':'Withdraw export authority.'}
        self.assertEqual(self.request('/api/intake/emails/revoke',revoke,h)[0],200)
        self.assertEqual(self.request(path)[0],409)


class RemoteIntakeEmailTests(unittest.TestCase):
    def test_hrana_preparation_review_export_and_uncertain_commit_preserve_original(self):
        import tempfile
        from test_turso_storage import Wire
        from acquisition.adapters.turso import CommitUncertain
        from acquisition.adapters.turso.transport import RemoteUnavailable
        with tempfile.TemporaryDirectory() as d:
            wire=Wire(Path(d)/'remote.sqlite')
            try:
                database=wire.database(True)
                with patch('acquisition.bootstrap.build_database',return_value=database):app=build_intake(None,clock=lambda:NOW)
                case=IntakeEmailTests();case.app=app;case.now=NOW;case.seed()
                app.save_brief('one','operator','email-brief',replace(case.brief_draft,channels=('email',)),brief_id=case.brief['id'],expected_revision=1)
                case.context_request='email-review';case.review_inputs(2)
                roles=SqliteReviews(database,lambda:NOW,None);roles.initialize_actor('one','operator',('operator',));roles.initialize_actor('one','reviewer',('reviewer',))
                request=case.command();send=database.send
                def lose_ack(payload):
                    result=send(payload)
                    if any(s.get('stmt',{}).get('sql')=='COMMIT' for r in payload['requests'] for s in r.get('batch',{}).get('steps',[])):
                        raise RemoteUnavailable('Lost email preparation COMMIT acknowledgement')
                    return result
                database.send=lose_ack
                with self.assertRaises(CommitUncertain):case.prepare(request=request)
                database.send=send
                with patch('acquisition.bootstrap.build_database',return_value=wire.database()):reopened=build_intake(None,clock=lambda:NOW)
                first=reopened.emails.prepare('one','operator','email',request);self.assertTrue(first['replayed'])
                case.app=reopened;a=case.approve();receipt=case.export(approval=a)
                data=reopened.email_reviews.download('one','operator','export',case.view()['subject']['id'])
                self.assertEqual(hashlib.sha256(data).hexdigest(),receipt['value']['content_sha256'])
                self.assertEqual(json.loads(data)['emails'],first['batch']['content']['rows'])
                with reopened.store.database.connect() as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0],0)
                    self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],28)
            finally:wire.close()
