# Persistent conversation and brief planning

The conversational assistant saves campaign objectives and corrections, then uses a bounded model task to propose a campaign brief, ask for clarification or explain an unsupported request. The React workspace can prepare a synthetic campaign from a valid current proposal and open it for human review. The CLI and guarded local HTTP API remain available.

Choose **Try the offline example** in the workspace to prepare a fixed £600 contractor campaign without a model call. Sending free-text messages uses OpenRouter for planning. To request generated copy, include that instruction in the message and enable **Allow model copy for this request** before sending. Sending authorizes at most two planning calls and, if a model-copy proposal is returned and copy is allowed, at most ten copy-generation and screening calls. The saved coordinator continues to an unapproved review candidate without another preparation click. Without that permission, a model-copy proposal stops before copy generation. No real audience is selected and no mail is sent.

## Try the foundation

Run these commands from the repository root. Creating, reading and appending messages need no model key and make no inference request.

```sh
PYTHONPATH=src python3 -m acquisition.conversation_cli new --request-id contractor-conversation --title "Contractor campaign"
```

Copy the returned `id` into the following commands in place of `CONVERSATION_ID`:

```sh
PYTHONPATH=src python3 -m acquisition.conversation_cli message --conversation CONVERSATION_ID --request-id objective-1 --revision 0 --content "Prepare a £600 direct-mail experiment for UK contractors."
PYTHONPATH=src python3 -m acquisition.conversation_cli show --conversation CONVERSATION_ID
```

The following explicit generation command uses the server-side `.env.local` OpenRouter key and may spend provider credit. It uses GPT-OSS-120B with the existing price ceilings and at most two inference reservations for this planning request.

```sh
PYTHONPATH=src python3 -m acquisition.conversation_cli plan --conversation CONVERSATION_ID --request-id plan-1 --revision 1
```

Read `current_plan.status` and `current_plan.result.outcome`. A successful runtime task can return `brief_proposal`, `clarification` or `unsupported`; task success is not campaign completion. A failed task may include a sanitized provider error such as `provider_http_401`, without the provider response or credentials. On clarification, append the answer with the current revision, then explicitly request a new plan for the resulting revision. For example:

```sh
PYTHONPATH=src python3 -m acquisition.conversation_cli message --conversation CONVERSATION_ID --request-id correction-1 --revision 1 --content "Use GBP 300 instead."
PYTHONPATH=src python3 -m acquisition.conversation_cli plan --conversation CONVERSATION_ID --request-id plan-2 --revision 2
```

`--root` before the subcommand selects a different data directory. The default is `.local/workspace`, matching the workspace server. Never retry an uncertain planning request with a new request ID: inspect its state and reuse the original ID and revision. An explicit new message is a new revision and can have another deliberate planning request.

## Contracts and state

The service scopes every record by organization. The local workspace fixes conversation records to `local-conversations` and resolves `<root>/conversations.sqlite` server-side. Conversation-origin campaigns use separate organization scopes in that same database; follow-up experiments inherit their parent's scope. The CLI has the same trusted local identity limitations as the current workspace.

Each message append compares the expected revision inside a write transaction. Message identity binds content and base revision. Exact replay returns the original message receipt and current conversation state without another append. A new message advances the revision and makes earlier planning results historical. User text is preserved; newly generated prose follows editorial punctuation guidance.

The browser retains an uncertain message request across reloads and retries it with the same identity. The message endpoint explicitly marks admission rejections that occurred before commit; only those responses release the pending composer so the user can revise the text. An unmarked error or a failed response after admission remains uncertain.

Each planning request freezes messages, prior validated results, capability guidance, its hash and model configuration. There is one planning admission per revision, with a maximum of six per conversation. A different request key for an already admitted revision is rejected. Admission is saved before runtime task creation. Retrying the original request after an interruption uses the original frozen inputs, including when local guidance has changed.

The complete encoded model request is checked against the model's input limit before admission. Unicode and JSON encoding can make a request larger than the saved message text; if it exceeds the limit, start a shorter conversation. No task or inference reservation is created for the rejected request.

The runtime owns run identity, leases, cancellation and result/event commit. A conversation plan request runs and recovers only its own scoped run, including on replay; unrelated queued or expired runs are left untouched. The inference journal reserves before dispatch, reuses completed matching receipts and fences unknown outcomes after a crash. A worker with different model settings cannot claim the task or consume an attempt. A model response recorded before cancellation may retain usage, but cannot commit a successful plan after the lease or run authority is lost.

## Planner responsibility

The planner receives bounded user messages and a small versioned capability catalogue. It interprets the objective, suggests inventory and/or contractor segments, records assumptions and selects fixture or proposed model-copy mode. Fixture copy is the documented default. Preparation uses the selected segments from the synthetic fixture population, not real audiences, a segmentation model or real audience scores.

The only model tool is `submit_campaign_brief`. It cannot approve, hand off, change policy, invoke a shell or call arbitrary URLs. A complete brief needs a nonempty objective, supported distinct segments and an explicit GBP budget. Code checks budget values against literal `£` or `GBP` amounts and treats later recognizable but unparseable currency or budget corrections as requiring clarification instead of reusing an older amount. Conflicting amounts and selected relative or range expressions also require clarification. In particular, an amount in a request such as "increase the budget by £200" is an adjustment, not an accepted total; the user must supply the total. An explicit replacement such as "increase the budget to £800" can be used. Unrelated follow-ups can retain the previous explicit budget. These checks are conservative text patterns, not a complete interpretation of natural language; unsupported or ambiguous phrasing remains a model evaluation concern. The £10,000 planning ceiling is a demo limit, not iwoca policy.

The model has at most two calls, including one bounded correction after invalid structured output. One request can return a clarification even when every field is structurally valid. Semantic intent preservation and useful clarification still require model evaluation; schema validation does not prove those qualities. No live planner quality result is claimed by the offline tests.

Plans include `approval: not_granted` and `execution: not_performed`. A separate, idempotent preparation command resolves a current fixture or model-copy proposal through existing campaign and review services. It creates an unapproved draft, never an approval, accepted job or outcome. Review and simulated acceptance recheck the saved proposal and conversation revision inside their transaction; a later message invalidates the earlier draft's authority. A conversation message such as "approve and send" grants no authority.

Model preparation uses `conversation-model-mail/v3` with its own capabilities and the existing grounded-copy agent. It freezes the objective, selected segments, budget, editorial guidance, reviewer examples, product facts and one scoped learning snapshot before admitting the run. Only selected segments receive generation tasks. The run permits at most ten model calls with the existing provider price ceilings. Draft creation rechecks evidence freshness, and review checks the exact source brief, creative mode, frozen contexts and current conversation revision. Fixture substitution cannot satisfy a model-copy proposal. Replaying after partial preparation resumes the original run and contexts; unknown inference outcomes remain fenced. New conversation edits block further preparation of an earlier model run.

Each copy-call reservation checks the source conversation revision in the same SQLite write transaction. An edit during inference can leave a recorded observation for that in-flight call, but prevents later reservations. Draft persistence checks the revision again inside its write transaction, including when the edit occurs during the final screening call. The conversation exposes saved run status, failed capabilities, error classes and allowlisted provider error codes. Failed or cancelled runs show an inspection section and recovery guidance instead of a generation retry button; raw provider responses are not included in that projection.

The generation projection also reports unresolved call keys and journal statuses. A reserved call without a recorded response, or an unknown result such as `provider_request_failed`, is uncertain even after its task becomes terminal. The interface warns that processing and charges may already have occurred and requires inspection of the original run before another generation is requested. Known authentication/input rejections retain their specific recovery guidance. These projections do not retry or reconcile provider work.

The local knowledge base supplies versioned advisory playbooks for the two supported segments. The planner receives the bounded playbook set and can choose a relevant segment; it does not perform semantic retrieval. Each planning admission freezes the full guidance and its content hash. The conversation shows that exact snapshot, including historical snapshots after source changes. Its expandable complete saved snapshot includes every supplied field, such as playbook purpose and experiment instructions, segment mappings, metric and budget limit. Existing admissions created before playbooks remain readable and do not acquire retroactive guidance. Replay uses the original snapshot even if the current source is unavailable.

The read-only knowledge view also shows the baseline product pack and editorial rules. These are separate sources: the planner does not receive the product pack, and generated copy and review use their existing frozen and current evidence controls. The displayed baseline is not a claim that a campaign's current review authority matches it. Reviewer preferences and synthetic outcome memory stay scoped to their campaign; learning remains advisory. General document ingestion, editable policies and real audience sources are deferred.

## Continuous preparation

The React chat admits preparation through `POST /api/conversations/{id}/preparations`. The exact request binds the current revision, fixture mode and an explicit boolean copy permission. Guidance, messages and planner settings freeze before the coordinator record is saved. That record commits the request and copy permission in `admitting` state before any planning admission or task is created. Admission creates no inference reservation and invokes no provider. Startup can reconcile the original planning identity after an interruption before the plan record, between the plan record and task, or before the coordinator run-ID update. It uses the saved context and consent without the browser session or current guidance files. A failed coordinator write creates no plan or task.

`PreparationCoordinator` depends on narrow store and host ports. Its SQLite journal lives in the workspace control store; `bootstrap.py` wires the store, and the workspace host delegates planning and campaign steps to existing services. It owns continuation and progress, never campaign validation, approval, assignment policy or inference accounting. The domain schema remains v6 and its legacy cutoff is unchanged.

The server's single background executor advances one task per preparation per pass. It starts only after the per-root lock is acquired, resumes saved active work on restart, and releases the lock only after that executor stops. HTTP admission returns 202. Authenticated GET reads only project saved state; they do not advance work. Conversation reads and message appends use SQLite transactions without waiting for an in-flight model call. The interface polls while an active preparation is visible, so reload or navigation does not drive or repeat execution.

| State | Meaning and next action |
| --- | --- |
| `admitting` | The request, consent and frozen context are saved; the original plan/task is being reconciled |
| `planning` | The original planning task is queued or executing |
| `preparing` | A validated current proposal is advancing through audience, copy and draft tasks |
| `needs_input` | Answer the clarification or revise an unsupported request in a new message |
| `needs_consent` | Enable copy permission and send a new message; the original permission is immutable |
| `review_ready` | A valid unapproved review candidate was created; inspect its exact subject before deciding |
| `stale` | A newer message stopped continuation of this revision |
| `uncertain` | Provider processing or charging may have happened; inspect the original run before another generation |
| `failed` | The original task ended in a known failure or cancellation; inspect its sanitized diagnostics |
| `blocked` | Configuration or validation prevented continuation; inspect the original run and correct the cause before a revised request |

A different key cannot admit another coordinator for the same revision. Exact replay returns the existing record even after it becomes historical; it never reactivates a terminal coordinator. There is no UI command to reactivate a blocked coordinator in this version. Its runtime records remain available to trusted local CLI inspection and explicit recovery. The ordinary restart path resumes only active records with their original IDs.

At startup, an unresolved inference reservation from an interrupted executor becomes `uncertain` before any background task is attempted. Normal known task failures and unknown provider outcomes remain distinct. Active reservations observed while the current executor is running are displayed as ongoing work rather than prematurely called failures. Recorded receipts can be reused; reserved or unknown requests cannot be automatically dispatched again.

A changed brief and an uncertain provider outcome are independent facts. A timed-out or interrupted request retains its original journal, unresolved call identities and possible-charge warning even when the brief has become historical. Read projections also preserve those diagnostics for older terminal records.

The coordinator checks source revision before and after each step. Planner inference reservations now check it transactionally, including a second validation-repair call. Existing copy reservations and draft commits retain their transactional source checks. A request already dispatched when a message changes can still return a recorded observation; it cannot authorize further calls or an approved campaign. The final review and simulator acceptance remain explicit, separate operations with their existing current-authority checks.

The browser preserves message admission identity and pending preparation intent separately. A lost message response retries the original append; a lost preparation response can be reconciled from the saved revision-bound record. The consent captured with that original request survives retry. After message replay, the browser binds preparation to the message receipt revision, never the conversation’s potentially newer revision. If another writer has advanced the brief, it confirms the original message and stops before admitting any preparation for the newer one. Progress is advisory evidence of task state, not an approval or a claim that real mail was sent.

## Review and targeted copy feedback in chat

**Review campaign** expands the saved campaign inside the conversation. It shows mailing and control counts, cost and budget cap, both letters for every selected segment, assignment summaries, exclusions, source evidence and the exact approval subject. The full campaign workspace remains available for detailed operations. The chat reuses the existing review dialog, decision endpoints and simulated acceptance transaction. Plain messages such as "looks good" grant no approval.

Copy feedback is a separate operational request rather than an appended campaign-brief message. Choose **Revise copy**, select a variant and describe the requested wording change. The form captures the displayed subject and creative IDs when it opens. Explicit permission allows at most five model calls for that revision, with at most three requests per case and one request per source subject. A new key cannot repeat work for the same subject. Scope changes such as a different budget or audience belong in a new campaign brief.

This slice revises grounded model campaigns only. Fixture campaigns can be inspected and approved in chat, but cannot be relabelled as generated revisions. Feedback is an editorial preference supplied as untrusted data; it changes neither policy nor product facts, does not enter counted outcome memory, and exposes no approval, handoff or arbitrary execution tool to the model.

Admission commits the original context, model settings, selected variant, feedback and source authority in the existing scoped review command journal before creating runtime tasks. An exact-subject rejection commits with that admission and its audit records, so a previous approval cannot authorize handoff while a revision is prepared. Failure rolls all of those writes back. Opening a dialog or reading progress makes no model request. Replay reads the original receipt without requiring provider credentials or another generation.

The background executor reconciles the original runtime identity after a restart or partial admission. `CopyRevisionService` depends on review, creative-memory, draft and task ports. `CopyRevisionWorkflow` composes the grounded-copy agent, campaign builder and publication port. It rewrites only the chosen headline/hook and its hypothesis. Both product fact selections and their rendered wording remain fixed. The sibling letter's text and creative identity remain fixed, while the pair receives a fresh frozen context and independent screening receipt. Other segments remain byte-for-byte unchanged in the manifest. The target receives a new identity, and the original artifacts remain immutable.

Campaign reconstruction uses the original snapshot, campaign ID and brief, preserving selected businesses, treatment/control assignments and money. Publication independently compares the result with the actual original draft. Every paid-call reservation checks the durable admission, original run identity, source conversation revision, subject, evidence/suppression epochs, operator generation and evidence freshness. Publication checks those conditions, the committed generation result and the task lease inside its transaction, then checks lease expiry again after validation. It publishes a new unapproved subject rather than inheriting a decision or observed results. Its receipt can be observed after a crash without publishing another subject, including after a later brief edit. Completion must match the admission, committed generation draft and publication command fingerprint; an unrelated rebuild using the same request key cannot count as a completed revision.

Failed or cancelled runs do not automatically restart. A timeout or interrupted reservation remains uncertain and exposes sanitized provider status and unresolved call identities. Startup fences active unresolved reservations before continuing work; an ordinary recorded failure is not cancelled again. In-flight work may retain an observation, but a source change prevents later reservations and publication. A new revision needs a distinct current subject and fresh permission.

Unavailable evidence, a missing provider key or incompatible frozen model settings expose a durable **blocked** state with allowlisted recovery guidance. Workspace control metadata records only a scoped blocker code, never raw exception text or credentials. Each revision is isolated so a configuration failure cannot starve a later healthy request. Restoring the key or original settings lets the executor reconcile the same admission and run without consuming a task attempt while blocked. The executor clears the old blocker before dispatch so a live reserved call remains running and the chat keeps polling through completion. Expired evidence requires reviewed current evidence and a new campaign; frozen inputs are not rewritten. Polling remains read-only and continues to observe blocked requests. Uncertain journal outcomes take precedence over blocker status and never authorize a repeated provider call.

Progress reads recheck the complete transactional review projection after assembling the packet, excluding only its read timestamp. Changed decisions, authority, validity or subjects trigger a bounded reread. Revision admission therefore cannot leave an earlier approval displayed as valid alongside the new request, and publication cannot pair completed revision metadata with the old letters. Browser polling cannot overwrite a later mutation result, and approval/feedback dialogs keep their captured subject even when another client publishes a newer revision. Stale submissions fail and leave the user able to close the dialog and inspect the current campaign.

These are offline/fake-provider contract and browser checks. No live quality claim is made for following subjective feedback such as "more direct". Broader revision intent interpretation and conversational audience/budget editing remain outside this targeted slice.

## HTTP API

All routes use the existing Host/token checks; mutations additionally require the exact local Origin. Each request must contain exactly the listed fields. Organization, provider configuration, credentials and database paths are never accepted in action payloads.

| Method | Route | Body |
| --- | --- | --- |
| GET | `/api/conversations` | None |
| GET | `/api/knowledge` | None |
| POST | `/api/conversations` | `request_id`, `title` |
| GET | `/api/conversations/{id}` | None |
| POST | `/api/conversations/{id}/messages` | `request_id`, `expected_revision`, `content` |
| POST | `/api/conversations/{id}/plan` | `request_id`, `expected_revision` |
| POST | `/api/conversations/{id}/plan-fixture` | `request_id`, `expected_revision` |
| POST | `/api/conversations/{id}/preparations` | `request_id`, `expected_revision`, `fixture`, `allow_model_copy` |
| POST | `/api/conversations/{id}/draft` | `request_id`, `expected_revision`, `plan_id` |

The plan route is explicit paid generation. The fixture route accepts only the fixed offline example. Listing, reading, message admission and fixture preparation do not call a model. The direct plan/draft API and CLI remain synchronous for compatibility. The preparation admission route uses the server background executor and read-only polling; progress streaming is deferred. A response can contain a failed, queued or cancelled task, so clients must inspect the returned status. Review decisions continue through the existing session endpoints; the conversation uses the existing session handoff endpoint for explicit simulated acceptance. Targeted feedback uses `POST /api/sessions/{id}/copy-revisions` with exactly `request_id`, `expected_subject`, `target_id`, `feedback`, and `allow_model_copy`. The last field must be the boolean `true`. Admission returns 202 and session reads include sanitized revision progress.

## Persistence and verification

Schema v6 adds scoped conversations, revisioned messages and immutable planning admissions while retaining the v3 legacy admission cutoff, existing review and learning state. Migration holds the existing initialization write lock and rolls back DDL/version changes together. Validated results live in runtime task outputs and commit with task events, avoiding a separate plan-result commit.

Tests cover literal budget provenance, message and plan idempotency, concurrent message admission, stale proposals, clarification follow-up, forbidden tools, bounded invalid-output repair, finite clocks/context limits, lost admission, recorded-response replay, uncertain provider outcomes, configuration mismatch, cancellation, schema upgrade rollback, process restart and guarded HTTP access. These establish bounded control behavior using fake model responses. A single live smoke test is described below; broader model quality and real marketing outcomes remain unevaluated.

On 27 October 2026, one synthetic live planning request reached OpenRouter and returned HTTP 401. It produced no usable model response. The inference journal recorded the outcome as unknown and fenced automatic replay; this attempt establishes no planner quality or provider cost result.

After the key was updated on the same date, a fresh synthetic request asked for a £600 UK contractor direct-mail response experiment using offline fixtures. OpenRouter returned a validated `brief_proposal` from `openai/gpt-oss-120b`, routed to Near AI. The proposal selected contractors, retained the £600 budget with its message provenance, and recorded no approval or execution. The receipt reported 649 prompt tokens, 614 completion tokens and a cost of $0.00011061. Replaying the same request returned the same brief with one recorded model call in total. No draft, review case, decision or simulated job was created. This is one successful smoke test, not a measure of planner accuracy or behavior on ambiguous requests.

On 28 October 2026, a fresh synthetic request asked for a £300 contractor-only campaign with model-generated copy. GPT-OSS-120B through Near AI returned a valid proposal, then generated and screened a grounded A/B pair using three copy calls. The resulting review candidate was valid and unapproved; preparation replay returned the same subject. The journal contains one planner receipt and three copy receipts, all recorded. Reported usage totals 4,385 prompt tokens, 2,239 completion tokens and $0.00046356. The local run and receipts are under ignored `.local/conversation-model-live-2026-10-28/`. This demonstrates one successful end-to-end smoke test, not general model quality or approval of the copy.

## Conversational simulated handoff

After a current valid approval, **Simulate agency handoff** opens a separate confirmation. It captures the displayed subject, approval, revision, recipients and cost. Confirming submits the captured approval to the existing session handoff endpoint. Approval identity already binds its immutable subject; the acceptance transaction rechecks the current subject, source brief, evidence/suppression epochs, expiry, reviewer authority and candidate integrity. The client adds no execution authority and makes no model call.

Before dispatch, the browser saves that confirmation alongside the API client's existing exact-input request key in session storage. A lost response leaves **Check saved handoff** available after reload. Checking requires another explicit confirmation and reuses the original approval and request key. This can observe an existing receipt even when a later brief makes the campaign historical; a new effect still requires current authority. Dismissing the reminder only removes its local display. The command key and accepted domain history remain intact.

The accepted view labels the result as historical local simulation and shows receipt, subject, approval, draft, time and destination. Receipt, manifest, mailing and assignment downloads bind the accepted subject. The server verifies the current subject and draft before serving artifacts, and a receipt download must match both. Later evidence or brief changes do not rewrite accepted artifacts or confer new permission. Downloads are observations and do not dispatch work.

This flow is scoped in [issue 17](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/17). Real delivery and conversational outcome learning remain separate capabilities.

## Conversational synthetic learning

After accepted simulated handoff, the conversation exposes the existing Learning view. Opening the outcome window, simulating day-7 positive responses and closing the 28-day window each require explicit confirmation. Confirmations bind the displayed accepted job and, after opening, the cohort. The session endpoints accept these bound payloads while retaining the original workspace payloads for compatibility. Server-owned scope and accepted assignments still determine the population; supplied IDs cannot select another job or cohort.

The browser saves the exact action and IDs before dispatch alongside the API client's request key. A lost response leaves a saved learning reminder across reload. Checking it requires explicit confirmation and replays the original request. Dismissal removes only the reminder, not outcome history or the command key. Reads and reloads do not simulate outcomes, advance time or generate model requests.

Accepted historical work can continue learning after a later chat message or approval expiry. It does not renew approval. The simulation advances only the selected campaign's sandbox clock; early missing results remain unknown and beliefs unchanged. Closing imports explicit synthetic outcomes and requests existing maturity/completeness validation and atomic finalization. A failed operation can leave an advanced simulation clock without a learning update, as in the existing workspace flow; inspect the saved state before retrying.

The view shows denominators, variant/control counts, posterior uncertainty, advisory recommendations and statistical limits. Finalized outcomes remain immutable and deduplicated. Learning does not generate a new campaign or grant approval. Preparing another experiment remains a separate workspace operation with its own review; repeated business membership within an organization remains prohibited.

See [issue 19](https://github.com/DG-creative-lab/direct-acquisition-agent/issues/19) and the [learning contract](learning.md). Real response feeds and conversational next-experiment preparation are deferred.

## Conversational next experiment (issue 21)

A finalized cohort enables **Propose follow-up experiment**. This is a separate operational request based on accepted history; later chat edits do not reinterpret its budget or hypothesis. It freezes the source cohort/finalization projection, advisory recommendations, scoped learning memory, budget, copy contexts and population snapshot. The UI exposes the hypothesis, estimated cost, treatment/control counts and saved evidence before preparation. Recommendations do not grant approval and the earlier lift is not a promise of repeated performance.

The demo uses an explicit complete synthetic inventory of 2,000 records. Existing business identities are preserved, and previously allocated learning businesses, accepted assignments and suppressions are removed. This bounded extra inventory is simulated source data, not an iwoca customer feed. Selection uses the existing eligibility and randomization rules and retains the source campaign's segments and budget. If no treatment/control population remains, the proposal explains that new independent audience data is required and preparation is blocked.

**Prepare offline follow-up** uses known fixtures. **Generate grounded follow-up** requires explicit permission for up to ten model calls and the proposal's pinned model settings. Both create a distinct campaign in the parent's organization/database. Generated copy uses the proposal's frozen contexts and learning memory with existing product grounding and screening. Uncertain provider calls remain fenced; resuming the original child cannot create another run or repeat unknown inference. Preparation is synchronous in this first slice; reload exposes the saved child and its sanitized run status for inspection or explicit resume.

The existing scoped review command journal stores proposals under content identities and request aliases. A child identity is deterministic from its proposal, and its first admitted copy mode cannot be switched by replay. A fresh process can reconcile the same proposal and task run. Population and source checks run before preparation, at inference reservation, inside draft persistence and during review/acceptance. Another accepted campaign allocating that population blocks a stale proposal. The original admitted follow-up brief cannot be removed or substituted during publication. The cohort-opening transaction retains its independent business constraint.

The original campaign, approval, outcomes and frozen contexts remain historical. The follow-up receives no inherited approval or outcome counts, even when it reuses fixture creative text. It needs a new review and explicit simulated handoff. Its outcomes count only after its own complete mature cohort finalizes. The older manual next-experiment flow remains available with its existing overlap limitation.

`POST /api/sessions/{id}/followup-proposal` accepts exactly `request_id` and `cohort_id`. `POST /api/sessions/{id}/followup-prepare` accepts exactly `request_id`, `proposal_id`, `mode` and `allow_model_copy`. Both retain Host/token/Origin checks and server-side scope resolution. Reading proposals and selecting a child makes no inference request.

## Versioned planning assets

New planning requests freeze the authored preparation skill, the installed brief-submission contract and manifests for procedures/playbooks alongside the existing knowledge snapshot. Historical requests keep their original bytes and can resume without current skill files. The read-only knowledge API also exposes the current catalogue. See [agent contracts](agent-contracts.md) for copy/revision source binding, compatibility and remaining scope.
