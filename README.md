# GTM Agent Platform

**An agent-led workspace for turning product knowledge into reviewable
go-to-market actions, then using observed outcomes to inform the next experiment.**

We are building a shared workspace for Direct acquisition, Advertising and
Agentic commerce. The user describes a goal; the agent prepares a proposal using
permitted product context; a person reviews the exact result; channel-specific
evidence informs what to try next.

The initial product focus is contextual YouTube campaigns. The broader platform
brings outreach and commerce capabilities into the same knowledge, asset and
review experience. Customers should eventually be able to use one channel or
an explicitly enabled combination.

For YouTube, the goal is to recommend which creative fits which video/channel
context within a campaign's objective, budget and pacing, then update those
recommendations from qualified product-demo outcomes. Live targeting and
trusted measurement are still being built.

**Stage: in development.** This repository has usable local workflows and
bounded API/CLI capabilities. It does not yet provide the complete authenticated
hosted workspace or autonomous live campaign execution. The working product
name follows the repository; customer positioning is being tested.

Built by Dessi Georgieva.

## Product areas

| Area | Intended job | What is available here today |
| --- | --- | --- |
| Direct acquisition | Prepare contextual email, direct-mail and human-assisted call campaigns | Fictional Fielddesk email/call journeys; reviewed company intake to synthetic email export; a retained legacy postal simulation |
| Advertising | Match campaign objectives and creative to suitable contexts and evaluate results | Local authored YouTube placement drafts, exact review/manual export, and separate offline recommendation and model-evaluation tools |
| Agentic commerce | Improve product discoverability, representation and commerce readiness | A future integration area; the separate commerce application has not been migrated into this repository |

The [product overview](docs/product.md) is the current scope and claims
reference. The [platform map](docs/gtm-platform-map.md) defines shared ownership,
channel boundaries and the incremental build sequence.
For early conversations, use the [design-partner brief](docs/product-discovery.md).

## What you can try now

- Save Company & brief drafts and inspect the exact context behind a proposal.
- Prepare, edit, review and manually export an authored YouTube placement package
  from chat. Its catalogue is fictional and its comparison media is prerecorded.
- Inspect the fictional Fielddesk [recorded preparation example](examples/fielddesk-profile/README.md)
  or rehearse its synthetic email/human-call sequence. The legacy postal
  simulation remains a separate compatibility workflow.
- Inspect recorded postal/email results through the external outcomes API/CLI.
  These are operator-attested records, not an authenticated provider feed.

Offline workflows need no provider key. Selected planning and copy workflows
can use explicitly permitted OpenRouter calls. YouTube chat preparation and
synthetic sequence generation remain authored/offline; connecting a model does
not turn them into live targeting or real delivery.

The current example entry points use fictional products and contacts or the
user's explicitly reviewed company assertions. Authored specifications are not
externally verified product facts. The application sends no mail, makes no calls
and buys no advertising. Older fixed-product fixtures are retained only as
[legacy compatibility material](docs/legacy-product-demo.md).

## Try it locally

Requires Python 3.14+, Node 22.12+ and pnpm 10.33+ on macOS or Linux.

```sh
git clone https://github.com/DG-creative-lab/gtm-agent-platform.git
cd gtm-agent-platform
make workspace
```

Open [the local workspace](http://127.0.0.1:8768/).
The command installs the locked frontend dependencies, builds React and starts
the Python server, which serves the UI and API from the same origin.
Stop it with Ctrl+C.

For a zero-cost first run, start a conversation and choose
**Prepare a YouTube brief**. Follow the [YouTube flow](docs/youtube-preparation.md)
for the exact review and export steps. The [examples index](examples/README.md)
also includes a fictional Fielddesk preparation and recorded outcome fixtures.
The separate [postal user guide](docs/user-guide.md) describes the older
fixed-product simulation; its assumptions do not define the platform.

The server is loopback-only and supports one active worker per workspace root.
For an isolated root or another port:

```sh
make workspace WORKSPACE_PORT=8769 WORKSPACE_ROOT=.local/another-workspace
```

[Local operations](docs/workspace.md) covers development watching, optional
OpenRouter connections, startup and recovery. Model generation needs separate
consent, funding and current reviewed evidence. Keep credentials outside Git;
paid calls and live model-quality tests are opt-in.

## Read next

| Reader need | Maintained guide |
| --- | --- |
| Understand the product, intended users and current capability limits | [Product overview](docs/product.md) |
| Pitch the initial use case and test demand | [Design-partner brief](docs/product-discovery.md) |
| Find operating instructions, contracts and evidence | [Documentation index](docs/index.md) |
| Understand shared services, channel ownership and future commerce integration | [Platform map](docs/gtm-platform-map.md) |
| Understand ports, adapters, transactions and runtime | [Architecture](docs/architecture.md) |
| Plan the hosted YouTube journey and remaining work | [Migration plan](docs/youtube-migration-plan.md), [hosted preparation](docs/hosted-platform-preparation.md) |
| Assess what verification does and does not establish | [Validation](docs/validation.md) |

## Engineering

Python owns business rules, durable tasks, inference reservations, authority and
learning. React presents the same application commands. Provider and storage
adapters implement narrow ports; `bootstrap.py` selects the implementations.
The repository name has changed; Python imports and commands still use
`acquisition`. Package names, saved identities and historical artifacts have
not been migrated by this documentation change.

Before verification, install the locked frontend dependencies and Chromium
while network access is available:

```sh
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend exec playwright install chromium
```

After dependencies and Chromium are installed, run the checks:

```sh
make test
make arch-check
make boundary-check
make mutation-check
make interface-check
```

These checks run offline after those prerequisites are installed and need no
provider credentials. Local HTTP tests still require loopback access.
`make boundary-check` retains a fresh evidence bundle under
`.local/boundary-evidence/`; use `BOUNDARY_OUTPUT=/path/to/new-empty-directory`
for another destination. It fails on missing/failed cases, network attempts or
changed source/historical evidence. See
[boundary verification](docs/hexagonal-boundaries.md) for its finite scope.
CI gate purpose, measured cost and cadence belong in the
[gate audit](docs/ci-gate-audit.md).

Development branches use `feature/...`. No license terms have been selected.
