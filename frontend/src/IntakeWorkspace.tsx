import {
  createContext,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import type { FormEvent, InputHTMLAttributes } from "react";
import {
  dispatchIntake,
  intakePage,
  intakeRecord,
  intakeStore,
  IntakeRejected,
  pendingIntake,
  queueIntake,
} from "./intake-api";
import type {
  BriefInput,
  CompanyInput,
  IntakeKind,
  IntakePayload,
  IntakeReceipt,
  IntakeSnapshot,
  PendingIntake,
} from "./intake-api";
import "./intake.css";

const emptyCompany = (): CompanyInput => ({
  company_name: "",
  website: "",
  product_name: "",
  description: "",
  official_cta: "",
  cta_url: "",
  source_urls: [],
  claims: [],
});
const emptyBrief = (): BriefInput => ({
  company_id: "",
  company_revision: 1,
  objective: "",
  audience: "",
  country: "",
  currency: "",
  channels: [],
  budget_minor: null,
  max_candidates: null,
  constraints: [],
  contact_source: "unspecified",
});
const lines = (text: string) => text.split("\n");
const nonempty = (values: string[]) => values.filter((value) => value !== "");
const FieldFeedback = createContext<(message: string) => void>(() => {});

type FieldProps = Omit<
  InputHTMLAttributes<HTMLInputElement>,
  "onChange" | "value"
> & {
  label: string;
  value: string;
  onChange: (value: string) => void;
  help?: string;
  multiline?: boolean;
};
function Field({
  label,
  value,
  onChange,
  help,
  multiline,
  ...props
}: FieldProps) {
  const announce = useContext(FieldFeedback);
  const id = useId(),
    edited = useRef(false);
  const control = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (control.current?.validity.valid) setError("");
  }, [value]);
  const common = {
    ref: (node: HTMLInputElement | HTMLTextAreaElement | null) => {
      control.current = node;
    },
    id,
    name: props.name ?? id,
    value,
    maxLength: props.maxLength,
    required: props.required,
    autoCorrect: props.autoCorrect,
    autoCapitalize: props.autoCapitalize,
    spellCheck: props.spellCheck,
    "aria-invalid": Boolean(error),
    "aria-describedby":
      [help ? id + "-help" : "", error ? id + "-error" : ""]
        .filter(Boolean)
        .join(" ") || undefined,
    onChange: (event: {
      currentTarget: HTMLInputElement | HTMLTextAreaElement;
    }) => {
      edited.current = true;
      onChange(event.currentTarget.value);
      if (error && event.currentTarget.validity.valid) {
        setError("");
        announce("");
      }
    },
    onBlur: (event: {
      currentTarget: HTMLInputElement | HTMLTextAreaElement;
    }) => {
      if (edited.current) {
        setError(event.currentTarget.validationMessage);
        if (event.currentTarget.validationMessage)
          announce(`${label}: ${event.currentTarget.validationMessage}`);
      }
    },
    onInvalid: (event: {
      currentTarget: HTMLInputElement | HTMLTextAreaElement;
    }) => setError(event.currentTarget.validationMessage),
  };
  return (
    <div className="intake-field">
      <label htmlFor={id}>{label}</label>
      {help && (
        <p id={id + "-help"} className="intake-help">
          {help}
        </p>
      )}
      {multiline ? (
        <textarea {...common} rows={3} />
      ) : (
        <input {...props} {...common} />
      )}
      {error && (
        <p id={id + "-error"} className="intake-field-error">
          Please correct this field: {error}
        </p>
      )}
    </div>
  );
}

export default function IntakeWorkspace({ active }: { active: boolean }) {
  const [companies, setCompanies] = useState<IntakeSnapshot<CompanyInput>[]>(
    [],
  );
  const [briefs, setBriefs] = useState<IntakeSnapshot<BriefInput>[]>([]);
  const [company, setCompany] = useState(emptyCompany),
    [brief, setBrief] = useState(emptyBrief);
  const [companyBase, setCompanyBase] =
    useState<IntakeSnapshot<CompanyInput> | null>(null);
  const [briefBase, setBriefBase] = useState<IntakeSnapshot<BriefInput> | null>(
    null,
  );
  const [pin, setPin] = useState<IntakeSnapshot<CompanyInput> | null>(null);
  const [pinError, setPinError] = useState("");
  const [pinTouched, setPinTouched] = useState(false);
  const [pending, setPending] = useState<PendingIntake | null>(null);
  const [storeId, setStoreId] = useState("");
  const [storageError, setStorageError] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [loaded, setLoaded] = useState(false),
    [moreCompanies, setMoreCompanies] = useState(false),
    [moreBriefs, setMoreBriefs] = useState(false);
  const [listAttempt, setListAttempt] = useState(0);
  const errorRef = useRef<HTMLDivElement>(null);
  const locked = busy || !!pending || !!storageError || !loaded;
  const companyDirty =
    JSON.stringify(company) !==
    JSON.stringify(companyBase?.draft ?? emptyCompany());
  const briefDirty =
    JSON.stringify(brief) !== JSON.stringify(briefBase?.draft ?? emptyBrief());
  const unsaved =
    (companyDirty && pending?.kind !== "companies") ||
    (briefDirty && pending?.kind !== "briefs");
  useEffect(() => {
    if (!unsaved) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = true;
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);

  function recover() {
    try {
      const saved = pendingIntake();
      setPending(saved);
      setStorageError("");
      if (saved?.kind === "companies") {
        setCompany(saved.payload.draft as CompanyInput);
        setCompanyBase(saved.base as IntakeSnapshot<CompanyInput> | null);
      }
      if (saved?.kind === "briefs") {
        setBrief(saved.payload.draft as BriefInput);
        setBriefBase(saved.base as IntakeSnapshot<BriefInput> | null);
      }
    } catch (failure) {
      setStorageError((failure as Error).message);
    }
  }
  useEffect(recover, []);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    Promise.all([
      intakeStore(controller.signal),
      intakePage<CompanyInput>("companies", "", controller.signal),
      intakePage<BriefInput>("briefs", "", controller.signal),
    ])
      .then(([identity, c, b]) => {
        if (controller.signal.aborted) return;
        setCompanies(c.items);
        setStoreId(identity);
        setBriefs(b.items);
        setMoreCompanies(c.items.length === 50);
        setMoreBriefs(b.items.length === 50);
        setLoaded(true);
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(failure.message);
      });
    return () => controller.abort();
  }, [active, listAttempt]);
  useEffect(() => {
    const controller = new AbortController();
    setPin(null);
    setPinError("");
    if (
      brief.company_id &&
      Number.isInteger(brief.company_revision) &&
      brief.company_revision > 0
    )
      intakeRecord<CompanyInput>(
        "companies",
        brief.company_id,
        brief.company_revision,
        controller.signal,
      )
        .then((value) => {
          if (!controller.signal.aborted) setPin(value);
        })
        .catch((failure) => {
          if (!controller.signal.aborted) setPinError(failure.message);
        });
    return () => controller.abort();
  }, [brief.company_id, brief.company_revision]);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);
  useEffect(() => {
    if (!active) return;
    const title = document.title;
    document.title = "Company & brief | Direct Acquisition";
    return () => {
      document.title = title;
    };
  }, [active]);

  function applyReceipt(kind: IntakeKind, receipt: IntakeReceipt) {
    if (kind === "companies") {
      const snapshot = receipt.snapshot as IntakeSnapshot<CompanyInput>;
      setCompanyBase(snapshot);
      setCompany(snapshot.draft);
      setCompanies((items) =>
        items.some(
          (item) =>
            item.id === snapshot.id && item.revision > snapshot.revision,
        )
          ? items
          : [snapshot, ...items.filter((item) => item.id !== snapshot.id)],
      );
    } else {
      const snapshot = receipt.snapshot as IntakeSnapshot<BriefInput>;
      setBriefBase(snapshot);
      setBrief(snapshot.draft);
      setBriefs((items) =>
        items.some(
          (item) =>
            item.id === snapshot.id && item.revision > snapshot.revision,
        )
          ? items
          : [snapshot, ...items.filter((item) => item.id !== snapshot.id)],
      );
    }
    setNotice(
      `${kind === "companies" ? "Company" : "Brief"} ${receipt.replayed ? "original save confirmed" : "saved"}: version ${receipt.snapshot.revision}.`,
    );
  }
  async function send(saved: PendingIntake) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const receipt = await dispatchIntake(saved);
      setPending(null);
      applyReceipt(saved.kind, receipt);
    } catch (failure) {
      if (failure instanceof IntakeRejected) setPending(null);
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save(event: FormEvent, kind: IntakeKind) {
    event.preventDefault();
    const base = kind === "companies" ? companyBase : briefBase;
    const payload: IntakePayload = {
      id: base?.id ?? null,
      expected_revision: base?.revision ?? 0,
      draft:
        kind === "companies"
          ? {
              ...company,
              source_urls: nonempty(company.source_urls),
              claims: company.claims.map((claim) => ({
                ...claim,
                source_urls: nonempty(claim.source_urls),
              })),
            }
          : {
              ...brief,
              channels: nonempty(brief.channels),
              constraints: nonempty(brief.constraints),
            },
    };
    try {
      const saved = queueIntake(kind, payload, base, storeId);
      setPending(saved);
      await send(saved);
    } catch (failure) {
      setError((failure as Error).message);
    }
  }
  async function open(kind: IntakeKind, id: string) {
    if (locked) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (kind === "companies") {
        const value = await intakeRecord<CompanyInput>(kind, id);
        setCompanyBase(value);
        setCompany(value.draft);
      } else {
        const value = await intakeRecord<BriefInput>(kind, id);
        setBriefBase(value);
        setBrief(value.draft);
      }
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function more(kind: IntakeKind) {
    setBusy(true);
    setError("");
    try {
      if (kind === "companies") {
        const page = await intakePage<CompanyInput>(kind, companies.at(-1)?.id);
        setCompanies((rows) => [
          ...rows,
          ...page.items.filter(
            (next) => !rows.some((row) => row.id === next.id),
          ),
        ]);
        setMoreCompanies(page.items.length === 50);
      } else {
        const page = await intakePage<BriefInput>(kind, briefs.at(-1)?.id);
        setBriefs((rows) => [
          ...rows,
          ...page.items.filter(
            (next) => !rows.some((row) => row.id === next.id),
          ),
        ]);
        setMoreBriefs(page.items.length === 50);
      }
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const c = (field: keyof CompanyInput, value: unknown) =>
    setCompany((prior) => ({ ...prior, [field]: value }));
  const b = (field: keyof BriefInput, value: unknown) =>
    setBrief((prior) => ({ ...prior, [field]: value }));

  return (
    <FieldFeedback.Provider value={setNotice}>
      <section className="intake-page" aria-labelledby="intake-title">
        <div className="page-heading">
          <div>
            <div className="eyebrow">YOUR CAMPAIGN INPUTS</div>
            <h1 id="intake-title">Company & brief</h1>
            <p>
              Save your company details and campaign requirements, then return
              to refine them.
            </p>
          </div>
        </div>
        <p className="intake-boundary">
          User-supplied drafts. Facts are unverified and campaign readiness has
          not been assessed. These drafts are not connected to generation yet.
        </p>
        {storageError && (
          <div role="alert" className="message error">
            {storageError}
            <button type="button" onClick={recover}>
              Check local save recovery
            </button>
          </div>
        )}
        <div ref={errorRef} tabIndex={-1}>
          {error && (
            <p role="alert" className="message error">
              {error}
            </p>
          )}
        </div>
        <p role="status" className="intake-status">
          {notice}
        </p>
        {pending && (
          <div className="intake-recovery">
            <strong>Confirm the original save</strong>
            <p>
              The result is not confirmed. Your original request and text are
              retained in this tab. Confirm it before editing or starting
              another save.
            </p>
            <button
              type="button"
              className="button primary"
              disabled={busy || !!storageError}
              onClick={() => void send(pending)}
            >
              Retry original save
            </button>
          </div>
        )}
        {!loaded && (
          <p>
            Loading saved drafts...{" "}
            <button
              type="button"
              onClick={() => {
                setError("");
                setListAttempt((value) => value + 1);
              }}
            >
              Reload saved drafts
            </button>
          </p>
        )}
        <section className="intake-section" aria-labelledby="company-title">
          <div className="intake-section-heading">
            <div>
              <span className="eyebrow">01 / BUSINESS CONTEXT</span>
              <h2 id="company-title">Company & product</h2>
            </div>
            <span>
              {companyBase
                ? `Editing version ${companyBase.revision}`
                : "New draft"}
            </span>
          </div>
          <div className="intake-records">
            <label htmlFor="intake-company-list">Saved company drafts</label>
            <select
              id="intake-company-list"
              value={companyBase?.id ?? ""}
              disabled={locked || companyDirty}
              onChange={(event) => {
                if (event.target.value)
                  void open("companies", event.target.value);
              }}
            >
              <option value="">Choose a saved company</option>
              {companies.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.draft.company_name || "Untitled company"} · version{" "}
                  {item.revision}
                </option>
              ))}
              {companyBase &&
                !companies.some((row) => row.id === companyBase.id) && (
                  <option value={companyBase.id}>
                    {companyBase.draft.company_name || "Untitled company"} ·
                    selected version {companyBase.revision}
                  </option>
                )}
            </select>
            {companyDirty && (
              <p className="intake-help">
                Save or discard company edits before opening another draft.
              </p>
            )}
            {moreCompanies && (
              <button
                type="button"
                disabled={locked}
                onClick={() => void more("companies")}
              >
                Load more companies
              </button>
            )}
            <div className="intake-actions">
              <button
                type="button"
                disabled={locked || companyDirty}
                onClick={() => {
                  setCompanyBase(null);
                  setCompany(emptyCompany());
                  setNotice("");
                }}
              >
                New company draft
              </button>
              <button
                type="button"
                disabled={locked || !companyDirty}
                onClick={() => setCompany(companyBase?.draft ?? emptyCompany())}
              >
                Discard company edits
              </button>
              {companyBase && (
                <button
                  type="button"
                  disabled={locked}
                  onClick={() => void open("companies", companyBase.id)}
                >
                  Replace edits with latest company
                </button>
              )}
            </div>
          </div>
          <form
            action="/api/intake/companies"
            method="post"
            aria-labelledby="company-title"
            onSubmit={(event) => void save(event, "companies")}
          >
            <fieldset disabled={locked}>
              <legend>Company information</legend>
              <p className="intake-help">
                All fields are optional. Save a partial draft and complete it
                later.
              </p>
              <Field
                label="Company name"
                value={company.company_name}
                onChange={(value) => c("company_name", value)}
                maxLength={600}
                autoComplete="organization"
              />
              <Field
                label="Company website"
                value={company.website}
                onChange={(value) => c("website", value)}
                type="url"
                maxLength={2000}
                autoComplete="url"
                autoCapitalize="none"
                autoCorrect="off"
                spellCheck={false}
                help="An HTTP or HTTPS reference. Saving does not visit or verify the website."
              />
              <Field
                label="Product or service name"
                value={company.product_name}
                onChange={(value) => c("product_name", value)}
                maxLength={600}
              />
              <Field
                label="Company and product description"
                value={company.description}
                onChange={(value) => c("description", value)}
                multiline
                maxLength={8000}
              />
              <Field
                label="Call to action wording"
                value={company.official_cta}
                onChange={(value) => c("official_cta", value)}
                maxLength={600}
              />
              <Field
                label="Call to action URL"
                value={company.cta_url}
                onChange={(value) => c("cta_url", value)}
                type="url"
                maxLength={2000}
                autoCapitalize="none"
                spellCheck={false}
              />
              <Field
                label="Company reference URLs"
                autoCorrect="off"
                autoCapitalize="none"
                spellCheck={false}
                value={company.source_urls.join("\n")}
                onChange={(value) => c("source_urls", lines(value))}
                multiline
                help="One reference per line, up to 20. References remain unverified."
              />
            </fieldset>
            <fieldset disabled={locked}>
              <legend>Product claims and qualifications</legend>
              <p className="intake-help">
                Record your exact wording and any restrictions. These are your
                assertions, not verified campaign facts.
              </p>
              {company.claims.map((claim, index) => (
                <fieldset className="intake-claim" key={index}>
                  <legend>Claim {index + 1}</legend>
                  <Field
                    label={`Claim ${index + 1} statement`}
                    value={claim.statement}
                    required
                    multiline
                    maxLength={4000}
                    onChange={(value) =>
                      c(
                        "claims",
                        company.claims.map((row, i) =>
                          i === index ? { ...row, statement: value } : row,
                        ),
                      )
                    }
                  />
                  <Field
                    label={`Claim ${index + 1} qualifications`}
                    value={claim.qualification}
                    multiline
                    maxLength={4000}
                    onChange={(value) =>
                      c(
                        "claims",
                        company.claims.map((row, i) =>
                          i === index ? { ...row, qualification: value } : row,
                        ),
                      )
                    }
                  />
                  <Field
                    label={`Claim ${index + 1} reference URLs`}
                    autoCorrect="off"
                    autoCapitalize="none"
                    spellCheck={false}
                    value={claim.source_urls.join("\n")}
                    multiline
                    help="One HTTP or HTTPS reference per line, up to 20."
                    onChange={(value) =>
                      c(
                        "claims",
                        company.claims.map((row, i) =>
                          i === index
                            ? { ...row, source_urls: lines(value) }
                            : row,
                        ),
                      )
                    }
                  />
                  <button
                    type="button"
                    onClick={() =>
                      c(
                        "claims",
                        company.claims.filter((_, i) => i !== index),
                      )
                    }
                  >
                    Remove claim {index + 1}
                  </button>
                </fieldset>
              ))}
              <button
                type="button"
                disabled={company.claims.length >= 20}
                onClick={() =>
                  c("claims", [
                    ...company.claims,
                    { statement: "", qualification: "", source_urls: [] },
                  ])
                }
              >
                Add product claim
              </button>
            </fieldset>
            <button type="submit" className="button primary" disabled={locked}>
              Save company draft
            </button>
          </form>
        </section>
        <section className="intake-section" aria-labelledby="brief-title">
          <div className="intake-section-heading">
            <div>
              <span className="eyebrow">02 / CAMPAIGN REQUIREMENTS</span>
              <h2 id="brief-title">Campaign brief</h2>
            </div>
            <span>
              {briefBase
                ? `Editing version ${briefBase.revision}`
                : "New draft"}
            </span>
          </div>
          <div className="intake-records">
            <label htmlFor="intake-brief-list">Saved campaign briefs</label>
            <select
              id="intake-brief-list"
              value={briefBase?.id ?? ""}
              disabled={locked || briefDirty}
              onChange={(event) => {
                if (event.target.value) void open("briefs", event.target.value);
              }}
            >
              <option value="">Choose a saved brief</option>
              {briefs.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.draft.objective.slice(0, 70) || "Untitled brief"} ·
                  version {item.revision}
                </option>
              ))}
              {briefBase && !briefs.some((row) => row.id === briefBase.id) && (
                <option value={briefBase.id}>
                  {briefBase.draft.objective || "Untitled brief"} · selected
                  version {briefBase.revision}
                </option>
              )}
            </select>
            {briefDirty && (
              <p className="intake-help">
                Save or discard brief edits before opening another draft.
              </p>
            )}
            {moreBriefs && (
              <button
                type="button"
                disabled={locked}
                onClick={() => void more("briefs")}
              >
                Load more briefs
              </button>
            )}
            <div className="intake-actions">
              <button
                type="button"
                disabled={locked || briefDirty}
                onClick={() => {
                  setBriefBase(null);
                  setBrief(emptyBrief());
                  setNotice("");
                }}
              >
                New campaign brief
              </button>
              <button
                type="button"
                disabled={locked || !briefDirty}
                onClick={() => setBrief(briefBase?.draft ?? emptyBrief())}
              >
                Discard brief edits
              </button>
              {briefBase && (
                <button
                  type="button"
                  disabled={locked}
                  onClick={() => void open("briefs", briefBase.id)}
                >
                  Replace edits with latest brief
                </button>
              )}
            </div>
          </div>
          <form
            action="/api/intake/briefs"
            method="post"
            aria-labelledby="brief-title"
            onSubmit={(event) => void save(event, "briefs")}
          >
            <fieldset disabled={locked}>
              <legend>Company version for this brief</legend>
              <p className="intake-help">
                Save a company first, then choose its exact version. Later
                company edits do not change this brief.
              </p>
              <label htmlFor="intake-company-pin">Company for this brief</label>
              <select
                id="intake-company-pin"
                name="company_id"
                required
                aria-invalid={pinTouched && !brief.company_id}
                aria-describedby={
                  pinTouched && !brief.company_id
                    ? "intake-pin-required"
                    : undefined
                }
                onInvalid={() => setPinTouched(true)}
                value={brief.company_id}
                onChange={(event) => {
                  setPinTouched(false);
                  const selected = companies.find(
                    (row) => row.id === event.target.value,
                  );
                  setBrief((prior) => ({
                    ...prior,
                    company_id: event.target.value,
                    company_revision: selected?.revision ?? 1,
                  }));
                }}
              >
                <option value="">Choose a saved company</option>
                {companies.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.draft.company_name || "Untitled company"}
                  </option>
                ))}
                {brief.company_id &&
                  !companies.some((item) => item.id === brief.company_id) && (
                    <option value={brief.company_id}>
                      {pin?.draft.company_name || "Saved company"}
                    </option>
                  )}
              </select>
              {pinTouched && !brief.company_id && (
                <p id="intake-pin-required" className="intake-field-error">
                  Choose a saved company for this brief.
                </p>
              )}
              <Field
                label="Company version"
                type="number"
                min={1}
                max={1000000}
                step={1}
                required
                value={String(brief.company_revision || "")}
                onChange={(value) => b("company_revision", Number(value))}
              />
              {pin && (
                <div className="intake-pin">
                  <strong>
                    Uses {pin.draft.company_name || "Untitled company"}, version{" "}
                    {pin.revision}
                  </strong>
                  <p>{pin.draft.product_name}</p>
                  <p>
                    {pin.draft.description ||
                      "No description saved in this version."}
                  </p>
                </div>
              )}
              {pinError && (
                <p className="intake-field-error">
                  Company version unavailable: {pinError}
                </p>
              )}
            </fieldset>
            <fieldset disabled={locked}>
              <legend>Requested campaign</legend>
              <p className="intake-help">
                Save incomplete requirements. Availability and suitability are
                assessed in a later step.
              </p>
              <Field
                label="Campaign objective"
                value={brief.objective}
                onChange={(value) => b("objective", value)}
                multiline
                maxLength={4000}
              />
              <Field
                label="Audience requirements"
                value={brief.audience}
                onChange={(value) => b("audience", value)}
                multiline
                maxLength={4000}
              />
              <Field
                label="Requested country or market"
                value={brief.country}
                onChange={(value) => b("country", value)}
                maxLength={80}
              />
              <Field
                label="Currency"
                value={brief.currency}
                onChange={(value) => b("currency", value)}
                maxLength={80}
                help="For example GBP or EUR. Leave blank if undecided."
              />
              <Field
                label="Requested channels"
                value={brief.channels.join("\n")}
                onChange={(value) => b("channels", lines(value))}
                multiline
                help="One channel per line, up to 10. Saving a request does not establish that the channel is supported."
              />
              <Field
                label="Budget in minor currency units"
                value={
                  brief.budget_minor === null ? "" : String(brief.budget_minor)
                }
                onChange={(value) =>
                  b("budget_minor", value === "" ? null : Number(value))
                }
                type="number"
                min={0}
                max={1000000000}
                step={1}
                help="Use whole minor units: 10000 means GBP 100.00. Leave blank if undecided."
              />
              <Field
                label="Maximum candidate count"
                value={
                  brief.max_candidates === null
                    ? ""
                    : String(brief.max_candidates)
                }
                onChange={(value) =>
                  b("max_candidates", value === "" ? null : Number(value))
                }
                type="number"
                min={1}
                max={400000}
                step={1}
              />
              <Field
                label="Campaign constraints"
                value={brief.constraints.join("\n")}
                onChange={(value) => b("constraints", lines(value))}
                multiline
                help="One requirement per line, up to 20. Keep each qualification in its original wording."
              />
            </fieldset>
            <fieldset disabled={locked}>
              <legend>Contact data</legend>
              <div className="intake-radio">
                <input
                  id="intake-unspecified"
                  name="contact_source"
                  type="radio"
                  checked={brief.contact_source === "unspecified"}
                  onChange={() => b("contact_source", "unspecified")}
                />
                <label htmlFor="intake-unspecified">Not decided</label>
              </div>
              <div className="intake-radio">
                <input
                  id="intake-synthetic"
                  name="contact_source"
                  type="radio"
                  checked={brief.contact_source === "synthetic"}
                  onChange={() => b("contact_source", "synthetic")}
                />
                <label htmlFor="intake-synthetic">
                  Synthetic contacts for testing
                </label>
              </div>
              <p className="intake-help">
                This records a preference. Saving does not connect to a CRM or
                fetch contacts.
              </p>
            </fieldset>
            <button type="submit" className="button primary" disabled={locked}>
              Save campaign brief
            </button>
          </form>
        </section>
      </section>
    </FieldFeedback.Provider>
  );
}
