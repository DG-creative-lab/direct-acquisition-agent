"""Offline, transactional projection repair. Application stores are read-only."""
import fcntl
import sqlite3
from contextlib import contextmanager, closing
from pathlib import Path

from acquisition.contracts import Conflict, digest
from .database import Database
from .workspace_ancestry import ensure_workspace_identity


CONTROL_TABLES = {
    'sessions': 'id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, payload TEXT NOT NULL',
    'commands': 'session_id TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, done INTEGER NOT NULL, PRIMARY KEY(session_id,request_id)',
    'conversation_draft_requests': 'conversation_id TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, session_id TEXT NOT NULL, PRIMARY KEY(conversation_id,request_id)',
    'followup_prepare_requests': 'organization TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, session_id TEXT NOT NULL, PRIMARY KEY(organization,request_id)',
    'copy_revision_blocks': 'organization TEXT NOT NULL, revision_id TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY(organization,revision_id)',
    'checkpoint_recovery_blocks': 'organization TEXT NOT NULL, run_id TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY(organization,run_id)',
}
KEYS = {'sessions': 1, 'commands': 2, 'conversation_draft_requests': 2, 'followup_prepare_requests': 2}


def initialize_control_tables(db):
    for name, definition in CONTROL_TABLES.items():
        db.execute(f'CREATE TABLE IF NOT EXISTS {name} ({definition})')


class ReadOnlyDatabase(Database):
    @classmethod
    def unmigrated(cls, path):
        """Read an existing historical schema without initializing or upgrading it."""
        value = cls.__new__(cls)
        value.path = Path(path)
        if not value.path.is_file():
            raise ValueError('Inspection source is unavailable')
        return value

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA foreign_keys=ON')
            yield db
        finally:
            db.close()


def sql_name(value):
    return '"' + value.replace('"', '""') + '"'


def values_hash(value):
    # Opaque legacy BLOBs and non-finite old timestamps must remain preservable.
    return digest(repr(value))


def owned(table, row, identities, diagnostics):
    if table in diagnostics:
        return row[:2] in diagnostics[table]
    return (row[0] if table in {'sessions', 'commands'} else row[-1]) in identities


class SqliteWorkspaceProjection:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / 'workspace.sqlite'

    @contextmanager
    def exclusive(self):
        if not self.root.is_dir():
            raise Conflict('Use an existing workspace root')
        path = self.root / 'server.lock'
        if path.is_symlink():
            raise Conflict('The workspace lock must be a regular local file')
        with path.open('a+') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Conflict('Stop the workspace server before inspecting or rebuilding projections') from None
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def check_path(self):
        for suffix in ('', '-wal', '-shm', '-journal'):
            path = Path(str(self.path) + suffix)
            if path.is_symlink() or (path.exists() and (not path.is_file() or path.stat().st_nlink != 1)):
                raise Conflict('Projection files must be regular files, never aliases of authoritative or legacy stores')

    @staticmethod
    def inventory(db, bundle):
        rows = bundle['rows'] | {table: [] for table in bundle['diagnostics']}
        diagnostics = {table: set(map(tuple, keys)) for table, keys in bundle['diagnostics'].items()}
        identities = {r[0] for r in rows['sessions']}
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        schema = [tuple(r) for r in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        contents, protected, blocked = {}, {}, []
        if {'runs', 'application_store_identity', 'campaign_environments'} & set(tables):
            raise Conflict('The projection path contains authoritative application records; it cannot be rebuilt')
        with closing(sqlite3.connect(':memory:')) as reference:
            initialize_control_tables(reference)
            for table in CONTROL_TABLES:
                if table not in tables:
                    if db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
                        blocked.append('unsupported projection object: ' + table)
                    continue
                if [tuple(r) for r in db.execute(f'PRAGMA table_info({table})')] != reference.execute(f'PRAGMA table_info({table})').fetchall():
                    blocked.append('unsupported projection layout: ' + table)
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,)).fetchone():
                    blocked.append('unexpected projection trigger: ' + table)
        for table in tables:
            records = [tuple(r) for r in db.execute('SELECT * FROM ' + sql_name(table))]
            contents[table] = sorted(records, key=repr)
            layout_ok = table in rows and not any(b.endswith(': ' + table) for b in blocked)
            protected[table] = [r for r in contents[table] if not (layout_ok and owned(table, r, identities, diagnostics))]
            if layout_ok:
                size = KEYS.get(table, 2)
                protected_keys = {r[:size] for r in protected[table]}
                if any(tuple(r[:size]) in protected_keys for r in rows[table]):
                    blocked.append('original request key conflicts with protected legacy data: ' + table)
        changes = {table: values_hash([r for r in contents.get(table, []) if owned(table, r, identities, diagnostics)]) != values_hash(sorted(map(tuple, expected), key=repr))
                   for table, expected in rows.items() if not any(b.endswith(': ' + table) for b in blocked)}
        return {'fingerprint': values_hash((schema, contents)), 'protected': protected, 'blocked': blocked,
                'changes': changes, 'protected_records': {table: len(records) for table, records in protected.items()}}

    def inspect(self, rows):
        self.check_path()
        if not self.path.exists():
            return {'fingerprint': values_hash('missing'), 'blocked': [], 'projection': 'missing',
                    'changes': {table: bool(values) for table, values in rows['rows'].items()}, 'protected_records': {}}
        try:
            # Existing projections may need SQLite's own hot-journal rollback.
            # Do not create a file; SQL remains query-only. Application sources
            # always use ReadOnlyDatabase instead of this recovery connection.
            db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=rw', uri=True, timeout=10, isolation_level=None)
            try:
                db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
                if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise Conflict('Projection integrity failed; preserve and recover the original legacy journal')
                result = self.inventory(db, rows)
            finally:
                db.close()
        except sqlite3.DatabaseError:
            raise Conflict('Projection is unreadable; preserve and recover the original legacy journal before rebuilding') from None
        return {k: v for k, v in result.items() if k != 'protected'} | {
            'projection': 'blocked' if result['blocked'] else 'stale' if any(result['changes'].values()) else 'current'}

    @staticmethod
    def replace_owned(db, bundle):
        rows = bundle['rows']
        identities = [r[0] for r in rows['sessions']]
        for table, expected in rows.items():
            key = 'id' if table == 'sessions' else 'session_id'
            db.executemany(f'DELETE FROM {table} WHERE {key}=?', [(identity,) for identity in identities])
            placeholders = ','.join('?' for _ in range(3 if table == 'sessions' else 4))
            db.executemany(f'INSERT INTO {table} VALUES({placeholders})', expected)
        for table, keys in bundle['diagnostics'].items():
            key = 'run_id' if table == 'checkpoint_recovery_blocks' else 'revision_id'
            db.executemany(f'DELETE FROM {table} WHERE organization=? AND {key}=?', keys)

    def rebuild(self, rows, expected_projection, expected_source, read_source):
        self.check_path()
        missing = not self.path.exists()
        if missing:
            try:
                self.path.open('xb').close()
            except FileExistsError:
                raise Conflict('Projection appeared after inspection; inspect the current journal') from None
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            db.execute('BEGIN IMMEDIATE')
            before = self.inventory(db, rows)
            actual = values_hash('missing') if missing else before['fingerprint']
            if actual != expected_projection or before['blocked']:
                raise Conflict('Projection changed after inspection; no legacy records were replaced')
            initialize_control_tables(db)
            ensure_workspace_identity(db)
            self.replace_owned(db, rows)
            after = self.inventory(db, rows)
            for table, protected in before['protected'].items():
                if values_hash(protected) != values_hash(after['protected'].get(table, [])):
                    raise Conflict('Rebuild changed protected legacy records')
            if read_source()['fingerprint'] != expected_source:
                raise Conflict('Authoritative records changed during rebuild; retry inspection')
            db.commit()
        finally:
            if db.in_transaction:
                db.rollback()
            db.close()
