"""Compose public profile, planning, audience, copy and campaign APIs."""

from datetime import datetime, timezone

from acquisition.audiences import ProfileFixtureAudience
from acquisition.campaigns import CampaignProfileSource, CampaignService, ProfiledBrief, ProfileProposalStore
from acquisition.conversations import profile_plan
from acquisition.contracts import Conflict, canonical
from acquisition.creative import ProfileCopyService


class ProfilePreparation:
    def __init__(self, profiles: CampaignProfileSource, source: ProfileFixtureAudience,
                 copy: ProfileCopyService, campaigns: CampaignService, proposals: ProfileProposalStore, clock):
        self.profiles, self.source = profiles, source
        self.copy, self.campaigns, self.proposals, self.clock = copy, campaigns, proposals, clock

    def prepare(self, organization, request_id, key, version, *, objective, budget_pence,
                segments, country, currency, channel, size=100, seed=42, as_of=None):
        command = {'schema': 'profile-preparation/v1', 'organization': organization, 'key': key, 'version': version,
            'objective': objective, 'budget_pence': budget_pence, 'segments': list(segments), 'country': country,
            'currency': currency, 'channel': channel, 'size': size, 'seed': seed, 'as_of': as_of}
        existing = self.proposals.find(organization, request_id)
        if existing is not None:
            if canonical(existing.manifest['brief']['plan']['command']) != canonical(command):
                raise Conflict('Profile request already binds different exact inputs')
            return self._result(existing, historical=True)
        profile = self.profiles.campaign_profile(organization, key, version)
        today = datetime.fromtimestamp(self.clock(), timezone.utc).date()
        snapshot = self.source.snapshot(organization, profile.taxonomy, size, seed, as_of or today.isoformat())
        plan = profile_plan(organization, request_id, profile, objective=objective, budget_pence=budget_pence,
                            segments=segments, country=country, currency=currency, channel=channel,
                            snapshot_id=snapshot.id, command=command)
        brief = ProfiledBrief(campaign_id='profile-campaign-' + plan['id'].removeprefix('profile_plan_'),
                              budget_pence=budget_pence, profile=profile, segments=segments, plan=plan)
        bundles = tuple(self.copy.prepare(organization, profile.product_profile_id, segment, plan['id'], today)
                        for segment in segments)
        creatives = tuple(item for _, pair in bundles for item in pair)
        draft = self.campaigns.propose(snapshot, brief, creatives)
        identity = self.proposals.publish(organization, request_id, snapshot, bundles, draft)
        if identity != draft.id:
            raise Conflict('Published proposal identity differs from its exact artifact')
        return self._result(draft, historical=False)

    @staticmethod
    def _result(draft, *, historical):
        identity = draft.id
        plan = draft.manifest['brief']['plan']
        result = {'draft_id': identity, 'manifest_hash': identity.removeprefix('draft_'),
                  'counts': draft.manifest['counts'], 'variable_cost_pence': draft.manifest['variable_cost_pence']}
        return result | {'profile_id': draft.manifest['profile_id'], 'plan': plan, 'approval': 'not_granted',
            'execution': 'not_performed', 'semantic_screen': 'not_evaluated',
            'observation': 'historical_proposal' if historical else 'prepared_proposal'}
