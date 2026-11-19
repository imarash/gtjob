import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { buildSetStatusArgs } from "@/lib/status-args.mjs";
import { readStateLabels } from "@/lib/states.mjs";
import { gtjobRoot } from "@/lib/studio-data";
import { resolvePaths } from "@/lib/paths.mjs";
import { readTrackerFile } from "@/lib/tracker.mjs";

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!/^\d+$/.test(id)) return Response.json({ error: "Row must be a number." }, { status: 400 });
  let body: { status?: unknown };
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Expected JSON." }, { status: 400 });
  }
  if (typeof body.status !== "string") {
    return Response.json({ error: "Status is required." }, { status: 400 });
  }
  const paths = resolvePaths(gtjobRoot());
  if (!paths.careerOpsRoot || !paths.setStatusPath || !paths.trackerPath) {
    return Response.json({ error: "CAREER_OPS_ROOT is not set." }, { status: 400 });
  }
  if (!existsSync(paths.setStatusPath)) {
    return Response.json({ error: `set-status.mjs is missing at ${paths.setStatusPath}` }, { status: 400 });
  }
  const labels = readStateLabels(paths.careerOpsRoot);
  if (!labels.ok) return Response.json({ error: labels.error }, { status: 400 });
  const tracker = readTrackerFile(paths.trackerPath);
  if (!tracker.ok || tracker.missing) {
    return Response.json({ error: tracker.error || "Tracker file is missing." }, { status: 400 });
  }
  if (!tracker.rows.some((row) => row.num === id)) {
    return Response.json({ error: `No row #${id}.` }, { status: 404 });
  }
  let args: string[];
  try {
    args = buildSetStatusArgs({
      script: paths.setStatusPath,
      row: id,
      status: body.status,
      allowed: labels.labels,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Rejected status.";
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
  return Response.json({ ok: true, stdout: result.stdout ?? "" });
}
