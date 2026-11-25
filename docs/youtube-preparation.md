# Local YouTube preparation

Issue #132 implements the first native YouTube slice of the [channel contract](youtube-channel-contract.md). It runs inside the existing local workspace. This is authored campaign preparation, not live inference, verified inventory or a deployed ad campaign.

## Use the flow

1. Open a new conversation and choose **Prepare a YouTube brief**. This fills a request and selects **Allow a YouTube placement draft for this request**. Nothing runs until you send it.
2. Send the request. The installed `youtube.prepare.v1` capability freezes the request, permission, authored context, conversation revision and exact runtime plan. It saves an unapproved native campaign revision and shows the actual preparation activity in chat.
3. Edit the title, objective and fictional placement selection. **Save YouTube draft** appends a revision; saving an unchanged draft keeps the existing revision. A later draft has no inherited approval.
4. Open each bundled comparison preview and inspect **Exact reviewed payload and fingerprint**. Missing placements or unavailable media block approval. Budget and schedule remain explicitly unset.
5. Choose **Approve this YouTube package**, then **Download manual JSON**. Approval binds the exact package, context, media, local origin and current authority generation for 24 hours. Download requires that approval to remain current. **Revoke approval** blocks subsequent downloads, including replay of an earlier export command.

For advice without saving a draft, leave the placement permission unchecked or ask for advice only. Mixed explicit channel requests ask which channel to prepare. This authored capability recognizes bounded context keywords; it does not interpret arbitrary requests with an LLM. Instruction-test preparation, measured visits and learning are deferred to #133.

The two installed contexts are video editing and audiobook narration. The four placement records are deliberately fictional. The refreshed recordings and matching passages are copied from merged YouTube source `2d4e60d4027217edada6c93153d02cc0aa17cc75`. Speech and imagery are AI-generated, as disclosed on each preview. The destination uses new v2 creative/comparison identities; provenance and source hashes are recorded in `examples/youtube-media/README.md`. Preview URLs work while the local server and exact media remain available. They collect no playback, preference, visit or conversion events. The export records these limits and is not a Google Ads upload file.

The changed authored context cannot reuse old approvals or export receipts. Existing native history stays immutable; retain an older store for historical inspection and prepare a fresh YouTube conversation in the updated app. The separate `examples/youtube-ad-samples/` folder contains four additional ad-copy candidates, scripts and images. They are not installed as selectable ads or substituted for the existing comparison task. This update imports no credentials, live authoring capability or source application history.

## Ownership and recovery

`acquisition.youtube` owns native scope, package validation, review subjects and the shared UI/tool command surface. Its typed tool adapter can inspect or save an explicitly permitted placement draft; it exposes no human approval or export operation. `workflows/youtube_preparation.py` composes the existing conversation admission values and runtime. Bootstrap installs the authored handler and an authority adapter over the existing platform operator/reviewer records. Approval and revocation use the server-resolved local reviewer; draft and export use the local operator. Disabling or changing either role changes the subject, and reopening never overrides prior administration. Runtime imports no channel code.

The existing application database gains additive schema 26 after the saved-intake planning migration at schema 25. The earlier unpublished YouTube-only schema-25 preview is recognized and upgraded transactionally without discarding its history. Earlier binaries reject this schema; use a pre-upgrade copy to test an older binary. Private append-only channel tables retain request receipts, frozen preparations, interactions/results, campaign revisions, approvals and revocations. Message admission commits the conversation append, original task and channel linkage together. Publication checks the active lease, original full plan, unchanged conversation revision, native stop, scope, permission and context before committing the draft, terminal conversation result and runtime settlement together. Other installed workers cannot claim this capability.

A lost reply is retried with the original request inputs and identity. A queued or interrupted preparation exposes **Resume original YouTube preparation** and reuses the original operation. A newer conversation revision, stop or competing campaign edit prevents late publication. Failed atomic admission is distinguished from an uncertain failure after admission; only the former unlocks editing. Browser commands retain the original application-store identity, so restarting the same origin on another root cannot retarget pending work.

Approval stores the exact reviewed payload and receipt atomically. Export recomputes the current subject and validates scope, authority, expiry, revocation and assets before recovering an old export receipt. Receipt history is not current authorization. SQLite rollback and the existing libSQL wire adapter are exercised locally. A fresh interpreter/connection sees saved state; this does not claim hosted Turso or multi-worker readiness.

Read-only inspection and verified-paused stores continue to reject channel writes. This local slice installs no hosted membership registry, credential session, inference account or alternate provider journal. Platform issues #130/#131 and applicable #70 remain prerequisites for hosted/live use. Existing source stores and approvals are not imported or trusted by this implementation.

## Verification boundaries

Native command tests exercise exact bytes, stale and foreign subjects, media/origin change, revocation/expiry, rollback, lost acknowledgement, duplicate keys, concurrent edits, stale leases, cancellation, resume and schema-24 upgrade rollback. HTTP tests use the real loopback server and SQLite. Browser tests exercise edit, exact approval, download, reload, advice-only behavior and lost/rejected message recovery. A local Hrana simulator exercises the production libSQL adapter; no hosted database or provider is contacted.

The authored contract examples remain a specification spanning several future slices. This change covers preparation, review, manual export and local preview behavior; it does not claim to execute the full viewer, live inference, experiment, correction or Bayesian-learning example set. See [validation](validation.md) for the retained gate results and finite evidence.
