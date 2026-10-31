# Campaign validation and review readiness

This is the second slice of [issue 25](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/25). It composes existing validators into a read-only report for the current exact campaign. It introduces no approval, dispatch or lending authority.

## Required machine checks

The `campaign-validation/v1` report has seven required checks:

1. Artifact, audience and context integrity, verified before the report is assembled.
2. The original run reached its review checkpoint.
3. The brief and conversation/follow-up provenance match the admitted source.
4. Evidence, policy and suppression epochs still match the subject.
5. The current product evidence is within its existing review window.
6. Audience selection, exclusions, randomized assignments and integer costs reproduce the exact draft and comply with current suppressions.
7. Copy satisfies the existing fixture or grounded-copy contract, including evidence relationships and the recorded paired semantic screen for generated copy.

The underlying population and copy rules are shared with the existing approval validator. Their domain owners still enforce the actual rules. The report does not infer separate successes from one aggregate boolean.

Every required result must be `passed`. A known domain rejection is `failed`; an unexpected validator failure is `unknown` with sanitized recovery guidance. Neither is ready. Omitting a required check or marking it optional is rejected by the report constructor. No report exists until a committed draft and review subject are available.

Artifact or context corruption that prevents safe bundle reconstruction still fails the existing read rather than exposing an apparently usable report or artifact. The client receives no ready result in that case.

## Honest evaluation limits

The recorded semantic screen is advisory. Offline fixtures explicitly show it as `not_evaluated`; generated copy can show `passed` only after the existing copy validator checks the paired verdict. A failed copy contract leaves semantic-screen validity `unknown` rather than fabricating a screening diagnosis.

Editorial suitability for the user's objective is `not_evaluated` by this machine gate and still requires human judgment. The source check verifies structural brief correspondence, supported segments and budget provenance, not general marketing quality. Real customer performance is `unknown`. These optional fields do not prevent presentation for human review, and they cannot be counted as successes.

## Binding and observation semantics

The report binds organization, subject, draft, audience snapshot, recorded brief and its conversation revision/plan or follow-up identity, current evidence/suppression epochs, product pack and policy IDs, frozen creative-context IDs, skill IDs and source versions/hashes. `evaluated_at` uses the campaign's clock. Its content hash includes the evaluation time.

Reports are read-time observations, not new durable authority records. Capture the returned JSON to retain an exact historical snapshot; this slice does not introduce a report-history store or database migration. A later read may produce a different report ID while the exact subject remains the same. Legacy artifacts retain their original interpretation; missing old skill annotations are represented by absent metadata rather than invented provenance.

All checks and the approval projection are read in one SQLite transaction. The workspace additionally checks that the meaningful review/report projection did not change while loading revision progress, ignoring only observation timestamps and their derived report ID. A changed state triggers the existing bounded read retry.

## Readiness versus approval

`candidate_valid` now follows `validation_report.review_ready`. The preparation coordinator requires both before announcing a new result as ready. Reading progress rechecks completed preparation against current validation, so a later amendment or suppression cannot keep advertising current readiness from an old coordinator receipt. This read projection does not restart or mutate preparation.

The React review panel shows the required-check count and an expandable full snapshot. Approval is unavailable when the report is missing or not ready. Blocked campaigns can still be inspected to understand their failures; they are not labelled ready.

Approval, revocation and simulated acceptance continue to use the original exact-subject contracts and fresh transactional validation. They do not accept a report ID, report JSON, client checkbox or historical `passed` value as authorization. A valid report creates no decision. Later suppression, evidence changes, reviewer changes or expiry can prevent acceptance even if a saved report was valid.

Accepted simulator receipts remain historical. A blocked current report does not undo or rewrite accepted history or counted outcomes.

## Verification scope

Real SQLite cases cover an exact fixture report without side effects, model-context and screen provenance, stale suppressions and evidence, unavailable validators, failed/unknown/not-evaluated required checks, omitted/downgraded checks, restart observations and conversation-amendment invalidation. The real-backend browser case inspects the report at desktop/mobile widths, imports an actual suppression and verifies that refreshed readiness and approval controls become blocked. Existing approval, replay and concurrent-read regressions remain required.

Mutation probes remove the readiness gate and required-check coverage. These tests establish bounded control behavior, not live model or marketing quality.

Verified for this slice: 288 backend tests, 52 browser tests, all 56 declared mutation checks, architecture, production build/formatting and whitespace checks passed. The expanded validation view was checked at 1440px, 390px and 320px widths without document-level horizontal overflow. No paid model call was made.

The final mobile grid-span correction was followed by a fresh production build, formatting check and the real-backend responsive validation journey. That journey also asserts a usable panel width at the smallest breakpoint, so fitting the document without overflow cannot hide a half-width report.
