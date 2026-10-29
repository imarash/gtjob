import { existsSync } from "node:fs";
import path from "node:path";

/**
 * @param {string} gtjobRoot
 * @param {NodeJS.ProcessEnv} [env]
 */
export function resolvePaths(gtjobRoot, env = process.env) {
  const root = path.resolve(gtjobRoot);
  const careerRaw = env.CAREER_OPS_ROOT?.trim() ?? "";
  const careerOpsRoot = careerRaw ? path.resolve(careerRaw) : null;
  const tracker = careerOpsRoot ? trackerFile(careerOpsRoot) : null;
  const dossier = path.resolve(root, "..", "dossier");
  return {
    gtjobRoot: root,
    outDir: path.join(root, "out"),
    careerOpsRoot,
    trackerPath: tracker,
    setStatusPath: careerOpsRoot ? path.join(careerOpsRoot, "set-status.mjs") : null,
    livenessPath: careerOpsRoot ? path.join(careerOpsRoot, "check-liveness.mjs") : null,
    cadencePath: careerOpsRoot ? path.join(careerOpsRoot, "followup-cadence.mjs") : null,
    statesPath: careerOpsRoot ? path.join(careerOpsRoot, "templates", "states.yml") : null,
    followupsPath: careerOpsRoot ? path.join(careerOpsRoot, "data", "follow-ups.md") : null,
    statusLogPath: tracker ? path.join(path.dirname(tracker), "status-log.tsv") : null,
    reportsDir: careerOpsRoot ? path.join(careerOpsRoot, "reports") : null,
    inboxPath: path.join(root, ".studio", "inbox.json"),
    dossierPath: existsSync(dossier) ? dossier : null,
  };
}

/** career-ops read resolution: data/applications.md, else applications.md. */
export function trackerFile(careerOpsRoot) {
  const nested = path.join(careerOpsRoot, "data", "applications.md");
  if (existsSync(nested)) return nested;
  return path.join(careerOpsRoot, "applications.md");
}

/**
 * @param {string} careerOpsRoot
 * @param {string} href from the tracker report cell
 * @returns {string | null}
 */
export function resolveReportFile(careerOpsRoot, href) {
  if (!href || href.includes("\0") || path.isAbsolute(href)) return null;
  const parts = href.split(/[/\\]/);
  if (parts.includes("..")) return null;
  const target = path.resolve(careerOpsRoot, href);
  const reports = path.resolve(careerOpsRoot, "reports");
  const relative = path.relative(reports, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return null;
  return target;
}
