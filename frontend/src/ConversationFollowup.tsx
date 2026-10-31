import { useState } from "react";
import type { ReactNode } from "react";
import { command, money } from "./api";
import type { State, Followup } from "./api";
export default function ConversationFollowup({
  state,
  onRefresh,
  renderChild,
}: {
  state: State;
  onRefresh: () => void;
  renderChild: (id: string) => ReactNode;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [consent, setConsent] = useState<Record<string, boolean>>({}),
    [showChild, setShowChild] = useState<string | null>(null);
  const propose = async () => {
    setBusy(true);
    setError("");
    try {
      await command<Followup>(
        `/api/sessions/${state.session.id}/followup-proposal`,
        { cohort_id: state.learning!.cohort.id },
      );
      onRefresh();
    } catch (e) {
      setError((e as Error).message);
      onRefresh();
    } finally {
      setBusy(false);
    }
  };
  const prepare = async (p: Followup, mode: string) => {
    setBusy(true);
    setError("");
    try {
      const result = await command<State>(
        `/api/sessions/${state.session.id}/followup-prepare`,
        {
          proposal_id: p.id,
          mode,
          allow_model_copy:
            mode === "model" && (!!p.session_id || !!consent[p.id]),
        },
      );
      setShowChild(result.session.id);
      onRefresh();
    } catch (e) {
      setError((e as Error).message);
      onRefresh();
    } finally {
      setBusy(false);
    }
  };
  return (
    <section
      className="chat-learning"
      aria-label="Next experiment in conversation"
    >
      <h3>Propose a follow-up experiment</h3>
      <p>
        Use finalized synthetic learning to plan a separate experiment. No
        approval or outcome counts transfer.
      </p>
      {
        <button className="button secondary" disabled={busy} onClick={propose}>
          Propose follow-up experiment
        </button>
      }
      {state.followups?.map((p) => (
        <article key={p.id}>
          <h4>Follow-up proposal</h4>
          <p>{p.hypothesis}</p>
          <p>{p.source_label}</p>
          <p>
            Budget cap {money(p.brief.budget_pence)}. {p.counts.mailed} proposed
            mailing recipients and {p.counts.holdout} no-mail controls. Mailing
            estimate {money(p.cost_pence)}.
          </p>
          <details className="chat-campaign-detail">
            <summary>Inspect frozen follow-up evidence</summary>
            <p>
              Source cohort: <code>{p.source_cohort}</code>
            </p>
            <p>
              Population snapshot: <code>{p.snapshot_id}</code>
            </p>
            <p>
              Proposal: <code>{p.id}</code>
            </p>
            <pre>
              {JSON.stringify(
                {
                  learning: p.learning,
                  memory: p.memory,
                  contexts: p.contexts,
                },
                null,
                2,
              )}
            </pre>
          </details>
          {!p.eligible ? (
            <p role="status">
              No sufficient independent population remains. Supply a verified
              new audience before preparing another experiment.
            </p>
          ) : p.session_id ? (
            <button
              className="button secondary"
              disabled={busy}
              onClick={() =>
                p.case_id ? setShowChild(p.session_id) : prepare(p, p.mode!)
              }
            >
              Inspect or resume follow-up
            </button>
          ) : (
            <>
              <p>
                Preparing creates a new unapproved campaign. Previously
                allocated businesses and suppressions are excluded and
                eligibility is checked again.
              </p>
              <button
                className="button secondary"
                disabled={busy}
                onClick={() => prepare(p, "fixture")}
              >
                Prepare offline follow-up
              </button>
              <label className="conversation-consent">
                <input
                  type="checkbox"
                  checked={!!consent[p.id]}
                  disabled={busy}
                  onChange={(e) =>
                    setConsent((previous) => ({
                      ...previous,
                      [p.id]: e.target.checked,
                    }))
                  }
                />
                Allow up to ten model calls for this follow-up
              </label>
              <button
                className="button primary"
                disabled={busy || !consent[p.id]}
                onClick={() => prepare(p, "model")}
              >
                Generate grounded follow-up
              </button>
            </>
          )}
          {p.generation && (
            <p>
              Saved preparation: {p.generation.status}.{" "}
              {p.generation.outcome_uncertain
                ? "Provider outcome is uncertain. Inspect the original run before another generation."
                : "Resuming uses the original run and generation permission."}
            </p>
          )}
          {showChild && p.session_id === showChild && renderChild(showChild)}
        </article>
      ))}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
    </section>
  );
}
