# Day five: interactive campaign workspace

Implemented on `feature/demo-workspace`. React and TypeScript provide the local interface; Vite produces static assets served by the Python loopback server. The existing modules retain responsibility for population rules, grounded copy, exact-subject review and mature outcome learning. No business rule or approval is implemented only in the browser.

## Start locally

Requires Python 3.11+, Node 22.12+ and npm on macOS or Linux. The local server uses a POSIX file lock to permit one server process per workspace root.

```sh
make workspace
```

Open `http://127.0.0.1:8768`. This command installs the locked frontend dependencies, builds the interface and starts the Python server. Stop the server with Ctrl+C. For a different port or isolated data directory:

```sh
PYTHONPATH=src python3 -m acquisition.workspace_server --port 8769 --root .local/another-workspace
```

After the first build, frontend development can use `npm --prefix frontend run dev` in another terminal. It rebuilds assets on change; refresh the browser against the Python server. Serving the compiled app and API from one origin preserves the local request controls. This build does not use a separate cross-origin development proxy.

## Design and operating flow

Visual direction: a restrained operating workspace with a dark forest navigation rail, clear typography, warm neutral surfaces and one green action accent. Audience records and copy remain the primary working surface, with exact-draft review beside them. Evidence, learning and committed activity have dedicated views. Self-hosted Inter and local vector icons avoid third-party font or asset requests. Motion is limited to brief view/dialog transitions and progress indicators, with reduced-motion support.

1. Create a campaign with **Offline fixtures** to explore without API cost. This seeds 1,000 explicitly synthetic records, two segments and four unchanged known fixture messages. Its fixed clock is visibly labelled simulated. A new campaign starts a separate sandbox and preserves older campaigns.
2. Inspect audience filters, all assignments, exclusions and copy variants. Download exact manifest or assignment bytes. A download must bind the displayed subject; a newer revision cannot silently substitute its file.
3. Inspect the product evidence and qualifications. Record a review reason to approve or request changes. The decision dialog pins the subject that was displayed when it opened. Approval grants only simulated handoff authority.
4. Record a suppression for a selected mailing business. The old approval becomes invalid. Rebuild, inspect the new revision and record a fresh decision. The backend rejects stale browser subjects even when the client still displays old state.
5. Simulate agency acceptance, then open the outcome window. Day-seven simulation imports positive observations without updating beliefs. Closing the window imports full explicit outcomes and invokes the existing maturity/completeness finalization gate.
6. Inspect counted beliefs, estimated uncertainty and advisory comparisons with the no-mail control. **Prepare a next experiment** can carry finalized learning into a new campaign in the same sandbox. Model copy then freezes that mature memory into its context. The old approval never carries over. Repeated business exposure still prevents a second learning cohort, as documented in day four.

The learning chart uses a labelled 0% to 50% visual scale and reports numerical intervals alongside it. The prior, sampling and recommendation thresholds remain illustrative. Synthetic labels deliberately create a visible signal; they are not measured customer performance.

## Optional model copy

Choosing **Generate with GPT-OSS-120B** and submitting the form uses the ignored server-side `.env.local` OpenRouter key. It invokes the existing custom worker, read-context and copy-submission tools, source-bound rendering and separate claim screen. It uses the existing ten-call reservation limit. The interface does not offer arbitrary model URLs, keys, shell tools or provider settings.

No model inference occurs simply by opening the interface, inspecting a campaign, reviewing, suppressing, handing off or simulating outcomes. Live preparation checks product evidence against the real current date as well as the sandbox's existing domain checks. A missing key, expired evidence or failed workflow is reported. A saved incomplete campaign can resume preparation through its existing run and inference receipts. A scoped request lookup recovers an admitted run even if its metadata write was lost, preserving its frozen context when editorial/learning memory later changes; unknown paid outcomes are not automatically dispatched again.

Model-mode clocks progress with real time until an explicit outcome simulation advances that sandbox. Offline and inherited future experiment clocks are visibly simulated. None of these clocks or approvals authorizes external printing or sending.

## Ownership and recovery

`workspace.py` is an entry-point facade around the existing composition root. It calls public application services and ports rather than reimplementing domain decisions. `workspace_server.py` provides bounded JSON transport and serves only compiled frontend assets and explicit verified artifact downloads.

Each root has a small separate `workspace.sqlite` control store for session metadata and command identities, plus existing application databases under sandbox directories. The core schema remains v5. Descendant experiments share their parent's organization/application database to retain scoped learning; independent campaigns have separate sandboxes. Organization and database paths are resolved from server-owned metadata, never supplied by action payloads.

The control store does not claim a distributed transaction with the domain database. A command is durably admitted with a fingerprint before execution. If a domain commit succeeds but metadata/response persistence fails, retrying the same command reuses domain idempotency and completes the metadata. A monotonic sandbox-clock advance may remain visible after a later operation fails. It does not create an approval, outcome or belief by itself. Reusing a request ID for another action or changed inputs is rejected before that advance. Completed command replay refreshes current state and is labelled as receipt observation, not another effect.

A single server process serializes facade operations. A per-root file lock prevents a second server from opening the same workspace. Domain SQLite transactions, exact subjects, scoped reads, leases, inference reservations and authoritative receipt journals remain in force. This is a local prototype rather than a multi-user deployment architecture.

## Local HTTP boundary

The server binds only to `127.0.0.1`. It checks the Host header, a per-start browser token, the exact local Origin for mutations and bounded JSON request bodies. There is no permissive CORS response. The startup token is injected into the served HTML and expires on server restart; reload the page to obtain a new one. Static paths must stay inside `frontend/dist`, and artifact routes resolve only a known campaign and exact displayed subject. Errors do not return provider bodies or credentials.

These controls protect the local browser transport. They do not establish user authentication, separation of duties or a production authorization service. Local reviewer/operator identities are configured by the trusted sandbox. Hosted identity, TLS, tenant membership, operational hardening, real outcome feeds and external agency dispatch remain future work. Do not expose this server publicly.

## Verification

```sh
make test
make arch-check
make mutation-check
make interface-check
```

The suite has 149 Python tests, including 14 workspace tests. They exercise the suppression/approval journey, rejection and revocation, exact artifact downloads, scoped creation/replay, complete outcome learning and restart, command identity before clock mutation, lost metadata after a domain commit, model integration with a deterministic gateway double, inherited mature context without inherited approval, real HTTP Host/token/Origin checks, bounded input, static traversal and per-root server exclusion.

The selected mutation set has 22 probes, including three new workspace boundaries: Origin validation, command identity and displayed-subject artifact binding. The interface build checks strict TypeScript, unused declarations and formatting; CI adds the locked frontend build to the existing Python 3.11 to 3.14 matrix.

Browser verification exercises the real React-to-HTTP-to-SQLite journey, not a mock UI. Desktop and 390px mobile views were inspected; a discovered mobile table-width overflow was corrected. Native dialogs trap focus, restore focus and support Escape. Audience/copy tabs support arrow keys, Home and End. Async campaign loads abort on selection changes and stale responses cannot overwrite another selected campaign. Failed decisions remain in their dialog with the server error. Browser command identity survives uncertain responses in session storage.

No paid model calls were made during this implementation. No hosted deployment, walkthrough video or external application submission is included in this interface slice.
