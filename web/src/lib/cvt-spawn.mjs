import { spawnSync } from "node:child_process";
import path from "node:path";

/**
 * The last JSON object line cvt prints in --json mode.
 * @param {string} stdout
 * @returns {Record<string, unknown> | null}
 */
export function parseCvtStdout(stdout) {
  const lines = String(stdout)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    if (!lines[index].startsWith("{")) continue;
    try {
      const parsed = JSON.parse(lines[index]);
      if (parsed && typeof parsed === "object") return parsed;
    } catch {
      /* an earlier brace line */
    }
  }
  return null;
}

/**
 * @param {string} root
 * @param {string} script
 * @param {string[]} args
 * @param {number} timeoutMs
 */
export function spawnTool(root, script, args, timeoutMs) {
  const result = spawnSync("uv", ["run", script, ...args], {
    cwd: root,
    encoding: "utf8",
    timeout: timeoutMs,
    maxBuffer: 4_000_000,
    env: { ...process.env, UV_CACHE_DIR: path.join(root, ".cache", "uv") },
  });
  if (result.error && "code" in result.error && result.error.code === "ENOENT") {
    return { ok: false, error: "uv is not on PATH.", envelope: null, stderr: "" };
  }
  if (result.error) {
    const message = result.error.message || "The command did not finish.";
    return { ok: false, error: message, envelope: null, stderr: result.stderr || "" };
  }
  const envelope = parseCvtStdout(result.stdout || "");
  return {
    ok: true,
    error: "",
    envelope,
    stderr: (result.stderr || "").slice(0, 8_000),
    status: result.status,
    stdout: envelope ? "" : (result.stdout || "").slice(0, 80_000),
  };
}
