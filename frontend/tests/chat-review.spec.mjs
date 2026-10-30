import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
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
from acquisition.conversations import FIXTURE_MESSAGE
model=RevisionModel()
original=model.complete
class Gateway:
    def complete(self, request):
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
