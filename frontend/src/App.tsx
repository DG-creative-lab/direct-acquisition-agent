import { useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  BarChart3,
  Check,
  ChevronRight,
  Clock3,
  FileText,
  FlaskConical,
  History,
  Layers3,
  Loader2,
  Mail,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Users,
  X,
  AlertTriangle,
  ArrowUpRight,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { command, date, download, money, read } from "./api";
import type { Act, Session, State } from "./api";
import { Badge, Empty, Modal } from "./ui";
import { AudienceView, CopyView } from "./CampaignViews";
import ReviewPanel from "./ReviewPanel";
import LearningView from "./LearningView";

type Page = "campaign" | "evidence" | "learning" | "activity";
type Tab = "audience" | "copy";

export default function App() {
  const [sessions, setSessions] = useState<Session[]>([]),
    [selected, setSelected] = useState(
      () => localStorage.getItem("workspace-selected") ?? "",
    ),
    [state, setState] = useState<State | null>(null);
  const [page, setPage] = useState<Page>("campaign"),
    [tab, setTab] = useState<Tab>("audience"),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [creating, setCreating] = useState(false),
    [mode, setMode] = useState<"fixture" | "model">("fixture");
  const [listed, setListed] = useState(false);
  const [parent, setParent] = useState<string | null>(null);
  const selectedRef = useRef(selected),
    generation = useRef(0),
    listGeneration = useRef(0);
  selectedRef.current = selected;
  const loadList = async () => {
    const epoch = ++listGeneration.current;
    const list = await read<{ sessions: Session[] }>("/api/sessions");
    if (epoch === listGeneration.current) setSessions(list.sessions);
    return list.sessions;
  };
  useEffect(() => {
    let alive = true;
    const initial = selectedRef.current;
    loadList()
      .then((list) => {
        if (alive) setListed(true);
        if (
          alive &&
          selectedRef.current === initial &&
          !list.some((session) => session.id === initial)
        )
          setSelected(list[0]?.id ?? "");
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    setState(null);
    setError("");
    if (!selected || !listed) return;
    localStorage.setItem("workspace-selected", selected);
    const controller = new AbortController();
    const epoch = ++generation.current;
    read<State>(`/api/sessions/${selected}`, controller.signal)
      .then((v) => {
        if (epoch === generation.current) setState(v);
      })
      .catch((e) => {
        if (e.name !== "AbortError" && epoch === generation.current)
          setError(e.message);
      });
    return () => controller.abort();
  }, [selected, listed]);
  const refresh = async () => {
    const id = selectedRef.current;
    if (!id) return;
    setBusy("Refreshing");
    try {
      const v = await read<State>(`/api/sessions/${id}`);
      if (id === selectedRef.current) setState(v);
      await loadList();
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const act: Act = async (action, payload = {}) => {
    if (busy) return false;
    const id = selectedRef.current;
    setBusy(action);
    setError("");
    setNotice("");
    try {
      const v = await command(`/api/sessions/${id}/${action}`, payload);
      if (id === selectedRef.current) {
        setState(v);
        setNotice(
          v.command_replayed
            ? "Existing command receipt observed. Current campaign state refreshed."
            : ((
                {
                  approve: "Approval recorded for this exact revision.",
                  reject: "Rejection recorded.",
                  refresh: "A new revision is ready for review.",
                  suppress:
                    "Suppression recorded. Earlier approval is now invalid.",
                  handoff: "Accepted by the local simulator. Nothing was sent.",
                  revoke: "Approval revoked.",
                  observe:
                    "Early synthetic responses imported. Beliefs remain pending.",
                  finalize:
                    "The simulated window is complete. Beliefs updated once.",
                  "open-learning": "Outcome window opened.",
                } as Record<string, string>
              )[action] ?? "Campaign prepared."),
        );
      }
      await loadList();
      return true;
    } catch (e) {
      if (id === selectedRef.current) setError((e as Error).message);
      return false;
    } finally {
      setBusy("");
    }
  };
  const create = async () => {
    setBusy("Creating campaign");
    setError("");
    try {
      const v = await command("/api/sessions", { mode, parent_id: parent });
      await loadList();
      setCreating(false);
      setSelected(v.session.id);
      selectedRef.current = v.session.id;
      setState(v);
      setPage("campaign");
      setTab("audience");
      setNotice(
        "Campaign prepared. Review the audience and copy before approving.",
      );
    } catch (e) {
      setError((e as Error).message);
      await loadList().catch(() => {});
    } finally {
      setBusy("");
    }
  };
  const view = state?.review;
  const status = view?.handoff
    ? "Accepted by simulator"
    : view?.approval_valid
      ? "Approved"
      : view?.approval?.decision === "reject"
        ? "Changes requested"
        : view && !view.candidate_valid
          ? "Needs refresh"
          : "Awaiting review";
  const nav: { id: Page; label: string; icon: LucideIcon }[] = [
    { id: "campaign", label: "Campaign", icon: Layers3 },
    { id: "evidence", label: "Product evidence", icon: ShieldCheck },
    { id: "learning", label: "Learning", icon: BarChart3 },
    { id: "activity", label: "Activity log", icon: History },
  ];
  return (
    <div className="app-shell">
      <a className="skip" href="#workspace-main">
        Skip to workspace
      </a>
      <aside className="sidebar">
        <a
          className="wordmark"
          aria-label="Direct Acquisition by Dessi Georgieva"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("campaign");
          }}
        >
          <span className="brand-mark" aria-hidden="true">
            <img
              src="/brand/nested-squares.svg"
              alt=""
              width="44"
              height="44"
            />
          </span>
          <span className="product-signature">
            Direct<span>Acquisition</span>
            <small>By Dessi Georgieva</small>
          </span>
        </a>
        <div className="workspace-label">
          WORKSPACE <span>01</span>
        </div>
        <nav aria-label="Workspace navigation">
          {nav.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={page === id ? "nav-item active" : "nav-item"}
              onClick={() => setPage(id)}
            >
              <Icon size={17} />
              {label}
              {id === "campaign" && (
                <span className="nav-count">{sessions.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-heading">
          CAMPAIGNS
          <button
            title="New campaign"
            aria-label="New campaign"
            onClick={() => {
              setParent(null);
              setCreating(true);
            }}
            disabled={!!busy}
          >
            <Plus size={15} />
          </button>
        </div>
        <div className="campaign-list">
          {sessions.map((s) => (
            <button
              key={s.id}
              className={`campaign-link ${s.id === selected ? "selected" : ""}`}
              onClick={() => {
                if (!busy) {
                  setSelected(s.id);
                  setPage("campaign");
                  setNotice("");
                }
              }}
              disabled={!!busy}
            >
              <span className="tiny-dot" />
              <span>
                <strong>{s.name.split(" / ")[0]}</strong>
                <small>
                  {s.mode === "model" ? "GPT-OSS-120B" : "Offline fixture"} ·{" "}
                  {new Date(s.created_at * 1000).toLocaleDateString("en-GB", {
                    day: "numeric",
                    month: "short",
                  })}
                </small>
              </span>
            </button>
          ))}
          {!sessions.length && (
            <p className="sidebar-empty">Your campaigns will appear here.</p>
          )}
        </div>
        <div className="sidebar-bottom">
          <div className="sandbox-label">
            <FlaskConical size={16} />
            <span>Synthetic sandbox</span>
            <span className="live-dot" />
          </div>
          <p>
            Local identities. Simulated delivery.
            <br />
            No production data.
          </p>
          <div className="profile">
            <span className="avatar">LR</span>
            <span>
              Local reviewer<small>Trusted local workspace</small>
            </span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <Layers3 size={16} />
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{nav.find((n) => n.id === page)?.label}</strong>
          </div>
          <div className="top-actions">
            <span className="environment">
              <span className="live-dot" /> LOCAL DEMO
            </span>
            <button
              className="icon-button"
              title="Refresh current state"
              aria-label="Refresh current state"
              disabled={!!busy || !selected}
              onClick={refresh}
            >
              <RefreshCw
                size={16}
                className={busy === "Refreshing" ? "spin" : ""}
              />
            </button>
            <span className="avatar small">LR</span>
          </div>
        </header>
        <main id="workspace-main">
          <div className="page-heading">
            <div>
              <div className="eyebrow">ACQUISITION OPERATIONS</div>
              <h1>
                {page === "campaign"
                  ? "Campaign workspace"
                  : page === "evidence"
                    ? "Product evidence"
                    : page === "learning"
                      ? "Campaign learning"
                      : "Activity log"}
              </h1>
              <p>
                {page === "campaign"
                  ? "From audience selection to a reviewed, traceable campaign."
                  : page === "evidence"
                    ? "The source material and qualifications behind this campaign."
                    : page === "learning"
                      ? "Counted outcomes, uncertainty and the next experiment."
                      : "Decisions and receipts, in the order they were committed."}
              </p>
            </div>
            <button
              className="button primary"
              onClick={() => {
                setParent(null);
                setCreating(true);
              }}
              disabled={!!busy}
            >
              <Plus size={16} />
              New campaign
            </button>
          </div>
          {error && (
            <div className="message error" role="alert">
              <AlertTriangle size={17} />
              <span>{error}</span>
              <button
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={15} />
              </button>
            </div>
          )}
          {notice && (
            <div className="message success" role="status">
              <Check size={17} />
              <span>{notice}</span>
              <button
                className="icon-button"
                aria-label="Dismiss notification"
                onClick={() => setNotice("")}
              >
                <X size={15} />
              </button>
            </div>
          )}
          {busy && (
            <div className="busy-line" role="status">
              <Loader2 size={14} className="spin" />
              {busy === "Creating campaign" && mode === "model"
                ? "Generating and checking copy. Up to 10 bounded model calls."
                : `${busy.replaceAll("-", " ")} in progress…`}
            </div>
          )}
          {!selected && !sessions.length ? (
            <Empty icon={Mail} title="Prepare your first campaign">
              <p>
                Explore audience selection, exact-draft review and response
                learning in one local sandbox.
              </p>
              <button
                className="button primary"
                onClick={() => {
                  setParent(null);
                  setCreating(true);
                }}
              >
                <Plus size={16} />
                Create a synthetic campaign
              </button>
            </Empty>
          ) : !state ? (
            <div className="loading">
              <Loader2 className="spin" size={22} />
              Loading campaign
            </div>
          ) : !view ? (
            <Empty icon={Clock3} title="Campaign preparation">
              <p>
                This campaign has not reached review. Resume preparation to
                recover persisted tasks.
              </p>
              <button
                className="button primary"
                onClick={() => act("prepare")}
                disabled={!!busy}
              >
                Resume preparation
              </button>
              <details>
                <summary>Task state</summary>
                <pre>{JSON.stringify(state.tasks, null, 2)}</pre>
              </details>
            </Empty>
          ) : (
            <>
              <section className="campaign-header">
                <div>
                  <span className="campaign-number">
                    CAMPAIGN / {state.session.id.slice(-6).toUpperCase()}
                  </span>
                  <h2>Working capital exploration</h2>
                  <div className="campaign-meta">
                    <span>
                      <Clock3 size={13} />
                      {date(state.session.clock)} ·{" "}
                      {state.session.clock_mode === "SIMULATED"
                        ? "Simulated clock"
                        : "Sandbox clock"}
                    </span>
                    <span>Revision {view.subject.revision}</span>
                    <Badge
                      tone={
                        view.handoff || view.approval_valid
                          ? "green"
                          : !view.candidate_valid
                            ? "amber"
                            : "neutral"
                      }
                    >
                      {status}
                    </Badge>
                  </div>
                </div>
                <button
                  className="button secondary"
                  onClick={() =>
                    download(selected, "manifest", view.subject.id).catch((e) =>
                      setError(e.message),
                    )
                  }
                >
                  <ArrowDownToLine size={15} />
                  Manifest
                </button>
              </section>
              <div className="stage-strip" aria-label="Campaign progress">
                {[
                  { label: "Audience prepared", done: true },
                  { label: "Copy prepared", done: true },
                  {
                    label: "Human review",
                    done: view.approval_valid || !!view.handoff,
                  },
                  { label: "Simulated handoff", done: !!view.handoff },
                  {
                    label: "Outcome learning",
                    done: state.learning?.status === "finalized",
                  },
                ].map((s, i) => (
                  <div
                    key={s.label}
                    className={s.done ? "stage done" : "stage"}
                  >
                    <span>
                      {s.done ? (
                        <Check size={11} />
                      ) : (
                        String(i + 1).padStart(2, "0")
                      )}
                    </span>
                    {s.label}
                    {i < 4 && <ChevronRight size={13} />}
                  </div>
                ))}
              </div>
              {page === "campaign" && (
                <>
                  <section className="metrics">
                    {[
                      {
                        label: "Source audience",
                        value: view.manifest.counts.input.toLocaleString(),
                        note: "Synthetic business records",
                        icon: Users,
                      },
                      {
                        label: "Mailing recipients",
                        value: view.manifest.counts.mailed.toLocaleString(),
                        note: `${view.manifest.counts.excluded} excluded by policy`,
                        icon: Mail,
                      },
                      {
                        label: "No-mail control",
                        value: view.manifest.counts.holdout.toLocaleString(),
                        note: "Within the selected cohort",
                        icon: FlaskConical,
                      },
                      {
                        label: "Mailing estimate",
                        value: money(view.manifest.variable_cost_pence),
                        note: "Synthetic variable cost",
                        icon: FileText,
                      },
                    ].map((m) => (
                      <div className="metric" key={m.label}>
                        <div>
                          {m.label}
                          <m.icon size={16} />
                        </div>
                        <strong>{m.value}</strong>
                        <small>{m.note}</small>
                      </div>
                    ))}
                  </section>
                  <div className="campaign-grid">
                    <section className="workspace-body">
                      <div
                        onKeyDown={(event) => {
                          if (
                            ![
                              "ArrowLeft",
                              "ArrowRight",
                              "Home",
                              "End",
                            ].includes(event.key)
                          )
                            return;
                          event.preventDefault();
                          const next =
                            event.key === "Home"
                              ? "audience"
                              : event.key === "End"
                                ? "copy"
                                : tab === "audience"
                                  ? "copy"
                                  : "audience";
                          setTab(next);
                          event.currentTarget
                            .querySelector<HTMLButtonElement>(`#${next}-tab`)
                            ?.focus();
                        }}
                        className="section-tabs"
                        role="tablist"
                        aria-label="Campaign details"
                      >
                        <button
                          role="tab"
                          id="audience-tab"
                          aria-controls="audience-panel"
                          tabIndex={tab === "audience" ? 0 : -1}
                          aria-selected={tab === "audience"}
                          onClick={() => setTab("audience")}
                          className={tab === "audience" ? "active" : ""}
                        >
                          <Users size={16} />
                          Audience<span>{state.audience.length}</span>
                        </button>
                        <button
                          role="tab"
                          id="copy-tab"
                          aria-controls="copy-panel"
                          tabIndex={tab === "copy" ? 0 : -1}
                          aria-selected={tab === "copy"}
                          onClick={() => setTab("copy")}
                          className={tab === "copy" ? "active" : ""}
                        >
                          <FileText size={16} />
                          Copy variants<span>4</span>
                        </button>
                      </div>
                      {tab === "audience" ? (
                        <AudienceView
                          state={state}
                          busy={!!busy}
                          act={act}
                          onError={setError}
                        />
                      ) : (
                        <CopyView state={state} />
                      )}
                    </section>
                    <ReviewPanel
                      state={state}
                      busy={!!busy}
                      act={act}
                      error={error}
                      onEvidence={() => setPage("evidence")}
                    />
                  </div>
                </>
              )}
              {page === "evidence" && (
                <section className="evidence-layout">
                  <div>
                    <div className="section-title">
                      <div>
                        <h3>Reviewed product facts</h3>
                        <p>
                          Locked wording and qualifications, kept separate from
                          generated framing.
                        </p>
                      </div>
                      <Badge tone="green">Source-bound</Badge>
                    </div>
                    {view.authority.pack.facts.map((f) => (
                      <article className="fact" key={f.id}>
                        <ShieldCheck size={20} />
                        <div>
                          <h3>{f.copy}</h3>
                          <p>{f.qualification}</p>
                          <code>{f.id}</code>
                        </div>
                      </article>
                    ))}
                    <div className="policy-note">
                      <AlertTriangle size={17} />
                      <p>
                        Sources are manually verified and activated. The
                        semantic claim screen can make mistakes and never grants
                        approval.
                      </p>
                    </div>
                  </div>
                  <aside className="evidence-aside">
                    <h3>Evidence registry</h3>
                    <dl>
                      <dt>Checked on</dt>
                      <dd>{view.authority.pack.checked_on}</dd>
                      <dt>Review due</dt>
                      <dd>{view.authority.pack.review_by}</dd>
                      <dt>Evidence version</dt>
                      <dd>Epoch {view.subject.evidence_epoch}</dd>
                      <dt>Suppression version</dt>
                      <dd>Epoch {view.subject.audience_epoch}</dd>
                    </dl>
                    {view.authority.pack.sources.map((s) => (
                      <a
                        className="source-link"
                        key={s.url}
                        href={s.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {s.title}
                        <ArrowUpRight size={16} />
                      </a>
                    ))}
                    <details>
                      <summary>Review policy</summary>
                      <pre>
                        {JSON.stringify(view.authority.policy, null, 2)}
                      </pre>
                    </details>
                  </aside>
                </section>
              )}
              {page === "learning" && (
                <LearningView
                  state={state}
                  busy={!!busy}
                  act={act}
                  onCampaign={() => setPage("campaign")}
                  onNext={() => {
                    setParent(selected);
                    setCreating(true);
                  }}
                />
              )}
              {page === "activity" && (
                <section className="activity">
                  <div className="section-title">
                    <div>
                      <h3>Campaign history</h3>
                      <p>
                        Persisted domain events. Replayed receipts do not repeat
                        effects.
                      </p>
                    </div>
                    <Badge>
                      {view.events.length +
                        (state.learning?.events.length ?? 0)}{" "}
                      events
                    </Badge>
                  </div>
                  {[...view.events, ...(state.learning?.events ?? [])]
                    .sort((a, b) => a.at - b.at)
                    .map((ev, i) => (
                      <div className="event" key={`${ev.kind}-${i}`}>
                        <span className="event-line">
                          <Check size={12} />
                        </span>
                        <div>
                          <h4>{ev.kind.replaceAll("_", " ")}</h4>
                          <p>
                            {date(ev.at)}
                            {ev.payload.actor
                              ? ` · ${String(ev.payload.actor)}`
                              : ""}
                          </p>
                          <details>
                            <summary>View committed receipt</summary>
                            <pre>{JSON.stringify(ev.payload, null, 2)}</pre>
                          </details>
                        </div>
                      </div>
                    ))}
                </section>
              )}
            </>
          )}
          <footer className="workspace-footer">
            <span>
              <FlaskConical size={13} />
              Synthetic audience and outcomes
            </span>
            <span>
              Dessi Georgieva · Independent product demo · No production
              connection
            </span>
          </footer>
        </main>
      </div>
      {creating && (
        <Modal
          label="new-title"
          busy={!!busy}
          onClose={() => setCreating(false)}
        >
          <button
            className="modal-close icon-button"
            aria-label="Close new campaign"
            disabled={!!busy}
            onClick={() => setCreating(false)}
          >
            <X size={18} />
          </button>
          <span className="modal-icon">
            <Mail size={24} />
          </span>
          <h2 id="new-title">New synthetic campaign</h2>
          <p>
            Prepare 1,000 business records, two audience segments and four copy
            variants in an isolated sandbox.
          </p>
          {parent && (
            <div className="modal-note">
              <BarChart3 size={17} />
              <span>
                Finalized learning from the current campaign will be frozen into
                new model copy. The previous approval will not carry over.
              </span>
            </div>
          )}
          <fieldset disabled={!!busy}>
            <legend>Copy preparation</legend>
            <label
              className={`mode-option ${mode === "fixture" ? "selected" : ""}`}
            >
              <input
                type="radio"
                name="copy-mode"
                value="fixture"
                checked={mode === "fixture"}
                onChange={() => setMode("fixture")}
              />
              <span>
                <strong>
                  Offline fixtures<Badge>NO API COST</Badge>
                </strong>
                <small>
                  Fast, repeatable inputs for exploring review and learning.
                  Uses a labelled simulated clock.
                </small>
              </span>
            </label>
            <label
              className={`mode-option ${mode === "model" ? "selected" : ""}`}
            >
              <input
                type="radio"
                name="copy-mode"
                value="model"
                checked={mode === "model"}
                onChange={() => setMode("model")}
              />
              <span>
                <strong>
                  Generate with GPT-OSS-120B
                  <Sparkles size={15} />
                </strong>
                <small>
                  Uses the server's OpenRouter key and credit. Up to 10 bounded
                  calls with product-claim checks.
                </small>
              </span>
            </label>
          </fieldset>
          <div className="modal-note">
            <ShieldCheck size={16} />
            Copy remains unreviewed. Approval applies only to a local simulated
            handoff.
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button
            className="button primary wide"
            onClick={create}
            disabled={!!busy}
          >
            {busy ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}{" "}
            {busy ? "Preparing campaign…" : "Prepare campaign"}
          </button>
        </Modal>
      )}
    </div>
  );
}
