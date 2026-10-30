import { useState } from "react";
import { X } from "lucide-react";
import { date } from "./api";
import type { Act, State } from "./api";
import LearningView from "./LearningView";
import { Modal } from "./ui";

const descriptions = {
  "open-learning": [
    "Open synthetic outcome window",
    "Create a cohort from the accepted assignments, including no-mail controls. Missing results stay unknown.",
  ],
  observe: [
    "Simulate day 7 responses",
    "Advance this campaign's sandbox clock to day 7 and import synthetic positive responses. Beliefs stay unchanged while results are incomplete or immature.",
  ],
  finalize: [
    "Close synthetic window and learn",
    "Advance this campaign's sandbox clock to day 28, import explicit outcomes for every assigned business and request finalization. Existing maturity, completeness and immutable-outcome checks still apply. Synthetic labels deliberately favor variant A.",
  ],
} as const;
type Action = keyof typeof descriptions;
type Intent = {
  action: Action;
  payload: { handoff_id: string; cohort_id?: string };
};

export default function ConversationLearning({
  state,
  busy,
  act,
  error,
}: {
  state: State;
  busy: boolean;
  act: Act;
  error: string;
}) {
  const storageKey = `conversation-learning:${state.session.id}`;
  const [saved, setSaved] = useState<Intent | null>(() => {
    try {
      const value = JSON.parse(sessionStorage.getItem(storageKey) || "null");
      return value &&
        Object.hasOwn(descriptions, value.action) &&
        typeof value.payload?.handoff_id === "string"
        ? value
        : null;
    } catch {
      return null;
    }
  });
  const [intent, setIntent] = useState<Intent | null>(null);
  const [localError, setLocalError] = useState("");
  const propose: Act = async (action) => {
    if (busy || saved || !Object.hasOwn(descriptions, action)) return false;
    setLocalError("");
    setIntent({
      action: action as Action,
      payload: {
        handoff_id: state.review!.handoff!.id,
        ...(action !== "open-learning"
          ? { cohort_id: state.learning!.cohort.id }
          : {}),
      },
    });
    return false;
  };
  const submit = async () => {
    if (!intent || busy) return;
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(intent));
      setSaved(intent);
      if (await act(intent.action, intent.payload)) {
        sessionStorage.removeItem(storageKey);
        setSaved(null);
        setIntent(null);
      }
    } catch {
      setLocalError(
        "The saved learning request could not be updated. Inspect current learning before continuing.",
      );
    }
  };
  return (
    <section
      className="chat-learning"
      aria-label="Campaign learning in conversation"
    >
      <h3>Synthetic campaign learning</h3>
      <p>
        Accepted assignments are historical evidence. Learning does not approve
        or prepare another campaign.
      </p>
      {state.learning && (
        <details className="chat-campaign-detail">
          <summary>Inspect learning provenance and maturity</summary>
          <p>
            Accepted job: <code>{state.review!.handoff!.id}</code>
          </p>
          <p>
            Cohort: <code>{state.learning.cohort.id}</code>
          </p>
          <p>
            Sandbox time: {date(state.session.clock)}. Window closes:{" "}
            {date(state.learning.cohort.window_end)}.
          </p>
          <p>
            {state.session.clock >= state.learning.cohort.window_end
              ? "Observation window is mature."
              : "Observation window is not yet mature."}{" "}
            {state.learning.missing} outcomes remain unknown.
          </p>
          <p>
            Recorded learning events: {state.learning.events.length}. Finalized
            counts and outcomes remain immutable.
          </p>
        </details>
      )}
      <LearningView
        state={state}
        busy={busy || !!saved}
        act={propose}
        onCampaign={() => {}}
      />
      {state.learning?.status === "finalized" && (
        <p>
          A next experiment needs separate preparation, review and approval. Use
          the campaign workspace to prepare it deliberately.
        </p>
      )}
      {saved && (
        <div role="status">
          <p>
            A saved learning request needs checking. Reuse its original
            acceptance and cohort to observe or finish that request.
          </p>
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => setIntent(saved)}
          >
            Check saved learning request
          </button>
          <button
            className="text-button"
            disabled={busy}
            onClick={() => {
              sessionStorage.removeItem(storageKey);
              setSaved(null);
            }}
          >
            Dismiss learning reminder
          </button>
        </div>
      )}
      {error && !intent && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {localError && (
        <p className="form-error" role="alert">
          {localError}
        </p>
      )}
      {intent && (
        <Modal
          label="learning-confirmation-title"
          busy={busy}
          onClose={() => setIntent(null)}
        >
          <button
            className="modal-close icon-button"
            aria-label="Close learning confirmation"
            disabled={busy}
            onClick={() => setIntent(null)}
          >
            <X size={18} />
          </button>
          <h2 id="learning-confirmation-title">
            {descriptions[intent.action][0]}
          </h2>
          <p>{descriptions[intent.action][1]}</p>
          <p>
            Synthetic simulation only. No model calls or campaign changes are
            requested.
          </p>
          <div className="subject-preview">
            <span>BOUND ACCEPTANCE</span>
            <code>{intent.payload.handoff_id}</code>
            {intent.payload.cohort_id && (
              <>
                <span>BOUND COHORT</span>
                <code>{intent.payload.cohort_id}</code>
              </>
            )}
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button
            className="button primary wide"
            disabled={busy}
            onClick={submit}
          >
            {saved
              ? "Check original learning request"
              : "Confirm synthetic learning step"}
          </button>
        </Modal>
      )}
    </section>
  );
}
