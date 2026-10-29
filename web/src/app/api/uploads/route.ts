import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { gtjobRoot } from "@/lib/studio-data";

const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.(pdf|md|txt)$/i;
const MAX_BYTES = 10_000_000;

export async function POST(request: Request) {
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return Response.json({ error: "Expected a file upload." }, { status: 400 });
  }
  const kind = form.get("kind");
  const folder = kind === "cv" ? "CVs" : kind === "jd" ? "JDs" : "";
  if (!folder) return Response.json({ error: "Upload a CV or a job description." }, { status: 400 });
  const file = form.get("file");
  if (!(file instanceof File)) return Response.json({ error: "Choose a file." }, { status: 400 });
  const name = path.basename(file.name);
  if (!NAME_RE.test(name)) {
    return Response.json({ error: "Use a pdf, md, or txt file name with letters, numbers, dots, or dashes." }, { status: 400 });
  }
  if (file.size > MAX_BYTES) return Response.json({ error: "That file is over 10 MB." }, { status: 400 });
  const bytes = Buffer.from(await file.arrayBuffer());
  const dir = path.join(gtjobRoot(), folder);
  mkdirSync(dir, { recursive: true });
  writeFileSync(path.join(dir, name), bytes);
  return Response.json({ name, folder });
}
