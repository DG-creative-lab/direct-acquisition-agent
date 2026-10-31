"""Immutable source selection and read-only scoped audience discovery."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from acquisition.adapters.local_audiences import LocalAudienceSource
from acquisition.audiences import AudienceDiscovery
from acquisition.bootstrap import build
from acquisition.contracts import Conflict, NotFound


class AudienceCatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source_root=self.root/'source'
        shutil.copytree(Path('config/audience-catalogue'),self.source_root)
        self.now=1793404800. # 31 October, within the source review window.
        self.source=LocalAudienceSource(self.source_root)
        self.service=AudienceDiscovery(self.source,lambda:self.now)
        self.org='local-conversations'
        self.entry=self.service.discover(self.org,'contractor-project-costs')['entries'][0]

    def read(self, service=None, entry=None, org=None):
        m=entry or self.entry
        return (service or self.service).read(org or self.org,m['dataset_id'],m['version'],m['checksum'],m['id'])

    def catalogue(self):
        return json.loads((self.source_root/'catalogue.json').read_text())

    def write_catalogue(self,value):
        (self.source_root/'catalogue.json').write_text(json.dumps(value))

    def rewrite_payload(self, mutate):
        c=self.catalogue();m=c['entries'][0];path=self.source_root/m['file']
        p=json.loads(path.read_text());mutate(p)
        raw=json.dumps(p).encode();path.write_bytes(raw);m['checksum']=hashlib.sha256(raw).hexdigest()
        self.write_catalogue(c)
        return self.service.discover(self.org,'contractor-project-costs')['entries'][0]

    def test_discovery_preserves_ambiguity_and_requires_exact_version(self):
        result=self.service.discover(self.org,'contractor-project-costs')
        self.assertEqual(result['resolution'],'ambiguous')
        self.assertEqual({m['version'] for m in result['entries']},{'v1','v2'})
        self.assertEqual(self.service.discover(self.org,'missing')['resolution'],'none')
        self.assertEqual(self.service.discover(self.org,'inventory-supplier-timing')['resolution'],'single')
        self.assertNotIn('file',json.dumps(result))
        m,s=self.read()
        self.assertEqual(m.id,self.entry['id'])
        self.assertEqual(len(s.records),100)
        self.assertEqual(s.records[0].business_id,'synthetic-000001')
        original=json.loads((self.source_root/'project-contractors-v1.json').read_text())
        self.assertEqual([asdict(r) for r in s.records],original['records'])
        self.assertEqual(result['authority'],'none')

    def test_scope_version_and_manifest_substitutions_are_rejected(self):
        self.assertEqual(self.service.discover('other')['entries'],[])
        with self.assertRaises(NotFound):self.read(org='other')
        with self.assertRaises(NotFound):self.read(entry=self.entry|{'version':'not-installed'})
        with self.assertRaises(Conflict):self.read(entry=self.entry|{'checksum':'0'*64})
        with self.assertRaises(Conflict):self.read(entry=self.entry|{'id':'dataset_'+'0'*64})
        c=self.catalogue();c['entries'][0]['campaign_key']='another-purpose';self.write_catalogue(c)
        with self.assertRaises(Conflict):self.read()

    def test_source_change_after_listing_cannot_replace_selected_bytes(self):
        c=self.catalogue();path=self.source_root/c['entries'][0]['file']
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(Conflict):self.read()

    def test_declared_checksum_does_not_excuse_incomplete_or_substituted_population(self):
        for mutation in (lambda p:p.update(complete=False),lambda p:p['records'].pop(),
                         lambda p:p.update(organization='other'),lambda p:p.update(model_version='different'),
                         lambda p:p['records'][0].update(segment='inventory'),
                         lambda p:p['records'][0].update(business_id=p['records'][1]['business_id']),
                         lambda p:p['records'][0].update(address='A real address is not a demo contact')):
            shutil.rmtree(self.source_root);shutil.copytree(Path('config/audience-catalogue'),self.source_root)
            selected=self.rewrite_payload(mutation)
            with self.subTest(mutation=mutation),self.assertRaises((Conflict,ValueError)):
                self.read(entry=selected)

    def test_stale_and_future_sources_are_visible_but_not_usable(self):
        for now in (1792454400.,1795564800.):
            service=AudienceDiscovery(self.source,lambda:now)
            self.assertFalse(service.discover(self.org)['entries'][0]['within_review_window'])
            with self.assertRaises(Conflict):self.read(service=service)

    def test_manifest_dates_counts_and_source_mode_are_validated(self):
        original=self.catalogue()
        for changes in ({'as_of':'20261025'}, {'review_by':'2026-10-20'},
                        {'record_count':0}, {'record_count':True}, {'business_count':101},
                        {'channel':'email'}, {'mode':'LIVE'}, {'schema_version':'unknown'},
                        {'segments':['contractors','contractors']}, {'model_version':''}):
            c=json.loads(json.dumps(original));c['entries'][0].update(changes);self.write_catalogue(c)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.service.discover(self.org)

    def test_paths_symlinks_duplicate_versions_and_oversized_files_fail_closed(self):
        original=self.catalogue()
        for filename in ('../outside.json','https://example.com/data.json','/tmp/data.json'):
            c=json.loads(json.dumps(original));c['entries'][0]['file']=filename;self.write_catalogue(c)
            with self.assertRaises(ValueError):self.read()
        self.write_catalogue(original)
        path=self.source_root/original['entries'][0]['file'];saved=path.read_bytes();path.unlink()
        outside=self.root/'outside.json';outside.write_bytes(saved);path.symlink_to(outside)
        with self.assertRaises(ValueError):self.read()
        path.unlink();path.write_bytes(b' ' * 4_000_001)
        with self.assertRaises(ValueError):self.read()
        c=original;c['entries'].append(c['entries'][0]);self.write_catalogue(c)
        with self.assertRaises(Conflict):self.service.discover(self.org)

    def test_duplicate_json_fields_cannot_be_hidden_by_checksum(self):
        c=self.catalogue();entry=c['entries'][0];path=self.source_root/entry['file']
        raw=path.read_bytes().replace(b'"complete": true',b'"complete": false, "complete": true')
        path.write_bytes(raw);entry['checksum']=hashlib.sha256(raw).hexdigest();self.write_catalogue(c)
        selected=self.service.discover(self.org,'contractor-project-costs')['entries'][0]
        with self.assertRaises(ValueError):self.read(entry=selected)

    def test_read_only_tool_results_and_persisted_snapshot_survive_restart(self):
        app=build(self.root/'app.sqlite',clock=lambda:self.now)
        before={}
        with app.tasks.database.connect() as db:
            for table in ('audiences','runs','review_decisions','simulated_agency_jobs'):
                before[table]=db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
        m,s=self.read(app.audience_discovery)
        summary=app.audience_discovery.inspect(self.org,m.dataset_id,m.version,m.checksum,m.id)
        self.assertNotIn('records',summary);self.assertNotIn('address',json.dumps(summary))
        with app.tasks.database.connect() as db:
            for table,count in before.items():self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],count)
        app.audiences.put(s)
        code="""import json,sys
from acquisition.bootstrap import build
print(json.dumps(build(sys.argv[1]).audiences.get(sys.argv[2],sys.argv[3]).id))
"""
        result=subprocess.run([sys.executable,'-c',code,str(self.root/'app.sqlite'),self.org,s.id],env=dict(os.environ,PYTHONPATH=str(Path('src').resolve())),capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),s.id)
