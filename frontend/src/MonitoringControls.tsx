import { useEffect, useId, useState } from "react";
import { X } from "lucide-react";
import type { Act, State } from "./api";
import { date } from "./api";
import { pendingMonitoring } from "./monitoring-session";
import type { MonitoringIntent } from "./monitoring-session";
import { Modal } from "./ui";

type Upload = { name: string; content: string };
type Draft = { payload: Record<string, unknown>; filenames: string[] };

function utcInput(seconds: number) {
  return new Date(seconds * 1000).toISOString().slice(0, 19);
}

export default function MonitoringControls({
  state,
  busy,
  act,
  requestError,
  onPendingChange,
}: {
  state: State;
  busy: boolean;
  act: Act;
  requestError?: string;
  onPendingChange: (pending: boolean) => void;
}) {
  const id = useId();
  const learning = state.learning!;
  const plan = learning.monitoring;
  const cohort = learning.cohort.id;
  const session = state.session.id;
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [firstCheck, setFirstCheck] = useState(
    utcInput(Math.ceil(learning.cohort.window_start)),
  );
  const [minutes, setMinutes] = useState(
    String((plan?.interval_seconds ?? 3600) / 60),
  );
  const [saved, setSaved] = useState<MonitoringIntent | null>(null);
  const [loading, setLoading] = useState(true);
  const [readable, setReadable] = useState(false);
  const [reading, setReading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  useEffect(() => {
    let alive = true;
    pendingMonitoring(session, cohort)
      .then((intent) => {
        if (alive) {
          setSaved(intent);
          setReadable(true);
        }
      })
      .catch((reason: Error) => {
        if (alive) setError(reason.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [session, cohort]);
  useEffect(() => {
    onPendingChange(loading || !readable || !!saved || submitting);
    return () => onPendingChange(false);
  }, [loading, readable, saved, submitting, onPendingChange]);
  useEffect(() => {
    if (!saved) setMinutes(String((plan?.interval_seconds ?? 3600) / 60));
  }, [plan?.revision, saved]);
  const disabled =
    busy || loading || !readable || reading || submitting || !!saved;
  const binding = { handoff_id: state.review!.handoff!.id, cohort_id: cohort };

  const chooseFiles = async (files: FileList | null) => {
    setError("");
    setUploads([]);
    const selected = Array.from(files ?? []);
    if (!selected.length) return;
    if (
      selected.length > 12 ||
      selected.some((file) => file.size > 4 * 1024 * 1024) ||
      selected.reduce((sum, file) => sum + file.size, 0) > 16 * 1024 * 1024
    ) {
      setError("Choose up to 12 reports, at most 4 MiB each and 16 MiB total.");
      return;
    }
    setReading(true);
    try {
      const result = await Promise.all(
        selected.map(async (file) => ({
          name: file.name,
          content: new TextDecoder("utf-8", { fatal: true }).decode(
            await file.arrayBuffer(),
          ),
        })),
      );
      setUploads(result);
    } catch {
      setError("The reports could not be read as UTF-8 JSON files.");
    } finally {
      setReading(false);
    }
  };
  const interval = () => {
    const value = Number(minutes);
    if (!Number.isInteger(value) || value < 1 || value > 10080)
      throw new Error("Choose a whole number of minutes from 1 to 10080.");
    return value * 60;
  };
  const moveUpload = (index: number, offset: number) => {
    const ordered = [...uploads];
    const [file] = ordered.splice(index, 1);
    ordered.splice(index + offset, 0, file);
    setUploads(ordered);
  };
  const propose = () => {
    setError("");
    try {
      const first = Date.parse(firstCheck + "Z") / 1000;
      if (
        !Number.isFinite(first) ||
        first < learning.cohort.window_start ||
        first > learning.cohort.window_end
      )
        throw new Error(
          "Choose a first check within this cohort's observation window.",
        );
      if (!uploads.length)
        throw new Error("Choose recorded synthetic reports.");
      setDraft({
        filenames: uploads.map((file) => file.name),
        payload: {
          ...binding,
          first_check: first,
          interval_seconds: interval(),
          reports: uploads.map((file) => file.content),
        },
      });
    } catch (reason) {
      setError((reason as Error).message);
    }
  };
  const submit = async (action: string, payload: Record<string, unknown>) => {
    if (busy || submitting || loading) return;
    setSubmitting(true);
    setError("");
    try {
      if (await act(action, payload)) {
        setDraft(null);
        setUploads([]);
      }
      setSaved(await pendingMonitoring(session, cohort));
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setSubmitting(false);
    }
  };
  const update = (status: "scheduled" | "paused", changeCadence = false) => {
    setError("");
    try {
      void submit("monitoring-update", {
        ...binding,
        revision: plan!.revision,
        status,
        interval_seconds: changeCadence ? interval() : null,
      });
    } catch (reason) {
      setError((reason as Error).message);
    }
  };

  return (
    <section
      className="monitoring-controls"
      aria-label="Monitoring setup and controls"
    >
      <h3>Report monitoring</h3>
      {saved ? (
        <div role="status">
          <p>
            A saved monitoring request needs confirmation. Retry its original
            reports and settings.
          </p>
          <button
            className="button secondary"
            disabled={busy || submitting}
            onClick={() =>
              submit(
                saved.path.endsWith("monitoring-start")
                  ? "monitoring-start"
                  : "monitoring-update",
                saved.payload,
              )
            }
          >
            Recover saved monitoring request
          </button>
        </div>
      ) : plan ? (
        <>
          <p>
            Current cadence {plan.interval_seconds / 60} minutes. Schedule
            revision {plan.revision}.
          </p>
          {plan.status !== "complete" && (
            <div className="monitoring-fields">
              <label htmlFor={id + "-cadence"}>
                Check every, in minutes
                <input
                  id={id + "-cadence"}
                  type="number"
                  min="1"
                  max="10080"
                  step="1"
                  disabled={disabled}
                  value={minutes}
                  onChange={(event) => setMinutes(event.target.value)}
                />
              </label>
              <button
                className="button secondary"
                disabled={disabled}
                onClick={() =>
                  update(
                    plan.status === "scheduled" ? "scheduled" : "paused",
                    true,
                  )
                }
              >
                {plan.status === "blocked"
                  ? "Save cadence and pause"
                  : "Save cadence"}
              </button>
              <button
                className="button secondary"
                disabled={disabled}
                onClick={() =>
                  update(plan.status === "scheduled" ? "paused" : "scheduled")
                }
              >
                {plan.status === "scheduled"
                  ? "Pause monitoring"
                  : "Resume monitoring"}
              </button>
            </div>
          )}
        </>
      ) : learning.status !== "finalized" ? (
        <>
          <p>
            Upload recorded synthetic reports for this accepted cohort. The
            server checks their assignments and watermarks before saving a
            schedule.
          </p>
          <div className="monitoring-fields">
            <label htmlFor={id + "-reports"}>
              Recorded synthetic reports
              <input
                id={id + "-reports"}
                type="file"
                accept=".json,application/json"
                multiple
                disabled={disabled}
                onChange={(event) => void chooseFiles(event.target.files)}
              />
            </label>
            <label htmlFor={id + "-first"}>
              First report check, UTC
              <input
                id={id + "-first"}
                type="datetime-local"
                step="1"
                disabled={disabled}
                min={utcInput(Math.ceil(learning.cohort.window_start))}
                max={utcInput(Math.floor(learning.cohort.window_end))}
                value={firstCheck}
                onChange={(event) => setFirstCheck(event.target.value)}
              />
            </label>
            <label htmlFor={id + "-interval"}>
              Check every, in minutes
              <input
                id={id + "-interval"}
                type="number"
                min="1"
                max="10080"
                step="1"
                disabled={disabled}
                value={minutes}
                onChange={(event) => setMinutes(event.target.value)}
              />
            </label>
          </div>
          {uploads.length > 0 && (
            <ul>
              {uploads.map((file, index) => (
                <li key={index}>
                  <span>{file.name}</span>
                  <button
                    className="button secondary"
                    disabled={disabled || index === 0}
                    aria-label={`Move ${file.name} up`}
                    onClick={() => moveUpload(index, -1)}
                  >
                    Move up
                  </button>
                  <button
                    className="button secondary"
                    disabled={disabled || index === uploads.length - 1}
                    aria-label={`Move ${file.name} down`}
                    onClick={() => moveUpload(index, 1)}
                  >
                    Move down
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="small-print">
            Up to 12 UTF-8 JSON files, 4 MiB each and 16 MiB total. Reports must
            be in watermark order. First check times use UTC.
          </p>
          <button
            className="button secondary"
            disabled={disabled || !uploads.length}
            onClick={propose}
          >
            Review monitoring schedule
          </button>
        </>
      ) : (
        <p>The cohort is finalized.</p>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {draft && !saved && (
        <Modal
          label={id + "-confirm"}
          busy={busy || submitting}
          onClose={() => setDraft(null)}
        >
          <button
            className="modal-close icon-button"
            aria-label="Close monitoring confirmation"
            disabled={busy || submitting}
            onClick={() => setDraft(null)}
          >
            <X size={18} />
          </button>
          <h2 id={id + "-confirm"}>Confirm report monitoring</h2>
          <p>
            Save these recorded synthetic reports for the displayed acceptance
            and cohort.
          </p>
          <div className="subject-preview">
            <span>ACCEPTED JOB</span>
            <code>{binding.handoff_id}</code>
            <span>COHORT</span>
            <code>{binding.cohort_id}</code>
          </div>
          <p>
            First check {date(draft.payload.first_check as number)} UTC. Check
            every {(draft.payload.interval_seconds as number) / 60} minutes.
          </p>
          <ul>
            {draft.filenames.map((name, index) => (
              <li key={index}>{name}</li>
            ))}
          </ul>
          {requestError && (
            <p className="form-error" role="alert">
              {requestError}
            </p>
          )}
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button
            className="button primary wide"
            disabled={busy || submitting}
            onClick={() => submit("monitoring-start", draft.payload)}
          >
            Confirm monitoring schedule
          </button>
        </Modal>
      )}
    </section>
  );
}
