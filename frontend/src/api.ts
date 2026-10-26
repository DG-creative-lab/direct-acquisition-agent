export type Act = (
  action: string,
  payload?: Record<string, unknown>,
) => Promise<boolean>;
export type Creative = {
  id: string;
  segment: string;
  arm: string;
  headline?: string;
  opening: string;
  locked_block?: string;
  hypothesis?: string;
  status: string;
  model?: string;
  evidence_ids?: string[];
  fact_id?: string;
  claim_check?: string;
};
export type Subject = {
  id: string;
  revision: number;
  draft_id: string;
  snapshot_id: string;
  evidence_epoch: number;
  audience_epoch: number;
};
export type Event = {
  sequence: number;
  kind: string;
  at: number;
  payload: Record<string, unknown>;
};
export type Review = {
  case_id: string;
  subject: Subject;
  candidate_valid: boolean;
  approval_valid: boolean;
  blocked_reasons: string[];
  approval: null | {
    id: string;
    decision: string;
    reason: string;
    actor: string;
    at: number;
    expires_at: number;
  };
  handoff: null | { id: string; recipients: number; accepted_at: number };
  manifest: {
    counts: Record<string, number>;
    variable_cost_pence: number;
    exclusion_reasons: Record<string, number>;
    creatives: Creative[];
    arm_counts: Record<string, number>;
  };
  authority: {
    pack: {
      product: string;
      checked_on: string;
      review_by: string;
      facts: { id: string; copy: string; qualification: string }[];
      sources: { title: string; url: string }[];
    };
    policy: Record<string, unknown>;
  };
  changes: null | {
    removed_count: number;
    added_count: number;
    copy_changed: boolean;
    cost_delta_pence: number;
  };
  events: Event[];
  revisions: Subject[];
};
export type Recommendation = {
  segment: string;
  action: string;
  candidate_arm?: string;
  probability_beats_control?: number;
  probability_beats_other?: number;
  lift_mean?: number;
  lift_interval_90?: number[];
  response_intervals_90?: Record<string, number[]>;
  reason: string;
};
export type Learning = {
  cohort: { id: string; window_start: number; window_end: number };
  status: string;
  enrolled: number;
  received: number;
  missing: number;
  beliefs: {
    segment: string;
    arm: string;
    trials: number;
    successes: number;
    alpha: number;
    beta: number;
    mean: number;
    creative_id: string;
  }[];
  recommendations: Recommendation[];
  events: Event[];
  limitations: string[];
};
export type Row = {
  id: string;
  segment: string;
  country: string;
  entity_type: string;
  suppressed: boolean;
  arm: string;
  score: number | null;
  address: string;
};
export type Session = {
  id: string;
  name: string;
  mode: "fixture" | "model";
  clock: number;
  clock_mode: "REAL" | "SIMULATED";
  parent_id?: string | null;
  created_at: number;
  case_id: string | null;
  run_id: string | null;
  cohort_id: string | null;
};
export type State = {
  command_replayed?: boolean;
  session: Session;
  review: Review | null;
  audience: Row[];
  learning: Learning | null;
  tasks: unknown;
};
export const token = () =>
  document.querySelector<HTMLMetaElement>('meta[name="workspace-token"]')
    ?.content ?? "";
export async function read<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    headers: { "X-Workspace-Token": token() },
    signal,
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error ?? "Unable to load workspace");
  return result;
}
export async function command(
  path: string,
  payload: Record<string, unknown>,
): Promise<State> {
  const signature = JSON.stringify([path, payload]);
  let pending: { signature: string; request_id: string } | null = null;
  try {
    pending = JSON.parse(sessionStorage.getItem("workspace-pending") ?? "null");
  } catch {
    /* New request below. */
  }
  if (pending?.signature !== signature) {
    pending = { signature, request_id: crypto.randomUUID() };
    sessionStorage.setItem("workspace-pending", JSON.stringify(pending));
  }
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-Token": token(),
    },
    body: JSON.stringify({ ...payload, request_id: pending.request_id }),
  });
  const result = await response.json();
  if (response.status < 500) sessionStorage.removeItem("workspace-pending");
  if (!response.ok)
    throw new Error(
      result.error ??
        "The action did not return a confirmed result. Refresh before retrying.",
    );
  sessionStorage.removeItem("workspace-pending");
  return result;
}
export async function download(id: string, kind: string, subjectId: string) {
  const response = await fetch(
    `/api/sessions/${id}/artifacts/${kind}?subject_id=${encodeURIComponent(subjectId)}`,
    {
      headers: { "X-Workspace-Token": token() },
    },
  );
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    throw new Error(result.error ?? "Unable to download this artifact");
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = kind + (kind === "manifest" ? ".json" : ".csv");
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const money = (p: number) =>
  new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(
    p / 100,
  );
export const date = (v: number) =>
  new Date(v * 1000).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  }) + " UTC";
export const percent = (v: number) =>
  new Intl.NumberFormat("en-GB", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(v);
