import IntakeEmail from "./IntakeEmail";
import IntakePreparation from "./IntakePreparation";
import { useEffect, useId, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { BriefInput, IntakeSnapshot } from "./intake-api";
import {
  ContextRejected,
  dispatchContext,
  pendingContext,
  preparationHistory,
  preparationPreview,
  queueContext,
} from "./preparation-context-api";
import type {
  PendingContext,
  PreparationContext as Context,
  PreparationPreview,
} from "./preparation-context-api";

type Props = {
  brief: IntakeSnapshot<BriefInput> | null;
  storeId: string;
  active: boolean;
  disabled: boolean;
  sourceVersion: string;
  onLock: (value: boolean) => void;
  onError: (value: string) => void;
  onNotice: (value: string) => void;
};
export default function PreparationContext({
  brief,
  storeId,
  active,
  disabled,
  sourceVersion,
  onLock,
  onError,
  onNotice,
}: Props) {
  const id = useId();
  const [pending, setPending] = useState<PendingContext | null>(null),
    [storageError, setStorageError] = useState("");
  const [busy, setBusy] = useState(false),
    [attempt, setAttempt] = useState(0);
  const [preview, setPreview] = useState<PreparationPreview | null>(null);
  const [{ rows, view }, setHistory] = useState<{
    rows: Context[];
    view: Context | null;
  }>({ rows: [], view: null });
  const [loadedFor, setLoadedFor] = useState("");
  const [groundedLocked, setGroundedLocked] = useState(false);
  const [emailLocked, setEmailLocked] = useState(false);
  const [selection, setSelection] = useState({
    key: "",
    claims: [] as string[],
    description: false,
    cta: false,
  });
  const [note, setNote] = useState(""),
    [questions, setQuestions] = useState(""),
    [days, setDays] = useState(7),
    [consentFor, setConsentFor] = useState("");
  const selectionKey = `${storeId}:${brief?.id ?? ""}:${brief?.revision ?? ""}:${sourceVersion}`;
  const selected =
    selection.key === preview?.id
      ? selection
      : { key: preview?.id ?? "", claims: [], description: false, cta: false };
  const sourceRef = useRef("");
  const historyRead = useRef<AbortController | null>(null);
  sourceRef.current = selectionKey;
  useEffect(() => {
    try {
      setPending(pendingContext());
    } catch (error) {
      setStorageError((error as Error).message);
      onError((error as Error).message);
    }
  }, [onError]);
  useEffect(() => {
    onLock(
      busy || !!pending || !!storageError || groundedLocked || emailLocked,
    );
  }, [busy, pending, storageError, groundedLocked, emailLocked, onLock]);
  useEffect(() => {
    setLoadedFor("");
    setPreview(null);
    setHistory({ rows: [], view: null });
    if (!active || !brief) return;
    const controller = new AbortController();
    historyRead.current = controller;
    Promise.all([
      preparationPreview(brief, controller.signal),
      preparationHistory(brief.id, controller.signal),
    ])
      .then(([p, h]) => {
        if (controller.signal.aborted) return;
        setPreview(p);
        setHistory({ rows: h.items, view: h.items[0] ?? null });
        setLoadedFor(selectionKey);
      })
      .catch((error) => {
        if (!controller.signal.aborted) onError(error.message);
      });
    return () => controller.abort();
  }, [selectionKey, active, attempt, onError]);
  const fields = preview
    ? {
        brief_id: preview.brief.id,
        brief_revision: preview.brief.revision,
        preview_id: preview.id,
        expected_context_revision: preview.context_revision,
        selected_claim_ids: selected.claims,
        include_description: selected.description,
        include_cta: selected.cta,
        review_days: days,
        review_note: note,
        issues: questions.split("\n").filter((v) => v !== ""),
        confirmed: true as const,
      }
    : null;
  const consentKey = JSON.stringify(fields);
  async function send(command: PendingContext) {
    const current = sourceRef.current;
    setBusy(true);
    onError("");
    onNotice("");
    try {
      const result = await dispatchContext(command);
      setPending(null);
      if (
        sourceRef.current === current &&
        (!brief || brief.id === command.payload.brief_id)
      ) {
        historyRead.current?.abort();
        setHistory(({ rows: items }) => {
          const merged = [
            result,
            ...items.filter((item) => item.request_id !== result.request_id),
          ].sort((a, b) => b.context.revision - a.context.revision);
          const latest = merged[0].context.revision;
          const updated = merged.map((item) =>
            item.context.revision < latest
              ? {
                  ...item,
                  current: false,
                  review_required: Array.from(
                    new Set([
                      ...item.review_required,
                      "A later input review exists.",
                    ]),
                  ),
                }
              : item,
          );
          return {
            rows: updated,
            view: updated.find(
              (item) => item.request_id === result.request_id,
            )!,
          };
        });
      }
      setLoadedFor("");
      onNotice(
        "Original preparation review confirmed. User assertions remain unverified; no campaign was created.",
      );
    } catch (error) {
      if (error instanceof ContextRejected) setPending(null);
      onError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function confirm(event: FormEvent) {
    event.preventDefault();
    if (
      !fields ||
      busy ||
      pending ||
      storageError ||
      disabled ||
      preview?.read_only ||
      loadedFor !== selectionKey ||
      groundedLocked ||
      emailLocked
    )
      return;
    try {
      const command = queueContext(storeId, fields);
      setPending(command);
      await send(command);
    } catch (error) {
      onError((error as Error).message);
    }
  }
  return (
    <section
      className="intake-section preparation-review"
      aria-labelledby={id + "-title"}
    >
      <div className="intake-section-heading">
        <div>
          <span className="eyebrow">04 / PREPARATION INPUT REVIEW</span>
          <h2 id={id + "-title"}>Review preparation context</h2>
        </div>
      </div>
      <p className="intake-help">
        Choose the exact source wording to retain for future preparation. This
        records your input review. It does not verify claims, approve a campaign
        or make model calls.
      </p>
      {pending && (
        <div className="intake-recovery">
          <strong>Confirm the original preparation review</strong>
          <p>
            Brief version {pending.payload.brief_revision}. Retry keeps its
            exact selected inputs and original review window.
          </p>
          <button
            type="button"
            className="button primary"
            disabled={busy || !!storageError || !storeId}
            onClick={() => void send(pending)}
          >
            Retry original preparation review
          </button>
        </div>
      )}
      {!brief && !pending && (
        <p>Save or reopen a campaign brief to review its preparation inputs.</p>
      )}
      {preview && (
        <>
          <p>
            Saved brief version {preview.brief.revision}, pinned company version{" "}
            {preview.company.revision}. Latest company version:{" "}
            {preview.company_head_revision}.
          </p>
          <p>
            <strong>{preview.company.draft.company_name}</strong> /{" "}
            {preview.company.draft.product_name}
          </p>
          <p>
            Objective: {preview.brief.draft.objective || "not supplied"}.
            Audience: {preview.brief.draft.audience || "not supplied"}.
          </p>
          <p>
            Requested market: {preview.brief.draft.country || "not supplied"};
            currency: {preview.brief.draft.currency || "not supplied"}; budget
            in minor units: {preview.brief.draft.budget_minor ?? "not supplied"}
            ; channels:{" "}
            {preview.brief.draft.channels.join(", ") || "not supplied"}.
          </p>
          <ul>
            {preview.brief.draft.constraints.map((value, index) => (
              <li key={index}>{value}</li>
            ))}
          </ul>
          <form
            aria-labelledby={id + "-title"}
            onSubmit={(event) => void confirm(event)}
          >
            <fieldset
              disabled={
                disabled ||
                preview.read_only ||
                busy ||
                !!pending ||
                !!storageError ||
                loadedFor !== selectionKey ||
                groundedLocked ||
                emailLocked
              }
            >
              <legend>Source wording to retain</legend>
              {preview.company.draft.description && (
                <div className="preparation-choice">
                  <label htmlFor={id + "-description"}>
                    <input
                      type="checkbox"
                      id={id + "-description"}
                      name="include_description"
                      checked={selected.description}
                      onChange={(event) =>
                        setSelection({
                          ...selected,
                          description: event.target.checked,
                        })
                      }
                    />{" "}
                    Include the saved company description
                  </label>
                  <p>{preview.company.draft.description}</p>
                </div>
              )}
              {preview.claims.map((claim, index) => (
                <div className="preparation-choice" key={claim.id}>
                  <label htmlFor={id + "-claim-" + index}>
                    <input
                      type="checkbox"
                      id={id + "-claim-" + index}
                      name="selected_claim_ids"
                      checked={selected.claims.includes(claim.id)}
                      onChange={(event) =>
                        setSelection({
                          ...selected,
                          claims: event.target.checked
                            ? [...selected.claims, claim.id]
                            : selected.claims.filter((key) => key !== claim.id),
                        })
                      }
                    />{" "}
                    Include claim {index + 1}
                  </label>
                  <p>{claim.statement}</p>
                  <p>Qualification: {claim.qualification || "none supplied"}</p>
                  <p>
                    Unverified references:{" "}
                    {claim.source_urls.join(", ") || "none supplied"}
                  </p>
                </div>
              ))}
              {preview.company.draft.official_cta && (
                <div className="preparation-choice">
                  <label htmlFor={id + "-cta"}>
                    <input
                      type="checkbox"
                      id={id + "-cta"}
                      name="include_cta"
                      checked={selected.cta}
                      onChange={(event) =>
                        setSelection({ ...selected, cta: event.target.checked })
                      }
                    />{" "}
                    Include the saved call to action
                  </label>
                  <p>{preview.company.draft.official_cta}</p>
                  <p>
                    Unverified reference:{" "}
                    {preview.company.draft.cta_url || "none supplied"}
                  </p>
                </div>
              )}
              <p>
                Company references, stored without fetching or verification:{" "}
                {preview.company.draft.source_urls.join(", ") ||
                  "none supplied"}
                .
              </p>
              <div className="intake-field">
                <label htmlFor={id + "-note"}>
                  Input review note (required)
                </label>
                <textarea
                  id={id + "-note"}
                  name="review_note"
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  required
                  maxLength={1000}
                  rows={3}
                />
              </div>
              <div className="intake-field">
                <label htmlFor={id + "-questions"}>
                  Contradictions or questions to resolve
                </label>
                <p className="intake-help" id={id + "-questions-help"}>
                  Your observations, one per line, up to eight. This review does
                  not automatically detect semantic contradictions.
                </p>
                <textarea
                  id={id + "-questions"}
                  name="issues"
                  aria-describedby={id + "-questions-help"}
                  value={questions}
                  onChange={(event) => setQuestions(event.target.value)}
                  maxLength={8007}
                  rows={3}
                />
              </div>
              <div className="intake-field">
                <label htmlFor={id + "-days"}>Input review validity</label>
                <select
                  id={id + "-days"}
                  name="review_days"
                  value={days}
                  onChange={(event) => setDays(Number(event.target.value))}
                >
                  <option value={1}>1 day from confirmation</option>
                  <option value={7}>7 days from confirmation</option>
                  <option value={30}>30 days from confirmation</option>
                </select>
              </div>
              <div className="preparation-choice">
                <label htmlFor={id + "-consent"}>
                  <input
                    type="checkbox"
                    id={id + "-consent"}
                    name="confirmed"
                    required
                    checked={consentFor === consentKey}
                    onChange={(event) =>
                      setConsentFor(event.target.checked ? consentKey : "")
                    }
                  />{" "}
                  I reviewed these exact selected inputs. This does not verify
                  claims or approve a campaign.
                </label>
              </div>
              <button type="submit" className="button primary">
                Save reviewed preparation context
              </button>
            </fieldset>
          </form>
          {preview.read_only && (
            <p>
              This store is open for inspection. Input reviews cannot be saved
              here.
            </p>
          )}
          {disabled && !pending && (
            <p>
              Save or discard your source edits before confirming a preparation
              review.
            </p>
          )}
        </>
      )}
      {rows.length > 0 && (
        <div className="intake-field">
          <label htmlFor={id + "-history"}>
            Preparation review history (latest 20)
          </label>
          <select
            id={id + "-history"}
            disabled={busy || !!pending || groundedLocked || emailLocked}
            value={view?.request_id ?? ""}
            onChange={(event) =>
              setHistory((prior) => ({
                ...prior,
                view:
                  prior.rows.find((r) => r.request_id === event.target.value) ??
                  null,
              }))
            }
          >
            {rows.map((row) => (
              <option key={row.request_id} value={row.request_id}>
                Context version {row.context.revision} / brief version{" "}
                {row.context.source.brief.revision}
              </option>
            ))}
          </select>
        </div>
      )}
      {view && (
        <article className="intake-plan-result">
          <h3>Saved preparation input review</h3>
          <p>
            {view.current
              ? "Current when last checked"
              : "Review required or historical"}
            . Context version {view.context.revision}; brief version{" "}
            {view.context.source.brief.revision}; company version{" "}
            {view.context.source.company.revision}.
          </p>
          <p>
            Review window ends:{" "}
            {new Date(view.context.review_expires_at * 1000).toISOString()}. An
            original retry never extends this deadline.
          </p>
          <p>
            User assertions remain unverified. Campaign generation is
            unavailable from this context; campaign approval is separate.
          </p>
          <p>Review note: {view.context.selection.review_note}</p>
          <ul>
            {[
              ...view.review_required,
              ...view.context.missing_evidence,
              ...view.context.requirements_readiness.missing,
              ...view.context.requirements_readiness.unsupported,
              ...view.context.reviewer_questions,
            ].map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
          <details>
            <summary>Exact reviewed preparation inputs</summary>
            <p>
              {view.context.selected_inputs.company_name} /{" "}
              {view.context.selected_inputs.product_name}
            </p>
            {view.context.selected_inputs.description && (
              <p>{view.context.selected_inputs.description}</p>
            )}
            <ul>
              {view.context.selected_inputs.claims.map((claim) => (
                <li key={claim.id}>
                  <p>{claim.statement}</p>
                  <p>{claim.qualification}</p>
                  <p>
                    Unverified references:{" "}
                    {claim.source_urls.join(", ") || "none supplied"}
                  </p>
                </li>
              ))}
            </ul>
            {view.context.selected_inputs.cta && (
              <p>
                {view.context.selected_inputs.cta.wording} /{" "}
                {view.context.selected_inputs.cta.url}
              </p>
            )}
            <p>
              Objective: {view.context.requirements.objective}. Audience:{" "}
              {view.context.requirements.audience}.
            </p>
            <p>
              {view.context.requirements.country};{" "}
              {view.context.requirements.currency};{" "}
              {view.context.requirements.budget_minor ?? "not supplied"} minor
              units; {view.context.requirements.channels.join(", ")}.
            </p>
            <ul>
              {view.context.requirements.constraints.map((line, index) => (
                <li key={index}>{line}</li>
              ))}
            </ul>
          </details>
        </article>
      )}
      <button
        type="button"
        className="button quiet"
        disabled={!brief || busy || !!pending || !!storageError}
        onClick={() => setAttempt((v) => v + 1)}
      >
        Reload preparation sources and history
      </button>
      <IntakePreparation
        contextRequest={view?.request_id ?? ""}
        storeId={storeId}
        sourceVersion={selectionKey}
        active={active}
        disabled={
          disabled || busy || !!pending || !!storageError || emailLocked
        }
        onLock={setGroundedLocked}
        enabled={
          !view?.context.requirements.channels.some(
            (channel) => channel.toLowerCase() === "email",
          )
        }
      />
      <IntakeEmail
        contextRequest={view?.request_id ?? ""}
        storeId={storeId}
        sourceVersion={selectionKey}
        active={active}
        enabled={
          !!view?.context.requirements.channels.some(
            (channel) => channel.toLowerCase() === "email",
          )
        }
        disabled={
          disabled || busy || !!pending || !!storageError || groundedLocked
        }
        onLock={setEmailLocked}
      />
    </section>
  );
}
