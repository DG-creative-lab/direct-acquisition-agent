import { useEffect, useRef, useState } from "react";
import { command, read } from "./api";
import type { CopyRevision } from "./api";
import ConversationCopyRevision from "./ConversationCopyRevision";

export type ConversationAction = {
  id: string;
  revision: number;
  content: string;
  method: string;
  status: string;
  current: boolean;
  target_current?: boolean;
  copy_revision_progress?: CopyRevision;
  detail?: string;
  run_id: string | null;
  allow_model_copy: boolean;
  continuation_pending?: boolean;
  typed_effect?: {
    preparation_id?: string;
    session_id?: string;
    proposal_id?: string;
    stopped?: boolean;
  };
  continuation_reason?: string;
  confirmed: null | {
    kind?: string;
    message_receipt?: { revision: number };
    session_id?: string;
  };
  result: null | {
    kind: string;
    text: string;
    observed_at: number;
    target: { id: string; revision: number };
    requires_confirmation: boolean;
    evidence: unknown;
    id: string;
    copy_revision?: {
      status: string;
      reason: string;
      feedback: string;
      target: null | {
        session_id: string;
        subject_id: string;
        id: string;
        segment: string;
        arm: string;
        headline: string;
        opening: string;
      };
    };
    amendment_exchange?: {
      action_id: string | null;
      content: string;
      response: null | { id: string; kind: string; text: string };
    }[];
  };
  generation: null | {
    outcome_uncertain: boolean;
    provider_error: string | null;
  };
};

function isTypedAction(action: ConversationAction) {
  return (
    action.result?.kind === "prepare_campaign" ||
    action.result?.kind === "propose_next_experiment"
  );
}

function TypedActionView({
  action,
  disabled,
  inferenceExhausted,
  busy,
  onConfirm,
  onReview,
}: {
  action: ConversationAction;
  disabled: boolean;
  inferenceExhausted: boolean;
  busy: boolean;
  onConfirm: () => void;
  onReview?: (sessionId: string) => void;
}) {
  const result = action.result;
  if (!result) return null;
  const effect = action.typed_effect;
  const sessionId = effect?.session_id;
  const prepare = result.kind === "prepare_campaign";
  const mode = (result.evidence as { mode?: string }).mode;
  let status = "";
  if (action.confirmed) {
    if (effect?.proposal_id) status = "Next experiment proposed.";
    else if (effect?.stopped)
      status = "Preparation stopped. Inspect the saved run.";
    else if (effect) status = "Preparation saved. Follow its progress in chat.";
    else if (action.continuation_pending)
      status =
        "Confirmation saved. Waiting for the original request to continue.";
    else status = "Confirmation saved. Its source changed or work was stopped.";
  }
  return (
    <>
      <p>{result.text}</p>
      <small>
        Saved brief {action.revision}
        {!action.current && " · Earlier brief"}
      </small>
      {status && <p role="status">{status}</p>}
      {sessionId && onReview && (
        <button
          className="button secondary"
          onClick={() => onReview(sessionId)}
        >
          {effect?.proposal_id ? "Open source campaign" : "Inspect campaign"}
        </button>
      )}
      {!action.confirmed && result.requires_confirmation && (
        <>
          {prepare && (
            <p>
              {mode === "planning" &&
                "Planning can use up to two model calls. "}
              {mode === "fixture"
                ? "Preparation uses offline fixture copy."
                : action.allow_model_copy
                  ? "The saved permission allows up to ten model copy calls."
                  : "Preparation uses fixture copy."}
            </p>
          )}
          <button
            className="button primary"
            disabled={
              disabled ||
              !action.current ||
              (inferenceExhausted && prepare && mode !== "fixture")
            }
            onClick={onConfirm}
          >
            {busy
              ? "Saving confirmation…"
              : prepare
                ? "Confirm campaign preparation"
                : "Confirm next experiment proposal"}
          </button>
        </>
      )}
    </>
  );
}

export default function ConversationActions<T>({
  actions,
  conversationId,
  disabled,
  inferenceExhausted,
  onChanged,
  onReview,
}: {
  actions: ConversationAction[];
  conversationId: string;
  disabled: boolean;
  inferenceExhausted: boolean;
  onChanged: (value: T) => void;
  onReview?: (sessionId: string) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const epoch = useRef(0);
  useEffect(() => {
    epoch.current += 1;
    return () => {
      epoch.current += 1;
    };
  }, [conversationId]);
  const confirm = async (action: ConversationAction) => {
    if (!action.result) return;
    const stamp = epoch.current;
    setBusy(action.id);
    setError("");
    const typed = isTypedAction(action);
    const payload = {
      action_id: action.id,
      expected_revision: action.revision,
      ...(typed
        ? { result_id: action.result.id }
        : { target_id: action.result.target.id }),
    };
    try {
      const value = await command<T>(
        `/api/conversations/${conversationId}/${typed ? "confirm-typed-action" : "confirm-action"}`,
        payload,
      );
      if (stamp === epoch.current) onChanged(value);
    } catch (e) {
      if (stamp !== epoch.current) return;
      setError((e as Error).message);
      try {
        const value = await read<T>(`/api/conversations/${conversationId}`);
        if (stamp === epoch.current) onChanged(value);
      } catch {
        /* Keep the saved request identity for explicit retry. */
      }
    } finally {
      if (stamp === epoch.current) setBusy(null);
    }
  };
  return (
    <div className="conversation-actions" aria-label="Campaign follow-ups">
      {actions.map((action) => (
        <section
          className="conversation-action"
          key={action.id}
          aria-label="Saved follow-up"
        >
          {(!action.confirmed ||
            action.confirmed.kind === "copy_revision_confirmation" ||
            action.confirmed.kind === "typed_action_confirmation") && (
            <div className="conversation-user">
              <span>You</span>
              <p>{action.content}</p>
            </div>
          )}
          <div className="conversation-assistant">
            {action.result?.kind === "revise_copy" ? (
              <ConversationCopyRevision<T>
                action={action}
                conversationId={conversationId}
                disabled={disabled || inferenceExhausted}
                onChanged={onChanged}
                onReview={onReview}
              />
            ) : isTypedAction(action) ? (
              <TypedActionView
                action={action}
                disabled={disabled || !!busy}
                inferenceExhausted={inferenceExhausted}
                busy={busy === action.id}
                onConfirm={() => confirm(action)}
                onReview={onReview}
              />
            ) : action.confirmed ? (
              <p>
                Change applied as brief revision{" "}
                {action.confirmed.message_receipt?.revision}.
              </p>
            ) : action.result ? (
              <>
                <p>{action.result.text}</p>
                <small>
                  Recorded{" "}
                  {new Date(action.result.observed_at * 1000).toLocaleString()}{" "}
                  · Brief {action.revision}
                  {!action.current ? " · Earlier brief" : ""}
                </small>
                {action.result.requires_confirmation && (
                  <div className="action-amendment">
                    {action.result.amendment_exchange && (
                      <div aria-label="Clarification carried into the brief">
                        <p>
                          These earlier requests and your reply will enter the
                          brief together, in this order.
                        </p>
                        {action.result.amendment_exchange
                          .slice(0, -1)
                          .map((entry) => (
                            <div key={entry.action_id}>
                              <p>
                                <strong>Earlier request</strong>
                              </p>
                              <blockquote>{entry.content}</blockquote>
                              <p>
                                <strong>Agent response</strong>
                              </p>
                              <p>{entry.response?.text}</p>
                            </div>
                          ))}
                      </div>
                    )}
                    <p>
                      <strong>Proposed change</strong>
                    </p>
                    <blockquote>{action.content}</blockquote>
                    <p>
                      Applying this change stops preparation of the previous
                      brief and invalidates its current review. Planning can use
                      up to 2 model calls. Model copy is{" "}
                      {action.allow_model_copy
                        ? "allowed within the existing request limit"
                        : "not authorized by this request"}
                      .
                    </p>
                    <button
                      className="button primary"
                      disabled={
                        disabled ||
                        inferenceExhausted ||
                        !!busy ||
                        !action.current
                      }
                      onClick={() => confirm(action)}
                    >
                      {busy === action.id
                        ? "Applying change…"
                        : "Apply brief change"}
                    </button>
                  </div>
                )}
              </>
            ) : action.generation?.outcome_uncertain &&
              !["admitted", "queued", "running", "blocked"].includes(
                action.status,
              ) ? (
              <p>
                The routing provider outcome is uncertain and may have been
                charged. Inspect the original run before requesting another
                interpretation.
              </p>
            ) : ["failed", "cancelled"].includes(action.status) ? (
              <p>
                Routing stopped. Inspect the saved run and server configuration.
                This follow-up did not change the brief.
              </p>
            ) : !action.current ? (
              <p>
                This interpretation belongs to an earlier brief and will not
                continue.
              </p>
            ) : ["blocked", "budget_exhausted"].includes(action.status) ? (
              <p role="status">{action.detail}</p>
            ) : (
              <p role="status">
                Interpreting your follow-up. The brief is unchanged.
              </p>
            )}
            {action.continuation_pending && (
              <p role="status">
                {action.continuation_reason === "planning_budget_exhausted"
                  ? "The change is saved, but this conversation has used its planning budget. Start a new conversation to prepare another campaign."
                  : "The change is saved. Planning has not started. Check server configuration; the original request is retained for recovery."}
              </p>
            )}
            <details>
              <summary>Inspect follow-up</summary>
              <pre>{JSON.stringify(action, null, 2)}</pre>
            </details>
          </div>
        </section>
      ))}
      {error && (
        <p className="conversation-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
