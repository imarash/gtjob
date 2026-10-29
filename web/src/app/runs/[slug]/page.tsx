import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumb, BreadcrumbItem } from "@/components/base/breadcrumb/breadcrumb";
import { AttachForm } from "@/components/studio/attach-form";
import { RunActions } from "@/components/studio/skill-actions";
import { renderMarkdown } from "@/lib/markdown.mjs";
import { readFileSync, existsSync } from "node:fs";
import { hintMatches, loadStudio } from "@/lib/studio-data";

export const instant = false;

export default async function RunPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const { paths, runs, tracker } = await loadStudio();
  if (!runs.ok) {
    return <p className="text-body-regular text-text-error-primary">{runs.error}</p>;
  }
  const run = runs.runs.find((item) => item.slug === slug);
  if (!run) notFound();
  const reportText =
    run.hasReport && run.reportPath && existsSync(run.reportPath)
      ? readFileSync(run.reportPath, "utf8").slice(0, 200_000)
      : "";
  const rows = tracker?.ok && !tracker.missing ? tracker.rows : [];
  const hints = hintMatches(run.heading, rows);

  return (
    <>
      <Breadcrumb>
        <BreadcrumbItem href="/runs">Runs</BreadcrumbItem>
        <BreadcrumbItem current>{run.slug}</BreadcrumbItem>
      </Breadcrumb>
      <header className="flex flex-col gap-2">
        <h1 className="text-title-2-medium text-text-primary">{run.heading || run.slug}</h1>
        <p className="text-body-regular text-text-secondary">{run.dir}</p>
        {run.waiting ? (
          <p className="text-body-regular text-text-primary">
            This run is waiting{run.stage ? ` (${run.stage})` : ""}. Answer it in the tailoring skill. Studio does not
            rewrite the CV.
          </p>
        ) : null}
      </header>
      <section className="flex flex-col gap-3">
        <h2 className="text-headline-medium text-text-primary">Tailoring skill</h2>
        <p className="text-body-regular text-text-secondary">
          These buttons call cvt in .claude. They do not call a model. Load questions only when this run is waiting on
          checkpoint 1.
        </p>
        <RunActions slug={run.slug} />
      </section>
      <section className="flex flex-col gap-2">
        <h2 className="text-headline-medium text-text-primary">PDF</h2>
        {run.pdfs.length === 0 ? (
          <p className="text-body-regular text-text-secondary">No PDF in this run yet.</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {run.pdfs.map((file) => (
              <li key={file}>
                <Link
                  href={`/runs/${run.slug}/pdf?file=${encodeURIComponent(file)}`}
                  className="text-body-medium text-text-primary underline"
                >
                  {file}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="flex flex-col gap-3">
        <h2 className="text-headline-medium text-text-primary">Match report</h2>
        {reportText ? (
          <div
            className="flex flex-col gap-3 overflow-x-auto text-body-regular text-text-primary [&_a]:underline [&_h1]:text-title-3-medium [&_h2]:text-headline-medium [&_h3]:text-body-medium [&_table]:w-full [&_td]:border [&_td]:border-border-table [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-border-table [&_th]:px-2 [&_th]:py-1 [&_ul]:list-disc [&_ul]:ps-5"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(reportText) }}
          />
        ) : (
          <p className="text-body-regular text-text-secondary">This run has no report.md.</p>
        )}
      </section>
      <section className="flex flex-col gap-3">
        <h2 className="text-headline-medium text-text-primary">Attach to application</h2>
        {!paths.careerOpsRoot ? (
          <p className="text-body-regular text-text-secondary">
            Attach is hidden until CAREER_OPS_ROOT is set. Matching a company and a role here does not write the tracker.
          </p>
        ) : (
          <>
            {hints.length > 0 ? (
              <p className="text-body-regular text-text-secondary">
                Same company and role, not linked yet:{" "}
                {hints.map((row) => (
                  <Link key={row.num} href={`/applications/${row.num}`} className="text-text-primary underline">
                    #{row.num} {row.company}
                  </Link>
                ))}
              </p>
            ) : null}
            {tracker?.ok && !tracker.missing ? (
              <AttachForm slug={run.slug} rows={rows} />
            ) : (
              <p className="text-body-regular text-text-secondary">
                {tracker && !tracker.ok ? tracker.error : `No tracker at ${paths.trackerPath}.`}
              </p>
            )}
          </>
        )}
      </section>
    </>
  );
}
