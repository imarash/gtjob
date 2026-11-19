import Link from "next/link";
import path from "node:path";
import { notFound } from "next/navigation";
import { MarkdownBlock } from "@/components/studio/markdown-block";
import { listCatalog, readMarkdownDoc } from "@/lib/claude-catalog.mjs";
import { loadStudio } from "@/lib/studio-data";

export const instant = false;

export default async function AgentPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const { paths } = await loadStudio();
  const catalog = listCatalog(path.join(paths.gtjobRoot, ".claude"));
  const agent = catalog.agents.find((item) => item.id === name);
  if (!agent) notFound();
  const doc = readMarkdownDoc(agent.file);
  return (
    <>
      <header className="flex flex-col gap-1">
        <p className="text-caption-1-semibold text-text-tertiary">
          <Link href="/skills" className="underline">
            Skills
          </Link>
        </p>
        <h1 className="text-title-2-medium text-text-primary">{agent.name}</h1>
        <p className="text-body-regular text-text-secondary">{agent.description}</p>
      </header>
      <p className="rounded-3xl border border-border-button-default bg-background-secondary-default p-4 text-body-regular text-text-secondary">
        Studio does not run this agent and does not call its model. The instructions below are the file in .claude/agents.
      </p>
      <MarkdownBlock markdown={doc.body} />
    </>
  );
}
