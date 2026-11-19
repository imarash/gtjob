import Link from "next/link";
import { Breadcrumb, BreadcrumbItem } from "@/components/base/breadcrumb/breadcrumb";
import { DetailTabs } from "@/components/studio/detail-tabs";
import { LivenessCheck } from "@/components/studio/liveness-check";
import { ScoreValue, StatusChip } from "@/components/studio/score";
import { StatusForm } from "@/components/studio/status-form";
import { actionLine, loadStudio, readCareerReport } from "@/lib/studio-data";
import { readStatusLog } from "@/lib/status-log.mjs";

export const instant = false;

export default async function ApplicationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) {
    return <Missing body="Application ids are tracker row numbers." />;
  }
  const { paths, runs, tracker, labels, cadence } = await loadStudio();
  if (!paths.careerOpsRoot || !tracker) {
    return (
      <Missing body="Tracking turns on when CAREER_OPS_ROOT is set. Studio does not keep a second status for this role." />
    );
  }
  if (!tracker.ok) return <Missing body={tracker.error} path={tracker.path} />;
  if (tracker.missing) return <Missing body="No tracker file yet." path={tracker.path} />;
  const row = tracker.rows.find((item) => item.num === id);
  if (!row) return <Missing body={`No row #${id}.`} path={tracker.path} />;

  const report = paths.careerOpsRoot ? readCareerReport(paths.careerOpsRoot, row.reportHref) : null;
  const run = row.runSlug && runs.ok ? runs.runs.find((item) => item.slug === row.runSlug) : undefined;
  const log = paths.statusLogPath ? readStatusLog(paths.statusLogPath, id) : null;
  const posting = row.url || report?.header?.url || "";

  const overview = (
    <div className="flex flex-col gap-4">
      <p className="text-body-regular text-text-primary">{actionLine(cadence, id)}</p>
      {!cadence.ok ? <p className="text-body-2-regular text-text-error-primary">{cadence.error}</p> : null}
      <dl className="grid gap-3 sm:grid-cols-2">
        <div>
          <dt className="text-caption-1-semibold text-text-tertiary">Score</dt>
          <dd>
            <ScoreValue score={row.score} />
          </dd>
        </div>
        <div>
          <dt className="text-caption-1-semibold text-text-tertiary">Legitimacy</dt>
          <dd className="text-body-regular text-text-primary">{report?.header?.legitimacy || "—"}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-caption-1-semibold text-text-tertiary">Posting</dt>
          <dd className="text-body-regular text-text-primary" dir="ltr">
            {posting ? (
              <a href={posting} className="underline" rel="noreferrer">
                {posting}
              </a>
            ) : (
              "—"
            )}
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-caption-1-semibold text-text-tertiary">Report file</dt>
          <dd className="text-body-regular text-text-primary">
            {row.reportHref ? row.reportHref : "—"}
            {report?.file ? ` · ${report.found ? report.file : `${report.file} (missing)`}` : ""}
          </dd>
        </div>
      </dl>
      {paths.careerOpsRoot ? <LivenessCheck id={id} hasUrl={Boolean(posting)} /> : null}
      {labels?.ok ? (
        <StatusForm id={id} status={row.status} labels={labels.labels} />
      ) : (
        <p className="text-body-regular text-text-error-primary">
          {labels?.error || "Status cannot change until templates/states.yml can be read."}
        </p>
      )}
    </div>
  );

  const documents = (
    <div className="flex flex-col gap-3">
      {run ? (
        <>
          <p className="text-body-regular text-text-secondary">
            Linked run <Link href={`/runs/${run.slug}`} className="text-text-primary underline">{run.slug}</Link>
          </p>
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
            {run.hasReport ? (
              <li>
                <Link href={`/runs/${run.slug}`} className="text-body-medium text-text-primary underline">
                  report.md
                </Link>
              </li>
            ) : null}
          </ul>
        </>
      ) : (
        <p className="text-body-regular text-text-secondary">
          No gtjob PDF is linked. On a run, Attach to application writes gtjob-run:&lt;slug&gt; into the notes.
        </p>
      )}
    </div>
  );

  const activity = (
    <div className="flex flex-col gap-3">
      <p className="text-body-regular text-text-primary">
        {row.date || "No date"} · {row.status}
      </p>
      {log && !log.ok ? <p className="text-body-regular text-text-error-primary">{log.error}</p> : null}
      {log?.ok && log.missing ? (
        <p className="text-body-regular text-text-secondary">No status-log.tsv next to the tracker.</p>
      ) : null}
      {log?.ok && log.events.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {log.events.map((event, index) => (
            <li key={`${event.date}-${index}`} className="text-body-regular text-text-primary">
              {event.date}: {event.from} → {event.to}
              {event.note ? ` · ${event.note}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );

  return (
    <>
      <Breadcrumb>
        <BreadcrumbItem href="/applications">Applications</BreadcrumbItem>
        <BreadcrumbItem current>{`#${row.num}`}</BreadcrumbItem>
      </Breadcrumb>
      <header className="flex flex-col gap-2">
        <h1 className="text-title-2-medium text-text-primary">
          {row.company} — {row.role}
        </h1>
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip status={row.status} />
          <ScoreValue score={row.score} />
        </div>
      </header>
      <DetailTabs overview={overview} documents={documents} activity={activity} />
    </>
  );
}

function Missing({ body, path }: { body: string; path?: string }) {
  return (
    <p className="rounded-3xl border border-border-button-default bg-background-secondary-default p-6 text-body-regular text-text-secondary">
      {body}
      {path ? ` Looked at ${path}.` : ""}
    </p>
  );
}
