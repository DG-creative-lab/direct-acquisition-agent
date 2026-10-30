import { useState } from "react";
import {
  Check,
  ChevronRight,
  FileCheck2,
  Loader2,
  ShieldCheck,
  X,
  AlertTriangle,
  RefreshCw,
  LockKeyhole,
  Send,
} from "lucide-react";
import type { Act, State } from "./api";
import { date, money } from "./api";
import { Badge, Modal } from "./ui";

export default function ReviewPanel({
  state,
  busy,
  act,
  error,
  onEvidence,
  allowHandoff = true,
  readOnly = false,
}: {
  state: State;
  busy: boolean;
  act: Act;
  error: string;
  onEvidence: () => void;
  allowHandoff?: boolean;
  readOnly?: boolean;
}) {
  const review = state.review!;
  const [decision, setDecision] = useState<null | {
      kind: "approve" | "reject" | "revoke";
      subject: string;
      approval: string | undefined;
      revision: number;
    }>(null),
    [reason, setReason] = useState("");
  const begin = (kind: "approve" | "reject" | "revoke") => {
    setReason("");
    setDecision({
      kind,
      subject: review.subject.id,
      approval: review.approval?.id,
      revision: review.subject.revision,
    });
  };
  const submit = async () => {
    if (!decision || !reason.trim() || readOnly) return;
    const payload =
      decision.kind === "revoke"
        ? { approval_id: decision.approval, reason: reason.trim() }
        : { subject_id: decision.subject, reason: reason.trim() };
    if (await act(decision.kind, payload)) setDecision(null);
  };
  const checks = [
    { label: "Audience and artifact integrity", good: review.candidate_valid },
    { label: "Product facts and review window", good: review.candidate_valid },
    {
      label: "Exact revision reviewed",
      good: review.approval_valid || !!review.handoff,
    },
  ];
  return (
    <aside className="review-panel">
      <div className="review-heading">
        <span className="review-icon">
          <FileCheck2 size={19} />
        </span>
        <div>
          <h3>Review & approval</h3>
          <p>Revision {review.subject.revision}</p>
        </div>
        <Badge tone={review.approval_valid ? "green" : "neutral"}>
          {review.handoff
            ? "Accepted"
            : review.approval_valid
              ? "Approved"
              : "Pending"}
        </Badge>
      </div>
      <div className="review-intro">
        A decision applies to the exact audience, copy and evidence in this
        revision.
      </div>
      <div className="check-list">
        {checks.map((c) => (
          <div key={c.label}>
            <span className={c.good ? "check-circle" : "check-circle pending"}>
              {c.good ? <Check size={11} /> : <span />}
            </span>
            <span>{c.label}</span>
          </div>
        ))}
      </div>
      {!review.candidate_valid && (
        <div className="review-warning">
          <AlertTriangle size={16} />
          <div>
            <strong>Review is blocked</strong>
            <p>
              {review.blocked_reasons
                .filter((r) => !r.startsWith("No approval"))
                .join(". ")}
            </p>
            {review.blocked_reasons.some((r) =>
              r.includes(
                "Conversation changed after this campaign was prepared",
              ),
            ) && (
              <p>
                Return to the assistant and prepare a campaign from the current
                conversation.
              </p>
            )}
            {!review.handoff &&
              !review.blocked_reasons.some((r) =>
                r.includes(
                  "Conversation changed after this campaign was prepared",
                ),
              ) && (
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() =>
                    act("refresh", { subject_id: review.subject.id })
                  }
                >
                  <RefreshCw size={13} />
                  Rebuild draft
                </button>
              )}
          </div>
        </div>
      )}
      {review.changes && (
        <div className="revision-change">
          <strong>Revision changes</strong>
          <p>
            {review.changes.removed_count} recipients removed ·{" "}
            {review.changes.added_count} added
            <br />
            Copy {review.changes.copy_changed ? "changed" : "unchanged"} · Cost{" "}
            {money(review.changes.cost_delta_pence)}
          </p>
        </div>
      )}
      <dl className="review-facts">
        <dt>Review scope</dt>
        <dd>Simulated handoff</dd>
        <dt>Evidence checked</dt>
        <dd>{review.authority.pack.checked_on}</dd>
        <dt>Review due</dt>
        <dd>{review.authority.pack.review_by}</dd>
        <dt>Reviewer</dt>
        <dd>Local reviewer</dd>
      </dl>
      <button className="evidence-button" onClick={onEvidence}>
        <ShieldCheck size={16} />
        <span>Inspect product evidence</span>
        <ChevronRight size={15} />
      </button>
      {review.approval && (
        <div className="decision-record">
          <Badge
            tone={review.approval.decision === "approve" ? "green" : "amber"}
          >
            {review.approval.decision === "approve"
              ? "Approval recorded"
              : "Changes requested"}
          </Badge>
          <p>{review.approval.reason}</p>
          {review.approval.decision === "approve" && (
            <small>Expires {date(review.approval.expires_at)}</small>
          )}
          {!review.approval_valid && !review.handoff && (
            <p className="invalid-approval">
              This decision does not authorize a new handoff.
            </p>
          )}
        </div>
      )}
      {review.handoff ? (
        <div className="accepted-note">
          <Check size={17} />
          <strong>Accepted by local simulator</strong>
          <p>
            {review.handoff.recipients} recipients ·{" "}
            {date(review.handoff.accepted_at)}
            <br />
            Historical acceptance. Nothing was printed or sent.
          </p>
        </div>
      ) : (
        <div className="review-actions">
          <button
            className="button primary wide"
            disabled={busy || readOnly || !review.candidate_valid}
            onClick={() => begin("approve")}
          >
            <Check size={16} />
            Approve this revision
          </button>
          <button
            className="button secondary wide"
            disabled={busy || readOnly}
            onClick={() => begin("reject")}
          >
            Request changes
          </button>
          {review.approval_valid && (
            <>
              {allowHandoff && (
                <button
                  className="button dark wide"
                  disabled={busy}
                  onClick={() =>
                    act("handoff", { approval_id: review.approval!.id })
                  }
                >
                  <Send size={15} />
                  Simulate agency handoff
                </button>
              )}
              <button
                className="text-button"
                disabled={busy || readOnly}
                onClick={() => begin("revoke")}
              >
                Revoke approval
              </button>
            </>
          )}
        </div>
      )}
      <div className="authority-note">
        <LockKeyhole size={13} />
        <span>
          Configured local identities, without hosted authentication. Approval
          never permits real sending.
        </span>
      </div>
      <details className="exact-subject">
        <summary>
          Exact approval subject
          <ChevronRight size={13} />
        </summary>
        <code>{review.subject.id}</code>
        <small>Draft identity</small>
        <code>{review.subject.draft_id}</code>
        <small>Audience snapshot</small>
        <code>{review.subject.snapshot_id}</code>
      </details>
      {decision && (
        <Modal
          label="decision-title"
          busy={busy}
          onClose={() => setDecision(null)}
        >
          <button
            className="modal-close icon-button"
            aria-label="Close decision"
            disabled={busy}
            onClick={() => setDecision(null)}
          >
            <X size={18} />
          </button>
          <span className="modal-icon">
            <FileCheck2 size={24} />
          </span>
          <h2 id="decision-title">
            {decision.kind === "approve"
              ? "Approve this revision"
              : decision.kind === "reject"
                ? "Request changes"
                : "Revoke approval"}
          </h2>
          <p>
            Revision {decision.revision}.{" "}
            {decision.kind === "approve"
              ? "Confirm that you reviewed the audience, all copy variants and current evidence. This permits only a local simulated handoff."
              : "Record why this decision is needed."}
          </p>
          <label className="form-label" htmlFor="decision-reason">
            Review reason
          </label>
          <textarea
            autoFocus
            id="decision-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
            placeholder="What did you review or what needs to change?"
            disabled={busy}
          />
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="subject-preview">
            <span>BOUND SUBJECT</span>
            <code>{decision.subject}</code>
          </div>
          <button
            className="button primary wide"
            disabled={busy || readOnly || !reason.trim()}
            onClick={submit}
          >
            {busy ? (
              <Loader2 className="spin" size={15} />
            ) : (
              <Check size={15} />
            )}
            Record{" "}
            {decision.kind === "approve"
              ? "approval"
              : decision.kind === "reject"
                ? "rejection"
                : "revocation"}
          </button>
        </Modal>
      )}
    </aside>
  );
}
