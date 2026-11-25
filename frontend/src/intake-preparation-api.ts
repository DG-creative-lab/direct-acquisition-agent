import { read, token } from "./api";
import { intakeStore } from "./intake-api";
import type { BriefInput } from "./intake-api";
import type { PreparationContext } from "./preparation-context-api";

export type Eligibility = {
  id: string;
  store_id: string;
  context_request_id: string;
  context_fingerprint: string;
  selected_inputs: PreparationContext["context"]["selected_inputs"];
  requirements: BriefInput;
  references: { id: string; url: string }[];
  blockers: string[];
  checked_on: string;
  original_preparation_request_id?: string;
  settings: { size: number; mode: string };
};
export type GroundingCommand = {
  request_id: string;
  context_request_id: string;
  preview_id: string;
  evidence: {
    reference_ids: string[];
    checked_on: string;
    review_days: number;
    note: string;
    confirmed_official_sources: true;
    confirmed_exact_wording: true;
  };
  confirmed_synthetic_preparation: true;
};
export type PendingPreparation = {
  store_id: string;
  context_fingerprint: string;
  payload: GroundingCommand;
};
export type PreparedIntake = {
  request_id: string;
  store_id: string;
  draft_id: string;
  current: boolean;
  review_required: string[];
  approval: "not_granted";
  model_calls: 0;
  grounding: {
    actor: string;
    request: Omit<GroundingCommand, "request_id">;
    context_fingerprint: string;
    context_request_id: string;
    store_id: string;
    review_expires_at: number;
  };
  manifest: {
    creatives: {
      id: string;
      headline: string;
      opening: string;
      locked_block: string;
    }[];
  };
};
const key = "workspace-grounded-preparation:v1";
function stable(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(stable).join(",") + "]";
  if (value && typeof value === "object")
    return (
      "{" +
      Object.entries(value)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([k, v]) => JSON.stringify(k) + ":" + stable(v))
        .join(",") +
      "}"
    );
  return JSON.stringify(value);
}
export function pendingPreparation(): PendingPreparation | null {
  const raw = sessionStorage.getItem(key);
  if (raw === null) return null;
  try {
    const v = JSON.parse(raw),
      p = v.payload,
      e = p.evidence;
    if (
      Object.keys(v).sort().join() !== "context_fingerprint,payload,store_id" ||
      Object.keys(p).sort().join() !==
        "confirmed_synthetic_preparation,context_request_id,evidence,preview_id,request_id" ||
      Object.keys(e).sort().join() !==
        "checked_on,confirmed_exact_wording,confirmed_official_sources,note,reference_ids,review_days" ||
      ![
        v.store_id,
        v.context_fingerprint,
        p.request_id,
        p.context_request_id,
        p.preview_id,
      ].every(
        (x) => typeof x === "string" && x.length > 0 && x.length <= 160,
      ) ||
      !Array.isArray(e.reference_ids) ||
      !e.reference_ids.length ||
      e.reference_ids.length > 60 ||
      !e.reference_ids.every(
        (x: unknown) => typeof x === "string" && x.length <= 160,
      ) ||
      new Set(e.reference_ids).size !== e.reference_ids.length ||
      typeof e.checked_on !== "string" ||
      !/^\d{4}-\d{2}-\d{2}$/.test(e.checked_on) ||
      !Number.isInteger(e.review_days) ||
      e.review_days < 1 ||
      e.review_days > 30 ||
      typeof e.note !== "string" ||
      !e.note ||
      e.note.length > 1000 ||
      e.confirmed_exact_wording !== true ||
      e.confirmed_official_sources !== true ||
      p.confirmed_synthetic_preparation !== true
    )
      throw new Error();
    return v;
  } catch {
    throw new Error(
      "The original grounded preparation could not be restored. Keep its recovery data and restore this browser session.",
    );
  }
}
export function queuePreparation(e: Eligibility, payload: GroundingCommand) {
  if (pendingPreparation())
    throw new Error("Reconcile the original preparation first.");
  const v: PendingPreparation = {
    store_id: e.store_id,
    context_fingerprint: e.context_fingerprint,
    payload,
  };
  sessionStorage.setItem(key, JSON.stringify(v));
  if (!pendingPreparation())
    throw new Error("Preparation recovery could not be saved.");
  return v;
}
export function eligibility(contextRequest: string, signal?: AbortSignal) {
  return read<Eligibility>(
    `/api/intake/eligibility?context_request_id=${encodeURIComponent(contextRequest)}`,
    signal,
  );
}
export function preparationReceipt(request: string, signal?: AbortSignal) {
  return read<PreparedIntake>(
    `/api/intake/preparations/requests/${encodeURIComponent(request)}`,
    signal,
  );
}
function matches(v: PreparedIntake, c: PendingPreparation) {
  const { request_id, ...request } = c.payload;
  return (
    v.request_id === request_id &&
    v.store_id === c.store_id &&
    v.grounding?.store_id === c.store_id &&
    v.grounding.context_fingerprint === c.context_fingerprint &&
    v.grounding.actor === "local-operator" &&
    stable(v.grounding.request) === stable(request) &&
    v.approval === "not_granted" &&
    v.model_calls === 0
  );
}
export class PreparationRejected extends Error {}
export async function dispatchPreparation(
  c: PendingPreparation,
): Promise<PreparedIntake> {
  if (stable(pendingPreparation()) !== stable(c))
    throw new Error(
      "The original preparation changed in storage. Reload to recover it.",
    );
  if ((await intakeStore()) !== c.store_id)
    throw new Error(
      "Restore the original workspace store before retrying this preparation.",
    );
  let response = await fetch(
    `/api/intake/preparations/requests/${encodeURIComponent(c.payload.request_id)}`,
    { headers: { "X-Workspace-Token": token() } },
  );
  if (!response.ok && response.status !== 404)
    throw new Error(
      "Original preparation progress is unavailable. Keep the original request.",
    );
  if (response.status === 404)
    response = await fetch("/api/intake/preparations", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Workspace-Token": token(),
        "X-Intake-Store": c.store_id,
      },
      body: JSON.stringify(c.payload),
    });
  const value = await response.json();
  if (!response.ok) {
    if (value.preparation_not_saved === true && value.store_id === c.store_id) {
      sessionStorage.removeItem(key);
      throw new PreparationRejected(value.error);
    }
    throw new Error(
      value.error ??
        "Preparation is uncertain. Reconcile the original request.",
    );
  }
  if (!matches(value, c))
    throw new Error(
      "The original preparation receipt could not be verified. Keep its recovery data.",
    );
  sessionStorage.removeItem(key);
  return value;
}
