"""Scheduled imports of immutable, recorded synthetic reports."""

import json
import time
from contextlib import contextmanager
from uuid import uuid4

from acquisition.contracts import Conflict, canonical, digest
from acquisition.learning import finite, identifier, normalize_report, validate_outcome, validate_report_binding

from .actors import require_actor
from .learning import accepted_cohort_draft
from .workspace_ancestry import JOURNAL_BINDING_KEY


LEASE_SECONDS = 30
PUBLIC_FIELDS = ("cohort_id", "interval_seconds", "first_check", "revision", "status",
                 "position", "report_count", "next_due", "last_checked", "last_report_id", "watermark", "detail")


def _public(row):
    return {key: row[key] for key in PUBLIC_FIELDS} if row is not None else None


def _interval(seconds):
    if type(seconds) is not int or not 60 <= seconds <= 7 * 86400:
        raise ValueError("Choose a report check interval from 60 seconds to 7 days")


def require_due_report(db, organization, actor, cohort_id, case_id, job_id, position, due):
    require_actor(db, organization, actor, "operator")
    plan = db.execute("""SELECT 1 FROM report_monitoring p JOIN learning_cohorts c
        ON c.organization=p.organization AND c.id=p.cohort_id JOIN simulated_agency_jobs j
        ON j.organization=c.organization AND j.id=c.job_id
        WHERE p.organization=? AND p.cohort_id=? AND j.id=? AND j.case_id=?
        AND p.status='scheduled' AND p.position=? AND p.next_due=?""",
        (organization, cohort_id, job_id, case_id, position, due)).fetchone()
    if plan is None:
        raise Conflict("Refresh the current recorded report check before advancing time")


class SqliteReportMonitoring:
    def __init__(self, learning, lease_clock=time.time):
        self.learning = learning
        self.database = learning.database
        self.lease_clock = lease_clock

    def _plan(self, db, organization, cohort_id):
        return db.execute("SELECT * FROM report_monitoring WHERE organization=? AND cohort_id=?",
                          (organization, cohort_id)).fetchone()

    def _source(self, db, organization, cohort_id, position):
        return db.execute("""SELECT * FROM report_monitoring_sources
            WHERE organization=? AND cohort_id=? AND position=?""", (organization, cohort_id, position)).fetchone()

    def status(self, organization, cohort_id):
        identifier(cohort_id)
        with self.database.connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] < 17:
                return None  # Older checkpoints remain inspectable.
            return _public(self._plan(db, organization, cohort_id))

    @contextmanager
    def fixture_check(self, organization, actor, cohort_id, case_id, job_id, position, due):
        with self.database.transaction() as db:
            require_due_report(db, organization, actor, cohort_id, case_id, job_id, position, due)
            yield

    def start(self, organization, actor, request_id, cohort_id, first_check, interval, reports):
        identifier(cohort_id)
        finite(first_check)
        _interval(interval)
        if not 1 <= len(reports) <= 12:
            raise ValueError("Choose 1 to 12 recorded reports")
        sources = []
        for report in reports:
            snapshot, outcomes, _ = normalize_report(report)
            sources.append((snapshot, outcomes, digest(snapshot), canonical(snapshot)))
        if (sum(len(raw.encode()) for _, _, _, raw in sources) > 16 * 1024 * 1024
                or len({report["report_id"] for report, _, _, _ in sources}) != len(sources)):
            raise ValueError("Choose distinct recorded reports totaling at most 16 MiB")
        watermarks = [report["watermark"] for report, _, _, _ in sources]
        if watermarks != sorted(watermarks):
            raise Conflict("Stage reports in watermark order")
        inputs = {"cohort_id": cohort_id, "first_check": first_check, "interval_seconds": interval,
                  "report_hashes": [report_hash for _, _, report_hash, _ in sources]}
        with self.database.transaction() as db:
            require_actor(db, organization, actor, "operator")
            fingerprint, cached = self.learning._cached(db, organization, actor, request_id, "monitor_start", inputs)
            if cached:
                return cached
            cohort, record = self.learning._cohort(db, organization, cohort_id)
            accepted_cohort_draft(db, organization, cohort)
            if record["finalized_at"] is not None or not cohort["window_start"] <= first_check <= cohort["window_end"]:
                raise Conflict("Schedule an open cohort with a first check inside its observation window")
            if self._plan(db, organization, cohort_id):
                raise Conflict("This cohort already has a report monitoring schedule")
            members = {member["business_id"]: member for member in cohort["members"]}
            staged = {}
            for report, outcomes, report_hash, _ in sources:
                validate_report_binding(report, cohort, cohort["window_end"])
                previous = self.learning._report_import(db, organization, cohort_id, report["report_id"])
                if previous and previous[0] != report_hash:
                    raise Conflict("Provider report ID already binds a different snapshot")
                for business_id, outcome in outcomes.items():
                    if business_id not in members:
                        raise Conflict("Outcome business is outside the enrolled cohort")
                    validate_outcome(outcome, members[business_id], cohort, report["watermark"])
                    encoded = canonical(outcome)
                    if staged.setdefault(business_id, encoded) != encoded:
                        raise Conflict("Staged reports disagree on an immutable outcome")
            db.execute("""INSERT INTO report_monitoring
                (organization,cohort_id,actor,interval_seconds,first_check,revision,status,position,report_count,next_due)
                VALUES(?,?,?,?,?,1,'scheduled',0,?,?)""",
                       (organization, cohort_id, actor, interval, first_check, len(sources), max(first_check, watermarks[0])))
            db.executemany("INSERT INTO report_monitoring_sources VALUES(?,?,?,?,?,?)",
                           ((organization, cohort_id, i, report["watermark"], report_hash, raw)
                            for i, (report, _, report_hash, raw) in enumerate(sources)))
            return self.learning._command(db, organization, request_id, fingerprint,
                                          _public(self._plan(db, organization, cohort_id)))

    def update(self, organization, actor, request_id, cohort_id, expected_revision, status, interval=None):
        identifier(cohort_id)
        if type(expected_revision) is not int or expected_revision < 1 or status not in ("scheduled", "paused"):
            raise ValueError("Use the displayed schedule revision and choose scheduled or paused")
        if interval is not None:
            _interval(interval)
        inputs = {"cohort_id": cohort_id, "revision": expected_revision, "status": status, "interval_seconds": interval}
        with self.database.transaction() as db:
            require_actor(db, organization, actor, "operator")
            fingerprint, cached = self.learning._cached(db, organization, actor, request_id, "monitor_update", inputs)
            if cached:
                return cached
            plan = self._plan(db, organization, cohort_id)
            if (plan is None or plan["actor"] != actor or plan["revision"] != expected_revision
                    or plan["status"] == "complete"):
                raise Conflict("Use the current unfinished schedule and its original operator")
            db.execute("""UPDATE report_monitoring SET status=?,interval_seconds=?,revision=revision+1,
                detail=NULL,lease_token=NULL,lease_until=NULL WHERE organization=? AND cohort_id=?""",
                       (status, interval if interval is not None else plan["interval_seconds"], organization, cohort_id))
            return self.learning._command(db, organization, request_id, fingerprint,
                                          _public(self._plan(db, organization, cohort_id)))

    def claim(self, organization, cohort_id, *, standalone=False, expected_position=None):
        with self.database.transaction() as db:
            if standalone and db.execute("""SELECT 1 FROM execution_commands WHERE organization=? AND request_id=?
                    UNION ALL SELECT 1 FROM campaign_environments WHERE organization=? AND cohort_id=? LIMIT 1""",
                    (organization, JOURNAL_BINDING_KEY, organization, cohort_id)).fetchone():
                raise Conflict("Workspace report checks use the workspace server and its campaign clock")
            plan = self._plan(db, organization, cohort_id)
            now, lease_now = self.learning._now(), self.lease_clock()
            if (plan is None or plan["status"] != "scheduled" or plan["next_due"] > now
                    or (expected_position is not None and plan["position"] != expected_position)
                    or (plan["lease_until"] is not None and plan["lease_until"] > lease_now)):
                return None
            token = uuid4().hex
            db.execute("UPDATE report_monitoring SET lease_token=?,lease_until=? WHERE organization=? AND cohort_id=?",
                       (token, lease_now + LEASE_SECONDS, organization, cohort_id))
            return token

    def _leased(self, db, organization, cohort_id, token):
        plan = self._plan(db, organization, cohort_id)
        if (not token or plan is None or plan["status"] != "scheduled" or plan["lease_token"] != token
                or plan["lease_until"] <= self.lease_clock()):
            return None
        return plan

    def _request_id(self, organization, cohort_id, position):
        return "monitor-report:" + digest({"organization": organization, "cohort_id": cohort_id, "position": position})

    def import_claim(self, organization, cohort_id, token):
        with self.database.transaction() as db:
            plan = self._leased(db, organization, cohort_id, token)
            if plan is None:
                return False
            now = self.learning._now()
            if now < plan["next_due"]:
                return False
            source = self._source(db, organization, cohort_id, plan["position"])
            if source is None:
                raise Conflict("The scheduled report snapshot is unavailable")
            report, outcomes, duplicates = normalize_report(json.loads(source["snapshot"]))
            report_hash = digest(report)
            if report_hash != source["report_sha256"] or report["watermark"] != source["available_at"]:
                raise Conflict("The scheduled report differs from its saved snapshot")
            request_id = self._request_id(organization, cohort_id, plan["position"])
            self.learning.import_report(db, organization, plan["actor"], request_id, cohort_id, report,
                                        outcomes, duplicates, report_hash, now)
            if self._leased(db, organization, cohort_id, token) is None:
                raise Conflict("Report check lease expired before import committed")
            return True

    def finish(self, organization, cohort_id, token):
        with self.database.transaction() as db:
            plan = self._leased(db, organization, cohort_id, token)
            if plan is None:
                return
            require_actor(db, organization, plan["actor"], "operator")
            position = plan["position"]
            source = self._source(db, organization, cohort_id, position)
            if source is None:
                raise Conflict("The scheduled report snapshot is unavailable")
            _, receipt = self.learning._cached(db, organization, plan["actor"],
                self._request_id(organization, cohort_id, position), "ingest_report",
                {"cohort_id": cohort_id, "report_sha256": source["report_sha256"]})
            if (type(receipt) is not dict or receipt.get("report_sha256") != source["report_sha256"]
                    or receipt.get("watermark") != source["available_at"] or receipt.get("cohort_id") != cohort_id
                    or type(receipt.get("report_id")) is not str):
                raise Conflict("The scheduled report import receipt is unavailable")
            cohort, _ = self.learning._cohort(db, organization, cohort_id)
            now = max(self.learning._now(), plan["next_due"])
            next_due = None
            if position + 1 < plan["report_count"]:
                following = self._source(db, organization, cohort_id, position + 1)
                if following is None:
                    raise Conflict("The next scheduled report snapshot is unavailable")
                next_due = max(following["available_at"], min(now + plan["interval_seconds"], cohort["window_end"]))
            db.execute("""UPDATE report_monitoring SET position=position+1,status=?,next_due=?,last_checked=?,
                last_report_id=?,watermark=?,lease_token=NULL,lease_until=NULL WHERE organization=? AND cohort_id=?""",
                       ("complete" if next_due is None else "scheduled", next_due, now, receipt["report_id"],
                        receipt["watermark"], organization, cohort_id))
            if plan["lease_until"] <= self.lease_clock():
                raise Conflict("Report check lease expired before progress committed")

    def block(self, organization, cohort_id, token, detail):
        with self.database.transaction() as db:
            if self._leased(db, organization, cohort_id, token) is not None:
                db.execute("""UPDATE report_monitoring SET status='blocked',detail=?,lease_token=NULL,lease_until=NULL
                    WHERE organization=? AND cohort_id=?""", (detail, organization, cohort_id))
