import { read, token } from "./api";
import { intakeStore } from "./intake-api";
import type { Eligibility, GroundingCommand } from "./intake-preparation-api";

export type EmailEligibility = Eligibility & {
  original_email_request_id?: string;
};
export type EmailView = {
  request_id: string;
  store_id: string;
  subject: { id: string };
  review_ready: boolean;
  review_required: string[];
  approval_valid: boolean;
  approval: { id: string; decision: string; expires_at: number } | null;
  batch: {
    id: string;
    request_id: string;
    targeting: string;
    cost_minor: number;
    binding: {
      store_id: string;
      context_request_id: string;
      context_fingerprint: string;
      request: Omit<GroundingCommand, "request_id">;
      expires_at: number;
    };
    content: {
      rows: {
        id: string;
        email: {
          to: string;
          from: string;
          from_name: string;
          reply_to: string;
          subject: string;
          text: string;
          html: string;
        };
      }[];
    };
  };
};
export type EmailOperation = "prepare" | "decision" | "revoke" | "export";
export type EmailPayload =
  | GroundingCommand
  | {
      request_id: string;
      preparation_request_id: string;
      subject_id?: string;
      approval_id?: string;
      decision?: string;
      reason?: string;
      ttl_seconds?: number;
    };
export type PendingEmail = {
  store_id: string;
  context_request_id: string;
  context_fingerprint: string;
  operation: EmailOperation;
  payload: EmailPayload;
};
export type EmailReceipt = {
  request_id: string;
  actor: string;
  kind: string;
  purpose: string;
  inputs: Record<string, unknown>;
  value: {
    subject_id?: string;
    approval_id?: string;
    id?: string;
    purpose: string;
  };
};
const key = "workspace-intake-email:v1";
const fields: Record<EmailOperation, string[]> = {
  prepare: [
    "request_id",
    "context_request_id",
    "preview_id",
    "evidence",
    "confirmed_synthetic_preparation",
  ],
  decision: [
    "request_id",
    "preparation_request_id",
    "subject_id",
    "decision",
    "reason",
    "ttl_seconds",
  ],
  revoke: ["request_id", "preparation_request_id", "approval_id", "reason"],
  export: ["request_id", "preparation_request_id", "subject_id", "approval_id"],
};
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
export function pendingEmail(): PendingEmail | null {
  const raw = sessionStorage.getItem(key);
  if (raw === null) return null;
  try {
    const v = JSON.parse(raw),
      p = v.payload,
      op = v.operation as EmailOperation;
    if (
      Object.keys(v).sort().join() !==
        "context_fingerprint,context_request_id,operation,payload,store_id" ||
      !Object.hasOwn(fields, op) ||
      Object.keys(p).sort().join() !== [...fields[op]].sort().join() ||
      ![
        v.store_id,
        v.context_request_id,
        v.context_fingerprint,
        p.request_id,
      ].every((x) => typeof x === "string" && x.length > 0 && x.length <= 160)
    )
      throw new Error();
    if (op === "prepare") {
      const e = p.evidence;
      if (
        p.confirmed_synthetic_preparation !== true ||
        p.context_request_id !== v.context_request_id ||
        typeof p.preview_id !== "string" ||
        !e ||
        Object.keys(e).sort().join() !==
          "checked_on,confirmed_exact_wording,confirmed_official_sources,note,reference_ids,review_days" ||
        !Array.isArray(e.reference_ids) ||
        !e.reference_ids.length ||
        e.reference_ids.length > 60 ||
        !e.reference_ids.every(
          (x: unknown) => typeof x === "string" && x.length <= 160,
        ) ||
        typeof e.checked_on !== "string" ||
        !/^\d{4}-\d{2}-\d{2}$/.test(e.checked_on) ||
        !Number.isInteger(e.review_days) ||
        e.review_days < 1 ||
        e.review_days > 30 ||
        typeof e.note !== "string" ||
        !e.note ||
        e.note.length > 1000 ||
        e.confirmed_official_sources !== true ||
        e.confirmed_exact_wording !== true
      )
        throw new Error();
    } else {
      if (
        typeof p.preparation_request_id !== "string" ||
        !p.preparation_request_id ||
        p.preparation_request_id.length > 160
      )
        throw new Error();
      for (const f of fields[op].filter(
        (f) =>
          !["request_id", "preparation_request_id", "ttl_seconds"].includes(f),
      ))
        if (typeof p[f] !== "string" || !p[f] || p[f].length > 1000)
          throw new Error();
      if (
        op === "decision" &&
        (!["approve", "reject"].includes(p.decision) ||
          !Number.isInteger(p.ttl_seconds) ||
          p.ttl_seconds < 1 ||
          p.ttl_seconds > 86400)
      )
        throw new Error();
    }
    return v;
  } catch {
    throw new Error(
      "The original email command could not be restored. Keep its recovery data and restore this browser session.",
    );
  }
}
export function queueEmail(command: PendingEmail) {
  if (pendingEmail())
    throw new Error("Reconcile the original email command first.");
  sessionStorage.setItem(key, JSON.stringify(command));
  if (stable(pendingEmail()) !== stable(command))
    throw new Error("Email recovery could not be saved exactly.");
  return command;
}
export function emailEligibility(contextRequest: string, signal?: AbortSignal) {
  return read<EmailEligibility>(
    `/api/intake/emails/eligibility?context_request_id=${encodeURIComponent(contextRequest)}`,
    signal,
  );
}
export function emailView(request: string, signal?: AbortSignal) {
  return read<EmailView>(
    `/api/intake/emails/requests/${encodeURIComponent(request)}`,
    signal,
  );
}
export class EmailRejected extends Error {}
export async function dispatchEmail(
  c: PendingEmail,
): Promise<EmailView | EmailReceipt> {
  if (stable(pendingEmail()) !== stable(c))
    throw new Error(
      "The original email command changed in storage. Reload to recover it.",
    );
  if ((await intakeStore()) !== c.store_id)
    throw new Error(
      "Restore the original workspace store before retrying this email command.",
    );
  const op = c.operation === "revoke" ? "revocation" : c.operation;
  const path =
    c.operation === "prepare"
      ? `/api/intake/emails/requests/${encodeURIComponent(c.payload.request_id)}`
      : `/api/intake/emails/commands/${op}/${encodeURIComponent(c.payload.request_id)}`;
  let response = await fetch(path, {
    headers: { "X-Workspace-Token": token() },
  });
  if (!response.ok && response.status !== 404)
    throw new Error(
      "Original email command status is unavailable. Keep and retry the same command.",
    );
  if (response.status === 404)
    response = await fetch(`/api/intake/emails/${c.operation}`, {
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
    if (value.email_not_saved === true && value.store_id === c.store_id) {
      sessionStorage.removeItem(key);
      throw new EmailRejected(value.error);
    }
    throw new Error(
      value.error ??
        "Email command is uncertain. Reconcile its original identity.",
    );
  }
  if (c.operation === "prepare") {
    const { request_id, ...request } = c.payload;
    if (
      value.request_id !== request_id ||
      value.store_id !== c.store_id ||
      value.batch?.binding?.store_id !== c.store_id ||
      value.batch?.binding?.context_fingerprint !== c.context_fingerprint ||
      stable(value.batch.binding.request) !== stable(request)
    )
      throw new Error(
        "The original email preparation receipt could not be verified. Keep its recovery data.",
      );
  } else {
    const { request_id, preparation_request_id, ...rest } =
      c.payload as Exclude<EmailPayload, GroundingCommand>;
    if (
      value.request_id !== request_id ||
      value.actor !==
        (c.operation === "export" ? "local-operator" : "local-reviewer") ||
      value.kind !== `intake_email_${op}` ||
      value.purpose !== "synthetic_intake_email_export/v1" ||
      stable(value.inputs) !==
        stable({ request_id: preparation_request_id, ...rest })
    )
      throw new Error(
        "The original email review receipt could not be verified. Keep its recovery data.",
      );
  }
  sessionStorage.removeItem(key);
  return value;
}
export async function downloadEmail(
  request: string,
  subject: string,
  storeId: string,
) {
  if ((await intakeStore()) !== storeId)
    throw new Error(
      "Restore the original workspace store before downloading this email package.",
    );
  const response = await fetch(
    `/api/intake/emails/exports/${encodeURIComponent(request)}?subject_id=${encodeURIComponent(subject)}`,
    { headers: { "X-Workspace-Token": token() } },
  );
  if (!response.ok) {
    const value = await response.json();
    throw new Error(
      value.error ?? "This exact email export is no longer authorized.",
    );
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "reviewed-synthetic-emails.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
