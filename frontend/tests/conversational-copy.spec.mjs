import { test, expect } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

async function workspace(scenario, run) {
  const root = await mkdtemp(join(tmpdir(), "acquisition-chat-copy-"));
  const script = `
import sys
from pathlib import Path
from unittest.mock import patch
from acquisition.workspace import Workspace
from acquisition.workspace_server import WorkspaceServer
from acquisition.reasoning import ModelError
from test_conversational_copy_revision import CopyRoutingModel
root=Path(sys.argv[1]);scenario=sys.argv[2];model=CopyRoutingModel()
patch('acquisition.workspace.openrouter_key',return_value='fixture').start()
patch('acquisition.workspace.OpenRouter',return_value=model).start()
w=Workspace(root,real_clock=lambda:1793404800.)
c=w.create_conversation('c','Copy campaign')['id']
w.message_conversation(c,'m',0,'Prepare a £600 contractor campaign with model copy.')
w.start_preparation(c,'prepare',1,False,True,True)
for _ in range(3):w.advance_preparations()
v=w.conversation(c);e=v['preparations'][0]['audience_candidates']['entries'][0]
w.select_conversation_audience(c,request_id='source',expected_revision=1,plan_id=v['current_plan']['result']['id'],dataset_id=e['dataset_id'],version=e['version'],checksum=e['checksum'],manifest_id=e['id'])
for _ in range(6):
    if scenario in {'checkpoint','disabled-checkpoint'}:
        from acquisition.adapters.sqlite.reviews import SqliteReviews
        with patch.object(SqliteReviews,'open_case',side_effect=OSError('case storage interrupted')):w.advance_preparations()
    else:w.advance_preparations()
if scenario=='disabled-checkpoint':
    session=w._session(w.conversation(c)['campaigns'][0]['session_id'])
    w._app(session).reviews.store.register_actor(session['organization'],'local-operator',('operator',),False)
    w.stop_execution(c,'stop-disabled',1)
if scenario=='unattributed':
    session=w._session(w.conversation(c)['campaigns'][0]['session_id'])
    app=w._app(session,with_model=True);scope=session['organization']
    run=app.start_model(scope,'unattributed-cli',campaign_id='unknown-campaign',as_of='2026-10-26')
    app.worker.drain(scope,run_id=run)
    assert len(app.calls.inspect(scope,run))==6
    with app.calls.database.transaction() as db:
        db.execute('INSERT INTO execution_pending_origins VALUES(?,?)',(scope,run))
original=model.complete
def complete(request):
    if scenario=='delayed' and request['tools'][0]['function']['name']!='propose_conversation_action':
        import time
        time.sleep(3)
    if scenario=='unknown' and request['tools'][0]['function']['name']!='propose_conversation_action':raise ModelError('provider_request_failed')
    return original(request)
model.complete=complete
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
    await exited;
    await rm(root, { recursive: true, force: true });
  }
}

async function backend(page, path, payload) {
  return page.evaluate(
    async ({ path, payload }) => {
      const response = await fetch(path, {
        method: payload ? "POST" : "GET",
        headers: {
          "X-Workspace-Token": document.querySelector(
            'meta[name="workspace-token"]',
          ).content,
          ...(payload ? { "Content-Type": "application/json" } : {}),
        },
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
  return backend(page, `/api/conversations/${id}`);
}
async function open(page, url) {
  await page.goto(url);
  await page
    .getByRole("button", { name: "Copy campaign", exact: true })
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
const consent = (page) =>
  page.getByLabel("Allow up to five model calls for this revision", {
    exact: true,
  });
const generate = (page) =>
  page.getByRole("button", { name: "Generate copy revision", exact: true });
const ready = (page) =>
  page.getByRole("button", { name: "Review revised copy", exact: true });

test("chat copy editing keeps exact consent and fresh approval on desktop and mobile", async ({
  page,
}) => {
  await workspace("success", async (url) => {
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await open(page, url);
    const before = await current(page),
      sid = before.campaigns[0].session_id;
    const state = await backend(page, `/api/sessions/${sid}`);
    await backend(page, `/api/sessions/${sid}/approve`, {
      request_id: "approve",
      subject_id: state.review.subject.id,
      reason: "Reviewed exact draft.",
    });
    await ask(
      page,
      "Make variant B more direct. Keep variant A and the audience unchanged.",
    );
    const proposal = page.getByLabel("Copy edit proposal", { exact: true });
    await expect(proposal).toContainText("Variant B");
    await expect(generate(page)).toBeDisabled();
    expect(
      (await backend(page, `/api/sessions/${sid}`)).review.approval_valid,
    ).toBe(true);
    await page.screenshot({
      path: "../.local/chat-copy-desktop.png",
      fullPage: true,
    });
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(await page.evaluate(() => document.documentElement.clientWidth));
    }
    await page.screenshot({
      path: "../.local/chat-copy-mobile.png",
      fullPage: true,
    });
    await page.reload();
    await expect(generate(page)).toBeDisabled();
    await consent(page).check();
    await generate(page).click();
    await expect(ready(page)).toBeVisible();
    const after = await current(page),
      revised = await backend(page, `/api/sessions/${sid}`);
    expect(after.revision).toBe(1);
    expect(after.messages).toHaveLength(1);
    expect(after.preparations).toHaveLength(1);
    expect(revised.review.subject.id).not.toBe(state.review.subject.id);
    expect(revised.review.approval_valid).toBe(false);
    expect(revised.review.manifest.brief).toEqual(state.review.manifest.brief);
    await ready(page).click();
    const review = page.getByRole("region", {
      name: "Campaign review in conversation",
    });
    await expect(review.getByText("Review & approval")).toBeVisible();
    await expect(
      review.getByRole("button", {
        name: "Approve this revision",
        exact: true,
      }),
    ).toBeEnabled();
    expect(errors).toEqual([]);
  });
});

test("a bare variant reply retains the prior copy feedback across reload", async ({
  page,
}) => {
  await workspace("success", async (url) => {
    await open(page, url);
    await ask(page, "Make the copy more direct.");
    await expect(
      page.getByLabel("Copy edit proposal", { exact: true }),
    ).toContainText("Which variant should I revise?");
    await expect(generate(page)).toHaveCount(0);
    const id = (await current(page)).id;
    let release;
    const gate = new Promise((resolve) => (release = resolve));
    await page.route(`${url}/api/conversations/${id}`, async (route) => {
      const response = await route.fetch();
      await gate;
      await route.fulfill({ response });
    });
    await page.reload();
    await expect(page.getByLabel("Message Direct Acquisition")).toBeDisabled();
    await expect(
      page.getByRole("button", { name: "Send to agent", exact: true }),
    ).toBeDisabled();
    release();
    await ask(page, "B");
    await expect(
      page.getByLabel("Copy edit proposal", { exact: true }).last(),
    ).toContainText("Make the copy more direct. / B");
    await consent(page).check();
    await generate(page).click();
    await expect(ready(page)).toBeVisible();
    const value = await current(page);
    expect(value.id).toBe(id);
    expect(value.revision).toBe(1);
    expect(value.actions[1].copy_revision_progress.feedback).toBe(
      "Make the copy more direct. / B",
    );
  });
});

test("a selected variant survives its wording question and reload", async ({
  page,
}) => {
  await workspace("success", async (url) => {
    await open(page, url);
    await ask(page, "B");
    await expect(
      page.getByLabel("Copy edit proposal", { exact: true }),
    ).toContainText("What wording would you like me to change");
    await expect(generate(page)).toHaveCount(0);
    await page.reload();
    await expect(page.getByLabel("Message Direct Acquisition")).toBeEnabled();
    await ask(page, "Make it more direct.");
    const proposal = page
      .getByLabel("Copy edit proposal", { exact: true })
      .last();
    await expect(proposal).toContainText("Variant B");
    await expect(proposal).toContainText("B / Make it more direct.");
    await consent(page).check();
    await generate(page).click();
    await expect(ready(page)).toBeVisible();
    const view = await current(page);
    expect(view.revision).toBe(1);
    expect(view.actions[1].copy_revision_progress.feedback).toBe(
      "B / Make it more direct.",
    );
    expect(view.actions[1].result.copy_revision.target.arm).toBe("B");
  });
});

test("an independent variant edit receives only its own feedback", async ({
  page,
}) => {
  await workspace("success", async (url) => {
    await open(page, url);
    await ask(page, "Make variant B more formal.");
    await expect(
      page.getByLabel("Copy edit proposal", { exact: true }),
    ).toContainText("Variant B");
    await ask(page, "Make variant A more casual.");
    const proposal = page
      .getByLabel("Copy edit proposal", { exact: true })
      .last();
    await expect(proposal).toContainText("Variant A");
    await expect(proposal).toContainText("Make variant A more casual.");
    await expect(proposal).not.toContainText("formal");
    await consent(page).last().check();
    await generate(page).last().click();
    await expect(ready(page)).toBeVisible();
    const view = await current(page);
    expect(view.actions[0].confirmed).toBeNull();
    expect(view.actions[1].result.copy_revision.target.arm).toBe("A");
    expect(view.actions[1].copy_revision_progress.feedback).toBe(
      "Make variant A more casual.",
    );
    expect(view.revision).toBe(1);
  });
});

test("blocked preparation without checkpoint recovery stops polling after case storage is restored", async ({
  page,
}) => {
  // The storage failure ends before the server starts. This ordinary blocked
  // preparation has no stopped-checkpoint receipt for the coordinator to retry.
  await workspace("checkpoint", async (url) => {
    await page.goto(url);
    await page
      .getByRole("button", { name: "Copy campaign", exact: true })
      .click();
    const progress = page.getByRole("region", {
      name: "Campaign preparation progress",
    });
    await expect(progress).toContainText("Preparation needs attention");
    const value = await current(page);
    expect(value.preparations[0].status).toBe("blocked");
    expect(value.preparations[0].checkpoint_recovery).toBeUndefined();
    expect(value.campaigns[0].generation.status).toBe("waiting");
    expect(value.campaigns[0].case_id).toBeNull();
    expect(value.execution.pending_receipts).toBe(0);
    // Observe three polling intervals: no background conversation reads should
    // continue when the server has no automatic recovery to advance.
    await expect(
      page.waitForRequest(
        (request) =>
          request.method() === "GET" &&
          request.url() === `${url}/api/conversations/${value.id}`,
        { timeout: 1800 },
      ),
    ).rejects.toThrow(/Timeout/);
    const after = await current(page);
    expect(after.preparations[0].status).toBe("blocked");
    expect(after.campaigns[0].case_id).toBeNull();
    expect(after.execution.used).toBe(value.execution.used);
    await expect(
      page.getByRole("button", { name: /Review campaign/ }),
    ).toHaveCount(0);
    await expect(progress).toContainText("Preparation needs attention");
  });
});

test("stopping a completed checkpoint recovers its unapproved review without inference", async ({
  page,
}) => {
  await workspace("checkpoint", async (url) => {
    await page.goto(url);
    await page
      .getByRole("button", { name: "Copy campaign", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Review campaign", exact: false }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("button", { name: "Stop work", exact: true }),
    ).toBeVisible();
    const before = (await current(page)).execution.used;
    await page.getByRole("button", { name: "Stop work", exact: true }).click();
    await expect(
      page.getByRole("button", { name: /Review campaign/ }),
    ).toBeVisible();
    const stopped = await current(page);
    expect(stopped.execution.stopped).toBe(true);
    expect(stopped.execution.used).toBe(before);
    const state = await backend(
      page,
      `/api/sessions/${stopped.campaigns[0].session_id}`,
    );
    expect(state.review.candidate_valid).toBe(true);
    expect(state.review.approval_valid).toBe(false);
    expect(state.review.handoff).toBeNull();
    await page.reload();
    await page.getByRole("button", { name: /Review campaign/ }).click();
    await expect(
      page.getByRole("region", { name: "Campaign review in conversation" }),
    ).toBeVisible();
    expect((await current(page)).execution.used).toBe(before);
  });
});

test("unattributed historical calls label the displayed cost as incomplete", async ({
  page,
}) => {
  await workspace("unattributed", async (url, root) => {
    await open(page, url);
    const controls = page.getByRole("region", { name: "Execution controls" });
    await expect(
      controls.getByText("Model-call allowance unknown", { exact: true }),
    ).toBeVisible();
    await expect(
      controls.getByText(/remaining allowance unknown/),
    ).toBeVisible();
    await expect(controls.getByText(/\d+ remaining/)).toHaveCount(0);
    await expect(
      controls.getByText(/Historical campaign ancestry needs recovery/),
    ).toBeVisible();
    await controls.getByText("Inspect model usage", { exact: true }).click();
    await expect(
      controls.getByText(/Provider-reported cost: \$0 \(incomplete\)/),
    ).toBeVisible();
    const view = await current(page);
    expect(view.execution.accounting_complete).toBe(false);
    expect(view.execution.cost_complete).toBe(false);
    expect(view.execution.unresolved_runs).toHaveLength(1);
    expect(view.execution.remaining).toBeNull();
    await expect(controls.getByText(/Operator recovery:/)).toBeVisible();
    await expect(controls.getByText(/Organization:/)).toBeVisible();
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      expect(
        await page.evaluate(
          () =>
            document.documentElement.scrollWidth ===
            document.documentElement.clientWidth,
        ),
      ).toBe(true);
      await expect(
        controls.getByText(/remaining allowance unknown/),
      ).toBeVisible();
    }
    const script = `
import json,sys,subprocess
from pathlib import Path
root=Path(sys.argv[1]);run=sys.argv[2]
import sqlite3
with sqlite3.connect(root/'conversations.sqlite') as db:
    scope=db.execute('SELECT organization FROM runs WHERE id=?',(run,)).fetchone()[0]
prefix=[sys.executable,'-m','acquisition','--db',str(root/'conversations.sqlite'),'--organization',scope]
items=json.loads(subprocess.check_output(prefix+['execution-unresolved'],text=True))
item=next(i for i in items if i['run_id']==run)
subprocess.check_call(prefix+['execution-resolve-independent','--run',run,'--request-id','browser-attestation','--fingerprint',item['fingerprint'],'--actor','local-operator','--reason','Operator verified independent CLI experiment.'],stdout=subprocess.DEVNULL)
`;
    execFileSync(
      "python3",
      ["-c", script, root, view.execution.unresolved_runs[0]],
      {
        cwd: fileURLToPath(new URL("../..", import.meta.url)),
        env: { ...process.env, PYTHONPATH: "src:tests" },
      },
    );
    await page.reload();
    await expect(controls.getByText(/remaining allowance unknown/)).toHaveCount(
      0,
    );
    await expect(
      controls.getByText(
        new RegExp(`${view.execution.limit - view.execution.used} remaining`),
      ),
    ).toBeVisible();
    const recovered = await current(page);
    expect(recovered.execution.accounting_complete).toBe(true);
    expect(recovered.execution.used).toBe(view.execution.used);
  });
});

test("blocked checkpoint recovery stays visible and polling completes after authority is restored", async ({
  page,
}) => {
  await workspace("disabled-checkpoint", async (url, root) => {
    await page.goto(url);
    await page
      .getByRole("button", { name: "Copy campaign", exact: true })
      .click();
    const progress = page.getByRole("region", {
      name: "Campaign preparation progress",
    });
    await expect(progress).toContainText("Restore a permitted local operator");
    await expect(
      page.getByRole("button", { name: /Review campaign/ }),
    ).toHaveCount(0);
    const value = await current(page),
      before = value.execution.used;
    // Recovery can update progress after the conversation read captured its
    // campaign list. Deliver that one intermediate read deterministically.
    let intermediate = false;
    await page.route(`**/api/conversations/${value.id}`, async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      if (
        !intermediate &&
        body.preparations?.some((p) => p.status === "review_ready") &&
        body.campaigns?.some((c) => c.case_id)
      ) {
        intermediate = true;
        body.campaigns = body.campaigns.map((c) => ({ ...c, case_id: null }));
        await route.fulfill({ response, json: body });
      } else {
        await route.fulfill({ response });
      }
    });
    execFileSync(
      "python3",
      [
        "-c",
        `
import sys
from acquisition.workspace import Workspace
w=Workspace(sys.argv[1],real_clock=lambda:1793404800.)
s=w._session(w.conversation(sys.argv[2])['campaigns'][0]['session_id'])
w._app(s).reviews.store.register_actor(s['organization'],'local-operator',('operator',),True)
`,
        root,
        value.id,
      ],
      {
        env: { ...process.env, PYTHONPATH: "src:tests" },
        cwd: fileURLToPath(new URL("../..", import.meta.url)),
      },
    );
    await expect(
      page.getByRole("button", { name: /Review campaign/ }),
    ).toBeVisible();
    await expect(progress).toContainText("Ready for your review");
    expect(intermediate).toBe(true);
    expect((await current(page)).execution.used).toBe(before);
    const state = await backend(
      page,
      `/api/sessions/${value.campaigns[0].session_id}`,
    );
    expect(state.review.approval_valid).toBe(false);
    expect(state.review.handoff).toBeNull();
  });
});

test("stopping an active revision reconciles a lost response and retains accounting", async ({
  page,
}) => {
  await workspace("delayed", async (url) => {
    await open(page, url);
    await ask(page, "Make variant B more direct.");
    await consent(page).check();
    await generate(page).click();
    await expect
      .poll(async () => (await current(page)).execution.counts.in_progress)
      .toBe(1);
    const before = (await current(page)).execution.used;
    const attempts = [];
    await page.route("**/api/conversations/*/stop", async (route) => {
      attempts.push(route.request().postDataJSON());
      await route.fetch();
      await route.abort("failed");
    });
    await page.getByRole("button", { name: "Stop work", exact: true }).click();
    const controls = page.getByRole("region", { name: "Execution controls" });
    await expect(controls).toContainText("Work stopped");
    await expect(controls).toContainText("may still return after stopping");
    await expect
      .poll(async () => (await current(page)).execution.pending_receipts)
      .toBe(0);
    await page.reload();
    await expect(controls).toContainText("Work stopped");
    expect(attempts).toHaveLength(1);
    expect((await current(page)).execution.used).toBe(before);
    await expect(ready(page)).toHaveCount(0);
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBe(await page.evaluate(() => document.documentElement.clientWidth));
    }
    await controls.getByText("Inspect model usage", { exact: true }).click();
    await expect(controls).toContainText("not a verified bill");
    await page.screenshot({
      path: "../.local/execution-controls-mobile.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({
      path: "../.local/execution-controls-desktop.png",
      fullPage: true,
    });
  });
});

test("a new brief after stopping keeps the shared allowance and needs a new audience", async ({
  page,
}) => {
  await workspace("delayed", async (url) => {
    await open(page, url);
    await ask(page, "Make variant B more direct.");
    await consent(page).check();
    await generate(page).click();
    await expect
      .poll(async () => (await current(page)).execution.counts.in_progress)
      .toBe(1);
    await page.getByRole("button", { name: "Stop work", exact: true }).click();
    await expect
      .poll(async () => (await current(page)).execution.pending_receipts)
      .toBe(0);
    const before = (await current(page)).execution.used;
    await page.reload();
    await expect(page.getByLabel("Message Direct Acquisition")).toBeEnabled();
    await page
      .getByLabel("Allow model copy for this request", { exact: true })
      .check();
    await ask(page, "Prepare a £600 contractor campaign with model copy.");
    await expect.poll(async () => (await current(page)).revision).toBe(2);
    await expect
      .poll(async () => (await current(page)).preparations.at(-1).status)
      .toBe("selecting_audience");
    const value = await current(page);
    expect(value.execution.stopped).toBe(false);
    expect(value.execution.used).toBeGreaterThan(before);
    expect(value.execution.limit).toBe(48);
    expect(value.messages).toHaveLength(2);
    expect(value.actions).toHaveLength(1);
    expect(value.preparations.at(-1).audience_selection).toBeNull();
  });
});

for (const committed of [false, true])
  test(`lost copy confirmation preserves its original command, committed=${committed}`, async ({
    page,
  }) => {
    await workspace("success", async (url) => {
      const attempts = [];
      let lost = false;
      await page.route(
        "**/api/conversations/*/confirm-copy-action",
        async (route) => {
          attempts.push(route.request().postDataJSON());
          if (lost) return route.continue();
          lost = true;
          if (committed) await route.fetch();
          await route.abort("failed");
        },
      );
      await open(page, url);
      await ask(page, "Make variant B more direct.");
      await consent(page).check();
      await generate(page).click();
      if (!committed) {
        await expect(generate(page)).toBeEnabled();
        await page.reload();
        await consent(page).check();
        await generate(page).click();
        expect(attempts).toHaveLength(2);
        expect(attempts[0]).toEqual(attempts[1]);
      }
      await expect(ready(page)).toBeVisible();
      const view = await current(page),
        sid = view.campaigns[0].session_id;
      const state = await backend(page, `/api/sessions/${sid}`);
      expect(state.copy_revisions).toHaveLength(1);
      expect(
        state.review.events.filter((e) => e.kind === "copy_revision_requested"),
      ).toHaveLength(1);
    });
  });

test("a stale target is rejected and the chat remains editable", async ({
  page,
}) => {
  await workspace("success", async (url) => {
    await open(page, url);
    await ask(page, "Make variant B more direct.");
    await consent(page).check();
    const view = await current(page),
      sid = view.campaigns[0].session_id,
      target = view.actions[0].result.copy_revision.target;
    await backend(page, `/api/sessions/${sid}/copy-revisions`, {
      request_id: "manual",
      expected_subject: target.subject_id,
      target_id: target.id,
      feedback: "A separate manual edit.",
      allow_model_copy: true,
    });
    await expect
      .poll(
        async () =>
          (await backend(page, `/api/sessions/${sid}`)).review.subject.id,
      )
      .not.toBe(target.subject_id);
    await generate(page).click();
    await expect(generate(page)).toBeDisabled();
    await expect(
      page.getByText(
        "This proposal belongs to an earlier draft or brief. Request a new edit for the current campaign.",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(page.getByLabel("Message Direct Acquisition")).toBeEnabled();
    expect(
      (await backend(page, `/api/sessions/${sid}`)).copy_revisions,
    ).toHaveLength(1);
  });
});

test("a native uncertain outcome remains visible after reload without resubmission", async ({
  page,
}) => {
  await workspace("unknown", async (url) => {
    let posts = 0;
    page.on("request", (r) => {
      if (r.method() === "POST" && r.url().endsWith("/confirm-copy-action"))
        posts++;
    });
    await open(page, url);
    await ask(page, "Make variant B more direct.");
    await consent(page).check();
    await generate(page).click();
    await expect(
      page.getByText(/The revision provider outcome is uncertain/),
    ).toBeVisible();
    await page.reload();
    await expect(
      page.getByText(/The revision provider outcome is uncertain/),
    ).toBeVisible();
    expect(posts).toBe(1);
    const view = await current(page);
    expect(
      view.actions[0].copy_revision_progress.generation.outcome_uncertain,
    ).toBe(true);
  });
});

for (const lost of [false, true])
  test(`a delayed copy confirmation cannot replace a new chat, lost=${lost}`, async ({
    page,
  }) => {
    await workspace("success", async (url) => {
      let release, saved;
      const gate = new Promise((resolve) => (release = resolve));
      const committed = new Promise((resolve) => (saved = resolve));
      await page.route(
        "**/api/conversations/*/confirm-copy-action",
        async (route) => {
          const response = await route.fetch();
          saved();
          await gate;
          if (lost) await route.abort("failed");
          else await route.fulfill({ response });
        },
      );
      await open(page, url);
      await ask(page, "Make variant B more direct.");
      await consent(page).check();
      await generate(page).click();
      await committed;
      await page
        .getByRole("button", { name: "New conversation", exact: true })
        .click();
      release();
      await expect(
        page.getByRole("heading", { name: "What would you like to prepare?" }),
      ).toBeVisible();
      await page.waitForTimeout(600);
      await expect(
        page.getByRole("heading", { name: "What would you like to prepare?" }),
      ).toBeVisible();
      expect(
        await page.evaluate(() =>
          localStorage.getItem("conversation-selected"),
        ),
      ).toBeNull();
    });
  });
