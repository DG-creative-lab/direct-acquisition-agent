"""Contact identity, source authority, permission and immutable history boundaries."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from acquisition.audiences import ContactDirectory, ContactAccount, contact_snapshot_from
from acquisition.bootstrap import build_contact_directory
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.adapters.contact_fixtures import RecordedContactSource, synthetic_contact_snapshots
from acquisition.adapters.local_profiles import LocalProfiles
from acquisition.adapters.sqlite.contacts import SqliteContactDirectory
from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.audiences import SqliteAudiences
from acquisition.adapters.synthetic import generate


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026,11,13,tzinfo=timezone.utc).timestamp()


class ContactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'contacts.sqlite'

    def service(self, key='fielddesk', organization='one', clock=lambda:NOW):
        return build_contact_directory(self.path,organization,key,clock)

    def custom(self, snapshots, name='custom', clock=lambda:NOW):
        profiles = LocalProfiles('one','fielddesk',ROOT/'config/profiles')
        source = RecordedContactSource('one',snapshots)
        db = Database(self.root/(name+'.sqlite'))
        return ContactDirectory(source,SqliteContactDirectory(db,source,profiles,'fielddesk','v1',clock))

    def prepare(self, service=None, request='first', version=1, channel='email', key='fielddesk'):
        return (service or self.service(key)).prepare('one',request,key+'-crm-a',version,channel)

    def counts(self, service):
        with service.store.database.connect() as db:
            return {table:db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in (
                'contact_sources','contact_source_heads','contact_objections','contact_assessments','contact_commands',
                'runs','tasks','model_calls','review_decisions','simulated_agency_jobs')}

    def test_two_companies_and_two_provider_accounts_keep_native_execution_identity_separate(self):
        for key in ('iwoca','fielddesk'):
            service = self.service(key)
            a = service.source.read('one',key+'-crm-a',1)
            b = service.source.read('one',key+'-crm-b',1)
            self.assertEqual(a.contacts[0].ref.native_id,b.contacts[0].ref.native_id)
            self.assertNotEqual(a.contacts[0].ref.id,b.contacts[0].ref.id)
            self.assertNotEqual(a.contacts[0].ref.id,a.accounts[0].ref.id)
            self.assertEqual(a.contacts[0].ref.native_type,'Person')
            self.assertEqual(a.contacts[0].ref.role,'contact')
            self.assertEqual(contact_snapshot_from(json.loads(canonical(asdict(a)))),a)
            result = self.prepare(service,request=key,key=key)
            report = result['report']
            self.assertTrue(report['ready_for_proposal'])
            self.assertEqual(len(report['eligible']),3)
            self.assertEqual(len(report['experiment_units']),2)
            self.assertEqual(report['rows'][0]['experiment_unit'],report['rows'][1]['experiment_unit'])
            self.assertEqual(report['approval'],'not_granted')
            self.assertEqual(report['execution'],'not_performed')
        for name,count in self.counts(service).items():
            if name in ('runs','tasks','model_calls','review_decisions','simulated_agency_jobs'):
                self.assertEqual(count,0)

    def test_replay_in_a_fresh_process_keeps_original_subject_without_effects(self):
        service = self.service()
        first = self.prepare(service)
        before = self.counts(service)
        args = [sys.executable,'-m','acquisition.contact_cli','--db',str(self.path),'--organization','one',
            '--profile','fielddesk','prepare','--request-id','first','--connection','fielddesk-crm-a',
            '--version','1','--channel','email']
        process = subprocess.run(args,cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(process.returncode,0,process.stderr)
        replay = json.loads(process.stdout)
        self.assertEqual(replay['observation'],'historical_receipt')
        self.assertEqual(replay['assessment_id'],first['assessment_id'])
        self.assertEqual(replay['report'],first['report'])
        self.assertEqual(self.counts(service),before)
        for change in ({'channel':'human_call'},{'version':2},{'key':'iwoca'}):
            with self.assertRaises((Conflict,NotFound)):
                self.prepare(service,**change)
            self.assertEqual(self.counts(service),before)

    def test_cross_organization_and_rehashed_candidate_substitution_cannot_publish(self):
        service = self.service()
        snapshot = service.source.read('one','fielddesk-crm-a',1)
        changed = replace(snapshot,contacts=(replace(snapshot.contacts[0],email='substituted@example.invalid'),*snapshot.contacts[1:]))
        before = self.counts(service)
        with self.assertRaisesRegex(Conflict,'attestation'):
            service.store.prepare('one','replacement',changed,'email','acquisition')
        with self.assertRaises(NotFound):
            service.source.read('other','fielddesk-crm-a',1)
        with self.assertRaises((Conflict,NotFound)):
            service.store.prepare('other','foreign',snapshot,'email','acquisition')
        self.assertEqual(self.counts(service),before)
        result = self.prepare(service)
        with self.assertRaises(NotFound):
            service.inspect('other',result['assessment_id'])
        with self.assertRaises(NotFound):
            service.object('other','foreign',snapshot.contacts[0].ref.id,'all','all','An explicit objection.')

    def test_new_request_for_identical_frozen_evidence_reuses_immutable_assessment(self):
        service = self.service()
        first = self.prepare(service)
        second = self.prepare(service,request='another-observation')
        self.assertEqual(first['assessment_id'],second['assessment_id'])
        self.assertEqual(first['report'],second['report'])
        self.assertEqual(self.counts(service)['contact_assessments'],1)
        self.assertEqual(self.counts(service)['contact_commands'],2)
        self.assertEqual(second['authority'],'none')

    def test_missing_ambiguous_partial_or_expired_evidence_cannot_claim_complete_readiness(self):
        snapshot = self.service().source.read('one','fielddesk-crm-a',1)
        variants = {
            'missing_permission':replace(snapshot,permissions=()),
            'unknown_permission':replace(snapshot,permissions=tuple(replace(p,status='unknown') for p in snapshot.permissions)),
            'expired_permission':replace(snapshot,permissions=tuple(replace(p,expires_at=NOW) for p in snapshot.permissions)),
            'partial_population':replace(snapshot,contacts=snapshot.contacts[:2],complete=False,cursor='next',
                permissions=tuple(p for p in snapshot.permissions if p.contact.id!=snapshot.contacts[2].ref.id),
                pressure=snapshot.pressure[:2]),
            'ambiguous_account':replace(snapshot,contacts=(replace(snapshot.contacts[0],accounts=tuple(a.ref for a in snapshot.accounts)),*snapshot.contacts[1:])),
            'unknown_account':replace(snapshot,contacts=(replace(snapshot.contacts[0],accounts=()),*snapshot.contacts[1:])),
            'missing_pressure':replace(snapshot,pressure=()),
            'incomplete_pressure':replace(snapshot,pressure=tuple(replace(p,complete=False) for p in snapshot.pressure)),
            'inconsistent_pressure':replace(snapshot,pressure=tuple(replace(p,contact_count=1) for p in snapshot.pressure)),
        }
        for name,value in variants.items():
            with self.subTest(name=name):
                report = self.prepare(self.custom((value,),name))['report']
                self.assertFalse(report['ready_for_proposal'])
                self.assertFalse(report['coverage_complete'])
                self.assertNotIn(snapshot.contacts[0].ref.id,report['eligible'])
        tombstone = replace(snapshot,contacts=(replace(snapshot.contacts[0],state='deleted',accounts=(),email=None,phone=None),
                                                *snapshot.contacts[1:]),
            permissions=tuple(p for p in snapshot.permissions if p.contact.id!=snapshot.contacts[0].ref.id),
            pressure=snapshot.pressure[1:])
        report = self.prepare(self.custom((tombstone,),'known-deleted'))['report']
        self.assertTrue(report['ready_for_proposal'])
        self.assertEqual(len(report['eligible']),2)
        self.assertIn('contact_deleted',report['rows'][0]['reasons'])

    def test_channel_purpose_caps_and_existing_business_suppression_remain_hard_constraints(self):
        snapshot = self.service().source.read('one','fielddesk-crm-a',1)
        for name,value,reason in (
            ('denied',replace(snapshot,permissions=tuple(replace(p,status='denied') for p in snapshot.permissions)),'permission_denied'),
            ('account_cap',replace(snapshot,pressure=tuple(replace(p,account_count=4) for p in snapshot.pressure)),'account_cap')):
            report = self.prepare(self.custom((value,),name))['report']
            self.assertEqual(report['eligible'],[])
            self.assertTrue(all(reason in row['reasons'] for row in report['rows']))
        contact_cap = replace(snapshot,pressure=(*snapshot.pressure[:2],
            replace(snapshot.pressure[2],contact_count=2,account_count=2)))
        report = self.prepare(self.custom((contact_cap,),'contact_cap'))['report']
        self.assertEqual(len(report['eligible']),2)
        self.assertNotIn(snapshot.contacts[2].ref.id,report['eligible'])
        self.assertEqual(report['rows'][2]['reasons'],['contact_cap'])
        email_only = replace(snapshot,permissions=tuple(p for p in snapshot.permissions if p.channel=='email'))
        directory = self.custom((email_only,),'email_only')
        self.assertTrue(self.prepare(directory)['report']['ready_for_proposal'])
        self.assertFalse(self.prepare(directory,request='call',channel='human_call')['report']['ready_for_proposal'])
        with self.assertRaises(ValueError):
            directory.prepare('one','purpose','fielddesk-crm-a',1,'email','another-purpose')
        service = self.service()
        first = self.prepare(service)
        with service.store.database.transaction() as db:
            db.execute('INSERT INTO review_suppressions VALUES(?,?,?,?,?)',
                ('one',snapshot.accounts[0].business_id,'reviewer','An authoritative local exclusion.',NOW))
        view = service.inspect('one',first['assessment_id'])
        self.assertFalse(view['currently_applicable'])
        self.assertEqual(len(view['current']['eligible']),1)
        self.assertIn('local_business_suppression',view['current']['rows'][0]['reasons'])

    def test_objection_merge_and_deletion_invalidate_new_use_without_rewriting_history(self):
        service = self.service()
        first = self.prepare(service)
        original = service.inspect('one',first['assessment_id'])['saved']
        person = first['report']['rows'][0]['contact_id']
        service.object('one','object',person,'email','acquisition','An explicit recipient objection.')
        self.assertFalse(service.inspect('one',first['assessment_id'])['currently_applicable'])
        email = self.prepare(service,request='after-object')['report']
        calls = self.prepare(service,request='calls',channel='human_call')['report']
        self.assertNotIn(person,email['eligible']); self.assertIn(person,calls['eligible'])
        service.refresh('one','merge','fielddesk-crm-a',2)
        merged = self.prepare(service,request='after-merge',version=2)['report']
        self.assertEqual(len(merged['eligible']),1)
        self.assertIn('current_objection',merged['rows'][1]['reasons'])
        self.assertIn('contact_merged',merged['rows'][0]['reasons'])
        service.refresh('one','delete','fielddesk-crm-a',3)
        deleted = self.prepare(service,request='after-delete',version=3)['report']
        self.assertIn('account_deleted',deleted['rows'][1]['reasons'])
        view = self.service().inspect('one',first['assessment_id'])
        self.assertEqual(view['saved'],original)
        self.assertFalse(view['currently_applicable'])
        self.assertEqual(self.prepare(service)['observation'],'historical_receipt')
        with service.store.database.transaction() as db:
            db.execute('UPDATE contact_source_heads SET source_id=? WHERE organization=? AND connection_key=?',
                       (first['report']['source_id'],'one','fielddesk-crm-a'))
        with self.assertRaisesRegex(Conflict,'rewind'):
            service.inspect('one',first['assessment_id'])
        with service.store.database.connect() as db:
            for sql in ('UPDATE contact_assessments SET payload=payload','DELETE FROM contact_sources'):
                with self.assertRaises(sqlite3.IntegrityError): db.execute(sql)

    def test_mapping_revision_cannot_erase_objections_or_resurrect_native_identity(self):
        profiles = LocalProfiles('one','fielddesk',ROOT/'config/profiles')
        history = tuple(synthetic_contact_snapshots('one',profiles.profile))[:2]
        payload = json.loads(canonical(asdict(history[1])).replace('mapping-v1','mapping-v2'))
        third = replace(contact_snapshot_from(payload),version=3)
        resurrected = replace(third,version=4,
            contacts=(replace(third.contacts[0],state='active',merged_into=None),*third.contacts[1:]))
        service = self.custom((*history,third,resurrected),'mapping')
        first = self.prepare(service)
        person = first['report']['rows'][0]['contact_id']
        service.object('one','object',person,'all','all','An explicit objection across channels.')
        service.refresh('one','merge','fielddesk-crm-a',2)
        service.refresh('one','mapping','fielddesk-crm-a',3)
        self.assertEqual(third.contacts[0].ref.id,history[0].contacts[0].ref.id)
        report = self.prepare(service,request='mapped',version=3)['report']
        self.assertIn('current_objection',report['rows'][1]['reasons'])
        before = self.counts(service)
        with self.assertRaisesRegex(Conflict,'resurrected'):
            service.refresh('one','resurrect','fielddesk-crm-a',4)
        self.assertEqual(self.counts(service),before)

    def test_connection_alias_cannot_erase_native_objections_or_retired_identity(self):
        profiles = LocalProfiles('one','fielddesk',ROOT/'config/profiles')
        history = tuple(synthetic_contact_snapshots('one',profiles.profile))[:3]
        alias = contact_snapshot_from(json.loads(canonical(asdict(history[0])).replace('fielddesk-crm-a','fielddesk-crm-alias')))
        service = self.custom((*history,alias),'alias')
        original = self.prepare(service)
        alias_view = service.prepare('one','alias','fielddesk-crm-alias',1,'email')
        self.assertEqual(alias.contacts[0].ref.id,history[0].contacts[0].ref.id)
        self.assertEqual(alias_view['report']['rows'][0]['contact_id'],original['report']['rows'][0]['contact_id'])
        service.object('one','object',alias.contacts[0].ref.id,'all','all','An objection follows native identity.')
        service.refresh('one','merge','fielddesk-crm-a',2)
        view = service.inspect('one',alias_view['assessment_id'])
        self.assertFalse(view['currently_applicable'])
        self.assertIn('contact_retired',view['current']['rows'][0]['reasons'])
        self.assertIn('current_objection',view['current']['rows'][1]['reasons'])
        service.refresh('one','delete','fielddesk-crm-a',3)
        view = service.inspect('one',alias_view['assessment_id'])
        self.assertIn('account_retired',view['current']['rows'][1]['reasons'])
        self.assertEqual(view['saved']['report'],alias_view['report'])

    def test_objection_does_not_cross_provider_account_or_channel_scope(self):
        service = self.service()
        first = self.prepare(service)
        service.object('one','object',first['report']['eligible'][0],'email','acquisition','A channel-specific objection.')
        other = service.prepare('one','other-account','fielddesk-crm-b',1,'email')
        self.assertEqual(len(other['report']['eligible']),3)
        calls = self.prepare(service,request='call',channel='human_call')
        self.assertEqual(len(calls['report']['eligible']),3)

    def test_stale_alias_cannot_ignore_newer_native_permission_or_shared_pressure(self):
        snapshot = self.service().source.read('one','fielddesk-crm-a',1)
        alias = contact_snapshot_from(json.loads(canonical(asdict(snapshot)).replace('fielddesk-crm-a','fielddesk-crm-alias')))
        observed = snapshot.observed_at + 60
        denied = replace(alias,version=2,observed_at=observed,permissions=tuple(
            replace(p,status='denied',observed_at=observed) if p.contact.id==snapshot.contacts[0].ref.id and p.channel=='email' else p
            for p in alias.permissions))
        pressure = replace(alias,version=2,observed_at=observed,
            pressure=tuple(replace(p,account_count=4,observed_at=observed) for p in alias.pressure))
        for name,changed in (('permission',denied),('pressure',pressure)):
            service = self.custom((snapshot,alias,changed),'newer-alias-'+name)
            first = self.prepare(service)
            service.refresh('one','alias','fielddesk-crm-alias',1)
            service.refresh('one','new-evidence','fielddesk-crm-alias',2)
            view = service.inspect('one',first['assessment_id'])
            with self.subTest(name=name):
                self.assertFalse(view['currently_applicable'])
                self.assertFalse(view['current_ready_for_proposal'])
                self.assertNotIn(snapshot.contacts[0].ref.id,view['current']['eligible'])
                self.assertEqual(view['saved']['report'],first['report'])

    def test_pressure_observation_times_cannot_regress_even_after_an_omission(self):
        snapshot = self.service().source.read('one','fielddesk-crm-a',1)
        alias = contact_snapshot_from(json.loads(canonical(asdict(snapshot)).replace('fielddesk-crm-a','fielddesk-crm-alias')))
        later = snapshot.observed_at + 60
        high = replace(alias,version=2,observed_at=later,
            pressure=tuple(replace(p,account_count=4,observed_at=later) for p in alias.pressure))
        for omitted in (False,True):
            middle = (replace(high,version=3,observed_at=later+60,pressure=()),) if omitted else ()
            backward = replace(alias,version=4 if omitted else 3,observed_at=later+120)
            service = self.custom((snapshot,alias,high,*middle,backward),'pressure-regression-'+str(omitted))
            first = self.prepare(service)
            service.refresh('one','alias','fielddesk-crm-alias',1)
            service.refresh('one','higher-pressure','fielddesk-crm-alias',2)
            if omitted: service.refresh('one','omitted-pressure','fielddesk-crm-alias',3)
            before = self.counts(service)
            with self.subTest(omitted=omitted), self.assertRaisesRegex(Conflict,'pressure observations cannot move backward'):
                service.refresh('one','backward','fielddesk-crm-alias',backward.version)
            self.assertEqual(self.counts(service),before)
            view = service.inspect('one',first['assessment_id'])
            self.assertFalse(view['current_ready_for_proposal'])
            self.assertEqual(view['saved']['report'],first['report'])

    def test_equal_time_permission_conflicts_survive_regrant_omission_and_restart(self):
        base = self.service().source.read('one','fielddesk-crm-a',1)
        other_account = self.service().source.read('one','fielddesk-crm-b',1)
        alias = contact_snapshot_from(json.loads(canonical(asdict(base)).replace('fielddesk-crm-a','fielddesk-crm-alias')))
        person = base.contacts[0].ref.id
        for name,change in (('denied',{'status':'denied'}),('expiry',{'expires_at':base.expires_at-60})):
            conflict = replace(alias,version=2,observed_at=base.observed_at+60,permissions=tuple(
                replace(p,**change) if p.contact.id==person and p.channel=='email' else p for p in alias.permissions))
            regrant = replace(alias,version=3,observed_at=base.observed_at+120)
            omitted = replace(alias,version=4,observed_at=base.observed_at+180,permissions=())
            fresh = replace(alias,version=5,observed_at=base.observed_at+240,permissions=tuple(
                replace(p,observed_at=base.observed_at+240) if p.contact.id==person and p.channel=='email' else p
                for p in alias.permissions))
            snapshots = (base,other_account,alias,conflict,regrant,omitted,fresh)
            service = self.custom(snapshots,'permission-tie-'+name)
            first = self.prepare(service)
            service.refresh('one','alias','fielddesk-crm-alias',1)
            service.refresh('one','conflict','fielddesk-crm-alias',2)
            self.assertFalse(service.inspect('one',first['assessment_id'])['current_ready_for_proposal'])
            candidate = service.prepare('one','regrant','fielddesk-crm-alias',3,'email')
            with self.subTest(name=name):
                self.assertFalse(candidate['report']['ready_for_proposal'])
                self.assertIn('permission_changed',candidate['report']['rows'][0]['reasons'])
                self.assertFalse(service.inspect('one',first['assessment_id'])['current_ready_for_proposal'])
            service.refresh('one','omit','fielddesk-crm-alias',4)
            code = '''
import json,sys
from pathlib import Path
from acquisition.audiences import ContactDirectory,contact_snapshot_from
from acquisition.adapters.contact_fixtures import RecordedContactSource
from acquisition.adapters.local_profiles import LocalProfiles
from acquisition.adapters.sqlite.contacts import SqliteContactDirectory
from acquisition.adapters.sqlite.database import Database
profiles=LocalProfiles('one','fielddesk',Path(sys.argv[2]))
source=RecordedContactSource('one',tuple(contact_snapshot_from(s) for s in json.load(sys.stdin)))
directory=ContactDirectory(source,SqliteContactDirectory(Database(sys.argv[1]),source,profiles,'fielddesk','v1',lambda:float(sys.argv[4])))
print(json.dumps(directory.inspect('one',sys.argv[3])))
'''
            process = subprocess.run([sys.executable,'-c',code,str(service.store.database.path),
                str(ROOT/'config/profiles'),first['assessment_id'],str(NOW)],
                input=canonical([asdict(s) for s in snapshots]),cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(process.returncode,0,process.stderr)
            view = json.loads(process.stdout)
            with self.subTest(name=name):
                self.assertFalse(view['currently_applicable'])
                self.assertFalse(view['current_ready_for_proposal'])
                self.assertIn('permission_changed',view['current']['rows'][0]['reasons'])
                self.assertNotIn('pressure_changed',view['current']['rows'][0]['reasons'])
                self.assertEqual(view['saved']['report'],first['report'])
            calls = self.prepare(service,request='calls',channel='human_call')
            other = service.prepare('one','other-account','fielddesk-crm-b',1,'email')
            self.assertTrue(calls['report']['ready_for_proposal'])
            self.assertTrue(other['report']['ready_for_proposal'])
            recovered = service.prepare('one','fresh','fielddesk-crm-alias',5,'email')
            self.assertTrue(recovered['report']['ready_for_proposal'])

    def test_stored_backdated_and_equal_time_pressure_cannot_erase_known_evidence(self):
        original = self.service().source.read('one','fielddesk-crm-a',1)
        for equal_time in (False,True):
            observed = original.observed_at + 60
            snapshot = (replace(original,observed_at=observed,
                pressure=tuple(replace(p,observed_at=observed) for p in original.pressure)) if equal_time else original)
            alias = contact_snapshot_from(json.loads(canonical(asdict(snapshot)).replace('fielddesk-crm-a','fielddesk-crm-alias')))
            high = replace(alias,version=2,observed_at=observed+60,
                pressure=tuple(replace(p,account_count=4,observed_at=observed) for p in alias.pressure))
            backward = replace(alias,version=3,observed_at=observed+120)
            fresh_time = observed+180
            recovered = replace(alias,version=4,observed_at=fresh_time,
                pressure=tuple(replace(p,observed_at=fresh_time,window_start=fresh_time-90*86400) for p in alias.pressure))
            snapshots = (snapshot,alias,high,backward,recovered)
            service = self.custom(snapshots,'stored-pressure-'+str(equal_time))
            first = self.prepare(service)
            service.refresh('one','alias','fielddesk-crm-alias',1)
            service.refresh('one','higher-pressure','fielddesk-crm-alias',2)
            with self.subTest(equal_time=equal_time):
                self.assertFalse(service.inspect('one',first['assessment_id'])['current_ready_for_proposal'])
            payload = canonical(asdict(backward))
            # This valid attested row was accepted by the prior v18 writer. Preserve it as history.
            with service.store.database.transaction() as db:
                db.execute('INSERT INTO contact_sources VALUES(?,?,?,?,?)',
                           ('one',backward.id,backward.connection.key,backward.version,payload))
                db.execute('UPDATE contact_source_heads SET source_id=? WHERE organization=? AND connection_key=?',
                           (backward.id,'one',backward.connection.key))
            code = '''
import json,sys
from pathlib import Path
from acquisition.audiences import ContactDirectory,contact_snapshot_from
from acquisition.adapters.contact_fixtures import RecordedContactSource
from acquisition.adapters.local_profiles import LocalProfiles
from acquisition.adapters.sqlite.contacts import SqliteContactDirectory
from acquisition.adapters.sqlite.database import Database
profiles=LocalProfiles('one','fielddesk',Path(sys.argv[2]))
source=RecordedContactSource('one',tuple(contact_snapshot_from(s) for s in json.load(sys.stdin)))
directory=ContactDirectory(source,SqliteContactDirectory(Database(sys.argv[1]),source,profiles,'fielddesk','v1',lambda:float(sys.argv[4])))
print(json.dumps(directory.inspect('one',sys.argv[3])))
'''
            process = subprocess.run([sys.executable,'-c',code,str(service.store.database.path),
                str(ROOT/'config/profiles'),first['assessment_id'],str(NOW)],
                input=canonical([asdict(s) for s in snapshots]),cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(process.returncode,0,process.stderr)
            view = json.loads(process.stdout)
            with self.subTest(equal_time=equal_time):
                self.assertFalse(view['currently_applicable'])
                self.assertFalse(view['current_ready_for_proposal'])
                self.assertIn('pressure_changed',view['current']['rows'][0]['reasons'])
                self.assertEqual(view['saved']['report'],first['report'])
            with service.store.database.connect() as db:
                self.assertEqual(db.execute('SELECT payload FROM contact_sources WHERE organization=? AND id=?',
                                           ('one',backward.id)).fetchone()[0],payload)
            recovered_view = service.prepare('one','fresh-observation','fielddesk-crm-alias',4,'email')
            self.assertTrue(recovered_view['report']['ready_for_proposal'])

    def test_mapping_cannot_relabel_a_native_person_as_an_account(self):
        snapshot = self.service().source.read('one','fielddesk-crm-a',1)
        person = snapshot.contacts[0]
        account = ContactAccount(replace(person.ref,role='account'),'relabelled-business',snapshot.accounts[0].segment)
        second = replace(snapshot,version=2,accounts=(*snapshot.accounts,account),declared_accounts=3,
            contacts=snapshot.contacts[1:],declared_contacts=2,
            permissions=tuple(p for p in snapshot.permissions if p.contact.id!=person.ref.id),
            pressure=snapshot.pressure[1:])
        self.assertEqual(account.ref.id,person.ref.id)
        service = self.custom((snapshot,second),'role')
        self.prepare(service)
        before = self.counts(service)
        with self.assertRaisesRegex(Conflict,'reinterpret'):
            service.refresh('one','relabel','fielddesk-crm-a',2)
        self.assertEqual(self.counts(service),before)

    def test_refresh_requires_known_population_and_monotonic_observations(self):
        snapshot = self.service().source.read('one','fielddesk-crm-a',1)
        omitted = replace(snapshot,version=2,contacts=snapshot.contacts[1:],declared_contacts=2,
            permissions=tuple(p for p in snapshot.permissions if p.contact.id!=snapshot.contacts[0].ref.id),
            pressure=snapshot.pressure[1:])
        backdated = replace(snapshot,version=2,observed_at=snapshot.observed_at-1,
            permissions=tuple(replace(p,observed_at=p.observed_at-2) for p in snapshot.permissions),
            pressure=tuple(replace(p,observed_at=p.observed_at-2) for p in snapshot.pressure))
        old_permission = replace(snapshot,version=2,observed_at=snapshot.observed_at+1,
            permissions=tuple(replace(p,observed_at=p.observed_at-1) for p in snapshot.permissions))
        for index,value in enumerate((omitted,backdated,old_permission)):
            service = self.custom((snapshot,value),'refresh-boundary-'+str(index))
            self.prepare(service)
            before = self.counts(service)
            with self.subTest(index=index), self.assertRaises(Conflict):
                service.refresh('one','invalid-refresh','fielddesk-crm-a',2)
            self.assertEqual(self.counts(service),before)

    def test_malformed_observation_relationships_and_real_destinations_are_rejected(self):
        snapshot = self.service().source.read('one','fielddesk-crm-a',1)
        for change in ({'email':'person@example.com'},{'phone':'+442012345678'}):
            with self.assertRaises(ValueError): replace(snapshot.contacts[0],**change)
        with self.assertRaises(ValueError): replace(snapshot,complete=True,cursor='next-page')
        with self.assertRaises(ValueError): replace(snapshot,permissions=snapshot.permissions+snapshot.permissions[:1])
        with self.assertRaises(ValueError): replace(snapshot.permissions[0],expires_at=snapshot.permissions[0].observed_at)
        with self.assertRaises(ValueError): replace(snapshot.pressure[0],contact_count=True)
        other = self.service().source.read('one','fielddesk-crm-b',1)
        with self.assertRaises(ValueError): replace(snapshot.contacts[0],accounts=(other.accounts[0].ref,))

    def test_new_objection_after_assessment_write_rolls_back_the_whole_bundle(self):
        service = self.service()
        contact = service.source.read('one','fielddesk-crm-a',1).contacts[0].ref.id
        payload = {'kind':'contact-objection/v1','organization':'one','contact_id':contact,
                   'channel':'all','purpose':'all','reason':'A late objection.','recorded_at':NOW}
        identity = 'objection_' + digest(payload)
        sql_payload = canonical(payload).replace("'","''")
        with service.store.database.transaction() as db:
            db.execute(f"""CREATE TRIGGER late_contact_objection AFTER INSERT ON contact_assessments BEGIN
                INSERT INTO contact_objections VALUES('one','{identity}','{sql_payload}'); END""")
        before = self.counts(service)
        with self.assertRaisesRegex(Conflict,'changed before assessment commit'):
            self.prepare(service)
        self.assertEqual(self.counts(service),before)

    def test_expiry_at_the_final_check_rolls_back_source_assessment_and_receipt(self):
        service = self.service()
        snapshot = service.source.read('one','fielddesk-crm-a',1)
        moments = iter((NOW,NOW,NOW,snapshot.expires_at))
        service.store.clock = lambda:next(moments)
        before = self.counts(service)
        with self.assertRaisesRegex(Conflict,'changed before assessment commit'):
            self.prepare(service)
        self.assertEqual(self.counts(service),before)

    def test_competing_changed_requests_publish_one_whole_original_assessment(self):
        services = [self.service(),self.service()]
        def prepare(index):
            try: return self.prepare(services[index],channel=('email','human_call')[index])
            except Conflict: return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(prepare,range(2)))
        self.assertEqual(sum(r is not None for r in results),1)
        counts = self.counts(services[0])
        for table in ('contact_sources','contact_source_heads','contact_assessments','contact_commands'):
            self.assertEqual(counts[table],1)

    def test_sealed_store_and_checkpoint_preserve_read_only_history(self):
        service = self.service()
        first = self.prepare(service)
        before = self.counts(service)
        Database(self.path,verified_admissions=True,clock=lambda:NOW)
        with self.assertRaises(Conflict): self.prepare(service,request='sealed')
        with self.assertRaises(Conflict): self.service()
        reader = build_contact_directory(self.path,'one','fielddesk',lambda:NOW,read_only=True)
        self.assertTrue(reader.inspect('one',first['assessment_id'])['currently_applicable'])
        self.assertEqual(self.counts(service),before)
        (self.root/'.acquisition-checkpoint.json').write_text('{}')
        saved = self.path.read_bytes()
        reader = build_contact_directory(self.path,'one','fielddesk',lambda:NOW,read_only=True)
        self.assertEqual(reader.inspect('one',first['assessment_id'])['saved']['report'],first['report'])
        with self.assertRaises(Conflict): self.prepare(reader,request='restored')
        self.assertEqual(self.path.read_bytes(),saved)


class ContactMigrationTests(unittest.TestCase):
    def test_v17_migration_failure_rolls_back_and_keeps_legacy_cutoff_and_artifact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'migration.sqlite'
            database = Database(path)
            snapshot = generate('one',10,42,'2026-10-25')
            SqliteAudiences(database).put(snapshot)
            with database.transaction() as db:
                db.execute("INSERT INTO runs VALUES('historical-run','one','historical-request','historical-request-hash','succeeded',?)",(NOW,))
                db.execute("INSERT INTO legacy_task_admissions VALUES('one','historical-run','historical-request-hash')")
                for table in ('contact_source_heads','contact_sources','contact_objections','contact_assessments','contact_commands'):
                    db.execute('DROP TABLE '+table)
                db.execute('PRAGMA user_version=17')
                saved = db.execute('SELECT payload FROM audiences').fetchone()[0]
            original = Database._apply_migration
            def fail(db,text):
                original(db,text)
                if 'CREATE TABLE IF NOT EXISTS contact_sources' in text: raise OSError('injected contact migration failure')
            with patch.object(Database,'_apply_migration',side_effect=fail), self.assertRaises(OSError):
                Database(path)
            with database.connect() as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],17)
                self.assertIsNone(db.execute("SELECT name FROM sqlite_schema WHERE name='contact_sources'").fetchone())
                self.assertEqual(db.execute('SELECT payload FROM audiences').fetchone()[0],saved)
            Database(path)
            with database.connect() as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],19)
                self.assertEqual(tuple(db.execute('SELECT * FROM legacy_task_admissions').fetchone()),
                                 ('one','historical-run','historical-request-hash'))
                self.assertEqual(db.execute('SELECT payload FROM audiences').fetchone()[0],saved)
            self.assertEqual(SqliteAudiences(database).get('one',snapshot.id),snapshot)


if __name__ == '__main__':
    unittest.main()
