import { existsSync, mkdirSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { SLUG_RE } from "./runs.mjs";

const SLUG_MAX = 121;

/**
 * @param {string} cvName
 */
export function polishStem(cvName) {
  const base = path.basename(cvName, path.extname(cvName));
  let stem = base
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  let trimmed = stem;
  let next = trimmed.replace(/-(cv|classic|modern|sidebar)$/, "");
  while (next !== trimmed) {
    trimmed = next;
    next = trimmed.replace(/-(cv|classic|modern|sidebar)$/, "");
  }
  return trimmed.replace(/-+$/g, "") || "cv";
}

/**
 * @param {string} cvName
 * @param {string} date YYYYMMDD
 * @param {Set<string>} taken
 */
export function polishSlug(cvName, date, taken) {
  const prefix = `${date}-${polishStem(cvName)}-generic`;
  let slug = prefix.slice(0, SLUG_MAX);
  let n = 2;
  while (taken.has(slug) || !SLUG_RE.test(slug)) {
    const suffix = `-${n}`;
    slug = `${prefix.slice(0, SLUG_MAX - suffix.length)}${suffix}`;
    n += 1;
    if (n > 50) throw new Error("Too many polish runs for this CV today.");
  }
  return slug;
}

/**
 * @param {Date} now
 */
export function polishDate(now) {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}${month}${day}`;
}

/**
 * Extract the CV and open out/<date>-<name>-generic/. The text stays on disk.
 * @param {string} root
 * @param {string} cvName
 */
export function startPolishRun(root, cvName) {
  const name = path.basename(String(cvName || ""));
  if (!name || name !== cvName || name.startsWith(".") || name.includes("\0")) {
    throw new Error("Pick a file by its name in CVs/.");
  }
  const cvPath = path.join(root, "CVs", name);
  if (!existsSync(cvPath)) throw new Error("That CV is not in CVs/.");
  const script = path.join(root, ".claude", "skills", "tailoring-cvs", "scripts", "polish_render.py");
  const result = spawnSync("uv", ["run", script, "extract", cvPath], {
    cwd: root,
    encoding: "utf8",
    timeout: 60_000,
    maxBuffer: 8_000_000,
    env: { ...process.env, UV_CACHE_DIR: path.join(root, ".cache", "uv") },
  });
  if (result.error) throw new Error(result.error.message || "The CV could not be read.");
  if (result.status !== 0) {
    const line = String(result.stderr || "")
      .trim()
      .split("\n")
      .filter(Boolean)
      .at(-1);
    throw new Error((line || "The CV could not be read.").replace(/^polish_render:\s*/, ""));
  }
  const text = String(result.stdout || "");
  if (!text.trim()) throw new Error("The CV has no readable text.");
  const outDir = path.join(root, "out");
  mkdirSync(outDir, { recursive: true });
  /** @type {Set<string>} */
  const taken = new Set();
  try {
    for (const entry of readdirSync(outDir)) taken.add(entry);
  } catch {
    /* empty out/ */
  }
  const slug = polishSlug(name, polishDate(new Date()), taken);
  const dir = path.join(outDir, slug);
  mkdirSync(dir);
  writeFileSync(path.join(dir, "cv.txt"), text.endsWith("\n") ? text : `${text}\n`);
  writeFileSync(path.join(dir, "polish.json"), `${JSON.stringify({ cv: name }, null, 2)}\n`);
  return { slug };
}
