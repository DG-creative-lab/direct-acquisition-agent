# Protected synthetic serverless preparation

This slice opens one operator-only synthetic preparation surface. Bootstrap
resolves its organization and storage from server configuration. There are no
visitor memberships, live model routes, approval actions or outbound transports.
The existing local workspace and single-worker root lock retain their contracts.

## Application contract

`HostedPreparations` uses the conversations-owned store port and public
`SequenceJourneys` service. Its first conversation request reserves a digest of
the exact profile, total budget and explicit fixture-generation consent. Native
message and journey admission commit together. Repeating the original start
resumes the same conversation and journey even if an earlier response was lost.
Changed inputs under that key are rejected. New native command IDs derive from
the original frozen journey; a partial stage always reuses them.

The seven existing stages prepare contacts, an audience decision, recipient
contexts, an initial email, a human call script, a follow-up and an unapproved
review subject. A continuation names `expected_stage` and executes at most that
one stage. An already completed stage returns `already_advanced` without another
step. A future stage is rejected. A generation stage executes at most one native
worker tick. Existing limits retain six recipients per channel, three content
runs and five fixture calls per run. Ready is an unapproved exact subject;
continuation never approves or simulates it.

Hosted journeys freeze `preparation_clock=real-invocation/v1` in their catalogue.
All preparation capabilities use real invocation time for leases, reservations
and commit checks. Local simulation journeys retain their persisted synthetic
clock. A process that dies after claiming a task can therefore be recovered by a
later invocation after lease expiry. Recorded calls can be reused. Reserved or
unknown calls stay fenced; a new request cannot repeat uncertain inference.
Stops use the original journey's transactional native stop command, which native
reservation and publication recheck. No new state journal or process lock is an
execution authority.

## HTTP contract

The Python function is `api/preparation.py`. Required server configuration:

- `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` for an already registered schema-23 store.
- `PREPARATION_ORGANIZATION`, a fixed server-owned operator scope.
- `PREPARATION_OPERATOR_TOKEN`, an independently generated secret of at least 32 characters.
- `PREPARATION_ALLOWED_HOSTS`, exact comma-separated additional HTTP Host values.
  On Vercel the exact server-supplied `VERCEL_URL` is also allowed; no request header supplies this identity.
- `PREPARATION_ALLOWED_ORIGINS`, exact comma-separated browser origins if browser access is needed.

Every request requires `Authorization: Bearer TOKEN` and an allowed Host.
A present Origin must also be allowed. Authorization precedes database opening.
Duplicate identity headers and unknown fields are rejected. No organization,
role, gateway, provider credential, model or raw source can be supplied by the
client. Bodies are limited to 2 KiB and JSON field names must be unique. Routine
logs and failures never echo request bodies, tokens or raw provider errors.

POST `/api/preparation` accepts these shapes:

```json
{"action":"start","request_id":"unique-request","profile_key":"fielddesk","budget_pence":10000,"allow_generation":true}
{"action":"continue","journey_id":"RETURNED_ID","expected_stage":0}
{"action":"stop","journey_id":"RETURNED_ID","request_id":"unique-stop-request"}
```

GET `/api/preparation?journey_id=RETURNED_ID` reads progress. Repeated status reads
never initialize a schema, grant roles, run a worker or reserve inference. The
receipt is immutable identity; the adjacent progress projection is current and
can become historical or blocked. A 503 requires observation/replay of the
original command, not a replacement request. Each start key and stage should be
retained by the caller before dispatch.

## Invocation and deployment boundary

No background thread, scheduler or unawaited work advances a preparation.
Continuation is request-bound. Saved work resumes when explicitly requested,
including when an operator returns later. Autonomous progress after every client
disconnect needs a separate durable trigger and is not promised here.

The function configuration has a 180-second platform maximum. The remote client
checks a 120-second monotonic I/O budget before each request and caps its socket
timeout to the remaining budget. These checks are cooperative; a platform kill
is the hard execution boundary. An in-flight provider operation can remain
uncertain, so fresh invocations reconcile original native records and leases.
The database is opened without migrations on every invocation. Migration/import
is an explicit operator step through the remote-storage contract.

Only `public/` is a static output directory. Source and configuration are function
inputs, not static assets. `scripts/package_serverless_preparation.py` reads one
resolved Git commit and excludes local credentials, ignored operator setup and
frontend/test outputs. It rejects symlinks/submodules and records payload hashes
in `serverless-preparation-source.json`.

```sh
python3 scripts/package_serverless_preparation.py /tmp/new-operator-package --commit REVIEWED_COMMIT
```

The artifact is suitable for a protected preview on the existing isolated
project. Deploying and configuring access is separate from exposing a public
MVP. No public website release or provider spending is enabled by this artifact.

## Verification

The focused tests use real SQLite, independent processes, a real local HTTP
server and the remote adapter over a Hrana wire fixture. They cover concurrent
start and claim, exact-stage replay after lost acknowledgement, current-source
and tenant checks, stop and lease fences, abrupt process exit, reserved/unknown
calls and budget exhaustion. The optional remote conformance command runs the
same application composition in independent processes against the existing
isolated database. It uses fixture generation, not a live model:

```sh
PYTHONPATH=src python3 -m scripts.serverless_preparation_conformance \
  --env-file PRIVATE_OPERATOR_ENV_FILE --output PRIVATE_RESULT_PATH
```

Hosted visitor identity, own-company input, live generation, exact hosted
exports, fresh remote provisioning, broader load and public release remain
separate work. Historical campaign and verification artifacts stay unchanged.
