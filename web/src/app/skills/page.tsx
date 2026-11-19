import Link from "next/link";
import path from "node:path";
import { listCatalog } from "@/lib/claude-catalog.mjs";
import { loadStudio } from "@/lib/studio-data";

export const instant = false;

export default async function SkillsPage() {
  const { paths } = await loadStudio();
  const catalog = listCatalog(path.join(paths.gtjobRoot, ".claude"));
  return (
    <>
      <header className="flex flex-col gap-1">
        <h1 className="text-title-2-medium text-text-primary">Skills</h1>
        <p className="text-body-regular text-text-secondary">
          Everything under .claude, read from disk. Studio runs the cvt commands these skills already use. A stage that
          writes model JSON still happens in Claude.
        </p>
      </header>
      <section className="flex flex-col gap-2">
        <h2 className="text-headline-medium text-text-primary">Skills</h2>
        {catalog.skills.length === 0 ? (
          <p className="text-body-regular text-text-secondary">No SKILL.md files under .claude/skills.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {catalog.skills.map((skill) => (
              <li key={skill.id}>
                <Link
                  href={`/skills/${skill.id}`}
                  className="flex flex-col gap-1 rounded-2xl border border-border-button-default px-4 py-3"
                >
                  <span className="text-body-medium text-text-primary">{skill.name}</span>
                  <span className="text-body-2-regular text-text-secondary">{skill.description}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="text-headline-medium text-text-primary">Agents</h2>
        <p className="text-body-regular text-text-secondary">
          cv-critic is the optional hiring-manager read. cv-builder, cv-builder-lite, and cv-reviewer were only for
          building this project, so they are not listed here. Their files are still in .claude/agents.
        </p>
        {catalog.agents.length === 0 ? (
          <p className="text-body-regular text-text-secondary">No agent files under .claude/agents.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {catalog.agents
              .filter((agent) => !["cv-builder", "cv-builder-lite", "cv-reviewer"].includes(agent.id))
              .map((agent) => (
              <li key={agent.id}>
                <Link
                  href={`/agents/${agent.id}`}
                  className="flex flex-col gap-1 rounded-2xl border border-border-button-default px-4 py-3"
                >
                  <span className="text-body-medium text-text-primary">{agent.name}</span>
                  <span className="text-body-2-regular text-text-secondary">{agent.description}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
