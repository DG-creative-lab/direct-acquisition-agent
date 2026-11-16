"""SQLite compatibility journal and disposable workspace presentation records.

Each mutating operation owns its complete transaction. Domain guards are held
by the caller through that operation, never through later provider/effect work.
The authoritative environment store remains SqliteWorkspaceState.
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from acquisition.application.workspace import WorkspaceStorageUnavailable
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.local_root import require_live_root
from .workspace_ancestry import ensure_workspace_identity
from .workspace_projection import initialize_control_tables


class SqliteWorkspaceFaults:
    @contextmanager
    def guard(self):
        try:
            yield
        except sqlite3.Error as error:
            raise WorkspaceStorageUnavailable('Workspace storage is unavailable. Restore local storage and retry recovery.') from error


class SqliteWorkspaceControl:
    def __init__(self, root, faults):
        self.root = Path(root)
        self.faults = faults
        with self._connection(write=True) as db:
            initialize_control_tables(db)
            ensure_workspace_identity(db)

    @contextmanager
    def _connection(self, *, write=False):
        require_live_root(self.root)
        with self.faults.guard():
            db = sqlite3.connect(self.root / 'workspace.sqlite', timeout=10, isolation_level=None)
            db.row_factory = sqlite3.Row
            try:
                if write:
                    db.execute('BEGIN IMMEDIATE')
                yield db
                if write:
                    db.commit()
            except BaseException:
                if write:
                    db.rollback()
                raise
            finally:
                db.close()

    @staticmethod
    def _session(db, identity, organization=None):
        row = db.execute('SELECT * FROM sessions WHERE id=?', (identity,)).fetchone()
        if row is None:
            raise NotFound('Campaign not found in this workspace')
        session = json.loads(row['payload'])
        if organization is not None and session['organization'] != organization:
            raise Conflict('Campaign belongs to another organization')
        return session

    def sessions(self, *, reverse=False):
        with self._connection() as db:
            return [dict(row) for row in db.execute('SELECT * FROM sessions ORDER BY rowid' + (' DESC' if reverse else ''))]

    def session(self, identity):
        with self._connection() as db:
            row = db.execute('SELECT * FROM sessions WHERE id=?', (identity,)).fetchone()
            return dict(row) if row else None

    def project_session(self, session):
        with self._connection(write=True) as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                       (session['id'], digest({'projection': session['id']}), canonical(session)))

    def save_session(self, session):
        with self._connection(write=True) as db:
            self._session(db, session['id'], session['organization'])
            db.execute('UPDATE sessions SET payload=? WHERE id=?', (canonical(session), session['id']))

    def restore_case_links(self, organization, identity, run, case):
        with self._connection(write=True) as db:
            current = self._session(db, identity, organization)
            if current['case_id'] and current['case_id'] != case:
                raise Conflict('Checkpoint session already refers to another case')
            current |= {'run_id': run, 'case_id': case}
            db.execute('UPDATE sessions SET payload=? WHERE id=?', (canonical(current), identity))

    def checkpoint_block(self, organization, run):
        with self._connection() as db:
            row = db.execute('SELECT code FROM checkpoint_recovery_blocks WHERE organization=? AND run_id=?', (organization, run)).fetchone()
            return row[0] if row else None

    def set_checkpoint_block(self, organization, run, code):
        with self._connection(write=True) as db:
            if code is None:
                db.execute('DELETE FROM checkpoint_recovery_blocks WHERE organization=? AND run_id=?', (organization, run))
            else:
                db.execute('INSERT INTO checkpoint_recovery_blocks VALUES(?,?,?) ON CONFLICT(organization,run_id) DO UPDATE SET code=excluded.code WHERE code<>excluded.code', (organization, run, code))

    def revision_block(self, organization, revision):
        with self._connection() as db:
            row = db.execute('SELECT code FROM copy_revision_blocks WHERE organization=? AND revision_id=?', (organization, revision)).fetchone()
            return row[0] if row else None

    def set_revision_block(self, organization, revision, code):
        with self._connection(write=True) as db:
            if code is None:
                db.execute('DELETE FROM copy_revision_blocks WHERE organization=? AND revision_id=?', (organization, revision))
            else:
                db.execute('INSERT INTO copy_revision_blocks VALUES(?,?,?) ON CONFLICT(organization,revision_id) DO UPDATE SET code=excluded.code WHERE code<>excluded.code', (organization, revision, code))

    def draft_request(self, conversation, request):
        # The legacy conversation facade has one fixed server-owned scope,
        # local-conversations. This mapping grants no environment ownership.
        with self._connection() as db:
            row = db.execute('SELECT * FROM conversation_draft_requests WHERE conversation_id=? AND request_id=?', (conversation, request)).fetchone()
            return dict(row) if row else None

    def admit_draft(self, conversation, request, fingerprint, session):
        with self._connection(write=True) as db:
            replay = db.execute('SELECT * FROM conversation_draft_requests WHERE conversation_id=? AND request_id=?', (conversation, request)).fetchone()
            if replay is not None and (replay['request_hash'] != fingerprint or replay['session_id'] != session['id']):
                raise Conflict('Draft request already binds different proposal inputs')
            existing = db.execute('SELECT * FROM sessions WHERE id=?', (session['id'],)).fetchone()
            if existing is not None and existing['request_hash'] != fingerprint:
                raise Conflict('Campaign identity already binds different proposal inputs')
            if existing is None:
                db.execute('INSERT INTO sessions VALUES(?,?,?)', (session['id'], fingerprint, canonical(session)))
            if replay is None:
                db.execute('INSERT INTO conversation_draft_requests VALUES(?,?,?,?)', (conversation, request, fingerprint, session['id']))

    def admit_followup(self, organization, request, fingerprint, identity, session_fingerprint, session):
        with self._connection(write=True) as db:
            prior = db.execute('SELECT * FROM followup_prepare_requests WHERE organization=? AND request_id=?', (organization, request)).fetchone()
            if prior and (prior['request_hash'] != fingerprint or prior['session_id'] != identity):
                raise Conflict('Follow-up preparation request already binds different inputs')
            old = db.execute('SELECT * FROM sessions WHERE id=?', (identity,)).fetchone()
            if old and old['request_hash'] != session_fingerprint:
                raise Conflict('Follow-up already binds its original copy mode and permission')
            if not old:
                if session is None:
                    raise Conflict('Original campaign state changed before admission. Retry the same request')
                if session['organization'] != organization or session['id'] != identity:
                    raise Conflict('Follow-up session differs from its original scope')
                db.execute('INSERT INTO sessions VALUES(?,?,?)', (identity, session_fingerprint, canonical(session)))
            else:
                self._session(db, identity, organization)
            if not prior:
                db.execute('INSERT INTO followup_prepare_requests VALUES(?,?,?,?)', (organization, request, fingerprint, identity))

    def create_session(self, identity, fingerprint, session):
        with self._connection(write=True) as db:
            old = db.execute('SELECT * FROM sessions WHERE id=?', (identity,)).fetchone()
            if old and old['request_hash'] != fingerprint:
                raise Conflict('Campaign request already binds another copy mode')
            if old is None:
                if session is None:
                    raise Conflict('Original campaign state changed before admission. Retry the same request')
                if session['id'] != identity:
                    raise Conflict('Campaign identity differs from its request')
                db.execute('INSERT INTO sessions VALUES(?,?,?)', (identity, fingerprint, canonical(session)))

    def command(self, organization, identity, request):
        with self._connection() as db:
            self._session(db, identity, organization)
            row = db.execute('SELECT * FROM commands WHERE session_id=? AND request_id=?', (identity, request)).fetchone()
            return dict(row) if row else None

    def begin_command(self, organization, identity, request, fingerprint, *, next_due=None):
        with self._connection(write=True) as db:
            session = self._session(db, identity, organization)
            old = db.execute('SELECT * FROM commands WHERE session_id=? AND request_id=?', (identity, request)).fetchone()
            if old:
                if old['request_hash'] != fingerprint:
                    raise Conflict('Workspace request already binds different action inputs')
                return {'done': bool(old['done']), 'clock': session['clock']}
            if next_due is not None:
                session['clock'] = max(session['clock'], next_due)
                db.execute('UPDATE sessions SET payload=? WHERE id=?', (canonical(session), identity))
            db.execute('INSERT INTO commands VALUES(?,?,?,0)', (identity, request, fingerprint))
            return {'done': False, 'clock': session['clock']}

    def complete_command(self, organization, identity, request):
        with self._connection(write=True) as db:
            self._session(db, identity, organization)
            db.execute('UPDATE commands SET done=1 WHERE session_id=? AND request_id=?', (identity, request))
