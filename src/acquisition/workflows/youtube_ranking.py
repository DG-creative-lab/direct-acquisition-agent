"""Opt-in evaluation only. Production recommendation reads never call a model."""
from decimal import Decimal, InvalidOperation
from time import monotonic

from acquisition.contracts import digest
from acquisition.reasoning import CallScope
from acquisition.runtime import Outcome
from acquisition.youtube import ranking_response, YouTubeError

RANKING_FINALIZATION = 'youtube.contextual_ranking_finalize.v1'
SOURCE_RECOVERY_POLICY = 'first-attempt-source-validation/v1'


class EvaluationSourceChanged(RuntimeError):
    """Persisted runtime failure code: never reinterpret as a valid old sample."""


class EvaluationSourceUnverified(RuntimeError):
    """An interrupted interval cannot be certified from a restored checkout."""


def check(condition, code):
    if not condition:
        raise YouTubeError(code, code.replace("_", " "))


class ContextualRankingEvaluation:
    def __init__(self, inference, verify, verify_source):
        self.inference, self.verify, self.verify_source = inference, verify, verify_source

    def rank(self, claim):
        self.require_first_attempt(claim)
        inputs = claim.inputs
        self.verify_source(inputs)
        if inputs['model_config'] != self.inference.config.payload():
            raise YouTubeError('ranking_settings_changed', 'Resume with the pinned model settings.')
        # Use exact saved request bytes, never rerender a paid request during recovery.
        messages, tools = inputs['messages'], inputs['tools']
        request = self.inference.prepare_request(messages, tools)
        if digest(request) != inputs['request_sha256']:
            raise YouTubeError('ranking_request_changed', 'The pinned ranking request changed.')
        recovered = any(row['key'] == inputs['case_id'] for row in
                        self.inference.journal.inspect(claim.organization, claim.run_id))
        if recovered:
            raise EvaluationSourceUnverified('Saved provider reply has no committed source interval')
        started = monotonic()
        response = self.inference.call(CallScope(claim.organization, claim.run_id, claim.task_id, claim.token),
                                       inputs['case_id'], messages, tools)
        elapsed = monotonic() - started
        ranking = ranking_response(inputs['frozen'], response, self.inference.config.model, digest(request))
        if reported_cost(response) > request_ceiling(self.inference.config):
            raise YouTubeError('reported_cost_exceeded_ceiling', 'Stop and reconcile provider billing.')
        # Independent grading/native consumption must finish before the next paid case.
        evidence = self.verify(inputs, ranking)
        source_validation = self.verify_source(inputs)
        return Outcome('succeeded', {'case_id': inputs['case_id'], 'ranking': ranking,
                                    'response_sha256': digest(response),
                                    'inference_wall_seconds': None if recovered else elapsed,
                                    'receipt_recovered': recovered, 'verification': evidence,
                                    'source_validation': source_validation})

    def finalize(self, claim):
        self.require_first_attempt(claim)
        # Completion has an explicit saved cutoff after all paid cases settle.
        return Outcome('succeeded', {'plan_id': claim.inputs['plan_id'],
                                    'source_validation': self.verify_source(claim.inputs)})

    @staticmethod
    def require_first_attempt(claim):
        # Claim attempts are durable before the handler runs. An expired worker
        # may have detected a mismatch without retaining authority to save it.
        if (claim.attempt != 1
                or claim.inputs.get('source_recovery_policy') != SOURCE_RECOVERY_POLICY):
            raise EvaluationSourceUnverified('Interrupted source-validation interval requires review')


def reported_cost(response):
    try:
        value = response['usage']['cost']
        check(type(value) in {int, float}, 'billing_unknown')
        cost = Decimal(str(value))
        check(cost.is_finite() and cost >= 0, 'billing_unknown')
        return cost
    except (KeyError, TypeError, InvalidOperation):
        check(False, 'billing_unknown')


def request_ceiling(config):
    # Conservative local estimate: at most one input token per serialized byte.
    # Provider price ceilings are routed separately; this is not a billing guarantee.
    if config.model.endswith(':free'):
        return Decimal(0)
    return (Decimal(config.max_input_bytes) * Decimal(str(config.max_prompt_usd_per_million))
            + Decimal(config.max_output_tokens) * Decimal(str(config.max_completion_usd_per_million))) / 1000000
