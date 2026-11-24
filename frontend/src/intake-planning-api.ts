import { read, token } from "./api";
import { intakeStore } from "./intake-api";
import { openRouterHeaders, openRouterSession } from "./openrouter-session";
import type { BriefInput, CompanyInput, IntakeSnapshot } from "./intake-api";

export type Readiness = {
  missing: string[];
  unsupported: string[];
  execution_blockers: string[];
};
export type IntakePlanView = {
  request_id: string;
  current: boolean;
  store_id: string;
  source: {
    brief_id: string;
    brief_revision: number;
    company_id: string;
    company_revision: number;
    conversation_id: string;
    revision: number;
    fingerprint: string;
    brief: IntakeSnapshot<BriefInput>;
    company: IntakeSnapshot<CompanyInput>;
    model_config: { model: string };
  };
  plan: null | {
    status: string;
    result: null | {
      schema: "intake-plan/v1";
      outcome: "proposal" | "clarification" | "unsupported";
      summary: string;
      approach: string[];
      questions: string[];
      limitations: string[];
      readiness: Readiness;
      requirements: BriefInput;
      authority: "none";
      execution: "unavailable";
    };
    error: null | { error_code?: string; provider_error?: string };
  };
};
export type PendingPlan = {
  store_id: string;
  payload: {
    request_id: string;
    brief_id: string;
    brief_revision: number;
    allow_model: true;
  };
};
const key = "workspace-intake-plan:v1";
export function pendingPlan(): PendingPlan | null {
  const raw = sessionStorage.getItem(key);
  if (raw === null) return null;
  try {
    const value = JSON.parse(raw);
    if (
      Object.keys(value).sort().join() !== "payload,store_id" ||
      typeof value.store_id !== "string" ||
      !value.store_id ||
      Object.keys(value.payload).sort().join() !==
        "allow_model,brief_id,brief_revision,request_id" ||
      typeof value.payload.request_id !== "string" ||
      !value.payload.request_id ||
      typeof value.payload.brief_id !== "string" ||
      !value.payload.brief_id ||
      !Number.isInteger(value.payload.brief_revision) ||
      value.payload.brief_revision < 1 ||
      value.payload.brief_revision > 1000000 ||
      value.payload.allow_model !== true
    )
      throw new Error("invalid");
    return value;
  } catch {
    throw new Error(
      "The original planning request could not be restored. Keep its recovery data and check browser storage before planning again.",
    );
  }
}
export function queuePlan(
  storeId: string,
  brief: IntakeSnapshot<BriefInput>,
): PendingPlan {
  if (!storeId)
    throw new Error("Load the original workspace store before planning.");
  if (pendingPlan())
    throw new Error(
      "Confirm the original planning request before starting another.",
    );
  const value: PendingPlan = {
    store_id: storeId,
    payload: {
      request_id: crypto.randomUUID(),
      brief_id: brief.id,
      brief_revision: brief.revision,
      allow_model: true,
    },
  };
  sessionStorage.setItem(key, JSON.stringify(value));
  return value;
}
export class PlanRejected extends Error {}
export async function dispatchPlan(
  value: PendingPlan,
): Promise<IntakePlanView> {
  if (JSON.stringify(pendingPlan()) !== JSON.stringify(value))
    throw new Error(
      "The original planning request changed in storage. Reload to recover it.",
    );
  if ((await intakeStore()) !== value.store_id)
    throw new Error(
      "Restore the original workspace store before resuming its planning request.",
    );
  // A completed request can be reconciled after a server/provider-session restart
  // without restoring credentials or dispatching a model task again.
  const original = await fetch(
    `/api/intake/plans/${encodeURIComponent(value.payload.request_id)}`,
    {
      headers: { "X-Workspace-Token": token() },
    },
  );
  if (original.ok) {
    const saved = (await original.json()) as IntakePlanView;
    if (
      saved.store_id !== value.store_id ||
      saved.request_id !== value.payload.request_id ||
      saved.source?.brief_id !== value.payload.brief_id ||
      saved.source?.brief_revision !== value.payload.brief_revision
    )
      throw new Error(
        "The original planning source could not be verified. Keep its recovery data.",
      );
    if (
      saved.plan &&
      ["succeeded", "failed", "cancelled"].includes(saved.plan.status)
    ) {
      sessionStorage.removeItem(key);
      return saved;
    }
  } else if (original.status !== 404) {
    throw new Error(
      "The original planning progress is unavailable. Keep and resume the same request.",
    );
  }
  const response = await fetch("/api/intake/plans", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-Token": token(),
      "X-Intake-Store": value.store_id,
      ...openRouterHeaders(openRouterSession()),
    },
    body: JSON.stringify(value.payload),
  });
  const result = await response.json();
  if (!response.ok) {
    if (
      result.intake_plan_not_admitted === true &&
      result.store_id === value.store_id &&
      response.status === 409
    ) {
      sessionStorage.removeItem(key);
      throw new PlanRejected(
        result.error ??
          "The request was not admitted. Review the saved brief before trying again.",
      );
    }
    throw new Error(
      result.error ??
        "The planning result is unconfirmed. Resume only its original request.",
    );
  }
  if (
    result.store_id !== value.store_id ||
    result.request_id !== value.payload.request_id ||
    result.source?.brief_id !== value.payload.brief_id ||
    result.source?.brief_revision !== value.payload.brief_revision
  )
    throw new Error(
      "The planning response could not be verified. Keep and resume its original request.",
    );
  sessionStorage.removeItem(key);
  return result as IntakePlanView;
}
export function planHistory(briefId: string, signal?: AbortSignal) {
  return read<{ items: IntakePlanView[] }>(
    `/api/intake/plans?brief_id=${encodeURIComponent(briefId)}`,
    signal,
  );
}
export function planProgress(requestId: string) {
  return read<IntakePlanView>(
    `/api/intake/plans/${encodeURIComponent(requestId)}`,
  );
}
export function briefReadiness(
  brief: IntakeSnapshot<BriefInput>,
  signal?: AbortSignal,
) {
  return read<Readiness>(
    `/api/intake/briefs/${encodeURIComponent(brief.id)}/readiness?revision=${brief.revision}`,
    signal,
  );
}

export function queuePlanResume(view: IntakePlanView): PendingPlan {
  if (pendingPlan())
    throw new Error("Confirm the original planning request first.");
  const value: PendingPlan = {
    store_id: view.store_id,
    payload: {
      request_id: view.request_id,
      brief_id: view.source.brief_id,
      brief_revision: view.source.brief_revision,
      allow_model: true,
    },
  };
  sessionStorage.setItem(key, JSON.stringify(value));
  return value;
}
