import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";

const SLUG_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$/;

/**
 * The error line plus the violation bullets printed under it.
 * @param {string} text
 */
export function formatRunError(text) {
  const raw = String(text || "");
  const lines = raw
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line, i, all) => line.trim() || (i > 0 && all[i + 1]?.trim()));
  let index = -1;
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    if (/error\[/.test(lines[i])) {
      index = i;
      break;
    }
  }
  if (index < 0) return lines.at(-1)?.trim() || "";
  /** @type {string[]} */
  const out = [];
  const head = lines[index].replace(/^cvt:\s*/, "").trim();
  out.push(head);
  for (const line of lines.slice(index + 1)) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (out.length && out.at(-1) !== "") out.push("");
      continue;
    }
    if (trimmed.startsWith("hint:")) continue;
    if (trimmed.startsWith("+") && /more \(/.test(trimmed)) continue;
    out.push(line.trimEnd());
    if (/^Your answers could not be saved:/.test(trimmed)) {
      // keep the whole guided block (• q-N lines)
      continue;
    }
  }
  return out.join("\n").trim();
}

/**
 * What the tailor panel should show after `gtjob continue` exits.
 * A crash while questions are still open is an error. Exit 6 is the normal pause.
 * @param {number} code
 * @param {string} stage
 * @param {string} [stderr]
 * @returns {{ phase: string, message: string }}
 */
export function continueOutcome(code, stage, stderr) {
  const gate = stage === "awaiting_answers" || stage === "awaiting_approval";
  if (code === 6 || (code === 0 && gate)) {
    if (stage === "awaiting_approval") {
      return { phase: "awaiting_approval", message: "The draft is ready for approval." };
    }
    return { phase: "awaiting_answers", message: "A few questions are waiting." };
  }
  if (code !== 0) {
    return {
      phase: "error",
      message: formatRunError(stderr) || "The run stopped before the PDF was ready.",
    };
  }
  if (stage === "reported") return { phase: "finished", message: "The tailored CV is ready." };
  return {
    phase: "error",
    message: stage ? `The run stopped while it was still at ${stage}.` : "The run stopped before the PDF was ready.",
  };
}

/**
 * @param {string} root
 */
export function inferDir(root) {
  return path.join(root, ".studio", "infer");
}

/**
 * @param {string} root
 * @param {string} slug
 */
export function statusPath(root, slug) {
  if (!SLUG_RE.test(slug)) throw new Error("Run is not a slug.");
  return path.join(inferDir(root), `${slug}.json`);
}

/**
 * The person's own words for the next Cursor turn. Not a run artifact.
 * @param {string} root
 * @param {string} slug
 */
export function replyPath(root, slug) {
  if (!SLUG_RE.test(slug)) throw new Error("Run is not a slug.");
  return path.join(inferDir(root), `${slug}.reply.txt`);
}

/**
 * @param {string} root
 * @param {string} slug
 * @param {string} text
 */
export function writeReply(root, slug, text) {
  const file = replyPath(root, slug);
  mkdirSync(inferDir(root), { recursive: true });
  writeFileSync(file, text);
  return file;
}

const NOTED_QUESTION = /^q-\d+\s*:/gm;

/**
 * A blank answer can be skipped, then filled in on the next try.
 * Put those questions back to pending so answer_parse can commit the new text.
 * @param {string} root
 * @param {string} slug
 * @param {string} text
 * @returns {string[]}
 */
export function reopenNotedQuestions(root, slug, text) {
  if (!SLUG_RE.test(slug)) throw new Error("Run is not a slug.");
  const ids = new Set(
    [...String(text).matchAll(NOTED_QUESTION)].map((match) => match[0].replace(/\s*:$/, "").trim()),
  );
  if (ids.size === 0) return [];
  const file = path.join(root, "out", slug, "questions.json");
  const data = readJson(file);
  if (!data || !Array.isArray(data.questions)) return [];
  /** @type {string[]} */
  const opened = [];
  for (const question of data.questions) {
    if (!question || !ids.has(question.id)) continue;
    if (question.status !== "skipped" && question.status !== "defaulted") continue;
    question.status = "pending";
    opened.push(question.id);
  }
  if (opened.length === 0) return [];
  const tmp = `${file}.tmp`;
  writeFileSync(tmp, `${JSON.stringify(data, null, 2)}\n`);
  renameSync(tmp, file);
  return opened;
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
 * @param {string} root
 * @param {string} slug
 */
export function readInferStatus(root, slug) {
  return readJson(statusPath(root, slug));
}

/**
 * @param {string} root
 * @param {string} slug
 * @param {Record<string, unknown>} patch
 */
export function writeInferStatus(root, slug, patch) {
  const current = readInferStatus(root, slug) || { slug };
  const next = { ...current, ...patch, slug, updatedAt: new Date().toISOString() };
  if (Array.isArray(next.log) && next.log.length > 12) next.log = next.log.slice(-12);
  if (Array.isArray(next.turns)) {
    next.turns = next.turns.slice(-80).map((turn) => {
      if (!turn || typeof turn !== "object") return turn;
      const text = typeof turn.text === "string" && turn.text.length > 12000 ? turn.text.slice(-12000) : turn.text;
      const detail = typeof turn.detail === "string" ? turn.detail.slice(0, 160) : turn.detail;
      return { ...turn, text, detail };
    });
  }
  mkdirSync(inferDir(root), { recursive: true });
  const file = statusPath(root, slug);
  const tmp = `${file}.tmp`;
  writeFileSync(tmp, JSON.stringify(next));
  renameSync(tmp, file);
  return next;
}

/**
 * @param {string} root
 */
export function readLoginStatus(root) {
  return readJson(path.join(inferDir(root), "login.json"));
}

/**
 * @param {string} root
 * @param {Record<string, unknown>} patch
 */
export function writeLoginStatus(root, patch) {
  mkdirSync(inferDir(root), { recursive: true });
  const file = path.join(inferDir(root), "login.json");
  const current = readJson(file) || {};
  const next = { ...current, ...patch, updatedAt: new Date().toISOString() };
  delete next.apiKey;
  const tmp = `${file}.tmp`;
  writeFileSync(tmp, JSON.stringify(next));
  renameSync(tmp, file);
  return next;
}

/**
 * A key in the environment, or a key minted by Cursor.auth.login().
 * The IDE login is not enough.
 */
export function cursorConnected() {
  if (process.env.CURSOR_API_KEY) return true;
  return existsSync(path.join(homedir(), ".cursor", "sdk", "auth.json"));
}

/**
 * @param {unknown} pid
 */
export function pidAlive(pid) {
  if (typeof pid !== "number" || !Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}
