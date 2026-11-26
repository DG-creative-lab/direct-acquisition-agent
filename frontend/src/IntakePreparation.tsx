import { useEffect, useId, useRef, useState } from "react";
import {
  dispatchPreparation,
  eligibility,
  pendingPreparation,
  preparationReceipt,
  PreparationRejected,
  queuePreparation,
} from "./intake-preparation-api";
import type {
  Eligibility,
  PendingPreparation,
  PreparedIntake,
} from "./intake-preparation-api";

type Props = {
  contextRequest: string;
  storeId: string;
  sourceVersion: string;
  active: boolean;
  disabled: boolean;
  enabled?: boolean;
  onLock: (value: boolean) => void;
};
export default function IntakePreparation({
  contextRequest,
  storeId,
  sourceVersion,
  active,
  disabled,
  enabled = true,
  onLock,
}: Props) {
  const id = useId();
  const [preview, setPreview] = useState<Eligibility | null>(null),
    [result, setResult] = useState<PreparedIntake | null>(null);
  const [pending, setPending] = useState<PendingPreparation | null>(null),
    [storageError, setStorageError] = useState("");
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [attempt, setAttempt] = useState(0);
  const [note, setNote] = useState(""),
    [consent, setConsent] = useState("");
  const errorRef = useRef<HTMLParagraphElement>(null);
  const selected = `${storeId}:${contextRequest}:${sourceVersion}`;
  const current = useRef(selected);
  current.current = selected;
  const evidenceKey = JSON.stringify({ preview: preview?.id, note });
  useEffect(() => {
    try {
      setPending(pendingPreparation());
    } catch (e) {
      setStorageError((e as Error).message);
    }
  }, []);
  useEffect(() => {
    onLock(busy || !!pending || !!storageError);
  }, [busy, pending, storageError, onLock]);
  useEffect(() => {
    setPreview(null);
    setResult(null);
    setConsent("");
    if (!active || !enabled || !contextRequest || !storeId) return;
    const controller = new AbortController();
    eligibility(contextRequest, controller.signal)
      .then(async (p) => {
        if (controller.signal.aborted) return;
        if (p.store_id !== storeId)
          throw new Error(
            "The workspace store changed. Reload before preparing.",
          );
        setPreview(p);
        if (p.original_preparation_request_id) {
          const r = await preparationReceipt(
            p.original_preparation_request_id,
            controller.signal,
          );
          if (
            !controller.signal.aborted &&
            r.store_id === storeId &&
            r.grounding.context_request_id === contextRequest
          )
            setResult(r);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [selected, active, enabled, attempt]);
  async function send(command: PendingPreparation) {
    const atStart = current.current;
    setBusy(true);
    setError("");
    try {
      const value = await dispatchPreparation(command);
      setPending(null);
      if (
        current.current === atStart &&
        command.payload.context_request_id === contextRequest &&
        command.store_id === storeId
      )
        setResult(value);
    } catch (e) {
      if (e instanceof PreparationRejected) {
        setPending(null);
        setAttempt((v) => v + 1);
      }
      setError((e as Error).message);
      requestAnimationFrame(() => errorRef.current?.focus());
    } finally {
      setBusy(false);
    }
  }
  if (!enabled && !pending && !storageError) return null;
  return (
    <section aria-labelledby={id + "-heading"}>
      <h3 id={id + "-heading"}>Preparation eligibility and source review</h3>
      <p>
        Only an explicit source review can make selected wording eligible for
        this fixed synthetic draft. No website is fetched or independently
        verified. No model calls are made.
      </p>
      {(error || storageError) && (
        <p ref={errorRef} tabIndex={-1} role="alert">
          {storageError || error}
        </p>
      )}
      {pending && (
        <div role="status">
          <p>
            The original preparation is unresolved. Keep its request until it is
            reconciled.
          </p>
          <button
            type="button"
            className="button secondary"
            disabled={busy || !storeId}
            onClick={() => void send(pending)}
          >
            Retry original grounded preparation
          </button>
        </div>
      )}
      {!contextRequest && !pending && (
        <p>Save a preparation input review to check eligibility.</p>
      )}
      {preview && (
        <>
          <p>
            Selected company: {preview.selected_inputs.company_name}. Product:{" "}
            {preview.selected_inputs.product_name}.
          </p>
          {preview.blockers.length > 0 ? (
            <ul>
              {preview.blockers.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          ) : (
            <p>
              {result
                ? "Prepared from the original source review. Reopening never renews its validity."
                : "Ready for a separate source evidence review. This status grants no approval."}
            </p>
          )}
          {preview.blockers.length === 0 &&
            !result &&
            !preview.original_preparation_request_id && (
              <form
                method="post"
                action="/api/intake/preparations"
                aria-labelledby={id + "-heading"}
                onSubmit={(event) => {
                  event.preventDefault();
                  if (
                    consent !== evidenceKey ||
                    disabled ||
                    busy ||
                    pending ||
                    storageError
                  )
                    return;
                  try {
                    const command = queuePreparation(preview, {
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
                    setPending(command);
                    void send(command);
                  } catch (e) {
                    setStorageError((e as Error).message);
                  }
                }}
              >
                <fieldset
                  disabled={disabled || busy || !!pending || !!storageError}
                >
                  <legend>
                    Check the exact selected material against its sources
                  </legend>
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
                        <a
                          href={r.url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {r.url}
                        </a>
                      </li>
                    ))}
                  </ul>
                  <div className="intake-field">
                    <label htmlFor={id + "-note"}>
                      Source evidence review note (required)
                    </label>
                    <textarea
                      id={id + "-note"}
                      name="evidence_note"
                      required
                      maxLength={1000}
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                    />
                  </div>
                  <p id={id + "-scope"}>
                    One-day source review, bounded by the input review expiry.
                    Fixed business questions and {preview.settings.size}{" "}
                    synthetic contact rows. The population is not matched to
                    your audience requirements. Live generation, campaign
                    approval and sending remain unavailable.
                  </p>
                  <div className="preparation-choice">
                    <input
                      id={id + "-confirm"}
                      name="confirmed"
                      type="checkbox"
                      required
                      aria-describedby={id + "-scope"}
                      checked={consent === evidenceKey}
                      onChange={(e) =>
                        setConsent(e.target.checked ? evidenceKey : "")
                      }
                    />
                    <label htmlFor={id + "-confirm"}>
                      I checked the official sources, exact selected wording,
                      qualifications and CTA. Prepare this unapproved synthetic
                      fixture.
                    </label>
                  </div>
                  <button type="submit" className="button primary">
                    Prepare grounded synthetic draft
                  </button>
                </fieldset>
              </form>
            )}
        </>
      )}
      {result && (
        <article
          className="intake-plan-result"
          aria-labelledby={id + "-result"}
        >
          <h4 id={id + "-result"}>Unapproved grounded synthetic draft</h4>
          <p role="status">
            {result.current
              ? "Current when last checked."
              : "Historical or review required."}{" "}
            No model calls, campaign approval or send authority.
          </p>
          <p>Draft: {result.draft_id}</p>
          <p>
            Source review expires:{" "}
            {new Date(result.grounding.review_expires_at * 1000).toISOString()}.
          </p>
          <ul>
            {result.review_required.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
          {result.manifest.creatives.map((c) => (
            <div key={c.id}>
              <h5>{c.headline}</h5>
              <p>{c.opening}</p>
              <p>{c.locked_block}</p>
            </div>
          ))}
        </article>
      )}
    </section>
  );
}
