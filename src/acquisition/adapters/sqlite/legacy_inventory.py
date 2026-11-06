"""Read-only discovery of known workspace history. No reconstruction or enrollment."""
import hashlib
import json
import math
import re
import sqlite3
from contextlib import ExitStack, contextmanager
from pathlib import Path

from acquisition.contracts import Conflict, digest
from acquisition.conversations import WORKSPACE_OWNER, identity as session_identifier, environment_time
from .execution import account_evidence
from .legacy_sources import LegacyFacts, record, record_id
from .workspace_projection import ReadOnlyDatabase, SqliteWorkspaceProjection, values_hash, sql_name
from .workspace_ancestry import JOURNAL_BINDING_KEY, journal_identity, pre_history_binding


def file_digest(path):
    result = {}
    for suffix in ('', '-wal', '-journal'):
        source = Path(str(path)+suffix)
        if source.is_file() and not source.is_symlink():
            hasher = hashlib.sha256()
            with source.open('rb') as stream:
                for block in iter(lambda: stream.read(65536), b''):
                    hasher.update(block)
            result[suffix or 'main'] = hasher.hexdigest()
    return result


def public_metadata(value):
    """Keep opaque malformed legacy values representable without printing payloads."""
    if value is None or type(value) in {str, int, bool}:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, dict):
        return {str(k): public_metadata(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [public_metadata(v) for v in value]
    return {'opaque_fingerprint': values_hash(value)}


SESSION_REFERENCE_FORMATS = {
    'id': r'workspace_[0-9a-f]{24}',
    'organization': r'(?:local-conversations|workspace_[0-9a-f]{24})',
    'run_id': r'run_[0-9a-f]{32}',
    'case_id': r'case_[0-9a-f]{64}',
    'cohort_id': r'cohort_[0-9a-f]{64}',
    'parent_id': r'workspace_[0-9a-f]{24}',
    'conversation_id': r'conversation_[0-9a-f]{32}',
    'plan_id': r'brief_[0-9a-f]{64}',
}


def native_session_reference(field, value):
    return value is None or (type(value) is str and re.fullmatch(SESSION_REFERENCE_FORMATS[field], value) is not None)


def legacy_session_metadata(session, original_id):
    """Validate the closed metadata projection before exporting or using a hint."""
    if type(session) is not dict or session.get('id') != original_id:
        raise Conflict('Legacy session identity differs from its journal key')
    for key in ('id','organization'):
        session_identifier(session[key])
    for key in ('run_id','case_id','cohort_id','parent_id'):
        if session.get(key) is not None:
            session_identifier(session[key])
    if type(session['mode']) is not str or session['mode'] not in {'fixture','model'}:
        raise Conflict('Legacy session mode is invalid')
    environment_time(session['clock'])
    if 'clock_mode' in session:
        if (type(session['clock_mode']) is not str or session['clock_mode'] not in {'REAL','SIMULATED'}
                or (session['mode']=='fixture' and session['clock_mode']!='SIMULATED')):
            raise Conflict('Legacy session clock mode is invalid')
    if session.get('database_scope') not in {None,'conversations','campaign'}:
        raise Conflict('Legacy session storage scope is invalid')
    plan = session.get('conversation_plan')
    if plan is not None:
        if type(plan) is not dict:
            raise Conflict('Legacy conversation hint is invalid')
        for key in ('id','conversation_id'):
            session_identifier(plan[key])
        if type(plan['revision']) is not int or plan['revision'] < 1:
            raise Conflict('Legacy conversation revision is invalid')
        plan = {k:plan[k] for k in ('id','conversation_id','revision')}
    # Other payload fields remain opaque evidence. Missing clock modes stay
    # missing rather than being upgraded to a current clock policy.
    return {k:session[k] for k in ('id','organization','mode','clock','clock_mode','database_scope') if k in session} | {
        k:session.get(k) for k in ('run_id','case_id','cohort_id','parent_id')} | {'conversation_plan':plan}


class SqliteLegacyInventory:
    def __init__(self, root, read_environment):
        self.root = Path(root)
        self.read_environment = read_environment

    @contextmanager
    def exclusive(self):
        lock = self.root/'server.lock'
        if lock.exists() and (not lock.is_file() or lock.stat().st_nlink != 1):
            raise Conflict('Use the original regular workspace lock file')
        with SqliteWorkspaceProjection(self.root).exclusive():
            yield

    def path(self, scope, key):
        if scope == 'conversations' and key == 'conversations':
            path = self.root/'conversations.sqlite'
        elif scope == 'campaign' and type(key) is str and re.fullmatch(r'workspace_[0-9a-f]{24}', key):
            path = self.root/key/'campaign.sqlite'
        else:
            raise Conflict('Unsupported canonical store reference')
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise Conflict('Store reference escapes its workspace root')
        return path

    @staticmethod
    def fingerprint(db):
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        schema = [tuple(r) for r in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        data = {table: sorted([tuple(r) for r in db.execute('SELECT * FROM '+sql_name(table))], key=repr) for table in tables}
        return values_hash((db.execute('PRAGMA user_version').fetchone()[0], schema, data)), set(tables)

    def snapshot(self, open_source=None):
        files, records, issues, hashes = [], [], [], {}
        with ExitStack() as stack:
            connections, metadata, inodes = {}, {}, {}

            def open_file(path, role, expected=None):
                key = str(path.relative_to(self.root))
                if key in metadata:
                    info = metadata[key]
                    if expected and info.get('store_identity') != expected:
                        info['state'] = 'conflicting'; issues.append({'source': key, 'code': 'registered_store_identity_mismatch'})
                    return connections.get(key), key
                info = {'key': key, 'role': role, 'state': 'missing'}
                files.append(info); metadata[key] = info
                if (path.is_symlink() and not path.resolve().is_relative_to(self.root.resolve())) or any(
                        Path(str(path)+s).is_symlink() for s in ('-wal','-shm','-journal')):
                    info['state'] = 'conflicting'; issues.append({'source': key, 'code': 'source_path_alias_is_unavailable'})
                    hashes[key] = 'unavailable_alias'; return None, key
                if not path.is_file():
                    issues.append({'source': key, 'code': 'source_is_missing'}); hashes[key] = 'missing'; return None, key
                stat = path.stat(); physical = (stat.st_dev, stat.st_ino)
                if physical in inodes and inodes[physical] != key:
                    info['state'] = 'conflicting'; metadata[inodes[physical]]['state'] = 'conflicting'
                    issues.append({'source': key, 'code': 'distinct_source_paths_alias_one_file'})
                    hashes[key] = file_digest(path); return None, key
                inodes[physical] = key
                try:
                    if open_source is None:
                        db = stack.enter_context(ReadOnlyDatabase.unmigrated(path).connect())
                        db.execute('BEGIN')
                    else:
                        db = open_source(path)
                    if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                        raise sqlite3.DatabaseError('integrity')
                    fingerprint, tables = self.fingerprint(db)
                    hashes[key] = fingerprint; info['schema_version'] = db.execute('PRAGMA user_version').fetchone()[0]
                    info['state'] = 'readable'; connections[key] = db
                    if role != 'journal' and not 1 <= info['schema_version'] <= 14:
                        info['state'] = 'unsupported'; issues.append({'source': key, 'code': 'unsupported_source_schema'})
                        return None, key
                    if 'application_store_identity' in tables:
                        identities = db.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchall()
                        info['store_identity'] = identities[0][0] if len(identities) == 1 else None
                    if expected and info.get('store_identity') != expected:
                        info['state'] = 'conflicting'; issues.append({'source': key, 'code': 'registered_store_identity_mismatch'})
                    if role != 'journal':
                        policy = db.execute('SELECT policy FROM admission_store_policy WHERE singleton=1').fetchone() if 'admission_store_policy' in tables else None
                        info['recorded_policy'] = policy[0] if policy else 'unsealed'
                        if policy and policy[0] != 'verified-paused/v1':
                            info['state'] = 'conflicting'; issues.append({'source': key, 'code': 'unsupported_recorded_policy'})
                    return db, key
                except (sqlite3.Error, ValueError, TypeError, KeyError, OSError):
                    info['state'] = 'unreadable'
                    issues.append({'source': key, 'code': 'source_requires_separate_sqlite_recovery'})
                    hashes[key] = file_digest(path); return None, key

            root, root_key = open_file(self.root/'conversations.sqlite', 'application')
            locations = {}
            if root:
                tables = {r[0] for r in root.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'workspace_locations' in tables:
                    for row in root.execute('SELECT * FROM workspace_locations WHERE organization=? ORDER BY id', (WORKSPACE_OWNER,)):
                        try:
                            path = self.path(row['store_scope'], row['store_key'])
                            open_file(path, 'registered_application', row['store_identity'])
                            locations[row['id']] = (dict(row), str(path.relative_to(self.root)))
                        except Conflict:
                            issues.append({'source': root_key, 'code': 'invalid_registered_store_reference'})
            journal, journal_key = open_file(self.root/'workspace.sqlite', 'journal')
            sessions = []
            if journal:
                tables = {r[0] for r in journal.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'workspace_identity' in tables:
                    try:
                        metadata[journal_key]['journal_identity'] = journal_identity(journal)
                    except Conflict:
                        issues.append({'source': journal_key, 'code': 'journal_identity_is_invalid'})
                if 'sessions' in tables:
                    columns={r[1] for r in journal.execute('PRAGMA table_info(sessions)')}
                    if not {'id','request_hash','payload'} <= columns:
                        issues.append({'source':journal_key,'code':'legacy_sessions_layout_is_incomplete'})
                        tables.discard('sessions')
                if 'sessions' in tables:
                    for raw in journal.execute('SELECT id,request_hash,payload FROM sessions ORDER BY rowid'):
                        value = record(journal_key, 'session', None, raw['id'])
                        value['missing'].append('legacy_journal_intent_requires_explicit_migration')
                        value['evidence'].append({'store': journal_key, 'table': 'sessions', 'key': raw['id'], 'fingerprint': values_hash(tuple(raw))})
                        if raw['id'] in locations:
                            value['format'] = 'projection'
                            value['missing'] = ['registered_environment_requires_validation']
                            records.append(value)
                            continue
                        try:
                            session = legacy_session_metadata(json.loads(raw['payload']),raw['id'])
                            shared = session.get('database_scope') == 'conversations' or bool(session.get('conversation_plan')) or session['organization'] == 'local-conversations'
                            path = self.path('conversations','conversations') if shared else self.path('campaign',session['organization'])
                            value['organization'] = session['organization']
                            value['id'] = record_id(journal_key,'session',session['organization'],session['id'])
                            value['preserve'] = {k:session[k] for k in ('mode','clock','clock_mode') if k in session}
                            for field in ('id','organization','run_id','case_id','cohort_id','parent_id'):
                                if field not in {'id','organization'}:
                                    value['preserve'][field] = session[field]
                                if not native_session_reference(field,session.get(field)):
                                    value['missing'].append('unverified_legacy_reference:'+field)
                            sessions.append((session, str(path.relative_to(self.root)), value))
                        except (Conflict, ValueError, TypeError, KeyError, OverflowError):
                            value['conflicts'].append('legacy_session_or_route_is_invalid')
                        records.append(value)
                if 'preparations' in tables:
                    columns={r[1] for r in journal.execute('PRAGMA table_info(preparations)')}
                    if not {'organization','id','request_id','conversation_id','revision','payload'} <= columns:
                        issues.append({'source':journal_key,'code':'legacy_preparations_layout_is_incomplete'})
                        tables.discard('preparations')
                if 'preparations' in tables:
                    for raw in journal.execute('SELECT * FROM preparations ORDER BY rowid'):
                        value = record(journal_key, 'preparation', raw['organization'], raw['id'])
                        value['missing'].append('legacy_journal_intent_requires_explicit_migration')
                        value['evidence'].append({'store': journal_key, 'table': 'preparations', 'organization': raw['organization'],
                                                  'key': raw['id'], 'fingerprint': values_hash(dict(raw))})
                        try:
                            payload = json.loads(raw['payload']); inputs = payload['inputs']
                            if (payload['id'] != raw['id'] or payload['request_id'] != raw['request_id']
                                    or inputs['conversation_id'] != raw['conversation_id'] or inputs['revision'] != raw['revision']
                                    or type(inputs['fixture']) is not bool or type(inputs['allow_model_copy']) is not bool
                                    or ('use_audience_catalogue' in inputs and type(inputs['use_audience_catalogue']) is not bool)
                                    or digest(payload['planning_context']) != payload['planning_context_id']):
                                raise Conflict('Preparation differs')
                            value['preserve'] = {'request_id': raw['request_id'], 'revision': raw['revision'],
                                                 'generation_choices_observed': inputs,
                                                 'frozen_context_fingerprint': payload['planning_context_id']}
                            if payload.get('run_id'):
                                value['parents'].append(record_id('conversations.sqlite', 'run', raw['organization'], payload['run_id']))
                        except (Conflict, ValueError, KeyError, TypeError):
                            value['conflicts'].append('legacy_preparation_integrity_failed')
                        records.append(value)

            for session, key, value in sessions:
                open_file(self.root/key, 'journal_referenced_application')

            for key, db in list(connections.items()):
                if key == journal_key or metadata[key]['state'] not in {'readable','conflicting'}:
                    continue
                facts = LegacyFacts(db, key)
                if not {'runs','tasks'} <= facts.tables:
                    issues.append({'source': key, 'code': 'runtime_journal_is_unavailable'}); continue
                required = {'runs':{'id','organization','request_id','request_hash','status'},
                            'tasks':{'id','run_id','position','capability','inputs','status','max_attempts'}}
                if any(not columns <= {r[1] for r in db.execute('PRAGMA table_info('+table+')')}
                       for table, columns in required.items()):
                    issues.append({'source':key,'code':'runtime_layout_is_unsupported'});continue
                scopes = set()
                for table in ('runs','conversation_plans','conversation_actions','admission_requests'):
                    if table in facts.tables:
                        scopes.update(r[0] for r in db.execute('SELECT DISTINCT organization FROM '+table))
                for org in sorted(scopes,key=repr):
                    records.extend(facts.pending(org))
                    association = facts.one('execution_commands', org, 'AND request_id=?', (JOURNAL_BINDING_KEY,))
                    bound_before_history = bool(association and pre_history_binding(db, org))
                    for run in facts.rows('runs', org, 'ORDER BY id'):
                        try:
                            value = facts.run(run)
                        except (sqlite3.Error, ValueError, TypeError, KeyError):
                            value = record(key, 'run', org, run['id']); value['missing'].append('runtime_source_is_unsupported_or_incomplete')
                        if facts.one('legacy_run_bindings', org, 'AND run_id=?', (run['id'],)):
                            value['migration_recorded'] = True
                        if facts.one('execution_pending_origins', org, 'AND run_id=?', (run['id'],)):
                            value['origin_pending'] = True
                        if association:
                            facts.evidence(value, 'execution_commands', JOURNAL_BINDING_KEY, association)
                            try:
                                inputs, receipt = json.loads(association['inputs']), json.loads(association['receipt'])
                                observed = metadata[journal_key].get('journal_identity', {})
                                matching = (type(inputs) is dict and bool(observed) and inputs == receipt
                                            and inputs.get('kind') == 'workspace_journal_binding'
                                            and inputs.get('journal_id') == observed.get('journal_id')
                                            and inputs.get('database_kind') == Path(key).name)
                                value['preserve']['journal_association'] = 'identity_match_completeness_unproven' if matching else 'identity_mismatch_or_missing'
                                value['journal_bound_before_history'] = matching and bound_before_history
                                if not matching and value['format'] != 'verified':
                                    value['conflicts'].append('bound_original_journal_is_missing_or_different')
                            except (ValueError,TypeError,KeyError):
                                value['conflicts'].append('historical_journal_binding_is_invalid')
                        records.append(value)
                if 'workflow_preparations' in facts.tables:
                    for raw in facts.rows('workflow_preparations','local-conversations','ORDER BY id'):
                        value = record(key, 'preparation','local-conversations', raw['id'], 'verified')
                        try:
                            from .preparation_intents import SqlitePreparationIntents
                            intent = SqlitePreparationIntents.decode(raw,db)
                            value['preserve'] = {'intent_fingerprint': raw['fingerprint'],
                                                 'request_id': raw['request_id'], 'revision': raw['revision']}
                            if intent['run_id']:
                                value['parents'].append(record_id(key,'run','local-conversations',intent['run_id']))
                            facts.evidence(value, 'workflow_preparations', raw['id'], raw)
                        except (Conflict, ValueError, TypeError, KeyError):
                            value['conflicts'].append('owned_preparation_integrity_failed')
                        records.append(value)

            for identity, (location, key) in sorted(locations.items()):
                db = connections.get(key)
                if db is None or metadata[key]['state'] != 'readable':
                    continue
                facts = LegacyFacts(db,key); org = location['run_organization']
                value = record(key,'environment',org,identity,'verified')
                projections = [r for r in records if r['kind']=='session' and r['format']=='projection' and r['key']==identity]
                for projection in projections:
                    projection['organization'] = org
                    projection['parents'] = [value['id']]
                try:
                    if metadata[root_key].get('recorded_policy') != 'verified-paused/v1' or metadata[key].get('recorded_policy') != 'verified-paused/v1':
                        raise Conflict('Environment requires its selected policy')
                    raw = facts.one('campaign_environments',org,'AND id=?',(identity,))
                    if raw is None:
                        value['missing'].append('registered_environment_intent_is_missing')
                    else:
                        facts.evidence(value,'campaign_environments',identity,raw)
                        session = self.read_environment(db,org,identity)
                        if session['organization'] != org or session['database_scope'] != location['store_scope']:
                            raise Conflict('Environment binding differs')
                        value['preserve'] = {k:session[k] for k in ('clock','clock_mode','run_id','case_id','cohort_id','mode')}
                        if session['run_id']:
                            value['parents'].append(record_id(key,'run',org,session['run_id']))
                        if session['parent_id']:
                            value['parents'].append(record_id(key,'environment',org,session['parent_id']))
                        for projection in projections:
                            projection['missing'] = []
                except (Conflict,ValueError,TypeError,KeyError,sqlite3.Error,RecursionError,OverflowError):
                    value['conflicts'].append('registered_environment_integrity_failed')
                records.append(value)

            # Workspace claims can expose a contradiction, never grant ownership
            # or turn absence of a parent into a standalone declaration.
            runs = {(r['store'], r['organization'], r['key']): r for r in records if r['kind'] == 'run'}
            requests = {(r['store'], r['organization'], r.get('native_request_id')): r for r in runs.values()}
            mapped_sessions = {}
            for session, key, value in sessions:
                scope = (key, session['organization'])
                run = runs.get((*scope, session['run_id']))
                request = requests.get((*scope, session['id']))
                if request is not None and session['run_id'] is not None and run is not request:
                    value['conflicts'].append('journal_runtime_mapping_conflicts')
                    for conflicting in (run, request):
                        if conflicting is not None:
                            conflicting['conflicts'].append('journal_runtime_mapping_conflicts')
                    continue
                source = run or request
                if source:
                    mapped_sessions[session['id']] = (session, source)
                    value['parents'].append(source['id'])
                    plan = session.get('conversation_plan')
                    if type(plan) is dict and type(plan.get('conversation_id')) is str and type(plan.get('revision')) is int:
                        verified_hint = (native_session_reference('conversation_id',plan['conversation_id'])
                                         and native_session_reference('plan_id',plan['id']))
                        if verified_hint:
                            claim = ['local-conversations','conversation',plan['conversation_id'],plan['revision']]
                            if 'journal_owner' in source and source['journal_owner'] != claim:
                                source['conflicts'].append('journal_conversation_claims_disagree')
                            source['journal_owner'] = claim
                        else:
                            value['missing'].append('unverified_legacy_conversation_hint')
                    elif plan:
                        source['conflicts'].append('journal_conversation_claim_is_invalid')
                else:
                    value['missing'].append('original_runtime_mapping_is_unavailable')
            for session, source in mapped_sessions.values():
                if session['parent_id'] is None:
                    continue
                parent = mapped_sessions.get(session['parent_id'])
                if parent is None or not source['parents']:
                    source['missing'].append('workspace_parent_claim_requires_domain_evidence')
                elif parent[1]['id'] not in source['parents']:
                    source['conflicts'].append('workspace_parent_claim_differs_from_domain_evidence')
            for value in records:
                if metadata.get(value['store'], {}).get('state') == 'conflicting':
                    value['conflicts'].append('source_identity_or_path_conflicts')
            migration_accounts = []
            if root and metadata[root_key].get('recorded_policy') == 'verified-paused/v1':
                for row in root.execute(
                    'SELECT a.organization,a.conversation_id,a.policy,a.call_limit,a.stopped_through '
                    'FROM conversation_execution a JOIN conversations c '
                    'ON c.organization=a.organization AND c.id=a.conversation_id '
                    'ORDER BY a.organization,a.conversation_id'):
                    if account_evidence(root, row['organization'], row['conversation_id']).resolved:
                        migration_accounts.append(list(row))
            result = {'files': sorted(files, key=lambda f: f['key']), 'records': sorted(records, key=lambda r: r['id']),
                      'migration_accounts': migration_accounts,
                      'issues': sorted(issues, key=lambda i: (i['source'],i['code']))}
            result = public_metadata(result)
            result['fingerprint'] = digest({'observations': result, 'source_hashes': hashes})
            return result
