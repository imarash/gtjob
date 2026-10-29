import { existsSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { SLUG_RE } from "./runs.mjs";

/**
 * Compile modern, classic, and sidebar next to the run's PDF.
 * @param {string} root
 * @param {string} slug
 */
export function renderTemplatePreviews(root, slug) {
  if (!SLUG_RE.test(slug)) throw new Error("Name the run.");
  const outDir = path.resolve(root, "out");
  const runDir = path.resolve(outDir, slug);
  if (!runDir.startsWith(`${outDir}${path.sep}`)) throw new Error("Name the run.");
  if (!existsSync(path.join(runDir, "tailored.json"))) {
    throw new Error("This run has no tailored CV to render.");
  }
  const script = path.join(root, "web", "scripts", "render-previews.py");
  const result = spawnSync("uv", ["run", script, runDir], {
    cwd: root,
    encoding: "utf8",
    timeout: 180_000,
    maxBuffer: 4_000_000,
    env: { ...process.env, UV_CACHE_DIR: path.join(root, ".cache", "uv") },
  });
  if (result.error) {
    const message = result.error.message || "The layouts did not render.";
    throw new Error(message);
  }
  if (result.status !== 0) {
    const message = (result.stderr || result.stdout || "The layouts did not render.").trim().split("\n").at(-1);
    throw new Error(message || "The layouts did not render.");
  }
  const line = String(result.stdout || "").trim().split("\n").at(-1) || "";
  const parsed = JSON.parse(line);
  return parsed;
}
