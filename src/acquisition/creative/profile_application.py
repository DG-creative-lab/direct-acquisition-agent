"""Profile-bound, sourced fixtures. No inference, screening or approval is implied."""

from dataclasses import asdict
import json

from acquisition.contracts import canonical, digest

from .domain import Creative
from .grounding import validate_fact_pack, fact_pack_id, product_suffix, validate_grounded_catalogue
from .ports import ProductEvidenceSource


class ProfileCopyService:
    def __init__(self, products: ProductEvidenceSource):
        self.products = products

    def prepare(self, organization, product_profile_id, segment, plan_id, today):
        profile = self.products.product_profile(organization, product_profile_id)
        material = self.products.product_material(organization, product_profile_id)
        validate_fact_pack(material['pack'], today, profile=profile)
        context = {'schema': 'creative-context/v4', 'product_profile': json.loads(canonical(asdict(profile))),
            'product_profile_id': profile.id, 'product_facts': material['pack'], 'segment': segment,
            'plan_id': plan_id, 'copy_mode': 'fixture', 'guidance': {'version': profile.brand_key + '/' + profile.brand_version,
                'voice': profile.voice, 'locked_block': profile.disclosure},
            'memory': [{'id': 'profile_fixture_no_outcomes', 'kind': 'authored_fixture_not_outcome'}],
            'audience_summary': {'taxonomy_id': profile.taxonomy_id, 'mode': 'SYNTHETIC_ONLY',
                                 'outcome_evidence': 'not_observed'}}
        context_id = 'context_' + digest({'organization': organization, **context})
        pack_id = fact_pack_id(material['pack'])
        pair = tuple(Creative(key='profile-fixture-' + profile.key + '-' + segment + '-' + arm,
            segment=segment, arm=arm, headline=item['headline'],
            opening=item['opening'] + product_suffix(material['pack'], item['fact_id']),
            hypothesis=item['hypothesis'], locked_block=profile.disclosure,
            status='synthetic_profile_fixture_unapproved', context_id=context_id, model='offline-fixture/v1',
            fact_id=item['fact_id'], fact_pack_id=pack_id, claim_check='not_evaluated',
            evidence_ids=(context['guidance']['version'], 'profile_fixture_no_outcomes', pack_id, item['fact_id']))
            for arm, item in sorted(material['fixtures'][segment].items()))
        validate_grounded_catalogue(pair, context, today)
        return context, pair

    def validate(self, organization, variants, contexts, product_profile_id, plan_id, today):
        profile = self.products.product_profile(organization, product_profile_id)
        for segment in sorted({v.segment for v in variants}):
            pair = tuple(sorted((v for v in variants if v.segment == segment), key=lambda v: v.arm))
            if not pair or len({v.context_id for v in pair}) != 1:
                raise ValueError('Profile copy requires an exact paired context')
            context = contexts[pair[0].context_id]
            if context.get('product_profile_id') != profile.id or context.get('plan_id') != plan_id:
                raise ValueError('Copy belongs to another product or plan')
            validate_grounded_catalogue(pair, context, today)
            expected_context, expected_pair = self.prepare(organization, product_profile_id, segment, plan_id, today)
            if canonical(context) != canonical(expected_context) or pair != expected_pair:
                raise ValueError('Profile proposal differs from its installed fixture context or catalogue')
