import Link from "next/link";
import path from "node:path";
import { notFound } from "next/navigation";
import { MarkdownBlock } from "@/components/studio/markdown-block";
import { AttestPanel, PolishForm, RunPicker, StartRunForm, StatusButton } from "@/components/studio/skill-actions";
import { listCatalog, listDirFiles, listSkillFiles, readMarkdownDoc, runsWithReply } from "@/lib/claude-catalog.mjs";
import { loadStudio } from "@/lib/studio-data";

export const instant = false;

export default async function SkillPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  const { paths, runs } = await loadStudio();
  const catalog = listCatalog(path.join(paths.gtjobRoot, ".claude"));
  const skill = catalog.skills.find((item) => item.id === name);
  if (!skill) notFound();
  const doc = readMarkdownDoc(skill.file);
  const files = listSkillFiles(skill.dir);
  const references = files.filter((file) => file.startsWith(`references${path.sep}`) && file.endsWith(".md"));
  const slugs = runs.ok ? runs.runs.map((run) => run.slug) : [];
  const replies = runsWithReply(paths.outDir);

  return (
    <>
      <header className="flex flex-col gap-1">
        <p className="text-caption-1-semibold text-text-tertiary">
          <Link href="/skills" className="underline">
            Skills
          </Link>
        </p>
        <h1 className="text-title-2-medium text-text-primary">{skill.name}</h1>
        {skill.argumentHint ? <p className="text-body-regular text-text-secondary">{skill.argumentHint}</p> : null}
        <p className="text-body-regular text-text-secondary">{skill.description}</p>
      </header>
      <section className="flex flex-col gap-3 rounded-3xl border border-border-button-default p-4">
        <h2 className="text-headline-medium text-text-primary">From Studio</h2>
        <SkillTools
          id={skill.id}
          cvs={listDirFiles(path.join(paths.gtjobRoot, "CVs"))}
          jds={listDirFiles(path.join(paths.gtjobRoot, "JDs"))}
          slugs={slugs}
          replies={replies}
        />
      </section>
      {references.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h2 className="text-headline-medium text-text-primary">References</h2>
          <ul className="flex flex-col gap-1">
            {references.map((file) => {
              const docName = path.basename(file);
              return (
                <li key={file}>
                  <Link href={`/skills/${skill.id}/references/${docName}`} className="text-body-regular text-text-primary underline">
                    {docName}
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
      <details className="text-body-2-regular text-text-secondary">
        <summary>{files.length} files in this skill</summary>
        <ul className="mt-2 flex flex-col gap-1">
          {files.map((file) => (
            <li key={file} dir="ltr">
              {file}
            </li>
          ))}
        </ul>
      </details>
      <MarkdownBlock markdown={doc.body} />
    </>
  );
}

function SkillTools({
  id,
  cvs,
  jds,
  slugs,
  replies,
}: {
  id: string;
  cvs: string[];
  jds: string[];
  slugs: string[];
  replies: string[];
}) {
  if (id === "tailor-cv" || id === "tailoring-cvs") return <StartRunForm cvs={cvs} jds={jds} />;
  if (id === "cv-polish") return <PolishForm cvs={cvs} />;
  if (id === "cv-status") return <StatusButton all />;
  if (id === "cv-profile") return <AttestPanel runs={slugs} />;
  if (id === "cv-continue" || id === "cv-render") return <RunPicker runs={slugs} />;
  if (id === "cv-reply") {
    return replies.length === 0 ? (
      <p className="text-body-regular text-text-secondary">
        A reply is written to out/&lt;run&gt;/reply.md by Claude after the tailored CV exists. None are on disk.
      </p>
    ) : (
      <ul className="flex flex-col gap-1">
        {replies.map((slug) => (
          <li key={slug}>
            <Link href={`/runs/${slug}`} className="text-body-regular text-text-primary underline">
              {slug}
            </Link>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <p className="text-body-regular text-text-secondary">
      Open a run to use the cvt commands. Studio does not call a model for the steps this skill assigns to Claude.
    </p>
  );
}
