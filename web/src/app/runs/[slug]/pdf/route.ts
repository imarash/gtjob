import { createReadStream } from "node:fs";
import { statSync } from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import { resolvePaths } from "@/lib/paths.mjs";
import { resolveRunFile } from "@/lib/runs.mjs";
import { gtjobRoot } from "@/lib/studio-data";

export async function GET(request: Request, context: { params: Promise<{ slug: string }> }) {
  const { slug } = await context.params;
  const file = new URL(request.url).searchParams.get("file") ?? "";
  const paths = resolvePaths(gtjobRoot());
  const target = resolveRunFile(paths.outDir, slug, file);
  if (!target) return new Response("Not found", { status: 404 });
  try {
    if (!statSync(target).isFile()) return new Response("Not found", { status: 404 });
  } catch {
    return new Response("Not found", { status: 404 });
  }
  const stream = Readable.toWeb(createReadStream(target)) as ReadableStream;
  const filename = path.basename(target).replace(/"/g, "");
  return new Response(stream, {
    headers: {
      "content-type": "application/pdf",
      "content-disposition": `inline; filename="${filename}"`,
      "cache-control": "no-store",
    },
  });
}
