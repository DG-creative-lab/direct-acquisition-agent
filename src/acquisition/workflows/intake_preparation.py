"""Compose reviewed intake with the existing offline profile draft builder."""

from dataclasses import asdict
from datetime import datetime, timezone
import json

from acquisition.audiences import AudienceSegment, AudienceTaxonomy, ProfileFixtureAudience
from acquisition.campaigns import (CampaignProfile, ProfiledBrief, GroundedPreparationRequest,
    GroundedPreparationStore, build_draft, intake_identity)
from acquisition.conversations import profile_plan
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.creative import grounded_intake_product, ProfileCopyService


class IntakePreparationBuilder:
    """Pure except for the injected synthetic recipe; no model or runtime access."""
    def __init__(self, audiences: ProfileFixtureAudience):
        self.audiences = audiences

    def build(self, organization, actor, request_id, request, preview, now):
        if preview['blockers'] or request.preview_id != preview['id']:
            raise Conflict('Reload preparation eligibility and resolve its blockers before confirming')
        today = datetime.fromtimestamp(now, timezone.utc).date()
        context = preview['context']
        taxonomy = AudienceTaxonomy('intake-fixture', 'v1', (AudienceSegment('businesses',
            'Synthetic businesses', 'Fixed fictional business population, not matched to the requested audience.'),))
        product, pack = grounded_intake_product(context, request.evidence, taxonomy, today)
        profile = CampaignProfile(product.key, 'v1', product.brand_key, product.key, product.id, taxonomy)
        settings, requirements = preview['settings'], preview['requirements']
        snapshot = self.audiences.snapshot(organization, taxonomy, settings['size'], settings['seed'], today.isoformat())
        command = {'schema': 'profile-preparation/v1', 'organization': organization, 'key': profile.key,
            'version': profile.version, 'objective': requirements['objective'], 'budget_pence': requirements['budget_minor'],
            'segments': ['businesses'], 'country': 'UK', 'currency': 'GBP', 'channel': 'direct_mail',
            'size': settings['size'], 'seed': settings['seed'], 'as_of': today.isoformat()}
        plan = profile_plan(organization, request_id, profile, objective=command['objective'],
            budget_pence=command['budget_pence'], segments=('businesses',), country='UK', currency='GBP',
            channel='direct_mail', snapshot_id=snapshot.id, command=command)
        plan.pop('id')
        plan['intake_grounding'] = {'schema': 'intake-grounding/v1', 'actor': actor, 'request': json.loads(canonical(asdict(request))),
            'prepared_at': now, 'context_request_id': context['request_id'], 'context_fingerprint': context['fingerprint'],
            'store_id': context['store_id'], 'requirements': requirements,
            'review_expires_at': min(context['review_expires_at'], now + request.evidence.review_days * 86400),
            'settings': settings, 'verification': 'operator_attested_sources_not_independently_verified',
            'authority': 'none', 'approval': 'not_granted'}
        plan['id'] = 'profile_plan_' + digest(plan)
        brief = ProfiledBrief(campaign_id='intake-campaign-' + plan['id'][13:],
            budget_pence=requirements['budget_minor'], max_candidates=requirements['max_candidates'] or 100,
            profile=profile, segments=('businesses',), plan=plan)
        facts = pack['facts']
        fixtures = {'businesses': {
            'A': {'headline': 'Planning a business project?',
                  'opening': 'When might the next business project begin?',
                  'hypothesis': 'The planning question may change response.', 'fact_id': facts[0]['id']},
            'B': {'headline': 'Considering supplier dates?',
                  'opening': 'When might supplier dates fall relative to the next project?',
                  'hypothesis': 'The timing question may change response.', 'fact_id': facts[-1]['id']}}}
        bundle = ProfileCopyService.prepare_material(organization, product, {'pack': pack, 'fixtures': fixtures},
                                                    'businesses', plan['id'], today)
        draft = build_draft(snapshot, brief, bundle[1])
        return snapshot, (bundle,), draft


class IntakePreparation:
    def __init__(self, store: GroundedPreparationStore, builder: IntakePreparationBuilder, clock):
        self.store, self.builder, self.clock = store, builder, clock

    def preview(self, organization, context_request_id):
        for v in (organization, context_request_id): intake_identity(v)
        return {k:v for k,v in self.store.preview(organization, context_request_id, self.clock()).items() if k != 'context'}

    def request(self, organization, request_id):
        for v in (organization, request_id): intake_identity(v)
        return self.store.request(organization, request_id, self.clock())

    def not_committed(self, organization, request_id):
        for v in (organization, request_id): intake_identity(v)
        return self.store.not_committed(organization, request_id)

    def prepare(self, organization, actor, request_id, request: GroundedPreparationRequest):
        for v in (organization, actor, request_id): intake_identity(v)
        if type(request) is not GroundedPreparationRequest:
            raise ValueError('Use an exact grounding review and explicit synthetic preparation permission')
        try:
            old = self.request(organization, request_id)
        except NotFound:
            old = None
        if old is not None:
            if canonical(old['grounding']['request']) != canonical(asdict(request)) or old['grounding']['actor'] != actor:
                raise Conflict('Preparation request already binds different exact inputs')
            return old
        now = self.clock()
        preview = self.store.preview(organization, request.context_request_id, now)
        bundle = self.builder.build(organization, actor, request_id, request, preview, now)
        return self.store.publish(organization, actor, request_id, request, preview, bundle, self.clock())
