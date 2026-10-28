import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ArrowUpRight,
  Check,
  Loader2,
  MessageSquare,
  Plus,
  Send,
} from "lucide-react";
import { command, MessageNotSavedError, money, read, replay } from "./api";
import type { State } from "./api";
import "./conversation.css";

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
};
type Conversation = {
  id: string;
  title: string;
  revision: number;
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
}: {
  onOpenCampaign: (state: State) => void;
  navigationTarget: HTMLElement | null;
  active: boolean;
  onNavigate: () => void;
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
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
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
      sessionStorage.removeItem(pendingMessageKey);
      setPendingMessage(null);
      accept(saved);
      setMessage("");
      setBusy("Planning with the agent");
      const planned = await command<Conversation>(
        `/api/conversations/${current.id}/plan`,
        { expected_revision: saved.revision },
      );
      await finishPlan(current.id, saved.revision, planned);
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
      const planned = await command<Conversation>(
        `/api/conversations/${current.id}/plan-fixture`,
        { expected_revision: saved.revision },
      );
      await finishPlan(current.id, saved.revision, planned);
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
            const generation = campaign?.generation;
            const terminal =
              generation &&
              (["failed", "cancelled"].includes(generation.status) ||
                generation.outcome_uncertain);
            return (
              <div className="conversation-turn" key={item.id}>
                <div className="conversation-user">
                  <span>You</span>
                  <p>{item.content}</p>
                </div>
                {plan && (
                  <div className="conversation-agent">
                    <div className="conversation-agent-label">
                      <span className="agent-dot">
                        <Check size={11} />
                      </span>
                      Direct Acquisition
                      {!plan.current && <small>Earlier proposal</small>}
                    </div>
                    {plan.status === "failed" ? (
                      <p>
                        Planning could not finish.{" "}
                        {plan.error?.provider_error === "provider_http_401"
                          ? "Check the OpenRouter key before starting a new request."
                          : "Review the request and send a new message to continue."}
                      </p>
                    ) : !plan.result ? (
                      <p>
                        Planning is {plan.status}. Resume this request to
                        continue.
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
                            onClick={() => openCampaign(campaign.session_id)}
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
                          plan.current && (
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
                          !terminal && (
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
                              : "Brief proposal. No campaign has been generated yet."}
                        </small>
                      </div>
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
          (!conversation.current_plan ||
            ["queued", "running", "admitted"].includes(
              conversation.current_plan.status,
            )) ? (
            <button
              className="text-button conversation-resume"
              onClick={resume}
            >
              Resume planning
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
          <p>
            {pendingMessage
              ? "The last message needs confirmation. Retry saving it before continuing."
              : "Sending uses OpenRouter for planning. Model copy requires a separate generation step."}
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
