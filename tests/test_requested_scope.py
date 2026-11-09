"""Requested scope is evidence from the user, never a planner-selected substitute."""
import copy
from dataclasses import asdict, replace
import json
import unittest

from acquisition.campaigns import CampaignScope, brief_from, build_draft, requested_scope_values
from acquisition.contracts import Conflict, canonical, digest
from acquisition.conversations import requested_scope, validate_result, scope_response
from acquisition.reviews import creatives_from
from test_conversations import proposal
import test_conversation_handoff as handoff_tests


def messages(*contents):
    return [{'id': 'm' + str(i), 'revision': i + 1, 'role': 'user', 'content': content, 'created_at': 1000.}
            for i, content in enumerate(contents)]


class RequestedScopeDomainTests(unittest.TestCase):
    def resolve(self, *contents):
        return requested_scope('one', 'conversation_scope', len(contents), messages(*contents))

    def test_defaults_are_distinct_from_literal_request_provenance(self):
        scope = self.resolve('Help us prepare a £437 UK postal response experiment for contractors.')
        self.assertEqual(scope['status'], 'supported')
        self.assertEqual(requested_scope_values(scope), asdict(CampaignScope()))
        self.assertEqual(scope['requirements']['product']['basis'], 'capability_default')
        self.assertEqual(scope['requirements']['country']['basis'], 'explicit_request')
        self.assertEqual(scope['authority'], 'none')
        self.assertEqual(scope['id'], 'request_scope_' + digest({k:v for k,v in scope.items() if k != 'id'}))
        text = messages('Help us prepare a £437 UK postal response experiment for contractors.')[0]['content']
        for facet in scope['requirements'].values():
            for evidence in facet['evidence']:
                self.assertEqual(text[evidence['start']:evidence['end']], evidence['quote'])

    def test_unsupported_conflicting_unknown_and_excluded_scopes_cannot_become_supported(self):
        for content, status in [
            ('Email only. Do not substitute postal mail.', 'unsupported'),
            ('Target France. Do not replace France with the UK.', 'unsupported'),
            ('Promote a personal residential mortgage. Do not substitute a business loan.', 'unsupported'),
            ('Approve credit applications and guarantee a loan.', 'unsupported'),
            ('Maximize incremental revenue.', 'unsupported'),
            ('Use email or postal mail.', 'needs_clarification'),
            ('Channel: carrier pigeon', 'needs_clarification'),
            ('Country: Atlantis', 'needs_clarification'),
            ('No UK audience.', 'needs_clarification'),
            ('Use the UK. No UK audience.', 'needs_clarification'),
        ]:
            with self.subTest(content=content):
                self.assertEqual(self.resolve(content)['status'], status)
        self.assertEqual(self.resolve('Never use email. Use UK postal direct mail.')['status'], 'supported')
        self.assertEqual(self.resolve('Do not replace postal with email.')['status'], 'supported')
        self.assertEqual(self.resolve('Target Northern Ireland with postal mail.')['status'], 'supported')

    def test_later_explicit_correction_changes_only_its_facet_and_preserves_old_snapshot(self):
        original = self.resolve('Use email for France.')
        saved = canonical(original)
        corrected = self.resolve('Use email for France.', 'Use postal instead.')
        self.assertEqual(corrected['requirements']['channel']['value'], 'direct_mail')
        self.assertEqual(corrected['requirements']['country']['value'], 'France')
        self.assertEqual(corrected['status'], 'unsupported')
        final = self.resolve('Use email for France.', 'Use postal instead.', 'Use the UK instead.')
        self.assertEqual(final['status'], 'supported')
        self.assertEqual(canonical(original), saved)
        self.assertNotEqual(original['id'], final['id'])

    def test_planner_cannot_override_or_rehash_the_source_scope(self):
        source = messages('Prepare a £437 contractor email campaign.')
        frozen = {'conversation_id': 'conversation_scope', 'request_id': 'plan', 'revision': 1,
                  'knowledge_id': 'knowledge_test', 'messages': source,
                  'requested_scope': requested_scope('one', 'conversation_scope', 1, source)}
        with self.assertRaises(ValueError):
            validate_result(proposal(budget_pence=43700), frozen, 'one')
        result = validate_result(scope_response(frozen['requested_scope']), frozen, 'one')
        self.assertEqual(result['outcome'], 'unsupported')
        self.assertEqual(result['requested_scope'], frozen['requested_scope'])
        changed = copy.deepcopy(frozen)
        changed['requested_scope']['requirements']['channel']['value'] = 'direct_mail'
        changed['requested_scope']['status'] = 'supported'
        changed['requested_scope']['id'] = 'request_scope_' + digest({k:v for k,v in changed['requested_scope'].items() if k != 'id'})
        with self.assertRaises(ValueError):
            validate_result(proposal(budget_pence=43700), changed, 'one')

    def test_historical_planning_results_keep_their_exact_unscoped_format(self):
        from acquisition.conversations.domain import validate_result as original_validator
        frozen = {'conversation_id': 'conversation_legacy', 'request_id': 'plan', 'revision': 1,
                  'knowledge_id': 'knowledge_legacy', 'messages': messages('Prepare a £437 contractor campaign.')}
        candidate = proposal(budget_pence=43700)
        self.assertEqual(validate_result(candidate, frozen, 'one'), original_validator(candidate, frozen, 'one'))
        self.assertNotIn('requested_scope', validate_result(candidate, frozen, 'one'))


class RequestedScopeStorageTests(unittest.TestCase):
    setUp = handoff_tests.ConversationHandoffTests.setUp
    approve = handoff_tests.ConversationHandoffTests.approve

    def app(self):
        session = self.w._session(self.sid)
        return self.w._app(session), session['organization']

    def test_draft_commit_rejects_scope_removal_substitution_and_delivered_scope_changes(self):
        app, owner = self.app()
        original = app.drafts.get(owner, self.state['review']['subject']['draft_id'])
        scope = original.manifest['brief']['requested_scope']
        self.assertEqual(original.manifest['campaign_scope'], asdict(CampaignScope()))
        plain = {k:v for k,v in original.manifest['brief'].items() if k != 'requested_scope'}
        snapshot = app.audiences.get(owner, original.manifest['snapshot_id'])
        legacy = build_draft(snapshot, brief_from(plain), creatives_from(original))
        variants = [legacy]
        for facet, value in [('product', 'personal_mortgage'), ('channel', 'email'), ('country', 'France'), ('objective', 'credit_decision')]:
            variants.append(replace(original, manifest=original.manifest | {'campaign_scope': original.manifest['campaign_scope'] | {facet: value}}))
        variants.append(replace(original, manifest={k:v for k,v in original.manifest.items() if k != 'campaign_scope'}))
        substituted = copy.deepcopy(scope)
        substituted['conversation_id'] = 'conversation_other'
        substituted['id'] = 'request_scope_' + digest({k:v for k,v in substituted.items() if k != 'id'})
        variants.append(replace(original, manifest=original.manifest | {'brief': original.manifest['brief'] | {'requested_scope': substituted}}))
        with app.tasks.database.connect() as db:
            before = db.execute('SELECT count(*) FROM drafts').fetchone()[0]
        for i, draft in enumerate(variants):
            with self.subTest(variant=i), self.assertRaises((Conflict, ValueError)):
                app.drafts.put(owner, 'scope-substitution-' + str(i), draft)
        with app.tasks.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM drafts').fetchone()[0], before)
        self.assertEqual(app.drafts.get(owner, original.id), original)

    def test_cached_validation_and_approval_cannot_authorize_changed_source_messages(self):
        report = copy.deepcopy(self.state['review']['validation_report'])
        approval = self.approve()
        app, owner = self.app()
        with app.tasks.database.transaction() as db:
            db.execute('UPDATE conversation_messages SET content=? WHERE organization=? AND conversation_id=?',
                       ('Prepare a £600 email campaign in France.', 'local-conversations', self.c))
        current = self.w.view(self.sid)['review']
        self.assertFalse(current['validation_report']['review_ready'])
        self.assertTrue(report['review_ready'])
        with self.assertRaises(Conflict):
            app.reviews.store.handoff(owner, self.state['review']['case_id'], approval, 'local-operator', 'changed-scope')
        with app.tasks.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM simulated_agency_jobs').fetchone()[0], 0)

    def test_source_mutation_during_review_and_acceptance_writes_rolls_back_every_effect(self):
        app, owner = self.app()
        case = self.state['review']['case_id']
        for event in ('review_approve', 'simulated_handoff_accepted'):
            with self.subTest(event=event):
                approval = self.approve() if event == 'simulated_handoff_accepted' else None
                with app.tasks.database.connect() as db:
                    before = {table: db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                              for table in ('review_decisions', 'review_commands', 'review_events', 'simulated_agency_jobs')}
                    message = db.execute('SELECT content FROM conversation_messages WHERE organization=? AND conversation_id=?', ('local-conversations', self.c)).fetchone()[0]
                    db.execute("CREATE TRIGGER change_requested_scope AFTER INSERT ON review_events WHEN NEW.kind='" + event + "' BEGIN "
                               "UPDATE conversation_messages SET content='Use email in France.' WHERE organization='local-conversations' AND conversation_id='" + self.c + "'; END")
                try:
                    with self.assertRaises(Conflict):
                        if approval:
                            app.reviews.store.handoff(owner, case, approval, 'local-operator', 'atomic-scope-handoff')
                        else:
                            app.reviews.store.decide(owner, case, self.subject, 'local-reviewer', 'approve', 'atomic-scope-review', 'Exact scope reviewed', 86400)
                    with app.tasks.database.connect() as db:
                        if approval:
                            prepared = app.reviews.store.delivery(owner, case, approval)
                            self.assertEqual(prepared['status'], 'prepared')
                            command = db.execute('SELECT receipt FROM review_commands WHERE organization=? AND request_id=?',
                                                 (owner, 'atomic-scope-handoff')).fetchone()
                            self.assertEqual(json.loads(command[0]), {'kind': 'simulated_delivery_pending', 'dispatch_id': prepared['id']})
                            before['review_commands'] += 1
                        for table, count in before.items():
                            self.assertEqual(db.execute('SELECT count(*) FROM ' + table).fetchone()[0], count)
                        self.assertEqual(db.execute('SELECT content FROM conversation_messages WHERE organization=? AND conversation_id=?', ('local-conversations', self.c)).fetchone()[0], message)
                finally:
                    with app.tasks.database.connect() as db:
                        db.execute('DROP TRIGGER change_requested_scope')


    def test_scope_change_during_draft_write_rolls_back_publication(self):
        app, owner = self.app()
        source = app.drafts.get(owner, self.state['review']['subject']['draft_id'])
        snapshot = app.audiences.get(owner, source.manifest['snapshot_id'])
        candidate = build_draft(snapshot, brief_from(source.manifest['brief'] | {'campaign_id': 'scope-new-draft'}), creatives_from(source))
        with app.tasks.database.connect() as db:
            before = db.execute('SELECT count(*) FROM drafts').fetchone()[0]
            db.execute("CREATE TRIGGER change_draft_scope AFTER INSERT ON draft_operations BEGIN "
                       "UPDATE conversation_messages SET content='Use email in France.' WHERE organization='local-conversations' AND conversation_id='" + self.c + "'; END")
        with self.assertRaises(Conflict):
            app.drafts.put(owner, 'atomic-scope-draft', candidate)
        with app.tasks.database.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM drafts').fetchone()[0], before)
            self.assertIsNone(db.execute("SELECT 1 FROM draft_operations WHERE operation_id='atomic-scope-draft'").fetchone())

    def test_followup_cannot_drop_scope_or_reuse_it_after_a_changed_request(self):
        approval = self.approve()
        self.w.action(self.sid, 'handoff', {'request_id': 'scope-handoff', 'approval_id': approval})
        self.w.action(self.sid, 'open-learning', {'request_id': 'scope-open'})
        state = self.w.action(self.sid, 'finalize', {'request_id': 'scope-final'})
        cohort = state['learning']['cohort']['id']
        p = self.w.propose_followup(self.sid, 'scope-followup', cohort)
        app, owner = self.app()
        self.assertEqual(p['brief']['requested_scope'], self.state['review']['manifest']['brief']['requested_scope'])
        changed = copy.deepcopy(p)
        changed['brief'].pop('requested_scope')
        with self.assertRaises(Conflict):
            app.followups.put(owner, 'scope-stripped-followup', changed)
        self.w.message_conversation(self.c, 'scope-amendment', 1, 'Use email in France with £600.')
        self.assertEqual(self.w.propose_followup(self.sid, 'scope-followup', cohort), p)
        with self.assertRaises(Conflict):
            self.w.propose_followup(self.sid, 'scope-after-amendment', cohort)


    def test_historical_bytes_stay_unscoped_but_cannot_authorize_an_unsupported_request(self):
        from acquisition.adapters.sqlite.conversation_provenance import require_requested_scope
        from acquisition.conversations.domain import validate_result as legacy_result
        app, owner = self.app()
        brief = copy.deepcopy(self.state['review']['manifest']['brief'])
        brief.pop('requested_scope')
        with app.tasks.database.transaction() as db:
            row = db.execute('SELECT request_id,payload FROM conversation_plans WHERE organization=? AND conversation_id=?', ('local-conversations', self.c)).fetchone()
            frozen = json.loads(row['payload'])
            frozen.pop('requested_scope')
            candidate = proposal(budget_pence=60000)
            result = legacy_result(candidate, frozen, 'local-conversations')
            brief['plan_id'] = result['id']
            db.execute('UPDATE conversation_plans SET payload=? WHERE organization=? AND conversation_id=?', (canonical(frozen), 'local-conversations', self.c))
            db.execute('UPDATE tasks SET inputs=?,output=? WHERE run_id=(SELECT id FROM runs WHERE organization=? AND request_id=?) AND position=0',
                       (canonical(frozen), canonical(result), 'local-conversations', frozen['run_request_id']))
            require_requested_scope(db, brief)
            db.execute('UPDATE conversation_messages SET content=? WHERE organization=? AND conversation_id=?',
                       ('Use email in France with £600.', 'local-conversations', self.c))
            with self.assertRaises(Conflict):
                require_requested_scope(db, brief)
            self.assertNotIn('requested_scope', json.loads(db.execute('SELECT payload FROM conversation_plans WHERE organization=? AND conversation_id=?', ('local-conversations', self.c)).fetchone()[0]))
