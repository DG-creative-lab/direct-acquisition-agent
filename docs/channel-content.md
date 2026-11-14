# Grounded email and human call content

Issue #65 adds an agent-callable preparation API and CLI. It freezes a complete
email or human call script for each of one to six intended synthetic recipients.
Both iwoca and the fictional Fielddesk profile use the same services. The
installed proposer and screen are deterministic offline fixtures. This is not
evidence of live-model quality, provider compatibility or outbound readiness.

## Ownership and flow

`creative` owns the request, rendering rules, artifact contracts, bounded agent
and `ChannelContentStore` port. `reasoning` owns inference limits, reservations
and frozen source/skill/tool integrity. `workflows` composes those public APIs
with runtime tasks. SQLite implements admission, current-source reconstruction
and atomic publication; `bootstrap.build_channel_preparation` wires adapters.
Runtime has no acquisition-specific dependency. There is no frontend change.

1. Resolve exact #64 recipient request keys inside the organization. Recheck
   current #62 contact readiness, objections and source history. Require the
   same profile and channel and one payload per native contact.
2. Freeze a `creative-context/v5` envelope containing the reviewed v3 product
   pack, selected recipient observations and citations, synthetic channel
   policy, authored framing, scoped writing preferences, skills and model
   settings. Admit the context, exact-input receipt and task together.
3. Read frozen context, propose reviewed framing keys and evidence IDs, render
   in code, then independently screen every complete rendered payload. A
   rejected candidate permits one repair and one further screen. The hard
   ceiling is five journalled calls, including the initial read.
4. Reconstruct current evidence and validate all recipients again in the
   publication transaction. Require the exact recorded proposal and screening
   responses. Commit the immutable bundle, task result and lifecycle event
   together, with a final lease and execution-policy check.

The initial content vocabulary deliberately uses two authored framing choices.
Models select those choices and supported fact IDs, rather than writing arbitrary
claims or HTML. Typed recipient wording qualifies statements as recorded
observations. Code assembles exact selected product wording, fact qualification,
pack-wide qualification and official CTA from the reviewed pack. Sparse context
produces an honest generic question with no invented personalization. Scores
are not supplied as recipient facts.

## Frozen artifacts and validation

A `channel-bundle/v1` contains every exact `channel-recipient/v1` artifact and the
full-population screening receipt. Email payloads contain subject, text, escaped
HTML, exact synthetic recipient, sender name/address, reply-to, official CTA,
disclosure and synthetic opt-out link. Call payloads contain a demo contact
reference, introduction, qualified relevance, discovery, reviewed claims,
objection guidance, next steps and explicit do-not-contact handling. Calls are
human-only guidance.

All destinations, senders and opt-out endpoints are explicitly synthetic.
Unsupported fact IDs, invented familiarity, missing recipients or qualifications,
unsafe HTML and recipient substitution block readiness. Rendering is rebuilt
from frozen inputs and compared in full, including identifiers. HTML is escaped
by code; model-supplied markup cannot enter the artifact. Screening binds the
hash of the entire rendered population, requires a verdict for every recipient
and remains advisory, never approval.

`config/channel-skills-v1.json` installs `contextual-email/v1` and
`call-guidance/v1`. `bootstrap.channel_agent_catalogue()` exposes their bounded
read, propose and screen contracts. Skills describe use; they cannot install
tools or grant effects. Product evidence, recipient evidence, channel policy,
authored guidance and preferences have separate frozen source manifests. The
historical postal catalogue and skill file retain their original bytes.

## Agent API and CLI

Given current recipient request keys prepared with the #64 API:

```python
from acquisition.bootstrap import build_channel_preparation

app = build_channel_preparation("application.sqlite", "example-org", "fielddesk")
view = app.prepare("example-org", "email-v1", "fielddesk",
                   ("recipient-context-1", "recipient-context-2"), "email")
```

The equivalent trusted local CLI is:

```sh
PYTHONPATH=src python3 -m acquisition.channel_cli \
  --db application.sqlite --organization example-org --profile fielddesk \
  prepare --request-id email-v1 \
  --recipient-requests recipient-context-1 recipient-context-2 --channel email
```

Use `--channel human_call` with contexts assessed for that channel. `start`
admits without draining work; `work`, `inspect` and `cancel` take the original
`--request-id`. `inspect` opens a read-only projection, including restored
stores. Organization flags are trusted local scope, not hosted authentication.
There is no form-based preparation flow or new conversational route in this
slice. Later sequence and review work will compose the API.

Use a new request key and `--parent-id <artifact_id>` for a rewrite. The parent
must belong to the same organization, product, channel and native population.
Every new preparation gets new context and recipient identities, with no
inherited approval or outcome support. Exact replay returns the original run
and payload without more inference. Changed inputs under the same key fail.

## Recovery, migration and limits

The existing inference journal reserves before dispatch. Unknown outcomes are
not automatically repeated, including after restart. Recorded calls can be
reused after worker loss; publication still requires a current lease and current
source state. Cancellation, objections, expiry and paused execution prevent
publication. Completed artifacts remain readable after becoming historical;
`currently_applicable` and `ready_for_review` are current observations, not
authorization or approval.

Schema 19 to 20 adds immutable `channel_preparations` and `channel_artifacts`
tables, reusing creative contexts and the inference/runtime journal. Migration
and version advancement are one transaction. Existing context/campaign bytes
and the schema-v3 legacy admission cutoff are preserved. Checkpoint readers
accept schema 20 and restored stores remain inspection-only. Older binaries
reject schema 20; rollback to older code requires a pre-upgrade database backup.

This capability is not admitted into verified or restored execution roots.
There is no paid model configuration, live recipient data, sender adapter,
approval purpose, dispatch, CRM task write, automatic reply or outcome import.
The gateway port supports bounded replacement in tests, but enabling a live
provider needs separate authority, data-handling and quality evidence. Production
retention and deletion remain deferred. A passing offline screen is not a
human-quality assessment of persuasive or useful personalization.
