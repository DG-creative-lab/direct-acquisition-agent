import { useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  Search,
  ShieldCheck,
  Users,
  X,
  AlertTriangle,
} from "lucide-react";
import { download } from "./api";
import type { Act, Row, State } from "./api";
import { Badge, Modal, segmentName } from "./ui";

export function AudienceView({
  state,
  busy,
  act,
  onError,
}: {
  state: State;
  busy: boolean;
  act: Act;
  onError: (error: string) => void;
}) {
  const view = state.review!,
    selected = state.session.id;
  const [query, setQuery] = useState(""),
    [segment, setSegment] = useState("all"),
    [arm, setArm] = useState("all"),
    [limit, setLimit] = useState(12);
  const [suppression, setSuppression] = useState<Row | null>(null),
    [reason, setReason] = useState("Synthetic late suppression received.");
  const setError = onError;
  const rows = state.audience.filter(
    (r) =>
      (segment === "all" || r.segment === segment) &&
      (arm === "all" ||
        (arm === "mailed" ? ["A", "B"].includes(r.arm) : r.arm === arm)) &&
      `${r.id} ${r.segment} ${r.address}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const suppress = (row: Row) => {
    setReason("Synthetic late suppression received.");
    setSuppression(row);
  };
  const submit = async () => {
    if (
      suppression &&
      (await act("suppress", {
        business_id: suppression.id,
        reason: reason.trim(),
      }))
    )
      setSuppression(null);
  };
  return (
    <>
      <div
        className="tab-content"
        role="tabpanel"
        id="audience-panel"
        aria-labelledby="audience-tab"
      >
        <div className="section-title">
          <div>
            <h3>Audience selection</h3>
            <p>Deterministic exclusions. Randomized A/B and no-mail groups.</p>
          </div>
          <button
            className="text-button"
            onClick={() =>
              download(selected, "assignments", view.subject.id).catch((e) =>
                setError(e.message),
              )
            }
          >
            <ArrowDownToLine size={14} />
            Export
          </button>
        </div>
        <div className="segment-summary">
          {["inventory", "contractors"].map((s) => {
            const members = state.audience.filter(
              (r) => r.segment === s && r.arm !== "excluded",
            );
            return (
              <button
                key={s}
                className={segment === s ? "selected" : ""}
                onClick={() => {
                  setSegment(segment === s ? "all" : s);
                  setLimit(12);
                }}
              >
                <span className={`segment-symbol ${s}`}>
                  <Users size={18} />
                </span>
                <span>
                  <strong>{segmentName(s)}</strong>
                  <small>
                    {members.length} enrolled ·{" "}
                    {members.filter((r) => r.arm === "no_mail").length} controls
                  </small>
                </span>
                <ChevronRight size={16} />
              </button>
            );
          })}
        </div>
        <div className="table-toolbar">
          <label className="search">
            <Search size={15} />
            <input
              aria-label="Search audience"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setLimit(12);
              }}
              placeholder="Search business ID or address"
            />
          </label>
          <label className="filter">
            <span className="sr-only">Filter assignments</span>
            <select
              value={arm}
              onChange={(e) => {
                setArm(e.target.value);
                setLimit(12);
              }}
            >
              <option value="all">All assignments</option>
              <option value="mailed">Mailing recipients</option>
              <option value="no_mail">No-mail control</option>
              <option value="excluded">Excluded</option>
            </select>
            <ChevronDown size={13} />
          </label>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Business</th>
                <th>Segment</th>
                <th>Assignment</th>
                <th>Status</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, limit).map((r, i) => (
                <tr key={`${r.id}-${i}`}>
                  <td>
                    <strong className="business-name">{r.id}</strong>
                    <small>
                      {r.entity_type} · {r.country} · Demo address
                    </small>
                  </td>
                  <td>
                    {r.segment === "inventory" ? "Inventory" : "Contractors"}
                  </td>
                  <td>
                    <Badge
                      tone={
                        r.arm === "no_mail"
                          ? "purple"
                          : r.arm === "excluded"
                            ? "neutral"
                            : "green"
                      }
                    >
                      {r.arm === "A" || r.arm === "B"
                        ? `Variant ${r.arm}`
                        : segmentName(r.arm)}
                    </Badge>
                  </td>
                  <td>
                    <span
                      className={`row-status ${r.suppressed ? "blocked" : ""}`}
                    >
                      <span />
                      {r.suppressed
                        ? "Suppressed"
                        : r.arm === "excluded"
                          ? "Excluded"
                          : "Eligible"}
                    </span>
                  </td>
                  <td>
                    {["A", "B"].includes(r.arm) &&
                      !r.suppressed &&
                      !view.handoff && (
                        <button
                          className="row-action"
                          onClick={() => suppress(r)}
                          disabled={!!busy}
                          aria-label={`Suppress ${r.id}`}
                        >
                          Suppress
                        </button>
                      )}
                  </td>
                </tr>
              ))}
              {!rows.length && (
                <tr>
                  <td colSpan={5} className="no-results">
                    No businesses match these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="table-footer">
          <span>
            Showing {Math.min(limit, rows.length)} of {rows.length} records
          </span>
          {rows.length > limit && (
            <button
              className="text-button"
              onClick={() => setLimit(limit + 24)}
            >
              Show more
              <ArrowRight size={14} />
            </button>
          )}
        </div>
        <div className="policy-note">
          <ShieldCheck size={16} />
          <span>
            Policy checks cover duplicate businesses, contact limits, address
            quality and product scope.
            <details>
              <summary>View exclusion counts</summary>
              {Object.entries(view.manifest.exclusion_reasons).map(([k, v]) => (
                <p key={k}>
                  {k.replaceAll("_", " ")} <strong>{v}</strong>
                </p>
              ))}
            </details>
          </span>
        </div>
      </div>
      {suppression && (
        <Modal
          label="suppression-title"
          busy={busy}
          onClose={() => setSuppression(null)}
        >
          <button
            className="modal-close icon-button"
            aria-label="Close suppression"
            disabled={busy}
            onClick={() => setSuppression(null)}
          >
            <X size={18} />
          </button>
          <span className="modal-icon">
            <AlertTriangle size={24} />
          </span>
          <h2 id="suppression-title">Suppress this business</h2>
          <p>
            Record a late suppression for <strong>{suppression.id}</strong>.
            This invalidates the existing approval and requires a rebuilt draft
            and fresh review.
          </p>
          <label className="form-label" htmlFor="suppression-reason">
            Suppression reason
          </label>
          <textarea
            autoFocus
            id="suppression-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
          />
          <button
            className="button primary wide"
            disabled={busy || !reason.trim()}
            onClick={submit}
          >
            Record suppression
          </button>
        </Modal>
      )}
    </>
  );
}

export function CopyView({ state }: { state: State }) {
  const view = state.review!;
  return (
    <div
      className="tab-content"
      role="tabpanel"
      id="copy-panel"
      aria-labelledby="copy-tab"
    >
      <div className="section-title">
        <div>
          <h3>Audience-specific copy</h3>
          <p>
            {state.session.mode === "model"
              ? "Generated by GPT-OSS-120B, grounded in the reviewed product pack."
              : "Fixed offline fixtures. Choose model copy in a new campaign to generate grounded letters."}
          </p>
        </div>
      </div>
      <div className="copy-grid">
        {view.manifest.creatives.map((c) => (
          <article className="letter" key={c.id}>
            <div className="letter-top">
              <span>{segmentName(c.segment)}</span>
              <Badge>Variant {c.arm}</Badge>
            </div>
            <div className="letter-paper">
              <div className="letter-brand">
                iwoca<span>Independent demonstration</span>
              </div>
              <p className="letter-label">SYNTHETIC DIRECT MAIL</p>
              <h3>{c.headline || "Offline message fixture"}</h3>
              <p className="letter-opening">{c.opening}</p>
              <p className="letter-disclosure">
                {c.locked_block ||
                  "SYNTHETIC FIXTURE. HUMAN REVIEW REQUIRED. Nothing will be printed or sent."}
              </p>
            </div>
            <details className="copy-provenance">
              <summary>
                Copy identity and evidence
                <ChevronDown size={13} />
              </summary>
              <code>{c.id}</code>
              <p>
                {c.hypothesis ||
                  "Fixed demonstration input. No outcome support is implied."}
              </p>
              <small>
                {c.model || "Offline fixture"} · {c.status.replaceAll("_", " ")}
              </small>
            </details>
          </article>
        ))}
      </div>
    </div>
  );
}
