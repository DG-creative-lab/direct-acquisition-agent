import { useEffect, useRef, useState } from "react";
import { command, read } from "./api";
import { segmentName } from "./ui";
import type { ConversationAction } from "./ConversationActions";

export default function ConversationCopyRevision<T>({
  action,
  conversationId,
  disabled,
  onChanged,
  onReview,
}: {
  action: ConversationAction;
  conversationId: string;
  disabled: boolean;
  onChanged: (value: T) => void;
  onReview?: (sessionId: string) => void;
}) {
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const epoch = useRef(0);
  useEffect(() => {
    epoch.current += 1;
    return () => {
      epoch.current += 1;
    };
  }, [conversationId, action.id]);
  const proposal = action.result?.copy_revision;
  const confirm = async () => {
    if (!consent || !action.result) return;
    const stamp = epoch.current;
    setBusy(true);
    setError("");
    try {
      const value = await command<T>(
        `/api/conversations/${conversationId}/confirm-copy-action`,
        {
          action_id: action.id,
          result_id: action.result.id,
          expected_revision: action.revision,
          allow_model_copy: true,
        },
      );
      if (stamp === epoch.current) onChanged(value);
    } catch (e) {
      if (stamp !== epoch.current) return;
      setError((e as Error).message);
      try {
        const value = await read<T>(`/api/conversations/${conversationId}`);
        if (stamp === epoch.current) onChanged(value);
      } catch {
        /* Keep the original command identity for explicit retry. */
      }
    } finally {
      if (stamp === epoch.current) setBusy(false);
    }
  };
  if (!proposal) return null;
  const progress = action.copy_revision_progress;
  const confirmed = action.confirmed?.kind === "copy_revision_confirmation";
  return (
    <div className="conversation-copy-edit" aria-label="Copy edit proposal">
      {confirmed ? (
        <>
          <p role="status">
            {progress?.status === "complete"
              ? "Revised copy is ready for a new review. Approval has not been granted."
              : progress?.status === "uncertain"
                ? "The revision provider outcome is uncertain and may have been charged. Inspect the original run before requesting another revision."
                : progress?.status === "blocked"
                  ? progress.block?.detail
                  : ["failed", "cancelled", "stale"].includes(
                        progress?.status ?? "",
                      )
                    ? "The saved revision has stopped. Inspect its original run and current evidence before continuing."
                    : "Your copy edit is saved. Preparing and validating the revised draft."}
          </p>
          {progress?.status === "complete" &&
            action.confirmed?.session_id &&
            onReview && (
              <button
                className="button primary"
                onClick={() => onReview(action.confirmed!.session_id!)}
              >
                Review revised copy
              </button>
            )}
          <details>
            <summary>Inspect copy revision</summary>
            <pre>{JSON.stringify(progress, null, 2)}</pre>
          </details>
        </>
      ) : proposal.status !== "ready" || !proposal.target ? (
        <p>{proposal.reason}</p>
      ) : (
        <>
          <p>
            <strong>
              {segmentName(proposal.target.segment)} · Variant{" "}
              {proposal.target.arm}
            </strong>
          </p>
          <p>{proposal.target.headline}</p>
          <details>
            <summary>Current copy</summary>
            <p>{proposal.target.opening}</p>
          </details>
          <p>
            <strong>Requested edit</strong>
          </p>
          <blockquote>{proposal.feedback}</blockquote>
          <p>
            Only this variant will change. Audience, assignments, budget and
            product wording stay fixed.
          </p>
          {(!action.current || action.target_current === false) && (
            <p>
              This proposal belongs to an earlier draft or brief. Request a new
              edit for the current campaign.
            </p>
          )}
          <label className="copy-revision-consent">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              disabled={
                busy ||
                disabled ||
                !action.current ||
                action.target_current === false
              }
            />
            Allow up to five model calls for this revision
          </label>
          <button
            className="button primary"
            disabled={
              !consent ||
              busy ||
              disabled ||
              !action.current ||
              action.target_current === false
            }
            onClick={confirm}
          >
            {busy ? "Saving copy revision…" : "Generate copy revision"}
          </button>
        </>
      )}
      {error && (
        <p className="conversation-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
