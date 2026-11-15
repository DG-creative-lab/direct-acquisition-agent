import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

async function isolated(run, scenario = "default") {
  const root = await mkdtemp(join(tmpdir(), "acquisition-sequence-chat-"));
  const script = `
from acquisition.workspace import Workspace
from acquisition.workspace_server import WorkspaceServer
from pathlib import Path
import sys
w=Workspace(sys.argv[1],real_clock=lambda:1792972800. if sys.argv[2]=='postal-budget' else 1794700800.)
if sys.argv[2]=='return-postal':
 from unittest.mock import patch
 from test_preparations import CombinedModel
 from test_conversations import proposal
 model=CombinedModel(proposal())
 patch('acquisition.workspace.openrouter_key',return_value='fixture').start()
 patch('acquisition.workspace.OpenRouter',return_value=model).start()
 c=w.create_conversation('sequence','Return to postal')['id']
 w.message_conversation(c,'sequence-message',0,'Prepare an email sequence with a £100 budget.')
if sys.argv[2]=='postal-budget':
 from unittest.mock import patch
 from test_preparations import CombinedModel
 from test_conversations import proposal
 model=CombinedModel(proposal(budget_pence=40000))
 patch('acquisition.workspace.openrouter_key',return_value='fixture').start()
 patch('acquisition.workspace.OpenRouter',return_value=model).start()
 c=w.create_conversation('postal','Postal budget clarification')['id']
 w.message_conversation(c,'postal-message',0,'Prepare a UK postal response experiment for contractors with £437 or £683.')
 w.start_preparation(c,'postal-preparation',1,False,True)
 [w.advance_preparations() for _ in range(5)]
 assert w.conversation(c)['current_plan']['result']['budget_clarification']
 w=Workspace(sys.argv[1],real_clock=lambda:1794700800.)
s=WorkspaceServer(0,w,Path('frontend/dist'))
print('http://127.0.0.1:'+str(s.server_port),flush=True)
s.serve_forever()
`;
  const child = spawn("python3", ["-c", script, root, scenario], {
    cwd: fileURLToPath(new URL("../..", import.meta.url)),
    env: {
      ...process.env,
      PYTHONPATH: "src:tests",
      OPENROUTER_API_KEY: "offline-tests-must-not-use-live-credentials",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const exited = new Promise((resolve) => child.once("exit", resolve));
  try {
    const url = await new Promise((resolve, reject) => {
      let output = "",
        errors = "";
      const timer = setTimeout(
        () => reject(new Error("Sequence fixture did not start: " + errors)),
        15000,
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

test("email and call objective continues through exact approval without setup or repeated effects", async ({
  page,
}) => {
  test.setTimeout(240000);
  await isolated(async (url) => {
    const posts = [],
      errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => {
      if (request.method() === "POST") {
        posts.push(new URL(request.url()).pathname);
        if (request.url().endsWith("/sequence-messages")) {
          expect(request.headers().authorization).toBeUndefined();
          expect(request.headers()["x-openrouter-session"]).toBeUndefined();
        }
      }
    });
    await page.goto(url);
    await page
      .getByLabel("Message Direct Acquisition")
      .fill(
        "Prepare a Fielddesk email and human call sequence for UK contacts with a £100 total budget.",
      );
    await page
      .getByRole("button", { name: "Send to agent", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Ready for your review", exact: true }),
    ).toBeVisible({ timeout: 90000 });
    expect(
      posts.some(
        (p) =>
          p.endsWith("/preparations") ||
          p.endsWith("/audience") ||
          p.endsWith("/plan"),
      ),
    ).toBe(false);
    await page
      .getByText("Inspect exact recipients, copy and evidence", { exact: true })
      .click();
    await expect(
      page.getByText("Current validation is incomplete or stale.", {
        exact: false,
      }),
    ).toHaveCount(0);
    await page.reload();
    await page
      .getByRole("button", {
        name: "Review and approve simulation",
        exact: true,
      })
      .click();
    const dialog = page.getByRole("dialog", {
      name: "Approve this exact synthetic sequence?",
    });
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByRole("button", { name: "Cancel", exact: true }),
    ).toBeFocused();
    await dialog
      .getByRole("button", { name: "Approve and simulate", exact: true })
      .click();
    await expect(dialog).not.toBeVisible({ timeout: 30000 });
    for (let i = 0; i < 3; i++) {
      await expect
        .poll(
          async () => {
            if (
              await page
                .getByRole("heading", {
                  name: "Synthetic simulation complete",
                  exact: true,
                })
                .count()
            )
              return "complete";
            if (
              await page
                .getByRole("heading", {
                  name: "Human call tasks need your observation",
                  exact: true,
                })
                .count()
            )
              return "human";
            return "waiting";
          },
          { timeout: 90000, intervals: [1000] },
        )
        .not.toBe("waiting");
      if (
        await page
          .getByRole("heading", {
            name: "Synthetic simulation complete",
            exact: true,
          })
          .count()
      )
        break;
      const tasks = page.getByRole("button", {
        name: /Record synthetic task \d+ completed/,
      });
      while (await tasks.count()) {
        const count = await tasks.count();
        await tasks.first().click();
        await expect(tasks).toHaveCount(count - 1, { timeout: 30000 });
      }
    }
    await expect(
      page.getByRole("heading", {
        name: "Synthetic simulation complete",
        exact: true,
      }),
    ).toBeVisible({ timeout: 90000 });
    const before = posts.length;
    await page.reload();
    await expect(
      page.getByRole("heading", {
        name: "Synthetic simulation complete",
        exact: true,
      }),
    ).toBeVisible();
    expect(
      posts
        .slice(before)
        .some((p) => /sequence-(approve|task-completed)/.test(p)),
    ).toBe(false);
    expect(posts.filter((p) => p.endsWith("/sequence-approve"))).toHaveLength(
      1,
    );
    expect(errors).toEqual([]);
    await page.screenshot({
      path: "/tmp/iwoca-68-completed.png",
      fullPage: true,
    });
  });
});

test("ambiguous company asks one question and unsupported scope remains explicit", async ({
  page,
}) => {
  await isolated(async (url) => {
    await page.goto(url);
    await page
      .getByRole("button", { name: /New conversation/ })
      .first()
      .click();
    await page
      .getByLabel("Message Direct Acquisition")
      .fill("Prepare an email sequence with a £100 budget.");
    await page
      .getByRole("button", { name: "Send to agent", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "One detail needed", exact: true }),
    ).toBeVisible();
    await expect(page.getByText(/Which company is this for:/)).toBeVisible();
    await page
      .getByLabel("Message Direct Acquisition")
      .fill(
        "Prepare a Fielddesk email sequence for Germany with a £100 budget.",
      );
    await page
      .getByRole("button", { name: "Send to agent", exact: true })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "Requested scope is unavailable",
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: "Review and approve simulation",
        exact: true,
      }),
    ).toHaveCount(0);
  });
});

test("a delayed sequence approval response cannot replace a new chat", async ({
  page,
}) => {
  test.setTimeout(180000);
  await isolated(async (url) => {
    await page.goto(url);
    await page
      .getByLabel("Message Direct Acquisition")
      .fill(
        "Prepare a Fielddesk email and human call sequence for UK contacts with a £100 total budget.",
      );
    await page
      .getByRole("button", { name: "Send to agent", exact: true })
      .click();
    await expect(
      page.getByRole("button", {
        name: "Review and approve simulation",
        exact: true,
      }),
    ).toBeVisible({ timeout: 90000 });
    let release,
      held = false;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    await page.route("**/sequence-approve", async (route) => {
      const response = await route.fetch();
      held = true;
      await gate;
      await route.fulfill({ response });
    });
    await page
      .getByRole("button", {
        name: "Review and approve simulation",
        exact: true,
      })
      .click();
    const dialog = page.getByRole("dialog", {
      name: "Approve this exact synthetic sequence?",
    });
    await dialog
      .getByRole("button", { name: "Approve and simulate", exact: true })
      .click();
    await expect.poll(() => held, { timeout: 30000 }).toBe(true);
    await dialog.press("Escape");
    await page
      .getByRole("button", { name: "New conversation", exact: true })
      .click();
    await expect(
      page.getByRole("heading", {
        name: "What would you like to prepare?",
        exact: true,
      }),
    ).toBeVisible();
    const responseSeen = page.waitForResponse((response) =>
      response.url().endsWith("/sequence-approve"),
    );
    release();
    await responseSeen;
    await page
      .getByLabel("Message Direct Acquisition")
      .fill("Another objective for later.");
    await expect(
      page.getByRole("heading", {
        name: "What would you like to prepare?",
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.locator(".sequence-proposal")).toHaveCount(0);
    expect(
      await page.evaluate(() => localStorage.getItem("conversation-selected")),
    ).toBeNull();
  });
});

test("a channel change starts its own revision instead of answering an earlier postal budget question", async ({
  page,
}) => {
  test.setTimeout(60000);
  await isolated(async (url) => {
    await page.goto(url);
    await page
      .getByRole("button", { name: "Postal budget clarification", exact: true })
      .click();
    const posts = [];
    page.on("request", (request) => {
      if (request.method() === "POST")
        posts.push({
          path: new URL(request.url()).pathname,
          body: request.postDataJSON(),
        });
    });
    await page
      .getByLabel("Message Direct Acquisition")
      .fill(
        "Prepare a Fielddesk email and human call sequence for UK contacts with a £100 total budget.",
      );
    await page
      .getByRole("button", { name: "Send to agent", exact: true })
      .click();
    await expect(page.locator(".sequence-proposal")).toBeVisible({
      timeout: 15000,
    });
    const sequence = posts.find((p) => p.path.endsWith("/sequence-messages"));
    expect(sequence).toBeDefined();
    expect(sequence.body.expected_revision).toBe(1);
    expect(sequence.body.plan_id).toBeUndefined();
    expect(posts.some((p) => p.path.endsWith("/budget-replies"))).toBe(false);
  }, "postal-budget");
});

for (const legacyPending of [false, true])
  test(`a sequence conversation returns to unapproved postal review, saved sequence route=${legacyPending}`, async ({
    page,
  }) => {
    test.setTimeout(90000);
    await isolated(async (url) => {
      await page.goto(url);
      await page
        .getByRole("button", { name: "Return to postal", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: "One detail needed", exact: true }),
      ).toBeVisible();
      const text =
        "Prepare a £600 direct-mail response experiment for UK contractors. Use offline copy fixtures.";
      if (legacyPending) {
        await page.evaluate((content) => {
          sessionStorage.setItem(
            "conversation-pending-message",
            JSON.stringify({
              conversationId: localStorage.getItem("conversation-selected"),
              expected_revision: 1,
              content,
              allow_model_copy: false,
              funding: { browser: null },
              route: true,
              sequence: true,
            }),
          );
        }, text);
        await page.reload();
        await page
          .getByRole("button", { name: "Retry saving message", exact: true })
          .click();
      } else {
        await page.getByLabel("Message Direct Acquisition").fill(text);
        await page
          .getByRole("button", { name: "Send to agent", exact: true })
          .click();
      }
      const choice = page.getByRole("region", {
        name: "Choose campaign audience",
      });
      await expect(choice).toBeVisible({ timeout: 20000 });
      await page.reload();
      await expect(choice).toBeVisible();
      await choice.getByRole("button", { name: "Use v1", exact: true }).click();
      await expect(
        page.getByRole("button", { name: /Review campaign/ }),
      ).toBeVisible({ timeout: 20000 });
      await expect(page.locator(".sequence-proposal")).toHaveCount(1);
      await expect(
        page.getByText(
          "This revision is historical. Send a new objective to prepare a current proposal.",
          { exact: true },
        ),
      ).toBeVisible();
      await page.getByLabel("Message Direct Acquisition").fill("status?");
      await page
        .getByRole("button", { name: "Send to agent", exact: true })
        .click();
      await expect(
        page.getByRole("region", { name: "Saved follow-up" }),
      ).toBeVisible();
      await expect(page.locator(".sequence-proposal")).toHaveCount(1);
      await page.screenshot({
        path: `/tmp/iwoca-postal-return-${legacyPending}.png`,
        fullPage: true,
      });
    }, "return-postal");
  });
