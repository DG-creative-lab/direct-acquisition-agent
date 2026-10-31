import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ArrowUpRight,
  Check,
  CircleAlert,
  Loader2,
  MessageSquare,
  Plus,
  Send,
} from "lucide-react";
import { command, MessageNotSavedError, money, read, replay } from "./api";
import type { State } from "./api";
import "./conversation.css";
import ConversationCampaignReview from "./ConversationCampaignReview";

type Brief = {
  id: string;
  outcome: "brief_proposal" | "clarification" | "unsupported";
  objective: string;
  budget_pence: number | null;
  segments: string[];
  copy_mode: "fixture" | "model";
  question: string;
  unsupported_reason: string;
};
type Plan = {
  request_id: string;
  revision: number;
  status: string;
  mode: "fixture" | "model";
  current: boolean;
  result: Brief | null;
  error: { provider_error?: string } | null;
  guidance?: {
    id: string;
    content: {
      version?: string;
      procedures?: string[];
      playbooks?: {
        version: string;
        playbooks: { id: string; title: string; guidance: string }[];
      };
    };
  };
};
type Preparation = {
  id: string;
  request_id: string;
  inputs: { revision: number; fixture: boolean; allow_model_copy: boolean };
  current: boolean;
  status: string;
  detail: string | null;
  run_id: string;
  generation: {
    run_id: string;
    status: string;
    provider_error: string | null;
    outcome_uncertain: boolean;
    unresolved_calls?: { key: string; status: string }[];
    steps?: { capability: string; status: string }[];
  } | null;
};
type PreparationIntent = {
  conversationId: string;
  expected_revision: number;
  fixture: boolean;
  allow_model_copy: boolean;
};
const preparationIntentKey = "conversation-preparation-intent";
function savedPreparationIntent(): PreparationIntent | null {
  try {
    const value = JSON.parse(
      sessionStorage.getItem(preparationIntentKey) ?? "null",
    );
    return value &&
      typeof value.conversationId === "string" &&
      Number.isInteger(value.expected_revision) &&
      typeof value.fixture === "boolean" &&
      typeof value.allow_model_copy === "boolean"
      ? value
      : null;
  } catch {
    return null;
  }
}
const activePreparation = (status: string) =>
  ["admitting", "planning", "preparing"].includes(status);

type Conversation = {
  preparations?: Preparation[];
  id: string;
  title: string;
  revision: number;
  message_receipt?: { id: string; revision: number; replayed: boolean };
  messages: { id: string; revision: number; content: string }[];
  plans: Plan[];
  current_plan: Plan | null;
  campaigns?: {
    session_id: string;
    plan_id: string;
    revision: number;
    case_id: string | null;
    generation?: {
      run_id: string | null;
      status: string;
      provider_error: string | null;
      outcome_uncertain?: boolean;
      unresolved_calls?: { key: string; status: string }[];
      failed_tasks: { capability: string; error_code: string }[];
    };
  }[];
};
type ConversationSummary = { id: string; title: string; revision: number };
type PendingMessage = {
  conversationId: string;
  expected_revision: number;
  content: string;
  allow_model_copy?: boolean;
};
const pendingMessageKey = "conversation-pending-message";
function savedPendingMessage(): PendingMessage | null {
  try {
    const value = JSON.parse(
      sessionStorage.getItem(pendingMessageKey) ?? "null",
    );
    return value &&
      typeof value.conversationId === "string" &&
      Number.isInteger(value.expected_revision) &&
      typeof value.content === "string"
      ? value
      : null;
  } catch {
    return null;
  }
}
const example =
  "Prepare a £600 direct-mail response experiment for UK contractors. Use offline copy fixtures.";

export default function ConversationWorkspace({
  onOpenCampaign,
  navigationTarget,
  active,
  onNavigate,
  onCampaignsChanged,
}: {
  onOpenCampaign: (state: State) => void;
  navigationTarget: HTMLElement | null;
  active: boolean;
  onNavigate: () => void;
  onCampaignsChanged: () => Promise<unknown>;
}) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [pendingMessage, setPendingMessage] = useState<PendingMessage | null>(
    savedPendingMessage,
  );
  const [selected, setSelected] = useState(
    () =>
      savedPendingMessage()?.conversationId ??
      localStorage.getItem("conversation-selected") ??
      "",
  );
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [message, setMessage] = useState(
    () => savedPendingMessage()?.content ?? "",
  );
  const [allowModelCopy, setAllowModelCopy] = useState(false);
  const [preparationIntent, setPreparationIntent] = useState(
    savedPreparationIntent,
  );
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [reviewing, setReviewing] = useState(
    () => localStorage.getItem("conversation-review-session") ?? "",
  );
  const epoch = useRef(0);

  const accept = (value: Conversation) => {
    epoch.current += 1;
    setConversation(value);
  };

  const list = async () =>
    setConversations(
      (
        await read<{ conversations: ConversationSummary[] }>(
          "/api/conversations",
        )
      ).conversations,
    );
  const load = async (id: string) => {
    const result = await read<Conversation>(`/api/conversations/${id}`);
    accept(result);
    return result;
  };
  useEffect(() => {
    list().catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    let active = true;
    const stamp = ++epoch.current;
    setConversation(null);
    if (!selected) return;
    localStorage.setItem("conversation-selected", selected);
    read<Conversation>(`/api/conversations/${selected}`)
      .then((value) => {
        if (active && stamp === epoch.current) setConversation(value);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [selected]);

  useEffect(() => {
    if (
      !conversation ||
      !preparationIntent ||
      conversation.id !== preparationIntent.conversationId
    )
      return;
    const saved = conversation.preparations?.find(
      (p) =>
        p.inputs.revision === preparationIntent.expected_revision &&
        p.inputs.fixture === preparationIntent.fixture &&
        p.inputs.allow_model_copy === preparationIntent.allow_model_copy,
    );
    if (saved) {
      sessionStorage.removeItem(preparationIntentKey);
      setPreparationIntent(null);
    }
  }, [conversation, preparationIntent]);

  const preparedCampaigns =
    conversation?.campaigns
      ?.filter((c) => c.case_id)
      .map((c) => c.session_id)
      .sort()
      .join(",") ?? "";
  useEffect(() => {
    if (preparedCampaigns)
      onCampaignsChanged().catch((e) => setError(e.message));
  }, [preparedCampaigns, onCampaignsChanged]);

  const preparing =
    conversation?.preparations?.some((p) => activePreparation(p.status)) ??
    false;
  useEffect(() => {
    if (!selected || !preparing || !active) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      const stamp = epoch.current;
      try {
        const value = await read<Conversation>(
          `/api/conversations/${selected}`,
        );
        if (!disposed && stamp === epoch.current) setConversation(value);
      } catch {
        // Keep the last saved progress and retry the read, never the model call.
      }
      if (!disposed) timer = setTimeout(poll, 600);
    };
    timer = setTimeout(poll, 300);
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [selected, preparing, active]);

  const continuePreparation = async (intent: PreparationIntent) => {
    sessionStorage.setItem(preparationIntentKey, JSON.stringify(intent));
    setPreparationIntent(intent);
    const value = await command<Conversation>(
      `/api/conversations/${intent.conversationId}/preparations`,
      {
        expected_revision: intent.expected_revision,
        fixture: intent.fixture,
        allow_model_copy: intent.allow_model_copy,
      },
    );
    sessionStorage.removeItem(preparationIntentKey);
    setPreparationIntent(null);
    accept(value);
  };

  const newConversation = async (title = "Campaign conversation") => {
    const created = await command<Conversation>("/api/conversations", {
      title,
    });
    setSelected(created.id);
    accept(created);
    localStorage.setItem("conversation-selected", created.id);
    await list();
    return created;
  };
  const createDraft = async (id: string, revision: number, brief: Brief) => {
    const state = await command<State>(`/api/conversations/${id}/draft`, {
      expected_revision: revision,
      plan_id: brief.id,
    });
    await load(id);
    return state;
  };
  const finishPlan = async (
    id: string,
    revision: number,
    planned: Conversation,
  ) => {
    const plan = planned.current_plan;
    accept(planned);
    if (
      plan?.status === "succeeded" &&
      plan.result?.outcome === "brief_proposal" &&
      plan.result.copy_mode === "fixture"
    ) {
      setBusy("Preparing the campaign");
      await createDraft(id, revision, plan.result);
    }
  };
  const send = async () => {
    if ((!message.trim() && !pendingMessage) || busy) return;
    setError("");
    setBusy("Saving your request");
    let current = conversation;
    try {
      if (!current && pendingMessage)
        throw new Error(
          "Wait for the original conversation to load before retrying.",
        );
      if (!current)
        current = await newConversation(
          message.trim().replace(/\s+/g, " ").slice(0, 80),
        );
      const pending = pendingMessage ?? {
        conversationId: current.id,
        expected_revision: current.revision,
        content: message.trim(),
        allow_model_copy: allowModelCopy,
      };
      if (pending.conversationId !== current.id)
        throw new Error(
          "Resume the pending message in its original conversation.",
        );
      sessionStorage.setItem(pendingMessageKey, JSON.stringify(pending));
      setPendingMessage(pending);
      let saved: Conversation;
      try {
        saved = await command<Conversation>(
          `/api/conversations/${current.id}/messages`,
          {
            expected_revision: pending.expected_revision,
            content: pending.content,
          },
        );
      } catch (error) {
        if (error instanceof MessageNotSavedError) {
          sessionStorage.removeItem(pendingMessageKey);
          setPendingMessage(null);
        }
        throw error;
      }
      const messageRevision = saved.message_receipt?.revision;
      if (messageRevision !== pending.expected_revision + 1)
        throw new Error(
          "The original message receipt could not be confirmed. Retry saving the original message.",
        );
      const intent = {
        conversationId: current.id,
        expected_revision: messageRevision,
        fixture: false,
        allow_model_copy: pending.allow_model_copy === true,
      };
      if (saved.revision === messageRevision) {
        sessionStorage.setItem(preparationIntentKey, JSON.stringify(intent));
        setPreparationIntent(intent);
      }
      sessionStorage.removeItem(pendingMessageKey);
      setPendingMessage(null);
      accept(saved);
      setMessage("");
      setAllowModelCopy(false);
      if (saved.revision !== messageRevision)
        throw new Error(
          "Your message was saved, but the brief has since changed. Review the latest messages and send a new request with its own copy permission.",
        );
      setBusy("Starting campaign preparation");
      await continuePreparation(intent);
      await list();
    } catch (e) {
      setError((e as Error).message);
      if (current) await load(current.id).catch(() => {});
    } finally {
      setBusy("");
    }
  };
  const startExample = async () => {
    setError("");
    setBusy("Preparing the offline example");
    let current: Conversation | null = null;
    try {
      current = await newConversation("Offline example");
      const saved = await command<Conversation>(
        `/api/conversations/${current.id}/messages`,
        { expected_revision: 0, content: example },
      );
      accept(saved);
      const messageRevision = saved.message_receipt?.revision;
      if (messageRevision !== 1 || saved.revision !== messageRevision)
        throw new Error(
          "The example brief changed. Review the latest messages before preparing a campaign.",
        );
      await continuePreparation({
        conversationId: current.id,
        expected_revision: messageRevision,
        fixture: true,
        allow_model_copy: false,
      });
      await list();
    } catch (e) {
      setError((e as Error).message);
      if (current) await load(current.id).catch(() => {});
    } finally {
      setBusy("");
    }
  };
  const resume = async () => {
    if (!conversation || busy) return;
    setError("");
    setBusy("Resuming the request");
    try {
      if (preparationIntent?.conversationId === conversation.id) {
        await continuePreparation(preparationIntent);
        return;
      }
      const plan = conversation.current_plan;
      const offline =
        plan?.mode === "fixture" ||
        (!plan &&
          conversation.title === "Offline example" &&
          conversation.messages.length === 1 &&
          conversation.messages[0].content === example);
      const path = `/api/conversations/${conversation.id}/${offline ? "plan-fixture" : "plan"}`;
      const payload = { expected_revision: conversation.revision };
      const result = plan
        ? await replay<Conversation>(path, payload, plan.request_id)
        : await command<Conversation>(path, payload);
      await finishPlan(conversation.id, conversation.revision, result);
    } catch (e) {
      setError((e as Error).message);
      await load(conversation.id).catch(() => {});
    } finally {
      setBusy("");
    }
  };
  const openCampaign = async (id: string) => {
    setError("");
    try {
      onOpenCampaign(await read<State>(`/api/sessions/${id}`));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const prepare = async (plan: Plan) => {
    if (!conversation || !plan.result) return;
    setBusy(
      plan.result.copy_mode === "model"
        ? "Generating and checking campaign copy"
        : "Preparing the campaign",
    );
    setError("");
    try {
      await createDraft(conversation.id, plan.revision, plan.result);
    } catch (e) {
      setError((e as Error).message);
      await load(conversation.id).catch(() => {});
    } finally {
      setBusy("");
    }
  };
  const startNew = () => {
    onNavigate();
    if (busy || pendingMessage) return;
    setSelected("");
    setConversation(null);
    setMessage("");
    localStorage.removeItem("conversation-selected");
    setError("");
  };
  const chooseConversation = (id: string) => {
    setSelected(id);
    setError("");
    onNavigate();
  };
  const hasMessages = Boolean(conversation?.messages.length);
  return (
    <section
      className="conversation-workspace"
      aria-label="Direct Acquisition assistant"
    >
      {navigationTarget &&
        createPortal(
          <div className="conversation-sidebar">
            <button
              className="conversation-new"
              aria-label={
                busy || pendingMessage
                  ? "Return to conversation"
                  : "New conversation"
              }
              onClick={startNew}
            >
              <Plus size={17} />
              <span>
                {busy || pendingMessage
                  ? "Return to conversation"
                  : "New conversation"}
              </span>
            </button>
            <div
              className="conversation-history"
              aria-label="Recent conversations"
            >
              {conversations.length > 0 && (
                <div className="conversation-history-title">CONVERSATIONS</div>
              )}
              {conversations.map((item) => (
                <button
                  key={item.id}
                  className={
                    active && selected === item.id
                      ? "conversation-history-item selected"
                      : "conversation-history-item"
                  }
                  disabled={!!busy || !!pendingMessage}
                  onClick={() => chooseConversation(item.id)}
                >
                  <MessageSquare size={15} />
                  <span>{item.title}</span>
                </button>
              ))}
            </div>
          </div>,
          navigationTarget,
        )}
      <aside className="conversation-list" aria-label="Recent conversations">
        {conversations.map((item) => (
          <button
            key={item.id}
            className={
              selected === item.id
                ? "conversation-choice selected"
                : "conversation-choice"
            }
            disabled={!!busy || !!pendingMessage}
            onClick={() => chooseConversation(item.id)}
          >
            <MessageSquare size={16} />
            <span>
              {item.title}
              <small>
                {item.revision
                  ? `${item.revision} message${item.revision === 1 ? "" : "s"}`
                  : "New conversation"}
              </small>
            </span>
          </button>
        ))}
      </aside>
      <div
        className={
          hasMessages ? "conversation-main" : "conversation-main is-empty"
        }
      >
        {!hasMessages && (
          <div className="conversation-intro">
            <h1>What would you like to prepare?</h1>
            <p>Describe your audience, objective and budget.</p>
          </div>
        )}
        <div className="conversation-thread" aria-live="polite">
          {conversation?.messages.map((item) => {
            const plan = conversation.plans.find(
              (p) => p.revision === item.revision,
            );
            const campaign = conversation.campaigns?.find(
              (c) => c.plan_id === plan?.result?.id,
            );
            const preparation = conversation.preparations?.find(
              (p) => p.inputs.revision === item.revision,
            );
            const coordinated =
              preparation && activePreparation(preparation.status);
            const generation = campaign?.generation;
            const terminal =
              generation &&
              !coordinated &&
              (["failed", "cancelled"].includes(generation.status) ||
                generation.outcome_uncertain);
            return (
              <div className="conversation-turn" key={item.id}>
                <div className="conversation-user">
                  <span>You</span>
                  <p>{item.content}</p>
                </div>
                {preparation && (
                  <PreparationProgress preparation={preparation} />
                )}
                {plan && (
                  <div className="conversation-agent">
                    <div className="conversation-agent-label">
                      <span className="agent-dot">
                        <Check size={11} />
                      </span>
                      Direct Acquisition
                      {!plan.current && <small>Earlier proposal</small>}
                    </div>
                    {plan.guidance && (
                      <details className="planning-guidance">
                        <summary>Inspect planning guidance</summary>
                        <p>
                          Frozen for this planning request. Advisory guidance
                          does not grant approval.
                        </p>
                        <p>
                          Snapshot: <code>{plan.guidance.id}</code>
                        </p>
                        <p>Catalogue: {plan.guidance.content.version}</p>
                        {plan.guidance.content.procedures?.map((rule) => (
                          <p key={rule}>{rule}</p>
                        ))}
                        {plan.guidance.content.playbooks && (
                          <div>
                            <p>
                              Playbooks:{" "}
                              {plan.guidance.content.playbooks.version}
                            </p>
                            {plan.guidance.content.playbooks.playbooks.map(
                              (item) => (
                                <p key={item.id}>
                                  <strong>{item.title}</strong> ·{" "}
                                  {item.guidance}
                                </p>
                              ),
                            )}
                          </div>
                        )}
                        <details>
                          <summary>Complete saved snapshot</summary>
                          <pre aria-label="Complete frozen planning guidance">
                            {JSON.stringify(plan.guidance.content, null, 2)}
                          </pre>
                        </details>
                      </details>
                    )}
                    {plan.status === "failed" ? (
                      <p>
                        Planning could not finish.{" "}
                        {plan.error?.provider_error === "provider_http_401"
                          ? "Check the OpenRouter key before starting a new request."
                          : "Review the request and send a new message to continue."}
                      </p>
                    ) : !plan.result ? (
                      <p>
                        Planning is {plan.status}.{" "}
                        {coordinated
                          ? "The agent is continuing this request."
                          : "Resume this request to continue."}
                      </p>
                    ) : plan.result.outcome === "clarification" ? (
                      <p>{plan.result.question}</p>
                    ) : plan.result.outcome === "unsupported" ? (
                      <p>{plan.result.unsupported_reason}</p>
                    ) : (
                      <div className="brief-summary">
                        <h3>Campaign brief</h3>
                        <p>{plan.result.objective}</p>
                        <dl>
                          <div>
                            <dt>Audience</dt>
                            <dd>
                              {plan.result.segments
                                .map((s) =>
                                  s === "contractors"
                                    ? "Projects and contractors"
                                    : "Stock and inventory",
                                )
                                .join(", ")}
                            </dd>
                          </div>
                          <div>
                            <dt>Budget</dt>
                            <dd>{money(plan.result.budget_pence ?? 0)}</dd>
                          </div>
                          <div>
                            <dt>Copy</dt>
                            <dd>
                              {plan.result.copy_mode === "fixture"
                                ? "Offline fixtures"
                                : "Model-generated"}
                            </dd>
                          </div>
                        </dl>
                        {campaign?.case_id ? (
                          <button
                            className="button primary"
                            onClick={() => {
                              setReviewing(campaign.session_id);
                              localStorage.setItem(
                                "conversation-review-session",
                                campaign.session_id,
                              );
                            }}
                            disabled={!!busy}
                          >
                            Review campaign <ArrowUpRight size={15} />
                          </button>
                        ) : terminal ? (
                          <div className="generation-failure" role="status">
                            <strong>
                              {generation.outcome_uncertain
                                ? "Generation outcome is uncertain"
                                : `Campaign generation ${generation.status}`}
                            </strong>
                            <p>
                              {generation.outcome_uncertain
                                ? "The provider may have processed and charged for this request. Inspect the original run before requesting another generation."
                                : generation.provider_error ===
                                    "provider_http_401"
                                  ? "OpenRouter rejected the API key (401). Update the server key, then send a new message to create a fresh proposal."
                                  : generation.provider_error ===
                                      "provider_outcome_unknown"
                                    ? "The provider outcome is unknown. Inspect this run before explicitly requesting a new proposal."
                                    : "This saved run cannot resume. Inspect the failure, then send a new message to create a fresh proposal."}
                            </p>
                            <details>
                              <summary>Inspect generation run</summary>
                              <p>
                                Run: <code>{generation.run_id}</code>
                              </p>
                              <p>Status: {generation.status}</p>
                              {generation.provider_error && (
                                <p>Provider: {generation.provider_error}</p>
                              )}
                              {generation.failed_tasks.map((task) => (
                                <p key={task.capability}>
                                  {task.capability}: {task.error_code}
                                </p>
                              ))}
                              {generation.unresolved_calls?.map((call) => (
                                <p key={call.key}>
                                  Unresolved call: <code>{call.key}</code> (
                                  {call.status})
                                </p>
                              ))}
                            </details>
                          </div>
                        ) : (
                          plan.current &&
                          !coordinated &&
                          !preparation && (
                            <button
                              className="button secondary"
                              onClick={() => prepare(plan)}
                              disabled={!!busy}
                            >
                              {campaign
                                ? "Resume campaign preparation"
                                : plan.result.copy_mode === "model"
                                  ? "Generate campaign copy"
                                  : "Prepare campaign"}
                            </button>
                          )
                        )}
                        {plan.result.copy_mode === "model" &&
                          !campaign?.case_id &&
                          !terminal &&
                          !coordinated && (
                            <small>
                              Uses OpenRouter credit to generate and screen copy
                              for the selected audience.
                            </small>
                          )}
                        <small>
                          {campaign?.case_id
                            ? "Unapproved synthetic draft. No mail is sent."
                            : terminal
                              ? "No reviewable campaign was created."
                              : coordinated
                                ? "Preparation is in progress. No approval has been granted."
                                : "Brief proposal. No campaign has been generated yet."}
                        </small>
                      </div>
                    )}
                    {campaign?.case_id && reviewing === campaign.session_id && (
                      <ConversationCampaignReview
                        key={campaign.session_id}
                        sessionId={campaign.session_id}
                        interactive={plan.current}
                        active={active}
                        onOpenWorkspace={(targetId) =>
                          void openCampaign(targetId ?? campaign.session_id)
                        }
                      />
                    )}
                  </div>
                )}
              </div>
            );
          })}
          {busy && (
            <div className="conversation-progress" role="status">
              <Loader2 className="spin" size={16} />
              {busy}…
            </div>
          )}
          {error && (
            <p className="conversation-error" role="alert">
              {error}
            </p>
          )}
          {!pendingMessage &&
          conversation?.messages.length &&
          !busy &&
          !preparing &&
          (preparationIntent?.conversationId === conversation.id ||
            !conversation.current_plan ||
            ["queued", "running", "admitted"].includes(
              conversation.current_plan.status,
            )) ? (
            <button
              className="text-button conversation-resume"
              onClick={resume}
            >
              {preparationIntent?.conversationId === conversation.id
                ? "Resume preparation"
                : "Resume planning"}
            </button>
          ) : null}
        </div>
        <form
          className="conversation-compose"
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          <label className="conversation-input-label" htmlFor="agent-message">
            Message Direct Acquisition
          </label>
          <div>
            <textarea
              id="agent-message"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="Describe the audience, objective and budget"
              maxLength={2000}
              disabled={!!busy || !!pendingMessage}
              rows={2}
            />
            <button
              type="submit"
              className="conversation-send"
              aria-label={
                pendingMessage ? "Retry saving message" : "Send to agent"
              }
              disabled={
                !!busy ||
                (!message.trim() && !pendingMessage) ||
                (!!pendingMessage && !conversation)
              }
            >
              <Send size={18} />
            </button>
          </div>
          <label className="conversation-consent">
            <input
              type="checkbox"
              checked={allowModelCopy}
              disabled={!!busy || !!pendingMessage}
              onChange={(event) => setAllowModelCopy(event.target.checked)}
            />
            Allow model copy for this request
          </label>
          <p>
            {pendingMessage
              ? "The last message needs confirmation. Retry saving it before continuing."
              : "Sending allows up to 2 planning calls. If allowed and proposed, model copy adds up to 10 calls. Approval is always separate."}
          </p>
        </form>
        {!hasMessages && (
          <div className="conversation-starters">
            <button
              className="conversation-example"
              disabled={!!busy || !!pendingMessage}
              onClick={startExample}
            >
              <span>
                Try the offline example <ArrowUpRight size={14} />
              </span>
              <small>Contractors · £600 · no model calls</small>
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

function PreparationProgress({ preparation }: { preparation: Preparation }) {
  const running = activePreparation(preparation.status);
  const uncertain =
    preparation.status === "uncertain" ||
    (!running && preparation.generation?.outcome_uncertain);
  const headings: Record<string, string> = {
    admitting: "Saving campaign preparation",
    planning: "Planning your campaign",
    preparing: "Preparing your campaign",
    review_ready: "Ready for your review",
    needs_input: "Your input is needed",
    needs_consent: "Permission needed for model copy",
    stale: "Stopped after a brief change",
    uncertain: "Provider outcome is uncertain",
    failed: "Preparation failed",
    blocked: "Preparation needs attention",
  };
  const taskLabels: Record<string, string> = {
    queued: "Queued",
    running: "In progress",
    succeeded: "Complete",
    waiting: "Human review required",
    failed: "Failed",
    cancelled: "Stopped",
  };
  const stage = (capability: string) =>
    capability.startsWith("conversations.")
      ? "Interpret the brief"
      : capability.startsWith("audiences.")
        ? "Check the synthetic audience"
        : capability.startsWith("creative.")
          ? "Generate and screen audience copy"
          : capability.includes("review")
            ? "Prepare the review checkpoint"
            : "Build and validate the draft";
  return (
    <section
      className="preparation-progress"
      aria-label="Campaign preparation progress"
    >
      <div className="preparation-heading" role="status">
        {running ? (
          <Loader2 className="spin" size={16} />
        ) : preparation.status === "review_ready" ? (
          <Check size={16} />
        ) : (
          <CircleAlert size={16} />
        )}
        <strong>
          {uncertain
            ? "Provider outcome is uncertain"
            : (headings[preparation.status] ?? preparation.status)}
        </strong>
        {!preparation.current && <small>Earlier brief</small>}
      </div>
      {preparation.detail && <p>{preparation.detail}</p>}
      {!preparation.current && (
        <p>This brief has changed. Its preparation will not continue.</p>
      )}
      {uncertain && preparation.status !== "uncertain" && (
        <p>
          The provider may have processed and charged for this request. Inspect
          the original run before requesting another generation.
        </p>
      )}
      {running && (
        <p>
          You can leave this chat. Progress is saved. A new message stops
          continuation of this brief.
        </p>
      )}
      {preparation.generation?.steps && (
        <ol className="preparation-steps">
          {preparation.generation.steps.map((step) => (
            <li key={step.capability}>
              <span>{stage(step.capability)}</span>
              <small>{taskLabels[step.status] ?? step.status}</small>
            </li>
          ))}
        </ol>
      )}
      <details>
        <summary>Inspect preparation</summary>
        <p>
          Preparation: <code>{preparation.id}</code>
        </p>
        <p>
          Planning run: <code>{preparation.run_id}</code>
        </p>
        {preparation.generation && (
          <p>
            Current run: <code>{preparation.generation.run_id}</code>
          </p>
        )}
        <p>
          Model copy permission:{" "}
          {preparation.inputs.allow_model_copy
            ? "Granted for this request"
            : "Not granted"}
        </p>
        {preparation.generation?.provider_error && (
          <p>Provider: {preparation.generation.provider_error}</p>
        )}
        {preparation.generation?.unresolved_calls?.map((call) => (
          <p key={call.key}>
            Unresolved call: <code>{call.key}</code> ({call.status})
          </p>
        ))}
        <p>Preparation grants no approval or delivery authority.</p>
      </details>
    </section>
  );
}
