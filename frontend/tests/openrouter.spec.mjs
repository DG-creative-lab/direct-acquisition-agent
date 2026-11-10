import { expect, test } from "@playwright/test";

const key = "fixture-key-" + "x".repeat(40);
const model = {
  id: "vendor/chat-model",
  name: "Chat Model",
  tier: "Lower cost",
  input: 0.12,
  output: 0.4,
};
const replacement = {
  ...model,
  id: "vendor/other",
  name: "Other Model",
  tier: "Standard",
};
const binding = "a".repeat(64);

async function mockProvider(page) {
  let connections = 0;
  await page.route("**/api/openrouter/check", (route) => {
    expect(route.request().headers().authorization).toBe("Bearer " + key);
    expect(route.request().postDataJSON()).toEqual({});
    return route.fulfill({
      json: { handle: "handle-" + ++connections, binding },
    });
  });
  await page.route(/\/api\/openrouter\/(advance|disconnect)$/, (route) => {
    expect(route.request().headers().authorization).toBeUndefined();
    expect(route.request().headers()["x-openrouter-handle"]).toBe(
      "handle-" + connections,
    );
    return route.fulfill({ json: { ok: true } });
  });
  await page.route("**/api/openrouter/models", (route) => {
    expect(route.request().headers().authorization).toBeUndefined();
    return route.fulfill({ json: { models: [model, replacement] } });
  });
}

async function connect(page) {
  await page.getByRole("button", { name: /Local reviewer/ }).click();
  const settings = page.getByRole("dialog", { name: "OpenRouter" });
  await settings.getByLabel("OpenRouter API key").fill(key);
  await settings.getByRole("button", { name: "Connect key" }).click();
  await expect(settings).toBeHidden();
}

async function send(page) {
  await page
    .getByRole("textbox", { name: "Message Direct Acquisition" })
    .fill("Prepare a £600 direct-mail experiment for contractors.");
  await page.getByRole("button", { name: "Send to agent" }).click();
}

test("browser retry keeps the original model and tier without storing or resending the raw key", async ({
  page,
}) => {
  await mockProvider(page);
  const requests = [];
  await page.route("**/api/conversations/*/preparations", (route) => {
    const headers = route.request().headers();
    expect(headers.authorization).toBeUndefined();
    expect(headers["x-openrouter-model"]).toBe(model.id);
    expect(headers["x-openrouter-tier"]).toBe(model.tier);
    expect(route.request().postData()).not.toContain(key);
    requests.push({
      id: route.request().postDataJSON().request_id,
      handle: headers["x-openrouter-handle"],
    });
    return requests.length === 1
      ? route.abort()
      : route.fulfill({
          status: 400,
          json: { error: "Test stopped at preparation admission." },
        });
  });

  await page.goto("/");
  await connect(page);
  await page.getByLabel("Chat model: Choose model").click();
  const option = page.getByRole("button", { name: /Chat Model/ });
  await expect(option).toContainText("$0.12 input · $0.40 output");
  await option.click();
  await page.reload();
  await expect(page.getByLabel("Chat model: Chat Model")).toBeVisible();
  const stored = await page.evaluate(() => [
    JSON.stringify({ ...localStorage }),
    JSON.stringify({ ...sessionStorage }),
  ]);
  for (const value of stored) expect(value).not.toContain(key);

  await send(page);
  const resume = page.getByRole("button", { name: "Resume preparation" });
  await expect(resume).toBeVisible();
  // Exercise a tab with the single preparation slot from the previous version.
  await page.evaluate(() => {
    const prefix = "conversation-preparation-intent";
    const scoped = Object.keys(sessionStorage).find((key) =>
      key.startsWith(prefix + ":"),
    );
    sessionStorage.setItem(prefix, sessionStorage.getItem(scoped));
    sessionStorage.removeItem(scoped);
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Local reviewer settings" }).click();
  const settings = page.getByRole("dialog", { name: "OpenRouter" });
  await expect(settings.getByLabel("Replace API key")).toHaveValue("");
  await settings.getByRole("button", { name: "Remove key" }).click();
  await expect(settings).toBeHidden();
  await page.reload();
  await expect(page.getByLabel("Chat model: Workspace default")).toBeVisible();
  await resume.click();
  await expect(
    page.getByText(/Reconnect the original OpenRouter key/),
  ).toBeVisible();
  expect(requests).toHaveLength(1);

  await connect(page);
  await page.getByLabel("Chat model: Choose model").click();
  await page.getByRole("button", { name: /Other Model/ }).click();
  await resume.click();
  await expect(
    page.getByText("Test stopped at preparation admission."),
  ).toBeVisible();
  expect(requests).toEqual([
    { id: requests[0].id, handle: "handle-1" },
    { id: requests[0].id, handle: "handle-2" },
  ]);
});

test("a second chat cannot clear the first chat's pending funding", async ({
  page,
}) => {
  await mockProvider(page);
  const firstBrief = "Prepare a contractor campaign for £600.";
  const requests = [];
  let planningPosts = 0;
  await page.route("**/api/conversations/*/plan", (route) => {
    planningPosts++;
    return route.abort();
  });
  await page.route("**/api/conversations/*/preparations", async (route) => {
    const request = route.request();
    const conversationUrl = request.url().replace(/\/preparations$/, "");
    const headers = request.headers();
    requests.push({
      conversationUrl,
      ...request.postDataJSON(),
      handle: headers["x-openrouter-handle"],
      model: headers["x-openrouter-model"],
      tier: headers["x-openrouter-tier"],
    });
    if (requests.length === 1) return route.abort();
    if (conversationUrl === requests[0].conversationUrl)
      return route.fulfill({
        status: 400,
        json: { error: "Test stopped at the original preparation." },
      });
    // Observe the second chat without starting real model work.
    const response = await page.request.get(conversationUrl, {
      headers: { "X-Workspace-Token": headers["x-workspace-token"] },
    });
    return route.fulfill({ status: 202, json: await response.json() });
  });

  const composer = page.getByRole("textbox", {
    name: "Message Direct Acquisition",
  });
  const sendButton = page.getByRole("button", { name: "Send to agent" });
  const resume = page.getByRole("button", {
    name: "Resume preparation",
    exact: true,
  });
  await page.goto("/");
  await connect(page);
  await page.getByLabel("Chat model: Choose model").click();
  await page.getByRole("button", { name: /Chat Model/ }).click();
  await composer.fill(firstBrief);
  await sendButton.click();
  await expect(resume).toBeVisible();
  await page.getByRole("button", { name: /Local reviewer/ }).click();
  await page.getByRole("button", { name: "Remove key" }).click();
  await expect(page.getByLabel("Chat model: Workspace default")).toBeVisible();
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  await composer.fill("Prepare an inventory campaign for £400.");
  await sendButton.click();
  await expect(
    page.getByRole("button", {
      name: "Prepare an inventory campaign for £400.",
      exact: true,
    }),
  ).toBeVisible();
  await expect.poll(() => requests.length).toBe(2);
  await expect(
    page.getByRole("button", { name: "New conversation", exact: true }),
  ).toBeVisible();
  expect(requests[1].conversationUrl).not.toBe(requests[0].conversationUrl);
  expect(requests[1].expected_revision).toBe(requests[0].expected_revision);
  expect(requests[1].handle).toBeUndefined();

  await page.getByRole("button", { name: firstBrief, exact: true }).click();
  await page.reload();
  await resume.click();
  await expect(
    page.getByText(/Reconnect the original OpenRouter key/),
  ).toBeVisible();
  expect(requests).toHaveLength(2);
  expect(planningPosts).toBe(0);

  // A tab that already lost its intent before this fix still has the original command.
  await page.evaluate(() => {
    const id = localStorage.getItem("conversation-selected");
    sessionStorage.removeItem(
      "conversation-preparation-intent:" + JSON.stringify([id, 1]),
    );
  });
  await page.reload();
  await connect(page);
  await page.getByLabel("Chat model: Choose model").click();
  await page.getByRole("button", { name: /Other Model/ }).click();
  await page
    .getByRole("button", { name: "Resume planning", exact: true })
    .click();
  await expect(
    page.getByText("Test stopped at the original preparation."),
  ).toBeVisible();
  expect(requests).toHaveLength(3);
  expect(requests[2]).toEqual({ ...requests[0], handle: "handle-2" });
  expect(planningPosts).toBe(0);

  await page.evaluate(async () => {
    const id = localStorage.getItem("conversation-selected");
    const response = await fetch(`/api/conversations/${id}/messages`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Workspace-Token": document.querySelector(
          'meta[name="workspace-token"]',
        ).content,
      },
      body: JSON.stringify({
        request_id: "new-revision",
        expected_revision: 1,
        content: "Use £450 for the contractor campaign.",
      }),
    });
    if (!response.ok) throw new Error(await response.text());
  });
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Resume planning", exact: true }),
  ).toBeVisible();
  await expect(resume).toHaveCount(0);
  expect(requests).toHaveLength(3);
});

test("connecting a browser key does not change a pending server-funded command", async ({
  page,
}) => {
  await mockProvider(page);
  const requests = [];
  await page.route("**/api/conversations/*/preparations", (route) => {
    expect(route.request().headers()["x-openrouter-handle"]).toBeUndefined();
    requests.push(route.request().postDataJSON().request_id);
    return requests.length === 1
      ? route.abort()
      : route.fulfill({
          status: 400,
          json: { error: "Test stopped at server preparation." },
        });
  });
  await page.goto("/");
  await send(page);
  const resume = page.getByRole("button", { name: "Resume preparation" });
  await expect(resume).toBeVisible();
  await connect(page);
  await page.getByLabel("Chat model: Choose model").click();
  await page.getByRole("button", { name: /Chat Model/ }).click();
  await resume.click();
  await expect(
    page.getByText("Test stopped at server preparation."),
  ).toBeVisible();
  expect(requests).toEqual([requests[0], requests[0]]);
});

test("losing the message acknowledgement preserves funding before preparation is first sent", async ({
  page,
}) => {
  await mockProvider(page);
  const messages = [];
  await page.route("**/api/conversations/*/messages", async (route) => {
    messages.push(route.request().postDataJSON().request_id);
    const response = await route.fetch();
    expect(response.ok()).toBe(true);
    return messages.length === 1 ? route.abort() : route.fulfill({ response });
  });
  const preparations = [];
  await page.route("**/api/conversations/*/preparations", (route) => {
    preparations.push(route.request().headers());
    return route.fulfill({
      status: 400,
      json: { error: "Test stopped at preparation." },
    });
  });

  await page.goto("/");
  await connect(page);
  await page.getByLabel("Chat model: Choose model").click();
  await page.getByRole("button", { name: /Chat Model/ }).click();
  await send(page);
  const retry = page.getByRole("button", { name: "Retry saving message" });
  await expect(retry).toBeEnabled();
  await page.getByRole("button", { name: /Local reviewer/ }).click();
  await page.getByRole("button", { name: "Remove key" }).click();
  await expect(page.getByLabel("Chat model: Workspace default")).toBeVisible();
  await page.reload();
  await retry.click();
  await expect(
    page.getByText(/Reconnect the original OpenRouter key/),
  ).toBeVisible();
  expect(messages).toEqual([messages[0], messages[0]]);
  expect(preparations).toEqual([]);

  await connect(page);
  await page.getByLabel("Chat model: Choose model").click();
  await page.getByRole("button", { name: /Other Model/ }).click();
  await page.getByRole("button", { name: "Resume preparation" }).click();
  await expect(page.getByText("Test stopped at preparation.")).toBeVisible();
  expect(preparations).toHaveLength(1);
  expect(preparations[0]["x-openrouter-handle"]).toBe("handle-2");
  expect(preparations[0]["x-openrouter-model"]).toBe(model.id);
  expect(preparations[0]["x-openrouter-tier"]).toBe(model.tier);
});

for (const scenario of ["committed", "missing", "superseded"]) {
  test(`older pending follow-up checks the saved receipt without a new POST, ${scenario}`, async ({
    page,
  }) => {
    await page.goto("/");
    const cid = await page.evaluate(async (scenario) => {
      const post = async (path, body) => {
        const response = await fetch(path, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Workspace-Token": document.querySelector(
              'meta[name="workspace-token"]',
            ).content,
          },
          body: JSON.stringify(body),
        });
        if (!response.ok) throw new Error(await response.text());
        return response.json();
      };
      const { id } = await post("/api/conversations", {
        title: "Legacy follow-up",
        request_id: crypto.randomUUID(),
      });
      const base = `/api/conversations/${id}`;
      await post(base + "/messages", {
        request_id: "brief",
        expected_revision: 0,
        content: "Prepare a contractor experiment.",
      });
      const requestId = "original-followup";
      const payload = {
        allow_model_copy: false,
        content: "Show status",
        expected_revision: 1,
      };
      if (scenario === "committed")
        await post(base + "/actions", { ...payload, request_id: requestId });
      if (scenario === "superseded")
        await post(base + "/messages", {
          request_id: "amend",
          expected_revision: 1,
          content: "Use £500 for contractors.",
        });
      sessionStorage.setItem(
        "conversation-pending-message",
        JSON.stringify({
          conversationId: id,
          ...payload,
          route: true,
        }),
      );
      sessionStorage.setItem(
        "workspace-pending:" + JSON.stringify([base + "/actions", payload]),
        requestId,
      );
      return id;
    }, scenario);
    let posts = 0;
    await page.route(`**/api/conversations/${cid}/actions`, (route) => {
      posts++;
      return route.abort();
    });
    await page.reload();
    const retry = page.getByRole("button", { name: "Retry saving message" });
    await retry.click();
    const composer = page.getByRole("textbox", {
      name: "Message Direct Acquisition",
    });
    if (scenario === "missing") {
      await expect(page.getByText(/no saved receipt yet/)).toBeVisible();
      await expect(composer).toBeDisabled();
      await expect(composer).toHaveValue("Show status");
      await page.reload();
      await expect(
        page.getByRole("button", { name: "Resend original follow-up" }),
      ).toBeVisible();
      expect(posts).toBe(0);
      expect(
        await page.evaluate(() => Object.values(sessionStorage)),
      ).toContain("original-followup");
      return;
    }
    await expect(retry).toHaveCount(0);
    await expect(composer).toBeEnabled();
    if (scenario === "committed") {
      await expect(
        page.getByRole("region", { name: "Saved follow-up" }),
      ).toBeVisible();
      await expect(composer).toHaveValue("");
    } else {
      await expect(page.getByText(/The brief has changed/)).toBeVisible();
      await expect(composer).toHaveValue("Show status");
    }
    expect(posts).toBe(0);
    expect(
      await page.evaluate(() =>
        sessionStorage.getItem("conversation-pending-message"),
      ),
    ).toBeNull();
  });
}
