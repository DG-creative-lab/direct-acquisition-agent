"""Operator-only hosting experiment using the existing application transactions.

The remote mode is restricted to the isolated acquisition-hosting-probe database.
This connection shim is diagnostic code, not a supported product adapter.
"""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import threading
import time
import traceback
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from acquisition.adapters.sqlite.database import Database
from acquisition.bootstrap import (build, build_admissions, build_channel_preparation,
                                   build_contact_directory, build_recipient_contexts)
from acquisition.contracts import Conflict, NotFound
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.reasoning import ModelError
from acquisition.runtime import LeaseLost


NOW = 1794700800.0
CASES = ('transport', 'admission', 'channel', 'publication', 'lease', 'unknown', 'replay', 'expiry')
_CONNECTIONS = {}
_CONNECTION_LOCK = threading.Lock()
_ORIGINAL_CONNECT = Database.connect


def probe_connection(database):
    with _CONNECTION_LOCK:
        owner = _CONNECTIONS.get(database.path.resolve())
    if owner is None:
        raise ValueError('An overlapping probe attempted an unregistered store')
    return owner.connect(database)


def require(value, message):
    if not value:
        raise AssertionError(message)


def positional_parameters(sql, values):
    """Preserve SQLite's unique named-slot order without rewriting SQL text.

    Only the ASCII named placeholders used by this repository are supported.
    Strings, quoted identifiers and comments cannot introduce binding slots.
    """
    if not isinstance(values, dict):
        return values
    tokens = re.finditer(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\[[^\]]*\]|"
                         r'--[^\n]*|/\*.*?\*/|(?P<name>[:@$][A-Za-z_][A-Za-z_0-9]*)|(?P<position>\?)',
                         sql, re.S)
    names = []
    for token in tokens:
        if token['position']:
            raise ValueError('Mixed named and positional parameters are outside the probe contract')
        if token['name']:
            name = token['name'][1:]
            if name not in names:
                names.append(name)
    if set(names) != set(values):
        raise ValueError('Named probe bindings differ from the exact SQL slots')
    return tuple(values[name] for name in names)


class Row:
    """The mapping and positional access used by the current SQLite adapters."""
    def __init__(self, names, values):
        self.names, self.values = names, tuple(values)

    def keys(self):
        return self.names

    def __getitem__(self, key):
        return self.values[self.names.index(key)] if isinstance(key, str) else self.values[key]

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def fetchone(self):
        value = self.cursor.fetchone()
        return None if value is None else Row(tuple(c[0] for c in self.cursor.description), value)

    def fetchall(self):
        return list(self)

    def __iter__(self):
        while (row := self.fetchone()) is not None:
            yield row

    def __getattr__(self, name):
        return getattr(self.cursor, name)


class Connection:
    def __init__(self, raw, owner):
        self.raw, self.owner = raw, owner
        self.started, self.statements = None, 0

    def execute(self, sql, parameters=()):
        if self.owner.mode == 'remote' and re.fullmatch(r'PRAGMA\s+busy_timeout\s*=\s*\d+;?', sql.strip(), re.I):
            # This local lock-wait setting is not configurable over Hrana.
            # The experiment records that provider timeouts need a hosted policy.
            return self.execute('SELECT 0 AS provider_managed_lock_timeout')
        version = re.fullmatch(r'PRAGMA\s+user_version\s*(?:=\s*(\d+))?;?', sql.strip(), re.I)
        if self.owner.mode == 'remote' and version:
            # Hrana disallows setting user_version. This explicit experimental
            # journal participates in the same transaction as the migration.
            self.execute('CREATE TABLE IF NOT EXISTS hosting_probe_schema_version('
                         'singleton INTEGER PRIMARY KEY CHECK(singleton=1),version INTEGER NOT NULL)')
            if version[1] is not None:
                return self.execute('INSERT INTO hosting_probe_schema_version VALUES(1,?) '
                                    'ON CONFLICT(singleton) DO UPDATE SET version=excluded.version',
                                    (int(version[1]),))
            return self.execute('SELECT COALESCE((SELECT version FROM hosting_probe_schema_version '
                                'WHERE singleton=1),0) AS user_version')
        verb = sql.lstrip().split(None, 1)[0].upper()
        if verb == 'BEGIN':
            self.started, self.statements = time.monotonic(), 0
        self.statements += 1
        with self.owner.lock:
            self.owner.sql[verb] += 1
        try:
            if self.owner.mode == 'remote':
                parameters = positional_parameters(sql, parameters)
            return Cursor(self.raw.execute(sql, parameters))
        except Exception as error:
            self.owner.record_error(error)
            if self.owner.mode == 'remote' and isinstance(error, (self.owner.driver.Error, ValueError)):
                # Normalize only the driver's constraint errors. Other failures remain failures.
                if any(s in str(error).lower() for s in ('constraint', 'immutable', 'probe rollback')):
                    raise sqlite3.IntegrityError('Remote constraint rejected the probe write') from None
            raise

    def finish(self, action):
        completed = False
        try:
            result = getattr(self.raw, action)()
            completed = True
            return result
        except Exception as error:
            self.owner.record_error(error)
            raise
        finally:
            if self.started is not None:
                with self.owner.lock:
                    self.owner.transactions.append({'outcome': action,
                        'completed': completed,
                        'seconds': round(time.monotonic() - self.started, 6),
                        'statements': self.statements})
                self.started = None

    def commit(self):
        return self.finish('commit')

    def rollback(self):
        return self.finish('rollback')


class Probe:
    def __init__(self, mode, probe_id, path):
        if mode not in {'local', 'remote'} or re.fullmatch('[a-f0-9]{32}', probe_id) is None:
            raise ValueError('Use a declared mode and a 32-character hexadecimal probe identity')
        self.mode, self.id, self.path = mode, probe_id, Path(path).resolve()
        self.sql, self.transactions, self.lock = Counter(), [], threading.Lock()
        self.error_codes = []
        self.driver = sqlite3
        if mode == 'remote':
            self.url, self.token = os.environ['TURSO_DATABASE_URL'], os.environ['TURSO_AUTH_TOKEN']
            target = urlsplit(self.url)
            if (target.scheme not in {'libsql', 'https'} or not target.hostname
                    or not target.hostname.startswith('acquisition-hosting-probe-')
                    or not target.hostname.endswith('.turso.io') or target.username or target.password
                    or target.port or target.path not in {'', '/'} or target.query or target.fragment):
                raise ValueError('Remote execution requires the dedicated acquisition-hosting-probe database')
            import libsql
            self.driver = libsql

    def record_error(self, error):
        message = str(error).lower()
        for needle, code in (
            ('stream was idle for too long', 'remote_transaction_idle_rollback'),
            ('no transaction is active', 'remote_transaction_already_ended'),
            ('probe rollback', 'injected_rollback'),
            ('sql not allowed', 'remote_sql_not_allowed'),
        ):
            if needle in message:
                with self.lock:
                    self.error_codes.append(code)

    @contextmanager
    def connect(self, database):
        if database.path.resolve() != self.path:
            raise ValueError('The experiment cannot route another application store')
        if self.mode == 'local':
            raw = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        else:
            raw = self.driver.connect(self.url, auth_token=self.token, isolation_level=None)
        try:
            raw.execute('PRAGMA foreign_keys=ON')
            yield Connection(raw, self)
        finally:
            raw.close()

    @contextmanager
    def composition(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Instrumentation is routed by exact scratch path. Nested global mock
        # patches would restore each other's connectors under Fluid concurrency.
        with _CONNECTION_LOCK:
            if self.path in _CONNECTIONS:
                raise ValueError('A scratch path already belongs to another probe')
            _CONNECTIONS[self.path] = self
            Database.connect = probe_connection
        try:
            yield
        finally:
            with _CONNECTION_LOCK:
                del _CONNECTIONS[self.path]
                if not _CONNECTIONS:
                    Database.connect = _ORIGINAL_CONNECT

    def organization(self, case):
        return 'hosting_probe_' + self.id + '_' + case

    def database(self):
        return Database(self.path)

    def count(self, database, table, organization):
        with database.connect() as db:
            return db.execute('SELECT count(*) FROM ' + table + ' WHERE organization=?',
                              (organization,)).fetchone()[0]

    def admission(self):
        org = self.organization('admission')
        app = build(self.path, clock=lambda: NOW)
        cid = app.conversations.create(org, 'chat', 'Hosting probe')['id']
        app.conversations.message(org, cid, 'message', 0, FIXTURE_MESSAGE)
        store = build_admissions(self.path, clock=lambda: NOW)
        context = app.conversations.planning_context(org, cid, 'prepare', 1, True)
        intent = store.request_planning(org, cid, 'prepare', 1, context,
                                        fixture=True, allow_model=False)
        with store.database.transaction() as db:
            db.execute('CREATE TRIGGER hosting_probe_admission_' + self.id +
                       " AFTER INSERT ON execution_admissions WHEN NEW.organization='" + org +
                       "' BEGIN SELECT RAISE(ABORT,'probe rollback'); END")
            # Rollback removes this trigger together with the failed admission.
            from acquisition.adapters.sqlite.admissions import commit_admission
            try:
                commit_admission(db, intent, NOW)
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError('The injected admission failure must reject the write')
            # ABORT rolls back its statement, not earlier writes. Roll back the whole transaction.
            db.rollback()
        require(self.count(store.database, 'runs', org) == 0, 'Failed admission leaked a run')
        with ThreadPoolExecutor(max_workers=2) as workers:
            receipts = list(workers.map(lambda _: store.admit(intent, NOW), range(2)))
        require(receipts[0] == receipts[1], 'Concurrent admission created different identities')
        require(self.count(store.database, 'runs', org) == 1, 'Admission duplicated its runtime run')
        require(store.find_request('foreign', 'prepare') is None, 'Foreign organization saw a receipt')
        require(app.tasks.claim(org, NOW, 60, run_id=receipts[0].run_id) is None,
                'The paused admission became executable')
        return {'run_id': receipts[0].run_id, 'admission': asdict(receipts[0]),
                'concurrent_receipts': 2, 'durable_runs': 1, 'execution': 'paused'}

    def transport(self):
        database = self.database()
        key = 'transport_' + self.id
        with database.transaction() as db:
            engine = db.execute('SELECT sqlite_version()').fetchone()[0]
            require(db.execute('PRAGMA foreign_keys').fetchone()[0] == 1, 'Foreign-key enforcement is disabled')
            require(db.execute('SELECT json_extract(?,?)', ('{"value":7}', '$.value')).fetchone()[0] == 7,
                    'JSON SQL semantics differ')
            db.execute('CREATE TABLE IF NOT EXISTS hosting_probe_transport(id TEXT PRIMARY KEY)')
            db.execute('INSERT OR IGNORE INTO hosting_probe_transport VALUES(?)', (key,))
        with database.connect() as db:
            require(db.execute('SELECT count(*) FROM hosting_probe_transport WHERE id=?', (key,)).fetchone()[0] == 1,
                    'A fresh connection lost the committed transport receipt')
        return {'engine': engine, 'json': 'passed', 'foreign_keys': 'enabled',
                'committed_receipts': 1, 'fresh_connection_read': 'passed'}

    def seed(self, case):
        org = self.organization(case)
        contacts = build_contact_directory(self.path, org, 'fielddesk', lambda: NOW)
        assessed = contacts.prepare(org, 'source', 'fielddesk-crm-a', 1, 'email')
        person = assessed['report']['eligible'][0]
        contexts = build_recipient_contexts(self.path, org, 'fielddesk', lambda: NOW)
        contexts.prepare(org, 'recipient', assessed['assessment_id'], person, 'reviewed-context-a', 1)
        return org

    def channel(self):
        org = self.seed('channel')
        app = build_channel_preparation(self.path, org, 'fielddesk', lambda: NOW)
        run = app.start(org, 'content', 'fielddesk', ('recipient',), 'email')
        app.worker.drain(org, run_id=run)
        view = app.inspect(org, 'content')
        require(view['ready_for_review'], 'The original channel workflow did not publish validated content')
        require(self.count(app.store.database, 'channel_artifacts', org) == 1,
                'Channel publication did not retain one artifact')
        require(len(view['model_calls']) == 3, 'The fixture generation receipts changed')
        return {'run_id': run, 'artifact_id': view['saved']['artifact_id'] if 'artifact_id' in view['saved']
                else view.get('artifact_id'), 'calls': len(view['model_calls']),
                'generation': 'offline_fixture_only', 'approval': 'not_granted'}

    def unknown(self):
        class Uncertain:
            def complete(self, request):
                raise ModelError('provider_request_failed')
        org = self.seed('unknown')
        app = build_channel_preparation(self.path, org, 'fielddesk', lambda: NOW, gateway=Uncertain())
        run = app.start(org, 'content', 'fielddesk', ('recipient',), 'email')
        app.worker.drain(org, run_id=run)
        original = app.inspect(org, 'content')['model_calls']
        require(len(original) == 1 and original[0]['status'] == 'unknown', 'Missing uncertain-call fence')
        restarted = build_channel_preparation(self.path, org, 'fielddesk', lambda: NOW)
        restarted.worker.drain(org, run_id=run)
        require(restarted.inspect(org, 'content')['model_calls'] == original,
                'Restart repeated or rewrote the uncertain call')
        require(self.count(app.store.database, 'channel_artifacts', org) == 0,
                'Uncertain generation published content')
        return {'run_id': run, 'calls': 1, 'status': 'unknown', 'restart_added_calls': 0}

    def publication(self):
        org = self.seed('publication')
        app = build_channel_preparation(self.path, org, 'fielddesk', lambda: NOW)
        run = app.start(org, 'content', 'fielddesk', ('recipient',), 'email')
        claim = app.tasks.claim(org, NOW, 180, run_id=run)
        outcome = app.worker.capabilities[claim.capability](claim)
        trigger = 'hosting_probe_publication_' + self.id
        with app.store.database.transaction() as db:
            db.execute('CREATE TRIGGER ' + trigger + " BEFORE INSERT ON events WHEN NEW.run_id='" + run +
                       "' AND NEW.kind='task_succeeded' BEGIN SELECT RAISE(ABORT,'probe rollback'); END")
        try:
            app.tasks.settle(claim, outcome, NOW)
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError('Publication failure was not observed')
        state = app.tasks.inspect(org, run)
        require(self.count(app.store.database, 'channel_artifacts', org) == 0
                and state['tasks'][0]['output'] is None
                and state['tasks'][0]['status'] == 'running', 'Failed publication leaked an artifact or completion')
        with app.store.database.transaction() as db:
            db.execute('DROP TRIGGER ' + trigger)
        app.tasks.settle(claim, outcome, NOW)
        require(self.count(app.store.database, 'channel_artifacts', org) == 1,
                'Publication recovery did not retain one artifact')
        return {'run_id': run, 'artifact_after_failure': 0, 'completion_after_failure': False,
                'artifact_after_retry': 1, 'additional_generation': 0}

    def lease(self):
        class NeverRepeat:
            def complete(self, request):
                raise AssertionError('Recovery repeated recorded generation')
        org = self.seed('lease')
        now = [NOW]
        app = build_channel_preparation(self.path, org, 'fielddesk', lambda: now[0])
        run = app.start(org, 'content', 'fielddesk', ('recipient',), 'email')
        claim = app.tasks.claim(org, NOW, 10, run_id=run)
        outcome = app.worker.capabilities[claim.capability](claim)
        now[0] += 11
        try:
            app.tasks.settle(claim, outcome, now[0])
        except LeaseLost:
            pass
        else:
            raise AssertionError('Expired lease published content')
        require(self.count(app.store.database, 'channel_artifacts', org) == 0,
                'Expired lease retained a publication')
        reopened = build_channel_preparation(self.path, org, 'fielddesk', lambda: now[0], gateway=NeverRepeat())
        reopened.worker.drain(org, run_id=run)
        view = reopened.inspect(org, 'content')
        require(view['ready_for_review'] and len(view['model_calls']) == 3,
                'Lease recovery lost recorded generation or its original run')
        return {'run_id': run, 'expired_publication': 'rejected', 'recovery_calls': 0,
                'original_recorded_calls': 3}

    def replay(self):
        org = self.organization('channel')
        app = build_channel_preparation(self.path, org, 'fielddesk', lambda: NOW)
        before = app.inspect(org, 'content')
        run = app.start(org, 'content', 'fielddesk', ('recipient',), 'email')
        app.worker.drain(org, run_id=run)
        after = app.inspect(org, 'content')
        require(before['model_calls'] == after['model_calls'], 'Replay added inference receipts')
        require(before['saved'] == after['saved'], 'Replay changed the original artifact')
        try:
            app.start(org, 'content', 'fielddesk', ('recipient',), 'human_call')
        except Conflict:
            pass
        else:
            raise AssertionError('A request key accepted different campaign inputs')
        try:
            app.inspect('foreign', 'content')
        except NotFound:
            pass
        else:
            raise AssertionError('Foreign organization inspected another campaign')
        return {'run_id': run, 'added_calls': 0, 'changed_inputs': 'rejected', 'foreign_read': 'rejected'}

    def expiry(self):
        if self.mode != 'remote':
            return {'status': 'not_applicable', 'reason': 'Local SQLite has no remote transaction window'}
        database = self.database()
        keys = (uuid4().hex, uuid4().hex)
        with database.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS hosting_probe_transport(id TEXT PRIMARY KEY)')
        rejected = False
        try:
            with database.transaction() as db:
                for key in keys:
                    db.execute('INSERT INTO hosting_probe_transport VALUES(?)', (key,))
                time.sleep(12)
        except Exception:
            rejected = True
        with database.connect() as db:
            present = db.execute('SELECT count(*) FROM hosting_probe_transport WHERE id IN (?,?)', keys).fetchone()[0]
        require(present in (0, 2) and (rejected or present == 2),
                'Idle transaction retained partial writes or acknowledged a missing commit')
        return {'commit_error_observed': rejected, 'reconciled_rows': present, 'wait_seconds': 12,
                'expiry_observed': rejected and present == 0,
                'interpretation': 'Observed idle behavior, not an assumed five-second wall-clock deadline',
                'repeated_write_attempts': 0}

    def run(self, case):
        if case not in CASES:
            raise ValueError('Unsupported hosting probe case')
        started = time.monotonic()
        with self.composition():
            try:
                result = getattr(self, case)()
                return {'id': case, 'passed': True, 'seconds': round(time.monotonic()-started, 3),
                        'observed': result, 'transactions': self.transactions, 'sql': dict(self.sql),
                        'error_codes': self.error_codes}
            except Exception as error:
                # Provider errors can echo credentials or SQL. Retain classification, not raw text.
                return {'id': case, 'passed': False, 'seconds': round(time.monotonic()-started, 3),
                        'error_type': type(error).__name__, 'transactions': self.transactions,
                        'error_site': [{'file': Path(f.filename).name, 'line': f.lineno,
                                        'function': f.name} for f in traceback.extract_tb(error.__traceback__)[-4:]],
                        'sql': dict(self.sql), 'error_codes': self.error_codes}


def load_environment(path):
    for line in Path(path).read_text().splitlines():
        if '=' not in line or line.startswith('#'):
            continue
        key, value = line.split('=', 1)
        if key in {'TURSO_DATABASE_URL', 'TURSO_AUTH_TOKEN'}:
            os.environ[key] = json.loads(value) if value.startswith('"') else value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('local', 'remote'), required=True)
    parser.add_argument('--case', choices=CASES, action='append')
    parser.add_argument('--probe-id', default=None)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.env_file:
        if args.mode != 'remote':
            parser.error('Credentials are only accepted for explicit remote execution')
        load_environment(args.env_file)
    identity = args.probe_id or uuid4().hex
    results = []
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / 'probe.sqlite'
        for case in args.case or CASES:
            result = Probe(args.mode, identity, path).run(case)
            results.append(result)
            print(case + ': ' + ('PASS' if result['passed'] else 'FAIL'), flush=True)
            if not result['passed']:
                break
    report = {'schema': 'hosting-storage-feasibility/v1', 'mode': args.mode, 'probe_id': identity,
              'passed': all(r['passed'] for r in results), 'results': results,
              'complete_corpus': {r['id'] for r in results} == set(CASES),
              'scope': 'Existing application transactions with synthetic source/model fixtures; no product deployment',
              'limits': ['Diagnostic driver shim only', 'No live-model quality evidence',
                         'Local results do not establish remote or hosted compatibility'],
              'remote_adjustments': ['Tuple/mapping rows', 'Constraint exception translation',
                                     'Named dictionaries bound in SQLite slot order without SQL rewriting',
                                     'Provider-managed lock timeout instead of local PRAGMA busy_timeout',
                                     'Atomic version table instead of unsupported PRAGMA user_version writes']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
