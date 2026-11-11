import { test, expect } from "@playwright/test";
import { execFileSync, spawn } from "node:child_process";
import { access, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

async function workspace(scenario, run) {
  const root = await mkdtemp(join(tmpdir(), "acquisition-chat-review-"));
  const script = `
import sys, time
from pathlib import Path
from unittest.mock import patch
from acquisition.workspace import Workspace
from acquisition.workspace_server import WorkspaceServer
from acquisition.reasoning import ModelError
from test_copy_revisions import RevisionModel
from test_model_copy import reply
from acquisition.conversations import FIXTURE_MESSAGE
model=RevisionModel()
original=model.complete
class Gateway:
    def complete(self, request):
        if sys.argv[2] == 'partial-delivery' and request['tools'][0]['function']['name'] == 'propose_conversation_action':
            return reply('propose_conversation_action',{'action':'revise_copy'})
        if len(model.copy.requests) >= 3 and request['tools'][0]['function']['name'] != 'submit_campaign_brief':
            time.sleep(0.3)
            if sys.argv[2] == 'timeout': raise ModelError('provider_request_failed')
            if sys.argv[2] == 'recover-key':
                (Path(sys.argv[1])/'provider-started').touch()
                deadline=time.monotonic()+15
                while not (Path(sys.argv[1])/'release-provider').exists():
                    if time.monotonic() >= deadline: raise ModelError('provider_request_failed')
                    time.sleep(0.01)
        return original(request)
patch('acquisition.workspace.openrouter_key', return_value='fake').start()
patch('acquisition.workspace.OpenRouter', return_value=Gateway()).start()
w=Workspace(sys.argv[1], real_clock=lambda:1792972800.0)
c=w.create_conversation('c','Campaign for copy review')['id']
offline=sys.argv[2].startswith('handoff')
w.message_conversation(c,'m',0,FIXTURE_MESSAGE if offline else 'Prepare a £600 contractor campaign with model copy.')
w.start_preparation(c,'p',1,offline,not offline)
[w.advance_preparations() for _ in range(6)]
if sys.argv[2] == 'partial-delivery':
    sid=w.conversation(c)['campaigns'][0]['session_id']
    review=w.view(sid)['review']
    subject=review['subject']['id']
    target=review['manifest']['creatives'][0]['id']
    w.comment_artifact(c,sid,subject,target,1,'Preserve this variant for inspection.','comment')
    w.route_followup(c,'route-revision',1,'Make contractors variant A more direct.',False)
    w.advance_actions()
    assert w.conversation(c)['actions'][0]['result']['copy_revision']['status']=='ready'
    approval=w.action(sid,'approve',{'request_id':'approve','subject_id':subject,'reason':'Reviewed the exact synthetic campaign.'})['review']['approval']['id']
    session=w._session(sid)
    w._app(session).reviews.store.handoff(session['organization'],session['case_id'],approval,'local-operator','partial',simulation='partial')
if sys.argv[2] in {'missing-key','recover-key'}:
    original_revision=w.request_copy_revision
    def restored_key(path):
        if sys.argv[2] == 'recover-key' and (Path(sys.argv[1])/'restore-key').exists(): return 'fake'
        raise ModelError('private-key-error-sentinel')
    def admit_then_remove_key(*args, **kwargs):
        with w.lock:
            result=original_revision(*args, **kwargs)
            patch('acquisition.workspace.openrouter_key', side_effect=restored_key).start()
            return result
    w.request_copy_revision=admit_then_remove_key
if sys.argv[2] == 'historical-dialog':
    row=w.preparations.store.listing('local-conversations')[0]
    w.preparations.store.update('local-conversations',row,'preparing',None)
    w.advance_preparations=w.advance_copy_revisions
if sys.argv[2] in {'handoff-recorded', 'handoff-upload'}:
    from acquisition.contracts import canonical, digest
    original_action = w.action
    def stage_recording(identity, action, payload):
        result = original_action(identity, action, payload)
        if action != 'open-learning' or result.get('command_replayed'):
            return result
        session = w._session(identity)
        app = w._app(session)
        scope = session['organization']
        cohort = app.learning.source.accepted(scope, session['case_id'])
        end = cohort['window_end']
        events = [{'event_id': 'synthetic_event_' + digest({'cohort_id': cohort['id'], 'business_id': member['business_id']}),
                   'outcome': member | {'response': False, 'observed_at': end}} for member in cohort['members']]
        report = {key: cohort[key] for key in ('organization', 'job_id', 'metric', 'window_start', 'window_end')}
        report |= {'schema': 'synthetic-provider-report/v1', 'mode': 'SYNTHETIC_ONLY', 'cohort_id': cohort['id'],
                   'report_id': 'recorded', 'watermark': end, 'final': True, 'page_count': 1,
                   'pages': [{'report_id': 'recorded', 'number': 1, 'events': events}]}
        path = Path(sys.argv[1]) / 'recorded.json'
        if sys.argv[2] == 'handoff-upload':
            # Two valid JSON recordings exceed typical session-storage capacity.
            path.write_text(canonical(report) + ' ' * (3 * 1024 * 1024))
            path.with_name('cumulative.json').write_text(canonical(report | {'report_id': 'cumulative',
                'pages': [report['pages'][0] | {'report_id': 'cumulative'}]}) + ' ' * (3 * 1024 * 1024))
            return w.view(identity)
        path.write_text(canonical(report))
        replay = path.with_name('cumulative.json')
        replay.write_text(canonical(report | {'report_id': 'cumulative',
            'pages': [report['pages'][0] | {'report_id': 'cumulative'}]}))
        app.learning.schedule_reports(scope, 'local-operator', 'schedule', cohort['id'], end, 3600, [path, replay])
        path.unlink()
        replay.unlink()
        return w.view(identity)
    w.action = stage_recording
server=WorkspaceServer(0,w,Path('frontend/dist'))
print('http://127.0.0.1:'+str(server.server_port),flush=True)
server.serve_forever()
`;
  const child = spawn("python3", ["-c", script, root, scenario], {
    cwd: fileURLToPath(new URL("../..", import.meta.url)),
    env: { ...process.env, PYTHONPATH: "src:tests" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const exited = new Promise((resolve) => child.once("exit", resolve));
  try {
    const url = await new Promise((resolve, reject) => {
      let stdout = "",
        stderr = "";
      const timer = setTimeout(
        () => reject(new Error(stderr || "Fixture timeout")),
        10000,
      );
      child.stderr.on("data", (data) => {
        stderr += data.toString();
      });
      child.stdout.on("data", (data) => {
        stdout += data.toString();
        const match = stdout.match(/http:\/\/127\.0\.0\.1:\d+/);
        if (match) {
          clearTimeout(timer);
          resolve(match[0]);
        }
      });
      child.once("exit", () => {
        clearTimeout(timer);
        reject(new Error(stderr));
      });
      child.once("error", (error) => {
        clearTimeout(timer);
        reject(error);
      });
    });
    await run(url, root);
  } finally {
    child.kill("SIGTERM");
    await exited;
    await rm(root, { recursive: true, force: true });
  }
}
async function openReview(page, url) {
  await page.goto(url);
  await page
    .getByRole("button", { name: "Campaign for copy review", exact: true })
    .click();
  await page.getByRole("button", { name: /Review campaign/ }).click();
  const region = page.getByRole("region", {
    name: "Campaign review in conversation",
  });
  await expect(region.getByText("Review & approval")).toBeVisible();
  return region;
}

test("writing preferences need confirmation, survive a lost response and retain correction and retirement history", async ({
  page,
}) => {
  await workspace("handoff", async (url) => {
    const region = await openReview(page, url);
    const sid = await selected(page);
    const initial = (await backend(page, `/api/sessions/${sid}`)).body;
    await region.getByRole("button", { name: "Comment in chat" }).click();
    await page
      .getByLabel("Message Direct Acquisition")
      .fill("Use a concrete opening.");
    await page.getByRole("button", { name: "Save copy comment" }).click();
    const comment = page.getByRole("region", {
      name: "Saved artifact comment",
    });
    await expect(comment).toHaveCount(1);
    const endpoint = await page.evaluate(() =>
      localStorage.getItem("conversation-selected"),
    );
    expect(
      (await backend(page, `/api/conversations/${endpoint}`)).body
        .writing_preferences,
    ).toEqual([]);
    await comment
      .getByRole("button", { name: "Remember as a writing preference" })
      .click();
    await page
      .getByLabel("Writing preference", { exact: true })
      .fill("Start with a specific business situation.");
    await expect(
      page.getByRole("button", {
        name: "Confirm writing preference",
        exact: true,
      }),
    ).toBeDisabled();
    await page
      .getByRole("button", { name: "Close writing preference" })
      .click();
    expect(
      (await backend(page, `/api/conversations/${endpoint}`)).body
        .writing_preferences,
    ).toEqual([]);
    await comment
      .getByRole("button", { name: "Remember as a writing preference" })
      .click();
    await page
      .getByLabel("Writing preference", { exact: true })
      .fill("Start with a specific business situation.");
    await page
      .getByLabel("Reason for this decision")
      .fill("Concrete examples are easier to review.");
    await page
      .getByRole("checkbox", { name: "Stock & inventory", exact: true })
      .check();
    await page
      .getByRole("checkbox", { name: "Projects & contractors", exact: true })
      .check();
    await page
      .getByLabel("Use this wording as guidance for the selected audiences")
      .check();
    await page.getByRole("dialog").evaluate((dialog) => {
      dialog.scrollTop = 0;
    });
    await page.screenshot({
      path: "../.local/writing-preference-desktop.png",
    });
    const attempts = [];
    let drop = true;
    await page.route(
      "**/api/conversations/*/writing-preferences",
      async (route) => {
        attempts.push(route.request().postDataJSON());
        if (drop) {
          drop = false;
          await route.fetch();
          await route.abort("failed");
        } else await route.continue();
      },
    );
    await page
      .getByRole("button", { name: "Confirm writing preference", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Retry saving preference" }),
    ).toBeVisible();
    await expect(
      page.getByLabel("Writing preference", { exact: true }),
    ).toBeDisabled();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(
      page.getByLabel("Writing preference", { exact: true }),
    ).toHaveValue("Start with a specific business situation.");
    await page.getByRole("button", { name: "Retry saving preference" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(attempts).toHaveLength(2);
    expect(attempts[0]).toEqual(attempts[1]);
    await expect(comment).toContainText("Writing preference active");
    await page.reload();
    await comment
      .getByRole("button", { name: "Correct writing preference" })
      .click();
    await expect(
      page.getByLabel(
        "Use this wording as guidance for the selected audiences",
      ),
    ).not.toBeChecked();
    await page
      .getByLabel("Writing preference", { exact: true })
      .fill("Keep the opening short and concrete.");
    await page
      .getByRole("checkbox", { name: "Projects & contractors", exact: true })
      .uncheck();
    await page
      .getByLabel("Reason for this decision")
      .fill("Narrow this to inventory campaigns.");
    await page
      .getByLabel("Use this wording as guidance for the selected audiences")
      .check();
    await page.getByRole("dialog").evaluate((dialog) => {
      dialog.scrollTop = 0;
    });
    await page.screenshot({
      path: "../.local/writing-preference-mobile.png",
    });
    await page
      .getByRole("button", { name: "Confirm writing preference", exact: true })
      .click();
    await expect(comment).toContainText("Version 2");
    await comment
      .getByText("Preference history and source", { exact: true })
      .click();
    await expect(comment).toContainText(
      "Start with a specific business situation.",
    );
    await expect(comment).toContainText(initial.review.subject.id);
    await comment
      .getByRole("button", { name: "Retire writing preference", exact: true })
      .click();
    await page
      .getByLabel("Reason for this decision")
      .fill("We no longer need this direction.");
    await page
      .getByLabel("Stop using this preference in future generation")
      .check();
    await page.getByRole("button", { name: "Confirm retirement" }).click();
    await page.reload();
    await expect(comment).toContainText("Writing preference retired");
    await expect(
      comment.getByRole("button", { name: "Correct writing preference" }),
    ).toHaveCount(0);
    const final = (await backend(page, `/api/sessions/${sid}`)).body;
    expect(final.review.subject).toEqual(initial.review.subject);
    expect(final.review.approval).toBeNull();
    expect(final.copy_revisions).toHaveLength(0);
    const stored = (await backend(page, `/api/conversations/${endpoint}`)).body;
    expect(stored.writing_preferences[0].history.map((v) => v.action)).toEqual([
      "confirm",
      "correct",
      "retire",
    ]);
    expect(stored.artifact_comments).toHaveLength(1);
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(await page.evaluate(() => document.documentElement.clientWidth));
    }
  });
});
async function feedback(page, region) {
  await region
    .getByRole("button", { name: "Revise copy", exact: true })
    .click();
  await page
    .getByLabel("Copy feedback", { exact: true })
    .fill("Make variant B more direct.");
  await expect(
    page.getByRole("button", { name: "Generate revision", exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel("Allow up to five model calls for this revision")
    .check();
}
async function backend(page, path, payload) {
  return page.evaluate(
    async ({ path, payload }) => {
      const token = document.querySelector(
        'meta[name="workspace-token"]',
      ).content;
      const response = await fetch(path, {
        method: payload ? "POST" : "GET",
        headers: {
          "X-Workspace-Token": token,
          ...(payload ? { "Content-Type": "application/json" } : {}),
        },
        body: payload ? JSON.stringify(payload) : undefined,
      });
      return { status: response.status, body: await response.json() };
    },
    { path, payload },
  );
}
async function selected(page) {
  const result = await backend(page, "/api/sessions");
  return result.body.sessions[0].id;
}
async function approve(
  page,
  region,
  reason = "Reviewed audience, copy and current evidence.",
) {
  await region
    .getByRole("button", { name: "Approve this revision", exact: true })
    .click();
  await page.getByLabel("Review reason").fill(reason);
  await page
    .getByRole("button", { name: "Record approval", exact: true })
    .click();
}

test("review views and history show partial delivery and close unavailable actions", async ({
  page,
}) => {
  await workspace("partial-delivery", async (url) => {
    const chat = await openReview(page, url);
    const sid = await selected(page);
    const { review } = (await backend(page, `/api/sessions/${sid}`)).body;
    expect(review.delivery.status).toBe("partially_accepted");
    expect(review.candidate_valid).toBe(true);
    expect(review.handoff).toBeNull();
    const { delivery } = review;
    const { conversations } = (await backend(page, "/api/conversations")).body;
    const progress = await backend(
      page,
      `/api/conversations/${conversations[0].id}/actions`,
      {
        request_id: "inspect-partial",
        expected_revision: 1,
        content: "status?",
        allow_model_copy: false,
      },
    );
    expect(progress.status).toBe(202);
    expect(progress.body.actions.at(-1).result.evidence).toMatchObject({
      status: "simulated_partially_accepted",
      delivery,
    });
    const assertPartial = async (surface) => {
      const outcome = surface.getByRole("region", {
        name: "Partial simulated delivery",
      });
      await expect(outcome).toBeVisible();
      await expect(outcome.locator("dt")).toHaveText([
        "Intended recipients",
        "Accepted recipients",
        "Rejected recipients",
        "No-mail controls",
      ]);
      await expect(outcome.locator("dd")).toHaveText(
        [
          delivery.intended_recipients,
          delivery.accepted_recipients,
          delivery.rejected_recipients,
          delivery.control_count,
        ].map((count) => count.toLocaleString()),
      );
      await expect(
        surface.getByRole("button", { name: "Approve this revision" }),
      ).toHaveCount(0);
      await expect(
        surface.getByRole("button", { name: "Request changes" }),
      ).toHaveCount(0);
      await expect(
        surface.getByRole("button", { name: "Revise copy" }),
      ).toHaveCount(0);
      await expect(
        surface.getByRole("button", { name: "Simulate agency handoff" }),
      ).toHaveCount(0);
    };
    await assertPartial(chat);
    await expect(
      page.getByRole("button", { name: "Request a copy revision" }),
    ).toBeDisabled();
    await expect(
      page.getByRole("button", { name: "Generate copy revision", exact: true }),
    ).toBeDisabled();
    await expect(
      page.getByText(
        "Partial simulated delivery closes this campaign to copy revisions.",
        { exact: true },
      ),
    ).toBeVisible();
    await chat.getByRole("button", { name: "Open campaign workspace" }).click();
    await assertPartial(page);
    await expect(
      page.getByText("Partially accepted", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Awaiting review", { exact: true }),
    ).toHaveCount(0);
    const committed = review.events.find(
      (event) => event.kind === "simulated_handoff_accepted",
    ).payload.delivery;
    expect(committed).toEqual(delivery);
    await page
      .getByRole("button", { name: "Activity log", exact: true })
      .click();
    const event = page.locator(".event").filter({
      has: page.getByRole("heading", {
        name: "Simulated handoff partially accepted",
        exact: true,
      }),
    });
    await expect(event).toBeVisible();
    await expect(event.locator("details")).toHaveJSProperty("open", false);
    await expect(
      event.getByText(
        `${committed.intended_recipients.toLocaleString()} intended · ${committed.accepted_recipients.toLocaleString()} accepted · ${committed.rejected_recipients.toLocaleString()} rejected · ${committed.control_count.toLocaleString()} no-mail controls`,
        { exact: true },
      ),
    ).toBeVisible();
  });
});

test("chat reviews, revises and approves the exact new subject on desktop and mobile", async ({
  page,
}) => {
  await workspace("success", async (url) => {
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width: 1440, height: 1000 });
    const region = await openReview(page, url),
      sid = await selected(page);
    const initial = (await backend(page, `/api/sessions/${sid}`)).body;
    const a = region.locator(".letter").filter({ hasText: "Variant A" });
    const beforeA = await a.locator(".letter-opening").textContent();
    await approve(page, region);
    await expect(
      region.getByText("Approval recorded", { exact: true }),
    ).toBeVisible();
    await expect(
      region.getByRole("button", { name: "Simulate agency handoff" }),
    ).toBeVisible();
    await feedback(page, region);
    const request = page.waitForRequest(
      (r) => r.method() === "POST" && r.url().endsWith("/copy-revisions"),
    );
    await page
      .getByRole("button", { name: "Generate revision", exact: true })
      .click();
    expect((await request).postDataJSON().expected_subject).toBe(
      initial.review.subject.id,
    );
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(
      region.getByText("Revised copy is ready for review", { exact: true }),
    ).toBeVisible();
    await expect(a.locator(".letter-opening")).toHaveText(beforeA);
    await region.getByLabel("Copy variant", { exact: true }).selectOption({
      label: "Projects & contractors · Variant B",
    });
    await expect(
      region.getByRole("heading", {
        name: "When might project invoices fall due?",
      }),
    ).toBeVisible();
    const revised = (await backend(page, `/api/sessions/${sid}`)).body;
    expect(revised.review.subject.id).not.toBe(initial.review.subject.id);
    expect(revised.review.subject.snapshot_id).toBe(
      initial.review.subject.snapshot_id,
    );
    expect(revised.review.manifest.variable_cost_pence).toBe(
      initial.review.manifest.variable_cost_pence,
    );
    expect(revised.review.approval_valid).toBe(false);
    await page.reload();
    await expect(
      region.getByRole("heading", {
        name: "When might project invoices fall due?",
      }),
    ).toBeVisible();
    await region.screenshot({ path: "../.local/chat-review-desktop.png" });
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(await page.evaluate(() => document.documentElement.clientWidth));
      for (const label of await region.locator(".review-facts dt").all()) {
        const bounds = await label.boundingBox();
        expect(bounds.width).toBeGreaterThanOrEqual(80);
        expect(bounds.height).toBeLessThan(40);
      }
    }
    await region.screenshot({ path: "../.local/chat-review-mobile.png" });
    await approve(
      page,
      region,
      "Reviewed the revised subject, unchanged audience and evidence.",
    );
    await expect(
      region.getByText("Approval recorded", { exact: true }),
    ).toBeVisible();
    const approved = (await backend(page, `/api/sessions/${sid}`)).body;
    expect(approved.review.approval.subject_id).toBe(revised.review.subject.id);
    expect(approved.review.handoff).toBeNull();
    expect(errors).toEqual([]);
  });
});

test("artifact selection survives reload and a variant comment replays once before confirmed revision", async ({
  page,
}) => {
  await workspace("success", async (url) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    const region = await openReview(page, url);
    const sid = await selected(page);
    const initial = (await backend(page, `/api/sessions/${sid}`)).body;
    const target = initial.review.manifest.creatives.find((c) => c.arm === "B");
    const variant = region.getByLabel("Copy variant", { exact: true });
    await variant.selectOption(target.id);
    await page.reload();
    await expect(variant).toHaveValue(target.id);
    await region.getByRole("tab", { name: "Audience", exact: true }).click();
    await expect(region.getByRole("tabpanel")).toContainText(
      "Audience selection",
    );
    await page.reload();
    await expect(
      region.getByRole("tab", { name: "Audience", exact: true }),
    ).toHaveAttribute("aria-selected", "true");
    await region.getByRole("tab", { name: "Creative copy" }).click();
    await expect(variant).toHaveValue(target.id);
    await page.screenshot({
      path: "../.local/artifact-pane-desktop.png",
      fullPage: true,
    });

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(
      page.getByRole("button", { name: "Artifacts", exact: true }),
    ).toBeVisible();
    await page.screenshot({
      path: "../.local/artifact-pane-mobile.png",
      fullPage: true,
    });
    await region.getByRole("button", { name: "Comment in chat" }).click();
    await expect(page.getByLabel("Message Direct Acquisition")).toBeFocused();
    await expect(
      page.getByRole("status").filter({ hasText: "Commenting on" }),
    ).toContainText("Variant B");
    await page
      .getByLabel("Message Direct Acquisition")
      .fill("Make the selected opening more direct.");
    const attempts = [];
    let drop = true;
    await page.route(
      "**/api/conversations/*/artifact-comments",
      async (route) => {
        attempts.push(route.request().postDataJSON());
        if (drop) {
          drop = false;
          await route.fetch();
          await route.abort("failed");
        } else await route.continue();
      },
    );
    await page.getByRole("button", { name: "Save copy comment" }).click();
    await expect(
      page.getByRole("button", { name: "Retry saving message" }),
    ).toBeVisible();
    await page.reload();
    await expect(page.getByLabel("Message Direct Acquisition")).toHaveValue(
      "Make the selected opening more direct.",
    );
    await page.getByRole("button", { name: "Retry saving message" }).click();
    await expect(
      page.getByRole("region", { name: "Saved artifact comment" }),
    ).toHaveCount(1);
    expect(attempts).toHaveLength(2);
    expect(attempts[0]).toEqual(attempts[1]);
    expect(attempts[0].target_id).toBe(target.id);
    expect(attempts[0].expected_subject).toBe(initial.review.subject.id);
    const saved = (await backend(page, `/api/sessions/${sid}`)).body;
    expect(saved.copy_revisions).toHaveLength(0);
    expect(saved.review.subject.id).toBe(initial.review.subject.id);
    expect(saved.review.approval).toBeNull();
    await page.getByRole("button", { name: "Request a copy revision" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByLabel("Copy feedback", { exact: true })).toHaveValue(
      "Make the selected opening more direct.",
    );
    await expect(
      page.getByRole("button", { name: "Generate revision", exact: true }),
    ).toBeDisabled();
    for (const close of ["button", "escape"]) {
      await page
        .getByLabel("Allow up to five model calls for this revision")
        .check();
      if (close === "button") {
        await page.getByRole("button", { name: "Close copy feedback" }).click();
      } else {
        await page.keyboard.press("Escape");
      }
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await page.getByRole("button", { name: "Chat", exact: true }).click();
      await page
        .getByRole("button", { name: "Request a copy revision" })
        .click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(
        page.getByLabel("Variant to revise", { exact: true }),
      ).toHaveValue(target.id);
      await expect(
        page.getByLabel("Copy feedback", { exact: true }),
      ).toHaveValue("Make the selected opening more direct.");
      await expect(
        page.getByLabel("Allow up to five model calls for this revision"),
      ).not.toBeChecked();
      await expect(
        page.getByRole("button", { name: "Generate revision", exact: true }),
      ).toBeDisabled();
      expect(
        (await backend(page, `/api/sessions/${sid}`)).body.copy_revisions,
      ).toHaveLength(0);
    }
    await page
      .getByLabel("Allow up to five model calls for this revision")
      .check();
    const request = page.waitForRequest(
      (r) => r.method() === "POST" && r.url().endsWith("/copy-revisions"),
    );
    await page
      .getByRole("button", { name: "Generate revision", exact: true })
      .click();
    const payload = (await request).postDataJSON();
    expect(payload.target_id).toBe(target.id);
    expect(payload.expected_subject).toBe(initial.review.subject.id);
    await expect(
      region.getByText("Revised copy is ready for review", { exact: true }),
    ).toBeVisible();
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(await page.evaluate(() => document.documentElement.clientWidth));
    }
    await page.getByRole("button", { name: "Chat", exact: true }).click();
    await page.reload();
    await expect(
      page.getByRole("region", { name: "Saved artifact comment" }),
    ).toContainText("Variant B");
    await page.screenshot({
      path: "../.local/artifact-chat-mobile.png",
      fullPage: true,
    });
  });
});

test("a stale fixture comment is rejected before saving and the composer can select the current artifact", async ({
  page,
}) => {
  await workspace("handoff", async (url) => {
    const region = await openReview(page, url);
    const sid = await selected(page);
    await region.getByRole("button", { name: "Comment in chat" }).click();
    await page
      .getByLabel("Message Direct Acquisition")
      .fill("Please check this exact opening.");
    const initial = (await backend(page, `/api/sessions/${sid}`)).body;
    const refreshed = await backend(page, `/api/sessions/${sid}/refresh`, {
      request_id: "advance-subject",
      subject_id: initial.review.subject.id,
    });
    expect(refreshed.status).toBe(200);
    await page.getByRole("button", { name: "Save copy comment" }).click();
    await expect(
      page.getByRole("alert").filter({ hasText: "newer review subject" }),
    ).toBeVisible();
    await expect(page.getByLabel("Message Direct Acquisition")).toBeEnabled();
    await page.getByRole("button", { name: "Remove reference" }).click();
    await region.getByRole("button", { name: "Refresh review" }).click();
    await region.getByRole("button", { name: "Comment in chat" }).click();
    await page
      .getByLabel("Message Direct Acquisition")
      .fill("This is the current fixture copy.");
    await page.getByRole("button", { name: "Save copy comment" }).click();
    await expect(
      page.getByRole("region", { name: "Saved artifact comment" }),
    ).toHaveCount(1);
    await expect(
      page.getByRole("button", { name: "Request a copy revision" }),
    ).toHaveCount(0);
    const saved = (await backend(page, `/api/sessions/${sid}`)).body;
    expect(saved.review.approval).toBeNull();
    expect(saved.copy_revisions).toHaveLength(0);
    expect(saved.review.subject.id).toBe(refreshed.body.review.subject.id);
  });
});

test("lost in-chat approval acknowledgement keeps the original request identity", async ({
  page,
}) => {
  await workspace("success", async (url) => {
    const attempts = [];
    let lost = false;
    await page.route("**/api/sessions/*/approve", async (route) => {
      attempts.push(route.request().postDataJSON());
      if (!lost) {
        lost = true;
        await route.fetch();
        await route.abort("failed");
      } else await route.continue();
    });
    const region = await openReview(page, url);
    await approve(page, region);
    await expect(page.getByRole("dialog")).toBeVisible();
    await page
      .getByRole("button", { name: "Record approval", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(attempts).toHaveLength(2);
    expect(attempts[0]).toEqual(attempts[1]);
    const state = (await backend(page, `/api/sessions/${await selected(page)}`))
      .body;
    expect(
      state.review.events.filter((e) => e.kind === "review_approve"),
    ).toHaveLength(1);
    await expect(
      region.getByText(
        "Existing decision receipt observed. Current campaign state refreshed.",
      ),
    ).toBeVisible();
  });
});

for (const kind of ["approval", "feedback"]) {
  test(`a stale ${kind} dialog cannot bind itself to a refreshed subject`, async ({
    page,
  }) => {
    await workspace("success", async (url) => {
      const region = await openReview(page, url),
        sid = await selected(page);
      const before = (await backend(page, `/api/sessions/${sid}`)).body;
      if (kind === "approval") {
        await region
          .getByRole("button", { name: "Approve this revision", exact: true })
          .click();
        await page
          .getByLabel("Review reason")
          .fill("Reviewed this original subject.");
      } else await feedback(page, region);
      const refreshed = await backend(page, `/api/sessions/${sid}/refresh`, {
        request_id: "other-client",
        subject_id: before.review.subject.id,
      });
      expect(refreshed.status).toBe(200);
      await page
        .getByRole("button", {
          name: kind === "approval" ? "Record approval" : "Generate revision",
          exact: true,
        })
        .click();
      await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
      await expect(
        page.getByRole("dialog").locator(".subject-preview code"),
      ).toHaveText(before.review.subject.id);
      const after = (await backend(page, `/api/sessions/${sid}`)).body;
      expect(after.review.subject.id).toBe(refreshed.body.review.subject.id);
      expect(after.review.approval_valid).toBe(false);
      expect(after.copy_revisions).toEqual([]);
    });
  });
}

test("an uncertain copy revision remains inspectable after reload without another generation", async ({
  page,
}) => {
  await workspace("timeout", async (url) => {
    const region = await openReview(page, url);
    await feedback(page, region);
    await page
      .getByRole("button", { name: "Generate revision", exact: true })
      .click();
    await expect(
      region.getByText("Revision outcome is uncertain", { exact: true }),
    ).toBeVisible();
    await expect(
      region.getByText(/may have processed and charged/),
    ).toBeVisible();
    await page.reload();
    await expect(
      region.getByText("Revision outcome is uncertain", { exact: true }),
    ).toBeVisible();
    await region.getByText("Inspect copy revision", { exact: true }).click();
    await expect(
      region.getByText("Provider: provider_request_failed", { exact: true }),
    ).toBeVisible();
    await expect(region.getByText(/Unresolved call:/)).toBeVisible();
    await expect(
      region.getByRole("button", { name: "Revise copy", exact: true }),
    ).toHaveCount(0);
  });
});

test("a missing revision key shows a persistent blocked state and recovery guidance", async ({
  page,
}) => {
  await workspace("missing-key", async (url) => {
    const region = await openReview(page, url);
    await feedback(page, region);
    await page
      .getByRole("button", { name: "Generate revision", exact: true })
      .click();
    await expect(
      region.getByText("Copy revision is blocked", { exact: true }),
    ).toBeVisible();
    await expect(
      region.getByText(/Restore the server-side OpenRouter key/).first(),
    ).toBeVisible();
    await page.reload();
    await expect(
      region.getByText("Copy revision is blocked", { exact: true }),
    ).toBeVisible();
    const state = (await backend(page, `/api/sessions/${await selected(page)}`))
      .body;
    expect(state.copy_revisions).toHaveLength(1);
    expect(state.copy_revisions[0].status).toBe("blocked");
    expect(state.copy_revisions[0].run_id).toBeNull();
    expect(state.copy_revisions[0].block.code).toBe(
      "configuration_unavailable",
    );
    expect(JSON.stringify(state)).not.toContain("private-key-error-sentinel");
    expect(state.review.approval_valid).toBe(false);
    await expect(
      region.getByRole("button", { name: "Revise copy", exact: true }),
    ).toHaveCount(0);
  });
});

test("restored configuration keeps polling through a delayed provider call to completion", async ({
  page,
}) => {
  await workspace("recover-key", async (url, root) => {
    const submissions = [];
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        request.url().endsWith("/copy-revisions")
      )
        submissions.push(request.postDataJSON());
    });
    const region = await openReview(page, url);
    await feedback(page, region);
    await page
      .getByRole("button", { name: "Generate revision", exact: true })
      .click();
    await expect(
      region.getByText("Copy revision is blocked", { exact: true }),
    ).toBeVisible();
    await writeFile(join(root, "restore-key"), "restored");
    try {
      await expect
        .poll(async () => {
          try {
            await access(join(root, "provider-started"));
            return true;
          } catch {
            return false;
          }
        })
        .toBe(true);
      // The provider stays gated until an actual poll renders running progress.
      await expect(
        region.getByText("Preparing copy revision", { exact: true }),
      ).toBeVisible();
      await expect(
        region.getByText("Revision outcome is uncertain", { exact: true }),
      ).toHaveCount(0);
      const state = (
        await backend(page, `/api/sessions/${await selected(page)}`)
      ).body;
      expect(state.copy_revisions[0].status).toBe("running");
      expect(state.copy_revisions[0].block).toBeNull();
      expect(
        state.copy_revisions[0].generation.unresolved_calls[0].status,
      ).toBe("reserved");
    } finally {
      await writeFile(join(root, "release-provider"), "released");
    }
    await expect(
      region.getByText("Revised copy is ready for review", { exact: true }),
    ).toBeVisible();
    await expect(
      region.getByText("Revision outcome is uncertain", { exact: true }),
    ).toHaveCount(0);
    expect(submissions).toHaveLength(1);
  });
});

test("a historical approval dialog disables submission but remains closable", async ({
  page,
}) => {
  await workspace("historical-dialog", async (url) => {
    const region = await openReview(page, url);
    await region
      .getByRole("button", { name: "Approve this revision", exact: true })
      .click();
    await page
      .getByLabel("Review reason")
      .fill("Reviewed this original campaign.");
    const id = await page.evaluate(() =>
      localStorage.getItem("conversation-selected"),
    );
    const edited = await backend(page, `/api/conversations/${id}/messages`, {
      request_id: "edit",
      expected_revision: 1,
      content: "Use £300 instead.",
    });
    expect(edited.status).toBe(200);
    await expect(
      page.getByRole("button", { name: "Record approval", exact: true }),
    ).toBeDisabled();
    await expect(
      page.getByRole("button", { name: "Close decision", exact: true }),
    ).toBeEnabled();
    await page
      .getByRole("button", { name: "Close decision", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });
});

async function handoffDialog(page, region) {
  await region
    .getByRole("button", { name: "Simulate agency handoff", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Confirm simulated handoff" }),
  ).toBeVisible();
}

test("offline chat confirms handoff, shows historical receipt and downloads exact accepted exports", async ({
  page,
}) => {
  await workspace("handoff", async (url) => {
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const region = await openReview(page, url),
      sid = await selected(page);
    await expect(
      region.getByRole("button", { name: "Simulate agency handoff" }),
    ).toHaveCount(0);
    await approve(page, region);
    await expect(
      region.getByText("Approval recorded", { exact: true }),
    ).toBeVisible();
    const before = (await backend(page, `/api/sessions/${sid}`)).body;
    await handoffDialog(page, region);
    await expect(
      page.getByRole("dialog").locator(".subject-preview"),
    ).toContainText(before.review.subject.id);
    await expect(
      page.getByRole("dialog").locator(".subject-preview"),
    ).toContainText(before.review.approval.id);
    expect(
      (await backend(page, `/api/sessions/${sid}`)).body.review.handoff,
    ).toBeNull();
    await page
      .getByRole("button", { name: "Confirm simulated handoff", exact: true })
      .click();
    await expect(
      region.getByRole("heading", { name: "Simulated handoff accepted" }),
    ).toBeVisible();
    const accepted = (await backend(page, `/api/sessions/${sid}`)).body;
    expect(accepted.review.handoff.subject_id).toBe(before.review.subject.id);
    expect(accepted.review.handoff.approval_id).toBe(before.review.approval.id);
    for (const [label, kind] of [
      ["acceptance receipt", "handoff"],
      ["manifest", "manifest"],
      ["mailing CSV", "mailing"],
      ["assignments CSV", "assignments"],
    ]) {
      const request = page.waitForRequest((r) =>
        r.url().includes(`/artifacts/${kind}?`),
      );
      const downloading = page.waitForEvent("download");
      await region
        .getByRole("button", { name: `Download ${label}`, exact: true })
        .click();
      expect(
        new URL((await request).url()).searchParams.get("subject_id"),
      ).toBe(before.review.subject.id);
      expect((await downloading).suggestedFilename()).toBe(
        kind + (["handoff", "manifest"].includes(kind) ? ".json" : ".csv"),
      );
    }
    await backend(
      page,
      `/api/conversations/${before.review.manifest.brief.conversation_id}/messages`,
      {
        request_id: "later-edit",
        expected_revision: 1,
        content: "Use a different budget now.",
      },
    );
    await page.reload();
    await expect(
      region.getByRole("heading", { name: "Simulated handoff accepted" }),
    ).toBeVisible();
    await expect(
      region.getByRole("button", { name: "Simulate agency handoff" }),
    ).toHaveCount(0);
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(await page.evaluate(() => document.documentElement.clientWidth));
    }
    await region.screenshot({ path: "../.local/chat-handoff-mobile.png" });
    expect(errors).toEqual([]);
  });
});

for (const committed of [false, true])
  test(`lost handoff response recovers after reload with original identity, committed=${committed}`, async ({
    page,
  }) => {
    await workspace("handoff", async (url) => {
      const attempts = [];
      await page.route("**/api/sessions/*/handoff", async (route) => {
        attempts.push(route.request().postDataJSON());
        if (attempts.length === 1) {
          if (committed) await route.fetch();
          await route.abort("failed");
        } else await route.continue();
      });
      const region = await openReview(page, url),
        sid = await selected(page);
      await approve(page, region);
      await handoffDialog(page, region);
      await page
        .getByRole("button", { name: "Confirm simulated handoff", exact: true })
        .click();
      await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
      await page.reload();
      await region
        .getByRole("button", { name: "Check saved handoff", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Check original handoff", exact: true })
        .click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(
        region.getByRole("heading", { name: "Simulated handoff accepted" }),
      ).toBeVisible();
      expect(attempts).toHaveLength(2);
      expect(attempts[1]).toEqual(attempts[0]);
      const state = (await backend(page, `/api/sessions/${sid}`)).body;
      expect(
        state.review.events.filter(
          (e) => e.kind === "simulated_handoff_accepted",
        ),
      ).toHaveLength(1);
    });
  });

for (const change of ["refresh", "revoke", "suppress", "message"])
  test(`open handoff confirmation cannot accept after ${change}`, async ({
    page,
  }) => {
    await workspace("handoff", async (url) => {
      const region = await openReview(page, url),
        sid = await selected(page);
      await approve(page, region);
      await expect(
        region.getByText("Approval recorded", { exact: true }),
      ).toBeVisible();
      const before = (await backend(page, `/api/sessions/${sid}`)).body;
      await handoffDialog(page, region);
      if (change === "message") {
        const c = await page.evaluate(() =>
          localStorage.getItem("conversation-selected"),
        );
        await backend(page, `/api/conversations/${c}/messages`, {
          request_id: "edit",
          expected_revision: 1,
          content: "Use £300 instead.",
        });
      } else {
        const fields =
          change === "refresh"
            ? { subject_id: before.review.subject.id }
            : change === "revoke"
              ? {
                  approval_id: before.review.approval.id,
                  reason: "Withdrawn before handoff.",
                }
              : {
                  business_id: before.audience.find((r) =>
                    ["A", "B"].includes(r.arm),
                  ).id,
                  reason: "Late suppression.",
                };
        expect(
          (
            await backend(page, `/api/sessions/${sid}/${change}`, {
              request_id: "other-client",
              ...fields,
            })
          ).status,
        ).toBe(200);
      }
      await page
        .getByRole("button", { name: "Confirm simulated handoff", exact: true })
        .click();
      await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
      await expect(
        page.getByRole("dialog").locator(".subject-preview"),
      ).toContainText(before.review.approval.id);
      const after = (await backend(page, `/api/sessions/${sid}`)).body;
      expect(after.review.handoff).toBeNull();
      expect(
        after.review.events.filter(
          (e) => e.kind === "simulated_handoff_accepted",
        ),
      ).toHaveLength(0);
      await page
        .getByRole("button", { name: "Close handoff confirmation" })
        .click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
    });
  });

async function acceptedLearning(page, url) {
  const region = await openReview(page, url);
  await approve(page, region);
  await handoffDialog(page, region);
  await page
    .getByRole("button", { name: "Confirm simulated handoff", exact: true })
    .click();
  const learning = page.getByRole("region", {
    name: "Campaign learning in conversation",
  });
  await expect(learning).toBeVisible();
  return learning;
}
async function learningStep(page, learning, label) {
  await learning.getByRole("button", { name: label, exact: true }).click();
  await expect(
    page.getByRole("dialog").locator(".subject-preview"),
  ).toContainText("fake_job_");
  await page
    .getByRole("button", {
      name: "Confirm synthetic learning step",
      exact: true,
    })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

test("offline conversational learning preserves unknown results then shows complete mature advisory counts", async ({
  page,
}) => {
  await workspace("handoff-learning", async (url) => {
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const learning = await acceptedLearning(page, url),
      sid = await selected(page);
    expect(
      (await backend(page, `/api/sessions/${sid}`)).body.learning,
    ).toBeNull();
    await learningStep(page, learning, "Open outcome window");
    const opened = (await backend(page, `/api/sessions/${sid}`)).body;
    await expect(
      page.getByRole("region", { name: "Campaign handoff" }),
    ).toHaveCount(1);
    await expect(learning).toHaveCount(1);
    expect(opened.learning.enrolled).toBe(
      opened.review.manifest.counts.mailed +
        opened.review.manifest.counts.holdout,
    );
    await learningStep(page, learning, "Simulate day 7 responses");
    await expect(
      learning.getByRole("heading", { name: "Beliefs are unchanged" }),
    ).toBeVisible();
    const early = (await backend(page, `/api/sessions/${sid}`)).body;
    expect(early.learning.missing).toBeGreaterThan(0);
    expect(early.learning.beliefs).toEqual([]);
    const c = await page.evaluate(() =>
      localStorage.getItem("conversation-selected"),
    );
    await backend(page, `/api/conversations/${c}/messages`, {
      request_id: "edit-after-accept",
      expected_revision: 1,
      content: "Prepare a different budget next time.",
    });
    await page.reload();
    await learningStep(page, learning, "Close window & learn");
    await expect(
      learning.getByText("Finalized", { exact: true }),
    ).toBeVisible();
    const final = (await backend(page, `/api/sessions/${sid}`)).body;
    expect(final.learning.missing).toBe(0);
    expect(final.learning.beliefs.reduce((sum, b) => sum + b.trials, 0)).toBe(
      final.learning.enrolled,
    );
    expect(final.learning.beliefs.map((b) => b.arm).sort()).toEqual([
      "A",
      "B",
      "no_mail",
    ]);
    expect(final.review.handoff).toEqual(opened.review.handoff);
    await expect(
      learning.getByText("No-mail control", { exact: true }),
    ).toBeVisible();
    await expect(
      learning.getByRole("button", { name: "Prepare a next experiment" }),
    ).toHaveCount(0);
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(await page.evaluate(() => document.documentElement.clientWidth));
    }
    await learning.screenshot({
      path: "../.local/conversation-learning-mobile.png",
    });
    await page.reload();
    await expect(
      learning.getByText("Finalized", { exact: true }),
    ).toBeVisible();
    expect((await backend(page, `/api/sessions/${sid}`)).body.learning).toEqual(
      final.learning,
    );
    expect(errors).toEqual([]);
  });
});

test("recorded monitoring advances the exact fixture check and leaves learning explicit", async ({
  page,
}) => {
  await workspace("handoff-recorded", async (url) => {
    const learning = await acceptedLearning(page, url);
    const sid = await selected(page);
    await learningStep(page, learning, "Open outcome window");
    const monitoring = learning.getByRole("region", {
      name: "Recorded report monitoring",
    });
    await expect(monitoring).toContainText("0 of 2 synthetic reports checked");
    await expect(monitoring).toContainText("Next check");
    await expect(
      learning.getByRole("button", { name: "Simulate day 7 responses" }),
    ).toHaveCount(0);
    await learningStep(page, monitoring, "Advance to next report check");
    await expect(monitoring).toContainText("2 of 2 synthetic reports checked");
    await expect(monitoring).toContainText("Reports verified through");
    const checked = (await backend(page, `/api/sessions/${sid}`)).body.learning;
    expect(checked.received).toBe(checked.enrolled);
    expect(checked.beliefs).toEqual([]);
    expect(
      checked.events
        .filter((event) => event.kind === "provider_report_imported")
        .map((event) => [event.payload.report_id, event.payload.added]),
    ).toEqual([
      ["recorded", checked.enrolled],
      ["cumulative", 0],
    ]);
    await learningStep(page, monitoring, "Finalize recorded learning");
    await expect(
      learning.getByText("Finalized", { exact: true }),
    ).toBeVisible();
    const final = (await backend(page, `/api/sessions/${sid}`)).body.learning;
    expect(final.finalization.observations).toBe(checked.enrolled);
    expect(final.finalization.successes).toBe(0);
  });
});

for (const action of ["open-learning", "observe", "finalize"])
  test(`lost ${action} response replays original learning identity after reload`, async ({
    page,
  }) => {
    await workspace("handoff-learning", async (url) => {
      const learning = await acceptedLearning(page, url),
        sid = await selected(page);
      if (action !== "open-learning")
        await learningStep(page, learning, "Open outcome window");
      const attempts = [];
      await page.route(`**/api/sessions/*/${action}`, async (route) => {
        attempts.push(route.request().postDataJSON());
        if (attempts.length === 1) {
          await route.fetch();
          await route.abort("failed");
        } else await route.continue();
      });
      const label = {
        "open-learning": "Open outcome window",
        observe: "Simulate day 7 responses",
        finalize: "Close window & learn",
      }[action];
      await learning.getByRole("button", { name: label, exact: true }).click();
      await page
        .getByRole("button", {
          name: "Confirm synthetic learning step",
          exact: true,
        })
        .click();
      await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
      const first = (await backend(page, `/api/sessions/${sid}`)).body.learning;
      await page.reload();
      await learning
        .getByRole("button", {
          name: "Check saved learning request",
          exact: true,
        })
        .click();
      await page
        .getByRole("button", {
          name: "Check original learning request",
          exact: true,
        })
        .click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      expect(attempts).toHaveLength(2);
      expect(attempts[1]).toEqual(attempts[0]);
      const replay = (await backend(page, `/api/sessions/${sid}`)).body
        .learning;
      expect(replay).toEqual(first);
      if (action === "finalize")
        expect(
          replay.events.filter((e) => e.kind === "cohort_finalized"),
        ).toHaveLength(1);
    });
  });

async function finalizedFollowup(page, url) {
  const learning = await acceptedLearning(page, url);
  const sid = await selected(page);
  await learningStep(page, learning, "Open outcome window");
  await learningStep(page, learning, "Close window & learn");
  const followup = page.getByRole("region", {
    name: "Next experiment in conversation",
  });
  await followup
    .getByRole("button", { name: "Propose follow-up experiment", exact: true })
    .click();
  await expect(
    followup.getByRole("heading", { name: "Follow-up proposal", exact: true }),
  ).toBeVisible();
  return { followup, sid };
}

test("finalized chat proposes a frozen disjoint next campaign requiring fresh approval", async ({
  page,
}) => {
  await workspace("handoff-followup", async (url) => {
    const { followup, sid } = await finalizedFollowup(page, url);
    const parent = (await backend(page, `/api/sessions/${sid}`)).body;
    const p = parent.followups[0];
    const hypothesis = p.hypotheses[0];
    expect(hypothesis.evidence_status).toBe("strong");
    const evidenceRegion = followup.getByRole("region", {
      name: /experiment hypothesis/,
    });
    await expect(evidenceRegion).toContainText(
      "Strong source comparison under the illustrative policy",
    );
    await expect(evidenceRegion).toContainText("Earlier lift may not repeat");
    await expect(evidenceRegion).toContainText("Synthetic source outcomes");
    await evidenceRegion.getByText(/Evidence and uncertainty for/).click();
    await expect(evidenceRegion).toContainText(p.source_cohort);
    await expect(evidenceRegion).toContainText(hypothesis.candidate.hook);
    await expect(evidenceRegion).toContainText("zero observed outcomes");
    await evidenceRegion
      .getByText(/Evidence and uncertainty for/)
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: "../.local/evidence-followup-desktop.png",
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await evidenceRegion
      .getByText(/Evidence and uncertainty for/)
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: "../.local/evidence-followup-mobile.png",
    });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBe(await page.evaluate(() => document.documentElement.clientWidth));
    await page.reload();
    expect(
      (await backend(page, `/api/sessions/${sid}`)).body.followups[0]
        .hypotheses,
    ).toEqual(p.hypotheses);
    await page.setViewportSize({ width: 1280, height: 800 });
    await expect(
      followup.getByRole("button", {
        name: "Generate grounded follow-up",
        exact: true,
      }),
    ).toBeDisabled();
    await followup
      .getByRole("button", { name: "Prepare offline follow-up", exact: true })
      .click();
    const child = followup.getByRole("region", {
      name: "Campaign review in conversation",
    });
    await expect(
      child.getByRole("button", { name: "Approve this revision", exact: true }),
    ).toBeVisible();
    const next = (await backend(page, "/api/sessions")).body.sessions.find(
      (s) => s.id !== sid,
    );
    const state = (await backend(page, `/api/sessions/${next.id}`)).body;
    expect(state.review.approval_valid).toBe(false);
    expect(state.review.subject.id).not.toBe(parent.review.subject.id);
    const old = new Set(
      parent.audience.filter((r) => r.arm !== "excluded").map((r) => r.id),
    );
    expect(
      state.audience
        .filter((r) => r.arm !== "excluded")
        .every((r) => !old.has(r.id)),
    ).toBe(true);
    expect((await backend(page, `/api/sessions/${sid}`)).body.learning).toEqual(
      parent.learning,
    );
    await approve(page, child, "Reviewed the distinct follow-up experiment.");
    await expect(
      child.getByText("Approval recorded", { exact: true }),
    ).toBeVisible();
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(await page.evaluate(() => document.documentElement.clientWidth));
    }
    await followup.screenshot({ path: "../.local/followup-mobile.png" });
    await page.reload();
    await followup
      .getByRole("button", { name: "Inspect or resume follow-up", exact: true })
      .click();
    await expect(
      child.getByText("Approval recorded", { exact: true }),
    ).toBeVisible();
    expect(
      (await backend(page, `/api/sessions/${sid}`)).body.followups[0].id,
    ).toBe(p.id);
  });
});

test("lost follow-up preparation response resumes original campaign after reload", async ({
  page,
}) => {
  await workspace("handoff-followup", async (url) => {
    const { followup, sid } = await finalizedFollowup(page, url);
    const attempts = [];
    await page.route("**/api/sessions/*/followup-prepare", async (route) => {
      attempts.push(route.request().postDataJSON());
      if (attempts.length === 1) {
        await route.fetch();
        await route.abort("failed");
      } else await route.continue();
    });
    await followup
      .getByRole("button", { name: "Prepare offline follow-up", exact: true })
      .click();
    await expect(followup.getByRole("alert")).toBeVisible();
    await page.reload();
    await followup
      .getByRole("button", { name: "Inspect or resume follow-up", exact: true })
      .click();
    await expect(
      followup.getByRole("region", { name: "Campaign review in conversation" }),
    ).toBeVisible();
    const listing = (await backend(page, "/api/sessions")).body.sessions;
    expect(listing).toHaveLength(2);
    expect(
      (await backend(page, `/api/sessions/${sid}`)).body.followups,
    ).toHaveLength(1);
    expect(attempts).toHaveLength(1); // Read the already committed child, without resubmission.
  });
});

test("generation consent is separate for each frozen follow-up proposal", async ({
  page,
}) => {
  await workspace("handoff-followup", async (url) => {
    const { followup, sid } = await finalizedFollowup(page, url);
    await followup.getByRole("checkbox").check();
    const state = (await backend(page, `/api/sessions/${sid}`)).body;
    expect(
      (
        await backend(page, `/api/sessions/${sid}/suppress`, {
          request_id: "new-population",
          business_id: state.followups[0].population[0],
          reason: "Change the next population.",
        })
      ).status,
    ).toBe(200);
    await followup
      .getByRole("button", {
        name: "Propose follow-up experiment",
        exact: true,
      })
      .click();
    const proposals = followup.locator(":scope > article");
    await expect(proposals).toHaveCount(2);
    await expect(proposals.nth(0).getByRole("checkbox")).toBeChecked();
    await expect(proposals.nth(1).getByRole("checkbox")).not.toBeChecked();
    await expect(
      proposals
        .nth(1)
        .getByRole("button", { name: "Generate grounded follow-up" }),
    ).toBeDisabled();
  });
});

test("requested scope is visible and unsupported facets never prepare a substitute campaign", async ({
  page,
}) => {
  await workspace("handoff", async (url) => {
    await page.goto(url);
    await page
      .getByRole("button", { name: "Campaign for copy review", exact: true })
      .click();
    const scope = page.getByLabel("Campaign scope", { exact: true });
    await expect(scope).toContainText(
      "iwoca Flexi-Loan · Postal direct mail · UK · Response experiment",
    );
    await expect(scope).toContainText("Supported defaults used for: product");
    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(scope).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBe(await page.evaluate(() => document.documentElement.clientWidth));
    for (const text of [
      "Prepare an email-only campaign for UK contractors with £437. Do not substitute postal mail.",
      "Prepare a postal contractor campaign in France with £437. Do not replace France with the UK.",
      "Use £437 for a personal residential mortgage campaign. Do not substitute a business loan.",
      "Use £437 to approve credit applications and guarantee a loan for UK contractors.",
    ]) {
      await page
        .getByRole("button", { name: "New conversation", exact: true })
        .click();
      await page.getByLabel("Message Direct Acquisition").fill(text);
      await page
        .getByRole("button", { name: "Send to agent", exact: true })
        .click();
      await expect(page.getByText(/Unsupported requested scope/)).toBeVisible();
      const cid = await page.evaluate(() =>
        localStorage.getItem("conversation-selected"),
      );
      const state = (await backend(page, `/api/conversations/${cid}`)).body;
      expect(state.current_plan.result.outcome).toBe("unsupported");
      expect(state.current_plan.result.requested_scope.status).toBe(
        "unsupported",
      );
      expect(state.execution.used).toBe(0);
      expect(state.campaigns).toHaveLength(0);
      await expect(
        page.getByRole("button", { name: /Review campaign/ }),
      ).toHaveCount(0);
    }
  });
});

for (const committed of [false, true]) {
  test(`monitoring uploads recover one schedule after a lost creation response, committed=${committed}`, async ({
    page,
  }) => {
    test.setTimeout(60000);
    await workspace("handoff-upload", async (url, root) => {
      const learning = await acceptedLearning(page, url);
      await learningStep(page, learning, "Open outcome window");
      const sid = await selected(page);
      const opened = (await backend(page, `/api/sessions/${sid}`)).body;
      const controls = learning.getByRole("region", {
        name: "Monitoring setup and controls",
      });
      if (!committed) await page.setViewportSize({ width: 390, height: 844 });
      await controls
        .getByLabel("Recorded synthetic reports", { exact: true })
        .setInputFiles([
          join(root, "recorded.json"),
          join(root, "cumulative.json"),
        ]);
      await controls
        .getByLabel("First report check, UTC", { exact: true })
        .fill(
          new Date(opened.learning.cohort.window_end * 1000)
            .toISOString()
            .slice(0, 16),
        );
      await controls
        .getByLabel("Check every, in minutes", { exact: true })
        .fill("15");
      const attempts = [];
      await page.route("**/api/sessions/*/monitoring-start", async (route) => {
        attempts.push(route.request().postDataJSON());
        if (attempts.length === 1) {
          if (committed) await route.fetch();
          await route.abort("failed");
        } else await route.continue();
      });
      await controls
        .getByRole("button", {
          name: "Review monitoring schedule",
          exact: true,
        })
        .click();
      const dialog = page.getByRole("dialog");
      await expect(dialog).toContainText(opened.learning.cohort.id);
      await expect(dialog).toContainText(opened.review.handoff.id);
      await dialog
        .getByRole("button", {
          name: "Confirm monitoring schedule",
          exact: true,
        })
        .click();
      await expect(
        controls.getByRole("button", {
          name: "Recover saved monitoring request",
          exact: true,
        }),
      ).toBeVisible();
      const beforeReload = (await backend(page, `/api/sessions/${sid}`)).body
        .learning.monitoring;
      if (committed) expect(beforeReload.revision).toBe(1);
      else {
        expect(beforeReload).toBeUndefined();
        await expect(
          learning.getByRole("button", {
            name: "Close window & learn",
            exact: true,
          }),
        ).toBeDisabled();
      }
      await page.reload();
      await controls
        .getByRole("button", {
          name: "Recover saved monitoring request",
          exact: true,
        })
        .click();
      await expect(controls).toContainText(
        "Current cadence 15 minutes. Schedule revision 1.",
      );
      expect(attempts).toHaveLength(2);
      expect(attempts[1]).toEqual(attempts[0]);
      const stored = JSON.parse(
        execFileSync(
          "python3",
          [
            "-c",
            `
import json, sqlite3, sys
with sqlite3.connect(sys.argv[1]) as db:
    print(json.dumps([db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
                      for table in ('report_monitoring', 'report_monitoring_sources', 'learning_outcomes')]))
`,
            join(root, "conversations.sqlite"),
          ],
          { encoding: "utf8" },
        ),
      );
      expect(stored).toEqual([1, 2, 0]);
      await controls
        .getByLabel("Check every, in minutes", { exact: true })
        .fill("30");
      await controls
        .getByRole("button", { name: "Save cadence", exact: true })
        .click();
      await expect(controls).toContainText(
        "Current cadence 30 minutes. Schedule revision 2.",
      );
      if (committed) {
        let lostPause = false;
        await page.route(
          "**/api/sessions/*/monitoring-update",
          async (route) => {
            if (
              !lostPause &&
              route.request().postDataJSON().status === "paused"
            ) {
              lostPause = true;
              await route.fetch();
              await route.abort("failed");
            } else await route.continue();
          },
        );
      }
      await controls
        .getByRole("button", { name: "Pause monitoring", exact: true })
        .click();
      if (committed) {
        await expect(
          controls.getByRole("button", {
            name: "Recover saved monitoring request",
            exact: true,
          }),
        ).toBeVisible();
        await page.reload();
        await controls
          .getByRole("button", {
            name: "Recover saved monitoring request",
            exact: true,
          })
          .click();
      }
      await expect(controls).toContainText("Schedule revision 3.");
      await page.reload();
      await expect(
        controls.getByRole("button", {
          name: "Resume monitoring",
          exact: true,
        }),
      ).toBeVisible();
      const paused = (await backend(page, `/api/sessions/${sid}`)).body
        .learning;
      expect(paused.monitoring.status).toBe("paused");
      expect(paused.received).toBe(0);
      await controls
        .getByRole("button", { name: "Resume monitoring", exact: true })
        .click();
      await expect(controls).toContainText("Schedule revision 4.");
      const resumed = (await backend(page, `/api/sessions/${sid}`)).body
        .learning;
      expect(resumed.monitoring.status).toBe("scheduled");
      expect(resumed.monitoring.interval_seconds).toBe(1800);
      expect(resumed.cohort.window_end).toBe(opened.learning.cohort.window_end);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
    });
  });
}

test("monitoring storage failure prevents upload dispatch", async ({
  page,
}) => {
  await workspace("handoff-upload", async (url, root) => {
    const learning = await acceptedLearning(page, url);
    await learningStep(page, learning, "Open outcome window");
    const controls = learning.getByRole("region", {
      name: "Monitoring setup and controls",
    });
    await controls
      .getByLabel("Recorded synthetic reports", { exact: true })
      .setInputFiles(join(root, "recorded.json"));
    await controls
      .getByRole("button", { name: "Review monitoring schedule", exact: true })
      .click();
    let dispatched = 0;
    await page.route("**/api/sessions/*/monitoring-start", async (route) => {
      dispatched += 1;
      await route.continue();
    });
    await page.evaluate(() => {
      IDBObjectStore.prototype.put = function () {
        throw new DOMException("fixture-quota-exceeded", "QuotaExceededError");
      };
    });
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Confirm monitoring schedule", exact: true })
      .click();
    await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
      "fixture-quota-exceeded",
    );
    expect(dispatched).toBe(0);
  });
});
