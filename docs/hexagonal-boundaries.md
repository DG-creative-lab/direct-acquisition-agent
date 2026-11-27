# Hexagonal boundaries and integrated evidence

The modular monolith now has no temporary architecture exceptions. This closes
migration #88 through #89-#93. The import gate enforces structure; the finite
recovery corpus and existing domain/browser tests establish the behaviors below.
Neither module names nor passing component counts alone prove authority safety.

## Confirmed responsibility and authority map

| Owner | Contract and effect boundary | Evidence |
| --- | --- | --- |
| Public business packages and their domain/ports | Identity, eligibility, exact artifacts, approval, counted outcomes and narrow required effects | `docs/architecture.md`, module exports and existing commit-time SQLite tests |
| `application/workspace/service.py`, `ports.py`, `state.py` | Coordinate public use cases through injected collaborators; preserve server-owned scope and original commands | Compatibility/model journey and verified lifecycle/rebuild cases |
| `application/workspace/views.py` | Progress and blocker projections grant no new execution or approval authority | Completion-order regression and real browser polling cases |
| `adapters/http/workspace_server.py` | JSON/routes, Host/token/Origin, bounded paths/bodies and exact-subject downloads | Existing real HTTP tests and full interface gate |
| `entrypoints/workspace.py` | Acquire the root lock before recovery/cutover; drain handlers and scheduler before release | Real socket shutdown, second-server and failed-startup restart tests |
| `entrypoints/*`, root compatibility wrappers | Parse/dispatch commands; wrappers contain only named forwarding imports and optional launch | All named launch commands, wrapper rejection probes and canonical CLI replays |
| `bootstrap.py`, concrete adapters | Select implementations, credentials, SQLite, report writers and storage-error translation | Architecture role/export/cycle probes and offline command tests |

The application database owns verified admission, original inputs, clock,
consent, run ownership and review/learning facts. `workspace.sqlite` is rebuildable
only for positively registered new-format records. Legacy compatibility rows
retain their distinct recovery requirements. A restored checkpoint is historical
inspection, not proof of absent later provider work, current approval or a new
execution allowance. The root lock and one-worker limit remain intentional.

## Reusable offline command

Run from the repository root:

```sh
make boundary-check
# Or retain one specifically named fresh bundle:
make boundary-check BOUNDARY_OUTPUT=.local/boundary-evidence/review-1
```

Python and repository fixtures are sufficient. No frontend dependency is needed
for this native corpus. It uses actual SQLite and fresh interpreters with
network-denial audit hooks, propagated even when nested fixtures override their
environment. The gateways and transports are deterministic and synthetic. Forward/reverse
hostname resolution and name-info lookups are denied and recorded as attempts,
including aliases and lookups whose exceptions a dependency catches.
The default output is a new timestamped directory. An existing nonempty output
is rejected. `results.json` and `evidence.md` accompany retained databases,
authoritative row snapshots, manifests and subprocess logs.

| Required case | Independent observable result |
| --- | --- |
| `compatibility-model-journey` | Reuse merged #25's supported corpus and revision/amendment lifecycle. Replay and inspection add no calls; the actual inference-journal count matches recorded fake dispatches. Native subject/approval, synthetic maturity and follow-up checks remain in that fixture. |
| `verified-commit-rebuild-replay` | Reuse the merged draft-commit hard-exit fixture. Recover the original draft/run, stop at review without approval, accept once, count mature complete outcomes once and restore for byte-preserving inspection. Delete/rebuild only the verified projection through its CLI, then replay original handoff/finalize requests in a fresh process. Every authoritative row remains equal and changed inputs fail. |
| `uncertain-restart` | Preserve one uncertain reservation and one used call. Stop/reopen in a new interpreter, create no campaign, issue no new inference and retain the exact authoritative snapshot. |
| `profile-replay` | Reuse Fielddesk and the legacy reference profile. Each 100-record fixture has 24 exclusions, 70 mailed and six controls, costing 5,950 pence. Fresh CLI replay preserves distinct draft identities/manifests and every row; changed inputs fail without approval or execution. |
| `engagement-replay` | Reuse current contact/recipient/channel/sequence fixtures. One simulation has two enrollments, six steps and two initial dispatches. A new process returns the same receipt without invoking the synthetic transport or changing any row count. |

The backend suite independently runs the session, acceptance, authority and
legacy regression tests. The evidence command does not repeat those tests.

The source manifest is captured before production/fixture imports and after all
cases. It covers production, fixtures, configuration, evaluation tooling,
frontend inputs, CI, Makefile and current operating/architecture guidance.
Dirty source is identified by its full per-file hashes and aggregate fingerprint,
never only by HEAD. A changing source fingerprint invalidates the report.
Committed `docs/evaluations` artifacts are compared byte-for-byte by hash against
HEAD before and after execution. New summaries are published separately; older
reports are never regenerated. Append-only validation/results are excluded from
the evaluated input set to avoid self-referential reports.

Each case is mandatory and unique. A success flag without its counts, identities,
artifacts or exact fresh-process evidence fails grading. A caught network attempt
still fails. Incomplete coverage, altered historical bytes, infrastructure errors
and architecture violations return a nonzero exit status and retain failure
evidence. The JSON's per-case inventory hashes the retained files; manifest-value
digests and complete authoritative row snapshots separately bind domain values.

## Required gates and CI

```sh
make arch-check
make test
pnpm --dir frontend install --frozen-lockfile
make interface-check
make boundary-check
```

Run resource-intensive backend and browser suites separately on a constrained
local machine. CI uses isolated jobs and supported shards. The backend fixture
test checks the combined crash, projection rebuild and fresh-process replay on
every PR. Run the broader evidence command on demand for integrated workspace,
recovery or architecture-boundary changes. It retains a local bundle; CI does
not upload one on every PR.
Harmful import, unresolved re-export, implicit initialization cycle, wrapper
bypass and closed-exception probes remain in the backend suite. Semantic mutation
checks supplement those oracles; compilation or line coverage is not a claim of
behavioral completeness.

The published run is summarized in `docs/validation.md`; its JSON report and
Markdown summary live in `docs/evaluations/issue-93-boundary-*`. The hostname-guard
review follow-up is recorded separately in `issue-93-hostname-guard-*`; the earlier
reports retain their original bytes. Full per-case stores and logs remain in a
local bundle. They are not product data.

## Applicable later gates and limits

| Consumer | Evidence it can reuse | Work this does not establish |
| --- | --- | --- |
| #60, multichannel product | Explicit owners, a second synthetic profile, frozen sequence effects and recovery conservation | Complete agent-led discovery or real integrations |
| #68, conversational multichannel | Exact commands, source revision/consent, replay and stale-authority rules | New conversational multichannel routing or UI completion |
| #69, CRM conformance | Scoped native fixture identities and repeatable adapter boundaries | Authorized sandbox reads, real CRM mappings, pagination or licensing |
| #70, hosted pilot authority | Loopback guards, scoped facts, inspection-only restore and root-lock lifecycle | Hosted membership, authentication, OAuth, retention or multi-worker operation |
| #74, end-to-end adversarial evaluation | Attributable runner, immutable history and explicit recovery/effect oracles | Held-out semantic accuracy, prompt-injection coverage, calibrated cost or useful real-world autonomy |
| #77, release/pilot gate | Exact evidence and counts with explicit non-pass conditions | Live-provider readiness, delivery quality or operational pilot approval |

#23 remains independently completable. Only its small source-attribution helper
and bounded native-fixture approach are reused here; its unmerged browser runner,
results and frontend changes are not copied. Existing #25/#33 evidence is reused
through current executable fixtures and preserved historical report bytes.
The regular interface suite supplies current desktop/mobile and HTTP flows.
This report is deterministic control evidence, not live model behavior, editorial
quality, customer outcomes or exactly-once external delivery. No later issue is
closed by these results.
