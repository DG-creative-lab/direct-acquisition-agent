"""Atomic synthetic outcomes, mature-cohort counts and advisory learning memory."""

import json
from collections import defaultdict

from acquisition.campaigns import Draft
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.learning import (cohort_proposal, counts_for, finite, identifier, normalize_report,
                                  posterior, recommend, validate_outcome, validate_report_binding)
from .actors import require_actor
from .drafts import read_draft, verify
from .simulated_delivery import SqliteSimulatedDelivery, require_provider_result


REPORT_SOURCE_EVENT = "provider_report_source_recorded"


def require_manual_simulation(db, organization, cohort_id):
    if db.execute("SELECT 1 FROM report_monitoring WHERE organization=? AND cohort_id=?",
                  (organization, cohort_id)).fetchone():
        raise Conflict("Use the recorded report controls for this cohort")


def accepted_cohort_draft(db, organization, cohort):
    """Rebuild an accepted experiment without treating its receipt as authority."""
    try:
        if (cohort['organization'] != organization or cohort['id'] != 'cohort_' + digest(
                {k: v for k, v in cohort.items() if k != 'id'})):
            raise Conflict('Source cohort integrity failure')
        job = db.execute('SELECT * FROM simulated_agency_jobs WHERE organization=? AND case_id=?',
                         (organization, cohort['case_id'])).fetchone()
        if job is None:
            raise Conflict('Source cohort lacks its accepted simulated job')
        receipt = json.loads(job['payload'])
        if (receipt['kind'] != 'simulated_agency_acceptance'
                or any(job[key] != receipt[key] for key in ('id', 'case_id', 'approval_id', 'subject_id'))
                or receipt['id'] != 'fake_job_' + digest({'case': receipt['case_id'], 'approval': receipt['approval_id']})):
            raise Conflict('Source cohort acceptance identity is inconsistent')
        require_provider_result(SqliteSimulatedDelivery(db), organization, receipt)
        draft = read_draft(db, organization, receipt['draft_id'])
        if cohort_proposal(organization, receipt, draft) != cohort:
            raise Conflict('Source cohort differs from its accepted experiment')
        return draft
    except (NotFound, ValueError, TypeError, KeyError) as error:
        raise Conflict('Source accepted experiment is invalid') from error


def require_source_request(db, organization, cohort_id):
    """Validate native requests through scoped legacy and current ancestry."""
    from .conversation_provenance import require_requested_scope
    seen = set()
    try:
        while True:
            if cohort_id in seen:
                raise Conflict('Follow-up request ancestry contains a cycle')
            seen.add(cohort_id)
            row = db.execute('SELECT payload FROM learning_cohorts WHERE organization=? AND id=?',
                             (organization, cohort_id)).fetchone()
            if row is None:
                raise Conflict('Follow-up source cohort is unavailable')
            cohort = json.loads(row[0])
            if cohort['id'] != cohort_id:
                raise Conflict('Follow-up source cohort identity changed')
            draft = accepted_cohort_draft(db, organization, cohort)
            brief = draft.manifest['brief']
            require_requested_scope(db, brief, draft.manifest.get('campaign_scope'))
            if 'followup_id' not in brief:
                return
            row = db.execute('SELECT receipt FROM review_commands WHERE organization=? AND request_id=?',
                             (organization, brief['followup_id'])).fetchone()
            proposal = json.loads(row[0]) if row else {}
            if (proposal.get('kind') != 'followup_proposal'
                    or proposal.get('id') != brief['followup_id']
                    or proposal['id'] != 'followup_' + digest({k:v for k,v in proposal.items() if k != 'id'})
                    or brief != proposal['brief'] | {'campaign_id': brief['campaign_id'], 'followup_id': proposal['id']}
                    or draft.manifest['snapshot_id'] != proposal['snapshot_id']):
                raise Conflict('Follow-up request ancestry differs from its saved proposal')
            cohort_id = proposal['source_cohort']
    except (NotFound, ValueError, TypeError, KeyError) as error:
        raise Conflict('Follow-up source request evidence is invalid') from error


def reconcile_finalized_outcomes(db, organization, cohort, finalization, now):
    """Recount native evidence inside the caller's read or write transaction."""
    try:
        accepted_cohort_draft(db, organization, cohort)
        if not finalization:
            raise Conflict('Finalized source lacks its finalization receipt')
        members = {m['business_id']: m for m in cohort['members']}
        indexed = {r[0] for r in db.execute(
            'SELECT business_id FROM learning_members WHERE organization=? AND cohort_id=?', (organization, cohort['id']))}
        if not members or len(members) != len(cohort['members']) or indexed != set(members):
            raise Conflict('Finalized source membership no longer matches its cohort')
        outcomes = {r['business_id']: json.loads(r['payload']) for r in db.execute(
            'SELECT business_id,payload FROM learning_outcomes WHERE organization=? AND cohort_id=?',
            (organization, cohort['id']))}
        if set(outcomes) != set(members):
            raise Conflict('Finalized source outcomes no longer cover the exact membership')
        for business_id, outcome in outcomes.items():
            validate_outcome(outcome, members[business_id], cohort, now)
        groups = counts_for(cohort['members'], outcomes)
        recorded = [json.loads(r[0]) for r in db.execute(
            'SELECT payload FROM learning_beliefs WHERE organization=? AND cohort_id=? ORDER BY segment,arm',
            (organization, cohort['id']))]
        if (digest(outcomes) != finalization['outcome_digest'] or digest(groups) != finalization['beliefs_digest']
                or groups != recorded or finalization['observations'] != len(outcomes)
                or finalization['successes'] != sum(r['response'] for r in outcomes.values())):
            raise Conflict('Finalized source outcomes differ from their receipt or beliefs')
        return groups
    except (NotFound, ValueError, TypeError, KeyError) as error:
        raise Conflict('Finalized source acceptance or outcome evidence is invalid') from error


class SqliteLearning:
    def __init__(self, database, clock):
        self.database, self.clock = database, clock

    def _now(self):
        now = self.clock()
        finite(now)
        return now

    def _cohort(self, db, organization, cohort_id):
        row = db.execute("SELECT * FROM learning_cohorts WHERE organization=? AND id=?", (organization, cohort_id)).fetchone()
        if row is None:
            raise NotFound("Learning cohort not found in this organization")
        payload = json.loads(row["payload"])
        if payload.get("id") != cohort_id or "cohort_" + digest({k: v for k, v in payload.items() if k != "id"}) != cohort_id:
            raise Conflict("Cohort integrity failure")
        return payload, row

    def _cached(self, db, organization, actor, request_id, kind, payload):
        identifier(request_id)
        fingerprint = digest({"actor": actor, "kind": kind, "payload": payload})
        old = db.execute("SELECT * FROM learning_commands WHERE organization=? AND request_id=?", (organization, request_id)).fetchone()
        if old:
            if old["request_hash"] != fingerprint:
                raise Conflict("Learning request ID already binds different inputs")
            return fingerprint, json.loads(old["receipt"])
        return fingerprint, None

    def _event(self, db, organization, cohort_id, kind, payload, now):
        return db.execute("INSERT INTO learning_events(organization,cohort_id,kind,payload,at) VALUES(?,?,?,?,?)",
                          (organization, cohort_id, kind, canonical(payload), now)).lastrowid

    def _record(self, db, organization, request_id, fingerprint, receipt, actor, now, *, snapshot=None):
        cohort_id = receipt["cohort_id"]
        sequence = self._event(db, organization, cohort_id, receipt["kind"], receipt | {"actor": actor}, now)
        if snapshot is not None:
            self._record_report_snapshot(db, organization, cohort_id, sequence, snapshot, actor, now)
        return self._command(db, organization, request_id, fingerprint, receipt)

    def _command(self, db, organization, request_id, fingerprint, receipt):
        db.execute("INSERT INTO learning_commands VALUES(?,?,?,?)", (organization, request_id, fingerprint, canonical(receipt)))
        return receipt

    def open(self, organization, actor, request_id, proposal):
        with self.database.transaction() as db:
            now = self._now()
            require_actor(db, organization, actor, "operator")
            fingerprint, cached = self._cached(db, organization, actor, request_id, "open", {"proposal": proposal})
            if cached:
                return cached
            # Check the immutable accepted artifact again at the storage boundary.
            job = db.execute("SELECT payload FROM simulated_agency_jobs WHERE organization=? AND case_id=?", (organization, proposal["case_id"])).fetchone()
            if job is None:
                raise Conflict("No accepted simulated job in this organization")
            receipt = json.loads(job[0])
            row = db.execute("SELECT * FROM drafts WHERE organization=? AND id=?", (organization, receipt["draft_id"])).fetchone()
            if row is None:
                raise NotFound("Accepted draft is unavailable")
            draft = Draft(json.loads(row["manifest"]), row["mailing"], row["assignments"])
            verify(organization, draft)
            if cohort_proposal(organization, receipt, draft) != proposal:
                raise Conflict("Proposal does not match the accepted experiment")
            if now < proposal["window_start"]:
                raise ValueError("Cannot open a cohort before simulated acceptance")
            old = db.execute("SELECT id FROM learning_cohorts WHERE organization=? AND job_id=?", (organization, receipt["id"])).fetchone()
            if old is None:
                # Pooling assumes independent business observations. Repeated
                # exposure requires a future clustered/repeated-measures model.
                for member in proposal["members"]:
                    if db.execute("SELECT 1 FROM learning_members WHERE organization=? AND business_id=?", (organization, member["business_id"])).fetchone():
                        raise Conflict("Business already belongs to a learning cohort; repeated exposure is unsupported")
                db.execute("INSERT INTO learning_cohorts VALUES(?,?,?,?,?,NULL,NULL)",
                    (organization, proposal["id"], receipt["id"], canonical(proposal), now))
                db.executemany("INSERT INTO learning_members VALUES(?,?,?)",
                    [(organization, m["business_id"], proposal["id"]) for m in proposal["members"]])
            elif old["id"] != proposal["id"]:
                raise Conflict("Accepted job already binds a different cohort")
            opened = {"kind": "cohort_opened", "cohort_id": proposal["id"], "members": len(proposal["members"]),
                "window_start": proposal["window_start"], "window_end": proposal["window_end"], "mode": "SYNTHETIC_ONLY"}
            if old is not None:
                return self._command(db, organization, request_id, fingerprint, opened)
            return self._record(db, organization, request_id, fingerprint, opened, actor, now)

    def ingest(self, organization, actor, request_id, cohort_id, batch, *, simulate=False):
        if (type(batch) is not dict or set(batch) != {"schema", "mode", "cohort_id", "outcomes"}
                or batch["schema"] != "synthetic-outcomes/v1" or batch["mode"] != "SYNTHETIC_ONLY" or batch["cohort_id"] != cohort_id
                or type(batch["outcomes"]) is not list or not 1 <= len(batch["outcomes"]) <= 10000):
            raise ValueError("Use a synthetic outcome batch with 1 to 10000 rows for this cohort")
        rows = batch["outcomes"]
        if any(type(r) is not dict or type(r.get("business_id")) is not str for r in rows):
            raise ValueError("Each outcome requires a business ID")
        if len({r["business_id"] for r in rows}) != len(rows):
            raise Conflict("Duplicate business outcomes in one batch")
        normalized = batch | {"outcomes": sorted(rows, key=lambda r: r["business_id"])}
        with self.database.transaction() as db:
            now = self._now()
            require_actor(db, organization, actor, "operator")
            fingerprint, cached = self._cached(db, organization, actor, request_id, "ingest", normalized)
            if cached:
                return cached
            if simulate:
                require_manual_simulation(db, organization, cohort_id)
            cohort, record = self._cohort(db, organization, cohort_id)
            added = self._write_outcomes(db, organization, cohort, record, normalized["outcomes"], now)
            return self._record(db, organization, request_id, fingerprint,
                {"kind": "outcomes_imported", "cohort_id": cohort_id, "added": added, "duplicates": len(rows) - added, "mode": "SYNTHETIC_ONLY"}, actor, now)

    def ingest_report(self, organization, actor, request_id, cohort_id, report):
        report, outcomes, duplicate_events = normalize_report(report)
        report_hash = digest(report)
        with self.database.transaction() as db:
            now = self._now()
            return self.import_report(db, organization, actor, request_id, cohort_id, report,
                                      outcomes, duplicate_events, report_hash, now)

    def import_report(self, db, organization, actor, request_id, cohort_id, report,
                      outcomes, duplicate_events, report_hash, now):
        """Commit report evidence inside the caller's scoped write transaction."""
        require_actor(db, organization, actor, "operator")
        fingerprint, cached = self._cached(db, organization, actor, request_id, "ingest_report",
                                           {"cohort_id": cohort_id, "report_sha256": report_hash})
        if cached:
            return cached
        cohort, record = self._cohort(db, organization, cohort_id)
        validate_report_binding(report, cohort, now)
        accepted_cohort_draft(db, organization, cohort)
        previous = self._report_import(db, organization, cohort_id, report["report_id"])
        if previous and previous[0] != report_hash:
            raise Conflict("Provider report ID already binds a different snapshot")
        added = self._write_outcomes(db, organization, cohort, record, outcomes.values(), report["watermark"])
        missing = len(cohort["members"]) - len(outcomes)
        receipt = {key: report[key] for key in ("mode", "cohort_id", "job_id", "metric", "report_id", "watermark", "final", "page_count")}
        receipt |= {"kind": "provider_report_imported", "report_sha256": report_hash, "added": added,
                    "duplicates": len(outcomes) - added, "duplicate_events": duplicate_events,
                    "missing_from_report": missing, "coverage_complete": report["final"] and missing == 0}
        if previous:
            if added:
                raise Conflict("Previously imported report outcomes are missing")
            if self._saved_report_snapshot(db, organization, cohort_id, previous) is None:
                self._record_report_snapshot(db, organization, cohort_id, previous["sequence"], report, actor, now)
            return self._command(db, organization, request_id, fingerprint, receipt)
        return self._record(db, organization, request_id, fingerprint, receipt, actor, now, snapshot=report)

    def _report_import(self, db, organization, cohort_id, report_id):
        return db.execute("""SELECT json_extract(payload, '$.report_sha256'), sequence, payload, at FROM learning_events
            WHERE organization=? AND cohort_id=? AND kind='provider_report_imported'
            AND json_extract(payload, '$.report_id')=?""", (organization, cohort_id, report_id)).fetchone()

    def _record_report_snapshot(self, db, organization, cohort_id, sequence, snapshot, actor, now):
        self._event(db, organization, cohort_id, REPORT_SOURCE_EVENT,
                    {"import_sequence": sequence, "snapshot": snapshot, "actor": actor}, now)

    def _saved_report_snapshot(self, db, organization, cohort_id, imported):
        rows = db.execute("""SELECT payload FROM learning_events
            WHERE organization=? AND cohort_id=? AND kind=?
            AND json_extract(payload, '$.import_sequence')=? LIMIT 2""",
            (organization, cohort_id, REPORT_SOURCE_EVENT, imported["sequence"])).fetchall()
        if not rows:
            return None
        snapshot = json.loads(rows[0][0]).get("snapshot")
        if len(rows) != 1 or type(snapshot) is not dict or digest(snapshot) != imported[0]:
            raise Conflict("Stored provider snapshot does not match the import receipt")
        return snapshot

    def report_snapshot(self, organization, cohort_id, report_id):
        identifier(report_id)
        with self.database.connect() as db:
            db.execute("BEGIN")
            cohort, _ = self._cohort(db, organization, cohort_id)
            imported = self._report_import(db, organization, cohort_id, report_id)
            if imported is None:
                raise NotFound("Provider report not found in this cohort")
            snapshot = self._saved_report_snapshot(db, organization, cohort_id, imported)
            if snapshot is None:
                raise NotFound("Provider snapshot is unavailable for this import receipt")
            validate_report_binding(snapshot, cohort, imported["at"])
            receipt = json.loads(imported["payload"])
            if any(receipt[key] != snapshot[key] for key in ("report_id", "job_id", "metric", "watermark", "final", "page_count")):
                raise Conflict("Stored provider snapshot does not match the import receipt")
            return {"import_receipt": receipt, "snapshot": snapshot}

    def _write_outcomes(self, db, organization, cohort, record, rows, now):
        cohort_id = cohort["id"]
        members = {m["business_id"]: m for m in cohort["members"]}
        added = 0
        for row in rows:
            business_id = row["business_id"]
            if business_id not in members:
                raise Conflict("Outcome business is outside the enrolled cohort")
            validate_outcome(row, members[business_id], cohort, now)
            payload = canonical(row)
            old = db.execute("SELECT payload FROM learning_outcomes WHERE organization=? AND cohort_id=? AND business_id=?",
                             (organization, cohort_id, business_id)).fetchone()
            if old:
                if old[0] != payload:
                    raise Conflict("An immutable outcome already exists for this business")
            else:
                if record["finalized_at"] is not None:
                    raise Conflict("Finalized outcomes are immutable")
                db.execute("INSERT INTO learning_outcomes VALUES(?,?,?,?)", (organization, cohort_id, business_id, payload))
                added += 1
        return added

    def _outcomes(self, db, organization, cohort_id):
        return {r["business_id"]: json.loads(r["payload"]) for r in db.execute(
            "SELECT * FROM learning_outcomes WHERE organization=? AND cohort_id=?", (organization, cohort_id))}

    def finalize(self, organization, actor, request_id, cohort_id, complete_through):
        finite(complete_through)
        with self.database.transaction() as db:
            now = self._now()
            require_actor(db, organization, actor, "operator")
            fingerprint, cached = self._cached(db, organization, actor, request_id, "finalize",
                {"cohort_id": cohort_id, "complete_through": complete_through})
            if cached:
                return cached
            cohort, row = self._cohort(db, organization, cohort_id)
            if complete_through != cohort["window_end"] or now < cohort["window_end"]:
                raise Conflict("The entire observation window must close before finalization")
            if row["finalized_at"] is not None:
                return self._command(db, organization, request_id, fingerprint, json.loads(row["finalization"]))
            outcomes = self._outcomes(db, organization, cohort_id)
            for member in cohort["members"]:
                if member["business_id"] in outcomes:
                    validate_outcome(outcomes[member["business_id"]], member, cohort, now)
            groups = counts_for(cohort["members"], outcomes)
            for group in groups:
                db.execute("INSERT INTO learning_beliefs VALUES(?,?,?,?,?,?)", (organization, cohort_id,
                    group["segment"], group["arm"], group["creative_id"], canonical(group)))
            receipt = {"kind": "cohort_finalized", "cohort_id": cohort_id, "mode": "SYNTHETIC_ONLY",
                "observations": len(outcomes), "successes": sum(r["response"] for r in outcomes.values()),
                "complete_through": complete_through, "finalized_at": now, "outcome_digest": digest(outcomes),
                "beliefs_digest": digest(groups), "prior": {"alpha": 1, "beta": 19}}
            db.execute("UPDATE learning_cohorts SET finalized_at=?,finalization=? WHERE organization=? AND id=?",
                (now, canonical(receipt), organization, cohort_id))
            return self._record(db, organization, request_id, fingerprint, receipt, actor, now)

    def view(self, organization, cohort_id):
        return self._view(organization, cohort_id, reconcile=False)

    def hypothesis_source(self, organization, cohort_id):
        return self._view(organization, cohort_id, reconcile=True)

    def _view(self, organization, cohort_id, *, reconcile):
        with self.database.connect() as db:
            db.execute("BEGIN")
            now = self._now()
            cohort, row = self._cohort(db, organization, cohort_id)
            received = db.execute("SELECT COUNT(*) FROM learning_outcomes WHERE organization=? AND cohort_id=?", (organization, cohort_id)).fetchone()[0]
            groups = [json.loads(r[0]) for r in db.execute("SELECT payload FROM learning_beliefs WHERE organization=? AND cohort_id=? ORDER BY segment,arm", (organization, cohort_id))]
            finalized = row["finalized_at"] is not None
            if finalized and reconcile:
                finalization = json.loads(row['finalization'] or 'null')
                if not finalization or row['finalized_at'] != finalization['finalized_at']:
                    raise Conflict('Finalized source timestamp differs from its receipt')
                groups = reconcile_finalized_outcomes(db, organization, cohort, finalization, now)
                require_source_request(db, organization, cohort_id)
            status = "finalized" if finalized else "awaiting_complete_outcomes" if now >= cohort["window_end"] else "observing"
            return {"cohort": {k: v for k, v in cohort.items() if k != "members"}, "status": status,
                "enrolled": len(cohort["members"]), "received": received, "missing": len(cohort["members"]) - received,
                "as_of": now, "beliefs": groups, "recommendations": recommend(cohort_id, groups) if finalized else [],
                "finalization": json.loads(row["finalization"]) if finalized else None,
                "events": [dict(r) | {"payload": json.loads(r["payload"])} for r in db.execute(
                    "SELECT * FROM learning_events WHERE organization=? AND cohort_id=? AND kind<>? ORDER BY sequence",
                    (organization, cohort_id, REPORT_SOURCE_EVENT))],
                "limitations": ["Synthetic responses are not customer evidence.", "Acceptance is simulated; delivery is not verified.",
                    "Beta(1,19) is an illustrative fixed prior, not calibrated production knowledge.",
                    "Monte Carlo intervals and probabilities are estimates, not guarantees.",
                    "Response lift is conditional on the selected randomized cohort; no revenue or profit claim.",
                    "Repeated business exposure, corrections and external outcome feeds are unsupported.",
                    "Recommendations require a new proposal and approval before any changed campaign."]}

    def memory(self, organization, segment):
        return self.memory_snapshot(organization, (segment,))[segment]

    def memory_snapshot(self, organization, segments):
        if (type(segments) is not tuple or not 1 <= len(segments) <= 2
                or len(set(segments)) != len(segments) or set(segments) - {"inventory", "contractors"}):
            raise ValueError("Choose unique supported learning segments")
        with self.database.connect() as db:
            db.execute("BEGIN")
            now = self._now()
            placeholders = ",".join("?" for _ in segments)
            rows = db.execute("SELECT b.* FROM learning_beliefs b JOIN learning_cohorts c "
                "ON c.organization=b.organization AND c.id=b.cohort_id "
                "WHERE b.organization=? AND b.segment IN (" + placeholders + ") "
                "AND c.finalized_at IS NOT NULL AND c.finalized_at<=? ORDER BY b.cohort_id,b.arm",
                (organization, *segments, now)).fetchall()
            snapshot = {}
            for segment in segments:
                totals = defaultdict(lambda: [0, 0, []])
                for row in rows:
                    if row["segment"] != segment:
                        continue
                    g = json.loads(row["payload"])
                    value = totals[(g["arm"], g["creative_id"])]
                    value[0] += g["trials"]
                    value[1] += g["successes"]
                    value[2].append(row["cohort_id"])
                snapshot[segment] = {"schema": "synthetic-learning-memory/v1", "segment": segment, "mode": "SYNTHETIC_ONLY",
                    "basis": "Finalized disjoint business cohorts only. Pooled rates are descriptive, not causal comparisons.",
                    "groups": [posterior(segment, arm, creative, n, s) | {"cohort_ids": ids}
                               for (arm, creative), (n, s, ids) in sorted(totals.items())],
                    "authority": "ADVISORY_ONLY_NO_COPY_OR_APPROVAL_INHERITANCE"}
            return snapshot
