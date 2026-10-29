import "server-only";

import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { connection } from "next/server";
import { cadenceEntries, dueEntries, nextActionLine } from "./followups.mjs";
import { readInbox } from "./inbox.mjs";
import { resolvePaths, resolveReportFile } from "./paths.mjs";
import { reportHeader } from "./report-header.mjs";
import { hintFromHeading, listRuns } from "./runs.mjs";
import { readStateLabels } from "./states.mjs";
import { readStatusLog } from "./status-log.mjs";
import { readTrackerFile } from "./tracker.mjs";

export function gtjobRoot() {
  const fromEnv = process.env.GTJOB_ROOT?.trim();
  if (fromEnv) return path.resolve(fromEnv);
  return path.resolve(process.cwd(), "..");
}

export async function loadStudio() {
  await connection();
  const paths = resolvePaths(gtjobRoot());
  const runs = listRuns(paths.outDir);
  const inbox = readInbox(paths.inboxPath);
  const tracker = paths.trackerPath ? readTrackerFile(paths.trackerPath) : null;
  const labels = paths.careerOpsRoot ? readStateLabels(paths.careerOpsRoot) : null;
  const cadence = loadCadence(paths, tracker);
  return { paths, runs, inbox, tracker, labels, cadence };
}

function loadCadence(
  paths: ReturnType<typeof resolvePaths>,
  tracker: ReturnType<typeof readTrackerFile> | null,
) {
  if (!paths.careerOpsRoot || !paths.cadencePath || !existsSync(paths.cadencePath)) {
    return { ok: true, skipped: true, entries: [], due: [], error: "" };
  }
  if (!tracker || !tracker.ok || tracker.missing) {
    return { ok: true, skipped: true, entries: [], due: [], error: "" };
  }
  const result = spawnSync(process.execPath, [paths.cadencePath, "--json"], {
    cwd: paths.careerOpsRoot,
    env: { ...process.env, CAREER_OPS_ROOT: paths.careerOpsRoot },
    encoding: "utf8",
    timeout: 20_000,
  });
  if (result.status !== 0 || !result.stdout) {
    const stderr = `${result.stderr ?? ""} ${result.error?.message ?? ""}`.trim();
    return { ok: false, skipped: false, entries: [], due: [], error: stderr || "followup-cadence.mjs failed" };
  }
  try {
    const entries = cadenceEntries(JSON.parse(result.stdout));
    return { ok: true, skipped: false, entries, due: dueEntries(entries), error: "" };
  } catch {
    return { ok: false, skipped: false, entries: [], due: [], error: "followup-cadence.mjs did not return JSON" };
  }
}

export function entryFor(cadence: Awaited<ReturnType<typeof loadStudio>>["cadence"], num: string) {
  return cadence.entries.find((entry) => entry.num === num) ?? null;
}

export function actionLine(cadence: Awaited<ReturnType<typeof loadStudio>>["cadence"], num: string) {
  if (!cadence.ok) return "Open the report";
  return nextActionLine(entryFor(cadence, num));
}

export function readCareerReport(careerOpsRoot: string, href: string) {
  const file = resolveReportFile(careerOpsRoot, href);
  if (!file) return { file: "", found: false, header: null as ReturnType<typeof reportHeader> | null };
  if (!existsSync(file)) return { file, found: false, header: null };
  const text = readFileSync(file, "utf8").slice(0, 80_000);
  return { file, found: true, header: reportHeader(text) };
}

export function hintMatches(
  heading: string,
  rows: { num: string; company: string; role: string }[],
) {
  const hint = hintFromHeading(heading);
  if (!hint) return [];
  const company = hint.company.toLocaleLowerCase();
  const role = hint.role.toLocaleLowerCase();
  return rows.filter(
    (row) =>
      row.company.toLocaleLowerCase() === company && row.role.toLocaleLowerCase() === role,
  );
}

export function toolExists(bin: string) {
  const result = spawnSync(bin, ["--version"], { encoding: "utf8" });
  return result.status === 0;
}
