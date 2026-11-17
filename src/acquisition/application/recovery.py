"""Storage failure contract for offline recovery commands."""

class RecoveryStorageUnavailable(Exception):
    """The recovery storage operation could not complete."""
