"""Profile isolation, frozen evidence, atomic preparation and historical compatibility."""

import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import date, datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from acquisition.audiences import Business, Snapshot
from acquisition.bootstrap import build_profile_preparation
from acquisition.campaigns import Brief, brief_from, build_draft
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.creative import (GroundedCopyAgent, fixture_catalog, product_profile_from,
                                  validate_fact_pack, validate_grounded_catalogue)
from acquisition.reviews import creatives_from
from acquisition.reviews.domain import validate_population
from acquisition.adapters.sqlite.audiences import SqliteAudiences
from acquisition.adapters.sqlite.creative import SqliteCreative
from acquisition.adapters.sqlite.database import Database
from acquisition.adapters.sqlite.drafts import SqliteDrafts
from acquisition.adapters.synthetic import generate


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 13, tzinfo=timezone.utc).timestamp()


class ProfilePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'profiles.sqlite'

    def service(self, key='fielddesk', organization='one', clock=lambda: NOW):
        return build_profile_preparation(self.path, organization, key, clock)

    def prepare(self, service=None, key='fielddesk', request='request', **overrides):
        service = service or self.service(key)
        segments = ('maintenance', 'installations') if key == 'fielddesk' else ('inventory', 'contractors')
        inputs = dict(objective='Compare response to hypothetical business planning questions.', budget_pence=60000,
                      segments=segments, country='UK', currency='GBP', channel='direct_mail', size=100)
        return service.prepare('one', request, key, 'v1', **(inputs | overrides))

    def counts(self):
        with Database(self.path).connect() as db:
            return {t: db.execute('SELECT count(*) FROM ' + t).fetchone()[0] for t in (
                'audiences', 'creative_contexts', 'generated_catalogues', 'drafts', 'draft_operations',
                'runs', 'tasks', 'model_calls', 'review_decisions', 'simulated_agency_jobs')}

    def test_two_company_profiles_use_the_same_services_with_distinct_grounded_product_text(self):
        identities = []
        for key, expected_segments, expected_brand in (
                ('iwoca', {'inventory', 'contractors'}, 'iwoca'),
                ('fielddesk', {'maintenance', 'installations'}, 'Fielddesk Demo')):
            service = self.service(key)
            result = self.prepare(service, key, key)
            draft = service.proposals.get('one', result['draft_id'])
            identities.append(draft.id)
            self.assertEqual(draft.manifest['schema'], 'profile-draft/v1')
            self.assertEqual(draft.manifest['counts'], {'input': 100, 'excluded': 24,
                'eligible_unselected': 0, 'holdout': 6, 'mailed': 70})
            self.assertEqual(draft.manifest['variable_cost_pence'], 5950)
            self.assertEqual({c['segment'] for c in draft.manifest['creatives']}, expected_segments)
            self.assertTrue(all(expected_brand in c['opening'] for c in draft.manifest['creatives']))
            self.assertEqual(result['approval'], 'not_granted')
            self.assertEqual(result['execution'], 'not_performed')
            self.assertEqual(result['semantic_screen'], 'not_evaluated')
            self.assertTrue(all(c['claim_check'] == 'not_evaluated' for c in draft.manifest['creatives']))
            if key == 'fielddesk':
                self.assertNotIn('iwoca', canonical(draft.manifest).casefold())
                self.assertTrue(all('fictional' in c['opening'] for c in draft.manifest['creatives']))
        self.assertEqual(len(set(identities)), 2)
        counts = self.counts()
        self.assertEqual(counts['drafts'], 2)
        for table in ('runs', 'tasks', 'model_calls', 'review_decisions', 'simulated_agency_jobs'):
            self.assertEqual(counts[table], 0)

    def test_fresh_process_replays_exact_artifacts_without_new_inputs_or_effects(self):
        service = self.service()
        first = self.prepare(service)
        before = self.counts()
        # Use the public CLI in a fresh interpreter, with the original exact request.
        process = subprocess.run([sys.executable, '-m', 'acquisition.profile_cli', '--db', str(self.path),
            '--organization', 'one', '--profile', 'fielddesk', '--version', 'v1', '--request-id', 'request',
            '--objective', 'Compare response to hypothetical business planning questions.', '--budget-pence', '60000',
            '--segments', 'maintenance', 'installations', '--country', 'UK', '--currency', 'GBP',
            '--channel', 'direct_mail', '--size', '100'], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        replay = json.loads(process.stdout)
        self.assertEqual(replay.pop('observation'), 'historical_proposal')
        self.assertEqual(replay, {k:v for k,v in first.items() if k != 'observation'})
        self.assertEqual(self.counts(), before)
        draft = service.proposals.get('one', first['draft_id'])
        reopened = self.service().proposals.get('one', first['draft_id'])
        self.assertEqual(reopened, draft)

    def test_expired_profile_replay_observes_history_without_renewing_or_rewriting_it(self):
        service = self.service()
        first = self.prepare(service)
        before = self.counts()
        later = datetime(2026, 12, 1, tzinfo=timezone.utc).timestamp()
        replay = self.prepare(self.service(clock=lambda: later))
        self.assertEqual(replay['draft_id'], first['draft_id'])
        self.assertEqual(replay['observation'], 'historical_proposal')
        self.assertEqual(replay['approval'], 'not_granted')
        self.assertEqual(self.counts(), before)
        with self.assertRaises(ValueError):
            self.prepare(self.service(clock=lambda: later), request='new-after-expiry')
        self.assertEqual(self.counts(), before)

    def test_reused_key_with_changed_exact_inputs_is_atomic(self):
        service = self.service()
        first = self.prepare(service)
        before = self.counts()
        for change in ({'budget_pence': 50000}, {'seed': 43}, {'segments': ('maintenance',)},
                       {'objective': 'A different experiment objective.'}):
            with self.subTest(change=change), self.assertRaises(Conflict):
                self.prepare(service, **change)
            self.assertEqual(self.counts(), before)
        self.assertEqual(service.proposals.get('one', first['draft_id']).id, first['draft_id'])

    def test_unknown_profile_version_market_currency_and_channel_do_not_substitute(self):
        service = self.service()
        before = self.counts()
        for change in ({'country': 'France'}, {'currency': 'USD'}, {'channel': 'email'},
                       {'segments': ('inventory',)}, {'budget_pence': True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.prepare(service, **change)
        with self.assertRaises(NotFound):
            self.service('unknown')
        with self.assertRaises(NotFound):
            service.prepare('one', 'request', 'fielddesk', 'v2', objective='Test', budget_pence=100,
                segments=('maintenance',), country='UK', currency='GBP', channel='direct_mail')
        self.assertEqual(self.counts(), before)

    def test_organization_and_product_substitutions_cannot_publish(self):
        service = self.service('iwoca')
        result = self.prepare(service, 'iwoca')
        draft = service.proposals.get('one', result['draft_id'])
        snapshot = SqliteAudiences(Database(self.path)).get('one', draft.manifest['snapshot_id'])
        brief = brief_from(draft.manifest['brief'])
        substituted = replace(brief.profile, company='different-company', product_key='fielddesk_visit_planner')
        plan = copy.deepcopy(brief.plan)
        plan.update(profile=json.loads(canonical(asdict(substituted))), profile_id=substituted.id,
                    request_id='substitution')
        plan['id'] = 'profile_plan_' + digest({k:v for k,v in plan.items() if k != 'id'})
        bundles = tuple(service.copy.prepare('one', brief.profile.product_profile_id, segment, plan['id'],
                                             date(2026, 11, 13)) for segment in brief.segments)
        changed = build_draft(snapshot, replace(brief, campaign_id='profile-campaign-' + plan['id'][13:],
            profile=substituted, plan=plan), tuple(c for _, pair in bundles for c in pair))
        before = self.counts()
        with self.assertRaisesRegex(Conflict, 'installed reviewed profile'):
            service.proposals.publish('one', 'substitution', snapshot, bundles, changed)
        with self.assertRaises(NotFound):
            service.proposals.get('two', draft.id)
        with self.assertRaises(NotFound):
            service.profiles.campaign_profile('two', 'iwoca', 'v1')
        self.assertEqual(self.counts(), before)

    def test_expiry_is_rechecked_at_publication_and_rolls_back_all_inputs(self):
        service = self.service()
        before = self.counts()
        service.proposals.clock = lambda: datetime(2026, 11, 25, tzinfo=timezone.utc).timestamp()
        with self.assertRaises(ValueError):
            self.prepare(service)
        self.assertEqual(self.counts(), before)

    def test_source_change_after_write_rolls_back_proposal_catalogue_and_snapshot(self):
        service = self.service()
        database = Database(self.path)
        with database.transaction() as db:
            db.execute("""CREATE TRIGGER alter_profile_source AFTER INSERT ON drafts
                WHEN json_extract(NEW.manifest,'$.schema')='profile-draft/v1' BEGIN
                UPDATE audiences SET payload=json_set(payload,'$.records[0].segment','installations')
                WHERE organization=NEW.organization; END""")
        before = self.counts()
        with self.assertRaises(Conflict):
            self.prepare(service)
        self.assertEqual(self.counts(), before)

    def test_newly_sealed_store_blocks_an_existing_service_before_any_input_write(self):
        service = self.service()
        Database(self.path, verified_admissions=True, clock=lambda: NOW)
        before = self.counts()
        with self.assertRaises(Conflict):
            self.prepare(service)
        self.assertEqual(self.counts(), before)
        with self.assertRaises(Conflict):
            self.service()

    def test_concurrent_changed_requests_publish_one_complete_original_bundle(self):
        services = [self.service(), self.service()]
        def attempt(index):
            try:
                return self.prepare(services[index], budget_pence=60000 - index * 10000)
            except Conflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, range(2)))
        self.assertEqual(sum(r is not None for r in results), 1)
        counts = self.counts()
        self.assertEqual({t:counts[t] for t in ('audiences', 'drafts', 'draft_operations')},
                         {'audiences': 1, 'drafts': 1, 'draft_operations': 1})
        self.assertEqual(counts['creative_contexts'], 2)
        self.assertEqual(counts['generated_catalogues'], 2)

    def test_inspection_marker_blocks_profile_entry_and_preserves_existing_history(self):
        service = self.service()
        result = self.prepare(service)
        before = self.counts()
        (self.path.parent / '.acquisition-checkpoint.json').write_text('{}')
        with self.assertRaises(Conflict):
            self.service()
        self.assertEqual(service.proposals.get('one', result['draft_id']).id, result['draft_id'])
        with self.assertRaises(Conflict):
            self.prepare(service, request='after-checkpoint')
        self.assertEqual(self.counts(), before)

    def test_catalogue_tampering_after_publication_rolls_back_every_proposal_input(self):
        service = self.service()
        with Database(self.path).transaction() as db:
            db.execute("""CREATE TRIGGER alter_profile_catalogue AFTER INSERT ON drafts
                WHEN json_extract(NEW.manifest,'$.schema')='profile-draft/v1' BEGIN
                UPDATE generated_catalogues SET payload='[]' WHERE organization=NEW.organization; END""")
        before = self.counts()
        with self.assertRaises(Conflict):
            self.prepare(service)
        self.assertEqual(self.counts(), before)

    def test_profile_inputs_cannot_downgrade_to_legacy_campaign_review_or_model_execution(self):
        service = self.service()
        result = self.prepare(service)
        draft = service.proposals.get('one', result['draft_id'])
        database = Database(self.path)
        snapshot = SqliteAudiences(database).get('one', draft.manifest['snapshot_id'])
        with self.assertRaises(ValueError):
            build_draft(snapshot, Brief('downgrade'), fixture_catalog())
        with self.assertRaises(Conflict):
            SqliteDrafts(database).put('one', 'downgrade', draft)
        with self.assertRaises(Conflict):
            validate_population(draft, snapshot, set())
        context_id = draft.manifest['creatives'][0]['context_id']
        memory = SqliteCreative(database)
        context = memory.get_context('one', context_id)
        with self.assertRaises(ValueError):
            GroundedCopyAgent.request(context)
        # Missing only one version edge is not a valid legacy representation.
        for mutation in ({'schema': 'creative-context/v3'}, {'product_profile_id': 'product_profile_' + '0' * 64}):
            changed = context | mutation
            pair = tuple(c for c in creatives_from(draft) if c.segment == context['segment'])
            with self.assertRaises(ValueError):
                validate_grounded_catalogue(pair, changed, date(2026, 11, 13))
        with self.assertRaises(ValueError):
            Snapshot('one', snapshot.as_of, snapshot.records, 42)

    def test_wrong_product_url_fact_or_qualification_cannot_reuse_reviewed_evidence(self):
        service = self.service()
        profile = service.profiles.product
        material = service.profiles.product_material('one', profile.id)
        validate_fact_pack(material['pack'], date(2026, 11, 24), profile=profile)
        for mutate in (lambda p:p['sources'][0].update(url='https://attacker.invalid/product'),
                       lambda p:p['facts'][0].update(copy='An invented product feature.'),
                       lambda p:p.update(required_qualification='Changed qualification.'),
                       lambda p:p.update(cta='Explore another product.')):
            changed = copy.deepcopy(material['pack']); mutate(changed)
            with self.assertRaises(ValueError):
                validate_fact_pack(changed, date(2026, 11, 13), profile=profile)
        with self.assertRaises(ValueError):
            validate_fact_pack(material['pack'], date(2026, 11, 25), profile=profile)
        with self.assertRaises(ValueError):
            validate_fact_pack(material['pack'], date(2026, 10, 24), profile=profile)

    def test_removing_both_profile_edges_does_not_authorize_fixture_as_legacy_grounding(self):
        for key, segment in (('fielddesk', 'maintenance'), ('iwoca', 'inventory')):
            service = self.service(key)
            result = self.prepare(service, key=key, request=key)
            draft = service.proposals.get('one', result['draft_id'])
            pair = tuple(c for c in creatives_from(draft) if c.segment == segment)
            context = SqliteCreative(Database(self.path)).get_context('one', pair[0].context_id)
            stripped = {k:v for k,v in context.items() if k not in ('product_profile', 'product_profile_id')}
            stripped['schema'] = 'creative-context/v3'
            with self.subTest(profile=key), self.assertRaises(ValueError):
                validate_grounded_catalogue(pair, stripped, date(2026, 11, 13))

    def test_reviewed_profile_markers_cannot_disable_market_or_source_rules(self):
        data = json.loads((ROOT / 'config/profiles/fielddesk-v1.json').read_text())
        for value in ('file:///tmp/product', 'https://fielddesk.example.invalid/product?redirect=x',
                      'https://fielddesk.example.invalid.evil.test/product'):
            changed = data['product_profile'] | {'official_urls': [value]}
            with self.assertRaises(ValueError):
                product_profile_from(changed)
        profile = self.service().profiles.profile
        for change in ({'currency': 'USD'}, {'country': 'France'}, {'channel': 'email'},
                       {'objective': 'credit_decision'}):
            with self.assertRaises(ValueError):
                replace(profile, **change)


class HistoricalProfileCompatibilityTests(unittest.TestCase):
    def test_legacy_record_and_string_subclasses_keep_the_same_serialized_identity(self):
        class HistoricalBusiness(Business):
            pass
        class HistoricalSegment(str):
            pass
        original = generate('historical-profile-test', 100, 42, '2026-10-25')
        row = HistoricalBusiness(**(asdict(original.records[0]) | {'segment': HistoricalSegment('inventory')}))
        snapshot = replace(original, records=(row, *original.records[1:]))
        self.assertEqual(snapshot.id, original.id)
        self.assertEqual(build_draft(snapshot, Brief('historical-profile-test'), fixture_catalog()).id,
                         'draft_9300f9d4db0dbd99995f8538573602d114d086983b497f64e0b8bdbb0538aafe')

    def test_legacy_product_url_validation_keeps_its_original_parser_semantics(self):
        pack = json.loads((ROOT / 'config/iwoca-product-facts-v1.json').read_text())
        for suffix in ('', '?', '#'):
            changed = copy.deepcopy(pack)
            changed['sources'][0]['url'] += suffix
            validate_fact_pack(changed, date(2026, 11, 13))

    def test_original_v1_snapshot_draft_and_csv_identities_match_prechange_baseline(self):
        # Captured independently from unchanged main before this implementation.
        snapshot = generate('historical-profile-test', 100, 42, '2026-10-25')
        draft = build_draft(snapshot, Brief('historical-profile-test'), fixture_catalog())
        self.assertEqual(snapshot.id, 'aud_20125e6d1a7e15886c22edfd4c8d0cb88ab03b5877b4df83cb3ef230be1cec03')
        self.assertEqual(draft.id, 'draft_9300f9d4db0dbd99995f8538573602d114d086983b497f64e0b8bdbb0538aafe')
        self.assertEqual(draft.manifest['mailing_sha256'], 'a78f9d08b905ffc0f3e032575f624bf3e3f544f9df0dba27094d82fecbb38dd8')
        self.assertEqual(draft.manifest['assignments_sha256'], 'f89842b77c2374c47ac2737c305168a8fe21c8b5d08901b61c521eb0e4b37491')
        self.assertNotIn('profile', draft.manifest['brief'])
        self.assertNotIn('taxonomy', asdict(snapshot))


if __name__ == '__main__':
    unittest.main()
