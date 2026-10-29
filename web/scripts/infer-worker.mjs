import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { Agent, Cursor, CursorAgentError, JsonlLocalAgentStore } from "@cursor/sdk";
import { inferPrompt } from "../src/lib/infer-prompt.mjs";
import { stopAtCheckpoint } from "../src/lib/infer-stop.mjs";
import { readInferStatus, writeInferStatus, writeLoginStatus } from "../src/lib/infer-status.mjs";
import { foldEvent, turnsFromLog } from "../src/lib/infer-transcript.mjs";

const root = process.env.GTJOB_ROOT || path.resolve(import.meta.dirname, "../..");
const model = { id: "composer-2.5" };

function store() {
  return new JsonlLocalAgentStore(path.join(root, ".studio", "cursor-agents"));
}

function local() {
  return {
    cwd: root,
    settingSources: ["project"],
    store: store(),
  };
}

/**
 * @param {string} slug
 */
function readStage(slug) {
  try {
    const raw = JSON.parse(readFileSync(path.join(root, "out", slug, "state.json"), "utf8"));
    return String(raw.stage || "");
  } catch {
    return "";
  }
}

/**
 * @param {unknown} error
 */
function errorMessage(error) {
  if (error instanceof CursorAgentError) return error.message || "Cursor did not start.";
  if (error instanceof Error) return error.message;
  return "Cursor did not start.";
}

async function login() {
  writeLoginStatus(root, { phase: "starting", message: "Opening Cursor to connect.", pid: process.pid });
  try {
    await Cursor.auth.login({
      openBrowser: true,
      apiKeyName: "gtjob-studio",
      onLoginUrl(url) {
        writeLoginStatus(root, {
          phase: "waiting",
          url: String(url || ""),
          message: "Finish connecting Cursor in the browser.",
          pid: process.pid,
        });
      },
    });
    writeLoginStatus(root, { phase: "logged-in", url: "", message: "Cursor is connected.", pid: 0 });
  } catch (error) {
    writeLoginStatus(root, { phase: "error", message: errorMessage(error), pid: 0 });
  }
}

/**
 * @param {string} slug
 * @param {"tailor" | "reply" | "polish"} mode
 * @param {"answers" | "approved" | "message" | ""} resume
 */
async function run(slug, mode, resume) {
  const existing = readInferStatus(root, slug) || {};
  let turns = Array.isArray(existing.turns) ? existing.turns : [];
  if (turns.length === 0 && Array.isArray(existing.log)) turns = turnsFromLog(existing.log);
  let dirty = false;
  /** @type {ReturnType<typeof setTimeout> | null} */
  let timer = null;
  const flush = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    if (!dirty) return;
    dirty = false;
    const last = [...turns].reverse().find((turn) => turn.role === "assistant" && turn.text);
    const message = last ? String(last.text).replace(/\s+/g, " ").trim().slice(0, 160) : "Cursor is working.";
    writeInferStatus(root, slug, { phase: "running", message, turns, pid: process.pid });
  };
  const schedule = () => {
    dirty = true;
    if (timer) return;
    timer = setTimeout(flush, 250);
  };

  writeInferStatus(root, slug, {
    phase: "starting",
    mode,
    message: "Starting Cursor.",
    turns,
    pid: process.pid,
  });

  const auth = await Cursor.auth.status().catch(() => ({ status: "logged-out" }));
  if (!process.env.CURSOR_API_KEY && auth.status !== "logged-in") {
    writeInferStatus(root, slug, {
      phase: "error",
      message: "Cursor is not connected. Connect it on this page, or set CURSOR_API_KEY and restart Studio.",
      pid: 0,
    });
    return;
  }

  /** @type {import("@cursor/sdk").SDKAgent | undefined} */
  let agent;
  try {
    const previous = resume ? readPreviousAgent(slug) : "";
    agent = previous
      ? await Agent.resume(previous, { model, local: local() })
      : await Agent.create({
          model,
          local: local(),
          name: `gtjob ${slug}`,
        });
    writeInferStatus(root, slug, {
      phase: "running",
      agentId: agent.agentId,
      message: mode === "polish" ? "Cursor is polishing this CV." : "Cursor is tailoring this run.",
    });
    const runHandle = await agent.send(inferPrompt({ slug, mode, resume }), { model });
    writeInferStatus(root, slug, { runId: runHandle.id });
    const startStage = readStage(slug);
    let seenOtherStage = false;
    for await (const event of runHandle.stream()) {
      turns = foldEvent(turns, event);
      schedule();
      const decision = stopAtCheckpoint(readStage(slug), startStage, resume, seenOtherStage);
      seenOtherStage = decision.seenOtherStage;
      if (decision.stop) {
        if (runHandle.supports("cancel")) await runHandle.cancel();
        break;
      }
    }
    flush();
    const result = await runHandle.wait();
    if (mode === "polish") {
      const ready = polishLayoutsReady(slug);
      const phase = ready ? "finished" : "error";
      const message = ready
        ? "The polished CV is ready."
        : result.status === "error"
          ? result.error?.message || "Cursor stopped before the PDF was ready."
          : "Cursor stopped before modern, classic, and sidebar were ready.";
      writeInferStatus(root, slug, { phase, stage: "", message, pid: 0 });
      return;
    }
    const stage = readStage(slug);
    const reported = existsSync(path.join(root, "out", slug, "report.md"));
    let phase = "finished";
    let message = reported ? "The tailored CV is ready." : "Cursor stopped.";
    if (stage === "awaiting_answers") {
      phase = "awaiting_answers";
      message = "A few questions are waiting.";
    } else if (stage === "awaiting_approval") {
      phase = "awaiting_approval";
      message = "The draft is ready for approval.";
    } else if (result.status === "error") {
      phase = "error";
      message = result.error?.message || "Cursor stopped before the PDF was ready.";
    } else if (!reported && stage) {
      phase = "error";
      message = `Cursor stopped while this run was still at ${stage}.`;
    }
    writeInferStatus(root, slug, { phase, stage, message, pid: 0 });
  } catch (error) {
    writeInferStatus(root, slug, { phase: "error", message: errorMessage(error), pid: 0 });
  } finally {
    if (timer) clearTimeout(timer);
    if (agent) await agent[Symbol.asyncDispose]();
  }
}

/**
 * @param {string} slug
 */
/**
 * @param {string} slug
 */
function polishLayoutsReady(slug) {
  try {
    const names = readdirSync(path.join(root, "out", slug));
    return ["modern", "classic", "sidebar"].every((layout) =>
      names.some((name) => name.toLowerCase().endsWith(`-${layout}.pdf`)),
    );
  } catch {
    return false;
  }
}

/**
 * @param {string} slug
 */
function readPreviousAgent(slug) {
  try {
    const raw = JSON.parse(readFileSync(path.join(root, ".studio", "infer", `${slug}.json`), "utf8"));
    return typeof raw.agentId === "string" ? raw.agentId : "";
  } catch {
    return "";
  }
}

const [command, slug, modeArg, resumeArg] = process.argv.slice(2);
if (command === "login") {
  await login();
} else if (command === "run" && slug) {
  const mode = modeArg === "reply" ? "reply" : modeArg === "polish" ? "polish" : "tailor";
  const resume = resumeArg === "answers" || resumeArg === "approved" || resumeArg === "message" ? resumeArg : "";
  await run(slug, mode, resume);
} else {
  console.error("usage: infer-worker.mjs login | run <slug> <tailor|reply|polish> [answers|approved|message]");
  process.exit(2);
}
