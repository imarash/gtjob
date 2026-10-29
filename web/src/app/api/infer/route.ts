import { spawn } from "node:child_process";
import path from "node:path";
import { turnsFromLog, userTurn } from "@/lib/infer-transcript.mjs";
import {
  cursorConnected,
  pidAlive,
  readInferStatus,
  readLoginStatus,
  writeInferStatus,
  writeLoginStatus,
  reopenNotedQuestions,
  writeReply,
} from "@/lib/infer-status.mjs";
import { gtjobRoot } from "@/lib/studio-data";

const SLUG_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$/;

function workerPath(root: string) {
  return path.join(root, "web", "scripts", "infer-worker.mjs");
}

function startWorker(root: string, args: string[]) {
  const child = spawn(process.execPath, [workerPath(root), ...args], {
    cwd: root,
    detached: true,
    stdio: "ignore",
    env: { ...process.env, GTJOB_ROOT: root },
  });
  child.unref();
  return child.pid ?? 0;
}

export async function GET(request: Request) {
  const root = gtjobRoot();
  const slug = new URL(request.url).searchParams.get("run") || "";
  let status = null;
  if (slug && SLUG_RE.test(slug)) {
    status = readInferStatus(root, slug);
    if (status && (status.phase === "running" || status.phase === "starting") && !pidAlive(status.pid)) {
      status = writeInferStatus(root, slug, {
        phase: "error",
        pid: 0,
        message: "The Cursor run stopped before it finished.",
      });
    }
  }
  const login = readLoginStatus(root);
  return Response.json({
    connected: cursorConnected() || login?.phase === "logged-in",
    login,
    status,
  });
}

export async function POST(request: Request) {
  const root = gtjobRoot();
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Expected JSON." }, { status: 400 });
  }
  if (body.command === "login") {
    const current = readLoginStatus(root);
    if (current && (current.phase === "starting" || current.phase === "waiting") && pidAlive(current.pid)) {
      return Response.json({ ok: true, login: current });
    }
    const pid = startWorker(root, ["login"]);
    const login = writeLoginStatus(root, { phase: "starting", pid, message: "Opening Cursor to connect." });
    return Response.json({ ok: true, login });
  }
  const slug = typeof body.run === "string" ? body.run : "";
  if (!SLUG_RE.test(slug)) return Response.json({ error: "Name the run." }, { status: 400 });
  if (!cursorConnected()) {
    return Response.json(
      { connected: false, error: "Connect Cursor to tailor this CV." },
      { status: 409 },
    );
  }
  const mode = body.mode === "reply" ? "reply" : body.mode === "polish" ? "polish" : "tailor";
  const current = readInferStatus(root, slug);
  if (current && (current.phase === "running" || current.phase === "starting") && pidAlive(current.pid)) {
    return Response.json({ ok: true, status: current, already: true });
  }
  const history =
    Array.isArray(current?.turns) && current.turns.length > 0
      ? current.turns
      : Array.isArray(current?.log)
        ? turnsFromLog(current.log)
        : [];
  if (body.command === "message") {
    const text = typeof body.text === "string" ? body.text.trim() : "";
    if (!text || text.length > 8000) return Response.json({ error: "Write a reply first." }, { status: 400 });
    writeReply(root, slug, text);
    reopenNotedQuestions(root, slug, text);
    writeInferStatus(root, slug, {
      phase: "starting",
      mode,
      message: "Cursor is reading your reply.",
      turns: [...history, userTurn(text)],
    });
    const pid = startWorker(root, ["run", slug, mode, "message"]);
    const status = writeInferStatus(root, slug, { pid });
    return Response.json({ ok: true, status });
  }
  const resume = body.resume === "answers" || body.resume === "approved" ? body.resume : "";
  writeInferStatus(root, slug, {
    phase: "starting",
    mode,
    message: "Starting Cursor.",
    log: resume ? current?.log : [],
    turns: resume ? history : [],
  });
  const pid = startWorker(root, ["run", slug, mode, resume]);
  const status = writeInferStatus(root, slug, { pid });
  return Response.json({ ok: true, status });
}
