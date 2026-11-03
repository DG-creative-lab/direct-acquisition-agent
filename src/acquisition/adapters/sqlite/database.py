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


CONVERSATIONS = """
CREATE TABLE IF NOT EXISTS conversations (
 organization TEXT NOT NULL, id TEXT NOT NULL, request_id TEXT NOT NULL, title TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL,
 PRIMARY KEY(organization,id), UNIQUE(organization,request_id));
CREATE TABLE IF NOT EXISTS conversation_messages (
 organization TEXT NOT NULL, conversation_id TEXT NOT NULL, request_id TEXT NOT NULL,
 revision INTEGER NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL,
 PRIMARY KEY(organization,conversation_id,request_id), UNIQUE(organization,conversation_id,revision),
 FOREIGN KEY(organization,conversation_id) REFERENCES conversations(organization,id));
CREATE TABLE IF NOT EXISTS conversation_plans (
 organization TEXT NOT NULL, conversation_id TEXT NOT NULL, request_id TEXT NOT NULL,
 revision INTEGER NOT NULL, payload TEXT NOT NULL, created_at REAL NOT NULL,
 PRIMARY KEY(organization,conversation_id,request_id), UNIQUE(organization,conversation_id,revision),
 FOREIGN KEY(organization,conversation_id) REFERENCES conversations(organization,id));
PRAGMA user_version=6;
"""


AUDIENCE_SELECTIONS = """
CREATE TABLE IF NOT EXISTS conversation_audiences (
 organization TEXT NOT NULL, conversation_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,conversation_id,revision),
 FOREIGN KEY(organization,conversation_id) REFERENCES conversations(organization,id));
CREATE TABLE IF NOT EXISTS audience_selection_requests (
 organization TEXT NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(organization,request_id));
PRAGMA user_version=7;
"""


CONVERSATION_ACTIONS = """
CREATE TABLE IF NOT EXISTS conversation_actions (
 organization TEXT NOT NULL, id TEXT NOT NULL, conversation_id TEXT NOT NULL, request_id TEXT NOT NULL,
 revision INTEGER NOT NULL, payload TEXT NOT NULL, confirmed TEXT, created_at REAL NOT NULL,
 PRIMARY KEY(organization,id), UNIQUE(organization,conversation_id,request_id),
 FOREIGN KEY(organization,conversation_id) REFERENCES conversations(organization,id));
CREATE TABLE IF NOT EXISTS conversation_action_commands (
 organization TEXT NOT NULL, request_id TEXT NOT NULL, inputs TEXT NOT NULL, receipt TEXT NOT NULL,
 PRIMARY KEY(organization,request_id));
PRAGMA user_version=8;
"""


EXECUTION = """
CREATE TABLE IF NOT EXISTS conversation_execution (
 organization TEXT NOT NULL, conversation_id TEXT NOT NULL, policy TEXT NOT NULL,
 call_limit INTEGER NOT NULL CHECK(call_limit>0), stopped_through INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(organization,conversation_id),
 FOREIGN KEY(organization,conversation_id) REFERENCES conversations(organization,id));
CREATE TABLE IF NOT EXISTS execution_runs (
 organization TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES runs(id), owner_organization TEXT NOT NULL,
 conversation_id TEXT NOT NULL, revision INTEGER NOT NULL,
 PRIMARY KEY(organization,run_id),
 FOREIGN KEY(owner_organization,conversation_id) REFERENCES conversation_execution(organization,conversation_id));
CREATE TABLE IF NOT EXISTS execution_commands (
 organization TEXT NOT NULL, request_id TEXT NOT NULL, inputs TEXT NOT NULL, receipt TEXT NOT NULL,
 PRIMARY KEY(organization,request_id));
PRAGMA user_version=9;
"""


EXECUTION_RECOVERY = """
CREATE TABLE IF NOT EXISTS execution_pending_origins (
 organization TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES runs(id),
 PRIMARY KEY(organization,run_id));
PRAGMA user_version=10;
"""


ATOMIC_ADMISSIONS = """
CREATE TABLE IF NOT EXISTS admission_requests (
 organization TEXT NOT NULL, request_id TEXT NOT NULL, inputs TEXT NOT NULL,
 payload TEXT NOT NULL, fingerprint TEXT NOT NULL, source TEXT NOT NULL,
 consent TEXT NOT NULL, created_at REAL NOT NULL,
 conversation_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
 PRIMARY KEY(organization,request_id), UNIQUE(organization,conversation_id,revision),
 FOREIGN KEY(organization,conversation_id) REFERENCES conversations(organization,id));
CREATE TABLE IF NOT EXISTS execution_admissions (
 organization TEXT NOT NULL, id TEXT NOT NULL, request_id TEXT NOT NULL,
 run_id TEXT NOT NULL REFERENCES runs(id), payload TEXT NOT NULL,
 fingerprint TEXT NOT NULL, receipt TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status='paused'),
 PRIMARY KEY(organization,id), UNIQUE(organization,request_id), UNIQUE(organization,run_id),
 FOREIGN KEY(organization,request_id) REFERENCES admission_requests(organization,request_id));
CREATE TRIGGER IF NOT EXISTS admission_requests_no_update BEFORE UPDATE ON admission_requests
 BEGIN SELECT RAISE(ABORT,'Admission requests are immutable'); END;
CREATE TRIGGER IF NOT EXISTS admission_requests_no_delete BEFORE DELETE ON admission_requests
 BEGIN SELECT RAISE(ABORT,'Admission requests are immutable'); END;
CREATE TRIGGER IF NOT EXISTS execution_admissions_no_update BEFORE UPDATE ON execution_admissions
 BEGIN SELECT RAISE(ABORT,'Execution admissions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS execution_admissions_no_delete BEFORE DELETE ON execution_admissions
 BEGIN SELECT RAISE(ABORT,'Execution admissions are immutable'); END;
PRAGMA user_version=11;
"""


WORKFLOW_ADMISSIONS = """
CREATE TABLE admission_requests_next (
 organization TEXT NOT NULL, request_id TEXT NOT NULL, inputs TEXT NOT NULL,
 payload TEXT NOT NULL, fingerprint TEXT NOT NULL, source TEXT NOT NULL,
 consent TEXT NOT NULL, created_at REAL NOT NULL,
 conversation_id TEXT, revision INTEGER CHECK(revision>0),
 CHECK((conversation_id IS NULL)=(revision IS NULL)),
 PRIMARY KEY(organization,request_id), UNIQUE(organization,conversation_id,revision),
 FOREIGN KEY(organization,conversation_id) REFERENCES conversations(organization,id));
INSERT INTO admission_requests_next SELECT * FROM admission_requests;
CREATE TABLE execution_admissions_next (
 organization TEXT NOT NULL, id TEXT NOT NULL, request_id TEXT NOT NULL,
 run_id TEXT NOT NULL REFERENCES runs(id), payload TEXT NOT NULL,
 fingerprint TEXT NOT NULL, receipt TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status='paused'),
 PRIMARY KEY(organization,id), UNIQUE(organization,request_id), UNIQUE(organization,run_id),
 FOREIGN KEY(organization,request_id) REFERENCES admission_requests_next(organization,request_id));
INSERT INTO execution_admissions_next SELECT * FROM execution_admissions;
DROP TABLE execution_admissions;
DROP TABLE admission_requests;
ALTER TABLE admission_requests_next RENAME TO admission_requests;
ALTER TABLE execution_admissions_next RENAME TO execution_admissions;
CREATE UNIQUE INDEX admission_operation ON admission_requests(organization,json_extract(inputs,'$.operation_key'));
CREATE UNIQUE INDEX admission_runtime_key ON admission_requests(organization,json_extract(payload,'$.tasks[0].inputs.run_request_id'));
CREATE TRIGGER admission_requests_no_update BEFORE UPDATE ON admission_requests
 BEGIN SELECT RAISE(ABORT,'Admission requests are immutable'); END;
CREATE TRIGGER admission_requests_no_delete BEFORE DELETE ON admission_requests
 BEGIN SELECT RAISE(ABORT,'Admission requests are immutable'); END;
CREATE TRIGGER execution_admissions_no_update BEFORE UPDATE ON execution_admissions
 BEGIN SELECT RAISE(ABORT,'Execution admissions are immutable'); END;
CREATE TRIGGER execution_admissions_no_delete BEFORE DELETE ON execution_admissions
 BEGIN SELECT RAISE(ABORT,'Execution admissions are immutable'); END;
PRAGMA user_version=12;
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as connection:
            # Version discovery and every migration share one SQLite write lock.
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}:
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
            if version < 6:
                self._apply_migration(connection, CONVERSATIONS)
                self._validate_conversation_schema(connection)
            if version < 7:
                self._apply_migration(connection, AUDIENCE_SELECTIONS)
                self._validate_audience_selection_schema(connection)
            if version < 8:
                self._apply_migration(connection, CONVERSATION_ACTIONS)
                self._validate_action_schema(connection)
            if version < 9:
                self._apply_migration(connection, EXECUTION)
                self._initialize_execution_schema(connection)
            if version < 10:
                self._apply_migration(connection, EXECUTION_RECOVERY)
                self._initialize_execution_recovery_schema(connection)
            else:
                from .execution import recover_pending_origins
                recover_pending_origins(connection)
            if version < 11:
                self._apply_migration(connection, ATOMIC_ADMISSIONS)
                self._validate_admission_schema(connection)
            if version < 12:
                self._apply_migration(connection, WORKFLOW_ADMISSIONS)
                self._validate_admission_schema(connection)
        self._enable_wal()

    @staticmethod
    def _validate_admission_schema(connection):
        connection.execute('SELECT organization,request_id,inputs,payload,fingerprint,source,consent,created_at,conversation_id,revision FROM admission_requests LIMIT 0')
        connection.execute('SELECT organization,id,request_id,run_id,payload,fingerprint,receipt,status FROM execution_admissions LIMIT 0')

    @staticmethod
    def _initialize_execution_recovery_schema(connection):
        connection.execute('SELECT organization,run_id FROM execution_pending_origins LIMIT 0')
        from .execution import quarantine_old_origins
        quarantine_old_origins(connection)

    @staticmethod
    def _initialize_execution_schema(connection):
        connection.execute('SELECT organization,conversation_id,policy,call_limit,stopped_through FROM conversation_execution LIMIT 0')
        connection.execute('SELECT organization,run_id,owner_organization,conversation_id,revision FROM execution_runs LIMIT 0')
        connection.execute('SELECT organization,request_id,inputs,receipt FROM execution_commands LIMIT 0')
        from .execution import backfill_execution
        backfill_execution(connection)

    @staticmethod
    def _validate_action_schema(connection):
        connection.execute("SELECT organization,id,conversation_id,request_id,revision,payload,confirmed,created_at FROM conversation_actions LIMIT 0")
        connection.execute("SELECT organization,request_id,inputs,receipt FROM conversation_action_commands LIMIT 0")

    @staticmethod
    def _validate_audience_selection_schema(connection):
        connection.execute("SELECT organization,conversation_id,revision,payload FROM conversation_audiences LIMIT 0")
        connection.execute("SELECT organization,request_id,payload FROM audience_selection_requests LIMIT 0")

    @staticmethod
    def _validate_conversation_schema(connection):
        # A stale version marker can leave already-created tables in place.
        # Verify their shape before committing the version change.
        connection.execute("SELECT organization,id,request_id,title,revision,created_at FROM conversations LIMIT 0")
        connection.execute("SELECT organization,conversation_id,request_id,revision,content,created_at FROM conversation_messages LIMIT 0")
        connection.execute("SELECT organization,conversation_id,request_id,revision,payload,created_at FROM conversation_plans LIMIT 0")

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
