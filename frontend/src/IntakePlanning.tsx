import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import type { BriefInput, IntakeSnapshot } from "./intake-api";
import {
  briefReadiness,
  dispatchPlan,
  pendingPlan,
  planHistory,
  planProgress,
  PlanRejected,
  queuePlan,
  queuePlanResume,
} from "./intake-planning-api";
import type {
  IntakePlanView,
  PendingPlan,
  Readiness,
} from "./intake-planning-api";

type Props = {
  brief: IntakeSnapshot<BriefInput> | null;
  storeId: string;
  disabled: boolean;
  active: boolean;
  onLock: (value: boolean) => void;
  onError: (value: string) => void;
  onNotice: (value: string) => void;
};
export default function IntakePlanning({
  brief,
  storeId,
  disabled,
  active,
  onLock,
  onError,
  onNotice,
}: Props) {
  const [pending, setPending] = useState<PendingPlan | null>(null);
  const [storageError, setStorageError] = useState("");
  const [busy, setBusy] = useState(false);
  const [consentFor, setConsentFor] = useState("");
  const selectionKey = `${storeId}:${brief?.id ?? ""}:${brief?.revision ?? ""}`;
  const consent = consentFor === selectionKey;
  const [loadedFor, setLoadedFor] = useState("");
  const [rows, setRows] = useState<IntakePlanView[]>([]);
  const [view, setView] = useState<IntakePlanView | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [attempt, setAttempt] = useState(0);
  const selection = useRef("");
  selection.current = brief?.id ?? "";
  useEffect(() => {
    try {
      setPending(pendingPlan());
    } catch (error) {
      setStorageError((error as Error).message);
      onError((error as Error).message);
    }
  }, [onError]);
  useEffect(() => {
    onLock(busy || !!pending || !!storageError);
  }, [busy, pending, storageError, onLock]);
  useEffect(() => {
    setLoadedFor("");
    setRows([]);
    setView(null);
    setReadiness(null);
    if (!brief || !active) return;
    const controller = new AbortController();
    Promise.all([
      planHistory(brief.id, controller.signal),
      briefReadiness(brief, controller.signal),
    ])
      .then(([history, ready]) => {
        if (controller.signal.aborted) return;
        setRows(history.items);
        setView(history.items.at(-1) ?? null);
        setReadiness(ready);
        setLoadedFor(selectionKey);
      })
      .catch((error) => {
        if (!controller.signal.aborted) onError(error.message);
      });
    return () => controller.abort();
  }, [brief?.id, brief?.revision, selectionKey, active, attempt, onError]);
  async function send(command: PendingPlan) {
    setBusy(true);
    onError("");
    onNotice("");
    try {
      const result = await dispatchPlan(command);
      setPending(null);
      if (
        selection.current === command.payload.brief_id ||
        !selection.current
      ) {
        setView(result);
        setRows((items) => [
          ...items.filter((item) => item.request_id !== result.request_id),
          result,
        ]);
        onNotice(
          "Original planning request confirmed. Its result grants no campaign authority.",
        );
      }
    } catch (error) {
      if (error instanceof PlanRejected) setPending(null);
      onError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function start(event: FormEvent) {
    event.preventDefault();
    if (
      !brief ||
      disabled ||
      busy ||
      pending ||
      storageError ||
      loadedFor !== selectionKey
    )
      return;
    try {
      const command = queuePlan(storeId, brief);
      setPending(command);
      await send(command);
    } catch (error) {
      onError((error as Error).message);
    }
  }
  async function refresh() {
    if (!view) return;
    const requestId = view.request_id,
      selected = selection.current;
    setBusy(true);
    onError("");
    try {
      const result = await planProgress(requestId);
      if (selection.current === selected && result.store_id === storeId)
        setView(result);
    } catch (error) {
      onError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const existing = rows.find(
    (row) => row.source.brief_revision === brief?.revision,
  );
  const result = view?.plan?.result;
  return (
    <section
      className="intake-section intake-planning"
      aria-labelledby="intake-planning-title"
    >
      <div className="intake-section-heading">
        <div>
          <span className="eyebrow">03 / CAMPAIGN INTERPRETATION</span>
          <h2 id="intake-planning-title">Plan from this brief</h2>
        </div>
      </div>
      <p className="intake-help">
        Interpret the exact saved company and brief versions. This can propose
        an approach or ask questions. It does not generate campaign copy, verify
        claims or grant approval.
      </p>
      {storageError && <p>{storageError}</p>}
      {pending && (
        <div className="intake-recovery">
          <strong>Confirm the original planning request</strong>
          <p>
            Brief version {pending.payload.brief_revision}. Keep this tab until
            the original request is confirmed. Retry uses its frozen source and
            original model settings.
          </p>
          <button
            className="button primary"
            type="button"
            disabled={busy || !!storageError}
            onClick={() => void send(pending)}
          >
            Retry original planning request
          </button>
        </div>
      )}
      {!brief && !pending && (
        <p>Save or reopen a campaign brief to interpret it.</p>
      )}
      {brief && (
        <>
          <p>
            Uses saved brief version {brief.revision}, company version{" "}
            {brief.draft.company_revision}.
          </p>
          {readiness &&
            (readiness.missing.length > 0 ||
              readiness.unsupported.length > 0) && (
              <div className="intake-planning-note">
                <h3>Before planning</h3>
                <ul>
                  {[...readiness.missing, ...readiness.unsupported].map(
                    (item) => (
                      <li key={item}>{item}</li>
                    ),
                  )}
                </ul>
                <p>
                  These checks use the saved requirements. They do not make
                  model calls.
                </p>
              </div>
            )}
          <form onSubmit={(event) => void start(event)}>
            <fieldset
              disabled={
                disabled ||
                busy ||
                !!pending ||
                !!storageError ||
                !!existing ||
                loadedFor !== selectionKey
              }
            >
              <legend>Planning permission</legend>
              <div className="intake-radio">
                <input
                  id="intake-plan-consent"
                  type="checkbox"
                  required
                  checked={consent}
                  onChange={(event) =>
                    setConsentFor(event.target.checked ? selectionKey : "")
                  }
                />
                <label htmlFor="intake-plan-consent">
                  Allow up to two planning model calls for this saved brief
                </label>
              </div>
              <p className="intake-help">
                Uses your connected model and its existing price limits. Saving
                alone makes no calls. Missing or unsupported requirements may be
                explained without inference.
              </p>
              <button className="button primary" type="submit">
                Prepare a plan
              </button>
            </fieldset>
          </form>
          {disabled && !pending && (
            <p>Save or discard your unsaved edits before planning.</p>
          )}
          {existing && (
            <p>
              This saved brief version already has an original planning request.
              Inspect its result or progress below. Edit and save the brief for
              a new interpretation.
            </p>
          )}
        </>
      )}
      {rows.length > 0 && (
        <div className="intake-field">
          <label htmlFor="intake-plan-history">Saved interpretations</label>
          <select
            id="intake-plan-history"
            value={view?.request_id ?? ""}
            disabled={busy || !!pending}
            onChange={(event) =>
              setView(
                rows.find((row) => row.request_id === event.target.value) ??
                  null,
              )
            }
          >
            {rows.map((row) => (
              <option key={row.request_id} value={row.request_id}>
                Brief version {row.source.brief_revision} /{" "}
                {row.plan?.status ?? "staged"}
              </option>
            ))}
          </select>
        </div>
      )}
      {view && (
        <article className="intake-plan-result">
          <h3>
            {view.current
              ? "Saved interpretation"
              : "Historical interpretation"}
          </h3>
          <p>
            Brief version {view.source.brief_revision}, company version{" "}
            {view.source.company_revision}. Model:{" "}
            {view.source.model_config.model}.
          </p>
          <p>
            Status: {view.plan?.status ?? "staged"}. Planning only. Company
            claims remain unverified.
          </p>
          {result && (
            <>
              <h4>
                {result.outcome === "proposal"
                  ? "Proposed approach"
                  : result.outcome === "clarification"
                    ? "Clarification needed"
                    : "Unsupported requirements"}
              </h4>
              <p>{result.summary}</p>
              {result.approach.length > 0 && (
                <ol>
                  {result.approach.map((line, index) => (
                    <li key={index}>{line}</li>
                  ))}
                </ol>
              )}
              {result.questions.length > 0 && (
                <>
                  <h4>Questions</h4>
                  <ul>
                    {result.questions.map((line, index) => (
                      <li key={index}>{line}</li>
                    ))}
                  </ul>
                </>
              )}
              {[...result.limitations, ...result.readiness.execution_blockers]
                .length > 0 && (
                <>
                  <h4>Limits and next requirements</h4>
                  <ul>
                    {[
                      ...result.limitations,
                      ...result.readiness.execution_blockers,
                    ].map((line, index) => (
                      <li key={index}>{line}</li>
                    ))}
                  </ul>
                </>
              )}
              <details>
                <summary>Exact source used</summary>
                <p>{view.source.company.draft.company_name}</p>
                <p>{view.source.company.draft.description}</p>
                <p>{view.source.company.draft.product_name}</p>
                <p>
                  Requested call to action:{" "}
                  {view.source.company.draft.official_cta}
                </p>
                <p>
                  Call to action reference: {view.source.company.draft.cta_url}
                </p>
                <ul>
                  {view.source.company.draft.claims.map((claim, index) => (
                    <li key={index}>
                      <p>{claim.statement}</p>
                      <p>{claim.qualification}</p>
                      <p>
                        Unverified references:{" "}
                        {claim.source_urls.join(", ") || "none supplied"}
                      </p>
                    </li>
                  ))}
                </ul>
                <p>{result.requirements.objective}</p>
                <p>{result.requirements.audience}</p>
                <p>
                  Requested market: {result.requirements.country}. Currency:{" "}
                  {result.requirements.currency}. Budget in minor units:{" "}
                  {result.requirements.budget_minor ?? "not supplied"}.
                </p>
                <p>
                  Requested channels:{" "}
                  {result.requirements.channels.join(", ") || "not supplied"}.
                </p>
                <ul>
                  {result.requirements.constraints.map((line, index) => (
                    <li key={index}>{line}</li>
                  ))}
                </ul>
              </details>
            </>
          )}
          {view.plan?.error && (
            <p>
              The planning task did not complete. Inspect its original progress.
              An uncertain model call is not automatically repeated.{" "}
              {view.plan.error.provider_error ?? view.plan.error.error_code}
            </p>
          )}
          {!view.plan?.result && !view.plan?.error && (
            <p>
              The original planning request is waiting. Planning may be paused;
              no additional model call has been made.
            </p>
          )}
          {(!view.plan ||
            ["queued", "running", "waiting", "admitted"].includes(
              view.plan.status,
            )) && (
            <button
              className="button primary"
              type="button"
              disabled={busy || !!pending || !!storageError}
              onClick={() => {
                try {
                  const command = queuePlanResume(view);
                  setPending(command);
                  void send(command);
                } catch (error) {
                  onError((error as Error).message);
                }
              }}
            >
              Resume original planning request
            </button>
          )}
          <button
            className="button secondary"
            type="button"
            disabled={busy || !!pending}
            onClick={() => void refresh()}
          >
            Refresh planning progress
          </button>
        </article>
      )}
      <button
        className="button quiet"
        type="button"
        disabled={busy || !!pending}
        onClick={() => {
          setLoadedFor("");
          setAttempt((value) => value + 1);
        }}
      >
        Reload planning history
      </button>
    </section>
  );
}
