"""Cold snapshots of the canonical local workspace, with inspection-only publication."""
import hashlib
import json
import os
import re
import sqlite3
import stat
from contextlib import ExitStack, closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from acquisition.contracts import Conflict, canonical, digest
from acquisition.conversations import WORKSPACE_OWNER
from acquisition.local_root import CHECKPOINT_FILE, workspace_root_lock, require_live_root
from .admission_guard import verified_required
from .database import Database
from .legacy_inventory import legacy_session_metadata
from .legacy_migration import file_identity
from .workspace_ancestry import JOURNAL_BINDING_KEY, journal_identity


FORMAT = 'workspace-checkpoint/v1'
ROOT = 'conversations.sqlite'
JOURNAL = 'workspace.sqlite'
CAMPAIGN = r'workspace_[0-9a-f]{24}'
MAX_FILES = 64
MAX_BYTES = 2 * 1024**3
MAX_MANIFEST = 128 * 1024
SIDECARS = ('-wal', '-shm', '-journal')


def store_key(scope, key):
    if scope == 'conversations' and key == 'conversations':
        return ROOT
    if scope == 'campaign' and isinstance(key, str) and re.fullmatch(CAMPAIGN, key):
        return key + '/campaign.sqlite'
    raise Conflict('The checkpoint contains an unsupported workspace store reference')


def directory(path):
    if path.is_symlink() or not path.is_dir():
        raise Conflict('Use a regular local directory for the workspace or checkpoint')
    return path.resolve()


def scan_stores(root):
    keys = [JOURNAL, ROOT]
    for entry in root.iterdir():
        if re.fullmatch(CAMPAIGN, entry.name):
            directory(entry)
            path = entry / 'campaign.sqlite'
            if any(os.path.lexists(str(path) + suffix) for suffix in ('', *SIDECARS)):
                keys.append(store_key('campaign', entry.name))
                if len(keys) > MAX_FILES:
                    raise Conflict('The workspace exceeds the checkpoint store limit')
    return sorted(keys)


def connect(path, mode):
    db = sqlite3.connect(path.as_uri() + '?' + mode, uri=True, timeout=0, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA trusted_schema=OFF')
    return closing(db)


@contextmanager
def read_file(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Conflict('Checkpoint inputs must be regular files without aliases')
        yield stream, info.st_size


def file_metadata(path, remaining):
    with read_file(path) as (stream, size):
        if not 0 < size <= remaining:
            raise Conflict('The checkpoint exceeds the size limit or contains an empty file')
        header = stream.read(100)
        if header[:16] != b'SQLite format 3\x00' or header[18:20] != b'\x01\x01':
            raise Conflict('A checkpoint file is not a self-contained SQLite snapshot')
        hasher = hashlib.sha256(header)
        count = len(header)
        for block in iter(lambda: stream.read(1024**2), b''):
            count += len(block)
            if count > size:
                raise Conflict('A checkpoint file changed during validation')
            hasher.update(block)
    if count != size:
        raise Conflict('A checkpoint file changed during validation')
    return {'bytes': size, 'sha256': hasher.hexdigest()}


def validate_stores(connections):
    root, journal = connections[ROOT], connections[JOURNAL]
    journal_id = journal_identity(journal)['journal_id']
    locations = set()
    registered = {ROOT: set()}
    for row in root.execute('SELECT * FROM workspace_locations WHERE organization=?', (WORKSPACE_OWNER,)):
        key = store_key(row['store_scope'], row['store_key'])
        if key not in connections:
            raise Conflict('A registered workspace application store is missing')
        if key != ROOT and row['run_organization'] != Path(key).parent.name:
            raise Conflict('A registered workspace location differs from its campaign organization')
        registered.setdefault(key, set()).add(row['store_identity'])
        locations.add((key, row['run_organization'], row['id']))

    # Owned rows are projections in this journal. For legacy rows, preserve
    # opaque payloads and require stores referenced by positively recorded links.
    projected = {identity for _, _, identity in locations}
    for row in journal.execute('SELECT id,payload FROM sessions'):
        if row['id'] in projected:
            continue
        try:
            session = legacy_session_metadata(json.loads(row['payload']), row['id'])
            shared = (session.get('database_scope') == 'conversations' or session.get('conversation_plan')
                      or session['organization'] == 'local-conversations')
            key = ROOT if shared else store_key('campaign', session['organization'])
        except (Conflict, KeyError, TypeError, ValueError, OverflowError, RecursionError):
            continue  # Opaque legacy evidence stays in the journal.
        if key not in connections and any(session.get(field) for field in ('run_id', 'case_id', 'cohort_id')):
            raise Conflict('An application store referenced by the legacy journal is missing')

    metadata = {}
    for key, db in connections.items():
        if [tuple(row) for row in db.execute('PRAGMA integrity_check')] != [('ok',)]:
            raise Conflict('A checkpoint store failed SQLite integrity checks')
        if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise Conflict('A checkpoint store has invalid SQLite foreign keys')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if key == JOURNAL:
            if version != 0 or db.execute("SELECT 1 FROM sqlite_schema WHERE name='application_store_identity'").fetchone():
                raise Conflict('Unsupported workspace journal schema')
            metadata[key] = {'role': 'workspace-journal', 'identity': journal_id, 'schema': version}
            continue
        if version not in {14, 15, 16, 17, 18, 19}:
            raise Conflict('Checkpoint application stores require schema 14 through 19')
        if version >= 15:
            try:
                db.execute('SELECT organization,id,revision,request_id,fingerprint,payload FROM writing_preference_versions LIMIT 0')
            except sqlite3.DatabaseError as error:
                raise Conflict('Writing preference history is unavailable') from error
        if version >= 16:
            try:
                Database._validate_simulated_delivery_schema(db)
            except sqlite3.DatabaseError as error:
                raise Conflict('Simulated delivery history is unavailable') from error
        if version >= 17:
            try:
                Database._validate_report_monitoring_schema(db)
            except sqlite3.DatabaseError as error:
                raise Conflict('Recorded report monitoring history is unavailable') from error
        if version >= 18:
            try:
                Database._validate_contact_schema(db)
            except sqlite3.DatabaseError as error:
                raise Conflict('Contact evidence history is unavailable') from error
        if version >= 19:
            try:
                Database._validate_recipient_context_schema(db)
            except sqlite3.DatabaseError as error:
                raise Conflict('Recipient context history is unavailable') from error
        ids = db.execute('SELECT singleton,id FROM application_store_identity').fetchall()
        if (len(ids) != 1 or ids[0][0] != 1 or not isinstance(ids[0][1], str)
                or not re.fullmatch(r'store_[0-9a-f]{32}', ids[0][1])):
            raise Conflict('A checkpoint application store has invalid identity')
        identity = ids[0][1]
        paused = verified_required(db)
        if key in registered and not paused:
            raise Conflict('The root and registered application stores must be verified-paused')
        expected_ids = registered.get(key)
        if expected_ids and expected_ids != {identity}:
            raise Conflict('A registered workspace application store has a different identity')
        for row in db.execute('SELECT organization,id FROM campaign_environments'):
            if (key, row['organization'], row['id']) not in locations:
                raise Conflict('An authoritative environment is missing its registered workspace location')
        for row in db.execute('SELECT inputs,receipt FROM execution_commands WHERE request_id=?', (JOURNAL_BINDING_KEY,)):
            binding = json.loads(row['inputs'])
            if (binding != json.loads(row['receipt']) or binding.get('kind') != 'workspace_journal_binding'
                    or binding.get('journal_id') != journal_id or binding.get('database_kind') != Path(key).name):
                raise Conflict('The workspace journal differs from a recorded application binding')
        if (db.execute("SELECT 1 FROM tasks WHERE status='running' LIMIT 1").fetchone()
                or db.execute("SELECT 1 FROM model_calls WHERE status='reserved' LIMIT 1").fetchone()):
            raise Conflict('Quiesce running tasks and reconcile reserved inference before backup')
        metadata[key] = {
            'role': 'registered-application' if key in registered else 'legacy-application',
            'identity': identity, 'schema': version,
            'recorded_policy': 'verified-paused/v1' if paused else 'unsealed',
        }
    if len({info['identity'] for info in metadata.values()}) != len(metadata):
        raise Conflict('Distinct checkpoint paths refer to the same store identity')
    return metadata


def validate_layout(root):
    keys = scan_stores(root)
    expected_dirs = {Path(key).parent.name for key in keys if '/' in key}
    if {entry.name for entry in root.iterdir()} != {ROOT, JOURNAL, CHECKPOINT_FILE} | expected_dirs:
        raise Conflict('The checkpoint directory has missing or unexpected files')
    for name in expected_dirs:
        if {entry.name for entry in (root / name).iterdir()} != {'campaign.sqlite'}:
            raise Conflict('A checkpoint store directory has missing or unexpected files')
    return keys


def checkpoint_file_stamp(path):
    info = path.stat(follow_symlinks=False)
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


@contextmanager
def open_checkpoint(root):
    """Keep the validated read-only SQLite connections open for inspection."""
    keys = validate_layout(root)
    manifest_path = root / CHECKPOINT_FILE
    file_identity(root, manifest_path)
    stamps = {manifest_path: checkpoint_file_stamp(manifest_path)}
    with read_file(manifest_path) as (stream, _):
        raw = stream.read(MAX_MANIFEST + 1)
    if len(raw) > MAX_MANIFEST:
        raise Conflict('The checkpoint manifest exceeds the size limit')
    manifest = json.loads(raw)
    if (type(manifest) is not dict or set(manifest) != {'format', 'created_at', 'stores', 'checkpoint_id'}
            or manifest['format'] != FORMAT or canonical(manifest).encode() != raw
            or type(manifest['stores']) is not dict or set(manifest['stores']) != set(keys)):
        raise Conflict('Unsupported or incomplete checkpoint manifest')
    payload = {k: v for k, v in manifest.items() if k != 'checkpoint_id'}
    if manifest['checkpoint_id'] != digest(payload):
        raise Conflict('The manifest differs from its checkpoint identity')
    created_at = datetime.fromisoformat(manifest['created_at'])
    if created_at.tzinfo != timezone.utc:
        raise Conflict('Unsupported checkpoint timestamp')
    with ExitStack() as stack:
        files, connections = {}, {}
        remaining = MAX_BYTES
        for key in keys:
            path = root / key
            file_identity(root, path)
            stamps[path] = checkpoint_file_stamp(path)
            info = file_metadata(path, remaining)
            remaining -= info['bytes']
            expected = manifest['stores'][key]
            if type(expected) is not dict or any(expected.get(k) != v for k, v in info.items()):
                raise Conflict('A checkpoint SQLite file differs from its manifest')
            files[key] = info
            connections[key] = stack.enter_context(connect(path, 'mode=ro&immutable=1'))
        for key, info in validate_stores(connections).items():
            if canonical(info | files[key]) != canonical(manifest['stores'][key]):
                raise Conflict('A checkpoint store differs from its recorded identity or schema')
        yield manifest, connections
        if keys != validate_layout(root) or any(checkpoint_file_stamp(path) != stamp for path, stamp in stamps.items()):
            raise Conflict('The checkpoint changed during inspection')


def validate_checkpoint(root):
    with open_checkpoint(root) as (manifest, _):
        return manifest


def output_path(value, source):
    value = Path(value)
    if value.name in {'', '..'}:
        raise Conflict('Choose a named destination directory')
    parent = directory(value.parent)
    destination = parent / value.name
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise Conflict('The checkpoint source and destination must be disjoint')
    require_live_root(parent)
    require_empty(destination)
    return destination


def require_empty(path):
    if os.path.lexists(path) and (path.is_symlink() or not path.is_dir() or any(path.iterdir())):
        raise Conflict('Choose a new or empty destination directory')


@contextmanager
def stage_output(destination):
    # A killed process can leave this private sibling. Fence even partial
    # databases there, before any source data is copied.
    with TemporaryDirectory(prefix='.acquisition-checkpoint-', dir=destination.parent) as staging:
        stage = Path(staging)
        (stage / CHECKPOINT_FILE).touch(mode=0o600)
        yield stage
        for path in sorted(stage.rglob('*'), key=lambda item: -len(item.parts)):
            sync(path)
        sync(stage)
        require_empty(destination)
        stage.rename(destination)
        sync(destination.parent)


def sync(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def snapshot_sqlite(path, target):
    target.parent.mkdir(mode=0o700, exist_ok=True)
    target.touch(mode=0o600, exist_ok=False)
    with connect(path, 'mode=ro') as source, connect(target, 'mode=rw') as snapshot:
        source.backup(snapshot, pages=1024, sleep=0)
        if snapshot.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
            raise Conflict('SQLite did not produce a self-contained snapshot')


def copy_snapshot(source, target, expected_size):
    with read_file(source) as (stream, size):
        if size != expected_size:
            raise Conflict('A checkpoint file changed before restore')
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as copy:
            # Bound reads even if a source grows after its size is checked.
            remaining = expected_size + 1
            while remaining and (block := stream.read(min(remaining, 1024**2))):
                copy.write(block)
                remaining -= len(block)


class SqliteWorkspaceCheckpoint:
    def create(self, root, bundle):
        root = directory(Path(root))
        require_live_root(root)
        bundle = output_path(bundle, root)
        with workspace_root_lock(root), ExitStack() as stack:
            keys = scan_stores(root)
            # Ancestry reconciliation locks the journal before application stores.
            locks, identities = {}, {}
            remaining = MAX_BYTES
            for key in [JOURNAL, *[key for key in keys if key != JOURNAL]]:
                path = root / key
                identities[key] = file_identity(root, path)
                journal = Path(str(path) + '-journal')
                if journal.exists() and journal.stat().st_size:
                    raise Conflict('Recover the source rollback journal separately before backup')
                db = stack.enter_context(connect(path, 'mode=rw'))
                db.execute('BEGIN IMMEDIATE')
                if file_identity(root, path) != identities[key]:
                    raise Conflict('A source store was replaced while opening it')
                locks[key] = db
                remaining -= db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0]
                if remaining < 0:
                    raise Conflict('The workspace exceeds the checkpoint size limit')

            created_at = datetime.now(timezone.utc).isoformat()
            metadata = validate_stores(locks)
            with stage_output(bundle) as stage:
                remaining = MAX_BYTES
                for key in keys:
                    snapshot_sqlite(root / key, stage / key)
                    info = file_metadata(stage / key, remaining)
                    remaining -= info['bytes']
                    metadata[key] |= info
                manifest = {'format': FORMAT, 'created_at': created_at, 'stores': metadata}
                manifest['checkpoint_id'] = digest(manifest)
                (stage / CHECKPOINT_FILE).write_text(canonical(manifest), encoding='utf-8')
                validate_checkpoint(stage)
                if keys != scan_stores(root) or any(file_identity(root, root / key) != identities[key] for key in keys):
                    raise Conflict('The source store inventory changed during backup')
        return manifest

    def verify(self, bundle):
        return validate_checkpoint(directory(Path(bundle)))

    def restore(self, bundle, root, checkpoint_id):
        bundle = directory(Path(bundle))
        root = output_path(root, bundle)
        manifest = validate_checkpoint(bundle)
        if manifest['checkpoint_id'] != checkpoint_id:
            raise Conflict('The bundle differs from the requested checkpoint identity')
        with stage_output(root) as stage:
            for key, info in manifest['stores'].items():
                target = stage / key
                target.parent.mkdir(mode=0o700, exist_ok=True)
                copy_snapshot(bundle / key, target, info['bytes'])
            (stage / CHECKPOINT_FILE).write_text(canonical(manifest), encoding='utf-8')
            validate_checkpoint(stage)
        return manifest
