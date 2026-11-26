# Validation and limits

## Email sender display-name review fix, 26 November 2026

The email approval view now displays each immutable email's `from_name` together
with its sender address and reply-to address. These are the same fields already
bound by the review subject and included in the JSON export. Rendering uses React
text nodes; sender data is not interpreted as HTML.

The existing desktop/mobile email regressions open every intended email before
approval, assert the literal fixture display name, capture the complete displayed
sender header and compare it with each downloaded email. The assertions fail on
`9163f55`, which displayed only the sender address. The patch changes presentation
and its client type; it does not modify email payloads, approval subjects or
backend persistence. Verification passes 14 email tests, 18 inherited preparation
tests, architecture with 245 modules and zero exceptions, and the full 162-case
interface gate with one worker, including build and formatting. The unchanged
backend retains its prior 1,235-test and five-case recovery evidence; those full
backend gates were not repeated for this presentation fix. Exact source
commits, the failing-before/fixed-after regression and hashes are retained in the
[sender review evidence](evaluations/issue-131-intake-email-sender-review-2026-11-26.json).

## Reviewed intake email preparation and export, 26 November 2026

The email-only intake path preserves the exact reviewed company/brief revisions,
selected wording, qualification and official CTA in a bounded synthetic package.
The contacts, permissions, sender and planned cost are explicitly synthetic and
are not matched to the requested audience. No runtime, model or dispatch work is
admitted. See [the contract](intake-email-preparation.md).

| Invariant | Commit/authority boundary | Executable regression |
| --- | --- | --- |
| Exact source, original command and one batch per context | Two intake journal bindings in one writer transaction; native source reconstruction | `test_intake_email`: selected wording and two companies; changed inputs; expiry rollback; lost commit and two contenders; fresh-process reopen |
| Source review, recipient permission and export approval are separate | Purpose-specific subject binds complete batch and scoped authority/stop basis | `test_intake_email`: foreign/purpose/role substitution, missing approval, suppression, edited sources |
| Historical approval/export receipts never authorize current downloads | Writer transaction rechecks current sources, actor generation, eligibility, expiry and revocation | `test_intake_email`: cached export after revocation/expiry/source edit; expiry before bytes; readonly, actual checkpoint restore and verified pause; exact byte hash |
| Interrupted commands reconcile the original store and inputs | Browser saves the full command before POST; receipt-first retry with store fence | `intake-workspace.spec.mjs`: lost preparation/approval/export replies, malformed recovery data, store switch and original-store recovery, desktop/mobile exact export |
| Remote transport preserves original native semantics | Existing Turso adapter via bootstrap; schema 27 and native journal transactions | `RemoteIntakeEmailTests`: loopback Hrana lost COMMIT acknowledgement, reopened replay, review and exact JSON download |

Sequential verification passes 1,235 backend tests, 162 browser tests with one
worker, architecture with 245 modules and zero exceptions, and all five integrated
recovery cases. Recovery records zero network attempts, 40 unchanged historical
artifacts and stable source. Four additional scoped native-state fault cases
cover contact pause, account stop, email objection and a foreign-organization
negative control. They inject native rows, rather than claiming a new contact
administration workflow.

The full backend run binds `940afa5`; subsequent commits change only frontend
selection and test synchronization. The final browser and recovery checks bind
`e0eb7be`. The [26 November verification record](evaluations/issue-131-intake-email-2026-11-26.json)
retains exact hashes, logs, source manifests and those attribution limits.
Managed Turso, live model/provider and real permission or sending behavior remain
outside this evidence. PR #145 grounding is included as a prerequisite without
modifying its independent branch.


## YouTube media refresh, 25 November 2026

The bundled comparisons now use the exact rendered files from merged YouTube
source `2d4e60d4027217edada6c93153d02cc0aa17cc75`. Fixture passages and the
editing instruction match its generation manifest. Destination creative and
comparison identities advance to v2; source identities remain recorded in the
provenance map. Four standalone ad candidates are retained as sample artifacts,
without adding ad selection or inference to the application.

The focused native suite passes 20 tests and the guarded HTTP suite passes eight.
The new upgrade regression preserves all original channel rows, rejects v1
approval/export replay after installing v2 context, and prepares a fresh
unapproved v2 package without model calls. A separate consistency check verifies
the source passages, instructions, take definitions and all 15 copied asset hashes
and sizes. Browser coverage now checks both comparison pages, their displayed
transcripts, AI disclosure, v2 identities and media metadata after exact export.

Architecture passes with 232 classified modules and zero exceptions. Production
build, frontend formatting and the 147-case browser catalogue check pass. The
complete backend/interface and attributable recovery results are recorded on
the refreshed PR head. No schema, review authority, provider client, credential,
source history or live campaign execution is imported by this asset update.

## CI fixture clocks, 25 November 2026

The authored product evidence ends its review window on 24 November. The next
day's full PR run exposed three Python failures and four browser failures:
unfrozen subprocess/browser clocks, an obsolete patch on the forwarding CLI
module, and an HTTP test that replaced the facade clock after application
dependencies had captured it.

The CLI tests now patch construction in bootstrap inside each subprocess. The
no-credentials admission test also rejects any attempt to load a gateway. HTTP
tests inject a shared mutable clock before constructing the workspace. The
browser test server injects a clock inside the authored source window through
the normal startup path. No production backdating flag, evidence date change
or freshness exception is introduced.

The 24 focused CLI/HTTP tests, 23 grounding/catalogue tests, eight CI-tool tests
and four previously failing browser cases pass locally. Changes to the new
browser server helper require the full browser portfolio, including when a
skip label exists. Formatting and the 232-module architecture
check pass. The existing grounding test still rejects 25 November evidence,
and catalogue regressions still reject stale/future sources. Full PR CI
verifies the combined suite separately; these checks make no live model calls.

## Integration with merged intake planning, 25 November 2026

Main PR #137 and the reviewed YouTube branch both used migration 25. The
integrated branch retains intake planning at 25 and installs native YouTube
history at 26. It recognizes the earlier unpublished YouTube-only schema-25
layout and upgrades it transactionally, while ordinary main schema-25 stores
receive the native tables without replacing intake sources or planning receipts.
Historical stores without the channel remain readable without creating channel
history. Current schema-26 stores still fail closed when required history is
missing.

Targeted real SQLite and local libSQL-wire regressions cover both schema-25
layouts, failed migration rollback, exact approved-export replay, store identity,
frozen intake source/result preservation and zero repeated model calls. The
original reviewed verification records remain immutable and describe their
original commits; final merge CI supplies the combined-branch gate results.


## YouTube routing review correction, 24 November 2026

The browser and native router now recognize the same singular/plural email,
e-mail, postcard, human-call, phone-call and call-script terms. A postcard
follow-up to the current YouTube turn leaves the native route and uses postal
message admission; generic follow-up callers receive the same transition.
Mixed explicit channel requests remain a clarification even when placement
permission is present, with zero draft, preparation task or model-call rows.

Current routing is also rechecked at publication. An older queued operation
admitted by the previous classifier cannot publish a YouTube-only draft after
resume. Its original request and runtime history remain intact. This correction
changes no schema, approval rule, provider adapter or historical artifact.

Both failures reproduced before the fix. After correction, 26 focused tests
passed, including all eight real loopback HTTP cases. All 1,168 discovered
backend tests passed exactly once across four supported shards. The production
build, formatting and all 141 browser cases passed with zero skipped,
unexpected or flaky results. Five recovery boundary scenarios passed on
`00c944f8a1f07732059c0394e2d56fd7b40d823a` with stable source, zero
network attempts, 228 classified modules, zero architecture exceptions and all
33 historical evaluation artifacts unchanged. The [routing review evidence](evaluations/issue-132-routing-review-2026-11-24.json)
records source identity, regression outcomes and finite verification limits.

## Native YouTube preparation, issue 132, 24 November 2026

The [authored local flow](youtube-preparation.md) adds a native channel module,
`youtube.prepare.v1`, exact human review and manual JSON export in existing chat.
Schema 25 appends native history without changing postal or sequence identities.
The frozen request, runtime plan, current conversation revision and active lease
bind publication. Stops, superseding messages and competing campaign edits block
late drafts. Advice and ambiguous channel requests grant no draft permission.

Approvals bind exact payload/media/context/origin and current local authority,
with bounded expiry and explicit revocation. The installed local adapter consumes
the existing operator/reviewer records and never resets disabled roles. Both
role generations bind the subject; disabling and re-enabling a reviewer cannot
renew an old approval, including after a fresh interpreter opens the store.
Export rechecks current state before
replaying a receipt. Receipt recovery cannot restore stale authority. Human
approval/download are absent from the typed agent tool surface. The guarded HTTP
path and browser pending commands bind the original store; a reply lost after
commit retries the original request. Definite admission rejection unlocks editing
without treating post-commit uncertainty as failure to save.

Real SQLite, fresh-process reads, migration rollback, lease expiry, concurrent
edits, stop/resume, public media and scope substitution have executable targeted
coverage. The existing libSQL transport also passes a local wire-simulator save,
approval rollback and fresh-connection export. This is not hosted Turso evidence.
Bundled previews are functional but collect no viewer events. No provider calls,
source-history import, live ad effect, deployment or source cutover is included.
The retained [evidence record](evaluations/issue-132-youtube-flow-2026-11-24.json)
records the source attribution, failure corrections and finite limits. Backend
coverage passed all 1,165 discovered cases across four supported shards, with
zero missing or repeated test identities; the affected 443-case partition was
rerun after the read-only fix. All 65 final affected-module tests also passed.
The final production build, formatting and both browser partitions passed all
133 cases, with zero skipped, unexpected or flaky results. The final five-case
boundary gate on `50792942ccfa9dc17372b3d01666bd5792a6d5bc` passed with
stable source, zero network attempts, 228 classified modules, zero architecture
exceptions and all 32 earlier evaluation artifacts unchanged. Desktop and 390px
manual inspection included a real native JSON download and fresh-server reopen.
Earlier browser runs under concurrent backend/build load failed; the final full
browser run used stable assets without backend load and unchanged assertions.

## Intake recovery store binding, review correction, 24 November 2026

The P2 review identified an ownership gap: an original save retained its inputs
but not its database identity. Restarting the same browser origin against another
root could create a draft there and clear recovery without reconciling the
original store. Pending commands now retain the existing immutable application
store ID. A guarded, non-cached identity read precedes every dispatch; the HTTP
writer independently checks the binding against the intake instance it uses.
A mismatch retains the original command and cannot act as a definite rejection
or receipt for its owner. Successful receipts and definite rejections also bind
the original store before the browser clears recovery. No migration was needed.

The real SQLite HTTP regression checks distinct store identities, missing/foreign
bindings, zero wrong-store writes and a same-key receipt in the other store.
The browser regression commits in A, loses its reply, restarts the server on B
at the same origin and proves zero POSTs and unchanged recovery. A stale identity
response then exercises the server fence and retains the pending command without
writing B. Returning to A confirms the original receipt with unchanged durable
rows. Older unbound recovery data stays retained and blocks new saves; ownership
is never guessed from the currently configured root. One deliberate server-fence
bypass in a disposable source copy was detected by its wrong-store 200 response.

Verification on `487b9f87f3be32b96e3436c614925b3df721fc2f`: `make test`
passed all 1,143 tests in 1283.784 seconds. `make interface-check` passed its
production build, formatting and all 129 Chromium cases with zero skipped,
unexpected or flaky tests. Focused intake checks passed 14 backend tests and
11 browser cases. Architecture passed with 221 modules and zero exceptions.
All five native recovery boundary cases passed with zero network attempts,
stable source and unchanged historical bytes. All 31 earlier evaluation artifacts
and the original dirty checkout were preserved.

The [store-binding review evidence](evaluations/issue-60-intake-store-review-2026-11-24.json)
records six selected invariants, source identity, logs and finite test limits.
Store binding does not provide hosted authentication or tenant authorization.
No deployment, managed remote probe, paid inference or outbound effect occurred.

## Local company and brief workspace, issue 60, 24 November 2026

The guarded loopback API and React **Company & brief** forms expose the existing
intake persistence contract. Company/product assertions and incomplete campaign
requirements retain exact wording. Briefs pin an immutable company revision;
subsequent company edits do not rebind them. Server composition resolves the
local organization and actor, rejects substituted authority fields and retains
the selected verified-admission policy. Saving and reading create no campaign,
model-call or approval rows. Hosted tester access and generation integration
remain separate.

Four real HTTP/SQLite tests cover source round trips, process restart, scoped
reads/writes, forged requests, stale edits, exact replay, transport/domain bounds
and zero execution effects. Ten browser cases cover desktop/mobile save and
reopen, competing tabs, a committed save whose reply is lost, exact original
retry after reload, uncertain edits retaining their original target/revision,
unavailable/corrupt recovery storage, pagination and stale preview responses.
Oversized drafts, including Unicode JSON expansion, are rejected before a
pending command is retained or dispatched. Independent unsaved edits retain
their leave-page warning while another form has a recoverable save. Unsaved
fields remain in memory until saved; browser warnings are best effort.

Three selected HTTP mutations were detected: a bypassed request guard, a wrong
writer organization and an ordinary body cap incorrectly applied to intake.
These are finite targeted checks, not exhaustive concurrency or mutation
coverage. Manual Playwright keyboard navigation confirmed visible focus and
label order. Automated browser evidence is Chromium with desktop/mobile
viewports, not a real-device or screen-reader conformance audit.

Final source `94f28d04637d322d38885ce2ad5509ac5b32eb77` passed `make test`:
1,142 tests in 1233.726 seconds. The focused backend suite passed 21 tests.
`make interface-check` passed the production build, formatting and all 128 browser
tests with no skipped, flaky or unexpected results. `make arch-check` passed
with 221 classified modules and zero exceptions. All five `make boundary-check`
cases passed with zero network attempts, stable source and unchanged historical
bytes. The evaluated source fingerprint remained stable throughout these gates.

The [dated verification record](evaluations/issue-60-intake-workspace-2026-11-24.json)
maps 14 selected acceptance invariants to observable checks and records source
identity, log/report hashes and limitations. All 30 prior evaluation artifacts
and the original dirty checkout were preserved. No managed Turso re-probe,
deployment, live inference or outbound effect was performed. The forms remain a
local operator surface; they do not activate Gateplane or establish hosted
tenant access. See [the intake contract](intake.md).

## Preserve source punctuation in intake, review follow-up, 24 November 2026

Intake text validation accepts em dashes in user-supplied company/product drafts
and campaign requirements. The restriction for newly generated editorial copy
never applies to this source evidence. Size, control-character, surrounding
whitespace, structural and URL checks remain in place. No stored history is
rewritten and no schema or execution authority changes.

The existing real-SQLite save/reopen regression now preserves exact punctuation
in company/product names, description, claims, qualifications, CTA, objective,
audience and constraints. A fresh interpreter reads both original draft types,
and exact retries retain their original snapshots after a later company edit.
Changing the punctuation on the same brief request key conflicts. The Hrana-wire
intake test also preserves company and objective punctuation after a lost COMMIT
reply and a fresh session. Restoring the old rejection in an isolated source copy
makes the regression fail with the original validation error.

All nine focused intake tests and all 18 Hrana-wire storage tests passed.
`make test` passed **1,138 tests in 1,241.119 seconds** on source
`f134d10a82ce47ec808187bbbec1720b201d21d6`. `make arch-check` passed with
220 modules and zero temporary exceptions. Source remained clean and stable;
all 29 earlier committed evaluation artifacts and the original dirty checkout
were preserved. The [review evidence](evaluations/issue-60-intake-punctuation-review-2026-11-24.json)
records the source fingerprint, targeted failure reproduction and full-run log
hash. No managed remote probe or deployment was repeated for this source-text
validation fix. Earlier boundary and remote evidence retain their original
commit attribution.

## Company and campaign intake persistence, issue 60, 24 November 2026

The internal intake API saves company/product assertions and campaign requirements
as organization-scoped immutable revisions. A brief pins an existing exact company
revision. Actor attribution and exact request inputs accompany the original save
receipt. `BEGIN IMMEDIATE` and the revision check choose one winner for competing
edits; snapshot and receipt commit together. User input remains unverified and
grants no fact-pack, planning, approval or execution authority.

The finite verification model has nine persistence invariants, each linked to
observable tests in the [dated evidence](evaluations/issue-60-intake-persistence-2026-11-24.json).
Nine new local tests cover isolation, history, both draft types' stale edits,
original replay, changed inputs, rollback, hard process exits before/after commit,
input bounds, pagination and inspection-only saves. Two additional Hrana-wire
cases cover intake composition, independent sessions, lost COMMIT acknowledgement
and remote DDL rollback. The existing checkpoint round trip now preserves intake
and rejects writes through the restored root. Four selected harmful mutations
were detected: omitted revision comparison, changed-input replay, foreign company
scope substitution and an early commit before receipt insertion. This is 4/4
selected mutations, not exhaustive mutation or concurrency coverage.

`make test` passed **1,138 tests in 1,472.370 seconds** on source
`26ec0aea18a1b9980a67fbbcf631126ef5fa14ac`. `make arch-check` passed with
220 modules and zero temporary exceptions. All five native boundary cases passed,
with zero network attempts, stable source and unchanged historical evidence.
The boundary source fingerprint is
`3306bd9af291de80eb36db6333d78f9fc48cc6a3e89b20965c2856b0d4a3f69f`.
An initial full run was stopped after two failures in a historical migration
factory that applied the new DDL while deliberately omitting older migrations. Historical factories
for schemas 4, 5, 11 and 22 now also omit intake DDL/validation. Their nine focused
checks passed before the successful full rerun. Production code was unchanged
by that fixture correction.

Real conformance on the existing isolated Turso resource passed with two fresh
processes competing for one revision, exact original-receipt recovery after a
simulated lost COMMIT acknowledgement, changed-input rejection, cross-organization
rejection and a pinned earlier company revision. One unique synthetic organization
contains two company revisions, one brief revision and three request receipts,
with zero campaign runs or model calls. The run binds a clean, stable source
fingerprint. Local SQLite and the Hrana-wire fixture exercise migration rollback;
no rollback fault was injected into the managed provider.

Schema 24 is additive. Legacy rows, historical bytes and cutoff rules retain their
existing contracts. The isolated remote probe is now migrated, so schema-23-only
preview binaries need a rebuild before reuse. No deployment, public tester access,
Gateplane integration, frontend, live model or outbound effect was activated.
Retention/deletion and future capability assessment remain separate work. The
original dirty checkout was preserved. See [the intake contract](intake.md) for
internal API usage and the trusted scope boundary.

## Saved replies fence native dispatch, issue 68

The SQLite regression saves a reply immediately after the worker reads its
observation intents, with the affected account's next step already due.
The stale tick leaves that reply pending and creates no new submission for
the affected account. Original observation processing and independent-account
continuation still complete after restart.

Reply admission now commits an engagement pause and its journey command in
one transaction. Native claim and commit authorization use the existing
engagement stop reader. A failed pause insert rolls back both the pause and
the command. Exact retries and a second request for the same accepted email
reuse the original pause.

Both targeted harmful mutations were detected: omitting the admission pause
fails the rollback assertion, and ignoring pause actions in native authorization
fails the stale-worker submission assertion. All 526 existing catalogue
mutations still match and compile. The seven sequence browser tests passed,
including lost-response recovery and a reply after completed submissions.
`make test` passed all 1,067 backend tests in 1,182.028 seconds.
`make arch-check` passed with 209 modules and zero exceptions. All five offline
boundary cases passed with zero network attempts, stable source state and
unchanged historical artifacts. The source fingerprint is
`f11916a9607ae69e369c2269a1548c40347f15d0ba5e0d78445ef1745dd6346e`
on base `ed0ae4335c93ced739ff6112a72e7e68daf231c9`.

## Replies after completed submissions, issue 68

The review regression reproduced rejection of a reply to an accepted final
follow-up on a current completed journey. The backend and workspace now allow
this observation. Continuation reads the native simulation after recording
the reply and returns to complete without invoking submission advance.

The existing two-company completion test now records the final email's reply,
preserves all original steps and accepted counts, retries the original key
and a second key, and reopens the original journey. The native advance method
is replaced with an assertion failure while the completed reply is processed.
The browser completion journey now records a reply after completion and
checks that it returns to complete before reload.
Both targeted mutation probes were detected by assertions. The architecture
check passed with 209 modules and zero exceptions. All five offline boundary
cases passed with zero network attempts and preserved historical artifacts.
`make interface-check` passed the production build, formatting and all 115
Chromium tests, including the post-completion reply and lost-response cases.
`make test` passed all 1,067 backend tests in 1,283.862 seconds.
The source fingerprint is
`223499df68ce5446622b3e3c16b93a018299eae4a43aa487f2420c87e95cfc9d`
on base `ed0ae4335c93ced739ff6112a72e7e68daf231c9`.

## Conversational synthetic reply, issue 68

The workspace admits an explicit reply observation for an accepted email in
the exact current journey and revision. The existing engagement observation
command records the original effect and pauses pending steps for its account.
The journey continues independent pending work while that pause is active.

The two-company SQLite regression covers pending-step and foreign-scope
rejection, changed-input replay, native commit followed by a lost continuation
acknowledgement, restart, a second tab's request, stop and read-only inspection.
Both request keys converge on one reply observation with the original time.
The Iwoca case also requires a later independent human task to be accepted.
The scheduling and observation-time catalogue mutations and a mutation that
blocks the journey on any account pause were detected.

The browser reply test exercises the HTTP action, a lost committed response,
polling and reload. When a command response fails, the sequence panel reads
current state to recover polling even if the prior view was waiting for human
input. The original pending command key remains available for exact retry.
Observation admission also changes the journey's continuation state so an
older worker tick cannot overwrite the saved request with a waiting status.
The initial browser runs exposed a historical-guidance timing failure and
this scheduler race after a lost reply response. All seven focused browser
journeys passed after the fix. A deterministic SQLite interleaving rejects
the stale progress write.

The final `make interface-check` passed its build, formatting and all 115
Chromium tests, including reply recovery. Four targeted mutations detected
the scheduling, timestamp, account-pause and stale-progress faults. All 526
catalogue definitions match one source location and compile.

The final `make test` passed all 1,067 backend tests in 1,256.933 seconds.
The focused sequence suite passed all 22 tests. The architecture check passed with
209 classified modules and zero exceptions. The offline boundary check passed
all five cases with zero network attempts and preserved historical bytes.
Its source fingerprint is
`cd0d1de7e860c02c4ac7cc7ef57749842215f50e4d97044d0374ccf98eb81306`
on base `ed0ae4335c93ced739ff6112a72e7e68daf231c9`.

## Final channel evidence timestamps, issue 109

Two SQLite regressions reproduced the review findings. Advancing the clock to
the contact-source expiry after the post-insert check previously dispatched
one synthetic call. Advancing it to a recipient fact expiry after the final
publication check previously committed the artifact and task completion.
The revised reservation leaves no call row and dispatches zero calls. The
revised publication rolls back the artifact, task completion and success event
while retaining the three recorded calls.

Reservation and publication validate the same evidence at the timestamp used
for the final lease check. Within the checked validity interval the result
still applies. If the timestamp crosses an evidence boundary, the current
evidence is evaluated at that timestamp inside the same transaction.
An email run still completed when the clock crossed a postal permission
deadline that left its email evidence valid.

`make test` passed all 1,066 backend tests. All 66 focused channel, contact
and recipient tests and all six Chromium sequence-journey tests passed.
Four catalogue mutations and both final timestamp
mutations were detected. All 526 catalogue definitions match one source
location and compile. `make arch-check` passed with 209 modules and zero
exceptions. `make boundary-check` passed all five cases with zero network
attempts and preserved historical evidence bytes. The source fingerprint is
`851b2e94612a0f9695f5fdabce23089c673950012c000dc051f4e3b21d67a169` on base
`fbd31d38aa2e47f96b4a533cdb5ff7854a3b25c0`.

## Default channel ownership cutover, issue 109

Six post-merge smoke tests passed on `main` after PR #116 at `fbd31d3`.
They exercised both companies' journeys, the schema-22 upgrade, paused journey
admission, worker recovery, uncertain-call reconciliation, and workspace HTTP.

The cutover uses the existing atomic admission transaction for the default
native and workspace channel paths. Real SQLite tests exercised faults before
and after each of seven admission writes in both writer modes. They also
verified that the ordinary runtime and inference adapters cannot execute a
synthetic channel admission. Each company's journey completed with one
binding per channel stage and every call charged to its original conversation.
A prior standalone run retained its own accounting after a later journey.
A recipient objection injected after the reservation insert caused the
transaction to roll back before dispatch. A separate probe
verified the final lease check and the installed five-call per-run limit.

A process running the PR #116 code fenced a queued cutover run and retained
its inspection history. The updated native CLI then resumed the same run with
three synthetic calls and the original admission receipt. Checkpoint tests
retained valid ownership for queued work and blocked execution on restore.

`make test` passed all 1,064 backend tests. `make arch-check` passed with 209
modules and zero exceptions.
`make boundary-check` passed all five cases with zero network attempts and
preserved historical evidence bytes. It evaluated the cutover worktree at
base `fbd31d38aa2e47f96b4a533cdb5ff7854a3b25c0` with source fingerprint
`a1bc9f12b33c63d45c5781042f5f0d1b0db23e030b2ad5da1011939d7ffd905f`.
`make interface-check` passed the production build, formatting and all 114
Chromium tests, including the six sequence-journey cases.
All 526 mutation definitions match one source location and compile. Seven
catalogue probes and three cutover probes detected their target faults.

## Ownership stack integration after PR #95, 18 November 2026

Four post-merge smoke tests passed on `main` at `6fb2920`. They exercised
both companies' sequence journeys, the schema-22 upgrade, channel worker
recovery, and the workspace HTTP flow.

The feature branch merges ownership PRs #113 through #115 at `20b3c48`.
The shared channel verifier enforces PR #95's original preparation and run
requirement, and the copied-task regression remains in the suite.
A fresh SQLite probe confirmed that default preparation completes with
three synthetic calls and zero ownership admissions. Explicitly staged
preparation remains queued with one ownership admission and zero calls.
The default-writer cutover remains open in #109.

`make test` passed all 1,063 backend tests. `make arch-check` passed with
209 classified modules and zero exceptions.
`make boundary-check` passed all five synthetic cases with zero external
network attempts and preserved historical evidence bytes. Its evaluated
commit is `20b3c48d5c49e78dc7db916408fc17b893279140` and source fingerprint is
`24a9fd868705b260e64c6bf13167fc9d38112cb3ef3bbf7ea1226b2d2e1d302c`.
`make interface-check` passed the production build, formatting and all 114
Chromium cases, including six sequence journeys. All 526 mutation definitions
match one source location and compile. All four targeted ownership mutations
were detected.

## Composed channel ownership conformance, issue 111

The existing SQLite suite now verifies seven prior-admission variants, with
exact positive call and artifact counts for both Fielddesk and Iwoca. Each
queued independent run records three calls against its own run, and the
later journey records nine against its original conversation and revision.
Both later journeys reach review without approval. Six detached continuation
variants exercise queued resume, reservation, cached replay, publication,
uncertainty and late observations. They preserve the original accounting
and leave ambiguous history unresolved. A fresh CLI process agrees on the
in-flight case after the late receipt arrives.

The stopped-source alias fixture uses the same provider-account identity with
a distinct source ID. It cannot obtain a new assessment. The reconciliation
checks observe rollback on a receipt-write fault and on drift after the audit
write. A process then exits after the transaction commits and a second
process returns the exact original receipt. The original call history
remains byte-for-byte intact.

The six focused methods ran in 33.414 seconds. Four selected mutations were
detected by behavioral assertions in 28.88 seconds wall time. All 526 manual
catalogue entries matched once and compiled. The focused timings include
overlapping verification workloads and are single-run observations. The
frontend build and the six existing Chromium sequence tests passed. The
browser suite took 1.2 minutes. The architecture check passed with 209
classified modules and zero exceptions, and the whitespace check passed.

`make boundary-check` passed all five synthetic cases with zero external
network attempts and preserved historical bytes. The report records base
`dcc80861a4a31ca5ccf919634c0a657ddf017718` and source fingerprint
`65f9f1785f2a68513c87be3ca4196002cd7aba533fadd382abd5d15065a0f1ee`. The full `make test` suite
passed all 1,063 tests in 978.893 seconds.

The [conformance matrix](run-ownership-admission.md#composed-ownership-conformance-in-111)
records denominators, retained legacy coverage, CI cadence and reuse for #74
and #77. The checks measure synthetic authority and recovery behavior. Live
model quality, delivery and customer outcomes require separate executed trials.

## Verified standalone ownership across legacy journeys, issue 110

The SQLite regression reproduced a committed standalone run becoming
inapplicable after a later same-source journey whose requested event lacked
`prior_channel_runs`. The committed admission now supplies the ownership proof.
After reopening the store, the run remains bound and applicable, with the
same run ID, ownership fingerprint and zero calls. Its frozen contexts and
explicit channel and recipient bindings are still checked. The paired
legacy run has no committed binding and remains unresolved without ordering
evidence, including when the clocks differ.

Three focused mutation probes detected reintroducing source ownership inference
for an admitted standalone run, skipping its explicit channel binding check
and skipping its explicit recipient binding check. The architecture and
whitespace checks passed. All five integrated boundary cases passed with zero
external network attempts and preserved historical bytes. The boundary report
records source fingerprint
`e44ef0b2486695e6b0eea6b12cbd27ad3b59c3bb956dddb83d9df1f898ef95de`. The full `make test` suite
passed all 1,063 tests.

## Standalone journey link review, issue 110

The real SQLite regression reproduced an admitted standalone run remaining
bound when its channel command or recipient request gained a conflicting
journey binding. Both ownership kinds now use the same frozen-lineage check.
Conflicting links make the standalone run unresolved and inapplicable, block
exact replay and keep its zero-call pause intact.

A genuine later journey on the same source leaves the standalone binding valid
when its snapshot names the exact earlier run and context. The regression uses
equal clocks. A separate probe changed only the context in that snapshot and
verified the ownership became unresolved until the exact pair was restored.
A targeted mutation that skipped the lineage check for standalone runs was
detected.

`make arch-check` and `git diff --check` passed. The five integrated boundary
cases passed with zero external network attempts and preserved historical bytes.
The boundary report records source fingerprint
`71afad34c21a1c95eab8c2db0697e9f9a0a2275705d259b795dcae3662c6a268`. The full `make test` suite
passed all 1,063 tests.

## Admitted recipient lineage review, issue 110

The paused journey regression reproduced missing and conflicting recipient
bindings on both Fielddesk and Iwoca. The canonical reader now corroborates the
frozen recipient context and assessment IDs, the recipient's original journey
origin and the original assessment command binding. The historical read uses
the original journey revision. Effect boundaries still check current stop and
consent independently.

Both profiles now report damaged runs as unresolved and inapplicable while
claim and inference remain paused. The regression restores the link, then
verifies the original binding and receipt after a stop. A separate SQLite
probe removed a native recipient context receipt and observed unresolved
ownership, an inapplicable run and zero calls. Independent mutations removing
either the recipient-origin check or the assessment-binding check were detected.

`make arch-check` and `git diff --check` passed. The five integrated boundary
cases passed with zero external network attempts and preserved historical
bytes. The final report records source fingerprint
`b9e2dc17605d8c104fdea9efe12dd7b1b644cf51ab99e087c2e238e504f26806`. The full `make test` suite
passed all 1,063 tests.

## Channel ownership readers and legacy reconciliation, issue 110

Real SQLite checks verified that a surviving admission event fences a run
after both admission rows and the task marker are removed. The channel read
and exact-request replay reject the missing binding. Detached legacy runs stay
unresolved through inspection, reservation and publication.

Legacy inspection and reconciliation ran in separate CLI processes. A fault
between the ownership receipt and audit event rolled back both writes. A stale
report could not reconcile a changed run. Exact retry returned one original
receipt after restart, including for an unknown call that was never repeated.
An in-flight reservation blocked reconciliation and its late observation still
recorded on the original call. A previously independent run completed after a later journey without adding to
the conversation allowance. A stopped conversation retained its original
account, revision and complete call journal. The checkpoint round trip allowed
inspection and blocked reconciliation writes.

`make arch-check` passed with 209 classified modules and zero exceptions.
`make boundary-check` passed 5 synthetic cases with zero external network
attempts and preserved historical bytes. The report records integration base
`ec5c0a373aa731d2187cbcab2e0aa9c715909d11` and stable source fingerprint
`d9d8439cb01190f21b5802310b37882e447f533944f59559345547eac3494467`. Both updated mutation probes detected
their target failures. Two additional mutation probes detected removal of the
surviving admission-event fence and bypass of stale-report rejection. All 522
catalogue definitions match once and compile. The full `make test` suite passed
all 1,063 tests.

## Universal writer review, issue 109

On 18 November 2026, a real SQLite probe compared two fresh stores using
the installed channel fixture. Default native preparation succeeded with
three synthetic calls and zero scoped `execution_admissions` rows. Explicit
paused composition left one committed binding, a queued run and zero calls.
This verifies the paused writer and the outstanding coverage gap. The
default native and workspace cutover remains open in #109.

## Preparatory paused channel ownership admission, issue 109

The staged writer verifies native assessment and recipient receipts, installed
source versions and provider accounts, and the original journey stage and
consent inside the same SQLite write transaction as its runtime and ownership
records. The paused receipt grants no execution authority. A native replay
uses the original run identity, and a cloned runtime task cannot use that
run's preparation to reserve a model call.

Real SQLite regressions passed for statement faults at each durable admission
table, concurrent identical commands, changed request rejection, restart,
late stop and revision changes on both profiles, and standalone ownership
after a later journey. A staged rewrite preserved the exact completed parent's
standalone operation root. The checkpoint round trip preserved the binding and
blocked resumed writes. The verified-paused writer fence also passed.

`make arch-check` passed with 209 classified modules and zero exceptions.
`make boundary-check` passed five synthetic journeys with zero external
network attempts and preserved historical evidence bytes. The JSON report
records local #68/#108 baseline `17bd908f5afc6ef088f5f09927c4cf3e700804c9`
and stable source fingerprint
`67219bdee2a0900feb6386e404b1402d5c218b0e78fc4df62e68a441ce7374a1`.
The two adjusted mutation probes both detected their target faults. All 522
probe definitions match one source location and compile. The full `make test`
suite passed all 1,061 tests.

## Refreshed #68 integration candidate for PR #95, 18 November 2026

The refreshed candidate combines the workspace architecture on main
(`e66245e`) and the reviewed #68 provenance compatibility snapshot
(`17bd908`). The architecture closure under #88 is present. The
ownership stack from PRs #113 through #115 is the separate promotion after
the #68 baseline is accepted. The default-writer cutover remains open in #109.

A real SQLite regression reproduced a reservation reaching the call journal
through a runtime task that reused another run's frozen channel context.
The reservation now requires the original scoped preparation and run. A
copied task cannot reserve calls, and the original run reuses its three
recorded observations after worker loss and publishes one artifact.

`make interface-check` passed the production build, formatting and all 114
Chromium cases, with zero skips, unexpected results or flaky retries.
`make arch-check` passed with 209 modules and zero exceptions.
`make boundary-check` passed all five synthetic cases with zero external
network attempts and preserved historical evidence bytes. Its evaluated
commit is `207e84049616d3da667cf2e950733d5a3436f2b5` and source fingerprint is
`baf3d759b3fcbdd2354eee62856a869f3658a06f35f9615f5b442743b4b426e9`.

Three selected mutations were detected by behavioral assertions. They cover
loss of the original preparation check, detached recipient lineage and
recovery of the shared scope when account links are missing. All 522 manual
mutation definitions match a single source location and compile. The full
`make test` suite passed all 1,059 tests.

## Run ownership contract, issue 108

The stage 1 comparator requires positive, consistent ownership for all required
source lineages. Contract tests cover matching standalone and conversation
owners, mixed ownership, missing evidence and substituted scope or revision.
The 38 focused admission tests passed, including the existing atomic SQLite,
replay and paused-execution checks. The architecture check passed with 205
classified modules and zero temporary exceptions. The full backend suite passed
all 1,039 tests with local loopback access.

Four existing integration tests also passed in the separate #68 candidate
worktree. Those checks cover independently admitted runs, detached continuation,
reassessment and missing accounting evidence. They establish behavior for that
candidate's compatibility bridge. The [reuse inventory and rollout plan](run-ownership-admission.md)
identifies the candidate and the later writer and reader work.

## Standalone accounting interaction review, issue 68

A prior standalone run could continue using its immutable admission-order
receipt, but conversation accounting did not recognize that evidence and marked
the shared native scope unresolved. The extended regression failed for both a
completed prior run and a prior unknown call with `accounting_complete: false`.

Accounting now uses the same validated prior-admission classifier as channel
continuation. The exact run/context must precede every relevant journey, retain
valid saved source provenance and have no contradictory native binding. Runtime
task completeness and plan-hash checks still run before this exception. No new
ownership is inferred from an absent link, a timestamp or the shared source.
After-journey detached calls and missing task-origin/index/account evidence stay
unresolved.

The composed test checks complete accounting with zero journey usage before
preparation, restart, a validated unapproved sequence and exactly nine counted
journey calls. Prior standalone calls, including an unknown call, remain on their
original run and outside the journey allowance. The detached late-publication
case independently verifies incomplete accounting. The three focused interaction,
detached-run and lost-link tests passed. The design assessment and proposed
immutable per-run ownership migration are recorded in
`docs/conversational-sequences.md`; that migration is not implemented here.

`make test` passed all 1,058 tests in 1,016.051 seconds. `make arch-check`
passed with 209 modules and zero exceptions. The selected omission and overly
broad accounting-exemption mutations were detected (2/2); all 522 catalogue
anchors still match once and compile. `git diff --check` passed.

## Independent standalone admission ordering review, issue 68

Dynamic source ownership incorrectly applied a later journey to a standalone
channel run admitted before it. The regression failed for both a queued run and
an unknown-call run because they became inapplicable after the later journey.

A journey's immutable requested event now records existing scoped channel
run/context identities inside its admission transaction. Continuation excludes
that later journey from ownership of those exact prior admissions, including
when both clocks are equal. Earlier source-owning journeys still fence detached
runs; being listed by a still-later journey cannot erase the original owner.
New preparation commands remain subject to current ownership checks. Existing
run and context identities are preserved.

For historical requested events without the snapshot, timestamps alone do not
establish transaction ordering. Missing admission events, missing snapshots and
malformed ordering receipts grant no exemption.
No historical artifact or event is rewritten and no schema migration is added.

The regression covers queued continuation, the original unknown-call fence,
equal-clock transactional ordering and older receipts without ordering evidence
under both equal and different clocks. The detached-run regression also creates a still-later
journey to prove it cannot legitimize the detached admission. All 19 focused
channel-content and journey tests passed.

`make test` passed all 1,058 backend tests in 1,607.226 seconds. The architecture
check passed with 209 classified modules and zero exceptions. Removing the
ordering receipt or incorrectly dropping earlier journey ownership was detected
(2/2 selected mutations). All 522 mutation anchors match once and compile.
`git diff --check` passed.

## Existing channel run provenance review, issue 68

An earlier writer could admit a detached channel run whose immutable context had
no journey field. Checking provenance only at new admission did not fence that
run when it later resumed. The new real-SQLite regression reproduced three new
calls after its source journey stopped. It also failed independently for direct
call reservation, late publication and an uncertain run still shown as applicable.

A shared derived-origin check reconstructs ownership from the saved recipient
assessments and original preparation command. Channel load/current inspection and
artifact publication invoke it regardless of the optional saved journey field.
The call journal repeats it before reservation and at the reservation commit
boundary. Existing contexts, run IDs and immutable receipts are preserved; the
late-call recording path remains available and does not grant continuation.

The regression retains an earlier-writer fixture for four positions: queued
resume, reservation from cached inputs, publication after calls completed and
restart with an unknown call. It verifies zero new calls or artifacts after the
stop, historical applicability, the same run on exact replay and the original
unknown-call fence. All 17 focused channel-content and continuation tests passed.

`make test` passed all 1,057 backend tests in 1,659.241 seconds. The architecture
check passed with 209 classified modules and zero exceptions. Independent removal
of the channel load/publication check or the reservation check was detected
(2/2 selected mutations). All 522 existing mutation anchors still match once and
compile. `git diff --check` passed.

## Reassessed contact source ownership review, issue 68

The first provenance fix followed an exact assessment identity. Reassessing a
journey-owned source at a later timestamp produced another identity and could
therefore detach its recipient contexts. The new regression failed before the
fix because a stopped journey's source accepted a fresh assessment command.

Ownership is now derived from each journey's immutable discovery catalogue and
selected source, using the scoped provider-account connection identity. It does
not depend on the mutable assessment timestamp, source version, access alias,
mapping revision or command-binding index. Contact assessment admission rejects
new unbound commands for that owned source. Recipient publication and channel
admission also derive the source ownership when reading older saved assessments
and contexts. No historical rows or schemas are rewritten.

The regression covers reassessment at a later time, a newer source version,
older-writer assessment/context fixtures, zero new generation on rejection and
the unchanged original conversation allowance. As positive controls, standalone
requests on an unowned connection within the same native scope and on the same
connection within a separate organization each produce a review-ready artifact
with three synthetic calls. These controls prevent a blanket ban on standalone
preparation. The 46 focused contact, recipient-context and journey tests passed.

`make test` passed all 1,056 backend tests in 999.072 seconds. The architecture
check passed with 209 classified modules and zero exceptions. Independent removal
of either reassessment admission fencing or downstream source ownership was
detected (2/2 selected mutations). `git diff --check` passed.

## Derived recipient-context provenance review, issue 68

The review reproduced a detached recipient-context key derived from a journey-owned
contact assessment. The previous context publication guard checked only the new
request key; channel admission therefore treated its source as standalone.
The extended real-SQLite regression failed for both active and stopped journeys
before the fix, with `Conflict not raised`.

Recipient context publication now resolves the assessment through scoped immutable
contact receipts and journey bindings. It requires the original bound context
command and its journey's assessment. Channel admission repeats that provenance
check on saved recipient inputs, so contexts persisted by the earlier writer cannot
be used under a fresh standalone generation key. No historical payload is rewritten.
The same regression retains an earlier-writer fixture and checks that rejected
publication/admission adds no context commands, runs, inference receipts or journey
events. Existing exact-key, material-edit and cross-organization checks remain.

`make test` passed all 1,055 tests in 996.201 seconds. `make arch-check` passed
with 209 classified modules and zero exceptions. The focused recipient-context
and journey regression run passed 21 tests. Independent removal of either the
publication guard or the channel provenance lookup was detected by the extended
regression (2/2 selected mutations). `git diff --check` passed.

## Multichannel workspace architecture integration, issue 68

The existing conversational multichannel branch is integrated with merged
architecture and CI-cleanup work through main commit `ff2e1ff`. Sequence message
coordination and progress now live in `application/workspace/service.py`, HTTP
commands in `adapters/http/workspace_server.py`, and construction in bootstrap.
The injected journey factory preserves lazy store construction. Root workspace
and server modules remain forwarding wrappers. The new pure language predicate
lives in the public conversations contract; the checker permits only the named
`difflib.get_close_matches` value helper for fuzzy company matching.

`make test` passed all 1,055 backend tests in 1,018.407 seconds on Python 3.14.
The 17 focused sequence-journey tests passed. The 25 architecture and CI-tool
tests passed, and `make arch-check` classifies 209 modules with zero exceptions.
All 522 mutation anchors match once and produce compilable variants; the selected
company-binding, budget-binding and cancellation-fence mutations were detected
by their target assertions (3/3). This is selected evidence, not a full mutation run.

`make interface-check` passed its build, formatting and all 114 browser cases,
including the six multichannel journey cases. The on-demand boundary command
passed all five cases at integrated commit `512e82d`; its report at
`/private/tmp/iwoca-68-integrated-boundary-evidence` records stable source inputs
and unchanged historical evidence bytes. All generation and engagement effects
in these checks are deterministic and synthetic.

## CI and evidence cleanup, issue 93

The initial proposal repeated the architecture check and eight tests already in
the backend suite. The separate per-PR evidence job has been removed. The existing
fixture lifecycle test now also deletes and rebuilds the verified projection,
replays the original commands in a fresh process, rejects changed inputs and
compares all authoritative rows. The eight regressions remain in backend
discovery and are not repeated by the on-demand evidence command. The original
six-case reports below remain immutable historical records; new evidence runs
contain five cases. The full corpus remains available through `make boundary-check`
for integrated workspace, recovery and architecture changes.

Backend discovery was checked against the original eight fully qualified test
IDs: all eight were present with no discovery errors. The revised five-case
corpus passed in 26.34 seconds locally and retained 18 MB uncompressed at
`/private/tmp/iwoca-93-cleanup-evidence`; the earlier six-case local run took
34.37 seconds. These are single local observations, not CI timing measurements.

In a disposable copy, a synthetic rebuild fault deleted one learning outcome
from an authoritative SQLite store. The previous lifecycle test and the
existing missing-projection rebuild test both passed individually. The extended
lifecycle test failed with `Projection rebuild changed authoritative facts`.
This establishes a difference for that specific fault and those two tests, not
that the complete previous suite misses it or that all other corpus cases are
redundant.

The duplicate source-attribution implementation was consolidated into the
shared helper. The focused attribution and boundary tests passed, as did the
standalone conversational evaluation with 12/12 cases and no live calls. The
updated five-case boundary corpus passed with stable inputs and unchanged
historical report bytes at `/private/tmp/iwoca-93-cleanup-final-evidence`.
`make test` passed all 1,038 backend tests in 919.858 seconds with local loopback
access. `make arch-check` passed with 205 classified modules and zero exceptions.

## Offline hostname lookup guard review, issue 93

The review identified that the offline audit guard counted connections and
`getaddrinfo`, but omitted forward/reverse hostname resolution and name-info
lookups. The guard now also records and denies `socket.gethostbyname`,
`socket.gethostbyaddr` and `socket.getnameinfo`. Python uses the first event for
both forward lookup functions; direct `_socket` aliases and `getfqdn` are covered
by the underlying audited resolver event. See the
[Python socket audit contract](https://docs.python.org/3.14/library/socket.html).

The existing caught-network regression now exercises nine real API operations
in both direct and nested interpreters, including a child that replaces
`PYTHONPATH`. A second audit hook prevents actual DNS/network activity if the
evidence guard misses an event. Only the evidence guard's `RuntimeError` is
caught; an escaped operation fails independently before reaching a resolver.
The original guard failed 14 of the 18 cases; the corrected guard passes all 18.
Each caught attempt is logged exactly once and makes an otherwise valid report
fail grading. Removing any one of the three new event families was detected by
a behavioral assertion, with no import/setup failure counted as detection.

The 36 focused evidence/checker/CI-tool tests passed. `make arch-check` passed
with 205 modules and zero exceptions. The six-case native corpus passed under
the updated guard, with stable evaluated inputs and unchanged historical bytes.
The [follow-up JSON](evaluations/issue-93-hostname-guard-results.json) and
[summary](evaluations/issue-93-hostname-guard-evidence.md) are separate artifacts;
the earlier #93 reports retain their original bytes. The full retained bundle is
`/private/tmp/iwoca-93-hostname-evidence`. Its source fingerprint is
`cda037421ca1067a8b441a5837879ff806110f8322e46e5702406069b554e866` on the uncommitted #93 branch.

Commands: `make boundary-check BOUNDARY_OUTPUT=/private/tmp/iwoca-93-hostname-evidence`,
`PYTHONPATH=src:tests python3 -m unittest test_boundary_evaluation test_architecture
test_conversational_evaluation test_ci_tools -v`, `make test`, and `make arch-check`.
`make test` passed all 1,038 backend tests in 928.183 seconds. Final whitespace
checks and all report fingerprints passed. Frontend, HTTP and product code are
unchanged, so the prior 108-case interface result
remains the applicable browser evidence. No DNS query, live inference or external
effect was required to reproduce or fix this finding.

## Hexagonal migration closure, issue 93

The branch starts at merged #92 (`1c88b42`, PR #103). Before changes, four smoke
cases passed in 17.461 seconds: real HTTP actions/artifacts, acceptance replay
after partial workspace acknowledgement, the draft-commit crash/restart lifecycle
and saved-plan completion projection. The existing evaluation worktree was left
unchanged. Only its bounded source-attribution helper was ported from unmerged
#23; its browser runner, product edits and historical reports were not imported.

### Confirmed integrated contract

`exceptions: []` is now mandatory, not merely the current migration count. Even
an exact former exception assigned to #90-#93 fails. Production roles, business
dependency directions and legitimate forwarding wrapper roles are unchanged.
All import/re-export/classification/cycle diagnostics are unconditional. Existing
independent fixtures retain harmful-import, wildcard/alias, implicit package-init,
cycle, unclassified-file and wrapper-bypass probes. The former exception-acceptance
tests now prove that the closed migration cannot be reopened through metadata.

| Interaction exercised | Authoritative observation and independent oracle |
| --- | --- |
| Compatibility model workflow, revision and amendment | Ten fake dispatches match ten inference journal rows. Exact replay and inspection add no calls. Existing #25 oracles bind subject, preferences, population, budget, simulated acceptance and mature learning. |
| Verified draft commit, acknowledgement loss and projection rebuild | The original hard-exit fixture retains one draft operation and one accepted job, zero inference, 379 complete outcomes and unchanged restored bytes. Supported offline CLI rebuild followed by new-process handoff/finalization replay preserves every authoritative row. Changed exact inputs fail. |
| Uncertain inference, stop and fresh process | One fake failed dispatch remains one used reservation; a fresh interpreter creates no campaign or new dispatch and preserves the complete authoritative snapshot. |
| Two profile identities and historical CLI replay | iwoca and Fielddesk each conserve 100 inputs, 24 exclusions, 70 mailed and six controls at 5,950 pence. Distinct draft/manifests replay without any database change; changed inputs fail without approval or execution. |
| Native sequence effect and fresh process | Current merged contact/recipient/channel fixtures produce one simulation, two enrollments, six planned steps and two initial dispatches. Replay returns the same receipt without submission and preserves all rows, including sequence review/approval records. Template generation's nine recorded calls are deterministic fixture calls, not live inference. |
| Existing session, acceptance, authority and legacy boundaries | Eight named regression oracles cover frozen model settings, expired/foreign handles and original binding recovery; acceptance commit before partial acknowledgement; projection commit/lookup replay; expired review/reviewer authority; legacy v2 cutoff and original serialization. All eight run in a fresh process, with no skipped target accepted. |

The original finite six-case matrix preceded the current five-case
[integrated evidence contract](hexagonal-boundaries.md). Each case was mandatory
and unique. Grading independently checks the stated counts, distinct identities,
fresh process IDs, artifact hashes and current effect/authority observations.
Missing cases, success-only flags, altered counts, source/history drift and even
caught network attempts fail. An inherited network audit hook remains active in
nested children whose fixtures replace `PYTHONPATH`. These are local synthetic
control observations, not model quality, provider delivery or customer outcomes.

### Attributable published evidence

The [JSON report](evaluations/issue-93-boundary-results.json) and
[run summary](evaluations/issue-93-boundary-evidence.md) retain all six passing
cases, eight nested regressions and hashes of per-case stores, manifests and logs.
The complete local bundle was retained at `/private/tmp/iwoca-93-verified-evidence`;
the originally proposed CI job would have uploaded the same format on failure.
The repository summaries do not embed the full SQLite stores.

This is explicitly an uncommitted evaluated revision: `evaluated_commit` is null,
base is `1c88b42a639b43fcc2107bbfb5d549d4d508ac62`, and 352 actual source/configuration/
fixture/frontend/CI/operating inputs have per-file hashes. The aggregate source
fingerprint is `d27a50c85d27c565d99d95c15dfb1df36d251ceb6b0c1d9e2b84914ee0c7417d`. Inputs were stable through execution. All ten
previous committed evaluation artifacts retain their exact original bytes.
The new reports were published separately and no earlier report was regenerated.

The existing complete conversational evaluator also passed 12/12 cases, with
zero false acceptances, zero planner/infrastructure failures and stable inputs.
Its shared input hashes match this six-case run. Its supplementary local report
is `/private/tmp/iwoca-93-conversation-corpus-verified.json`.

Executed commands:

```sh
make boundary-check BOUNDARY_OUTPUT=/private/tmp/iwoca-93-verified-evidence
python3 scripts/evaluate_conversational_agent.py --output /private/tmp/iwoca-93-conversation-corpus-verified.json
make test
make arch-check
make interface-check
```

`make test` passed all 1,038 backend tests in 923.091 seconds on Python 3.14.3,
including real SQLite, process restarts and HTTP lifecycle checks. The 36 focused
checker/evaluator/CI-tool tests passed. All nine selected fixture, projection,
replay and exact-subject mutations were detected; all five closed-ledger,
false-success, source/history drift and caught-network mutations were detected
by behavioral assertions, not fixture/import failures. All 513 existing
catalogue anchors match once and their mutated sources compile. The architecture
gate reports 205 modules and zero exceptions. `make interface-check` passed the
frontend build, formatting and all 108 Chromium cases in 6.6 minutes, after the
backend run. No browser case was skipped or accepted through a retry. Final
tracked and new-file whitespace checks passed.

### Applicable evidence and limits

The consumer map in `docs/hexagonal-boundaries.md` gives #60/#68/#69/#70/#74/#77
precise reusable fixtures, commands and restrictions. This closes the architecture
migration, not those product issues or #23. No hosted identity, real CRM, OAuth,
live outbound transport, held-out semantic quality, multi-worker execution or
exactly-once remote delivery is established. Compatibility stores, verified
fixture execution and inspection-only restores remain distinct. Approval, model
budgets, admission, lease/stop fencing and counted-outcome policy were not changed.

## Workspace directory boundaries, issue 92

The feature branch starts from merged #91 (`d48bbe7`, PR #102). Before changing
code, three post-merge smoke cases passed: real HTTP actions and artifacts,
fresh-process acceptance replay after a partial acknowledgement, and the offline
fixture journey restarting after draft commit. These are local synthetic checks;
no live provider call or external dispatch was executed.

| Protected outcome | Evidence | Boundary and limit |
| --- | --- | --- |
| Directory moves retain workspace behavior | 82 of 83 original workspace members retain identical AST bodies across the service and view owners; the conversation projection changes its read order as described below. The existing 132-case HTTP, workspace, recovery, grounding and report-command selection passes. | AST comparison supports relocation review; behavioral suites remain the authority for observable effects. |
| HTTP remains an inbound adapter | Its transport role rejects SQLite and bootstrap imports at the new path; existing real HTTP cases retain Host/token/Origin, path/body limits, fixed scope and exact-subject downloads. | Trusted loopback service with one worker, not hosted authentication. |
| Startup owns lock and worker lifetime | Existing in-flight inference shutdown and second-server tests pass. A new actual-socket recovery-failure case verifies immediate root reuse and a stopped worker after close. | The root lock remains held until handlers and scheduler drain. No deployment topology change. |
| Compatibility names cannot become reverse dependencies | Independently authored wrapper fixtures reject imports from application, adapters and bootstrap, reject composition imports inside wrappers and reject executable wrapper behavior. | Supported `python -m` names forward to canonical entrypoints. The static gate is not an execution sandbox. |
| Offline storage failures keep their command contract | Four CLI cases trigger an actual SQLite missing-table error and observe exit status 2 with each command's existing guidance, without a traceback. Existing fresh-process checkpoint, projection and migration tests remain in place. | SQLite exception handling stays in its adapter; command startup handles the neutral storage error. |
| Pure domain policy keeps its owner | Review validators resolve to pure creative policy and schema modules. The contact adapter uses an explicit public policy export. | No mixed inference file is relabeled as domain. Report output is bootstrap-injected. |
| Relocation preserves mutation oracles | All 512 existing mutation anchors and the new completion-order probe match once and their mutated sources compile. Relocated probes retain their original harmful changes and tests. | This audit alone does not establish detection; targeted executions are recorded below. |

A browser failure exposed a pre-existing projection interleaving: campaign rows
were captured before action progress observed review completion. The response
could report no pending continuation but omit the just-published case mapping,
which stopped browser polling. The conversation projection now samples actions
before campaign rows. The saved-plan SQLite/restart test publishes the exact
completed mapping between those reads. It failed before the fix with a missing
case and passes after it. The new mutation reverses the read order without
changing the behavioral oracle. No task, approval or model-call rule changed.

`make test` passed all 1,033 backend tests on Python 3.14.3 with loopback access
in 1,945.027 seconds. The architecture gate passes with 205 modules and zero
temporary exceptions. All 24 focused architecture, recovery-error and startup
cases passed; all 13 supported launch commands returned help successfully.
All nine targeted harmful mutations were detected, including the new
completion-order probe. All 513 catalogue targets match once and compile.

The saved-plan browser case passed three repetitions after its deterministic
projection fix. A separate navigation case was still preparing when its default
five-second assertion expired; its wait now uses the existing ten-second
preparation bound used by the other journeys, retaining every state and
navigation assertion. Three navigation repetitions passed. An artifact-revision
wait also expired when both browser partitions and the backend suite competed
locally; its trace recorded successful revision completion. It passed unchanged
when the first browser partition ran after the backend suite. Build and format
checks pass. Final interface verification passed all 108 distinct browser cases
across the supported two partitions: 49 in the isolated first partition and 59
in the second. The first used `make interface-check BROWSER_SHARD=1
BROWSER_SHARDS=2`; the second used `BROWSER_SHARD=2 BROWSER_SHARDS=2 pnpm --dir
frontend test` against the same source and verified build. No case was skipped
or accepted through a retry. No live or paid model call was executed.

## Architecture review follow-up: transport imports and current main (#89)

The transport role previously escaped external infrastructure checks. Extending
the independent import matrices reproduced 24 failures: three asyncio cases,
thirteen alternate infrastructure spellings and eight protocol-specific negative
controls. These include native storage, provider SDKs, client HTTP imports and
whole-server-module or helper-module re-exports. Legitimate named HTTP server
classes, static-asset helpers, URL parsing and lifecycle coordination remain
accepted. Transport now uses the same external-import gate with only its explicit
protocol/startup allowances. The inventory and 31 temporary exceptions are unchanged.
No transport implementation or business rules were changed for this follow-up.

The feature branch was fast-forwarded from `cc61aa8` to `cd3d638`, incorporating
the four reviewed-later commits, including sequence-review material reuse and
CI support/gate changes. A named stash backup preserved the uncommitted work;
applying it restored the six production import-normalization edits and untracked
policy byte-for-byte. All current-main validation ledger lines were retained.
Compatibility evidence below covers this combined updated-base worktree, not
only the earlier branch base. The updated CI still runs the architecture gate
and discovers its regression tests on supported Python versions.

Verification on 16 November 2026: all 20 focused architecture tests passed.
The required full `make test` run on base `cd3d638` plus the restored feature
changes passed all 1,018 backend tests on Python 3.14 with loopback access in
1,176.192 seconds. This includes the newer sequence-review and CI-tool regression
cases, real SQLite, fresh processes and HTTP transport behavior. `make arch-check`
and `git diff --check` passed with 170 classifications and the same 31 temporary
exceptions. The frontend interface suite was not rerun because no frontend or
transport implementation changed. No live model/provider calls were made.

## Architecture review follow-up: unpacking and alternate imports (#89)

The second review's two gaps reproduced independently. Six tuple/list, nested,
starred and chained unpacking cases rebind a previously pure public export to a
service in fresh Python processes, while the old checker still accepts the pure
consumer. Sixty alternate infrastructure imports also passed: twelve native
socket/SQLite, OS/process, foreign-function, filesystem, worker, logging,
command-submodule and deserialization spellings across five restricted roles.
The corrected pre-fix regression run reported all sixty-six failures.

A related alias-retargeting probe also passed the old checker even though the
export retained a service after its source name was rebound to a pure value.
The converse pure-value control was falsely rejected. The independent fresh-
process assertions distinguish the actual retained objects.

Unpacking now invalidates every stored name in the target. Simple assignments
capture bindings, including local declarations, at assignment time; subsequent
source-name reassignments cannot change the recorded origin. Unaffected exports
still resolve normally. Standard-library membership no longer grants access:
core and entry-point roles use explicit exact-module and named-value allowances.
This rejects low-level aliases and undeclared submodules without adding another
denylist. Package from-imports cannot load undeclared children such as json.tool;
five extra spelling probes reproduced that bypass before named-export checks.
Mixed io/uuid namespaces require named value imports. Six existing
StringIO callers now use the identical named class; campaign rules, storage,
approval, learning and historical artifact formats are unchanged. The production
inventory remains 170 modules with the same 31 temporary exceptions.

Verification on 16 November 2026: the required full `make test` run passed all
1,017 backend tests on Python 3.14 with loopback access in 1,336.121 seconds,
including real SQLite, fresh-process, historical-artifact and HTTP checks. The
final captured-binding refinement separately passed all 19 focused architecture
tests. AST comparison against the branch base confirmed that the six production
files differ only in equivalent StringIO import/name normalization. `make
arch-check` and `git diff --check` passed with the same 170 classifications and
31 dependency exceptions. No frontend or transport behavior was changed; the
frontend interface suite was not rerun. No live model/provider calls were made.

## Architecture review follow-up: package initialization and asyncio (#89)

Both reported gaps reproduced before the fix. Three nested-submodule import
forms passed the checker although fresh Python processes failed with a partially
initialized module error: absolute import, relative symbol import and import
from the parent package. Fifteen asyncio import cases passed across application,
workflow, port, public-API and entry-point roles, including aliases and subprocess
submodules. The regression run reported all eighteen failures before the fix.

The initialization graph now includes target parent packages that Python must
initialize outside the importer's already-entered ancestor chain. Existing parent
packages are not given artificial back edges. A positive fixture proves that a
package initializer can import a child that imports a sibling, both through the
checker and in a fresh Python process. Asyncio is classified as infrastructure;
core/application imports are rejected while the same adapter imports remain
permitted. The production inventory and its 31 temporary exceptions are unchanged.
No domain behavior, data schema, authority or provider call was changed.

Verification on 16 November 2026: all 17 focused architecture tests passed.
The required full `make test` run then passed all 1,015 backend tests on Python
3.14 with loopback access in 1,926.800 seconds, including real SQLite, fresh-process
and HTTP regressions. `make arch-check` and `git diff --check` passed with the
same 170 production classifications and 31 recorded dependency exceptions.
No frontend implementation changed, so `make interface-check` was not required.
No live model/provider calls were made.

## Complete production architecture inventory (#89)

The static architecture gate now covers all 170 production modules through an
explicit role inventory, including supporting pure files and all root utilities.
Named public export origins, declared business dependencies, layer direction,
infrastructure imports, eager module initialization cycles and all package
cycles are checked without executing product code. New/unclassified or removed
files, unknown targets and ambiguous file/package names fail classification.

The independent regression fixtures exercise pure public values beside services,
relative/re-export aliases and cycles, supporting-domain imports, forbidden
SQLite/provider/bootstrap/entry-point dependencies, allowed adapter validators,
and exact exception counts. A subprocess check proves a forbidden dependency
returns a nonzero command status and its removal returns success. Production
source and authority/storage behavior are unchanged by this tooling slice.

The initial reviewed baseline had 31 temporary dependency exceptions. After the
#90 extraction, 28 remain: fifteen assigned to #91 and thirteen to #92. An exception binds one module, rule,
target and exact occurrence count, with a reason/removal issue. With the reviewed
ledger, new/substituted dependencies, increased occurrence counts, duplicate or
wildcard entries and stale exceptions are rejected. No baseline is silently
regenerated. #93 owns their complete removal. Inventory/policy changes
remain reviewable inputs, not self-proving architecture evidence.

This gate does not prove transaction atomicity, effect authority or arbitrary
Python behavior. Deferred intra-adapter imports are not eager initialization
cycles. Real SQLite, process-restart and HTTP regressions remain the behavioral
oracles.

Verification: the required `make test` run passed all 1,011 discovered backend
cases on Python 3.14 with loopback access in 1,470.701 seconds. The final focused
architecture rerun passed all 14 tests, including 33 forbidden-dependency examples
and the fresh-process CLI check, after checker/schema refinements. `make arch-check`
and `git diff --check` passed. Existing CI already runs these checks; no new CI
job is needed. No frontend/HTTP implementation changed, so `make interface-check`
was not required. No live model/provider behavior is claimed.

## Workspace control-store boundary, issue 90

The control-store extraction leaves schema and ownership unchanged. The facade
uses `WorkspaceControlStore`; only its SQLite adapter opens connections or
executes compatibility-journal SQL. Bootstrap provides that port and preserves
lazy construction of the existing application-owned environment service. The
three #90 architecture exceptions are removed, with no replacement exceptions.
`ContextManager` is admitted as a pure typing contract for storage-error
translation; this admits no effectful contextlib infrastructure.

| Invariant | Behavioral regression evidence | Limit |
| --- | --- | --- |
| Draft and follow-up admission are all-or-nothing | `test_workspace_control.py` injects a trigger failure on each request-mapping insert and asserts that neither mapping nor session survives; exact retries retain the original session. | Compatibility and domain stores still have independent commits. |
| Report-clock advancement binds command admission | A command-insert trigger fault leaves the stored clock unchanged and no pending request. Exact replay after completion does not advance time; changed fingerprints and foreign organizations are rejected. | This port stores legacy metadata; verified clock authority stays in the application store. |
| Concurrent admission binds one exact input | Two independent connections race different fingerprints for the same session/request; one session and matching mapping survive and the other request conflicts. | The HTTP server still intentionally has one worker per root. |
| Lost control acknowledgement does not repeat acceptance | The existing conversation handoff test now injects failure in the extracted completion operation after domain acceptance. A fresh process replays the original receipt after a later conversation edit, with one acceptance event. | Replay reconciles through domain receipts; metadata alone is not current approval. |
| Historical identities and projections stay separate | Adapter replay preserves original creation time and journal identity across a fresh process. Projection upserts preserve request hashes and expose corrupt payloads to the existing tolerant filter. Existing authority/projection tests cover loss, poisoning and interrupted projection writes. | No authority/schema migration is introduced. |
| Storage failure remains recoverable and scoped | Trigger/storage faults become `WorkspaceStorageUnavailable`; value/authority errors and interrupts propagate unchanged. A restored table yields the original record. Foreign-scope case/session/command writes fail; blocker keys remain organization-scoped. | Existing domain adapters retain their own recovery contracts. |
| Control transactions end before provider work | The existing mocked-model workspace test opens a real immediate SQLite writer during every provider call. It completes six calls and leaves generated copy unreviewed. | This is an offline effect-boundary probe, not evidence of live provider behavior. |

Raw SQL corruption fixtures moved to a test-only helper, preserving existing
legacy, projection, ancestry, checkpoint, revision and execution regressions.
The saved-plan stop mutation probe now removes the domain fence around the
named admission call, so it continues to test the same commit boundary.

Verification: `make test` passed all 1,026 backend cases on Python 3.14.3
with loopback access in 1,411.473 seconds. The final focused reruns passed the
nine control-store/provider-lock cases and both strengthened checkpoint and
monitoring storage-recovery cases. `make arch-check` passed with 175 classified
modules and 28 remaining exceptions. The affected saved-plan stop mutation was
detected (1/1). `make interface-check` passed the build, formatting check and all
108 browser cases. `git diff --check` and whitespace checks for all seven new
files passed. No live or paid model calls were made.

The branch incorporates main's single-Python CI, monitoring-test and contact
identity reconstruction follow-ups. After the final rebase, all 43 focused
contact, control-store and workspace tests passed, both changed monitoring
browser cases passed, and both affected provider-account and saved-plan stop
mutations were detected. Architecture and whitespace checks also passed. The
full backend and browser totals above refer to the implementation before those
upstream follow-ups; those complete suites were not repeated after the rebase.

### Command-identity mutation target after extraction

PR #99's first CI run passed both backend shards and both browser shards, but
mutation shard 2 stopped at `workspace-command-identity`: its source replacement
still expected the pre-extraction double-quoted dictionary key. The live guard
uses a single-quoted key. Updating the mutation's exact source target preserves
its original change (`if False`) and behavioral oracle: reusing a completed
command key for another action must raise a conflict and cannot advance the
fixture clock or create beliefs. No production behavior or mutation criterion
changes.

The stale-target failure was reproduced independently before the fix. Afterwards,
all 511 catalogue targets matched exactly once and their mutated sources compiled.
The command-identity mutant was detected by the existing workspace regression;
all five focused CI-tool and command-reuse tests passed. The architecture and
whitespace checks passed. This source/compilation audit validates experiment
setup; it is not a claim that all 511 mutants were executed in that audit.

## Workspace composition boundary, issue 91

The branch starts from merged #90 (`05f7d9a`). The documented offline smoke
slice passed all three cases on that merge before implementation: real HTTP
actions/artifacts, fresh-process acceptance replay and the restartable offline
fixture journey. CI already runs on `main`; no extra post-merge workflow or live
provider call is introduced.

`build_workspace` now supplies all facade collaborators. Provider sessions live
in the model adapter, preparation continuation in its workflow host, campaign
use cases in the campaign workflow, and CLI dispatch in an injected command
handler. HTTP transport is separate from startup, so its role still rejects
bootstrap/provider wiring. Fifteen #91 dependency exceptions and the obsolete
workspace constructor root-guard exception are removed. Twelve #92 exceptions
remain; there are no new exceptions or weakened dependency rules.

| Protected outcome | Evidence and failure boundary | Limit |
| --- | --- | --- |
| Construction and fixture work consume no model calls | An injected gateway factory stays unused through construction/listing/fixture preparation; explicit model preparation makes six mocked calls and remains unapproved. | Offline mock-provider evidence, not a live inference claim. |
| Restart cannot repeat a completed generation | A fresh Python process replays the same model campaign with a gateway factory that fails on any construction; the exact subject is retained. Existing interrupted/uncertain reservation tests remain. | No automatic retry of uncertain paid work is introduced. |
| Ephemeral provider scope remains bounded | Existing browser preparation tests now inject sessions at composition and retain exact frozen model/caps across reconnect. New clock-controlled tests reject expiry at 300 seconds and foreign handles, preserve the original binding after reconnect, and reject the 33rd live connection without revoking the first tab. | The server still supports one worker per root. |
| Current configuration cannot rewrite historical context | Asset loading is deferred to new work. Existing historical-plan/action tests resume with current catalogue reads made unavailable; frozen admissions remain usable. | New requests continue to require current supported assets and freshness. |
| Consent, store identity and environment authority keep their owners | Existing preparation, authority, stop/edit, projection-loss and HTTP guard regressions use real SQLite through the new factory/host. Model/key tests inject bootstrap or adapter factories rather than concrete providers inside use cases. | Existing verified execution remains paused apart from explicit offline fixtures. |
| Relocation cannot silently invalidate mutation evidence | All 511 mutation targets still match once and their mutated sources compile. Four relocated guards retain the same harmful change and behavioral oracle. | Source/compilation checks alone do not establish mutant detection. |

Verification: `make test` passed all 1,029 backend tests on Python 3.14.3
with loopback access in 1,276.083 seconds. `make interface-check` passed the build,
formatting check and all 108 browser cases. The two missing/restored-configuration
browser cases passed again after the final shared CLI/workspace credential
factory update. All eight affected mutation probes were detected; all 511
catalogue targets matched once and their mutated sources compiled. The final
architecture check passed with 181 modules and 12 remaining exceptions.
`git diff --check` and whitespace checks for all eight new files passed. The
three-case smoke on merged #90 passed before implementation. No live or paid
model calls were made.

Publishing verification after rebasing onto #100/#101: the two reusable fixture
setups retain their isolated database/model copies and now inject through the
bootstrap boundary. All 103 focused conversation-action, copy-revision, contact,
CI-tool and workspace-composition cases passed. All nine affected mutation
probes, including the new exact-payload contact-source probe, were detected.
All 512 catalogue targets match once and compile; architecture and whitespace
checks passed. The full backend/browser totals above were established before
those upstream CI/performance changes and were not repeated after the rebase.

## Final sequence authority time follow-up

Review of `137db62` found that `authorize` discarded the successful readiness
report, then checked approval lifetime before the final evidence-epoch and
reviewer lookups. The complete readiness interval could expire after the report
returned while the approval itself remained within its longer lifetime.

Authorization now retains that exact report, completes the epoch and reviewer
checks, then evaluates both approval lifetime and the report's complete evidence
interval at one final authority-check timestamp. It cannot replace a bounded
report with its earlier positive status. This check remains inside each caller's
existing transaction, with no schema, subject or approval-receipt changes.

The existing full-basis SQLite regression now also crosses the interval end
after the report returns, during the final epoch lookup and during the final
reviewer lookup. It covers all five existing evidence variants, including
controls, and asserts that authorization fails without durable changes. All
fifteen added fault cases failed before the fix and passed afterwards. Readiness
and approval remain valid immediately before each exclusive boundary. No new
test methods or fixture populations were added for this follow-up.

The CI cost and coverage assessment is recorded separately in
[test-suite performance](test-suite-performance.md). `make test` passed all 994
backend tests on Python 3.14 with loopback access, including all sixteen
sequence-review tests and the HTTP tests. The successful full run took 1,470
seconds and recorded timings for all 994 cases. The two new authority mutation
probes were detected; the complete mutation portfolio was not rerun.
`make arch-check` and `git diff --check` passed. No live provider or model calls
were made, and no frontend or schema changes were introduced.

## Complete readiness time basis follow-up

Review of `04587b7` found that the final expiry check covered the sequence and
selected payloads but omitted indirect evidence used by complete readiness.
Before this fix, real SQLite regressions reproduced false readiness when a
non-selected contact's permission, an unused bundle recipient's manifest or an
omitted fact expired after its checker had passed. Selected payload bounds were
still valid. The original sequence and selected-payload expiry checks remain.

Campaigns and creative now expose their own pure readiness time boundaries.
They cover complete contact snapshots, permissions and pressure evidence,
including the ninety-day pressure-coverage threshold; recipient manifests and
all their facts; and UTC product review dates. The SQLite composition gathers
these boundaries within the same conservative organization scope as the frozen
evidence basis. Reviews binds a validity interval to the exact subject, starting
before any checker runs and ending at the next future boundary. The report and
the final operator projection require that interval to remain current. Missing,
malformed or substituted interval metadata withholds readiness, as does an
unavailable boundary checker.

The new regression covers non-selected permission and pressure evidence,
control-only populations, unused bundle recipients and omitted facts. For each
case it checks readiness immediately before expiry, actual invalidity at the
exclusive end, and expiry during campaign validation or later approval lookup
through both `view` and `preview` (twenty late-output cases). Saved summaries
are rejected when validation crosses the boundary. A separate case proves that
fresh complete validation can succeed after an irrelevant historical source
boundary passes. Pure domain checks exercise pressure coverage becoming current
and inclusive UTC product review dates. Existing tests now require valid
interval proof and reject missing, malformed, unbound or unavailable proof.

These changes add no schema or persisted artifact fields. Historical proposal,
subject, approval, content and receipt bytes remain immutable. Runtime and
frontend behavior are unchanged. Read-only checks on the retained database
written by the prior sequence implementation preserved every row across all 79
tables, with identical before/after digests and exact saved proposal bytes.
Its preview was ready before expiry and withheld substantive content at expiry.
All seven new mutation probes were detected. They independently remove contact
evidence, manifest or omitted-fact boundaries, bypass final interval expiry or
required interval proof, and alter the pressure-coverage or product-calendar
boundary. The prior mutation portfolio was not rerun.

`make test` passed all 994 backend tests on Python 3.14 with loopback access,
including all 16 sequence-review tests and the HTTP tests previously blocked by
the sandbox. `make arch-check` and `git diff --check` passed. No live provider or
model calls were made, and no frontend files changed.

## Review-readiness expiry follow-up

Review of `128cf72` found that the last campaign check could pass before expiry
and return after it, leaving a positive report stamped at an expired time.
The additional approval checks limited effect admission but did not repair the
operator-facing report or summary. The new real SQLite regression reproduced
that false readiness and the stale projection timestamp before the fix.

Campaigns now owns a pure evaluation-time check of the frozen sequence end and
every materialized payload's known evidence validity bound. Reviews applies it
at the report's final evaluation timestamp, preserving any earlier failed,
unknown or unevaluated required check. The operator view refreshes that timestamp
after approval inspection, then builds or withholds substantive output. A shorter
approval lifetime is checked at that same timestamp without treating otherwise
current content as unready for accountable review.

The bounded regression covers both sequence and frozen-evidence expiry, at the
exact exclusive end, after campaign validation and during the later approval
lookup, through both `view` and `preview` (eight late-output cases). It also
checks readiness just before each boundary, rejection of a saved summary when
validation crosses expiry, and the shorter-approval distinction. Durable row
counts remain unchanged. No schema, historical subject, approval receipt,
proposal or content bytes are rewritten. Generic runtime and frontend behavior
are unchanged.

All 13 sequence-review tests passed, and the focused final regression passed
with its before-boundary and shorter-approval assertions. All five new expiry
mutation probes were detected, covering removal of the final window check,
inclusive sequence/evidence ends, missing projection-time refresh and stale
approval validity. The prior full mutation portfolio was not rerun. Read-only
preview checks on the retained historical database preserved every row across
all 79 tables, verified by identical before/after digests.

`make test` passed all 991 backend tests on Python 3.14 with loopback access,
including the HTTP tests that could not start in the review sandbox.
`make arch-check` and `git diff --check` passed. No live provider/model calls
or frontend changes were introduced.

## Exact multichannel review, issue #67

Confirmed boundary: the standalone synthetic sequence API now requires a new
exact approval before new effects. This includes direct store calls, restart and
continuation. Existing proposal, content, dispatch and observation bytes are not
rewritten or granted approval. The original postal purpose stays separate.
See [sequence review](sequence-review.md) for the operational contract.

| Invariant | Independent authority and failure evidence |
| --- | --- |
| Complete validation | Reviews declares five required checks. Tests independently enumerate all five and all four nonpassing/omitted states, plus five requirement downgrades. A checker crash must withhold both sequence output and summary and prevent a decision/start. |
| Exact subjects and permissions | Audience/source contracts, current creative reconstruction and campaign reconstruction attest identities, purpose, both channels, assignments/controls, all payloads, sender/provider account/scope, limits, schedule and stops. Tests reject other proposals, missing approval, praise/confidence/skill/report references, changed sender/account/profile and changed materialized bytes. |
| Current approval | Real SQLite exercises revocation, later rejection, expiry and reviewer disable/re-enable. A source-pack change and restoration retains a newer evidence epoch, so the original subject and summary remain stale. Fresh review can authorize unchanged work under the new epoch. |
| Commit fencing | Faults after decision write and enrollment writes leave no partial decisions, bindings, enrollment, event or command receipt. Expiry during approval/reservation rolls back authority. Revocation during transport retains a provider observation while blocking completion and subsequent calls. Existing sequence lease, stop, unknown-effect and concurrent reservation tests remain. |
| Truthful output | The operator output validator rejects extra praise, invented population/cost facts, omitted counts and another subject. Rehashed content or absent inference observations cannot replace validation. Diagnostics remain available when substantive content is withheld. |
| History and recovery | Schema-21 migration failure is atomic; successful repeated migration preserves every prior row and the admission cutoff. Schema-21 inspection refuses new effects. Unapproved historical simulations cannot reserve another step. Approved strategies resume in another process without repeating effects; controls receive no steps or charges. |

The evidence model is bounded to installed synthetic sources, recorded offline
inference, exact local actor administration and a single local SQLite store.
The causal clusters are subject/evidence/permission identity; reviewer,
expiry/revocation and effect commit; durable command/receipt/restart; and
validation/projection truth. There is no distributed-provider oracle or live
model-quality claim. Organization-wide evidence invalidation is conservative;
new evidence or an objection can invalidate the full exact population's
approval, including unaffected pending members.

The 12 new review tests passed on Python 3.11 and Python 3.14. The focused
Python 3.14 rerun also confirmed explicit cleanup of test inspection connections. The 45-test checkpoint,
reconciliation and legacy migration selection passed on Python 3.14, as did
eight historical schema/CLI fixture tests. The broader run first exposed stale
schema caps in checkpoint and legacy readers, and old-schema fixture builders
that accidentally applied the new migration. Those readers now accept schema
22 and validate the new review tables; historical fixture builders still create
their original schemas and retain their preservation/rollback assertions.

A differential corpus against merged #84 matched all 17 selected artifact and
catalogue digests across both profiles, including legacy postal content,
profile proposals, contact assessments, decisions, contexts and channel
rewrites. A database actually written by the previous sequence binary retained
every row across all 73 pre-existing tables after upgrade. The new binary read
its schema-21 sequence before migration; the previous binary rejected schema
22 without migrating it. CLI preview and historical inspection passed, and CLI
start without an explicit approval flag was rejected. No frontend files changed.

All 32 selected sequence mutation probes were detected: ten new review probes
and the 22 existing sequence probes. They exercise step authority, expiry at
reservation commit, independent required membership, unknown-check handling,
evidence-epoch restoration, superseding decisions, revocation, exact proposal
binding, operator truth and the existing synthetic lifecycle boundaries. Early
probe attempts hit their wall-time bounds under parallel verification; those
were not counted as detections and the remaining probes were rerun to explicit
test failures with bounded longer deadlines. The complete mutation portfolio
was not rerun.

`make test` passed all 990 backend tests on Python 3.14 with loopback access.
The focused 12-test review rerun passed after the test connection cleanup;
`make arch-check` and `git diff --check` passed. No live model or provider calls
were made, and no interface check was required because frontend files are
unchanged. These results cover the modeled local synthetic boundaries, not
live-provider or distributed execution.

## Sequence objection merge-history follow-up

Review of `552a684` found that engagement objections matched exact native IDs,
so a surviving contact or account could escape an earlier objection after a
merge. The regressions failed before the fix: a new proposal was admitted after
a transitive contact merge, and an account survivor's pending steps remained
pending after a late objection against the original account.

The SQLite composition now resolves native constraints through audiences'
public `related_identities` function and organization-scoped immutable contact
history. Proposal checks, step admission/commit checks and immediate pending-step
propagation use the same ancestry semantics. Engagements' pure stop policy
matches against those resolved sets; neither execution targets nor permission
grants are inherited through a merge. Historical objection subjects, proposals,
enrollments, intents and accepted observations retain their original bytes.
No schema or approval-purpose change is required.

Real SQLite cases cover a two-hop contact merge under a new connection alias,
a fresh interpreter replay, and account objections both before and after the
merge. They verify that an independently current survivor cannot produce a new
proposal, that existing work is stopped, that another provider's same local
native IDs remain unrelated, and that the saved history is unchanged. Four new
mutation probes separately remove contact ancestry, account ancestry, pending
propagation and execution admission. All 22 selected sequence probes were
detected. The 43-test sequence/contact selection passed on Python 3.11, 3.12 and
3.13. The fresh-interpreter case also passed standard test discovery on Python
3.11 through 3.14 with explicit application/fixture import paths. `make test`
passed all 978 backend tests on Python 3.14 with loopback access, after correcting
that test-harness import setup. `make arch-check` and `git diff --check` passed.
The full mutation portfolio was not rerun. Frontend files are unchanged.

## Multichannel sequence simulation, issue #66

Confirmed boundary: a trusted local agent/operator prepares an immutable
campaign sequence from current #63 assignments and #65 content, then explicitly
starts a synthetic engagement simulation. Campaigns owns selection, controls,
cadences, budgets and proposal identity. Engagements owns pure step/stop policy,
enrollments, effect observations and operational accounting. Its application
depends on store/transport ports; bootstrap wires the installed synthetic
adapters. Runtime and the existing postal approval purpose are unchanged.

| Protected outcome | Independent authority and observable evidence |
| --- | --- |
| Frozen experiment membership | The saved audience decision is reconstructed against current contact evidence. Both profiles exercise A/B cadences with two native account units; a separate control case retains enrollment with no step or charge. Consistent account substitution across all content stages is rejected. |
| Exact complete proposal | All initial email, human task and follow-up content is bound to its recipient/account, source connection, synthetic sender/assignee, schedule, costs and stop scope. Missing/wrong channel material, insufficient budget/capacity and schedules beyond known material validity fail before publication. |
| Scoped, bounded simulation | Concurrent starts preserve one simulation per proposal and one enrollment per frozen unit. Concurrent claims submit two distinct initial effects, never the same step twice. Changed request inputs or provider configuration cannot reinterpret a saved command or pending effect. |
| No uncertain repeats | Real SQLite and fresh-process replay preserve effect identities and make no duplicate submissions. Crash after reservation, timeout, partial acceptance and lost acknowledgement after a recorded receipt remain explicit uncertainty. Dependent calls cannot bypass an uncertain email result. |
| Authority at reservation and commit | Current channel evidence, scope, stops, expiry and the lease are checked before transport and again at result commit. Faults after reservation/result writes expire the lease or add a stop; transition/audit writes roll back. Provider observations survive independently without granting continuation. |
| Applicable stops | Replies pause the configured account's pending work while another account can continue. Objections stop that native scope and block fresh proposals containing it. Stop, reply and eligibility change during transport preserve acceptance as an observation while the step becomes stopped, paused or blocked. A bounce cannot authorize an ineligible call. |
| Truthful observations and accounting | Hand calculations establish 208p maximum cost and six steps/two call tasks for two treatments; controls cost zero. Acceptance does not imply delivery, response or completed calling. Exact provider IDs, allowed event kinds and occurrence times are checked. Duplicate events under new keys do not double count. Two replies for one account yield one responding unit and two response observations. |
| Human execution stays explicit | An accepted task binds a synthetic representative. Follow-up waits for task completion and the read model explains that wait. There is no autonomous voice call, automatic reply or send-time generation. |
| Immutable identity and history | Step inputs and dispatch inputs/receipts have SQLite immutability guards. Claims and receipts are reconstructed against the immutable proposal. Rewrites and cached proposals confer no approval, and no learning cohort or postal handoff is created. |
| Migration, restore and isolation | Schema-20 migration failure rolls back DDL/version while preserving channel artifacts and the legacy admission cutoff. Wrong-organization reads fail. Verified-paused and inspection-only stores refuse new simulation work. Cold restore retains a partially submitted sequence and observations while refusing advancement. |

The bounded lifecycle has twelve modeled edges: pending to dispatching/paused/
stopped/blocked; dispatching to accepted/rejected/partial/unknown/paused/stopped/
blocked; paused to stopped. The SQLite cases exercise these edges, including
in-flight reply and source-change schedules. Thirteen selected resurrection
edges from terminal or paused states are rejected by the public domain policy.
No claim of exhaustive concurrency, provider or deployment coverage follows.

The failure portfolio covers exact membership, controls, coherent native target
substitution, missing content, integer money/capacity bounds, due/expired source
windows, receipt identity/cost substitution, event duplication and contradiction,
provider configuration drift, concurrent starts/claims, process loss, late
acceptance, cancellation/reply/objection/source changes and postwrite faults.
Schema migration/rollback, fresh interpreters and cold backup/restore use real
SQLite. Model inference and real provider behavior are not part of this slice.

Seventeen artifact/catalogue digest comparisons against merged #65 code retain
legacy postal, profile, contact, decision, recipient and email/call/rewrite
content for both companies. Upgrading its schema-20 database preserves all rows
in the 63 original tables. Frontend files, historical exports, skill catalogues
and runtime scheduling code are unchanged.

`make test` passed all 976 backend tests on Python 3.14 with loopback access,
after restarting verification for the final domain-policy extraction. The final
19 sequence tests passed on Python 3.14; the 19-test selection also passed on
Python 3.11, 3.12 and 3.13. Added in-flight stop/source-change and illegal-edge
checks were rerun on all four versions. The initial 20-test lifecycle/architecture
selection and 27-test migration/checkpoint/database selection passed.

All 117 selected harmful mutation probes were detected; the 18 sequence probes
were rerun successfully after the domain-policy extraction. The full 480-case
mutation portfolio was not rerun. `make arch-check` and `git diff --check` passed.
The prior binary rejects schema 21 before migration. No frontend files changed,
so `make interface-check` was not required. These results establish the modeled
synthetic boundaries, not live provider quality or commercial effectiveness.

Residual limits: synthetic transports and observations only; explicit per-proposal
budgets/capacity, not a global production quota; no new sequence approval,
conversation route, real dispatch, authenticated provider ingress, uncertain
provider reconciliation, production retention/deletion or commercial learning.
Different proposals are distinct explicitly requested simulations, not an
implemented production campaign-revision or cumulative-exposure workflow.
Current stops compose with campaign preparation without rewriting audience or
content history. Live policy/data truth and commercial effectiveness remain
unknown.

## Grounded channel content, issue #65

The confirmed path is a trusted local request with one to six current recipient
context keys, frozen creative v5 inputs, bounded offline proposal/screen calls,
code rendering, and an atomic SQLite artifact/task/event commit. The independent
authorities are the exact requested population, current native contact/source
history, reviewed v3 product pack, installed tool contracts and runtime lease.
The screen is advisory. Live-model quality, actual recipient data, delivery,
CRM writes and hosted identity are untested and unimplemented in this slice.

| Protected outcome | Falsifiable invariant and exercised boundary |
| --- | --- |
| Complete exact content | Every intended native recipient has one validated payload and one screen verdict. Maximum batches cover both profiles and channels. Missing the last recipient, foreign facts, invented familiarity and recipient substitution prevent readiness. |
| Grounded wording and safe rendering | Code assembles selected reviewed recipient wording, exact product fact, both qualifications and official CTA. Independent assertions check required text. Commit-time tampering removes a qualification, changes the destination, injects HTML or changes evidence. Literal authored markup is escaped. |
| Honest sparse context | A complete reviewed source with zero facts produces generic content with no invented role, prior interaction or score-as-fact. |
| Distinct source roles | A coordinated, rehashed asset bundle can pass generic asset integrity while demoting recipient evidence to preferences. The channel capability still rejects it. Legacy context versions and skill-added effect tools cannot substitute. New admissions use the existing current, segment-scoped style snapshot rather than preference history, while saved contexts retain frozen guidance. |
| Bounded inference and recovery | Three normal calls or at most five with repair. A rejected or sampled screen cannot pass. Unknown calls are not repeated after restart; worker loss reuses completed observations before publishing once. No provider credential or raw exception reaches the inspection projection. |
| Exact replay and fresh identity | Real SQLite and a fresh process retain the original payload and asset bytes without calls. Changed inputs under the same key fail. Rewrites bind the parent population and receive new identities without approval or outcomes. |
| Current authority at commit | Cancellation or source objection during work prevents publication. Faults after task/event writes expire the lease or add an objection inside the transaction; artifact and success lifecycle writes roll back together. Forged passing results without model receipts cannot publish. |
| Scoped history and paused execution | Wrong-organization reads and preparation fail. Read-only and verified-paused roots cannot start or claim channel work. Stale completed artifacts remain unchanged but are not ready for review. |
| Atomic migration and restore | A real schema-19 migration failure rolls back DDL/version. Upgrade preserves recipient payload bytes and the original legacy admission cutoff. The existing cold-backup test now also preserves channel artifacts and refuses restored work. |

The bounded failure space combines population membership and substitution,
source-role downgrade, wording/qualification/rendering integrity, provider
known/unknown/rejected outcomes, before/after commit faults, lease/stop/source
changes, replay/rewrite, organization and schema/restart/restore state. It does
not establish distributed-worker safety, production retention/deletion, live
extraction, model usefulness or outbound authority. The deterministic screening
fixture is not an independent judge of writing quality.

Compatibility comparison against reviewed #64 head `05b8470` retained ten exact
artifact/catalogue digests: the legacy postal draft and catalogue plus profile,
contact, decision and recipient artifacts for both companies. Opening that
schema-19 store with the new code preserved all rows in its 61 original tables
while advancing to schema 20. Historical files and the original postal skill
catalogue were not restyled or rewritten.

The 93-test content/recipient/contact/strategy/profile selection passed on Python
3.11, 3.12 and 3.13. After the style-memory review correction, the final 16
channel tests passed on Python 3.11 through 3.14, including the additional
source-role and postwrite-objection probes. All 99 selected
harmful mutations were detected across the channel, recipient, strategy,
contact, profile, migration and checkpoint checks, plus the affected fixture
settlement lease check. The full declared mutation portfolio was not rerun.
`make arch-check` passed. `make test` completed all 957 backend tests on Python
3.14 with loopback access. That full run began before the style-memory review
correction; the final 16-test reruns above cover the correction. No frontend
files changed, so `make interface-check` was not required.

## Recipient selected-review provenance follow-up

Review of `76c53ac` found that corroborating observations could select one fact ID
and citation while retaining the first observation's reviewed-mapping reference.
The regression failed before the fix with `review-b` instead of the selected
fact's `review-a`. Selection now reads all output provenance from the chosen
observation. Both source orders, real SQLite publication and new-process replay
retain the fact/review/citation relationship.

New context artifacts use v2 so stored v1 bytes retain their original derivation.
The compatibility test seeds valid prior-writer v1 artifacts independently:
accurate provenance remains currently applicable, while mismatched provenance
stays readable/replayable as historical and cannot validate current assertions.
The same mismatch is rejected in a v2 artifact. No saved row is rewritten and
neither format grants approval or outbound authority.

The 20 recipient tests and `make arch-check` passed. The 77-test recipient/contact/
strategy/profile selection passed on Python 3.11, 3.12 and 3.13. All 85 selected
harmful mutation probes were detected, including the chosen-review regression and
the separation of legacy reconstruction from v2 validation. The full mutation
portfolio was not rerun. `make test` passed all 941 backend tests on Python 3.14
with loopback access. Frontend files and historical campaign artifacts are unchanged.

## Bounded recipient context, issue #64

The confirmed path is a trusted local agent/operator request, current scoped
contact assessment, one installed offline source read, creative-owned selection,
atomic SQLite publication and historical replay/inspection. Source adapters
attest reviewed mappings; raw source prose supplies neither instructions nor
authority. No new model, copy, campaign, review, delivery or learning workflow is
admitted. Live source truth, extraction quality and production data handling are
unknown, not inferred from fixture success.

| Protected outcome | Executable evidence | Independent authority and boundary |
| --- | --- | --- |
| Exact native contact/account receives the facts | Both companies and both supported channels retain the requested native references. Foreign organization, another provider account and coordinated target replacement cannot publish or validate | Current attested contact assessment and independently reconstructed association inside the write transaction |
| A candidate cannot attest its own provenance or population | Rehashed fact replacement, omitted facts and source substitution fail; invalid subject/span packages are rejected. Selected document/excerpt hashes are checked with independent UTF-8 SHA-256 calculations | Frozen installed source manifest, declared package coverage and exact native target; this does not independently establish the semantic truth of a reviewed mapping |
| Current permitted evidence determines usable specificity | Missing, expired source/fact, unreviewed, incomplete, source-use denial, fact-use denial, withdrawn and unknown partitions omit facts and return explicit missingness | Source and per-fact use/freshness, reviewed-mapping reference and independent campaign eligibility, never source instructions or a model score |
| Newer restrictions cannot be erased by version or identity presentation | Equal-time conflicting roles survive omission and regrant; newer observations can resolve them. Another person's newer account evidence fences stale account claims while roles stay contact-specific. Profile/mapping changes preserve a newer withdrawal for the same native subject | Scoped native IDs and greatest observation time with all tied conflicts; history constrains candidates but supplies no copied fact or grant |
| Context stays minimal and bounded | One requested slot does not expose others; fact caps and the exact serialized prompt-data character budget omit whole facts. Reordering permission sets does not create false contradictions | Explicit requested slots and frozen typed guidance, bounded to four facts and 2,000 prompt-data characters |
| Untrusted content cannot become instructions or retained raw text | Injected instructions and credential sentinels across all five document kinds, including cited spans, appear in neither prompt projections, receipts nor stored manifests. A source URL cannot become a retrieval target | Closed reviewed fact vocabulary and fixed rendering; installed source keys only, no arbitrary HTTP, file, credential or effect capability |
| Exact replay freezes guidance and source selection | A new Python process recovers the same context; changed guidance does not retrieve or replace it. Changed source/version/slots/contact/cap conflicts; new keys can use new guidance | Organization/request key, exact canonical explicit inputs and immutable artifact bytes; historical derivation uses original manifests, guidance and time |
| Publication is atomic and current | Objection during retrieval, paused state before commit, objection after write and expiry after write prevent publication. All source, pointer, context and receipt rows roll back; a changed-input two-writer schedule commits one result | Current assessment/source reconstruction and post-write checks under one SQLite writer transaction |
| Provider failure stays observable and bounded | One failed read produces `retrieval_unavailable`, no raw exception and no retry on exact replay | Offline source contract and durable exact receipt; no paid or uncertain external effect is supported |
| Migration and restore preserve authority and history | Real schema-18 migration failure rolls back DDL/version and retains audience bytes and the legacy admission cutoff. Cold backup/restore retains recipient rows and refuses new preparation without changing restored bytes | Schema 19 forward migration and existing verified-paused/inspection-only guards; old binaries reject the new schema |
| Existing artifacts and authority remain separate | Exact factual wording/target checks reject invented statements. Preparation creates no task, model call, campaign, review decision or simulator job. Differential comparisons retain existing campaign/profile/contact/decision artifacts | Separate creative-owned tables and typed contracts; validation and historical receipts confer no approval or execution authority |

The selected interaction clusters are native identity/history/profile lifecycle,
fact/source/use/freshness, untrusted content/projection/retention, and
timeline/replay/store mode. Eighteen new tests exercise real SQLite, fresh Python
processes, a two-writer schedule, controlled source failures and commit-time fault
injection. The existing checkpoint round-trip test now includes recipient context.

Within that bounded model: 4/4 profile/channel combinations retain exact subjects;
5/5 supported document kinds contain injected text without source-body leakage;
9/9 selected unavailable/unsafe-evidence partitions omit specificity; and four
selected publication interleavings reject stale or paused work. These counts do
not establish complete concurrency coverage or live provider/model robustness.

The native-history counter-review reproduced a false current role through the
accepted source/store contracts: an attested profile/mapping change hid a newer
withdrawal under the previous profile. The regression failed before the fix.
History now follows exact native subject IDs across those presentation changes;
neither history collection nor interpretation filters out the earlier constraint.
This distinction matters even when installed fixtures have distinct provider
accounts. Both filtering regressions have independent harmful mutation probes.

Verification on 14 November 2026, based on merged main
`f3c0d5ddee50f583f5f4c5cb7097e3ad0f625ee8`:

- The initial 101-test focused selection and checkpoint round trip passed. The
  final 28-test recipient/initialization/architecture selection passed after the
  native-history fix. An earlier full run was superseded by that fix.
- `make test`: all 939 backend tests passed on Python 3.14 with loopback access.
  `make arch-check` passed. The final 75-test recipient/contact/strategy/profile
  selection passed on Python 3.11, 3.12 and 3.13.
- All 83 selected harmful mutation probes were detected, covering recipient
  context, the preceding foundations and affected migration/checkpoint boundaries.
  The full declared mutation portfolio was not rerun. The exact-request probe
  removes both redundant input-binding checks; removing just one left the other
  protection intact.
- Seven differential comparisons against an isolated merge export matched exact
  digests: the legacy campaign/snapshot/CSVs, both company profile proposals, both
  contact assessments and both audience decisions. Installed configuration and
  historical examples have no diff from the merge.
- Frontend files are unchanged. No real provider, customer data, paid inference,
  recipient or sender was exercised.

Residual scope: no live CRM extraction, semantic classification quality,
personalized-message validation, hosted authentication, production retention or
deletion, provider-side data handling or remote-effect recovery is established.
See [recipient context](recipient-context.md) for the implemented vocabulary,
port contract, retention/redaction expectations and later integration boundary.

## Frozen audience strategies, issue #63

The evidence inventory for this slice inspected the schema-18 contact journal,
source attestation/history, campaign eligibility, current review suppressions,
bootstrap, CLI and checkpoint guards. The confirmed path is: trusted local
operator/agent request, scoped assessment capture, offline adapter results,
campaign constraints, atomic journal publication, historical replay/inspection.
The strategy is an advisory producer, not an authority over eligibility. The
only durable effect is an audiences-owned command receipt. Calibration, real CRM
conformance, remote inference and outbound execution remain unknown or absent.

| Protected outcome | Executable evidence | Authority and commit point |
| --- | --- | --- |
| Exact evidence determines the required population | Rehashed feature truncation, segment substitution, foreign scope and readiness-digest replacement cannot publish | Independently reconstructed current source/profile/report inside the SQLite publication transaction |
| Score meanings cannot substitute | Fit is accepted; requests for propensity, expected value and uplift remain explicit incomplete results without inference. Units, horizons and contrasts are validated | Audiences-owned typed request and installed strategy specification; content identities include configuration |
| Incomplete inference cannot become a selection | Partial categories or scores, duplicate observations, wrong batch/strategy/interpretation, wrong scale, invalid intervals, invented missingness and explicit abstention yield zero allocations | Required batch membership and typed result checks, followed by campaign constraints |
| Provider failure is observable and bounded | Categorization and decision exceptions each save incomplete diagnostics, omit exception text and replay without another attempt | Offline service attempts each stage at most once per call; exact committed receipt prevents replay inference |
| Scores and categories cannot override hard policy | Maximum scores and reclassification still exclude permission denial, contact cap, account cap, unsupported country and current business suppression | Existing campaign eligibility independently supplies allowed contacts; no inference eligibility flag is consumed |
| Budget and assignment stay deterministic | Zero/below-unit/exact-unit budgets, candidate cap and one-person-per-account assertions; swapping strategies changes ranking but preserves account arms | Integer conservative budget and `contact-account-hash/v1` in campaigns; no shared capacity is reserved |
| Scope and exact requests fence duplicates | Foreign organization, contact-command key reuse and changed budget/cost/cap/seed/strategy fail; a two-writer changed-input schedule commits one complete receipt | Organization/request primary key and exact canonical inputs in the immutable contact command journal |
| Current evidence is checked at commit | Objection or source refresh during ranking and an objection or expiry after the journal write prevent publication; rollback retains prior history | Current assessment equality and independently rebuilt batch before and after publication |
| Paused and restored stores cannot gain authority | Sealing during ranking blocks commit. Read-only and restored-marker inspection retain the saved decision while mutations fail without changing database bytes | Existing live-root and verified-store guards, rechecked inside the write transaction |
| Saved results survive restart without renewing authority | Four profile/strategy combinations replay and reproduce both rule outputs and the constrained plan in new Python processes. Stale inspection preserves the original artifact and separately reports inapplicability | Immutable artifact identity, typed deserialization and saved assessment; current evidence is checked separately |
| Historical formats retain their contracts | Existing contact, profile and full backend tests; no changes to installed config, examples, legacy audience/campaign domain, creative or review code from merged main | Additive contracts and schema-18 journal command kind; no migration or historical byte rewrite |

The bounded model contains the eleven invariants above. The selected interaction
clusters are evidence/identity/completeness, score/type/interpretation, hard
policy/budget/account, and timeline/replay/store mode. The thirteen new tests use
real SQLite, independent expected account identities and limits, differential
offline strategies, fresh Python processes, provider fault injection and one
two-writer schedule. They supplement existing source-history and legacy tests.

Measured within that model: 4/4 installed profile/strategy combinations reproduce
after restart; 3/3 unsupported predictive metric contracts remain incomplete;
2/2 inference failure stages and 2/2 partial-result stages produce no allocation;
3/3 result identity edges (batch, strategy, preceding interpretation) reject
substitution. Five selected publication interleavings cover objection, refresh
and sealing during ranking, plus objection and expiry after the write. These
counts are finite selected cases, not exhaustive concurrency or provider proof.

Verification on 14 November 2026, based on merged main
`434d7d8046fcf269b6839dd3648c26fb747f991a`:

- `make test`: all 921 backend tests passed on Python 3.14 with loopback access.
  The 57-test strategy/contact/profile selection also passed on Python 3.11,
  3.12 and 3.13.
- `make arch-check` passed.
- All 43 selected harmful mutation probes were detected: the new strategy probes
  and existing contact/profile probes. The full declared portfolio was not rerun.
- A differential run against an isolated export of the merge retained exact
  artifact digests in 5/5 cases: the legacy campaign (including its snapshot and
  CSVs), both company profile proposals and both contact assessment receipts.
  Installed configuration and historical examples have no diff from that merge.
- Frontend files are unchanged. No real provider, paid inference, recipient or
  sender was exercised.

Residual scope: no ML quality, calibration, causal uplift, remote call recovery,
outbound capacity reservation, repeated-contact allocation, learning admission,
hosted authentication or live sender behavior is claimed. A new uncommitted
offline attempt may repeat after process loss; paid adapters cannot inherit that
recovery policy.

The product is tested at pure-rule, persistence, process, HTTP and browser boundaries. This guide describes the current portfolio rather than the chronology of its construction. The portfolio includes frontend regressions, selected mutation probes and backend tests covering the campaign lifecycle, conversational planning and synthetic preparation. Test counts do not measure overall completeness or production readiness.

## Organization/profile preparation foundation

| Invariant | Offline evidence | Boundary |
| --- | --- | --- |
| A profile changes company/product/taxonomy without changing campaign logic | Two company fixtures use the same planning, copy and campaign services. Independently expected population counts and integer costs reconcile; Fielddesk output contains its fictional product, distinct labels, qualifications and CTA | Unapproved synthetic postal preparation only; no new chat, model, review/handoff or learning capability |
| Reviewed source identity and current freshness bind publication | Exact profile/pack/context identities reject source, fact, qualification, CTA and product substitution. The source port derives the expected synthetic audience identity from frozen request parameters; consistently rehashed replacement rows, metadata and command/plan mismatches are rejected. Expiry or a default-date rollover at the commit boundary rolls back every input. Post-write source/catalogue mutations are rejected before commit | Installed local configuration and the synthetic recipe are the authority; candidate data cannot establish its own provenance. Model screening is not evaluated for fixtures |
| Request replay and concurrent commands cannot duplicate or substitute work | A fresh interpreter replays original CLI inputs with unchanged row counts and artifact identity. Changed requests conflict; concurrent different inputs publish one complete bundle. Expired replay observes history without renewing evidence | Exact original command mapping; no runtime task, inference, approval or simulator effect is created |
| A new proposal cannot downgrade or expand authority | Tests reject legacy campaign/writer/review/model paths, missing profile relations, another tenant, unsupported markets/currencies/channels and unknown profile versions. A newly sealed store and inspection marker prevent new writes | Existing verified-admission and restore fences remain intact; future capabilities need their own contracts |
| Historical identities remain unchanged | Prechange main supplies fixed snapshot, draft and CSV identities. The regression compares exact values and checks legacy source URL parser semantics | Existing v1/v2/v3 contracts and schema cutoff remain authoritative; full existing suites provide additional compatibility coverage |

See [organization profiles](organization-profiles.md) for ownership, supported entry points, replay semantics and the evidence deadline. Focused profile checks use real SQLite and fresh processes.

Verification on 13 November 2026, in the candidate worktree based on `2e1a11b1c46b145e88474d97cfd54a503c58184b`:

- `make test`: 883 tests passed on Python 3.14, including loopback HTTP tests. `make arch-check` passed.
- The 19 profile regressions passed on Python 3.11, 3.12, 3.13 and 3.14. The combined profile/grounding/model/domain/architecture selection passed 54 tests.
- All 24 selected harmful mutations were detected: nine new profile boundaries and 15 existing probes in changed modules. The full declared mutation portfolio was not rerun.
- The unchanged conversational corpus passed 12/12, with zero false acceptances, false rejections, planner failures, infrastructure failures or live calls. Its candidate-source fingerprints remained stable during execution. Reproduce with `PYTHONPATH=src python3 scripts/evaluate_conversational_agent.py --output /tmp/profile-corpus.json`.
- The documented Fielddesk CLI command prepared one unapproved synthetic proposal. Original `examples/` files and `config/iwoca-product-facts-v1.json` have no diff from the baseline; fixed original snapshot/draft/CSV hashes are asserted in `tests/test_profiles.py`.

These checks establish bounded offline behavior. There were no frontend changes, provider calls, real recipients or delivery effects; interface checks and live quality evaluation were outside this slice.

### Review remediation for #61

Review of `a0245a6` exposed a provenance gap: a caller could replace synthetic rows and consistently rehash the audience, plan and draft. Internal consistency alone did not establish recipe origin. Regression probes reproduced publication of the replacement before the fix.

Publication now obtains the expected audience identity through the injected `ProfileFixtureAudience` port using frozen organization, taxonomy, size, seed and date. It rebuilds the plan and brief from the frozen command and validates both before and after writes. Rejections roll back the entire bundle. Historical reads and replay retain their original identities and grant no new authority.

Three additional real-SQLite regressions cover coordinated row/metadata replacement, command/plan/brief disagreement, and date ownership including a rollover between validation and commit. The expiry regression freezes the audience date and requires the product-evidence expiry error, so the independent date fence cannot mask a missing freshness check. Three additional harmful mutations remove the recipe, command and brief checks separately.

Post-review verification on 13 November 2026, against the candidate based on `a0245a6`:

- `make test`: 886 backend tests passed with loopback access. `make arch-check` passed.
- The final 57-test focused selection passed, including the strengthened expiry assertion. All 22 profile tests passed on Python 3.11 through 3.14.
- All 27 selected harmful mutations were detected, including the isolated product-freshness probe and the three new publication checks. The full declared mutation portfolio was not rerun.
- The unchanged conversational corpus passed 12/12 with stable candidate-source fingerprints, zero false acceptances/rejections, zero planner/infrastructure failures and zero live calls.
- A differential run against an isolated `a0245a6` export retained both companies' exact draft, audience and CSV identities. Historical examples, installed profile configuration and the original fact pack have no diff from that commit.

## Scoped contact evidence foundation

| Protected outcome | Executable evidence | Boundary |
| --- | --- | --- |
| The exact native person/account remains scoped | Two companies and two provider accounts reuse native IDs without collision; native object type differs from mapped role. Mapping revisions and connection aliases cannot rename a native subject or erase objections. A known person cannot be reclassified as an account | Recorded synthetic sources only; logical connection key and mapping version retain access/interpretation provenance |
| A candidate cannot attest its own source or completeness | Rehashed destination replacement fails installed-source checks. Ambiguous/missing associations, incomplete pagination, missing/unknown/expired permission and incomplete/inconsistent pressure cannot claim complete readiness. Complete refreshes retain known identities or explicit tombstones; observation times cannot move backward | Source configuration is trusted local composition. Fixture conformance does not attest real CRM data, law or sender permission |
| Hard eligibility stays independent of inference | Purpose/channel separation, permission denial, isolated contact cap, account cap and current review-owned business suppression determine eligibility. Known deleted contacts remain excluded without unnecessary retrieval | Campaign-owned preparation policy; no model/strategy or outbound-capacity reservation is installed |
| Current objections and lifecycle fence new work | Channel-specific and all-channel objections, merge ancestry, deleted accounts, stale alternate connections, newer native permission/shared-pressure evidence and forbidden resurrection invalidate fresh applicability. Saved assessments and receipts retain original bytes | No automatic retargeting, inherited permission, correction/re-consent or release authority |
| Atomic observations survive races and retries | Fresh-process CLI replay preserves exact request inputs and row counts; new keys reuse identical immutable assessments. Concurrent changed requests publish one complete result. A post-write objection or final-check expiry rolls back sources, current pointer, assessment and receipt | Readiness observations grant no task, campaign, approval or external-effect authority |
| Migration and restore preserve existing contracts | Real schema-17 failure rolls back DDL/version while retaining original audience bytes and schema-v3 admissions. The existing cold-backup test now retains contact rows, inspects through the CLI and refuses mutations without changing restored bytes | Schema 18 is a forward migration. Older binaries reject it; verified-paused stores gain no contact mutation capability |

See [contact evidence](contact-evidence.md) for owners, ports, operating commands, supported scope and fixed fixture deadlines. Existing v1/v2/v3 artifacts and profile-draft identities remain unchanged; the new snapshot/readiness formats live in separate tables.

Verification on 13 November 2026, in the candidate worktree based on merged main `05ee6351eae14a5ab65ccad3ca0117b09f794bc1`:

- `make test`: 905 backend tests passed on Python 3.14 with loopback access. `make arch-check` passed.
- The final 61-test focused selection passed, including all 19 contact tests and the existing profile, initialization, architecture and cold-checkpoint boundaries. Contact tests passed on Python 3.11, 3.12, 3.13 and 3.14.
- All 68 selected harmful mutations were detected, covering the new contact checks, profile authority and affected migration/execution/checkpoint boundaries. The full declared mutation portfolio was not rerun.
- The unchanged conversational corpus passed 12/12 with stable candidate-source fingerprints, zero false acceptances/rejections, zero planner/infrastructure failures and zero live calls.
- An isolated merged-main comparison retained exact legacy/profile audience, draft and CSV identities. Historical examples, installed profile files and the original fact pack have no diff. The documented CLI prepared and inspected three synthetic contacts across two account units, with no authority.
- Old-schema fixture setup now explicitly omits the v18 migration when constructing historical v4/v11 stores; their original migration, rollback and cutoff assertions remain in place and pass. No tests were removed. The complete final run supersedes interrupted development runs.

These are bounded offline observations. There were no frontend changes, live CRM reads, model spending, real recipients or outbound effects; interface checks and live provider/quality evaluation were outside this slice.

### Pressure evidence review remediation

Review of `9ee774c` found that a higher source version could replace a newer pressure observation with an older lower count. Regression probes reproduced both successful backward refresh and restored false readiness before the fix.

Fresh refreshes now reject pressure observations older than any known observation for that source/contact, including after an intervening omission. Conflict evaluation selects pressure evidence by observation time and retains disagreements at equal times. This also fences valid historical v18 rows admitted by the previous writer without rewriting them. A genuinely newer observation can restore readiness, so an old high count does not become a permanent exclusion.

Two real-SQLite regressions cover rejection/rollback, omission, older and equal-time evidence, fresh-process inspection, unchanged source/assessment bytes and recovery with newer evidence. Three mutation probes independently remove the import fence, chronological selection and equal-time retention.

Post-review verification on 13 November 2026, against the candidate based on `9ee774c`:

- `make test`: 907 backend tests passed with loopback access. `make arch-check` passed.
- The 63-test focused selection passed. All 21 contact tests passed on Python 3.11 through 3.14.
- All 71 selected harmful mutations were detected, including the three new pressure-evidence probes. The full declared mutation portfolio was not rerun.
- The unchanged conversational corpus passed 12/12 with stable candidate-source fingerprints, zero false acceptances/rejections, zero planner/infrastructure failures and zero live calls.
- An isolated comparison against `9ee774c` retained exact receipts and saved assessment payloads for all 12 installed company/version/email-or-call cases. Historical examples and configuration files have no diff. No schema migration or historical data rewrite was introduced.

### Equal-time permission review remediation

Re-review of `57db051` found the parallel permission case: a later source version could replace a same-time denial or differing expiry with a grant and restore false readiness. A real-SQLite regression reproduced that result through the attested source/store API before the fix.

Permission reconciliation now retains every distinct observation at the greatest observed time for each source/contact/channel/purpose. Later versions and omissions cannot erase equal-time disagreement. The regression covers fresh-process inspection, unchanged saved history, channel/provider-account isolation and recovery with genuinely newer evidence. Two mutation probes remove chronological selection or equal-time retention; existing pressure probes now target their specific bucket to keep both boundaries independently testable.

Post-review verification on 13 November 2026, against the candidate based on `57db051`:

- `make test`: 908 backend tests passed with loopback access. `make arch-check` passed.
- The 64-test focused selection passed. All 22 contact tests passed on Python 3.11 through 3.14.
- All 73 selected harmful mutations were detected, including the new permission chronology and equal-time conflict probes. The full declared mutation portfolio was not rerun.
- The unchanged conversational corpus passed 12/12 with stable candidate-source fingerprints, zero false acceptances/rejections, zero planner/infrastructure failures and zero live calls.
- An isolated `57db051` comparison retained exact receipts and saved payloads for all 12 installed company/version/email-or-call cases. Historical examples and configuration have no diff. The fix introduces no schema migration or historical data rewrite.

## Reproduce the checks

```sh
make test
make arch-check
make mutation-check
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend exec playwright install chromium
make interface-check
```

Python checks require Python 3.11 or later; the interface requires Node 22.12+ and pnpm 10.33+. CI uses Python 3.11 through 3.14 and a Node interface job. Browser and HTTP tests need permission to bind loopback ports. Offline tests do not use provider credit. Live inference evaluations are separate and opt-in.

## Invariant ledger

| Protected outcome | Executable evidence | Boundary of the evidence |
| --- | --- | --- |
| Requested product, channel, country and objective stay attached to the campaign | Versioned literal requirements freeze native messages at admission. Real SQLite rejects a supported replacement, removed scope, foreign rehashed source and mismatched delivery headers. Source changes during publication, approval and acceptance roll back every write; stale requests cannot authorize follow-ups. Browser checks cover visible defaults, mobile reload and four zero-call unsupported outcomes | Finite literal vocabulary and explicit labels, not general semantic understanding. Historical formats and receipts remain immutable. See [scope contract](requested-campaign-scope.md) and the [unchanged issue-25 corpus](evaluations/issue-25-requested-scope.md). The preserved scope run improved from 6/12 to 10/12; the [budget clarification run](evaluations/issue-25-budget-clarification.md) reaches 12/12 with zero false acceptances. Typed routing and final acceptance reconciliation keep issue 25 open |
| Unscoped historical requests cannot authorize fresh follow-ups | Real legacy-format fixtures with no scope fields exercise unsupported frozen/current source text, missing native plans, restart, saved-receipt replay and unchanged artifact bytes. Read-time validation prevents new contexts, snapshots or tasks; source changes during proposal receipt, child publication, approval and acceptance writes roll back. A supported legacy child can learn and propose again, but an amended original conversation blocks the next generation and saved-proposal admission | The native accepted experiment and scoped ancestry, not the presence of a new JSON field, decide which request to validate. Historical learning views and exact receipt replay remain observations. Paid inference stays paused and restores remain inspection-only |
| Ambiguous, relative and explicitly non-total budgets require a confirmed absolute user total | Real SQLite checks a completed zero-call clarification for rates with possessive recipients, grouped quantities or intervening financial link words and partial amounts as well as ambiguous totals, valid totals with unrelated delivery/reporting rates or an explicit recipient-delivery purpose, fresh validation of valid historical delivery totals, later explicit retractions after delivery wording, a later clean whole-campaign confirmation, exact question/revision bindings, concurrent and conflicting replies, post-write message/question rollback, old-policy question reply/replay, a completion interleaved with projection reads, and fresh-process continuation. Mobile browser tests drop committed reply and preparation responses and retain one revision, one campaign, exact budget evidence and shared usage | Literal GBP evidence remains authoritative. A failed planner does not count as clarification. Missing-budget model questions retain their existing inference path; no live semantic-quality claim. See [budget clarification](budget-clarification.md) |
| Evaluation evidence needs meaningful outcomes and identifiable executed inputs | Real SQLite rejects an unrelated zero-call failure as a passing negative and distinguishes clarification from exhausted validation. Temporary Git repositories change source, fixtures and configuration without moving HEAD, including hidden edits; file hashes record those inputs, and an observed change during execution invalidates an otherwise passing report. Six regressions and two focused harmful variants cover these boundaries | A generic failure never establishes successful scope enforcement or clarification. The v2 report identifies actual input contents and Git differences; before/after checks do not claim immunity to deliberate transient tampering by a local administrator |
| Local checkpoints preserve scoped history and remain inspection-only | SQLite row comparisons across application stores and the legacy journal, committed WAL data, fresh-process status, worker/reservation, approval and learning fences | Trusted local operator and current checkout. Post-checkpoint spend, revocation and simulator effects remain unknown |
| A partial, mixed, corrupt or active checkpoint cannot publish | Recomputed manifests with an unrelated registered store or an inconsistent SQLite index, corrupt source and staged indexes, missing files, digest changes, aliases, sidecars, active root/SQLite locks, running and reserved work, staged-copy damage and killed copy processes | Local POSIX publication and selected failure schedules. No power-loss test or live provider claim |
| Later checkpoint evidence stays scoped and grants no execution authority | Compare real snapshots with later call receipts, a stop, a revocation and simulated acceptance. Reject substituted planner ownership, unavailable, replaced, older or conflicting history, and missing audit or command receipts for retained acceptance. Fresh processes leave both snapshots unchanged and a restored worker remains blocked | Trusted checkpoint IDs and local recorded history. External billing, delivery and completeness remain unknown |
| Fresh verified fixtures execute within their original admission and lease | Complete conversation preparation, exact-subject approval, simulated acceptance and synthetic learning. Kill a process after draft publication, reclaim the same task and verify one draft operation. Exercise grant rollback, stale publication, stop and replay, SQL inference fences and restored-root inspection | Two allowlisted fixture workflows in a fresh local root. Paid inference and restored execution stay paused |
| Fixture publication and settlement retain their authority through commit | SQLite triggers advance the clock during draft, settlement and failure writes and verify rollback. An alternate operation ID and substituted creative catalogue are rejected before publication. An exact-subject operator refresh preserves the copy and rolls back its draft if the review event fails | Local execution clock and scoped SQLite transactions |
| Simulated delivery binds the exact approval through dispatch | Real SQLite checks that the saved mailing bytes match the approved artifact. Substituting provider copy, recipient identity, demo address, arm or creative ID after preparation blocks dispatch. Revoking approval between transactions or changing suppression authority during settlement also blocks the effect. An original-format pending draft recovers the same dispatch identity after reopening | Local postal simulator and exact approved draft |
| Simulated delivery results survive recovery with their original population | Partial acceptance partitions every intended recipient and retains the control count. It blocks cohort opening. Rejection creates no accepted job. A dropped acknowledgement after commit replays the same native result in a fresh process after approval expiry, with one audit event and one accepted job | Local commit and read-back with synthetic recipient statuses |
| Partial simulated delivery remains visible in workspace review and history | A browser fixture records partial acceptance in SQLite and checks the original recipient and control counts in conversation review, campaign review and the collapsed history event. Approval, further handoff and copy revision controls are unavailable. Chat status reports the same provider result | Review and history display the saved partial outcome |
| Recorded provider reports preserve independent synthetic counts | Real SQLite rejects missing or substituted pages, job and assignment substitutions, invalid watermarks and reused report identities. Duplicate JSON fields at the report, page, event and outcome levels leave the store untouched. A fresh CLI process retries the complete snapshot. Duplicate events, cumulative and late reports preserve one observation per assignment. A final snapshot missing controls blocks finalization, an audit failure rolls back all writes, and an inspection-only copy remains byte-identical | Local file snapshots for an exact accepted simulated job. Coverage comes from the frozen cohort, independent of the page count or watermark |
| Imported provider reports retain their observation evidence | Snapshot write failure rolls back the receipt and outcomes. Inspection rejects altered pages and cross-organization lookups. An exact older report can attach pages without changing its original receipt. A fresh CLI process reads a verified checkpoint's saved event after the external file is deleted, while imports into the restore remain blocked | Normalized pages are checked against the original import digest. They are read separately from the activity summary |
| Ineligible records never enter mailing | Literal 18-record fixture, ordered exclusions, duplicate/suppressed businesses and disjoint counts | Synthetic source completeness and supplied metadata only |
| Population and integer budget reconcile | Hand-written population plus 3 seeds × 3 sizes × 4 budgets = 36 cases | Bounded examples, not general load/marketing effectiveness |
| Controls share selected enrollment | Scores require assignments from the same top-score cohort; controls absent from mailing | Small groups may lack controls; selected cohort is not the whole market |
| Organization scope persists | Wrong-scope reads/writes, acknowledgement, cancellation, exports, review and learning rejected | Trusted local identity, not hosted authentication |
| Artifact comments retain their exact copy target | Real SQLite rejects another conversation, creative or superseded subject. Receipt replay and audit rollback preserve one comment. Browser tests retain copy/audience selection and variant through reload, replay a dropped comment response, reopen the same comment after button or Escape dismissal with fresh consent, and separately confirm the exact native revision | Comments record feedback without inference, approval or a brief edit. The mobile toggle changes presentation |
| Writing preferences need separate confirmation and retain their lifecycle | Real SQLite checks scoped comment provenance and audit, explicit consent, exact-input replay, stale/concurrent correction, immutable versions, retirement, frozen context snapshots and future audience scope. Fresh-process, schema-15 migration/rollback and schema-14/15 checkpoint inspection tests retain history. Browser tests confirm dismissal has no effect and replay a dropped save after reload before correction/retirement | Preferences guide writing only. New contexts use up to three recent active preferences per audience; saved contexts and historical copy stay unchanged. Paid inference stays paused and restores remain inspection-only |
| Preference model projection and snapshot selection preserve confirmed intent | A real copy worker with a fake provider receives confirmed wording without original source feedback; full provenance remains frozen. Real SQLite rejects replacement through either version or request keys with recursive triggers disabled, including upgraded schema-15 stores. Retirement interleavings in campaign and follow-up context assembly select usable authored fallback guidance | No live model-quality claim. Authored fallback is guidance, never outcome evidence; historical audit bytes remain immutable |
| Follow-up hypotheses bind source evidence without inheriting authority | Held-out strong, weak and absent comparisons for both audiences include a B-leading case, small extreme samples, large negative lift, zero trials and missing controls. Real SQLite rejects substituted hypotheses/evidence/contexts and preserves zero-response uncertainty. Frozen model inputs, restart replay, desktop/mobile inspection and a fresh verified fixture checkpoint/restore retain the original proposal | Synthetic, within-cohort evidence only. Pooled rates remain descriptive; prior parameters, preferences and model scores add no observations. Paid inference stays paused, restored roots stay inspection-only and new copy still needs review |
| Follow-up framing and outcomes stay tied to original evidence and the proposed audience | Grounded and fixture source hooks reach frozen model inputs; the historical product block is excluded after active facts change. SQLite response, timestamp, assignment, membership, missing-row and same-count replacement corruptions block source reads and commit without creating contexts or receipts. Validly hashed contexts for another snapshot, wrong model version or input population count are rejected | Historical receipts remain immutable observations. Source hooks grant no product-fact authority. Reconciliation is repeated inside the save transaction; new inference stays behind existing consent and pause controls |
| Follow-up cohorts retain their accepted experiment provenance | Real SQLite checks 17 missing, foreign-scope, altered receipt/index and draft cases at source read and save. Deleting the accepted job leaves no foreign-key violations but blocks a new proposal, including in a fresh process. Failed checks create no contexts, commands or model calls; historical proposal replay and a repaired source fixture still work | Rebuilds the cohort from the scoped accepted job and verified draft inside each transaction. Historical acceptance is evidence of simulated enrollment, not current approval or delivery authority |
| Request identities bind exact inputs | Restart replay, concurrent admission, reordered equivalent commands and changed-input conflicts | Local storage contracts; future providers need their own idempotency |
| Stale workers cannot commit | Lease expiry boundary, token replacement, cancellation and attempt caps | Selected local schedules; no multi-node operational claim |
| Domain work survives lost task receipts | Artifact commits before task receipt; restart retrieves the same operation/artifact | Deterministic local operations only |
| Results and events commit atomically | Forced event-write failures roll back result, lifecycle and authority updates | No disk-full, power-loss or backup-restore guarantee |
| Work/configuration remains resumable | Incompatible worker skipped before claim/recovery; correct worker resumes; finite timestamps/deadlines enforced | Configuration must remain pinned; unknown provider outcomes need investigation |
| Version and content drift fail closed | Changed catalogue, bytes, capability/input downgrade, legacy certificate substitution and unknown schema | No protection against an administrator editing trusted database state |
| Initialization is serialized | Lock before version read, whole-chain migration rollback, process/connection races and bounded WAL-busy retry | Local SQLite behavior, no mixed-version rollback support |
| Module ownership remains enforced | Actual import graph plus nine deliberately invalid imports | Static imports, not malicious reflection/in-process code |
| Inference is bounded and replay-safe | Concurrent reservation, input/output limits, lease/cancellation checks, receipt failure and unknown-outcome fencing | Real charging/availability and provider reconciliation are outside offline tests |
| Product copy binds reviewed evidence | Required text, qualifications, provenance, freshness, paired verdict and changed-copy/pack rejection | Lexical checks and a same-model screen do not establish general claim accuracy |
| Approval binds current authority | Exact subject, policy/evidence/suppression epochs, expiry, reviewer generation, revocation and later rejection | Configured local actors, not independently authenticated humans |
| Acceptance is one local effect | Competing acceptors, suppression ordering, tampering and event-write rollback; receipt replay after expiry | Local simulator, not an external delivery contract |
| Outcomes have an exact denominator | Accepted membership, assignment joins, full explicit coverage, complete-but-immature and closed-incomplete cases | Synthetic attestation, not verified real feed completeness |
| Counts use immutable independent observations | Literal posterior examples, deduplication, conflicting imports, disjoint business membership and concurrent finalizers | Repeated exposures and late corrections are unsupported |
| Memory is a consistent snapshot | Finalization forced between segment reads cannot split frozen context evidence | Local transactional snapshot; future adapters must preserve it |
| Historical replay does not repeat effects | New actor/request observing finalized/opened cohorts retains original receipt, event count and time | Existing historical events are not rewritten |
| Workspace commands recover partial success | Domain commit before metadata loss, request identity before clock advance and current-state receipt observation | Compatibility storage still spans databases; no distributed transaction |
| New selected workspace intent is application-owned | Projection poisoning/loss, process restart, frozen preparation, exact creation mapping, verified domain links and store identity checks | `verified-paused/v1` only; no legacy enrollment or activated rebuild journey |
| Owned simulation time binds an exact command | Real-SQLite insert failure rolls back the clock; changed-input replay, disabled operator, missing cohort and non-finite window probes | Seeded domain facts exercise this boundary, not verified execution activation |
| HTTP transport checks precede effects | Host/token/Origin, absolute-form GET/POST, bounded JSON, static traversal and server-root lock probes | Loopback trusted use, not public-service authentication |
| Browser retries preserve identity | Actual lost/5xx approval responses, interposed rejection, authentication error, field ordering, key migration and storage failure | Pending identities live in the browser session; no cross-device recovery UI |
| Presentation preserves access and history | Exact page width at 390/1440px; saved-preview styles and token isolation; named wordmark at 390/820/1440px | Selected Chromium layouts, not exhaustive browser/accessibility certification |
| Conversation intent survives replay and revision | Scoped SQLite messages, concurrent append and plan admission, process restart, stale browser revision and changed request rejection | Local trusted identity; bounded message history |
| Planning guidance is inspectable and immutable per admission | Changed or unavailable playbook source on replay, restart, scoped read, hash tampering and complete saved snapshot inspection after a purpose change | Bounded local playbooks; no claim of semantic retrieval or independent source verification |
| Brief proposals retain provenance without authority | Literal current GBP budget, supported segment catalogue, forbidden tool and no campaign/review/job writes | Model intent interpretation and clarification quality are not proven by structural validation |
| Planning stays bounded across interruptions | Six admissions per conversation, two calls per request, frozen-context admission recovery, unknown-call fencing, recorded-response replay and cancellation | Fake model responses only; no live planner quality or general semantic compliance claim |
| Late planning cannot replace new intent | A correction during inference makes the completed earlier result historical; changing a conversation invalidates review authority for its prior fixture or model campaign | Synthetic audiences and simulated acceptance only |
| Conversational model copy stays bound to the proposal | Selected-segment generation, exact budget, source context, fixture-downgrade rejection, stale evidence, metadata-loss recovery and uncertain-call fencing | Fake-model contract tests; live evidence recorded separately |
| Conversation edits fence further generation spending and draft creation | Edits from a separate workspace during each of the three copy calls; exact call counts and absence of stored drafts | A call reserved before an edit may still return a recorded observation |
| Terminal generation failures remain actionable | Saved 401 run is exposed through the backend and inspected after browser reload without another generate action | Provider codes are allowlisted; recovery requires an explicit new proposal |
| Uncertain generation remains distinct from definitive rejection | Network failure and interrupted reservation survive restart and lease recovery without a second provider call; browser inspects both saved runs after reload | Reserved and unknown receipts require inspection of the original run; no provider reconciliation is claimed |
| Model-copy spending requires explicit permission | Continuous preparation binds per-request copy consent, refuses replay expansion and stops without consent; legacy proposals retain their explicit generation action | Fake-provider browser and real SQLite tests; model interpretation remains separately evaluated |
| Planning replay cannot dispatch unrelated work | Completed-plan replay with a separate queued conversation; targeted recovery with an unrelated expired lease and wrong organization | Targeted local worker path; general worker draining remains organization-wide |
| Budget corrections do not silently reuse stale amounts | Later unsupported currencies, shorthand, relative edits with valid amounts, ranges and mixed valid/invalid amounts require clarification; explicit new totals remain valid | Pattern-based detection cannot identify every natural-language correction |

| Continuous preparation reuses exact saved work | Duplicate admission, concurrent identical admission, lost coordinator write, lost draft-status write and real-process queued recovery. The browser drops a successful admission response before reload and reaches review with one admission | One local executor; no multi-node scheduling claim |
| Conversation edits stop continuation | Reads and appends during an in-flight planner, edit before a repair call and edit during copy; no later copy/draft or release | An already dispatched provider request cannot be withdrawn |
| Preparation progress grants no authority | One submitted model brief reaches a valid unapproved candidate; approval invalidates after a later message | Synthetic campaigns and simulated delivery only |
| Interrupted work cannot be presented as ordinary failure | Unknown network outcome and interrupted planner/copy reservation remain uncertain on restart, with no additional provider call | No provider-side reconciliation is implemented |
| Progress is a read-only projection | Guarded 202 admission leaves a queued task without calling the worker; browser reload reaches review with one admission and no plan/draft/approve/handoff POST | Background execution requires the local server; direct legacy endpoints remain synchronous |
| Checkpoint polling follows recoverable progress | Real SQLite recovery interleaves with old campaign/progress reads. Exact saved stop receipts keep both ready-progress and cancelled-progress reads pollable until the case appears. An ordinary blocked preparation, even alongside another conversation's stopped checkpoint, cannot claim recovery | Local eventual projection reads; polling grants no approval or inference authority |
| Projection reconstruction grants no authority | Independent snapshots of every application table remain unchanged after inspection, rebuild, process exit and retry; paused workers still dispatch nothing | Registered new-format stores only; no legacy migration or restore activation |
| Legacy projection records remain protected | Opaque preparations, BLOBs, journal identity, unrelated session/command rows and legacy diagnostics survive; a conflicting native request key blocks rebuild | Unreadable files and unsupported layouts are refused rather than replaced |
| Projection writes are atomic and bound to observed inputs | Hard exit before commit rolls back, lost acknowledgement replays, changed source/control records reject commit, stale inspection plans fail and locks release immediately | Supported single-server root lock; fingerprints bind projection inputs, not backup completeness |
| Rebuilt progress discards only owned diagnostics | Exact owned run/revision cache keys are removed while diagnostics for legacy keys in the same organization survive | Current progress and permission come from application journals; cache deletion admits no work |

| Message replay cannot transfer consent to a newer brief | Browser loses an acknowledged message response, another writer appends a correction, reload retries the original identity, and no preparation is admitted for the newer revision | Consent remains bound to the original message receipt revision |
| Staleness cannot hide possible provider charges | Planner and copy timeout/crash after an edit retain both historical status and unresolved journal details across restart; browser checks new and older stale records | No automatic provider reconciliation or uncertain retry |
| Planning cannot outlive its coordinator admission | A rejected coordinator write leaves no plan; three interrupted planning admission boundaries resume in a fresh process without a browser and with unavailable current guidance | Separate stores reconcile through original request IDs and frozen inputs |

## Continuous preparation failure model

Confirmed owners are the conversation revision transaction, runtime task lease, inference reservation journal and exact-subject review transaction. Coordinator state describes continuation, not domain authority. The test portfolio challenges six boundary groups: request/consent identity; scope; source revision; provider uncertainty; partial persistence/restart; and review authority. All six have executable cases in `test_preparations.py`, the HTTP suite and the browser journey. This is a bounded inventory, not exhaustive interaction coverage.

Selected schedules reject a coordinator write before any plan is created and interrupt after coordinator persistence before the plan record, after the plan record before task creation, after task creation before run-ID persistence, after campaign commit before coordinator progress, during planner repair and copy inference, and after an inference reservation without a response. Preparation mutations remove copy consent, misclassify uncertain outcomes, omit interrupted-reservation recovery, remove the planner reservation revision check, hide stale uncertainty or terminal journals, and admit a plan before coordinator persistence. Terminal coordination states are not automatically reactivated. Configuration-blocked recovery currently requires inspection and an explicit revised request or trusted local CLI recovery; the UI has no resume command for that state.

## Targeted copy revision boundaries

The new boundary groups are immutable feedback/consent admission, paid-run identity, copy-only scope, current source authority, publication lease, historical receipt replay and exact displayed browser subjects. Tests cover each group with real SQLite or real-backend browser journeys. The nine added mutations challenge source fencing before paid calls, paid-run binding, the final publication lease check, sibling-letter preservation, approval invalidation at admission, review/progress consistency, blocked-state visibility, per-revision failure isolation and blocker removal before dispatch.

- A request records rejection and its immutable context/receipt/audit atomically. Injected audit failure leaves the previous approval valid and creates no revision.
- The actual original and candidate drafts establish the comparison oracle: snapshot, brief, enrolled population, arm assignments, cost, product selections and sibling text/identity remain fixed. The target identity changes; no learning record or approval transfers.
- Separate writers change the brief, policy/evidence epoch, suppressions, operator authority or original run during inference. Later model calls and publication are blocked. A duplicate paid run cannot reuse another revision's admission.
- Expiry before publication and expiry during candidate validation prevent publication. Recorded generation and publication recover after lost task acknowledgements without duplicate calls or subjects. A fresh process resumes an admitted request without browser state.
- Browser tests cover the complete feedback/review journey, stale approval and feedback dialogs, lost decision acknowledgement, uncertain provider outcomes, reload and mobile overflow at 320px/390px. A read/publication interleaving cannot combine completed metadata with the earlier letters. An unrelated rebuild receipt cannot masquerade as copy publication, and a historical approval dialog disables submission while remaining closable.
- A separate workspace admits a revision between the review and progress reads in real SQLite. The returned packet includes the committed rejection and admission together, even though the subject ID is unchanged. The workspace rechecks the complete transactional review projection, excluding only its read timestamp, and retries a changed projection at most three times before returning a conflict. Reads dispatch no model calls.
- Missing-key and frozen-settings failures remain visibly blocked across workspace reconstruction, preserving the exact admission and any queued tasks without consuming attempts. Restoring configuration resumes the original run. An expired-evidence request with no run cannot starve a later healthy campaign. Browser coverage removes the key after actual backend admission, then checks sanitized guidance and blocker persistence after reload. Uncertain-result tests remain independent of recoverable configuration blockers.
- A gated fake provider holds a resumed request in flight after configuration restoration. Real SQLite reads show the same request running with a reserved call and no saved blocker. The browser observes this progress through polling, then reaches review after the gate opens without another generation submission or a stale charge warning. Terminal timeout and interrupted-reservation tests retain their uncertainty warnings.

These are bounded schedules and fake-model responses. They do not establish semantic success on subjective feedback, live model quality, external delivery or multi-worker readiness.

## Test composition

Pure domain tests use literal expected populations, money and posterior values. Persistence tests use real temporary SQLite databases, controlled clocks, concurrent connections and injected failures. CLI tests cross OS process boundaries to exercise restart, review, export, learning and replay. HTTP tests send real requests to the loopback server. Frontend client tests use the real backend, and Chromium tests inspect the rendered interface.

CI runs the complete backend suite on Python 3.14 in two parallel shards. Standard unittest discovery supplies both shards. Whole modules stay together, and measured module runtimes balance the groups. The first shard also runs the architecture check. Run the same groups locally with `make test-shard SHARD=1` and `make test-shard SHARD=2`. The mutation and browser jobs also use Python 3.14. Other Python versions are not checked in CI. The architecture checker retains its self-test with deliberately forbidden imports.

The mutation command creates temporary source copies and weakens selected enforcement points, including leases, reservations, uncertain-call fencing, retired-workflow admission, timestamp validation, migration locking, review expiry/epochs, cohort maturity/completeness, atomic finalization, snapshot memory, Origin checks, exact-subject binding, planning budget provenance, current-revision projection, conversation scope, targeted execution, stale-budget correction handling and relative-budget recognition. The results apply to the declared probes. They are not a general mutation score. Frontend regressions are reported separately.

The analytic Beta(1,19) quantiles provide an independent check on sampled prior intervals. Count tests verify exact trials/successes and sequential/batch equivalence. This checks calculation behavior; it does not calibrate the prior or turn simulated results into real causal evidence.

## Recorded live model evidence

The [grounding reference](product-grounding.md) records a dated GPT-OSS-120B run and a small eight-variant screening regression. The rubric and regression examples were developed together. Their match rate is not held-out accuracy, and the recorded run is not a fresh claim about current provider pricing, availability or output quality. The exported example remains unreviewed.

## Remaining gaps

There is no asserted line/branch coverage percentage or overall correctness percentage. Selected fault positions and concurrency schedules leave untested interleavings. General semantic claim detection, real data completeness, marketing impact, production authentication, external agency effects, multi-host throughput, disk-full/power-loss behavior, execution from a restored checkpoint, real outcome corrections and repeated-exposure attribution remain outside the demonstrated evidence.

A UI review cannot establish approval correctness, and module unit tests cannot establish restart behavior. Preserve checks at the boundary where each real effect is authorized and persisted as the system evolves.

## Conversational handoff boundary (issue 17)

The approval and simulator transaction remain authoritative. The new chat surface captures the displayed approval and subject, saves the confirmation before command dispatch and uses the existing exact-input API request identity. A simulated acceptance is historical evidence, never authority for another effect. Receipt exports require the exact displayed accepted subject and draft.

- Seven real-backend browser cases cover the offline end-to-end journey, receipt and artifact downloads, historical inspection after a brief edit, mobile overflow at 320px/390px, lost responses before and after commit with reload, and stale confirmations after refresh, revocation, suppression or message append. These cases make no model calls.
- Real SQLite tests cover receipt export before acceptance, wrong subjects, byte-preserved accepted history after a source edit, expiry and disabled reviewer denial. A fresh OS process replays the original handoff after acceptance but before the control acknowledgement is marked complete, producing the same receipt and exactly one acceptance event.
- Existing review tests continue to exercise evidence epochs, candidate integrity, cross-scope approval substitution, acceptance/audit/receipt rollback and transaction ordering. This slice adds no dispatch adapter, learning update, role or approval policy.

The demonstrated topology remains one local server and simulated acceptance. Real delivery, browser storage loss and a production authentication/reconciliation service are outside this evidence.

## Conversational learning boundary (issue 19)

The new surface reuses the Learning view and existing session operations. Chat confirmations bind accepted job/cohort IDs; the facade verifies them against the server-owned session and accepted cohort source before mutation. Legacy workspace payloads remain compatible. Domain cohort membership, maturity, completeness, operator authority, immutable outcomes and atomic finalization remain authoritative.

- Real SQLite tests reject learning before acceptance and reject substituted job/cohort IDs without changing the clock or learning state. Changed request inputs and disabled operators cannot update beliefs.
- Early synthetic responses preserve unknown denominators and leave beliefs/recommendations empty. Complete mature data yields counts summing to the accepted population, including A/B and controls. A later brief edit leaves accepted history usable for learning without authorizing another campaign.
- A fresh OS process replays finalization after the domain commit but before control acknowledgement, preserving the exact projection and one finalization event.
- Four backend browser cases cover the offline lifecycle, posterior/control display, mobile overflow, historical learning after an edit and loss of acknowledged open/observe/finalize responses with reload and exact request replay. No new model request or next experiment is generated.

These are synthetic demonstration results. Real attribution, production calibration, repeated exposure and external feed reconciliation remain outside this slice.

## Follow-up proposal boundary (issue 21)

Ten real-SQLite/fake-provider tests cover finalized-source admission, source and scope substitution, original-mode replay, frozen model context/memory and explicit inference consent, disjoint child enrollment, fresh approval and successful independent cohort opening. Further cases exercise a later allocation/evidence change, a source-stripping publication attempt, exhausted inventory, unknown-call replay and fresh-process preparation. Preparation request IDs bind the parent, proposal, mode and consent in the same control-database transaction as the child session. A restart regression checks replay and rejects reuse for a second valid proposal. The parent cohort and its counts remain unchanged.

Three browser journeys cover proposal-specific generation consent and the finalized offline conversation through proposal inspection and new child approval, exact population disjointness, mobile overflow, reload and a lost acknowledged preparation response. Reading the committed child does not submit another generation. Two added mutation probes weaken population independence and source-brief binding; existing mutation probes continue to cover approval and learning effects.

This establishes the bounded 2,000-record synthetic scenario and selected interleavings. It does not establish real audience inventory, calibrated marketing impact, concurrent hosted operation or remote delivery. Model tests use fake providers and make no live quality claim. The legacy manual follow-up path still has its documented overlap restriction.

## Versioned reasoning assets (issue 25, first slice)

Scoped content bundles bind installed tool schemas, authored skills and exact source hashes/roles in new planning and grounded-copy contexts. Real SQLite and fresh-process tests cover source coverage/content mismatch, foreign scope, tool/schema substitution, invalid skill references, changed current guidance, historical replay without current files, old unannotated tasks and a separately frozen revision skill. Actual base inputs remain exact at revision admission and no asset grants approval. Two declared mutation probes remove installed-schema equality and skill/tool membership checks. These checks establish serialization, provenance and bounded compatibility; they do not establish semantic skill quality or new conversational action execution.

The issue-25 review regressions additionally cover maximum permitted reviewer-memory size at the unchanged 24 KB input budget, complete initial-copy preflight before any paid read, zero-call failure for an oversized submission, original transcript behavior for old unannotated contexts and frozen follow-up preparation with a changed/unavailable current catalogue. Full server metadata is retained while new model-visible copy metadata is compacted through an explicit projection version. Two more mutation probes remove full-envelope preflight and frozen-context reuse.

Legacy copy compatibility also has an exact-input-limit regression with a recorded SQLite read response. The actual legacy request fits while the synthetic exchange is larger; replay must complete with three recorded calls and only one read dispatch. Stable-exchange preflight applies only to the new projection. A declared mutation incorrectly preflights legacy contexts and must be detected.

## Unified readiness report (issue 25, second slice)

Seven required checks compose exact artifact integrity, source-run state, brief provenance, current epochs, evidence freshness, deterministic population/money and copy contracts. The report requires every check to pass; missing/downgraded checks are invalid and unknown results block readiness. Human editorial suitability and real performance remain explicitly unevaluated/unknown. SQLite tests cover stale sources, validator unavailability, exact model/source bindings, read-only restart observations and amendment invalidation. A real-backend browser journey imports a suppression and checks readiness and approval blocking at responsive sizes. Mutation probes remove the required-check gate and coverage check. See [campaign validation](campaign-validation.md) for the observation and authority contract.

## Versioned audience source boundary (issue 26)

Discovery never resolves ambiguity by ordering. Retrieval requires a scoped dataset/version, content checksum and metadata identity. Raw-file integrity is separate from completeness, model provenance, declared population coverage and source freshness. Synthetic source data grants no targeting, approval or delivery authority. Reads make no model calls and create no campaign effects.

Real-file regressions reject changed bytes and metadata, another organization, incomplete or mismatched coverage, expired/future sources, unsafe paths, symlinks, duplicate fields/versions and oversized payloads. Real SQLite checks show that retrieval leaves audiences, runs, decisions and agency jobs unchanged; an explicitly saved immutable snapshot survives a fresh process. Protected loopback API tests verify exact query fields, scope resolution and metadata-only results. Mutation probes remove checksum, manifest matching and source completeness. See [audience catalogue](audience-catalogue.md) for implemented scope and deferred campaign binding.

Verified for the audience-catalogue slice: 298 backend tests, architecture checks, all 59 declared mutation probes and whitespace checks passed. The frontend was unchanged; no live model or external storage call was made.

## Conversation audience selection boundary

The new selection is a revision-bound input decision, not campaign approval. Materialized campaign rows must preserve the independently saved source population and values, allowing only added suppression flags during refresh. The source receipt binds both metadata and decoded snapshot identity; removing or substituting it cannot downgrade a selected campaign to the older generated path.

Real SQLite and process tests cover confirmation before campaign admission, exact-input replay, two valid competing versions, stale revision at commit, transactional rollback of snapshot/selection/receipt, unavailable current files after confirmation, source scope and segment mismatch, combined-segment coverage, targeted copy revision, suppression refresh and separate exact-subject approval. Schema-v7 failure rolls back DDL and the version marker while preserving the original legacy cutoff. Old schema migration tests continue to exercise earlier rollback boundaries.

Freshness tests shorten the audience review window while keeping product evidence valid. One advances twenty seconds across source expiry during a provider call while the lease remains active: no later call or draft is allowed. Separate review tests isolate the audience freshness gate from product expiry. Mutations remove selection-input binding, revision fencing, model-reservation checks, draft binding and review checks and must be detected.

Browser journeys cover source choice on desktop and 320px/390px mobile, original selection after reload, lost confirmation acknowledgement and definitive stale-choice rejection. They inspect actual backend manifests/readiness and confirm that no approval is inherited. No paid inference or remote storage integration is claimed by these fake-provider journeys.

Verified for this slice: 316 backend tests, 55 browser tests, architecture, production build, formatting, whitespace and all 64 declared mutation probes passed. Browser captures cover desktop and 320px/390px mobile. All provider behavior in these checks used fake adapters; no paid model call was made.

## Audience selection review corrections

The original campaign admission binds its sourced or unsourced mode. A later selection for the same conversation revision cannot retroactively invalidate an unsourced campaign or its existing approval. Real SQLite tests approve an unsourced campaign, record a later selection and complete its original handoff. Sourced admissions reject provenance stripping even when the separate selection row is also removed. Legacy preparation progress does not label a later selection as that campaign's confirmed audience.

Selection and inference adapters use composition-root-injected clocks and reread time after acquiring the write lock. Held-lock tests advance twenty seconds across source expiry before allowing each transaction to proceed. Selection leaves no snapshot, selection or command receipt. Inference makes no provider call and creates no reservation. Additional cases cross lease expiry and change the clock to a non-finite value while blocked. The source-expiry case keeps the lease and product evidence valid to isolate the source freshness rule.

Declared mutations remove each locked clock read, the original unsourced-mode preservation and the original sourced-mode binding. Each must be detected by its focused regression. These controlled interleavings do not claim exhaustive scheduling coverage.

Verified after these review corrections: 322 backend tests, architecture and whitespace checks, and all 68 declared mutation probes passed. No frontend files changed in this correction pass; the browser suite was not rerun. No paid model calls were made.

## Final selection and inference commit fences

A clock reading at lock acquisition cannot cover time spent validating or writing. Source confirmation therefore performs a cheap freshness check on its verified manifest at the end of the selection transaction. A newly reserved inference call similarly rechecks finite time, lease expiry and the verified source window after the reservation insert, immediately before transaction commit. No provider call can occur until that transaction returns. Full snapshots are not loaded again by these final deadline checks.

Real SQLite tests advance the clock during selection validation, snapshot serialization and the receipt insert, checking that all snapshot/selection/receipt writes roll back. Separate fake-provider cases advance time during source validation and during the reservation insert, independently crossing the audience deadline or the lease deadline. Product evidence remains valid, and lease-only tests keep the audience window open. All rejected calls leave no journal reservation and dispatch no provider request. A non-finite final clock is rejected; a valid-source/valid-lease control dispatches exactly once. A targeted revision regression checks that its verified source window reaches the shared final reservation fence.

The earlier lock-wait regressions remain. Locked-clock-only mutation probes were replaced with final-clock, final-source, final-lease and revision-deadline propagation probes, since the new final fences also contain the lock-wait failure. This is a bounded set of clock positions and SQL-trigger interleavings, not exhaustive temporal coverage.

Verified after the final-fence corrections: 332 backend tests, architecture and whitespace checks, and all 72 declared mutation probes passed. The correction changes no frontend files; the browser suite was not rerun. All provider tests used fake adapters and made no paid model calls.

## Follow-up action continuity

Inspection is a separate durable operational object, not a brief amendment. Real SQLite tests keep revision, selected source, exact subject and approval unchanged across progress, audience, exclusion and validation questions. A status query completes while a fake copy provider is held in flight, and the original campaign completes without extra copy calls. Answers derive from frozen server observations and retain timestamp and source references across replay and a fresh process.

Amendment confirmation checks the exact action, target, base revision, completed routing result and original task inputs. Its message, revision update, confirmation and command receipt are atomic. Tests reject read-only results, substituted targets, changed frozen text, another scope, stale revisions and conflicting request reuse. Concurrent confirmations advance once; loss after confirmation recovers the original planning identity and copy permission. The model gets no approval or delivery tool.

Routing permits one model call per admitted action and at most twelve model admissions per conversation. Missing configuration preserves the request; an incompatible worker cannot consume it. Inference reservation checks the original action admission and run identity. A stale route cannot dispatch through an internal worker. An interrupted reserved call is cancelled locally on exclusive startup and remains uncertain; a recorded response can replay after a lost task acknowledgement without another provider call. Active reserved calls are presented as in progress rather than falsely terminal or uncertain.

Schema-v8 fault injection rolls back DDL and version changes while preserving selected source and the original legacy cutoff. Browser journeys cover desktop and mobile, inspection without invalidation, explicit amendment, lost action/confirmation responses, stale confirmation and active versus unknown model outcomes. Delayed confirmation responses cannot replace a newly opened chat, including the lost-response reconciliation path. An incompatible routing configuration remains visibly blocked without claiming the task; the original configured worker can resume it. Mutation probes remove replay-input binding, concurrent admission binding, exact confirmation target, action authority, original text binding, routing reservation admission and routing budget. There is no claim of held-out semantic routing accuracy or live-provider quality from these fake-provider checks.

Verified for this slice: 363 backend tests, 66 browser tests, architecture checks, production build, formatting, whitespace and all 79 declared mutation probes passed. Desktop and 320px/390px mobile layouts were checked. Provider tests used fake adapters; no paid model call was made.

## Clarification context in follow-up routing

Routing now freezes the two most recent brief messages and latest completed planner response, including its exact question and result identity. The response records whether it belongs to the current revision. Real SQLite regressions show a budget clarification and short `£600` answer reaching the fake provider together, with no brief change until confirmation. After confirmation, the ordinary planner binds the new budget to the saved answer and waits for audience confirmation. Another case preserves a `yes` answer's original question across request replay, a process restart and an intervening edit; the older question is marked historical and the stale route dispatches no inference.

A boundary case passes two 2,000-character messages and the full planner question through the actual envelope preflight. A golden legacy prompt and recorded receipt survive restart without another call. Mutations remove the question projection and the model-visible dialogue independently. These checks prove context delivery and control continuity with fake providers, not semantic intent accuracy. Handoff browser tests now wait for the visible recorded-approval state before reading its identity, preventing the test from racing the approval command.

Fresh verification after the correction: 367 backend tests, the full 66-test browser run, architecture, production build, formatting, whitespace and all 81 declared mutation probes passed. This includes the handoff test previously reported as flaky. No live model calls were made.

## Router clarification continuity through planning

Dialogue v2 freezes pending clarification and amendment exchanges as well as recent router replies. The exact-subject amendment result carries the source action IDs, user text and recorded agent responses into the displayed confirmation. Real SQLite regressions exercise a mixed £400 change-and-explanation request followed by `Change it`: neither question nor proposal changes approval, then confirmation atomically appends the two displayed user texts and freezes the full exchange for the planner. The new budget cites the carried original request. Both coordinator and direct planner admission preserve the confirmed exchange.

Multiple clarification turns and an unconfirmed proposal retain chronology, so a later explicit £500 correction overrides £400 without concatenating conflicting amounts into one message. Intervening inspection remains observational and cannot supply a £900 budget. The original revision fence and exact-task checks still apply. Confirmation checks carried source admissions and completed outputs in the same transaction; a changed source is rejected. Injecting failure on the final reply rolls back all earlier carried messages, revision changes, confirmation and receipt. Lost continuation after confirmation and process restart preserve one preparation and the final request's copy permission. Confirmation replay observes the original message receipts without appending again.

The model carry limit is four pending change exchanges; exceeding it rejects admission before inference while authored status inspection remains available. Pre-dialogue and dialogue-v1 recorded requests remain replayable without new calls or rewritten artifacts. Browser journeys show the carried original request and clarification before confirmation and preserve exactly one effect after a lost committed response. Mutation probes remove carried context, user-message commitment, source verification, confirmed snapshot propagation, planner visibility, the carry limit and pending-proposal continuity. No live semantic accuracy is claimed from fake-provider tests.

Verified after this correction: 376 backend tests, all 68 browser tests, architecture, production build, formatting, whitespace and all 88 declared mutation probes passed. Carried-request confirmations also stay within 320px and 390px mobile viewports with a long unbroken text input. No paid model calls were made.

## Durable action admission order

Scoped action listing and organization-wide recovery listing use SQLite `rowid` admission order. Wall-clock timestamps remain historical observation data. A controlled-clock SQLite regression admits £400, moves time backwards, admits £500, moves time backwards again and admits the reply. Both listing scopes, frozen router context, the displayed amendment exchange and committed messages preserve admission chronology across restart and replay. The ordinary planner cites £500 as the latest explicit budget. The test failed against timestamp ordering before the correction.

Confirmation rechecks carried source admission order inside its write transaction. A compatibility regression constructs a reversed exchange using the previous timestamp-order producer, then confirms with the corrected consumer. Confirmation rejects it before any brief write and leaves the frozen action, result and message history unchanged. Separate mutations restore timestamp ordering or remove the confirmation sequence fence. No frontend files changed in this correction.

Verified after the ordering correction: 378 backend tests, architecture, whitespace and all 90 declared mutation probes passed. The frontend suite was not rerun for this backend-only correction; its preceding 68-test run remains recorded above. No paid model calls were made.

## Natural-language targeted copy revision

New versioned routing proposes copy-only edits against the current server-owned campaign. It does not change the brief, audience selection, approval or native copy state. Real SQLite tests bind an explicitly named variant, preserve earlier feedback through A/B and segment clarification, reject unsupported fixture targets and recover from the native 500-character feedback limit. A generic campaign-copy checkbox cannot authorize revision: exact confirmation requires the separate boolean five-call permission.

Confirmation, native copy admission, exact-subject rejection, events and command receipts share one transaction. Trigger faults at action confirmation and command receipt insertion roll all of them back, preserving the original approval. The native adapter independently checks the displayed subject, draft, creative and copy preview, and revalidates carried user feedback against its original task. Both facade and direct native admission paths are tested. A wrong result reference, another conversation, changed source feedback, stale subject or reused confirmation key cannot create another effect. Concurrent confirmations and lost-response restart recover one native revision. The native five-call limit, one request per source subject and three-revision case limit remain unchanged.

End-to-end fake-provider revision preserves the sibling's identity and wording, audience, assignments, budget and product wording, then publishes a new unapproved subject. Missing provider configuration remains visibly blocked and restoration resumes the original admission. An uncertain revision stays inspectable without automatic redispatch. Routing reservation now checks its exact admitted capability as well as inputs and run identity. Genuine earlier routing contexts retain their original tool and prompt envelopes for receipt replay.

Browser journeys exercise proposal/consent separation, target clarification, new in-chat review, stale-target rejection, lost committed and uncommitted acknowledgements, unknown outcomes and navigation during a delayed response. A held reload read proves a quick reply cannot create a new chat before the selected conversation loads. Desktop and 320px/390px mobile views were inspected, including document overflow assertions. Mutation probes weaken consent, feedback continuity, result binding, source feedback checks, actual preview attestation, atomic confirmation and routing-capability binding.

Verified for this slice: 399 backend tests, all 76 browser tests, architecture, production build, formatting, whitespace and all 97 declared mutation probes passed. No paid model calls were made. These fake-provider checks establish bounded authority and continuity behavior, not live semantic routing accuracy or marketing performance.

## Copy clarification and independent edit boundaries

New dialogue v4 carries only unanswered copy clarification. Selector-only wording questions survive reload, restart and intervening inspection. A ready proposal closes that feedback chain; a later self-contained target and wording request also starts independently of unresolved feedback. Invalid or overlong feedback resets instead of persisting as a selector. The exact displayed feedback still binds native admission and its separate generation permission.

Five regressions failed against the previous implementation before the correction. Real SQLite tests now exercise `B` followed by `Make it more direct`, a ready formal B edit followed by a casual A edit, a complete replacement of an unresolved request, a new clarification after a ready proposal, and an old cross-target carry rejected at confirmation. Additional cases keep invalid-feedback recovery and a genuine dialogue-v3 recorded request replay intact across task interruption and restart. Frozen legacy results are unchanged; same-target v3 feedback remains confirmable, while an unconfirmed cross-target proposal requires a new edit. Historical confirmation replay grants no new effect.

Browser journeys check both reported sequences through exact feedback display, separate consent and native revision completion. Mutation probes remove selector retention, the ready-proposal boundary, independent restatement and the legacy cross-target fence. Existing approval, source, inference and native revision checks remain in place. No paid model calls were made.

Verification after this correction: the 406-test backend run passed 391 tests and hit sandbox bind restrictions in the 15 HTTP test setups. All 15 HTTP tests then passed with loopback permission. The full 78-test browser suite, architecture check, production build, formatting, whitespace and all 101 declared mutation probes passed. The 27-test targeted copy suite also passed, including the seven new regressions. No live semantic model accuracy is claimed.

## Shared execution allowance and cancellation

The conversation-wide policy counts original inference reservations across planning, routing, campaign copy, targeted revisions and descendant experiments. Real SQLite checks compete for the final allowance slot, replay a recorded response at the exhausted cap, reject another valid conversation substituted into an admitted run, and preserve counts across a fresh process and schema-v9 backfill. Rejected and uncertain calls consume their original slot; late observations do not grant task authority. Cost projections expose metadata coverage and do not claim verified billing.

Cancellation binds an exact revision and idempotency identity. Tests stop held planning and revision providers, verify no additional dispatch or draft publication, retain late or unknown receipts, and recover after admission interruption. Fault injection on the stop receipt rolls back the fence, run/task cancellation and audit. Existing review checkpoints stay intact: stopping alone cannot invalidate approval, and new revision admission after stopping cannot insert a rejection. A new brief clears the current stopped state without resetting the allowance; replay of an earlier stop cannot cancel it. Migration rollback preserves the original legacy cutoff and exact journal bytes.

Browser journeys cover a lost committed stop response, receipt completion after cancellation, fresh audience confirmation for a new brief, unchanged usage across reload, and 320px/390px overflow assertions. The lost-stop-response test holds the fake provider until the browser observes stopped work with a pending response, then releases it and verifies accounting and publication fences. Desktop and mobile screenshots were inspected. Mutation probes weaken shared capacity, original run binding, stop fences, run/task cancellation, stop-receipt persistence, approval preservation and replay at capacity. No paid model calls were made.

Verification: the clean full backend run passed all 422 tests; the full interface check passed all 80 browser tests, production build and formatting. Architecture, whitespace and all 108 declared mutation probes passed. The 15 execution checks also passed after the final ancestry-lookup optimization. Earlier failures came from old-schema fixture setup and a follow-up fixture outside its evidence window; fixtures now preserve the intended historical setup and exercise valid evidence dates without extending production evidence. No live model or billing behavior is claimed.

## Manual descendant ancestry and checkpoint recovery

Manual next experiments now persist the workspace-resolved parent run in the existing execution journal before task admission. Their model calls, native revisions and draft writes resolve the same conversation allowance and stop fence. SQLite regressions observe all six fake-provider calls in shared usage, preserve usage across restart/replay, deny a new child after stopping, cancel a queued legacy child after reconstructing its missing ancestry, and reject further calls at the shared last slot. Recovery attaches existing manual call history without rewriting requests, receipts or draft bytes.

Stop preserves a reached review checkpoint using the final waiting task, successful predecessors and exact stored draft reference, independently of review-case timing. Both fixture and model checkpoints remain waiting and become valid unapproved cases without inference. A fault after the stop receipt commits leaves recoverable checkpoint references; repeated recovery opens one case and grants no approval or handoff. An unrelated waiting task is still cancelled. The chat retains a Stop control for blocked preparation and exposes the recovered review immediately, including after reload.

Targeted mutation probes restore the manual origin omission, skip ancestry admission, require an already-open case at a checkpoint, and omit immediate review recovery. Existing cancellation, allowance, replay and approval-preservation probes remain active. No paid model calls were made.

Verified after these corrections: all 430 backend tests, all 81 browser tests, architecture, production build, formatting, whitespace and all 112 declared mutation probes passed. The strengthened legacy-queued-child regression also passed separately after simulating missing old ancestry before stop. The isolated preview was restarted only after confirming no active runs or running tasks. No live provider behavior was tested.

## Worker migration fencing and isolated checkpoint restoration

Schema-v10 tests migrate an older manual descendant with no stored ancestry and a one-call allowance, then use a direct configured worker before any workspace recovery. It claims no tasks, consumes no attempts and dispatches no model calls. A separately retained live lease is denied at reservation. After the original workspace relationship is recovered, the same work can consume one properly attributed call and cannot exceed its shared allowance. An unrelated standalone organization still completes six fake-provider calls. A fault after the migration's ancestry marking rolls back DDL, version and data while preserving original receipts and the legacy cutoff.

A real loopback server starts with two pending checkpoint restorations while one operator is disabled. The affected checkpoint exposes sanitized blocked guidance, its actor remains disabled, and the other case recovers. Explicit administrative restoration permits recovery without generation or approval. Another test fails the preparation-journal update after the case ID is saved: restart reconciles that existing case to review readiness, records no second review-opened event and leaves approval absent. Repeating completed recovery does not advance the journal epoch.

Browser coverage checks visible recovery guidance and continued polling until authority is restored, without a reload or new inference. Five new mutations remove the unresolved-origin migration mark, worker claim gate, reservation guard, failure isolation and existing-case journal reconciliation. No live provider behavior is claimed.

Verified after the recovery corrections: all 436 backend tests, all 82 browser tests, architecture, production build, formatting, whitespace and all 117 declared mutation probes passed. The focused migration/recovery subset passed all 35 checks. The isolated preview was stopped only after verifying all its domain databases were idle, then reopened with schema v10. Verification used fake providers; no live provider behavior was tested.

## CLI campaign recovery and incomplete cost coverage

Two regressions reproduced a completed CLI campaign remaining quarantined without a descendant session, and six unattributed calls yielding a falsely complete zero-cost projection. Recovery now resolves the CLI's stable campaign reference against the original scoped request and frozen campaign brief. Fresh-process tests cover schema-v9 migration and already-quarantined schema-v10 records, with exact task history, receipts, drafts and legacy cutoff preserved. Repeated workspace recovery needs no descendant session. Recovered queued CLI work obeys the original stop fence and shared allowance before dispatch.

Negative cases preserve quarantine for missing campaign provenance, a request identity belonging to a planner, and a matching campaign in another organization. Unknown histories remain blocked. Cost coverage is incomplete whenever potentially shared runs remain unattributed, even if all known calls report cost. Tests retain a known $0.06 subtotal alongside unresolved calls, and the browser checks the explicit incomplete label using six real fake-provider journal records. Five new mutation probes remove CLI origin resolution, reopening recovery, organization scoping, campaign attestation and incomplete-cost coverage. No paid model calls were made.

Verified after these corrections: all 442 backend tests, all 83 browser tests, architecture, production build, formatting, whitespace and all 122 declared mutation probes passed. The focused execution suite passed all 35 tests; the strengthened stopped-CLI test also passed with an available allowance, independently of budget exhaustion. The idle isolated preview was refreshed and returned HTTP 200. Verification used fake providers; no live model or billing behavior is claimed.

## Explicit reconciliation of independent legacy runs

Unresolved ancestry now exposes a nullable remaining allowance and labels known usage without asserting a spendable remainder. The inspection panel lists recovery commands and scoped run identities. A trusted enabled local operator can inspect a quarantined run and attest that it is independent through the CLI, without a provider key. The command binds the exact run, task and inference-journal fingerprint, actor and explanation. A stale inspection, missing or disabled operator, another organization, active task or proven conversation origin is rejected. This is an explicit administrative classification, not an inference from missing metadata.

Real SQLite tests cover migration of an independent CLI run, preserved task and receipt bytes, existing approval, complete accounting after reconciliation, restart and repeated receipt observation. The immutable classification survives the migration quarantine sweep and rejects a conflicting later parent link. Concurrent classifications produce one decision; changing inputs on a reused identity is rejected. An injected audit failure rolls back both command receipts, the decision and quarantine removal. A queued independent run resumes under its original per-run limit without consuming the stopped conversation's allowance. Fresh-process CLI inspection, resolution and lost-response replay need no model adapter.

The browser checks unknown allowance, incomplete cost and visible operator instructions at desktop and mobile widths, then executes the real operator CLI and reloads to observe the restored numeric allowance. Seven new mutations weaken operator authority, exact inspection binding, proven-origin checks, classification immutability, marker durability, atomic audit and unknown-allowance projection. No paid model calls were made.

Verified after these corrections: all 449 backend tests, all 83 browser tests, architecture, production build, formatting, whitespace and all 129 declared mutation probes passed. The focused execution suite passed all 42 tests. The isolated preview was refreshed only after all domain databases were verified idle and returned HTTP 200. Verification used fake providers; no live semantic or billing behavior is claimed.

## Workspace ancestry at the independence boundary

Reconciliation now checks both authoritative journals before accepting an operator's independence claim. Scoped workspace records matching the run, request or campaign identity are part of the inspection fingerprint. A recorded parent, follow-up or conversation plan rejects classification before domain recovery. An inconsistent database scope or unavailable workspace journal also blocks classification. The command opens the original journal without creating a substitute, obtains its write lock before the domain transaction, and retains that lock through classification commit. Exact historical receipt replay remains observable without current workspace availability.

Real SQLite regressions reject an incorrect operator attestation against a migrated queued workspace child through both the adapter and a fresh CLI process. No decision, audit or quarantine removal commits, normal recovery succeeds, and a subsequent stop prevents dispatch. A completed child with six provider receipts retains those calls in its conversation accounting after recovery. A controlled interleaving commits a workspace parent while reconciliation waits for the write lock; the command reads the newly committed relationship and rejects independence. Another test attempts a competing workspace write at the resolution audit boundary and confirms that the workspace lock is still held. Changed workspace inspection data needs a fresh fingerprint; another organization's record cannot determine this run's origin. Missing-journal checks preserve quarantine while allowing observation of a genuinely completed resolution.

Four new mutations omit workspace-parent authority, weaken the write lock, exclude workspace evidence from the fingerprint, and remove organization scoping. Genuine independent-run authorization, concurrency, replay and atomicity checks remain active. No paid model calls were made.

Verified after this correction: all 456 backend tests, all 83 browser tests in one full run, architecture, production build, formatting, whitespace and all 133 declared mutation probes passed. The focused execution suite passed all 49 tests. No live provider behavior was tested.

## Persistent workspace journal identity

Workspace initialization now assigns an immutable journal ID and records whether identity initialization observed a new empty journal or populated legacy history. Workspace composition binds each organization's domain history to that ID in the existing execution ledger before its first run. Existing bindings are never overwritten. Inspection and new independence decisions verify the scoped binding while holding both journal locks, and include the verified journal ID in the inspection fingerprint. Public stop commands reserve the binding namespace. Historical decision replay remains an observation of the original receipt.

SQLite regressions replace the original journal with a newly created empty workspace and attempt the reported incorrect attestation before recovery. No decision, audit effect or quarantine removal commits, and reopening does not replace the domain binding. Restoring the original journal permits ancestry recovery and preserves the stop fence. A separate genuine independent run rejects a substituted unrelated journal and resolves after its original is restored. A fresh recreated journal cannot adopt old history after matching session rows are added. Journal identity survives restart and rejects updates or deletion through normal SQL operations.

Legacy enrollment requires a populated pre-identity journal with a matching persisted random run ID, request identity, intact task hash and frozen conversation provenance. A regression uses two genuine workspaces with matching campaign names and different run IDs: the unrelated journal cannot enroll the original domain history, while restoring the original permits verified enrollment and independent-run reconciliation. Three new mutations weaken the journal ID comparison, permit fresh journals to enroll existing history, and substitute a matching request name for the exact legacy run witness. No model calls were made during reconciliation; verification providers remain synthetic.

The existing fake-model workspace test wrapper forwards the new composition scope, so its six-call preparation check exercises real journal enrollment rather than bypassing the binding path.

Verified after this correction: all 462 backend tests passed in a clean full rerun, all 83 browser tests passed in one full run, and architecture, production build, formatting, whitespace and all 136 declared mutation probes passed. The focused execution suite passed all 55 tests. No live provider behavior was tested.

## Legacy completeness and deterministic lock release

A matching root cannot prove that a populated legacy backup contains later child sessions. Automatic enrollment of existing history has been removed. Only a binding made before the organization's first run can support independent classification. Witness-based legacy bindings and their independence receipts remain immutable history but do not supply current execution authority. On reopen, unlinked runs with such old decisions regain the pending-origin fence. Positive parent recovery can restore the correct execution account without rewriting the old receipt. Unknown pre-identity ancestry remains paused; full backward or partial-restore recovery is not claimed.

The stale-backup regression snapshots a populated root journal, admits a later child, removes its domain ancestry to represent legacy records, and restores the earlier backup. Neither workspace opening nor an incorrect operator attestation can enroll the history or clear quarantine. Restoring the complete source permits positive parent recovery and preserves stopping. Another test seeds an old witness-based binding and independence decision, verifies historical replay grants no authority, then recovers the positively recorded parent. Existing correctly bound independent runs keep their authorization, replay and atomicity coverage.

The journal guard now establishes cleanup before opening or validating the connection and closes it in a nested finally even if rollback fails. The lock regression retains validation exceptions and tracebacks with garbage collection disabled, supplies multiple invalid identity shapes, and immediately acquires and commits a second writer. This checks release at exception return rather than eventual collection. Mutation probes challenge completeness qualification, historical-decision authority, reinstatement of the weak-decision fence and cleanup on validation failure. No live provider calls were made.

Verified after these corrections: all 465 backend tests, all 83 browser tests in one full run, architecture, production build, formatting, whitespace and all 139 declared mutation probes passed. The focused execution suite passed all 58 tests. No live provider behavior was tested.

## Execution authority contract baseline, issue 33

The [ownership decision](execution-authority-decision.md) identifies current authority in the application and workspace databases, assigns one intended owner per fact and defines the supported recovery states. The first implementation slice exports versioned admission values and an inactive port. It does not implement atomic admission, change existing workers, migrate storage or make the workspace rebuildable.

Eight contract tests cover explicit ownership, a stable account across brief revisions, exact source/context/model/consent/task fingerprints, immutable task inputs, strict wire versions, parent account/revision equality, bounded task envelopes and finite receipt timestamps. A value can bind a supplied consent reference but cannot establish its authority. The future adapter must verify the source, registered effect requirements and consent independently under its transaction.

Four model-based tests compare real SQLite reservation and progress behavior against a separate specification with two accounts, three runs and two slots per account. All 49 pairs of a seven-action alphabet cover reservation, observation, unknown outcome, stopping and restart ordering. Longer traces reach the shared limit, replay a recorded call at that limit, observe a late result after stop and preserve uncertain work across restart. A separate Python process observes the original uncertain receipt and stopped account. Expected ownership is fixed by the scenario, not computed with the production origin resolver. These checks are a reusable baseline for later adapter/caller changes, not proof of those unimplemented changes.

Six new mutation probes weaken account identity, context binding, consent pairing, parent ownership, wire version and the actual SQLite shared-limit check. The last probe tests the independent oracle against a harmful production change. No browser, schema or live model behavior changes in this slice; new admission transaction, full projection rebuild, mixed writers and migration remain explicit acceptance gates for later slices.

Verified for this slice: all 477 backend tests, architecture, whitespace checks and all 145 declared mutation probes passed. The 12 new focused tests passed. The frontend was unchanged, so its prior browser result was not rerun or counted as new verification. No paid model call was made.

## Immutable model IDs at admission

`ModelConfig` now requires a plain string model ID before checking its existing length and whitespace rules. This rejects mutable list/dictionary IDs through both direct construction and admission payload reconstruction. A regression first reproduced acceptance of the reported list before the fix. Two new tests cover rejection of non-string values and verify that mutating valid source/exported configuration dictionaries cannot change an already-created admission's model settings or fingerprint. A targeted mutation removes the new type check and must be detected. No persisted artifact, approval rule or provider call is changed by this correction.

Verified after the correction: all 479 backend tests, architecture and whitespace checks passed. All 10 admission-contract tests and all seven targeted admission/authority mutation probes passed. The complete mutation portfolio and browser suite were not rerun for this correction. No live model call was made.

## Atomic SQLite planning admission, issue 33

Schema 11 adds immutable verified-request and admission journals alongside the existing tasks and inference records. The conversation module owns pure permission, planning-capacity, intent and binding rules. The SQLite adapter loads independently scoped source messages, exchanges, prior results and saved consent under its write transaction. It cannot use a proposed consent ID or fingerprint as a substitute for that saved decision. Request staging creates no task. Admission commits the run, task plan, explicit conversation owner, planning projection, receipt and audit together. Runtime remains business-agnostic.

The installed workflows are model and fixture planning only. They remain paused at claim and reservation, including after restart or loss of the admission row while its explicit task-format marker remains. There is no activation toggle or new model tool/HTTP/CLI route. Current operation paths continue to run, but cannot duplicate a staged planning revision or use the legacy service to evade the six-request limit. Standalone, child, routing, campaign-copy and native revision source policies remain part of the later cutover.

Twenty-one new SQLite tests cover exact-input replay, changed keys/settings/consent, mode downgrade, foreign scope, independent source and consent integrity, current revision/stop checks, frozen context without current catalogue files, full-envelope budget failure and validation-copy mutation. Two concurrent writers produce one request/admission. Seven insert-boundary faults, a saved-request insertion fault and a precommit fault leave no partial executable work. Real subprocess exits before commit leave no run; exits after commit preserve the original receipt for restart/replay. Scoped receipt reads verify the original task hash and ownership from one read snapshot, without granting current approval.

Migration regressions cover schema-11 rollback/retry and concurrent initialization. Older schema-four/five fixtures explicitly exclude later migrations so their failure tests still exercise the intended historical starting version. Existing tests retain positive legacy-cutoff and review-generation preservation. Thirteen new mutation probes challenge consent integrity, exact request binding, source bytes, paused claim/reservation, missing-journal format fencing, request capacity, legacy duplication, mode, early commits, asset scope, scoped reads and validation-copy isolation. The scope probe constructs a valid foreign bundle and updates all dependent hashes, so hash failure cannot hide a missing scope check.

Scoped saved-request lookup and enumeration preserve staging recovery without browser memory or current guidance files. The crash subprocess reads its intent from the database by scoped request identity; it receives no frozen payload from its parent process. These reads are observational and do not activate work.

Full workspace reconstruction, paid execution through new admissions, positive standalone/descendant admission and restore activation are not established by this slice. No live model calls or real campaign sends were made. The React interface is unchanged.

Verified for this slice: the final clean backend run passed all 500 tests, including the 21 new admission regressions. Architecture and whitespace checks passed. The full mutation portfolio detected all 159 declared mutations, and the 13 new probes passed again with the completed staging-recovery API. No frontend files changed, so the browser suite was not rerun or counted as new verification.

## Mixed planning request-key collisions

Staging now rejects a request key already owned by a legacy plan in the same scoped conversation, even on an earlier revision or before the legacy runtime run exists. It also checks the independently derived runtime request key before saving the immutable request and repeats that check at admission. The legacy service rejects keys already staged through the atomic path across revisions, while historical exact replay remains observational.

Three regressions first reproduced the missing protections, then passed with the fix. They cover complete and partial legacy admission, an occupied runtime key without a planning row, organization isolation, and atomic requests both before and after admission. Rejected staging leaves the request journal, planning counts and runtime records unchanged. A replacement key can still stage and admit the current revision; in the reverse direction, a replacement legacy request can finish through the fake planner. Original frozen records remain unchanged. Three targeted mutation probes remove the legacy-key, runtime-key and reverse-key checks.

Verified after this correction: all 503 backend tests, architecture and whitespace checks passed. All 24 focused admission tests and all 16 targeted atomic-admission mutation probes passed. The full mutation portfolio and browser suite were not rerun for this correction. No paid model calls were made.

## Runtime request reservation during staging

The immutable staged request now reserves its explicit runtime key. All application run insertion uses the shared SQLite helper, which checks that reservation inside the writer's transaction. Ordinary campaign, model-campaign and task callers cannot supply the internal owner binding. The verified admission path supplies the exact saved request identity/fingerprint, and insertion checks the original task plan and persisted binding. Missing or mismatched ownership fails before creating a run. No schema or historical artifact changes are needed.

Three regressions first reproduced the unreserved-key gap, then passed with the guard. They cover `Application.start`, model campaign creation, generic creation with copied exact task inputs, another organization using the same key, a fresh-process writer and successful original admission afterward. A controlled interleaving holds the staging write transaction while a campaign writer waits; after staging commits, the competing writer is rejected and the original admission completes. Private insertion tests reject incorrect owner/fingerprint, substituted task plans and a claimed reservation without its saved request. The staging-failure regression also proves rollback releases the key for ordinary creation. These checks assert no extra runtime/task/audit or approval effects; existing campaign preparation may retain unreferenced immutable input artifacts before a later run-creation rejection.

Three new mutation probes remove reservation enforcement, owner matching and exact plan binding. Runtime core contracts remain business-agnostic, and new-format execution stays paused. No paid model calls were made.

Verified after this correction: all 506 backend tests, architecture and whitespace checks passed. The 27 focused admission tests passed, and the full mutation portfolio detected all 165 declared mutations. No frontend files changed; browser checks were not rerun. Verification used fake providers and no paid model calls.

## Paused admission coverage across workflows

Schema 12 extends the existing request/admission journal to routing, conversation
and standalone campaign preparation, manual descendants, finalized learning
follow-ups and native copy revisions. The server-only request API accepts fixed
source references. The SQLite adapter loads actual scoped sources under the
write lock; workflow composition uses public domain contracts and existing task
factories. No caller-supplied task list, ownership declaration or consent ID can
replace that verification. New model copy uses grounded v3 contexts and the
stable transcript projection. The complete read/submit envelope is checked
without a gateway or inference journal, and final source deadlines are checked
after validation before committing staging or admission.

| Invariant | Executable evidence |
| --- | --- |
| A child retains its verified parent's account and original revision | Conversation and explicit standalone parent/child admissions; missing legacy linkage and foreign parents rejected |
| Source facts remain current at admission | Conversation edits and stop after staging; revoked operator; changed follow-up suppression epochs; expiry during preflight |
| Audience provenance cannot be substituted | Completed saved plan and its actual admitted task; selected manifest/version/checksum on every task; different audience bytes rejected; scoped snapshot/segment/context checks |
| Each request binds one exact operation, generation decision and runtime key | Changed inputs/model settings, competing keys, native reconciliation and ordinary task/campaign writers rejected without runtime effects |
| Review and learning authority remain in their existing modules | Native exact-subject revision receipt consumed without another rejection; parent approval/outcomes not inherited; finalized disjoint proposal uses its accepted parent job/case |
| Admission cannot dispatch before cutover | Claims consume no attempt and direct inference reservation is refused; unchanged call, approval, acceptance and belief counts |
| Replay and recovery observe original work | Concurrent duplicate staging, fresh-process receipt replay and retry after injected precommit failure |
| Forward migration preserves history | Concurrent schema-11 upgrade and interrupted schema-12 table rebuild preserve original request JSON, receipts, tasks, events, execution links and schema-3 cutoff; integrity/foreign-key checks and immutable triggers hold |

The focused coverage uses real SQLite, saved planning/routing/revision and cohort
records, and fake providers only to prepare source fixtures. Seven new mutation
probes remove explicit consent, current ownership, final freshness, dataset
provenance, original routing/revision settings and positive parent proof. Each
is detected by its corresponding boundary test.

The new path remains paused and has no transport or model-tool registration.
Live entry-point conversion, missing-workspace rebuild and activation/restore
gates remain later acceptance work for issue 33. No frontend files changed and
no paid model calls were made.

Verification: all 531 backend tests passed with loopback access for HTTP tests;
architecture and whitespace checks passed; all 172 declared mutations were
detected. The 25 focused workflow-coverage tests also passed after tightening
the registered parent-workflow check. The shared copy-request extraction retains
the original correction identifiers and passes the model-copy and grounding
regressions. Browser checks were not rerun because no frontend or transport
behavior changed.

## Frozen follow-up model settings at admission

Model follow-up task construction now requires the exact configuration recorded
in its saved proposal. The same composer runs before request staging and again
inside the admission transaction. A different model, call allowance, input or
output bound, or price ceiling cannot replace the proposal's frozen settings.
Fixture follow-ups still require no model configuration, and new-format tasks
remain paused.

Two real-SQLite regressions reproduced the missing checks before the fix.
The first varies six configuration fields independently, verifies rejection
before model preflight or any journal/runtime effects, then stages and admits
the original configuration successfully. The second reproduces a request saved
by the prior unchecked writer with its original source fingerprint and consent,
reopens the database and verifies that admission rejects it without changing
the immutable request, creating a run or reserving inference. Two targeted
mutation probes independently remove the comparison at these tested boundaries.

Verification after this correction: all 533 backend tests, architecture and
whitespace checks passed. All five focused learning-admission tests and both
targeted mutation probes passed. The full mutation portfolio and browser suite
were not rerun for this correction. No paid model calls were made.

## Entry-point cutover with execution paused

Schema 13 adds explicit `verified-paused/v1` store selection. Planning, chat
coordination, routing reconciliation, CLI/application campaign creation, manual
children, frozen learning follow-ups and native copy revisions use the public
admission port in selected stores. Command replay uses saved references before
context generation. New ownership is established by domain sources before the
first claim; workspace parent reconstruction and journal witness binding do not
supply new-format execution authority. Unselected stores retain their existing
compatibility behavior. No verified execution activation is implemented.

| Invariant | Evidence in `test_admission_entrypoints.py` |
| --- | --- |
| Selecting a format cannot race past live work | Running tasks, reserved provider calls and partial legacy plan admission block selection; original observation/reconciliation permits a later safe selection |
| Selection is atomic and cannot be downgraded | Transaction failure restores the old format; a competing raw writer waits for the write lock and is rejected after commit; immutable policy triggers and missing-metadata checks hold |
| Cached old writers cannot bypass selection | Direct old-protocol SQL cannot insert an unverified run, claim a task or reserve inference; guards need no connection-specific Python function |
| Admission and runtime are committed together | A deferred foreign key permits verified admission before runtime insertion; injected precommit failure leaves the original staged request and no runtime/admission effects; retry succeeds |
| Replay preserves exact commands and context | A fresh builder reuses the original model context without its factory; changed size, model settings and native revision receipt conflict; original requests stay discoverable |
| Descendants retain their original account and stop lineage | A conversation campaign and model child share owner/account; stopping cancels both; a manual workspace child retains its domain parent after presentation parent metadata changes |
| All new-format execution remains paused | Worker ticks and inference reservations are refused; no attempt, model-call or approval count advances; restored active leases cannot settle a task |
| Caller paths share the same contract | Fixture/model roots, successful saved conversation proposals, native revision and finalized follow-up sources produce verified admissions; fresh CLI workers see the persisted format |
| Chat does not mistake pause for missing credentials | Paused planning and routing show bounded progress without loading a provider key; restarting the coordinator preserves the original run |

The original authority and statistical tests remain applicable. SQL guards are
installed under the migration write lock, including when earlier table rebuilds
must run; they preserve saved request/receipt/task bytes and the legacy cutoff.
Existing provider observation rules remain separate from activation. The new
tests use real SQLite, controlled lock interleavings, subprocesses and fake
providers. They prove paused admission and refusal, not positive verified model
dispatch or a complete activated verified campaign. Projection rebuild and
restore/activation remain later gates for issue 33.

Eleven new mutation probes target raw creation, quiescence, partial planning,
context replay, restored leases, exact revision continuation, workspace ancestry
and the SQL run/claim/reservation barriers.

Verification: all 564 backend tests, 83 existing browser tests and 185 declared
mutation probes passed. Architecture, production frontend build/format and
whitespace checks passed. The 31 new entry-point tests include real loopback
requests and the second-server selection boundary. The offline learning demo
completed with the original finalization receipt replayed unchanged. No paid
model calls were made. The verified path remains paused; passing compatibility
journeys does not claim activated verified execution or projection rebuild.


## Cutover identity reservation and historical observation

Campaign identity is one organization-scoped reservation across standalone,
conversation, manual-descendant and learning-follow-up admissions. The adapter
checks actual frozen campaign IDs before staging and again before committing
admission, including older staged requests whose operation key used a workflow
prefix. New requests share a campaign operation namespace. Copy revisions retain
their separate operation identity because they intentionally revise an existing
campaign. Admission of contradictory historical staging blocks safely; replay
of an already committed receipt remains observation, not current permission.

Native routing keys remain conversation-scoped and distinct from planning keys.
The admission wrapper derives its identity from the routing kind and immutable
action ID. Existing raw-key wrappers replay only when their saved kind and source
references match the original action. Native message, action and runtime keys
are preserved.

Sealed stores recognize exact pre-cutover campaign and planning commands through
a read-only path. It compares original task-plan hashes, supported workflow
plans, scoped frozen references, model settings and planning revision/mode.
Historical planning replay does not require the conversation still to have that
revision. Optional frozen continuation context, including messages when supplied,
must match. Replay does not rebuild current guidance, write contexts, reserve
inference, attach ownership or create an admission. It returns the original run,
which remains paused and uncertified. This compatibility guarantee concerns
saved effect-bound inputs; legacy records do not contain every original CLI flag.

The real-SQLite regression portfolio in `test_cutover_review_regressions.py`
covers both cross-kind staging orders, concurrent commands, incompatible pre-fix
staging at admission, unchanged pre-fix operation keys, organization isolation,
a routing/plan key collision, two conversations sharing a routing key, original
raw-wrapper replay, exact fixture/model campaign replay after reopening, and
historical fixture/model planning replay after edits. Full durable-row comparisons
include task/event/admission/accounting, audience and context/memory tables.
Six targeted mutation checks remove the staging/admission campaign fences,
routing scope, exact legacy task-plan comparison, planning revision check and
frozen-context comparison independently.

Verification after these corrections: all 577 backend tests, including the 13
new regression tests, passed. All 191 declared mutation checks, architecture and
whitespace checks passed. The backend suite used loopback access for its HTTP
tests. The browser suite was not rerun because frontend and transport code did
not change in this correction. No live or paid model calls were made.


## Legacy routing and copy-revision observation after cutover

The sealed admission path also recognizes existing native routing and
copy-revision runs before attempting a new verified admission. Routing compares
the supplied action with its scoped saved source, excluding only mutable
confirmation state, then reconstructs the original task. Revision replay checks
the complete native receipt, reads and validates its existing content-addressed
context, and reconstructs both original tasks. The existing legacy reader checks
the runtime hash and compares the full ordered task plan with this independently
reconstructed source plan. Runtime integrity by itself is insufficient.

These observations return the original run without writing context, staging a
request, attaching ownership, recording a new approval/rejection or reserving
inference. They require the original model configuration. Current brief edits,
publication and later operator revocation do not block inspection of the
original run; they still govern any new effect. No new-format admission
is activated, and records already containing verified admission metadata remain
on the verified path.

Six real-SQLite tests in `test_legacy_action_replay.py` cover queued routing and
revision replay in separate processes, completed routing after a later brief,
completed revision after publication and operator revocation, cross-organization
requests, altered native sources and model settings, and substituted task inputs
with a recomputed internally consistent runtime hash. Full database row
comparisons verify observation only. Five new mutation probes target both replay
returns, both native-source checks and the revision task-plan comparison.

Verification: all 583 backend tests and all 196 declared mutation probes passed,
including the six new real-database replay tests and five new mutations.
Architecture and whitespace checks passed. The backend suite used local
loopback access for its HTTP tests. No frontend or transport code changed, so
the browser suite was not rerun for this correction. No live or paid model calls
were made. Verified execution remains paused.


## Recovery of source commands staged before entrypoint metadata

The admission facade recognizes the field-absent storage-slice envelope only for
routing and copy-revision commands. Their single source reference must equal
both the supplied entrypoint and the caller's source references. Workflow kind,
explicit Boolean generation permission and exact frozen model settings remain
bound. A present but null entrypoint is not this older format. Campaign commands
cannot infer missing creation arguments from source references. Other stored
workflow requests retain the original storage-port admission path using their
exact saved intent; this compatibility path does not invent absent CLI inputs.

The original scoped source operation can be found even when the storage-slice
request key differs from the native action or revision key. The adapter checks
the saved intent, source identity and canonical references before returning that
key. Existing native-spelled wrappers retain their keys; new routing and revision
wrappers use the same source-based namespace. Native sources and runtime request
keys are unchanged. Recovery passes the original field-absent envelope back to
the storage port, preserving every saved request byte and its fingerprint.

Unadmitted requests still recheck current source and ownership in the admission
transaction, so a later brief edit blocks stale work. Already-admitted requests
observe their original receipt after later edits. Both paths keep verified
execution paused and reserve no inference.

Seven real-SQLite tests in `test_pre_entrypoint_recovery.py` cover fresh-process
staged recovery, cached receipt replay, a separately keyed storage admission,
source-read organization isolation, changed references/settings/permission,
null metadata, unsupported campaign inference, stale unadmitted source and the
equivalent copy-revision path. Five mutation probes target preservation of the
old envelope, discovery of the original key, source-read scope and both saved
and caller reference comparisons.

Verification: all 590 backend tests, including the seven new recovery tests,
and all 201 declared mutation probes passed. Architecture and whitespace checks
passed. The backend suite used loopback access for its HTTP tests. No frontend
or transport code changed, so the browser suite was not rerun. No live or paid
model calls were made. Verified execution remains paused.


## Conversation-scoped native planning requests

Verified planning now derives an admission key from organization, conversation
and native request ID. Mode and revision remain bound inputs rather than key
components, so changing them cannot allocate another planning request. Native
request IDs remain unchanged in frozen tasks, runtime request hashes and the
conversation planning journal. Admission identity and consent use the separate
scoped key. A new optional native-request field records this relationship in the
staging envelope without a schema migration.

A scoped lookup finds existing staging or admission before freezing context.
Earlier raw-key requests retain their original key, serialized envelope,
fingerprint and task plan. Their cached receipts remain observational. New
requests in another conversation may use the same native key without adopting
that earlier work. Partially staged new requests recover their original context
and identity after reopening or process restart.

Planning capacity checks distinguish native command identity from admission
identity. The existing six-request limit counts revisions once across native
planning and staged records. A native key cannot be reused for another revision
or wrapped in another admission to evade its reservation. The compatibility
writer also checks the native key inside its transaction, including when the
store has not selected cutover yet. Runtime reservation and paused-execution
checks remain unchanged.

Nine real-SQLite tests in `test_planning_request_scope.py` cover shared fixture
and model keys across two conversations, independent consent, native task and
journal IDs, raw staging compatibility, partial admission recovery, concurrent
commands, changed mode/configuration/context, mixed old/new writers, the six
request bound, organization/campaign isolation and fresh-process replay. Eight
new mutation probes target key scope, original staging/envelope recovery, native
task/journal identities, both scoped read predicates and compatibility-writer
native reservation. Existing reverse-key mutation probes follow the updated
SQL predicate.

Verification: all 599 backend tests, including the nine new scope/recovery
regressions, and all 209 declared mutation probes passed. Architecture and
whitespace checks passed. The backend suite used local loopback access for its
HTTP tests. No frontend or transport code changed, so the browser suite was not
rerun for this correction. No live or paid model calls were made. Verified
execution remains paused.


## Application-owned workspace intent, issue 33 phase 4a

Schema 14 separates immutable preparation/environment intent from progress and
navigation projection. New selected work reads mode, routing, initial time,
clock advancement, creation-command mappings and domain links from application
storage. Scope comes from a server-owned catalogue with immutable store identity,
not a session payload. Preparation inputs include the original planning context,
model configuration and copy consent before plan admission. They cannot be
replaced by progress or copied from the old control-store journal.

`test_workspace_authority.py` tests poisoned projection fields, missing
`workspace.sqlite`, a fresh Python process, interruption after environment commit
and after task admission, original preparation recovery without rebuilding
context, and exact conversation draft replay after projection loss. All owned
runs remain paused with zero worker dispatch. Tests reject foreign run links,
changed clock/storage fields, unrelated creation-command aliases, replaced or
missing stores, and symlinks outside the root. A clock read under an existing
write transaction proves that known-store access does not acquire a second
migration lock.

A deliberately seeded set of committed review/job/cohort facts isolates the
simulation clock boundary without enabling paused work. It proves that clock
advance and command admission roll back together, exact retries do not change
state, changed-input retries cannot advance time, disabled operators cannot
advance time, and missing/non-finite cohort windows fail before mutation. A
manual child inherits the owned parent store, organization, clock and admitted
parent run without any workspace session row. These are boundary fixtures, not
an end-to-end verified approval/acceptance journey.

Migration checks inject failure after the v14 DDL but before identity creation:
tables, version and identity roll back together, while the legacy cutoff stays
unchanged. Reopen retains the original store identity. Current-schema missing
identity fails rather than silently assigning a new one. Existing concurrent
initialization and whole-chain rollback tests now include schema 14.

Targeted mutation probes weaken projection precedence, original command input
binding, preparation source selection, store identity/root confinement, clock
command atomicity, operator checks, link integrity, immutable progress fields,
planner-run binding and read-only store opening. The previous workspace ancestry
reconstruction probe is replaced by owned-parent and projection-boundary
coverage: new selected work no longer enters that reconstruction path.

Unsealed compatibility operation remains covered by the existing backend and
browser journeys. Full projection rebuild, legacy migration, stale-backup
consistency and activation of verified execution remain later acceptance gates.
No live model behavior is claimed by this offline pass.


Verification for this slice: `make test` passed 624 backend tests;
`make arch-check` passed; `make mutation-check` detected 223/223 declared
mutations; `make interface-check` passed the production build, formatting and
83 browser tests. The focused workspace authority file passed all 23 tests,
including the final organization-scope assertion. Fifteen new mutation probes
replace one retired reconstruction-path probe, for a net increase of fourteen.
No paid or live provider call was made.

## Exact environment/run binding and projection isolation

The environment/run link now verifies more than a valid admission and matching
runtime key. Inside the same SQLite transaction it reloads the immutable
creation command, original environment, frozen admission command/source and
verified parent environment. Workflow policy checks mode and model permission,
source kind and identity, exact brief, parent run/ownership, source references
and the original workspace command parameters. It does not rebuild model inputs,
refresh historical evidence or enroll legacy work. Reads repeat the integrity
check; an already inconsistent link is blocked, not rewritten.

| Confirmed invariant | Independent falsification | Boundary |
| --- | --- | --- |
| A runtime key alone cannot establish environment intent | Interrupt fixture environment creation, independently admit a valid model run with the same key, reject both direct linking and preparation after reopening | Real SQLite; all new-format runs remain paused |
| Valid commands cannot substitute different intent | Valid same-mode runs change size, seed, budget or date; a model environment receives fixture work; conversation/manual-child environments receive standalone work; a child receives another valid parent | No provider dispatch or alteration of the admitted candidate |
| Exact historical work remains readable | Original model-run recovery, clock advancement, conversation replay, process recovery and frozen fixture/model follow-up contracts continue to pass | Later activation and legacy migration remain deferred |
| Disposable corruption cannot hide owned records | Malformed JSON, wrong identity, incomplete objects, invalid timestamps and malformed nested plans coexist with owned state; listing, conversation and routing context remain readable after reopening | Malformed projection rows are ignored in selected mode; well-formed legacy rows remain visible |

The two causal clusters are admission identity/source/consent at link commit,
and projection corruption/observability during reads. The bounded tests use
valid competing admissions rather than trusting the new matcher to create
expected results. Projection tests assert original owned values and unchanged
application records. New mutations weaken original-command matching, substitute
the candidate's parent for the environment's parent, and remove corruption and
schema isolation. The existing link mutation now removes the complete semantic
check, because the former request-ID check is also covered by that policy.

Verification of these review corrections: `make test` passed 632 backend tests,
`make arch-check` passed, and `make mutation-check` detected 227/227 declared
mutations. The final focused authority file passed 31 tests, including the
additional nested-JSON and legacy-visibility assertions; both projection
mutations were rerun successfully after the parser-error refinement. No frontend
files changed, so the earlier 83-test browser evidence was not rerun for these
corrections. No live provider call was made.

## Audience identity behind a claimed creation command

The reported bypass was reproduced before the fix: eight valid admissions
substituted audience size, seed, date or record content while claiming the
workspace command, in both fixture and model mode. Each could link to the
original environment intent despite the contradictory population.

Generated workspace audiences now bind the content identity independently
derived from the environment's organization, fixed 1,000-record/seed-42 v1
recipe and original UTC simulation date. Bootstrap supplies the deterministic
synthetic adapter's identity function to workflow policy. The link transaction
compares that expected identity with both the frozen source and admitted task.
Claimed command fields and candidate snapshot metadata cannot supply the oracle.
The check covers root/manual-descendant campaigns and unsourced conversation
campaigns. The original synthetic-segmentation/v1 recipe must remain stable
when introducing a new generator version.

This recomputes only the deterministic synthetic identity, with a bounded
128-entry cache of immutable hashes. It does not rebuild model context, invoke
inference, read a live audience feed or change stored snapshots. Selected
datasets retain their independently confirmed version/manifest provenance;
learning follow-ups retain their frozen proposal population. Their audiences
are not replaced with the 1,000-record synthetic recipe.

Tests admit valid competing snapshots with a dishonest but exact entrypoint:
20 records, a different seed, a different date, and altered content with the
expected count and metadata. Link rejection leaves all application rows
unchanged, the environment unlinked and provider calls absent. A separate
unsourced-conversation test covers its implied generation recipe. A confirmed
100-record dataset and existing fixture/model follow-up contracts demonstrate
that legitimate overrides keep their provenance. Three mutations restore
self-certification, omit the conversation check or apply the synthetic recipe
to selected datasets.

Verification of the audience correction: the full `make test` run passed 635
tests. The latest focused authority run passed 35 tests, including the additional
reverse counterexample added while strengthening the command mutation: correct
audience bytes cannot excuse an incorrect saved command. `make arch-check`
passed and the complete mutation run detected 230/230 declared mutations.
No frontend files changed and no live provider call was made.


## Checkpoint recovery polling in CI

PR 38's first CI run passed backend, architecture and mutation checks on all
four Python versions. Its browser job failed waiting for Review campaign after
restoring a disabled checkpoint operator. A conversation read can capture its
campaign mapping before recovery updates the case, then read newer preparation
progress after recovery clears the blocker. The former client saw no active
preparation or blocker and stopped polling, leaving the completed draft hidden.

The client keeps its existing read-only polling active while a campaign has
reached `waiting` or `succeeded`, still has no review-case ID, and its preparation
reports `review_ready` for the same revision and campaign run. Explicit
checkpoint-recovery blockers and a pending-recovery hint backed by the exact
saved stop receipt also keep polling active. A missing case alone does not
imply automatic recovery. Readiness, approval, simulated
acceptance and inference remain controlled by the existing backend. No retry
setting or timeout was increased.

The existing browser test now delivers this single intermediate response from
a real recovery run deterministically. It failed before the client change and
passed ten repetitions afterward. It still asserts unchanged model-call usage,
an unapproved exact draft and no handoff after recovery. The incomplete read is
injected only into the response; the actual server performs checkpoint recovery
and the next poll retrieves the saved case.

A real SQLite probe also pauses the conversation read immediately after its
campaign snapshot, restores the checkpoint, and resumes the read. It produces
`case_id: null`, `generation: waiting`, `preparation: review_ready`, no blocker
and zero pending receipts while the saved case already exists. This confirms
that the browser's injected intermediate packet corresponds to a reachable
backend interleaving.

Local verification: `make interface-check` passed the production build,
formatting and all 83 browser tests. The forced-race checkpoint test passed ten
consecutive repetitions. Architecture and diff checks passed. Backend source
and authority rules are unchanged; CI reruns the full Python matrix on the
published fix. No paid model requests were made.

A follow-up review found that the original missing-case condition also polled
ordinary blocked preparations indefinitely. If case storage fails before a
stop receipt exists, the coordinator saves `blocked` and does not automatically
retry when storage returns. The new browser regression creates that real SQLite
state, restores storage before serving the interface, and observes three polling
intervals without another conversation read. It also checks that progress stays
blocked, no review appears and model usage does not increase. The regression
failed against the broad condition before the matching-ready-progress check was
added. The existing forced-race recovery test covers the transition that must
continue polling.

Follow-up verification: both checkpoint browser cases passed five consecutive
repetitions each. `make interface-check` passed the production build, formatting
and all 84 browser tests. `make test` passed all 636 backend tests;
`make arch-check` and `git diff --check` passed. No live provider calls were made.

The next CI run exposed a second reachable read schedule. A conversation read
captures its campaign mapping and cancelled preparation row, then checkpoint
recovery creates the case, updates the row and clears the blocker before the
read obtains generation state. The response has neither ready progress nor a
blocker, so matching only `review_ready` still stops polling too early. CI did
not retain its trace; a real SQLite probe and a browser test independently
reproduce this schedule and the same five-second missing-review failure.

The backend now projects `checkpoint_recovery_pending` only for a missing case
whose exact organization/run belongs to this conversation's immutable stop
receipt. That receipt is also the executor's recovery input. It remains
discoverable after the blocker clears, and the hint clears when the case mapping
is read. No new recovery task, inference, approval or acceptance is admitted by
this read. An unrelated checkpoint's stop receipt is insufficient.

The browser test holds recovery until an actual progress read has captured the
old row, then restores the real case during that read. Its response is not
rewritten. This complements the earlier injected ready-progress packet and the
ordinary blocked/no-retry case. All three browser cases passed five repetitions
each. Two declared mutations remove the recovery hint or falsely advertise all
missing cases as recoverable. CI now retains failed browser traces, screenshots
and error context for seven days.

Final local verification: all 637 backend tests, all 85 browser tests,
232/232 declared mutations, the production build, formatting, architecture and
diff checks passed. The three targeted browser cases passed 15/15 repetitions.
No live provider calls were made.

## Offline workspace projection rebuild, issue 33 phase 4b

`tests/test_workspace_projection.py` exercises 21 recovery scenarios against
real SQLite. The oracle compares independent snapshots of all application
tables, not the projection adapter's expected rows. A missing projection is
inspected without being created, then rebuilt in a fresh CLI process. Owned
identity, original request lookup, fixture/model mode, simulation clock,
accepted/cohort facts, stopped preparation and unknown provider observations
retain their original meaning. Verified workers remain paused after rebuild.

The mixed-history fixture retains opaque legacy consent, original command rows,
an existing journal identity and unrelated binary data. Conflicting legacy keys,
unreadable files, unsupported layouts and file aliases fail without discarding
history. Missing or replaced application stores are not recreated or enrolled.
An unsealed store is not implicitly selected for verified admission.

Fault tests exit the process after projection writes but before commit, lose the
acknowledgement after commit, change source clock facts before commit and insert
a legacy row after inspection. The crash forces SQLite cache spill so recovery
must handle a real hot rollback journal, not only unflushed process memory.
Query-only projection inspection permits SQLite's own rollback under the root
lock; authoritative source connections remain strictly read-only. These tests
check rollback or exact replay without a new
domain effect. Source-integrity and stale-plan errors release the root lock at
exception return, without garbage collection. A location-only interruption is
reported without inventing a campaign environment.

The diagnostic fixture distinguishes an owned run/revision from legacy keys in
the same organization. Only positively owned cache entries are discarded, so
restored progress is read from application facts rather than stale blocker text.
Nine targeted mutation cases cover SQLite crash recovery, the root lock, source identity, control and
source freshness, atomic commit, legacy preservation and diagnostic ownership.
The existing nested-migration mutation now targets the read-only reader's
equivalent branch; its protected invariant is unchanged.

These tests do not demonstrate executable verified campaigns, legacy
certification, arbitrary partial-backup recovery or absence of post-checkpoint
spend. Source fingerprints are inspection bindings. The migration, supported
restore procedure and activation journey remain phase-5 acceptance work.

Verification: `make test` passed all 658 backend tests, `make interface-check`
passed the production build, formatting and all 85 browser tests, and
`make mutation-check` detected 241/241 declared mutations, including all nine
projection cases. The 21 focused recovery scenarios passed with forced SQLite
cache spill in the pre-commit crash case. Architecture and diff checks passed.
No live provider calls were made.

## Legacy migration inventory, issue 33 phase 5a

The offline `acquisition.legacy_migration inspect` command produces a
`legacy-migration-plan/v1` proposal. All source connections are read-only, including
historical schemas. It never constructs a workspace, selects a store policy,
enrolls a legacy run, changes an allowance, dispatches inference or records approval.
The only writable coordination object is the existing root's `server.lock`.

| Invariant | Independent evidence | Limit |
| --- | --- | --- |
| Inspection conserves history | Full SQL-table and file-byte comparisons before/after repeated inspection and a fresh-process CLI; opaque binary tables, malformed sessions, preparation inputs and original receipts remain unchanged | SQLite may use shared memory for read locks; no cold-backup claim |
| Permission comes from its recorded source | Native planner/routing/revision task matching; an internally consistent replacement plan conflicts with the native admission; routing permission stays routing-only | Unsupported old model-copy consent proofs remain incomplete |
| Ownership needs positive scoped facts | Native conversation proposal and domain descendant fixtures, missing-parent/cycle/conflicting-owner checks, and contradictory account-index tests | No absent-parent inference or independence certification |
| A journal witness is not completeness | Lost, recreated and stale populated journals; matching identity explicitly reports unproven completeness; historical independence receipt remains non-authoritative | Arbitrary partial restore remains unsupported |
| Uncertainty survives inspection | Fake-provider network failure and interrupted reservation retain uncertain status, recorded call count and unknown remaining allowance; a definitive rejection remains a historical observation | No live billing verification, provider retry or account reset |
| Owned projections cannot replace authority | Corrupt owned session ignored in favor of registered environment/preparation evidence; wrong source identity, hardlink alias and escaping paths cannot supply support | No repair is performed |
| Partial admissions stay inspectable | Native admission without a runtime write and a staged verified request appear as pending, without finishing either admission | Inspection performs no migration |
| Recovery does not happen inside inspection | Old/future schemas, missing/unreadable stores and a forced cache-spill hot journal are retained; changed source invalidates the plan; locks release after failure | SQLite recovery must be handled separately |
| Report is metadata, not authority | Fresh-process output excludes prompts, context and response bodies; arbitrary preparation fields are filtered; apply/activate commands are rejected; every executable/migration/activation flag remains false | Historical approvals still require their normal current-authority checks |

`tests/test_legacy_inventory.py` supplies 27 focused scenarios using real SQLite,
fresh processes, source fingerprints and fake providers. Fourteen targeted
mutation cases remove pause/ownership/integrity/uncertainty/redaction and source
checks, accidentally initialize an old schema, or hide a partial admission.
Verification: `make test` passed all 685 backend tests with loopback access,
including all 27 inventory scenarios. `make arch-check` passed, and
`make mutation-check` detected 255/255 declared mutations, including all 14 new
inventory cases. Diff checks passed. No frontend files changed and no live
provider calls were made. Transactional migration, supported restore and verified
execution activation remain later acceptance gates.

### Review: complete environment validation and typed generation choices

The inventory now delegates environment reads to the existing authoritative
workspace reader through a bootstrap-wired callback. It uses the inventory's
pinned read-only transaction and checks the exact admitted run/creation inputs,
review case, learning cohort, original clock and parent before classifying an
environment as supported. Projection records depend on that environment even
when validation fails, so a conflict cannot leave a rebuild recommendation.
The normal reader and effectful workflows are unchanged.

Six additional real-SQLite tests reproduce missing, foreign and wrong-run review
cases; missing and wrong-case cohorts; backward clocks and incompatible clock
modes; valid paused runs with the same runtime key but different mode or audience;
and nonboolean generation choices. Required and optional choices are tested with
strings, objects, lists, integers and null. CLI output cannot contain the injected
credential-shaped marker; valid optional booleans remain exact. Full SQL and file
byte comparisons prove failed inspections leave the source records intact, and
an unrelated valid environment remains supported. The fault-injection cases
failed against the prior implementation and pass with the shared reader and
optional type check.

Three targeted mutation cases cover bypassing that reader, losing projection
conflict propagation and omitting the optional choice type check.

Review verification: `make test` passed all 691 backend tests with loopback
access, including all 33 inventory scenarios. `make arch-check` and
`git diff --check` passed. The targeted mutation run detected all 17/17 inventory
mutations, including the three new cases. No live provider calls were made;
inspection remains read-only and verified execution remains paused.

### Review: validate the complete legacy session metadata projection

Legacy session parsing now validates every exported payload field before
assigning organization, metadata or discovery/ownership hints. It uses the
public bounded identifier and UTC-time contracts, closed mode/clock-mode/storage
enums, nullable link identifiers, and typed conversation-hint identifiers and
revision. Missing historical clock mode is not inferred. Invalid journal keys
use fingerprint locators in both record and evidence references, while internal
record identities still bind the original key. Invalid values never enter the
report or CLI diagnostics, and malformed hints cannot taint a valid original run.

Four real-SQLite regressions cover clock-mode corruption, malformed required and
optional identifiers, invalid nested conversation hints, and valid metadata with
present or absent clock modes. They include credential-shaped strings, long
strings, objects, lists and numeric values, fresh-process CLI output, continued
visibility of an unrelated valid run, and exact SQL/file-byte preservation. The
fault-injection cases reproduced the prior implementation's unsafe reporting.
Five targeted mutations cover enum validation, required/optional identifier
validation, opaque-key rendering and conversation-hint validation.

Review verification: `make test` passed all 695 backend tests with loopback
access, including all 37 inventory scenarios. Architecture and diff checks
passed. The targeted mutation run detected all 22/22 inventory mutations,
including the five new session cases. No live provider calls were made.
Inspection remains read-only and verified execution remains paused.

### Review: native reference formats before public display

The general bounded-identity contract accepts realistic provider keys and is
insufficient for public legacy metadata. The inventory now applies field-specific
native v1 identifier formats to session keys, organizations and optional run,
case, cohort and parent references. Other strings become opaque fingerprint
locators with explicit unverified-reference reasons. Internal lookup and record
identities retain the original scoped inputs; no historical source is rewritten.
Conversation/brief hints outside their native formats cannot affect another
run's ownership classification. Native shape is a display rule, not proof of
ancestry, consent, approval or migration readiness.

Two additional real-SQLite regressions cover a realistic 73-character key-shaped
marker that explicitly passes the general identity validator, and historical
aliases that must stay opaque. They cover every
exported identifier position and both conversation-hint identifiers, fresh-process
CLI output, source preservation, native-format passthrough and opaque historical
aliases. Both tests failed against the prior implementation. Two new targeted
mutations cover bypassing reference redaction and trusting an unverified hint;
the existing opaque-key mutation now targets the shared public-reference rule.

Review verification: `make test` passed all 697 backend tests with loopback
access, including all 39 inventory scenarios. Architecture and diff checks
passed. The targeted mutation run detected all 24/24 inventory mutations,
including both new cases. No live provider calls were made. Inspection remains
read-only, original records are preserved and verified execution remains paused.

### Review of caller-supplied request references

The inventory fingerprints request IDs in both preparation journals, runtime
metadata, pending admission locators and request-keyed evidence. Standalone
ownership scopes use the same rule because campaign IDs can come from the caller.
Run matching by the original request key uses the corresponding fingerprint
within the original store and organization.

Real SQLite tests submit credential-shaped IDs through preparation, planning,
runtime and copy revision APIs. The assertions cover CLI output, partial
admissions, staged requests, standalone scope aliases and source preservation.
The existing journal-parent test exercises request-key matching without a run ID.

The full backend suite passed all 700 tests, including 42 inventory tests.
Architecture and diff checks passed. The targeted mutation run detected all
28 inventory mutations, including the four new request reference cases.

### Review of the inventory report boundary

The normal campaign API accepts a credential-shaped organization identifier.
Previously the inventory forwarded it from the same source dictionary used for
matching. Organization values appeared in records, evidence and resolved owners.
The earlier field-level fixes covered individual paths through that dictionary.

The report now selects fields in one projection after classification. It applies
one organization fingerprint rule to all three positions, retains the fixed
local label and checks the shapes of the metadata it emits. This supersedes the
earlier fingerprint-based matching approach. The classifier uses the original
values and scoped parent links.

The integration regression creates two organizations with credential-shaped
identifiers through the campaign API, reuses a request key across those scopes
and checks a descendant that inherits the first owner's scope. It verifies the
whole CLI output, consistent fingerprints, separate organizations and preserved
source rows. A separate projection test introduces extra source fields and
unsupported metadata strings to exercise the closed display surface.

All 702 backend tests passed, including 44 inventory tests. Architecture and
diff checks passed. The targeted run detected all 30 inventory mutations,
including the two new checks for organization references and report fields.

## Transactional legacy ownership migration, issue 33 phase 5b

Explicit apply records positively evidenced, already-attributed legacy runs
in a sealed schema-14 conversation store with a matching pre-history journal
association. The immutable batch receipt and per-run bindings commit together.
The other inspected databases are locked while SQLite commits the target
transaction.

| Invariant | Executable evidence |
| --- | --- |
| The reviewed plan binds current evidence at the effect boundary | Change the journal after inspection and reject the old ID. Competing writers to the journal and application database cannot obtain write locks during save and can obtain them after completion. |
| Migration adds only proven scope | A mixed store includes a fixture campaign with a native planner, a new paused admission, an unowned CLI run and recorded model usage. A separate case substitutes a different journal parent while retaining the original domain parent. |
| Unknown or missing authority stays visible | Conflicting inputs, uncertain inference, missing accounts and unbound or missing journals stay unresolved. Recreating a journal or restoring a stale copy with the same identity preserves quarantine and unknown allowance through apply and restart. |
| History survives atomic apply and replay | Compare all pre-existing tables, including task inputs, reviews, simulated acceptance, finalized learning and original call records. Interrupt a fresh process after writes and before commit, compare all rows, then retry and replay from fresh processes. |
| Receipt lookup is read-only | Query an uncommitted plan through the receipt command and compare all rows. After a commit, remove the source journal and recover the exact receipt from a fresh process without recreating the journal or acquiring its workspace lock. |
| Migration stays paused and durable | Check zero worker ticks, one retained historical fake-provider call, preserved stop state and rejection of update, delete and replace against committed migration records. |

The test scope uses synthetic data and a fake provider. Historical ownership
bindings are separate from new-format admissions. Supported backup and restore,
explicit activation and the full offline verified journey remain acceptance gates.

Verification passed with 714 backend tests, the architecture check and 69
targeted migration, inventory and recovery mutations.

## Cutover preserves legacy quarantine

Explicit verified selection skips origin recovery and seals the store under
the same SQLite write lock. A rejected cutover rolls back without clearing
quarantine. Existing schema-v10 and later markers remain intact. Cutover of a
pre-v10 store with recorded runs stops before schema changes and requires
separate ancestry reconciliation. Ordinary unsealed opens retain their existing
recovery behavior. A new or existing sandbox store uses the same boundary.
An add-only pass restores missing quarantine for weak historical independence
receipts before selection, and also repairs them on sealed-store startup. It
does not infer ownership, clear markers or rewrite old receipts.

Real SQLite tests cover both CLI forms, the workspace, a direct builder, an
existing standalone sandbox, a competing opener, failed cutovers and rejected
pre-v10 cutovers. They check weak and valid receipts across organizations,
rollback, repeated selection, unknown remaining allowance, preserved quarantine
and legacy cutoff, and paused execution after reopening. Mutation probes remove
the cutover, sandbox and weak-receipt quarantine fences.

## Legacy execution account recovery

A real SQLite regression retains the original run link and stop receipt after
deleting the account row. It exercises workspace reopening, exact stop receipt
replay, inspection and apply. It repeats the check after inserting a
default-valued replacement row. The recorded stop stays visible, remaining
allowance is unknown, and apply records only the separate healthy account's
binding.

Verification passed with 722 backend tests, 85 browser tests, the architecture
check and both targeted account recovery mutations.

The missing-account check also covers loss of the execution index. The
regressions retain an unstopped planning run with one recorded fake-provider
call, an original task with an orphaned call receipt, and a routing run with no
planning history. Reopening keeps the allowance unknown and a later model
request fails before dispatch. A first run can still initialize its account
in the admission transaction. The schema-nine backfill regression covers
stores that predate execution accounting.

Verification passed with 724 backend tests, the architecture check and both
targeted native-history mutations.

A further real-SQLite regression removes the account, run index, run and task
while retaining the planning admission and original call receipt. Reopening,
replaying the original request and submitting a later brief leave the allowance
unknown and the original provider call count intact. A fresh account in the
same organization stays unresolved. A different organization can initialize
its own allowance.

Verification passed with 725 backend tests, the architecture check and three
targeted account-history mutations.

The planning-history regression also retains a task with matching identifiers
after removing its ownership inputs and losing the account, index, run and
planning admission. The receipt keeps the allowance unknown and the provider
call count stays fixed. An intact original runtime plan with valid scoped
ownership still permits account initialization for a separate conversation.

Verification passed with 725 backend tests, the architecture check and three
targeted account-history mutations.

The existing-account regression removes only the execution link for a run
with a recorded call. After reopening, the allowance and cost coverage stay
incomplete. Previously queued work cannot reserve another call and a later
planning request cannot be admitted. Substituting another valid account for
the original owner blocks both accounts. Restoring the exact link restores
the original count. The descendant regression also removes the links from
the campaign organization. The direct reader reports an unknown allowance
until workspace recovery restores the links from the saved ancestry. The
companion mutation removes the existing-account receipt fence.


## Typed chat preparation and next experiments

| Invariant | Offline evidence | Boundary |
| --- | --- | --- |
| Routing proposes the exact current target | A fixture brief and a fake-provider inventory brief bind the saved revision. A qualified request routed as prepare asks for clarification. Missing finalized learning produces no confirmation. | The server resolves the brief or cohort. Chat text and router output grant no effect authority. |
| Confirmation recovery preserves one effect | Real SQLite tests interrupt after confirmation and after proposal commit, then resume in a fresh process. Browser tests lose a response before or after commit, reload, and verify one preparation or proposal with the original request identity. | Preparing a brief reaches a fresh unapproved draft. A next-experiment action saves a separate proposal. |
| Typed preparation requires a confirmed audience version | Fresh fixture and saved-plan requests survive reload and restart while waiting. Neither has a campaign before selection, and the final manifest binds the exact selected source. | The existing catalogue and audience selection command own the dataset receipt. The saved-plan path reuses the original plan. |
| Stop or lost confirmation prevents session creation | Real SQLite tests stop at session creation in legacy and verified stores. A verified insert trigger removes the confirmation during the write and the transaction rolls back the session, location and request. | Legacy creation holds the conversation writer lock through the control-store commit. Verified creation checks the confirmation in the transaction that records the session and location. |
| Stale and stopped sources fence continuation | Tests edit or stop a brief after confirmation and interpose both changes before saving a proposal. Exact-result and cross-conversation substitutions are rejected. | The proposal transaction checks the native confirmation and current source. Fixtures and fake providers establish control behavior. |

## Browser OpenRouter session

| Invariant | Offline evidence | Boundary |
| --- | --- | --- |
| Browser model work binds its original credential session and settings | Reopen the SQLite workspace with a pending preparation. The server-key scheduler, a different key and a different browser session make zero calls. The original session resumes through unapproved review with the frozen model and price ceilings even after choosing another model. | The workspace advances saved work using the original binding. The journal retains call reservations and the existing copy and review authority. |
| The connection handle is scoped to the tab and expires | The HTTP test rejects a wrong Host, token or Origin before constructing the provider adapter. A wrong tab, removed handle and expired handle cannot advance work. The preparation test scans SQLite and provider prompts for credential material. | The adapter keeps the raw key in server memory. The catalog is public and carries no credential. |
| An uncertain command preserves its funding source and price tier | Browser tests drop the first request, change the connection or selection, and verify the retried request ID and settings. A refreshed catalog that increases the tier cannot admit a request with the old ceiling. | The browser saves the original choice before dispatch. The server checks the selected ceiling against current catalog eligibility. |
| Only the plan's credential can continue after audience confirmation | The audience test moves the preparation to copy generation between the confirmation handler's read and its next step. The saved-plan test routes and confirms with a second key, then verifies that only the planning key generates the draft. | Audience selection commits independently of paid continuation. An existing plan determines the credential binding for its campaign. |
| Graceful shutdown drains inference before another server can recover the root | A real loopback request is held in a fake provider call while shutdown starts. Another server cannot acquire the root lock until the original handler records its result and exits. Recovery sees definitive progress. | The listener stops admitting handlers. Active handlers and the background worker drain before the root lock releases. |
| Funding is selected when the chat message is sent | The browser test commits the message, drops its acknowledgement, removes the key and retries after reload. The same message receipt is recovered, and preparation waits for the original connection and uses the original model and tier. | The browser carries funding through message retry and preparation admission. |
| Pending preparation funding stays with its conversation and revision | A browser test interrupts a browser-funded preparation, completes a submission in another chat, reloads and returns to the first chat. The retry waits for its original connection and preserves its request ID, model and tier. The test also recovers an older pending command whose intent was overwritten and checks that a newer revision cannot resume the earlier intent. | Saving or clearing an intent affects only its conversation revision. A recoverable earlier preparation command takes precedence over new planning. |
| Staged planning recovery uses the durable model settings | A verified planning request is interrupted after staging but before plan publication. A fresh workspace resumes with the original price ceiling even when catalog access would fail. Execution stays paused. | The original scoped admission controls replay before new-selection checks. |
| Older follow-up recovery preserves the original request ID | Browser cases check an existing receipt, an empty lookup and a superseded brief without posting an action. A real loopback test holds the original POST open, rejects one explicit resend and lets a second resend reach SQLite before releasing the original. Both successful submissions observe one follow-up and one fake-provider routing call. | An empty lookup keeps the request pending. An explicit resend uses the same ID and exact inputs. A newer saved revision fences a still-uncommitted request. |

Admission mutation probes remove the serialized model-settings comparison
for follow-up staging and admission, routing, and copy revision. Each
corresponding regression detects the removal.

## Recorded report monitoring

| Invariant | Offline evidence | Boundary |
| --- | --- | --- |
| A restart after import preserves one check and one observation per business | A child process exits after four outcomes and their receipt commit but before schedule progress. A fresh process recovers the same receipt after lease expiry. A cumulative final recording adds 750 distinct outcomes and finalization counts 754 observations, including 74 controls. | The schedule freezes normalized reports and uses one scoped import request ID for each position. Import and schedule progress commit separately. |
| Only a due and authorized check may import | Real SQLite rejects a substituted job, a stale revision and a wrong organization. Pausing fences an existing claim. Expiring a lease after writes but before commit rolls back the import. Cadence changes preserve the cohort cutoff. | The scoped plan and lease are checked inside the import transaction. |
| The workspace preserves the cohort clock and separates finalization from monitoring | A verified fixture rejects a stale check, restarts after advancing its clock and processes the due recording. A browser test confirms the displayed check, sees the verified watermark and finalizes explicitly. A restored checkpoint exposes the schedule for inspection and rejects a check. | Monitoring checks recorded synthetic files. Learning applies the existing maturity and population rules. |
| Upload retry after reload preserves one schedule and its exact inputs | Browser cases drop creation before dispatch and after commit with two uploads exceeding session-storage capacity. Reload retries the original request ID, report contents and settings. SQLite contains one schedule, two sources and zero observations. Cadence, pause and resume survive reload, including a lost pause acknowledgement. Storage failure makes zero upload requests. The form stays within a 390px viewport. | Pending uploads live in browser IndexedDB before dispatch. The existing scoped learning command commits the schedule and sources together. |
| Rejected uploads cannot leave an earlier request free to commit | A SQLite test rejects duplicate JSON fields, records the original request fence and rejects a delayed valid submission under that ID. A response-projection failure after successful creation recovers the saved receipt. HTTP tests enforce Host, token, Origin, report-size and displayed-job bindings. | A rejection marker is returned only when the original request ID is durably fenced. An existing committed receipt retains its identity. |

Verification for workspace monitoring controls passed with 864 backend tests,
108 browser tests, the production build, formatting, architecture and all
385 declared mutation probes. The committed-request rejection assertion also
passed in its final focused run. Reports and outcomes in these checks are synthetic.


## Conversational multichannel authority and recovery

See the [bounded validation model](conversational-sequences.md#validation-model). The new real-SQLite tests cover both installed companies from one objective to unapproved review, one exact confirmation through synthetic completion, explicit human task observations, read-only replay, subprocess recovery, atomic message admission, original consent and keys, stale material revisions, cancellation during a reserved model call, late usage without publication, detached native inputs, reviewer disablement, organization scope, verified-mode rejection and schema-22 history preservation. Cheap interpretation cases cover fuzzy uniqueness, focused ambiguity, unsupported scope and complete replacement objectives. Browser cases exercise the same server authorities through chat. Existing approval, full-basis expiry and transactional acceptance regressions are retained. Verification results and the bounded invariant ledger follow.


| Protected invariant | Trigger and independent observable evidence |
| --- | --- |
| Installed scope is retained | Pure cases resolve both profiles and a unique typo; ambiguous scope asks one question. Country, provider, company, connection and budget substitutions are rejected rather than replaced. |
| Preparation and publication retain their source | Material edits and stop during a reserved call retain one recorded usage receipt, produce no artifact and admit no next call. Unknown outcomes retain the original run and reservation. |
| Conversation allowance cannot reset through native scope | A real prepared journey loses task origin fields, execution links and optionally its account. Immutable journey scope still locates receipts; allowance stays unknown and a new message/admission cannot commit. |
| Human review binds the exact proposal | Both company journeys reach an unapproved subject. One confirmation completes their bounded simulation; a different subject/reason, source revision, tenant or disabled reviewer cannot acquire authority. Existing full-basis expiry and native acceptance checks remain in force. |
| Restart reuses original effects and observations | A subprocess resumes original review and simulation keys. Failure after native human-task observation and clock advancement replays its frozen time. A stale tab's second key remains the same logical observation and the journey completes. |
| An unfinished call holds only its dependent follow-up | A real SQLite journey accepts the day 1 call, restarts, and accepts another account's day 2 call without any completion observations. Completing only the second call permits its day 4 follow-up while the first account still waits. A later explicit observation completes the remaining follow-up with six total submissions, two observations and no additional model calls. The workflow uses the native simulator's dependency assessment rather than treating any open call as a global pause. |
| History survives schema changes | A real schema-22 store retains original artifact bytes and legacy cutoff. Failure after schema-23 DDL rolls the migration back; successful reopening adds the new tables. Existing checkpoint and v1/v2 compatibility cases remain intact. |
| Paused formats cannot gain execution | Verified mode rejects sequence admission before message, journey or run commit. Restored roots retain their inspection-only boundary. |
| Presentation cannot create authority | Browser reload reads progress without inference or repeated acceptance. Exact confirmation freezes the displayed subject/revision. A late response cannot replace a newly opened chat. An email/call objective starts a new revision rather than answering an earlier postal budget question. |

Verification recorded on 2026-11-15 in the isolated #68 worktree:

- `make test`: 1,005 tests passed in 2,089 seconds. This broad run was followed by the final 13-case journey suite and focused changed-surface checks, including the two durability cases added after its discovery.
- Final journey suite: 13 tests passed. The final human-task recovery/duplicate-observation refinement also passed its complete two-company path separately.
- Execution regression suite: 58 cases passed in the restricted run; its one loopback case passed when rerun with socket access. The full broad run had loopback access and passed.
- Database initialization and orphan-receipt checks: 10 cases passed. Two fresh standalone channel-content compatibility/uncertain-call checks passed.
- `make arch-check`: passed. `git diff --check`: passed.
- `make interface-check`: production build, formatting and 111 browser cases passed. The subsequently added postal-budget-to-sequence transition regression passed separately. In-app browser inspection also reached completed synthetic simulation after one approval and explicit human task observations.
- Six selected, valid #68 mutations were detected: company binding, budget binding, detached generation input, cancellation fence, frozen task-observation time and immutable receipt-scope discovery. The full repository mutation suite was not rerun for this slice.

Fault probes cover admission rollback, confirmation acknowledgement loss, stop/edit during a reserved call, unknown provider outcome, native observation/clock commit before continuation progress, and migration interruption after DDL. These are bounded offline control checks, not live-provider, arbitrary-language, multi-worker or commercial-outcome evidence. Local Python verification used 3.14; other versions remain covered by the existing CI matrix when this branch is published.


## Returning a sequence conversation to postal preparation

The `d37c43a` review found that any historical sequence row permanently selected sequence routing in the server and browser. Routing now considers only the request's source revision, and an affirmative, unambiguous postal objective goes through native message admission and existing postal preparation. The literal-scope v1 resolver and all immutable historical inputs remain unchanged. Read-only questions and mixed channel requests cannot select postal preparation through this shortcut.

Cheap real-SQLite routing tests reproduce the original failure, then verify both message/action entry points, original command replay after restart, preserved sequence inputs, historical presentation, native postal status routing, and existing postal preparation reaching fresh unapproved review with its shared call accounting. Pure cases cover affirmative, negated, mixed and read-only channel wording. Browser cases exercise fresh submission and a recovered sequence-routed command, reload at audience confirmation, unapproved postal review and subsequent native postal follow-ups. Two selected mutations remove the postal escape and current-revision filter independently.


Postal-return fix verification on 2026-11-15: `make test` passed all 1,010 backend cases; `make interface-check` passed build, formatting and all 114 browser cases. The six focused scope/routing checks also passed after the final request-validation refinement. Both postal-return mutation probes were detected, and `make arch-check` and `git diff --check` passed. No native binding, execution-account, approval or historical artifact format changed.

## Independent schedules while a call awaits completion

The conversation workflow now waits only when the native simulator reports that every remaining pending step needs human task completion. Another account's scheduled call and follow-up can proceed while an unfinished call continues to hold its own follow-up. Dependency rules, exact native acceptance checks, synthetic clock persistence and historical artifact formats remain in their existing modules.

Verification on 2026-11-15: all 17 focused journey tests passed. `make test` passed all 1,011 backend cases in 2,043 seconds, including all 19 workspace HTTP cases with loopback access enabled. `make arch-check` and `git diff --check` passed. The selected `sequence-journey-independent-schedules` mutation restored the original global pause and was detected by the new real-SQLite restart regression. No frontend files changed; the browser suite was not rerun for this fix.
## CI performance and mutation experiment boundaries

Backend discovery remains partitioned by module, so class fixtures and isolated
SQLite roots stay together. The sequence estimate now uses the approximately
143 seconds observed in the Python 3.11 run 43639063387; other estimates remain
approximate. Each shard reports estimated and elapsed time and uploads individual
test and class setup timings. These measurements can guide later rebalancing;
they do not predict the performance of a different Python version or machine.

The mutation catalogue is distributed deterministically across four CI jobs.
Every declared probe still gets a fresh source copy and interpreter. Estimates
are initial scheduling weights, not measured per-probe durations. Execution
stops on the first test failure. A failure or unexpected exception from the test
body detects a mutation; loader, setup, teardown, cleanup, skipped and timed-out
experiments cannot count as detections. Regression checks exercise these
classifications and verify that both sharding schemes retain every case once.
Superseded pull request runs are cancelled. The Python version matrix and the
single browser worker remain unchanged. No production authority or SQLite
reconstruction is cached by these changes.

The journal cleanup regression now creates a minimal real SQLite journal and
retains the invalid identity and open writer-lock checks. This keeps the same
observable boundary without preparing a campaign first. The previous mutation
changed normal preparation itself and failed in that fixture, so it never
reached the lock-release check; the isolated target now reaches and detects it.

Verification: `make test` passed 981 tests with loopback access and
`make arch-check` passed. The full run loaded the original lock fixture before
it was isolated; the final isolated test and its mutation passed separately.
All 484 declared mutations were detected across four shard runs and targeted
reruns. Three probes were rerun after result classification changed, one after
isolating its fixture, and three with loopback access after sandbox setup errors.
The timing artifact was also checked with a small two-shard smoke suite. These
local checks do not establish a CI speedup.

## Reconstruction reuse and isolated browser partitions

Current-source parsing can be reused only inside one evidence invocation after
comparing every stored field with a freshly queried row. Current head, latest
version, installed attestation and final profile reads remain in place. Each
invocation still rebuilds readiness, history, objections, suppression, epochs and
time. The extended contact regression rejects an attestation change after the
report clock and changed source bytes within the transaction. The new mutation
probe removes that final check. The 23-test contact module and 54 selected
contact, strategy and sequence mutation probes passed.

Browser CI now partitions by file into two jobs. Each job retains one worker,
its own server root, fixed shard-specific port and separate test evidence and
JSON report paths. Explicit screenshots use per-test paths. Discovery verified
108 distinct IDs across the 63/45 split without omissions or overlap. A shared
three-second test delay was replaced by the existing explicit release marker
when concurrent runs exposed its race. The test still stops actual in-progress
work and verifies receipt settlement before starting a new brief.

See [CI execution cost](ci-performance.md) for reproduction, profile counts,
isolation details and remaining scope. Profile counts show fewer parses with
the same number of evidence and final source checks; no hosted CI speedup is
claimed. Python compatibility policy remains unchanged.

The measured browser file weights replaced the initial 63/45 built-in split.
The final explicit whole-file partitions passed 49 and 59 tests concurrently,
with no skips, flaky retries or unexpected results. JSON reports verified distinct
ports 8770/8771 and durations of 267.8/310.6 seconds on this machine. Both builds
and frontend formatting passed. These local timings are not hosted CI timings.

Final verification for this slice: `make test` passed 982 cases with loopback
access, architecture and whitespace checks passed, and all 54 selected contact,
strategy and sequence mutations were detected on the settled implementation.
The final 23-test contact module also passed separately after extending the
source-byte regression and retaining the final profile read. Frontend production
build, formatting and both complete browser partitions passed (108 total).
The complete 485-probe catalogue was not rerun for this slice. No live provider
or billing behavior was exercised.

This slice was implemented and measured on merged baseline `0ffba90` (PR #84).
During verification, origin/main advanced through `b88e632` (PR #85), adding the
sequence-review path from the original assessment. That integration is not part
of these verification results; the local CI branch has not been rebased onto it.

## CI follow-up on exact sequence review

`fix/ci-review` was rebased onto fetched main `b88e632` (PR #85). The mutation
conflict retained all new review probes, the 300-second sequence timeout and
strict fixture/loader classification. The pressure/calendar test moved to a pure
class with the same asserted thresholds, synthetic source values and product
dates. Both existing mutation targets follow its new identity. Review templates
now build only fielddesk, reuse each distinct source variant once per class and
copy SQLite stores per case. The full evidence-basis test asserts that these
copies leave templates free of proposals, approvals and simulations.

Contact history parsing may reuse a current source only if the history query
returns every identical stored field. Independent historical rows and all final
source, attestation, profile, reviewer, epoch, clock and commit checks remain.
The added mutation substitutes the current source for unrelated history; the
existing equal-time permission conflict regression detects it. The profiled
review case retained 3,308 evidence and 6,622 current-source checks while reducing
source parses from 6,697 to 3,385. Concurrent local timings do not establish an
elapsed speedup. Sequence/review shard estimates now cover both slow modules.

Verification for this follow-up completed the production build,
frontend formatting, architecture, whitespace and CI-tool checks. Both isolated
browser partitions passed all 108 tests on the rebased backend. Backend discovery
found 998 distinct IDs without duplicates or loader errors. All 79 selected
sequence/review, contact and strategy mutations were detected across two
partitions and targeted reruns. Two initial experiments had invalid loader
targets after the pure test moved; those targets were updated and both mutations
were detected by the relocated pure test. The added history-row mutation passed
separately. The complete 510-probe catalogue is not claimed as rerun here.
Two mutations targeting the original two-profile scenario were rerun after
correcting a fixture-refactor loop typo; both were detected on the corrected
scenario. The final 79-probe result uses those corrected runs.

Final `make test` verification passed all 998 backend tests with loopback access
in 1,459.8 seconds. This includes all sequence-review, two-profile, SQLite restart,
expiry and migration cases on the corrected final source. The full basis and
history regressions also passed separately with cached-template isolation checks.
`make arch-check` and whitespace checks passed. Browser partitions passed 49/59
cases without skips or flaky retries, alongside build and formatting. No live
model calls were made and no hosted CI speedup is claimed.

## CI timing collector compatibility

PR #86 exposed a telemetry failure across every Python version: a historical
budget fixture assigns a string to `self.id`, shadowing `TestCase.id` after
setup. The timing collector now captures the base unittest identity before setup
and uses that saved value at completion. A regression reproduced the runner crash
before the correction and then passed. All four CI-tool tests and all four real
historical-budget cases passed through the timing runner, retaining four timing
records. Architecture and whitespace checks passed. This changes timing metadata
only; the fixture and its product assertions are retained.

## Report-local sequence material construction

Sequence report construction can pass completed payload materials to its
campaign validator within that report. The independent final current-proposal
reconstruction remains mandatory. No material map, positive readiness report or
approval authority is retained across reports or transactions. Failed payload
checks leave the map absent and keep the campaign check's independent fallback.

The existing required-check/checker-failure regression now injects changed
artifact bytes after the payload checker returns. Payload validation has passed,
but sequence-contract validation must fail and withhold readiness. A new mutation
removes the final current-proposal reconstruction and is detected by this fault.
The same regression first reproduced nine material constructions and now asserts
six per passing report. Actor, epoch, final clock, expiry, lease and effect-commit
paths are unchanged; their existing fault and mutation cases are retained.

Three unprofiled serial repetitions of each unchanged benchmark method measured
median case time reductions from 16.04 to 10.83 seconds (32.5%) for approval and
restart, and 50.03 to 35.59 seconds (28.9%) for complete evidence-basis expiry.
Measurements include per-case setup/cleanup; shared setup is recorded separately
in suite elapsed samples. Source hashes and test-method AST equality bind the
comparison. See the [raw samples](evaluations/sequence-review-material-reuse-2026-11-15.json).
No hosted or whole-suite speedup is claimed from these case measurements.

Verification passed all 999 backend tests (`make test`, with loopback access),
all 80 selected sequence/review, contact and strategy mutations, architecture and
whitespace checks. The new final-current mutation was also detected separately.
The full 511-probe catalogue was retained but was not rerun in this slice. The
full backend run took 1,117.5 seconds while mutation verification overlapped its
early portion; that elapsed result is verification evidence, not the paired
performance comparison. No frontend or schema changed and no live model call was
made. Review of the changed call graph found no removed final authority boundary;
input reuse is confined to the successful payload-to-campaign handoff in one
report, with the existing independent current-source reconstruction retained.


## CI support and gate audit, 15 November 2026

Python 3.11 is removed from CI and the advertised minimum is now 3.12. The
remaining runtime matrix is unchanged. Architecture scanning runs once and early;
frontend formatting runs in one interface partition. Both isolated browser jobs
still compile and serve their own production assets. Historical measurements and
compatibility artifacts are preserved.

The [gate audit](ci-gate-audit.md) summarizes the configured checks, their
protected behaviors, costs and limitations. It distinguishes compatibility
cadence and formatting policy from application behavior, and records the mutation
harness limits and observed absence of required merge checks. Production code, repository protection settings and authority boundaries
are unchanged.

Backend shard weights use median case plus class-setup costs across 3.12, 3.13
and 3.14 in PR #87. The [gate audit](ci-gate-audit.md) records the source run
and measurement limits. Both groups together retain all 999 cases, with no
missing or overlapping IDs. The existing coverage regression now also rejects loader
errors instead of accepting failed imports as discovered coverage. All 511
mutation targets remain in their existing four partitions. The new shard costs
are projections until a hosted run measures the changed allocation.

Verification passed all 999 backend cases with `make test` on Python 3.14.3
(1,616.1 seconds), plus the final focused CI-tool and architecture self-tests.
The backend run overlapped the initial browser runs, so its elapsed time is
verification evidence rather than a performance comparison. Production build,
formatting, `make arch-check`, workflow validation with actionlint 1.7.12,
whitespace, support-contract and audit-link checks passed. The original 59 module
weights reproduced the saved module medians; the current allocation retains the
20 highest measured weights.

The full mutation catalogue was not rerun for this CI configuration change.
PR #87's recorded run passed all 511 variants on the unchanged production code,
mutation harness and target regressions. No live model call was made.

The two initial local browser partitions passed 97 of 108 cases, with eleven
fixture-start, completion-wait and test-deadline failures while the full backend
suite ran on the same machine. Initial reports and traces were preserved. After
backend completion, only those failed IDs were rerun, one partition at a time:
all four first-partition cases and all seven second-partition cases passed
(31.6 and 42.3 seconds). Identity comparison verifies those reruns exactly cover
the eleven initial failures, yielding passing evidence for all 108 distinct
cases across the attempts. No assertion, timeout, retry configuration or
application code was changed. This is consistent with resource contention; it
is not a claim of a clean initial run or a measured CI speedup.


## Mutation assertion evidence

Mutation detection now requires a test assertion failure and rejects unexpected
test-body and subtest errors, in addition to fixture and loader failures. The
existing harness regression exercises both crash paths and a valid assertion
failure. This narrows what a detected mutation means; it does not establish that
every assertion is the intended behavioral oracle.

The first strict hosted run reported 48 invalid experiments. Existing tests now
make their expected result explicit at the relevant boundary, including the
required rejection type, required fields, replay success and lock release. The
workspace lock case prepares its fixture independently of the mutation before
exercising the unpatched read under a real SQLite writer. Each of the 48 named
mutations was detected in a targeted rerun, and the corresponding unmutated
tests passed. These assertions establish the stated behavior and error contract;
a wrong error type alone does not prove that an unauthorized effect occurred.
The complete catalogue remains the final CI check.


## Single Python runtime for CI

The backend, mutation and browser jobs now use Python 3.14. The backend remains
fully discovered across two shards, and the mutation catalogue and both browser
partitions remain unchanged. Python 3.14 is the minimum required version; CI
does not establish compatibility with other versions. The change removes four
backend jobs, so it reduces repeated runner work. Because jobs run in parallel,
its effect on the critical path depends on the remaining slowest job.

Verification on Python 3.14.3 passed all 999 backend tests, all 511 declared
mutation probes (run locally in two isolated partitions), the architecture and
CI-tool checks, the frontend production build and two Chromium review flows.
The workflow passed actionlint. The backend run overlapped the mutation and
browser checks, so its 1,257.5-second duration is verification evidence, not a
before/after timing comparison. The complete browser suite and hosted CI were not rerun for this change.

The first hosted browser partition exposed an asynchronous test race after a
monitoring pause: the server's new revision appeared before the browser had
finished clearing its saved request. Reloading at that point correctly showed
recovery instead of the resume control. The existing test now waits for the
enabled resume control before checking pause persistence across reload. Its
separate lost-pause-response branch still checks recovery. Both committed and
uncommitted creation-response cases passed three focused Chromium runs each on
Python 3.14; no production code or retry policy changed.

## Contact identity reconstruction, 16 November 2026

Connection validation and identity hashing read the same declared strings
directly, without caching identity or authority. The existing alias/objection
regression verifies literal historical connection and native IDs, scope, aliases
and invalid values for each connection field. The provider-account mutation now
targets the equivalent new expression.

Three serial runs of two unchanged sequence-review cases measured median case
times of 10.59 → 9.24 seconds and 34.41 → 30.06 seconds. The [performance
record](ci-performance.md) includes all samples, source hashes, profile counts
and limitations. Both profiles retained the same current-source,
current-proposal, readiness and authorization call counts.

Verification passed all 999 backend tests (`make test`, 1,139.0 seconds), the
architecture check and the final focused identity tests. Six targeted mutations
were detected: provider-account scoping, exact-row history reuse, final source
attestation, final current-material validation, final clock and the complete
readiness window. All 511 mutation definitions still match one source location
and compile; the full mutation catalogue was not rerun. Full-suite elapsed time
included overlapping focused verification and is not a before/after benchmark.
No live model calls were made.


## Exact installed snapshot reuse and four backend partitions, 16 November 2026

Installed synthetic contact snapshots may be reused only after a scoped source
lookup finds exactly the same serialized payload. The new contact regression
warms reuse, checks nested immutability and organization/key/version separation,
then replaces, corrupts and removes the installed payload. Replacement is
revalidated; invalid or absent evidence cannot fall back to the old value.
Source identities are still recalculated and final SQLite source, objection,
reviewer, epoch, expiry, lease and acceptance checks retain their existing paths.

The existing CI discovery regression now checks both two and four partitions
against every discovered test ID with multiplicity. Modules stay intact, so
class setup is not multiplied. Invalid partition selections are rejected.
Architecture and focused CI/contact checks passed. All six selected harmful
mutations were detected, including removal of exact-payload reuse binding,
final installed attestation, exact durable row binding, final proposal
reconstruction, final authority clock and complete readiness-window validation.
The complete 512-probe catalogue is retained and was not rerun locally.

Three serial repetitions of unchanged review methods measured median case
reductions of 20.5% and 22.5%, without concurrent verification workloads.
[Performance evidence and measurement limits](ci-performance.md#backend-critical-path-16-november-2026)
separate those local case measurements from the four-partition replay estimate.

Full backend verification passed all 1,019 discovered tests across the four
proposed CI partitions. Recorded IDs matched fresh discovery exactly once,
including real SQLite, process restart and authority tests. The initially
started serial `make test` was intentionally stopped in favor of this complete
four-partition verification; it is not recorded as a successful serial run.
No browser or frontend code changed. No live model calls were made.


## Prepared conversation fixture isolation, 16 November 2026

Conversation-action and conversational copy-revision cases reuse only a prepared,
quiescent workspace template, copied into a new root per case with independent
fake provider state. They open the real SQLite stores and read base review state
afresh. All 72 existing test methods and their assertions are unchanged; no
production authority path was modified. Clarification and multi-segment setup
remain fresh, and campaign preparation retains its own workflow tests.
Execution-control and legacy-replay classes borrow the setup methods directly;
their explicit fallback retains fresh preparation without requiring the owning
class lifecycle. Full-suite verification caught this dependency before publication.

A separate isolation experiment for each prepared class approved and amended
one copy and changed its model history and filesystem. The other copy remained
at revision 1 with a valid candidate and no approval, unchanged model history
and no extra file. Template file hashes were unchanged. All 29 existing mutation
probes targeting the two modules were detected, including exact preview/result
binding, explicit consent, changed admission text, final confirmation authority,
routing admission and atomic native confirmation. The full 512-probe catalogue
was retained and was not rerun locally. Architecture checks passed with 175
classified modules and 28 declared temporary exceptions.

The serial before/after measurements include shared setup. The 72-case module
run changed from 157.50s to 73.66s (one sample each); a four-case cohort changed
from median 11.71s to 7.80s across three runs each. These are local measurements.
[The performance record](ci-performance.md#conversation-preparation-fixtures-16-november-2026)
retains evidence and partition-calibration limitations.

Final verification passed all 1,027 backend cases across the refreshed four
partitions (151, 280, 265 and 331 cases), including all borrowed-setup execution
and legacy-replay cases. Recorded IDs matched fresh discovery exactly once.
The complete backend discovery suite was verified with `make test-shard`
for all four partitions instead of a separate serial `make test` rerun.
Final architecture and CI-tool checks passed, and all 29 relevant mutations were
detected again after the compatibility fix. No live model calls were made.


## Routine CI cadence and prepared fixture extension, 17 November 2026

The MVP policy keeps the entire backend authority regression suite, architecture,
frontend build and browser checks on pull requests. The 512 mutation probes audit
test strength and now run only through the explicit manual workflow. That audit
keeps its existing strict rejection of fixture, cleanup and unexpected body errors.
No application validator or authority check has been removed.

Execution, execution-follow-up, native copy-revision and follow-up classes opt
into quiescent prepared workspaces. Each case receives independent SQLite files,
journals and fake provider state, opens a new Workspace and reads current base
review state. The original fresh fixture paths remain for unconverted borrowers,
source-fence interleavings and the original handoff workflow tests. Static AST
comparison retained all 103 test methods across the four edited test modules.
Architecture passed with 205 classified modules and no temporary exceptions.
Full runtime and mutation verification is delegated to GitHub to avoid sustained
local CPU load. Hosted results and aggregate compute are recorded in the PR.

The hosted run exposed additional admission and workspace-authority classes
borrowing follow-up setup directly. Every newly prepared class now explicitly
retains fresh setup for external borrowers. The backend and strict mutation
runner rejected the initial fixture errors; no invalid experiment was credited
as a mutation detection. Final hosted reruns verify the corrected fallback.
## Complete offline journey evaluation

The issue-23 runner covers the assembled browser lifecycle at 1440px and 390px,
plus native consent, revision, uncertain-call, incomplete-coverage and restore
boundaries. JSON results and readable evidence bind source and built frontend
hashes to retained exports, screenshots, trace files and synthetic SQLite stores.
Missing results, duplicate cases, recounted observations, a reused process PID,
changed source inputs or network attempts fail the evaluator's own checks. See
the [acceptance contract and reproduction](evaluations/issue-23-offline-journey.md).
The browser lane is the synthetic legacy workspace; verified fixture preparation
and inspection-only restore remain separate native evidence.

Verification passed with 871 tests in the complete backend run and 14 final
focused evaluator/source-attribution tests, including the later native network
regression. The final interface check passed build, formatting and all 110 browser
tests. Architecture and whitespace checks passed. The recorded run passes all six
scenarios and retains 63 verified artifact hashes. The evaluation report preserves
an initially observed, non-reproduced copy-edit stopped state as an unresolved
observation rather than claiming it was fixed.

The review follow-up replaces the fixture's connect-only patch with a shared
scoped Python audit guard for native and server runs. It blocks and records
`connect`/`connect_ex`, datagram sends and hostname resolution before the
operation, including saved method aliases and server-worker threads. The
fixture's fixed loopback server name needs no DNS. This is a Python harness
boundary, not an operating-system sandbox for arbitrary native code.

Downloaded manifests now equal the reviewed manifest, and downloaded acceptance
receipts equal the observed handoff and bind the exact displayed subject,
draft, case and approval. CSV hashes and population counts remain independently
checked. The evaluator also rejects missing or mismatched subject, approval
and handoff identities between its review and export checkpoints. Regressions
reject a coordinated wrong-campaign bundle with identical population counts,
seven receipt-field substitutions and a substituted audience snapshot.

The fresh review run on 20 November 2026 passed all six scenarios, with zero
blocked/external attempts, stable source/build inputs and 63 independently
rechecked artifact hashes. Evidence is retained separately in
`.local/issue-23-offline-review-20261120/`; earlier reports are unchanged.
The source fingerprint is
`23811d03a61ce82719e99a713052eb7e7195100ff6f0f68bd0848d69cf322fe1`.
All seven focused evaluator tests passed, including ten socket/resolver paths
and a server-entry worker probe. The interface check passed build, formatting
and all 111 browser tests. The full backend suite passed all 872 tests in
782.126 seconds. Architecture and whitespace checks passed.

For the PR, the reviewed implementation was carried onto `72ac7cb` in
`feature/23-offline-journey-main`. The fixture uses the existing bootstrap
factory and canonical server entrypoint after the architecture refactor;
current CI sharding remains intact. The seven focused regressions, all six
offline-evaluation scenarios and five architecture-boundary cases passed on
this base. The new journey evidence is `.local/issue-23-main-20261120/`, with
source fingerprint
`238c592fbdbd156c8435a7edd03601d047688ef7b12415a53f4af0c7e26a9da9`.
Its 63 artifact hashes were independently rechecked. The boundary run reported
zero network attempts, stable source inputs and unchanged historical bytes.
The PR records full-suite results separately from the older-branch counts above.

The first PR CI run exposed a harness ordering race: its campaign GET started
9 ms after the approval POST began and finished before the approval response,
so it observed the earlier unapproved state. A bounded 250 ms delay before
desktop approval dispatch reproduces that failure. The driver now waits for
the visible Approved state and closed decision dialog before taking the exact
approval snapshot. Both complete journeys and the export regression pass with
this delay. This changes test synchronization, not application authority.
Final evidence is retained in `.local/issue-23-main-approval-20261120/`; the PR
records final validation and the source fingerprint separately from prior runs.

## Hosting and storage feasibility, parent issue 60, original 20 November 2026

The experiment runs the existing admission, channel task, inference journal,
publication and recovery code over real SQLite and an isolated Turso database.
It adds no production storage selection or CI job. Local and hosted evidence
are distinguished in [the feasibility report](hosting-feasibility.md).

Real hosted checks passed for committed transport reads, fixture generation,
publication rollback, lease loss with recorded-call reuse, unknown-call fencing
and exact replay. The native driver's competing admission failed, while serial
admission and recovery of the original competing request retained one run and
receipt. This is a cutover blocker requiring a supported adapter/transaction
policy, not permission to weaken ownership or retry uncertain model calls.
An initial provider-expiry assumption was falsified and retained as such.
The isolated hosted repeat confirmed the admission idle rollback. After a
twelve-second idle pause, the provider rejected commit and reconciliation
found zero marker rows without repeating writes. A separate redeployment
replayed the original channel run with zero additional calls.

All 1,074 backend tests passed in 1,190.854 seconds. Seven focused probe tests
cover real SQLite workflows, overlapping instrumentation scopes, native binding
semantics, target restrictions, HTTP rejection before storage, credential
redaction and exclusion of private files from deployment packages.
Architecture passed with 209 modules and zero exceptions. The five-case offline
boundary check passed. No frontend or runnable product files changed.

## Hosting feasibility carried onto merged main, 21 November 2026

The review branch `feature/60-hosting-feasibility-main` starts at merged main
`2dcc5f434fe319ebd66f505487a95ae7c6468305`, after PR #119. Its clean-baseline
post-merge smoke passed both browser widths and all four native scenarios,
with stable source/build inputs and 63 verified artifact hashes, before the
feasibility files were applied.

The operator probe, private handler, packaging/client scripts, seven existing
regressions and original cloud JSON were copied byte-for-byte from the prior
worktree. The probe and handler hashes also match the final recorded cloud
package. Credentials, project links and deployment packages were excluded.
No production module, frontend file, schema, root dependency or CI job changed.

Seven focused probe tests and the complete local corpus pass on this base.
The local expiry case is explicitly not applicable; it does not prove remote
transaction behavior. Architecture passed with 209 modules and zero temporary
exceptions. All five integrated boundary cases passed with zero network
attempts, stable source inputs and unchanged historical artifacts.

The [current validation record](evaluations/issue-60-hosting-main-validation-2026-11-21.json)
keeps these checks separate from the preserved 20 November cloud observations.
Remote contention remains a cutover blocker. This branch does not install a
supported remote adapter, redeploy the probe or enable hosted model execution.

The full backend suite passed all 1,082 tests in 1,599.807 seconds. The final
source fingerprint is
`d24a990e0ede1357bf30047506a779825ce6f7a8ba3f3371032de44144387a3a`.
Whitespace checks include the newly added files as well as tracked changes.

## Commit-pinned hosting package review, 21 November 2026

The review reproduced a modified tracked source entering the old package:
`VALUE = 2` was copied even though the selected baseline contained `VALUE = 1`.
The packager now resolves `--commit` (default `HEAD`) once and reads source,
configuration and both probe entries from immutable Git blobs. It never copies
those inputs from the working tree or index. Missing probe entries and unsafe
committed file modes fail before the output directory is created.

The generated `hosting-probe-source.json` records the resolved commit, source
path mapping and SHA-256 of each payload file. Generated runtime configuration
and allowlisted project metadata are hashed too. Operators must commit the
reviewed probe files before packaging; local edits cannot silently enter a
bundle for an older reviewed commit.

The existing packaging regression now covers unstaged source/probe edits,
staged configuration edits, an older explicit commit after HEAD advances,
manifest hashes, missing entries, untracked credentials and committed symlinks.
All seven focused feasibility tests pass. No production or frontend file,
root dependency, CI job or remote deployment changed.

Both retained historical packages also match their previously recorded package
hashes and all 225 source/config files at the recorded baseline. This is a
read-only check of the retained packages, not a new remote deployment test.
The original cloud JSON and carry-forward validation JSON remain unchanged.
The [packaging review record](evaluations/issue-60-hosting-packaging-review-2026-11-21.json)
keeps the later verification separate from those historical records.

Packaging review verification passed all 1,082 backend tests in 1,103.833
seconds, all seven focused tests, architecture (209 modules, zero exceptions)
and all five boundary cases. The source fingerprint is
`b84decd06304d0f454e5c5626ce9fbd38d2b63ee4b8169a7caf8e9b1b4207d58`.
Whitespace checks cover tracked changes and new files.

## Remote libSQL storage and atomic admission

The `remote-storage` slice keeps the domain admission writer and integrity
reader while selecting Hrana 3 storage explicitly in bootstrap. The regression
oracles are independent committed SQLite rows, schema definitions and receipts:

| Invariant | Observable failure | Evidence |
| --- | --- | --- |
| One original admission under contention | Competing independent streams return different receipts or store duplicate runs | `test_turso_storage` concurrency/replay test; opt-in remote process conformance |
| DDL, cutoff and version are atomic | Interrupted initialization leaves a journal or partial application schema | Migration interruption/restart and concurrent initializer tests |
| Unknown commit cannot repeat an effect | Missing ACK causes another run or falsely acknowledges an absent receipt | Lost-ACK and unknown-commit tests |
| Expiry cannot turn a writer into autocommit | A statement following provider rollback persists independently | Provider-rollback test and Hrana 3 server-side transaction conditions |
| Inputs and scope remain bound | Changed input succeeds or a foreign organization sees a receipt | Changed-input and foreign-scope checks |
| SQL values remain exact | Dictionary order, repeated names, literals, large integers or blobs change values | Binding and unpadded-blob tests |
| Remote selection grants no authority | Paused work executes, expired lease publishes, or unknown inference repeats | Existing native boundary suite and optional remote channel recovery |

See [remote storage](remote-storage.md) for transport selection, migration/import
limits and reproducible opt-in checks. Historical hosting evidence is retained.

The [21 November 2026 verification record](evaluations/issue-60-remote-storage-2026-11-21.json)
binds remote and local checks to their source commits and retains the failed
remote observations. Full backend: 1,092 passed. Final focused storage: 12 passed.
Architecture: 213 modules, zero exceptions. Native boundary: five passed, zero
network attempts, source stable and historical bytes unchanged. Current-schema
remote admission, idle expiry, DDL/version rollback, lease recovery and unknown
inference recovery passed on the existing isolated resource. Wider load,
fresh remote provisioning and hosted continuation remain outside this evidence.


## Remote insert row IDs and saved report retrieval, 22 November 2026

Hrana encodes non-null `last_insert_rowid` as a JSON string. The transport must
return a Python integer to SQLite callers, retaining null and integer precision.
Otherwise a synthetic report import can commit its source snapshot with a JSON
string `import_sequence` that cannot match the integer import event sequence.

The HTTP fixture now emits string row IDs. The regression in
`test_turso_storage` imports a valid report through the learning store, commits,
reopens the database adapter and retrieves the saved snapshot and receipt.
It also checks the persisted sequence reference against the actual SQLite event
sequence. Before the fix this failed with `Provider snapshot is unavailable for
this import receipt`. A small cursor contract case covers null and a row ID above
IEEE-754's exact integer range. Historical verification artifacts are unchanged.

Verification on `b9a2471`: `make test` passed all 1,096 tests in 1,117.733
seconds. The focused storage suite passed all 14 tests; `make arch-check`
passed with 213 modules and zero exceptions. The regression used a localhost
Hrana fixture backed by real SQLite. No new live remote or model run is claimed.

## CI partition calibration and optional Chromium, 22 November 2026

Executable revision: `f562f9b`. This slice changes CI scheduling and test fixtures;
production Python and frontend application code are unchanged. The isolated branch
is `feature/ci-partition-and-fixtures`, based on main `5e37b25`.

Confirmed authorities are backend unittest discovery, Playwright discovery,
GitHub's Actions expression evaluator, the real workspace initialization CLI and
SQLite rows in each test's private root. Seven policy contexts were evaluated:
main, main with an irrelevant PR-shaped opt-out, ordinary PR, unrelated PR label,
opt-out alone, opt-out among labels and opt-out removal. All retained backend and
frontend build/format paths remain enabled; only Chromium steps follow the PR
opt-out. Both label activity types are subscribed. Mutation-audit dispatch keeps
its prior cadence. Effective branch-protection configuration was not rechecked or
changed.

| Protected behavior | Regression and observable oracle |
| --- | --- |
| No backend test omitted or duplicated | Existing CI-tool test compares both two- and four-way partitions against fresh discovery, including ID multiplicity. It now also rejects a module split across runners, preserving class setup sequencing. |
| No browser test omitted or duplicated | Actual Playwright JSON discovery found 118 tests; the new partitions contain 38 and 80, with identical union and zero overlap. |
| No shared test authority or leaked run | Fixture activation copies one closed, empty CLI-initialized template into a private temporary directory per test. The existing restore/fresh-root test now verifies an independent copy cannot read a sibling's run. Per-test cleanup and class teardown compare original template bytes. |
| Important checks remain with browser opt-out | Actionlint 1.7.12 passed. Seven actual workflow-expression contexts passed with `@actions/expressions` 0.3.25; build/type, formatting and backend checks remain enabled in each context. Main forces Chromium. |

All 23 fixture test methods are retained. AST comparison found unchanged bodies
for 22; the remaining restore test only adds sibling-isolation assertions.
The positive initialization subprocess moved from per-test setup to class setup;
all explicit initialization rejection and process-restart paths still execute.
The focused five-check run passed in 1.079 seconds. The 23-case fixture module
passed before and after in 51.649 and 47.864 seconds respectively, in one local
pair. This small sample is not a hosted performance guarantee.

The retained [main-run baseline](evaluations/ci-partition-baseline-2026-11-22.json)
is measured Actions data; new partition projections are documented in
[ci-performance.md](ci-performance.md). No test cases, mutation variants or
runtime authority checks were removed. This verification uses no live model or
remote database. Routine Turso adapter tests use a loopback Hrana server backed
by real SQLite; remote conformance is a separate explicit operation.

All 18 existing mutation probes whose target is `test_fixture_activation`
were rerun against the new fixture lifecycle. All 18 were detected by test
assertions; setup, loader and unexpected runtime errors do not count as kills.
This bounded check covers the affected fixture's original mutation targets, not
the complete manual catalogue. It retains evidence that setup reuse does not
mask the existing lease, publication, source, stop and restore regressions.

The complete browser portfolio passed: 38 tests in 382.124 seconds and 80 tests
in 403.967 seconds, with zero failed, flaky or skipped cases. The first command
was `make interface-check BROWSER_SHARD=1 BROWSER_SHARDS=2`; the second test-only
partition started after that build completed. Both servers used independent
roots and one worker. Build/type checking and formatting passed. A full local
backend run was executing concurrently, so these are not hosted CI timings.

`make test` passed all 1,096 tests in 1,258.393 seconds on Python 3.14.3.
This was one complete local run on the executable bytes committed as `f562f9b`;
the browser checks overlapped its early portion. `make arch-check` passed with
213 modules and zero exceptions. No new hosted Actions timing or live remote
conformance run is claimed. The final evidence commit changes documentation
only; executable files remain identical to `f562f9b`.

The [verification record](evaluations/ci-optimization-validation-2026-11-22.json)
retains commit identity, local environment, partition inventory, policy scenarios,
mutation results, measured durations and completed-log hashes. The original dirty
checkout and the separate serverless implementation worktree were preserved.

## Offline journey pause acknowledgement, 23 November 2026

PR #122's first hosted run passed all backend shards and browser shard 1, but
its desktop offline journey timed out. The retained page shows a paused schedule
and an unresolved browser monitoring request. The driver waited only for the
polled Resume monitoring button to become visible before reloading, which can
interrupt acknowledgement before IndexedDB clears the pending request.

The same existing journey now holds the pause acknowledgement after the real
server commits it, proves the Resume control is visible but disabled, and then
releases the response. Without the readiness wait this reproduced the failure
at `cadence-pause-and-resume`: after reload the recovery prompt replaces Resume.
The driver now waits for Resume to become enabled before its ordinary reload,
as the existing chat-review regression already does. All original exact-subject,
export, schedule identity, crash/restart and learning assertions remain.

The outer 120-second test limit is unchanged. Self-created browser contexts now
bound individual actions to ten seconds and navigation to fifteen seconds, so
future failures can produce their phase result and trace before the outer limit.
The held acknowledgement is released during cleanup as well as on the success
path. No application code or durable authority rules changed.

The corrected offline-journey file passed all nine focused cases across three
repetitions in 156.531 seconds: three desktop delayed-acknowledgement journeys,
three mobile journeys and three exact-export negative checks, with zero flaky
or skipped cases. Each desktop result confirms the held pause was exercised.
Formatting and architecture passed (213 modules, zero exceptions). The
[attributable record](evaluations/ci-pause-reload-fix-2026-11-23.json) includes
source and log hashes. Full hosted checks will run on the correction commit in
PR #122; their result is not preclaimed by this local record.

## Lean MVP gate, 23 November 2026

The user authorized a further leaner CI pass within PR #122. Every existing
backend test remains required on PRs. Comparing current discovery with the
actual successful parent-run timing artifacts retained all 1,096 original IDs;
four new small scheduling/scope regressions bring the total to 1,100. Both two-
and four-way allocations preserve ID multiplicity. Modules remain whole except
`SequenceJourneyTests`, whose isolated per-test SQLite backups permit explicit
case partitioning. The allocator charges class setup once per runner using it,
and a regression prevents leaving and re-entering a class within one runner.
No production code, native test body or browser test body changed.

Routine PRs use the 11 existing critical browser cases in
`frontend/browser-smoke.json`. Each entry records the behavior it protects.
Product UI, HTTP, persistence, runtime, composition, recovery/checkpoint,
configuration and unclassified changes automatically select the full suite.
Main always uses full coverage. Explicit full and skip PR labels remain available;
full takes precedence if both are present. Missing change information falls back
to full. A real Git rename regression verifies that the old product path cannot
be hidden by moving it outside a product directory.

The browser catalogue check executes actual Playwright discovery. It found the
same 118 full-suite IDs as the earlier baseline, requires every smoke contract
entry, and proves full partitions 38/80 have identical union and no overlap.
This preserves the larger portfolio while moving unrelated browser permutations
off routine PRs. Backend checks do not depend on browser selection. Only one
interface runner installs tools/builds on routine PRs; the second explicitly
records that it has no selected full partition. Diagnostic uploads are non-blocking,
while test/build/type/format/architecture failures remain blocking.

Local `BROWSER_SUITE=smoke make interface-check` passed all 11 smoke cases in
68.499 seconds, plus production build/type checking and formatting. All eight
CI-tool checks passed in 1.099 seconds. Actionlint 1.7.12 and six actual workflow
suite/shard combinations evaluated with GitHub's expression interpreter passed.
Architecture passed with 213 modules and zero exceptions. Full browser execution
already passed all 118 cases on the parent `3f057dc`; this slice leaves their bodies
and identities unchanged, verifies full selection, and executes the PR portfolio.

The [attributable record](evaluations/ci-mvp-lean-2026-11-23.json) retains parent
identity, source/log hashes, suite policy and the measured-allocation projection.
The new backend allocation projects approximately 336 seconds per shard using
the parent run's observed costs; this includes repeated fixture setup and is not
a hosted timing guarantee. Full hosted backend verification will run on the pushed
correction commit in PR #122. No live model or remote database was used, and no
historical evidence was rewritten.

Browser selection also fails closed if the selection job itself fails or emits
an invalid suite. Both existing interface check names run a fatal guard in that
case, so a failed dependency cannot silently turn required browser checks into
successful skipped jobs. Six suite/shard combinations and all 16 selector-result/
suite combinations passed evaluation against the actual workflow expressions.

## Execute changed browser tests before merge, 23 November 2026

The local review finding on merged PR #122 was reproduced on main `806ab2d`:
a new non-smoke browser test, browser driver, Playwright configuration and smoke
contract each selected smoke-only coverage. The catalogue proved discovery but
could not establish that a newly failing test executed.

Full coverage is now mandatory for browser tests, frontend browser scripts,
Playwright/smoke configuration, the CI selector/workflow and known Python helpers
imported by browser drivers. An existing skip label cannot hide these changed
tests; unavailable changed-path information also falls back to full before the
skip override. Unrelated PRs retain the lean smoke option and explicit opt-out.

The existing scope regression failed with 17 assertions before the fix, then
passed with explicit new/changed/nested test paths, shared helpers, mixed paths,
unknown change information and an existing skip label. The real-Git rename test
now checks both a product file and a browser test moved into a smoke-eligible docs
path. Both old and new paths remain visible to the selector. All eight CI-tool
tests and architecture (213 modules, zero exceptions) passed locally. No test
cases were removed, and production application code is unchanged. Full hosted
checks will verify the fix branch's selected suite before merge.

## Request-bound synthetic serverless preparation

The protected operator surface reuses native conversation and sequence journals.
Its invariant oracles are committed SQLite data, original receipts and actual
call reservations across independent processes, rather than process-local locks.

| Invariant | Regression and independent observation |
| --- | --- |
| Exact start converges | Concurrent starts retain one conversation/journey and reject changed profile or budget |
| One displayed stage per request | Cold-process continuation and same-stage replay retain exact native runs, calls and progress |
| Reads have no work effects | Repeated status requests, including ready review, leave the database dump unchanged |
| Authority stays server-owned | Wrong Host/Origin/token and client organization/role/model fields fail before composition |
| Native leases remain real | A killed claim expires and a cold invocation resumes its original run; late settlement cannot publish |
| Stop fences effects | Stop before reservation makes zero calls; stop after recorded generation cannot publish an artifact |
| Uncertainty survives death | Process exit after reservation and I/O-budget expiry retain one reserved call with no repeat or artifact |
| No approval through continuation | The ready sequence retains zero review decisions and no simulation |

See [serverless preparation](serverless-preparation.md) for bounded request,
clock, storage and preview deployment contracts. These are synthetic operator
checks, not live-model, public-access or autonomous-background guarantees.

Hosted transport reuse retains exact independent request payloads on one HTTP
connection. The focused regressions prove no retry after a lost response on a
reused socket, no redirect forwarding and no submission after budget expiry.
The start-race regression commits an independent original admission between the
first receipt lookup and source read, then requires the original receipt rather
than a revision conflict. Changed-input conflicts remain enforced.

Hosted cadence is frozen separately from lease time. The complete preparation
regression runs on 22 November, rather than a historical fixture clock. The
one-day hourly demonstration still blocks expired product evidence before any
inference reservation. Historical/local multi-day journeys retain their cadence.

Physical HTTP sockets are retired before submission after one idle second. A
real HTTP regression verifies a new socket and exactly one new request; lost
acknowledgements on an active reused socket still receive no retry. This keeps
long operator or provider waits from relying on an old keep-alive socket.

Remote continuation exposed HTTP 429 under the native provenance read volume.
Hosted-only transaction snapshot reuse retains all validation while reducing
identical deterministic SELECT round trips. Aggregate/JSON reads are eligible;
volatile, quoted or commented functions remain fresh. Regressions cover fresh
cursors, exact inputs, write/new-transaction invalidation, combined key/result
bounds and provider rollback before COMMIT, which must prevent dispatch. No
memoized row is used across transactions or as approval authority.

Verification on `2ba484a`: `make test` passed all 1,118 tests in 1196.796 seconds.
The focused suite passed 22 tests. Architecture passed with 216 modules and zero
exceptions. All five native boundary cases passed with zero network attempts,
stable source and unchanged historical bytes. The clean protected Ireland
preview completed seven stages, exact replay and read-only status with nine
fixture calls, three content runs and zero review decisions. Its longest stage
request took 20.221 seconds including CLI overhead. A real process exit after a
remote claim recovered the same task/run after lease expiry, retained three
fixture calls, and preserved cancellation, replay and foreign-scope fences.

See the [commit-bound verification record](evaluations/issue-60-serverless-preparation-2026-11-22.json)
for failed observations, the HTTP 429 diagnosis, provenance equivalence, package
hashes and the operator-only scope. No live model or public release is claimed.

## Hosted continuation stage binding, 22 November 2026

The requested preparation stage is checked against the exact row passed to
workflow selection, after the hosted ownership/preflight read. If a competing
invocation has completed that stage, continuation only observes its progress.
It cannot prepare the next stage, admit its content run or reserve its inference.
A future stage conflicts before the journey's blocking/error handler and changes
no durable state. Existing local callers can still advance without a stage bound.

Two real SQLite regressions reproduced the old behavior before the fix. They now
cover all seven delayed-request boundaries, with a separate cold process
committing the winning request. Exact database dumps remain equal after each
losing continuation. Generation retains one run and three fixture calls per
requested content stage, with no approval decisions. The existing Hrana wire
journey also exercises all seven delayed-request boundaries on independent
connections. These are finite deterministic schedules, not a claim about every
possible distributed interleaving. Verification for this fix is recorded
separately from the earlier immutable deployment evidence.

Verification of source `4a6d94d`: `make test` passed 1,120 tests in 1133.783
seconds; the focused suite passed 24 tests in 43.544 seconds. `make arch-check`
passed with 216 modules and zero exceptions. All five `make boundary-check`
cases passed with zero network attempts, stable source and unchanged historical
bytes. One final full backend run was used for this fix.

The existing isolated Turso database also retained all seven requested-stage
fences, three original content runs, nine fixture calls and zero approvals.
That probe includes partial responses: the first admission conflicted and was
reconciled under its original command; stage 5 failed during status projection,
and the final review winner committed ready before its response failed. Fresh
reads confirmed saved progress, and a fresh stage-6 execution-service replay
changed no durable evidence. Causes of those response failures were not
established. This proves the recorded stage gates and reconciliation results,
not a fully passing remote response-path run. No new deployment was made.

See the separate [review-fix verification record](evaluations/issue-60-serverless-stage-binding-2026-11-22.json)
for exact schedules, source commit, artifact hashes and retained failures.

## Remote response reliability, 23 November 2026

Exact request admission must compare the same values that were frozen, and a
successful stage must remain inspectable within the invocation's bounded I/O
budget. A seeded real-provider probe reproduced one-ULP drift in 121 of 1,000
full-precision timestamp bindings. A separate ready-status read made 1,083 HTTP
requests. The earlier generic exception wrapper hid the distinction between
transport, deadline and provider failures.

Float parameters now travel as exact integer significands with SQL binary
scaling, preserving REAL types and finite binary64 values. The native-SQLite
oracle covers 134 fixed/seeded values, slot identity, repeated bindings, opaque
strings/comments/identifiers, Tcl-style and Unicode names. A wire fixture injects
one-ULP float-input drift independently of the encoder. The complete frozen
message now admits and replays once with its original timestamp. Historical
stored values and request identities remain unchanged.

Journey-current reads use a coherent transaction snapshot. Deterministic
JSON_VALID and read-only WITH queries may reuse exact results inside it; a
write-bearing CTE still executes each time and invalidates the memo. Existing
unknown-function, clock, write, bounds and provider-rollback regressions remain
active. No memo crosses a transaction or connection, grants approval or skips
native commit authority. The existing full Hrana journey now checks ready
status stays within 400 round trips, and its database dump remains unchanged.

Error categories and numeric HTTP status survive wrapping without raw provider
text, SQL parameters or credentials. Redirect/429, pre-submit budget exhaustion,
lost acknowledgements, inactive transactions and uncertain COMMIT retain their
no-retry and no-dispatch assertions. The previous admission/status failures were
retained as evidence rather than rewritten as passes. Focused red tests caught
the admission mismatch and 1,080-call status projection before these fixes.

Counter-review also exercised leading, repeated and trailing Tcl namespace
separators. Native SQLite accepts these parameter names, so they must not be
partially rewritten. The corrected tokenizer matches all 11 explicit edge
forms. A separate seed-23 differential probe generated 3,000 names; all 2,940
accepted by native SQLite retained the same value and REAL type. This is a
finite grammar probe, not a claim about every possible SQL statement. The
first broader run was stopped when this edge case was found; final verification
uses the corrected committed source.

Final verification on `e761b3a`: `make test` passed all 1,126 tests in 1193.561
seconds. The focused storage/serverless suite passed all 40 tests in 50.393
seconds. Architecture passed with 216 modules and zero exceptions. All five
native recovery boundary cases passed with zero network attempts, stable source
and unchanged historical bytes.

The real Turso cold-process conformance run passed all seven stages, original
replays, read-only status and changed-input rejection. Its slowest stage took
45.703 seconds. The protected Ireland preview of the same committed package
also passed concurrent original starts, all seven HTTP stage responses and
replays, changed-input rejection and repeated read-only status. Its slowest stage
request took 17.639 seconds including CLI overhead. Each exact journey retained
three content runs, nine recorded fixture calls and zero review decisions.
The committed-source package contains 236 verified payload hashes. No live model,
new resource, production promotion or outbound delivery was used.

The earlier generic failures cannot all be classified retrospectively. The
reproduced admission precision mismatch and excessive status reads are fixed,
and both final remote response paths now pass. Interim numeric/timing probes
remain candidate-worktree observations; the full, boundary, cold-process and
protected-preview results bind to the final commit. The initial preview helper
incorrectly counted historical calls in the shared native scope; an independent
read confirmed 18 global calls versus nine for its exact journey. The final
helper checks exact journey run IDs and proposal, preserving all history.

The separate [response-reliability record](evaluations/issue-60-remote-response-reliability-2026-11-23.json)
retains those observations, red tests, the interrupted earlier full run, final
results, source/package identities and evidence hashes. Historical reports were
not regenerated.

## Remote binding review corrections, 23 November 2026

Two P2 review findings reproduced against source `191d7ae`: internal REAL CAST
affinity changed which TEXT rows were selected or updated, and numbered aliases
could expose the encoded integer significand instead of their named slot's
float. Two differential regressions failed with 19 assertions before the fix.

The exact-value expression now has no affinity, matching a native parameter.
The native SQLite oracle covers five column affinities, three floats and 13
predicate forms, plus five UPDATE row-count/result comparisons. Explicit caller
CASTs retain their original meaning. Existing bit-exact finite-number, signed
zero and subnormal checks remain active.

Binding compilation first assigns every slot and its canonical name, including
numbered aliases and later names for earlier anonymous markers. Each marker is
then reconstructed using the value for that slot. Dictionary arguments use
explicit Hrana prefixes, preserving distinct `:x`/`@x` slots, integer/blob/text
types and ignored extra keys. Missing canonical names and unnamed gaps fail
before dispatch. The real provider confirmed 15 comparison, update and mixed-
alias checks in a transaction whose probe schema/data were rolled back.

A seed-124 differential probe generated 2,000 alias schedules. All 1,177 accepted
by native SQLite retained identical float bits after reconstruction; the 823
invalid dictionary schedules were excluded by the independent native oracle.
The finite checks do not claim every possible SQL or concurrency schedule.
No durable identities, schema version, deadlines, cache rules or uncertain-call
fences changed. Earlier commit-bound evidence remains immutable.

Verification on `9da95db`: the focused storage/serverless suite passed all 41
tests in 54.291 seconds. `make test` passed all 1,127 tests in 1519.742 seconds.
Architecture passed with 216 modules and zero exceptions. All five native
recovery boundary cases passed with zero network attempts, stable source and
unchanged historical bytes. The real-provider binding probe passed all 15
checks and independently confirmed its DDL/data rollback.

The same committed source also completed all seven cold-process Turso stages,
original replay, changed-input rejection and repeated read-only status. Its
slowest stage took 48.044 seconds within the unchanged 120-second I/O budget.
The exact journey retained three runs, nine fixture calls and zero approvals.
No live model, new resource or deployment was used for this review correction.

The separate [binding-review verification record](evaluations/issue-60-remote-binding-review-2026-11-23.json)
retains both findings, native differential oracles, red assertions, the provider
prefix observation, final commit-bound results and artifact hashes. Earlier
preview and reliability evidence retain their original source attribution.

## 24 November 2026: saved-intake planning

Source `3232ffd8faa7c47b6ac5c670c6fd85b0b5921442` connects exact saved company and brief revisions
to the existing bounded planner. It adds an append-only schema-25 source selection,
separate proposal-only result, guarded loopback API and explicit browser consent.
It creates no campaign, verified product facts, approval or outbound authority.

`make test` passed 1160 cases in 1191.537 seconds. `make interface-check`
passed all 135 Chromium cases, including six new desktop/mobile, competing-tab,
recovery-storage and store-switch schedules. The interface was evaluated on
`b4c145b8ed5743f34f376abb623e72b5cf6e39b3`; the later correction changes only
legacy migration schema bounds and documentation. Its frontend, HTTP and planning
workspace code is byte-identical. Architecture passes with 225 modules and no
exceptions. All five boundary cases pass on the final source with zero network
attempts, stable inputs and unchanged historical evidence.

The first broad run exposed schema-24 upper bounds in legacy migration readiness
and apply. Both now accept schema 25 without relaxing the seal or source checks;
83 focused legacy/inventory/planning cases and the final full run pass. Two of
two semantic mutations were caught: replacing independent intake evidence and
accepting model-supplied authority. Two of two modeled real-process crash points
(after reservation and after receipt) recover without a replacement model call.
The managed Turso probe migrated to schema 25 and passed synthetic source,
competing-write and original-request replay checks with one synthetic call and
zero paid calls, campaign runs or approvals. Older probe binaries require rebuild.

The original dirty checkout is unchanged. No live-model quality, hosted tester
authentication or verified-format execution is claimed. See
[intake planning](intake-planning.md) and the
[dated evidence](evaluations/issue-60-intake-planning-2026-11-24.json) for exact
commands, source hashes, finite acceptance coverage and limits.

## Saved-intake runtime admission review, 24 November 2026

Source `91a4e58e823927510c7aba86f0c779b969b9367c` fixes a recoverability gap: a native
`conversation_plans` row can exist before its runtime run. A later saved-brief
selection previously advanced the managed conversation during this gap and
stranded the original request. The selection transaction now checks the exact
organization, native request, revision and frozen runtime request key against
the runtime run before advancing. Original retries bypass the new-selection
gate. Queued verified runs remain sufficient and retain their execution pause.

The extended real-process regression failed before the fix and passes afterward.
It verifies three of three modeled process-loss positions (after planning-row
commit, call reservation and receipt), rejection despite a foreign run sharing
the key, zero new-selection effects, exact original recovery and later progress
once runtime admission exists. Existing staged-source and six-request checks
remain in place. The real Hrana-wire path and isolated managed Turso probe also
block later selection in the gap and recover the original source. Managed
conformance used one synthetic response, zero paid calls and no campaign or
approval effects. Two of two mutations were caught: accepting the planning row
alone and accepting another organization's run.

`make test` passed 1160 cases in 1223.117 seconds. Architecture
passes with 225 modules and zero exceptions. All five boundary cases pass with
zero network attempts, stable source and unchanged historical artifacts. No
frontend files changed, so the interface gate was not repeated. The original
dirty checkout and earlier evaluation bytes are preserved. See the
[review evidence](evaluations/issue-60-intake-planning-admission-review-2026-11-24.json).


## 24 November 2026: reviewed preparation context

Source `c671be2b1036c307cc6988c2a5b5b7ffa387a01f` adds exact saved-input review
under #131. Campaigns owns an immutable schema-26 preparation context; bootstrap
wires its narrow store for SQLite and Turso. The workspace lets an operator select
description, claims with their original qualifications and references, and CTA,
retain exact campaign requirements, record questions and confirm a one-to-thirty
day input-review window. Selected assertions remain `user_supplied_unverified`.
No context record grants fact verification, campaign approval or generation
authority. References are not fetched and human questions are not automatic
semantic contradiction detection.

One writer transaction rechecks the exact saved source, observed company head,
preview and expected review revision and appends the original command with the
immutable context. Original retries reconcile before stale-selection checks and
never renew expiry. Competing confirmations converge on one original receipt;
new commands against the same prior review conflict. Later company/brief edits,
new reviews and expiry mark old contexts historical without changing bytes.
Independent reconstruction from native source revisions rejects coordinated
rehashing of substituted source and derived payload.

The guarded loopback API keeps organization and actor server-resolved and uses
the original store identity. Browser recovery persists the whole original
command before dispatch, reconciles its receipt first, fences a different store,
and blocks uncertain or corrupt-storage resubmission under a new key. Inspection
restores retain history without write or definite-original-absence authority.
Native process exits before and after commit both recover the original request.

`make test` passed 1171 cases in 1362.598 seconds. `make interface-check`
passed all 140 Chromium cases in 12.8 minutes, plus build and formatting. The
optional validated `BROWSER_PORT=8897` override avoided another worktree's server;
default/CI ports were preserved. Architecture passed with 228 modules and zero
exceptions. All five recovery boundary cases passed with zero network attempts,
stable source and all 34 historical artifacts unchanged. Three of three semantic
mutations were caught: trusting a substituted source, ignoring the current
company head and renewing a replayed expiry.

The existing isolated managed Turso database passed schema-26 review persistence,
two competing processes, foreign-scope refusal and lost-acknowledgement replay
with original expiry retained. Its existing planning regression used one synthetic
response; no paid call or campaign run was created. The context-only phase had
zero execution effects. Manual browser and authoritative SQLite checks retained
one claim, qualification and CTA for each of two different products with no
substitution, zero runs, model calls or approval decisions. Desktop/mobile visuals
and keyboard focus were inspected. The source remained byte-identical throughout
the gates and the original dirty checkout's HEAD, status, file hashes and modes
were preserved.

Schema-25 processes must be upgraded before opening migrated schema-26 stores.
Parallel YouTube migrations and shared integration points require reconciliation
before merge; that worktree was not changed. No deployment, hosted identity,
live-model quality or generation-from-context capability is claimed. The finite
checks establish the exercised schedules, not exhaustive failure-space coverage.
See [the implemented contract](reviewed-preparation-context.md) and
[commit-bound evidence](evaluations/issue-131-reviewed-preparation-context-2026-11-24.json).


## 25 November 2026: preparation review-history reconciliation

Source `a895a842a7f921b970c93baaae1b58fda2929247` fixes the reviewed P2:
reconciling an older original receipt no longer makes a newer review historical.
The browser merges by original request and review revision, preserves the newest
server projection and existing historical reasons, sorts history by revision,
and updates displayed selection from the same merged state. It never promotes
a cached historical record to current. Obsolete in-flight history reads are
cancelled after acknowledgement so that late empty results cannot erase the
saved review. Original recovery waits for the workspace store identity to load;
the original-store check, request binding, payload and expiry remain unchanged.

Three controlled regressions fail against the original component and pass after
the correction. Each schedule passed ten repeats, for 30 of 30 passes: older
receipt after a newer review, delayed startup store identity, and an empty
history response captured before confirmation but delivered afterward. Native
SQLite assertions retain the original payload and expiry, two exact review rows
after competing review, no replay POST and zero model calls or approval effects.
These finite schedules do not establish the precise cause of the reviewer's
earlier intermittent run or every possible browser interleaving.

The first broad run exposed an existing wall-clock-dependent admission test:
its subprocess used the real date after bundled evidence expired on 24 November.
Source `cdd1bf5bbdd45ad019f2762d173b24c2d1a137c1` pins that subprocess to the
fixture's existing 26 October clock before imports capture defaults. Production
freshness checks and evidence were not changed. The first backend and browser
runs were interrupted, retained as incomplete evidence, and restarted on this
committed source for that fixture. The shared browser fixture also used the
real date, which correctly disabled expired synthetic catalogue choices in four
existing offline-example and knowledge cases. Source `c3db76beb06717dfa904a5ae8133b3c0ecc0a58a`
gives only the Playwright-launched shared server a 1 November fixture date plus
monotonic elapsed time. All four targeted scenarios pass. Production freshness
rules, recorded evidence windows, root locking and elapsed-time progression
were retained. The native run then found a second ineffective CLI fixture clock:
it patched a build hook on a compatibility wrapper that no longer owns startup.
Source `d68551499d4aa502b33cf6ac64a4e23eacdc60d3` pins the intended clock before
canonical CLI imports instead. All four CLI review tests pass with the original restart,
receipt, approval and export assertions retained. The earlier monolithic run was
interrupted and final complete backend verification used the existing CI shards.
The shared HTTP fixture also replaced its clock only after composition, leaving
the audience port on the real date. Source `abf57038a2f569bbab3bb56bd7177b0b3201e87e`
injects that mutable fixture clock before composition. Its 19 tests and all other users
in the 40-case intake/admission check pass. The fourth backend partition was
repeated after this repair; the first three retain their earlier source
attribution. No production freshness or authority rule was weakened.

All 1171 backend cases passed through the existing four-way `make test-shard`
runner. Independent discovery and timing-record comparison prove the selected
successful partitions cover every discovered test ID once, without omissions
or duplicates. The slowest partition took 590.267 seconds. The full
`make interface-check` passed 142 Chromium cases, including all 24 intake cases,
plus build and formatting. Architecture passed with 228 modules and zero
exceptions. All five native recovery boundary cases passed with zero network
attempts, stable source and all 35 historical artifacts unchanged. The original
dirty checkout's HEAD, status, protected path inventory, hashes and modes are
unchanged. Frontend, API and browser launch/body code stayed byte-identical during
the final interface gate. Later changes were native CLI and HTTP test fixtures.
Per-partition source attribution and focused
fixture consumer reruns are recorded in the evidence; final boundary checks
bind the final source.
No live provider, schema migration, deployment or paid model activation
was part of this correction. See the
[commit-bound review evidence](evaluations/issue-131-preparation-history-review-2026-11-25.json).


## 25 November 2026: PR 139 merge with native YouTube main

Source `ff9ebba4e6db10a7320f0e46f63c6768aa9003b8` merges reviewed head `be29709` with main
`a1659ce`. YouTube retains its published schema-26 migration; reviewed
preparation appends schema 27. Both bootstrap services, HTTP surfaces, architecture
roles, checkpoint validators and legacy migration bounds remain.

Published intake schema 25, published YouTube schema 26 and the unpublished
YouTube schema-25 preview retain their supported paths. The intact earlier
preparation-only schema-26 preview is recognized by exact context table/trigger
definitions and absence of YouTube objects. It upgrades atomically without
rewriting payloads, source identities, original requests or expiry. Failures after
either addition roll back both; missing guards and partial channel shapes fail
closed. Historical read-only inspection does not migrate.

All 228 focused integration cases passed in 89.425 seconds. These include native
YouTube approval/export preservation across schema-27 review creation, exact
preparation-preview recovery, both migration rollback positions, genuine older
fixtures and real Hrana-wire lost-acknowledgement/concurrent-command behavior.
Architecture passed with 235 modules and zero exceptions. All five native boundary
cases passed with zero network attempts, stable source and
38 historical artifacts unchanged. Frontend build and formatting passed.

The fourth native partition completed all 246 cases and the first full browser
partition completed all 38 cases. Other local partitions were interrupted after
the user reported heat/fan activity; remaining complete coverage was moved to
the existing GitHub CI workflow. Interrupted partitions are not counted as full
passes. One existing uncertain-provider browser expectation timed out while its
copy task was still in progress, then passed three independent repeats with
unchanged assertions and timeouts. The precise timing cause remains unconfirmed.

The original checkout's HEAD, status, protected paths, hashes and modes are
unchanged. The managed Turso check was unavailable because its ignored operator
configuration is no longer present. Earlier provider evidence retains its source
attribution. No live model, paid activation, deployment or new cloud resource was
used. The [integration record](evaluations/issue-131-main-integration-2026-11-25.json)
retains exact source attribution, partial local results and CI follow-up scope.

## Reviewed intake preparation eligibility and grounding (#131)

The [implemented preparation contract](preparation-eligibility.md) separates input
selection, explicit operator source attestation and offline fixture preparation.
The draft binds exact source revisions, selected wording, qualifications, CTA,
requirements and no-model settings. It cannot grant campaign approval or activate
profile model execution. Current sources and review expiry are checked inside the
publication transaction. Existing native artifact tables atomically retain the
original request and exact-context binding, with no new schema migration.

`tests/test_intake_preparation.py` exercises literal product-specific output and
unselected-text exclusion, authority/scope substitution, current-source and expiry
fences, original-request conflicts, complete rollback, lost acknowledgements,
process reopening, two-writer convergence, verified-store pauses and Hrana wire
recovery. The workspace intake browser suite adds required evidence confirmation,
consent reset, mobile/desktop rendering, saved-draft reopening, original-store
recovery and corrupt-storage refusal. Execution results and limitations are
recorded in the dated commit-bound evaluation for this slice.

Executed on 25 November 2026 against source `ff1428d`: `make test` passed all
1,221 cases in 1,308.129 seconds; `make arch-check` passed with 239 modules and zero
exceptions; `make interface-check` passed its build, formatting and all 158 browser
cases with one worker. The five native boundary cases passed with zero network
attempts, stable source and 39 historical artifacts unchanged. An actual checkpoint
restore preserved the exact grounded draft and source review, refused new writes
and retained unchanged database bytes. The full suites ran sequentially. Managed
Turso was not rechecked because the operator configuration is unavailable; the
focused conformance uses real SQLite through independent Hrana wire sessions.
See the [commit-bound results](evaluations/issue-131-preparation-eligibility-2026-11-25.json).

## Issue 143: targeting and qualified-action feasibility, 26 November 2026

Base `74a53bbd7bb0e3d5c1b67ae12d12db6bbcaedda9` (merged #142). The dated
[targeting/data matrix](youtube-targeting-verification.md) selects offline-only
GO for #144. Public documentation is not account/write/delivery proof. The
[reward contract](youtube-data-reward-contract.md) defines a requested,
server-verified generated voice sample; prerecorded playback, preference and
client events cannot become qualified actions. Both numerator and denominator
use one mature, attributed assignment cohort. Current real events are zero for
this protocol; task collection and enforcement remain #133 implementation.

The producer is an authored frozen JSON handoff; its only executable consumer
in this change is an offline checker. There are no production imports, commands,
schema, provider, asset-serving or browser changes. The checker is not runtime
authorization or an event verifier. Future #144/#133 consumers must implement
and test their own admission, receipt, attribution and measurement boundaries.

| Invariant | Finite evidence | Remaining gap |
| --- | --- | --- |
| Documentation cannot grant live authority | CLI rejects changed route readiness, automatic handoff/effects and impression-level interval | No account probe or actual ad setup |
| Reward unit cannot become a proxy | Reject changed reward/denominator, client success, weakened exclusions and implicit failures | No trusted generation receipt/event handler yet |
| Scope and provenance remain explicit | Missing scoped asset/candidate identity and invented real labels/propensities rejected | Runtime foreign/stale identity behavior belongs to future consumers |
| Money is a declared simulation tradeoff | Boolean/inconsistent budgets and changed action-value formula rejected | Not a billing guarantee, calibrated value or spend permission |
| Invalid files do not emit a validity receipt | Duplicate JSON, non-finite number, unknown version and invalid CLI input checked | Not a general-purpose schema validator |

All eight focused checker tests passed. The real CLI emitted the canonical v1
contract hash `d70454c2db829c103d49ad8dcc1698fb50bebd1ef9255ed81fa45ed3242da2d8`
with `live_ready: false`. Architecture passed with 235 modules and zero
exceptions; all 19 relative links in the four changed design documents resolve.
Whitespace checks passed. Full backend coverage is delegated to the review
branch's existing CI shards; it was not rerun locally. No browser or boundary
journey is needed for this non-runtime handoff. No live provider, paid model,
participant data collection, cloud resource or deployment was used. The
[evidence record](evaluations/issue-143-feasibility-2026-11-26.json) separates
these local checks from unexecuted runtime/statistical/live paths.

### Issue 143 review corrections, 26 November 2026

Review base `abab7a86cbc6c3eacd44bce82cf187ef4999e8f7`. Before the fix,
regressions reproduced the missing estimation policy and acceptance of five
independently changed, internally consistent simulation assumptions. An added
variant ID was also accepted inside the baseline. The preceding eight-test
record and `d70454...` hash describe that pre-review candidate, not the current
handoff. This corrects the proposed v1 before acceptance; no installed consumer
or released policy is migrated.

The revised contract requires known manifest, nonempty mature cohort, complete
coverage and zero unknown outcomes for a point estimate or cohort posterior
update. One success and one unknown permits 50% to 100% missing-outcome bounds
and no point estimate or update. Unknown manifest or empty cohort has no bounds.
Partial cohorts cannot be dropped for a favorable comparison. #144/#133 must
implement these rules; no runtime aggregation is added here.

All simulation fields are now pinned with exact type/value/key equality.
Seven days, budgets 10,000/2,000/1,000 pence, 500-pence utility and the 200-basis-
point threshold cannot change under v1. Sensitivity needs a separate identified
contract and validator, not a baseline override. The real CLI rejects invalid
missingness and consistent budget changes without a validity receipt.

All ten focused tests, architecture (235 modules, zero exceptions) and whitespace
checks passed. The corrected candidate hash is
`c7f4129dd6d50e5de4a2c41db4ab0cddf34f31bb6e1829711019ad462df59949`.
The [review correction record](evaluations/issue-143-review-corrections-2026-11-26.json)
preserves original attribution, counterexamples and verification limits. Full
coverage runs in updated PR CI. No live provider calls, account checks, browser
or campaign effects were introduced or executed by the local checks.

## Issue 144: native offline contextual recommendations, 26 November 2026

Base `208826199f2390e90491dbf72466915d29ecdf22`, merged #146. The
[benchmark and measurement handoff](youtube-contextual-benchmark.md) adds a
read-only native recommendation command and typed-tool entry, exact bundled
creative identities, frozen simulation limits and a reproducible evaluator.
Approval, SQL schema, hosted routing and provider execution are unchanged.

| Invariant | Executed boundary | Result |
| --- | --- | --- |
| Native source and authority remain current | Real SQLite campaign read, revoked actor, revision change during ranking, changed asset snapshot, actual altered media bytes and exact command/tool replay | Denial or unchanged unapproved result; no inherited package approval |
| Model proposals cannot establish scope, cost or authority | Foreign/duplicate candidate IDs, invalid fit types, extra budget field, false live-model identity and malformed provenance | Specific ranking/source blockers |
| Unknown evidence cannot become a point estimate or support | One success/one unknown, empty/immature manifests, missing allocation reports, repeated/conflicting receipts, wrong source/reward and partial cell/day reports | Bounds only where permitted; no partial cell/day response update; unknown denominator stays unavailable |
| Reports do not release resources | Issued-allocation ledger survives missing feedback, exploration exhaustion, daily/total limits and changed versions | No refunded budget or silent restart under a new snapshot |
| Independent evaluation can falsify a candidate | Reversed but structurally valid context ranking, independent cost/limit grader and exact known-truth oracle including the no-spend option | Wrong relevance and constraints detected; regret uses compatible expected utility |
| Failed execution does not become a passing denial or continue the batch | Injected unexpected simulation error | Failure report, one invocation, 576 remaining trials not run |
| Report aggregation cannot select complete cases | One complete and one unavailable trial rate | Aggregate rate unavailable |

All 55 focused tests passed, including 21 existing native YouTube flow cases,
10 accepted contract checks and 24 new contextual cases. Architecture passes
with 238 modules and zero temporary exceptions. The full 576-trial benchmark
passes with zero constraint violations and network attempts; source/import
fingerprints remain stable. Its Bayesian candidate is not promoted: the rules
baseline has better stationary expected utility and activation rate, while the
Bayesian policy is better in the authored drift case. Sparse/missing data can
leave rates unavailable, and both policies lose to spending nothing in the
negative-utility case.

An initial prototype result remains in ignored local output. Self-review
corrected per-batch completeness to freeze all cell/day allocations, and
prevented reporting a mean activation rate over only complete replicates.
Priors, epsilon, budgets and scenario surfaces were not tuned to favor the
Bayesian result. The retained current corpus hash is
`9a82400b1695f5fcf0fd489c8f64d556cd07becb74c456f51a4f0f3948ec8b36`.
The [attributable evidence](evaluations/issue-144-offline-benchmark-2026-11-26.json)
records the source overlay, metrics, baseline decision and verification limits.
Full backend/browser checks run in PR CI. No actual LLM ranking quality,
real-response calibration, replay/IPS/DR value or live delivery is established.

The final five-case boundary journey also passed: zero network attempts,
stable source attribution and all 41 historical evaluation artifacts unchanged.
It exercises existing compatibility/model recovery, verified rebuild/replay,
uncertain restart, profile isolation and engagement replay. These are finite
native workflow checks, not hosted/browser or new model-quality evidence.

### Issue 144 review corrections: complete traffic and resumed sampling

Review base `c71cc09`. Three regression methods reproduced both findings:
partial cell/day reports inflated traffic from 2/100 to 102/200 and unlocked
exploitation, while same-day calls repeated the first draw with incorrect
conditional probabilities. Prefix lengths 1, 4 and 7 exhibited the sampling
failure. The preceding v1 results remain historical, not current evidence.

Current allocation policies/recommendation schema are v2. Traffic estimation
requires every member of a closed cell/day group to have mature, complete
exposure and manifest reporting. Partial counts are separately labeled and
cannot affect valuation or its supported draw basis. Response and exposure
completeness remain independent: unknown task results cannot update the
response posterior, but do not discard independently complete traffic reports.
Zero-arrival complete groups contribute traffic denominators correctly.

Each allocation now binds an `allocation-prefix-sha256/v1` draw namespace and
decision ID to the canonical contents of its issued prefix and supported inputs. Changing a
receipt body while retaining its ID changes the draw namespace. Call
partitioning, duplicate/reordered identical history and same-state replay
preserve choices, probabilities and allocation IDs. Subsequent decisions use
different namespaces; calls never restart one correlated random prefix.
Pre-review v1 histories are rejected. These are nominal simulation sampling
probabilities, not certified auction propensities.

All 62 focused tests passed, including conditional choice-mass and same-day
continuation checks. Architecture remains 238 modules with zero exceptions.
The corrected 576-trial benchmark passes with zero constraint violations and
network attempts; source/import fingerprints are stable. It still retains the
rules baseline: stationary expected utility is 19,514.375 versus 14,225 pence
for Bayesian; under drift Bayesian scores 20,562.5 versus rules' 9,407.8125.
These are authored utility units. Economic assumptions, priors, epsilon, truth
surfaces and seeds were not tuned; the v2 corpus is separately identified.

All five workflow boundary cases passed, with zero network attempts, stable
source and 42 historical evaluation artifacts unchanged. The
[v2 correction record](evaluations/issue-144-review-corrections-2026-11-26.json)
supersedes the v1 handoff for current use while preserving its original record.
Full checks run in updated PR CI. No provider/model calls or real participant
learning were introduced.
