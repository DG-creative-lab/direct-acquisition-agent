import { test, expect } from "@playwright/test";
import { mkdtemp, rm, readFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { createHash } from "node:crypto";
import { checkExactExports, runJourney } from "../scripts/offline-journey.mjs";

test("export evidence rejects internally consistent files from another campaign", () => {
  const hash = (value) => createHash("sha256").update(value).digest("hex");
  const bundle = (identity) => {
    const mailing = Buffer.from(`business_id\n${identity}\n`);
    const assignments = Buffer.from(`business_id\n${identity}\ncontrol\n`);
    const manifest = {
      organization: "fixture-org",
      snapshot_id: "snapshot-" + identity,
      counts: { mailed: 1, holdout: 1 },
      mailing_sha256: hash(mailing),
      assignments_sha256: hash(assignments),
    };
    const subject = {
      id: "subject-" + identity,
      draft_id: "draft-" + identity,
      case_id: "case-" + identity,
      organization: manifest.organization,
      snapshot_id: manifest.snapshot_id,
    };
    const approval = {
      id: "approval-" + identity,
      subject_id: subject.id,
      case_id: subject.case_id,
      decision: "approve",
    };
    const handoff = {
      id: "handoff-" + identity,
      subject_id: subject.id,
      draft_id: subject.draft_id,
      case_id: subject.case_id,
      approval_id: approval.id,
      mailing_sha256: manifest.mailing_sha256,
      assignments_sha256: manifest.assignments_sha256,
    };
    return {
      files: { manifest, handoff, mailing, assignments },
      review: {
        manifest,
        subject,
        approval,
        handoff,
        case_id: subject.case_id,
      },
    };
  };
  const original = bundle("displayed"),
    other = bundle("other");
  expect(() =>
    checkExactExports(original.files, original.review, original.review),
  ).not.toThrow();
  // Same population, valid internal hashes, coordinated replacement of every file.
  expect(() =>
    checkExactExports(other.files, original.review, original.review),
  ).toThrow();
  for (const field of [
    "id",
    "subject_id",
    "draft_id",
    "case_id",
    "approval_id",
    "mailing_sha256",
    "assignments_sha256",
  ]) {
    const files = {
      ...original.files,
      handoff: { ...original.files.handoff, [field]: "substituted" },
    };
    expect(() =>
      checkExactExports(files, original.review, original.review),
    ).toThrow();
  }
  const altered = {
    ...original.files,
    manifest: { ...original.files.manifest, snapshot_id: "other-snapshot" },
  };
  expect(() =>
    checkExactExports(altered, original.review, original.review),
  ).toThrow();
});

// The shared driver owns its trace, including standalone evaluation runs.
test.use({ trace: "off" });

for (const [width, committed] of [
  [1440, true],
  [390, false],
]) {
  test(`complete offline journey at ${width}px preserves monitoring and restart identities`, async ({
    browser,
  }, testInfo) => {
    test.setTimeout(120000);
    const directory = await mkdtemp(
      join(tmpdir(), "acquisition-offline-journey-"),
    );
    try {
      const result = await runJourney(browser, directory, width, committed);
      await testInfo.attach("journey-result", {
        body: JSON.stringify(result, null, 2),
        contentType: "application/json",
      });
      if (!result.passed) {
        await testInfo.attach("journey-trace", {
          path: join(directory, "trace.zip"),
          contentType: "application/zip",
        });
        await testInfo.attach("journey-failure", {
          body: await readFile(join(directory, "failure.png")),
          contentType: "image/png",
        });
      }
      expect(result, JSON.stringify(result.checks)).toMatchObject({
        passed: true,
        external_requests: [],
        page_errors: [],
      });
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
}
