import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Loader2, X } from "lucide-react";
import { command, money, read } from "./api";
import type { Act, Creative, State } from "./api";
import { CopyLetters } from "./CampaignViews";
import ReviewPanel from "./ReviewPanel";
import ConversationHandoff from "./ConversationHandoff";
import ConversationLearning from "./ConversationLearning";
import { Modal, segmentName } from "./ui";
import "./conversation-review.css";

type Feedback = {
  subject: string;
  target: string;
  variants: Creative[];
  text: string;
  consent: boolean;
};
export default function ConversationCampaignReview({
  sessionId,
  interactive,
  active,
  onOpenWorkspace,
}: {
  sessionId: string;
  interactive: boolean;
  active: boolean;
  onOpenWorkspace: () => void;
}) {
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [showEvidence, setShowEvidence] = useState(false);
  const [reload, setReload] = useState(0);
  const epoch = useRef(0);
  const pending =
    state?.copy_revisions?.some((r) =>
      ["admitted", "queued", "running", "blocked"].includes(r.status),
    ) ?? false;
  useEffect(() => {
    const controller = new AbortController();
    const stamp = ++epoch.current;
    read<State>(`/api/sessions/${sessionId}`, controller.signal)
      .then((value) => {
        if (stamp === epoch.current) setState(value);
      })
      .catch((e) => {
        if (e.name !== "AbortError" && stamp === epoch.current)
          setError(e.message);
      });
    return () => controller.abort();
  }, [sessionId, reload]);
  useEffect(() => {
    if (!pending || !active) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      const stamp = epoch.current;
      try {
        const value = await read<State>(`/api/sessions/${sessionId}`);
        if (!cancelled && stamp === epoch.current) setState(value);
      } catch {
        if (!cancelled && stamp === epoch.current)
          setError(
            "Progress could not refresh. The saved request will continue on the server.",
          );
      }
      if (!cancelled) timer = setTimeout(poll, 600);
    };
    timer = setTimeout(poll, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [pending, active, sessionId]);
  const act: Act = async (action, payload = {}) => {
    const learningAction = ["open-learning", "observe", "finalize"].includes(
      action,
    );
    if (
      busy ||
      (!interactive &&
        action !== "handoff" &&
        !(learningAction && state?.review?.handoff))
    )
      return false;
    epoch.current += 1;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const value = await command<State>(
        `/api/sessions/${sessionId}/${action}`,
        payload,
      );
      epoch.current += 1;
      setState(value);
      setNotice(
        learningAction
          ? "Saved synthetic learning state loaded. Recommendations grant no campaign approval."
          : action === "handoff"
            ? "Simulator acceptance receipt observed. Nothing was printed or sent."
            : value.command_replayed
              ? "Existing decision receipt observed. Current campaign state refreshed."
              : "Review decision recorded for the displayed subject.",
      );
      return true;
    } catch (e) {
      setError((e as Error).message);
      setReload((n) => n + 1);
      return false;
    } finally {
      setBusy(false);
    }
  };
  const revise = async () => {
    if (!feedback || busy || !interactive) return;
    epoch.current += 1;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const value = await command<State>(
        `/api/sessions/${sessionId}/copy-revisions`,
        {
          expected_subject: feedback.subject,
          target_id: feedback.target,
          feedback: feedback.text.trim(),
          allow_model_copy: feedback.consent,
        },
      );
      epoch.current += 1;
      setState(value);
      setFeedback(null);
      setNotice(
        value.command_replayed
          ? "Existing revision request observed."
          : "Copy feedback saved. The earlier subject requires a new review decision.",
      );
    } catch (e) {
      setError((e as Error).message);
      setReload((n) => n + 1);
    } finally {
      setBusy(false);
    }
  };
  if (!state?.review)
    return <p role="status">{error || "Loading campaign review…"}</p>;
  const review = state.review;
  const alreadyRequested = state.copy_revisions?.some(
    (r) => r.base_subject_id === review.subject.id,
  );
  const canRevise =
    interactive &&
    state.session.mode === "model" &&
    review.candidate_valid &&
    !review.handoff &&
    !alreadyRequested &&
    (state.copy_revisions?.length ?? 0) < 3;
  return (
    <section
      className="conversation-campaign-review"
      aria-label="Campaign review in conversation"
    >
      <header>
        <div>
          <h3>Review the campaign</h3>
          <p>
            Revision {review.subject.revision}. Synthetic data. No mail is sent.
          </p>
        </div>
        <button className="text-button" onClick={onOpenWorkspace}>
          Open campaign workspace <ArrowUpRight size={14} />
        </button>
        <button
          className="text-button"
          disabled={busy}
          onClick={() => setReload((n) => n + 1)}
        >
          Refresh review
        </button>
      </header>
      <dl className="chat-campaign-facts">
        <div>
          <dt>Mailing recipients</dt>
          <dd>{review.manifest.counts.mailed}</dd>
        </div>
        <div>
          <dt>No-mail controls</dt>
          <dd>{review.manifest.counts.holdout}</dd>
        </div>
        <div>
          <dt>Mailing estimate</dt>
          <dd>{money(review.manifest.variable_cost_pence)}</dd>
        </div>
        <div>
          <dt>Budget cap</dt>
          <dd>{money(review.manifest.brief.budget_pence)}</dd>
        </div>
      </dl>
      {!interactive && (
        <p role="status">
          Historical brief. New messages prevent approval or revision of this
          campaign.
        </p>
      )}
      <details className="chat-campaign-detail">
        <summary>Inspect audience and experiment</summary>
        <p>
          A/B treatments and no-mail controls come from the same selected
          synthetic population.
        </p>
        <dl>
          {Object.entries(review.manifest.arm_counts).map(([arm, count]) => (
            <div key={arm}>
              <dt>{arm}</dt>
              <dd>{count}</dd>
            </div>
          ))}
        </dl>
        <p>Excluded records</p>
        <dl>
          {Object.entries(review.manifest.exclusion_reasons).map(
            ([reason, count]) => (
              <div key={reason}>
                <dt>{reason.replaceAll("_", " ")}</dt>
                <dd>{count}</dd>
              </div>
            ),
          )}
        </dl>
        <p>
          Snapshot: <code>{review.subject.snapshot_id}</code>
        </p>
      </details>
      <div className="chat-review-copy">
        <CopyLetters state={state} />
      </div>
      {canRevise && (
        <button
          className="button secondary"
          onClick={() =>
            setFeedback({
              subject: review.subject.id,
              target: review.manifest.creatives.find((c) => c.arm === "B")!.id,
              variants: review.manifest.creatives,
              text: "",
              consent: false,
            })
          }
          disabled={busy}
        >
          Revise copy
        </button>
      )}
      {state.session.mode !== "model" && (
        <p className="chat-review-note">
          Offline fixtures can be reviewed here. Targeted revisions require a
          grounded model campaign.
        </p>
      )}
      {state.copy_revisions?.map((revision) => (
        <div className="chat-copy-feedback" key={revision.id} role="status">
          <strong>
            {revision.status === "complete"
              ? revision.published_subject_id === review.subject.id &&
                interactive &&
                review.candidate_valid
                ? "Revised copy is ready for review"
                : "Earlier copy revision"
              : revision.status === "uncertain"
                ? "Revision outcome is uncertain"
                : revision.status === "blocked"
                  ? "Copy revision is blocked"
                  : ["admitted", "queued", "running"].includes(revision.status)
                    ? "Preparing copy revision"
                    : `Copy revision ${revision.status}`}
          </strong>
          <p>Copy feedback: {revision.feedback}</p>
          {revision.status === "complete" ? (
            <p>
              New draft and subject. Previous approval and outcome support do
              not transfer.
            </p>
          ) : revision.status === "uncertain" ? (
            <p>
              The provider may have processed and charged for this request.
              Inspect this original run before requesting another generation.
            </p>
          ) : revision.status === "blocked" && revision.block ? (
            <p>{revision.block.detail}</p>
          ) : ["failed", "cancelled", "stale"].includes(revision.status) ? (
            <p>
              Inspect the saved run. This request will not be repeated
              automatically.
            </p>
          ) : (
            <p>
              The audience, budget and assignments stay fixed while the selected
              hook is rewritten and screened.
            </p>
          )}
          <details>
            <summary>Inspect copy revision</summary>
            <p>
              Original subject: <code>{revision.base_subject_id}</code>
            </p>
            <p>
              Selected creative: <code>{revision.target_id}</code>
            </p>
            <p>
              Run: <code>{revision.run_id ?? "Not started"}</code>
            </p>
            {revision.block && (
              <p>
                Blocker: {revision.block.code}. {revision.block.detail}
              </p>
            )}
            {revision.generation?.provider_error && (
              <p>Provider: {revision.generation.provider_error}</p>
            )}
            {revision.generation?.unresolved_calls.map((call) => (
              <p key={call.key}>
                Unresolved call: <code>{call.key}</code> ({call.status})
              </p>
            ))}
            {revision.generation?.failed_tasks.map((task) => (
              <p key={task.capability}>
                {task.capability}: {task.error_code}
              </p>
            ))}
          </details>
        </div>
      ))}
      {notice && <p role="status">{notice}</p>}
      {error && !feedback && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <details
        className="chat-campaign-detail"
        open={showEvidence}
        onToggle={(event) => setShowEvidence(event.currentTarget.open)}
      >
        <summary>Current product evidence</summary>
        <p>
          Checked {review.authority.pack.checked_on}. Review due{" "}
          {review.authority.pack.review_by}.
        </p>
        {review.authority.pack.facts.map((fact) => (
          <p key={fact.id}>
            {fact.copy} {fact.qualification}
          </p>
        ))}
        {review.authority.pack.sources.map((source) => (
          <p key={source.url}>
            <a href={source.url} target="_blank" rel="noreferrer">
              {source.title}
            </a>
          </p>
        ))}
      </details>
      <ReviewPanel
        state={state}
        busy={busy}
        readOnly={!interactive}
        act={act}
        error={error}
        onEvidence={() => setShowEvidence(true)}
        allowHandoff={false}
      />
      <ConversationHandoff
        key={`handoff:${sessionId}`}
        state={state}
        interactive={interactive}
        busy={busy}
        act={act}
        error={error}
      />
      {review.handoff && (
        <ConversationLearning
          key={`learning:${sessionId}`}
          state={state}
          busy={busy}
          act={act}
          error={error}
        />
      )}
      {feedback && (
        <Modal
          label="copy-feedback-title"
          busy={busy}
          onClose={() => setFeedback(null)}
        >
          <button
            className="modal-close icon-button"
            aria-label="Close copy feedback"
            disabled={busy}
            onClick={() => setFeedback(null)}
          >
            <X size={18} />
          </button>
          <h2 id="copy-feedback-title">Revise one copy variant</h2>
          <p>
            Keep the audience, budget, assignments, product wording and other
            hooks. Feedback requests a change, never approval.
          </p>
          <label className="form-label" htmlFor="copy-revision-target">
            Variant to revise
          </label>
          <select
            className="copy-revision-select"
            id="copy-revision-target"
            value={feedback.target}
            disabled={busy}
            onChange={(event) =>
              setFeedback({ ...feedback, target: event.target.value })
            }
          >
            {feedback.variants.map((c) => (
              <option key={c.id} value={c.id}>
                {segmentName(c.segment)} / Variant {c.arm}
              </option>
            ))}
          </select>
          <label className="form-label" htmlFor="copy-revision-feedback">
            Copy feedback
          </label>
          <textarea
            id="copy-revision-feedback"
            value={feedback.text}
            onChange={(event) =>
              setFeedback({ ...feedback, text: event.target.value })
            }
            maxLength={500}
            disabled={busy}
            placeholder="For example, make variant B more direct."
          />
          <label className="conversation-consent">
            <input
              type="checkbox"
              checked={feedback.consent}
              disabled={busy}
              onChange={(event) =>
                setFeedback({ ...feedback, consent: event.target.checked })
              }
            />
            Allow up to five model calls for this revision
          </label>
          <p>
            Up to three revisions per campaign. The selected subject will be
            recorded as needing changes. Review the new subject before
            approving.
          </p>
          <div className="subject-preview">
            <span>BOUND SUBJECT</span>
            <code>{feedback.subject}</code>
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button
            className="button primary wide"
            disabled={
              busy || !feedback.consent || !feedback.text.trim() || !interactive
            }
            onClick={revise}
          >
            {busy && <Loader2 className="spin" size={16} />}Generate revision
          </button>
        </Modal>
      )}
    </section>
  );
}
