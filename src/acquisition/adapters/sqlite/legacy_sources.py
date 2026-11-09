"""Version-bounded readers of historical evidence. No ownership writes or live policy checks."""
import json
from dataclasses import asdict

from acquisition.contracts import Conflict, digest
from acquisition.conversations import CAPABILITY, FIXTURE_CAPABILITY, ROUTING_CAPABILITIES
from acquisition.reasoning import ModelConfig
from .admission_guard import binding
from .execution import DEFINITIVE_REJECTIONS, descendant_parent, campaign_parent
from .workspace_projection import values_hash


def record_id(store, kind, organization, key):
    return 'inventory_' + values_hash([store, kind, organization, key])


def record(store, kind, organization, key, format='legacy'):
    return {'id': record_id(store, kind, organization, key), 'kind': kind, 'store': store,
            'organization': organization, 'key': key, 'format': format, 'evidence': [],
            'conflicts': [], 'missing': [], 'uncertain': [], 'owners': [], 'parents': [],
            'permission_recorded': False, 'preserve': {}}


class LegacyFacts:
    def __init__(self, db, store):
        self.db, self.store = db, store
        self.tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def rows(self, table, organization, suffix='', params=()):
        if table not in self.tables:
            return []
        return [dict(r) for r in self.db.execute('SELECT * FROM '+table+' WHERE organization=? '+suffix, (organization, *params))]

    def one(self, table, organization, suffix='', params=()):
        values = self.rows(table, organization, suffix, params)
        return values[0] if values else None

    def evidence(self, result, table, key, value, organization=None):
        ref = {'store': self.store, 'table': table, 'organization': organization or result['organization'],
               'key': key, 'fingerprint': values_hash(value)}
        result['evidence'].append(ref)

    def owner(self, result, organization, conversation, revision):
        row = self.one('conversations', organization, 'AND id=?', (conversation,))
        if row is None:
            result['missing'].append('original_conversation_is_unavailable')
        elif type(revision) is not int or revision < 1 or row['revision'] < revision:
            result['conflicts'].append('source_revision_differs_from_conversation')
        else:
            result['owners'].append([organization, 'conversation', conversation, revision])
            self.evidence(result, 'conversations', conversation, row, organization)
            result['preserve']['current_revision'] = row['revision']
            account = self.one('conversation_execution', organization, 'AND conversation_id=?', (conversation,))
            result['preserve']['recorded_execution_account'] = ({k:account[k] for k in
                ('policy','call_limit','stopped_through')} if account else None)

    @staticmethod
    def config(config):
        if type(config) is not dict:
            raise Conflict('Frozen model settings are missing')
        parsed = asdict(ModelConfig(**config))
        if parsed != config:
            raise Conflict('Frozen model settings are incomplete')
        return digest(config)

    @staticmethod
    def specs(tasks):
        return [{'capability': t['capability'], 'inputs': json.loads(t['inputs']), 'max_attempts': t['max_attempts']} for t in tasks]

    def pending(self, organization):
        """Retain admitted native sources whose runtime write never completed."""
        result = []
        for table in ('conversation_plans', 'conversation_actions', 'admission_requests'):
            for row in self.rows(table, organization):
                key = row.get('id', row['request_id'])
                value = record(self.store, 'pending_admission', organization, table+':'+key)
                self.evidence(value, table, key, row)
                try:
                    payload = json.loads(row['payload'])
                    if table == 'admission_requests':
                        if self.one('execution_admissions', organization, 'AND request_id=?', (row['request_id'],)):
                            continue
                        from .admissions import SqliteAdmissions
                        intent = SqliteAdmissions._request_intent(row)
                        value['format'] = 'verified'
                        value['preserve']['intent_fingerprint'] = intent.fingerprint
                        value['missing'].append('staged_request_requires_atomic_admission')
                    else:
                        if table == 'conversation_actions' and payload.get('alias') is not None:
                            continue
                        if self.one('runs', organization, 'AND request_id=?', (payload['run_request_id'],)):
                            continue
                        value['preserve']['native_request_id'] = row['request_id']
                        value['preserve']['revision'] = row['revision']
                        value['missing'].append('native_source_has_no_runtime_mapping')
                except (Conflict,ValueError,KeyError,TypeError):
                    value['conflicts'].append('pending_source_integrity_is_unresolved')
                result.append(value)
        return result

    def native(self, result, run, tasks):
        org, key = run['organization'], run['request_id']
        specs = self.specs(tasks)
        first = specs[0]['inputs'] if specs else {}
        caps = [t['capability'] for t in tasks]
        if caps and caps[0] in {CAPABILITY, FIXTURE_CAPABILITY}:
            matches = [r for r in self.rows('conversation_plans', org) if json.loads(r['payload']).get('run_request_id') == key]
            if len(matches) != 1:
                result['missing'].append('original_planning_admission_is_missing'); return
            row = matches[0]; frozen = json.loads(row['payload'])
            fixture = caps[0] == FIXTURE_CAPABILITY
            expected = [{'capability': caps[0], 'inputs': frozen, 'max_attempts': 3}]
            if (specs != expected or frozen['conversation_id'] != row['conversation_id'] or frozen['request_id'] != row['request_id']
                    or frozen['revision'] != row['revision'] or frozen['knowledge_id'] != 'knowledge_'+digest(frozen['knowledge'])
                    or bool(frozen.get('fixture')) != fixture):
                raise Conflict('Native planning evidence differs')
            result['permission_recorded'] = True
            if not fixture:
                result['preserve']['model_config_fingerprint'] = self.config(frozen['model_config'])
            self.owner(result, org, row['conversation_id'], row['revision'])
            self.evidence(result, 'conversation_plans', row['request_id'], row)
            return
        if caps and caps[0] in ROUTING_CAPABILITIES:
            matches = [r for r in self.rows('conversation_actions', org) if json.loads(r['payload']).get('run_request_id') == key]
            if len(matches) != 1:
                result['missing'].append('original_routing_admission_is_missing'); return
            row = matches[0]; frozen = json.loads(row['payload'])
            if (specs != [{'capability': caps[0], 'inputs': frozen, 'max_attempts': 3}] or frozen.get('alias') is not None
                    or frozen['inputs']['conversation_id'] != row['conversation_id'] or frozen['inputs']['revision'] != row['revision']
                    or frozen['request_id'] != row['request_id'] or frozen['organization'] != org or frozen['id'] != row['id']):
                raise Conflict('Native routing evidence differs')
            result['preserve']['model_config_fingerprint'] = self.config(frozen['model_config'])
            result['permission_recorded'] = True
            result['preserve']['permission_scope'] = 'routing_only'
            self.owner(result, org, row['conversation_id'], row['revision'])
            self.evidence(result, 'conversation_actions', row['id'], row)
            return
        if caps and caps[0] == 'creative.revise_copy.v3':
            row = self.one('review_commands', org, 'AND request_id=?', (first.get('admission_request_id'),))
            if row is None:
                result['missing'].append('original_revision_admission_is_missing'); return
            receipt = json.loads(row['receipt']); inputs = receipt.get('inputs', {})
            expected = receipt.get('task_inputs', {}) | {'context_id': 'context_'+digest({'organization': org, **receipt.get('context', {})})}
            if (receipt.get('kind') != 'copy_revision_admission' or receipt.get('id') != key
                    or inputs.get('allow_model_copy') is not True
                    or row['request_hash'] != digest({'actor': inputs['actor'], 'kind': 'copy_revision', 'payload': inputs})
                    or specs != [{'capability': cap, 'inputs': expected, 'max_attempts': 3}
                                 for cap in ('creative.revise_copy.v3', 'reviews.publish_copy_revision.v3')]):
                raise Conflict('Native copy revision evidence differs')
            case = self.one('review_cases', org, 'AND id=?', (inputs['case_id'],))
            if case is None:
                result['missing'].append('original_revision_case_is_missing')
            else:
                result['parents'].append(record_id(self.store, 'run', org, case['run_id']))
                self.evidence(result, 'review_cases', case['id'], case)
            result['permission_recorded'] = True
            result['preserve']['permission_scope'] = 'exact_copy_revision_only'
            result['preserve']['model_config_fingerprint'] = self.config(expected['model_config'])
            self.evidence(result, 'review_commands', row['request_id'], row)
            return
        brief = first.get('brief', {})
        if type(brief) is not dict:
            raise Conflict('Frozen campaign brief is invalid')
        fixture_caps = ['audiences.inspect.v1', 'campaigns.build_draft.v1', 'campaigns.review_checkpoint.v1']
        conversation_caps = ['audiences.inspect_conversation.v1', 'campaigns.build_conversation.v1', 'campaigns.review_conversation.v1']
        fixture = caps in (fixture_caps, conversation_caps) and first.get('model_config') is None
        if fixture:
            if specs != [{'capability': cap, 'inputs': first, 'max_attempts': 5 if i == 2 else 3} for i, cap in enumerate(caps)]:
                raise Conflict('Historical fixture task plan differs')
            result['permission_recorded'] = True
            result['preserve']['permission_scope'] = 'fixture_only'
        else:
            result['missing'].append('legacy_workflow_permission_requires_source_review')
        if brief.get('conversation_id'):
            conversation = brief['conversation_id']; revision = brief.get('conversation_revision')
            plan = self.one('conversation_plans', 'local-conversations', 'AND conversation_id=? AND revision=?', (conversation, revision))
            frozen = json.loads(plan['payload']) if plan else None
            parent = self.one('runs', 'local-conversations', 'AND request_id=?', (frozen['run_request_id'],)) if frozen else None
            source = self.db.execute("SELECT output FROM tasks WHERE run_id=? AND position=0 AND status='succeeded'", (parent['id'],)).fetchone() if parent else None
            proposal = json.loads(source[0]) if source and source[0] else None
            if proposal is None:
                result['missing'].append('original_campaign_proposal_is_missing')
            elif (proposal.get('id') != brief.get('plan_id') or proposal['id'] != 'brief_'+digest({
                    'organization': 'local-conversations', 'request_id': frozen['request_id'],
                    'result': {k: v for k, v in proposal.items() if k != 'id'}})
                    or proposal['budget_pence'] != brief['budget_pence'] or proposal['segments'] != brief['segments']
                    or proposal['copy_mode'] != ('fixture' if fixture else 'model')):
                raise Conflict('Original campaign proposal differs')
            else:
                result['parents'].append(record_id(self.store, 'run', 'local-conversations', parent['id']))
                self.owner(result, 'local-conversations', conversation, revision)
                self.evidence(result, 'conversation_plans', plan['request_id'], plan, 'local-conversations')
        elif brief.get('followup_id'):
            row = self.one('review_commands', org, 'AND request_id=?', (brief['followup_id'],))
            proposal = json.loads(row['receipt']) if row else None
            if (proposal is None or proposal.get('kind') != 'followup_proposal'
                    or proposal['id'] != 'followup_'+digest({k: v for k, v in proposal.items() if k != 'id'})):
                result['missing'].append('original_followup_proposal_requires_review')
            else:
                parent = self.one('runs', org, 'AND request_id=?', (proposal['parent_id'],))
                if parent:
                    result['parents'].append(record_id(self.store, 'run', org, parent['id']))
                else:
                    result['missing'].append('original_parent_is_unavailable')
                self.evidence(result, 'review_commands', row['request_id'], row)
        elif brief.get('campaign_id'):
            parent = descendant_parent(self.db, org, brief['campaign_id']) if 'execution_commands' in self.tables else None
            if parent is None:
                parent = campaign_parent(self.db, org, brief['campaign_id'], run['id'])
            if parent:
                result['parents'].append(record_id(self.store, 'run', org, parent))
                commands = self.rows('execution_commands', org)
                self.evidence(result, 'execution_commands', 'recorded_parent_relation', commands)

    def run(self, run):
        org, key = run['organization'], run['id']
        result = record(self.store, 'run', org, key)
        result['state'] = run['status']
        result['native_request_id'] = run['request_id']
        tasks = [dict(r) for r in self.db.execute('SELECT * FROM tasks WHERE run_id=? ORDER BY position', (key,))]
        result['preserve']['task_plan_fingerprint'] = run['request_hash']
        self.evidence(result, 'runs', key, run); self.evidence(result, 'tasks', key, tasks)
        try:
            if not tasks or digest(self.specs(tasks)) != run['request_hash'] or [t['position'] for t in tasks] != list(range(len(tasks))):
                raise Conflict('Original task plan differs')
            admitted = self.one('execution_admissions', org, 'AND run_id=?', (key,))
            if admitted:
                result['format'] = 'verified'
                intent = binding(self.db, org, key)
                owner = intent.ownership
                result['owners'].append([owner.organization, owner.kind, owner.scope_id, owner.revision])
                result['permission_recorded'] = True
                result['preserve']['consent_fingerprint'] = intent.consent_id
                if intent.parent_run_id:
                    result['parents'].append(record_id(self.store, 'run', org, intent.parent_run_id))
                self.evidence(result, 'execution_admissions', admitted['id'], admitted)
            elif any('execution_admission_id' in json.loads(t['inputs']) for t in tasks):
                raise Conflict('New-format admission is missing')
            else:
                self.native(result, run, tasks)
        except (Conflict, ValueError, TypeError, KeyError):
            result['conflicts'].append('stored_admission_or_source_integrity_failed')
        link = self.one('execution_runs', org, 'AND run_id=?', (key,))
        if link:
            if type(link['owner_organization']) is str and type(link['conversation_id']) is str and type(link['revision']) is int:
                result['index_owner'] = [link['owner_organization'], 'conversation', link['conversation_id'], link['revision']]
            else:
                result['conflicts'].append('recorded_account_scope_is_invalid')
            self.evidence(result, 'execution_runs', key, link)
        if run['status'] == 'running' or any(t['status'] == 'running' for t in tasks):
            result['uncertain'].append('work_was_in_flight_at_snapshot')
        calls = self.rows('model_calls', org, 'AND run_id=? ORDER BY rowid', (key,))
        result['preserve']['recorded_calls'] = len(calls) if 'model_calls' in self.tables else None
        result['preserve']['remaining_allowance'] = None
        result['preserve']['billing_verified'] = False
        result['preserve']['provider_observations'] = []
        for call in calls:
            self.evidence(result, 'model_calls', call['call_key'], call)
            result['preserve']['provider_observations'].append({
                'call_key': call['call_key'], 'state': call['status'] if call['status'] in {'recorded','rejected','reserved','unknown'} else 'unsupported',
                'definitive_rejection': call['error'] in DEFINITIVE_REJECTIONS})
            if call['status'] == 'reserved' or (call['status'] == 'unknown' and call['error'] not in DEFINITIVE_REJECTIONS):
                result['uncertain'].append('provider_outcome_requires_reconciliation')
            elif call['status'] not in {'recorded','rejected','unknown'}:
                result['conflicts'].append('provider_observation_state_is_unsupported')
        historical = self.one('execution_commands', org, 'AND request_id=?', ('independent:'+key,))
        if historical:
            self.evidence(result, 'execution_commands', 'independent:'+key, historical)
            result['preserve']['historical_independence_receipt'] = True
            if result['owners'] or result['parents']:
                result['conflicts'].append('historical_independence_disagrees_with_positive_parentage')
            else:
                result['missing'].append('historical_independence_is_not_a_migration_grant')
        if 'legacy_task_admissions' in self.tables:
            cutoff = self.db.execute('SELECT * FROM legacy_task_admissions WHERE organization=? AND run_id=?', (org,key)).fetchone()
            if cutoff:
                self.evidence(result, 'legacy_task_admissions', key, dict(cutoff))
                result['preserve']['legacy_cutoff_fingerprint'] = values_hash(dict(cutoff))
        if 'model_calls' not in self.tables and any('.v2' in t['capability'] or '.v3' in t['capability'] for t in tasks):
            result['missing'].append('inference_journal_is_unavailable')
        return result
