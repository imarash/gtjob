const SLUG = /^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$/;

/**
 * argv for `node set-status.mjs`. One element per argument.
 * The posting URL and the company name are not accepted here.
 * @param {{ script: string, row: string | number, status: string, note?: string, allowed: string[] }} input
 * @returns {string[]}
 */
export function buildSetStatusArgs(input) {
  const row = String(input.row);
  if (!/^\d+$/.test(row)) throw new Error("Tracker row must be a number.");
  if (!input.allowed.includes(input.status)) {
    throw new Error(
      `Rejected status "${input.status}". templates/states.yml does not list it.`,
    );
  }
  const args = [input.script, "--row", row, input.status];
  if (input.note !== undefined) {
    if (typeof input.note !== "string" || input.note.includes("\0")) {
      throw new Error("Note is not valid.");
    }
    args.push("--note", input.note);
  }
  return args;
}

/** The notes token that links a tracker row to `out/<slug>/`. */
export function attachRunNote(slug) {
  if (!SLUG.test(slug)) throw new Error("Run slug is not a single path segment.");
  return `gtjob-run:${slug}`;
}

/**
 * argv for a read-only liveness check. `--no-record` keeps scan history unchanged.
 * @param {string} script
 * @param {string} url
 */
export function buildLivenessArgs(script, url) {
  if (!/^https?:\/\//i.test(url) || /\s/.test(url)) {
    throw new Error("Posting URL must be one http(s) URL.");
  }
  return [script, "--no-record", url];
}
