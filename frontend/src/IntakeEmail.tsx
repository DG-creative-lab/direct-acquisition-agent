import { useEffect, useId, useRef, useState } from "react";
import {
  dispatchEmail,
  downloadEmail,
  emailEligibility,
  emailView,
  EmailRejected,
  pendingEmail,
  queueEmail,
} from "./intake-email-api";
import type {
  EmailEligibility,
  EmailOperation,
  EmailPayload,
  EmailReceipt,
  EmailView,
  PendingEmail,
} from "./intake-email-api";

type Props = {
  contextRequest: string;
  storeId: string;
  sourceVersion: string;
  active: boolean;
  enabled: boolean;
  disabled: boolean;
  onLock: (v: boolean) => void;
};
export default function IntakeEmail({
  contextRequest,
  storeId,
  sourceVersion,
  active,
  enabled,
  disabled,
  onLock,
}: Props) {
  const id = useId(),
    [preview, setPreview] = useState<EmailEligibility | null>(null),
    [view, setView] = useState<EmailView | null>(null);
  const [pending, setPending] = useState<PendingEmail | null>(null),
    [storageError, setStorageError] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0);
  const [note, setNote] = useState(""),
    [consent, setConsent] = useState(""),
    [reason, setReason] = useState(""),
    [reviewConsent, setReviewConsent] = useState("");
  const errorRef = useRef<HTMLParagraphElement>(null),
    selection = `${storeId}:${contextRequest}:${sourceVersion}`;
  const readGeneration = useRef(0);
  const current = useRef(selection);
  current.current = selection;
  const inputConsent = JSON.stringify({ preview: preview?.id, note });
  const decisionConsent = JSON.stringify({ subject: view?.subject.id, reason });
  useEffect(() => {
    try {
      setPending(pendingEmail());
    } catch (e) {
      setStorageError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    onLock(busy || !!pending || !!storageError);
  }, [busy, pending, storageError, onLock]);
  useEffect(() => {
    setPreview(null);
    setView(null);
    setConsent("");
    setReviewConsent("");
    if (!active || !enabled || !storeId || !contextRequest) return;
    const controller = new AbortController();
    const generation = ++readGeneration.current;
    emailEligibility(contextRequest, controller.signal)
      .then(async (p) => {
        if (controller.signal.aborted || generation !== readGeneration.current)
          return;
        if (p.store_id !== storeId)
          throw new Error(
            "The email workspace store changed. Reload before proceeding.",
          );
        setPreview(p);
        if (p.original_email_request_id) {
          const v = await emailView(
            p.original_email_request_id,
            controller.signal,
          );
          if (
            !controller.signal.aborted &&
            generation === readGeneration.current &&
            v.store_id === storeId
          )
            setView(v);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted && generation === readGeneration.current)
          setError(e.message);
      });
    return () => controller.abort();
  }, [selection, active, enabled, attempt]);
  async function send(command: PendingEmail) {
    const started = current.current;
    ++readGeneration.current;
    setBusy(true);
    setError("");
    try {
      const result = await dispatchEmail(command);
      setPending(null);
      if (
        current.current !== started ||
        command.context_request_id !== contextRequest ||
        command.store_id !== storeId
      )
        return;
      const request =
        command.operation === "prepare"
          ? command.payload.request_id
          : (command.payload as { preparation_request_id: string })
              .preparation_request_id;
      const next = await emailView(request);
      if (current.current === started) setView(next);
      if (command.operation === "export" && current.current === started) {
        const r = result as EmailReceipt;
        await downloadEmail(
          command.payload.request_id,
          r.value.subject_id!,
          command.store_id,
        );
      }
    } catch (e) {
      if (e instanceof EmailRejected) {
        setPending(null);
        setAttempt((v) => v + 1);
      }
      setError((e as Error).message);
      requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      setBusy(false);
    }
  }
  function submit(operation: EmailOperation, payload: EmailPayload) {
    if (!preview || busy || disabled || pending || storageError) return;
    try {
      const c = queueEmail({
        store_id: storeId,
        context_request_id: contextRequest,
        context_fingerprint: preview.context_fingerprint,
        operation,
        payload,
      });
      setPending(c);
      void send(c);
    } catch (e) {
      setStorageError((e as Error).message);
    }
  }
  if (!enabled && !pending && !storageError) return null;
  return (
    <section aria-labelledby={id + "-heading"}>
      <h3 id={id + "-heading"}>Email preparation, review and export</h3>
      <p>
        Use your selected company facts in a synthetic email batch. One to six
        fictional contacts have explicit demonstration permissions. They are not
        matched to your requested audience. No live models or email delivery.
      </p>
      {(error || storageError) && (
        <p role="alert" tabIndex={-1} ref={errorRef}>
          {storageError || error}
        </p>
      )}
      {pending && (
        <div role="status">
          <p>
            The original email command is unresolved. Reconcile it before
            another command.
          </p>
          <button
            type="button"
            className="button secondary"
            disabled={busy || !storeId}
            onClick={() => void send(pending)}
          >
            Retry original email command
          </button>
        </div>
      )}
      {preview && preview.blockers.length > 0 && (
        <ul>
          {preview.blockers.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
      {preview &&
        !view &&
        !preview.original_email_request_id &&
        preview.blockers.length === 0 && (
          <form
            method="post"
            action="/api/intake/emails/prepare"
            aria-labelledby={id + "-heading"}
            onSubmit={(e) => {
              e.preventDefault();
              if (consent !== inputConsent) return;
              submit("prepare", {
                request_id: crypto.randomUUID(),
                context_request_id: contextRequest,
                preview_id: preview.id,
                evidence: {
                  reference_ids: preview.references.map((r) => r.id),
                  checked_on: preview.checked_on,
                  review_days: 1,
                  note,
                  confirmed_official_sources: true,
                  confirmed_exact_wording: true,
                },
                confirmed_synthetic_preparation: true,
              });
            }}
          >
            <fieldset
              disabled={disabled || busy || !!pending || !!storageError}
            >
              <legend>Review the selected company evidence</legend>
              <p>{preview.selected_inputs.description}</p>
              <ul>
                {preview.selected_inputs.claims.map((c) => (
                  <li key={c.id}>
                    {c.statement} {c.qualification}
                  </li>
                ))}
              </ul>
              <p>
                CTA: {preview.selected_inputs.cta?.wording} (
                {preview.selected_inputs.cta?.url})
              </p>
              <ul>
                {preview.references.map((r) => (
                  <li key={r.id}>
                    <a href={r.url} target="_blank" rel="noopener noreferrer">
                      {r.url}
                    </a>
                  </li>
                ))}
              </ul>
              <label htmlFor={id + "-note"}>
                Email source review note (required)
              </label>
              <textarea
                id={id + "-note"}
                name="source_note"
                required
                maxLength={1000}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <p>
                Prepare {preview.settings.size} fictional emails with fixed
                framing. The source review expires within one day and grants no
                export approval.
              </p>
              <div className="preparation-choice">
                <input
                  id={id + "-source"}
                  type="checkbox"
                  name="source_confirmed"
                  required
                  checked={consent === inputConsent}
                  onChange={(e) =>
                    setConsent(e.target.checked ? inputConsent : "")
                  }
                />
                <label htmlFor={id + "-source"}>
                  I checked the exact selected wording, qualifications, official
                  sources and CTA. Prepare synthetic emails only.
                </label>
              </div>
              <button type="submit" className="button primary">
                Prepare synthetic email batch
              </button>
            </fieldset>
          </form>
        )}
      {view && (
        <article className="intake-plan-result">
          <h4>Exact synthetic email batch</h4>
          <p>
            Fictional recipients and sender. Contacts are not matched to your
            audience. Fixed authored framing; no independent fact verification
            or live generation.
          </p>
          <p>
            Subject: {view.subject.id}. Planned synthetic cost:{" "}
            {view.batch.cost_minor} GBP minor units.
          </p>
          <ul>
            {view.review_required.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
          <button
            type="button"
            className="button secondary"
            disabled={busy || !!pending}
            onClick={() => setAttempt((v) => v + 1)}
          >
            Refresh email review
          </button>
          {view.batch.content.rows.map((row) => (
            <details key={row.id}>
              <summary>
                {row.email.subject} / {row.email.to}
              </summary>
              <p>
                From: {row.email.from_name} &lt;{row.email.from}&gt;. Reply-to:{" "}
                {row.email.reply_to}.
              </p>
              <pre>{row.email.text}</pre>
              <details>
                <summary>Exact email HTML</summary>
                <pre>{row.email.html}</pre>
              </details>
            </details>
          ))}
          <p role="status">
            {view.approval_valid
              ? "Approved for this exact synthetic export only."
              : "No current export approval. Sending remains unavailable."}
          </p>
          <form
            method="post"
            action="/api/intake/emails/decision"
            aria-labelledby={id + "-decision-heading"}
            onSubmit={(e) => {
              e.preventDefault();
              if (reviewConsent !== decisionConsent) return;
              submit("decision", {
                request_id: crypto.randomUUID(),
                preparation_request_id: view.request_id,
                subject_id: view.subject.id,
                decision: "approve",
                reason,
                ttl_seconds: 86400,
              });
            }}
          >
            <fieldset
              disabled={
                disabled ||
                busy ||
                !!pending ||
                !!storageError ||
                !view.review_ready
              }
            >
              <legend id={id + "-decision-heading"}>
                Review the complete email package
              </legend>
              <label htmlFor={id + "-reason"}>
                Email approval reason (required)
              </label>
              <textarea
                id={id + "-reason"}
                name="approval_reason"
                required
                maxLength={1000}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <div className="preparation-choice">
                <input
                  id={id + "-review"}
                  name="exact_review"
                  type="checkbox"
                  required
                  checked={reviewConsent === decisionConsent}
                  onChange={(e) =>
                    setReviewConsent(e.target.checked ? decisionConsent : "")
                  }
                />
                <label htmlFor={id + "-review"}>
                  I reviewed every exact recipient, subject, text, HTML,
                  qualification and opt-out field. Approve this synthetic export
                  only.
                </label>
              </div>
              <button type="submit" className="button primary">
                Approve exact email export
              </button>
              <button
                type="button"
                className="button secondary"
                onClick={() =>
                  submit("decision", {
                    request_id: crypto.randomUUID(),
                    preparation_request_id: view.request_id,
                    subject_id: view.subject.id,
                    decision: "reject",
                    reason:
                      reason ||
                      "Rejected the displayed synthetic email package.",
                    ttl_seconds: 86400,
                  })
                }
              >
                Reject email package
              </button>
            </fieldset>
          </form>
          {view.approval && (
            <button
              type="button"
              className="button secondary"
              disabled={disabled || busy || !!pending || !!storageError}
              onClick={() =>
                submit("revoke", {
                  request_id: crypto.randomUUID(),
                  preparation_request_id: view.request_id,
                  approval_id: view.approval!.id,
                  reason: "Revoked the exact synthetic email export approval.",
                })
              }
            >
              Revoke email export approval
            </button>
          )}
          <button
            type="button"
            className="button primary"
            disabled={
              disabled ||
              busy ||
              !!pending ||
              !!storageError ||
              !view.approval_valid
            }
            onClick={() =>
              submit("export", {
                request_id: crypto.randomUUID(),
                preparation_request_id: view.request_id,
                subject_id: view.subject.id,
                approval_id: view.approval!.id,
              })
            }
          >
            Download reviewed synthetic emails
          </button>
        </article>
      )}
    </section>
  );
}
