import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { isAbsolute, relative } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const cli = createRequire(import.meta.url).resolve("@playwright/test/cli");
const required = JSON.parse(
  readFileSync(new URL("../browser-smoke.json", import.meta.url), "utf8"),
);

function discover(suite, shard = 1, partitions = 1) {
  const result = spawnSync(
    process.execPath,
    [cli, "test", "--list", "--reporter=json"],
    {
      cwd: root,
      env: {
        ...process.env,
        BROWSER_SUITE: suite,
        BROWSER_SHARD: String(shard),
        BROWSER_SHARDS: String(partitions),
      },
      encoding: "utf8",
    },
  );
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const report = JSON.parse(result.stdout);
  assert.equal(report.errors?.length ?? 0, 0, result.stdout);
  const specs = [];
  function visit(suites) {
    for (const item of suites) {
      specs.push(...(item.specs ?? []));
      visit(item.suites ?? []);
    }
  }
  visit(report.suites);
  return specs.map((spec) => ({
    id: spec.id,
    key: JSON.stringify([
      isAbsolute(spec.file)
        ? relative(report.config.rootDir, spec.file)
        : spec.file,
      spec.title,
    ]),
  }));
}

const full = discover("full");
const smoke = discover("smoke");
const expected = required.map(({ file, title }) =>
  JSON.stringify([file, title]),
);
assert.ok(expected.length > 0, "The smoke contract must not be empty");
assert.equal(
  new Set(expected).size,
  expected.length,
  "Duplicate smoke contract",
);
assert.deepEqual(smoke.map((test) => test.key).sort(), expected.sort());
const fullIds = new Set(full.map((test) => test.id));
assert.equal(fullIds.size, full.length, "Duplicate full-suite identity");
assert.ok(smoke.every((test) => fullIds.has(test.id)));
const partitions = [discover("full", 1, 2), discover("full", 2, 2)];
assert.deepEqual(
  partitions
    .flat()
    .map((test) => test.id)
    .sort(),
  full.map((test) => test.id).sort(),
  "Full partitions must retain every discovered test exactly once",
);
console.log(
  `Browser catalogue: ${full.length} full, ${smoke.length} smoke; full partitions ${partitions.map((group) => group.length).join("/")}. All identities covered exactly once.`,
);
