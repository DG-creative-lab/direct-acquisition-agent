import { test, expect } from "@playwright/test";

test("YouTube draft, exact review and manual JSON export survive reload", async ({
  page,
}) => {
  const providerRequests = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/openrouter/"))
      providerRequests.push(request.url());
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Prepare a YouTube brief/ }).click();
  await expect(
    page.getByLabel("Allow a YouTube placement draft for this request"),
  ).toBeChecked();
  await page
    .getByRole("button", { name: "Send to agent", exact: true })
    .click();
  const artifact = page.getByRole("region", { name: "YouTube campaign draft" });
  await expect(artifact).toBeVisible();
  await expect(artifact).toContainText("Revision 1");
  await expect(
    page.getByRole("button", { name: "Resume planning", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText(/single total campaign budget/)).toHaveCount(0);
  await artifact
    .getByLabel("Campaign title", { exact: true })
    .fill("YouTube comparison experiment");
  await artifact.getByRole("button", { name: "Save YouTube draft" }).click();
  await expect(artifact).toContainText("Revision 2");
  await expect(
    artifact.getByRole("button", { name: "Download manual JSON" }),
  ).toBeDisabled();
  await artifact
    .getByRole("button", { name: "Approve this YouTube package" })
    .click();
  await expect(artifact).toContainText("Revision 2 · Approved");
  const downloaded = page.waitForEvent("download");
  await artifact.getByRole("button", { name: "Download manual JSON" }).click();
  const file = await downloaded;
  const stream = await file.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const exported = JSON.parse(Buffer.concat(chunks).toString());
  expect(exported.schema).toBe("youtube-manual-export/v1");
  expect(exported.payload.package.revision).toBe(2);
  expect(exported.payload.package.title).toBe("YouTube comparison experiment");
  expect(exported.payload.package.groups).toHaveLength(2);
  expect(exported.payload.package.groups[0].placements[0].label).toBe(
    "Fictional placement",
  );
  const preview = await page.context().newPage();
  await preview.goto(exported.payload.package.groups[0].viewer_path);
  await expect(
    preview.getByText(
      "Preview only. No playback or choice events are collected.",
    ),
  ).toBeVisible();
  await expect(preview.locator("video,audio")).toHaveCount(2);
  expect(
    await preview
      .locator("video,audio")
      .first()
      .evaluate((element) => element.error),
  ).toBeNull();
  await preview.close();
  await page.reload();
  await expect(artifact).toContainText("Revision 2 · Approved");
  await artifact
    .getByLabel("Campaign title", { exact: true })
    .fill("Revised plan");
  await artifact.getByRole("button", { name: "Save YouTube draft" }).click();
  await expect(artifact).toContainText("Revision 3 · Unapproved");
  await expect(
    artifact.getByRole("button", { name: "Download manual JSON" }),
  ).toBeDisabled();
  expect(providerRequests).toEqual([]);
});

test("YouTube advice without draft permission never creates an artifact", async ({
  page,
}) => {
  await page.goto("/");
  await page
    .getByLabel("Message Direct Acquisition", { exact: true })
    .fill("Suggest YouTube contexts for a video editor; advice only.");
  await expect(
    page.getByLabel("Allow a YouTube placement draft for this request"),
  ).not.toBeChecked();
  await page
    .getByRole("button", { name: "Send to agent", exact: true })
    .click();
  await expect(
    page.getByText(/Suggested contexts: Video editing/),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "YouTube campaign draft" }),
  ).toHaveCount(0);
  await expect(
    page.getByText("Authored offline · $0 · Approval is separate"),
  ).toBeVisible();
});

test("YouTube lost message reply retries the original request after reload", async ({
  page,
}) => {
  const sent = [];
  let loseReply = true;
  await page.route("**/youtube-messages", async (route) => {
    sent.push(route.request().postDataJSON());
    const response = await route.fetch();
    if (loseReply) {
      loseReply = false;
      await route.abort();
    } else await route.fulfill({ response });
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Prepare a YouTube brief/ }).click();
  await page
    .getByRole("button", { name: "Send to agent", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Retry saving message", exact: true }),
  ).toBeEnabled();
  await page.reload();
  await page
    .getByRole("button", { name: "Retry saving message", exact: true })
    .click();
  await expect(
    page.getByLabel("Message Direct Acquisition", { exact: true }),
  ).toBeEmpty();
  await expect(
    page.getByRole("region", { name: "YouTube campaign draft" }),
  ).toContainText("Revision 1");
  expect(sent).toHaveLength(2);
  expect(sent[0]).toEqual(sent[1]);
  await expect(
    page.getByText(
      "Prepared an unapproved YouTube placement draft from authored context. Review the exact package below.",
      { exact: true },
    ),
  ).toHaveCount(1);
});

test("a definitely rejected YouTube message unlocks the composer", async ({
  page,
}) => {
  await page.goto("/");
  await page.route("**/youtube-messages", (route) =>
    route.fulfill({
      status: 409,
      json: {
        error: "The conversation changed. Review it before sending again.",
        message_not_saved: true,
      },
    }),
  );
  await page.getByRole("button", { name: /Prepare a YouTube brief/ }).click();
  await page
    .getByRole("button", { name: "Send to agent", exact: true })
    .click();
  await expect(
    page.getByLabel("Message Direct Acquisition", { exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Retry saving message", exact: true }),
  ).toHaveCount(0);
  await page.unroute("**/youtube-messages");
  await page
    .getByRole("button", { name: "Send to agent", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "YouTube campaign draft" }),
  ).toContainText("Revision 1");
});

for (const content of [
  "Prepare a postcard campaign",
  "Prepare postcards for UK contractors",
]) {
  test(`YouTube follow-up leaves the native route for: ${content}`, async ({
    page,
  }) => {
    // Stop at saved postal admission. This regression must make no planning call.
    await page.route("**/preparations", (route) =>
      route.fulfill({
        status: 409,
        json: {
          error: "Planning deliberately stopped by the offline routing test.",
        },
      }),
    );
    await page.goto("/");
    await page
      .getByLabel("Message Direct Acquisition", { exact: true })
      .fill("Suggest YouTube contexts for video editors; advice only.");
    await page
      .getByRole("button", { name: "Send to agent", exact: true })
      .click();
    await expect(
      page.getByText(/Suggested contexts: Video editing/),
    ).toBeVisible();
    await page
      .getByLabel("Message Direct Acquisition", { exact: true })
      .fill(content);
    await expect(
      page.getByLabel("Allow a YouTube placement draft for this request"),
    ).toHaveCount(0);
    const response = page.waitForResponse(
      (response) =>
        /\/api\/conversations\/[^/]+\/messages$/.test(response.url()) &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Send to agent", exact: true })
      .click();
    const saved = await response;
    expect(saved.status()).toBe(200);
    const view = await saved.json();
    expect(view.revision).toBe(2);
    expect(view.messages.at(-1).content).toBe(content);
    expect(view.messages).toHaveLength(2);
    await expect(
      page.getByLabel("Message Direct Acquisition", { exact: true }),
    ).toBeEmpty();
  });
}

for (const channel of [
  "emails",
  "e-mails",
  "postcards",
  "call scripts",
  "human calls",
  "phone calls",
]) {
  test(`mixed YouTube and ${channel} clarifies without a draft`, async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Prepare a YouTube brief/ }).click();
    await page
      .getByLabel("Message Direct Acquisition", { exact: true })
      .fill(`Prepare YouTube and ${channel} for this product`);
    const response = page.waitForResponse(
      (response) =>
        response.url().endsWith("/youtube-messages") &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "Send to agent", exact: true })
      .click();
    const saved = await response;
    expect(saved.status()).toBe(200);
    const interaction = (await saved.json()).youtube_interactions[0];
    expect(interaction.reason_code).toBe("channel_ambiguous");
    expect(interaction.campaign_id).toBeNull();
    expect(interaction.run_id).toBeNull();
    await expect(
      page.getByText(
        "Which channel should I prepare: YouTube or the other requested channel?",
        { exact: true },
      ),
    ).toBeVisible();
    await expect(
      page.getByRole("region", { name: "YouTube campaign draft" }),
    ).toHaveCount(0);
  });
}
