"""Opt-in fixture execution in a fresh local conversation store."""
import math

from acquisition.conversations import FIXTURE_CAPABILITY
from acquisition.runtime import LeaseLost

from .admission_guard import binding
from .execution import account_evidence

POLICY = 'verified-fixture-execution/v1'
OWNER = 'local-conversations'
FIXTURE_PLANS = {
    'conversation-fixture-planning/v1': (FIXTURE_CAPABILITY,),
    'conversation-campaign-admission/v1': (
        'audiences.inspect_conversation.v1', 'campaigns.build_conversation.v1', 'campaigns.review_conversation.v1',
    ),
}
DRAFT_CAPABILITIES = frozenset(FIXTURE_PLANS['conversation-campaign-admission/v1'][1:])


def require_fixture_deadline(deadline: float, now: float) -> None:
    if not math.isfinite(now) or deadline <= now:
        raise LeaseLost('Fixture task lease expired or execution clock is invalid')


# The SQL fence also protects the store when a cached writer reaches SQLite
# without running the current Python checks. Paid reservations keep the
# original independent verified_inference_insert trigger.
def install_fixture_execution(db, now):
    from .database import Database
    from .tasks import finite_time

    finite_time(now)
    sequences = []
    for workflow, capabilities in FIXTURE_PLANS.items():
        checks = [f"json_extract(a.payload,'$.workflow_version')='{workflow}'",
                  f"json_array_length(a.payload,'$.tasks')={len(capabilities)}"]
        checks.extend(f"json_extract(a.payload,'$.tasks[{index}].capability')='{name}'"
                      for index, name in enumerate(capabilities))
        if workflow == 'conversation-fixture-planning/v1':
            checks.append(f"a.organization='{OWNER}'")
        sequences.append('(' + ' AND '.join(checks) + ')')
    permitted = ' OR '.join(sequences)
    Database._apply_migration(db, f"""
CREATE TABLE fixture_execution_policy (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 policy TEXT NOT NULL CHECK(policy='{POLICY}'), created_at REAL NOT NULL);
CREATE TRIGGER fixture_policy_no_update BEFORE UPDATE ON fixture_execution_policy
 BEGIN SELECT RAISE(ABORT,'Fixture execution policy is immutable'); END;
CREATE TRIGGER fixture_policy_no_delete BEFORE DELETE ON fixture_execution_policy
 BEGIN SELECT RAISE(ABORT,'Fixture execution policy is immutable'); END;
CREATE TRIGGER fixture_policy_no_replace BEFORE INSERT ON fixture_execution_policy
 WHEN EXISTS(SELECT 1 FROM fixture_execution_policy)
 BEGIN SELECT RAISE(ABORT,'Fixture execution policy is immutable'); END;
CREATE TABLE fixture_execution_grants (
 organization TEXT NOT NULL, run_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
 PRIMARY KEY(organization,run_id),
 FOREIGN KEY(organization,run_id) REFERENCES execution_admissions(organization,run_id));
CREATE TRIGGER fixture_grant_no_update BEFORE UPDATE ON fixture_execution_grants
 BEGIN SELECT RAISE(ABORT,'Fixture execution grant is immutable'); END;
CREATE TRIGGER fixture_grant_no_delete BEFORE DELETE ON fixture_execution_grants
 BEGIN SELECT RAISE(ABORT,'Fixture execution grant is immutable'); END;
CREATE TRIGGER fixture_grant_no_replace BEFORE INSERT ON fixture_execution_grants
 WHEN EXISTS(SELECT 1 FROM fixture_execution_grants WHERE organization=NEW.organization AND run_id=NEW.run_id)
 BEGIN SELECT RAISE(ABORT,'Fixture execution grant is immutable'); END;
DROP TRIGGER verified_task_effect;
CREATE TRIGGER verified_task_effect BEFORE UPDATE OF status,attempts,token,lease_until,output,resume,available_at ON tasks
 WHEN NEW.status IN ('queued','running','succeeded','waiting','failed')
 BEGIN SELECT RAISE(ABORT,'Task lacks current fixture execution authority') WHERE NOT EXISTS(
  SELECT 1 FROM fixture_execution_policy f JOIN admission_store_policy p ON p.singleton=1
   JOIN fixture_execution_grants g ON g.run_id=OLD.run_id
   JOIN execution_admissions a ON a.organization=g.organization AND a.run_id=g.run_id AND a.fingerprint=g.fingerprint
   JOIN admission_requests q ON q.organization=a.organization AND q.request_id=a.request_id
      AND q.fingerprint=a.fingerprint AND q.payload=a.payload
   JOIN execution_runs e ON e.organization=a.organization AND e.run_id=a.run_id
   JOIN conversations c ON c.organization=e.owner_organization AND c.id=e.conversation_id
   JOIN conversation_execution x ON x.organization=c.organization AND x.conversation_id=c.id
   WHERE f.singleton=1 AND f.policy='{POLICY}' AND p.policy='verified-paused/v1'
     AND json_type(a.payload,'$.model_config')='null' AND json_type(a.payload,'$.consent_id')='null'
     AND json_type(q.consent,'$.allow_model')='false'
     AND e.owner_organization='{OWNER}' AND e.revision=c.revision AND e.revision>x.stopped_through
     AND json_extract(a.payload,'$.ownership.kind')='conversation'
     AND json_type(a.payload,'$.parent_run_id')='null'
     AND json_extract(a.payload,'$.ownership.organization')=e.owner_organization
     AND json_extract(a.payload,'$.ownership.scope_id')=e.conversation_id
     AND json_extract(a.payload,'$.ownership.revision')=e.revision
     AND ({permitted})
     AND NEW.run_id=OLD.run_id AND NEW.position=OLD.position
     AND NEW.capability=json_extract(a.payload,'$.tasks['||OLD.position||'].capability')
     AND NEW.max_attempts=json_extract(a.payload,'$.tasks['||OLD.position||'].max_attempts')
     AND json(NEW.inputs)=json_extract(a.payload,'$.tasks['||OLD.position||'].inputs')
 ); END;
""")
    db.execute('INSERT INTO fixture_execution_policy VALUES(1,?,?)', (POLICY, now))


def fixture_enabled(db):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fixture_execution_policy'").fetchone():
        return False
    row = db.execute('SELECT policy FROM fixture_execution_policy WHERE singleton=1').fetchone()
    return row is not None and row[0] == POLICY


def fixture_intent(intent):
    return (intent is not None and intent.model_config is None and intent.consent_id is None and intent.parent_run_id is None
            and intent.ownership.kind == 'conversation' and intent.ownership.organization == OWNER
            and (intent.workflow_version != 'conversation-fixture-planning/v1' or intent.organization == OWNER)
            and tuple(task.capability for task in intent.tasks) == FIXTURE_PLANS.get(intent.workflow_version))


def grant_fixture_execution(db, intent, run_id):
    if not fixture_enabled(db) or not fixture_intent(intent):
        return False
    db.execute('INSERT INTO fixture_execution_grants VALUES(?,?,?)',
               (intent.organization, run_id, intent.fingerprint))
    return True


def fixture_granted(db, organization, run_id, intent):
    if not fixture_enabled(db) or not fixture_intent(intent):
        return False
    grant = db.execute('SELECT fingerprint FROM fixture_execution_grants WHERE organization=? AND run_id=?',
                       (organization, run_id)).fetchone()
    return grant is not None and grant[0] == intent.fingerprint


def fixture_active(db, organization, run_id):
    intent = binding(db, organization, run_id)
    if not fixture_granted(db, organization, run_id, intent):
        return False
    owner = intent.ownership
    account = account_evidence(db, owner.organization, owner.scope_id)
    return account.resolved and account.revision == owner.revision and account.recorded_stop < owner.revision
