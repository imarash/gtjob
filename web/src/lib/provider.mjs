import { mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import path from "node:path";

/** Studio writing providers. A missing choice means Cursor. `auto` is an explicit Automatic choice: Anthropic when a key is set, otherwise Cursor. */
export const PROVIDERS = ["auto", "cursor", "anthropic"];

/**
 * @param {string} root
 */
export function providerPath(root) {
  return path.join(root, ".studio", "provider.json");
}

/**
 * @param {unknown} value
 * @returns {"auto" | "cursor" | "anthropic" | null}
 */
export function parseProvider(value) {
  const name = String(value ?? "").trim().toLowerCase();
  if (name === "auto" || name === "cursor" || name === "anthropic") return name;
  return null;
}

/**
 * @param {string} root
 * @returns {"auto" | "cursor" | "anthropic"}
 */
export function readProvider(root) {
  try {
    const raw = JSON.parse(readFileSync(providerPath(root), "utf8"));
    return parseProvider(raw?.provider) || "cursor";
  } catch {
    return "cursor";
  }
}

/**
 * @param {string} root
 * @param {unknown} value
 * @returns {"auto" | "cursor" | "anthropic"}
 */
export function writeProvider(root, value) {
  const provider = parseProvider(value);
  if (!provider) throw new Error("Choose Cursor, Anthropic, or Automatic.");
  const file = providerPath(root);
  mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp`;
  writeFileSync(tmp, `${JSON.stringify({ provider }, null, 2)}\n`);
  renameSync(tmp, file);
  return provider;
}

export function anthropicReady() {
  return Boolean(process.env.ANTHROPIC_API_KEY && String(process.env.ANTHROPIC_API_KEY).trim());
}

/**
 * The env passed to a writing process. Automatic leaves the shell's choice alone.
 * @param {"auto" | "cursor" | "anthropic"} provider
 * @param {NodeJS.ProcessEnv} [base]
 */
export function providerEnv(provider, base = process.env) {
  const env = { ...base };
  if (provider === "cursor" || provider === "anthropic") env.GTJOB_PROVIDER = provider;
  return env;
}

export { providerStatus } from "./provider-hint.mjs";
