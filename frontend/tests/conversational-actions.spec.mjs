import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { access, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

async function workspace(scenario, run) {
  const root = await mkdtemp(join(tmpdir(), "acquisition-actions-"));
  const script = `
import json,sys,time
from pathlib import Path
from unittest.mock import patch
from acquisition.workspace import Workspace
from acquisition.workspace_server import WorkspaceServer
from acquisition.conversations import FIXTURE_MESSAGE
from acquisition.reasoning import ModelError
from test_conversation_actions import ActionGateway
from test_model_copy import reply
from test_conversations import proposal
root=Path(sys.argv[1]);scenario=sys.argv[2]
class Gateway(ActionGateway):
    def complete(self,request):
        name=request['tools'][0]['function']['name']
        if name=='propose_conversation_action':
            self.routing_requests.append(request)
            if scenario=='unknown':raise ModelError('provider_request_failed')
            if scenario=='delayed':
                while not (root/'release').exists():time.sleep(0.05)
            content=json.loads(request['messages'][-1]['content'])['message']
            if scenario=='clarification' and 'explain the audience' in content:
                return reply(name,{'action':'clarify'})
            return reply(name,{'action':'amend_brief' if 'Change' in content else 'explain_exclusions'})
        if name=='submit_campaign_brief':return reply(name,proposal(budget_pence=40000,copy_mode='fixture'))
        return super().complete(request)
patch('acquisition.workspace.openrouter_key',return_value='fixture').start()
patch('acquisition.workspace.OpenRouter',return_value=Gateway()).start()
w=Workspace(root,real_clock=lambda:1793404800.)
c=w.create_conversation('c','Routing example')['id'];w.message_conversation(c,'m',0,FIXTURE_MESSAGE)
if scenario == 'typed-saved-prepare':
    w.plan_conversation_fixture(c,'p',1)
elif scenario != 'typed-prepare':
    w.start_preparation(c,'p',1,True,False,True)
    for _ in range(3):w.advance_preparations()
    v=w.conversation(c);e=v['preparations'][0]['audience_candidates']['entries'][0]
    w.select_conversation_audience(c,request_id='s',expected_revision=1,plan_id=v['current_plan']['result']['id'],dataset_id=e['dataset_id'],version=e['version'],checksum=e['checksum'],manifest_id=e['id'])
    for _ in range(6):w.advance_preparations()
if scenario == 'typed-next':
    sid=w.conversation(c)['campaigns'][0]['session_id']
    subject=w.view(sid)['review']['subject']['id']
    approval=w.action(sid,'approve',{'request_id':'approve','subject_id':subject,'reason':'Reviewed the exact fixture campaign.'})['review']['approval']['id']
    w.action(sid,'handoff',{'request_id':'handoff','approval_id':approval})
    w.action(sid,'open-learning',{'request_id':'open'})
    w.action(sid,'finalize',{'request_id':'finalize'})
if scenario == 'legacy-followup-race':
    original = w.route_followup
    def delay_first(*args, **kwargs):
        started = root/'original-started'
        if not started.exists():
            started.touch()
            deadline = time.monotonic() + 25
            while not (root/'release-original').exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError('Test did not release the original POST')
                time.sleep(0.05)
        return original(*args, **kwargs)
    w.route_followup = delay_first
server=WorkspaceServer(0,w,Path('frontend/dist'))
print('http://127.0.0.1:'+str(server.server_port),flush=True)
server.serve_forever()
`;
  const child = spawn("python3", ["-c", script, root, scenario], {
    cwd: fileURLToPath(new URL("../..", import.meta.url)),
    env: { ...process.env, PYTHONPATH: "src:tests" },
    stdio: ["ignore", "pipe", "pipe"],
  });
  const exit = new Promise((resolve) => child.once("exit", resolve));
  try {
    const url = await new Promise((resolve, reject) => {
      let output = "",
        errors = "";
      const timer = setTimeout(
        () => reject(new Error(errors || "Server did not start")),
        10000,
      );
      child.stderr.on("data", (chunk) => {
        errors += chunk.toString();
      });
      child.stdout.on("data", (chunk) => {
        output += chunk.toString();
        const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
        if (match) {
          clearTimeout(timer);
          resolve(match[0]);
        }
      });
      child.once("exit", () => {
        clearTimeout(timer);
        reject(new Error(errors));
      });
      child.once("error", reject);
    });
    await run(url, root);
  } finally {
    child.kill("SIGTERM");
    await exit;
    await rm(root, { recursive: true, force: true });
  }
}
async function open(page, url) {
  await page.goto(url);
  await page
    .getByRole("button", { name: "Routing example", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: /Review campaign/ }),
  ).toBeVisible();
}
async function ask(page, text) {
  await page.getByLabel("Message Direct Acquisition").fill(text);
  await page
    .getByRole("button", { name: "Send to agent", exact: true })
    .click();
}
async function backend(page, path, payload) {
  return page.evaluate(
    async ({ path, payload }) => {
      const headers = {
        "X-Workspace-Token": document.querySelector(
          'meta[name="workspace-token"]',
        ).content,
      };
      if (payload) headers["Content-Type"] = "application/json";
      const response = await fetch(path, {
        headers,
        method: payload ? "POST" : "GET",
        body: payload ? JSON.stringify(payload) : undefined,
      });
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    },
    { path, payload },
  );
}
async function current(page) {
  const id = await page.evaluate(() =>
    localStorage.getItem("conversation-selected"),
  );
  return backend(page, "/api/conversations/" + id);
}

test("resending a legacy follow-up shares one routing call with a delayed original POST", async ({
  page,
}) => {
  await workspace("legacy-followup-race", async (url, root) => {
    await open(page, url);
    const { id, revision } = await current(page);
    const path = `/api/conversations/${id}/actions`;
    const requestId = "original-followup";
    const payload = {
      allow_model_copy: false,
      content: "Explain the excluded businesses.",
      expected_revision: revision,
    };
    const token = await page
      .locator('meta[name="workspace-token"]')
      .getAttribute("content");
    await page.evaluate(
      ({ id, path, requestId, payload }) => {
        sessionStorage.setItem(
          "conversation-pending-message",
          JSON.stringify({
            conversationId: id,
            ...payload,
            route: true,
          }),
        );
        sessionStorage.setItem(
          "workspace-pending:" + JSON.stringify([path, payload]),
          requestId,
        );
      },
      { id, path, requestId, payload },
    );
    const original = page.request.post(url + path, {
      headers: { Origin: url, "X-Workspace-Token": token },
      data: { ...payload, request_id: requestId },
    });
    const resends = [];
    await page.route(url + path, (route) => {
      resends.push(route.request().postDataJSON());
      if (resends.length === 1)
        return route.fulfill({
          status: 409,
          json: { action_not_saved: true, error: "Test resend rejected." },
        });
      return route.continue();
    });
    try {
      await expect
        .poll(() =>
          access(join(root, "original-started")).then(
            () => true,
            () => false,
          ),
        )
        .toBe(true);
      await page.reload();
      await page.getByRole("button", { name: "Retry saving message" }).click();
      await expect(page.getByText(/no saved receipt yet/)).toBeVisible();
      expect(resends).toEqual([]);
      const resend = page.getByRole("button", {
        name: "Resend original follow-up",
      });
      await resend.click();
      await expect(page.getByText("Test resend rejected.")).toBeVisible();
      await page.reload();
      await resend.click();
      await expect(
        page.getByRole("region", { name: "Saved follow-up" }),
      ).toHaveCount(1);
      expect(resends).toEqual([
        { ...payload, request_id: requestId },
        { ...payload, request_id: requestId },
      ]);
    } finally {
      await writeFile(join(root, "release-original"), "");
    }
    const response = await original;
    expect(response.ok()).toBe(true);
    const { action_receipt } = await response.json();
    await expect
      .poll(async () =>
        (await current(page)).actions.map((action) => [
          action.id,
          action.request_id,
          action.status,
        ]),
      )
      .toEqual([[action_receipt.id, requestId, "succeeded"]]);
    expect((await current(page)).execution.used).toBe(1);
  });
});

test("read-only follow-ups preserve the selected audience and approval on desktop and mobile", async ({
  page,
}) => {
  await workspace("success", async (url) => {
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await open(page, url);
    const original = await current(page),
      sid = original.campaigns[0].session_id;
    const campaign = await backend(page, "/api/sessions/" + sid);
    await backend(page, "/api/sessions/" + sid + "/approve", {
      request_id: "approve",
      subject_id: campaign.review.subject.id,
      reason: "Reviewed the exact synthetic campaign.",
    });
    for (const text of [
      "status?",
      "Why did you choose this audience?",
      "Why were these businesses excluded?",
      "Explain validation",
    ])
      await ask(page, text);
    await expect(
      page.getByRole("region", { name: "Saved follow-up" }),
    ).toHaveCount(4);
    const view = await current(page),
      state = await backend(page, "/api/sessions/" + sid);
    expect(view.revision).toBe(1);
    expect(view.messages).toHaveLength(1);
    expect(state.review.approval_valid).toBe(true);
    expect(state.review.manifest.brief.audience_source).toEqual(
      campaign.review.manifest.brief.audience_source,
    );
    await page.screenshot({
      path: "../.local/routing-desktop.png",
      fullPage: true,
    });
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(await page.evaluate(() => document.documentElement.clientWidth));
    }
    await page.screenshot({
      path: "../.local/routing-mobile.png",
      fullPage: true,
    });
    await page.reload();
    await expect(
      page.getByRole("region", { name: "Saved follow-up" }),
    ).toHaveCount(4);
    expect(errors).toEqual([]);
  });
});

test("a proposed budget change waits for exact confirmation then starts a new source-bound preparation", async ({
  page,
}) => {
  await workspace("success", async (url) => {
    await open(page, url);
    await ask(page, "Change the budget to £400.");
    const apply = page.getByRole("button", {
      name: "Apply brief change",
      exact: true,
    });
    await expect(apply).toBeEnabled();
    expect((await current(page)).revision).toBe(1);
    await page.reload();
    await apply.click();
    await expect(
      page.getByRole("region", { name: "Choose campaign audience" }),
    ).toBeVisible();
    const value = await current(page);
    expect(value.revision).toBe(2);
    expect(value.messages).toHaveLength(2);
    expect(value.current_plan.result.budget_pence).toBe(40000);
    expect(value.preparations[1].audience_selection).toBeNull();
    expect(value.preparations[1].inputs.allow_model_copy).toBe(false);
  });
});

for (const loseAcknowledgement of [false, true])
  test(`router clarification displays the exact carried change and replans it once, lost=${loseAcknowledgement}`, async ({
    page,
  }) => {
    await workspace("clarification", async (url) => {
      if (loseAcknowledgement) {
        let lost = false;
        await page.route(
          "**/api/conversations/*/confirm-action",
          async (route) => {
            if (lost) return route.continue();
            lost = true;
            await route.fetch();
            await route.abort("failed");
          },
        );
      }
      await open(page, url);
      const before = await current(page),
        sid = before.campaigns[0].session_id;
      const campaign = await backend(page, `/api/sessions/${sid}`);
      await backend(page, `/api/sessions/${sid}/approve`, {
        request_id: "review-before-clarification",
        subject_id: campaign.review.subject.id,
        reason: "Reviewed exact campaign before any proposed change.",
      });
      const original =
        "Change the budget to £400 and explain the audience" +
        (loseAcknowledgement ? " " + "x".repeat(1200) : "");
      await ask(page, original);
      await expect(
        page.getByText(
          "Would you like an explanation of the existing campaign, or do you want to change its brief?",
          { exact: true },
        ),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "Apply brief change" }),
      ).toHaveCount(0);
      await ask(page, "Change it");
      const exchange = page.getByLabel("Clarification carried into the brief", {
        exact: true,
      });
      await expect(exchange).toContainText(original);
      await expect(exchange).toContainText("Would you like an explanation");
      expect((await current(page)).revision).toBe(1);
      expect(
        (await backend(page, `/api/sessions/${sid}`)).review.approval_valid,
      ).toBe(true);
      await page.reload();
      await expect(exchange).toContainText(original);
      for (const width of [390, 320]) {
        await page.setViewportSize({ width, height: 844 });
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth),
        ).toBe(await page.evaluate(() => document.documentElement.clientWidth));
      }
      await page
        .getByRole("button", { name: "Apply brief change", exact: true })
        .click();
      await expect(
        page.getByRole("region", { name: "Choose campaign audience" }),
      ).toBeVisible();
      const after = await current(page);
      expect(after.revision).toBe(3);
      expect(after.messages.map((m) => m.content).slice(-2)).toEqual([
        original,
        "Change it",
      ]);
      expect(after.current_plan.result.budget_pence).toBe(40000);
      expect(after.preparations).toHaveLength(2);
      expect(
        (await backend(page, `/api/sessions/${sid}`)).review.approval_valid,
      ).toBe(false);
      const confirmation = after.actions[1].confirmed;
      expect(confirmation.message_receipts.map((r) => r.revision)).toEqual([
        2, 3,
      ]);
      await page.reload();
      expect((await current(page)).messages).toHaveLength(3);
    });
  });

test("routing remains in progress while a provider call is active and completes without a false uncertainty warning", async ({
  page,
}) => {
  await workspace("delayed", async (url, root) => {
    await open(page, url);
    await ask(page, "Could you unpack why records were left out?");
    await expect
      .poll(
        async () =>
          (await current(page)).actions[0]?.generation?.outcome_uncertain,
      )
      .toBe(true);
    await expect(
      page.getByText("Interpreting your follow-up. The brief is unchanged.", {
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      page.getByText(/routing provider outcome is uncertain/),
    ).toHaveCount(0);
    await writeFile(join(root, "release"), "ready");
    await expect(
      page
        .getByRole("region", { name: "Saved follow-up" })
        .getByRole("paragraph")
        .filter({ hasText: /The draft excluded/ }),
    ).toBeVisible();
    expect((await current(page)).revision).toBe(1);
  });
});

test("unknown routing outcomes stay inspectable after reload without another request", async ({
  page,
}) => {
  await workspace("unknown", async (url) => {
    let posts = 0;
    page.on("request", (r) => {
      if (r.method() === "POST" && r.url().endsWith("/actions")) posts++;
    });
    await open(page, url);
    await ask(page, "Could you explain the audience choice in detail?");
    await expect(
      page.getByText(/routing provider outcome is uncertain/),
    ).toBeVisible();
    await page.reload();
    await expect(
      page.getByText(/routing provider outcome is uncertain/),
    ).toBeVisible();
    expect(posts).toBe(1);
    expect((await current(page)).revision).toBe(1);
  });
});

for (const committed of [false, true])
  test(`lost amendment confirmation response reconciles the original request, committed=${committed}`, async ({
    page,
  }) => {
    await workspace("success", async (url) => {
      const attempts = [];
      let dropped = false;
      await page.route(
        "**/api/conversations/*/confirm-action",
        async (route) => {
          attempts.push(route.request().postDataJSON());
          if (dropped) return route.continue();
          dropped = true;
          if (committed) await route.fetch();
          await route.abort("failed");
        },
      );
      await open(page, url);
      await ask(page, "Change the budget to £400.");
      const apply = page.getByRole("button", {
        name: "Apply brief change",
        exact: true,
      });
      await apply.click();
      if (!committed) {
        await expect(apply).toBeEnabled();
        await apply.click();
        expect(attempts).toHaveLength(2);
        expect(attempts[0]).toEqual(attempts[1]);
      }
      await expect(
        page.getByText("Change applied as brief revision 2.", { exact: true }),
      ).toBeVisible();
      const value = await current(page);
      expect(value.revision).toBe(2);
      expect(value.messages).toHaveLength(2);
      expect(value.preparations).toHaveLength(2);
    });
  });

test("stale amendment confirmation cannot apply to a changed brief and remains recoverable", async ({
  page,
}) => {
  await workspace("success", async (url) => {
    await open(page, url);
    await ask(page, "Change the budget to £400.");
    const apply = page.getByRole("button", {
      name: "Apply brief change",
      exact: true,
    });
    await expect(apply).toBeEnabled();
    const value = await current(page);
    await backend(page, `/api/conversations/${value.id}/messages`, {
      request_id: "another-client",
      expected_revision: 1,
      content: "Use £700 instead.",
    });
    await apply.click();
    await expect(apply).toBeDisabled();
    await expect(page.getByLabel("Message Direct Acquisition")).toBeEnabled();
    expect((await current(page)).revision).toBe(2);
    expect((await current(page)).messages[1].content).toBe("Use £700 instead.");
  });
});

for (const lost of [false, true])
  test(`a delayed confirmation cannot replace a newly opened chat, lost=${lost}`, async ({
    page,
  }) => {
    await workspace("success", async (url) => {
      let release;
      const gate = new Promise((resolve) => (release = resolve));
      let committed;
      const saved = new Promise((resolve) => (committed = resolve));
      await page.route(
        "**/api/conversations/*/confirm-action",
        async (route) => {
          const response = await route.fetch();
          committed();
          await gate;
          if (lost) await route.abort("failed");
          else await route.fulfill({ response });
        },
      );
      await open(page, url);
      const id = (await current(page)).id;
      await ask(page, "Change the budget to £400.");
      await page
        .getByRole("button", { name: "Apply brief change", exact: true })
        .click();
      await saved;
      await page
        .getByRole("button", { name: "New conversation", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: "What would you like to prepare?" }),
      ).toBeVisible();
      release();
      await expect
        .poll(
          async () =>
            (await backend(page, `/api/conversations/${id}`)).revision,
        )
        .toBe(2);
      // Wait for the delayed response and its reconciliation read to settle.
      await page.waitForTimeout(700);
      await expect(
        page.getByRole("heading", { name: "What would you like to prepare?" }),
      ).toBeVisible();
      await expect(
        page.getByText("Change applied as brief revision 2."),
      ).toHaveCount(0);
      expect(
        await page.evaluate(() =>
          localStorage.getItem("conversation-selected"),
        ),
      ).toBeNull();
    });
  });

for (const committed of [false, true])
  test(`lost follow-up response retains its original message and request identity, committed=${committed}`, async ({
    page,
  }) => {
    await workspace("success", async (url) => {
      const attempts = [];
      let dropped = false;
      await page.route("**/api/conversations/*/actions", async (route) => {
        attempts.push(route.request().postDataJSON());
        if (dropped) return route.continue();
        dropped = true;
        if (committed) await route.fetch();
        await route.abort("failed");
      });
      await open(page, url);
      await ask(page, "status?");
      await expect(
        page.getByRole("button", { name: "Retry saving message", exact: true }),
      ).toBeEnabled();
      await page.reload();
      await page
        .getByRole("button", { name: "Retry saving message", exact: true })
        .click();
      await expect(page.getByLabel("Message Direct Acquisition")).toBeEnabled();
      const value = await current(page);
      expect(value.actions).toHaveLength(1);
      expect(value.revision).toBe(1);
      expect(attempts).toHaveLength(2);
      expect(attempts[0]).toEqual(attempts[1]);
      expect(attempts[0].expected_revision).toBe(1);
    });
  });

for (const scenario of ["typed-prepare", "typed-saved-prepare", "typed-next"]) {
  test(`${scenario} recovers a lost confirmation response after reload`, async ({
    page,
  }) => {
    await workspace(scenario, async (url) => {
      await page.goto(url);
      await page
        .getByRole("button", { name: "Routing example", exact: true })
        .click();
      const prepare = scenario !== "typed-next";
      await ask(
        page,
        prepare ? "Prepare this campaign" : "Propose the next experiment",
      );
      const confirm = page.getByRole("button", {
        name: prepare
          ? "Confirm campaign preparation"
          : "Confirm next experiment proposal",
      });
      await expect(confirm).toBeVisible();
      const before = await current(page);
      expect(before.actions[0].confirmed).toBeNull();
      const attempts = [];
      let dropped = false;
      await page.route("**/confirm-typed-action", async (route) => {
        attempts.push(route.request().postDataJSON());
        if (attempts.length === 1) {
          if (!prepare) {
            const response = await route.fetch();
            expect(response.ok()).toBe(true);
          }
          await route.abort("failed");
          dropped = true;
          return;
        }
        await route.continue();
      });
      await confirm.click();
      await expect.poll(() => dropped).toBe(true);
      await page.reload();
      if (prepare) {
        await confirm.click();
        const choice = page.getByRole("region", {
          name: "Choose campaign audience",
        });
        await expect(choice).toBeVisible();
        expect((await current(page)).campaigns).toHaveLength(0);
        await choice
          .getByRole("button", { name: "Use v1", exact: true })
          .click();
        await expect(
          page.getByRole("button", { name: /Review campaign/ }),
        ).toBeVisible({ timeout: 10000 });
        expect(attempts).toHaveLength(2);
        expect(attempts[0]).toEqual(attempts[1]);
      } else {
        await expect(page.getByText("Next experiment proposed.")).toBeVisible();
        expect(attempts).toHaveLength(1);
      }
      const final = await current(page);
      expect(final.messages).toEqual(before.messages);
      expect(final.execution.used).toBe(0);
      expect(final.campaigns).toHaveLength(1);
      expect(final.preparations).toHaveLength(
        scenario === "typed-saved-prepare" ? 0 : 1,
      );
      if (!prepare) {
        const source = await backend(
          page,
          "/api/sessions/" + final.campaigns[0].session_id,
        );
        expect(source.followups).toHaveLength(1);
        expect(source.followups[0].id).toBe(
          final.actions[0].typed_effect.proposal_id,
        );
        expect(source.followups[0].session_id).toBeNull();
      }
    });
  });
}
