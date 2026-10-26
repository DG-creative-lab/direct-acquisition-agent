"""Atomic synthetic outcomes, mature-cohort counts and advisory learning memory."""

import json
from collections import defaultdict

from acquisition.campaigns import Draft
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.learning import cohort_proposal, counts_for, finite, identifier, posterior, recommend, validate_outcome
from .actors import require_actor
from .drafts import verify


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

    def _record(self, db, organization, request_id, fingerprint, receipt, actor, now):
        db.execute("INSERT INTO learning_events(organization,cohort_id,kind,payload,at) VALUES(?,?,?,?,?)",
            (organization, receipt["cohort_id"], receipt["kind"], canonical(receipt | {"actor": actor}), now))
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

    def ingest(self, organization, actor, request_id, cohort_id, batch):
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
            cohort, record = self._cohort(db, organization, cohort_id)
            members = {m["business_id"]: m for m in cohort["members"]}
            added = 0
            for row in normalized["outcomes"]:
                if row["business_id"] not in members:
                    raise Conflict("Outcome business is outside the enrolled cohort")
                validate_outcome(row, members[row["business_id"]], cohort, now)
                old = db.execute("SELECT payload FROM learning_outcomes WHERE organization=? AND cohort_id=? AND business_id=?",
                    (organization, cohort_id, row["business_id"])).fetchone()
                if old:
                    if old[0] != canonical(row):
                        raise Conflict("An immutable outcome already exists for this business")
                else:
                    if record["finalized_at"] is not None:
                        raise Conflict("Finalized outcomes are immutable")
                    db.execute("INSERT INTO learning_outcomes VALUES(?,?,?,?)", (organization, cohort_id, row["business_id"], canonical(row)))
                    added += 1
            return self._record(db, organization, request_id, fingerprint,
                {"kind": "outcomes_imported", "cohort_id": cohort_id, "added": added, "duplicates": len(rows) - added, "mode": "SYNTHETIC_ONLY"}, actor, now)

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
        with self.database.connect() as db:
            db.execute("BEGIN")
            now = self._now()
            cohort, row = self._cohort(db, organization, cohort_id)
            received = db.execute("SELECT COUNT(*) FROM learning_outcomes WHERE organization=? AND cohort_id=?", (organization, cohort_id)).fetchone()[0]
            groups = [json.loads(r[0]) for r in db.execute("SELECT payload FROM learning_beliefs WHERE organization=? AND cohort_id=? ORDER BY segment,arm", (organization, cohort_id))]
            finalized = row["finalized_at"] is not None
            status = "finalized" if finalized else "awaiting_complete_outcomes" if now >= cohort["window_end"] else "observing"
            return {"cohort": {k: v for k, v in cohort.items() if k != "members"}, "status": status,
                "enrolled": len(cohort["members"]), "received": received, "missing": len(cohort["members"]) - received,
                "as_of": now, "beliefs": groups, "recommendations": recommend(cohort_id, groups) if finalized else [],
                "finalization": json.loads(row["finalization"]) if finalized else None,
                "events": [dict(r) | {"payload": json.loads(r["payload"])} for r in db.execute(
                    "SELECT * FROM learning_events WHERE organization=? AND cohort_id=? ORDER BY sequence", (organization, cohort_id))],
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
