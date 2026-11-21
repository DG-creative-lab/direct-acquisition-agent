"""Infrastructure experiments must not leak credentials or claim untested compatibility."""

from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from scripts.hosting_probe import Probe, positional_parameters
from scripts import package_hosting_probe
from scripts.hosting_function import handler


class HostingProbeTests(unittest.TestCase):
    def test_named_translation_preserves_native_sqlite_binding_and_ignores_quoted_slots(self):
        sql = "SELECT :tenant, ':ignored', :tenant, :recipient /* :comment */ -- :line\n"
        values = {'recipient': 'recipient-b', 'tenant': 'tenant-a'}
        with closing(sqlite3.connect(':memory:')) as db:
            expected = db.execute(sql, values).fetchone()
        slots = positional_parameters(sql, values)
        self.assertEqual(slots, ('tenant-a', 'recipient-b'))
        self.assertEqual((slots[0], ':ignored', slots[0], slots[1]), expected)
        with self.assertRaises(ValueError):
            positional_parameters('SELECT :tenant, ?', values)
        with self.assertRaises(ValueError):
            positional_parameters('SELECT :tenant', values)

    def test_overlapping_probes_cannot_route_each_others_store(self):
        with tempfile.TemporaryDirectory() as root:
            probes = [Probe('local', letter*32, Path(root)/(letter+'.sqlite')) for letter in ('a', 'b')]
            barrier = threading.Barrier(2)
            original = Probe.admission
            def overlap(probe):
                barrier.wait(timeout=5)
                return original(probe)
            with patch.object(Probe, 'admission', overlap), ThreadPoolExecutor(max_workers=2) as workers:
                results = list(workers.map(lambda p: p.run('admission'), probes))
            self.assertTrue(all(r['passed'] for r in results), results)
            for probe in probes:
                with closing(sqlite3.connect(probe.path)) as db:
                    self.assertEqual(db.execute('SELECT DISTINCT organization FROM runs').fetchall(),
                                     [(probe.organization('admission'),)])

    def test_http_gate_rejects_unauthorized_and_unbounded_input_before_storage(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with patch.dict(os.environ, HOSTING_PROBE_TOKEN='private-probe-token'), \
                 patch('scripts.hosting_function.Probe') as database:
                for authorization, body, expected in (
                    ('', {'case':'admission','probe_id':'a'*32}, 403),
                    ('Bearer private-probe-token', {'case':'admission','probe_id':'a'*32,'database_url':'foreign'},400),
                    ('Bearer private-probe-token', {'case':'arbitrary_sql','probe_id':'a'*32},400),
                    ('Bearer private-probe-token', {'case':'admission','probe_id':'foreign'},400)):
                    connection = HTTPConnection(*server.server_address, timeout=5)
                    try:
                        connection.request('POST', '/api/probe', body=json.dumps(body),
                            headers={'Authorization':authorization,'Content-Type':'application/json'})
                        response = connection.getresponse()
                        self.assertEqual(response.status, expected)
                        self.assertNotIn('private-probe-token', response.read().decode())
                    finally:
                        connection.close()
                database.assert_not_called()
        finally:
            server.shutdown(); worker.join(timeout=5); server.server_close()

    def test_local_original_workflows_keep_one_receipt_and_fence_uncertainty(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'probe.sqlite'
            key = 'a' * 32
            results = [Probe('local', key, path).run(case)
                       for case in ('admission', 'channel', 'unknown', 'replay')]
            self.assertTrue(all(r['passed'] for r in results), results)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM execution_admissions WHERE organization=?',
                    ('hosting_probe_' + key + '_admission',)).fetchone()[0], 1)
                self.assertEqual(db.execute('SELECT status,count(*) FROM model_calls WHERE organization=? GROUP BY status',
                    ('hosting_probe_' + key + '_unknown',)).fetchall(), [('unknown', 1)])
                self.assertEqual(db.execute('SELECT count(*) FROM channel_artifacts WHERE organization=?',
                    ('hosting_probe_' + key + '_channel',)).fetchone()[0], 1)
            self.assertEqual(results[-1]['observed']['added_calls'], 0)
            self.assertEqual(Probe('local', key, path).run('expiry')['observed']['status'], 'not_applicable')

    def test_remote_target_validation_precedes_driver_import_and_network(self):
        with tempfile.TemporaryDirectory() as root:
            for url in ('https://production.turso.io', 'http://acquisition-hosting-probe-test.turso.io',
                        'https://acquisition-hosting-probe-test.turso.io.attacker.invalid',
                        'https://acquisition-hosting-probe-test.turso.io/private',
                        'https://user@acquisition-hosting-probe-test.turso.io',
                        'https://acquisition-hosting-probe-test.turso.io?token=secret'):
                with self.subTest(url=url), patch.dict(os.environ, TURSO_DATABASE_URL=url,
                                                       TURSO_AUTH_TOKEN='do-not-export'):
                    with self.assertRaisesRegex(ValueError, 'dedicated acquisition-hosting-probe'):
                        Probe('remote', 'a'*32, Path(root) / 'probe.sqlite')

    def test_failure_reports_omit_raw_provider_errors(self):
        with tempfile.TemporaryDirectory() as root:
            probe = Probe('local', 'a'*32, Path(root) / 'probe.sqlite')
            with patch.object(probe, 'channel', side_effect=RuntimeError('secret-token-do-not-export')):
                report = probe.run('channel')
            self.assertFalse(report['passed'])
            self.assertEqual(report['error_type'], 'RuntimeError')
            self.assertNotIn('secret-token', json.dumps(report))

    def test_deployment_package_uses_committed_bytes_and_excludes_unsafe_files(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            for folder in ('src', 'config', 'scripts', '.vercel'):
                (root / folder).mkdir()
            (root / 'src/public.py').write_text('VALUE = 1\n')
            (root / 'config/profile.json').write_text('{}\n')
            for name in ('hosting_probe.py', 'hosting_function.py'):
                (root / 'scripts' / name).write_text('# approved probe entry\n')
            (root / '.vercel/project.json').write_text(json.dumps({'orgId':'test', 'projectId':'test',
                                                                  'projectName':'direct-acquisition-feasibility'}))
            (root / 'src/.env.private').write_text('TOKEN=secret-token-do-not-export\n')
            subprocess.run(['git', 'init', '-q', str(root)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'add', 'src/public.py', 'config/profile.json'],
                           check=True, capture_output=True)
            def commit(message):
                subprocess.run(['git', '-C', str(root), '-c', 'user.name=Offline test',
                                '-c', 'user.email=offline@example.invalid', 'commit', '-qm', message],
                               check=True, capture_output=True)
                return subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()

            base_commit = commit('Application fixture')
            with patch.object(package_hosting_probe, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'both reviewed probe entry files'):
                    package_hosting_probe.package(root / 'missing-entries', commit=base_commit)
                self.assertFalse((root / 'missing-entries').exists())
            subprocess.run(['git', '-C', str(root), 'add', 'scripts/hosting_probe.py', 'scripts/hosting_function.py'],
                           check=True, capture_output=True)
            original_commit = commit('Reviewed fixture')
            with patch.object(package_hosting_probe, 'ROOT', root):
                package_hosting_probe.package(root / 'bundle')
                self.assertFalse((root / 'bundle/src/.env.private').exists())
                self.assertEqual((root / 'bundle/src/public.py').read_text(), 'VALUE = 1\n')
                provenance = json.loads((root / 'bundle/hosting-probe-source.json').read_text())
                self.assertEqual(provenance['source_commit'], original_commit)
                self.assertEqual(provenance['git_paths']['api/probe.py'], 'scripts/hosting_function.py')
                for relative, record in provenance['files'].items():
                    self.assertEqual(hashlib.sha256((root / 'bundle' / relative).read_bytes()).hexdigest(),
                                     record['sha256'])
                # An unstaged source edit and staged config edit must not enter
                # a bundle selected from the already reviewed commit.
                (root / 'src/public.py').write_text('VALUE = 2\n')
                (root / 'config/profile.json').write_text('{"changed":true}\n')
                (root / 'scripts/hosting_probe.py').write_text('# unreviewed probe edit\n')
                subprocess.run(['git', '-C', str(root), 'add', 'config/profile.json'],
                               check=True, capture_output=True)
                package_hosting_probe.package(root / 'dirty-worktree')
                self.assertEqual((root / 'dirty-worktree/src/public.py').read_text(), 'VALUE = 1\n')
                self.assertEqual((root / 'dirty-worktree/config/profile.json').read_text(), '{}\n')
                self.assertEqual((root / 'dirty-worktree/scripts/hosting_probe.py').read_text(), '# approved probe entry\n')
                subprocess.run(['git', '-C', str(root), 'add', 'src/public.py', 'scripts/hosting_probe.py'],
                               check=True, capture_output=True)
                later_commit = commit('Later fixture')
                package_hosting_probe.package(root / 'pinned', commit=original_commit)
                self.assertEqual((root / 'pinned/src/public.py').read_text(), 'VALUE = 1\n')
                self.assertEqual(json.loads((root / 'pinned/hosting-probe-source.json').read_text())['source_commit'],
                                 original_commit)
                package_hosting_probe.package(root / 'later')
                self.assertEqual((root / 'later/src/public.py').read_text(), 'VALUE = 2\n')
                self.assertEqual(json.loads((root / 'later/hosting-probe-source.json').read_text())['source_commit'],
                                 later_commit)
                (root / 'src/secret-link.py').symlink_to(root / 'src/.env.private')
                subprocess.run(['git', '-C', str(root), 'add', 'src/secret-link.py'], check=True, capture_output=True)
                commit('Unsafe committed symlink')
                with self.assertRaisesRegex(ValueError, 'regular checked-in'):
                    package_hosting_probe.package(root / 'unsafe-bundle')
                self.assertFalse((root / 'unsafe-bundle').exists())
