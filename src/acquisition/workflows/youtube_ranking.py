"""Opt-in evaluation only. Production recommendation reads never call a model."""
from decimal import Decimal, InvalidOperation
from time import monotonic

from acquisition.contracts import digest
from acquisition.reasoning import CallScope
from acquisition.runtime import Outcome
from acquisition.youtube import ranking_response, YouTubeError


def check(condition, code):
    if not condition:
        raise YouTubeError(code, code.replace("_", " "))


class ContextualRankingEvaluation:
    def __init__(self, inference, verify):
        self.inference, self.verify = inference, verify

    def rank(self, claim):
        inputs = claim.inputs
        if inputs['model_config'] != self.inference.config.payload():
            raise YouTubeError('ranking_settings_changed', 'Resume with the pinned model settings.')
        # Use exact saved request bytes, never rerender a paid request during recovery.
        messages, tools = inputs['messages'], inputs['tools']
        request = self.inference.prepare_request(messages, tools)
        if digest(request) != inputs['request_sha256']:
            raise YouTubeError('ranking_request_changed', 'The pinned ranking request changed.')
        recovered = any(row['key'] == inputs['case_id'] for row in
                        self.inference.journal.inspect(claim.organization, claim.run_id))
        started = monotonic()
        response = self.inference.call(CallScope(claim.organization, claim.run_id, claim.task_id, claim.token),
                                       inputs['case_id'], messages, tools)
        elapsed = monotonic() - started
        ranking = ranking_response(inputs['frozen'], response, self.inference.config.model, digest(request))
        if reported_cost(response) > request_ceiling(self.inference.config):
            raise YouTubeError('reported_cost_exceeded_ceiling', 'Stop and reconcile provider billing.')
        # Independent grading/native consumption must finish before the next paid case.
        evidence = self.verify(inputs, ranking)
        return Outcome('succeeded', {'case_id': inputs['case_id'], 'ranking': ranking,
                                    'response_sha256': digest(response),
                                    'inference_wall_seconds': None if recovered else elapsed,
                                    'receipt_recovered': recovered, 'verification': evidence})


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
