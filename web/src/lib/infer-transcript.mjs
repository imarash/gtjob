/**
 * Fold Cursor SDK stream events into a short chat transcript.
 * Assistant text is appended until a tool call starts a new bubble.
 * A later event that already contains the bubble is a snapshot and replaces it.
 * Tool rows update in place by call id. User echoes from the SDK are ignored;
 * the app records the person's own messages.
 */

const MAX_TURNS = 80;
const MAX_TEXT = 12000;
const CHOICE_KEYS = ["command", "cmd", "path", "file_path", "file", "target_file", "target", "pattern", "query", "glob", "url"];

const TOOL_LABELS = {
  read: "Read",
  shell: "Shell",
  edit: "Edit",
  write: "Write",
  grep: "Search",
  glob: "Find files",
  delete: "Delete",
  task: "Task",
};

/**
 * @param {unknown} value
 */
function asText(value) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.filter((item) => typeof item === "string").join(" ");
  return "";
}

/**
 * @param {unknown} args
 */
export function toolDetail(args) {
  if (!args || typeof args !== "object") return "";
  const record = /** @type {Record<string, unknown>} */ (args);
  for (const key of CHOICE_KEYS) {
    const text = asText(record[key]).replace(/\s+/g, " ").trim();
    if (text) return text.slice(0, 160);
  }
  return "";
}

/**
 * @param {unknown} name
 */
export function toolLabel(name) {
  const key = String(name || "tool").toLowerCase();
  return TOOL_LABELS[key] || key.replace(/_/g, " ");
}

/**
 * @param {string[]} log
 */
export function turnsFromLog(log) {
  return log.map((name, index) => ({
    id: `log-${index}`,
    role: "tool",
    name: String(name || "tool"),
    status: "completed",
    text: "",
    detail: "",
  }));
}

/**
 * @param {string} text
 */
export function userTurn(text) {
  return {
    id: `user-${Date.now()}`,
    role: "user",
    name: "",
    status: "",
    text: String(text || "").slice(0, 8000),
    detail: "",
  };
}

/**
 * @param {unknown[]} turns
 */
function trim(turns) {
  const sliced = turns.length > MAX_TURNS ? turns.slice(-MAX_TURNS) : turns;
  return sliced.map((turn) => {
    if (!turn || typeof turn !== "object") return turn;
    const row = /** @type {{ text?: string, detail?: string }} */ (turn);
    const text = typeof row.text === "string" && row.text.length > MAX_TEXT ? row.text.slice(-MAX_TEXT) : row.text;
    const detail = typeof row.detail === "string" ? row.detail.slice(0, 160) : row.detail;
    return { ...row, text, detail };
  });
}

/**
 * @param {unknown} event
 */
function assistantText(event) {
  const message = event && typeof event === "object" ? /** @type {{ message?: { content?: unknown[] } }} */ (event).message : null;
  const content = Array.isArray(message?.content) ? message.content : [];
  return content
    .filter((block) => block && typeof block === "object" && /** @type {{ type?: string }} */ (block).type === "text")
    .map((block) => String(/** @type {{ text?: string }} */ (block).text || ""))
    .join("");
}

/**
 * Ids stay unique after the transcript keeps only the latest turns.
 * An index into the array collides once that window slides.
 * @param {unknown[]} turns
 */
function nextAssistantId(turns) {
  let max = 0;
  for (const turn of turns) {
    const id = turn && typeof turn === "object" ? String(/** @type {{ id?: string }} */ (turn).id || "") : "";
    const match = /^assistant-(\d+)$/.exec(id);
    if (match) max = Math.max(max, Number(match[1]));
  }
  return `assistant-${max + 1}`;
}

/**
 * @param {unknown[]} turns
 * @param {unknown} event
 */
export function foldEvent(turns, event) {
  const copy = Array.isArray(turns) ? turns.slice() : [];
  if (!event || typeof event !== "object") return trim(copy);
  const row = /** @type {{ type?: string, call_id?: string, name?: string, status?: string, args?: unknown }} */ (event);
  if (row.type === "assistant") {
    const text = assistantText(event);
    if (!text) return trim(copy);
    const last = copy[copy.length - 1];
    if (last && /** @type {{ role?: string, text?: string }} */ (last).role === "assistant") {
      const previous = String(/** @type {{ text?: string }} */ (last).text || "");
      if (text.startsWith(previous)) {
        copy[copy.length - 1] = { .../** @type {object} */ (last), text };
      } else if (!previous.startsWith(text) && !previous.endsWith(text)) {
        copy[copy.length - 1] = { .../** @type {object} */ (last), text: previous + text };
      }
      return trim(copy);
    }
    copy.push({ id: nextAssistantId(copy), role: "assistant", name: "", status: "", text, detail: "" });
    return trim(copy);
  }
  if (row.type === "tool_call") {
    const id = String(row.call_id || `tool-${copy.length}`);
    const detail = toolDetail(row.args);
    const index = copy.findIndex((turn) => turn && /** @type {{ role?: string, id?: string }} */ (turn).role === "tool" && /** @type {{ id?: string }} */ (turn).id === id);
    const next = {
      id,
      role: "tool",
      name: String(row.name || "tool"),
      status: String(row.status || "running"),
      text: "",
      detail,
    };
    if (index >= 0) {
      const previous = /** @type {{ detail?: string }} */ (copy[index]);
      copy[index] = { ...next, detail: detail || previous.detail || "" };
    } else {
      copy.push(next);
    }
    return trim(copy);
  }
  return trim(copy);
}
