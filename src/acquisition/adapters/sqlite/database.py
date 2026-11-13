import sqlite3
from contextlib import contextmanager
from pathlib import Path
import json
import time

from acquisition.contracts import Conflict, digest
from acquisition.local_root import inspection_only, require_live_root


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


ADMISSION_CUTOVER = """
CREATE TABLE execution_admissions_deferred (
 organization TEXT NOT NULL, id TEXT NOT NULL, request_id TEXT NOT NULL,
 run_id TEXT NOT NULL REFERENCES runs(id) DEFERRABLE INITIALLY DEFERRED,
 payload TEXT NOT NULL, fingerprint TEXT NOT NULL, receipt TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status='paused'),
 PRIMARY KEY(organization,id), UNIQUE(organization,request_id), UNIQUE(organization,run_id),
 FOREIGN KEY(organization,request_id) REFERENCES admission_requests(organization,request_id));
INSERT INTO execution_admissions_deferred SELECT * FROM execution_admissions;
DROP TABLE execution_admissions;
ALTER TABLE execution_admissions_deferred RENAME TO execution_admissions;
CREATE TRIGGER execution_admissions_no_update BEFORE UPDATE ON execution_admissions
 BEGIN SELECT RAISE(ABORT,'Execution admissions are immutable'); END;
CREATE TRIGGER execution_admissions_no_delete BEFORE DELETE ON execution_admissions
 BEGIN SELECT RAISE(ABORT,'Execution admissions are immutable'); END;
CREATE TABLE IF NOT EXISTS admission_store_policy (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 policy TEXT NOT NULL CHECK(policy='verified-paused/v1'), created_at REAL NOT NULL);
CREATE TRIGGER IF NOT EXISTS admission_policy_no_update BEFORE UPDATE ON admission_store_policy
 BEGIN SELECT RAISE(ABORT,'Admission cutover cannot be downgraded'); END;
CREATE TRIGGER IF NOT EXISTS admission_policy_no_delete BEFORE DELETE ON admission_store_policy
 BEGIN SELECT RAISE(ABORT,'Admission cutover cannot be downgraded'); END;
CREATE TRIGGER verified_run_insert BEFORE INSERT ON runs
 WHEN EXISTS(SELECT 1 FROM admission_store_policy)
 BEGIN SELECT RAISE(ABORT,'Verified admission must precede runtime creation') WHERE NOT EXISTS(
  SELECT 1 FROM execution_admissions a JOIN admission_requests q
   ON q.organization=a.organization AND q.request_id=a.request_id
  WHERE a.organization=NEW.organization AND a.run_id=NEW.id AND a.payload=q.payload
   AND a.fingerprint=q.fingerprint
   AND json_extract(a.payload,'$.tasks[0].inputs.run_request_id')=NEW.request_id); END;
CREATE TRIGGER verified_task_insert BEFORE INSERT ON tasks
 WHEN EXISTS(SELECT 1 FROM admission_store_policy)
 BEGIN SELECT RAISE(ABORT,'Task differs from its verified admission') WHERE NOT EXISTS(
  SELECT 1 FROM execution_admissions a JOIN runs r ON r.id=a.run_id AND r.organization=a.organization
  WHERE a.run_id=NEW.run_id
   AND json_extract(a.payload,'$.tasks['||NEW.position||'].capability')=NEW.capability
   AND json_extract(a.payload,'$.tasks['||NEW.position||'].max_attempts')=NEW.max_attempts
   AND json_extract(a.payload,'$.tasks['||NEW.position||'].inputs')=json(NEW.inputs)); END;
CREATE TRIGGER verified_task_effect BEFORE UPDATE OF status ON tasks
 WHEN EXISTS(SELECT 1 FROM admission_store_policy) AND NEW.status IN ('running','succeeded','waiting','failed')
 BEGIN SELECT RAISE(ABORT,'Verified admission execution remains paused'); END;
CREATE TRIGGER verified_inference_insert BEFORE INSERT ON model_calls
 WHEN EXISTS(SELECT 1 FROM admission_store_policy)
 BEGIN SELECT RAISE(ABORT,'Verified admission inference remains paused'); END;
PRAGMA user_version=13;
"""


WORKSPACE_AUTHORITY = """
CREATE TABLE IF NOT EXISTS application_store_identity(singleton INTEGER PRIMARY KEY CHECK(singleton=1),id TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS application_identity_no_update BEFORE UPDATE ON application_store_identity
 BEGIN SELECT RAISE(ABORT,'Application store identity is immutable'); END;
CREATE TRIGGER IF NOT EXISTS application_identity_no_delete BEFORE DELETE ON application_store_identity
 BEGIN SELECT RAISE(ABORT,'Application store identity is immutable'); END;
CREATE TABLE IF NOT EXISTS workspace_locations(
 organization TEXT NOT NULL,id TEXT NOT NULL,run_organization TEXT NOT NULL,store_scope TEXT NOT NULL,
 store_key TEXT NOT NULL,store_identity TEXT NOT NULL,PRIMARY KEY(organization,id));
CREATE TRIGGER IF NOT EXISTS workspace_location_no_update BEFORE UPDATE ON workspace_locations
 BEGIN SELECT RAISE(ABORT,'Sandbox location is immutable'); END;
CREATE TRIGGER IF NOT EXISTS workspace_location_no_delete BEFORE DELETE ON workspace_locations
 BEGIN SELECT RAISE(ABORT,'Sandbox location is immutable'); END;
CREATE TABLE IF NOT EXISTS campaign_environments(
 organization TEXT NOT NULL,id TEXT NOT NULL,intent TEXT NOT NULL,fingerprint TEXT NOT NULL,
 epoch INTEGER NOT NULL,clock REAL NOT NULL CHECK(clock>=0 AND clock<253402300800),
 clock_mode TEXT NOT NULL CHECK(clock_mode IN('REAL','SIMULATED')),run_id TEXT,case_id TEXT,cohort_id TEXT,
 PRIMARY KEY(organization,id),FOREIGN KEY(run_id) REFERENCES runs(id));
CREATE TRIGGER IF NOT EXISTS environment_intent_no_update BEFORE UPDATE OF organization,id,intent,fingerprint ON campaign_environments
 BEGIN SELECT RAISE(ABORT,'Sandbox intent is immutable'); END;
CREATE TRIGGER IF NOT EXISTS environment_time_monotonic BEFORE UPDATE OF clock,clock_mode ON campaign_environments
 WHEN NEW.clock<OLD.clock OR (OLD.clock_mode='SIMULATED' AND NEW.clock_mode!='SIMULATED')
 BEGIN SELECT RAISE(ABORT,'Sandbox time cannot be reset'); END;
CREATE TRIGGER IF NOT EXISTS environment_no_delete BEFORE DELETE ON campaign_environments
 BEGIN SELECT RAISE(ABORT,'Sandbox intent is immutable'); END;
CREATE TABLE IF NOT EXISTS workspace_requests(
 organization TEXT NOT NULL,scope TEXT NOT NULL,request_id TEXT NOT NULL,kind TEXT NOT NULL,
 inputs TEXT NOT NULL,environment_organization TEXT NOT NULL,environment_id TEXT NOT NULL,
 PRIMARY KEY(organization,scope,request_id),
 FOREIGN KEY(environment_organization,environment_id) REFERENCES campaign_environments(organization,id));
CREATE TRIGGER IF NOT EXISTS workspace_request_no_update BEFORE UPDATE ON workspace_requests
 BEGIN SELECT RAISE(ABORT,'Workspace request intent is immutable'); END;
CREATE TRIGGER IF NOT EXISTS workspace_request_no_delete BEFORE DELETE ON workspace_requests
 BEGIN SELECT RAISE(ABORT,'Workspace request intent is immutable'); END;
CREATE TABLE IF NOT EXISTS workspace_commands(
 organization TEXT NOT NULL,environment_id TEXT NOT NULL,request_id TEXT NOT NULL,
 inputs TEXT NOT NULL,done INTEGER NOT NULL CHECK(done IN(0,1)),
 PRIMARY KEY(organization,environment_id,request_id),
 FOREIGN KEY(organization,environment_id) REFERENCES campaign_environments(organization,id));
CREATE TRIGGER IF NOT EXISTS workspace_command_no_rebind BEFORE UPDATE OF organization,environment_id,request_id,inputs ON workspace_commands
 BEGIN SELECT RAISE(ABORT,'Workspace command inputs are immutable'); END;
CREATE TRIGGER IF NOT EXISTS workspace_command_no_reopen BEFORE UPDATE OF done ON workspace_commands
 WHEN OLD.done=1 AND NEW.done!=1 BEGIN SELECT RAISE(ABORT,'Completed workspace command cannot reopen'); END;
CREATE TRIGGER IF NOT EXISTS workspace_command_no_delete BEFORE DELETE ON workspace_commands
 BEGIN SELECT RAISE(ABORT,'Workspace command inputs are immutable'); END;
CREATE TABLE IF NOT EXISTS workflow_preparations(
 organization TEXT NOT NULL,id TEXT NOT NULL,request_id TEXT NOT NULL,conversation_id TEXT NOT NULL,
 revision INTEGER NOT NULL,intent TEXT NOT NULL,fingerprint TEXT NOT NULL,epoch INTEGER NOT NULL,progress TEXT NOT NULL,
 PRIMARY KEY(organization,id),UNIQUE(organization,request_id),UNIQUE(organization,conversation_id,revision),
 FOREIGN KEY(organization,conversation_id) REFERENCES conversations(organization,id));
CREATE TRIGGER IF NOT EXISTS preparation_intent_no_update BEFORE UPDATE OF organization,id,request_id,conversation_id,revision,intent,fingerprint ON workflow_preparations
 BEGIN SELECT RAISE(ABORT,'Preparation intent is immutable'); END;
CREATE TRIGGER IF NOT EXISTS preparation_no_delete BEFORE DELETE ON workflow_preparations
 BEGIN SELECT RAISE(ABORT,'Preparation intent is immutable'); END;
PRAGMA user_version=14;
"""


WRITING_PREFERENCE_INSERT_GUARD = """
CREATE TRIGGER IF NOT EXISTS writing_preference_no_replace BEFORE INSERT ON writing_preference_versions
 WHEN EXISTS(SELECT 1 FROM writing_preference_versions WHERE organization=NEW.organization
   AND ((id=NEW.id AND revision=NEW.revision) OR request_id=NEW.request_id))
 BEGIN SELECT RAISE(ABORT,'Writing preference history is immutable'); END;
"""


WRITING_PREFERENCES = """
CREATE TABLE IF NOT EXISTS writing_preference_versions (
 organization TEXT NOT NULL,id TEXT NOT NULL,revision INTEGER NOT NULL,
 request_id TEXT NOT NULL,fingerprint TEXT NOT NULL,payload TEXT NOT NULL,
 PRIMARY KEY(organization,id,revision),UNIQUE(organization,request_id));
CREATE TRIGGER IF NOT EXISTS writing_preference_no_update BEFORE UPDATE ON writing_preference_versions
 BEGIN SELECT RAISE(ABORT,'Writing preference history is immutable'); END;
CREATE TRIGGER IF NOT EXISTS writing_preference_no_delete BEFORE DELETE ON writing_preference_versions
 BEGIN SELECT RAISE(ABORT,'Writing preference history is immutable'); END;
""" + WRITING_PREFERENCE_INSERT_GUARD + "PRAGMA user_version=15;"

SIMULATED_DELIVERY = """
CREATE TABLE IF NOT EXISTS simulated_deliveries (
 organization TEXT NOT NULL, case_id TEXT NOT NULL, approval_id TEXT NOT NULL,
 id TEXT NOT NULL, simulation TEXT NOT NULL, binding TEXT NOT NULL, provider_draft TEXT NOT NULL,
 result TEXT, result_hash TEXT, CHECK((result IS NULL) = (result_hash IS NULL)),
 PRIMARY KEY(organization,case_id,approval_id), UNIQUE(organization,id),
 FOREIGN KEY(organization,case_id) REFERENCES review_cases(organization,id),
 FOREIGN KEY(organization,approval_id) REFERENCES review_decisions(organization,id));
CREATE TRIGGER IF NOT EXISTS simulated_delivery_no_replace BEFORE INSERT ON simulated_deliveries
 WHEN EXISTS(SELECT 1 FROM simulated_deliveries WHERE organization=NEW.organization
  AND (id=NEW.id OR (case_id=NEW.case_id AND approval_id=NEW.approval_id)))
 BEGIN SELECT RAISE(ABORT,'Simulated delivery already exists'); END;
CREATE TRIGGER IF NOT EXISTS simulated_delivery_preserve_binding BEFORE UPDATE ON simulated_deliveries
 WHEN OLD.result IS NOT NULL OR NEW.organization<>OLD.organization OR NEW.case_id<>OLD.case_id
  OR NEW.approval_id<>OLD.approval_id OR NEW.id<>OLD.id OR NEW.simulation<>OLD.simulation OR NEW.binding<>OLD.binding
 BEGIN SELECT RAISE(ABORT,'Simulated delivery identity and results are immutable'); END;
CREATE TRIGGER IF NOT EXISTS simulated_delivery_no_delete BEFORE DELETE ON simulated_deliveries
 BEGIN SELECT RAISE(ABORT,'Simulated delivery history is immutable'); END;
PRAGMA user_version=16;
"""

REPORT_MONITORING = """
CREATE TABLE IF NOT EXISTS report_monitoring (
 organization TEXT NOT NULL, cohort_id TEXT NOT NULL, actor TEXT NOT NULL,
 interval_seconds INTEGER NOT NULL, first_check REAL NOT NULL, revision INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('scheduled','paused','blocked','complete')),
 position INTEGER NOT NULL, report_count INTEGER NOT NULL, next_due REAL,
 last_checked REAL, last_report_id TEXT, watermark REAL, detail TEXT,
 lease_token TEXT, lease_until REAL, CHECK((lease_token IS NULL) = (lease_until IS NULL)),
 PRIMARY KEY(organization,cohort_id),
 FOREIGN KEY(organization,cohort_id) REFERENCES learning_cohorts(organization,id));
CREATE TABLE IF NOT EXISTS report_monitoring_sources (
 organization TEXT NOT NULL, cohort_id TEXT NOT NULL, position INTEGER NOT NULL,
 available_at REAL NOT NULL, report_sha256 TEXT NOT NULL, snapshot TEXT NOT NULL,
 PRIMARY KEY(organization,cohort_id,position),
 FOREIGN KEY(organization,cohort_id) REFERENCES report_monitoring(organization,cohort_id));
PRAGMA user_version=17;
"""


class Database:
    def __init__(self, path: str | Path, *, verified_admissions=False, clock=time.time, fixture_execution=False):
        if type(verified_admissions) is not bool:
            raise ValueError('Choose an explicit admission mode')
        if type(fixture_execution) is not bool or (fixture_execution and not verified_admissions):
            raise ValueError('Fixture execution requires an explicit verified workspace initialization')
        self.path = Path(path)
        if inspection_only(self.path):
            if verified_admissions:
                require_live_root(self.path)
            with self.connect() as connection:
                version = connection.execute('PRAGMA user_version').fetchone()[0]
                if version not in {14, 15, 16, 17, 18}:
                    raise ValueError('Unsupported application schema for checkpoint inspection')
                self._validate_workspace_schema(connection)
                if version >= 17:
                    self._validate_report_monitoring_schema(connection)
                if version >= 18:
                    self._validate_contact_schema(connection)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as connection:
            # Version discovery and every migration share one SQLite write lock.
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if fixture_execution and (version != 0 or connection.execute('SELECT 1 FROM sqlite_schema LIMIT 1').fetchone()):
                raise Conflict('Fixture execution requires a fresh application store')
            if not 0 <= version <= 18:
                raise ValueError(f"Unsupported database schema {version}")
            if (verified_admissions and version < 10
                    and connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='runs'").fetchone()
                    and connection.execute('SELECT 1 FROM runs LIMIT 1').fetchone()):
                raise Conflict('Reconcile historical execution ancestry before cutting over a pre-v10 store')
            if version<13:
                # Partially newer fixtures/restores may contain guards referencing
                # tables that an older migration rebuilds. Remove and recreate
                # them under this same lock; rollback restores the original set.
                for name in ('verified_run_insert','verified_task_insert','verified_task_effect','verified_inference_insert'):
                    connection.execute('DROP TRIGGER IF EXISTS '+name)
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
                first_accounting = connection.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
                    AND name IN ('conversation_execution','execution_runs','execution_commands')""").fetchone() is None
                self._apply_migration(connection, EXECUTION)
                self._initialize_execution_schema(connection, first_accounting=first_accounting)
            if version < 10:
                self._apply_migration(connection, EXECUTION_RECOVERY)
                self._initialize_execution_recovery_schema(connection)
            elif verified_admissions:
                from .execution import quarantine_weak_independence_receipts
                quarantine_weak_independence_receipts(connection)
            else:
                from .execution import recover_pending_origins
                recover_pending_origins(connection)
            if version < 11:
                self._apply_migration(connection, ATOMIC_ADMISSIONS)
                self._validate_admission_schema(connection)
            if version < 12:
                self._apply_migration(connection, WORKFLOW_ADMISSIONS)
                self._validate_admission_schema(connection)
            if version < 13:
                self._apply_migration(connection, ADMISSION_CUTOVER)
            if version < 14:
                self._initialize_workspace_schema(connection)
            else:self._validate_workspace_schema(connection)
            if version < 15:
                self._apply_migration(connection, WRITING_PREFERENCES)
            else:
                self._apply_migration(connection, WRITING_PREFERENCE_INSERT_GUARD)
            self._validate_writing_preference_schema(connection)
            if version < 16:
                self._apply_migration(connection, SIMULATED_DELIVERY)
            self._validate_simulated_delivery_schema(connection)
            if version < 17:
                self._apply_migration(connection, REPORT_MONITORING)
            self._validate_report_monitoring_schema(connection)
            if version < 18:
                from .contacts import CONTACT_DIRECTORY
                self._apply_migration(connection, CONTACT_DIRECTORY)
            self._validate_contact_schema(connection)
            if verified_admissions:
                # Seal under the same write lock that skipped legacy recovery.
                from .admission_guard import seal_legacy_writes
                seal_legacy_writes(connection, clock)
            if fixture_execution:
                from .fixture_execution import install_fixture_execution
                install_fixture_execution(connection, clock())
        self._enable_wal()

    @staticmethod
    def _validate_contact_schema(connection):
        from .contacts import validate_contact_schema
        validate_contact_schema(connection)

    @staticmethod
    def _validate_writing_preference_schema(connection):
        connection.execute('SELECT organization,id,revision,request_id,fingerprint,payload FROM writing_preference_versions LIMIT 0')

    @staticmethod
    def _validate_simulated_delivery_schema(connection):
        connection.execute('SELECT organization,case_id,approval_id,id,simulation,binding,provider_draft,result,result_hash FROM simulated_deliveries LIMIT 0')

    @staticmethod
    def _validate_report_monitoring_schema(connection):
        connection.execute('SELECT organization,cohort_id,position,report_count,next_due,lease_token,lease_until FROM report_monitoring LIMIT 0')
        connection.execute('SELECT organization,cohort_id,position,available_at,report_sha256,snapshot FROM report_monitoring_sources LIMIT 0')

    @classmethod
    def _initialize_workspace_schema(cls,connection):
        from uuid import uuid4
        cls._apply_migration(connection,WORKSPACE_AUTHORITY)
        connection.execute('INSERT OR IGNORE INTO application_store_identity VALUES(1,?)',('store_'+uuid4().hex,))
        cls._validate_workspace_schema(connection)

    @staticmethod
    def _validate_workspace_schema(connection):
        if connection.execute('SELECT id FROM application_store_identity WHERE singleton=1').fetchone() is None:
            raise ValueError('Application store identity is unavailable')

    @classmethod
    def existing(cls,path):
        """Open a known current store without migration or a nested write lock."""
        database=cls.__new__(cls);database.path=Path(path)
        if not database.path.is_file():raise ValueError('Authoritative application store is unavailable')
        with database.connect() as db:
            if db.execute('PRAGMA user_version').fetchone()[0] not in {14, 15, 16, 17, 18}:
                raise ValueError('Migrate the authoritative application store before workspace access')
        return database

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
    def _initialize_execution_schema(connection, *, first_accounting):
        connection.execute('SELECT organization,conversation_id,policy,call_limit,stopped_through FROM conversation_execution LIMIT 0')
        connection.execute('SELECT organization,run_id,owner_organization,conversation_id,revision FROM execution_runs LIMIT 0')
        connection.execute('SELECT organization,request_id,inputs,receipt FROM execution_commands LIMIT 0')
        from .execution import backfill_execution
        backfill_execution(connection, first_accounting=first_accounting)

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
        checkpoint = inspection_only(self.path)
        source = self.path.resolve().as_uri() + '?mode=ro&immutable=1' if checkpoint else self.path
        if checkpoint and not self.path.is_file():
            raise Conflict('This store is absent from the inspection-only checkpoint')
        connection = sqlite3.connect(source, uri=checkpoint, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self):
        require_live_root(self.path)
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
