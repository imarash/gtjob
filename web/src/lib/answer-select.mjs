/**
 * Map a question form onto `cvt answers-apply --select`.
 * Multi-select and scope questions keep every chosen id.
 * Single-select and yes/no keep one.
 * Written answers stay out of --select; cvt only accepts a choice id or skip there.
 */

const CHOICE_RE = /^[a-z0-9_]+$/;

/**
 * @param {{ type?: string, choices?: { id?: string }[] }} question
 */
export function controlKind(question) {
  if (question.type === "multi_select" || question.type === "scope_confirm") return "multiple";
  if (question.type === "free_text") return "text";
  if (question.type === "yes_no" || question.type === "single_select") return "single";
  if (!Array.isArray(question.choices) || question.choices.length === 0) return "text";
  return "single";
}

/**
 * @param {{ type?: string, choices?: { id: string, label: string }[] }} question
 */
export function questionChoices(question) {
  if (Array.isArray(question.choices) && question.choices.length > 0) return question.choices;
  if (question.type === "yes_no") {
    return [
      { id: "yes", label: "Yes" },
      { id: "no", label: "No" },
    ];
  }
  return [];
}

/**
 * @param {string[] | undefined} ids
 * @param {"multiple" | "single" | "text"} kind
 */
function cleanIds(ids, kind) {
  const chosen = (Array.isArray(ids) ? ids : []).map(String).filter((id) => CHOICE_RE.test(id));
  if (kind === "single") return chosen.slice(0, 1);
  return [...new Set(chosen)];
}

/**
 * Defaults are pre-checked. A key set to [] means the person cleared it.
 * A missing key still uses the question default.
 * @param {{ id: string, type?: string, choices?: { id: string, label: string }[], default?: { choice_ids?: string[] } }[]} questions
 */
export function initialPicked(questions) {
  /** @type {Record<string, string[]>} */
  const picked = {};
  for (const question of questions) {
    const kind = controlKind(question);
    if (kind === "text") continue;
    const ids = cleanIds(question.default?.choice_ids, kind);
    if (ids.length) picked[question.id] = ids;
  }
  return picked;
}

/**
 * A question already answered or skipped is left out. Sending it again makes cvt reject the whole round.
 * @param {{ id: string, status?: string, type?: string, choices?: { id: string, label: string }[], default?: { choice_ids?: string[], description?: string } }[]} questions
 * @param {Record<string, string[]>} picked
 * @param {Record<string, string>} notes
 * @returns {{ select: string[], prose: string, defaultRest: boolean, auto: boolean }}
 */
export function buildAnswerRequest(questions, picked, notes) {
  const open = questions.filter((question) => !question.status || question.status === "pending");
  /** @type {string[]} */
  const select = [];
  /** @type {string[]} */
  const prose = [];
  for (const question of open) {
    const kind = controlKind(question);
    if (kind === "text") {
      const note = String(notes[question.id] || "").trim();
      if (note) prose.push(`${question.id}: ${note}`);
      continue;
    }
    const given = Object.prototype.hasOwnProperty.call(picked, question.id) ? picked[question.id] : question.default?.choice_ids;
    const chosen = cleanIds(given, kind);
    select.push(chosen.length ? `${question.id}=${chosen.join(",")}` : `${question.id}=skip`);
  }
  if (prose.length > 0) {
    for (const question of open) {
      if (controlKind(question) !== "text") continue;
      if (String(notes[question.id] || "").trim()) continue;
      select.push(`${question.id}=skip`);
    }
    return { select, prose: prose.join("\n"), defaultRest: false, auto: false };
  }
  if (select.length === 0) return { select: [], prose: "", defaultRest: false, auto: true };
  return { select, prose: "", defaultRest: true, auto: false };
}

/**
 * Written answers for questions that are no longer pending still go back to Cursor.
 * They are not sent through --select.
 * @param {{ id: string, status?: string, type?: string, choices?: { id: string, label: string }[], default?: { choice_ids?: string[], description?: string } }[]} questions
 * @param {Record<string, string[]>} picked
 * @param {Record<string, string>} notes
 */
/**
 * A committed round can still exit as "awaiting" when written answers remain.
 * That is not a rejection. A rejection carries an error message.
 * @param {{ ok?: boolean, exit_code?: number, error?: { message?: string, hint?: string } } | null | undefined} envelope
 * @param {string} [httpError]
 * @returns {string}
 */
export function applyFailure(envelope, httpError) {
  const message = (envelope && envelope.error && envelope.error.message) || httpError || "";
  if (message) {
    const hint = envelope && envelope.error && envelope.error.hint;
    return hint ? `${message}. ${hint}` : message;
  }
  if (envelope && envelope.ok === false && envelope.exit_code === 6) return "";
  return "Those answers were not applied.";
}

/**
 * Written answers for questions that are no longer pending still go back to Cursor.
 * They are not sent through --select.
 * @param {{ id: string, status?: string, type?: string, choices?: { id: string, label: string }[], default?: { choice_ids?: string[], description?: string } }[]} questions
 * @param {Record<string, string[]>} picked
 * @param {Record<string, string>} notes
 */
export function pendingReply(questions, picked, notes) {
  const plan = buildAnswerRequest(questions, picked, notes);
  const covered = new Set(questions.map((question) => question.id));
  const extra = [];
  for (const [id, value] of Object.entries(notes || {})) {
    if (covered.has(id) || !/^q-\d+$/.test(id)) continue;
    const text = String(value || "").trim();
    if (text) extra.push(`${id}: ${text}`);
  }
  const prose = [plan.prose, ...extra].filter(Boolean).join("\n");
  return { ...plan, prose };
}
