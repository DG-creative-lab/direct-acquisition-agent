import { useRef, useState } from "react";
import { ChevronDown, KeyRound, X } from "lucide-react";
import { connectOpenRouter, openRouterRequest, read } from "./api";
import { openRouterSessionId } from "./openrouter-session";
import type { OpenRouterModel, OpenRouterSession } from "./openrouter-session";
import { Modal } from "./ui";
import "./openrouter.css";

export function OpenRouterSettings({
  session,
  onChange,
  onClose,
}: {
  session: OpenRouterSession | null;
  onChange: (value: OpenRouterSession | null) => void;
  onClose: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Modal label="openrouter-title" busy={busy} onClose={onClose}>
      <button
        className="modal-close icon-button openrouter-close"
        aria-label="Close OpenRouter settings"
        disabled={busy}
        onClick={onClose}
      >
        <X size={18} />
      </button>
      <span className="modal-icon">
        <KeyRound size={20} />
      </span>
      <h2 id="openrouter-title">OpenRouter</h2>
      <p>
        Connect your own OpenRouter key for chat. Paid model use is billed to
        your OpenRouter account.
      </p>
      <form
        className="openrouter-form"
        onSubmit={async (event) => {
          event.preventDefault();
          if (busy) return;
          const key = input.current?.value.trim();
          if (!key) return;
          setError("");
          setBusy(true);
          try {
            const next = await connectOpenRouter(
              key,
              openRouterSessionId(),
              session,
            );
            onChange(next);
            onClose();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label htmlFor="openrouter-key">
          {session ? "Replace API key" : "OpenRouter API key"}
        </label>
        <input
          ref={input}
          id="openrouter-key"
          type="password"
          autoComplete="off"
          spellCheck={false}
          maxLength={512}
          required
          disabled={busy}
        />
        <p>
          The workspace keeps your key in server memory while this tab is
          connected. Reconnect after a server restart or five minutes of
          inactivity.
        </p>
        <a
          href="https://openrouter.ai/settings/keys"
          target="_blank"
          rel="noopener noreferrer"
        >
          Get a key from OpenRouter
        </a>
        {error && (
          <p role="alert" className="openrouter-error">
            {error}
          </p>
        )}
        <div className="openrouter-form-actions">
          {session && (
            <button
              className="button secondary"
              type="button"
              disabled={busy}
              onClick={async () => {
                setError("");
                setBusy(true);
                try {
                  await openRouterRequest("disconnect", session);
                  onChange(null);
                  onClose();
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Remove key
            </button>
          )}
          <button className="button primary" type="submit" disabled={busy}>
            {busy ? "Checking key" : session ? "Update key" : "Connect key"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

const dollars = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 4,
});
const tiers = ["Free", "Lower cost", "Standard"] as const;
const ceilings = {
  Free: "$0.00 input · $0.00 output",
  "Lower cost": "$0.25 input · $0.50 output",
  Standard: "$1.00 input · $2.00 output",
};

export function ModelPicker({
  session,
  onSelect,
  onSettings,
}: {
  session: OpenRouterSession | null;
  onSelect: (model: OpenRouterModel) => void;
  onSettings: () => void;
}) {
  const details = useRef<HTMLDetailsElement>(null);
  const trigger = useRef<HTMLElement>(null);
  const [models, setModels] = useState<OpenRouterModel[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const load = async () => {
    if (loading) return;
    setLoading(true);
    setError("");
    try {
      const result = await read<{ models: OpenRouterModel[] }>(
        "/api/openrouter/models",
      );
      setModels(result.models);
    } catch (e) {
      setModels(null);
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
  const close = () => {
    if (details.current) details.current.open = false;
    trigger.current?.focus();
  };
  return (
    <details
      className="model-picker"
      ref={details}
      onToggle={(event) => {
        if (event.currentTarget.open && session) void load();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && details.current?.open) {
          event.preventDefault();
          close();
        }
      }}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget))
          event.currentTarget.open = false;
      }}
    >
      <summary
        ref={trigger}
        aria-label={`Chat model: ${session?.model?.name ?? (session ? "Choose model" : "Workspace default")}`}
      >
        <span>
          {session?.model?.name ??
            (session ? "Choose model" : "Workspace default")}
        </span>
        <ChevronDown size={14} />
      </summary>
      <div className="model-options">
        <h3>Chat model</h3>
        {!session ? (
          <>
            <p>Connect an OpenRouter key to choose a model for chat.</p>
            <button
              className="text-button"
              type="button"
              onClick={() => {
                close();
                onSettings();
              }}
            >
              Set up OpenRouter
            </button>
          </>
        ) : (
          <>
            <p>Popular models with tool calling. USD per million tokens.</p>
            {loading && <p role="status">Loading OpenRouter models…</p>}
            {error && (
              <>
                <p role="alert">{error}</p>
                <button className="text-button" type="button" onClick={load}>
                  Retry
                </button>
              </>
            )}
            {models?.length === 0 && (
              <p>No compatible models are available right now.</p>
            )}
            {tiers.map((tier) => {
              const group =
                models?.filter((model) => model.tier === tier) ?? [];
              return (
                group.length > 0 && (
                  <section key={tier} aria-label={tier}>
                    <h4>{tier}</h4>
                    <p>Ceilings {ceilings[tier]}</p>
                    {group.map((model) => (
                      <button
                        key={model.id}
                        type="button"
                        aria-pressed={
                          session.model?.id === model.id &&
                          session.model.tier === model.tier
                        }
                        disabled={loading}
                        onClick={() => {
                          try {
                            onSelect(model);
                            close();
                          } catch (e) {
                            setError((e as Error).message);
                          }
                        }}
                      >
                        <span>{model.name}</span>
                        <small>
                          {dollars.format(model.input)} input ·{" "}
                          {dollars.format(model.output)} output
                        </small>
                      </button>
                    ))}
                  </section>
                )
              );
            })}
          </>
        )}
      </div>
    </details>
  );
}
