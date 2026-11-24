import { read, token } from "./api";

export type CompanyInput = {
  company_name: string;
  website: string;
  product_name: string;
  description: string;
  official_cta: string;
  cta_url: string;
  source_urls: string[];
  claims: { statement: string; qualification: string; source_urls: string[] }[];
};
export type BriefInput = {
  company_id: string;
  company_revision: number;
  objective: string;
  audience: string;
  country: string;
  currency: string;
  channels: string[];
  budget_minor: number | null;
  max_candidates: number | null;
  constraints: string[];
  contact_source: "unspecified" | "synthetic";
};
export type IntakeKind = "companies" | "briefs";
export type IntakeSnapshot<T> = {
  id: string;
  revision: number;
  draft: T;
  actor: string;
  saved_at: number;
  provenance: "user_supplied_unverified";
  authority: "none";
  execution_readiness: "not_assessed";
};
export type IntakePayload = {
  id: string | null;
  expected_revision: number;
  draft: CompanyInput | BriefInput;
};
export type PendingIntake = {
  store_id: string;
  kind: IntakeKind;
  payload: IntakePayload & { request_id: string };
  base: IntakeSnapshot<CompanyInput | BriefInput> | null;
};
export type IntakeReceipt = {
  snapshot: IntakeSnapshot<CompanyInput | BriefInput>;
  replayed: boolean;
};
const pendingKey = "workspace-intake-save:v1";

function inputShape(
  kind: IntakeKind,
  input: CompanyInput | BriefInput,
): boolean {
  const values = input as unknown as Record<string, unknown>;
  const strings =
    kind === "companies"
      ? [
          "company_name",
          "website",
          "product_name",
          "description",
          "official_cta",
          "cta_url",
        ]
      : [
          "company_id",
          "objective",
          "audience",
          "country",
          "currency",
          "contact_source",
        ];
  if (
    !values ||
    typeof values !== "object" ||
    strings.some((key) => typeof values[key] !== "string")
  )
    return false;
  const list = (value: unknown) =>
    Array.isArray(value) && value.every((item) => typeof item === "string");
  if (kind === "companies")
    return (
      list(values.source_urls) &&
      Array.isArray(values.claims) &&
      values.claims.every(
        (claim) =>
          claim &&
          typeof claim.statement === "string" &&
          typeof claim.qualification === "string" &&
          list(claim.source_urls),
      )
    );
  return (
    list(values.channels) &&
    list(values.constraints) &&
    Number.isInteger(values.company_revision) &&
    (values.budget_minor === null || Number.isInteger(values.budget_minor)) &&
    (values.max_candidates === null || Number.isInteger(values.max_candidates))
  );
}

export function pendingIntake(): PendingIntake | null {
  const raw = sessionStorage.getItem(pendingKey);
  if (!raw) return null;
  let value: PendingIntake;
  try {
    value = JSON.parse(raw) as PendingIntake;
  } catch {
    throw new Error(
      "The original save could not be restored. Keep this tab open and check browser storage before saving.",
    );
  }
  if (
    !value ||
    typeof value.store_id !== "string" ||
    !value.store_id ||
    !["companies", "briefs"].includes(value.kind) ||
    !value.payload ||
    typeof value.payload.request_id !== "string" ||
    !value.payload.request_id ||
    !Number.isInteger(value.payload.expected_revision) ||
    !(value.payload.id === null || typeof value.payload.id === "string") ||
    !value.payload.draft ||
    typeof value.payload.draft !== "object" ||
    !inputShape(value.kind, value.payload.draft) ||
    !(value.payload.id === null
      ? value.base === null
      : value.base?.id === value.payload.id &&
        value.base?.revision === value.payload.expected_revision &&
        inputShape(value.kind, value.base.draft))
  )
    throw new Error(
      "The original save could not be restored. Keep this tab open and check browser storage before saving.",
    );
  return value;
}

export function queueIntake(
  kind: IntakeKind,
  payload: IntakePayload,
  base: IntakeSnapshot<CompanyInput | BriefInput> | null,
  storeId: string,
): PendingIntake {
  if (!storeId) throw new Error("Load the workspace store before saving.");
  if (pendingIntake())
    throw new Error("Confirm the original save before starting another.");
  // Match the domain's ASCII JSON bound without rewriting any source wording.
  // Unicode escapes can occupy more serialized bytes than their UTF-8 input.
  const serialized = JSON.stringify(payload.draft).replace(
    /[\u007f-\uffff]/g,
    (character) =>
      "\\u" + character.charCodeAt(0).toString(16).padStart(4, "0"),
  );
  if (serialized.length > 64000)
    throw new Error(
      "This draft is too large to save. Shorten the text or remove some references, then try again.",
    );
  const pending = {
    store_id: storeId,
    kind,
    payload: { ...payload, request_id: crypto.randomUUID() },
    base,
  };
  // Freeze the complete body before dispatch. A reload must never invent a replacement key.
  sessionStorage.setItem(pendingKey, JSON.stringify(pending));
  return pending;
}

export class IntakeRejected extends Error {}

export async function dispatchIntake(
  pending: PendingIntake,
): Promise<IntakeReceipt> {
  const stored = pendingIntake();
  if (JSON.stringify(stored) !== JSON.stringify(pending))
    throw new Error(
      "The original save changed in browser storage. Reload to recover it.",
    );
  if ((await intakeStore()) !== pending.store_id)
    throw new Error(
      "Restore the original workspace store and retry. The original save has been kept.",
    );
  const response = await fetch(`/api/intake/${pending.kind}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-Token": token(),
      "X-Intake-Store": pending.store_id,
    },
    body: JSON.stringify(pending.payload),
  });
  const result = await response.json();
  if (!response.ok) {
    if (
      result.intake_not_saved === true &&
      result.store_id === pending.store_id &&
      [400, 404, 409].includes(response.status)
    ) {
      sessionStorage.removeItem(pendingKey);
      throw new IntakeRejected(
        result.error ??
          "The draft was not saved. Review it before trying again.",
      );
    }
    throw new Error(
      result.error ??
        "The save result is uncertain. Retry the original save to confirm it.",
    );
  }
  if (
    !result.snapshot ||
    result.store_id !== pending.store_id ||
    result.snapshot.request_id !== pending.payload.request_id
  )
    throw new Error(
      "The save response could not be verified. Retry the original save.",
    );
  sessionStorage.removeItem(pendingKey);
  return result as IntakeReceipt;
}

export async function intakeStore(signal?: AbortSignal): Promise<string> {
  const result = await read<{ store_id: string }>("/api/intake/store", signal);
  if (typeof result.store_id !== "string" || !result.store_id)
    throw new Error(
      "The workspace store could not be identified. Reload before saving.",
    );
  return result.store_id;
}

export async function intakePage<T>(
  kind: IntakeKind,
  after = "",
  signal?: AbortSignal,
) {
  return read<{ items: IntakeSnapshot<T>[] }>(
    `/api/intake/${kind}?after_id=${encodeURIComponent(after)}&limit=50`,
    signal,
  );
}

export function intakeRecord<T>(
  kind: IntakeKind,
  id: string,
  revision?: number,
  signal?: AbortSignal,
) {
  return read<IntakeSnapshot<T>>(
    `/api/intake/${kind}/${encodeURIComponent(id)}${revision === undefined ? "" : `?revision=${revision}`}`,
    signal,
  );
}
