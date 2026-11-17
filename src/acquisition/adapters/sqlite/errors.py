"""Translate native storage errors at the offline command boundary."""
import sqlite3
from contextlib import contextmanager
from acquisition.application import RecoveryStorageUnavailable


@contextmanager
def recovery_storage_errors():
    try:
        yield
    except sqlite3.Error as error:
        raise RecoveryStorageUnavailable(str(error)) from error
