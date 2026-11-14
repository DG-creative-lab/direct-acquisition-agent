"""Frozen advisory inference contracts. These values confer no campaign authority."""

from dataclasses import asdict, dataclass

from acquisition.contracts import digest
from .contacts import bounded, channel_purpose
from .domain import AudienceTaxonomy, taxonomy_from


FEATURE_SCHEMA = 'contact-features/v1'


@dataclass(frozen=True)
class ScoreSemantics:
    metric: str = 'fit'
    units: str = 'ordinal_points'
    horizon_days: int | None = None
    contrast: str | None = None

    def __post_init__(self):
        units = {'fit':'ordinal_points', 'response_propensity':'probability_ppm',
                 'expected_value':'GBP_minor_units', 'uplift':'incremental_probability_ppm'}
        if self.metric not in units or self.units != units[self.metric]:
            raise ValueError('Declare the exact score metric and units')
        if self.metric == 'fit':
            if self.horizon_days is not None:
                raise ValueError('Ordinal fit has no response horizon')
        elif type(self.horizon_days) is not int or not 1 <= self.horizon_days <= 3650:
            raise ValueError('Predictive scores require a bounded horizon in days')
        if self.metric == 'uplift':
            bounded(self.contrast)
        elif self.contrast is not None:
            raise ValueError('Only uplift has a treatment/control contrast')

    def accepts(self, value):
        if type(value) is not int:
            return False
        limits = {'fit':(0,100), 'response_propensity':(0,1000000),
                  'expected_value':(-10**12,10**12), 'uplift':(-1000000,1000000)}
        low, high = limits[self.metric]
        return low <= value <= high


@dataclass(frozen=True)
class FeatureRow:
    contact_id: str
    experiment_unit: str | None
    segment: str | None

    def __post_init__(self):
        bounded(self.contact_id)
        for value in (self.experiment_unit,self.segment):
            if value is not None: bounded(value)

    @property
    def missing(self):
        return tuple(key for key in ('experiment_unit','segment') if getattr(self,key) is None)


@dataclass(frozen=True)
class FeatureBatch:
    organization: str
    assessment_id: str
    profile_id: str
    source_id: str
    readiness_digest: str
    channel: str
    purpose: str
    taxonomy: AudienceTaxonomy
    objective: str
    rows: tuple[FeatureRow, ...]
    feature_schema: str = FEATURE_SCHEMA
    mode: str = 'SYNTHETIC_ONLY'

    def __post_init__(self):
        for value in (self.organization,self.assessment_id,self.profile_id,self.source_id,
                      self.readiness_digest,self.objective): bounded(value)
        channel_purpose(self.channel,self.purpose)
        if (type(self.taxonomy) is not AudienceTaxonomy or self.feature_schema != FEATURE_SCHEMA
                or self.mode != 'SYNTHETIC_ONLY' or type(self.rows) is not tuple or len(self.rows)>500
                or any(type(r) is not FeatureRow for r in self.rows)
                or len({r.contact_id for r in self.rows}) != len(self.rows)):
            raise ValueError('Use a complete bounded typed feature batch')

    @property
    def feature_digest(self):
        return digest({'schema':self.feature_schema,'rows':[asdict(r) for r in self.rows]})

    @property
    def id(self):
        return 'features_' + digest(asdict(self))


@dataclass(frozen=True)
class StrategySpec:
    kind: str
    key: str
    version: str
    model_version: str
    config: tuple[tuple[str, str], ...]
    taxonomy_id: str
    objective: str
    score: ScoreSemantics | None = None
    feature_schema: str = FEATURE_SCHEMA

    def __post_init__(self):
        for value in (self.key,self.version,self.model_version,self.taxonomy_id,self.objective): bounded(value)
        if (self.kind not in {'categorization','decision'} or self.feature_schema != FEATURE_SCHEMA
                or (self.kind=='decision' and type(self.score) is not ScoreSemantics)
                or (self.kind=='categorization' and self.score is not None)):
            raise ValueError('Declare a typed strategy kind and score contract')
        if type(self.config) is not tuple or len(self.config)>16:
            raise ValueError('Freeze bounded strategy configuration')
        for pair in self.config:
            if type(pair) is not tuple or len(pair)!=2: raise ValueError('Use immutable configuration pairs')
            for value in pair: bounded(value)
        if len({p[0] for p in self.config})!=len(self.config): raise ValueError('Duplicate strategy configuration')

    @property
    def id(self):
        return 'strategy_' + digest(asdict(self))


@dataclass(frozen=True)
class StrategyObservation:
    contact_id: str
    category: str | None = None
    value: int | None = None
    missing: tuple[str, ...] = ()
    abstention: str | None = None
    uncertainty: str = 'not_estimated'
    lower: int | None = None
    upper: int | None = None

    def __post_init__(self):
        bounded(self.contact_id)
        for value in (self.category,self.abstention):
            if value is not None: bounded(value)
        for value in (self.value,self.lower,self.upper):
            if value is not None and (type(value) is not int or not -10**12<=value<=10**12):
                raise ValueError('Use bounded integer score observations')
        if (type(self.missing) is not tuple or len(set(self.missing))!=len(self.missing)
                or not set(self.missing)<={'segment','experiment_unit'}):
            raise ValueError('Declare explicit missing feature names')
        if self.uncertainty not in {'not_estimated','interval'}:
            raise ValueError('Declare uncertainty without inventing confidence')


@dataclass(frozen=True)
class StrategyResult:
    batch_id: str
    strategy_id: str
    observations: tuple[StrategyObservation, ...]
    # Ranking binds the exact preceding interpretation, including abstentions.
    categories_id: str | None = None

    def __post_init__(self):
        bounded(self.batch_id); bounded(self.strategy_id)
        if self.categories_id is not None: bounded(self.categories_id)
        if (type(self.observations) is not tuple or len(self.observations)>500
                or any(type(r) is not StrategyObservation for r in self.observations)):
            raise ValueError('Use bounded typed strategy observations')

    @property
    def id(self):
        return 'strategy_result_' + digest(asdict(self))


@dataclass(frozen=True)
class StrategyRun:
    categories: StrategyResult | None = None
    decisions: StrategyResult | None = None
    failure: str | None = None

    def __post_init__(self):
        if (any(r is not None and type(r) is not StrategyResult for r in (self.categories,self.decisions))
                or self.failure not in {None,'categorization_failure','decision_failure'}):
            raise ValueError('Use typed strategy results and fixed failure classifications')


@dataclass(frozen=True)
class DecisionRequest:
    assessment_id: str
    categorizer: StrategySpec
    decision: StrategySpec
    score: ScoreSemantics
    budget_pence: int
    unit_cost_pence: int
    max_candidates: int
    seed: int

    def __post_init__(self):
        bounded(self.assessment_id)
        if (type(self.categorizer) is not StrategySpec or self.categorizer.kind!='categorization'
                or type(self.decision) is not StrategySpec or self.decision.kind!='decision'
                or type(self.score) is not ScoreSemantics):
            raise ValueError('Declare exact categorization and decision contracts')
        for value, low, high in ((self.budget_pence,0,10**9),(self.unit_cost_pence,1,10**6),
                                  (self.max_candidates,1,500),(self.seed,0,2**31-1)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError('Use bounded integer selection limits')


def strategy_compatibility(batch, request):
    reasons = []
    for spec in (request.categorizer,request.decision):
        if spec.taxonomy_id != batch.taxonomy.id: reasons.append('unsupported_taxonomy')
        if spec.objective != batch.objective: reasons.append('unsupported_objective')
        if spec.feature_schema != batch.feature_schema: reasons.append('unsupported_feature_schema')
    if request.decision.score != request.score: reasons.append('unsupported_score_semantics')
    return sorted(set(reasons))


def result_issues(batch, spec, result, categories=None):
    """Reject partial, substituted and untyped output without fabricating missing results."""
    if type(result) is not StrategyResult:
        return ['result_missing']
    if (result.batch_id != batch.id or result.strategy_id != spec.id
            or result.categories_id != (categories.id if categories else None)):
        return ['result_binding_mismatch']
    if (type(result.observations) is not tuple or len(result.observations)>500
            or any(type(r) is not StrategyObservation for r in result.observations)):
        return ['invalid_observations']
    inputs = {r.contact_id:r for r in batch.rows}
    ids = [r.contact_id for r in result.observations]
    if len(set(ids))!=len(ids) or set(ids)!=set(inputs): return ['incomplete_population']
    reasons = set()
    taxonomy = {s.key for s in batch.taxonomy.segments}
    for row in result.observations:
        source = inputs[row.contact_id]
        if (type(row.missing) is not tuple or row.missing != source.missing
                or (row.abstention is not None and (type(row.abstention) is not str
                    or not row.abstention.strip() or len(row.abstention)>200))):
            reasons.add('invalid_missingness')
        if source.missing or row.missing: reasons.add('missing_features')
        if row.abstention is not None: reasons.add('strategy_abstention')
        if spec.kind == 'categorization':
            if row.value is not None or row.category not in taxonomy: reasons.add('category_unavailable')
        else:
            if row.category is not None or not spec.score.accepts(row.value): reasons.add('score_unavailable')
        if row.uncertainty == 'not_estimated':
            if row.lower is not None or row.upper is not None: reasons.add('invalid_uncertainty')
        elif (spec.kind!='decision' or row.uncertainty!='interval'
                or not spec.score.accepts(row.lower) or not spec.score.accepts(row.upper)
                or not spec.score.accepts(row.value) or not row.lower<=row.value<=row.upper):
            reasons.add('invalid_uncertainty')
    return sorted(reasons)


def run_issues(batch, request, run):
    issues = strategy_compatibility(batch,request)
    if type(run) is not StrategyRun: return issues + ['invalid_run']
    if run.failure:
        # Fixed classifications only. Provider exception text never enters an artifact.
        issues.append(run.failure if run.failure in {'categorization_failure','decision_failure'} else 'invalid_run')
    issues += result_issues(batch,request.categorizer,run.categories)
    if not issues:
        issues += result_issues(batch,request.decision,run.decisions,run.categories)
    return sorted(set(issues))


def feature_batch_from(payload):
    return FeatureBatch(**(payload | {'taxonomy':taxonomy_from(payload['taxonomy']),
        'rows':tuple(FeatureRow(**r) for r in payload['rows'])}))


def strategy_spec_from(payload):
    return StrategySpec(**(payload | {'config':tuple(tuple(p) for p in payload['config']),
        'score':ScoreSemantics(**payload['score']) if payload['score'] is not None else None}))


def decision_request_from(payload):
    return DecisionRequest(**(payload | {'categorizer':strategy_spec_from(payload['categorizer']),
        'decision':strategy_spec_from(payload['decision']),'score':ScoreSemantics(**payload['score'])}))


def strategy_run_from(payload):
    def result(value):
        if value is None: return None
        return StrategyResult(**(value | {'observations':tuple(StrategyObservation(**(r | {
            'missing':tuple(r['missing'])})) for r in value['observations'])}))
    return StrategyRun(result(payload['categories']),result(payload['decisions']),payload['failure'])
