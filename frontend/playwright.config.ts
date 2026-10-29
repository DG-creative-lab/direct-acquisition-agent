import { defineConfig } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("..", import.meta.url));
export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.spec.mjs",
  workers: 1,
  fullyParallel: false,
  outputDir: root + "/.local/browser-test-results",
  reporter: "list",
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:8770",
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: `python3 -m acquisition.workspace_server --port 8770 --root .local/browser-tests/${randomUUID()}`,
    cwd: root,
    env: {
      PYTHONPATH: "src",
      OPENROUTER_API_KEY: "offline-tests-must-not-use-live-credentials",
    },
    url: "http://127.0.0.1:8770",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
