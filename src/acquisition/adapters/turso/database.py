"""Remote libSQL transactions with the existing SQLite schema and writer rules."""
from contextlib import contextmanager
import sqlite3
import time

from acquisition.adapters.sqlite.database import Database
from .transport import Http, Connection, Busy, RemoteUnavailable, CommitUncertain


class SchemaConnection:
    """Explicit remote migration journal, atomically written with application DDL."""
    def __init__(self, connection):self.connection = connection
    def execute(self, sql, parameters=()):
        import re
        version = re.fullmatch(r'PRAGMA\s+user_version\s*(?:=\s*(\d+))?;?', sql.strip(), re.I)
        if version:
            if version[1] is not None:
                return self.connection.execute('UPDATE acquisition_schema SET version=? WHERE singleton=1', (int(version[1]),))
            return self.connection.execute('SELECT version FROM acquisition_schema WHERE singleton=1')
        return self.connection.execute(sql, parameters)
    def __getattr__(self, name):return getattr(self.connection, name)


class TursoDatabase(Database):
    """Explicit remote composition. No local paths, root locks or replica sync."""
    def __init__(self, url, token, *, clock=time.time, verified_admissions=False,
                 lock_seconds=15, initialize=True, deadline=None):
        if type(verified_admissions) is not bool:raise ValueError('Choose an explicit admission mode')
        if not 0 < lock_seconds <= 60:raise ValueError('Bound remote lock acquisition to 60 seconds')
        self.send, self.lock_seconds = Http(url, token, deadline=deadline), lock_seconds
        if initialize:
            self._initialize(verified_admissions, clock, False)
        else:
            if verified_admissions:raise ValueError('Select verified policy during migration')
            with self.connect() as db:
                if db.execute('PRAGMA user_version').fetchone()[0] != 23:
                    raise ValueError('Migrate the remote application store before opening')

    @property
    def inspection_only(self):
        return False

    @property
    def path(self):
        from acquisition.contracts import Conflict
        raise Conflict('Remote storage does not support local ancestry or checkpoint operations')

    @contextmanager
    def connect(self):
        connection = Connection(self.send)
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            yield SchemaConnection(connection)
        finally:connection.close()

    @contextmanager
    def transaction(self):
        # Retry only a positively rejected BEGIN, before exposing the connection.
        # The body and COMMIT are never automatically repeated.
        deadline = time.monotonic() + self.lock_seconds
        while True:
            with self.connect() as db:
                try:db.execute('BEGIN IMMEDIATE')
                except Busy:
                    if time.monotonic() >= deadline:raise
                else:
                    try:
                        if getattr(self, '_initializing', False):
                            registered = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='acquisition_schema'").fetchone()
                            if not registered:
                                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1").fetchone():
                                    raise ValueError('Remote store requires an explicit reviewed import')
                                db.execute('CREATE TABLE acquisition_schema(singleton INTEGER PRIMARY KEY CHECK(singleton=1),version INTEGER NOT NULL)')
                                db.execute('INSERT INTO acquisition_schema VALUES(1,0)')
                        yield db
                        db.commit()
                    except BaseException:
                        try:db.rollback()
                        except Exception:pass
                        raise
                    return
            time.sleep(min(.05, max(0, deadline - time.monotonic())))

    def _initialize(self, verified_admissions, clock, fixture_execution):
        # The journal is created inside the same migration transaction, not in
        # a separately committed setup step. Refuse unregistered application data.
        self._initializing = True
        try:super()._initialize(verified_admissions, clock, fixture_execution)
        finally:self._initializing = False

    @staticmethod
    def _apply_migration(connection, script):
        statements, pending = [], ''
        for line in script.splitlines(keepends=True):
            pending += line
            if sqlite3.complete_statement(pending):
                statements.append(pending);pending = ''
        if pending.strip():raise ValueError('Incomplete migration statement')
        import re
        batch = []
        for statement in statements:
            version = re.fullmatch(r'PRAGMA\s+user_version\s*=\s*(\d+);?', statement.strip(), re.I)
            batch.append(('UPDATE acquisition_schema SET version=? WHERE singleton=1', (int(version[1]),))
                         if version else (statement, ()))
        # The outer transaction owns rollback if any pipeline statement fails.
        connection.connection.pipeline(batch)
