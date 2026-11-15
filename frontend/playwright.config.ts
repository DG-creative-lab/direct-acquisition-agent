import { defineConfig } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("..", import.meta.url));
const shard = process.env.BROWSER_SHARD || "1";
if (!/^[12]$/.test(shard)) throw new Error("BROWSER_SHARD must be 1 or 2");
const partitions = process.env.BROWSER_SHARDS || "1";
if (!/^[12]$/.test(partitions) || Number(shard) > Number(partitions))
  throw new Error("BROWSER_SHARDS must be 1 or 2 and include BROWSER_SHARD");
// Whole-file partition from the measured local run. New files join partition 2.
const firstPartition = [
  "**/chat-review.spec.mjs",
  "**/review-regressions.spec.mjs",
];
const port = 8769 + Number(shard);
const baseURL = `http://127.0.0.1:${port}`;
export default defineConfig({
  testDir: "./tests",
  testMatch:
    partitions === "2" && shard === "1" ? firstPartition : "**/*.spec.mjs",
  testIgnore: partitions === "2" && shard === "2" ? firstPartition : [],
  workers: 1,
  fullyParallel: false,
  outputDir: root + `/.local/browser-test-results/shard-${shard}`,
  reporter: [
    ["list"],
    [
      "json",
      { outputFile: root + `/.local/browser-reports/shard-${shard}.json` },
    ],
  ],
  timeout: 30000,
  use: {
    baseURL,
    browserName: "chromium",
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: `python3 -m acquisition.workspace_server --port ${port} --root .local/browser-tests/shard-${shard}-${randomUUID()}`,
    cwd: root,
    env: {
      PYTHONPATH: "src",
      OPENROUTER_API_KEY: "offline-tests-must-not-use-live-credentials",
    },
    url: baseURL,
    reuseExistingServer: false,
    timeout: 30000,
  },
});
