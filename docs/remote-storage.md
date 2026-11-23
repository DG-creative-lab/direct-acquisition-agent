# Remote libSQL storage and atomic admission

This slice selects remote application storage through `bootstrap.build_database`,
`build`, `build_admissions` and the contact, recipient and channel compositions.
Pass `path=None` and `remote_storage={'url': ..., 'token': ...}` explicitly.
Credentials belong to the server composition and transport, never domain inputs.
Local SQLite remains the default. No environment variable silently redirects a
local store. Hosted workspace identity and serverless continuation require later
integration. Local ancestry resolution, checkpoints and offline restoration are
not remote operations and fail explicitly if given this adapter.

## Transport and transaction contract

The adapter uses standard-library HTTPS and Hrana 3 JSON at `/v3/pipeline` on
remote libSQL. It does not use local replicas, sync, the diagnostic connection
monkeypatch or `libsql==0.1.11`. This targets the existing libSQL resource, not
the distinct Turso Database engine or its `turso_serverless` driver.
[Python engine guidance](https://docs.turso.tech/sdk/python/quickstart) and the
[Hrana 3 specification](https://github.com/tursodatabase/libsql/blob/main/docs/HRANA_3_SPEC.md)
define the selected transport. Server support is a conformance requirement.

Named parameters retain their original names and slot order. Integer precision,
blobs including unpadded response base64, nulls, finite floats and positional/named
rows have explicit serialization.
Credentials cannot follow HTTP redirects. Provider failures expose bounded
application messages, not raw provider text or parameter values.

Full-precision float bindings require special treatment: the existing provider's
JSON number parser changed 121 of 1,000 seeded timestamp values by one ULP in
the 23 November probe. That can reject exact frozen-message admission. Decimal
text plus SQL CAST also loses precision for some finite doubles. The adapter
therefore binds each float as its exact integer significand and reconstructs
the REAL value using power-of-two SQL arithmetic. Parameter tokens retain their
names/numbers; quoted text, identifiers and comments remain opaque. Only fixed
operators and derived integer powers are inserted, never user text. Native
SQLite comparisons cover positional, numbered, repeated, named, Tcl-style and
Unicode parameters, signed zero, subnormals and large finite values. Non-finite
floats remain rejected. Historical stored values are not rewritten.

Storage failures carry adapter-owned `reason` categories and an optional numeric
HTTP status for operator diagnostics. These survive the transaction wrapper and
uncertain COMMIT exception. HTTP clients still receive the bounded generic
reconciliation response. The adapter never automatically repeats a submitted
request, follows a redirect or exposes raw provider bodies/messages.

Every writer uses the existing `BEGIN IMMEDIATE` transaction and domain writer.
Only a positively rejected busy lock acquisition can retry, on a fresh stream,
within a bounded acquisition window. A submitted transaction body or uncertain
commit is never automatically repeated. Socket deadlines bound individual I/O;
they are not a guarantee about provider lock latency.

Each statement inside a transaction uses a server-side batch condition requiring
that the stream is still outside autocommit. Steps also depend on the previous
step succeeding. An expired or implicitly rolled-back transaction therefore
cannot continue as independent writes. A skipped step poisons the connection.
Transport failures likewise prevent further statements on that stream. Closing
a stream is best effort; provider cleanup may complete after the caller exits.

`TursoAdmissions` reuses the complete admission writer and integrity reader.
After an uncertain commit acknowledgement it reads the original scoped receipt,
validates its request, fingerprint, task plan, run and ownership, and returns it
only if the exact original admission exists. An absent or unreadable receipt
remains uncertain. Retrying an original command uses its original identity.
Staging and other domain-command failures retain their existing explicit replay
paths. No uncertainty grants inference, approval or delivery authority.

## Schema and import contract

Remote `user_version` operations map to `acquisition_schema`, a singleton journal.
The journal, every migration statement, legacy cutoff, and final version commit
in the same transaction. Initialization takes the writer lock before reading the
version. A failed migration rolls back DDL and journal together. Existing
migration code and validators remain the authority; application schema is 23.
`initialize=False` opens only a registered current schema and performs no repair.

A database with application tables but no journal is rejected. Ordinary startup
never adopts a diagnostic or restored database. The opt-in conformance command
can register only the existing dedicated probe through
`--register-reviewed-probe`. It compares every supported schema definition,
including triggers, with a freshly initialized local schema inside a remote
writer transaction, checks the old probe's schema-23 journal, rejects unknown
objects, and atomically registers the new journal. Formatting and the equivalent
`!=`/`<>` operators are normalized; literals and token boundaries are preserved.
Historical data, store identity, probe journal and legacy admission cutoff stay
untouched. This narrow probe operation is not a customer migration facility.
General imports, SQLite checkpoint downloads, engine conversion and downgrade
remain unsupported. Older binaries must not be used on this remote journal.

## Verification and limits

`tests/test_turso_storage.py` uses real SQLite behind an HTTP server with
independent streams. It checks concurrent admission and initialization, exact
replay and foreign-scope rejection, lost commit acknowledgements, migration
interruption/restart, atomic DDL/version rollback, exact bindings and a provider
rollback before a write. Existing SQLite/process and boundary suites protect
provenance, account/stop rules, reservation, publication and legacy compatibility.

Run the explicit remote check against the existing isolated resource:

```sh
PYTHONPATH=src python3 -m scripts.remote_storage_conformance \
  --env-file PRIVATE_OPERATOR_ENV_FILE --channel-recovery \
  --output PRIVATE_RESULT_PATH
```

It uses unique synthetic organizations and two independent admission processes.
It checks original-receipt replay, changed-input rejection, tenant isolation,
paused authority, lost acknowledgements, exact bindings and atomic rollback.
The idle case measures expiry rather than assuming that twelve seconds must
expire a transaction. Optional channel recovery uses offline fixture generation
and an unknown-result gateway; it must recover recorded calls without another
inference request. This is an operator conformance command, not an HTTP endpoint.
It prints no credentials, makes no live model calls and creates no new service.

Remote conformance is narrower than product readiness. Visitor sessions, real
input intake, bounded serverless continuation, hosted exports and actual delivery
are separate work. The loopback workspace deployment and root lock are unchanged.

Recorded verification on 21 November 2026 is retained in the
[commit-bound evidence](evaluations/issue-60-remote-storage-2026-11-21.json).
The full backend run passed 1,092 tests, and the final focused storage run
passed all 12 tests. Architecture passed with 213 modules and no exceptions;
all five native boundary cases passed with zero network attempts and unchanged
historical bytes. Remote native lease/unknown recovery and a synchronized
independent-process admission run passed. One overlapping remote run returned
an unclassified provider failure, retained alongside the successful isolated
repeat. Availability under wider contention is not established. No live model
request was made. Full fresh remote provisioning was not exercised: the remote
checks used the registered schema-23 probe and transactional DDL/version rollback;
fresh migrations and concurrent initializers used real local SQLite over HTTP.
