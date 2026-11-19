import { readFileSync } from "node:fs";
import path from "node:path";
import { activeStep, describeStage, waitDetail, STEP_LABELS } from "./stage-copy.mjs";

const SLUG_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$/;
const ROLE_WORD =
  /\b(architect|engineer|engineering|manager|director|consultant|developer|analyst|designer|scientist|administrator|specialist|officer|lead|recruiter|coordinator|intern|devops|sre)\b/i;
const STOP_HEADING =
  /^(about|overview|description|summary|the role|job overview|responsibilities|requirements|qualifications|what you|must have|nice to have|details)\b/i;
const SKIP_LINE = /^(location|salary|compensation|type|employment type|posted|date)\s*[:\-–]/i;
const GREETING =
  /^(hope you|hi|hello|dear|greetings|good morning|good afternoon|good evening|thanks|thank you)\b/i;

/**
 * @param {string} value
 */
function clean(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

/**
 * @param {string} a
 * @param {string} b
 */
function sameText(a, b) {
  return clean(a).toLowerCase() === clean(b).toLowerCase();
}

/**
 * @param {string} text
 * @param {string} phrase
 */
function containsPhrase(text, phrase) {
  const needle = clean(phrase);
  if (!needle) return false;
  const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`\\b${escaped}\\b`, "i").test(text);
}

/**
 * @param {string} line
 */
function isShortHeading(line) {
  if (!line || line.length > 80) return false;
  const words = line.split(/\s+/);
  if (words.length > 12) return false;
  if (/[.!?]$/.test(line) && words.length > 6) return false;
  return true;
}

/**
 * @param {string} text
 * @returns {{ title: string, company: string }}
 */
export function extractJob(text) {
  let title = "";
  let company = "";
  /** @type {string[]} */
  const shorts = [];
  let inPreamble = true;
  for (const raw of String(text || "").split("\n").slice(0, 60)) {
    const line = raw.trim().replace(/^#+\s*/, "").replace(/\*+/g, "").trim();
    if (!line || line.startsWith("-") || line.startsWith("|") || line.startsWith("•")) continue;
    const labeledCompany = line.match(/^(?:company|employer|organization)\s*[:\-–]\s*(.+)$/i);
    if (labeledCompany) {
      if (!company) company = clean(labeledCompany[1]);
      continue;
    }
    const labeledTitle = line.match(/^(?:job title|position title|title|position|role)\s*[:\-–]\s*(.+)$/i);
    if (labeledTitle) {
      const value = clean(labeledTitle[1]);
      if (!title && value.length <= 120) title = value;
      continue;
    }
    if (!inPreamble || SKIP_LINE.test(line) || GREETING.test(line)) continue;
    if (!isShortHeading(line) || STOP_HEADING.test(line)) {
      inPreamble = false;
      continue;
    }
    shorts.push(line);
    if (shorts.length >= 3) inPreamble = false;
  }
  if (!title && shorts.length >= 2 && ROLE_WORD.test(shorts[1]) && !ROLE_WORD.test(shorts[0])) {
    company = company || shorts[0];
    title = shorts[1];
  } else if (!title && shorts.length > 0) {
    const role = shorts.find((line) => ROLE_WORD.test(line));
    title = role || shorts[0];
    if (!company && role && shorts[0] !== role) company = shorts[0];
  }
  return { title: clean(title), company: clean(company) };
}

/**
 * The current role line from CV text, before a profile exists.
 * @param {string} text
 */
export function extractPosition(text) {
  const lines = String(text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const expAt = lines.findIndex((line) =>
    /^(experience|work experience|professional experience|employment history|employment)$/i.test(line),
  );
  if (expAt >= 0) {
    const parts = (lines[expAt + 1] || "")
      .split("|")
      .map((part) => part.trim())
      .filter(Boolean);
    if (parts.length >= 2 && parts[1].length <= 80) return parts[1];
  }
  const second = lines[1] || "";
  const dots = second.match(/·/g) || [];
  if (second && second.length <= 80 && !second.includes("@") && dots.length < 2 && ROLE_WORD.test(second)) {
    return second;
  }
  return "";
}

/**
 * @param {string} filePath
 */
export function cvLabel(filePath) {
  const base = path.basename(String(filePath || ""));
  if (!base || /^cv\./i.test(base)) return "";
  const parts = base.replace(/\.[^.]+$/, "").split(/[-_]+/).filter(Boolean);
  const cvAt = parts.findIndex((part) => /^cv$/i.test(part));
  const kept = (cvAt >= 0 ? parts.slice(0, cvAt + 1) : parts).filter(
    (part) => !/^(classic|modern|sidebar)$/i.test(part),
  );
  return kept.join(" ");
}

/**
 * @param {string} value YYYYMMDD or YYYY-MM-DD
 * @param {Date} [now]
 */
export function formatRunDate(value, now = new Date()) {
  const match = String(value || "").match(/^(\d{4})-?(\d{2})-?(\d{2})/);
  if (!match) return "";
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return "";
  const date = new Date(Date.UTC(year, month - 1, day, 12));
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: year === now.getFullYear() ? undefined : "numeric",
    timeZone: "UTC",
  }).format(date);
}

/**
 * @param {string} slug
 * @param {Date} [now]
 */
export function labelFromSlug(slug, now = new Date()) {
  const date = formatRunDate(slug.slice(0, 8), now);
  const stem = slug.replace(/^\d{8}-/, "").replace(/-/g, " ");
  const titled = stem.replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
  return [titled, date].filter(Boolean).join(" · ");
}

/**
 * Job title, CV position, CV name, and date. Empty pieces are left out.
 * @param {{ jobTitle?: string, company?: string, position?: string, cv?: string, date?: string }} facts
 */
export function formatRunTitle(facts) {
  const jobTitle = clean(facts.jobTitle);
  const company = clean(facts.company);
  const job =
    jobTitle && company && !containsPhrase(jobTitle, company) ? `${jobTitle}, ${company}` : jobTitle || company;
  const position = clean(facts.position);
  const role = position && !sameText(position, jobTitle) && !containsPhrase(job, position) ? position : "";
  return [job, role, clean(facts.cv), clean(facts.date)].filter(Boolean).join(" · ");
}

/**
 * @param {string} file
 * @param {number} [max]
 */
function readText(file, max = 8000) {
  try {
    return readFileSync(file, "utf8").slice(0, max);
  } catch {
    return "";
  }
}

/**
 * @param {string} file
 */
function readJson(file) {
  try {
    return JSON.parse(readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

/**
 * @param {string} outDir
 * @param {string} slug
 */
function runDir(outDir, slug) {
  if (!SLUG_RE.test(slug)) return "";
  const root = path.resolve(outDir);
  const dir = path.resolve(root, slug);
  const relative = path.relative(root, dir);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return "";
  return dir;
}

/**
 * Facts already on disk for a tailor run. Missing files leave those fields blank.
 * @param {string} outDir
 * @param {string} slug
 * @param {Date} [now]
 */
export function readRunFacts(outDir, slug, now = new Date()) {
  const dir = runDir(outDir, slug);
  if (!dir) return null;
  const state = readJson(path.join(dir, "state.json"));
  const jd = readJson(path.join(dir, "jd.json"));
  const profile = readJson(path.join(dir, "profile.json"));
  const jdText = readText(path.join(dir, "jd.txt")) || readText(path.join(dir, "inputs", "jd.md"));
  const fromText = extractJob(jdText);
  const jobTitle = clean(jd && typeof jd.title === "string" ? jd.title : "") || fromText.title;
  const company = clean(jd && typeof jd.company === "string" ? jd.company : "") || fromText.company;
  const work = profile && Array.isArray(profile.work) ? profile.work : profile && Array.isArray(profile.experience) ? profile.experience : [];
  const current = work.find((item) => item && typeof item.position === "string" && item.position.trim());
  const position = clean(current ? current.position : "") || extractPosition(readText(path.join(dir, "cv.txt"), 4000));
  const cvPath =
    state && state.inputs && state.inputs.cv && typeof state.inputs.cv.original_path === "string"
      ? state.inputs.cv.original_path
      : "";
  const created = state && typeof state.created_at === "string" ? state.created_at : "";
  return {
    stage: state && typeof state.stage === "string" ? state.stage : "",
    jobTitle,
    company,
    position,
    cv: cvLabel(cvPath),
    date: formatRunDate(slug.slice(0, 8), now) || formatRunDate(created, now),
  };
}

/**
 * Live title and step for the tailor panel. Null when the slug is not a run name.
 * @param {string} outDir
 * @param {string} slug
 * @param {Date} [now]
 */
export function readRunProgress(outDir, slug, now = new Date()) {
  const facts = readRunFacts(outDir, slug, now);
  if (!facts) return null;
  const described = describeStage(facts.stage);
  return {
    stage: facts.stage,
    step: activeStep(facts.stage),
    steps: STEP_LABELS,
    title: facts.stage ? described.title : "Tailoring this CV",
    detail: waitDetail(facts.stage),
    label: formatRunTitle(facts) || labelFromSlug(slug, now),
  };
}
