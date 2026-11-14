"""Frozen strategy interchange, independent selection and atomic observation boundaries."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from acquisition.audiences import (AudienceDecisions, ContactDirectory, DecisionRequest, FeatureBatch,
    FeatureRow, ScoreSemantics, StrategyObservation, StrategyResult, StrategyRun)
from acquisition.adapters.audience_strategies import (DeclaredSegmentCategorizer, TaxonomyOrderDecision,
                                                    ReverseTaxonomyDecision)
from acquisition.adapters.contact_fixtures import RecordedContactSource
from acquisition.adapters.local_profiles import LocalProfiles
from acquisition.adapters.sqlite.audience_decisions import SqliteAudienceDecisions
from acquisition.adapters.sqlite.contacts import SqliteContactDirectory
from acquisition.adapters.sqlite.database import Database
from acquisition.bootstrap import build_contact_directory, build_audience_decisions
from acquisition.contracts import Conflict, NotFound, canonical, digest


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026,11,14,tzinfo=timezone.utc).timestamp()
LIMITS = {'budget_pence':100,'unit_cost_pence':100,'max_candidates':10,'seed':42}


class AudienceStrategyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'application.sqlite'
        self.contacts = build_contact_directory(self.path,'one','fielddesk',lambda:NOW)
        self.snapshot = self.contacts.source.read('one','fielddesk-crm-a',1)
        self.assessment = self.contacts.prepare('one','evidence','fielddesk-crm-a',1,'email')['assessment_id']

    def service(self, strategy='taxonomy-order', key='fielddesk', clock=lambda:NOW):
        return build_audience_decisions(self.path,'one',key,strategy,clock)

    def custom_contacts(self, snapshot):
        profiles = LocalProfiles('one','fielddesk',ROOT/'config/profiles')
        source = RecordedContactSource('one',(snapshot,))
        store = SqliteContactDirectory(Database(Path(self.temp.name)/(snapshot.id+'.sqlite')),
                                        source,profiles,'fielddesk','v1',lambda:NOW)
        contacts = ContactDirectory(source,store)
        assessment = contacts.prepare('one','evidence',snapshot.connection.key,1,'email')['assessment_id']
        return contacts, assessment

    def composed(self, contacts=None, categorizer=None, decision=None):
        contacts = contacts or self.contacts
        profile = contacts.store._profile('one')
        categorizer = categorizer or DeclaredSegmentCategorizer(profile.taxonomy,profile.objective)
        decision = decision or TaxonomyOrderDecision(profile.taxonomy,profile.objective)
        return AudienceDecisions(categorizer,decision,SqliteAudienceDecisions(contacts.store,categorizer.spec,decision.spec))

    def prepare(self, service=None, request='decision', assessment=None, **limits):
        return (service or self.service()).prepare('one',request,assessment or self.assessment,**(LIMITS|limits))

    def count(self, contacts=None):
        with (contacts or self.contacts).store.database.connect() as db:
            return {t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in (
                'contact_commands','contact_assessments','contact_sources','runs','tasks','model_calls',
                'drafts','review_decisions','simulated_agency_jobs')}

    def request(self, service, **limits):
        return DecisionRequest(self.assessment,service.categorizer.spec,service.decision.spec,
            ScoreSemantics(),**(LIMITS|limits))

    def test_two_strategies_swap_through_unchanged_policy_for_two_profiles_and_restart(self):
        for key in ('fielddesk','iwoca'):
            contacts = build_contact_directory(self.path,'one',key,lambda:NOW)
            assessment = contacts.prepare('one',key+'-evidence',key+'-crm-a',1,'email')['assessment_id']
            source = contacts.source.read('one',key+'-crm-a',1)
            chosen = []
            for strategy, account in (('taxonomy-order',source.accounts[0]),('reverse-taxonomy-test',source.accounts[1])):
                request = key+'-'+strategy
                first = self.prepare(self.service(strategy,key),request,assessment)
                saved = first['decision']; plan = saved['plan']
                self.assertEqual(plan['status'],'complete')
                self.assertEqual(len(plan['allocations']),1)
                self.assertEqual(plan['allocations'][0]['experiment_unit'],account.experiment_unit)
                self.assertEqual(plan['conservative_cost_pence'],100)
                self.assertEqual(plan['policy'],'contact-selection/v1')
                self.assertEqual(saved['request']['decision']['score'],asdict(ScoreSemantics()))
                self.assertEqual(saved['feature_digest'],digest({'schema':'contact-features/v1','rows':saved['feature_batch']['rows']}))
                chosen.append(plan['allocations'][0]['experiment_unit'])
                # An actual new Python process must return the original complete frozen artifact.
                command = [sys.executable,'-m','acquisition.decision_cli','--db',str(self.path),
                    '--organization','one','--profile',key,'--strategy',strategy,'prepare',
                    '--request-id',request,'--assessment-id',assessment,'--budget-pence','100',
                    '--unit-cost-pence','100','--max-candidates','10','--seed','42']
                process = subprocess.run(command,cwd=ROOT,text=True,capture_output=True)
                self.assertEqual(process.returncode,0,process.stderr)
                replay = json.loads(process.stdout)
                self.assertEqual(replay['decision'],saved)
                self.assertEqual(replay['observation'],'historical_receipt')
                reproduce = '''
import json, sys
from dataclasses import asdict
from acquisition.bootstrap import build_audience_decisions
from acquisition.audiences import feature_batch_from, decision_request_from, StrategyRun
from acquisition.campaigns import contact_decision_plan
service = build_audience_decisions(sys.argv[1], 'one', sys.argv[2], sys.argv[3], read_only=True)
saved = service.inspect('one', sys.argv[4])['saved']['decision']
batch = feature_batch_from(saved['feature_batch'])
request = decision_request_from(saved['request'])
categories = service.categorizer.categorize(batch)
run = StrategyRun(categories, service.decision.decide(batch, categories))
with service.store.contacts.database.connect() as db:
    report = service.store.contacts.assessment(db, 'one', request.assessment_id)['report']
print(json.dumps({'run':asdict(run), 'plan':contact_decision_plan(batch, request, run, report)}))
'''
                process = subprocess.run([sys.executable,'-c',reproduce,str(self.path),key,strategy,request],
                                         cwd=ROOT,text=True,capture_output=True)
                self.assertEqual(process.returncode,0,process.stderr)
                self.assertEqual(json.loads(process.stdout),{'run':saved['run'],'plan':plan})
                self.assertEqual(plan['authority'],'none')
                self.assertFalse(plan['capacity_reserved'])
            self.assertNotEqual(*chosen)
        for table in ('runs','tasks','model_calls','drafts','review_decisions','simulated_agency_jobs'):
            self.assertEqual(self.count()[table],0)

    def test_score_contracts_cannot_silently_substitute_metrics_units_horizon_or_contrast(self):
        service = self.service()
        variants = (ScoreSemantics('response_propensity','probability_ppm',30),
                    ScoreSemantics('expected_value','GBP_minor_units',30),
                    ScoreSemantics('uplift','incremental_probability_ppm',30,'email_vs_no_contact'))
        for index, score in enumerate(variants):
            with patch.object(service.categorizer,'categorize',side_effect=AssertionError('must not infer')) as infer:
                saved = self.prepare(service,'metric-'+str(index),score=score)['decision']
            infer.assert_not_called()
            self.assertIn('unsupported_score_semantics',saved['plan']['issues'])
            self.assertEqual(saved['plan']['status'],'incomplete')
            self.assertEqual(saved['plan']['allocations'],[])
            self.assertEqual(saved['request']['score'],asdict(score))
        for kwargs in ({'metric':'fit','units':'probability_ppm'}, {'horizon_days':30},
                       {'metric':'response_propensity','units':'probability_ppm'},
                       {'metric':'uplift','units':'incremental_probability_ppm','horizon_days':30}):
            with self.assertRaises(ValueError): ScoreSemantics(**kwargs)
        # Equal numerical values under different horizons are still different contracts.
        self.assertNotEqual(replace(variants[0],horizon_days=60),variants[0])
        self.assertNotEqual(replace(variants[2],contrast='call_vs_no_contact'),variants[2])

    def test_partial_substituted_duplicate_and_invalid_interval_results_abstain_without_fallback(self):
        service = self.service()
        batch = service.store.capture('one',self.request(service))
        categories = service.categorizer.categorize(batch)
        original = service.decision.decide(batch,categories)
        cases = {
            'partial':replace(original,observations=original.observations[:-1]),
            'duplicate':replace(original,observations=(original.observations[0],)*len(original.observations)),
            'foreign_batch':replace(original,batch_id='features_other'),
            'foreign_strategy':replace(original,strategy_id='strategy_other'),
            'foreign_interpretation':replace(original,categories_id='strategy_result_other'),
            'interval':replace(original,observations=(replace(original.observations[0],uncertainty='interval',lower=80,upper=20),*original.observations[1:])),
            'invented_missingness':replace(original,observations=(replace(original.observations[0],missing=('segment',)),*original.observations[1:])),
            'wrong_scale':replace(original,observations=(replace(original.observations[0],value=1000000),*original.observations[1:])),
            'abstain':replace(original,observations=(replace(original.observations[0],value=None,abstention='insufficient_context'),*original.observations[1:])),
            'untyped':{'value':100},
        }
        for name, result in cases.items():
            with patch.object(service.decision,'decide',return_value=result) as infer:
                receipt = self.prepare(service,name)
                replay = self.prepare(service,name)
            self.assertEqual(infer.call_count,1)
            self.assertEqual(receipt['decision'],replay['decision'])
            self.assertEqual(receipt['decision']['plan']['status'],'incomplete',name)
            self.assertEqual(receipt['decision']['plan']['allocations'],[],name)
        # Deleting both the category and its dependent score cannot redefine required coverage.
        partial = replace(categories,observations=categories.observations[:-1])
        with patch.object(service.categorizer,'categorize',return_value=partial), patch.object(service.decision,'decide') as decision:
            result = self.prepare(service,'partial-categories')
        decision.assert_not_called()
        self.assertIn('incomplete_population',result['decision']['plan']['issues'])
        # Reordering complete observations cannot change deterministic selection or assignment.
        baseline = self.prepare(service,'ordered')['decision']['plan']['allocations']
        with patch.object(service.decision,'decide',return_value=replace(original,observations=tuple(reversed(original.observations)))):
            reordered = self.prepare(service,'reordered')['decision']['plan']['allocations']
        self.assertEqual(reordered,baseline)

    def test_provider_failures_are_explicit_frozen_and_never_retried_or_expose_exception_text(self):
        for stage in ('categorizer','decision'):
            service = self.service()
            adapter = getattr(service,stage)
            method = 'categorize' if stage=='categorizer' else 'decide'
            with patch.object(adapter,method,side_effect=RuntimeError('SECRET_PROVIDER_CREDENTIAL')) as infer:
                first = self.prepare(service,stage)
                second = self.prepare(service,stage)
            self.assertEqual(infer.call_count,1)
            self.assertEqual(first['decision'],second['decision'])
            self.assertEqual(first['decision']['plan']['status'],'incomplete')
            self.assertEqual(first['decision']['plan']['allocations'],[])
            self.assertIn('categorization_failure' if stage=='categorizer' else 'decision_failure',first['decision']['plan']['issues'])
            self.assertNotIn('SECRET_PROVIDER',canonical(first))

    def test_missing_features_and_unsupported_taxonomy_never_claim_complete_inference(self):
        missing = replace(self.snapshot,contacts=(replace(self.snapshot.contacts[0],accounts=()),*self.snapshot.contacts[1:]))
        contacts, assessment = self.custom_contacts(missing)
        result = self.prepare(self.composed(contacts),assessment=assessment)['decision']
        self.assertIn('missing_features',result['plan']['issues'])
        self.assertIn('evidence_incomplete',result['plan']['issues'])
        self.assertEqual(result['plan']['allocations'],[])
        self.assertTrue(any(r['missing']==['experiment_unit','segment'] for r in json.loads(canonical(result))['run']['categories']['observations']))
        categorizer = self.service().categorizer
        categorizer.spec = replace(categorizer.spec,taxonomy_id='taxonomy_unsupported')
        service = self.composed(categorizer=categorizer)
        with patch.object(categorizer,'categorize') as infer:
            result = self.prepare(service,'unsupported')['decision']
        infer.assert_not_called()
        self.assertIn('unsupported_taxonomy',result['plan']['issues'])
        self.assertEqual(result['plan']['allocations'],[])

    def test_maximal_scores_and_changed_categories_cannot_override_hard_exclusions_or_pressure(self):
        first = self.snapshot.contacts[0].ref.id
        variants = {
            'permission':replace(self.snapshot,permissions=tuple(replace(p,status='denied') if p.contact.id==first and p.channel=='email' else p for p in self.snapshot.permissions)),
            'contact_cap':replace(self.snapshot,pressure=tuple(replace(p,contact_count=2,account_count=2) if p.contact.id==first else replace(p,account_count=2) if p.experiment_unit==self.snapshot.accounts[0].experiment_unit else p for p in self.snapshot.pressure)),
            'account_cap':replace(self.snapshot,pressure=tuple(replace(p,account_count=4) if p.experiment_unit==self.snapshot.accounts[0].experiment_unit else p for p in self.snapshot.pressure)),
            'country':replace(self.snapshot,accounts=(replace(self.snapshot.accounts[0],country='US'),self.snapshot.accounts[1])),
        }
        for name, snapshot in variants.items():
            contacts, assessment = self.custom_contacts(snapshot)
            service = self.composed(contacts)
            decide = service.decision.decide
            categorize = service.categorizer.categorize
            def reclassify(batch):
                result = categorize(batch)
                return replace(result,observations=tuple(replace(r,category=batch.taxonomy.segments[-1].key) for r in result.observations))
            def maximal(batch, categories):
                result = decide(batch,categories)
                return replace(result,observations=tuple(replace(r,value=100 if r.contact_id==first else 0) for r in result.observations))
            with patch.object(service.categorizer,'categorize',side_effect=reclassify), patch.object(service.decision,'decide',side_effect=maximal):
                plan = self.prepare(service,assessment=assessment,budget_pence=10000)['decision']['plan']
            self.assertEqual(plan['status'],'complete',name)
            self.assertNotIn(first,{r['contact_id'] for r in plan['allocations']},name)
            self.assertTrue(any(r['contact_id']==first for r in plan['excluded']),name)
        # A current review-owned suppression is a separate authoritative exclusion.
        with self.contacts.store.database.transaction() as db:
            db.execute('INSERT INTO review_suppressions VALUES(?,?,?,?,?)',
                       ('one',self.snapshot.accounts[0].business_id,'reviewer','do not acquire',NOW))
        assessment = self.contacts.prepare('one','suppressed','fielddesk-crm-a',1,'email')['assessment_id']
        plan = self.prepare(assessment=assessment,budget_pence=10000)['decision']['plan']
        self.assertEqual({r['experiment_unit'] for r in plan['allocations']},{self.snapshot.accounts[1].experiment_unit})

    def test_budget_caps_one_contact_per_account_and_assignment_are_independent_of_ranking(self):
        allocations = []
        for strategy in ('taxonomy-order','reverse-taxonomy-test'):
            plan = self.prepare(self.service(strategy),strategy,budget_pence=10000,max_candidates=500)['decision']['plan']
            self.assertEqual(len(plan['allocations']),2)
            self.assertEqual(len({r['experiment_unit'] for r in plan['allocations']}),2)
            allocations.append({r['experiment_unit']:r['arm'] for r in plan['allocations']})
        self.assertEqual(*allocations)
        for index,(budget,cost,maximum,expected) in enumerate(((0,100,10,0),(99,100,10,0),(199,100,10,1),(10000,100,1,1))):
            plan = self.prepare(request='limit-'+str(index),budget_pence=budget,unit_cost_pence=cost,max_candidates=maximum)['decision']['plan']
            self.assertEqual(len(plan['allocations']),expected)
            self.assertLessEqual(plan['conservative_cost_pence'],budget)
        for limits in ({'budget_pence':True},{'unit_cost_pence':0},{'max_candidates':501},{'seed':-1}):
            with self.assertRaises(ValueError): self.prepare(request='invalid',**limits)

    def test_coordinated_rehashed_feature_substitution_cannot_publish(self):
        service = self.service(); request = self.request(service)
        batch = service.store.capture('one',request)
        before = self.count()
        variants = (replace(batch,rows=batch.rows[:-1]),
                    replace(batch,rows=(replace(batch.rows[0],segment=next(s.key for s in batch.taxonomy.segments if s.key!=batch.rows[0].segment)),*batch.rows[1:])),
                    replace(batch,organization='other'),replace(batch,readiness_digest='replacement'))
        for candidate in variants:
            categories = service.categorizer.categorize(candidate)
            run = StrategyRun(categories,service.decision.decide(candidate,categories))
            with self.assertRaisesRegex(Conflict,'independently reconstructed'):
                service.store.publish('one','forged',request,candidate,run)
            self.assertEqual(self.count(),before)
        with self.assertRaisesRegex(Conflict,'installed strategy'):
            service.store.capture('one',replace(request,decision=replace(request.decision,model_version='replacement')))

    def test_objection_or_source_refresh_during_inference_cannot_publish_stale_work(self):
        for kind in ('objection','refresh'):
            service = self.service(); original = service.decision.decide
            before = self.count()['contact_commands']
            def changed(batch,categories):
                if kind=='objection': self.contacts.object('one','change-'+kind,self.snapshot.contacts[0].ref.id,'all','all','stop')
                else: self.contacts.refresh('one','change-'+kind,'fielddesk-crm-a',2)
                return original(batch,categories)
            # Re-prepare after each deliberate evidence change.
            assessment = self.contacts.prepare('one','fresh-'+kind,'fielddesk-crm-a',1,'email')['assessment_id']
            before = self.count()['contact_commands']
            with patch.object(service.decision,'decide',side_effect=changed):
                with self.assertRaisesRegex(Conflict,'no longer applicable'):
                    self.prepare(service,kind,assessment)
            self.assertEqual(self.count()['contact_commands'],before+1)

    def test_postwrite_change_or_expiry_rolls_back_the_whole_decision(self):
        service = self.service(); record = service.store.contacts._record
        before = self.count()
        def inject(db,organization,request_id,inputs,receipt):
            result = record(db,organization,request_id,inputs,receipt)
            payload = {'organization':organization,'channel':'all','purpose':'all',
                       'contact_id':self.snapshot.contacts[0].ref.id,'recorded_at':NOW,'reason':'stop'}
            db.execute('INSERT INTO contact_objections VALUES(?,?,?)',
                       (organization,'objection_'+digest(payload),canonical(payload)))
            return result
        with patch.object(service.store.contacts,'_record',side_effect=inject):
            with self.assertRaisesRegex(Conflict,'no longer applicable'): self.prepare(service)
        self.assertEqual(self.count(),before)
        with self.contacts.store.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM contact_objections').fetchone()[0],0)
        now = [NOW]
        service = self.service(clock=lambda:now[0]); record = service.store.contacts._record
        def expire(*args):
            result = record(*args); now[0] = self.snapshot.expires_at
            return result
        with patch.object(service.store.contacts,'_record',side_effect=expire):
            with self.assertRaisesRegex(Conflict,'no longer applicable'): self.prepare(service)
        self.assertEqual(self.count(),before)

    def test_exact_replay_preserves_historical_artifact_and_current_applicability_is_separate(self):
        first = self.prepare(); before = self.count()
        self.contacts.object('one','stop',self.snapshot.contacts[0].ref.id,'email','acquisition','stop')
        current = self.service()
        with patch.object(current.categorizer,'categorize') as infer:
            with self.assertRaises(Conflict): self.prepare(current,'new-work-with-old-assessment')
        infer.assert_not_called()
        service = self.service(clock=lambda:self.snapshot.expires_at+1)
        with patch.object(service.categorizer,'categorize') as infer:
            replay = self.prepare(service)
        infer.assert_not_called()
        self.assertEqual(first['decision'],replay['decision'])
        self.assertEqual(replay['observation'],'historical_receipt')
        inspected = service.inspect('one','decision')
        self.assertFalse(inspected['currently_applicable'])
        self.assertFalse(inspected['complete_proposal'])
        self.assertEqual(inspected['saved']['decision'],first['decision'])
        for changes in ({'budget_pence':101},{'seed':43},{'unit_cost_pence':101},{'max_candidates':9}):
            with self.assertRaisesRegex(Conflict,'different exact inputs'): self.prepare(service,**changes)
        with self.assertRaises(Conflict): self.prepare(self.service('reverse-taxonomy-test'))
        self.assertEqual(self.count()['contact_commands'],before['contact_commands']+1)

    def test_organization_request_namespaces_and_read_only_stores_fence_decisions(self):
        first = self.prepare(); before = self.count()
        with self.assertRaises(NotFound): self.service().inspect('other','decision')
        foreign = build_audience_decisions(self.path,'other','fielddesk',clock=lambda:NOW)
        with self.assertRaises(NotFound): foreign.prepare('other','foreign',self.assessment,**LIMITS)
        with self.assertRaises(Conflict): self.prepare(request='evidence')
        readonly = build_audience_decisions(self.path,'one','fielddesk',clock=lambda:NOW,read_only=True)
        self.assertEqual(readonly.inspect('one','decision')['saved']['decision'],first['decision'])
        with self.assertRaises(Conflict): self.prepare(readonly,request='readonly')
        service = self.service()
        decide = service.decision.decide
        def seal(batch,categories):
            Database(self.path,verified_admissions=True,clock=lambda:NOW)
            return decide(batch,categories)
        with patch.object(service.decision,'decide',side_effect=seal):
            with self.assertRaises(Conflict): self.prepare(service,request='sealed')
        with self.assertRaises(Conflict): self.service()
        self.assertEqual(self.count(),before)
        (self.path.parent/'.acquisition-checkpoint.json').write_text('{}')
        saved_bytes = self.path.read_bytes()
        readonly = build_audience_decisions(self.path,'one','fielddesk',clock=lambda:NOW,read_only=True)
        self.assertEqual(readonly.inspect('one','decision')['saved']['decision'],first['decision'])
        with self.assertRaises(Conflict): self.prepare(readonly,request='restored')
        self.assertEqual(self.path.read_bytes(),saved_bytes)

    def test_concurrent_different_inputs_publish_one_complete_receipt(self):
        def attempt(budget):
            try: return self.prepare(self.service(),budget_pence=budget)
            except Conflict: return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt,(100,200)))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(self.count()['contact_commands'],2)
        saved = self.service().inspect('one','decision')['saved']['decision']
        self.assertEqual(saved,next(r['decision'] for r in results if r is not None))


if __name__=='__main__':
    unittest.main()
