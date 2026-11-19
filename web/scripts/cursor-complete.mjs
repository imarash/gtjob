/**
 * One JSON completion through the Cursor SDK.
 * The agent has no tools and an in-memory tree, so it cannot read or write this repo.
 * Stdin is the request. Stdout is one JSON line: {ok, data, usage} or {ok:false, id, message}.
 */
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const TIMEOUT_MS = 180_000;

/**
 * @param {unknown} value
 * @returns {string}
 */
export function textOf(value) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(textOf).filter(Boolean).join("\n");
  if (value && typeof value === "object") {
    const record = /** @type {Record<string, unknown>} */ (value);
    if (typeof record.text === "string") return record.text;
    if (record.type === "image") return "[image omitted]";
    if ("content" in record) return textOf(record.content);
  }
  return "";
}

/**
 * @param {Record<string, unknown>} payload
 */
export function buildPrompt(payload) {
  const history = Array.isArray(payload.history) ? payload.history : [];
  const turns = history
    .map((turn) => {
      const record = turn && typeof turn === "object" ? /** @type {Record<string, unknown>} */ (turn) : {};
      const role = typeof record.role === "string" ? record.role : "user";
      const text = textOf(record.content ?? record);
      return text ? `${role}: ${text}` : "";
    })
    .filter(Boolean)
    .join("\n\n");
  return [
    "Reply with one JSON object that matches this schema. No prose and no code fences.",
    `Schema:\n${JSON.stringify(payload.schema ?? {})}`,
    textOf(payload.system),
    turns,
    textOf(payload.blocks),
  ]
    .filter(Boolean)
    .join("\n\n");
}

/**
 * @param {string} text
 */
export function extractJson(text) {
  const trimmed = String(text || "").trim();
  const fenced = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/);
  const body = fenced ? fenced[1].trim() : trimmed;
  const parsed = parseObject(body) ?? parseObject(sliceObject(body));
  if (!parsed) throw new Error("the model reply is not a JSON object");
  return parsed;
}

/**
 * @param {string} text
 */
function sliceObject(text) {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  return start >= 0 && end > start ? text.slice(start, end + 1) : "";
}

/**
 * @param {string} text
 */
function parseObject(text) {
  if (!text) return null;
  try {
    const data = JSON.parse(text);
    return data && typeof data === "object" && !Array.isArray(data) ? data : null;
  } catch {
    return null;
  }
}

/**
 * @param {string} message
 */
export function classifyCursorError(message) {
  const text = String(message || "");
  if (/usage limit|rate limit|quota|429/i.test(text)) return "E_CURSOR_QUOTA";
  if (/api key|unauthenticated|not logged|authentication|sign in/i.test(text)) return "E_CURSOR_AUTH";
  return "E_CURSOR";
}

/**
 * @param {string} stateDir
 * @param {string} model
 */
export function agentShape(stateDir, model) {
  return {
    model: { id: model },
    tools: [],
    name: "gtjob",
    local: {
      cwd: stateDir,
      settingSources: [],
      autoReview: false,
    },
  };
}

/**
 * @param {Record<string, unknown>} payload
 */
function reply(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

/**
 * @param {string} id
 * @param {string} message
 */
function fail(id, message) {
  const hint =
    id === "E_CURSOR_AUTH"
      ? "export CURSOR_API_KEY=... or connect Cursor from the toolbox"
      : id === "E_CURSOR_QUOTA"
        ? "Cursor quota is exhausted; wait, or set ANTHROPIC_API_KEY and rerun"
        : "rerun; finished stages are cached";
  reply({ ok: false, id, message, hint });
}

async function main() {
  let payload;
  try {
    payload = JSON.parse(readFileSync(0, "utf8"));
  } catch {
    fail("E_CURSOR", "the Cursor request was not JSON");
    return;
  }
  const model = typeof payload.model === "string" && payload.model.trim() ? payload.model.trim() : "composer-2.5";
  const stateDir = mkdtempSync(path.join(tmpdir(), "gtjob-cursor-"));
  let agent;
  try {
    const { Agent, tempFs } = await import("@cursor/sdk");
    const options = agentShape(stateDir, model);
    options.local.fs = tempFs();
    agent = await Agent.create(options);
    const run = await agent.send(buildPrompt(payload));
    const result = await Promise.race([
      run.wait(),
      new Promise((_, reject) => {
        setTimeout(() => {
          void run.cancel().catch(() => undefined);
          reject(new Error("Cursor SDK request timed out."));
        }, TIMEOUT_MS);
      }),
    ]);
    if (!result || result.status !== "finished" || !String(result.result || "").trim()) {
      const message = result?.error?.message || (result?.status === "error" ? "Cursor SDK request failed." : "Cursor SDK returned empty output.");
      fail(classifyCursorError(message), message);
      return;
    }
    let data;
    try {
      data = extractJson(String(result.result));
    } catch (error) {
      fail("E_MODEL_JSON", error instanceof Error ? error.message : "the model reply is not a JSON object");
      return;
    }
    const usage = result.usage || {};
    reply({
      ok: true,
      data,
      usage: {
        input_tokens: Number(usage.inputTokens || 0),
        output_tokens: Number(usage.outputTokens || 0),
        cache_read_tokens: Number(usage.cacheReadTokens || 0),
        cache_write_tokens: Number(usage.cacheWriteTokens || 0),
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Cursor SDK request failed.";
    fail(classifyCursorError(message), message);
  } finally {
    await Promise.race([
      agent ? agent[Symbol.asyncDispose]().catch(() => undefined) : Promise.resolve(),
      new Promise((resolve) => setTimeout(resolve, 2000)),
    ]);
    rmSync(stateDir, { recursive: true, force: true });
    process.exit(0);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
