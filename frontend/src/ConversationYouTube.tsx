import { useEffect, useRef, useState } from "react";
import { command, read } from "./api";
import "./youtube.css";

type Placement = {
  id: string;
  title: string;
  creative: string;
  source: string;
};
type Draft = {
  title: string;
  goal: string;
  contexts: string[];
  placements: Placement[];
};
type Subject = {
  subject_id: string;
  kind: string;
  campaign_id: string;
  revision: number;
  package_fingerprint: string;
  payload_sha256: string;
  delivery_fingerprint: string;
};
type View = {
  campaign: { id: string; revision: number; draft: Draft };
  catalogue: Placement[];
  review: {
    subject: Subject;
    blockers: string[];
    payload: {
      limitations: string[];
      package: {
        groups: {
          context: string;
          title: string;
          viewer_path: string;
          content: { instruction: string };
        }[];
      };
    };
  };
  approval: null | { id: string; actor: string; expires_at: number };
  command_receipt?: {
    result: {
      content: string;
      filename: string;
      content_type: string;
      sha256: string;
    };
  };
};

export default function ConversationYouTube({
  campaignId,
  refreshKey,
}: {
  campaignId: string;
  refreshKey: number;
}) {
  const [view, setView] = useState<View | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const generation = useRef(0);
  const accept = (next: View) => {
    setView(next);
    setDraft(structuredClone(next.campaign.draft));
  };
  useEffect(() => {
    const epoch = ++generation.current;
    const controller = new AbortController();
    setView(null);
    setError("");
    setBusy(false);
    read<View>("/api/youtube/campaigns/" + campaignId, controller.signal)
      .then((next) => {
        if (generation.current === epoch) accept(next);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError((e as Error).message);
      });
    return () => controller.abort();
  }, [campaignId, refreshKey]);

  const act = async (operation: string) => {
    if (!view || !draft || busy) return;
    const epoch = generation.current;
    const inputs =
      operation === "save"
        ? { expected_revision: view.campaign.revision, draft }
        : operation === "revoke"
          ? { approval_id: view.approval!.id }
          : {
              subject: view.review.subject,
              ...(operation === "export"
                ? { approval_id: view.approval!.id }
                : {}),
            };
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const next = await command<View>(
        "/api/youtube/" + operation,
        { campaign_id: campaignId, ...inputs },
        null,
      );
      if (generation.current !== epoch) return;
      accept(next);
      if (operation === "export") {
        const result = next.command_receipt!.result;
        const url = URL.createObjectURL(
          new Blob([result.content], { type: result.content_type }),
        );
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = result.filename;
        anchor.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        setNotice("Downloaded the approved manual JSON export.");
      } else {
        setNotice(
          operation === "save"
            ? "Saved. Review this revision before approving."
            : operation === "approve"
              ? "Approved this exact package."
              : "Approval revoked.",
        );
      }
    } catch (e) {
      if (generation.current === epoch) setError((e as Error).message);
    } finally {
      if (generation.current === epoch) setBusy(false);
    }
  };

  if (!view || !draft)
    return (
      <div className="youtube-artifact" role="status">
        {error || "Loading the saved YouTube draft…"}
      </div>
    );
  const dirty = JSON.stringify(draft) !== JSON.stringify(view.campaign.draft);
  return (
    <section className="youtube-artifact" aria-label="YouTube campaign draft">
      <header>
        <div>
          <p className="eyebrow">YOUTUBE · AUTHORED OFFLINE</p>
          <h3>{view.campaign.draft.title}</h3>
        </div>
        <span className="youtube-state">
          Revision {view.campaign.revision} ·{" "}
          {view.approval ? "Approved" : "Unapproved"}
        </span>
      </header>
      <p>
        Fictional placements and synthetic comparison media. No model calls.
      </p>
      <form
        aria-label="Edit YouTube draft"
        action="/api/youtube/save"
        method="post"
        onSubmit={(event) => {
          event.preventDefault();
          void act("save");
        }}
      >
        <label htmlFor={"yt-title-" + campaignId}>Campaign title</label>
        <input
          id={"yt-title-" + campaignId}
          name="title"
          required
          maxLength={120}
          value={draft.title}
          disabled={busy}
          onChange={(event) =>
            setDraft({ ...draft, title: event.target.value })
          }
        />
        <label htmlFor={"yt-goal-" + campaignId}>Objective</label>
        <textarea
          id={"yt-goal-" + campaignId}
          name="goal"
          required
          rows={2}
          maxLength={500}
          disabled={busy}
          value={draft.goal}
          onChange={(event) => setDraft({ ...draft, goal: event.target.value })}
        />
        <fieldset disabled={busy}>
          <legend>Fictional placement candidates</legend>
          {view.catalogue
            .filter((row) => draft.contexts.includes(row.creative))
            .map((row) => (
              <div className="youtube-placement" key={row.id}>
                <input
                  type="checkbox"
                  name="placement"
                  id={campaignId + "-" + row.id}
                  checked={draft.placements.some((p) => p.id === row.id)}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      placements: event.target.checked
                        ? [...draft.placements, row]
                        : draft.placements.filter((p) => p.id !== row.id),
                    })
                  }
                />
                <label htmlFor={campaignId + "-" + row.id}>{row.title}</label>
              </div>
            ))}
        </fieldset>
        <button className="button secondary" type="submit" disabled={busy}>
          Save YouTube draft
        </button>
      </form>
      <section aria-label="Exact YouTube package review">
        <h4>Review this package</h4>
        {dirty && (
          <p role="status">Save your changes before approval or export.</p>
        )}
        {view.review.payload.package.groups.map((group) => (
          <div key={group.context} className="youtube-comparison">
            <strong>{group.title}</strong>
            <p>{group.content.instruction}</p>
            <a href={group.viewer_path} target="_blank" rel="noreferrer">
              Open bundled comparison preview
            </a>
          </div>
        ))}
        <p>Ad budget unset · Unscheduled · Manual setup only</p>
        {view.review.payload.limitations.map((line) => (
          <p className="muted" key={line}>
            {line}
          </p>
        ))}
        <details>
          <summary>Exact reviewed payload and fingerprint</summary>
          <p className="youtube-hash">
            {view.review.subject.package_fingerprint}
          </p>
          <pre>{JSON.stringify(view.review.payload, null, 2)}</pre>
        </details>
        {view.review.blockers.length > 0 && (
          <ul role="status">
            {view.review.blockers.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
        <div className="youtube-actions">
          <button
            type="button"
            className="button"
            disabled={
              busy ||
              dirty ||
              !!view.approval ||
              view.review.blockers.length > 0
            }
            onClick={() => void act("approve")}
          >
            Approve this YouTube package
          </button>
          <button
            type="button"
            className="button secondary"
            disabled={busy || dirty || !view.approval}
            onClick={() => void act("export")}
          >
            Download manual JSON
          </button>
          {view.approval && (
            <button
              type="button"
              className="text-button"
              disabled={busy}
              onClick={() => void act("revoke")}
            >
              Revoke approval
            </button>
          )}
        </div>
      </section>
      {notice && <p role="status">{notice}</p>}
      {error && (
        <p role="alert">
          {error} Retry the original action to check its saved result.
        </p>
      )}
    </section>
  );
}
