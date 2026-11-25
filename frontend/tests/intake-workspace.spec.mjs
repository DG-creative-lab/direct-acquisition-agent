import { test, expect } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const project = fileURLToPath(new URL("../..", import.meta.url));
async function isolated(run, seed = 0, planning = false) {
  const root = await mkdtemp(join(tmpdir(), "acquisition-intake-ui-"));
  const script = `
from acquisition.bootstrap import build_workspace
from acquisition.entrypoints.workspace import WorkspaceServer
from pathlib import Path
import sys
if sys.argv[4] == 'true':
 from test_intake_planning import IntakeModel
 model=IntakeModel()
 w=build_workspace(sys.argv[1],gateway_factory=lambda:model)
else:
 w=build_workspace(sys.argv[1])
for i in range(int(sys.argv[2])):
 w.intake.save('companies',{'request_id':'seed-'+str(i),'id':None,'expected_revision':0,'draft':{'company_name':'Saved company '+str(i)}})
s=WorkspaceServer(int(sys.argv[3]),w,Path('frontend/dist'))
print('http://127.0.0.1:'+str(s.server_port),flush=True)
s.serve_forever()
`;
  const roots = [root];
  let child, exited;
  async function start(directory, port = 0, seedCount = 0) {
    child = spawn(
      "python3",
      [
        "-c",
        script,
        directory,
        String(seedCount),
        String(port),
        String(planning),
      ],
      {
        cwd: project,
        env: {
          ...process.env,
          PYTHONPATH: "src:tests",
          OPENROUTER_API_KEY: "offline-tests-must-not-use-live-credentials",
        },
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    exited = new Promise((resolve) => child.once("exit", resolve));
    return await new Promise((resolve, reject) => {
      let output = "",
        errors = "";
      const timer = setTimeout(
        () => reject(new Error("Intake fixture did not start: " + errors)),
        15000,
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
      child.once("error", (error) => {
        clearTimeout(timer);
        reject(error);
      });
      child.once("exit", () => {
        clearTimeout(timer);
        reject(new Error(errors));
      });
    });
  }
  try {
    const url = await start(root, 0, seed);
    const restart = async (directory) => {
      child.kill("SIGTERM");
      await exited;
      if (!directory) {
        directory = await mkdtemp(join(tmpdir(), "acquisition-intake-other-"));
        roots.push(directory);
      }
      expect(await start(directory, Number(new URL(url).port))).toBe(url);
      return directory;
    };
    await run(url, root, restart);
  } finally {
    child?.kill("SIGTERM");
    await exited;
    for (const directory of roots)
      await rm(directory, { recursive: true, force: true });
  }
}

async function enter(page, url) {
  await page.goto(url);
  await page
    .getByRole("button", { name: "Company & brief", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Company & brief", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save company draft", exact: true }),
  ).toBeEnabled();
}
function rows(root) {
  const script = `
import sqlite3,json,sys
db=sqlite3.connect(sys.argv[1]+'/conversations.sqlite')
print(json.dumps({t:db.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall() for t in ('intake_company_revisions','intake_brief_revisions','intake_requests','runs','model_calls','review_decisions')}))
`;
  return JSON.parse(
    execFileSync("python3", ["-c", script, root], {
      cwd: project,
      encoding: "utf8",
    }),
  );
}
async function company(page, name = "Example company") {
  await page.getByLabel("Company name", { exact: true }).fill(name);
  await page
    .getByRole("button", { name: "Save company draft", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Company saved: version 1." }),
  ).toBeVisible();
}

for (const mobile of [false, true])
  test(`intake saves exact company and pinned campaign brief on ${mobile ? "mobile" : "desktop"}`, async ({
    page,
  }, testInfo) => {
    await isolated(async (url, root) => {
      await page.setViewportSize(
        mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
      );
      await enter(page, url);
      const wording =
        "Fast, flexible service \u2014 subject to eligibility. <img src=x onerror=alert(1)>";
      await page
        .getByLabel("Company name", { exact: true })
        .fill("Example \u2014 Company");
      await page.getByLabel("Company and product description").fill(wording);
      await page.getByRole("button", { name: "Add product claim" }).click();
      await page
        .getByLabel("Claim 1 statement", { exact: true })
        .fill("Exact claim \u2014 with qualification");
      await page
        .getByLabel("Claim 1 qualifications")
        .fill("UK businesses only");
      const refs = page.getByLabel("Company reference URLs");
      await refs.fill("https://example.invalid/one");
      await refs.press("End");
      await refs.press("Enter");
      await refs.pressSequentially("https://example.invalid/two");
      await expect(refs).toHaveValue(
        "https://example.invalid/one\nhttps://example.invalid/two",
      );
      await page
        .getByRole("button", { name: "Save company draft", exact: true })
        .click();
      await expect(
        page
          .getByRole("status")
          .filter({ hasText: "Company saved: version 1." }),
      ).toBeVisible();
      const companyId = rows(root).intake_company_revisions[0][1];
      await page.getByLabel("Company for this brief").selectOption(companyId);
      await expect(page.locator(".intake-pin")).toContainText(wording);
      await expect(page.locator(".intake-pin img")).toHaveCount(0);
      await page
        .getByLabel("Campaign objective", { exact: true })
        .fill("Find new customers \u2014 keep the qualification");
      await page.getByLabel("Requested country or market").fill("France");
      await page.getByLabel("Currency", { exact: true }).fill("EUR");
      await page.getByLabel("Requested channels").fill("video\nemail");
      await page.getByLabel("Budget in minor currency units").fill("12345");
      await page
        .getByLabel("Campaign constraints")
        .fill("Keep exact wording \u2014 do not shorten");
      await page.getByLabel("Synthetic contacts for testing").check();
      await page
        .getByRole("button", { name: "Save campaign brief", exact: true })
        .click();
      await expect(
        page.getByRole("status").filter({ hasText: "Brief saved: version 1." }),
      ).toBeVisible();
      const before = rows(root);
      const briefId = before.intake_brief_revisions[0][1];
      await page.reload();
      await page
        .getByRole("button", { name: "Company & brief", exact: true })
        .click();
      await page.getByLabel("Saved company drafts").selectOption(companyId);
      await expect(
        page.getByLabel("Company and product description"),
      ).toHaveValue(wording);
      await page.getByLabel("Saved campaign briefs").selectOption(briefId);
      await expect(
        page.getByLabel("Campaign objective", { exact: true }),
      ).toHaveValue("Find new customers \u2014 keep the qualification");
      await expect(page.getByLabel("Requested channels")).toHaveValue(
        "video\nemail",
      );
      await page
        .getByLabel("Company and product description")
        .fill("Later description");
      await page
        .getByRole("button", { name: "Save company draft", exact: true })
        .click();
      await expect(
        page
          .getByRole("status")
          .filter({ hasText: "Company saved: version 2." }),
      ).toBeVisible();
      await expect(
        page.getByLabel("Company version", { exact: true }),
      ).toHaveValue("1");
      await expect(page.locator(".intake-pin")).toContainText(wording);
      expect(rows(root).intake_brief_revisions).toEqual(
        before.intake_brief_revisions,
      );
      expect(rows(root).runs).toEqual([]);
      expect(rows(root).model_calls).toEqual([]);
      expect(rows(root).review_decisions).toEqual([]);
      await expect(page.getByLabel("Requested country or market")).toHaveValue(
        "France",
      );
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page
        .getByRole("heading", { name: "Company & brief", exact: true })
        .scrollIntoViewIfNeeded();
      await page.screenshot({
        path: testInfo.outputPath(
          `intake-${mobile ? "mobile" : "desktop"}.png`,
        ),
        fullPage: true,
      });
    });
  });

test("intake competing tabs retain edits and require an explicit latest-version reload", async ({
  page,
  context,
}) => {
  await isolated(async (url, root) => {
    await enter(page, url);
    await company(page);
    const id = rows(root).intake_company_revisions[0][1];
    const other = await context.newPage();
    await enter(other, url);
    await other.getByLabel("Saved company drafts").selectOption(id);
    await other
      .getByLabel("Company name", { exact: true })
      .fill("Other tab edit");
    await page.getByLabel("Company name", { exact: true }).fill("Winner");
    await page
      .getByRole("button", { name: "Save company draft", exact: true })
      .click();
    await expect(
      page.getByRole("status").filter({ hasText: "Company saved: version 2." }),
    ).toBeVisible();
    await other
      .getByRole("button", { name: "Save company draft", exact: true })
      .click();
    await expect(other.getByRole("alert")).toContainText(
      "reload before saving",
    );
    await expect(other.getByLabel("Company name", { exact: true })).toHaveValue(
      "Other tab edit",
    );
    expect(rows(root).intake_company_revisions).toHaveLength(2);
    await other
      .getByRole("button", { name: "Replace edits with latest company" })
      .click();
    await expect(other.getByLabel("Company name", { exact: true })).toHaveValue(
      "Winner",
    );
    await other.getByLabel("Company name", { exact: true }).fill("Resolved");
    await other
      .getByRole("button", { name: "Save company draft", exact: true })
      .click();
    await expect(
      other
        .getByRole("status")
        .filter({ hasText: "Company saved: version 3." }),
    ).toBeVisible();
    expect(rows(root).intake_company_revisions).toHaveLength(3);
    await other.close();
  });
});

test("intake lost brief acknowledgement preserves the pinned company and original command", async ({
  page,
}) => {
  await isolated(async (url, root) => {
    await enter(page, url);
    await company(page);
    const id = rows(root).intake_company_revisions[0][1];
    await page.getByLabel("Company for this brief").selectOption(id);
    await page
      .getByLabel("Campaign objective", { exact: true })
      .fill("Original brief \u2014 preserve wording");
    await page
      .getByLabel("Company name", { exact: true })
      .fill("Separate unsaved company edit");
    let original;
    await page.route("**/api/intake/briefs", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      original = route.request().postDataJSON();
      await route.fetch();
      await route.abort("failed");
    });
    await page
      .getByRole("button", { name: "Save campaign brief", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Retry original save" }),
    ).toBeEnabled();
    await page.unroute("**/api/intake/briefs");
    const warning = page.waitForEvent("dialog");
    const reload = page.reload();
    const leaving = await warning;
    expect(leaving.type()).toBe("beforeunload");
    await leaving.accept();
    await reload;
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await expect(
      page.getByLabel("Campaign objective", { exact: true }),
    ).toHaveValue("Original brief \u2014 preserve wording");
    const request = page.waitForRequest(
      (r) => r.method() === "POST" && r.url().endsWith("/api/intake/briefs"),
    );
    await page.getByRole("button", { name: "Retry original save" }).click();
    expect((await request).postDataJSON()).toEqual(original);
    await expect(
      page
        .getByRole("status")
        .filter({ hasText: "Brief original save confirmed: version 1." }),
    ).toBeVisible();
    await expect(page.getByLabel("Company for this brief")).toHaveValue(id);
    await expect(
      page.getByLabel("Company version", { exact: true }),
    ).toHaveValue("1");
    expect(rows(root).intake_brief_revisions).toHaveLength(1);
  });
});

test("intake lost committed save acknowledgement retries one original request after reload", async ({
  page,
}) => {
  await isolated(async (url, root) => {
    await enter(page, url);
    await page
      .getByLabel("Company name", { exact: true })
      .fill("Committed once");
    const sent = [];
    await page.route("**/api/intake/companies", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      sent.push(route.request().postDataJSON());
      const response = await route.fetch();
      expect(response.ok()).toBe(true);
      await route.fulfill({
        status: 500,
        json: { error: "Committed save acknowledgement unavailable" },
      });
    });
    await page
      .getByRole("button", { name: "Save company draft", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Retry original save" }),
    ).toBeEnabled();
    expect(rows(root).intake_company_revisions).toHaveLength(1);
    await page.unroute("**/api/intake/companies");
    await page.reload();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await expect(page.getByLabel("Company name", { exact: true })).toHaveValue(
      "Committed once",
    );
    await expect(
      page.getByRole("button", { name: "Save company draft", exact: true }),
    ).toBeDisabled();
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        request.url().endsWith("/api/intake/companies")
      )
        sent.push(request.postDataJSON());
    });
    await page.getByRole("button", { name: "Retry original save" }).click();
    await expect(
      page
        .getByRole("status")
        .filter({ hasText: "Company original save confirmed: version 1." }),
    ).toBeVisible();
    expect(sent).toHaveLength(2);
    expect(sent[0]).toEqual(sent[1]);
    expect(rows(root).intake_company_revisions).toHaveLength(1);
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("workspace-intake-save:v1"),
      ),
    ).toBeNull();
  });
});

test("intake uncertain edit recovery keeps its target after a competing edit", async ({
  page,
  context,
}) => {
  await isolated(async (url, root) => {
    await enter(page, url);
    await company(page);
    const id = rows(root).intake_company_revisions[0][1];
    await page
      .getByLabel("Company name", { exact: true })
      .fill("Uncertain edit");
    await page.route("**/api/intake/companies", (route) =>
      route.request().method() === "POST"
        ? route.abort("failed")
        : route.continue(),
    );
    await page
      .getByRole("button", { name: "Save company draft", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Retry original save" }),
    ).toBeEnabled();
    const other = await context.newPage();
    await enter(other, url);
    await other.getByLabel("Saved company drafts").selectOption(id);
    await other
      .getByLabel("Company name", { exact: true })
      .fill("Other writer");
    await other
      .getByRole("button", { name: "Save company draft", exact: true })
      .click();
    await expect(
      other
        .getByRole("status")
        .filter({ hasText: "Company saved: version 2." }),
    ).toBeVisible();
    await page.unroute("**/api/intake/companies");
    await page.reload();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await page.getByRole("button", { name: "Retry original save" }).click();
    await expect(page.getByRole("alert")).toContainText("reload before saving");
    await expect(page.getByLabel("Company name", { exact: true })).toHaveValue(
      "Uncertain edit",
    );
    const request = page.waitForRequest(
      (r) => r.method() === "POST" && r.url().endsWith("/api/intake/companies"),
    );
    await page
      .getByRole("button", { name: "Save company draft", exact: true })
      .click();
    expect((await request).postDataJSON().id).toBe(id);
    await expect(page.getByRole("alert")).toContainText("reload before saving");
    expect(rows(root).intake_company_revisions).toHaveLength(2);
    await other.close();
  });
});

test("intake storage failure and corrupt recovery data block new saves", async ({
  page,
}) => {
  await isolated(async (url, root) => {
    await enter(page, url);
    await page
      .getByLabel("Company name", { exact: true })
      .fill("Do not dispatch");
    await page.evaluate(() => {
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key, value) {
        if (key === "workspace-intake-save:v1")
          throw new Error("Save storage unavailable");
        return original.call(this, key, value);
      };
    });
    await page
      .getByRole("button", { name: "Save company draft", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "Save storage unavailable",
    );
    expect(rows(root).intake_company_revisions).toEqual([]);
    page.once("dialog", (dialog) => dialog.accept());
    await page.reload();
    await page.evaluate(() =>
      sessionStorage.setItem(
        "workspace-intake-save:v1",
        JSON.stringify({
          store_id: "store_corrupt_test",
          kind: "companies",
          payload: {
            id: null,
            expected_revision: 0,
            request_id: "corrupt",
            draft: { claims: "invalid" },
          },
          base: null,
        }),
      ),
    );
    await page.reload();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "original save could not be restored",
    );
    await expect(
      page.getByRole("button", { name: "Save company draft", exact: true }),
    ).toBeDisabled();
    expect(rows(root).intake_company_revisions).toEqual([]);
  });
});

test("intake loads saved companies beyond its first bounded page", async ({
  page,
}) => {
  await isolated(async (url) => {
    await enter(page, url);
    const list = page.getByLabel("Saved company drafts");
    await expect(list.locator("option")).toHaveCount(51);
    await page.getByRole("button", { name: "Load more companies" }).click();
    await expect(list.locator("option")).toHaveCount(53);
    await expect(
      page.getByRole("button", { name: "Load more companies" }),
    ).toHaveCount(0);
  }, 52);
});

test("intake oversized drafts stay editable before dispatch including Unicode serialization", async ({
  page,
}) => {
  await isolated(async (url, root) => {
    await enter(page, url);
    const posts = [];
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        request.url().endsWith("/api/intake/companies")
      )
        posts.push(request);
    });
    await page.getByLabel("Company name", { exact: true }).fill("Large draft");
    await page
      .getByLabel("Company and product description")
      .fill("x".repeat(8000));
    await page
      .getByLabel("Company reference URLs")
      .fill(
        Array.from(
          { length: 20 },
          (_, i) => "https://example.invalid/" + "x".repeat(1960) + i,
        ).join("\n"),
      );
    for (let i = 1; i <= 3; i++) {
      await page.getByRole("button", { name: "Add product claim" }).click();
      await page
        .getByLabel(`Claim ${i} statement`, { exact: true })
        .fill("s".repeat(4000));
      await page
        .getByLabel(`Claim ${i} qualifications`, { exact: true })
        .fill("q".repeat(4000));
    }
    await page
      .getByRole("button", { name: "Save company draft", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText("too large to save");
    expect(posts).toHaveLength(0);
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("workspace-intake-save:v1"),
      ),
    ).toBeNull();
    await expect(
      page.getByLabel("Company name", { exact: true }),
    ).toBeEditable();
    expect(rows(root).intake_company_revisions).toEqual([]);
    await page.getByLabel("Company reference URLs").fill("");
    await page
      .getByRole("button", { name: "Save company draft", exact: true })
      .click();
    await expect(
      page.getByRole("status").filter({ hasText: "Company saved: version 1." }),
    ).toBeVisible();
    await page
      .getByLabel("Company and product description")
      .fill("é".repeat(8000));
    await page
      .getByRole("button", { name: "Save company draft", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText("too large to save");
    expect(posts).toHaveLength(1);
    await expect(
      page.getByLabel("Company and product description"),
    ).toHaveValue("é".repeat(8000));
    expect(rows(root).intake_company_revisions).toHaveLength(1);
  });
});

test("intake validates after interaction and ignores a stale company-version preview", async ({
  page,
}) => {
  await isolated(async (url, root) => {
    await enter(page, url);
    await expect(page.locator(".intake-field-error")).toHaveCount(0);
    await page
      .getByRole("button", { name: "Save campaign brief", exact: true })
      .click();
    await expect(page.getByLabel("Company for this brief")).toBeFocused();
    await expect(page.getByLabel("Company for this brief")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    await company(page, "First company");
    const id = rows(root).intake_company_revisions[0][1];
    await page
      .getByLabel("Company name", { exact: true })
      .fill("Latest company");
    await page
      .getByRole("button", { name: "Save company draft", exact: true })
      .click();
    await expect(
      page.getByRole("status").filter({ hasText: "Company saved: version 2." }),
    ).toBeVisible();
    let release;
    const held = new Promise((resolve) => {
      release = resolve;
    });
    let arrived;
    const requested = new Promise((resolve) => {
      arrived = resolve;
    });
    let finished;
    const delivered = new Promise((resolve) => {
      finished = resolve;
    });
    await page.route(
      `**/api/intake/companies/${id}?revision=1`,
      async (route) => {
        const response = await route.fetch();
        arrived();
        await held;
        try {
          await route.fulfill({ response });
        } catch {
          /* The UI deliberately aborted this stale read. */
        } finally {
          finished();
        }
      },
    );
    await page.getByLabel("Company for this brief").selectOption(id);
    await expect(page.locator(".intake-pin")).toContainText(
      "Latest company, version 2",
    );
    await page.getByLabel("Company version", { exact: true }).fill("1");
    await requested;
    await page.getByLabel("Company version", { exact: true }).fill("2");
    await expect(page.locator(".intake-pin")).toContainText(
      "Latest company, version 2",
    );
    release();
    await delivered;
    await page.evaluate(
      () =>
        new Promise((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(resolve)),
        ),
    );
    await expect(page.locator(".intake-pin")).toContainText(
      "Latest company, version 2",
    );
    await page.unroute(`**/api/intake/companies/${id}?revision=1`);
    await page.getByLabel("Company version", { exact: true }).fill("1");
    await expect(page.locator(".intake-pin")).toContainText(
      "First company, version 1",
    );
    await page
      .getByLabel("Company website", { exact: true })
      .fill("invalid-url");
    await page
      .getByRole("button", { name: "Save company draft", exact: true })
      .click();
    await expect(
      page.getByLabel("Company website", { exact: true }),
    ).toBeFocused();
    await expect(
      page.getByLabel("Company website", { exact: true }),
    ).toHaveAttribute("aria-invalid", "true");
    expect(rows(root).intake_company_revisions).toHaveLength(2);
    const dialog = page.waitForEvent("dialog");
    const reloading = page.reload().catch(() => null);
    const warning = await dialog;
    expect(warning.type()).toBe("beforeunload");
    await warning.accept();
    await reloading;
    // Explicitly leaving discards unsaved fields; only saved database revisions are durable.
    expect(rows(root).intake_company_revisions).toHaveLength(2);
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await page.getByLabel("Saved company drafts").selectOption(id);
    await expect(page.getByLabel("Company name", { exact: true })).toHaveValue(
      "Latest company",
    );
  });
});

test("intake original recovery refuses another store at the same origin and resumes on its original store", async ({
  page,
}) => {
  await isolated(async (url, root, restart) => {
    await enter(page, url);
    await page.getByLabel("Company name", { exact: true }).fill("Belongs to A");
    await page.route("**/api/intake/companies", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      const response = await route.fetch();
      expect(response.ok()).toBe(true);
      await route.fulfill({
        status: 500,
        json: { error: "Lost original acknowledgement" },
      });
    });
    await page
      .getByRole("button", { name: "Save company draft", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Retry original save" }),
    ).toBeEnabled();
    const stored = await page.evaluate(() =>
      sessionStorage.getItem("workspace-intake-save:v1"),
    );
    // Older recovery data has no provable owner. Never guess the current store.
    const legacy = JSON.parse(stored);
    delete legacy.store_id;
    await page.evaluate(
      (value) => sessionStorage.setItem("workspace-intake-save:v1", value),
      JSON.stringify(legacy),
    );
    await page.reload();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "original save could not be restored",
    );
    await expect(
      page.getByRole("button", { name: "Save company draft", exact: true }),
    ).toBeDisabled();
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("workspace-intake-save:v1"),
      ),
    ).toBe(JSON.stringify(legacy));
    await page.evaluate(
      (value) => sessionStorage.setItem("workspace-intake-save:v1", value),
      stored,
    );
    const before = rows(root);
    expect(before.intake_company_revisions).toHaveLength(1);
    await page.unroute("**/api/intake/companies");
    const otherRoot = await restart();
    await page.reload();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    let posts = 0;
    const count = (request) => {
      if (
        request.method() === "POST" &&
        request.url().endsWith("/api/intake/companies")
      )
        posts++;
    };
    page.on("request", count);
    await page.getByRole("button", { name: "Retry original save" }).click();
    await expect(page.getByRole("alert")).toContainText(
      "original workspace store",
    );
    expect(posts).toBe(0);
    expect(rows(otherRoot).intake_company_revisions).toEqual([]);
    expect(rows(otherRoot).intake_requests).toEqual([]);
    expect(rows(root)).toEqual(before);
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("workspace-intake-save:v1"),
      ),
    ).toBe(stored);
    await expect(
      page.getByRole("button", { name: "Save company draft", exact: true }),
    ).toBeDisabled();
    // A stale preflight (or a switch after it) still cannot write to B.
    await page.route("**/api/intake/store", (route) =>
      route.fulfill({ json: { store_id: JSON.parse(stored).store_id } }),
    );
    await page.getByRole("button", { name: "Retry original save" }).click();
    await expect.poll(() => posts).toBe(1);
    await expect(page.getByRole("alert")).toContainText(
      "original workspace store",
    );
    await expect(
      page.getByRole("button", { name: "Retry original save" }),
    ).toBeEnabled();
    expect(rows(otherRoot).intake_requests).toEqual([]);
    expect(rows(otherRoot).intake_company_revisions).toEqual([]);
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("workspace-intake-save:v1"),
      ),
    ).toBe(stored);
    await page.unroute("**/api/intake/store");
    await restart(root);
    await page.reload();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await page.getByRole("button", { name: "Retry original save" }).click();
    await expect(
      page
        .getByRole("status")
        .filter({ hasText: "Company original save confirmed: version 1." }),
    ).toBeVisible();
    expect(rows(root)).toEqual(before);
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("workspace-intake-save:v1"),
      ),
    ).toBeNull();
    page.off("request", count);
  });
});

async function planningBrief(page, root) {
  await page
    .getByLabel("Company and product description")
    .fill("User assertion about consultancy services.");
  await company(page, "Aster Consultancy");
  const companyId = rows(root).intake_company_revisions[0][1];
  await page.getByLabel("Company for this brief").selectOption(companyId);
  await page
    .getByLabel("Campaign objective", { exact: true })
    .fill("Find independent retail clients");
  await page
    .getByLabel("Audience requirements")
    .fill("Independent UK retailers");
  await page.getByLabel("Requested country or market").fill("UK");
  await page.getByLabel("Currency", { exact: true }).fill("GBP");
  await page.getByLabel("Requested channels").fill("email");
  await page.getByLabel("Budget in minor currency units").fill("12345");
  await page
    .getByRole("button", { name: "Save campaign brief", exact: true })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "Brief saved: version 1." }),
  ).toBeVisible();
}
function planSources(root) {
  return JSON.parse(
    execFileSync(
      "python3",
      [
        "-c",
        `
import json,sqlite3,sys
db=sqlite3.connect(sys.argv[1]+'/conversations.sqlite')
print(json.dumps([json.loads(row[0]) for row in db.execute('SELECT source FROM intake_planning_sources ORDER BY revision')]))
`,
        root,
      ],
      { cwd: project, encoding: "utf8" },
    ),
  );
}
for (const mobile of [false, true])
  test(`intake interpretation binds the saved source and explicit consent on ${mobile ? "mobile" : "desktop"}`, async ({
    page,
  }, testInfo) => {
    await isolated(
      async (url, root) => {
        await page.setViewportSize(
          mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
        );
        await enter(page, url);
        await planningBrief(page, root);
        const button = page.getByRole("button", {
          name: "Prepare a plan",
          exact: true,
        });
        await button.click();
        await expect(
          page.getByLabel(
            "Allow up to two planning model calls for this saved brief",
          ),
        ).toBeFocused();
        expect(planSources(root)).toHaveLength(0);
        expect(rows(root).model_calls).toHaveLength(0);
        await page
          .getByLabel(
            "Allow up to two planning model calls for this saved brief",
          )
          .check();
        await button.click();
        await expect(
          page.getByRole("heading", { name: "Proposed approach", exact: true }),
        ).toBeVisible();
        expect(planSources(root)).toHaveLength(1);
        expect(rows(root).model_calls).toHaveLength(1);
        await expect(button).toBeDisabled();
        await page.getByText("Exact source used", { exact: true }).click();
        const sourceDetails = page.getByRole("region", {
          name: "Plan from this brief",
          exact: true,
        });
        await expect(sourceDetails).toContainText("Aster Consultancy");
        await expect(sourceDetails).toContainText("Independent UK retailers");
        await expect(sourceDetails).toContainText("12345");
        expect(rows(root).review_decisions).toHaveLength(0);
        const briefId = planSources(root)[0].brief_id;
        await page.reload();
        await page
          .getByRole("button", { name: "Company & brief", exact: true })
          .click();
        await page.getByLabel("Saved campaign briefs").selectOption(briefId);
        await expect(
          page.getByRole("heading", { name: "Proposed approach", exact: true }),
        ).toBeVisible();
        await page
          .getByLabel("Campaign objective", { exact: true })
          .fill("A revised retail objective");
        await expect(button).toBeDisabled();
        await page
          .getByRole("button", { name: "Save campaign brief", exact: true })
          .click();
        await expect(
          page.getByRole("heading", {
            name: "Historical interpretation",
            exact: true,
          }),
        ).toBeVisible();
        expect(rows(root).model_calls).toHaveLength(1);
        await page
          .getByLabel(
            "Allow up to two planning model calls for this saved brief",
          )
          .check();
        await button.click();
        await expect(
          page.getByRole("heading", {
            name: "Saved interpretation",
            exact: true,
          }),
        ).toBeVisible();
        expect(planSources(root)).toHaveLength(2);
        expect(rows(root).model_calls).toHaveLength(2);
        await page
          .getByRole("region", { name: "Plan from this brief", exact: true })
          .screenshot({
            path: testInfo.outputPath(
              `intake-planning-${mobile ? "mobile" : "desktop"}.png`,
            ),
          });
      },
      0,
      true,
    );
  });

test("intake interpretation recovers a lost reply across different-root and original-root restarts without another model call", async ({
  page,
}) => {
  await isolated(
    async (url, root, restart) => {
      await enter(page, url);
      await planningBrief(page, root);
      await page
        .getByLabel("Allow up to two planning model calls for this saved brief")
        .check();
      let posts = 0;
      await page.route("**/api/intake/plans", async (route) => {
        if (route.request().method() !== "POST") return route.continue();
        posts++;
        const response = await route.fetch();
        expect(response.ok()).toBe(true);
        await route.fulfill({
          status: 500,
          json: { error: "Lost interpretation response" },
        });
      });
      await page
        .getByRole("button", { name: "Prepare a plan", exact: true })
        .click();
      await expect(
        page.getByRole("button", {
          name: "Retry original planning request",
          exact: true,
        }),
      ).toBeEnabled();
      const raw = await page.evaluate(() =>
        sessionStorage.getItem("workspace-intake-plan:v1"),
      );
      expect(planSources(root)).toHaveLength(1);
      expect(rows(root).model_calls).toHaveLength(1);
      await page.unroute("**/api/intake/plans");
      const other = await restart();
      await page.reload();
      await page
        .getByRole("button", { name: "Company & brief", exact: true })
        .click();
      await page
        .getByRole("button", {
          name: "Retry original planning request",
          exact: true,
        })
        .click();
      await expect(page.getByRole("alert")).toContainText(
        "original workspace store",
      );
      expect(planSources(other)).toHaveLength(0);
      expect(rows(other).model_calls).toHaveLength(0);
      expect(
        await page.evaluate(() =>
          sessionStorage.getItem("workspace-intake-plan:v1"),
        ),
      ).toBe(raw);
      await restart(root);
      await page.reload();
      await page
        .getByRole("button", { name: "Company & brief", exact: true })
        .click();
      page.on("request", (request) => {
        if (
          request.method() === "POST" &&
          request.url().endsWith("/api/intake/plans")
        )
          posts++;
      });
      await page
        .getByRole("button", {
          name: "Retry original planning request",
          exact: true,
        })
        .click();
      await expect(
        page.getByRole("heading", { name: "Proposed approach", exact: true }),
      ).toBeVisible();
      expect(posts).toBe(1);
      expect(rows(root).model_calls).toHaveLength(1);
      expect(planSources(root)).toHaveLength(1);
      expect(
        await page.evaluate(() =>
          sessionStorage.getItem("workspace-intake-plan:v1"),
        ),
      ).toBeNull();
    },
    0,
    true,
  );
});

test("intake interpretation preserves unsupported requirements and partial briefs without model calls", async ({
  page,
}) => {
  await isolated(
    async (url, root) => {
      await enter(page, url);
      await planningBrief(page, root);
      await page.getByLabel("Requested country or market").fill("France");
      await page.getByLabel("Currency", { exact: true }).fill("EUR");
      await page.getByLabel("Requested channels").fill("video");
      await page
        .getByRole("button", { name: "Save campaign brief", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: "Before planning", exact: true }),
      ).toBeVisible();
      await page
        .getByLabel("Allow up to two planning model calls for this saved brief")
        .check();
      await page
        .getByRole("button", { name: "Prepare a plan", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "Unsupported requirements",
          exact: true,
        }),
      ).toBeVisible();
      expect(rows(root).model_calls).toHaveLength(0);
      await page.getByText("Exact source used", { exact: true }).click();
      await expect(
        page.getByRole("region", { name: "Plan from this brief", exact: true }),
      ).toContainText("France");
      await expect(
        page.getByRole("region", { name: "Plan from this brief", exact: true }),
      ).toContainText("EUR");
      await expect(
        page.getByRole("region", { name: "Plan from this brief", exact: true }),
      ).toContainText("video");
      await page.getByLabel("Requested country or market").fill("UK");
      await page.getByLabel("Currency", { exact: true }).fill("GBP");
      await page.getByLabel("Requested channels").fill("email");
      await page.getByLabel("Campaign objective", { exact: true }).fill("");
      await page
        .getByRole("button", { name: "Save campaign brief", exact: true })
        .click();
      await expect(
        page.getByRole("status").filter({ hasText: "Brief saved: version 3." }),
      ).toBeVisible();
      await page
        .getByLabel("Allow up to two planning model calls for this saved brief")
        .check();
      await page
        .getByRole("button", { name: "Prepare a plan", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "Clarification needed",
          exact: true,
        }),
      ).toBeVisible();
      expect(rows(root).model_calls).toHaveLength(0);
    },
    0,
    true,
  );
});

test("intake planning waits for the selected revision history and competing tabs cannot repeat its model work", async ({
  page,
  context,
}) => {
  await isolated(
    async (url, root) => {
      await enter(page, url);
      await planningBrief(page, root);
      const briefId = JSON.parse(
        execFileSync(
          "python3",
          [
            "-c",
            `
import json,sqlite3,sys
r=sqlite3.connect(sys.argv[1]+'/conversations.sqlite').execute('SELECT payload FROM intake_brief_revisions').fetchone()
print(json.dumps(json.loads(r[0])['id']))
`,
            root,
          ],
          { cwd: project, encoding: "utf8" },
        ),
      );
      const peer = await context.newPage();
      await enter(peer, url);
      let releaseHistory;
      const historyGate = new Promise((resolve) => (releaseHistory = resolve));
      let historyArrived;
      const historyCaptured = new Promise(
        (resolve) => (historyArrived = resolve),
      );
      await peer.route("**/api/intake/plans?brief_id=*", async (route) => {
        const response = await route.fetch();
        historyArrived();
        await historyGate;
        await route.fulfill({ response });
      });
      await peer.getByLabel("Saved campaign briefs").selectOption(briefId);
      await historyCaptured;
      await expect(
        peer.getByRole("button", { name: "Prepare a plan", exact: true }),
      ).toBeDisabled();
      expect(planSources(root)).toHaveLength(0);
      releaseHistory();
      const startA = page.getByRole("button", {
        name: "Prepare a plan",
        exact: true,
      });
      const startB = peer.getByRole("button", {
        name: "Prepare a plan",
        exact: true,
      });
      await expect(startB).toBeEnabled();
      await page
        .getByLabel("Allow up to two planning model calls for this saved brief")
        .check();
      await peer
        .getByLabel("Allow up to two planning model calls for this saved brief")
        .check();
      let release;
      const gate = new Promise((resolve) => (release = resolve));
      let captured;
      const arrived = new Promise((resolve) => (captured = resolve));
      await page.route("**/api/intake/plans", async (route) => {
        if (route.request().method() !== "POST") return route.continue();
        captured();
        await gate;
        await route.continue();
      });
      await startA.click();
      await arrived;
      await startB.click();
      await expect(
        peer.getByRole("heading", { name: "Proposed approach", exact: true }),
      ).toBeVisible();
      release();
      await expect(page.getByRole("alert")).toContainText(
        "already has a planning request",
      );
      expect(planSources(root)).toHaveLength(1);
      expect(rows(root).model_calls).toHaveLength(1);
      expect(
        await page.evaluate(() =>
          sessionStorage.getItem("workspace-intake-plan:v1"),
        ),
      ).toBeNull();
      await page.unroute("**/api/intake/plans");
      await page
        .getByRole("button", { name: "Reload planning history", exact: true })
        .click();
      await expect(
        page.getByRole("heading", { name: "Proposed approach", exact: true }),
      ).toBeVisible();
      await peer.close();
    },
    0,
    true,
  );
});

test("intake planning blocks dispatch when recovery storage is unavailable or corrupt", async ({
  page,
}) => {
  await isolated(
    async (url, root) => {
      await enter(page, url);
      await planningBrief(page, root);
      await page.evaluate(() => {
        const original = Storage.prototype.setItem;
        Storage.prototype.setItem = function (key, value) {
          if (key === "workspace-intake-plan:v1")
            throw new Error("Planning recovery storage unavailable");
          return original.call(this, key, value);
        };
      });
      await page
        .getByLabel("Allow up to two planning model calls for this saved brief")
        .check();
      await page
        .getByRole("button", { name: "Prepare a plan", exact: true })
        .click();
      await expect(page.getByRole("alert")).toContainText(
        "Planning recovery storage unavailable",
      );
      expect(planSources(root)).toHaveLength(0);
      expect(rows(root).model_calls).toHaveLength(0);
      await page.reload();
      await page.evaluate(() =>
        sessionStorage.setItem(
          "workspace-intake-plan:v1",
          '{"payload":{"request_id":"old"}}',
        ),
      );
      await page.reload();
      await page
        .getByRole("button", { name: "Company & brief", exact: true })
        .click();
      await expect(page.getByRole("alert")).toContainText(
        "original planning request could not be restored",
      );
      await expect(
        page.getByRole("button", { name: "Save company draft", exact: true }),
      ).toBeDisabled();
      expect(planSources(root)).toHaveLength(0);
      expect(rows(root).model_calls).toHaveLength(0);
      expect(
        await page.evaluate(() =>
          sessionStorage.getItem("workspace-intake-plan:v1"),
        ),
      ).toBe('{"payload":{"request_id":"old"}}');
    },
    0,
    true,
  );
});
