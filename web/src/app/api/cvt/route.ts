import { advanceRun } from "@/lib/cvt-advance.mjs";
import { buildToolArgv } from "@/lib/cvt-args.mjs";
import { spawnTool } from "@/lib/cvt-spawn.mjs";
import { startPolishRun } from "@/lib/polish-run.mjs";
import { gtjobRoot } from "@/lib/studio-data";
import { renderTemplatePreviews } from "@/lib/template-previews.mjs";

export const maxDuration = 180;

export async function POST(request: Request) {
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Expected JSON." }, { status: 400 });
  }
  const root = gtjobRoot();
  if (body.command === "render-templates") {
    const run = typeof body.run === "string" ? body.run : "";
    try {
      return Response.json(renderTemplatePreviews(root, run));
    } catch (error) {
      const message = error instanceof Error ? error.message : "The layouts did not render.";
      return Response.json({ error: message }, { status: 400 });
    }
  }
  if (body.command === "polish-start") {
    const cv = typeof body.cv === "string" ? body.cv : "";
    try {
      return Response.json(startPolishRun(root, cv));
    } catch (error) {
      const message = error instanceof Error ? error.message : "The CV could not be read.";
      return Response.json({ error: message }, { status: 400 });
    }
  }
  if (body.command === "advance") {
    const run = typeof body.run === "string" ? body.run : "";
    if (!run) return Response.json({ error: "Name the run." }, { status: 400 });
    try {
      return Response.json(advanceRun(root, run));
    } catch (error) {
      const message = error instanceof Error ? error.message : "That step did not run.";
      return Response.json({ error: message }, { status: 400 });
    }
  }
  let built;
  try {
    built = buildToolArgv(body, { gtjobRoot: root });
  } catch (error) {
    const message = error instanceof Error ? error.message : "That command is not available.";
    return Response.json({ error: message }, { status: 400 });
  }
  const result = spawnTool(root, built.script, built.args, built.timeoutMs);
  if (!result.ok) return Response.json({ error: result.error, stderr: result.stderr }, { status: 500 });
  if (body.command === "init" && result.envelope && result.envelope.ok === true && typeof result.envelope.run === "string") {
    try {
      const advanced = advanceRun(root, result.envelope.run);
      return Response.json({
        envelope: result.envelope,
        advance: advanced,
        stderr: result.stderr,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ingest did not start.";
      return Response.json({ envelope: result.envelope, error: message });
    }
  }
  return Response.json({ envelope: result.envelope, stdout: result.stdout, stderr: result.stderr });
}
