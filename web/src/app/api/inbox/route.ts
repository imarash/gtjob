import { appendInbox, evaluationHint } from "@/lib/inbox.mjs";
import { resolvePaths } from "@/lib/paths.mjs";
import { gtjobRoot } from "@/lib/studio-data";

export async function POST(request: Request) {
  let body: { text?: unknown };
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Expected JSON." }, { status: 400 });
  }
  if (typeof body.text !== "string") {
    return Response.json({ error: "Paste a URL or some job text." }, { status: 400 });
  }
  const paths = resolvePaths(gtjobRoot());
  const kind = /^https?:\/\/\S+$/i.test(body.text.trim()) ? "url" : "text";
  try {
    const item = appendInbox(paths.inboxPath, {
      kind,
      text: body.text,
      hint: evaluationHint({ careerOpsRoot: paths.careerOpsRoot, kind }),
    });
    return Response.json({ id: item.id, kind: item.kind, hint: item.hint });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Could not save that.";
    return Response.json({ error: message }, { status: 400 });
  }
}
