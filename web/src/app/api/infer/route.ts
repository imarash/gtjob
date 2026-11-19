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
import { anthropicReady, parseProvider, providerEnv, readProvider, writeProvider } from "@/lib/provider.mjs";
import { readRunProgress } from "@/lib/run-label.mjs";
import { gtjobRoot, workspaceRoot } from "@/lib/studio-data";

const SLUG_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$/;

function workerPath(root: string) {
  return path.join(root, "web", "scripts", "infer-worker.mjs");
}

function startWorker(root: string, args: string[], provider: "auto" | "cursor" | "anthropic") {
  const child = spawn(process.execPath, [workerPath(root), ...args], {
    cwd: root,
    detached: true,
    stdio: "ignore",
    env: { ...providerEnv(provider), GTJOB_ROOT: root },
  });
  child.unref();
  return child.pid ?? 0;
}

export async function GET(request: Request) {
  const root = workspaceRoot();
  const slug = new URL(request.url).searchParams.get("run") || "";
  let status = null;
  if (slug && SLUG_RE.test(slug)) {
    status = readInferStatus(root, slug);
    if (status && (status.phase === "running" || status.phase === "starting") && !pidAlive(status.pid)) {
      status = writeInferStatus(root, slug, {
        phase: "error",
        pid: 0,
        message: "The run stopped before it finished.",
      });
    }
  }
  const login = readLoginStatus(root);
  const progress = slug && SLUG_RE.test(slug) ? readRunProgress(path.join(root, "out"), slug) : null;
  return Response.json({
    connected: true,
    cursor: cursorConnected() || login?.phase === "logged-in",
    anthropic: anthropicReady(),
    provider: readProvider(root),
    login,
    status,
    progress,
  });
}

export async function POST(request: Request) {
  const root = workspaceRoot();
  const repo = gtjobRoot();
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
    const pid = startWorker(repo, ["login"], "auto");
    const login = writeLoginStatus(root, { phase: "starting", pid, message: "Opening Cursor to connect." });
    return Response.json({ ok: true, login });
  }
  if (body.command === "provider") {
    const provider = parseProvider(body.provider);
    if (!provider) return Response.json({ error: "Choose Cursor, Anthropic, or Automatic." }, { status: 400 });
    return Response.json({ ok: true, provider: writeProvider(root, provider) });
  }
  const provider = readProvider(root);
  if (provider === "anthropic" && !anthropicReady()) {
    return Response.json(
      { error: "Anthropic needs ANTHROPIC_API_KEY in the environment that starts Studio. Choose Cursor to use the connected account." },
      { status: 400 },
    );
  }
  if (provider === "cursor" && !process.env.GTJOB_FAKE_LLM && !cursorConnected()) {
    return Response.json({ error: "Connect Cursor before using it.", connected: false }, { status: 409 });
  }
  const slug = typeof body.run === "string" ? body.run : "";
  if (!SLUG_RE.test(slug)) return Response.json({ error: "Name the run." }, { status: 400 });
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
      message: "Reading your reply.",
      turns: [...history, userTurn(text)],
    });
    const pid = startWorker(repo, ["run", slug, mode, "message"], provider);
    const status = writeInferStatus(root, slug, { pid });
    return Response.json({ ok: true, status });
  }
  const resume = body.resume === "answers" || body.resume === "approved" ? body.resume : "";
  writeInferStatus(root, slug, {
    phase: "starting",
    mode,
    message: "Starting.",
    log: resume ? current?.log : [],
    turns: resume ? history : [],
  });
  const pid = startWorker(repo, ["run", slug, mode, resume], provider);
  const status = writeInferStatus(root, slug, { pid });
  return Response.json({ ok: true, status });
}
