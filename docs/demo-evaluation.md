# Demo and offline evaluation

This first evaluation pass follows issue [23](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/23). It exercises synthetic campaign controls without provider inference. It does not score a model's reasoning or editorial quality.

## Repeatable evidence

```sh
make evaluate-offline
```

Each invocation creates a new directory under `.local/offline-evaluation/`. It preserves the workspace databases, supplied brief corpus, assignment CSV, manifest, acceptance receipt, initial campaign, finalized learning, follow-up proposal and child campaign. `report.json` lists individual checks and returns a failed overall result if an assertion or unexpected exception stops the run. The command exits nonzero on failure. An aborted run has partial coverage; the number of recorded checks is not a completeness score. Existing runs are never overwritten.

The full successful scenario contains 37 checks. The eight brief cases test explicit, missing, corrected, stale, relative, unsupported-suffix, foreign-currency and ambiguous budgets. Invalid budget candidates must fail, and a supplied clarification must carry no approval. These are deterministic candidate-validation cases. There is no natural-language model interpretation in this corpus.

The lifecycle uses the fixed contractor fixture: £600 budget, 85p per mailed business, 342 mailed businesses and 37 controls. Exported CSV rows provide the independent count and cost oracle. The journey checks absent initial approval, rejected unauthorized handoff, exact simulated acceptance, replay, pending outcomes, complete finalization, a fresh decision for the exact child subject, current approval authority and its persistence after reopening, disjoint enrollment, unchanged parent learning and receipt survival across a fresh interpreter and a later brief edit. The follow-up in the recorded scenario has 355 mailing recipients and 39 controls at £301.75.

Provider construction and ordinary Python socket connection are forbidden in the evaluation process. The fresh read-only interpreter also forbids socket connection. Fixture preparation makes no model requests. The fixed clock is 26 October 2026 at 00:00 UTC; the offline campaign itself uses the fact pack's fixture clock, and synthetic learning explicitly advances its sandbox to maturity. These clocks are not live wall-clock operations.

## Browser walkthrough

Start a fresh root so the demo does not reuse someone else's history:

```sh
make workspace WORKSPACE_PORT=8782 WORKSPACE_ROOT=.local/demo-evaluation-browser
```

1. Choose **Try the offline example**. Wait for **Ready for your review** and open **Review campaign**.
2. Inspect A/B fixtures, audience exclusions, the £600 cap, £290.70 mailing estimate and current product evidence. Fixtures demonstrate controls and layout; they are not a sample of generated marketing copy.
3. Choose **Approve this revision**, enter a review reason and record approval. Then **Simulate agency handoff** and confirm the exact revision. Acceptance is simulated and sends no mail.
4. Open the outcome window and confirm. All 379 assigned businesses start with unknown outcomes. Optionally simulate day 7; beliefs remain unchanged until full mature results exist.
5. Choose **Close window & learn** and confirm the synthetic clock advance and explicit results. Inspect A, B and no-mail denominators. Synthetic labels deliberately favor A.
6. Choose **Propose follow-up experiment**, inspect its frozen source and cost, then **Prepare offline follow-up**. The child has a new subject and requires its own approval. Keep model consent unchecked throughout this offline walkthrough.
7. Approve the exact child revision with its own review reason. Confirm that approval is recorded and that this does not itself accept a handoff. Reload, select **Offline example** from saved conversations, and choose **Inspect or resume follow-up**. Inspect the retained campaign without creating another run. Repeat the visual check at desktop and mobile widths.

Targeted copy rewriting is available only for grounded model campaigns. A free-text budget correction can be persisted, but planning it uses the model path. The offline fixture button is a fixed scenario, not a free-text agent. Those model behaviors need a separate evaluation with explicit inference permission and a current product fact pack.

## Evidence and usability observations

Observed on 31 October 2026 using the loopback preview and real browser interactions:

- Preparation, exact review, simulated acceptance, complete synthetic learning and follow-up preparation are reachable in one chat.
- The read-only planning explanation and preparation banner remain visible above the campaign. After acceptance they still say the draft is unapproved. This creates contradictory status language even though the review and acceptance panels show saved acceptance. A later UI pass should label preparation as historical or derive current campaign status.
- Fixture approval expiry can appear earlier than today's date. The underlying sandbox clock is deliberate, but the review panel should identify that clock near the date to prevent confusion.
- Finalized learning still instructs users to use the campaign workspace for a next experiment, directly above the in-chat follow-up action. That instruction should point to the new conversational action.
- Reload preserves the conversation and child, but returns to an empty composer. Reopening the saved conversation and choosing **Inspect or resume follow-up** restores the child review. Consider restoring the active conversation explicitly.
- A prepared child reports **Saved preparation: waiting** at the runtime review checkpoint. The label should explain that it is waiting for human review, rather than suggesting generation is unfinished.
- The accumulated review, receipt, learning and child review make the conversation long. Evaluate collapsing completed stages while preserving access to their exact historical artifacts.

These are maintainer observations, not a user study or measured task-completion rate. Functional browser regressions and visual inspection are separate evidence. Live brief interpretation, grounded rewrite quality, unsupported-claim detection accuracy, accessibility beyond the exercised controls, real audiences and production concurrency remain unproven by this pass.

## Verification for this pass

- Offline scenario: 37/37 checks passed.
- Backend suite: 268 tests passed. This was the initial pass; the child approval review fix is verified separately below.
- Existing browser suite: 51 tests passed, including responsive, lost-response and follow-up journeys. Production build and formatting checks passed.
- Architecture and whitespace checks passed.
- Interactive browser observation exercised the offline conversation through follow-up review and reload. DOM measurements showed equal document/client widths at mobile and desktop sizes. The browser suite also checked 320px and 390px breakpoints.
- No paid inference was executed. No real audience or delivery integration was exercised.

## Authority and evidence map

| Protected outcome | Independent oracle | Exercised boundary |
| --- | --- | --- |
| No invented budget | Literal expected outcomes in the supplied corpus | Candidate validation |
| Population and cost conservation | Exported CSV membership and fixed 85p cost | Prepared campaign |
| No release without a fresh decision | Rejected handoff and exact accepted receipt | Approval and acceptance |
| Missing is unknown | Full assigned population before results, empty beliefs | Learning admission |
| Count outcomes once | Explicit population denominator and original finalized projection | Finalization and replay |
| Follow-up independence | Set intersection of parent assignments and child membership | Child preparation |
| Historical work survives edits | Saved receipt comparison in a new interpreter and after correction | Persistence and historical export |

The existing failure-space suite covers additional races, leases, uncertain provider calls and authority substitutions. This evaluation adds a bounded serial narrative and inspectable evidence; it does not replace those tests.

## Child approval review correction

The original 34-check scenario stopped after rejecting inherited approval. It did not exercise a fresh child approval. The corrected 37-check scenario records a distinct approval for the exact child case and subject, checks current approval/candidate validity and simulator-only purpose, then reopens the workspace and verifies the saved decision and authority. The saved child artifact now contains that reviewed state. The inherited-approval rejection remains a separate check. A regression rejects child approval or forces its reported authority invalid; either fault must make the evaluator fail. After this correction, all 269 backend tests, the 37-check offline scenario, architecture checks and whitespace checks passed.
