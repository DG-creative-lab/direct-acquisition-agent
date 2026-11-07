import { useState } from "react";
import { X } from "lucide-react";
import { command, MessageNotSavedError } from "./api";
import { Modal, segmentName } from "./ui";
import type { ArtifactComment } from "./ConversationCampaignReview";

export type SavedCopyComment = ArtifactComment & {
  request_id: string;
  conversation_revision: number;
  feedback: string;
  copy_mode: string;
  at: number;
};
export type WritingPreference = {
  id: string;
  revision: number;
  status: "active" | "retired";
  action: "confirm" | "correct" | "retire";
  segments: string[];
  preferred: string;
  avoid: string;
  reason: string;
  actor: string;
  at: number;
  source: Omit<SavedCopyComment, "session_id"> & {
    conversation_id: string;
    draft_id: string;
  };
  history: Omit<WritingPreference, "history">[];
};
type Decision = {
  session_id: string;
  comment_id: string;
  preference_id: string;
  action: "confirm" | "correct" | "retire";
  expected_revision: number;
  segments: string[];
  preferred: string;
  avoid: string;
  reason: string;
  confirmed: boolean;
};
function pendingDecision(key: string): Decision | null {
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) ?? "null");
    const value =
      saved?.schema === "writing-preference-pending/v1" ? saved.decision : null;
    if (
      value &&
      [
        "session_id",
        "comment_id",
        "preference_id",
        "preferred",
        "avoid",
        "reason",
      ].every((field) => typeof value[field] === "string") &&
      ["confirm", "correct", "retire"].includes(value.action) &&
      Number.isInteger(value.expected_revision) &&
      value.expected_revision >= 0 &&
      Array.isArray(value.segments) &&
      value.segments.length > 0 &&
      value.segments.every(
        (segment: unknown) =>
          segment === "inventory" || segment === "contractors",
      ) &&
      value.confirmed === true
    )
      return value;
    return null;
  } catch {
    return null;
  }
}
export default function WritingPreferences<T>({
  conversationId,
  comment,
  preferences,
  disabled,
  onSaved,
}: {
  conversationId: string;
  comment: SavedCopyComment;
  preferences: WritingPreference[];
  disabled: boolean;
  onSaved: (value: T) => void;
}) {
  const storageKey = `writing-preference-pending:${conversationId}:${comment.session_id}:${comment.request_id}`;
  const [pending, setPending] = useState(() => pendingDecision(storageKey));
  const [form, setForm] = useState<Decision | null>(pending);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const preference = preferences.find(
    (p) =>
      p.source.request_id === comment.request_id &&
      p.source.subject_id === comment.subject_id,
  );
  const open = (action: Decision["action"]) => {
    setError("");
    setForm({
      session_id: comment.session_id,
      comment_id: comment.request_id,
      preference_id: preference?.id ?? "",
      action,
      expected_revision: preference?.revision ?? 0,
      segments: preference?.segments ?? [comment.segment],
      preferred: preference?.preferred ?? comment.feedback,
      avoid: preference?.avoid ?? "",
      reason: "",
      confirmed: false,
    });
  };
  const save = async () => {
    if (!form) return;
    setBusy(true);
    setError("");
    try {
      const decision = pending ?? form;
      sessionStorage.setItem(
        storageKey,
        JSON.stringify({ schema: "writing-preference-pending/v1", decision }),
      );
      setPending(decision);
      const value = await command<T>(
        `/api/conversations/${conversationId}/writing-preferences`,
        decision,
      );
      sessionStorage.removeItem(storageKey);
      setPending(null);
      setForm(null);
      onSaved(value);
    } catch (e) {
      if (e instanceof MessageNotSavedError) {
        sessionStorage.removeItem(storageKey);
        setPending(null);
        setForm((current) => current && { ...current, confirmed: false });
      }
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const close = () => {
    if (!pending) setForm(null);
  };
  return (
    <div className="writing-preference">
      {!preference && (
        <button
          className="text-button"
          disabled={disabled}
          onClick={() => open("confirm")}
        >
          Remember as a writing preference
        </button>
      )}
      {preference && (
        <>
          <p>
            <strong>Writing preference {preference.status}</strong> · Version{" "}
            {preference.revision}
          </p>
          <p>{preference.preferred}</p>
          <p>Audience: {preference.segments.map(segmentName).join(", ")}</p>
          {preference.status === "active" && (
            <div className="button-row">
              <button
                className="text-button"
                disabled={disabled}
                onClick={() => open("correct")}
              >
                Correct writing preference
              </button>
              <button
                className="text-button"
                disabled={disabled}
                onClick={() => open("retire")}
              >
                Retire writing preference
              </button>
            </div>
          )}
          <details className="chat-campaign-detail">
            <summary>Preference history and source</summary>
            <p>
              Original comment on {segmentName(comment.segment)}, variant{" "}
              {comment.arm}, revision {comment.subject_revision}.
            </p>
            <p>
              Copy: <code>{comment.target_id}</code>
            </p>
            <p>
              Subject: <code>{comment.subject_id}</code>
            </p>
            {preference.history.map((version) => (
              <div key={version.revision}>
                <p>
                  Version {version.revision} · {version.action} ·{" "}
                  {version.actor} ·{" "}
                  {new Date(version.at * 1000).toLocaleString()}
                </p>
                <p>{version.preferred}</p>
                {version.avoid && <p>Avoid: {version.avoid}</p>}
                <p>Audience: {version.segments.map(segmentName).join(", ")}</p>
                <p>Reason: {version.reason}</p>
              </div>
            ))}
          </details>
        </>
      )}
      {form && (
        <Modal
          label="writing-preference-title"
          busy={busy || !!pending}
          onClose={close}
        >
          <button
            className="modal-close icon-button"
            aria-label="Close writing preference"
            disabled={busy || !!pending}
            onClick={close}
          >
            <X size={18} />
          </button>
          <h2 id="writing-preference-title">
            {form.action === "retire"
              ? "Retire writing preference"
              : form.action === "correct"
                ? "Correct writing preference"
                : "Confirm writing preference"}
          </h2>
          <p>
            Writing guidance for future campaigns in this workspace. Existing
            copy and frozen contexts keep their original guidance.
          </p>
          <p>Source comment: {comment.feedback}</p>
          <p>
            {segmentName(comment.segment)} · Variant {comment.arm} · Revision{" "}
            {comment.subject_revision}
          </p>
          <fieldset disabled={busy || !!pending}>
            <label className="form-label" htmlFor="preference-wording">
              Writing preference
            </label>
            <textarea
              id="preference-wording"
              maxLength={600}
              readOnly={form.action === "retire"}
              value={form.preferred}
              onChange={(e) =>
                setForm({
                  ...form,
                  preferred: e.target.value,
                  confirmed: false,
                })
              }
            />
            <label className="form-label" htmlFor="preference-avoid">
              Wording to avoid (optional)
            </label>
            <textarea
              id="preference-avoid"
              maxLength={600}
              readOnly={form.action === "retire"}
              value={form.avoid}
              onChange={(e) =>
                setForm({ ...form, avoid: e.target.value, confirmed: false })
              }
            />
            <fieldset disabled={form.action === "retire"}>
              <legend>Audience scope</legend>
              {["inventory", "contractors"].map((segment) => (
                <label key={segment} className="consent">
                  <input
                    type="checkbox"
                    checked={form.segments.includes(segment)}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        segments: e.target.checked
                          ? [...form.segments, segment]
                          : form.segments.filter((s) => s !== segment),
                        confirmed: false,
                      })
                    }
                  />
                  {segmentName(segment)}
                </label>
              ))}
            </fieldset>
            <label className="form-label" htmlFor="preference-reason">
              Reason for this decision
            </label>
            <textarea
              id="preference-reason"
              maxLength={600}
              value={form.reason}
              onChange={(e) =>
                setForm({ ...form, reason: e.target.value, confirmed: false })
              }
            />
            <label className="consent">
              <input
                type="checkbox"
                checked={form.confirmed}
                onChange={(e) =>
                  setForm({ ...form, confirmed: e.target.checked })
                }
              />
              {form.action === "retire"
                ? "Stop using this preference in future generation"
                : "Use this wording as guidance for the selected audiences"}
            </label>
          </fieldset>
          <p>
            Editorial guidance carries no product evidence, outcome support or
            campaign approval. Saving makes no model call.
          </p>
          {pending && !busy && (
            <p role="status">
              The last save is unconfirmed. Retry the saved decision to retrieve
              its receipt.
            </p>
          )}
          {error && <p role="alert">{error}</p>}
          <button
            className="button primary"
            disabled={
              busy ||
              (!pending &&
                (!form.confirmed ||
                  !form.preferred.trim() ||
                  !form.reason.trim() ||
                  !form.segments.length))
            }
            onClick={save}
          >
            {busy
              ? "Saving preference…"
              : pending
                ? "Retry saving preference"
                : form.action === "retire"
                  ? "Confirm retirement"
                  : "Confirm writing preference"}
          </button>
        </Modal>
      )}
    </div>
  );
}
