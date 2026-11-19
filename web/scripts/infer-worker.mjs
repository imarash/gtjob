import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { Cursor, CursorAgentError } from "@cursor/sdk";
import { continueOutcome, formatRunError, readInferStatus, writeInferStatus, writeLoginStatus } from "../src/lib/infer-status.mjs";

const repo = process.env.GTJOB_ROOT || path.resolve(import.meta.dirname, "../..");
const root = process.env.GTJOB_HOME?.trim() ? path.resolve(process.env.GTJOB_HOME.trim()) : repo;

/**
 * @param {unknown} error
 */
function errorMessage(error) {
  if (error instanceof CursorAgentError) return error.message || "Cursor did not start.";
  if (error instanceof Error) return error.message;
  return "The run did not start.";
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
 * @param {string[]} args
 */
function gtjob(args) {
  const result = spawnSync("uv", ["run", "gtjob", ...args], {
    cwd: repo,
    encoding: "utf8",
    maxBuffer: 8_000_000,
    env: { ...process.env, GTJOB_ROOT: repo, GTJOB_HOST: process.env.GTJOB_HOST || "cursor" },
  });
  const stderr = `${result.stderr || ""}\n${result.error ? result.error.message : ""}`.trim();
  return { code: result.status ?? 1, stderr };
}

/**
 * @param {string} slug
 */
function noteText(slug) {
  try {
    return readFileSync(path.join(root, ".studio", "infer", `${slug}.reply.txt`), "utf8").trim();
  } catch {
    return "";
  }
}

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
 * @param {"tailor" | "reply" | "polish"} mode
 * @param {"answers" | "approved" | "message" | ""} resume
 */
function run(slug, mode, resume) {
  const existing = readInferStatus(root, slug) || {};
  const turns = Array.isArray(existing.turns) ? existing.turns : [];
  writeInferStatus(root, slug, {
    phase: "running",
    mode,
    agentId: "",
    message:
      mode === "polish"
        ? "Polishing this CV. Stay on this page — this takes a few minutes."
        : "Tailoring this CV. Stay on this page — this takes a few minutes.",
    turns,
    pid: process.pid,
  });

  /** @type {string[]} */
  let args;
  if (mode === "polish") {
    args = ["polish", "fill", slug];
    if (resume === "message") {
      const note = noteText(slug);
      if (note) args.push("--text", note);
    }
  } else {
    args = ["continue", slug];
    if (resume === "message") {
      const note = noteText(slug);
      if (note) args.push("--text", note);
    }
  }

  let result = gtjob(args);
  if (mode === "reply" && result.code === 0) {
    const reply = gtjob(["reply", slug]);
    if (reply.code !== 0) result = reply;
  }

  if (mode === "polish") {
    const ready = polishLayoutsReady(slug);
    writeInferStatus(root, slug, {
      phase: ready ? "finished" : "error",
      stage: "",
      agentId: "",
      pid: 0,
      message: ready
        ? "The polished CV is ready."
        : formatRunError(result.stderr) || "The polish run stopped before modern, classic, and sidebar were ready.",
    });
    return;
  }

  const stage = readStage(slug);
  const outcome = continueOutcome(result.code, stage, result.stderr);
  writeInferStatus(root, slug, { phase: outcome.phase, stage, agentId: "", message: outcome.message, pid: 0 });
}

const [command, slug, modeArg, resumeArg] = process.argv.slice(2);
if (command === "login") {
  await login();
} else if (command === "run" && slug) {
  const mode = modeArg === "reply" ? "reply" : modeArg === "polish" ? "polish" : "tailor";
  const resume = resumeArg === "answers" || resumeArg === "approved" || resumeArg === "message" ? resumeArg : "";
  run(slug, mode, resume);
} else {
  console.error("usage: infer-worker.mjs login | run <slug> <tailor|reply|polish> [answers|approved|message]");
  process.exit(2);
}
