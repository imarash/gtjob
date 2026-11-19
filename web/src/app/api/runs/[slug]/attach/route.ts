import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolvePaths } from "@/lib/paths.mjs";
import { directoryIsRun, SLUG_RE } from "@/lib/runs.mjs";
import { attachRunNote, buildSetStatusArgs } from "@/lib/status-args.mjs";
import { readStateLabels } from "@/lib/states.mjs";
import { gtjobRoot } from "@/lib/studio-data";
import { readTrackerFile } from "@/lib/tracker.mjs";
import path from "node:path";

export async function POST(request: Request, context: { params: Promise<{ slug: string }> }) {
  const { slug } = await context.params;
  if (!SLUG_RE.test(slug)) return Response.json({ error: "Run slug is not valid." }, { status: 400 });
  let body: { row?: unknown };
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Expected JSON." }, { status: 400 });
  }
  if (typeof body.row !== "string" || !/^\d+$/.test(body.row)) {
    return Response.json({ error: "Choose a tracker row." }, { status: 400 });
  }
  const paths = resolvePaths(gtjobRoot());
  if (!paths.careerOpsRoot || !paths.setStatusPath || !paths.trackerPath) {
    return Response.json({ error: "CAREER_OPS_ROOT is not set." }, { status: 400 });
  }
  const runDir = path.join(paths.outDir, slug);
  if (!existsSync(runDir) || !directoryIsRun(runDir)) {
    return Response.json({ error: "That run is not on disk." }, { status: 404 });
  }
  const labels = readStateLabels(paths.careerOpsRoot);
  if (!labels.ok) return Response.json({ error: labels.error }, { status: 400 });
  const tracker = readTrackerFile(paths.trackerPath);
  if (!tracker.ok || tracker.missing) {
    return Response.json({ error: tracker.error || "Tracker file is missing." }, { status: 400 });
  }
  const row = tracker.rows.find((item) => item.num === body.row);
  if (!row) return Response.json({ error: `No row #${body.row}.` }, { status: 404 });
  let args: string[];
  try {
    args = buildSetStatusArgs({
      script: paths.setStatusPath,
      row: row.num,
      status: row.status,
      note: attachRunNote(slug),
      allowed: labels.labels,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Could not attach.";
    return Response.json({ error: message }, { status: 400 });
  }
  const result = spawnSync(process.execPath, args, {
    cwd: paths.careerOpsRoot,
    env: { ...process.env, CAREER_OPS_ROOT: paths.careerOpsRoot },
    encoding: "utf8",
    timeout: 30_000,
  });
  if (result.status !== 0) {
    return Response.json(
      { error: "set-status.mjs failed", stderr: `${result.stderr ?? ""}${result.error?.message ?? ""}`.trim() },
      { status: 422 },
    );
  }
  return Response.json({ ok: true });
}
