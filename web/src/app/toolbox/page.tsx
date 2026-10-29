import { readFileSync } from "node:fs";
import path from "node:path";
import { ToolboxForm } from "@/components/studio/toolbox-form";
import { listDirFiles } from "@/lib/claude-catalog.mjs";
import { listPolishRuns, listStateRuns, previewFile, reportHeading } from "@/lib/runs.mjs";
import { loadStudio } from "@/lib/studio-data";

export const instant = false;

function readText(file: string) {
  try {
    return readFileSync(file, "utf8").slice(0, 20_000);
  } catch {
    return "";
  }
}

export default async function ToolboxPage() {
  const { paths } = await loadStudio();
  const tailor = listStateRuns(paths.outDir).map((run) => {
    const dir = path.join(paths.outDir, run.slug);
    const report = run.hasReport ? readText(path.join(dir, "report.md")) : "";
    return {
      slug: run.slug,
      title: reportHeading(report) || run.slug,
      stage: run.stage,
      template: run.template,
      downloads: run.downloads,
      preview: previewFile(run.downloads),
      hasReport: run.hasReport,
      reply: readText(path.join(dir, "reply.md")),
      kind: "tailor" as const,
    };
  });
  const polish = listPolishRuns(paths.outDir).map((run) => {
    const dir = path.join(paths.outDir, run.slug);
    return {
      slug: run.slug,
      title: run.title || run.slug,
      stage: run.stage,
      template: run.template,
      downloads: run.downloads,
      preview: previewFile(run.downloads),
      hasReport: false,
      reply: readText(path.join(dir, "notes.md")),
      kind: "polish" as const,
    };
  });
  const runs = [...tailor, ...polish];
  return (
    <>
      <header className="flex flex-col gap-1">
        <h1 className="text-title-2-medium text-text-primary">Toolbox</h1>
        <p className="text-body-regular text-text-secondary">
          Tailor a CV to one job, or polish the CV you already have. When a PDF is ready, compare the layouts and download it. Nothing is sent.
        </p>
      </header>
      <ToolboxForm
        cvs={listDirFiles(path.join(paths.gtjobRoot, "CVs"))}
        jds={listDirFiles(path.join(paths.gtjobRoot, "JDs"))}
        runs={runs}
      />
    </>
  );
}
