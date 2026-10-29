import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

async function fakeWorkspace(scenario, run) {
  const root = await mkdtemp(join(tmpdir(), "acquisition-continuation-"));
  const script = `
import sys, time
from pathlib import Path
from unittest.mock import patch
from acquisition.workspace import Workspace
from acquisition.workspace_server import WorkspaceServer
from acquisition.reasoning import ModelError
from test_preparations import CombinedModel
from test_conversations import proposal
scenario = sys.argv[2]
result = proposal(outcome='clarification', question='What total GBP budget should I use?', budget_pence=None, segments=[]) if scenario == 'clarification' else proposal(copy_mode='model')
model = CombinedModel(result)
original = model.complete
class Gateway:
    def complete(self, request):
        time.sleep(0.5)
        name = request['tools'][0]['function']['name']
        if scenario in {'changed-uncertain', 'legacy-stale-uncertain'} and name == 'submit_campaign_brief':
            w.message_conversation(w.conversations()['conversations'][0]['id'], 'edit', 1, 'Use £300 instead.')
            raise ModelError('provider_request_failed')
        if scenario in {'uncertain', 'reserved'} and name != 'submit_campaign_brief':
            if scenario in {'reserved', 'legacy-stale-uncertain'}:
                raise KeyboardInterrupt()
            raise ModelError('provider_request_failed')
        return original(request)
patch('acquisition.workspace.openrouter_key', return_value='fixture').start()
patch('acquisition.workspace.OpenRouter', return_value=Gateway()).start()
w = Workspace(Path(sys.argv[1]), real_clock=lambda: 1792972800.0)
if scenario in {'reserved', 'legacy-stale-uncertain'}:
    c = w.create_conversation('new', 'Interrupted generation')['id']
    w.message_conversation(c, 'message', 0, 'Prepare a £600 contractor campaign with model copy.')
    w.start_preparation(c, 'prepare', 1, False, True)
    try:
        [w.advance_preparations() for _ in range(4)]
    except KeyboardInterrupt:
        pass
    if scenario == 'legacy-stale-uncertain':
        row = w.preparations.store.listing('local-conversations')[0]
        w.preparations.store.update('local-conversations', row, 'stale', 'The brief changed.')
    w = Workspace(Path(sys.argv[1]), real_clock=lambda: 1792972800.0)
server = WorkspaceServer(0, w, Path('frontend/dist'))
print('http://127.0.0.1:' + str(server.server_port), flush=True)
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
      let output = "",
        errors = "";
      const timer = setTimeout(
        () => reject(new Error("Fixture did not start: " + errors)),
        10000,
      );
      child.stderr.on("data", (data) => {
        errors += data.toString();
      });
      child.stdout.on("data", (data) => {
        output += data.toString();
        const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
        if (match) {
          clearTimeout(timer);
          resolve(match[0]);
        }
      });
      child.once("error", (error) => {
        clearTimeout(timer);
        reject(error);
      });
      child.once("exit", () => {
        clearTimeout(timer);
        reject(new Error(errors));
      });
    });
    await run(url);
  } finally {
    child.kill("SIGTERM");
    await exited;
    await rm(root, { recursive: true, force: true });
  }
}

async function submit(page, consent = true) {
  await page
    .getByLabel("Message Direct Acquisition")
    .fill("Prepare a £600 contractor campaign with model copy.");
  if (consent)
    await page.getByLabel("Allow model copy for this request").check();
  await page
    .getByRole("button", { name: "Send to agent", exact: true })
    .click();
}

test("one authorized submission continues after reload to an unapproved review", async ({
  page,
}) => {
  await fakeWorkspace("success", async (url) => {
    const posts = [],
      errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => {
      if (request.method() === "POST")
        posts.push(new URL(request.url()).pathname);
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(url);
    await submit(page);
    await expect(
      page.getByRole("region", { name: "Campaign preparation progress" }),
    ).toBeVisible();
    await page.reload();
    const copyStep = page
      .locator(".preparation-steps li")
      .filter({ hasText: "Generate and screen audience copy" });
    await expect(
      copyStep.getByText("In progress", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Generation outcome is uncertain", { exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Review campaign", exact: false }),
    ).toBeVisible();
    await expect(
      page.getByText("Ready for your review", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Campaign 1", exact: true }),
    ).toBeVisible();
    expect(posts.filter((path) => path.endsWith("/preparations"))).toHaveLength(
      1,
    );
    expect(
      posts.some((path) => /\/(plan|draft|approve|handoff)$/.test(path)),
    ).toBe(false);
    await page.screenshot({
      path: "../.local/continuous-preparation-desktop.png",
      fullPage: true,
    });
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(await page.evaluate(() => document.documentElement.clientWidth));
    }
    await page.screenshot({
      path: "../.local/continuous-preparation-mobile.png",
      fullPage: true,
    });
    await page.getByRole("button", { name: /Review campaign/ }).click();
    await expect(page.getByText("Review & approval")).toBeVisible();
    await expect(
      page.getByText("Pending", { exact: true }).first(),
    ).toBeVisible();
    expect(errors).toEqual([]);
  });
});

test("a lost admission acknowledgement reconciles saved progress without another request", async ({
  page,
}) => {
  await fakeWorkspace("success", async (url) => {
    let admissions = 0;
    await page.route("**/api/conversations/*/preparations", async (route) => {
      admissions += 1;
      await route.fetch();
      await route.abort("failed");
    });
    await page.goto(url);
    await submit(page);
    await expect(
      page.getByRole("region", { name: "Campaign preparation progress" }),
    ).toBeVisible();
    await page.reload();
    await expect(
      page.getByRole("button", { name: /Review campaign/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Resume preparation", exact: true }),
    ).toHaveCount(0);
    expect(admissions).toBe(1);
    await expect(page.locator(".conversation-user")).toHaveCount(1);
  });
});

for (const scenario of [
  "clarification",
  "no-consent",
  "uncertain",
  "reserved",
  "changed-uncertain",
  "legacy-stale-uncertain",
]) {
  test(`continuous preparation surfaces ${scenario} without repeated generation`, async ({
    page,
  }) => {
    await fakeWorkspace(scenario, async (url) => {
      await page.goto(url);
      if (["reserved", "legacy-stale-uncertain"].includes(scenario)) {
        await page
          .getByRole("button", { name: "Interrupted generation", exact: true })
          .click();
      } else await submit(page, scenario !== "no-consent");
      const region = page.getByRole("region", {
        name: "Campaign preparation progress",
      });
      if (scenario === "clarification") {
        await expect(
          region.getByText("Your input is needed", { exact: true }),
        ).toBeVisible();
        await expect(
          page.getByText("What total GBP budget should I use?", {
            exact: true,
          }),
        ).toBeVisible();
      } else if (scenario === "no-consent") {
        await expect(
          region.getByText("Permission needed for model copy", { exact: true }),
        ).toBeVisible();
        await expect(
          region.getByText(/Enable model copy and send a new message/),
        ).toBeVisible();
      } else {
        await expect(
          region.getByText("Provider outcome is uncertain", { exact: true }),
        ).toBeVisible();
        await expect(
          region.getByText(/may have processed and charged/),
        ).toBeVisible();
        if (
          ["changed-uncertain", "legacy-stale-uncertain"].includes(scenario)
        ) {
          await expect(
            region.getByText("Earlier brief", { exact: true }),
          ).toBeVisible();
          await expect(
            region.getByText(
              "This brief has changed. Its preparation will not continue.",
              { exact: true },
            ),
          ).toBeVisible();
          await region
            .getByText("Inspect preparation", { exact: true })
            .click();
          await expect(region.getByText(/Unresolved call:/)).toBeVisible();
          await expect(
            region.getByText("Provider: provider_request_failed", {
              exact: true,
            }),
          ).toBeVisible();
        }
        await page.reload();
        await expect(
          region.getByText("Provider outcome is uncertain", { exact: true }),
        ).toBeVisible();
      }
      await expect(
        page.getByRole("button", {
          name: /Review campaign|Generate campaign copy|Resume campaign preparation/,
        }),
      ).toHaveCount(0);
      await expect(page.getByLabel("Message Direct Acquisition")).toBeEnabled();
    });
  });
}

test("lost message acknowledgement cannot move copy consent to an intervening revision", async ({
  page,
}) => {
  await fakeWorkspace("success", async (url) => {
    const admissions = [],
      attempts = [];
    let dropped = false;
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        request.url().endsWith("/preparations")
      )
        admissions.push(request.postDataJSON());
    });
    await page.route("**/api/conversations/*/messages", async (route) => {
      attempts.push(route.request().postDataJSON());
      if (dropped) return route.continue();
      dropped = true;
      const saved = await (await route.fetch()).json();
      expect(saved.message_receipt.revision).toBe(1);
      const changed = await route.fetch({
        postData: JSON.stringify({
          request_id: "intervening-client",
          expected_revision: 1,
          content:
            "Prepare a £1200 inventory campaign with model copy instead.",
        }),
      });
      expect(changed.ok()).toBe(true);
      await route.abort("failed");
    });
    await page.goto(url);
    await submit(page, true);
    await expect(
      page.getByRole("button", { name: "Retry saving message", exact: true }),
    ).toBeEnabled();
    await page.reload();
    await expect(
      page.getByRole("button", { name: "Retry saving message", exact: true }),
    ).toBeEnabled();
    await page
      .getByRole("button", { name: "Retry saving message", exact: true })
      .click();
    await expect(
      page.getByText(/Your message was saved, but the brief has since changed/),
    ).toBeVisible();
    expect(attempts).toHaveLength(2);
    expect(attempts[0]).toEqual(attempts[1]);
    expect(admissions).toEqual([]);
    await expect(page.locator(".conversation-user")).toHaveCount(2);
    await expect(
      page.getByLabel("Allow model copy for this request"),
    ).not.toBeChecked();
    await expect(page.getByLabel("Message Direct Acquisition")).toBeEnabled();
    await expect(
      page.getByRole("button", {
        name: /Review campaign|Generate campaign copy/,
      }),
    ).toHaveCount(0);
    const conversationId = await page.evaluate(() =>
      localStorage.getItem("conversation-selected"),
    );
    const state = await page.evaluate(async (id) => {
      const token = document.querySelector(
        'meta[name="workspace-token"]',
      ).content;
      return (
        await fetch(`/api/conversations/${id}`, {
          headers: { "X-Workspace-Token": token },
        })
      ).json();
    }, conversationId);
    expect(state.revision).toBe(2);
    expect(state.current_plan).toBeNull();
    expect(state.preparations).toEqual([]);
  });
});
