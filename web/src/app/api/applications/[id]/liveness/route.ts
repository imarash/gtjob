import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolvePaths } from "@/lib/paths.mjs";
import { buildLivenessArgs } from "@/lib/status-args.mjs";
import { gtjobRoot } from "@/lib/studio-data";
import { readTrackerFile } from "@/lib/tracker.mjs";
import { readFileSync } from "node:fs";
import { resolveReportFile } from "@/lib/paths.mjs";
import { reportHeader } from "@/lib/report-header.mjs";

export async function POST(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  const paths = resolvePaths(gtjobRoot());
  if (!paths.careerOpsRoot || !paths.livenessPath || !paths.trackerPath) {
    return Response.json({ error: "CAREER_OPS_ROOT is not set." }, { status: 400 });
  }
  if (!existsSync(paths.livenessPath)) {
    return Response.json({ error: "check-liveness.mjs is missing." }, { status: 400 });
  }
  const tracker = readTrackerFile(paths.trackerPath);
  if (!tracker.ok || tracker.missing) {
    return Response.json({ error: tracker.error || "Tracker file is missing." }, { status: 400 });
  }
  const row = tracker.rows.find((item) => item.num === id);
  if (!row) return Response.json({ error: `No row #${id}.` }, { status: 404 });
  let url = row.url;
  if (!url && row.reportHref) {
    const file = resolveReportFile(paths.careerOpsRoot, row.reportHref);
    if (file && existsSync(file)) {
      url = reportHeader(readFileSync(file, "utf8").slice(0, 20_000)).url;
    }
  }
  if (!url) return Response.json({ error: "This row has no posting URL." }, { status: 400 });
  let args: string[];
  try {
    args = buildLivenessArgs(paths.livenessPath, url);
  } catch (error) {
    const message = error instanceof Error ? error.message : "URL rejected.";
    return Response.json({ error: message }, { status: 400 });
  }
  const result = spawnSync(process.execPath, args, {
    cwd: paths.careerOpsRoot,
    env: { ...process.env, CAREER_OPS_ROOT: paths.careerOpsRoot },
    encoding: "utf8",
    timeout: 25_000,
  });
  const verdict = `${result.stdout ?? ""}`.trim();
  if (!verdict && result.status !== 0) {
    return Response.json(
      { error: "check-liveness.mjs failed", stderr: `${result.stderr ?? ""}${result.error?.message ?? ""}`.trim() },
      { status: 422 },
    );
  }
  return Response.json({ verdict: verdict || "not checked", stderr: (result.stderr ?? "").trim() });
}
