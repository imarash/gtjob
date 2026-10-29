import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

export const SLUG_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$/;

/**
 * @typedef {object} RunRecord
 * @property {string} slug
 * @property {string} dir
 * @property {string[]} pdfs
 * @property {boolean} hasReport
 * @property {string} reportPath
 * @property {number} mtimeMs
 * @property {boolean} waiting
 * @property {string} stage
 * @property {string} heading
 */

/**
 * @param {string} parent
 * @param {string} child
 */
function staysInside(parent, child) {
  const relative = path.relative(parent, child);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

/**
 * A run has a match report, a final PDF, or a polish PDF in the directory
 * itself. Source copies under inputs/ and fit drafts under build/ do not count.
 * @param {string} dir
 */
export function directoryIsRun(dir) {
  try {
    if (statSync(path.join(dir, "report.md")).isFile()) return true;
  } catch {
    /* no report */
  }
  try {
    const finalDir = path.join(dir, "final");
    if (readdirSync(finalDir).some((name) => name.endsWith(".pdf"))) return true;
  } catch {
    /* no final/ */
  }
  try {
    if (readdirSync(dir).some((name) => name.endsWith(".pdf"))) return true;
  } catch {
    return false;
  }
  return false;
}

/**
 * @param {string} statePath
 * @returns {{ waiting: boolean, stage: string }}
 */
export function checkpointFromStateFile(statePath) {
  try {
    const state = JSON.parse(readFileSync(statePath, "utf8"));
    const checkpoints = state?.checkpoints ?? {};
    const kind = state?.pending?.kind;
    const waiting =
      checkpoints.cp1 === "pending" ||
      checkpoints.cp2 === "pending" ||
      (typeof kind === "string" && kind !== "none" && kind !== "");
    return { waiting, stage: typeof state?.stage === "string" ? state.stage : "" };
  } catch {
    return { waiting: false, stage: "" };
  }
}

/**
 * @param {string} outDir
 */
export function listRuns(outDir) {
  let entries;
  try {
    entries = readdirSync(outDir, { withFileTypes: true });
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error ? error.code : "";
    if (code === "ENOENT") return { ok: true, missing: true, runs: [], path: outDir, error: "" };
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, missing: false, runs: [], path: outDir, error: message };
  }
  const root = path.resolve(outDir);
  /** @type {RunRecord[]} */
  const runs = [];
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name.startsWith(".") || entry.name.startsWith("_")) continue;
    if (!SLUG_RE.test(entry.name)) continue;
    const dir = path.resolve(root, entry.name);
    if (!staysInside(root, dir)) continue;
    if (!directoryIsRun(dir)) continue;
    const pdfs = pdfsInRun(dir);
    const reportPath = path.join(dir, "report.md");
    let hasReport = false;
    try {
      hasReport = statSync(reportPath).isFile();
    } catch {
      hasReport = false;
    }
    let mtimeMs = 0;
    try {
      mtimeMs = statSync(dir).mtimeMs;
    } catch {
      mtimeMs = 0;
    }
    const checkpoint = checkpointFromStateFile(path.join(dir, "state.json"));
    let heading = "";
    if (hasReport) {
      try {
        const text = readFileSync(reportPath, "utf8").slice(0, 4000);
        heading = reportHeading(text);
      } catch {
        heading = "";
      }
    }
    runs.push({
      slug: entry.name,
      dir,
      pdfs,
      hasReport,
      reportPath: hasReport ? reportPath : "",
      mtimeMs,
      waiting: checkpoint.waiting,
      stage: checkpoint.stage,
      heading,
    });
  }
  runs.sort((a, b) => Number(b.mtimeMs) - Number(a.mtimeMs) || String(a.slug).localeCompare(String(b.slug)));
  return { ok: true, missing: false, runs, path: outDir, error: "" };
}

/**
 * @param {string} dir
 * @returns {string[]} paths relative to the run directory
 */
export function pdfsInRun(dir) {
  /** @type {string[]} */
  const finalPdfs = [];
  try {
    for (const name of readdirSync(path.join(dir, "final"))) {
      if (name.endsWith(".pdf")) finalPdfs.push(path.join("final", name));
    }
  } catch {
    /* no final/ */
  }
  if (finalPdfs.length > 0) return finalPdfs;
  /** @type {string[]} */
  const top = [];
  try {
    for (const name of readdirSync(dir)) {
      if (name.endsWith(".pdf")) top.push(name);
    }
  } catch {
    /* unreadable */
  }
  return top;
}

/** @param {string} markdown */
export function reportHeading(markdown) {
  const line = String(markdown).split("\n").find((item) => item.startsWith("# "));
  return line ? line.replace(/^#\s+/, "").trim() : "";
}

/**
 * "Match report: Role at Company" → company and role for an on-screen hint.
 * @param {string} heading
 */
export function hintFromHeading(heading) {
  const match = String(heading).match(/^Match report:\s*(.+?)\s+at\s+(.+)$/i);
  if (!match) return null;
  return { role: match[1].trim(), company: match[2].trim() };
}

/**
 * @param {string} outDir
 * @param {string} slug
 * @param {string} relativePath
 * @returns {string | null}
 */
export function resolveRunFile(outDir, slug, relativePath) {
  if (!SLUG_RE.test(slug)) return null;
  if (
    !relativePath ||
    relativePath.includes("\0") ||
    relativePath.split(/[/\\]/).includes("..")
  ) {
    return null;
  }
  const root = path.resolve(outDir);
  const runDir = path.resolve(root, slug);
  if (!staysInside(root, runDir)) return null;
  const target = path.resolve(runDir, relativePath);
  if (!staysInside(runDir, target)) return null;
  if (!downloadAllowed(relativePath)) return null;
  return target;
}

/**
 * Files a person can download from a finished run. Not the source CV or the profile JSON.
 * @param {string} relativePath
 */
export function downloadAllowed(relativePath) {
  const normalized = String(relativePath).replace(/\\/g, "/");
  if (normalized === "cv.md" || normalized === "reply.md" || normalized === "build/cv.typ") return true;
  if (!normalized.endsWith(".pdf")) return false;
  const parts = normalized.split("/");
  if (parts.length === 1) return true;
  return parts.length === 2 && parts[0] === "final";
}

/**
 * @param {string} dir
 * @returns {{ file: string, label: string }[]}
 */
export function listDownloads(dir) {
  /** @type {{ file: string, label: string }[]} */
  const found = [];
  const add = (file, label) => {
    try {
      if (statSync(path.join(dir, file)).isFile()) found.push({ file, label });
    } catch {
      /* absent */
    }
  };
  try {
    for (const name of readdirSync(path.join(dir, "final"))) {
      if (name.endsWith(".pdf")) add(`final/${name}`, `PDF · ${name}`);
    }
  } catch {
    /* no final/ */
  }
  add("cv.pdf", "PDF · working copy");
  add("preview-modern.pdf", "Modern");
  add("preview-classic.pdf", "Classic");
  add("preview-sidebar.pdf", "Sidebar");
  try {
    for (const name of readdirSync(dir)) {
      const match = name.match(/-(modern|classic|sidebar)\.pdf$/i);
      if (!match) continue;
      const label = match[1].toLowerCase();
      add(name, label.charAt(0).toUpperCase() + label.slice(1));
    }
  } catch {
    /* unreadable */
  }
  add("cv.md", "Markdown");
  add("build/cv.typ", "Typst source");
  add("reply.md", "Email reply");
  return found;
}

/**
 * The PDF to show in the preview. Prefer a named final file over a generic CV.pdf.
 * @param {{ file: string }[]} downloads
 */
export function previewFile(downloads) {
  const finals = downloads.filter((item) => item.file.startsWith("final/") && item.file.endsWith(".pdf"));
  const named = finals.find((item) => !/\/[^/]*-CV\.pdf$/i.test(item.file));
  if (named) return named.file;
  if (finals[0]) return finals[0].file;
  const modern = downloads.find((item) => /-(modern)\.pdf$/i.test(item.file) && !item.file.startsWith("preview-"));
  if (modern) return modern.file;
  const any = downloads.find((item) => item.file.endsWith(".pdf") && !item.file.startsWith("preview-"));
  return any ? any.file : "";
}

/**
 * Every cvt run, including one that has no PDF yet. Symlinks are skipped.
 * @param {string} outDir
 * @returns {{ slug: string, stage: string, nextAction: string, template: string, hasReport: boolean, downloads: { file: string, label: string }[] }[]}
 */
export function listStateRuns(outDir) {
  /** @type {{ slug: string, stage: string, nextAction: string, template: string, hasReport: boolean, downloads: { file: string, label: string }[], mtimeMs: number }[]} */
  const found = [];
  let entries;
  try {
    entries = readdirSync(outDir, { withFileTypes: true });
  } catch {
    return [];
  }
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.isSymbolicLink() || !SLUG_RE.test(entry.name)) continue;
    const dir = path.join(outDir, entry.name);
    const statePath = path.join(dir, "state.json");
    let stage = "";
    let nextAction = "";
    let template = "modern";
    let mtimeMs = 0;
    try {
      const raw = JSON.parse(readFileSync(statePath, "utf8"));
      stage = String(raw.stage || "");
      nextAction = String(raw.next_action || "");
      const options = raw.options && typeof raw.options === "object" ? raw.options : {};
      const named = String(options.template || "");
      if (named === "classic" || named === "sidebar" || named === "modern") template = named;
      mtimeMs = statSync(statePath).mtimeMs;
    } catch {
      continue;
    }
    let hasReport = false;
    try {
      hasReport = statSync(path.join(dir, "report.md")).isFile();
    } catch {
      hasReport = false;
    }
    found.push({ slug: entry.name, stage, nextAction, template, hasReport, downloads: listDownloads(dir), mtimeMs });
  }
  return found
    .sort((a, b) => b.mtimeMs - a.mtimeMs)
    .map(({ mtimeMs: _mtime, ...row }) => row);
}

/**
 * A polish run has polish.json, or a render model and a PDF, and no cvt state.json.
 * @param {string} outDir
 * @returns {{ slug: string, title: string, stage: string, nextAction: string, template: string, hasReport: boolean, downloads: { file: string, label: string }[] }[]}
 */
export function listPolishRuns(outDir) {
  /** @type {{ slug: string, title: string, stage: string, nextAction: string, template: string, hasReport: boolean, downloads: { file: string, label: string }[], mtimeMs: number }[]} */
  const found = [];
  let entries;
  try {
    entries = readdirSync(outDir, { withFileTypes: true });
  } catch {
    return [];
  }
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.isSymbolicLink() || !SLUG_RE.test(entry.name)) continue;
    const dir = path.join(outDir, entry.name);
    try {
      if (statSync(path.join(dir, "state.json")).isFile()) continue;
    } catch {
      /* polish runs have no cvt state */
    }
    let marker = false;
    let title = "";
    let mtimeMs = 0;
    try {
      const raw = JSON.parse(readFileSync(path.join(dir, "polish.json"), "utf8"));
      marker = true;
      title = typeof raw.cv === "string" ? raw.cv : "";
      mtimeMs = statSync(path.join(dir, "polish.json")).mtimeMs;
    } catch {
      marker = false;
    }
    const downloads = listDownloads(dir);
    const preview = previewFile(downloads);
    if (!marker) {
      try {
        if (!statSync(path.join(dir, "render.json")).isFile() || !preview) continue;
        mtimeMs = statSync(path.join(dir, "render.json")).mtimeMs;
      } catch {
        continue;
      }
    }
    found.push({
      slug: entry.name,
      title,
      stage: "",
      nextAction: "",
      template: "modern",
      hasReport: false,
      downloads,
      mtimeMs,
    });
  }
  return found
    .sort((a, b) => b.mtimeMs - a.mtimeMs)
    .map(({ mtimeMs: _mtime, ...row }) => row);
}
