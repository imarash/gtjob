import { existsSync } from "node:fs";
import { loadStudio, toolExists } from "@/lib/studio-data";

export const instant = false;

export default async function SettingsPage() {
  const { paths, tracker, labels } = await loadStudio();
  const uv = toolExists("uv");
  const rows = [
    ["gtjob", paths.gtjobRoot, existsSync(paths.gtjobRoot)],
    ["out/", paths.outDir, existsSync(paths.outDir)],
    ["uv", "uv on PATH", uv],
    [
      "career-ops",
      paths.careerOpsRoot ?? "CAREER_OPS_ROOT is not set",
      Boolean(paths.careerOpsRoot && existsSync(paths.careerOpsRoot)),
    ],
    ["tracker", paths.trackerPath ?? "—", Boolean(paths.trackerPath && existsSync(paths.trackerPath))],
    [
      "set-status.mjs",
      paths.setStatusPath ?? "—",
      Boolean(paths.setStatusPath && existsSync(paths.setStatusPath)),
    ],
    [
      "templates/states.yml",
      paths.statesPath ?? "—",
      Boolean(paths.statesPath && existsSync(paths.statesPath)),
    ],
    ["dossier", paths.dossierPath ?? "No reference checkout at ../dossier", Boolean(paths.dossierPath)],
  ] as const;

  return (
    <>
      <header className="flex flex-col gap-1">
        <h1 className="text-title-2-medium text-text-primary">Settings</h1>
        <p className="text-body-regular text-text-secondary">
          Local paths only. Dossier is a reference checkout. Studio does not connect to a database.
        </p>
      </header>
      <ul className="flex flex-col gap-2">
        {rows.map(([label, value, ok]) => (
          <li
            key={label}
            className="flex flex-col gap-1 rounded-2xl border border-border-button-default px-4 py-3"
          >
            <span className="text-caption-1-semibold text-text-tertiary">{label}</span>
            <span className="text-body-regular text-text-primary" dir="ltr">
              {value}
            </span>
            <span className="text-body-2-regular text-text-secondary">{ok ? "Found" : "Not found"}</span>
          </li>
        ))}
      </ul>
      {tracker && !tracker.ok ? (
        <p className="text-body-regular text-text-error-primary">
          Tracker error: {tracker.error} ({tracker.path})
        </p>
      ) : null}
      {labels && !labels.ok ? (
        <p className="text-body-regular text-text-error-primary">
          States error: {labels.error} ({labels.path})
        </p>
      ) : null}
    </>
  );
}
