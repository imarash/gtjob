import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { draftReply } from "@/lib/reply.mjs";
import { resolvePaths } from "@/lib/paths.mjs";
import { gtjobRoot } from "@/lib/studio-data";
import { SLUG_RE } from "@/lib/runs.mjs";

export async function POST(_request: Request, context: { params: Promise<{ slug: string }> }) {
  const { slug } = await context.params;
  if (!SLUG_RE.test(slug)) return Response.json({ error: "Unknown run." }, { status: 400 });
  const paths = resolvePaths(gtjobRoot());
  const dir = path.resolve(paths.outDir, slug);
  const relative = path.relative(path.resolve(paths.outDir), dir);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    return Response.json({ error: "Unknown run." }, { status: 400 });
  }
  const reportPath = path.join(dir, "report.md");
  if (!existsSync(reportPath)) {
    return Response.json({ error: "This run has no match report yet, so there is nothing to base a reply on." }, { status: 400 });
  }
  const draft = draftReply(readFileSync(reportPath, "utf8").slice(0, 200_000));
  writeFileSync(path.join(dir, "reply.md"), draft.markdown);
  return Response.json({ markdown: draft.markdown, attach: draft.attach });
}
