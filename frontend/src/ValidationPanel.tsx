import type { ValidationReport } from "./api";
import { date } from "./api";
import "./validation.css";

const labels = {
  passed: "Passed",
  failed: "Failed",
  unknown: "Unknown",
  not_evaluated: "Not evaluated",
};

export default function ValidationPanel({
  report,
}: {
  report: ValidationReport;
}) {
  if (!report)
    return (
      <p role="alert">Validation is unavailable. Refresh before reviewing.</p>
    );
  const passed = report.checks.filter(
    (check) => check.required && check.status === "passed",
  ).length;
  const required = report.checks.filter((check) => check.required).length;
  return (
    <section className="validation-report" aria-label="Campaign validation">
      <strong>
        {report.review_ready
          ? "Checks passed for review"
          : "Validation needs attention"}
      </strong>
      <p>
        {passed} of {required} required checks passed. Human approval is
        separate.
      </p>
      <details className="chat-campaign-detail">
        <summary>Inspect campaign validation</summary>
        <p>
          Evaluated {date(report.evaluated_at)} using this campaign's clock.
        </p>
        <ul className="validation-checks">
          {report.checks.map((check) => (
            <li key={check.id}>
              <strong>
                {check.label}: {labels[check.status]}
              </strong>
              <p>
                {check.detail}{" "}
                {check.required
                  ? "Required for readiness."
                  : "Outside the readiness gate."}
              </p>
            </li>
          ))}
        </ul>
        <details>
          <summary>Complete validation snapshot</summary>
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {JSON.stringify(report, null, 2)}
          </pre>
        </details>
      </details>
    </section>
  );
}
