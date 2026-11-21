# Hosted execution and storage feasibility

Original experiment: 20 November 2026 · Parent #60 · Baseline 72ac7cb.
Carried forward for review on 21 November 2026 at merged main `2dcc5f4`, on
`feature/60-hosting-feasibility-main`.

The cloud observations below belong to the original experiment. The original
JSON summary is preserved byte-for-byte, including its failures, deployment
identities and old source fingerprint. This carry-forward runs local verification
against merged main; it does not redeploy the probe or revalidate the remote
driver on the new branch. See the
[current-main validation](evaluations/issue-60-hosting-main-validation-2026-11-21.json)
for that separate evidence.

## Decision and scope

Vercel Hobby can build and run the Python 3.14 probe, and the isolated Turso
Starter database retains application artifacts across connections. This is a
conditional infrastructure result, not approval to replace the product's
SQLite connection with the native libSQL driver. Concurrent admission needs
an explicit contention and receipt-reconciliation contract before cutover.

The runnable product, its local root lock, background worker, admission formats
and provider selection are unchanged. No live-model generation, hosted visitor
identity, real campaign intake or delivery was enabled. The probe uses existing
application writers with synthetic source and model fixtures. It is not the
online MVP described in [the deployment plan](mvp-demo-deployment.md).

## Isolated resources

- Vercel project: `direct-acquisition-feasibility`, on the confirmed Hobby plan.
- Database: `acquisition-hosting-probe`, Turso Starter, EU West / Ireland.
- Database credentials are connected to this project's Development and Preview
  environments. The diagnostic bearer token is deployment-specific.
- Successful preview deployments retain Vercel Authentication. The operator
  endpoint additionally rejects requests without its own token with HTTP 403.
- No Git repository is connected. The original probe was uploaded through the
  CLI from tracked source/configuration paths and two explicit probe entry
  files. That working-tree packager did not enforce committed bytes. The
  commit-based package contract below supersedes it for future packages.

The account already had the free Turso integration installed. No paid plan,
top-up, model request or customer data was used. Hobby's personal/non-commercial
restriction still applies to the later release. The CLI upload demonstrates a
deployment path without connecting this organization-owned Git repository.
[Vercel terms](https://vercel.com/legal/terms) ·
[Git integration limits](https://vercel.com/docs/limits#connecting-a-project-to-a-git-repository) ·
[Turso pricing](https://turso.tech/pricing)

## What was exercised

`scripts/hosting_probe.py` calls the existing application composition and
transaction writers. The diagnostic connection wrapper supplies the minimum
driver differences needed to run that experiment. It is not a product adapter.

| Boundary | Observable check |
| --- | --- |
| Migration and SQL | Existing schema, JSON SQL, foreign-key activation and committed reads through a new connection |
| Admission | Trigger-induced rollback; two competing requests for one exact intent; original paused execution and foreign-scope rejection |
| Channel generation | Original context, admission, claim, three recorded fixture calls and one validated unapproved artifact |
| Publication | A failure at the task success event rolls back artifact and completion; retry publishes the original recorded result |
| Lease | An expired lease cannot publish; recovery reuses the three recorded calls with a gateway that rejects any new generation |
| Uncertainty | One unknown call remains fenced after rebuilding the application; no artifact or additional call is created |
| Replay | Original run, artifact and call receipts remain equal; changed inputs and foreign reads are rejected |
| Provider idle behavior | Commit and subsequent receipt reads measure the actual outcome; a timing assumption cannot substitute for observation |

The first complete hosted run passed transport, channel generation,
publication rollback, lease recovery, uncertainty and replay. Concurrent
admission returned a provider error. A separate recovery using the same saved
request found the original receipt and retained exactly one runtime run.
Serial admission passed. This is evidence for preserving identity during
recovery, not evidence that the direct driver handles simultaneous admission
without additional coordination.

A second preview deployment replayed the first deployment's original channel
run with zero additional calls. An isolated repeat of competing admission,
without the workstation probes running alongside it, again reported
`remote_transaction_idle_rollback`. This confirms the contention blocker
independently of the first run's additional database load. Observed timings
are diagnostic measurements, not latency guarantees.

The initial idle experiment assumed a six-second pause would exceed the
documented transaction window. Its assertion failed: that assumed deadline
was not observed. The revised experiment waits twelve seconds, reconciles two
original marker rows and rejects partial writes or an acknowledged missing
commit. It reports whether expiry was actually observed. Application lease
checks remain mandatory regardless of provider idle behavior.
A twelve-second idle pause on the second deployment did produce a commit
error and zero committed marker rows. Reconciliation found no partial write,
and the probe made no repeated write attempt.
[HTTP protocol](https://docs.turso.tech/sdk/http/reference)

## Required adapter decisions

The installed `libsql==0.1.11` driver is not a drop-in `sqlite3` connection:

1. Rows need both positional and named access for current readers.
2. Named parameter dictionaries need a verified binding contract. The probe
   preserves SQLite slot order without rewriting SQL and tests quoted text,
   comments, repeated names and differing dictionary insertion order.
3. Remote `PRAGMA user_version` writes are rejected. The experiment uses a
   separate version table within the same migration transaction. A product
   adapter needs a reviewed migration journal and upgrade/restore contract.
4. Local `PRAGMA busy_timeout` configuration is not available over this
   protocol. Provider lock/timeout behavior needs a bounded hosted policy.
5. Provider errors need explicit normalization. A failed commit must be
   reconciled against the original receipt, not repeated as a new command.

The next implementation slice should choose a compatible remote transport,
preserve exact bindings and admission identity, and prove two competing
invocations with bounded contention and original-receipt recovery. Do not add
generic automatic transaction replay around uncertain inference or effects.
Provider I/O stays in adapters; bootstrap selects the supported composition.
Historical SQLite artifacts and paused verified formats retain their rules.
[Python driver choices](https://docs.turso.tech/sdk/python/quickstart)

## Reproduction and retained evidence

Local baseline, with no cloud credentials or optional dependency:

```sh
python3 scripts/hosting_probe.py --mode local --output .local/hosting-local.json
```

The optional native-driver experiment uses `libsql==0.1.11` in an isolated
environment. Remote execution requires explicit `--mode remote`, the dedicated
probe database hostname, and server credentials. `--env-file` reads only the two
Turso variable names from an ignored local file. No raw provider exception,
SQL parameter or credential is written to result evidence.

`scripts/package_hosting_probe.py` creates a separate deployment package.
Commit the reviewed source, configuration and both probe entry files first,
then select that exact commit with `--commit`:

```sh
python3 scripts/package_hosting_probe.py /tmp/acquisition-probe-package --commit REVIEWED_COMMIT
```

The default is `HEAD`, resolved once to an immutable commit ID. Every application,
configuration and probe entry file is read from that commit's Git blobs. Staged
and unstaged edits are ignored; a commit missing either probe entry is rejected.
Committed symlinks and submodules are rejected before creating the output.
`hosting-probe-source.json` records the resolved commit, Git source paths and
SHA-256 hashes of the packaged payload, including generated runtime configuration
and the allowlisted project-link metadata. Record this manifest with new
deployment evidence. An uncommitted probe edit cannot be deployed by this path.

`python3 -m scripts.run_hosting_probe` invokes the protected deployment and
saves each result, including failures. Its header token is read through a
private temporary curl configuration, not supplied as a command argument.
Neither script adds a CI job or makes cloud calls in ordinary tests.

The evidence summary is
[issue-60-hosting-feasibility.json](evaluations/issue-60-hosting-feasibility.json).
It distinguishes original failures, diagnostic adjustments, local controls,
hosted cases and fresh-deployment replay. The first upload's function-discovery
failure is retained; CLI upload success alone was not accepted as deployment
success. The final build used a concrete handler entry file and actual READY
status plus an authenticated HTTP health response.

Original verification: all 1,074 backend tests passed, the seven focused probe
tests passed, and architecture passed with 209 modules and zero exceptions.
The offline boundary evaluator passed its five cases. No frontend files were
changed. Live-model quality and public visitor readiness remain unverified.

## Carry-forward verification, 21 November 2026

Merged-main smoke passed all six scenarios on the clean PR #119 baseline.
The carry-forward passed all 1,082 backend tests, seven focused feasibility
regressions, seven local contract cases, architecture and all five boundary
cases. Local provider-expiry behavior is explicitly not applicable. The
[current validation record](evaluations/issue-60-hosting-main-validation-2026-11-21.json)
binds these results to the new branch and preserved cloud evidence.
No frontend or production files changed, and no cloud probe was rerun.

The carry-forward record above predates the packaging review fix. Its source
fingerprint remains historical. The
[packaging review evidence](evaluations/issue-60-hosting-packaging-review-2026-11-21.json)
records the later regression, fix and verification separately; the original
cloud JSON and earlier validation record remain unchanged.
