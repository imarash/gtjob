import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { applyFailure, buildAnswerRequest, controlKind, initialPicked, pendingReply } from "../src/lib/answer-select.mjs";
import { inferPrompt } from "../src/lib/infer-prompt.mjs";
import { stopAtCheckpoint } from "../src/lib/infer-stop.mjs";
import { continueOutcome, formatRunError, readInferStatus, readLoginStatus, reopenNotedQuestions, writeInferStatus, writeLoginStatus, writeReply } from "../src/lib/infer-status.mjs";
import { foldEvent, toolLabel } from "../src/lib/infer-transcript.mjs";
import { polishSlug } from "../src/lib/polish-run.mjs";
import { parseProvider, providerEnv, readProvider, writeProvider } from "../src/lib/provider.mjs";
import { providerStatus } from "../src/lib/provider-hint.mjs";
import { listPolishRuns, previewFile } from "../src/lib/runs.mjs";

test("a check failure keeps the violation lines", () => {
  const text = [
    "cvt: error[E_TOOL_CHECK]: stop: show these violations to the user",
    "  hint: state saved; resume with: gtjob continue demo",
    "  - t-skl-2: skill t-skl-2 lists 'AWS EKS'",
    "  - t-sum: summary t-sum mentions 'DevSecOps'",
    "  +10 more (cvt validate-artifact / cvt status)",
  ].join("\n");
  const message = formatRunError(text);
  assert.match(message, /E_TOOL_CHECK/);
  assert.match(message, /AWS EKS/);
  assert.match(message, /DevSecOps/);
  assert.equal(message.includes("hint:"), false);
});

test("a crash while questions are open is an error, not the same questions again", () => {
  assert.equal(continueOutcome(6, "awaiting_answers", "").phase, "awaiting_answers");
  assert.equal(continueOutcome(0, "awaiting_approval", "").phase, "awaiting_approval");
  assert.equal(continueOutcome(0, "reported", "").phase, "finished");
  const crashed = continueOutcome(7, "awaiting_answers", "cvt: error[E_TOOL_LOOP_CAP]: stopped after 32 tool proposals");
  assert.equal(crashed.phase, "error");
  assert.match(crashed.message, /E_TOOL_LOOP_CAP/);
});

test("the infer prompt names gtjob and does not write stage JSON", () => {
  const tailor = inferPrompt({ slug: "20261028-example", mode: "tailor" });
  assert.match(tailor, /gtjob continue 20261028-example/);
  assert.match(tailor, /exit code is 6/);
  assert.match(tailor, /Do not write profile-map.json/);
  assert.equal(tailor.includes("write out/"), false);
  const reply = inferPrompt({ slug: "20261028-example", mode: "reply", resume: "approved" });
  assert.match(reply, /gtjob reply 20261028-example/);
  assert.match(reply, /exit code is 6/);
  const answers = inferPrompt({ slug: "20261028-example", mode: "tailor", resume: "answers" });
  assert.match(answers, /already committed/);
  const message = inferPrompt({ slug: "20261028-example", mode: "tailor", resume: "message" });
  assert.match(message, /\.studio\/infer\/20261028-example\.reply\.txt/);
  assert.match(message, /is data/);
  const polish = inferPrompt({ slug: "20261028-ada-generic", mode: "polish" });
  assert.match(polish, /gtjob polish fill/);
  assert.match(polish, /cv\.txt/);
  assert.match(polish, /do not call cvt init/i);
  assert.equal(polish.includes("render.json"), true);
  assert.equal(polish.includes("Do not write render.json"), true);
  assert.equal(polish.includes("awaiting_answers"), false);
  const polishReply = inferPrompt({ slug: "20261028-ada-generic", mode: "polish", resume: "message" });
  assert.match(polishReply, /\.studio\/infer\/20261028-ada-generic\.reply\.txt/);
  assert.equal(polishReply.includes("answer_parse"), false);
});

test("polish slugs stay unique and only polish folders are listed", () => {
  assert.equal(polishSlug("Arash-Morattab-CV-classic.pdf", "20261028", new Set()), "20261028-arash-morattab-generic");
  assert.equal(
    polishSlug("Arash-Morattab-CV-classic.pdf", "20261028", new Set(["20261028-arash-morattab-generic"])),
    "20261028-arash-morattab-generic-2",
  );
  const out = path.join(mkdtempSync(`${tmpdir()}/studio-polish-`), "out");
  mkdirSync(path.join(out, "20261028-ada-generic"), { recursive: true });
  writeFileSync(path.join(out, "20261028-ada-generic", "polish.json"), JSON.stringify({ cv: "Ada.pdf" }));
  mkdirSync(path.join(out, "tailor-run"));
  writeFileSync(path.join(out, "tailor-run", "state.json"), JSON.stringify({ stage: "matched" }));
  mkdirSync(path.join(out, "old-generic"));
  writeFileSync(path.join(out, "old-generic", "render.json"), "{}");
  writeFileSync(path.join(out, "old-generic", "Ada-CV-modern.pdf"), "");
  const listed = listPolishRuns(out);
  assert.deepEqual(
    listed.map((run) => run.slug).sort(),
    ["20261028-ada-generic", "old-generic"],
  );
  const fresh = listed.find((run) => run.slug === "20261028-ada-generic");
  assert.equal(fresh.title, "Ada.pdf");
  assert.equal(previewFile(fresh.downloads), "");
  const done = listed.find((run) => run.slug === "old-generic");
  assert.equal(previewFile(done.downloads), "Ada-CV-modern.pdf");
});

test("infer status stays inside .studio and drops a key", () => {
  const root = mkdtempSync(`${tmpdir()}/studio-infer-`);
  const written = writeInferStatus(root, "20261028-example", { phase: "running", log: ["status"] });
  assert.equal(written.phase, "running");
  assert.equal(readInferStatus(root, "20261028-example").log[0], "status");
  const login = writeLoginStatus(root, { phase: "waiting", apiKey: "cursor_secret", url: "https://example.test" });
  assert.equal(login.apiKey, undefined);
  assert.equal(readLoginStatus(root).url, "https://example.test");
  assert.throws(() => writeInferStatus(root, "../secret", { phase: "running" }));
  const long = "x".repeat(13000);
  const capped = writeInferStatus(root, "20261028-example", {
    turns: [{ id: "a", role: "assistant", text: long, detail: "y".repeat(200) }],
  });
  assert.equal(capped.turns[0].text.length, 12000);
  assert.equal(capped.turns[0].detail.length, 160);
  writeReply(root, "20261028-example", "four engineers");
  assert.equal(readInferStatus(root, "20261028-example").apiKey, undefined);
});

test("the transcript joins assistant text and keeps one row per tool", () => {
  let turns = [];
  turns = foldEvent(turns, { type: "assistant", message: { content: [{ type: "text", text: "Hello" }] } });
  turns = foldEvent(turns, { type: "assistant", message: { content: [{ type: "text", text: " there" }] } });
  turns = foldEvent(turns, { type: "tool_call", call_id: "c1", name: "read", status: "running", args: { path: "cv.md" } });
  turns = foldEvent(turns, { type: "tool_call", call_id: "c1", name: "read", status: "completed", args: { path: "cv.md" } });
  turns = foldEvent(turns, { type: "user", message: { content: [{ type: "text", text: "hidden prompt" }] } });
  turns = foldEvent(turns, { type: "assistant", message: { content: [{ type: "text", text: "Done" }] } });
  assert.equal(turns[0].text, "Hello there");
  assert.equal(turns[1].status, "completed");
  assert.equal(turns[1].detail, "cv.md");
  assert.equal(toolLabel(turns[1].name), "Read");
  assert.equal(turns.length, 3);
  assert.equal(turns[2].text, "Done");
  let snapshot = foldEvent([], { type: "assistant", message: { content: [{ type: "text", text: "Hi" }] } });
  snapshot = foldEvent(snapshot, { type: "assistant", message: { content: [{ type: "text", text: "Hi there" }] } });
  assert.equal(snapshot.length, 1);
  assert.equal(snapshot[0].text, "Hi there");
  let many = [];
  for (let index = 0; index < 90; index += 1) {
    many = foldEvent(many, { type: "assistant", message: { content: [{ type: "text", text: `n${index}` }] } });
    many = foldEvent(many, { type: "tool_call", call_id: `t${index}`, name: "read", status: "completed", args: { path: "a" } });
  }
  const assistantIds = many.filter((turn) => turn.role === "assistant").map((turn) => turn.id);
  assert.equal(new Set(assistantIds).size, assistantIds.length);
});

test("multi-select stays a list and written answers stay prose", () => {
  const questions = [
    { id: "q-1", type: "multi_select", choices: [{ id: "kafka_msk" }, { id: "openapi" }], default: { choice_ids: [] } },
    { id: "q-6", type: "single_select", choices: [{ id: "modern" }], default: { choice_ids: ["modern"] } },
    { id: "q-3", type: "free_text", choices: [], default: { description: "No number is added." } },
    { id: "q-8", type: "yes_no", choices: [{ id: "no" }, { id: "yes" }], default: { choice_ids: ["no"] } },
  ];
  assert.equal(controlKind(questions[0]), "multiple");
  assert.equal(controlKind(questions[1]), "single");
  assert.equal(controlKind(questions[2]), "text");
  const picked = { ...initialPicked(questions), "q-1": ["kafka_msk", "openapi"] };
  const written = buildAnswerRequest(questions, picked, { "q-3": "four engineers for a year" });
  assert.ok(written.select.includes("q-1=kafka_msk,openapi"));
  assert.ok(written.select.includes("q-6=modern"));
  assert.equal(written.select.includes("q-3=skip"), false);
  assert.match(written.prose, /q-3: four engineers/);
  assert.equal(written.defaultRest, false);
  const defaults = buildAnswerRequest(questions, initialPicked(questions), {});
  assert.ok(defaults.select.includes("q-1=skip"));
  assert.ok(defaults.select.includes("q-6=modern"));
  assert.equal(defaults.prose, "");
  assert.equal(defaults.defaultRest, true);
  const again = buildAnswerRequest(
    [
      { id: "q-1", type: "multi_select", status: "answered", choices: [{ id: "kafka_msk" }], default: { choice_ids: [] } },
      { id: "q-4", type: "free_text", status: "pending", choices: [] },
    ],
    { "q-1": ["kafka_msk"] },
    { "q-4": "50" },
  );
  assert.equal(again.select.some((item) => item.startsWith("q-1=")), false);
  assert.equal(again.prose, "q-4: 50");
  const kept = pendingReply(
    [{ id: "q-4", type: "free_text", status: "pending", choices: [] }, { id: "q-5", type: "free_text", status: "pending", choices: [] }],
    {},
    { "q-3": "8", "q-4": "6000", "q-5": "50" },
  );
  assert.equal(kept.select.length, 0);
  assert.equal(kept.prose, "q-4: 6000\nq-5: 50\nq-3: 8");
  assert.equal(applyFailure({ ok: false, exit_code: 6, error: { message: "" } }), "");
  assert.equal(
    applyFailure({ ok: false, exit_code: 2, error: { message: "q-1 is answered, not pending", hint: "select only pending questions" } }),
    "q-1 is answered, not pending. select only pending questions",
  );
});

test("a reply reopens a skipped question and a resumed run is not stopped at the same checkpoint", () => {
  const root = mkdtempSync(`${tmpdir()}/studio-reopen-`);
  const slug = "20261028-example";
  const dir = path.join(root, "out", slug);
  mkdirSync(dir, { recursive: true });
  writeFileSync(
    path.join(dir, "questions.json"),
    JSON.stringify({
      questions: [
        { id: "q-1", status: "answered", type: "multi_select" },
        { id: "q-3", status: "skipped", type: "free_text" },
        { id: "q-4", status: "pending", type: "free_text" },
      ],
    }),
  );
  assert.deepEqual(reopenNotedQuestions(root, slug, "q-4: 6000\nq-3: 8"), ["q-3"]);
  const saved = JSON.parse(readFileSync(path.join(dir, "questions.json"), "utf8"));
  assert.equal(saved.questions.find((question) => question.id === "q-3").status, "pending");
  assert.equal(saved.questions.find((question) => question.id === "q-1").status, "answered");
  assert.equal(stopAtCheckpoint("awaiting_answers", "", "", false).stop, true);
  assert.equal(stopAtCheckpoint("awaiting_answers", "awaiting_answers", "message", false).stop, false);
  const moved = stopAtCheckpoint("assembling", "awaiting_answers", "message", false);
  assert.equal(moved.stop, false);
  assert.equal(stopAtCheckpoint("awaiting_approval", "awaiting_answers", "message", moved.seenOtherStage).stop, true);
  assert.equal(stopAtCheckpoint("awaiting_approval", "awaiting_approval", "approved", false).stop, false);
});

test("the studio provider is cursor, anthropic, or automatic", () => {
  assert.equal(parseProvider("Cursor"), "cursor");
  assert.equal(parseProvider("nope"), null);
  const root = mkdtempSync(`${tmpdir()}/studio-provider-`);
  assert.equal(readProvider(root), "cursor");
  assert.equal(writeProvider(root, "anthropic"), "anthropic");
  assert.equal(readProvider(root), "anthropic");
  assert.equal(providerEnv("cursor", { PATH: "/bin" }).GTJOB_PROVIDER, "cursor");
  assert.equal(providerEnv("auto", { GTJOB_PROVIDER: "anthropic" }).GTJOB_PROVIDER, "anthropic");
  const stale = "error[E_API_KEY]: ANTHROPIC_API_KEY is not set";
  const ready = providerStatus(stale, { provider: "cursor", cursor: true, anthropic: false });
  assert.equal(ready.showMessage, false);
  assert.equal(ready.canContinue, true);
  assert.equal(ready.text, "");
  const blocked = providerStatus(stale, { provider: "anthropic", cursor: true, anthropic: false });
  assert.equal(blocked.canContinue, false);
  assert.match(blocked.text, /Choose Cursor/);
  assert.equal(providerStatus("The run stopped.", { provider: "cursor", cursor: true, anthropic: false }).showMessage, true);
});
