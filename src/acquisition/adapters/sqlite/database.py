import sqlite3
from contextlib import contextmanager
from pathlib import Path
import json
import time

from acquisition.contracts import digest


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, organization TEXT NOT NULL, request_id TEXT NOT NULL,
 request_hash TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN
 ('queued','running','waiting','succeeded','failed','cancelled')),
 created_at REAL NOT NULL, UNIQUE(organization,request_id));
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), position INTEGER NOT NULL,
 capability TEXT NOT NULL, inputs TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN
 ('queued','running','waiting','succeeded','failed','cancelled')),
 attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
 available_at REAL NOT NULL, lease_until REAL, token TEXT, output TEXT, resume TEXT,
 UNIQUE(run_id,position));
CREATE INDEX IF NOT EXISTS tasks_ready ON tasks(status,available_at);
CREATE TABLE IF NOT EXISTS events (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
 task_id TEXT, kind TEXT NOT NULL, data TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audiences (
 organization TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS drafts (
 organization TEXT NOT NULL, id TEXT NOT NULL, manifest TEXT NOT NULL,
 mailing TEXT NOT NULL, assignments TEXT NOT NULL, PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS draft_operations (
 organization TEXT NOT NULL, operation_id TEXT NOT NULL, draft_id TEXT NOT NULL,
 PRIMARY KEY(organization,operation_id),
 FOREIGN KEY(organization,draft_id) REFERENCES drafts(organization,id));
PRAGMA user_version=1;
"""

DAY_TWO = """
CREATE TABLE IF NOT EXISTS editorial_memories (
 organization TEXT NOT NULL, id TEXT NOT NULL, segment TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS creative_contexts (
 organization TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS generated_catalogues (
 organization TEXT NOT NULL, operation_id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,operation_id));
CREATE TABLE IF NOT EXISTS model_calls (
 organization TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES runs(id), call_key TEXT NOT NULL,
 task_id TEXT NOT NULL REFERENCES tasks(id), lease_token TEXT NOT NULL,
 request_hash TEXT NOT NULL, status TEXT NOT NULL, response TEXT, error TEXT,
 PRIMARY KEY(organization,run_id,call_key));
PRAGMA user_version=2;
"""

DAY_THREE = """
CREATE TABLE IF NOT EXISTS review_actors (
 organization TEXT NOT NULL, id TEXT NOT NULL, roles TEXT NOT NULL,
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), generation INTEGER NOT NULL,
 PRIMARY KEY(organization,id));
CREATE TABLE IF NOT EXISTS review_authorities (
 organization TEXT PRIMARY KEY, evidence_epoch INTEGER NOT NULL, audience_epoch INTEGER NOT NULL,
 pack TEXT NOT NULL, policy TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS review_cases (
 organization TEXT NOT NULL, id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES runs(id), current_subject TEXT NOT NULL,
 PRIMARY KEY(organization,id), UNIQUE(organization,run_id));
CREATE TABLE IF NOT EXISTS review_subjects (
 organization TEXT NOT NULL, id TEXT NOT NULL, case_id TEXT NOT NULL, revision INTEGER NOT NULL,
 payload TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(organization,id), UNIQUE(organization,case_id,revision),
 FOREIGN KEY(organization,case_id) REFERENCES review_cases(organization,id));
CREATE TABLE IF NOT EXISTS review_decisions (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, organization TEXT NOT NULL, id TEXT NOT NULL,
 case_id TEXT NOT NULL, subject_id TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(organization,id),
 FOREIGN KEY(organization,subject_id) REFERENCES review_subjects(organization,id));
CREATE TABLE IF NOT EXISTS review_revocations (
 organization TEXT NOT NULL, approval_id TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL,
 at REAL NOT NULL, PRIMARY KEY(organization,approval_id),
 FOREIGN KEY(organization,approval_id) REFERENCES review_decisions(organization,id));
CREATE TABLE IF NOT EXISTS review_suppressions (
 organization TEXT NOT NULL, business_id TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL,
 at REAL NOT NULL, PRIMARY KEY(organization,business_id));
CREATE TABLE IF NOT EXISTS review_commands (
 organization TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, receipt TEXT NOT NULL,
 PRIMARY KEY(organization,request_id));
CREATE TABLE IF NOT EXISTS simulated_agency_jobs (
 organization TEXT NOT NULL, case_id TEXT NOT NULL, id TEXT NOT NULL, approval_id TEXT NOT NULL,
 subject_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(organization,case_id), UNIQUE(organization,id),
 FOREIGN KEY(organization,approval_id) REFERENCES review_decisions(organization,id));
CREATE TABLE IF NOT EXISTS review_events (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, organization TEXT NOT NULL, case_id TEXT,
 kind TEXT NOT NULL, payload TEXT NOT NULL, at REAL NOT NULL);
PRAGMA user_version=4;
"""


DAY_FOUR = """
CREATE TABLE IF NOT EXISTS learning_cohorts (
 organization TEXT NOT NULL, id TEXT NOT NULL, job_id TEXT NOT NULL, payload TEXT NOT NULL,
 opened_at REAL NOT NULL, finalized_at REAL, finalization TEXT,
 PRIMARY KEY(organization,id), UNIQUE(organization,job_id));
CREATE TABLE IF NOT EXISTS learning_members (
 organization TEXT NOT NULL, business_id TEXT NOT NULL, cohort_id TEXT NOT NULL,
 PRIMARY KEY(organization,business_id),
 FOREIGN KEY(organization,cohort_id) REFERENCES learning_cohorts(organization,id));
CREATE TABLE IF NOT EXISTS learning_outcomes (
 organization TEXT NOT NULL, cohort_id TEXT NOT NULL, business_id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,cohort_id,business_id),
 FOREIGN KEY(organization,cohort_id) REFERENCES learning_cohorts(organization,id));
CREATE TABLE IF NOT EXISTS learning_beliefs (
 organization TEXT NOT NULL, cohort_id TEXT NOT NULL, segment TEXT NOT NULL, arm TEXT NOT NULL,
 creative_id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,cohort_id,segment,arm),
 FOREIGN KEY(organization,cohort_id) REFERENCES learning_cohorts(organization,id));
CREATE TABLE IF NOT EXISTS learning_commands (
 organization TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, receipt TEXT NOT NULL,
 PRIMARY KEY(organization,request_id));
CREATE TABLE IF NOT EXISTS learning_events (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, organization TEXT NOT NULL, cohort_id TEXT NOT NULL,
 kind TEXT NOT NULL, payload TEXT NOT NULL, at REAL NOT NULL);
PRAGMA user_version=5;
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as connection:
            # Version discovery and every migration share one SQLite write lock.
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1, 2, 3, 4, 5}:
                raise ValueError(f"Unsupported database schema {version}")
            if version == 0:
                self._apply_migration(connection, SCHEMA)
            if version < 2:
                self._apply_migration(connection, DAY_TWO)
            if version < 3:
                self._freeze_legacy_admissions(connection)
            if version < 4:
                self._apply_migration(connection, DAY_THREE)
            if version < 5:
                self._apply_migration(connection, DAY_FOUR)
        self._enable_wal()

    def _enable_wal(self):
        # Journal-mode changes require their own lock outside a transaction.
        # A competing initializer can hold it just after our migration commits.
        deadline = time.monotonic() + 10
        while True:
            try:
                with self.connect() as connection:
                    connection.execute("PRAGMA busy_timeout=100")
                    if connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal":
                        return
                    if connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] != "wal":
                        raise sqlite3.OperationalError("SQLite did not enable WAL journal mode")
                    return
            except sqlite3.OperationalError as error:
                code = getattr(error, "sqlite_errorcode", None)
                remaining = deadline - time.monotonic()
                if code is None or code & 0xFF != sqlite3.SQLITE_BUSY or remaining <= 0:
                    raise
                time.sleep(min(0.05, remaining))

    @staticmethod
    def _apply_migration(connection, script):
        # executescript can commit a pending transaction. Execute each complete
        # checked-in statement instead, retaining the constructor's write lock.
        statement = ""
        for line in script.splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                connection.execute(statement)
                statement = ""
        if statement.strip():
            raise ValueError("Incomplete migration statement")

    @staticmethod
    def _freeze_legacy_admissions(connection):
        existing = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='legacy_task_admissions'").fetchone()
        if existing:
            # Repair the previous race's stale version marker, retaining the
            # original cutoff. Never grant admission to rows added afterwards.
            connection.execute("SELECT organization,run_id,request_hash FROM legacy_task_admissions LIMIT 0")
        else:
            connection.execute("""CREATE TABLE legacy_task_admissions (
                organization TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES runs(id),
                request_hash TEXT NOT NULL, PRIMARY KEY(organization,run_id))""")
            for run in connection.execute("SELECT * FROM runs").fetchall():
                if stored_plan_hash(connection, run["id"]) == run["request_hash"]:
                    connection.execute("INSERT INTO legacy_task_admissions VALUES(?,?,?)",
                                       (run["organization"], run["id"], run["request_hash"]))
        connection.execute("PRAGMA user_version=3")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise


def stored_plan_hash(connection, run_id: str) -> str | None:
    try:
        specs = [{"capability": row["capability"], "inputs": json.loads(row["inputs"]), "max_attempts": row["max_attempts"]}
                 for row in connection.execute("SELECT * FROM tasks WHERE run_id=? ORDER BY position", (run_id,))]
        return digest(specs) if specs else None
    except (ValueError, TypeError):
        return None
