import { useEffect, useRef, useState } from "react";
import { command, read } from "./api";

export type Execution = {
  accounting_complete?: boolean;
  account_unresolved?: boolean;
  unresolved_runs?: string[];
  recovery_scopes?: { organization: string; run_id: string }[];
  status: string;
  limit: number | null;
  used: number;
  remaining: number | null;
  stopped: boolean;
  pending_receipts: number;
  counts: {
    in_progress: number;
    uncertain: number;
    completed: number;
    rejected: number;
  };
  reported_cost_usd: string;
  cost_complete: boolean;
};

export default function ConversationExecution<T>({
  id,
  revision,
  execution,
  active,
  onChanged,
}: {
  id: string;
  revision: number;
  execution: Execution;
  active: boolean;
  onChanged: (value: T) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const recoveryScopes = execution.recovery_scopes ?? [];
  const ancestryUnresolved = recoveryScopes.length > 0;
  const epoch = useRef(0);
  useEffect(() => {
    epoch.current++;
    return () => {
      epoch.current++;
    };
  }, [id, revision]);
  const stop = async () => {
    const stamp = epoch.current;
    setBusy(true);
    setError("");
    try {
      const value = await command<T>(`/api/conversations/${id}/stop`, {
        expected_revision: revision,
      });
      if (stamp === epoch.current) onChanged(value);
    } catch (e) {
      if (stamp !== epoch.current) return;
      setError((e as Error).message);
      try {
        const value = await read<T>(`/api/conversations/${id}`);
        if (stamp === epoch.current) onChanged(value);
      } catch {
        /* Preserve original stop identity for explicit retry. */
      }
    } finally {
      if (stamp === epoch.current) setBusy(false);
    }
  };
  return (
    <section className="conversation-execution" aria-label="Execution controls">
      <div className="execution-summary">
        <p role="status">
          <strong>
            {execution.stopped
              ? "Work stopped"
              : execution.accounting_complete === false
                ? "Model-call allowance unknown"
                : execution.remaining === 0
                  ? "Model-call allowance exhausted"
                  : "Model-call allowance"}
          </strong>
          <span>
            {execution.accounting_complete === false ? (
              <>
                {execution.used} known calls reserved · remaining allowance
                unknown
              </>
            ) : (
              <>
                {execution.used} of {execution.limit} calls reserved ·{" "}
                {execution.remaining} remaining
              </>
            )}
          </span>
        </p>
        {active &&
          !execution.stopped &&
          !execution.account_unresolved &&
          revision > 0 && (
            <button className="button secondary" onClick={stop} disabled={busy}>
              {busy ? "Stopping…" : "Stop work"}
            </button>
          )}
      </div>
      {execution.stopped && !execution.account_unresolved && (
        <p>
          Send a new brief to start new work. The shared allowance does not
          reset. Existing campaign history and approvals are preserved.
        </p>
      )}
      {execution.account_unresolved && (
        <p>
          The execution account, run links, or stop history needs recovery. Ask
          a local operator to reconcile the records before continuing.
        </p>
      )}
      {ancestryUnresolved && (
        <p>
          Historical campaign ancestry needs recovery. Model calls are paused
          and usage is incomplete until a local operator restores the original
          relationship or explicitly reconciles an independent legacy run.
        </p>
      )}
      {execution.counts.uncertain > 0 && (
        <p>
          Some provider outcomes are uncertain and may have been charged.
          Inspect the original calls before requesting more generation.
        </p>
      )}
      {execution.pending_receipts > 0 && (
        <p>
          A dispatched request may still return after stopping. Its receipt will
          be recorded; stopping does not undo provider charges.
        </p>
      )}
      <details>
        <summary>Inspect model usage</summary>
        {ancestryUnresolved && (
          <div>
            <p>
              Operator recovery: use <code>execution-unresolved</code> to
              inspect the runs below. After verifying a run is independent, use{" "}
              <code>execution-resolve-independent</code> with its exact
              fingerprint and a reason. See{" "}
              <code>docs/execution-controls.md</code> for the commands and
              database selection. This does not approve a campaign.
            </p>
            <ul>
              {recoveryScopes.map((scope) => (
                <li key={scope.run_id}>
                  Organization: <code>{scope.organization}</code>; run:{" "}
                  <code>{scope.run_id}</code>
                </li>
              ))}
            </ul>
          </div>
        )}
        <p>
          {execution.counts.completed} completed · {execution.counts.rejected}{" "}
          rejected · {execution.counts.in_progress} in progress ·{" "}
          {execution.counts.uncertain} uncertain
        </p>
        <p>
          Provider-reported cost: ${execution.reported_cost_usd}
          {execution.cost_complete ? "" : " (incomplete)"}. This is not a
          verified bill. Every reservation consumes the allowance; replay does
          not consume another call. Existing generation consent and per-run
          limits still apply.
        </p>
        <pre>{JSON.stringify(execution, null, 2)}</pre>
      </details>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
