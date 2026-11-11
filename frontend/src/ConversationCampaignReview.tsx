import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Loader2, X } from "lucide-react";
import { command, money, partialDelivery, read } from "./api";
import type { Act, Creative, State } from "./api";
import { AudienceView, CopyLetters } from "./CampaignViews";
import ReviewPanel from "./ReviewPanel";
import ConversationHandoff from "./ConversationHandoff";
import ConversationFollowup from "./ConversationFollowup";
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
export type ArtifactComment = {
  session_id: string;
  subject_id: string;
  subject_revision: number;
  target_id: string;
  segment: string;
  arm: string;
  feedback?: string;
};
type ArtifactChoice = {
  tab: "copy" | "audience";
  creativeId: string;
  subjectId: string;
};
function savedChoice(sessionId: string): ArtifactChoice {
  try {
    const value = JSON.parse(
      localStorage.getItem("artifact-choice:" + sessionId) ?? "null",
    );
    if (
      value &&
      ["copy", "audience"].includes(value.tab) &&
      typeof value.creativeId === "string" &&
      typeof value.subjectId === "string"
    )
      return value;
  } catch {
    /* A missing preference starts with the current artifact. */
  }
  return { tab: "copy", creativeId: "", subjectId: "" };
}
export default function ConversationCampaignReview({
  sessionId,
  interactive,
  active,
  onOpenWorkspace,
  artifactPane = false,
  onComment,
  feedbackRequest,
}: {
  sessionId: string;
  interactive: boolean;
  active: boolean;
  onOpenWorkspace: (sessionId?: string) => void;
  artifactPane?: boolean;
  onComment?: (comment: ArtifactComment) => void;
  feedbackRequest?: ArtifactComment | null;
}) {
  const [state, setState] = useState<State | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [showEvidence, setShowEvidence] = useState(false);
  const [reload, setReload] = useState(0);
  const epoch = useRef(0);
  const handledFeedback = useRef<ArtifactComment | null>(null);
  const [choice, setChoice] = useState(() => savedChoice(sessionId));
  const partiallyAccepted = !!partialDelivery(state?.review);
  const selectArtifact = (value: ArtifactChoice) => {
    localStorage.setItem("artifact-choice:" + sessionId, JSON.stringify(value));
    setChoice(value);
  };
  useEffect(() => {
    if (
      !feedbackRequest ||
      handledFeedback.current === feedbackRequest ||
      !state?.review ||
      feedbackRequest.session_id !== sessionId
    )
      return;
    handledFeedback.current = feedbackRequest;
    if (partiallyAccepted) {
      setError("This campaign already has a partial simulated delivery.");
      return;
    }
    if (feedbackRequest.subject_id !== state.review.subject.id) {
      setError(
        "This comment belongs to an earlier revision. Open the current copy to request another edit.",
      );
      return;
    }
    setFeedback({
      subject: feedbackRequest.subject_id,
      target: feedbackRequest.target_id,
      variants: state.review.manifest.creatives,
      text: feedbackRequest.feedback ?? "",
      consent: false,
    });
  }, [
    feedbackRequest,
    sessionId,
    state?.review?.subject.id,
    partiallyAccepted,
  ]);
  const pending =
    state?.learning?.monitoring?.status === "scheduled" ||
    (state?.copy_revisions?.some((r) =>
      ["admitted", "queued", "running", "blocked"].includes(r.status),
    ) ??
      false);
  useEffect(() => {
    const controller = new AbortController();
    const stamp = ++epoch.current;
    setLoading(true);
    read<State>(`/api/sessions/${sessionId}`, controller.signal)
      .then((value) => {
        if (stamp === epoch.current) {
          setState(value);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (e.name !== "AbortError" && stamp === epoch.current) {
          setError(e.message);
          setLoading(false);
        }
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
    const learningAction = [
      "open-learning",
      "observe",
      "finalize",
      "advance-report-check",
      "finalize-report-learning",
      "monitoring-start",
      "monitoring-update",
    ].includes(action);
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
    if (!feedback || busy || !interactive || partiallyAccepted) return;
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
  const chosenCreative = review.manifest.creatives.find(
    (c) => c.id === choice.creativeId,
  );
  const selectedCreative = chosenCreative ?? review.manifest.creatives[0];
  const selectionChanged =
    !!choice.subjectId && choice.subjectId !== review.subject.id;
  const alreadyRequested = state.copy_revisions?.some(
    (r) => r.base_subject_id === review.subject.id,
  );
  const canRevise =
    interactive &&
    !loading &&
    (!artifactPane || !selectionChanged) &&
    state.session.mode === "model" &&
    review.candidate_valid &&
    !review.handoff &&
    !partiallyAccepted &&
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
        <button
          className="text-button"
          onClick={() => onOpenWorkspace(sessionId)}
        >
          Open campaign workspace <ArrowUpRight size={14} />
        </button>
        <button
          className="text-button"
          disabled={busy || loading}
          onClick={() => {
            setLoading(true);
            setReload((n) => n + 1);
          }}
        >
          {loading ? "Refreshing review…" : "Refresh review"}
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
      {artifactPane && (
        <>
          <div
            className="artifact-tabs"
            role="tablist"
            aria-label="Campaign artifacts"
          >
            {(["copy", "audience"] as const).map((tab) => (
              <button
                key={tab}
                role="tab"
                id={"artifact-" + tab + "-tab"}
                aria-controls={"artifact-" + tab + "-panel"}
                aria-selected={choice.tab === tab}
                onClick={() =>
                  selectArtifact({
                    ...choice,
                    tab,
                    creativeId: selectedCreative.id,
                    subjectId: review.subject.id,
                  })
                }
              >
                {tab === "copy" ? "Creative copy" : "Audience"}
              </button>
            ))}
          </div>
          {selectionChanged && (
            <p role="status">
              A newer campaign revision is available.
              <button
                className="text-button"
                onClick={() =>
                  selectArtifact({
                    ...choice,
                    subjectId: review.subject.id,
                    creativeId: selectedCreative.id,
                  })
                }
              >
                View current revision
              </button>
            </p>
          )}
          {!selectionChanged && choice.tab === "copy" && (
            <div
              id="artifact-copy-panel"
              role="tabpanel"
              aria-labelledby="artifact-copy-tab"
            >
              <label className="form-label" htmlFor="artifact-variant">
                Copy variant
              </label>
              <select
                id="artifact-variant"
                value={selectedCreative.id}
                onChange={(event) =>
                  selectArtifact({
                    ...choice,
                    creativeId: event.target.value,
                    subjectId: review.subject.id,
                  })
                }
              >
                {review.manifest.creatives.map((c) => (
                  <option key={c.id} value={c.id}>
                    {segmentName(c.segment)} · Variant {c.arm}
                  </option>
                ))}
              </select>
              <CopyLetters
                state={state}
                creativeId={selectedCreative.id}
                onComment={
                  interactive && !loading && !busy && onComment
                    ? () =>
                        onComment({
                          session_id: sessionId,
                          subject_id: review.subject.id,
                          subject_revision: review.subject.revision,
                          target_id: selectedCreative.id,
                          segment: selectedCreative.segment,
                          arm: selectedCreative.arm,
                        })
                    : undefined
                }
              />
            </div>
          )}
          {!selectionChanged && choice.tab === "audience" && (
            <AudienceView
              key={review.subject.id}
              state={state}
              busy={busy}
              act={act}
              onError={setError}
              readOnly={!interactive}
              idPrefix="artifact-"
            />
          )}
        </>
      )}
      {!artifactPane && (
        <div className="chat-review-copy">
          <CopyLetters state={state} />
        </div>
      )}
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
                review.candidate_valid &&
                !partiallyAccepted
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
        readOnly={!interactive || (artifactPane && selectionChanged)}
        act={act}
        error={error}
        onEvidence={() => setShowEvidence(true)}
        allowHandoff={false}
      />
      {!partiallyAccepted && (
        <ConversationHandoff
          key={`handoff:${sessionId}`}
          state={state}
          interactive={interactive && (!artifactPane || !selectionChanged)}
          busy={busy}
          act={act}
          error={error}
        />
      )}
      {review.handoff && (
        <ConversationLearning
          key={`learning:${sessionId}`}
          state={state}
          busy={busy}
          act={act}
          error={error}
        />
      )}
      {state.learning?.status === "finalized" && (
        <ConversationFollowup
          state={state}
          onRefresh={() => setReload((n) => n + 1)}
          renderChild={(id) => (
            <ConversationCampaignReview
              sessionId={id}
              interactive={true}
              active={active}
              onOpenWorkspace={onOpenWorkspace}
            />
          )}
        />
      )}
      {feedback && !partiallyAccepted && (
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
