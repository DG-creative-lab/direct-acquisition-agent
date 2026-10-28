# Persistent conversation and brief planning

The conversational assistant saves campaign objectives and corrections, then uses a bounded model task to propose a campaign brief, ask for clarification or explain an unsupported request. The React workspace can prepare a synthetic campaign from a valid current proposal and open it for human review. The CLI and guarded local HTTP API remain available.

Choose **Try the offline example** in the workspace to prepare a fixed £600 contractor campaign without a model call. Sending free-text messages uses OpenRouter for planning. To request generated copy, include that instruction in the message, then choose **Generate campaign copy** on the completed proposal. This separate action spends OpenRouter credit on generation and screening for the selected synthetic segments. No real audience is selected and no mail is sent.

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

The catalogue supplies procedures and supported capability metadata only. It is not a general knowledge base. Verified product facts, enforceable policy, editorial preference and counted outcome memory retain their existing owners. Retrieval of those sources for planning, richer objectives and campaign execution tools are deferred.

## HTTP API

All routes use the existing Host/token checks; mutations additionally require the exact local Origin. Each request must contain exactly the listed fields. Organization, provider configuration, credentials and database paths are never accepted in action payloads.

| Method | Route | Body |
| --- | --- | --- |
| GET | `/api/conversations` | None |
| POST | `/api/conversations` | `request_id`, `title` |
| GET | `/api/conversations/{id}` | None |
| POST | `/api/conversations/{id}/messages` | `request_id`, `expected_revision`, `content` |
| POST | `/api/conversations/{id}/plan` | `request_id`, `expected_revision` |
| POST | `/api/conversations/{id}/plan-fixture` | `request_id`, `expected_revision` |
| POST | `/api/conversations/{id}/draft` | `request_id`, `expected_revision`, `plan_id` |

The plan route is explicit paid generation. The fixture route accepts only the fixed offline example. Listing, reading, message admission and fixture preparation do not call a model. API/CLI generation is synchronous in this local slice; background progress streaming is deferred. A response can contain a failed, queued or cancelled task, so clients must inspect the returned status. There are no conversation approval or dispatch routes.

## Persistence and verification

Schema v6 adds scoped conversations, revisioned messages and immutable planning admissions while retaining the v3 legacy admission cutoff, existing review and learning state. Migration holds the existing initialization write lock and rolls back DDL/version changes together. Validated results live in runtime task outputs and commit with task events, avoiding a separate plan-result commit.

Tests cover literal budget provenance, message and plan idempotency, concurrent message admission, stale proposals, clarification follow-up, forbidden tools, bounded invalid-output repair, finite clocks/context limits, lost admission, recorded-response replay, uncertain provider outcomes, configuration mismatch, cancellation, schema upgrade rollback, process restart and guarded HTTP access. These establish bounded control behavior using fake model responses. A single live smoke test is described below; broader model quality and real marketing outcomes remain unevaluated.

On 27 October 2026, one synthetic live planning request reached OpenRouter and returned HTTP 401. It produced no usable model response. The inference journal recorded the outcome as unknown and fenced automatic replay; this attempt establishes no planner quality or provider cost result.

After the key was updated on the same date, a fresh synthetic request asked for a £600 UK contractor direct-mail response experiment using offline fixtures. OpenRouter returned a validated `brief_proposal` from `openai/gpt-oss-120b`, routed to Near AI. The proposal selected contractors, retained the £600 budget with its message provenance, and recorded no approval or execution. The receipt reported 649 prompt tokens, 614 completion tokens and a cost of $0.00011061. Replaying the same request returned the same brief with one recorded model call in total. No draft, review case, decision or simulated job was created. This is one successful smoke test, not a measure of planner accuracy or behavior on ambiguous requests.

On 28 October 2026, a fresh synthetic request asked for a £300 contractor-only campaign with model-generated copy. GPT-OSS-120B through Near AI returned a valid proposal, then generated and screened a grounded A/B pair using three copy calls. The resulting review candidate was valid and unapproved; preparation replay returned the same subject. The journal contains one planner receipt and three copy receipts, all recorded. Reported usage totals 4,385 prompt tokens, 2,239 completion tokens and $0.00046356. The local run and receipts are under ignored `.local/conversation-model-live-2026-10-28/`. This demonstrates one successful end-to-end smoke test, not general model quality or approval of the copy.
