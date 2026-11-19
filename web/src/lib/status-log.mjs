import { readFileSync } from "node:fs";

/**
 * Rows of data/status-log.tsv for one tracker number.
 * A missing file is an empty timeline. A broken line is skipped.
 * @param {string} filePath
 * @param {string} num
 */
export function readStatusLog(filePath, num) {
  let text;
  try {
    text = readFileSync(filePath, "utf8");
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error ? error.code : "";
    if (code === "ENOENT") return { ok: true, missing: true, events: [], error: "" };
    const message = error instanceof Error ? error.message : String(error);
    return { ok: false, missing: false, events: [], error: message };
  }
  /** @type {{ num: string, date: string, from: string, to: string, source: string, note: string }[]} */
  const events = [];
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    const parts = line.split("\t");
    if (parts.length < 4) continue;
    if (!/^\d+$/.test(parts[0])) continue;
    if (parts[0] !== num) continue;
    events.push({
      num: parts[0],
      date: parts[1] ?? "",
      from: parts[2] ?? "",
      to: parts[3] ?? "",
      source: parts[4] ?? "",
      note: parts[5] ?? "",
    });
  }
  return { ok: true, missing: false, events, error: "" };
}
