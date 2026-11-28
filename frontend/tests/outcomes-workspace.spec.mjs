import { test, expect } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { mkdtemp, rm, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
const project = fileURLToPath(new URL("../..", import.meta.url));
async function isolated(run) {
  const roots = [await mkdtemp(join(tmpdir(), "gtm-outcomes-ui-"))];
  let child, exited, seed;
  const script = `
import json,sys
from pathlib import Path
from acquisition.bootstrap import build_workspace
from acquisition.entrypoints.workspace import WorkspaceServer
from acquisition.learning import external_registration
from test_external_outcomes import manifest,report,event,NOW
w=build_workspace(sys.argv[1],real_clock=lambda:NOW+100)
c=w.intake.save('companies',{'request_id':'company','id':None,'expected_revision':0,'draft':{'company_name':'Fielddesk'}})['snapshot']
b=w.intake.save('briefs',{'request_id':'brief','id':None,'expected_revision':0,'draft':{'company_id':c['id'],'company_revision':1,'objective':'Recorded email pilot','channels':['email']}})['snapshot']
m=manifest('local-conversations');cohort=external_registration(m,'local-conversations',NOW+100)
rows=[event(a,'qualified_enquiry' if i==0 else 'no_qualified_enquiry',NOW if i==0 else NOW+100) for i,a in enumerate(cohort['assignments'])]
p=report(cohort,rows,final=True,identity='complete')
Path(sys.argv[1],'seed.json').write_text(json.dumps({'company':c,'brief':b,'manifest':m,'report':p,'cohort':cohort}))
s=WorkspaceServer(int(sys.argv[2]),w,Path('frontend/dist'))
print('http://127.0.0.1:'+str(s.server_port),flush=True)
s.serve_forever()
`;
  async function start(root, port = 0) {
    child = spawn("python3", ["-c", script, root, String(port)], {
      cwd: project,
      env: {
        ...process.env,
        PYTHONPATH: "src:tests",
        OPENROUTER_API_KEY: "offline-tests-must-not-use-live-credentials",
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    exited = new Promise((resolve) => child.once("exit", resolve));
    const url = await new Promise((resolve, reject) => {
      let out = "",
        err = "";
      const timer = setTimeout(
        () => reject(new Error(err || "Outcome fixture did not start")),
        30000,
      );
      child.stdout.on("data", (chunk) => {
        out += chunk.toString();
        const match = out.match(/http:\/\/127\.0\.0\.1:\d+/);
        if (match) {
          clearTimeout(timer);
          resolve(match[0]);
        }
      });
      child.stderr.on("data", (chunk) => {
        err += chunk.toString();
      });
      child.once("error", reject);
      child.once("exit", () => {
        clearTimeout(timer);
        reject(new Error(err));
      });
    });
    seed = JSON.parse(await readFile(join(root, "seed.json"), "utf8"));
    return url;
  }
  try {
    const url = await start(roots[0]);
    const restart = async (root) => {
      child.kill("SIGTERM");
      await exited;
      if (!root) {
        root = await mkdtemp(join(tmpdir(), "gtm-outcomes-other-"));
        roots.push(root);
      }
      await start(root, Number(new URL(url).port));
      return root;
    };
    await run(url, roots[0], seed, restart);
  } finally {
    child?.kill("SIGTERM");
    await exited;
    for (const root of roots) await rm(root, { recursive: true, force: true });
  }
}
async function open(page, url) {
  await page.goto(url);
  await page.getByRole("button", { name: "Learning", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Recorded outcomes", exact: true }),
  ).toBeVisible();
}
async function registration(page, seed) {
  await page
    .getByLabel("Company", { exact: true })
    .selectOption(seed.company.id);
  await page
    .getByLabel("Saved campaign brief", { exact: true })
    .selectOption(seed.brief.id);
  await page
    .getByLabel("Original JSON source")
    .fill(JSON.stringify(seed.manifest));
  await page
    .getByRole("button", { name: "Preview registration", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Confirm registration", exact: true }),
  ).toBeEnabled();
}
async function pending(page) {
  return page.evaluate(
    () =>
      new Promise((resolve, reject) => {
        const open = indexedDB.open("workspace-recorded-outcomes", 1);
        open.onsuccess = () => {
          const db = open.result;
          const tx = db.transaction("pending");
          const get = tx.objectStore("pending").get("original");
          get.onsuccess = () => resolve(get.result ?? null);
          tx.oncomplete = () => db.close();
        };
        open.onerror = reject;
      }),
  );
}

async function loseNextReply(page, operation) {
  await page.route(
    `**/api/outcomes/${operation}`,
    async (route) => {
      const response = await route.fetch();
      expect(response.ok()).toBe(true);
      await route.abort("failed");
    },
    { times: 1 },
  );
}
async function reconcileLostReply(page) {
  const recover = page.getByRole("button", {
    name: "Recover original request",
    exact: true,
  });
  await expect(recover).toBeEnabled();
  const original = await pending(page);
  expect(original).not.toBeNull();
  await recover.click();
  await expect(
    page.getByRole("heading", {
      name: "Recover original request",
      exact: true,
    }),
  ).toHaveCount(0);
  expect(await pending(page)).toBeNull();
}

test("recorded email outcomes preview, finalize and download exact historical evidence", async ({
  page,
}) => {
  await isolated(async (url, root, seed, restart) => {
    await open(page, url);
    await registration(page, seed);
    await expect(page.getByText(/Company: Fielddesk/)).toBeVisible();
    await page
      .getByRole("button", { name: "Confirm registration", exact: true })
      .click();
    await expect(
      page.getByText("Unknown outcomes", { exact: true }),
    ).toBeVisible();
    await page
      .getByLabel("Operation", { exact: true })
      .selectOption("finalize");
    await page
      .getByRole("button", { name: "Preview finalization", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Confirm finalization", exact: true }),
    ).toBeDisabled();
    // Use the registered wire identity, not a separately serialized Python fixture.
    seed.report.cohort_id = await page
      .getByLabel("Recorded campaign", { exact: true })
      .inputValue();
    seed.cohort.id = seed.report.cohort_id;
    await page.getByLabel("Operation", { exact: true }).selectOption("import");
    await page.getByLabel("JSON evidence file").setInputFiles({
      name: "final.json",
      mimeType: "application/json",
      buffer: Buffer.from(JSON.stringify(seed.report)),
    });
    await page
      .getByRole("button", { name: "Preview report", exact: true })
      .click();
    await loseNextReply(page, "import");
    await page
      .getByRole("button", { name: "Confirm report import", exact: true })
      .click();
    await reconcileLostReply(page);
    await expect(
      page.getByText("ready to finalize", { exact: false }).first(),
    ).toBeVisible();
    await page
      .getByLabel("Operation", { exact: true })
      .selectOption("finalize");
    await page
      .getByRole("button", { name: "Preview finalization", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Confirm finalization", exact: true }),
    ).toBeEnabled();
    await loseNextReply(page, "finalize");
    await page
      .getByRole("button", { name: "Confirm finalization", exact: true })
      .click();
    await reconcileLostReply(page);
    await expect(
      page.getByRole("heading", { name: "Current eligible learning" }),
    ).toBeVisible();
    await expect(
      page.getByRole("cell", { name: "9.1%", exact: true }),
    ).toHaveCount(1);
    await page
      .getByRole("button", {
        name: "Inspect report complete (final snapshot)",
        exact: true,
      })
      .click();
    const downloaded = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "Download displayed report", exact: true })
      .click();
    const file = await downloaded;
    const value = JSON.parse(await readFile(await file.path(), "utf8"));
    expect(value.snapshot).toEqual(seed.report);
    expect(value.observation).toBe("HISTORICAL_RECEIPT_NO_CURRENT_AUTHORITY");
    await restart(root);
    await open(page, url);
    await page
      .getByLabel("Company", { exact: true })
      .selectOption(seed.company.id);
    await page
      .getByLabel("Recorded campaign", { exact: true })
      .selectOption(seed.cohort.id);
    await expect(
      page.getByRole("heading", { name: "Current eligible learning" }),
    ).toBeVisible();
    const dbPath = join(root, "conversations.sqlite");
    const counts = JSON.parse(
      execFileSync(
        "python3",
        [
          "-c",
          "import sqlite3,json,sys; c=sqlite3.connect(sys.argv[1]); print(json.dumps({t:c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('model_calls','learning_beliefs','learning_cohorts','runs')}))",
          dbPath,
        ],
        { encoding: "utf8" },
      ),
    );
    expect(counts).toEqual({
      model_calls: 0,
      learning_beliefs: 0,
      learning_cohorts: 0,
      runs: 0,
    });
  });
});

test("lost registration reply survives reload and refuses a different workspace store", async ({
  page,
}) => {
  await isolated(async (url, root, seed, restart) => {
    await open(page, url);
    await registration(page, seed);
    let body;
    await page.route("**/api/outcomes/register", async (route) => {
      body = route.request().postDataJSON();
      const response = await route.fetch();
      expect(response.ok()).toBe(true);
      await route.abort("failed");
    });
    await page
      .getByRole("button", { name: "Confirm registration", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Recover original request" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", {
        name: "Recover original request",
        exact: true,
      }),
    ).toBeEnabled();
    const original = await pending(page);
    expect(original.payload.request_id).toBe(body.request_id);
    await page.unroute("**/api/outcomes/register");
    await restart();
    await open(page, url);
    let dispatched = 0;
    page.on("request", (request) => {
      if (request.url().endsWith("/api/outcomes/register")) dispatched++;
    });
    await page
      .getByRole("button", { name: "Recover original request", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "different workspace store",
    );
    expect(dispatched).toBe(0);
    expect(await pending(page)).toEqual(original);
    await restart(root);
    await open(page, url);
    await page
      .getByRole("button", { name: "Recover original request", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Saved request receipt", exact: true }),
    ).toBeVisible();
    expect(await pending(page)).toBeNull();
    expect(dispatched).toBe(1);
    const count = execFileSync(
      "python3",
      [
        "-c",
        "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute(\"SELECT count(*) FROM learning_events WHERE kind='external_registration'\").fetchone()[0])",
        join(root, "conversations.sqlite"),
      ],
      { encoding: "utf8" },
    );
    expect(count.trim()).toBe("1");
  });
});

test("strict duplicate source rejection and company switching invalidate reviewed registration", async ({
  page,
}) => {
  await isolated(async (url, root, seed) => {
    await open(page, url);
    await registration(page, seed);
    await page.getByLabel("Company", { exact: true }).selectOption("");
    await expect(
      page.getByRole("button", { name: "Confirm registration", exact: true }),
    ).toHaveCount(0);
    await page
      .getByLabel("Company", { exact: true })
      .selectOption(seed.company.id);
    await page
      .getByLabel("Saved campaign brief", { exact: true })
      .selectOption(seed.brief.id);
    await page
      .getByLabel("Original JSON source")
      .fill('{"schema":"a","schema":"b"}');
    await page
      .getByRole("button", { name: "Preview registration", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText("Duplicate");
    await expect(page.getByRole("alert")).toBeFocused();
    expect(await pending(page)).toBeNull();
  });
});

test("mobile Learning works without a synthetic campaign and keeps reading controls visible", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await isolated(async (url, root, seed) => {
    await page.goto(url);
    // The responsive navigation retains labeled buttons.
    const nav = page.getByRole("button", { name: "Learning", exact: true });
    if (!(await nav.isVisible()))
      await page.getByRole("button", { name: /navigation|menu/i }).click();
    await nav.click();
    await registration(page, seed);
    await expect(
      page.getByRole("heading", { name: "Recorded outcomes", exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: "/private/tmp/gtm-outcomes-mobile.png",
      fullPage: true,
    });
  });
});
