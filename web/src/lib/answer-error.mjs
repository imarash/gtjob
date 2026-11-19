/**
 * Turn answers-apply / answer_parse violations into question-level guidance for Studio.
 */

const TERM_RE = /term '([^']+)'/;
const Q_LINE_RE = /^(q-\d+)\s*:\s*(.*)$/i;

/**
 * @param {string} prompt
 */
export function questionLabel(prompt) {
  const text = String(prompt || "").trim();
  if (!text) return "";
  if (text.includes(":")) return text.split(":")[0].trim();
  return text.length > 100 ? `${text.slice(0, 100)}…` : text;
}

/**
 * @param {{ code?: string, message?: string }} violation
 * @param {{ prompt?: string } | null | undefined} question
 * @param {string} userAnswer
 */
export function fixHint(violation, question, userAnswer) {
  const code = String(violation.code || "");
  const msg = String(violation.message || "");
  if (code === "unsupported_term" || msg.includes("not something the user said")) {
    const term = TERM_RE.exec(msg)?.[1] || "that term";
    if (userAnswer) {
      return (
        `Your answer did not include «${term}». The parser tried to add it from the question text. ` +
        `Either type «${term}» yourself if true, or shorten the answer so only your words are used ` +
        `(example for PCI scope: "PCI scope: infrastructure only, not cardholder data").`
      );
    }
    return `Do not add «${term}» unless you typed it. Leave the field blank to keep the default bullet.`;
  }
  if (code === "unsupported_number") {
    return "Remove numbers you did not state. Metric answers should only include figures you are willing to defend.";
  }
  if (code === "fact_mismatch") {
    return "Copy your exact words into the answer box (the verbatim clause must appear in what you submit).";
  }
  return "Edit this answer and submit again, or clear it to accept the default.";
}

/**
 * @param {string} raw
 */
export function replyByQuestion(raw) {
  /** @type {Record<string, string>} */
  const out = {};
  for (const line of String(raw || "").split("\n")) {
    const match = Q_LINE_RE.exec(line.trim());
    if (!match) continue;
    out[match[1].toLowerCase()] = match[2].trim();
  }
  return out;
}

/**
 * @param {Array<{ question_id?: string, item_id?: string, code?: string, message?: string }>} violations
 * @param {Array<{ id: string, prompt?: string }>} [questions]
 * @param {Record<string, string>} [notes]
 * @param {string} [rawText]
 */
export function formatAnswerViolations(violations, questions, notes = {}, rawText = "") {
  if (!Array.isArray(violations) || violations.length === 0) return "";
  const byId = Object.fromEntries((questions || []).map((q) => [q.id, q]));
  const fromReply = replyByQuestion(rawText);
  /** @type {Record<string, string>} */
  const merged = { ...fromReply, ...notes };
  /** @type {Record<string, { question_id?: string, code?: string, message?: string }>} */
  const byQ = {};
  for (const v of violations) {
    const qid = String(v.question_id || "").trim();
    if (!qid) continue;
    const prev = byQ[qid];
    const termish = v.code === "unsupported_term" || String(v.message || "").includes("not something the user said");
    const prevTermish =
      prev && (prev.code === "unsupported_term" || String(prev.message || "").includes("not something the user said"));
    if (!prev || (termish && !prevTermish)) byQ[qid] = v;
  }
  /** @type {string[]} */
  const lines = ["Your answers could not be saved:", ""];
  for (const qid of Object.keys(byQ).sort((a, b) => Number(a.split("-")[1]) - Number(b.split("-")[1]))) {
    const v = byQ[qid];
    const q = byId[qid];
    const label = questionLabel(q?.prompt);
    lines.push(`• ${qid}${label ? ` — ${label}` : ""}`);
    const ans = String(merged[qid] || "").trim();
    if (ans) lines.push(`  Your answer: ${ans.length > 240 ? `${ans.slice(0, 240)}…` : ans}`);
    lines.push(`  Issue: ${String(v.message || "").trim()}`);
    lines.push(`  How to fix: ${fixHint(v, q, ans)}`);
    lines.push("");
  }
  if (Object.keys(byQ).length === 0) return "";
  return lines.join("\n").trimEnd();
}

/**
 * @param {Record<string, unknown> | null | undefined} envelope
 * @param {Array<{ id: string, prompt?: string }>} [questions]
 * @param {Record<string, string>} [notes]
 * @param {string} [rawText]
 */
export function formatEnvelopeAnswerFailure(envelope, questions, notes, rawText) {
  /** @type {unknown} */
  const data = envelope && typeof envelope === "object" ? envelope.data : null;
  const violations =
    data && typeof data === "object" && Array.isArray(data.violations) ? data.violations : [];
  const block = formatAnswerViolations(violations, questions, notes, rawText);
  const head = envelope?.error?.message || "";
  if (block && head) return `${head}\n\n${block}`;
  return block || head;
}
