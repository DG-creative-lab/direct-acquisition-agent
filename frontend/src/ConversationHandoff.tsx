import { useState } from "react";
import { X } from "lucide-react";
import { date, download, money } from "./api";
import type { Act, State } from "./api";
import { Modal } from "./ui";

type Confirmation = {
  subject: string;
  approval: string;
  revision: number;
  recipients: number;
  cost: number;
};

export default function ConversationHandoff({
  state,
  interactive,
  busy,
  act,
  error,
}: {
  state: State;
  interactive: boolean;
  busy: boolean;
  act: Act;
  error: string;
}) {
  const review = state.review!;
  const storageKey = `conversation-handoff:${state.session.id}`;
  const [saved, setSaved] = useState<Confirmation | null>(() => {
    try {
      return JSON.parse(sessionStorage.getItem(storageKey) || "null");
    } catch {
      return null;
    }
  });
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [localError, setLocalError] = useState("");
  const accepted = review.handoff;
  const begin = () => {
    setLocalError("");
    setConfirmation({
      subject: review.subject.id,
      approval: review.approval!.id,
      revision: review.subject.revision,
      recipients: review.manifest.counts.mailed,
      cost: review.manifest.variable_cost_pence,
    });
  };
  const submit = async () => {
    if (!confirmation || busy || (!saved && !interactive)) return;
    try {
      // Save the displayed identity before dispatch. command() separately saves
      // the request key for these exact inputs, including across page reload.
      sessionStorage.setItem(storageKey, JSON.stringify(confirmation));
      setSaved(confirmation);
      setLocalError("");
      if (await act("handoff", { approval_id: confirmation.approval })) {
        sessionStorage.removeItem(storageKey);
        setSaved(null);
        setConfirmation(null);
      }
    } catch {
      setLocalError(
        "The saved handoff could not be updated. Inspect the campaign receipt before continuing.",
      );
    }
  };
  const exportFile = async (kind: string) => {
    setLocalError("");
    try {
      await download(state.session.id, kind, accepted!.subject_id);
    } catch (e) {
      setLocalError((e as Error).message);
    }
  };
  return (
    <section className="chat-handoff" aria-label="Campaign handoff">
      {accepted ? (
        <>
          <h3>Simulated handoff accepted</h3>
          <p>
            Historical acceptance by the local simulator. Nothing was printed or
            sent.
          </p>
          <p>
            {accepted.recipients} recipients · {date(accepted.accepted_at)}
          </p>
          <details className="chat-campaign-detail">
            <summary>Inspect acceptance receipt</summary>
            <dl>
              <dt>Receipt</dt>
              <dd>
                <code>{accepted.id}</code>
              </dd>
              <dt>Subject</dt>
              <dd>
                <code>{accepted.subject_id}</code>
              </dd>
              <dt>Approval</dt>
              <dd>
                <code>{accepted.approval_id}</code>
              </dd>
              <dt>Draft</dt>
              <dd>
                <code>{accepted.draft_id}</code>
              </dd>
              <dt>Destination</dt>
              <dd>{accepted.destination}</dd>
            </dl>
            <p>
              Receipt mode: {accepted.mode}. This records past work and grants
              no new authority.
            </p>
          </details>
          <div className="chat-handoff-downloads">
            {[
              ["handoff", "acceptance receipt"],
              ["manifest", "manifest"],
              ["mailing", "mailing CSV"],
              ["assignments", "assignments CSV"],
            ].map(([kind, label]) => (
              <button
                className="button secondary"
                key={kind}
                onClick={() => exportFile(kind)}
              >
                Download {label}
              </button>
            ))}
          </div>
        </>
      ) : interactive && review.approval_valid && !saved ? (
        <>
          <h3>Ready for simulated handoff</h3>
          <p>
            Your approval covers this exact campaign. Confirm the handoff
            separately.
          </p>
          <button className="button dark" disabled={busy} onClick={begin}>
            Simulate agency handoff
          </button>
        </>
      ) : null}
      {saved && (
        <div role="status">
          <p>
            A saved handoff request needs checking. Reuse its original approval
            to observe the receipt or finish that request.
          </p>
          <button
            className="button secondary"
            disabled={busy}
            onClick={() => {
              setLocalError("");
              setConfirmation(saved);
            }}
          >
            Check saved handoff
          </button>
          <button
            className="text-button"
            disabled={busy}
            onClick={() => {
              // This only dismisses the local reminder. The exact command key stays
              // in api.ts storage, and accepted history remains in the domain store.
              sessionStorage.removeItem(storageKey);
              setSaved(null);
            }}
          >
            Dismiss reminder
          </button>
        </div>
      )}
      {localError && (
        <p className="form-error" role="alert">
          {localError}
        </p>
      )}
      {confirmation && (
        <Modal
          label="handoff-title"
          busy={busy}
          onClose={() => setConfirmation(null)}
        >
          <button
            className="modal-close icon-button"
            aria-label="Close handoff confirmation"
            disabled={busy}
            onClick={() => setConfirmation(null)}
          >
            <X size={18} />
          </button>
          <h2 id="handoff-title">Confirm simulated handoff</h2>
          <p>
            Revision {confirmation.revision}. {confirmation.recipients}{" "}
            recipients. Mailing estimate {money(confirmation.cost)}.
          </p>
          <p>
            This requests local simulated acceptance. Nothing will be printed or
            sent. Current authority is checked by the server.
          </p>
          <div className="subject-preview">
            <span>BOUND SUBJECT</span>
            <code>{confirmation.subject}</code>
            <span>BOUND APPROVAL</span>
            <code>{confirmation.approval}</code>
          </div>
          {(error || localError) && (
            <p className="form-error" role="alert">
              {error || localError}
            </p>
          )}
          <button
            className="button primary wide"
            disabled={busy || (!saved && !interactive)}
            onClick={submit}
          >
            {saved ? "Check original handoff" : "Confirm simulated handoff"}
          </button>
        </Modal>
      )}
    </section>
  );
}
