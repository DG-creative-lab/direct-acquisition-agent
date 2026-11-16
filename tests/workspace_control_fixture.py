"""Test-only raw access for corrupt legacy fixtures and injected storage faults."""
import sqlite3
from contextlib import contextmanager


@contextmanager
def control_connection(workspace):
    db = sqlite3.connect(workspace.root / 'workspace.sqlite', timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()
