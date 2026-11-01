import { useEffect, useRef, useState } from "react";
import { command, read } from "./api";

export type ConversationAction = {
  id: string;
  revision: number;
  content: string;
  method: string;
  status: string;
  current: boolean;
  detail?: string;
  run_id: string | null;
  allow_model_copy: boolean;
  continuation_pending?: boolean;
  continuation_reason?: string;
  confirmed: null | { message_receipt: { revision: number } };
  result: null | {
    kind: string;
    text: string;
    observed_at: number;
    target: { id: string; revision: number };
    requires_confirmation: boolean;
    evidence: unknown;
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

export default function ConversationActions<T>({
  actions,
  conversationId,
  disabled,
  onChanged,
}: {
  actions: ConversationAction[];
  conversationId: string;
  disabled: boolean;
  onChanged: (value: T) => void;
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
    const payload = {
      action_id: action.id,
      target_id: action.result.target.id,
      expected_revision: action.revision,
    };
    try {
      const value = await command<T>(
        `/api/conversations/${conversationId}/confirm-action`,
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
          {!action.confirmed && (
            <div className="conversation-user">
              <span>You</span>
              <p>{action.content}</p>
            </div>
          )}
          <div className="conversation-assistant">
            {action.confirmed ? (
              <p>
                Change applied as brief revision{" "}
                {action.confirmed.message_receipt.revision}.
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
                      disabled={disabled || !!busy || !action.current}
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
            ) : action.status === "blocked" ? (
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
