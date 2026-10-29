import Link from "next/link";
import path from "node:path";
import { notFound } from "next/navigation";
import { MarkdownBlock } from "@/components/studio/markdown-block";
import { listCatalog, readMarkdownDoc, referenceFile } from "@/lib/claude-catalog.mjs";
import { loadStudio } from "@/lib/studio-data";

export const instant = false;

export default async function ReferencePage({ params }: { params: Promise<{ name: string; doc: string }> }) {
  const { name, doc } = await params;
  const { paths } = await loadStudio();
  const catalog = listCatalog(path.join(paths.gtjobRoot, ".claude"));
  const skill = catalog.skills.find((item) => item.id === name);
  if (!skill) notFound();
  const file = referenceFile(skill.dir, doc);
  if (!file) notFound();
  const text = readMarkdownDoc(file);
  return (
    <>
      <header className="flex flex-col gap-1">
        <p className="text-caption-1-semibold text-text-tertiary">
          <Link href={`/skills/${skill.id}`} className="underline">
            {skill.name}
          </Link>
        </p>
        <h1 className="text-title-2-medium text-text-primary">{doc}</h1>
      </header>
      <MarkdownBlock markdown={text.body || text.description} />
    </>
  );
}
