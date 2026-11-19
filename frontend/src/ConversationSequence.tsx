import { useEffect, useId, useRef, useState } from "react";
import { command, money, read } from "./api";

export type SequenceJourney = {
  id: string;
  revision: number;
  current: boolean;
  status: string;
  stage: number;
  detail: string | null;
  profile_key: string;
  pending_task_steps: string[];
  pending_reply_steps: string[];
  source: null | { label: string; key: string; version: number };
  interpretation: {
    question: string;
    reason: string;
    budget_pence: number | null;
  };
  outputs: { subject_id?: string };
  audience?: {
    current: {
      declared_contacts: number;
      eligible: string[];
      rows: { contact_id: string; reasons: string[] }[];
    };
  };
  review: null | {
    subject_id: string;
    approval_valid: boolean;
    validation: {
      review_ready: boolean;
      checks: { id: string; status: string }[];
    };
    summary: null | {
      counts: {
        enrolled: number;
        treatment: number;
        controls: number;
        email_steps: number;
        call_tasks: number;
      };
      limits: { budget_pence: number; maximum_cost_pence: number };
      schedule: { starts_at: number; expires_at: number };
    };
    sequence: null | {
      population: {
        contact_id: string;
        arm: string;
        segment: string;
        steps: {
          stage: string;
          channel: string;
          due_at: number;
          assignee: string | null;
          content: {
            rendered: {
              recipient_facts: {
                wording: string;
                fact_id: string;
                review_id: string;
              }[];
              email?: { to: string; subject: string; text: string };
              call?: {
                contact: string;
                introduction: string;
                relevance: string[];
                discovery: string[];
                objections: string[];
                next_steps: string[];
                do_not_contact: string;
              };
            };
          };
        }[];
      }[];
    };
  };
  simulation: null | {
    status: string;
    observations: { step_id: string; kind: string }[];
    steps: {
      id: string;
      channel: string;
      status: string;
      assignee?: string;
      submission: null | { status: string };
    }[];
  };
};

const date = (seconds: number) => new Date(seconds * 1000).toLocaleString();
const statuses: Record<string, string> = {
  preparing: "Preparing your sequence",
  ready: "Ready for your review",
  approving: "Saving exact approval",
  approved: "Approved for synthetic simulation",
  simulating: "Simulating the approved sequence",
  awaiting_human: "Human call tasks need your observation",
  complete: "Synthetic simulation complete",
  clarification: "One detail needed",
  unsupported: "Requested scope is unavailable",
  consent_required: "Generation consent needed",
  cancelled: "Sequence stopped",
  historical: "Earlier sequence",
  blocked: "Sequence needs attention",
};

export default function ConversationSequence<T>({
  journey,
  conversationId,
  disabled,
  onChanged,
}: {
  journey: SequenceJourney;
  conversationId: string;
  disabled: boolean;
  onChanged: (value: T) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const titleId = useId();
  const [confirmation, setConfirmation] = useState<{
    journey_id: string;
    expected_revision: number;
    subject_id: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ready =
    journey.current &&
    journey.status === "ready" &&
    journey.review?.validation.review_ready === true;
  const exact =
    ready &&
    confirmation?.journey_id === journey.id &&
    confirmation.expected_revision === journey.revision &&
    confirmation.subject_id === journey.review?.subject_id;
  const summary = journey.review?.summary;
  const population = journey.review?.sequence?.population ?? [];
  const contextual = population.filter((p) =>
    p.steps.some((s) => s.content.rendered.recipient_facts.length > 0),
  ).length;
  const selectedContacts = new Set(population.map((p) => p.contact_id));
  const omittedEligible =
    journey.audience?.current.eligible.filter((id) => !selectedContacts.has(id))
      .length ?? 0;
  const act = async (kind: string, payload: Record<string, unknown>) => {
    setBusy(true);
    setError("");
    try {
      const result = await command<T>(
        `/api/conversations/${conversationId}/${kind}`,
        payload,
        null,
      );
      if (mounted.current) {
        dialog.current?.close();
        onChanged(result);
      }
    } catch (e) {
      if (mounted.current) {
        setError((e as Error).message);
        try {
          const current = await read<T>(`/api/conversations/${conversationId}`);
          if (mounted.current) onChanged(current);
        } catch {
          // Preserve the pending command identity for retry or reload.
        }
      }
    } finally {
      if (mounted.current) setBusy(false);
    }
  };
  const scope = { journey_id: journey.id, expected_revision: journey.revision };
  const completed = new Set(
    journey.simulation?.observations
      .filter((o) => o.kind === "task_completed")
      .map((o) => o.step_id),
  );
  const waiting =
    journey.simulation?.steps.filter(
      (s) =>
        s.channel === "human_call" &&
        s.status === "accepted" &&
        !completed.has(s.id) &&
        !journey.pending_task_steps.includes(s.id),
    ) ?? [];
  const replied = new Set(
    journey.simulation?.observations
      .filter((observation) => observation.kind === "replied")
      .map((observation) => observation.step_id),
  );
  const replyTargets =
    journey.simulation?.steps.filter(
      (step) =>
        step.channel === "email" &&
        step.submission?.status === "accepted" &&
        !replied.has(step.id) &&
        !journey.pending_reply_steps.includes(step.id),
    ) ?? [];
  return (
    <section className="conversation-agent sequence-proposal">
      <p className="sequence-eyebrow">
        Synthetic email and human call sequence ·{" "}
        {journey.profile_key || "Company unresolved"}
      </p>
      <h3>
        {journey.status === "ready" && !journey.review?.validation.review_ready
          ? "Sequence needs current validation"
          : (statuses[journey.status] ?? "Sequence status unavailable")}
      </h3>
      {journey.source && (
        <p>
          {journey.source.label} · UK response experiment · account allocation
          with A/B/no-contact assignment.
        </p>
      )}
      {journey.detail && <p>{journey.detail}</p>}
      {!journey.current && (
        <p>
          This revision is historical. Send a new objective to prepare a current
          proposal.
        </p>
      )}
      {journey.status === "preparing" && (
        <p role="status">
          I am checking source permissions, selecting accounts, preparing
          reviewed context and validating personalized content. Step{" "}
          {journey.stage + 1} of 7.
        </p>
      )}
      {summary && (
        <>
          <p>
            {summary.counts.enrolled} accounts: {summary.counts.treatment} in
            treatment and {summary.counts.controls} in the no-contact control.
            Approval permits at most {summary.counts.email_steps} synthetic
            emails and {summary.counts.call_tasks} human call tasks.
          </p>
          <p>
            Estimated maximum {money(summary.limits.maximum_cost_pence)} against
            your {money(summary.limits.budget_pence)} budget. Generation uses at
            most 15 offline model calls and costs $0.
          </p>
          <p>
            Initial email at the start; call task on day 1 or 2; follow-up on
            day 3 or 4, subject to recorded task completion and stop conditions.
            The agent advances a persisted synthetic clock. Valid{" "}
            {date(summary.schedule.starts_at)} to{" "}
            {date(summary.schedule.expires_at)}.
          </p>
        </>
      )}
      {summary && (
        <p>
          Reviewed personal context covers {contextual} of{" "}
          {summary.counts.treatment} treatment contacts. {omittedEligible} other
          eligible contacts are omitted by account allocation. Inspect the exact
          evidence and any gaps below.
        </p>
      )}
      {journey.audience && (
        <p>
          Evidence covers {journey.audience.current.declared_contacts} source
          contacts; {journey.audience.current.eligible.length} are eligible for
          email preparation. Account selection keeps one contact per account.
          Excluded contacts:{" "}
          {journey.audience.current.rows
            .filter((r) => r.reasons.length)
            .map((r) => `${r.contact_id}: ${r.reasons.join(", ")}`)
            .join("; ") || "none at the permission check"}
          .
        </p>
      )}
      {journey.review && !journey.review.validation.review_ready && (
        <p role="status">
          Current validation is incomplete or stale. Content and approval are
          withheld.
        </p>
      )}
      <p>
        No live delivery or autonomous voice. Call completion is an explicit
        human observation; recipient replies are never invented. Recorded
        semantic screening does not grant approval.
      </p>
      {journey.review?.sequence && (
        <details>
          <summary>Inspect exact recipients, copy and evidence</summary>
          <p>
            Subject: <code>{journey.review.subject_id}</code> · Revision{" "}
            {journey.revision}
          </p>
          <ul>
            {journey.review.validation.checks.map((c) => (
              <li key={c.id}>
                {c.id.replaceAll("_", " ")}: {c.status}
              </li>
            ))}
          </ul>
          {journey.review.sequence.population.map((person) => (
            <article key={person.contact_id} className="sequence-recipient">
              <h4>
                {person.segment} · Arm {person.arm}
              </h4>
              <p>
                <code>{person.contact_id}</code>
              </p>
              {person.steps.map((step) => (
                <details key={step.stage}>
                  <summary>
                    {step.stage.replaceAll("_", " ")} · {date(step.due_at)}
                  </summary>
                  {step.content.rendered.email && (
                    <>
                      <p>To: {step.content.rendered.email.to}</p>
                      <p>Subject: {step.content.rendered.email.subject}</p>
                      <pre>{step.content.rendered.email.text}</pre>
                    </>
                  )}
                  {step.content.rendered.call && (
                    <>
                      <p>
                        Assigned to {step.assignee}.{" "}
                        {step.content.rendered.call.contact}
                      </p>
                      <p>{step.content.rendered.call.introduction}</p>
                      <ul>
                        {[
                          ...step.content.rendered.call.relevance,
                          ...step.content.rendered.call.discovery,
                          ...step.content.rendered.call.objections,
                          ...step.content.rendered.call.next_steps,
                        ].map((line, i) => (
                          <li key={i}>{line}</li>
                        ))}
                      </ul>
                      <p>{step.content.rendered.call.do_not_contact}</p>
                    </>
                  )}
                  <ul>
                    {step.content.rendered.recipient_facts.map((f) => (
                      <li key={f.fact_id}>
                        {f.wording} <code>{f.fact_id}</code> · Review{" "}
                        {f.review_id}
                      </li>
                    ))}
                  </ul>
                </details>
              ))}
            </article>
          ))}
        </details>
      )}
      {ready && (
        <button
          type="button"
          className="primary"
          disabled={disabled || busy}
          onClick={() => {
            setConfirmation({
              ...scope,
              subject_id: journey.review!.subject_id,
            });
            dialog.current?.showModal();
          }}
        >
          Review and approve simulation
        </button>
      )}
      {journey.current &&
        !["complete", "cancelled", "unsupported", "clarification"].includes(
          journey.status,
        ) && (
          <button
            type="button"
            className="text-button"
            disabled={disabled || busy}
            onClick={() => void act("sequence-stop", scope)}
          >
            Stop this sequence
          </button>
        )}
      {journey.current &&
        ["simulating", "awaiting_human", "complete"].includes(journey.status) &&
        replyTargets.map((step, index) => (
          <div key={step.id}>
            <p>
              Synthetic email {index + 1}: <code>{step.id}</code>
            </p>
            <button
              type="button"
              disabled={disabled || busy}
              onClick={() =>
                void act("sequence-replied", { ...scope, step_id: step.id })
              }
            >
              Record synthetic reply to email {index + 1}
            </button>
          </div>
        ))}
      {journey.simulation?.observations.some(
        (observation) => observation.kind === "replied",
      ) && (
        <p>
          A synthetic reply was recorded. Pending steps for that account are
          paused.
        </p>
      )}
      {journey.current &&
        waiting.map((step, index) => (
          <div key={step.id}>
            <p>
              Synthetic human call task {index + 1}: <code>{step.id}</code>
            </p>
            <button
              type="button"
              disabled={disabled || busy}
              onClick={() =>
                void act("sequence-task-completed", {
                  ...scope,
                  step_id: step.id,
                })
              }
            >
              Record synthetic task {index + 1} completed
            </button>
          </div>
        ))}
      {error && (
        <p role="alert" className="conversation-error">
          {error}
        </p>
      )}
      <dialog
        ref={dialog}
        aria-labelledby={titleId}
        className="sequence-confirmation"
      >
        <h2 id={titleId}>Approve this exact synthetic sequence?</h2>
        <p>
          This authorizes the displayed recipients, copy, account controls,
          costs and schedule for bounded simulation. The agent continues
          automatically. Human call tasks still require an explicit completion
          observation.
        </p>
        <p>
          Revision {confirmation?.expected_revision} ·{" "}
          <code>{confirmation?.subject_id}</code>
        </p>
        {!exact && (
          <p role="alert">
            This confirmation is stale. Cancel and inspect the current proposal.
          </p>
        )}
        {error && <p role="alert">{error}</p>}
        <form method="dialog">
          <button autoFocus disabled={busy}>
            Cancel
          </button>
        </form>
        <button
          type="button"
          className="primary"
          disabled={!exact || disabled || busy}
          onClick={() =>
            confirmation &&
            void act("sequence-approve", {
              ...confirmation,
              reason:
                "Exact displayed synthetic sequence reviewed by the local user.",
            })
          }
        >
          {busy ? "Saving approval…" : "Approve and simulate"}
        </button>
      </dialog>
    </section>
  );
}
