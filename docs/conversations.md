# Persistent conversation and brief planning

The conversational foundation saves campaign objectives and corrections, then uses a bounded model task to propose a campaign brief, ask for clarification or explain an unsupported request. The current interface is a CLI and the guarded local HTTP API. React chat, execution of campaign tools and automatic preparation from a plan are the next increments.

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

The service scopes every record by organization. The local workspace fixes the organization to `local-conversations` and resolves `<root>/conversations.sqlite` server-side. The CLI has the same trusted local identity limitations as the current workspace.

Each message append compares the expected revision inside a write transaction. Message identity binds content and base revision. Exact replay returns the original message receipt and current conversation state without another append. A new message advances the revision and makes earlier planning results historical. User text is preserved; newly generated prose follows editorial punctuation guidance.

Each planning request freezes messages, prior validated results, capability guidance, its hash and model configuration. There is one planning admission per revision, with a maximum of six per conversation. A different request key for an already admitted revision is rejected. Admission is saved before runtime task creation. Retrying the original request after an interruption uses the original frozen inputs, including when local guidance has changed.

The complete encoded model request is checked against the model's input limit before admission. Unicode and JSON encoding can make a request larger than the saved message text; if it exceeds the limit, start a shorter conversation. No task or inference reservation is created for the rejected request.

The runtime owns run identity, leases, cancellation and result/event commit. A conversation plan request runs and recovers only its own scoped run, including on replay; unrelated queued or expired runs are left untouched. The inference journal reserves before dispatch, reuses completed matching receipts and fences unknown outcomes after a crash. A worker with different model settings cannot claim the task or consume an attempt. A model response recorded before cancellation may retain usage, but cannot commit a successful plan after the lease or run authority is lost.

## Planner responsibility

The planner receives bounded user messages and a small versioned capability catalogue. It interprets the objective, suggests inventory and/or contractor segments, records assumptions and selects fixture or proposed model-copy mode. Fixture copy is the documented default. Segment choice is a proposal: this slice does not resolve real populations, run a segmentation model, retrieve real audience scores or prepare a contractor-only campaign.

The only model tool is `submit_campaign_brief`. It cannot approve, hand off, change policy, invoke a shell or call arbitrary URLs. A complete brief needs a nonempty objective, supported distinct segments and an explicit GBP budget. Code checks budget values against literal `£` or `GBP` amounts and treats later recognizable but unparseable currency or budget corrections as requiring clarification instead of reusing an older amount. Conflicting amounts and selected relative or range expressions also require clarification. Unrelated follow-ups can retain the previous explicit budget. These checks are conservative text patterns, not a complete interpretation of natural language; unsupported or ambiguous phrasing remains a model evaluation concern. The £10,000 planning ceiling is a demo limit, not iwoca policy.

The model has at most two calls, including one bounded correction after invalid structured output. One request can return a clarification even when every field is structurally valid. Semantic intent preservation and useful clarification still require model evaluation; schema validation does not prove those qualities. No live planner quality result is claimed by the offline tests.

Plans include `approval: not_granted` and `execution: not_performed`. They cannot create a draft, review decision, accepted job or outcome. Future campaign execution must resolve the proposed brief through existing audience, campaign and grounded-copy services, then present the exact resulting subject for human approval. A conversation message such as "approve and send" grants no authority.

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

The plan route is explicit paid generation. Listing, reading and message admission do not construct a model adapter. API/CLI generation is synchronous in this local slice; background progress streaming is deferred. A response can contain a failed, queued or cancelled task, so clients must inspect the returned status. There are no conversation approval or dispatch routes.

## Persistence and verification

Schema v6 adds scoped conversations, revisioned messages and immutable planning admissions while retaining the v3 legacy admission cutoff, existing review and learning state. Migration holds the existing initialization write lock and rolls back DDL/version changes together. Validated results live in runtime task outputs and commit with task events, avoiding a separate plan-result commit.

Tests cover literal budget provenance, message and plan idempotency, concurrent message admission, stale proposals, clarification follow-up, forbidden tools, bounded invalid-output repair, finite clocks/context limits, lost admission, recorded-response replay, uncertain provider outcomes, configuration mismatch, cancellation, schema upgrade rollback, process restart and guarded HTTP access. These establish bounded control behavior using fake model responses. A single live smoke test is described below; broader model quality and real marketing outcomes remain unevaluated.

On 27 October 2026, one synthetic live planning request reached OpenRouter and returned HTTP 401. It produced no usable model response. The inference journal recorded the outcome as unknown and fenced automatic replay; this attempt establishes no planner quality or provider cost result.

After the key was updated on the same date, a fresh synthetic request asked for a £600 UK contractor direct-mail response experiment using offline fixtures. OpenRouter returned a validated `brief_proposal` from `openai/gpt-oss-120b`, routed to Near AI. The proposal selected contractors, retained the £600 budget with its message provenance, and recorded no approval or execution. The receipt reported 649 prompt tokens, 614 completion tokens and a cost of $0.00011061. Replaying the same request returned the same brief with one recorded model call in total. No draft, review case, decision or simulated job was created. This is one successful smoke test, not a measure of planner accuracy or behavior on ambiguous requests.
