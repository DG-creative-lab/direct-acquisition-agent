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
    brief: { budget_pence: number };
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
export type CopyRevision = {
  id: string;
  request_id: string;
  run_id: string | null;
  status: string;
  base_subject_id: string;
  target_id: string;
  feedback: string;
  published_subject_id: string | null;
  block: null | { code: string; detail: string };
  generation: null | {
    provider_error: string | null;
    outcome_uncertain: boolean;
    unresolved_calls: { key: string; status: string }[];
    failed_tasks: { capability: string; error_code: string }[];
  };
};
export type State = {
  copy_revisions?: CopyRevision[];
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
function pendingKey(path: string, payload: Record<string, unknown>) {
  // Workspace commands have flat JSON fields. Match the server's order-independent identity.
  return (
    "workspace-pending:" +
    JSON.stringify([
      path,
      Object.fromEntries(
        Object.entries(payload).sort(([a], [b]) => a.localeCompare(b)),
      ),
    ])
  );
}

function migratePendingCommand() {
  const legacy = sessionStorage.getItem("workspace-pending");
  if (!legacy) return;
  let record: { signature: string; request_id: string };
  let path: string, payload: Record<string, unknown>;
  try {
    record = JSON.parse(legacy);
    [path, payload] = JSON.parse(record.signature);
    if (
      typeof path !== "string" ||
      !payload ||
      typeof payload !== "object" ||
      Array.isArray(payload) ||
      typeof record.request_id !== "string" ||
      !record.request_id
    )
      return;
  } catch {
    return;
  }
  const key = pendingKey(path, payload);
  if (!sessionStorage.getItem(key))
    sessionStorage.setItem(key, record.request_id);
  sessionStorage.removeItem("workspace-pending");
}

export class MessageNotSavedError extends Error {}

export async function command<T = State>(
  path: string,
  payload: Record<string, unknown>,
): Promise<T> {
  migratePendingCommand();
  const key = pendingKey(path, payload);
  let requestId = sessionStorage.getItem(key);
  if (!requestId) {
    requestId = crypto.randomUUID();
    // Persist before dispatch. Storage failure leaves the action undispatched.
    sessionStorage.setItem(key, requestId);
  }
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-Token": token(),
    },
    body: JSON.stringify({ ...payload, request_id: requestId }),
  });
  const result = await response.json();
  if (
    !response.ok &&
    [400, 404, 409].includes(response.status) &&
    result.message_not_saved === true &&
    /^\/api\/conversations\/[^/]+\/messages$/.test(path)
  ) {
    sessionStorage.removeItem(key);
    throw new MessageNotSavedError(
      result.error ?? "The message was not saved.",
    );
  }
  if (!response.ok)
    throw new Error(
      result.error ??
        "The action did not return a confirmed result. Refresh before retrying.",
    );
  sessionStorage.removeItem(key);
  return result;
}

export async function replay<T>(
  path: string,
  payload: Record<string, unknown>,
  requestId: string,
): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-Token": token(),
    },
    body: JSON.stringify({ ...payload, request_id: requestId }),
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(result.error ?? "Unable to resume this request.");
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
