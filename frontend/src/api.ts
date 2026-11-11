import { openRouterHeaders, openRouterSession } from "./openrouter-session";
import type { OpenRouterSession } from "./openrouter-session";

export type ValidationReport = {
  id: string;
  subject_id: string;
  draft_id: string;
  snapshot_id: string;
  evaluated_at: number;
  review_ready: boolean;
  authority: "none";
  checks: {
    id: string;
    label: string;
    required: boolean;
    status: "passed" | "failed" | "unknown" | "not_evaluated";
    detail: string;
  }[];
};
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
  payload: Record<string, unknown> & { delivery?: DeliverySummary | null };
};
export type DeliverySummary = {
  status: "accepted" | "partially_accepted" | "rejected";
  intended_recipients: number;
  accepted_recipients: number;
  rejected_recipients: number;
  control_count: number;
};
export type Review = {
  case_id: string;
  subject: Subject;
  candidate_valid: boolean;
  validation_report: ValidationReport;
  approval_valid: boolean;
  blocked_reasons: string[];
  delivery?: DeliverySummary | null;
  approval: null | {
    id: string;
    decision: string;
    reason: string;
    actor: string;
    at: number;
    expires_at: number;
  };
  handoff: null | {
    id: string;
    recipients: number;
    accepted_at: number;
    subject_id: string;
    approval_id: string;
    draft_id: string;
    destination: string;
    mode: string;
  };
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

export function partialDelivery(
  source: Pick<Review, "delivery"> | null | undefined,
) {
  const delivery = source?.delivery;
  return delivery?.status === "partially_accepted" ? delivery : null;
}

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
  monitoring?: {
    status: "scheduled" | "paused" | "blocked" | "complete";
    position: number;
    report_count: number;
    next_due: number | null;
    last_checked: number | null;
    last_report_id: string | null;
    watermark: number | null;
    detail: string | null;
  } | null;
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
export type FollowupHypothesis = {
  schema: "followup-hypothesis/v1";
  segment: string;
  evidence_status: "strong" | "weak" | "absent";
  hypothesis: string;
  evidence_id: string;
  candidate: null | { arm: string; creative_id: string; hook?: string };
  limitations: string;
  evidence: {
    source_cohort: string;
    source_draft: string;
    groups: {
      arm: string;
      creative_id: string;
      trials: number;
      successes: number;
    }[];
    comparison: Recommendation | null;
  };
};
export type Followup = {
  id: string;
  source_cohort: string;
  eligible: boolean;
  source_label: string;
  hypothesis: string;
  hypotheses?: FollowupHypothesis[];
  brief: { budget_pence: number; segments: string[] };
  counts: Record<string, number>;
  cost_pence: number;
  snapshot_id: string;
  contexts: Record<string, string>;
  memory: unknown;
  learning: unknown;
  session_id: string | null;
  mode?: string;
  case_id?: string | null;
  generation?: {
    status: string;
    outcome_uncertain: boolean;
    provider_error: string | null;
  };
};
export type State = {
  followups?: Followup[];
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

function modelCommand(path: string, payload: Record<string, unknown>) {
  const conversation =
    /^\/api\/conversations\/[^/]+\/(actions|confirm-copy-action|plan|preparations)$/.test(
      path,
    );
  const campaign = /^\/api\/sessions\/[^/]+\/copy-revisions$/.test(path);
  return (conversation && payload.fixture !== true) || campaign;
}

export class OpenRouterDisconnected extends Error {}

async function providerPost<T>(
  action: "check" | "advance" | "disconnect",
  headers: Record<string, string>,
  signal?: AbortSignal,
) {
  const response = await fetch(`/api/openrouter/${action}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-Token": token(),
      ...headers,
    },
    body: "{}",
    signal,
  });
  const result = await response.json();
  if (!response.ok) {
    if (result.openrouter_disconnected)
      throw new OpenRouterDisconnected(result.error);
    throw new Error(result.error ?? "OpenRouter is unavailable.");
  }
  return result as T;
}

export async function connectOpenRouter(
  key: string,
  tab: string,
  previous: OpenRouterSession | null,
): Promise<OpenRouterSession> {
  const connection = await providerPost<
    Pick<OpenRouterSession, "handle" | "binding">
  >("check", {
    ...(previous ? { "X-OpenRouter-Handle": previous.handle } : {}),
    "X-OpenRouter-Session": tab,
    Authorization: "Bearer " + key,
  });
  return {
    ...connection,
    session: tab,
    model:
      previous?.binding === connection.binding ? previous?.model : undefined,
  };
}

export function openRouterRequest(
  action: "advance" | "disconnect",
  session: OpenRouterSession,
  signal?: AbortSignal,
) {
  return providerPost<{ ok: true }>(
    action,
    openRouterHeaders({ ...session, model: undefined }),
    signal,
  );
}

export async function read<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, {
    headers: { "X-Workspace-Token": token() },
    signal,
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error ?? "Unable to load workspace");
  return result;
}
const pendingPrefix = "workspace-pending:";

function pendingKey(path: string, payload: Record<string, unknown>) {
  // Workspace commands have flat JSON fields. Match the server's order-independent identity.
  return (
    pendingPrefix +
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
    // The single-record format predates browser-funded commands.
    sessionStorage.setItem(
      key,
      JSON.stringify({ requestId: record.request_id, browser: null }),
    );
  sessionStorage.removeItem("workspace-pending");
}

export class MessageNotSavedError extends Error {}
export class FollowupReceiptPendingError extends Error {}
export class AudienceNotSavedError extends Error {}
export class ModelSelectionNotSavedError extends Error {}

export type ModelFunding = {
  browser: Pick<OpenRouterSession, "binding" | "model"> | null;
};

export function captureModelFunding(): ModelFunding {
  const current = openRouterSession();
  return {
    browser: current
      ? { binding: current.binding, model: current.model }
      : null,
  };
}

type PendingCommand = ModelFunding & {
  requestId: string;
  legacyFollowup?: true;
};

export function pendingPreparation(conversationId: string, revision: number) {
  const path = `/api/conversations/${conversationId}/preparations`;
  const prefix = pendingPrefix + "[" + JSON.stringify(path) + ",";
  const matches = Object.keys(sessionStorage)
    .filter((key) => key.startsWith(prefix))
    .map((key) => {
      const [, payload] = JSON.parse(key.slice(pendingPrefix.length));
      if (payload.expected_revision !== revision) return null;
      const { fixture, allow_model_copy, use_audience_catalogue } = payload;
      const record = sessionStorage.getItem(key);
      const inputs = {
        expected_revision: revision,
        fixture,
        allow_model_copy,
        ...(use_audience_catalogue === true
          ? { use_audience_catalogue: true }
          : {}),
      };
      if (
        typeof fixture !== "boolean" ||
        typeof allow_model_copy !== "boolean" ||
        key !== pendingKey(path, inputs) ||
        !record
      )
        throw new Error(
          "The original preparation inputs could not be verified.",
        );
      const funding = record.startsWith("{")
        ? { browser: (JSON.parse(record) as PendingCommand).browser }
        : undefined;
      if (
        funding &&
        funding.browser !== null &&
        typeof funding.browser?.binding !== "string"
      )
        throw new Error(
          "The original preparation funding could not be verified.",
        );
      return { conversationId, ...inputs, funding };
    })
    .filter((intent) => intent !== null);
  if (matches.length > 1)
    throw new Error(
      "More than one preparation is pending for this brief. Inspect the saved conversation before retrying.",
    );
  return matches[0];
}

async function observePendingFollowup<T>(
  conversationPath: string,
  payload: Record<string, unknown>,
  requestId: string,
): Promise<T | null> {
  const view = await read<{
    id: string;
    revision: number;
    actions: {
      id: string;
      request_id: string;
      revision: number;
      content: string;
      allow_model_copy: boolean;
    }[];
  }>(conversationPath);
  if (
    conversationPath !== `/api/conversations/${view.id}` ||
    !Array.isArray(view.actions)
  )
    throw new Error(
      "The workspace could not verify this follow-up. Retry checking its receipt.",
    );
  const action = view.actions.find((item) => item.request_id === requestId);
  if (!action) {
    // The server reads the revision before listing actions. Admission checks
    // that revision in the same transaction that saves the follow-up.
    if (
      typeof payload.expected_revision === "number" &&
      view.revision > payload.expected_revision
    )
      return null;
    throw new FollowupReceiptPendingError(
      "There is no saved receipt yet. Check again or resend the original follow-up.",
    );
  }
  if (
    action.revision !== payload.expected_revision ||
    action.content !== payload.content ||
    action.allow_model_copy !== payload.allow_model_copy
  )
    throw new Error("The saved follow-up differs from this pending message.");
  return {
    ...view,
    action_receipt: { id: action.id, revision: action.revision },
  } as T;
}

export async function command<T = State>(
  path: string,
  payload: Record<string, unknown>,
  funding?: ModelFunding | null,
  legacyFollowup?: {
    resend: boolean;
    acknowledge: () => void;
  },
): Promise<T> {
  migratePendingCommand();
  const key = pendingKey(path, payload);
  const saved = sessionStorage.getItem(key);
  const usesModel = modelCommand(path, payload);
  const current = usesModel ? openRouterSession() : null;
  const followup = /^(\/api\/conversations\/[^/]+)\/actions$/.exec(path);
  const savedCommand = saved?.startsWith("{")
    ? (JSON.parse(saved) as PendingCommand)
    : null;
  const legacyRequestId =
    followup && (!savedCommand || savedCommand.legacyFollowup)
      ? (savedCommand?.requestId ?? saved)
      : null;
  if (legacyRequestId && followup && !legacyFollowup?.resend) {
    const result = await observePendingFollowup<T>(
      followup[1],
      payload,
      legacyRequestId,
    );
    legacyFollowup?.acknowledge();
    sessionStorage.removeItem(key);
    if (result === null)
      throw new MessageNotSavedError(
        "The brief has changed. Review it before sending this follow-up again.",
      );
    return result;
  }
  if (legacyFollowup?.resend && !legacyRequestId)
    throw new Error(
      "The original follow-up request ID is unavailable. Check its receipt before continuing.",
    );
  let pending: PendingCommand;
  if (savedCommand) {
    pending = savedCommand;
  } else if (!saved || legacyRequestId) {
    if (usesModel && funding === null && !legacyRequestId)
      throw new MessageNotSavedError(
        "The previous submission did not record a request ID. Review the text and send it again when ready.",
      );
    pending = {
      requestId: legacyRequestId ?? crypto.randomUUID(),
      browser: usesModel ? (funding ?? captureModelFunding()).browser : null,
      ...(legacyRequestId ? { legacyFollowup: true } : {}),
    };
    // Persist before dispatch. Storage failure leaves the action undispatched.
    sessionStorage.setItem(key, JSON.stringify(pending));
  } else {
    if (usesModel)
      throw new Error(
        "This older pending request has no saved provider choice. Inspect the conversation before starting a new request.",
      );
    pending = { requestId: saved, browser: null };
  }
  let headers: Record<string, string> = {};
  if (pending.browser) {
    if (!current || current.binding !== pending.browser.binding)
      throw new Error(
        "Reconnect the original OpenRouter key in this tab before retrying this request.",
      );
    headers = openRouterHeaders({ ...current, model: pending.browser.model });
  } else if (
    /^\/api\/(conversations\/[^/]+\/draft|sessions\/[^/]+\/prepare)$/.test(path)
  ) {
    // These operations use settings bound by the server to existing work.
    headers = openRouterHeaders(openRouterSession());
  }
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-Token": token(),
      ...headers,
    },
    body: JSON.stringify({ ...payload, request_id: pending.requestId }),
  });
  const result = await response.json();
  if (
    legacyRequestId &&
    !response.ok &&
    (result.action_not_saved === true ||
      result.model_selection_not_saved === true)
  ) {
    // This attempt was rejected. An earlier request with the same ID may still commit.
    sessionStorage.setItem(key, legacyRequestId);
    throw new Error(
      result.error ??
        "The resend was rejected. Check the original follow-up receipt.",
    );
  }
  if (!response.ok && result.model_selection_not_saved === true) {
    sessionStorage.removeItem(key);
    throw new ModelSelectionNotSavedError(
      result.error ?? "Choose an available OpenRouter model in the composer.",
    );
  }
  if (
    !response.ok &&
    response.status === 409 &&
    result.action_not_saved === true &&
    /^\/api\/conversations\/[^/]+\/actions$/.test(path)
  ) {
    sessionStorage.removeItem(key);
    throw new MessageNotSavedError(
      result.error ?? "The follow-up was not saved.",
    );
  }
  if (
    !response.ok &&
    [400, 404, 409].includes(response.status) &&
    result.message_not_saved === true &&
    /^\/api\/conversations\/[^/]+\/(messages|artifact-comments|writing-preferences)$/.test(
      path,
    )
  ) {
    sessionStorage.removeItem(key);
    throw new MessageNotSavedError(
      result.error ?? "The message was not saved.",
    );
  }
  if (
    !response.ok &&
    response.status === 409 &&
    result.audience_not_saved === true &&
    /^\/api\/conversations\/[^/]+\/audience$/.test(path)
  ) {
    sessionStorage.removeItem(key);
    throw new AudienceNotSavedError(
      result.error ?? "The audience was not confirmed.",
    );
  }
  if (!response.ok)
    throw new Error(
      result.error ??
        "The action did not return a confirmed result. Refresh before retrying.",
    );
  if (legacyRequestId) legacyFollowup?.acknowledge();
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
      "X-Workspace-Plan-Replay": "1",
      // This path observes an existing plan. The server selects its frozen configuration.
      ...openRouterHeaders(
        modelCommand(path, payload) ? openRouterSession() : null,
      ),
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
  link.download =
    kind + (["manifest", "handoff"].includes(kind) ? ".json" : ".csv");
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
