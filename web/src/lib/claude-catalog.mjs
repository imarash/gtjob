import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { splitFrontmatter } from "./frontmatter.mjs";

const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$/;

/**
 * @typedef {object} CatalogEntry
 * @property {string} id
 * @property {string} name
 * @property {string} description
 * @property {string} argumentHint
 * @property {string} file
 * @property {string} dir
 */

/**
 * @param {string} parent
 * @param {string} child
 */
function staysInside(parent, child) {
  const relative = path.relative(parent, child);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

/**
 * @param {string} claudeDir
 * @returns {{ skills: CatalogEntry[], agents: CatalogEntry[] }}
 */
export function listCatalog(claudeDir) {
  return {
    skills: listSkills(path.join(claudeDir, "skills")),
    agents: listAgents(path.join(claudeDir, "agents")),
  };
}

/**
 * @param {string} skillsDir
 * @returns {CatalogEntry[]}
 */
function listSkills(skillsDir) {
  /** @type {CatalogEntry[]} */
  const found = [];
  let names;
  try {
    names = readdirSync(skillsDir);
  } catch {
    return found;
  }
  for (const name of names) {
    if (!NAME_RE.test(name)) continue;
    const dir = path.join(skillsDir, name);
    const file = path.join(dir, "SKILL.md");
    try {
      if (!statSync(dir).isDirectory() || !statSync(file).isFile()) continue;
    } catch {
      continue;
    }
    found.push(entryFromFile(name, file, dir));
  }
  return found.sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * @param {string} agentsDir
 * @returns {CatalogEntry[]}
 */
function listAgents(agentsDir) {
  /** @type {CatalogEntry[]} */
  const found = [];
  let names;
  try {
    names = readdirSync(agentsDir);
  } catch {
    return found;
  }
  for (const fileName of names) {
    if (!fileName.endsWith(".md")) continue;
    const name = fileName.slice(0, -3);
    if (!NAME_RE.test(name)) continue;
    const file = path.join(agentsDir, fileName);
    try {
      if (!statSync(file).isFile()) continue;
    } catch {
      continue;
    }
    found.push(entryFromFile(name, file, agentsDir));
  }
  return found.sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * @param {string} name
 * @param {string} file
 * @param {string} dir
 * @returns {CatalogEntry}
 */
function entryFromFile(name, file, dir) {
  const text = readFileSync(file, "utf8");
  const { data } = splitFrontmatter(text);
  return {
    id: name,
    name: data.name || name,
    description: data.description || "",
    argumentHint: data["argument-hint"] || "",
    file,
    dir,
  };
}

/**
 * @param {string} file
 * @returns {{ description: string, argumentHint: string, body: string }}
 */
export function readMarkdownDoc(file) {
  const { data, body } = splitFrontmatter(readFileSync(file, "utf8"));
  return {
    description: data.description || "",
    argumentHint: data["argument-hint"] || "",
    body,
  };
}

/**
 * Relative file names under a skill directory. Symlinks are skipped.
 * @param {string} skillDir
 * @returns {string[]}
 */
export function listSkillFiles(skillDir) {
  /** @type {string[]} */
  const found = [];
  walk(skillDir, "", found);
  return found.sort();
}

/**
 * @param {string} dir
 * @param {string} prefix
 * @param {string[]} found
 */
function walk(dir, prefix, found) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (entry.name.startsWith(".") || entry.isSymbolicLink()) continue;
    const rel = prefix ? path.join(prefix, entry.name) : entry.name;
    if (entry.isDirectory()) walk(path.join(dir, entry.name), rel, found);
    else if (entry.isFile()) found.push(rel);
  }
}

/**
 * A reference markdown file inside skills/<name>/references/.
 * @param {string} skillDir
 * @param {string} doc basename without a path
 * @returns {string | null}
 */
export function referenceFile(skillDir, doc) {
  if (!doc.endsWith(".md") || doc.includes("/") || doc.includes("\\") || doc.includes("\0")) return null;
  const file = path.resolve(skillDir, "references", doc);
  const references = path.resolve(skillDir, "references");
  if (!staysInside(references, file)) return null;
  try {
    if (!statSync(file).isFile()) return null;
  } catch {
    return null;
  }
  return file;
}

/**
 * @param {string} dir
 * @returns {string[]}
 */
export function listDirFiles(dir) {
  /** @type {string[]} */
  const names = [];
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return names;
  }
  for (const entry of entries) {
    if (entry.name.startsWith(".") || entry.isSymbolicLink() || !entry.isFile()) continue;
    if (entry.name.includes("/") || entry.name.includes("\\")) continue;
    names.push(entry.name);
  }
  return names.sort();
}

/**
 * @param {string} outDir
 * @returns {string[]}
 */
export function runsWithReply(outDir) {
  /** @type {string[]} */
  const slugs = [];
  let entries;
  try {
    entries = readdirSync(outDir, { withFileTypes: true });
  } catch {
    return slugs;
  }
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.isSymbolicLink() || !NAME_RE.test(entry.name)) continue;
    try {
      if (statSync(path.join(outDir, entry.name, "reply.md")).isFile()) slugs.push(entry.name);
    } catch {
      /* no reply */
    }
  }
  return slugs.sort();
}
