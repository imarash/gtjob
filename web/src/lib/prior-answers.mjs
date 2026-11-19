import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { controlKind, questionChoices } from "./answer-select.mjs";
import { SLUG_RE } from "./runs.mjs";

/**
 * Earlier answers for questions the person has already been asked.
 * Question ids are per run, so a match is the same bullet, the same
 * standing question (template, earlier experience), or the same gap choice.
 * The caller shows the match and waits for an explicit approval.
 */

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
 * @param {string} text
 */
function cleanVerbatim(text) {
  return String(text || "")
    .replace(/^q-\d+:\s*/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * @param {unknown} ids
 */
function itemKey(ids) {
  if (!Array.isArray(ids)) return "";
  return ids.map(String).map((id) => id.trim()).filter(Boolean).sort().join("|");
}

/**
 * @param {{ topic?: string, type?: string, prompt?: string }} question
 */
function family(question) {
  const prompt = String(question.prompt || "")
    .toLowerCase()
    .replace(/[-–—]/g, " ");
  const topic = question.topic || "";
  const type = question.type || "";
  if (topic === "strategy" && type === "single_select" && /\btemplate\b/.test(prompt)) return "template";
  if (
    topic === "strategy" &&
    (type === "yes_no" || type === "single_select") &&
    /earlier experience|older than|roles before|pre-20|pre–/.test(prompt)
  ) {
    return "earlier";
  }
  return "";
}

/**
 * @param {string} iso
 */
function stamp(iso) {
  const value = Date.parse(iso || "");
  return Number.isFinite(value) ? value : 0;
}

/**
 * @param {{ stamp: number }[]} hits
 */
function latest(hits) {
  let best = null;
  for (const hit of hits) {
    if (!best || hit.stamp >= best.stamp) best = hit;
  }
  return best;
}

/**
 * @param {{ choices?: { id: string, label: string }[] }} question
 * @param {string[]} choiceIds
 */
function labelsFor(question, choiceIds) {
  const byId = new Map(questionChoices(question).map((choice) => [choice.id, choice.label]));
  return choiceIds.map((id) => byId.get(id) || id).join(", ");
}

/**
 * @param {string} outDir
 * @param {string} slug
 */
function historyOf(outDir, slug) {
  /** @type {{ question: Record<string, unknown>, text: string, choiceIds: string[], at: string, stamp: number }[]} */
  const history = [];
  let entries;
  try {
    entries = readdirSync(outDir, { withFileTypes: true });
  } catch {
    return history;
  }
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.isSymbolicLink() || !SLUG_RE.test(entry.name) || entry.name === slug) continue;
    const dir = path.join(outDir, entry.name);
    const questionsFile = readJson(path.join(dir, "questions.json"));
    const answersFile = readJson(path.join(dir, "answers.json"));
    const questions = questionsFile && Array.isArray(questionsFile.questions) ? questionsFile.questions : null;
    const rounds = answersFile && Array.isArray(answersFile.rounds) ? answersFile.rounds : null;
    if (!questions || !rounds) continue;
    const byId = new Map(questions.map((question) => [question.id, question]));
    for (const round of rounds) {
      const at = typeof round.received_at === "string" ? round.received_at : "";
      const items = Array.isArray(round.items) ? round.items : [];
      for (const item of items) {
        if (!item || item.action === "skip" || !item.question_id) continue;
        const question = byId.get(item.question_id);
        if (!question) continue;
        const attestations = Array.isArray(item.attestations) ? item.attestations : [];
        const text = cleanVerbatim(
          attestations.map((row) => row && (row.verbatim || row.claim)).find((value) => String(value || "").trim()) || "",
        );
        const choiceIds = (Array.isArray(item.choice_ids) ? item.choice_ids : []).map(String).filter(Boolean);
        if (!text && choiceIds.length === 0) continue;
        history.push({ question, text, choiceIds, at, stamp: stamp(at) });
      }
    }
  }
  return history;
}

/**
 * @param {Record<string, unknown>} question
 * @param {{ question: Record<string, unknown>, text: string, choiceIds: string[], at: string, stamp: number }[]} history
 */
function matchOne(question, history) {
  const kind = controlKind(question);
  if (kind === "text") {
    const key = itemKey(question.links && question.links.item_ids);
    if (!key) return null;
    const topic = question.topic || "";
    const hits = history.filter(
      (hit) =>
        controlKind(hit.question) === "text" &&
        (hit.question.topic || "") === topic &&
        itemKey(hit.question.links && hit.question.links.item_ids) === key &&
        hit.text &&
        hit.text.toLowerCase() !== "no number",
    );
    const best = latest(hits);
    if (!best) return null;
    return { kind: "text", text: best.text, choiceIds: [], summary: best.text, at: best.at };
  }

  const group = family(question);
  if (group) {
    const allowed = new Set(questionChoices(question).map((choice) => choice.id));
    const hits = history.filter((hit) => family(hit.question) === group && hit.choiceIds.some((id) => allowed.has(id)));
    const best = latest(hits);
    if (!best) return null;
    const choiceIds = best.choiceIds.filter((id) => allowed.has(id));
    if (choiceIds.length === 0) return null;
    const kept = kind === "single" ? choiceIds.slice(0, 1) : choiceIds;
    return { kind, text: "", choiceIds: kept, summary: labelsFor(question, kept), at: best.at };
  }

  if (question.type === "multi_select" && question.topic === "gap") {
    /** @type {string[]} */
    const chosen = [];
    let at = "";
    let newest = -1;
    for (const choice of questionChoices(question)) {
      const hits = history.filter(
        (hit) =>
          hit.question.type === "multi_select" &&
          hit.question.topic === "gap" &&
          questionChoices(hit.question).some((offered) => offered.id === choice.id),
      );
      const best = latest(hits);
      if (!best || !best.choiceIds.includes(choice.id)) continue;
      chosen.push(choice.id);
      if (best.stamp >= newest) {
        newest = best.stamp;
        at = best.at;
      }
    }
    if (chosen.length === 0) return null;
    return { kind: "multiple", text: "", choiceIds: chosen, summary: labelsFor(question, chosen), at };
  }

  return null;
}

/**
 * @param {string} outDir
 * @param {string} slug
 * @returns {Record<string, { kind: "text" | "single" | "multiple", text: string, choiceIds: string[], summary: string, at: string }>}
 */
export function priorAnswers(outDir, slug) {
  if (!SLUG_RE.test(String(slug || ""))) return {};
  const root = path.resolve(outDir);
  const currentDir = path.resolve(root, slug);
  const relative = path.relative(root, currentDir);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) return {};
  const current = readJson(path.join(currentDir, "questions.json"));
  const questions = current && Array.isArray(current.questions) ? current.questions : [];
  const history = historyOf(root, slug);
  /** @type {Record<string, { kind: "text" | "single" | "multiple", text: string, choiceIds: string[], summary: string, at: string }>} */
  const priors = {};
  for (const question of questions) {
    if (question.status && question.status !== "pending") continue;
    const prior = matchOne(question, history);
    if (prior) priors[question.id] = prior;
  }
  return priors;
}
