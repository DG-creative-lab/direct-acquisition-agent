import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

for (const failure of [
  "provider_http_401",
  "provider_request_failed",
  "reserved",
]) {
  test(`saved ${failure} remains inspectable after reload without a generate loop`, async ({
    page,
  }) => {
    const root = await mkdtemp(join(tmpdir(), "acquisition-failed-run-"));
    const cwd = fileURLToPath(new URL("../..", import.meta.url));
    const script = `
import sys
from pathlib import Path
from unittest.mock import patch
from acquisition.workspace import Workspace
from acquisition.workspace_server import WorkspaceServer
from acquisition.reasoning import ModelError
from acquisition.contracts import Conflict
from test_conversations import PlannerModel, proposal
w = Workspace(Path(sys.argv[1]), real_clock=lambda: 1792972800.0)
c = w.create_conversation('failure', 'Failed generation example')
w.message_conversation(c['id'], 'message', 0, 'Use £300 and model copy for contractors.')
model = PlannerModel(proposal(budget_pence=30000, copy_mode='model'))
with patch('acquisition.workspace.openrouter_key', return_value='fixture'), patch('acquisition.workspace.OpenRouter', return_value=model):
    p = w.plan_conversation(c['id'], 'plan', 1)['current_plan']['result']
    failure = sys.argv[2]
    with patch.object(model, 'complete', side_effect=KeyboardInterrupt() if failure == 'reserved' else ModelError(failure)):
        try:
            w.draft_conversation(c['id'], 'draft', 1, p['id'])
        except (Conflict, KeyboardInterrupt):
            pass
        if failure == 'reserved':
            w.real_clock = lambda: 1792973000.0
            try:
                w.draft_conversation(c['id'], 'draft', 1, p['id'])
            except Conflict:
                pass
server = WorkspaceServer(0, w, Path('frontend/dist'))
print('http://127.0.0.1:' + str(server.server_port), flush=True)
server.serve_forever()
`;
    const child = spawn("python3", ["-c", script, root, failure], {
      cwd,
      env: { ...process.env, PYTHONPATH: "src:tests" },
      stdio: ["ignore", "pipe", "pipe"],
    });
    const exited = new Promise((resolve) => child.once("exit", resolve));
    try {
      const url = await new Promise((resolve, reject) => {
        let output = "",
          errors = "";
        const timer = setTimeout(
          () => reject(new Error("Fixture server did not start: " + errors)),
          10000,
        );
        child.stderr.on("data", (data) => {
          errors += data.toString();
        });
        child.stdout.on("data", (data) => {
          output += data.toString();
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
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(url);
      await page
        .getByRole("button", { name: "Failed generation example", exact: true })
        .click();
      await expect(
        page.getByText(
          failure === "provider_http_401"
            ? "Campaign generation failed"
            : "Generation outcome is uncertain",
          { exact: true },
        ),
      ).toBeVisible();
      await expect(
        page.getByText(
          failure === "provider_http_401"
            ? /OpenRouter rejected the API key \(401\)/
            : /Inspect the original run before requesting another generation/,
        ),
      ).toBeVisible();
      await expect(
        page.getByRole("button", {
          name: "Generate campaign copy",
          exact: true,
        }),
      ).toHaveCount(0);
      await page.getByText("Inspect generation run", { exact: true }).click();
      if (failure !== "provider_http_401") {
        await expect(page.getByText(/Unresolved call:/)).toBeVisible();
        await expect(
          page.getByRole("button", { name: "Resume campaign preparation" }),
        ).toHaveCount(0);
        await expect(
          page.getByText(/send a new message to create a fresh proposal/),
        ).toHaveCount(0);
      }
      await expect(
        page.getByText("creative.generate_conversation.v3: ModelError", {
          exact: true,
        }),
      ).toBeVisible();
      await page.reload();
      await expect(
        page.getByText(
          failure === "provider_http_401"
            ? "Campaign generation failed"
            : "Generation outcome is uncertain",
          { exact: true },
        ),
      ).toBeVisible();
      await expect(
        page.getByRole("button", {
          name: "Generate campaign copy",
          exact: true,
        }),
      ).toHaveCount(0);
    } finally {
      child.kill("SIGTERM");
      await exited;
      await rm(root, { recursive: true, force: true });
    }
  });
}
