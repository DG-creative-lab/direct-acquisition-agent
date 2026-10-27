# Direct Acquisition Agent

An acquisition workspace for preparing audience-specific direct-mail experiments, reviewing the exact campaign and learning from counted outcomes. It combines a custom agent runtime with deterministic population rules, source-grounded copy generation and explicit human approval.

Built by Dessi Georgieva. The current product is a local demonstration using synthetic businesses, simulated agency acceptance and synthetic responses. The example campaign uses public iwoca product evidence. It has no connection to iwoca production systems, sends no mail and makes no lending decisions.

## What the product does

- Prepares a campaign audience with traceable exclusions, a bounded mailing budget and randomized A/B/no-mail assignments.
- Uses offline copy fixtures or explicitly requested GPT-OSS-120B generation through OpenRouter. Generated framing is checked against a frozen product fact pack; factual text and qualifications are inserted by code.
- Records review decisions against an exact draft and current evidence. Suppression, revision, expiry or withdrawn authority blocks a new simulated handoff until the requirements are met again.
- Counts only complete, mature outcome cohorts. Bayesian comparisons with the no-mail group inform a proposed next experiment, which needs its own review.

The [product overview](docs/product.md) explains the intended users, authority boundaries and current limits. The [user guide](docs/user-guide.md) follows the interface from a new campaign through review and learning.

## Try it locally

Requires Python 3.11 or later, Node 22.12+ and npm on macOS or Linux.

```sh
make workspace
```

Open [the local workspace](http://127.0.0.1:8768/) and choose **New campaign → Offline fixtures → Prepare campaign**. This path needs no model key and makes no inference requests. All audience records and results are labelled synthetic. Stop the server with Ctrl+C.

To try model copy, configure `OPENROUTER_API_KEY` in ignored `.env.local`, then explicitly choose **Generate with GPT-OSS-120B**. This spends provider credit and requires an unexpired, manually reviewed fact pack. No paid fallback or uncertain-call retry is automatic. See [model integration](docs/model-integration.md) and [product grounding](docs/product-grounding.md).

The server is loopback-only and intended for trusted local use. Startup, storage, recovery and CLI alternatives are in [local operations](docs/workspace.md).

## Documentation

| Reader need | Guide |
| --- | --- |
| Understand the product and demonstrated scope | [Product overview](docs/product.md) |
| Walk through campaign, review and learning | [User guide](docs/user-guide.md) |
| Understand modules, state and transactions | [Architecture](docs/architecture.md) |
| Assess a path to hosted operation and scale | [Scalability](docs/scalability.md) |
| Run and recover the local application | [Workspace operations](docs/workspace.md) |
| Inspect approval and invalidation semantics | [Review reference](docs/reviews.md) |
| Inspect outcome contracts and Bayesian assumptions | [Learning reference](docs/learning.md) |
| Inspect inference controls and evidence | [Model integration](docs/model-integration.md), [grounding](docs/product-grounding.md) |
| Assess verification and remaining gaps | [Validation](docs/validation.md) |
| Reuse the visual system and trace the shared mark | [Branding](docs/branding.md) |

## Engineering

A Python modular monolith owns business rules, durable tasks, inference reservations and authority. SQLite and OpenRouter sit behind narrow ports. React is a presentation client of the same-origin local API. The workflow order is explicit in code, and the model's tool surface is bounded to context reading and copy submission.

```sh
make test
make arch-check
make mutation-check
npm --prefix frontend exec -- playwright install chromium
make interface-check
```

Offline checks need no provider credentials. Live model quality is evaluated separately. A [recorded generated-copy example](examples/grounded-run/letters.txt) is supplied for inspection, with its limitations described in the grounding guide.

Development branches use `feature/...`. Build history is available in Git; the guides describe the current product and label future work explicitly. No license terms have been selected yet.
