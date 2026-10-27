from collections.abc import Callable
import re

from acquisition.contracts import canonical, digest

from .domain import CallScope, ModelConfig, ModelError
from .ports import CallJournal, ModelGateway


class Inference:
    """Reserve before the paid call; reuse durable receipts on task replay."""

    def __init__(self, gateway: ModelGateway, journal: CallJournal, config: ModelConfig, clock: Callable[[], float]):
        self.gateway, self.journal, self.config, self.clock = gateway, journal, config, clock

    def prepare_request(self, messages: list[dict], tools: list[dict]) -> dict:
        free = self.config.model.endswith(":free")
        request = {
            "model": self.config.model, "messages": messages, "tools": tools,
            "max_tokens": self.config.max_output_tokens, "stream": False,
            "provider": {"require_parameters": True, "sort": "price", "allow_fallbacks": False,
                         "max_price": {"prompt": 0 if free else self.config.max_prompt_usd_per_million,
                                       "completion": 0 if free else self.config.max_completion_usd_per_million, "request": 0}},
        }
        if self.config.force_tool_choice:
            request["tool_choice"] = "required"
        if len(canonical(request).encode()) > self.config.max_input_bytes:
            raise ModelError("input_budget_exceeded")
        return request

    def call(self, scope: CallScope, key: str, messages: list[dict], tools: list[dict]) -> dict:
        request = self.prepare_request(messages, tools)
        cached = self.journal.reserve(scope, key, digest(request), self.config.max_calls, self.clock())
        if cached is not None:
            return cached
        try:
            response = self.gateway.complete(request)
        except Exception as error:
            code = str(error) if isinstance(error, ModelError) and re.fullmatch(r"[a-z_0-9]{1,80}", str(error)) else "provider_outcome_unknown"
            receipt = error.receipt if isinstance(error, ModelError) else None
            self.journal.record(scope, key, receipt, code)
            raise ModelError(code + "_no_automatic_retry") from None
        self.journal.record(scope, key, response, None)
        return response
