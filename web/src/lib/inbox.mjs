import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";

/**
 * @typedef {object} InboxItem
 * @property {string} id
 * @property {string} at
 * @property {"url" | "text"} kind
 * @property {string} text
 * @property {string} hint
 */

/**
 * @param {{ careerOpsRoot: string | null, kind: "url" | "text" }} input
 */
export function evaluationHint(input) {
  if (!input.careerOpsRoot) {
    return "Tracking is off until CAREER_OPS_ROOT is set. This is saved on this machine only. Studio did not score it.";
  }
  const pipeline = path.join(input.careerOpsRoot, "data", "pipeline.md");
  if (input.kind === "url") {
    return `Saved. Studio did not score it. Add the URL to ${pipeline}, then run career-ops pipeline mode in that checkout.`;
  }
  return `Saved. Studio did not score it. Put the text in a file, add that file to ${pipeline}, then run career-ops pipeline mode.`;
}

/**
 * A missing inbox is empty. Invalid JSON is an error, not an empty list.
 * @param {string} filePath
 * @returns {{ ok: true, missing: boolean, items: InboxItem[], error: "" } | { ok: false, missing: false, items: [], error: string }}
 */
export function readInbox(filePath) {
  let text;
  try {
    text = readFileSync(filePath, "utf8");
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error ? error.code : "";
    if (code === "ENOENT") return { ok: true, missing: true, items: [], error: "" };
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, missing: false, items: [], error: message };
  }
  try {
    const parsed = JSON.parse(text);
    const items = Array.isArray(parsed?.items) ? parsed.items : null;
    if (!items) return { ok: false, missing: false, items: [], error: "inbox.json is not a list" };
    return {
      ok: true,
      missing: false,
      items: items.flatMap((item) => {
        if (!item || typeof item.text !== "string" || typeof item.id !== "string") return [];
        return [
          {
            id: item.id,
            at: typeof item.at === "string" ? item.at : "",
            kind: item.kind === "url" ? "url" : "text",
            text: item.text,
            hint: typeof item.hint === "string" ? item.hint : "",
          },
        ];
      }),
      error: "",
    };
  } catch {
    return { ok: false, missing: false, items: [], error: "inbox.json is not valid JSON" };
  }
}

/**
 * @param {string} filePath
 * @param {{ kind: "url" | "text", text: string, hint: string }} item
 */
export function appendInbox(filePath, item) {
  const text = item.text.trim();
  if (!text) throw new Error("Paste a URL or some job text.");
  if (text.length > 100_000) throw new Error("That text is too long to store.");
  const kind = /^https?:\/\/\S+$/i.test(text) ? "url" : "text";
  const next = {
    id: randomUUID(),
    at: new Date().toISOString(),
    kind,
    text,
    hint: item.hint,
  };
  const existing = readInbox(filePath);
  if (!existing.ok) throw new Error(existing.error);
  const items = existing.items;
  items.unshift(next);
  const dir = path.dirname(filePath);
  mkdirSync(dir, { recursive: true });
  const temporary = path.join(dir, `.inbox-${next.id}.json`);
  writeFileSync(temporary, JSON.stringify({ items: items.slice(0, 50) }, null, 2));
  renameSync(temporary, filePath);
  return next;
}
