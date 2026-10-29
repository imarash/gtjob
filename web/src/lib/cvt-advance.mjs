import { buildToolArgv } from "./cvt-args.mjs";
import { spawnTool } from "./cvt-spawn.mjs";
import { describeStage } from "./stage-copy.mjs";

/**
 * @param {string} root
 * @param {Record<string, unknown>} request
 */
function call(root, request) {
  const built = buildToolArgv(request, { gtjobRoot: root });
  return spawnTool(root, built.script, built.args, built.timeoutMs);
}

/**
 * @param {Record<string, unknown> | null | undefined} envelope
 * @param {string} key
 */
function field(envelope, key) {
  const data = envelope && typeof envelope.data === "object" && envelope.data ? envelope.data : null;
  if (!data || !(key in data)) return undefined;
  return /** @type {Record<string, unknown>} */ (data)[key];
}

function failed(result, stage) {
  const fromEnvelope =
    result.envelope && typeof result.envelope.error === "object" && result.envelope.error
      ? /** @type {{ message?: string }} */ (result.envelope.error).message
      : "";
  return { ok: false, stage, blocked: "error", message: fromEnvelope || result.error || "That step failed." };
}

/**
 * Walk the deterministic steps. Stop when the next file has to be written by Claude.
 * @param {string} root
 * @param {string} slug
 */
export function advanceRun(root, slug) {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const status = call(root, { command: "status", run: slug });
    if (!status.ok || !status.envelope) return failed(status, "");
    const stage = String(status.envelope.stage || "");
    if (!stage) return failed(status, stage);

    if (stage === "initialized") {
      const ingest = call(root, { command: "ingest", run: slug });
      if (!ingest.envelope || ingest.envelope.ok !== true) return failed(ingest, stage);
      continue;
    }
    if (stage === "ingested") {
      const lookup = call(root, { command: "profile-cache", run: slug });
      if (!lookup.ok || !lookup.envelope || lookup.envelope.ok !== true) return failed(lookup, stage);
      if (field(lookup.envelope, "hit") !== true) {
        const described = describeStage("ingested");
        return { ok: true, stage, blocked: described.blocked, message: described.detail };
      }
      continue;
    }
    if (stage === "profiled") {
      const brief = call(root, { command: "brief", stage: "jd", run: slug });
      if (!brief.ok || !brief.envelope || brief.envelope.ok !== true) return failed(brief, stage);
      if (field(brief.envelope, "cache_hit") !== true) {
        const described = describeStage("profiled");
        return { ok: true, stage, blocked: described.blocked, message: described.detail };
      }
      const check = call(root, { command: "jd-check", run: slug });
      if (!check.envelope || check.envelope.ok !== true) return failed(check, stage);
      continue;
    }
    const described = describeStage(stage);
    return { ok: true, stage, blocked: described.blocked, message: described.detail };
  }
  return { ok: true, stage: "", blocked: "wait", message: "Stopped after several steps." };
}
