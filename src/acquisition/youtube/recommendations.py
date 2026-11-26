"""Read-only native recommendation command, shared by offline clients/tools."""
from acquisition.contracts import canonical, digest
from json import loads
from .domain import YouTubeError, revision
from .decisioning import freeze_decision, rules_ranking, allocate_batch
from .ports import DecisionInputs, RankingReceipts


class YouTubeRecommendations:
    def __init__(self, campaigns, source: DecisionInputs, ranker: RankingReceipts | None = None):
        self.campaigns, self.source, self.ranker = campaigns, source, ranker

    def prepare(self, campaign_id, expected_revision, *, day=0, seed=42,
                policy='contextual-rules/v1', allocations=None, cohorts=None):
        revision(expected_revision)
        view = self.campaigns.read(campaign_id)
        if view['campaign']['revision'] != expected_revision:
            raise YouTubeError('campaign_changed', 'Read the current campaign revision before recommending.')
        source = self.source.load(self.campaigns.scope)
        frozen = freeze_decision(self.campaigns.scope, view, source['manifest'], source['contract'])
        if policy == 'contextual-recorded/v1':
            if self.ranker is None:
                raise YouTubeError('model_evidence_unavailable', 'No recorded model ranking is installed.')
            ranking = self.ranker.rank(loads(canonical(frozen)))
        else:
            ranking = rules_ranking(frozen)
        result = allocate_batch(frozen, ranking, [] if allocations is None else allocations,
                                [] if cohorts is None else cohorts,
                                policy=policy, day=day, seed=seed)
        # No write or provider effect is admitted. Still fence changed native
        # authority, revision, input bytes and assets before returning the view.
        current = self.campaigns.read(campaign_id)
        latest = self.source.load(self.campaigns.scope)
        if (digest(current['campaign']) != digest(view['campaign']) or latest != source):
            raise YouTubeError('recommendation_inputs_changed', 'Campaign, candidates or assets changed.')
        return result
