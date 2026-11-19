import Link from "next/link";
import { loadStudio } from "@/lib/studio-data";

export const instant = false;

export default async function RunsPage() {
  const { runs } = await loadStudio();
  if (!runs.ok) {
    return (
      <div className="flex flex-col gap-2">
        <h1 className="text-title-2-medium text-text-primary">Runs</h1>
        <p className="text-body-regular text-text-error-primary">{runs.error}</p>
      </div>
    );
  }
  return (
    <>
      <header className="flex flex-col gap-1">
        <h1 className="text-title-2-medium text-text-primary">Runs</h1>
        <p className="text-body-regular text-text-secondary">
          {runs.missing
            ? `No out/ directory at ${runs.path}. A tailoring run creates one.`
            : `${runs.runs.length} tailored ${runs.runs.length === 1 ? "run" : "runs"} on disk.`}
        </p>
      </header>
      {runs.runs.length === 0 ? (
        <p className="rounded-3xl border border-border-button-default bg-background-secondary-default p-6 text-body-regular text-text-secondary">
          Nothing here has a match report or a finished PDF. Source copies under inputs/ are not runs.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {runs.runs.map((run) => (
            <li key={run.slug}>
              <Link
                href={`/runs/${run.slug}`}
                className="flex flex-col gap-1 rounded-2xl border border-border-button-default px-4 py-3"
              >
                <span className="text-body-medium text-text-primary">{run.slug}</span>
                <span className="text-body-2-regular text-text-secondary">
                  {run.pdfs[0] ?? "No PDF"}
                  {run.hasReport ? " · report.md" : ""}
                  {run.waiting ? " · waiting" : ""}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
