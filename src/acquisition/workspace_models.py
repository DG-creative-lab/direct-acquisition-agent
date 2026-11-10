"""Ephemeral OpenRouter connections for the local workspace."""

import re
import secrets
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from threading import Lock
from uuid import UUID

from acquisition.adapters.openrouter import OpenRouter, WORKSPACE_PRICE_TIERS, workspace_models
from acquisition.contracts import Conflict, digest
from acquisition.reasoning import ModelConfig


class ModelSessionExpired(Conflict):
    pass


class ModelSelectionRejected(ValueError):
    pass


@dataclass
class Connection:
    tab: str
    binding: str
    gateway: OpenRouter
    expires: float


class WorkspaceModels:
    idle_seconds = 300
    max_connections = 32

    def __init__(self):
        self._browser = ContextVar("workspace_browser_model", default=None)
        self._connections = {}
        self._connection_lock = Lock()
        self._catalogue_lock = Lock()
        self._catalogue = []
        self._refresh_at = 0

    def catalogue(self):
        with self._catalogue_lock:
            if time.monotonic() >= self._refresh_at:
                self._catalogue = workspace_models()
                self._refresh_at = time.monotonic() + 300
            return self._catalogue

    def connect(self, key, session, previous=None):
        if not key or not re.fullmatch(r"[A-Za-z0-9_-]{32,512}", key):
            raise ValueError("Enter a valid OpenRouter API key.")
        try:
            if str(UUID(session or "", version=4)) != session:
                raise ValueError
        except ValueError:
            raise ValueError("Reload the workspace to establish a browser model session.") from None
        binding = digest({"purpose": "openrouter-browser/v1", "session": session, "key": key})
        gateway = OpenRouter(key)
        gateway.validate_key()
        handle = secrets.token_urlsafe(32)
        with self._connection_lock:
            now = time.monotonic()
            self._prune(now)
            prior = self._connections.get(previous)
            if prior and prior.tab != session:
                raise Conflict("The previous connection belongs to another browser session.")
            # Reconnecting an identical key and tab also supersedes its old handle
            # when the original acknowledgement was lost.
            replaced = [h for h, c in self._connections.items() if h == previous or c.binding == binding]
            if len(self._connections) - len(replaced) >= self.max_connections:
                raise Conflict("Too many OpenRouter connections. Remove an existing connection and retry.")
            for h in replaced:
                del self._connections[h]
            self._connections[handle] = Connection(session, binding, gateway, now + self.idle_seconds)
        return {"handle": handle, "binding": binding}

    def _prune(self, now):
        for handle in [h for h, c in self._connections.items() if c.expires <= now]:
            del self._connections[handle]

    def expire(self):
        with self._connection_lock:
            self._prune(time.monotonic())

    def disconnect(self, handle, tab):
        with self._connection_lock:
            current = self._connections.get(handle)
            if current and current.tab == tab:
                del self._connections[handle]

    @contextmanager
    def browser(self, handle, tab, model=None, tier=None):
        with self._connection_lock:
            now = time.monotonic()
            self._prune(now)
            current = self._connections.get(handle)
            if current is None or current.tab != tab:
                raise ModelSessionExpired("Reconnect your OpenRouter key in Local reviewer.")
            current.expires = now + self.idle_seconds
        context = self._browser.set((current, model, tier))
        try:
            yield
        finally:
            self._browser.reset(context)

    @property
    def binding(self):
        current = self._browser.get()
        return current[0].binding if current else None

    def selected(self, max_calls):
        current = self._browser.get()
        if current is None:
            return ModelConfig("openai/gpt-oss-120b", max_calls=max_calls, force_tool_choice=True)
        connection, model, tier = current
        entry = next((entry for entry in self.catalogue() if entry["id"] == model), None) if model else None
        if entry is None or tier not in WORKSPACE_PRICE_TIERS:
            raise ModelSelectionRejected("Choose an available OpenRouter model in the composer.")
        prompt, completion = WORKSPACE_PRICE_TIERS[tier]
        current_prompt, current_completion = WORKSPACE_PRICE_TIERS[entry["tier"]]
        if current_prompt > prompt or current_completion > completion:
            raise ModelSelectionRejected("This model moved to a higher price tier. Choose a model again before retrying.")
        return ModelConfig(model, max_calls=max_calls, force_tool_choice=True, browser_binding=connection.binding,
                           max_prompt_usd_per_million=prompt, max_completion_usd_per_million=completion)

    def matches(self, frozen):
        return (frozen or {}).get("browser_binding") == self.binding

    @staticmethod
    def frozen(payload, *, max_calls=None):
        if not (payload or {}).get("browser_binding"):
            return None
        config = ModelConfig(**payload)
        return replace(config, max_calls=max_calls) if max_calls is not None else config

    def gateway(self, config):
        if config.browser_binding != self.binding:
            raise Conflict("Continue this request from its original OpenRouter session.")
        return self._browser.get()[0].gateway
