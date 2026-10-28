import { test, expect } from "@playwright/test";
import { command, read } from "../src/api.ts";

const nativeFetch = globalThis.fetch.bind(globalThis);
let storage, requestLog, fault, base, workspaceToken;
let previousDocument, previousStorage;
class MemoryStorage {
  values = new Map();
  getItem(key) {
    return this.values.get(key) ?? null;
  }
  setItem(key, value) {
    this.values.set(key, String(value));
  }
  removeItem(key) {
    this.values.delete(key);
  }
}
test.beforeEach(async ({ baseURL }) => {
  base = baseURL;
  const html = await (await nativeFetch(base)).text();
  workspaceToken = html.match(/name="workspace-token" content="([^"]+)"/)[1];
  storage = new MemoryStorage();
  requestLog = [];
  fault = null;
  previousDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
  previousStorage = Object.getOwnPropertyDescriptor(
    globalThis,
    "sessionStorage",
  );
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: { querySelector: () => ({ content: workspaceToken }) },
  });
  Object.defineProperty(globalThis, "sessionStorage", {
    configurable: true,
    value: storage,
  });
  globalThis.fetch = async (path, options = {}) => {
    const headers = new Headers(options.headers);
    if (options.method === "POST") headers.set("Origin", base);
    const payload = options.body ? JSON.parse(options.body) : null;
    requestLog.push({ path, payload });
    const response = await nativeFetch(new URL(path, base), {
      ...options,
      headers,
    });
    if (fault?.path === path) {
      const kind = fault.kind;
      fault = null;
      await response.text(); // The real backend has committed before its acknowledgement is lost.
      if (kind === "network")
        throw new TypeError("Injected response loss after backend commit");
      return new Response(
        JSON.stringify({ error: "Injected uncertain result" }),
        { status: 503, headers: { "Content-Type": "application/json" } },
      );
    }
    return response;
  };
});
test.afterEach(() => {
  globalThis.fetch = nativeFetch;
  if (previousDocument)
    Object.defineProperty(globalThis, "document", previousDocument);
  else delete globalThis.document;
  if (previousStorage)
    Object.defineProperty(globalThis, "sessionStorage", previousStorage);
  else delete globalThis.sessionStorage;
});
async function campaign() {
  return command("/api/sessions", { mode: "fixture", parent_id: null });
}
function approval(state) {
  return {
    subject_id: state.review.subject.id,
    reason: "Reviewed the exact synthetic draft and evidence.",
  };
}
async function assertSingleApproval(state, path, expectedAttempts = 2) {
  const current = await read(`/api/sessions/${state.session.id}`);
  expect(
    current.review.events.filter((e) => e.kind === "review_approve"),
  ).toHaveLength(1);
  expect(current.review.approval.decision).toBe("reject");
  const attempts = requestLog
    .filter((r) => r.path === path)
    .map((r) => r.payload.request_id);
  expect(attempts).toHaveLength(expectedAttempts);
  expect(new Set(attempts).size).toBe(1);
}
for (const kind of ["network", "server"]) {
  test(`uncertain ${kind} approval retains its identity across an interposed command`, async () => {
    const state = await campaign(),
      path = `/api/sessions/${state.session.id}/approve`,
      payload = approval(state);
    fault = { path, kind };
    await expect(command(path, payload)).rejects.toThrow();
    await command(`/api/sessions/${state.session.id}/reject`, {
      subject_id: payload.subject_id,
      reason: "An independent later review requests changes.",
    });
    const replay = await command(path, payload);
    await assertSingleApproval(state, path);
    expect(replay.command_replayed).toBe(true);
    expect(storage.values.size).toBe(0);
  });
}
test("authentication rejection does not discard an earlier uncertain identity", async () => {
  const state = await campaign(),
    path = `/api/sessions/${state.session.id}/approve`,
    payload = approval(state);
  fault = { path, kind: "network" };
  await expect(command(path, payload)).rejects.toThrow();
  const activeToken = workspaceToken;
  workspaceToken = "expired-workspace-token";
  await expect(command(path, payload)).rejects.toThrow("Reload the workspace");
  workspaceToken = activeToken;
  await command(`/api/sessions/${state.session.id}/reject`, {
    subject_id: payload.subject_id,
    reason: "A later review requires changes.",
  });
  const replay = await command(path, payload);
  await assertSingleApproval(state, path, 3);
  expect(replay.command_replayed).toBe(true);
  expect(storage.values.size).toBe(0);
});

test("equivalent field ordering reuses the uncertain request identity", async () => {
  const state = await campaign(),
    path = `/api/sessions/${state.session.id}/approve`,
    payload = approval(state);
  fault = { path, kind: "network" };
  await expect(command(path, payload)).rejects.toThrow();
  const replay = await command(path, {
    reason: payload.reason,
    subject_id: payload.subject_id,
  });
  expect(replay.command_replayed).toBe(true);
  expect(
    replay.review.events.filter((e) => e.kind === "review_approve"),
  ).toHaveLength(1);
  const ids = requestLog
    .filter((r) => r.path === path)
    .map((r) => r.payload.request_id);
  expect(ids[1]).toBe(ids[0]);
});
test("an existing single-slot pending identity survives migration and another command", async () => {
  const state = await campaign(),
    path = `/api/sessions/${state.session.id}/approve`,
    payload = approval(state),
    id = crypto.randomUUID();
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Workspace-Token": workspaceToken,
    },
    body: JSON.stringify({ ...payload, request_id: id }),
  });
  expect(response.ok).toBe(true);
  await response.json();
  storage.setItem(
    "workspace-pending",
    JSON.stringify({
      signature: JSON.stringify([path, payload]),
      request_id: id,
    }),
  );
  await command(`/api/sessions/${state.session.id}/reject`, {
    subject_id: payload.subject_id,
    reason: "Subsequent review requests changes.",
  });
  const replay = await command(path, payload);
  await assertSingleApproval(state, path);
  expect(replay.command_replayed).toBe(true);
});
test("storage failure blocks a new mutation before dispatch", async () => {
  const state = await campaign(),
    path = `/api/sessions/${state.session.id}/approve`;
  storage.setItem = () => {
    throw new Error("Injected storage capacity failure");
  };
  await expect(command(path, approval(state))).rejects.toThrow(
    "storage capacity",
  );
  expect(requestLog.filter((r) => r.path === path)).toHaveLength(0);
  const current = await read(`/api/sessions/${state.session.id}`);
  expect(
    current.review.events.filter((e) => e.kind === "review_approve"),
  ).toHaveLength(0);
});
for (const viewport of [
  { width: 390, height: 844 },
  { width: 1440, height: 1000 },
]) {
  test(`audience table stays within the document at ${viewport.width}px`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await page.getByRole("button", { name: /^Campaign(?: \d+)?$/ }).click();
    await page
      .locator(".page-heading")
      .getByRole("button", { name: "New campaign" })
      .click();
    await page
      .getByRole("button", { name: "Prepare campaign", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 15000 });
    await expect(page.getByRole("tab", { name: /Audience/ })).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page
      .locator(".workspace-body .table-scroll")
      .scrollIntoViewIfNeeded();
    await expect(
      page.getByRole("columnheader", { name: "Actions", exact: true }),
    ).toHaveCount(1);
    const dimensions = () =>
      page.evaluate(() => ({
        scroll: document.documentElement.scrollWidth,
        client: document.documentElement.clientWidth,
      }));
    await expect.poll(dimensions).toEqual({
      scroll: await page.evaluate(() => document.documentElement.clientWidth),
      client: await page.evaluate(() => document.documentElement.clientWidth),
    });
    // Local horizontal table scrolling must not move the page or extend its width.
    await page.locator(".workspace-body .table-scroll").evaluate((element) => {
      element.scrollLeft = 100;
    });
    expect((await dimensions()).scroll).toBe((await dimensions()).client);
    await page.getByRole("tab", { name: /Copy variants/ }).click();
    expect((await dimensions()).scroll).toBe((await dimensions()).client);
    const originalCreative = await page
      .locator(".copy-provenance code")
      .first()
      .textContent();
    // Reload the persisted creative: publication tokens must not restyle it.
    await page.reload();
    await page.getByRole("button", { name: /^Campaign(?: \d+)?$/ }).click();
    await page.getByRole("tab", { name: /Copy variants/ }).click();
    await page.evaluate(() => document.fonts.ready);
    await expect(page.locator(".copy-provenance code").first()).toHaveText(
      originalCreative,
    );
    const letter = page.locator(".letter").first();
    await expect(letter).toHaveCSS(
      "font-family",
      '"Inter Variable", Inter, Arial, sans-serif',
    );
    await expect(letter).toHaveCSS("border-radius", "5px");
    await expect(letter.locator(".letter-paper")).toHaveCSS(
      "background-color",
      "rgb(255, 254, 250)",
    );
    await expect(letter.locator(".letter-paper")).toHaveCSS(
      "padding",
      viewport.width < 550 ? "25px" : "24px 20px",
    );
    await expect(letter.locator(".letter-brand")).toHaveCSS(
      "color",
      "rgb(24, 61, 50)",
    );
    await expect(letter.locator("h3")).toHaveCSS("font-size", "20px");
    await expect(letter.locator("h3")).toHaveCSS("font-weight", "550");
    await expect(letter.locator(".letter-opening")).toHaveCSS(
      "font-size",
      "12px",
    );
    await expect(letter.locator(".letter-opening")).toHaveCSS(
      "color",
      "rgb(97, 112, 89)",
    );
    await expect(letter.locator(".letter-disclosure")).toHaveCSS(
      "font-size",
      "9px",
    );
    await expect(letter.locator(".copy-provenance summary")).toHaveCSS(
      "font-size",
      "10px",
    );
    await expect(letter.locator(".badge")).toHaveCSS(
      "background-color",
      "rgb(244, 246, 239)",
    );
    // Workspace changes remain isolated even when the public brand roles change.
    await page.evaluate(() => {
      document.documentElement.style.setProperty("--brand-paper", "magenta");
      document.documentElement.style.setProperty("--brand-ink", "blue");
      document.documentElement.style.setProperty("--brand-sans", "monospace");
    });
    await expect(letter.locator(".letter-paper")).toHaveCSS(
      "background-color",
      "rgb(255, 254, 250)",
    );
    await expect(letter.locator(".letter-brand")).toHaveCSS(
      "color",
      "rgb(24, 61, 50)",
    );
    await expect(letter).toHaveCSS(
      "font-family",
      '"Inter Variable", Inter, Arial, sans-serif',
    );
  });
}

test("brand identity stays named on desktop, tablet and mobile", async ({
  page,
}) => {
  for (const width of [1440, 820, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/");
    await expect(
      page.getByRole("link", {
        name: "Direct Acquisition by Dessi Georgieva",
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute(
      "content",
      "#000000",
    );
  }
});

test("offline assistant prepares a persistent draft without a model call", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const paths = [];
  page.on("request", (request) => {
    if (request.method() === "POST")
      paths.push(new URL(request.url()).pathname);
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Try the offline example/ }).click();
  await expect(
    page.getByRole("heading", { name: "Campaign brief" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Review campaign/ }),
  ).toBeVisible();
  expect(paths.some((path) => path.endsWith("/plan-fixture"))).toBe(true);
  expect(paths.some((path) => path.endsWith("/plan"))).toBe(false);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    await page.evaluate(() => document.documentElement.clientWidth),
  );
  await page.reload();
  await expect(
    page.getByRole("button", { name: /Review campaign/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Review campaign/ }).click();
  await expect(page.getByText("Review & approval")).toBeVisible();
  await expect(
    page.getByText("Pending", { exact: true }).first(),
  ).toBeVisible();
});

test("conversation navigation opens a new chat and returns to recent work", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Assistant", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "New conversation", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("Message Direct Acquisition")).toBeInViewport();
  await page.screenshot({ path: "../.local/chat-desktop.png", fullPage: true });
  await page.getByRole("button", { name: /Try the offline example/ }).click();
  await expect(
    page.getByRole("button", { name: /Review campaign/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: /Review campaign/ }).click();
  await expect(page.getByText("Review & approval")).toBeVisible();
  await page
    .locator(".conversation-history")
    .getByRole("button", { name: "Offline example" })
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: /Review campaign/ }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "What would you like to prepare?" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByLabel("Message Direct Acquisition")).toBeInViewport();
  await page.screenshot({ path: "../.local/chat-mobile.png", fullPage: true });
  await expect(
    page.getByRole("button", { name: "New conversation", exact: true }),
  ).toBeVisible();
  await page
    .locator(".conversation-list")
    .getByRole("button", { name: /Offline example/ })
    .first()
    .click();
  await expect(
    page.getByRole("button", { name: /Review campaign/ }),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(
    await page.evaluate(() => document.documentElement.clientWidth),
  );
});

test("lost message acknowledgement is retried with the original identity after reload", async ({
  page,
}) => {
  let attempts = [],
    dropped = false;
  await page.route("**/api/conversations/*/messages", async (route) => {
    const body = route.request().postDataJSON();
    attempts.push(body);
    if (!dropped) {
      dropped = true;
      await route.fetch();
      await route.abort("failed");
    } else await route.continue();
  });
  await page.route("**/api/conversations/*/plan", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: "Model disabled for test" }),
    }),
  );
  await page.goto("/");
  await page
    .getByLabel("Message Direct Acquisition")
    .fill("Plan a £600 campaign for contractors.");
  await page.getByRole("button", { name: "Send to agent" }).click();
  await expect(
    page.getByRole("button", { name: "Retry saving message" }),
  ).toBeEnabled();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Retry saving message" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Retry saving message" }).click();
  await expect(page.getByText("Model disabled for test")).toBeVisible();
  expect(attempts).toHaveLength(2);
  expect(attempts[1]).toEqual(attempts[0]);
  await expect(
    page
      .locator(".conversation-thread")
      .getByText("Plan a £600 campaign for contractors.", { exact: true }),
  ).toHaveCount(1);
});

test("stale message rejection unlocks the composer and allows revision", async ({
  page,
}) => {
  let advanced = false;
  await page.route("**/api/conversations/*/messages", async (route) => {
    if (!advanced) {
      advanced = true;
      const body = route.request().postDataJSON();
      const response = await nativeFetch(route.request().url(), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Workspace-Token": workspaceToken,
          Origin: base,
        },
        body: JSON.stringify({
          request_id: "other-client",
          expected_revision: body.expected_revision,
          content: "A concurrent message.",
        }),
      });
      expect(response.ok).toBeTruthy();
    }
    await route.continue();
  });
  await page.route("**/api/conversations/*/plan", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: "Model disabled for test" }),
    }),
  );
  await page.goto("/");
  const composer = page.getByLabel("Message Direct Acquisition");
  await composer.fill("Plan a £600 campaign for contractors.");
  await page.getByRole("button", { name: "Send to agent" }).click();
  await expect(
    page.getByText(
      "Conversation changed; reload before appending this message",
    ),
  ).toBeVisible();
  await expect(composer).toBeEnabled();
  await expect(composer).toHaveValue("Plan a £600 campaign for contractors.");
  await expect(
    page.getByText("A concurrent message.", { exact: true }),
  ).toBeVisible();
  await composer.fill("Plan a £300 campaign for contractors.");
  await page.getByRole("button", { name: "Send to agent" }).click();
  await expect(page.getByText("Model disabled for test")).toBeVisible();
  await expect(
    page.getByText("Plan a £300 campaign for contractors.", { exact: true }),
  ).toHaveCount(1);
});

test("unmarked conflict keeps the message pending", async ({ page }) => {
  await page.route("**/api/conversations/*/messages", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({ error: "Unconfirmed conflict" }),
    }),
  );
  await page.goto("/");
  await page
    .getByLabel("Message Direct Acquisition")
    .fill("Plan a £600 campaign for contractors.");
  await page.getByRole("button", { name: "Send to agent" }).click();
  await expect(page.getByText("Unconfirmed conflict")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Retry saving message" }),
  ).toBeEnabled();
  await expect(page.getByLabel("Message Direct Acquisition")).toBeDisabled();
});

test("model copy waits for explicit generation and reports an uncertain failure", async ({
  page,
}) => {
  let generationRequests = 0;
  await page.route("**/api/conversations/*/plan", async (route) => {
    const url = route
      .request()
      .url()
      .replace(/\/plan$/, "");
    const conversation = await (
      await nativeFetch(url, {
        headers: { "X-Workspace-Token": workspaceToken },
      })
    ).json();
    const result = {
      id: "brief_test",
      outcome: "brief_proposal",
      objective: "Test contractor responses.",
      budget_pence: 60000,
      segments: ["contractors"],
      copy_mode: "model",
      question: "",
      unsupported_reason: "",
    };
    const plan = {
      request_id: "plan_test",
      revision: conversation.revision,
      status: "succeeded",
      mode: "model",
      current: true,
      result,
      error: null,
    };
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ...conversation,
        plans: [plan],
        current_plan: plan,
      }),
    });
  });
  await page.route("**/api/conversations/*/draft", async (route) => {
    generationRequests += 1;
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: "Generation outcome is uncertain. Inspect the saved run.",
      }),
    });
  });
  await page.goto("/");
  await page
    .getByLabel("Message Direct Acquisition")
    .fill("Prepare a £600 contractor campaign with model copy.");
  await page.getByRole("button", { name: "Send to agent" }).click();
  await expect(
    page.getByRole("button", { name: "Generate campaign copy" }),
  ).toBeVisible();
  expect(generationRequests).toBe(0);
  await page.getByRole("button", { name: "Generate campaign copy" }).click();
  await expect(
    page.getByText("Generation outcome is uncertain. Inspect the saved run."),
  ).toBeVisible();
  expect(generationRequests).toBe(1);
  await expect(
    page.getByRole("button", { name: /Review campaign/ }),
  ).toHaveCount(0);
});
