import Link from "next/link";
import { AddRoleDialog } from "@/components/studio/add-role";
import { StudioStats } from "@/components/studio/studio-stats";
import { actionLine, loadStudio } from "@/lib/studio-data";

export const instant = false;

export default async function TodayPage() {
  const { paths, runs, inbox, tracker, cadence } = await loadStudio();
  const runList = runs.ok ? runs.runs : [];
  const waiting = runList.filter((run) => run.waiting);
  const rows = tracker?.ok && !tracker.missing ? tracker.rows : [];
  const review = rows.filter((row) => row.status === "Evaluated");
  const needs = [
    ...cadence.due.map((entry) => ({
      key: `follow-${entry.num}`,
      href: `/applications/${entry.num}`,
      title: `${entry.company} — ${entry.role}`,
      detail: actionLine(cadence, entry.num),
    })),
    ...review.map((row) => ({
      key: `review-${row.num}`,
      href: `/applications/${row.num}`,
      title: `${row.company} — ${row.role}`,
      detail: "In Review",
    })),
    ...waiting.map((run) => ({
      key: `run-${run.slug}`,
      href: `/runs/${run.slug}`,
      title: run.slug,
      detail: run.stage ? `Waiting at ${run.stage}` : "Waiting at a checkpoint",
    })),
  ];
  const trackingOff = !paths.careerOpsRoot;
  const trackerBroken = Boolean(tracker && !tracker.ok);
  const trackerCount = trackingOff || trackerBroken ? null : rows.length;
  const interviewCount =
    trackerCount == null ? null : rows.filter((row) => row.status === "Interview").length;
  const offerCount =
    trackerCount == null
      ? null
      : rows.filter((row) => row.status === "Offer" || row.status === "Hired").length;

  return (
    <>
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-title-2-medium text-text-primary">Today</h1>
          <p className="text-body-regular text-text-secondary">
            {needs.length === 0
              ? "Nothing needs you right now."
              : needs.length === 1
                ? "1 thing needs you."
                : `${needs.length} things need you.`}
          </p>
        </div>
        <AddRoleDialog />
      </header>

      <StudioStats
        applications={trackerCount == null ? "—" : String(trackerCount)}
        interview={interviewCount == null ? "—" : String(interviewCount)}
        offers={offerCount == null ? "—" : String(offerCount)}
        runs={runs.ok ? String(runList.length) : "—"}
        applicationsDelta={trackingOff ? "off" : "tracker"}
      />

      {trackingOff ? (
        <p className="text-body-regular text-text-secondary">
          Tracking turns on when CAREER_OPS_ROOT is set. Tailored runs on this machine still show under Runs.
        </p>
      ) : null}
      {trackerBroken ? (
        <p className="text-body-regular text-text-error-primary">{tracker?.error}</p>
      ) : null}
      {tracker?.ok && tracker.missing ? (
        <p className="text-body-regular text-text-secondary">
          No tracker file at {tracker.path}. Applications stay at zero until that file exists.
        </p>
      ) : null}
      {!cadence.ok ? (
        <p className="text-body-regular text-text-error-primary">
          Follow-up dates could not be read. {cadence.error}
        </p>
      ) : null}
      {!runs.ok ? <p className="text-body-regular text-text-error-primary">{runs.error}</p> : null}

      <section className="flex flex-col gap-3">
        <h2 className="text-headline-medium text-text-primary">Needs you</h2>
        {needs.length === 0 ? (
          <p className="rounded-3xl border border-border-button-default bg-background-secondary-default p-6 text-body-regular text-text-secondary">
            Review is empty, no follow-up is due, and no run is waiting on a checkpoint.
          </p>
        ) : (
          <ul className="flex flex-col gap-2">
            {needs.map((item) => (
              <li key={item.key}>
                <Link
                  href={item.href}
                  className="flex items-baseline justify-between gap-4 rounded-2xl border border-border-button-default bg-background-secondary-default px-4 py-3"
                >
                  <span className="text-body-medium text-text-primary">{item.title}</span>
                  <span className="text-body-regular text-text-secondary">{item.detail}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-headline-medium text-text-primary">Saved roles</h2>
        {!inbox.ok ? <p className="text-body-regular text-text-error-primary">{inbox.error}</p> : null}
        {inbox.ok && inbox.items.length === 0 ? (
          <p className="text-body-regular text-text-secondary">
            Nothing saved yet. Add a role stores the text here. It does not evaluate the job.
          </p>
        ) : null}
        <ul className="flex flex-col gap-3">
          {inbox.items.slice(0, 8).map((item) => (
            <li
              key={item.id}
              className="flex flex-col gap-1 rounded-2xl border border-border-button-default px-4 py-3"
            >
              <p className="truncate text-body-medium text-text-primary" dir="auto">
                {item.text}
              </p>
              <p className="text-body-2-regular text-text-secondary">{item.hint}</p>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
