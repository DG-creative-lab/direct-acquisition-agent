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
    await page
      .locator(".page-heading")
      .getByRole("button", { name: "New campaign" })
      .click();
    await page
      .getByRole("button", { name: "Prepare campaign", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
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
  });
}
