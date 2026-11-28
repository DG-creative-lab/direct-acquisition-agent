import { useEffect, useRef, useState } from "react";
import { read, token } from "./api";
import type { BriefInput, CompanyInput, IntakeSnapshot } from "./intake-api";
import {
  dispatchOutcome,
  inspectOutcome,
  outcomePending,
  outcomePreview,
  outcomeStore,
  saveOutcomeIntent,
} from "./outcomes-api";
import type { OutcomeOperation, OutcomePending } from "./outcomes-api";
import "./outcomes.css";

type Context = {
  company: IntakeSnapshot<CompanyInput>;
  brief: IntakeSnapshot<BriefInput>;
};
type Cohort = {
  id: string;
  campaign_id: string;
  channel: string;
  data_class: string;
  metric: string;
  qualification_rule: string;
  window_start: number;
  window_end: number;
  assignments: { arm: string }[];
  prior: { alpha: number; beta: number };
  assignment_design: string;
  sources: { id: string; system: string; account_id: string; role: string }[];
};
type Group = {
  segment: string;
  arm: string;
  trials: number;
  successes: number;
  alpha: number;
  beta: number;
  mean: number;
};
type CohortItem = Pick<
  Cohort,
  "id" | "campaign_id" | "channel" | "data_class"
> & { company_context: Context | null };
type View = {
  cohort: Cohort;
  company_context: Context | null;
  status: string;
  current: boolean;
  received: number;
  missing: number;
  successes: number;
  coverage_complete: boolean;
  event_counts: Record<string, number>;
  business_counts: Record<string, number>;
  posterior_groups: Group[];
  comparisons: unknown[];
  reports: { report_id: string; final: boolean }[];
  reconciliation: { status: string; excluded_diagnostics: number };
  finalization: unknown;
  limitations: string[];
};
type Preview = {
  preview_id: string;
  operation: OutcomeOperation;
  company_context: Context | null;
  manifest?: Cohort;
  cohort?: Cohort;
  writable: boolean;
  report?: Record<string, unknown>;
  events?: number;
  eligible?: boolean;
  posterior_groups?: Group[];
  comparisons?: unknown[];
  summary?: unknown;
};
type Evidence = {
  snapshot_id: string;
  snapshot: unknown;
  reconciliation: unknown;
  observation: string;
};
const enc = encodeURIComponent;
const human = (value: string) => value.replaceAll("_", " ");
const date = (value: number) => new Date(value * 1000).toLocaleString();
function Json({ label, value }: { label: string; value: unknown }) {
  return (
    <details>
      <summary>{label}</summary>
      <pre tabIndex={0} role="region" aria-label={label}>
        <code>{JSON.stringify(value, null, 2)}</code>
      </pre>
    </details>
  );
}
function Groups({ groups }: { groups: Group[] }) {
  return (
    <div
      className="outcomes-scroll"
      tabIndex={0}
      role="region"
      aria-label="Posterior outcome groups"
    >
      <table>
        <caption>
          Qualified enquiries per independent business. Prior plus observed
          outcomes.
        </caption>
        <thead>
          <tr>
            <th>Segment / arm</th>
            <th>Outcomes</th>
            <th>Qualified</th>
            <th>Beta posterior</th>
            <th>Estimated rate</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => (
            <tr key={g.segment + g.arm}>
              <th scope="row">
                {g.segment} / {g.arm}
              </th>
              <td>{g.trials}</td>
              <td>{g.successes}</td>
              <td>
                {g.alpha}, {g.beta}
              </td>
              <td>{(g.mean * 100).toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function OutcomesWorkspace({
  onIntake,
}: {
  onIntake: () => void;
}) {
  const [store, setStore] = useState("");
  const [companies, setCompanies] = useState<IntakeSnapshot<CompanyInput>[]>(
    [],
  );
  const [briefs, setBriefs] = useState<IntakeSnapshot<BriefInput>[]>([]);
  const [company, setCompany] = useState("");
  const [brief, setBrief] = useState("");
  const [briefRevision, setBriefRevision] = useState(0);
  const [cohorts, setCohorts] = useState<CohortItem[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [selected, setSelected] = useState("");
  const [view, setView] = useState<View | null>(null);
  const [source, setSource] = useState("");
  const [operation, setOperation] = useState<OutcomeOperation>("register");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [pending, setPending] = useState<OutcomePending | null>(null);
  const [snapshot, setSnapshot] = useState<{
    report: string;
    value: Evidence;
  } | null>(null);
  const [receipt, setReceipt] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [moreCompanies, setMoreCompanies] = useState(false);
  const [moreBriefs, setMoreBriefs] = useState(false);
  const generation = useRef(0);
  const errorRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      outcomeStore(),
      outcomePending(),
      read<{ items: IntakeSnapshot<CompanyInput>[] }>(
        "/api/intake/companies",
        controller.signal,
      ),
      read<{ items: IntakeSnapshot<BriefInput>[] }>(
        "/api/intake/briefs",
        controller.signal,
      ),
    ])
      .then(([identity, saved, cs, bs]) => {
        if (controller.signal.aborted) return;
        setStore(identity);
        setPending(saved);
        setCompanies(cs.items);
        setBriefs(bs.items);
        setMoreCompanies(cs.items.length === 50);
        setMoreBriefs(bs.items.length === 50);
        if (saved?.store_id === identity) setCompany(saved.company_id);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(String(e.message));
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!store) return;
    const controller = new AbortController();
    read<{ items: CohortItem[]; next_after: string | null }>(
      `/api/outcomes/cohorts?company_id=${enc(company)}`,
      controller.signal,
    )
      .then((result) => {
        if (!controller.signal.aborted) {
          setCohorts(result.items);
          setNext(result.next_after);
        }
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [store, company, refresh]);
  useEffect(() => {
    setView(null);
    setSnapshot(null);
    setPreview(null);
    if (!selected) return;
    const controller = new AbortController();
    read<View>(`/api/outcomes/cohorts/${enc(selected)}`, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setView(result);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [selected, refresh]);
  function invalidate() {
    generation.current++;
    setPreview(null);
    setError("");
    setNotice("");
    setReceipt(null);
  }
  async function act(work: () => Promise<void>) {
    const current = generation.current;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
    } catch (e) {
      if (current === generation.current)
        setError(
          e instanceof Error ? e.message : "Unable to load recorded outcomes.",
        );
    } finally {
      if (current === generation.current) {
        setBusy(false);
        try {
          setPending(await outcomePending());
        } catch {
          setError(
            "Recovery storage could not be read. Reload before continuing.",
          );
        }
      }
    }
  }
  const selectedBrief = briefs.find((b) => b.id === brief);
  const selection = selectedBrief
    ? {
        brief_id: selectedBrief.id,
        brief_revision: briefRevision || selectedBrief.revision,
      }
    : null;
  function previewPayload() {
    return operation === "register"
      ? { source, selection }
      : operation === "import"
        ? { source, cohort_id: selected }
        : { cohort_id: selected };
  }
  async function submit() {
    if (!preview?.company_context) return;
    const context = preview.company_context;
    const saved = await saveOutcomeIntent({
      store_id: store,
      operation,
      company_name: context.company.draft.company_name,
      company_id: context.company.id,
      payload: { ...previewPayload(), preview_id: preview.preview_id },
    });
    setPending(saved);
    await recover(saved);
  }
  async function recover(saved: OutcomePending) {
    const result = await dispatchOutcome(saved);
    setReceipt(result);
    setPreview(null);
    setSource("");
    setCompany(saved.company_id);
    setSelected(result.result.cohort_id);
    setRefresh((n) => n + 1);
    setNotice(
      "Original request reconciled. Its saved receipt is historical evidence and grants no send or approval authority.",
    );
  }
  async function more(kind: "companies" | "briefs") {
    if (kind === "companies") {
      const result = await read<{ items: IntakeSnapshot<CompanyInput>[] }>(
        `/api/intake/companies?after_id=${enc(companies.at(-1)?.id ?? "")}`,
      );
      setCompanies((old) => [...old, ...result.items]);
      setMoreCompanies(result.items.length === 50);
    } else {
      const result = await read<{ items: IntakeSnapshot<BriefInput>[] }>(
        `/api/intake/briefs?after_id=${enc(briefs.at(-1)?.id ?? "")}`,
      );
      setBriefs((old) => [...old, ...result.items]);
      setMoreBriefs(result.items.length === 50);
    }
  }
  const locked = busy || !!pending;
  return (
    <div className="outcomes-page" aria-busy={busy}>
      <header>
        <p className="eyebrow">LEARNING / RECORDED CAMPAIGNS</p>
        <h1>Recorded outcomes</h1>
        <p>
          Register an already dispatched email or postal campaign, import its
          source reports and review qualified-enquiry learning.
        </p>
      </header>
      <p className="outcomes-boundary">
        External records are operator-attested. Recorded fixtures remain
        labeled. Missing outcomes stay unknown. Opens, clicks and raw replies
        are diagnostics. This workspace does not send messages or update
        synthetic or YouTube learning.
      </p>
      {error && (
        <p className="outcomes-error" role="alert" tabIndex={-1} ref={errorRef}>
          {error}
        </p>
      )}
      <p role="status">{busy ? "Working with recorded evidence…" : notice}</p>
      {pending && (
        <section
          className="outcomes-warning"
          aria-label="Pending original outcome request"
        >
          <h2>Recover original request</h2>
          <p>
            {human(pending.operation)} for {pending.company_name}. Request{" "}
            {pending.payload.request_id} is retained with its original source
            and workspace store.
          </p>
          <p>
            Restore the original workspace if the store has changed. A new
            request cannot replace uncertain work.
          </p>
          <button
            disabled={busy}
            onClick={() => void act(() => recover(pending))}
          >
            Recover original request
          </button>
          <button
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const saved = await inspectOutcome(pending);
                setReceipt({
                  company_name: pending.company_name,
                  historical_receipt: saved,
                });
                setNotice(
                  "Historical receipt inspected. The original request remains retained for recovery.",
                );
              })
            }
          >
            Inspect saved request receipt
          </button>
        </section>
      )}
      <section>
        <h2>Company and campaign brief</h2>
        <p>
          The selected brief freezes its saved company revision. This
          association is context, not approval.
        </p>
        <label htmlFor="outcomes-company">Company</label>
        <select
          id="outcomes-company"
          value={company}
          disabled={locked}
          onChange={(e) => {
            invalidate();
            setCompany(e.target.value);
            setBrief("");
            setBriefRevision(0);
            setSelected("");
          }}
        >
          <option value="">All cohorts, including unassociated history</option>
          {companies.map((c) => (
            <option value={c.id} key={c.id}>
              {c.draft.company_name}
            </option>
          ))}
        </select>
        {moreCompanies && (
          <button
            disabled={locked}
            onClick={() => void act(() => more("companies"))}
          >
            Load more companies
          </button>
        )}
        <label htmlFor="outcomes-saved-campaign-brief">
          Saved campaign brief
        </label>
        <select
          id="outcomes-saved-campaign-brief"
          value={brief}
          disabled={locked || !company}
          onChange={(e) => {
            invalidate();
            setBrief(e.target.value);
            setBriefRevision(0);
          }}
        >
          <option value="">Select a brief revision for registration</option>
          {briefs
            .filter((b) => b.draft.company_id === company)
            .map((b) => (
              <option key={b.id} value={b.id}>
                {b.draft.objective || b.id} / brief v{b.revision}, company v
                {b.draft.company_revision}
              </option>
            ))}
        </select>
        {selectedBrief && (
          <label>
            Brief revision to associate
            <input
              type="number"
              min={1}
              max={selectedBrief.revision}
              step={1}
              value={briefRevision || selectedBrief.revision}
              disabled={locked}
              onChange={(e) => {
                invalidate();
                setBriefRevision(Number(e.target.value));
              }}
            />
          </label>
        )}
        {moreBriefs && (
          <button
            disabled={locked}
            onClick={() => void act(() => more("briefs"))}
          >
            Load more briefs
          </button>
        )}
        <button disabled={busy} onClick={onIntake}>
          Open company and brief intake
        </button>
      </section>
      <section>
        <h2>Saved campaigns</h2>
        {!cohorts.length && (
          <p>
            No registered cohorts in this selection. Select a saved brief and
            review a registration manifest below.
          </p>
        )}
        <label htmlFor="outcomes-recorded-campaign">Recorded campaign</label>
        <select
          id="outcomes-recorded-campaign"
          value={selected}
          disabled={locked}
          onChange={(e) => {
            invalidate();
            setSelected(e.target.value);
            setOperation("import");
          }}
        >
          <option value="">Select a cohort</option>
          {cohorts.map((c) => (
            <option key={c.id} value={c.id}>
              {c.campaign_id} / {c.channel} / {human(c.data_class)}
              {c.company_context ? "" : " / unassociated history"}
            </option>
          ))}
        </select>
        {next && (
          <button
            disabled={locked}
            onClick={() =>
              void act(async () => {
                const result = await read<{
                  items: CohortItem[];
                  next_after: string | null;
                }>(
                  `/api/outcomes/cohorts?company_id=${enc(company)}&after_id=${enc(next)}`,
                );
                setCohorts((old) => [...old, ...result.items]);
                setNext(result.next_after);
              })
            }
          >
            Load more cohorts
          </button>
        )}
        <button
          disabled={locked || !selected}
          onClick={() => {
            invalidate();
            setRefresh((n) => n + 1);
          }}
        >
          Refresh current evidence
        </button>
      </section>
      {view && (
        <section aria-label="Current cohort evidence">
          <h2>{view.cohort.campaign_id}</h2>
          <p>
            <strong>{human(view.cohort.data_class)}</strong> /{" "}
            {view.cohort.channel} / {human(view.status)}
          </p>
          {view.company_context ? (
            <p>
              Frozen company: {view.company_context.company.draft.company_name}{" "}
              v{view.company_context.company.revision}. Brief v
              {view.company_context.brief.revision}.
            </p>
          ) : (
            <p>
              Unassociated historical cohort. Inspection only in this browser.
              Its original identity has not been rewritten.
            </p>
          )}
          <p>
            Observation window: {date(view.cohort.window_start)} to{" "}
            {date(view.cohort.window_end)}.
          </p>
          <p>Qualification rule: {view.cohort.qualification_rule}</p>
          <dl className="outcomes-counts">
            <div>
              <dt>Explicit outcomes</dt>
              <dd>{view.received}</dd>
            </div>
            <div>
              <dt>Unknown outcomes</dt>
              <dd>{view.missing}</dd>
            </div>
            <div>
              <dt>Qualified enquiries</dt>
              <dd>{view.successes}</dd>
            </div>
            <div>
              <dt>Complete final snapshot</dt>
              <dd>{view.coverage_complete ? "Yes" : "No"}</dd>
            </div>
          </dl>
          <h3>Diagnostics</h3>
          <p>
            Event counts can repeat. Independent businesses are counted
            separately. Excluded diagnostics:{" "}
            {view.reconciliation.excluded_diagnostics}.
          </p>
          <Json
            label="Diagnostic events and independent businesses"
            value={{
              events: view.event_counts,
              businesses: view.business_counts,
              reconciliation: view.reconciliation,
            }}
          />
          {view.posterior_groups.length > 0 && (
            <>
              <h3>Current eligible learning</h3>
              <Groups groups={view.posterior_groups} />
              <Json
                label="Current comparison and statistical limits"
                value={view.comparisons}
              />
              <p>
                Advisory only. Any next campaign needs a new proposal and
                approval.
              </p>
            </>
          )}
          <h3>Source report history</h3>
          {view.reports.length === 0 && <p>No imported reports yet.</p>}
          {view.reports.map((r) => (
            <button
              disabled={busy}
              key={r.report_id}
              onClick={() =>
                void act(async () => {
                  const value = await read<Evidence>(
                    `/api/outcomes/cohorts/${enc(selected)}/reports/${enc(r.report_id)}`,
                  );
                  setSnapshot({ report: r.report_id, value });
                })
              }
            >
              Inspect report {r.report_id}
              {r.final ? " (final snapshot)" : ""}
            </button>
          ))}
          {snapshot && (
            <div>
              <h4>Historical source: {snapshot.report}</h4>
              <p>
                Original saved evidence, not current authorization. Snapshot{" "}
                {snapshot.value.snapshot_id}.
              </p>
              <Json label="Original saved report" value={snapshot.value} />
              <button
                disabled={busy}
                onClick={() =>
                  void act(async () => {
                    const response = await fetch(
                      `/api/outcomes/cohorts/${enc(selected)}/reports/${enc(snapshot.report)}?snapshot_id=${enc(snapshot.value.snapshot_id)}`,
                      { headers: { "X-Workspace-Token": token() } },
                    );
                    if (!response.ok)
                      throw new Error(
                        "Displayed report changed or is unavailable. Inspect it again.",
                      );
                    const url = URL.createObjectURL(await response.blob());
                    const link = document.createElement("a");
                    link.href = url;
                    link.download = "recorded-outcomes-report.json";
                    link.click();
                    setTimeout(() => URL.revokeObjectURL(url), 1000);
                  })
                }
              >
                Download displayed report
              </button>
            </div>
          )}
          {view.finalization !== null && (
            <Json
              label="Historical finalization receipt"
              value={view.finalization}
            />
          )}
          <Json
            label="Frozen cohort and limitations"
            value={{
              cohort: view.cohort,
              company_context: view.company_context,
              limitations: view.limitations,
            }}
          />
        </section>
      )}
      <section>
        <h2>Review an intake</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void act(async () => {
              const value = await outcomePreview<Preview>(
                store,
                operation,
                previewPayload(),
              );
              setPreview(value);
            });
          }}
        >
          <label htmlFor="outcomes-operation">Operation</label>
          <select
            id="outcomes-operation"
            value={operation}
            disabled={locked}
            onChange={(e) => {
              invalidate();
              setOperation(e.target.value as OutcomeOperation);
              setSource("");
            }}
          >
            <option value="register">Register dispatched campaign</option>
            <option value="import">Import source report</option>
            <option value="finalize">Review finalization</option>
          </select>
          {operation !== "finalize" && (
            <>
              <label>
                JSON evidence file
                <input
                  type="file"
                  accept=".json,application/json"
                  disabled={locked}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    invalidate();
                    setSource("");
                    if (!file) return;
                    if (file.size > 4 * 1024 * 1024) {
                      setError("Evidence files are limited to four MiB.");
                      return;
                    }
                    void act(async () => {
                      setSource(await file.text());
                    });
                  }}
                />
              </label>
              <label>
                Original JSON source
                <textarea
                  value={source}
                  spellCheck={false}
                  disabled={locked}
                  onChange={(e) => {
                    invalidate();
                    setSource(e.target.value);
                  }}
                  rows={8}
                />
              </label>
              <p>
                Four MiB maximum. Source text is parsed strictly on the server.
                Provider tokens and local file paths are not required.
              </p>
            </>
          )}
          <button
            type="submit"
            disabled={
              locked ||
              !store ||
              (operation === "register"
                ? !selection || !source
                : !selected || (operation === "import" && !source))
            }
          >
            Preview{" "}
            {operation === "register"
              ? "registration"
              : operation === "import"
                ? "report"
                : "finalization"}
          </button>
        </form>
        {preview && (
          <div className="outcomes-preview" aria-label="Reviewed evidence">
            <h3>Review before saving</h3>
            <p>
              Company:{" "}
              {preview.company_context?.company.draft.company_name ??
                "Unassociated history"}
              . Company v{preview.company_context?.company.revision}, brief v
              {preview.company_context?.brief.revision}.
            </p>
            <p>
              Campaign: {(preview.manifest ?? preview.cohort)?.campaign_id}.{" "}
              <strong>
                {human((preview.manifest ?? preview.cohort)?.data_class ?? "")}
              </strong>
              . {(preview.manifest ?? preview.cohort)?.assignments.length}{" "}
              original assignments.
            </p>
            {(preview.manifest ?? preview.cohort) &&
              (() => {
                const c = (preview.manifest ?? preview.cohort)!;
                return (
                  <>
                    <p>
                      Channel: {c.channel}. Design: {human(c.assignment_design)}
                      . Prior: Beta({c.prior.alpha}, {c.prior.beta}).
                    </p>
                    <p>
                      Window: {date(c.window_start)} to {date(c.window_end)}.
                    </p>
                    <p>Qualification rule: {c.qualification_rule}</p>
                    <p>
                      Original groups:{" "}
                      {["A", "B", "holdout"]
                        .map(
                          (arm) =>
                            `${arm}: ${c.assignments.filter((m) => m.arm === arm).length}`,
                        )
                        .join("; ")}
                      .
                    </p>
                    <p>
                      Sources:{" "}
                      {c.sources
                        .map(
                          (s) =>
                            `${s.role}: ${s.system} / ${s.account_id} (${s.id})`,
                        )
                        .join("; ")}
                      .
                    </p>
                  </>
                );
              })()}
            {preview.events !== undefined && (
              <p>
                {preview.events} source events. Duplicate source IDs will be
                reconciled; missing outcomes remain unknown.
              </p>
            )}
            {operation === "finalize" && (
              <p>
                {preview.eligible
                  ? "Mature, complete evidence is available for finalization."
                  : "Finalization is blocked until maturity and complete explicit outcome coverage, or this cohort is already finalized."}
              </p>
            )}
            {preview.posterior_groups &&
              preview.posterior_groups.length > 0 && (
                <Groups groups={preview.posterior_groups} />
              )}
            <Json
              label="Exact reviewed evidence and comparisons"
              value={preview}
            />
            {!preview.writable && (
              <p>
                Saving is blocked for unassociated history, inspection roots or
                paused verified formats.
              </p>
            )}
            <p>
              Confirming records observations or advisory learning only. It
              grants no campaign approval or send authority.
            </p>
            <button
              disabled={
                locked ||
                !preview.writable ||
                (operation === "finalize" && !preview.eligible)
              }
              onClick={() => void act(submit)}
            >
              Confirm{" "}
              {operation === "register"
                ? "registration"
                : operation === "import"
                  ? "report import"
                  : "finalization"}
            </button>
          </div>
        )}
      </section>
      {receipt !== null && (
        <section>
          <h2>Saved request receipt</h2>
          <p>
            Historical evidence. Current eligibility appears in the current
            cohort view.
          </p>
          <Json label="Original request receipt" value={receipt} />
        </section>
      )}
    </div>
  );
}
