import { test, expect } from "@playwright/test";
import { spawn, execFileSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const project = fileURLToPath(new URL("../..", import.meta.url));
async function isolated(run, seed = 0) {
  const root = await mkdtemp(join(tmpdir(), "acquisition-intake-ui-"));
  const script = `
from acquisition.bootstrap import build_workspace
from acquisition.entrypoints.workspace import WorkspaceServer
from pathlib import Path
import sys
w=build_workspace(sys.argv[1])
for i in range(int(sys.argv[2])):
 w.intake.save('companies',{'request_id':'seed-'+str(i),'id':None,'expected_revision':0,'draft':{'company_name':'Saved company '+str(i)}})
s=WorkspaceServer(0,w,Path('frontend/dist'))
print('http://127.0.0.1:'+str(s.server_port),flush=True)
s.serve_forever()
`;
  const child = spawn("python3", ["-c", script, root, String(seed)], {
    cwd: project,
    env: {
      ...process.env,
      PYTHONPATH: "src",
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
    await run(url, root);
  } finally {
    child.kill("SIGTERM");
    await exited;
    await rm(root, { recursive: true, force: true });
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
    await page.reload();
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
