"""Small shared technical vocabulary; business concepts belong to modules."""

import hashlib
import json


class Conflict(ValueError):
    """An identity or expected revision refers to different durable content."""


class NotFound(LookupError):
    """An object does not exist in the requested organization."""


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()
