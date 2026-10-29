import path from "node:path";

export const TEMPLATES = ["modern", "classic", "sidebar"];
const SLUG_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$/;
const SELECT_RE = /^q-\d+=(?:skip|[a-z0-9_]+(?:,[a-z0-9_]+)*)$/;
const ATT_RE = /^att-\d{3,}$/;
const JD_TEXT_MAX = 100_000;

/**
 * @param {string} root
 */
export function cvtScript(root) {
  return path.join(root, ".claude", "skills", "tailoring-cvs", "scripts", "cvt.py");
}

/**
 * @param {string} root
 */
export function polishScript(root) {
  return path.join(root, ".claude", "skills", "tailoring-cvs", "scripts", "polish_render.py");
}

/**
 * @param {string} value
 * @param {string} label
 */
function slug(value, label) {
  if (value === "latest") return value;
  if (!SLUG_RE.test(value)) throw new Error(`${label} is not a run slug.`);
  return value;
}

/**
 * A file name chosen from a directory listing. The caller joins it.
 * @param {string} name
 */
function baseName(name) {
  if (!name || name !== path.basename(name) || name.includes("\0") || name.startsWith(".")) {
    throw new Error("Pick a file by its name in CVs/ or JDs/.");
  }
  return name;
}

/**
 * Argv after `uv run <script>`. Always a list. Never a shell string.
 * @param {Record<string, unknown>} request
 * @param {{ gtjobRoot: string }} paths
 * @returns {{ script: string, args: string[], timeoutMs: number }}
 */
export function buildToolArgv(request, paths) {
  const command = String(request.command || "");
  if (command === "polish-extract") {
    const cv = path.join(paths.gtjobRoot, "CVs", baseName(String(request.cv || "")));
    return { script: polishScript(paths.gtjobRoot), args: ["extract", cv], timeoutMs: 60_000 };
  }
  const args = cvtArgs(request, paths.gtjobRoot);
  const slow = command === "init" || command === "ingest" || command === "render" || command === "fit" || command === "validate";
  return { script: cvtScript(paths.gtjobRoot), args, timeoutMs: slow ? 120_000 : 30_000 };
}

/**
 * @param {Record<string, unknown>} request
 * @param {string} root
 * @returns {string[]}
 */
function cvtArgs(request, root) {
  const command = String(request.command || "");
  /** @type {string[]} */
  let args;
  switch (command) {
    case "status":
      args = ["status"];
      if (request.run) args.push(slug(String(request.run), "Run"));
      if (request.all === true) args.push("--all");
      break;
    case "profile-show":
      args = personOrRun("profile-show", request);
      break;
    case "attest":
      args = attestArgs(request);
      break;
    case "questions":
      args = ["questions", slug(String(request.run || ""), "Run"), "--format", "json"];
      break;
    case "answers-apply":
      args = answersArgs(request);
      break;
    case "diff":
      args = ["diff", slug(String(request.run || ""), "Run")];
      break;
    case "approve":
      args = ["approve", slug(String(request.run || ""), "Run")];
      if (request.all === true) args.push("--all");
      break;
    case "render":
      args = ["render", slug(String(request.run || ""), "Run")];
      if (request.template) args.push("--template", template(String(request.template)));
      break;
    case "fit":
    case "validate":
    case "report":
    case "ingest":
      args = [command, slug(String(request.run || ""), "Run")];
      break;
    case "profile-cache":
      args = ["profile-cache", slug(String(request.run || ""), "Run"), "--lookup"];
      break;
    case "brief":
      if (request.stage !== "jd") throw new Error("Studio only reuses a job analysis it already has.");
      args = ["brief", "jd", slug(String(request.run || ""), "Run")];
      break;
    case "jd-check":
      args = ["jd-check", slug(String(request.run || ""), "Run")];
      break;
    case "init":
      args = initArgs(request, root);
      break;
    default:
      throw new Error("That command is not available from Studio.");
  }
  if (command === "answers-apply" || command === "attest" || command === "profile-show") args.push("--all");
  args.push("--json");
  return args;
}

/**
 * @param {string} command
 * @param {Record<string, unknown>} request
 */
function personOrRun(command, request) {
  if (request.person) return [command, "--person", slug(String(request.person), "Person")];
  return [command, slug(String(request.run || "latest"), "Run")];
}

/**
 * @param {Record<string, unknown>} request
 */
function attestArgs(request) {
  const action = String(request.action || "");
  if (action !== "list" && action !== "show" && action !== "revoke" && action !== "activate") {
    throw new Error("Attest action must be list, show, revoke, or activate.");
  }
  /** @type {string[]} */
  const args = ["attest", action];
  if (action !== "list") {
    const id = String(request.id || "");
    if (!ATT_RE.test(id)) throw new Error("Attestation id looks like att-001.");
    args.push(id);
  }
  if (request.person) args.push("--person", slug(String(request.person), "Person"));
  else if (request.run) args.push(slug(String(request.run), "Run"));
  return args;
}

/**
 * @param {Record<string, unknown>} request
 */
function answersArgs(request) {
  const run = slug(String(request.run || ""), "Run");
  const mode = request.mode === "commit" ? "--commit" : request.mode === "dry-run" ? "--dry-run" : "";
  if (!mode) throw new Error("Preview the answers before applying them.");
  if (request.auto === true) return ["answers-apply", run, "--auto", mode];
  const select = Array.isArray(request.select) ? request.select.map(String) : [];
  if (select.length === 0 || select.length > 16) throw new Error("Choose at least one question, or use the defaults.");
  for (const item of select) {
    if (!SELECT_RE.test(item)) throw new Error("An answer was not a question choice.");
  }
  const rest = request.defaultRest === false ? [] : ["--default-rest"];
  return ["answers-apply", run, ...select.flatMap((item) => ["--select", item]), ...rest, mode];
}

/**
 * @param {string} value
 */
function template(value) {
  if (!TEMPLATES.includes(value)) throw new Error("Template is modern, classic, or sidebar.");
  return value;
}

/**
 * @param {Record<string, unknown>} request
 * @param {string} root
 */
function initArgs(request, root) {
  const cvName = baseName(String(request.cv || ""));
  const cv = path.join(root, "CVs", cvName);
  /** @type {string[]} */
  const args = ["init", "--cv", cv, "--host", "cursor"];
  const jdFile = request.jd ? baseName(String(request.jd)) : "";
  const jdText = typeof request.jdText === "string" ? request.jdText : "";
  if (jdFile && jdText.trim()) throw new Error("Pass a JD file or pasted text, not both.");
  if (jdFile) args.push("--jd", path.join(root, "JDs", jdFile));
  else if (jdText.trim()) {
    if (jdText.includes("\0") || jdText.length > JD_TEXT_MAX) throw new Error("That job text is empty or too long.");
    args.push("--jd-text", jdText);
  } else throw new Error("Add a job description file or paste the job text.");
  if (request.template) args.push("--template", template(String(request.template)));
  return args;
}
