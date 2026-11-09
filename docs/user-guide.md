# Campaign user guide

Use this guide with the local React workspace. [Local operations](workspace.md) covers installation and recovery. The workflow below uses offline fixtures and spends no provider credit.

```mermaid
flowchart TD
    PREP[Prepare audience and copy] --> INSPECT[Inspect exact proposal and evidence]
    INSPECT --> DECIDE[Human review]
    DECIDE -->|Approve current subject| ACCEPT[Simulated handoff]
    DECIDE -->|Request changes| REVISE[Prepare a new proposal]
    REVISE --> INSPECT
    ACCEPT --> WINDOW[Observe complete mature synthetic cohort]
    WINDOW --> LEARN[Count outcomes and compare with control]
    LEARN --> NEXT[Propose next experiment with memory]
    NEXT --> PREP
    DECIDE -->|Suppression or evidence changes| STALE[Old approval invalid]
    STALE --> REVISE
```

## 1. Prepare a campaign

In a new chat, choose **Try the offline example**. The agent saves the brief, prepares the contractor experiment in the background, and offers **Review campaign**. Progress survives refresh.

For a custom brief, describe the objective, audience and explicit GBP budget. Sending invokes bounded OpenRouter planning. To request generated copy, say so in the message and enable **Allow model copy for this request**. The agent continues through preparation and checks, asking only for missing input or permission. It ends at an unapproved review candidate. A new message stops continuation of the earlier brief.

The manual campaign controls remain available: choose **New campaign**, select **Offline fixtures** and choose **Prepare campaign**. The workspace creates a separate synthetic sandbox with 1,000 business records, two audience segments and four fixture variants. The campaign displays a simulated clock. Independent new campaigns preserve previous campaigns in their own sandboxes.

Model copy is optional. Selecting **Generate with GPT-OSS-120B** explicitly requests provider inference using the server's OpenRouter key and spending controls. Opening or navigating the interface alone makes no inference request. See [grounding](product-grounding.md) before evaluating generated copy.

Choose **Review campaign** in the conversation to inspect and decide on the prepared result without leaving chat. **Open campaign workspace** retains access to the full operational controls.

## 2. Inspect the audience and messages

The **Campaign** view shows source population, mailing recipients, no-mail controls and synthetic cost. The **Audience** tab exposes business assignments, exclusions, suppressions and segment filters. Inspect the counts together; a control is an enrolled business deliberately receiving no mail, whereas an exclusion is outside the experiment.

The **Copy variants** tab shows both treatments for each segment. Expand identity and evidence details to inspect provenance. Historical creative previews preserve their original presentation independently of workspace branding. Download the displayed manifest and assignment files when needed; the server checks the exact displayed subject so a newer revision cannot silently replace its export.

## 3. Review evidence and record a decision

Open **Product evidence** to inspect permitted factual wording, qualifications, source review dates and the active evidence registry. The source pack is manually reviewed; the interface does not monitor the live product page.

Return to **Review & approval**. Read the exact audience, copy and cost, then approve or request changes with a reason. The dialog binds the proposal displayed when it opened. A stale dialog is rejected by the server. Generated copy remains a proposal even if its semantic screen passed.

Approval authorizes only a local simulated handoff. A runtime checkpoint acknowledgement is a different operation and grants no approval authority.

For grounded model copy, **Revise copy** opens feedback tied to the displayed subject and selected variant. Enable generation permission and submit the request. The agent preserves the audience, budget, assignments and product wording, then generates and screens the chosen hook. It records the original subject as needing changes and presents a new unapproved subject. Inspect it before approving. Offline fixture copy cannot use this revision path.

If a revision is **blocked**, inspect its recovery guidance. Restore the server-side key or original model settings to let the same saved request continue. Expired evidence requires reviewed current evidence and a new campaign. Reloading preserves the blocker; submitting duplicate feedback does not repair it. An uncertain outcome retains its separate warning about possible processing and charges.

## 4. Exercise an approval invalidation

Before accepting the job, suppress a selected mailing business and record a reason. The current approval becomes invalid. Choose **Rebuild draft**, inspect the revised audience and cost, then record a fresh decision. Rebuild preserves the copy; replacing copy or expired grounded evidence requires a new generated draft through the review/CLI workflow described in [review reference](reviews.md).

Evidence and policy changes, expiry, reviewer changes, rejection and revocation can also invalidate authority. Refreshing the page or replaying an old command does not restore it. This is the important distinction between a historical decision and current permission to act.

## 5. Simulate handoff

In chat, choose **Simulate agency handoff** after a valid approval, inspect the bound subject and approval in the confirmation, then confirm. The full campaign workspace also retains its handoff control. The backend checks the proposal, evidence, current suppression state and reviewer authority in the acceptance transaction. It records one simulated acceptance with its audit event and receipt.

The chat shows the saved receipt and downloads for the exact accepted campaign. If a response is lost, reload and choose **Check saved handoff** to reuse the original request. A dismissed reminder does not cancel or undo an acceptance.

Nothing is printed or sent. Repeating the command observes its original receipt rather than creating another job. After acceptance, the case is historical and cannot acquire a new proposal or decision. A revocation can record withdrawn authority but cannot retract that accepted simulation.

## 6. Observe and finalize outcomes

In chat after acceptance, open **Synthetic campaign learning**, choose **Open outcome window** and confirm the bound acceptance. The **Learning** workspace retains the same controls. Simulating early responses imports positives but does not update beliefs. Confirming **Close window & learn** in chat closes the simulated 28-day window, imports explicit results for the complete assigned population and requests finalization. Time is advanced inside the sandbox; the demo does not wait 28 real days.

Finalization requires maturity, completeness and valid assignment identities. A missing row is unknown, not an implied non-response. The learning view in chat displays exact counts, posterior estimates and uncertainty for each segment/arm. If a response is lost, reload and choose **Check saved learning request** to reuse the original action and cohort. Results deliberately favor one fixture variant to demonstrate recommendations; they are not customer performance measurements.

## 7. Propose another experiment

In chat, choose **Propose follow-up experiment** after finalization. Inspect the frozen learning, budget, hypothesis and independent population. Choose offline fixtures or explicitly permit bounded model generation. Inspect the resulting new campaign and record a fresh approval. Reload exposes an existing child through **Inspect or resume follow-up**; an uncertain provider result must be investigated before another generation.

The chat demonstration expands to a labeled 2,000-record synthetic inventory while preserving and excluding previously allocated business identities. Exhausted or stale populations block preparation. A later chat edit does not change a saved follow-up proposal; use the displayed source budget when deciding whether to prepare it.

The manual **Prepare a next experiment** control retains scoped mature memory in the same sandbox while creating a separate campaign proposal. Model mode freezes that memory alongside editorial guidance. Approval never transfers. The current repeated-business rule prevents opening a second learning cohort over the same population; this path demonstrates memory reuse rather than a production repeated-exposure experiment.

Inspect **Activity log** for committed events and historical receipts. A read-only export or saved report can become stale and does not authorize an operation.

## When an operation stops

| Situation | Operator response |
| --- | --- |
| Stale subject or invalid approval | Reload current state, inspect the change, rebuild or replace where appropriate and obtain a fresh decision |
| Expired product evidence | Manually verify sources and activate an updated pack; regenerate grounded copy when required |
| Server restarted | Reload to obtain the new local browser token |
| Network interruption or server error after a command | Retry the same action in the same browser session so its pending request identity is retained; inspect the current state and receipt |
| Incomplete model preparation | Resume the saved campaign with the pinned configuration; an uncertain provider call remains fenced and needs investigation |
| Conflicting, incomplete or repeated outcome data | Inspect cohort membership and explicit results; the prototype does not support correcting finalized outcomes or repeated exposures |

Do not bypass a failure by changing a clock, editing the database or treating a previous receipt as current permission. For CLI commands and exact invalidation conditions, use the [review](reviews.md), [learning](learning.md) and [model](model-integration.md) references.

## Choosing a source dataset in chat

After the agent prepares a complete brief, choose the synthetic dataset version to use. Each candidate shows its population, source date and review window. **Inspect dataset** reveals the manifest and checksum. A future-dated or expired version is unavailable for confirmation. If no dataset covers the proposed segments, revise the brief or ask the workspace owner to publish a suitable source.

Confirmation resumes preparation using those saved records. **Inspect confirmed source** shows the exact selection after reload. You still review and approve the complete campaign separately. To choose another dataset, send a new message and confirm a new proposal. Existing approval does not carry forward.

## Asking about current work

After your first request, ask `status?`, `Why did you choose this audience?`, `Why were these businesses excluded?` or `Explain validation`. These shortcuts read saved evidence without a model call and leave the brief, audience selection and approval intact. Other follow-ups may use one model-routing call. Answers include their observation time; **Inspect follow-up** shows the evidence and frozen guidance.

To amend the brief, describe the change and review **Apply brief change** before confirming. Confirmation saves a new brief revision and authorizes planning for that change. It stops obsolete preparation; the new campaign still needs source confirmation and its own review. Set model-copy permission before sending the follow-up if you want to allow it for the proposed change. Approval and simulated handoff continue through their existing exact-campaign controls.

If the agent asks whether to explain or change a campaign, your short reply retains the earlier request. Review all carried requests and agent responses in the confirmation before applying it. The displayed user texts enter the brief in order, so the final revision can advance by more than one. Earlier model-copy permission does not override the permission saved with your final reply.

For a grounded model campaign, ask `Make variant B more direct. Keep variant A and the audience unchanged.` Check the selected variant and feedback, then give separate five-call permission through **Generate copy revision**. If the target is unclear, answer with A/B and the segment name. A copy edit does not change the brief or audience selection. **Review revised copy** opens the resulting new subject for fresh approval. See [conversational copy revision](conversational-copy-revision.md) for scope and recovery.

## Model usage and stopping work

Chat shows a shared 48-call allowance across planning, routing, campaign copy, revisions and descendant experiments. Each operation still needs its existing consent and smaller limit. Use **Stop work** to stop the displayed brief and pending work. An already-dispatched request may still return or incur a charge. **Inspect model usage** shows recorded and uncertain outcomes and incomplete provider-reported costs. Send a new brief to start new work without resetting the allowance. Stopping preserves existing history and does not withdraw approval or restore a decision rejected for revision. See [execution controls](execution-controls.md).

Stopping after a campaign reaches its review checkpoint preserves that completed draft, even if its review case was not yet opened. It becomes available for unapproved review without more model calls. Manual next experiments share their parent conversation's allowance and stop fence.

If an older campaign has unresolved ancestry, model calls pause and remaining allowance is shown as unknown. **Inspect model usage** lists operator recovery commands, run IDs and organizations. Restore its original workspace relationship. An enabled local operator can reconcile an independent run only when its journal binding predates the organization's first run; unverified pre-identity ancestry stays paused. See [execution controls](execution-controls.md#reconcile-a-genuinely-independent-legacy-cli-run) for exact commands and fingerprint requirements. Reload after reconciliation; a numeric allowance returns once all uncertain ancestry is resolved. A blocked checkpoint shows recovery guidance without preventing other conversations from working. Restoring the required local operator or storage lets the saved review recovery continue without generating copy again.

## Development: verified admission cutover

Issue 33 has an opt-in, paused admission path. Normal startup keeps the current
compatibility workflow. Use a separate development data directory to inspect
verified admissions without activating generation:

```bash
PYTHONPATH=src python3 -m acquisition.workspace_server \
  --root .local/verified-workspace --port 8783 --verified-admissions
```

The server selects the store format after obtaining its existing root lock.
Chat requests save verified tasks and show a paused explanation. Model settings
and generation permission are still required, but paused admission loads no
provider key or client. Nothing proceeds to a new draft or approval through
this path yet.

For a standalone application database:

```bash
PYTHONPATH=src python3 -m acquisition --db .local/verified.sqlite admission-cutover
PYTHONPATH=src python3 -m acquisition --db .local/verified.sqlite create --request-id example
PYTHONPATH=src python3 -m acquisition --db .local/verified.sqlite work
```

The worker reports zero ticks because execution remains paused. `status --run`
shows the saved admission and binding status. `--verified-admissions` can also
select this format on a creation command; `--parent-run` supplies the exact
verified parent when creating a descendant. A raw `--campaign-id` reference
cannot replace verified parent ownership.

Selection persists in the application database and cannot be downgraded by
omitting the option later. An existing store must have no running task,
reserved provider call or partially admitted legacy plan. Reconcile the original
work before retrying selection. Legacy records remain inspectable and paused;
selection does not certify their execution authority. Do not use file deletion
or a version change to bypass this boundary. Execution activation and supported
restore procedures remain separate work. See the [authority decision](execution-authority-decision.md).


After admission cutover, an exact replay of a pre-cutover campaign or planning
command returns its original run for inspection. It does not certify that run,
resume it or create new authority records. Restore the original input values
and model settings when inspecting it through the creation command. Historical
planning requests can be inspected after later chat messages. New or changed
requests still require verified admission, and execution remains paused.


### Answering a budget question

If you give alternative totals or a relative change, the agent asks you to state one absolute GBP total. For example, reply "Use GBP 400 as the total budget." The agent does not choose a budget for you. Your reply creates a new brief revision; earlier questions remain in the conversation history.

Keep model-copy permission explicit for that request. Reloading after a lost response retains the saved reply or preparation, so retry the displayed pending command rather than sending a duplicate message. Review the resulting audience, copy and exact budget before any approval. Approval and simulated acceptance remain separate actions.
