"""Thin REST adapter; orchestration and tool execution stay in our application."""

import json
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

from acquisition.reasoning import ModelError


BASE = "https://openrouter.ai/api/v1"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ModelError("provider_redirect_denied")


class OpenRouter:
    def __init__(self, api_key: str, timeout: float = 25):
        if not api_key.strip():
            raise ModelError("OpenRouter key is missing")
        self._api_key, self.timeout = api_key.strip(), timeout
        self._opener = urllib.request.build_opener(NoRedirect())

    def complete(self, request: dict) -> dict:
        payload = json.dumps(request, allow_nan=False).encode()
        message = urllib.request.Request(BASE + "/chat/completions", data=payload, headers={
            "Authorization": "Bearer " + self._api_key, "Content-Type": "application/json",
            "X-OpenRouter-Title": "Direct Acquisition Agent local demo",
        })
        try:
            with self._opener.open(message, timeout=self.timeout) as response:
                raw = response.read(128001)
            if len(raw) > 128000:
                raise ModelError("provider_response_too_large")
            return normalize(json.loads(raw))
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            raise ModelError(f"provider_http_{code}") from None
        except (urllib.error.URLError, TimeoutError, OSError):
            # Never expose Authorization headers, provider error bodies or exception URLs.
            raise ModelError("provider_request_failed") from None


def normalize(data: dict) -> dict:
    if not isinstance(data, dict) or data.get("error") or len(data.get("choices", [])) != 1:
        raise ModelError("invalid_provider_envelope")
    choice, usage = data["choices"][0], data.get("usage") or {}
    message = choice.get("message") or {}
    calls = message.get("tool_calls") or []
    for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if field in usage and (type(usage[field]) is not int or usage[field] < 0):
            raise ModelError("invalid_usage")
    try:
        cost = Decimal(str(usage["cost"])) if usage.get("cost") is not None else None
    except InvalidOperation:
        raise ModelError("invalid_usage_cost") from None
    if cost is not None and (not cost.is_finite() or cost < 0):
        raise ModelError("invalid_usage_cost")
    metadata = {"generation_id": data.get("id"), "model": data.get("model"), "provider": data.get("provider"),
                "usage": {k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cost")
                          if k in usage and type(usage[k]) in {int, float} and usage[k] >= 0}}
    if choice.get("finish_reason") != "tool_calls":
        reason = choice.get("finish_reason")
        code = "provider_finish_" + reason if reason in {"stop", "length", "error", "content_filter"} else "invalid_finish_reason"
        raise ModelError(code, metadata)
    if len(calls) != 1:
        raise ModelError("expected_one_tool_call", metadata)
    call = calls[0]
    function = call.get("function") or {}
    if call.get("type") != "function" or not isinstance(call.get("id"), str) or not call["id"]:
        raise ModelError("invalid_tool_call")
    if not isinstance(function.get("name"), str) or not isinstance(function.get("arguments"), str):
        raise ModelError("invalid_tool_arguments")
    return {"message": {"role": "assistant", "content": None, "tool_calls": [call]},
            "generation_id": data.get("id"), "model": data.get("model"),
            "provider": data.get("provider"), "usage": {k: usage[k] for k in
                ("prompt_tokens", "completion_tokens", "total_tokens", "cost") if k in usage}}


def inexpensive_models() -> list[dict]:
    """Public live catalogue; no static recommendation or credential is required."""
    with urllib.request.build_opener(NoRedirect()).open(BASE + "/models", timeout=20) as response:
        raw = response.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ModelError("model_catalogue_too_large")
    result = []
    for model in json.loads(raw).get("data", []):
        if "tools" not in model.get("supported_parameters", []) or "text" not in model.get("architecture", {}).get("output_modalities", []):
            continue
        try:
            prompt = Decimal(model["pricing"]["prompt"]) * 1_000_000
            completion = Decimal(model["pricing"]["completion"]) * 1_000_000
            request_cost = Decimal(model["pricing"].get("request", "0"))
        except (KeyError, InvalidOperation):
            continue
        if all(v.is_finite() and v >= 0 for v in (prompt, completion, request_cost)) and prompt <= 1 and completion <= 2 and request_cost == 0:
            result.append({"id": model["id"], "input_usd_per_million": str(prompt),
                           "output_usd_per_million": str(completion),
                           "supports_forced_tool_choice": "tool_choice" in model.get("supported_parameters", [])})
    return sorted(result, key=lambda m: (Decimal(m["input_usd_per_million"]) + Decimal(m["output_usd_per_million"]), m["id"]))
