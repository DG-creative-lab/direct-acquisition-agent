"""Transparent offline rules and a contrasting deterministic conformance adapter."""

from acquisition.audiences import (ScoreSemantics, StrategySpec, StrategyObservation,
                                  StrategyResult)


class DeclaredSegmentCategorizer:
    def __init__(self, taxonomy, objective):
        self.spec = StrategySpec('categorization','declared-segment','v1','declared-source/v1',
                                  (('rule','retain_declared_segment'),),taxonomy.id,objective)

    def categorize(self, batch):
        keys = {s.key for s in batch.taxonomy.segments}
        rows = tuple(StrategyObservation(r.contact_id,
            category=r.segment if r.segment in keys else None, missing=r.missing,
            abstention='missing_features' if r.missing else 'unknown_segment' if r.segment not in keys else None)
            for r in batch.rows)
        return StrategyResult(batch.id,self.spec.id,rows)


class TaxonomyOrderDecision:
    """Ordinal fit only. Taxonomy order is a declared heuristic, never probability or uplift."""
    def __init__(self, taxonomy, objective):
        self.spec = StrategySpec('decision','taxonomy-order','v1','ordinal-rule/v1',
            (('order','declared'),),taxonomy.id,objective,ScoreSemantics())

    def decide(self, batch, categories):
        keys = [s.key for s in batch.taxonomy.segments]
        scores = {key:100-index*100//max(1,len(keys)-1) for index,key in enumerate(keys)}
        interpreted = {r.contact_id:r.category for r in categories.observations}
        rows = tuple(StrategyObservation(r.contact_id,value=scores.get(interpreted[r.contact_id]),
            missing=r.missing,abstention='missing_features' if r.missing else None) for r in batch.rows)
        return StrategyResult(batch.id,self.spec.id,rows,categories.id)


class ReverseTaxonomyDecision:
    """Deliberately different deterministic test strategy through the same port and policy."""
    def __init__(self, taxonomy, objective):
        self.spec = StrategySpec('decision','reverse-taxonomy-test','v1','ordinal-test-rule/v1',
            (('order','reverse'),),taxonomy.id,objective,ScoreSemantics())

    def decide(self, batch, categories):
        keys = [s.key for s in batch.taxonomy.segments]
        scores = {key:index*100//max(1,len(keys)-1) for index,key in enumerate(keys)}
        interpreted = {r.contact_id:r.category for r in categories.observations}
        rows = tuple(StrategyObservation(r.contact_id,value=scores.get(interpreted[r.contact_id]),
            missing=r.missing,abstention='missing_features' if r.missing else None) for r in batch.rows)
        return StrategyResult(batch.id,self.spec.id,rows,categories.id)
