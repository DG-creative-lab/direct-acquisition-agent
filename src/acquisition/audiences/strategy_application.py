"""One bounded offline strategy attempt; no retries, fallback or text-completion gateway."""

from .strategies import (DecisionRequest, ScoreSemantics, StrategyRun, StrategyResult, result_issues,
                         strategy_compatibility)
from .ports import AudienceCategorizer, AudienceDecisionStrategy, AudienceDecisionStore


class AudienceDecisions:
    def __init__(self, categorizer: AudienceCategorizer, decision: AudienceDecisionStrategy,
                 store: AudienceDecisionStore):
        self.categorizer, self.decision, self.store = categorizer, decision, store

    def prepare(self, organization, request_id, assessment_id, *, budget_pence, unit_cost_pence,
                max_candidates, seed, score=ScoreSemantics()):
        request = DecisionRequest(assessment_id,self.categorizer.spec,self.decision.spec,score,
                                  budget_pence,unit_cost_pence,max_candidates,seed)
        replay = self.store.replay(organization,request_id,request)
        if replay is not None: return replay
        batch = self.store.capture(organization,request)
        run = StrategyRun()
        if not strategy_compatibility(batch,request):
            try:
                categories = self.categorizer.categorize(batch)
            except Exception:
                run = StrategyRun(failure='categorization_failure')
            else:
                if type(categories) is not StrategyResult: categories = None
                run = StrategyRun(categories=categories)
                if not result_issues(batch,request.categorizer,categories):
                    try:
                        decisions = self.decision.decide(batch,categories)
                        run = StrategyRun(categories,decisions if type(decisions) is StrategyResult else None)
                    except Exception:
                        run = StrategyRun(categories=categories,failure='decision_failure')
        return self.store.publish(organization,request_id,request,batch,run)

    def inspect(self, organization, request_id):
        return self.store.inspect(organization,request_id)
