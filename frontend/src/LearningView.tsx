import { useState } from "react";
import {
  ArrowRight,
  BarChart3,
  Clock3,
  FlaskConical,
  ShieldCheck,
} from "lucide-react";
import type { Act, State } from "./api";
import { date, percent } from "./api";
import { Badge, Empty, segmentName } from "./ui";
import MonitoringControls from "./MonitoringControls";

export default function LearningView({
  state,
  busy,
  act,
  onCampaign,
  onNext,
  monitoringAct = act,
  monitoringError,
}: {
  state: State;
  busy: boolean;
  act: Act;
  onCampaign: () => void;
  onNext?: () => void;
  monitoringAct?: Act;
  monitoringError?: string;
}) {
  const [monitoringPending, setMonitoringPending] = useState(false);
  const learningBusy = busy || monitoringPending;
  const learning = state.learning;
  if (!state.review?.handoff)
    return (
      <Empty icon={BarChart3} title="Learning starts after acceptance">
        <p>
          Review this campaign and complete its simulated handoff before opening
          an outcome window.
        </p>
        <button className="button secondary" onClick={onCampaign}>
          Return to campaign
          <ArrowRight size={15} />
        </button>
      </Empty>
    );
  if (!learning)
    return (
      <Empty icon={FlaskConical} title="Open the response window">
        <p>
          Track every assigned business, including no-mail controls. Missing
          results stay pending until all explicit outcomes arrive.
        </p>
        <button
          className="button primary"
          disabled={busy}
          onClick={() => act("open-learning")}
        >
          Open outcome window
          <ArrowRight size={15} />
        </button>
        <p className="small-print">
          The next steps simulate elapsed time and outcomes inside this sandbox.
        </p>
      </Empty>
    );
  const complete = learning.status === "finalized";
  const monitoring = learning.monitoring;
  const binding = {
    handoff_id: state.review.handoff.id,
    cohort_id: learning.cohort.id,
  };
  return (
    <section className="learning-workspace">
      <div className="learning-window">
        <div>
          <span className="eyebrow">28-DAY OBSERVATION WINDOW</span>
          <h3>
            {complete
              ? "A complete cohort. Counted once."
              : learning.received
                ? monitoring
                  ? "Recorded outcomes received"
                  : "Early responses received"
                : "Waiting for response evidence"}
          </h3>
          <p>
            {date(learning.cohort.window_start)} to{" "}
            {date(learning.cohort.window_end)}
          </p>
        </div>
        <Badge tone={complete ? "green" : "amber"}>
          {complete ? "Finalized" : "Pending evidence"}
        </Badge>
      </div>
      <div className="learning-metrics">
        {[
          { label: "Enrolled businesses", value: learning.enrolled },
          { label: "Explicit outcomes", value: learning.received },
          { label: "Pending results", value: learning.missing },
        ].map((m) => (
          <div key={m.label}>
            <span>{m.label}</span>
            <strong>{m.value}</strong>
          </div>
        ))}
      </div>
      <MonitoringControls
        key={state.session.id + learning.cohort.id}
        state={state}
        busy={busy}
        act={monitoringAct}
        requestError={monitoringError}
        onPendingChange={setMonitoringPending}
      />
      {monitoring && (
        <section
          className="observation-actions"
          aria-label="Recorded report monitoring"
        >
          <div>
            <Clock3 size={19} />
            <span>
              Recorded report monitoring
              <strong>
                {monitoring.position} of {monitoring.report_count} synthetic
                reports checked
              </strong>
              {monitoring.last_checked !== null && (
                <small>Last check {date(monitoring.last_checked)} UTC</small>
              )}
              {monitoring.watermark !== null && (
                <small>
                  Reports verified through {date(monitoring.watermark)} UTC
                </small>
              )}
              {monitoring.status === "scheduled" &&
                monitoring.next_due !== null && (
                  <small>Next check {date(monitoring.next_due)} UTC</small>
                )}
              {monitoring.status === "blocked" && (
                <small>Blocked. {monitoring.detail}</small>
              )}
              {monitoring.status === "paused" && <small>Paused</small>}
              {monitoring.status === "complete" && (
                <small>All scheduled reports checked</small>
              )}
            </span>
          </div>
          {state.session.mode === "fixture" &&
            monitoring.status === "scheduled" &&
            monitoring.next_due !== null && (
              <button
                className="button secondary"
                disabled={learningBusy}
                onClick={() =>
                  act("advance-report-check", {
                    ...binding,
                    position: monitoring.position,
                    next_due: monitoring.next_due,
                  })
                }
              >
                Advance to next report check
              </button>
            )}
          {!complete && monitoring.status === "complete" && (
            <button
              className="button primary"
              disabled={
                learningBusy ||
                learning.missing > 0 ||
                state.session.clock < learning.cohort.window_end
              }
              onClick={() => act("finalize-report-learning", binding)}
            >
              Finalize recorded learning
            </button>
          )}
        </section>
      )}
      {!complete && !monitoring && (
        <div className="observation-actions">
          <div>
            <Clock3 size={19} />
            <span>
              Simulation controls
              <strong>Advance only this campaign's sandbox clock.</strong>
            </span>
          </div>
          <button
            className="button secondary"
            disabled={learningBusy || learning.received > 0}
            onClick={() => act("observe")}
          >
            Simulate day 7 responses
          </button>
          <button
            className="button primary"
            disabled={learningBusy}
            onClick={() => act("finalize")}
          >
            Close window & learn
            <ArrowRight size={15} />
          </button>
        </div>
      )}
      <div className="learning-columns">
        <section>
          <div className="section-title">
            <div>
              <h3>Response beliefs</h3>
              <p>
                Beta(1,19) starting prior. Exact counts, with estimated 90%
                posterior intervals.
              </p>
            </div>
            <Badge>{learning.beliefs.length} groups</Badge>
          </div>
          {complete ? (
            <div className="table-scroll">
              <table className="belief-table">
                <thead>
                  <tr>
                    <th>Audience / variant</th>
                    <th>Responses</th>
                    <th>Posterior mean</th>
                    <th>90% interval</th>
                  </tr>
                </thead>
                <tbody>
                  {learning.beliefs.map((g) => {
                    const interval = learning.recommendations.find(
                      (r) => r.segment === g.segment,
                    )?.response_intervals_90?.[g.arm];
                    return (
                      <tr key={g.segment + g.arm}>
                        <td>
                          <strong>
                            {g.segment === "inventory"
                              ? "Inventory"
                              : "Contractors"}
                          </strong>
                          <small>
                            {g.arm === "no_mail"
                              ? "No-mail control"
                              : `Variant ${g.arm}`}
                          </small>
                        </td>
                        <td>
                          {g.successes} / {g.trials}
                        </td>
                        <td>
                          <strong>{percent(g.mean)}</strong>
                        </td>
                        <td>
                          {interval ? (
                            <>
                              <div className="interval-track">
                                <span
                                  style={{
                                    left: `${interval[0] * 200}%`,
                                    width: `${Math.max(1, (interval[1] - interval[0]) * 200)}%`,
                                  }}
                                />
                                <i style={{ left: `${g.mean * 200}%` }} />
                              </div>
                              <small>
                                {percent(interval[0])} to {percent(interval[1])}
                              </small>
                            </>
                          ) : (
                            "Unavailable"
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="chart-note">
                Interval scale: 0% to 50%. Values above 50% extend beyond the
                scale.
              </p>
            </div>
          ) : (
            <div className="pending-beliefs">
              <Clock3 size={24} />
              <h4>Beliefs are unchanged</h4>
              <p>
                The observation window must close and every enrolled business
                needs an explicit result. Absence is not a non-response.
              </p>
            </div>
          )}
        </section>
        <aside className="recommendation-panel">
          <span className="recommendation-icon">
            <BarChart3 size={21} />
          </span>
          <h3>Next experiment</h3>
          <p className="recommendation-intro">
            Recommendations are advisory. A new campaign still needs its own
            review.
          </p>
          {complete ? (
            learning.recommendations.map((r) => (
              <article key={r.segment}>
                <span className="eyebrow">{segmentName(r.segment)}</span>
                <h4>
                  {r.action === "propose_next_experiment"
                    ? `Explore variant ${r.candidate_arm} again`
                    : "Collect more evidence"}
                </h4>
                <p>{r.reason}</p>
                {r.lift_mean !== undefined && (
                  <>
                    <strong className="lift">
                      {r.lift_mean >= 0 ? "+" : ""}
                      {(r.lift_mean * 100).toFixed(1)}
                      <small>percentage points</small>
                    </strong>
                    <p className="small-print">
                      Estimated response lift over this cohort's control. 90%
                      interval:{" "}
                      {r.lift_interval_90
                        ?.map((n) => (n * 100).toFixed(1))
                        .join(" to ")}{" "}
                      points.
                    </p>
                  </>
                )}
              </article>
            ))
          ) : (
            <p className="no-recommendation">
              No recommendation while evidence is pending.
            </p>
          )}
          <div className="policy-note">
            <ShieldCheck size={15} />
            <span>
              10,000 seeded posterior draws. Illustrative prior and thresholds,
              without calibrated production claims.
            </span>
          </div>
        </aside>
      </div>
      {complete && onNext && (
        <button className="button primary" disabled={busy} onClick={onNext}>
          Prepare a next experiment
          <ArrowRight size={15} />
        </button>
      )}
      <div className="learning-limitations">
        <FlaskConical size={18} />
        <div>
          <strong>Synthetic outcomes. No measured customer performance.</strong>
          <p>
            {monitoring
              ? "Recorded reports contain synthetic outcomes for this cohort."
              : "Labels deliberately favor variant A to demonstrate learning."}{" "}
            Simulated acceptance does not establish delivery. Repeated business
            exposure and corrections require further modelling.
          </p>
        </div>
      </div>
    </section>
  );
}
