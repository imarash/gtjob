import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * Labels under `states:` in career-ops templates/states.yml.
 * The file is a flat list of maps; this reads `label:` lines only.
 * @param {string} yaml
 * @returns {string[]}
 */
export function labelsFromStatesYaml(yaml) {
  /** @type {string[]} */
  const labels = [];
  let inStates = false;
  for (const line of String(yaml).split("\n")) {
    if (/^states:\s*$/.test(line)) {
      inStates = true;
      continue;
    }
    if (inStates && /^[^\s#]/.test(line)) break;
    if (!inStates) continue;
    const match = line.match(/^\s+label:\s*(.+?)\s*$/);
    if (!match) continue;
    const label = match[1].replace(/^["']|["']$/g, "");
    if (label) labels.push(label);
  }
  return labels;
}

/** @param {string} careerOpsRoot */
export function readStateLabels(careerOpsRoot) {
  const filePath = path.join(careerOpsRoot, "templates", "states.yml");
  let text;
  try {
    text = readFileSync(filePath, "utf8");
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error ? error.code : "";
    const message = error instanceof Error ? error.message : String(error);
    return {
      ok: false,
      missing: code === "ENOENT",
      labels: [],
      path: filePath,
      error: code === "ENOENT" ? "templates/states.yml is missing" : message,
    };
  }
  const labels = labelsFromStatesYaml(text);
  if (labels.length === 0) {
    return {
      ok: false,
      missing: false,
      labels: [],
      path: filePath,
      error: "templates/states.yml has no state labels",
    };
  }
  return { ok: true, missing: false, labels, path: filePath, error: "" };
}
