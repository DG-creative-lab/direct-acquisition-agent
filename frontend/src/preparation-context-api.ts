import { read, token } from "./api";
import { intakeStore } from "./intake-api";
import type { CompanyInput, BriefInput, IntakeSnapshot } from "./intake-api";
import type { Readiness } from "./intake-planning-api";

export type PreparationPreview = {
  read_only?: boolean;
  id: string;
  store_id: string;
  company: IntakeSnapshot<CompanyInput>;
  brief: IntakeSnapshot<BriefInput>;
  company_head_revision: number;
  context_revision: number;
  claims: (CompanyInput["claims"][number] & { id: string })[];
};
export type PreparationReview = {
  request_id: string;
  brief_id: string;
  brief_revision: number;
  preview_id: string;
  expected_context_revision: number;
  selected_claim_ids: string[];
  include_description: boolean;
  include_cta: boolean;
  review_days: number;
  review_note: string;
  issues: string[];
  confirmed: true;
};
export type PreparationContext = {
  request_id: string;
  store_id: string;
  current: boolean;
  replayed: boolean;
  review_required: string[];
  context: {
    schema: "reviewed-preparation-context/v1";
    id: string;
    revision: number;
    request_id: string;
    store_id: string;
    reviewer: string;
    reviewed_at: number;
    review_expires_at: number;
    source: PreparationPreview;
    selection: Omit<PreparationReview, "request_id">;
    selected_inputs: {
      company_name: string;
      product_name: string;
      description: string | null;
      claims: PreparationPreview["claims"];
      cta: { wording: string; url: string } | null;
    };
    requirements: BriefInput;
    references: { id: string; url: string; verification: string }[];
    missing_evidence: string[];
    reviewer_questions: string[];
    requirements_readiness: Readiness;
    review_status: string;
    verification: "user_supplied_unverified";
    generation: "unavailable";
    authority: "none";
  };
};
export type PendingContext = { store_id: string; payload: PreparationReview };
const key = "workspace-preparation-review:v1";
const fields = [
  "request_id",
  "brief_id",
  "brief_revision",
  "preview_id",
  "expected_context_revision",
  "selected_claim_ids",
  "include_description",
  "include_cta",
  "review_days",
  "review_note",
  "issues",
  "confirmed",
].sort();
export function pendingContext(): PendingContext | null {
  const raw = sessionStorage.getItem(key);
  if (raw === null) return null;
  try {
    const value = JSON.parse(raw),
      p = value.payload;
    if (
      Object.keys(value).sort().join() !== "payload,store_id" ||
      typeof value.store_id !== "string" ||
      !value.store_id ||
      Object.keys(p).sort().join() !== fields.join() ||
      ![p.request_id, p.brief_id, p.preview_id].every(
        (v) => typeof v === "string" && v.length > 0 && v.length <= 160,
      ) ||
      !Number.isInteger(p.brief_revision) ||
      p.brief_revision < 1 ||
      p.brief_revision > 1000000 ||
      !Number.isInteger(p.expected_context_revision) ||
      p.expected_context_revision < 0 ||
      p.expected_context_revision >= 1000000 ||
      !Number.isInteger(p.review_days) ||
      p.review_days < 1 ||
      p.review_days > 30 ||
      !Array.isArray(p.selected_claim_ids) ||
      p.selected_claim_ids.length > 20 ||
      !p.selected_claim_ids.every((v: unknown) => typeof v === "string") ||
      !Array.isArray(p.issues) ||
      p.issues.length > 8 ||
      !p.issues.every((v: unknown) => typeof v === "string") ||
      typeof p.review_note !== "string" ||
      !p.review_note ||
      p.review_note.length > 1000 ||
      typeof p.include_description !== "boolean" ||
      typeof p.include_cta !== "boolean" ||
      p.confirmed !== true
    )
      throw new Error("Invalid recovery command");
    return value;
  } catch {
    throw new Error(
      "The original preparation review could not be restored. Keep its recovery data and check browser storage before confirming again.",
    );
  }
}
export function queueContext(
  storeId: string,
  review: Omit<PreparationReview, "request_id">,
): PendingContext {
  if (!storeId)
    throw new Error("Load the original workspace store before confirming.");
  if (pendingContext())
    throw new Error("Confirm the original preparation review first.");
  const value = {
    store_id: storeId,
    payload: { request_id: crypto.randomUUID(), ...review },
  };
  if (
    new TextEncoder().encode(JSON.stringify(value.payload)).byteLength >
    70 * 1024
  )
    throw new Error(
      "The preparation review exceeds the bounded request size. Shorten the review notes.",
    );
  sessionStorage.setItem(key, JSON.stringify(value));
  return value;
}
function matching(value: PreparationContext, command: PendingContext) {
  const c = value.context;
  return (
    value.store_id === command.store_id &&
    value.request_id === command.payload.request_id &&
    c?.store_id === command.store_id &&
    c.request_id === command.payload.request_id &&
    c.source?.id === command.payload.preview_id &&
    c.source?.store_id === command.store_id &&
    c.source?.brief.id === command.payload.brief_id &&
    c.source?.brief.revision === command.payload.brief_revision &&
    c.revision === command.payload.expected_context_revision + 1 &&
    c.schema === "reviewed-preparation-context/v1" &&
    c.authority === "none" &&
    c.generation === "unavailable" &&
    c.verification === "user_supplied_unverified" &&
    fields
      .filter((k) => k !== "request_id")
      .every(
        (k) =>
          JSON.stringify(c.selection?.[k as keyof typeof c.selection]) ===
          JSON.stringify(command.payload[k as keyof PreparationReview]),
      )
  );
}
export class ContextRejected extends Error {}
export async function dispatchContext(
  command: PendingContext,
): Promise<PreparationContext> {
  if (JSON.stringify(pendingContext()) !== JSON.stringify(command))
    throw new Error(
      "The original review changed in storage. Reload to recover it.",
    );
  if ((await intakeStore()) !== command.store_id)
    throw new Error(
      "Restore the original workspace store before retrying its preparation review.",
    );
  const original = await fetch(
    `/api/intake/contexts/requests/${encodeURIComponent(command.payload.request_id)}`,
    { headers: { "X-Workspace-Token": token() } },
  );
  if (original.ok) {
    const value = await original.json();
    if (!matching(value, command))
      throw new Error(
        "The original preparation receipt could not be verified. Keep its recovery data.",
      );
    sessionStorage.removeItem(key);
    return value;
  }
  if (original.status !== 404)
    throw new Error(
      "Original review progress is unavailable. Keep and retry the same request.",
    );
  const response = await fetch("/api/intake/contexts", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-Token": token(),
      "X-Intake-Store": command.store_id,
    },
    body: JSON.stringify(command.payload),
  });
  const value = await response.json();
  if (!response.ok) {
    if (
      response.status === 409 &&
      value.context_not_saved === true &&
      value.store_id === command.store_id
    ) {
      sessionStorage.removeItem(key);
      throw new ContextRejected(
        value.error ??
          "The review was not saved. Reload its exact sources before confirming again.",
      );
    }
    throw new Error(
      value.error ??
        "The preparation review is unconfirmed. Retry only the original request.",
    );
  }
  if (!matching(value, command))
    throw new Error(
      "The preparation receipt could not be verified. Keep and retry the original request.",
    );
  sessionStorage.removeItem(key);
  return value;
}
export function preparationPreview(
  brief: IntakeSnapshot<BriefInput>,
  signal?: AbortSignal,
) {
  return read<PreparationPreview>(
    `/api/intake/contexts/preview?brief_id=${encodeURIComponent(brief.id)}&revision=${brief.revision}`,
    signal,
  );
}
export function preparationHistory(briefId: string, signal?: AbortSignal) {
  return read<{ items: PreparationContext[] }>(
    `/api/intake/contexts?brief_id=${encodeURIComponent(briefId)}`,
    signal,
  );
}
