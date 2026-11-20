# Complete offline journey evaluation

Run the acceptance suite from the repository root with installed frontend
dependencies and Playwright Chromium.

```sh
python3 scripts/evaluate_offline_journey.py --output-dir .local/issue-23-run
```

The destination must be new or empty. The command builds the frontend, runs the
desktop and mobile journeys against isolated loopback servers, executes native
control cases, and writes `results.json` and `evidence.md`. It returns nonzero
for a failed expectation, unavailable infrastructure, missing evidence or inputs
that change during execution. Existing evidence directories are preserved.

## Recorded results

The [recorded JSON result](issue-23-offline-journey-results.json) passes both
browser journeys and all four native cases. Each browser journey has eight
independent checkpoints. Source and built frontend files remained stable across
execution. The source-content SHA-256 is
`38aeb5310f2f01020e9e3a4bcd20283efc389cdc1169507ecf73876ca08a76b1`.
The base commit is `2e1a11b1c46b145e88474d97cfd54a503c58184b`. Evaluated inputs
include uncommitted implementation files, recorded by individual content hashes;
the result therefore has no claimed evaluated commit.

| Scenario | Observed result |
| --- | --- |
| Desktop, lost committed schedule response | One schedule, two sources, four observations before and after a real process restart |
| Mobile, lost request before dispatch | Same request ID after reload, one schedule, same four-observation restart recovery |
| Mature recorded learning, both widths | 77 explicit observations, seven controls, four synthetic responses, one finalization |
| Independent follow-up, both widths | No shared parent business identities and a new unapproved subject |
| Native revision and amendment | Separate copy consent and exact review identity; confirmed £512 amendment; replay adds no calls |
| Verified fixture and cold restore | Zero model calls; rejected restored writes preserve bytes |
| Uncertain inference replay | One accounted scripted call; replay adds none |
| Missing control outcomes | 680 treatments recorded, 74 controls unknown, zero counted belief groups |

The retained local run is `.local/issue-23-verified-evidence-20261111`. Its readable
`evidence.md` and 63 evidence artifacts have verified SHA-256 hashes. The JSON
snapshot preserves that inventory. SQLite files, screenshots, traces and exports
stay in the local run rather than being committed; the command above recreates
them in a new directory. Historical issue-25 artifacts are unchanged.

## Acceptance contract

The browser starts with an ambiguous GBP budget, observes a completed
clarification without a model call, reloads and supplies one explicit £600 total.
A scripted provider supplies the corrected contractor brief. Audience confirmation
selects the checked contractors v1 catalogue. Its independent fixture expectations
are 100 source records, 23 exclusions, 70 mailed assignments and seven no-mail
controls. At 85 pence per mailed business, the export cost is £59.50.

Both 1440px and 390px journeys then exercise exact-subject review and simulated
acceptance, download the manifest and CSVs, and verify their counts and hashes.
They upload early and cumulative recorded reports, configure cadence, pause,
reload and resume. Desktop loses the schedule response after commit. Mobile
drops the request before dispatch. Retrying preserves the original payload and
request ID and leaves one schedule and two sources.

The runner exits the actual server process after four observations commit but
before monitoring progress commits. It records the first PID, durable count and
unfinished schedule. A fresh server starts on the same port with the fixture
lease clock advanced by 31 seconds. Recovery retains the four observations and
one import receipt. The application observation clock advances only through the
explicit fixture controls.

The final recording covers all 77 assignments, including the seven controls.
Exactly four synthetic responses contribute successes. Import leaves beliefs
pending until explicit finalization. Reload preserves one finalization event.
The next experiment excludes all parent business identities and appears as a
separate unapproved draft with its own review subject.

Native cases complement the browser journey with targeted copy consent,
new-subject approval, confirmed budget amendments, uncertain inference fencing,
verified fixture execution, inspection-only restore, and missing control
attribution. The incomplete report covers 680 mailed assignments while leaving
74 controls unknown. Even at maturity, it cannot finalize or write counted
beliefs.

## Demo walkthrough

1. Enter the ambiguous contractor brief and answer the budget clarification with
   one £600 total. Confirm contractors v1 and open the prepared campaign.
2. Inspect population, exclusions, cost, exact copy and evidence. Record approval,
   confirm the simulated handoff, and download the manifest and assignment files.
3. Open the synthetic outcome window, upload the two recorded reports, set the
   first check and cadence, then pause, reload and resume monitoring.
4. Recover the saved schedule request after its lost response. Advance to the
   early report, restart after the committed import, and recover the original
   learning request. Four observations remain four.
5. Advance to maturity and finalize the complete recorded population. Prepare the
   independent follow-up and inspect its separate, unapproved review subject.

The automated runner supplies the crash and lost-response faults. Normal users
do not need to terminate the server or interrupt requests to use monitoring.

## Retained evidence

Each browser case retains its SQLite workspace, accepted and finalized state,
exact exports, report inputs, expected population, screenshots, trace and
provider-call hashes. The JSON report inventories retained artifacts by SHA-256
and binds the readable report by hash. Native logs and structured results are
retained. The reused verified-restore case checks disposable roots and records its
result.

Source attribution includes backend code, fixtures, evaluation scripts, React
source, browser tests, public assets, package metadata and the lockfile. The
frontend build has its own file-hash inventory and stability check. A dirty
working tree is recorded by content and has no claimed evaluated commit.

## Evidence limits

All businesses, assignments, acceptance and observations are synthetic. The
scripted planning response exercises orchestration and validation. It does not
measure live model interpretation or editorial quality. Browser requests are
restricted to the fixture's loopback origin, and fixture sockets reject external
connections. Scripted calls and blocked attempts are recorded separately.

The browser journeys use the synthetic legacy workspace lane. Verified fixture
preparation and inspection-only restore are separate native cases. This run does
not establish the complete activated verified-root lifecycle.

The required controls were reachable at both tested widths, with no uncaught
page errors or horizontal overflow in the final follow-up view. The mobile review
and learning page spans several screens and requires substantial vertical
scrolling. Screenshots support inspection of this navigation cost; this smoke
walk does not establish discoverability or assistive-technology usability.

The suite checks declared failure positions and two viewport sizes. Its elapsed
times describe local execution. Provider integration, real delivery, customer
performance and production capacity require separate evidence. The historical
issue-25 evaluation files retain their original content and interpretation.

An initial full interface run exposed a trace-ownership conflict between the new
driver and Playwright's automatic tracing. The wrapper now leaves trace ownership
to the driver, and both complete journeys pass under the test runner. That same
initial run showed an existing copy-edit scenario in a stopped state rather than
ready for review. The focused rerun and subsequent full-suite execution of that
case passed without application changes. Its original cause remains unresolved;
a passing rerun does not establish that this intermittent behavior is fixed.

## Verification

The complete backend run passed 871 tests. Fourteen focused evaluator and source
attribution tests passed against the final Python implementation, including the
native network-attempt regression added after full-suite discovery. The final
`make interface-check` passed the production build, formatting and all 110
browser tests, including both complete journeys. `make arch-check` and
`git diff --check` passed. The evaluation's six scenarios, 16 browser checkpoints,
stable source/build hashes and all 63 retained artifact hashes were verified.
No live provider calls were made.

## Current-main compatibility, 20 November 2026

The initial JSON snapshot above is preserved historical evidence. It predates
the stricter socket and export-identity checks and is not a claim about the
current PR's inputs. The review follow-up and its older-branch validation are
recorded in the [validation ledger](../validation.md).

The PR is based on `72ac7cb`, after the architecture and ownership changes.
Its server fixture now obtains the workspace through `build_workspace` with
an explicit scripted gateway, and uses the canonical server entrypoint. It
preserves current CI sharding and reuses the existing source-attribution helper.
No production behavior, provider configuration or CI job is added.

A new run in `.local/issue-23-main-20261120/` passes all six scenarios, including
desktop and mobile exact-subject exports and restart recovery. All 63 retained
artifact hashes were rechecked. Source and built assets remained stable; the
source-content fingerprint is
`238c592fbdbd156c8435a7edd03601d047688ef7b12415a53f4af0c7e26a9da9`.
The five-case architecture-boundary smoke also passed with zero network
attempts and unchanged historical bytes. This is synthetic functional evidence,
not live-model or deployment evidence.

The first PR CI run also retained an approval-ordering failure: a campaign read
finished before the approval command's response. The desktop fixture now delays
approval dispatch by 250 ms to expose this ordering, and waits for visible
approval before capturing its receipt identities. The delayed regression fails
without that wait and passes with it. The final run is retained separately in
`.local/issue-23-main-approval-20261120/`; its final source fingerprint and
full-suite results are recorded in PR #119. Earlier snapshots remain historical.
