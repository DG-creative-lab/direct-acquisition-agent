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

function preparationRows(root) {
  return JSON.parse(
    execFileSync(
      "python3",
      [
        "-c",
        `
import json,sqlite3,sys
with sqlite3.connect(sys.argv[1]+'/conversations.sqlite') as db:
 print(json.dumps([json.loads(row[0]) for row in db.execute('SELECT payload FROM preparation_contexts ORDER BY revision')]))
`,
        root,
      ],
      { cwd: project, encoding: "utf8" },
    ),
  );
}
async function choosePreparation(
  page,
  note = "Checked the exact source wording.",
) {
  const area = page.getByRole("region", {
    name: "Review preparation context",
    exact: true,
  });
  await expect(
    area.getByRole("button", {
      name: "Save reviewed preparation context",
      exact: true,
    }),
  ).toBeEnabled();
  await area
    .getByLabel("Include the saved company description", { exact: true })
    .check();
  await area
    .getByLabel("Input review note (required)", { exact: true })
    .fill(note);
  await area
    .getByLabel(
      "I reviewed these exact selected inputs. This does not verify claims or approve a campaign.",
      { exact: true },
    )
    .check();
  return area;
}
for (const mobile of [false, true])
  test(`preparation context preserves selected wording and review history on ${mobile ? "mobile" : "desktop"}`, async ({
    page,
  }, testInfo) => {
    await isolated(async (url, root) => {
      await page.setViewportSize(
        mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
      );
      await enter(page, url);
      await planningBrief(page, root);
      const area = page.getByRole("region", {
        name: "Review preparation context",
        exact: true,
      });
      const save = area.getByRole("button", {
        name: "Save reviewed preparation context",
        exact: true,
      });
      await expect(save).toBeEnabled();
      await save.click();
      await expect(
        area.getByLabel("Input review note (required)"),
      ).toBeFocused();
      expect(preparationRows(root)).toHaveLength(0);
      await choosePreparation(page, "Reviewed user wording — preserved.");
      await save.click();
      await expect(
        area.getByRole("heading", {
          name: "Saved preparation input review",
          exact: true,
        }),
      ).toBeVisible();
      const record = preparationRows(root)[0];
      expect(record.selection.review_note).toBe(
        "Reviewed user wording — preserved.",
      );
      expect(record.selected_inputs.description).toBe(
        "User assertion about consultancy services.",
      );
      expect(record.verification).toBe("user_supplied_unverified");
      expect(rows(root).model_calls).toHaveLength(0);
      expect(rows(root).review_decisions).toHaveLength(0);
      await area
        .getByText("Exact reviewed preparation inputs", { exact: true })
        .click();
      await expect(area).toContainText("Aster Consultancy");
      await expect(area).toContainText("12345");
      await area.screenshot({
        path: testInfo.outputPath(
          `preparation-context-${mobile ? "mobile" : "desktop"}.png`,
        ),
      });
      const briefId = record.source.brief.id;
      await page.reload();
      await page
        .getByRole("button", { name: "Company & brief", exact: true })
        .click();
      await page.getByLabel("Saved campaign briefs").selectOption(briefId);
      await expect(
        area.getByRole("heading", {
          name: "Saved preparation input review",
          exact: true,
        }),
      ).toBeVisible();
      await page
        .getByLabel("Campaign objective", { exact: true })
        .fill("Changed objective.");
      await expect(save).toBeDisabled();
      await page
        .getByRole("button", { name: "Save campaign brief", exact: true })
        .click();
      await expect(
        page.getByRole("status").filter({ hasText: "Brief saved: version 2." }),
      ).toBeVisible();
      await expect(area).toContainText("Review required or historical");
      await expect(
        area.getByLabel(
          "I reviewed these exact selected inputs. This does not verify claims or approve a campaign.",
        ),
      ).not.toBeChecked();
      await choosePreparation(page, "Review the changed brief.");
      await save.click();
      await expect(area).toContainText("Context version 2");
      expect(preparationRows(root)).toHaveLength(2);
      expect(preparationRows(root)[0].requirements.objective).toBe(
        "Find independent retail clients",
      );
      expect(preparationRows(root)[1].requirements.objective).toBe(
        "Changed objective.",
      );
    });
  });

test("preparation review keeps the original receipt and expiry after a lost reply and store switches", async ({
  page,
}) => {
  await isolated(async (url, root, restart) => {
    await enter(page, url);
    await planningBrief(page, root);
    const area = await choosePreparation(page);
    await page.route("**/api/intake/contexts", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await route.fetch();
      await route.abort("failed");
    });
    await area
      .getByRole("button", {
        name: "Save reviewed preparation context",
        exact: true,
      })
      .click();
    await expect(
      area.getByRole("button", {
        name: "Retry original preparation review",
        exact: true,
      }),
    ).toBeVisible();
    await expect.poll(() => preparationRows(root).length).toBe(1);
    await expect(
      area.getByRole("button", {
        name: "Retry original preparation review",
        exact: true,
      }),
    ).toBeEnabled();
    const original = preparationRows(root)[0];
    const pending = await page.evaluate(() =>
      sessionStorage.getItem("workspace-preparation-review:v1"),
    );
    expect(pending).not.toBeNull();
    await expect(
      page.getByRole("button", { name: "Save campaign brief", exact: true }),
    ).toBeDisabled();
    await page.unroute("**/api/intake/contexts");
    await restart();
    await page.reload();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    let posts = 0;
    page.on("request", (r) => {
      if (r.method() === "POST" && r.url().endsWith("/api/intake/contexts"))
        posts++;
    });
    await area
      .getByRole("button", {
        name: "Retry original preparation review",
        exact: true,
      })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "Restore the original workspace store",
    );
    expect(posts).toBe(0);
    expect(preparationRows(root)).toEqual([original]);
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("workspace-preparation-review:v1"),
      ),
    ).toBe(pending);
    await restart(root);
    const identityRequested = Promise.withResolvers();
    const releaseIdentity = Promise.withResolvers();
    await page.route("**/api/intake/store", async (route) => {
      const response = await route.fetch();
      identityRequested.resolve();
      await releaseIdentity.promise;
      await route.fulfill({ response });
    });
    await page.reload();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await identityRequested.promise;
    const retry = area.getByRole("button", {
      name: "Retry original preparation review",
      exact: true,
    });
    await expect(retry).toBeDisabled();
    releaseIdentity.resolve();
    await expect(retry).toBeEnabled();
    await page.unroute("**/api/intake/store");
    await area
      .getByRole("button", {
        name: "Retry original preparation review",
        exact: true,
      })
      .click();
    await expect(
      area.getByRole("heading", {
        name: "Saved preparation input review",
        exact: true,
      }),
    ).toBeVisible();
    expect(posts).toBe(0);
    expect(preparationRows(root)).toEqual([original]);
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("workspace-preparation-review:v1"),
      ),
    ).toBeNull();
  });
});

test("reconciling an older preparation receipt preserves the newer current review", async ({
  page,
  context,
}) => {
  await isolated(async (url, root) => {
    await enter(page, url);
    await planningBrief(page, root);
    const area = await choosePreparation(page, "The original input review.");
    let posts = 0;
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        request.url().endsWith("/api/intake/contexts")
      )
        posts++;
    });
    await page.route("**/api/intake/contexts", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await route.fetch();
      await route.abort("failed");
    });
    await area
      .getByRole("button", {
        name: "Save reviewed preparation context",
        exact: true,
      })
      .click();
    await expect.poll(() => preparationRows(root).length).toBe(1);
    const retry = area.getByRole("button", {
      name: "Retry original preparation review",
      exact: true,
    });
    await expect(retry).toBeEnabled();
    const original = preparationRows(root)[0];
    await page.unroute("**/api/intake/contexts");

    const peer = await context.newPage();
    await enter(peer, url);
    await peer
      .getByLabel("Saved campaign briefs")
      .selectOption(original.source.brief.id);
    const other = await choosePreparation(
      peer,
      "The newer current input review.",
    );
    await other
      .getByRole("button", {
        name: "Save reviewed preparation context",
        exact: true,
      })
      .click();
    await expect(other).toContainText("Context version 2");
    const saved = preparationRows(root);
    expect(saved).toHaveLength(2);

    // Navigation reloads authoritative history while the original receipt is pending.
    await page.getByRole("button", { name: "Knowledge", exact: true }).click();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await expect(area).toContainText("The newer current input review.");
    await expect(area).toContainText(
      "Current when last checked. Context version 2",
    );
    await retry.click();
    await expect(area).toContainText("The original input review.");
    await expect(retry).toHaveCount(0);
    const history = area.getByLabel("Preparation review history (latest 20)");
    await history.selectOption(saved[1].request_id);
    await expect(area).toContainText(
      "Current when last checked. Context version 2",
    );
    await expect(history.locator("option")).toHaveText([
      "Context version 2 / brief version 1",
      "Context version 1 / brief version 1",
    ]);
    await history.selectOption(original.request_id);
    await expect(area).toContainText(
      "Review required or historical. Context version 1",
    );
    expect(preparationRows(root)).toEqual(saved);
    expect(posts).toBe(1);
    expect(rows(root).model_calls).toHaveLength(0);
    expect(rows(root).review_decisions).toHaveLength(0);
    await peer.close();
  });
});

test("a delayed preparation history read cannot erase a confirmed receipt", async ({
  page,
}) => {
  await isolated(async (url, root) => {
    await enter(page, url);
    await planningBrief(page, root);
    const area = await choosePreparation(page);
    const postRequested = Promise.withResolvers();
    const releasePost = Promise.withResolvers();
    const historyRequested = Promise.withResolvers();
    const releaseHistory = Promise.withResolvers();
    const historyFinished = Promise.withResolvers();
    await page.route("**/api/intake/contexts", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      postRequested.resolve();
      await releasePost.promise;
      await route.continue();
    });
    await area
      .getByRole("button", {
        name: "Save reviewed preparation context",
        exact: true,
      })
      .click();
    await postRequested.promise;
    await page.route("**/api/intake/contexts?brief_id=*", async (route) => {
      const response = await route.fetch();
      expect((await response.json()).items).toEqual([]);
      historyRequested.resolve();
      await releaseHistory.promise;
      try {
        await route.fulfill({ response });
      } catch {
        // Confirmation can deliberately cancel this obsolete read.
      } finally {
        historyFinished.resolve();
      }
    });
    await page.getByRole("button", { name: "Knowledge", exact: true }).click();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await historyRequested.promise;
    releasePost.resolve();
    await expect(
      area.getByRole("heading", {
        name: "Saved preparation input review",
        exact: true,
      }),
    ).toBeVisible();
    const saved = preparationRows(root);
    expect(saved).toHaveLength(1);
    releaseHistory.resolve();
    await historyFinished.promise;
    await page.evaluate(
      () =>
        new Promise((resolve) =>
          requestAnimationFrame(() => requestAnimationFrame(resolve)),
        ),
    );
    await expect(
      area.getByRole("heading", {
        name: "Saved preparation input review",
        exact: true,
      }),
    ).toBeVisible();
    await expect(area).toContainText(
      "Current when last checked. Context version 1",
    );
    expect(preparationRows(root)).toEqual(saved);
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("workspace-preparation-review:v1"),
      ),
    ).toBeNull();
  });
});

test("stale preparation previews and competing reviews retain the winner without a second record", async ({
  page,
  context,
}) => {
  await isolated(async (url, root) => {
    await enter(page, url);
    await planningBrief(page, root);
    const area = await choosePreparation(page);
    const briefId = rows(root).intake_brief_revisions[0][1];
    const peer = await context.newPage();
    await enter(peer, url);
    await peer.getByLabel("Saved campaign briefs").selectOption(briefId);
    const other = await choosePreparation(peer, "A competing review.");
    await other
      .getByRole("button", {
        name: "Save reviewed preparation context",
        exact: true,
      })
      .click();
    await expect(
      other.getByRole("heading", {
        name: "Saved preparation input review",
        exact: true,
      }),
    ).toBeVisible();
    await area
      .getByRole("button", {
        name: "Save reviewed preparation context",
        exact: true,
      })
      .click();
    await expect(page.getByRole("alert")).toContainText("review changed");
    expect(preparationRows(root)).toHaveLength(1);
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("workspace-preparation-review:v1"),
      ),
    ).toBeNull();
    await area
      .getByRole("button", {
        name: "Reload preparation sources and history",
        exact: true,
      })
      .click();
    await expect(area).toContainText("A competing review.");
    await expect(
      area.getByLabel(
        "I reviewed these exact selected inputs. This does not verify claims or approve a campaign.",
      ),
    ).not.toBeChecked();
    await peer.close();
  });
});

test("preparation review storage failure and corrupt recovery prevent dispatch", async ({
  page,
}) => {
  await isolated(async (url, root) => {
    await enter(page, url);
    await planningBrief(page, root);
    const area = await choosePreparation(page);
    await page.evaluate(() => {
      const original = Storage.prototype.setItem;
      Storage.prototype.setItem = function (key, value) {
        if (key === "workspace-preparation-review:v1")
          throw new Error("Preparation storage unavailable");
        return original.call(this, key, value);
      };
    });
    await area
      .getByRole("button", {
        name: "Save reviewed preparation context",
        exact: true,
      })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "Preparation storage unavailable",
    );
    expect(preparationRows(root)).toHaveLength(0);
    await page.reload();
    await page.evaluate(() =>
      sessionStorage.setItem(
        "workspace-preparation-review:v1",
        '{"payload":{"request_id":"lost"}}',
      ),
    );
    await page.reload();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "original preparation review could not be restored",
    );
    await expect(
      page.getByRole("button", { name: "Save company draft", exact: true }),
    ).toBeDisabled();
    expect(preparationRows(root)).toHaveLength(0);
  });
});

function seedGroundedIntake(root, channel = "postal") {
  const script = `
import json,sys
from pathlib import Path
from acquisition.bootstrap import build_intake
from acquisition.campaigns import CampaignBriefDraft,PreparationReview
from acquisition.creative import CompanyDraft,CompanyClaimDraft
app=build_intake(Path(sys.argv[1])/'conversations.sqlite')
c=app.save_company('local-conversations','local-operator','grounding-company',CompanyDraft(company_name='Aster',product_name='Retail advice',
 claims=(CompanyClaimDraft('Aster offers retail advice.','Subject to the published terms.',('https://aster.invalid/product',)),
 CompanyClaimDraft('UNSELECTED SECRET CLAIM','Never selected.',('https://unselected.invalid/source',))),
 official_cta='Read the Aster terms.',cta_url='https://aster.invalid/terms'))['snapshot']
b=app.save_brief('local-conversations','local-operator','grounding-brief',CampaignBriefDraft(c['id'],1,objective='Compare responses.',audience='Independent retailers',
 country='UK',currency='GBP',channels=(sys.argv[2],),budget_minor=12345,contact_source='synthetic'))['snapshot']
p=app.preparation.preview('local-conversations',b['id'],1)
app.preparation.confirm('local-conversations','local-operator','grounding-review',PreparationReview(b['id'],1,p['id'],0,(p['claims'][0]['id'],),False,True,7,'Selected exact material.',confirmed=True))
print(json.dumps({'company':c['id'],'brief':b['id']}))
`;
  return JSON.parse(
    execFileSync("python3", ["-c", script, root, channel], {
      cwd: project,
      env: { ...process.env, PYTHONPATH: "src" },
      encoding: "utf8",
    }),
  );
}
function groundedRows(root) {
  return JSON.parse(
    execFileSync(
      "python3",
      [
        "-c",
        `import json,sqlite3,sys
with sqlite3.connect(sys.argv[1]+'/conversations.sqlite') as db:
 print(json.dumps([json.loads(r[0]) for r in db.execute("SELECT manifest FROM drafts WHERE manifest LIKE '%intake-grounding/v1%'")]))`,
        root,
      ],
      { cwd: project, encoding: "utf8" },
    ),
  );
}
async function selectGroundedBrief(page, ids) {
  await page
    .getByLabel("Saved company drafts", { exact: true })
    .selectOption(ids.company);
  await page
    .getByLabel("Saved campaign briefs", { exact: true })
    .selectOption(ids.brief);
  const area = page.getByRole("region", {
    name: "Preparation eligibility and source review",
    exact: true,
  });
  await expect(area).toContainText("Selected company: Aster");
  return area;
}
async function consentGrounding(area) {
  await area
    .getByLabel("Source evidence review note (required)")
    .fill(
      "Inspected each official page and its exact wording, qualifications and CTA.",
    );
  await area
    .getByLabel(
      "I checked the official sources, exact selected wording, qualifications and CTA. Prepare this unapproved synthetic fixture.",
      { exact: true },
    )
    .check();
}
for (const mobile of [false, true])
  test(`grounded intake prepares selected product wording without model or approval on ${mobile ? "mobile" : "desktop"}`, async ({
    page,
  }, testInfo) => {
    await isolated(async (url, root) => {
      const ids = seedGroundedIntake(root);
      await page.setViewportSize(
        mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
      );
      await enter(page, url);
      const area = await selectGroundedBrief(page, ids);
      expect(groundedRows(root)).toHaveLength(0);
      const prepare = area.getByRole("button", {
        name: "Prepare grounded synthetic draft",
        exact: true,
      });
      await prepare.click();
      await expect(
        area.getByLabel("Source evidence review note (required)"),
      ).toBeFocused();
      await consentGrounding(area);
      await area
        .getByLabel("Source evidence review note (required)")
        .fill("A changed source review note.");
      await expect(area.getByRole("checkbox")).not.toBeChecked();
      await area.getByRole("checkbox").check();
      await prepare.click();
      await expect(
        area.getByRole("heading", {
          name: "Unapproved grounded synthetic draft",
          exact: true,
        }),
      ).toBeVisible();
      await expect(area).toContainText(
        "Aster offers retail advice. Subject to the published terms.",
      );
      await expect(area).not.toContainText("UNSELECTED SECRET CLAIM");
      const saved = groundedRows(root);
      expect(saved).toHaveLength(1);
      expect(rows(root).model_calls).toHaveLength(0);
      expect(rows(root).review_decisions).toHaveLength(0);
      await area.screenshot({
        path: testInfo.outputPath(
          `grounded-intake-${mobile ? "mobile" : "desktop"}.png`,
        ),
      });
      await page.reload();
      await page
        .getByRole("button", { name: "Company & brief", exact: true })
        .click();
      await selectGroundedBrief(page, ids);
      await expect(
        area.getByRole("heading", {
          name: "Unapproved grounded synthetic draft",
          exact: true,
        }),
      ).toBeVisible();
      expect(groundedRows(root)).toEqual(saved);
    });
  });

test("grounded preparation lost reply stays bound to the original store and reconciles without another POST", async ({
  page,
}) => {
  await isolated(async (url, root, restart) => {
    const ids = seedGroundedIntake(root);
    await enter(page, url);
    const area = await selectGroundedBrief(page, ids);
    await consentGrounding(area);
    await page.route("**/api/intake/preparations", async (route) => {
      await route.fetch();
      await route.abort("failed");
    });
    await area
      .getByRole("button", {
        name: "Prepare grounded synthetic draft",
        exact: true,
      })
      .click();
    const retry = page.getByRole("button", {
      name: "Retry original grounded preparation",
      exact: true,
    });
    await expect(retry).toBeEnabled();
    expect(groundedRows(root)).toHaveLength(1);
    const original = groundedRows(root);
    const saved = await page.evaluate(() =>
      sessionStorage.getItem("workspace-grounded-preparation:v1"),
    );
    expect(saved).toBeTruthy();
    await page.unroute("**/api/intake/preparations");
    const other = await restart();
    await page.reload();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    let posts = 0;
    page.on("request", (r) => {
      if (r.method() === "POST" && r.url().endsWith("/api/intake/preparations"))
        posts++;
    });
    await retry.click();
    await expect(page.getByRole("alert")).toContainText(
      "original workspace store",
    );
    expect(posts).toBe(0);
    expect(groundedRows(other)).toEqual([]);
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("workspace-grounded-preparation:v1"),
      ),
    ).toBe(saved);
    await restart(root);
    await page.reload();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await retry.click();
    await expect(retry).toHaveCount(0);
    await selectGroundedBrief(page, ids);
    await expect(
      area.getByRole("heading", {
        name: "Unapproved grounded synthetic draft",
        exact: true,
      }),
    ).toBeVisible();
    expect(posts).toBe(0);
    expect(groundedRows(root)).toEqual(original);
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("workspace-grounded-preparation:v1"),
      ),
    ).toBeNull();
  });
});

test("corrupt grounded preparation recovery blocks new commands", async ({
  page,
}) => {
  await isolated(async (url, root) => {
    seedGroundedIntake(root);
    await page.addInitScript(() =>
      sessionStorage.setItem(
        "workspace-grounded-preparation:v1",
        '{"payload":{"request_id":"lost"}}',
      ),
    );
    await page.goto(url);
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText(
      "original grounded preparation could not be restored",
    );
    await expect(
      page.getByRole("button", { name: "Save company draft", exact: true }),
    ).toBeDisabled();
    expect(groundedRows(root)).toEqual([]);
  });
});

async function selectEmailBrief(page, ids) {
  await page
    .getByLabel("Saved company drafts", { exact: true })
    .selectOption(ids.company);
  await page
    .getByLabel("Saved campaign briefs", { exact: true })
    .selectOption(ids.brief);
  const area = page.getByRole("region", {
    name: "Email preparation, review and export",
    exact: true,
  });
  await expect(
    area.getByRole("button", {
      name: "Prepare synthetic email batch",
      exact: true,
    }),
  ).toBeEnabled();
  return area;
}
function emailRecords(root) {
  return JSON.parse(
    execFileSync(
      "python3",
      [
        "-c",
        `import sqlite3,json,sys
with sqlite3.connect(sys.argv[1]+'/conversations.sqlite') as db:
 print(json.dumps([json.loads(r[0]) for r in db.execute("SELECT receipt FROM intake_requests WHERE json_extract(inputs,'$.kind')='intake_email_preparation/v1'")]))`,
        root,
      ],
      { cwd: project, encoding: "utf8" },
    ),
  );
}
async function prepareEmail(area) {
  await area
    .getByLabel("Email source review note (required)")
    .fill("Checked the exact official source wording and qualifications.");
  await area
    .getByLabel(
      "I checked the exact selected wording, qualifications, official sources and CTA. Prepare synthetic emails only.",
      { exact: true },
    )
    .check();
  await area
    .getByRole("button", { name: "Prepare synthetic email batch", exact: true })
    .click();
  await expect(
    area.getByRole("heading", {
      name: "Exact synthetic email batch",
      exact: true,
    }),
  ).toBeVisible();
}
async function approveEmail(area) {
  await area
    .getByLabel("Email approval reason (required)")
    .fill("Reviewed each complete synthetic email and permission record.");
  await area
    .getByLabel(
      "I reviewed every exact recipient, subject, text, HTML, qualification and opt-out field. Approve this synthetic export only.",
      { exact: true },
    )
    .check();
  await area
    .getByRole("button", { name: "Approve exact email export", exact: true })
    .click();
  await expect(
    area
      .getByRole("status")
      .filter({ hasText: "Approved for this exact synthetic export only." }),
  ).toBeVisible();
}
for (const mobile of [false, true])
  test(`reviewed intake email batch requires exact approval and exports its displayed content on ${mobile ? "mobile" : "desktop"}`, async ({
    page,
  }, testInfo) => {
    await isolated(async (url, root) => {
      const ids = seedGroundedIntake(root, "email");
      await page.setViewportSize(
        mobile ? { width: 390, height: 844 } : { width: 1440, height: 1000 },
      );
      await enter(page, url);
      const area = await selectEmailBrief(page, ids);
      await area
        .getByRole("button", {
          name: "Prepare synthetic email batch",
          exact: true,
        })
        .click();
      await expect(
        area.getByLabel("Email source review note (required)"),
      ).toBeFocused();
      await prepareEmail(area);
      expect(emailRecords(root)).toHaveLength(2); // original command plus exact-context binding
      const download = area.getByRole("button", {
        name: "Download reviewed synthetic emails",
        exact: true,
      });
      await expect(download).toBeDisabled();
      await area
        .locator("article > details")
        .first()
        .locator("summary")
        .first()
        .click();
      await expect(area).toContainText("Aster offers retail advice.");
      await expect(area).not.toContainText("UNSELECTED SECRET CLAIM");
      await area
        .getByRole("button", {
          name: "Approve exact email export",
          exact: true,
        })
        .click();
      await expect(
        area.getByLabel("Email approval reason (required)"),
      ).toBeFocused();
      await approveEmail(area);
      const exportedResponse = page.waitForResponse(
        (r) =>
          r.request().method() === "POST" &&
          r.url().endsWith("/api/intake/emails/export"),
      );
      const downloaded = page.waitForEvent("download");
      await download.click();
      const file = await downloaded;
      const exportReceipt = await (await exportedResponse).json();
      const content = JSON.parse(
        await (
          await import("node:fs/promises")
        ).readFile(await file.path(), "utf8"),
      );
      expect(content.emails).toEqual(emailRecords(root)[0].content.rows);
      expect(content.live_send_authority).toBe("none");
      expect(content.emails[0].email.cta_url).toBe(
        "https://aster.invalid/terms",
      );
      expect(rows(root).model_calls).toHaveLength(0);
      expect(rows(root).runs).toHaveLength(0);
      await area.screenshot({
        path: testInfo.outputPath(
          `intake-email-${mobile ? "mobile" : "desktop"}.png`,
        ),
      });
      await page.reload();
      await page
        .getByRole("button", { name: "Company & brief", exact: true })
        .click();
      await page
        .getByLabel("Saved company drafts", { exact: true })
        .selectOption(ids.company);
      await page
        .getByLabel("Saved campaign briefs", { exact: true })
        .selectOption(ids.brief);
      await expect(download).toBeEnabled();
      await area
        .getByRole("button", {
          name: "Revoke email export approval",
          exact: true,
        })
        .click();
      await expect(download).toBeDisabled();
      const token = await page
        .locator('meta[name="workspace-token"]')
        .getAttribute("content");
      const exportUrl = new URL(
        `/api/intake/emails/exports/${exportReceipt.request_id}?subject_id=${exportReceipt.inputs.subject_id}`,
        url,
      ).href;
      const denied = await page.request.get(exportUrl, {
        headers: { "X-Workspace-Token": token },
      });
      expect(denied.status()).toBe(409);
    });
  });

test("lost email preparation and approval replies reconcile without another effect", async ({
  page,
}) => {
  await isolated(async (url, root) => {
    const ids = seedGroundedIntake(root, "email");
    await enter(page, url);
    const area = await selectEmailBrief(page, ids);
    await page.route("**/api/intake/emails/prepare", async (route) => {
      await route.fetch();
      await route.abort("failed");
    });
    await area
      .getByLabel("Email source review note (required)")
      .fill("Reviewed selected exact product wording.");
    await area
      .getByLabel(
        "I checked the exact selected wording, qualifications, official sources and CTA. Prepare synthetic emails only.",
        { exact: true },
      )
      .check();
    await area
      .getByRole("button", {
        name: "Prepare synthetic email batch",
        exact: true,
      })
      .click();
    const retry = page.getByRole("button", {
      name: "Retry original email command",
      exact: true,
    });
    await expect(retry).toBeEnabled();
    const original = emailRecords(root);
    expect(original).toHaveLength(2);
    await page.unroute("**/api/intake/emails/prepare");
    let prepares = 0;
    page.on("request", (r) => {
      if (
        r.method() === "POST" &&
        r.url().endsWith("/api/intake/emails/prepare")
      )
        prepares++;
    });
    await retry.click();
    await expect(
      area.getByRole("heading", {
        name: "Exact synthetic email batch",
        exact: true,
      }),
    ).toBeVisible();
    expect(prepares).toBe(0);
    expect(emailRecords(root)).toEqual(original);
    await page.route("**/api/intake/emails/decision", async (route) => {
      await route.fetch();
      await route.abort("failed");
    });
    await area
      .getByLabel("Email approval reason (required)")
      .fill("Reviewed each exact email.");
    await area
      .getByLabel(
        "I reviewed every exact recipient, subject, text, HTML, qualification and opt-out field. Approve this synthetic export only.",
        { exact: true },
      )
      .check();
    await area
      .getByRole("button", { name: "Approve exact email export", exact: true })
      .click();
    await expect(retry).toBeEnabled();
    await page.unroute("**/api/intake/emails/decision");
    let decisions = 0;
    page.on("request", (r) => {
      if (
        r.method() === "POST" &&
        r.url().endsWith("/api/intake/emails/decision")
      )
        decisions++;
    });
    await retry.click();
    await expect(
      area.getByRole("button", {
        name: "Download reviewed synthetic emails",
        exact: true,
      }),
    ).toBeEnabled();
    expect(decisions).toBe(0);
    await page.route("**/api/intake/emails/export", async (route) => {
      await route.fetch();
      await route.abort("failed");
    });
    await area
      .getByRole("button", {
        name: "Download reviewed synthetic emails",
        exact: true,
      })
      .click();
    await expect(retry).toBeEnabled();
    await page.unroute("**/api/intake/emails/export");
    let exports = 0;
    page.on("request", (r) => {
      if (
        r.method() === "POST" &&
        r.url().endsWith("/api/intake/emails/export")
      )
        exports++;
    });
    const downloaded = page.waitForEvent("download");
    await retry.click();
    const file = await downloaded;
    const content = JSON.parse(
      await (
        await import("node:fs/promises")
      ).readFile(await file.path(), "utf8"),
    );
    expect(content.emails).toEqual(original[0].content.rows);
    expect(exports).toBe(0);
    expect(rows(root).model_calls).toHaveLength(0);
    await page.evaluate(() =>
      sessionStorage.setItem("workspace-intake-email:v1", "{broken"),
    );
    await page.reload();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await expect(area.getByRole("alert")).toContainText(
      "original email command could not be restored",
    );
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("workspace-intake-email:v1"),
      ),
    ).toBe("{broken");
    expect(exports).toBe(0);
  });
});

test("email recovery refuses a switched store and retains the original command", async ({
  page,
}) => {
  await isolated(async (url, root, restart) => {
    const ids = seedGroundedIntake(root, "email");
    await enter(page, url);
    const area = await selectEmailBrief(page, ids);
    await page.route("**/api/intake/emails/prepare", (route) =>
      route.abort("failed"),
    );
    await area
      .getByLabel("Email source review note (required)")
      .fill("Checked sources for an exact email batch.");
    await area
      .getByLabel(
        "I checked the exact selected wording, qualifications, official sources and CTA. Prepare synthetic emails only.",
        { exact: true },
      )
      .check();
    await area
      .getByRole("button", {
        name: "Prepare synthetic email batch",
        exact: true,
      })
      .click();
    const retry = page.getByRole("button", {
      name: "Retry original email command",
      exact: true,
    });
    await expect(retry).toBeEnabled();
    const saved = await page.evaluate(() =>
      sessionStorage.getItem("workspace-intake-email:v1"),
    );
    await page.unroute("**/api/intake/emails/prepare");
    const other = await restart();
    await page.reload();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    let posts = 0;
    page.on("request", (r) => {
      if (
        r.method() === "POST" &&
        r.url().endsWith("/api/intake/emails/prepare")
      )
        posts++;
    });
    await retry.click();
    await expect(page.getByRole("alert")).toContainText(
      "original workspace store",
    );
    expect(posts).toBe(0);
    expect(emailRecords(other)).toEqual([]);
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("workspace-intake-email:v1"),
      ),
    ).toBe(saved);
    await restart(root);
    await page.reload();
    await page
      .getByRole("button", { name: "Company & brief", exact: true })
      .click();
    await retry.click();
    await expect(retry).toHaveCount(0);
    expect(posts).toBe(1);
    expect(emailRecords(root)).toHaveLength(2);
  });
});
