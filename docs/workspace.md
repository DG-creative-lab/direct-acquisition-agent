# Local workspace and operations

React and TypeScript provide the local interface; Vite produces static assets served by the Python loopback server. Population rules, grounded copy, exact-subject review and mature outcome learning are enforced in the Python application.

## Start locally

Requires Python 3.11+, Node 22.12+ and pnpm 10.33+ on macOS or Linux. The local server uses a POSIX file lock to permit one server process per workspace root.

```sh
make workspace
```

Open `http://127.0.0.1:8768`. This one command installs the locked frontend dependencies with pnpm, builds the interface and starts the Python server. The Python process serves both the compiled React application and the API from the same origin, so normal use does not need a second frontend server. Stop it with Ctrl+C. For a different port or isolated data directory:

```sh
make workspace WORKSPACE_PORT=8769 WORKSPACE_ROOT=.local/another-workspace
```

For frontend development, keep `make workspace` running and use `pnpm --dir frontend run dev` in another terminal. The watcher rebuilds static assets on change; refresh the browser against the Python server. It is a build watcher, not a separate frontend server. Serving the compiled app and API from one origin preserves the local request controls.

## Product and presentation

Follow the [user guide](user-guide.md) for campaign creation, audience and copy inspection, exact-subject approval, simulated handoff and learning. The [product overview](product.md) separates demonstrated capabilities from future work.

The interface follows the publication's Arial/Helvetica typography, warm paper and black navigation, with the shared static Op Art mark. Historical creative previews retain their original presentation. Fonts and vector assets are served locally; reduced-motion support applies to workspace transitions. See [branding](branding.md) for tokens and provenance.

## Optional model copy

Choosing **Generate with GPT-OSS-120B** and submitting the form uses the ignored server-side `.env.local` OpenRouter key. It invokes the existing custom worker, read-context and copy-submission tools, source-bound rendering and separate claim screen. It uses the existing ten-call reservation limit. The interface does not offer arbitrary model URLs, keys, shell tools or provider settings.

No model inference occurs simply by opening the interface, inspecting a campaign, reviewing, suppressing, handing off or simulating outcomes. Live preparation checks product evidence against the real current date as well as the sandbox's existing domain checks. A missing key, expired evidence or failed workflow is reported. A saved incomplete campaign can resume preparation through its existing run and inference receipts. A scoped request lookup recovers an admitted run even if its metadata write was lost, preserving its frozen context when editorial/learning memory later changes; unknown paid outcomes are not automatically dispatched again.

Model-mode clocks progress with real time until an explicit outcome simulation advances that sandbox. Offline and inherited future experiment clocks are visibly simulated. None of these clocks or approvals authorizes external printing or sending.

## Ownership and recovery

`workspace.py` is an entry-point facade around the existing composition root. It calls public application services and ports rather than reimplementing domain decisions. `workspace_server.py` provides bounded JSON transport and serves only compiled frontend assets and explicit verified artifact downloads.

Each root has a small separate `workspace.sqlite` control store for session metadata and command identities, plus existing application databases under sandbox directories. The core schema is v6. Descendant experiments share their parent's organization/application database to retain scoped learning; independent campaigns have separate sandboxes. Organization and database paths are resolved from server-owned metadata, never supplied by action payloads.

Conversation messages and planning requests use `<root>/conversations.sqlite` under the fixed local conversation scope. They are accessible through the [conversation API and CLI](conversations.md). Reading and appending messages make no model request. The explicit plan action invokes OpenRouter and returns a proposal or clarification; it does not create a campaign or record approval. The React workspace still presents the campaign operations flow.

The control store does not claim a distributed transaction with the domain database. A command is durably admitted with a fingerprint before execution. If a domain commit succeeds but metadata/response persistence fails, retrying the same command reuses domain idempotency and completes the metadata. A monotonic sandbox-clock advance may remain visible after a later operation fails. It does not create an approval, outcome or belief by itself. Reusing a request ID for another action or changed inputs is rejected before that advance. Completed command replay refreshes current state and is labelled as receipt observation, not another effect.

A single server process serializes facade operations. A per-root file lock prevents a second server from opening the same workspace. Domain SQLite transactions, exact subjects, scoped reads, leases, inference reservations and authoritative receipt journals remain in force. This is a local prototype rather than a multi-user deployment architecture.

## Local HTTP boundary

The server binds only to `127.0.0.1`. It rejects absolute-form request targets before authentication or routing, then uses the same parsed origin-form target for both. It checks the Host header, a per-start browser token, the exact local Origin for mutations and bounded JSON request bodies. There is no permissive CORS response. The startup token is injected into the served HTML and expires on server restart; reload the page to obtain a new one. Static paths must stay inside `frontend/dist`, and artifact routes resolve only a known campaign and exact displayed subject. Errors do not return provider bodies or credentials.

These controls protect the local browser transport. They do not establish user authentication, separation of duties or a production authorization service. Local reviewer/operator identities are configured by the trusted sandbox. Hosted identity, TLS, tenant membership, operational hardening, real outcome feeds and external agency dispatch remain future work. Do not expose this server publicly.

## Development and verification

Run `make test`, `make arch-check` and `make mutation-check` for backend checks. Install Chromium with `pnpm --dir frontend exec playwright install chromium`, then run `make interface-check`. See [validation](validation.md) for the test portfolio and its limits.

Native dialogs support focus containment, return focus and Escape. Audience/copy tabs support arrow keys, Home and End. Stale loads cannot replace another selected campaign. Failed decisions retain the server error in their dialog. Browser session storage retains each uncertain command identity until confirmed success; storage failure blocks dispatch. Equivalent field ordering preserves identity and older pending-key records migrate without dropping requests.

Historical creative previews retain their original styling and bundled Inter font independently of workspace tokens. The shared mark, accessible navigation name and brand provenance are documented in [branding](branding.md).
