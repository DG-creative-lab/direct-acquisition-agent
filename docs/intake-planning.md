# Planning from saved intake

This slice connects saved company and campaign brief revisions to the existing
bounded conversation planner. It produces a proposal, clarification questions or
an unsupported explanation. It creates no campaign, reviewed product profile,
approval, contact import or outbound effect. User assertions remain unverified.
Verification uses synthetic providers; no live-model quality claim is implied.

## Ownership and flow

Creative owns company assertions and campaigns owns campaign requirements.
Conversations owns the frozen planning selection, context and result. Bootstrap
wires their narrow public APIs and the SQLite/Turso adapters. Runtime continues
to own admission, calls, leases, stop authority and atomic task result/events.

An explicit request names a saved brief and its exact current revision. An
append-only source record binds organization, actor, original request ID,
company/brief snapshots, their fingerprints, native conversation revision and
model settings. Six requests per brief conversation and two calls per request
remain the bounds. A new key cannot repeat a selection already staged for that
brief version. Exact retry resumes its original source even after later edits.
New selections require the current brief and never silently change its pinned
company version. Provider configuration and source size are checked before the
selection commits. A later selection waits until every earlier source has its
corresponding runtime run, not just a saved planning row. The check and revision
advance share one write transaction. A queued run is sufficient; execution need
not finish or be unpaused. Original-request recovery bypasses this new-selection
gate and keeps its frozen source. The existing verified planning admission independently loads
and rechecks this source before assigning execution ownership.

A dedicated intake interpretation tool shares the existing planner/inference
harness. Its knowledge contains no default iwoca product facts. User snapshots
are separate from authored guidance. The server copies requirements and source
references into the result; the model proposes interpretation and questions,
not replacement budgets, scope, facts or execution permission. Deterministic
readiness checks identify missing input and unsupported installed capabilities.
No model call is made when those checks can explain the blocker directly.

Native campaign preparation cannot consume this result format. Managed intake
conversations cannot be amended or prepared through the ordinary chat APIs.
Users refine the saved brief and explicitly request another interpretation.
Older interpretations remain visible as historical records.

## Browser and transport

The Company & brief area provides a planning action for the exact saved brief.
Unsaved edits must be saved or discarded first. Consent is explicit and bounded;
model credentials remain in existing server-side provider sessions. Read-only
progress and history never dispatch inference. Pending commands retain their
original store identity and exact inputs before dispatch. Cross-root retries,
late responses for another selected brief and uncertain inference must not
create replacement commands or clear recovery incorrectly.

## Acceptance portfolio

- Exact company/brief wording, qualifications and source identities survive the
  UI, frozen context, model envelope, result and restart.
- Partial input and unsupported country/currency/channel requests retain their
  source requirements and produce questions/blockers, never default substitution.
- Same key with changed input/configuration conflicts; a different key for an
  already selected brief version cannot repeat planning or spend.
- Competing selection, staging loss, lost admission/reply and restart converge
  on one source/conversation/run; unknown paid calls remain fenced.
- Organization/reference substitution and corrupt source relations fail before
  admission or inference. Stop and lease checks still fence result publication.
- Editing either source cannot rewrite an older plan or make it authorize a new
  source. Current/historical status derives from saved revisions.
- Model output cannot create campaign, approval, profile or outbound authority.
- Migration rollback, historical bytes, legacy cutoffs, inspection-only roots,
  architecture and existing browser/workflow behavior remain covered.

## API and rollout

- `GET /api/intake/briefs/{id}/readiness?revision=N` reads deterministic readiness.
- `GET /api/intake/plans?brief_id=...` reads at most six source/result selections.
- `GET /api/intake/plans/{request_id}` reads original progress without credentials.
- `POST /api/intake/plans` accepts only `request_id`, `brief_id`,
  `brief_revision` and `allow_model: true`. It requires the existing loopback
  security controls and matching `X-Intake-Store` identity.

Schema 25 adds the append-only source table transactionally to schema 24. Failed
migration leaves the previous version intact. Historical revision payloads,
legacy cutoffs and admission policy are preserved. Upgrade every process using
a store before writing schema 25; an older schema-24 binary cannot operate that
migrated store. A checkpoint restore retains source inspection without granting
execution or write authority. Never restore a checkpoint to repeat an uncertain
model request.

The local browser and native harness are tested using injected synthetic model
responses. Real OpenRouter response quality, hosted tester identity and live
campaign generation from arbitrary company assertions remain unproven/deferred.
Verified planning formats remain paused. The managed remote conformance uses
its existing legacy execution policy and an in-process synthetic provider; it
does not grant execution permission to a verified store.
