# Live MVP deployment plan

Reading status: retained deployment design and dated feasibility context.
Native remote storage and operator-only serverless preparation were implemented
after this plan. Use [hosted preparation](hosted-platform-preparation.md) for
current release gaps, [remote storage](remote-storage.md) and
[serverless preparation](serverless-preparation.md) for installed contracts,
and the [product overview](product.md) for current scope. The original
observations below are not a fresh deployment or capacity claim.

20 November 2026 · Reviewed main baseline 72ac7cb after PR #118

Carry-forward review, 21 November 2026: the feasibility work is now based on
merged main `2dcc5f4`, after PR #119. That PR adds the offline acceptance runner;
the clean merged-baseline smoke passed all six scenarios before these files
were applied. The hosting observations and provider-plan details in this plan
remain the recorded 20 November evidence. This branch adds no supported remote
storage composition, hosted identity or live-model capability.

## Intended experience

Visitors bring an acquisition problem, explain their company and objective,
supply permitted context, and interact with a live agent. The application
persists their work, asks relevant clarification questions, prepares grounded
outputs and obtains exact approval for supported actions. Their own problem
drives the result. Evaluate task completion, output validity and recovery using
actual hosted runs.

The first release prepares and exports campaigns, as confirmed on 20 November.
Visitors bring their own company/product facts, acquisition objective and
supported campaign settings. They review the result and download the exact
emails, human call scripts and campaign plan. Email delivery is deferred.
Source CRM/contact records may be synthetic and must remain visibly labeled.
Model interpretation, generated content, sessions and durable application
storage must be real. The two installed companies remain examples and
regression controls, rather than the only problems a visitor can test.

Keep supported markets and channels explicit. Changed budgets, audience
choices, wording and supported schedule settings must affect the actual
campaign. Unsupported requirements must not silently become defaults.

The free deployment constraint covers hosting, database and model usage.
Use free plans with hard resource limits and an explicit capacity-exhausted
response. Keep provider keys server-side and enforce a zero-price model route.
Current free model limits require measured capacity before opening access.
[OpenRouter limits](https://openrouter.ai/docs/api_reference/limits)

## Product work before release

#68 is complete. Post-merge verification at 72ac7cb passed ten SQLite/HTTP
smoke tests, seven sequence browser tests, architecture and all five offline
boundary cases. Main CI passed after a retry of one existing postal browser
timing failure. Ownership epic #107 is also closed. These establish the
synthetic workflow controls, not a hosted live-model release.

The current multichannel interpreter and copy generator are offline adapters
bound to two installed profiles. A live release needs validated company/product
input, permitted user context, and real interpretation and generation adapters
through the existing ports. Reuse the current fact grounding, consent,
admission, per-run and conversation budgets, stop rules, exact review and
uncertain-call fences. Execute live-model trials against supported user
problems and record both successes and unsupported outcomes.
[Product scope](product.md) · [Ownership contract](run-ownership-admission.md)

Freeze versioned user-provided fact packs and distinguish their provenance
from externally verified product facts. Verify input provenance before
deriving ownership. Bind model settings, source evidence, request, run and
task plan through existing admission machinery. Register new live workflow
contracts deliberately. Selecting a provider must not activate paused verified
formats or relabel synthetic admissions as live work.

The release scope must state which actions visitors can actually complete.
General CRM reads and outbound delivery retain their #69–#73 dependencies.
Real model reasoning and user-specific preparation can be evaluated before
provider dispatch, with the execution mode clearly shown to the visitor.
[Product epic #60](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/60)

The next milestone under #60 is live, hosted campaign preparation and export.
It does not require #69's selected real CRM adapter. Reuse the hosted identity,
tenant isolation and recovery responsibilities in #70 for this narrower
release. Keep full pilot acceptance separate. #71–#73 remain external-effect
work and are not required for preparation and export.

## Candidate deployment

The first candidate is the existing React frontend on Vercel and a dedicated
Python HTTP entry point on Vercel Functions, subject to free-plan eligibility.
All durable application data lives in remote storage. Use the provider
subdomain. No always-on VM or application framework rewrite is part of this
plan. Hobby currently has a five-minute function maximum; bound each work
step and model request below the selected invocation and lease limits.
[Function limits](https://vercel.com/docs/functions/limitations)

Turso Free is the first SQLite-compatible storage candidate. Its Python remote
driver is a replacement for the native SQLite connection adapter. Prove
compatibility with the exact schema, JSON functions, triggers, foreign keys,
row results, transactions, migrations and stored-plan hashes before selecting
it. The existing local-file checkpoint procedures need a remote recovery
procedure. Database credentials belong in adapters.
[Turso Python SDK](https://docs.turso.tech/sdk/python/quickstart) ·
[Turso pricing](https://turso.tech/pricing)

Select the engine and matching remote driver explicitly. Current Python docs
distinguish `turso_serverless` for Turso databases and `libsql` for libSQL
databases. Local files followed by push/pull synchronization are not a shared
transaction authority for concurrent function invocations. The documented
libSQL HTTP transaction window is five seconds. Test expiry, latency and
batching without separating authority checks from atomic writes. Failure to
meet the transaction window is a compatibility failure, not a reason to weaken
atomicity.
[Remote Python drivers](https://docs.turso.tech/sdk/python/quickstart#remote-access-over-the-wire) ·
[HTTP transaction limits](https://docs.turso.tech/sdk/http/reference)

The current root lock and background executor coordinate one local process.
For functions, each invocation should claim and perform a bounded durable step,
commit its receipt, and return. Persist admission and continuation state before
dispatch. Concurrent requests must use database leases and transactional
checks. Browser polling reads progress and a deliberate continuation request
can resume original work after an invocation ends. Reads cannot implicitly
spend model budget. An interrupted reservation retains the uncertain-call
fence and requires explicit recovery.
[Vercel Functions limits](https://vercel.com/docs/functions/limitations)

Specify the continuation guarantee before release. A bounded step can finish
within its invocation and resume original durable work when the visitor
returns. If work must progress after all clients disconnect, prove a free
durable trigger and its retry behavior separately. A daemon thread or
unawaited promise does not establish that guarantee.

Use authenticated server-derived demo sessions and organization scopes, secure
cookies, request origin checks, expiry and bounded per-session resource usage.
Build the hosted entry point through the existing application APIs. The
loopback startup token and local reviewer identities need a hosted access
replacement. Coordinate this work with the applicable #70 access contracts.
[Workspace boundary](workspace.md#local-http-boundary) ·
[Pilot access #70](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/70)

Vercel Hobby restricts usage to personal or non-commercial projects and its
Git integration excludes organization-owned repositories. Verify the intended
demo's eligibility and deployment path before creating infrastructure.
Document the free quota for each selected service, disable paid upgrades and
define what visitors see when capacity is exhausted.
[Vercel Hobby](https://vercel.com/docs/plans/hobby) ·
[Vercel terms](https://vercel.com/legal/terms) ·
[Vercel Git limits](https://vercel.com/docs/limits#connecting-a-project-to-a-git-repository)

## Implementation sequence and acceptance

1. Establish hosting eligibility and run a small Python and Turso transaction
   spike using the existing
   admission, claim, reservation, publication and restart scenarios. Require
   atomic receipts, exact replay and tenant isolation under two simultaneous
   invocations. Measure latency and quota use. Select the precise SDK/engine.
2. Implement remote storage and request-bound continuation through existing
   ports. Preserve local SQLite as the supported local composition. Prove cold
   start, invocation termination, timeouts, lost responses and replay.
3. Implement hosted session access and user-provided profile/evidence intake,
   plus bounded live agent interpretation and generation on a free model.
   Ground every output in the visitor's permitted input and expose incomplete
   evidence or unsupported actions. Freeze company/product facts and changed
   settings by revision. Add exact reviewed exports through existing
   application boundaries. Preserve historical synthetic artifacts unchanged.
4. Release an invite-only preview and test user problems end to end. Verify
   reload, stop, identity isolation, exact approval, output downloads, quota
   exhaustion and uncertain-call recovery. Record the deployed commit, costs,
   model, limits and actual outcomes. Include novel briefs outside authored
   examples and materially different budgets, audiences and wording requests.
5. Open the reviewed demo within the measured free capacity. Retain a tested
   rollback and remote backup/recovery procedure. Apply existing CI checks,
   with hosted smoke after deployment.

Release acceptance requires a fresh visitor to sign in, bring their own
supported problem, obtain genuinely generated contextual outputs, amend the
campaign, review and export the exact version, and reopen it after a cold
start. A second visitor cannot see or change that work. Exercise source/model
unavailability, quota exhaustion, stop, lost acknowledgements and uncertain
calls. Record live model identity, quality, latency and calls per completed
campaign. Never substitute canned generation when the live provider is
unavailable. Hard limits must prevent paid fallback.

The first [hosting feasibility slice](hosting-feasibility.md) has now built
private Python 3.14 previews and exercised an isolated Turso Starter database.
Original publication, lease, uncertain-call and replay checks passed with an
explicit diagnostic driver shim. Direct substitution is not approved:
simultaneous native-driver admission needs bounded contention handling and
original-receipt recovery. The next small implementation slice is the reviewed
remote adapter and migration contract. Live-model/profile/export and hosted
access work then use that supported persistence composition.

The documented transaction window must not be treated as an assumed total or
idle deadline. The probe's six-second expiry hypothesis was falsified; measured
idle behavior and application-owned lease checks remain separate evidence.
The diagnostic previews are private infrastructure experiments, not the live
campaign-preparation release. No paid resource or live-model call was enabled.

Neon Free is an alternative if the Turso spike fails the required semantics,
and a later option when Postgres is justified. Compare implementation effort
before migrating to Turso and then Postgres in succession. Preserve identities,
receipts, ownership, uncertain calls and history through any migration.
[Neon plans](https://neon.com/docs/introduction/plans)
