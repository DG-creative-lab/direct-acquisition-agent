import { expect, chromium } from "@playwright/test";
import { execFileSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile, appendFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repository = fileURLToPath(new URL("../..", import.meta.url));
const python = process.env.JOURNEY_PYTHON || "python3";
const fixture = join(repository, "scripts/offline_journey_fixture.py");
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const save = (path, value) =>
  writeFile(path, JSON.stringify(value, null, 2) + "\n");
const rows = (csv) => csv.trim().split(/\r?\n/).slice(1);
const businessIds = (csv) => rows(csv).map((line) => line.split(",")[0]);

export function checkExactExports(
  { manifest, handoff, mailing, assignments },
  reviewed,
  accepted,
) {
  expect(accepted.subject).toEqual(reviewed.subject);
  expect(manifest).toEqual(reviewed.manifest);
  expect(manifest.organization).toBe(reviewed.subject.organization);
  expect(manifest.snapshot_id).toBe(reviewed.subject.snapshot_id);
  expect(accepted.approval.decision).toBe("approve");
  expect(accepted.approval.subject_id).toBe(reviewed.subject.id);
  expect(accepted.approval.case_id).toBe(reviewed.case_id);
  expect(handoff).toEqual(accepted.handoff);
  expect(handoff.subject_id).toBe(reviewed.subject.id);
  expect(handoff.draft_id).toBe(reviewed.subject.draft_id);
  expect(handoff.case_id).toBe(reviewed.case_id);
  expect(handoff.approval_id).toBe(accepted.approval.id);
  expect(handoff.mailing_sha256).toBe(manifest.mailing_sha256);
  expect(handoff.assignments_sha256).toBe(manifest.assignments_sha256);
  expect(hash(mailing)).toBe(manifest.mailing_sha256);
  expect(hash(assignments)).toBe(manifest.assignments_sha256);
  expect(rows(mailing.toString()).length).toBe(manifest.counts.mailed);
  expect(rows(assignments.toString()).length).toBe(
    manifest.counts.mailed + manifest.counts.holdout,
  );
}

async function server(root, port, generation) {
  const child = spawn(
    python,
    [
      fixture,
      "serve",
      "--root",
      root,
      "--port",
      String(port),
      "--generation",
      String(generation),
    ],
    { cwd: repository, env: process.env, stdio: ["ignore", "pipe", "pipe"] },
  );
  let errors = "";
  child.stderr.on("data", (data) => {
    errors += data;
  });
  const exited = new Promise((resolve) =>
    child.once("exit", (code, signal) => resolve({ code, signal })),
  );
  const address = await new Promise((resolve, reject) => {
    let output = "";
    const timer = setTimeout(
      () => reject(new Error("Workspace startup timed out. " + errors)),
      20000,
    );
    child.stdout.on("data", (data) => {
      output += data;
      if (output.includes("\n")) {
        clearTimeout(timer);
        try {
          resolve(JSON.parse(output.split("\n")[0]));
        } catch (error) {
          reject(error);
        }
      }
    });
    child.once("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.once("exit", () => {
      clearTimeout(timer);
      reject(new Error("Workspace exited during startup. " + errors));
    });
  }).catch((error) => {
    child.kill("SIGKILL");
    throw error;
  });
  return {
    ...address,
    child,
    exited,
    stop: async () => {
      if (child.exitCode === null && child.signalCode === null)
        child.kill("SIGTERM");
      await exited;
      if (errors) await appendFile(join(root, "server-stderr.log"), errors);
    },
  };
}

async function api(page, path, payload) {
  return page.evaluate(
    async ({ path, payload }) => {
      const response = await fetch(path, {
        method: payload === undefined ? "GET" : "POST",
        headers: {
          "X-Workspace-Token": document.querySelector(
            'meta[name="workspace-token"]',
          ).content,
          ...(payload === undefined
            ? {}
            : { "Content-Type": "application/json" }),
        },
        ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
      });
      return { status: response.status, body: await response.json() };
    },
    { path, payload },
  );
}

async function approve(page, region) {
  await region
    .getByRole("button", { name: "Approve this revision", exact: true })
    .click();
  await page
    .getByLabel("Review reason")
    .fill("Reviewed the exact synthetic audience, copy and evidence.");
  await page
    .getByRole("button", { name: "Record approval", exact: true })
    .click();
}

async function learningStep(page, region, label) {
  await region.getByRole("button", { name: label, exact: true }).click();
  await page
    .getByRole("button", {
      name: "Confirm synthetic learning step",
      exact: true,
    })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

export async function runJourney(browser, directory, width, committed) {
  await mkdir(directory, { recursive: true });
  const root = join(directory, "workspace");
  const result = {
    id: width === 1440 ? "desktop-journey" : "mobile-journey",
    viewport: { width, height: 1000 },
    lost_schedule_response: committed ? "after_commit" : "before_dispatch",
    checks: [],
    passed: false,
    external_requests: [],
    runtime: { node: process.version, browser: browser.version() },
  };
  let current, active, context, page;
  const pageErrors = [];
  const check = async (id, operation) => {
    active = id;
    const observed = await operation();
    result.checks.push({ id, passed: true, observed });
    await save(join(directory, "result.json"), result);
    return observed;
  };
  try {
    current = await server(root, 0, 0);
    const origin = current.url;
    context = await browser.newContext({
      viewport: result.viewport,
      acceptDownloads: true,
    });
    await context.tracing.start({
      screenshots: true,
      snapshots: true,
      sources: true,
    });
    await context.route("**/*", async (route) => {
      if (new URL(route.request().url()).origin !== origin) {
        result.external_requests.push(route.request().url());
        await route.abort();
      } else await route.continue();
    });
    page = await context.newPage();
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.goto(origin);
    await check("incomplete-and-corrected-brief", async () => {
      await page
        .getByLabel("Message Direct Acquisition")
        .fill(
          "Prepare a UK postal response experiment for contractors with £437 or £683.",
        );
      await page
        .getByRole("button", { name: "Send to agent", exact: true })
        .click();
      await expect(
        page.getByText(/Please state one absolute amount using £ or GBP/),
      ).toBeVisible();
      const cid = await page.evaluate(() =>
        localStorage.getItem("conversation-selected"),
      );
      const incomplete = (await api(page, "/api/conversations/" + cid)).body;
      expect(incomplete.current_plan.result.outcome).toBe("clarification");
      expect(incomplete.execution.used).toBe(0);
      expect(incomplete.campaigns).toHaveLength(0);
      await page.reload();
      await page
        .getByLabel("Message Direct Acquisition")
        .fill("Use GBP 600 as the total budget.");
      await page
        .getByRole("button", { name: "Send to agent", exact: true })
        .click();
      await page
        .getByRole("region", { name: "Choose campaign audience" })
        .getByRole("button", { name: "Use v1", exact: true })
        .click();
      await page.getByRole("button", { name: /Review campaign/ }).click();
      const corrected = (await api(page, "/api/conversations/" + cid)).body;
      expect(corrected.revision).toBe(2);
      expect(corrected.messages).toHaveLength(2);
      expect(corrected.current_plan.result.budget_pence).toBe(60000);
      return {
        conversation_id: cid,
        revisions: [incomplete.revision, corrected.revision],
        budget_pence: 60000,
        clarification_calls: incomplete.execution.used,
      };
    });
    const reviewRegion = page.getByRole("region", {
      name: "Campaign review in conversation",
    });
    await expect(reviewRegion.getByText("Review & approval")).toBeVisible();
    const sid = (await api(page, "/api/sessions")).body.sessions[0].id;
    const campaignPath = "/api/sessions/" + sid;
    let prepared = (await api(page, campaignPath)).body;
    let acceptedReview;
    await check("exact-review-and-money", async () => {
      await reviewRegion
        .getByText("Exact approval subject", { exact: true })
        .click();
      await expect(
        reviewRegion.getByText(prepared.review.subject.id, { exact: true }),
      ).toBeVisible();
      const manifest = prepared.review.manifest;
      const source = JSON.parse(
        await readFile(
          join(
            repository,
            "config/audience-catalogue/project-contractors-v1.json",
          ),
          "utf8",
        ),
      );
      expect(manifest.counts.input).toBe(source.records.length);
      expect(manifest.brief.budget_pence).toBe(60000);
      expect(manifest.brief.unit_cost_pence).toBe(85);
      expect(manifest.counts.input).toBe(
        manifest.counts.excluded +
          manifest.counts.eligible_unselected +
          manifest.counts.mailed +
          manifest.counts.holdout,
      );
      expect(manifest.variable_cost_pence).toBe(manifest.counts.mailed * 85);
      expect(manifest.variable_cost_pence).toBeLessThanOrEqual(60000);
      expect(prepared.review.approval_valid).toBe(false);
      expect(prepared.review.handoff).toBeNull();
      expect(
        (
          await api(page, campaignPath + "/approve", {
            request_id: "stale",
            subject_id: "obsolete-subject",
            reason: "Stale",
          })
        ).status,
      ).toBe(409);
      await approve(page, reviewRegion);
      const approved = (await api(page, campaignPath)).body;
      expect(approved.review.subject).toEqual(prepared.review.subject);
      expect(approved.review.approval_valid).toBe(true);
      expect(approved.review.approval.subject_id).toBe(
        prepared.review.subject.id,
      );
      expect(approved.review.handoff).toBeNull();
      await reviewRegion
        .getByRole("button", { name: "Simulate agency handoff", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Confirm simulated handoff", exact: true })
        .click();
      await expect(
        reviewRegion.getByRole("heading", {
          name: "Simulated handoff accepted",
        }),
      ).toBeVisible();
      const accepted = (await api(page, campaignPath)).body;
      expect(accepted.review.approval).toEqual(approved.review.approval);
      expect(accepted.review.handoff.subject_id).toBe(
        prepared.review.subject.id,
      );
      expect(accepted.review.handoff.mode).toBe("SYNTHETIC_NO_PRINT_NO_SEND");
      acceptedReview = accepted.review;
      await save(join(directory, "accepted-state.json"), accepted);
      return {
        session_id: sid,
        subject_id: prepared.review.subject.id,
        approval_id: acceptedReview.approval.id,
        handoff_id: acceptedReview.handoff.id,
        counts: manifest.counts,
        cost_pence: manifest.variable_cost_pence,
        budget_pence: manifest.brief.budget_pence,
      };
    });
    await check("exact-exports", async () => {
      const downloads = {};
      for (const [label, kind] of [
        ["acceptance receipt", "handoff"],
        ["manifest", "manifest"],
        ["mailing CSV", "mailing"],
        ["assignments CSV", "assignments"],
      ]) {
        const waiting = page.waitForEvent("download");
        await reviewRegion
          .getByRole("button", { name: "Download " + label, exact: true })
          .click();
        const download = await waiting;
        const path = join(directory, download.suggestedFilename());
        await download.saveAs(path);
        downloads[kind] = path;
      }
      const manifest = JSON.parse(await readFile(downloads.manifest, "utf8"));
      const handoff = JSON.parse(await readFile(downloads.handoff, "utf8"));
      const mailing = await readFile(downloads.mailing);
      const assignments = await readFile(downloads.assignments);
      checkExactExports(
        { manifest, handoff, mailing, assignments },
        prepared.review,
        acceptedReview,
      );
      return {
        subject_id: handoff.subject_id,
        approval_id: handoff.approval_id,
        handoff_id: handoff.id,
        mailed: rows(mailing.toString()).length,
        enrolled: rows(assignments.toString()).length,
        mailing_sha256: hash(mailing),
        assignments_sha256: hash(assignments),
      };
    });
    const learning = page.getByRole("region", {
      name: "Campaign learning in conversation",
    });
    await learningStep(page, learning, "Open outcome window");
    const opened = (await api(page, campaignPath)).body;
    await save(join(directory, "cohort.json"), opened.learning.cohort);
    const expected = JSON.parse(
      execFileSync(
        python,
        [
          fixture,
          "recordings",
          "--assignments",
          join(directory, "assignments.csv"),
          "--cohort",
          join(directory, "cohort.json"),
          "--directory",
          join(directory, "recordings"),
        ],
        { encoding: "utf8", cwd: repository },
      ),
    );
    const controls = learning.getByRole("region", {
      name: "Monitoring setup and controls",
    });
    await check("lost-schedule-response-and-reload", async () => {
      await controls
        .getByLabel("Recorded synthetic reports", { exact: true })
        .setInputFiles([
          join(directory, "recordings/early.json"),
          join(directory, "recordings/final.json"),
        ]);
      await controls
        .getByLabel("First report check, UTC", { exact: true })
        .fill(new Date(expected.early_time * 1000).toISOString().slice(0, 16));
      const requests = [];
      await page.route("**/api/sessions/*/monitoring-start", async (route) => {
        requests.push(route.request().postDataJSON());
        if (requests.length === 1) {
          if (committed) await route.fetch();
          await route.abort("failed");
        } else await route.continue();
      });
      await controls
        .getByRole("button", {
          name: "Review monitoring schedule",
          exact: true,
        })
        .click();
      await page
        .getByRole("dialog")
        .getByRole("button", {
          name: "Confirm monitoring schedule",
          exact: true,
        })
        .click();
      await expect(
        controls.getByRole("button", {
          name: "Recover saved monitoring request",
          exact: true,
        }),
      ).toBeVisible();
      await page.reload();
      await controls
        .getByRole("button", {
          name: "Recover saved monitoring request",
          exact: true,
        })
        .click();
      await expect(controls).toContainText("Schedule revision 1.");
      expect(requests).toHaveLength(2);
      expect(requests[1]).toEqual(requests[0]);
      const audit = JSON.parse(
        execFileSync(python, [fixture, "audit", "--root", root], {
          encoding: "utf8",
        }),
      );
      expect(audit.schedules).toHaveLength(1);
      expect(audit.sources).toBe(2);
      expect(audit.outcomes).toBe(0);
      await save(
        join(directory, "schedule-requests.json"),
        requests.map((request) => ({
          request_id: request.request_id,
          cohort_id: request.cohort_id,
          interval_seconds: request.interval_seconds,
          reports_sha256: request.reports.map(hash),
        })),
      );
      return {
        request_id: requests[0].request_id,
        attempts: 2,
        schedules: 1,
        sources: 2,
        observations: 0,
      };
    });
    await check("cadence-pause-and-resume", async () => {
      await controls
        .getByLabel("Check every, in minutes", { exact: true })
        .fill("30");
      await controls
        .getByRole("button", { name: "Save cadence", exact: true })
        .click();
      await expect(controls).toContainText("Schedule revision 2.");
      await controls
        .getByRole("button", { name: "Pause monitoring", exact: true })
        .click();
      await expect(
        controls.getByRole("button", {
          name: "Resume monitoring",
          exact: true,
        }),
      ).toBeVisible();
      await page.reload();
      expect((await api(page, campaignPath)).body.learning.received).toBe(0);
      await controls
        .getByRole("button", { name: "Resume monitoring", exact: true })
        .click();
      await expect(controls).toContainText("Schedule revision 4.");
      const plan = (await api(page, campaignPath)).body.learning.monitoring;
      expect(plan.interval_seconds).toBe(1800);
      expect(plan.next_due).toBe(expected.early_time);
      await page.screenshot({
        path: join(directory, "monitoring.png"),
        fullPage: true,
      });
      return {
        revision: plan.revision,
        interval_seconds: plan.interval_seconds,
        original_due: plan.next_due,
      };
    });
    await check("process-restart-after-import", async () => {
      await writeFile(join(root, "crash-after-import"), "armed\n");
      const originalPid = current.pid;
      await learning
        .getByRole("button", {
          name: "Advance to next report check",
          exact: true,
        })
        .click();
      await page
        .getByRole("button", {
          name: "Confirm synthetic learning step",
          exact: true,
        })
        .click();
      expect((await current.exited).code).toBe(91);
      const interrupted = JSON.parse(
        await readFile(join(root, "import-before-crash.json"), "utf8"),
      );
      expect(interrupted.observations).toBe(4);
      expect(interrupted.progress.position).toBe(0);
      await current.stop();
      current = await server(root, Number(new URL(origin).port), 1);
      expect(current.url).toBe(origin);
      expect(current.pid).not.toBe(originalPid);
      await page.reload();
      await expect
        .poll(
          async () =>
            (await api(page, campaignPath)).body.learning.monitoring.position,
          { timeout: 10000 },
        )
        .toBe(1);
      await learning
        .getByRole("button", {
          name: "Check saved learning request",
          exact: true,
        })
        .click();
      await page
        .getByRole("button", {
          name: "Check original learning request",
          exact: true,
        })
        .click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      const recovered = (await api(page, campaignPath)).body.learning;
      expect(recovered.received).toBe(4);
      expect(recovered.missing).toBe(expected.observations - 4);
      expect(recovered.beliefs).toEqual([]);
      expect(
        recovered.events.filter(
          (event) => event.kind === "provider_report_imported",
        ),
      ).toHaveLength(1);
      await save(join(directory, "recovered-learning.json"), recovered);
      await page.screenshot({
        path: join(directory, "recovery.png"),
        fullPage: true,
      });
      return {
        original_pid: originalPid,
        recovered_pid: current.pid,
        observations_before: 4,
        observations_after: recovered.received,
        report_imports: 1,
        lease_clock_advance_seconds: 31,
      };
    });
    await check("mature-learning-counted-once", async () => {
      await learningStep(page, learning, "Advance to next report check");
      const imported = (await api(page, campaignPath)).body.learning;
      expect(imported.received).toBe(expected.observations);
      expect(imported.beliefs).toEqual([]);
      expect(
        imported.events
          .filter((event) => event.kind === "provider_report_imported")
          .map((event) => [event.payload.report_id, event.payload.added]),
      ).toEqual([
        ["early", 4],
        ["final", expected.observations - 4],
      ]);
      await learningStep(page, learning, "Finalize recorded learning");
      const final = (await api(page, campaignPath)).body;
      expect(final.learning.finalization.observations).toBe(
        expected.observations,
      );
      expect(final.learning.finalization.successes).toBe(4);
      expect(
        final.learning.beliefs.reduce((sum, group) => sum + group.trials, 0),
      ).toBe(expected.observations);
      expect(
        final.learning.beliefs
          .filter((group) => group.arm === "no_mail")
          .reduce((sum, group) => sum + group.trials, 0),
      ).toBe(expected.controls);
      const events = final.learning.events;
      await page.reload();
      expect((await api(page, campaignPath)).body.learning.events).toEqual(
        events,
      );
      await save(join(directory, "final-state.json"), final);
      return {
        observations: expected.observations,
        successes: 4,
        controls: expected.controls,
        finalization_events: events.filter(
          (event) => event.kind === "cohort_finalized",
        ).length,
      };
    });
    await check("independent-followup-needs-fresh-approval", async () => {
      const followup = page.getByRole("region", {
        name: "Next experiment in conversation",
      });
      await followup
        .getByRole("button", {
          name: "Propose follow-up experiment",
          exact: true,
        })
        .click();
      await followup
        .getByRole("button", { name: "Prepare offline follow-up", exact: true })
        .click();
      const childRegion = followup.getByRole("region", {
        name: "Campaign review in conversation",
      });
      await expect(childRegion.getByText("Review & approval")).toBeVisible();
      const parent = (await api(page, campaignPath)).body;
      const childId = parent.followups[0].session_id;
      const child = (await api(page, "/api/sessions/" + childId)).body;
      expect(child.review.approval_valid).toBe(false);
      expect(child.review.handoff).toBeNull();
      expect(child.review.subject.id).not.toBe(prepared.review.subject.id);
      const token = await page.evaluate(
        () => document.querySelector('meta[name="workspace-token"]').content,
      );
      const response = await context.request.get(
        origin +
          "/api/sessions/" +
          childId +
          "/artifacts/assignments?subject_id=" +
          encodeURIComponent(child.review.subject.id),
        { headers: { "X-Workspace-Token": token } },
      );
      // Use the exact-subject API for the still-unapproved child's export.
      const childCsv = await response.text();
      expect(response.status()).toBe(200);
      const intersection = businessIds(childCsv).filter((id) =>
        expected.business_ids.includes(id),
      );
      expect(intersection).toEqual([]);
      await writeFile(join(directory, "followup-assignments.csv"), childCsv);
      await save(join(directory, "followup-state.json"), child);
      await page.screenshot({
        path: join(directory, "followup.png"),
        fullPage: true,
      });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      expect(pageErrors).toEqual([]);
      const trace = (await readFile(join(root, "provider.jsonl"), "utf8"))
        .trim()
        .split("\n")
        .map(JSON.parse);
      result.fake_provider_calls = trace.filter(
        (entry) => entry.kind === "scripted_model_call",
      ).length;
      result.blocked_external_attempts = trace.filter(
        (entry) => entry.kind === "blocked_external_attempt",
      ).length;
      expect(result.fake_provider_calls).toBe(1);
      expect(result.blocked_external_attempts).toBe(0);
      return {
        session_id: childId,
        subject_id: child.review.subject.id,
        shared_businesses: intersection.length,
        approved: child.review.approval_valid,
        accepted: !!child.review.handoff,
      };
    });
    result.passed = true;
  } catch (error) {
    result.checks.push({
      id: active ?? "startup",
      passed: false,
      error: String(error),
    });
    if (page && !page.isClosed())
      await page
        .screenshot({ path: join(directory, "failure.png"), fullPage: true })
        .catch(() => {});
  } finally {
    if (context) {
      await context.tracing
        .stop({ path: join(directory, "trace.zip") })
        .catch(() => {});
      await context.close();
    }
    if (current) await current.stop();
    result.page_errors = pageErrors;
    await save(join(directory, "result.json"), result);
  }
  return result;
}

async function main() {
  const directory = resolve(process.argv[2]);
  const browser = await chromium.launch({ headless: true });
  const results = [];
  try {
    for (const [width, committed] of [
      [1440, true],
      [390, false],
    ]) {
      results.push(
        await runJourney(
          browser,
          join(directory, width === 1440 ? "desktop" : "mobile"),
          width,
          committed,
        ),
      );
    }
  } finally {
    await browser.close();
  }
  await save(join(directory, "browser-results.json"), results);
  process.exitCode = results.every(
    (row) => row.passed && !row.external_requests.length,
  )
    ? 0
    : 1;
}
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
)
  await main();
