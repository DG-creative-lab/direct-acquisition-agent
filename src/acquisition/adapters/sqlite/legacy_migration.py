"""Commit positively evidenced legacy ownership in a sealed application store."""
import json
import sqlite3
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path

from acquisition.contracts import Conflict, canonical
from acquisition.local_root import require_live_root
from acquisition.conversations import MIGRATION_STORE, WORKSPACE_OWNER
from .admission_guard import verified_required
from .database import Database
from .legacy_inventory import SqliteLegacyInventory
from .workspace_projection import ReadOnlyDatabase


MIGRATION_JOURNAL = """
CREATE TABLE IF NOT EXISTS legacy_migration_receipts(
 organization TEXT NOT NULL, plan_id TEXT NOT NULL, receipt TEXT NOT NULL,
 PRIMARY KEY(organization,plan_id));
CREATE TABLE IF NOT EXISTS legacy_run_bindings(
 organization TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES runs(id),
 receipt_organization TEXT NOT NULL, plan_id TEXT NOT NULL, binding TEXT NOT NULL,
 PRIMARY KEY(organization,run_id),
 FOREIGN KEY(receipt_organization,plan_id) REFERENCES legacy_migration_receipts(organization,plan_id),
 FOREIGN KEY(organization,run_id) REFERENCES execution_runs(organization,run_id));
CREATE TRIGGER IF NOT EXISTS legacy_migration_receipt_no_update BEFORE UPDATE ON legacy_migration_receipts
 BEGIN SELECT RAISE(ABORT,'Legacy migration receipts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS legacy_migration_receipt_no_delete BEFORE DELETE ON legacy_migration_receipts
 BEGIN SELECT RAISE(ABORT,'Legacy migration receipts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS legacy_migration_receipt_no_replace BEFORE INSERT ON legacy_migration_receipts
 WHEN EXISTS(SELECT 1 FROM legacy_migration_receipts WHERE organization=NEW.organization AND plan_id=NEW.plan_id)
 BEGIN SELECT RAISE(ABORT,'Legacy migration receipts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS legacy_run_binding_no_update BEFORE UPDATE ON legacy_run_bindings
 BEGIN SELECT RAISE(ABORT,'Legacy migration bindings are immutable'); END;
CREATE TRIGGER IF NOT EXISTS legacy_run_binding_no_delete BEFORE DELETE ON legacy_run_bindings
 BEGIN SELECT RAISE(ABORT,'Legacy migration bindings are immutable'); END;
CREATE TRIGGER IF NOT EXISTS legacy_run_binding_no_replace BEFORE INSERT ON legacy_run_bindings
 WHEN EXISTS(SELECT 1 FROM legacy_run_bindings WHERE organization=NEW.organization AND run_id=NEW.run_id)
 BEGIN SELECT RAISE(ABORT,'Legacy migration bindings are immutable'); END;
"""


def file_identity(root, path):
    if any(part.is_symlink() for part in (path, *path.parents) if part != root and part.is_relative_to(root)):
        raise Conflict('Migration sources must use canonical local paths')
    for suffix in ('-wal', '-shm', '-journal'):
        sidecar = Path(str(path) + suffix)
        if sidecar.is_symlink() or (sidecar.exists() and (not sidecar.is_file() or sidecar.stat().st_nlink != 1)):
            raise Conflict('Migration sidecars must be regular files without aliases')
    if not path.is_file():
        raise Conflict('Migration requires existing application and journal files')
    stat = path.stat()
    if stat.st_nlink != 1:
        raise Conflict('Migration sources must be regular files without aliases')
    return stat.st_dev, stat.st_ino


class SqliteLegacyMigration(SqliteLegacyInventory):
    def receipt(self, plan_id):
        path = self.root / MIGRATION_STORE
        file_identity(self.root, path)
        with ReadOnlyDatabase.unmigrated(path).connect() as db:
            db.execute('BEGIN')
            return read_receipt(db, plan_id)

    @contextmanager
    def transaction(self):
        require_live_root(self.root)
        with ExitStack() as stack:
            opened = {}

            def lock(path):
                if path in opened:
                    return opened[path][0]
                original = file_identity(self.root, path)
                journal = Path(str(path) + '-journal')
                if journal.exists() and journal.stat().st_size:
                    raise Conflict('Recover the rollback journal separately before migration')
                db = stack.enter_context(closing(sqlite3.connect(
                    path.resolve().as_uri() + '?mode=rw', uri=True, timeout=10, isolation_level=None)))
                db.row_factory = sqlite3.Row
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('BEGIN IMMEDIATE')
                if file_identity(self.root, path) != original:
                    raise Conflict('A migration source was replaced while opening it')
                opened[path] = (db, original)
                return db

            # Existing ancestry reconciliation takes these locks in this order.
            lock(self.root / 'workspace.sqlite')
            target = lock(self.root / MIGRATION_STORE)
            if (target.execute('PRAGMA user_version').fetchone()[0] != 14
                    or not verified_required(target)):
                raise Conflict('Apply requires an already sealed schema-14 conversation store')
            Database._validate_workspace_schema(target)
            yield MigrationTransaction(target, lambda: self.snapshot(open_source=lock))
            for path, (_, original) in opened.items():
                if file_identity(self.root, path) != original:
                    raise Conflict('A migration source was replaced during apply')
            # Keep the auxiliary write locks until the only writable target commits.
            target.commit()


def read_receipt(db, plan_id):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='legacy_migration_receipts'").fetchone():
        return None
    row = db.execute('SELECT receipt FROM legacy_migration_receipts WHERE organization=? AND plan_id=?',
                     (WORKSPACE_OWNER, plan_id)).fetchone()
    return json.loads(row['receipt']) if row else None


class MigrationTransaction:
    def __init__(self, db, snapshot):
        self.db = db
        self.snapshot = snapshot

    def receipt(self, plan_id):
        return read_receipt(self.db, plan_id)

    def save(self, bindings, receipt):
        Database._apply_migration(self.db, MIGRATION_JOURNAL)
        self.db.execute('INSERT INTO legacy_migration_receipts VALUES(?,?,?)',
                        (WORKSPACE_OWNER, receipt['plan_id'], canonical(receipt)))
        for binding in bindings:
            org, run_id = binding['organization'], binding['run_id']
            owner, _, conversation, revision = binding['owner']
            existing = self.db.execute(
                'SELECT owner_organization,conversation_id,revision FROM execution_runs WHERE organization=? AND run_id=?',
                (org, run_id)).fetchone()
            pending = self.db.execute('SELECT 1 FROM execution_pending_origins WHERE organization=? AND run_id=?',
                                      (org, run_id)).fetchone()
            if pending or existing is None or tuple(existing) != (owner, conversation, revision):
                raise Conflict('Migration requires existing ownership with no unresolved origin')
            self.db.execute('INSERT INTO legacy_run_bindings VALUES(?,?,?,?,?)',
                            (org, run_id, WORKSPACE_OWNER, receipt['plan_id'], canonical(binding)))
