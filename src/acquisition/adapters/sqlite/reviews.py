"""Atomic local review authority and simulated acceptance. No network dispatch."""

import json
import csv
import io
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from acquisition.audiences import Business, Snapshot
from acquisition.campaigns import Draft
from acquisition.contracts import Conflict, NotFound, canonical, digest
from acquisition.conversations import validate_result
from acquisition.creative import fact_pack_id, validate_fact_pack
from acquisition.reviews import ReviewPolicy, current_reasons, subject, text, timestamp, validate_candidate

from .database import Database
from .actors import require_actor
from .drafts import verify
from .tasks import scoped_run


class SqliteReviews:
    def __init__(self, database: Database, clock):
        self.database, self.clock = database, clock

    def _now(self):
        now = self.clock()
        timestamp(now)
        return now

    def _actor(self, db, organization, actor, role):
        return require_actor(db, organization, actor, role)

    def _authority(self, db, organization):
        row = db.execute("SELECT * FROM review_authorities WHERE organization=?", (organization,)).fetchone()
        if row is None:
            raise NotFound("Activate reviewed product evidence before opening a review")
        return dict(row) | {"pack": json.loads(row["pack"]), "policy": json.loads(row["policy"])}

    def evidence(self, organization):
        with self.database.connect() as db:
            row = db.execute("SELECT * FROM review_authorities WHERE organization=?", (organization,)).fetchone()
            return self._authority(db, organization) if row else None

    def _case(self, db, organization, case_id):
        row = db.execute("SELECT * FROM review_cases WHERE organization=? AND id=?", (organization, case_id)).fetchone()
        if row is None:
            raise NotFound("Review case not found in this organization")
        return row

    def _subject(self, db, organization, identity):
        row = db.execute("SELECT * FROM review_subjects WHERE organization=? AND id=?", (organization, identity)).fetchone()
        if row is None:
            raise NotFound("Review subject not found in this organization")
        payload = json.loads(row["payload"])
        if payload.get("id") != identity or "subject_" + digest({k: v for k, v in payload.items() if k != "id"}) != identity:
            raise Conflict("Review subject integrity failure")
        return payload

    def _bundle(self, db, organization, draft_id):
        row = db.execute("SELECT * FROM drafts WHERE organization=? AND id=?", (organization, draft_id)).fetchone()
        if row is None:
            raise NotFound("Draft not found in this organization")
        draft = Draft(json.loads(row["manifest"]), row["mailing"], row["assignments"])
        verify(organization, draft)
        if draft.id != draft_id:
            raise Conflict("Draft integrity failure")
        row = db.execute("SELECT payload FROM audiences WHERE organization=? AND id=?",
                         (organization, draft.manifest["snapshot_id"])).fetchone()
        if row is None:
            raise NotFound("Audience snapshot not found")
        data = json.loads(row[0])
        snapshot = Snapshot(records=tuple(Business(**r) for r in data.pop("records")), **data)
        if snapshot.id != draft.manifest["snapshot_id"] or snapshot.organization != organization:
            raise Conflict("Audience integrity failure")
        contexts = {}
        for creative in draft.manifest["creatives"]:
            identity = creative.get("context_id")
            if not identity:
                continue
            row = db.execute("SELECT payload FROM creative_contexts WHERE organization=? AND id=?", (organization, identity)).fetchone()
            if row is None:
                raise NotFound("Creative context not found")
            context = json.loads(row[0])
            if "context_" + digest({"organization": organization, **context}) != identity:
                raise Conflict("Creative context integrity failure")
            contexts[identity] = context
        return draft, snapshot, contexts

    def _suppressed(self, db, organization):
        return {r[0] for r in db.execute("SELECT business_id FROM review_suppressions WHERE organization=?", (organization,))}

    def _conversation_source(self, db, organization, case, draft):
        original = db.execute("SELECT inputs FROM tasks WHERE run_id=? ORDER BY position LIMIT 1", (case["run_id"],)).fetchone()
        inputs = json.loads(original[0]) if original else {}
        source = inputs.get("brief", {})
        brief = draft.manifest["brief"]
        version = inputs.get("workflow_version")
        if version not in {"conversation-mail/v1", "conversation-model-mail/v3"}:
            if "conversation_id" in brief:
                raise Conflict("Conversation provenance cannot be added to another workflow")
            return
        if brief != source:
            raise Conflict("Campaign differs from its original conversation proposal")
        expected_status = "generated_unreviewed" if version == "conversation-model-mail/v3" else "synthetic_fixture_unapproved"
        if any(item.get("status") != expected_status for item in draft.manifest["creatives"]):
            raise Conflict("Conversation copy mode cannot be substituted")
        conversation_scope = "local-conversations"
        conversation = db.execute("SELECT revision FROM conversations WHERE organization=? AND id=?",
                                  (conversation_scope, source["conversation_id"])).fetchone()
        if conversation is None or conversation[0] != source["conversation_revision"]:
            raise Conflict("Conversation changed after this campaign was prepared")
        row = db.execute("SELECT payload FROM conversation_plans WHERE organization=? AND conversation_id=? AND revision=?",
                         (conversation_scope, source["conversation_id"], source["conversation_revision"])).fetchone()
        if row is None:
            raise Conflict("Original conversation plan is unavailable")
        frozen = json.loads(row[0])
        row = db.execute("""SELECT t.output FROM runs r JOIN tasks t ON t.run_id=r.id
            WHERE r.organization=? AND r.request_id=? AND r.status='succeeded' AND t.status='succeeded'
            AND t.capability IN ('conversations.plan.v1','conversations.fixture_plan.v1')""", (conversation_scope, frozen["run_request_id"])).fetchone()
        if row is None:
            raise Conflict("Original conversation plan has not succeeded")
        result = json.loads(row[0])
        fields = ("outcome", "objective", "budget_pence", "segments", "copy_mode", "question", "assumptions", "unsupported_reason")
        try:
            verified = validate_result({field: result[field] for field in fields}, frozen, conversation_scope)
        except (KeyError, TypeError, ValueError):
            raise Conflict("Original conversation plan failed integrity checks") from None
        if (verified != result or result["id"] != source["plan_id"] or result["outcome"] != "brief_proposal"
                or result["copy_mode"] != ("model" if version == "conversation-model-mail/v3" else "fixture") or result["budget_pence"] != brief["budget_pence"]
                or result["segments"] != brief["segments"]):
            raise Conflict("Campaign does not match its validated conversation proposal")

    def _validate(self, db, organization, case, draft_id, authority, now):
        bundle = self._bundle(db, organization, draft_id)
        self._conversation_source(db, organization, case, bundle[0])
        validate_candidate(*bundle, authority["pack"], ReviewPolicy(**authority["policy"]), self._suppressed(db, organization), now)
        return bundle[0]

    def _event(self, db, organization, case_id, kind, payload, now):
        db.execute("INSERT INTO review_events(organization,case_id,kind,payload,at) VALUES(?,?,?,?,?)",
                   (organization, case_id, kind, canonical(payload), now))

    def _cached(self, db, organization, actor, request_id, kind, payload):
        text(request_id, 160)
        fingerprint = digest({"actor": actor, "kind": kind, "payload": payload})
        row = db.execute("SELECT * FROM review_commands WHERE organization=? AND request_id=?", (organization, request_id)).fetchone()
        if row:
            if row["request_hash"] != fingerprint:
                raise Conflict("Review request ID already binds different inputs")
            return fingerprint, json.loads(row["receipt"])
        return fingerprint, None

    def _record(self, db, organization, request_id, fingerprint, receipt):
        db.execute("INSERT INTO review_commands VALUES(?,?,?,?)", (organization, request_id, fingerprint, canonical(receipt)))
        return receipt

    def register_actor(self, organization, actor, roles, enabled=True):
        """Trusted local administration, deliberately not a network authentication API."""
        text(organization, 120)
        text(actor, 120)
        if not roles or set(roles) - {"operator", "reviewer"} or type(enabled) is not bool:
            raise ValueError("Known local operator/reviewer roles required")
        with self.database.transaction() as db:
            now = self._now()
            old = db.execute("SELECT * FROM review_actors WHERE organization=? AND id=?", (organization, actor)).fetchone()
            role_json = canonical(sorted(set(roles)))
            generation = old["generation"] if old else 0
            if old is None or old["roles"] != role_json or old["enabled"] != enabled:
                generation += 1
                db.execute("INSERT OR REPLACE INTO review_actors VALUES(?,?,?,?,?)", (organization, actor, role_json, enabled, generation))
                self._event(db, organization, None, "local_actor_configured", {"actor": actor, "generation": generation}, now)
            return {"actor": actor, "roles": json.loads(role_json), "enabled": enabled, "generation": generation}

    def initialize_actor(self, organization, actor, roles):
        """Create initial local authority once without overriding later administration."""
        text(organization, 120), text(actor, 120)
        if not roles or set(roles) - {"operator", "reviewer"}:
            raise ValueError("Known local operator/reviewer roles required")
        with self.database.transaction() as db:
            if db.execute("SELECT 1 FROM review_actors WHERE organization=? AND id=?", (organization, actor)).fetchone() is None:
                db.execute("INSERT INTO review_actors VALUES(?,?,?,?,?)", (organization, actor, canonical(sorted(set(roles))), True, 1))
                self._event(db, organization, None, "local_actor_configured", {"actor": actor, "generation": 1}, self._now())

    def activate(self, organization, actor, request_id, pack, policy):
        with self.database.transaction() as db:
            now = self._now()
            self._actor(db, organization, actor, "operator")
            payload = {"pack": pack, "policy": asdict(policy)}
            fingerprint, cached = self._cached(db, organization, actor, request_id, "activate_evidence", payload)
            if cached:
                return cached
            validate_fact_pack(pack, datetime.fromtimestamp(now, timezone.utc).date())
            old = db.execute("SELECT * FROM review_authorities WHERE organization=?", (organization,)).fetchone()
            epoch = old["evidence_epoch"] if old else 0
            if old is None or old["pack"] != canonical(pack) or old["policy"] != canonical(asdict(policy)):
                epoch += 1
                db.execute("INSERT OR REPLACE INTO review_authorities VALUES(?,?,?,?,?)",
                    (organization, epoch, old["audience_epoch"] if old else 0, canonical(pack), canonical(asdict(policy))))
                self._event(db, organization, None, "evidence_activated", {"actor": actor, "evidence_epoch": epoch, "fact_pack_id": fact_pack_id(pack), "policy_id": policy.id}, now)
            return self._record(db, organization, request_id, fingerprint, {"kind": "evidence_activated", "actor": actor, "evidence_epoch": epoch, "fact_pack_id": fact_pack_id(pack)})

    def _run_ready(self, db, organization, case):
        run = scoped_run(db, organization, case["run_id"])
        if run["status"] not in {"waiting", "succeeded"}:
            raise Conflict("Source run is cancelled, failed or has not reached review")

    def _new_subject(self, db, organization, case_id, revision, draft, authority, now):
        proposal = subject(case_id, revision, draft, authority)
        db.execute("INSERT INTO review_subjects VALUES(?,?,?,?,?,?)",
                   (organization, proposal["id"], case_id, revision, canonical(proposal), now))
        db.execute("UPDATE review_cases SET current_subject=? WHERE organization=? AND id=?", (proposal["id"], organization, case_id))
        return proposal

    def open_case(self, organization, run_id, actor):
        with self.database.transaction() as db:
            now = self._now()
            self._actor(db, organization, actor, "operator")
            case_id = "case_" + digest({"organization": organization, "run_id": run_id})
            existing = db.execute("SELECT * FROM review_cases WHERE organization=? AND id=?", (organization, case_id)).fetchone()
            if existing:
                return {"case_id": case_id, "subject_id": existing["current_subject"]}
            run = scoped_run(db, organization, run_id)
            if run["status"] not in {"waiting", "succeeded"}:
                raise Conflict("Source run must reach its review checkpoint first")
            outputs = [json.loads(r[0]) for r in db.execute("SELECT output FROM tasks WHERE run_id=? AND output IS NOT NULL ORDER BY position", (run_id,))]
            drafts = [output["draft_id"] for output in outputs if output.get("draft_id")]
            if not drafts:
                raise Conflict("Source run has no committed draft")
            authority = self._authority(db, organization)
            # Opening records a proposal, including a blocked one that needs a
            # rebuild. Only approval and acceptance can grant bounded authority.
            draft = self._bundle(db, organization, drafts[-1])[0]
            db.execute("INSERT INTO review_cases VALUES(?,?,?,?)", (organization, case_id, run_id, ""))
            proposal = self._new_subject(db, organization, case_id, 1, draft, authority, now)
            self._event(db, organization, case_id, "review_opened", {"actor": actor, "subject_id": proposal["id"]}, now)
            return {"case_id": case_id, "subject_id": proposal["id"]}

    def _latest(self, db, organization, case_id, subject_id):
        row = db.execute("SELECT payload FROM review_decisions WHERE organization=? AND case_id=? AND subject_id=? ORDER BY sequence DESC LIMIT 1",
                         (organization, case_id, subject_id)).fetchone()
        return json.loads(row[0]) if row else None

    def _approval_reasons(self, db, organization, case, proposal, authority, approval, now):
        reasons = current_reasons(proposal, authority)
        if approval is None or approval.get("decision") != "approve":
            return reasons + ["No approval recorded for this exact subject"]
        if approval["subject_id"] != case["current_subject"]:
            reasons.append("Approval belongs to a superseded subject")
        latest = self._latest(db, organization, case["id"], proposal["id"])
        if latest is None or latest["id"] != approval["id"]:
            reasons.append("A later review decision supersedes this approval")
        if now < approval["at"] or now >= approval["expires_at"]:
            reasons.append("Approval expired or is not yet valid")
        reviewer = db.execute("SELECT * FROM review_actors WHERE organization=? AND id=?", (organization, approval["actor"])).fetchone()
        if (reviewer is None or not reviewer["enabled"] or "reviewer" not in json.loads(reviewer["roles"])
                or reviewer["generation"] != approval["actor_generation"]):
            reasons.append("Reviewer authority changed")
        if db.execute("SELECT 1 FROM review_revocations WHERE organization=? AND approval_id=?", (organization, approval["id"])).fetchone():
            reasons.append("Approval was revoked")
        return reasons

    def view(self, organization, case_id):
        with self.database.connect() as db:
            db.execute("BEGIN")
            now = self._now()
            case = self._case(db, organization, case_id)
            proposal = self._subject(db, organization, case["current_subject"])
            authority = self._authority(db, organization)
            draft = self._bundle(db, organization, proposal["draft_id"])[0]
            approval = self._latest(db, organization, case_id, proposal["id"])
            reasons = self._approval_reasons(db, organization, case, proposal, authority, approval, now)
            candidate_reasons = current_reasons(proposal, authority)
            try:
                self._run_ready(db, organization, case)
                self._validate(db, organization, case, proposal["draft_id"], authority, now)
            except (ValueError, NotFound) as error:
                candidate_reasons.append(str(error))
            reasons.extend(candidate_reasons)
            job = db.execute("SELECT payload FROM simulated_agency_jobs WHERE organization=? AND case_id=?", (organization, case_id)).fetchone()
            revisions = [json.loads(r[0]) for r in db.execute("SELECT payload FROM review_subjects WHERE organization=? AND case_id=? ORDER BY revision", (organization, case_id))]
            changes = None
            if len(revisions) > 1:
                previous = self._bundle(db, organization, revisions[-2]["draft_id"])[0]
                before = {r["business_id"] for r in csv.DictReader(io.StringIO(previous.mailing_csv))}
                after = {r["business_id"] for r in csv.DictReader(io.StringIO(draft.mailing_csv))}
                changes = {"previous_subject": revisions[-2]["id"], "added_count": len(after - before),
                    "removed_count": len(before - after), "added_preview": sorted(after - before)[:20],
                    "removed_preview": sorted(before - after)[:20], "preview_limit": 20,
                    "copy_changed": previous.manifest["creatives"] != draft.manifest["creatives"],
                    "cost_delta_pence": draft.manifest["variable_cost_pence"] - previous.manifest["variable_cost_pence"]}
            events = [dict(r) | {"payload": json.loads(r["payload"])} for r in db.execute(
                "SELECT * FROM review_events WHERE organization=? AND (case_id=? OR case_id IS NULL) ORDER BY sequence", (organization, case_id))]
            return {"case_id": case_id, "run_id": case["run_id"], "subject": proposal, "authority": authority,
                "manifest": draft.manifest, "approval": approval, "approval_valid": not reasons,
                "candidate_valid": not candidate_reasons, "changes": changes,
                "blocked_reasons": list(dict.fromkeys(reasons)), "handoff": json.loads(job[0]) if job else None,
                "suppressions": sorted(self._suppressed(db, organization)), "revisions": revisions,
                "events": events, "as_of": now, "mode": "local_synthetic_review_not_lender_approval"}

    def decide(self, organization, case_id, expected_subject, actor, decision, request_id, reason, ttl_seconds=86400):
        text(reason)
        if decision not in {"approve", "reject"} or type(ttl_seconds) is not int or ttl_seconds <= 0:
            raise ValueError("Choose approve/reject and a positive integer lifetime")
        with self.database.transaction() as db:
            now = self._now()
            reviewer = self._actor(db, organization, actor, "reviewer")
            payload = {"case_id": case_id, "subject_id": expected_subject, "decision": decision, "reason": reason, "ttl_seconds": ttl_seconds}
            fingerprint, cached = self._cached(db, organization, actor, request_id, "review_decision", payload)
            if cached:
                return cached
            case = self._case(db, organization, case_id)
            if case["current_subject"] != expected_subject:
                raise Conflict("Review refers to a superseded subject")
            if db.execute("SELECT 1 FROM simulated_agency_jobs WHERE organization=? AND case_id=?", (organization, case_id)).fetchone():
                raise Conflict("This case already has an accepted simulated handoff")
            self._run_ready(db, organization, case)
            proposal = self._subject(db, organization, expected_subject)
            authority = self._authority(db, organization)
            policy = ReviewPolicy(**authority["policy"])
            if ttl_seconds > policy.max_approval_seconds:
                raise ValueError("Approval lifetime exceeds the active policy")
            if decision == "approve":
                if current_reasons(proposal, authority):
                    raise Conflict("Current evidence changed; publish a refreshed subject before approving")
                self._validate(db, organization, case, proposal["draft_id"], authority, now)
            receipt = {"kind": "review_decision", "id": "decision_" + uuid4().hex, "case_id": case_id,
                "subject_id": expected_subject, "actor": actor, "actor_generation": reviewer["generation"],
                "decision": decision, "reason": reason, "at": now, "expires_at": now + ttl_seconds,
                "purpose": "simulated_agency_handoff"}
            if decision == "approve":
                review_end = datetime.fromisoformat(authority["pack"]["review_by"]).replace(tzinfo=timezone.utc) + timedelta(days=1)
                receipt["expires_at"] = min(receipt["expires_at"], review_end.timestamp())
            timestamp(receipt["expires_at"])
            db.execute("INSERT INTO review_decisions(organization,id,case_id,subject_id,payload) VALUES(?,?,?,?,?)",
                       (organization, receipt["id"], case_id, expected_subject, canonical(receipt)))
            self._event(db, organization, case_id, "review_" + decision, receipt, now)
            return self._record(db, organization, request_id, fingerprint, receipt)

    def revoke(self, organization, case_id, approval_id, actor, request_id, reason):
        text(reason)
        with self.database.transaction() as db:
            now = self._now()
            self._actor(db, organization, actor, "reviewer")
            fingerprint, cached = self._cached(db, organization, actor, request_id, "revoke", {"case_id": case_id, "approval_id": approval_id, "reason": reason})
            if cached:
                return cached
            row = db.execute("SELECT 1 FROM review_decisions WHERE organization=? AND case_id=? AND id=?", (organization, case_id, approval_id)).fetchone()
            if row is None:
                raise NotFound("Review decision not found in this case")
            db.execute("INSERT OR IGNORE INTO review_revocations VALUES(?,?,?,?,?)", (organization, approval_id, actor, reason, now))
            receipt = {"kind": "approval_revoked", "case_id": case_id, "approval_id": approval_id, "actor": actor, "at": now}
            self._event(db, organization, case_id, "approval_revoked", receipt, now)
            return self._record(db, organization, request_id, fingerprint, receipt)

    def suppress(self, organization, actor, request_id, business_id, reason):
        text(business_id, 160)
        text(reason)
        with self.database.transaction() as db:
            now = self._now()
            self._actor(db, organization, actor, "operator")
            fingerprint, cached = self._cached(db, organization, actor, request_id, "suppress", {"business_id": business_id, "reason": reason})
            if cached:
                return cached
            authority = self._authority(db, organization)
            existing = db.execute("SELECT 1 FROM review_suppressions WHERE organization=? AND business_id=?", (organization, business_id)).fetchone()
            if not existing:
                db.execute("INSERT INTO review_suppressions VALUES(?,?,?,?,?)", (organization, business_id, actor, reason, now))
                db.execute("UPDATE review_authorities SET audience_epoch=audience_epoch+1 WHERE organization=?", (organization,))
                self._event(db, organization, None, "suppression_added", {"business_id": business_id, "actor": actor}, now)
            return self._record(db, organization, request_id, fingerprint, {"kind": "suppression_recorded", "actor": actor, "business_id": business_id,
                "audience_epoch": authority["audience_epoch"] + (0 if existing else 1), "at": now})

    def prepare(self, organization, case_id, expected_subject, actor, request_id):
        with self.database.transaction() as db:
            self._now()
            self._actor(db, organization, actor, "operator")
            _, cached = self._cached(db, organization, actor, request_id, "refresh", {"case_id": case_id, "expected_subject": expected_subject})
            if cached:
                return {"receipt": cached}
            case = self._case(db, organization, case_id)
            if case["current_subject"] != expected_subject:
                raise Conflict("A different review subject is current")
            self._run_ready(db, organization, case)
            if db.execute("SELECT 1 FROM simulated_agency_jobs WHERE organization=? AND case_id=?", (organization, case_id)).fetchone():
                raise Conflict("Accepted simulated jobs are immutable; create a new campaign")
            proposal = self._subject(db, organization, expected_subject)
            return {"subject": proposal, "authority": self._authority(db, organization), "suppressions": sorted(self._suppressed(db, organization))}

    def propose(self, organization, case_id, expected_subject, draft_id, actor, request_id, audience_epoch, evidence_epoch, kind="replace"):
        with self.database.transaction() as db:
            now = self._now()
            self._actor(db, organization, actor, "operator")
            payload = {"case_id": case_id, "expected_subject": expected_subject}
            if kind == "replace":
                payload["draft_id"] = draft_id
            if kind not in {"replace", "refresh"}:
                raise ValueError("Unknown proposal operation")
            fingerprint, cached = self._cached(db, organization, actor, request_id, kind, payload)
            if cached:
                return cached
            case = self._case(db, organization, case_id)
            if case["current_subject"] != expected_subject:
                raise Conflict("A different review subject is current")
            if db.execute("SELECT 1 FROM simulated_agency_jobs WHERE organization=? AND case_id=?", (organization, case_id)).fetchone():
                raise Conflict("Accepted simulated jobs are immutable; create a new campaign")
            self._run_ready(db, organization, case)
            old = self._subject(db, organization, expected_subject)
            authority = self._authority(db, organization)
            if (audience_epoch, evidence_epoch) != (authority["audience_epoch"], authority["evidence_epoch"]):
                raise Conflict("Evidence changed during preparation; retry with a new request ID")
            draft = self._validate(db, organization, case, draft_id, authority, now)
            original = self._bundle(db, organization, old["draft_id"])[0]
            if draft.manifest["brief"]["campaign_id"] != original.manifest["brief"]["campaign_id"]:
                raise Conflict("Replacement belongs to a different campaign")
            proposal = self._new_subject(db, organization, case_id, old["revision"] + 1, draft, authority, now)
            receipt = {"kind": "proposal_published", "actor": actor, "case_id": case_id, "subject_id": proposal["id"], "draft_id": draft_id, "at": now}
            self._event(db, organization, case_id, "proposal_revised", receipt | {"previous_subject": expected_subject}, now)
            return self._record(db, organization, request_id, fingerprint, receipt)

    def handoff(self, organization, case_id, approval_id, actor, request_id):
        with self.database.transaction() as db:
            now = self._now()
            operator = self._actor(db, organization, actor, "operator")
            fingerprint, cached = self._cached(db, organization, actor, request_id, "handoff", {"case_id": case_id, "approval_id": approval_id})
            if cached:
                return cached
            case = self._case(db, organization, case_id)
            existing = db.execute("SELECT payload FROM simulated_agency_jobs WHERE organization=? AND case_id=?", (organization, case_id)).fetchone()
            if existing:
                receipt = json.loads(existing[0])
                if receipt["approval_id"] != approval_id:
                    raise Conflict("This case already has a different accepted job")
                return self._record(db, organization, request_id, fingerprint, receipt)
            self._run_ready(db, organization, case)
            proposal = self._subject(db, organization, case["current_subject"])
            authority = self._authority(db, organization)
            row = db.execute("SELECT payload FROM review_decisions WHERE organization=? AND case_id=? AND id=?", (organization, case_id, approval_id)).fetchone()
            if row is None:
                raise NotFound("Approval not found in this case")
            approval = json.loads(row[0])
            reasons = self._approval_reasons(db, organization, case, proposal, authority, approval, now)
            if reasons:
                raise Conflict("Simulated handoff blocked: " + "; ".join(reasons))
            draft = self._validate(db, organization, case, proposal["draft_id"], authority, now)
            receipt = {"kind": "simulated_agency_acceptance", "mode": "SYNTHETIC_NO_PRINT_NO_SEND", "id": "fake_job_" + digest({"case": case_id, "approval": approval_id}),
                "actor": actor, "actor_generation": operator["generation"], "case_id": case_id,
                "approval_id": approval_id, "subject_id": proposal["id"], "draft_id": draft.id,
                "mailing_sha256": draft.manifest["mailing_sha256"], "assignments_sha256": draft.manifest["assignments_sha256"],
                "recipients": draft.manifest["counts"]["mailed"], "accepted_at": now, "destination": "local_simulated_agency"}
            db.execute("INSERT INTO simulated_agency_jobs VALUES(?,?,?,?,?,?)", (organization, case_id, receipt["id"], approval_id, proposal["id"], canonical(receipt)))
            self._event(db, organization, case_id, "simulated_handoff_accepted", receipt, now)
            return self._record(db, organization, request_id, fingerprint, receipt)
