import { readFileSync } from "node:fs";

/** English headers the career-ops tracker uses, lowercased. */
const ALIASES = {
  "#": "num",
  num: "num",
  date: "date",
  company: "company",
  via: "via",
  role: "role",
  location: "location",
  score: "score",
  status: "status",
  pdf: "pdf",
  materials: "pdf",
  report: "report",
  "apply link": "applylink",
  apply: "applylink",
  "follow-up": "followup",
  "follow up": "followup",
  followup: "followup",
  notes: "notes",
  url: "url",
};

const REQUIRED = ["num", "company", "role", "score", "status"];

/**
 * @typedef {object} TrackerRow
 * @property {string} num
 * @property {string} date
 * @property {string} company
 * @property {string} via
 * @property {string} role
 * @property {string} location
 * @property {string} score
 * @property {string} status
 * @property {string} pdf
 * @property {string} report
 * @property {string} reportHref
 * @property {string} notes
 * @property {string} runSlug
 * @property {string} url
 * @property {string} followup
 */

/**
 * @param {string} line
 * @returns {string[]}
 */
export function trackerCells(line) {
  const parts = line.split("|").map((cell) => cell.trim());
  return parts.slice(1, line.trimEnd().endsWith("|") ? -1 : undefined);
}

/**
 * Href from a markdown link, or "" when the cell is not one http(s) link.
 * A bare http(s) URL is returned up to the first space.
 * @param {string} cell
 */
export function extractHttpUrl(cell) {
  const value = String(cell ?? "").trim();
  if (!value || value === "—" || value === "-") return "";
  if (/^https?:\/\//i.test(value)) return value.split(/\s/)[0];
  const match = value.match(/\[[^\]]*\]\((https?:\/\/[^)\s]+)\)/i);
  return match ? match[1] : "";
}

/**
 * Destination of the first markdown link, including a relative report path.
 * @param {string} cell
 */
export function extractMarkdownTarget(cell) {
  const value = String(cell ?? "").trim();
  const match = value.match(/\[[^\]]*\]\(([^)\s]+)\)/);
  return match ? match[1] : "";
}

/** Last `gtjob-run:<slug>` token in a notes cell. */
export function runSlugFromNotes(notes) {
  const matches = String(notes ?? "").matchAll(/gtjob-run:([A-Za-z0-9][A-Za-z0-9._-]*)/g);
  let slug = "";
  for (const match of matches) slug = match[1];
  return slug;
}

/**
 * @param {string} markdown
 * @returns {{ ok: true, rows: TrackerRow[] } | { ok: false, error: string }}
 */
export function parseTrackerMarkdown(markdown) {
  const lines = String(markdown ?? "").split("\n");
  /** @type {Record<string, number> | null} */
  let map = null;
  for (const raw of lines) {
    const line = raw.trim();
    if (!line.startsWith("|")) continue;
    const cells = trackerCells(line);
    /** @type {Record<string, number>} */
    const candidate = {};
    cells.forEach((cell, index) => {
      const field = ALIASES[cell.toLowerCase()];
      if (field) candidate[field] = index;
    });
    if (REQUIRED.every((field) => candidate[field] != null)) {
      map = candidate;
      break;
    }
  }
  if (!map) {
    return {
      ok: false,
      error: "The tracker has no header row with #, company, role, score, and status.",
    };
  }
  const width = Math.max(...Object.values(map)) + 1;
  /** @type {TrackerRow[]} */
  const rows = [];
  for (const raw of lines) {
    const line = raw.trim();
    if (!line.startsWith("|")) continue;
    const cells = trackerCells(line);
    if (cells.length < width) continue;
    const at = (field) => (map[field] == null ? "" : cells[map[field]] ?? "");
    if (!/^\d+$/.test(at("num"))) continue;
    const notes = at("notes");
    rows.push({
      num: at("num"),
      date: at("date"),
      company: at("company"),
      via: at("via"),
      role: at("role"),
      location: at("location"),
      score: at("score"),
      status: at("status"),
      pdf: at("pdf"),
      report: at("report"),
      reportHref: extractMarkdownTarget(at("report")),
      notes,
      runSlug: runSlugFromNotes(notes),
      url: extractHttpUrl(at("url")),
      followup: at("followup"),
    });
  }
  return { ok: true, rows };
}

/**
 * A missing file is an empty tracker. Any other failure, including a broken
 * table, is an error.
 * @param {string} filePath
 */
export function readTrackerFile(filePath) {
  let text;
  try {
    text = readFileSync(filePath, "utf8");
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error ? error.code : "";
    if (code === "ENOENT") {
      return { ok: true, missing: true, rows: [], path: filePath, error: "" };
    }
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, missing: false, rows: [], path: filePath, error: message };
  }
  const parsed = parseTrackerMarkdown(text);
  if (!parsed.ok) {
    return { ok: false, missing: false, rows: [], path: filePath, error: parsed.error };
  }
  return { ok: true, missing: false, rows: parsed.rows, path: filePath, error: "" };
}
