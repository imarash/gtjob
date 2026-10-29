import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { listCatalog, referenceFile } from "../src/lib/claude-catalog.mjs";
import { splitFrontmatter } from "../src/lib/frontmatter.mjs";
import { buildToolArgv } from "../src/lib/cvt-args.mjs";
import { parseCvtStdout } from "../src/lib/cvt-spawn.mjs";
import { describeStage } from "../src/lib/stage-copy.mjs";

test("folded skill descriptions stay one string", () => {
  const { data, body } = splitFrontmatter(`---
name: cv-reply
description: >-
  Tailors a CV to a job and drafts the reply.
argument-hint: "[cv-path]"
---

# Body
`);
  assert.equal(data.name, "cv-reply");
  assert.equal(data.description, "Tailors a CV to a job and drafts the reply.");
  assert.match(body, /^# Body/);
});

test("the catalog reads skills and agents from a folder", () => {
  const root = mkdtempSync(path.join(tmpdir(), "claude-catalog-"));
  const skill = path.join(root, "skills", "tailor-cv");
  mkdirSync(skill, { recursive: true });
  mkdirSync(path.join(root, "agents"), { recursive: true });
  writeFileSync(
    path.join(skill, "SKILL.md"),
    "---\nname: tailor-cv\ndescription: Start a run.\n---\n\n# Tailor\n",
  );
  writeFileSync(
    path.join(root, "agents", "cv-critic.md"),
    "---\nname: cv-critic\ndescription: Read-only review.\n---\n\n# Critic\n",
  );
  const catalog = listCatalog(root);
  assert.deepEqual(
    catalog.skills.map((item) => item.name),
    ["tailor-cv"],
  );
  assert.equal(catalog.agents[0].description, "Read-only review.");
  assert.equal(referenceFile(skill, "../SKILL.md"), null);
  assert.equal(referenceFile(skill, "guide.md"), null);
});

test("cvt argv is an argument list and rejects a path escape", () => {
  const root = "/tmp/gtjob";
  const init = buildToolArgv(
    { command: "init", cv: "me.pdf", jd: "role.md", template: "classic" },
    { gtjobRoot: root },
  );
  assert.deepEqual(init.args.slice(0, 6), [
    "init",
    "--cv",
    path.join(root, "CVs", "me.pdf"),
    "--host",
    "cursor",
    "--jd",
  ]);
  assert.equal(init.args.at(-1), "--json");
  assert.throws(() => buildToolArgv({ command: "init", cv: "../secret.pdf", jdText: "role" }, { gtjobRoot: root }));
  assert.throws(() => buildToolArgv({ command: "brief", run: "latest" }, { gtjobRoot: root }));
  assert.throws(() => buildToolArgv({ command: "brief", stage: "match", run: "20261028-example" }, { gtjobRoot: root }));
  assert.deepEqual(
    buildToolArgv({ command: "profile-cache", run: "20261028-example" }, { gtjobRoot: root }).args,
    ["profile-cache", "20261028-example", "--lookup", "--json"],
  );
  assert.deepEqual(
    buildToolArgv({ command: "approve", run: "20261028-example", all: true }, { gtjobRoot: root }).args,
    ["approve", "20261028-example", "--all", "--json"],
  );
  assert.deepEqual(
    buildToolArgv({ command: "brief", stage: "jd", run: "20261028-example" }, { gtjobRoot: root }).args,
    ["brief", "jd", "20261028-example", "--json"],
  );
});

test("answers stay one argv element per flag", () => {
  const built = buildToolArgv(
    { command: "answers-apply", run: "20261026-example", select: ["q-1=terraform", "q-2=skip"], mode: "dry-run" },
    { gtjobRoot: "/tmp/gtjob" },
  );
  assert.deepEqual(built.args, [
    "answers-apply",
    "20261026-example",
    "--select",
    "q-1=terraform",
    "--select",
    "q-2=skip",
    "--default-rest",
    "--dry-run",
    "--all",
    "--json",
  ]);
  assert.throws(() =>
    buildToolArgv(
      { command: "answers-apply", run: "ok", select: ["q-1=Terraform"], mode: "dry-run" },
      { gtjobRoot: "/tmp/gtjob" },
    ),
  );
});

test("a cvt envelope is the last JSON line", () => {
  const parsed = parseCvtStdout('warning\n{"ok":true,"command":"status"}\n');
  assert.equal(parsed && parsed.ok, true);
  assert.equal(parseCvtStdout("not json"), null);
});

test("stage copy never tells the person to run a shell command", () => {
  for (const stage of ["ingested", "profiled", "jd_analyzed", "reported"]) {
    const text = `${describeStage(stage).title} ${describeStage(stage).detail}`;
    assert.equal(text.includes("uv run"), false);
    assert.equal(text.includes("cvt.py"), false);
  }
});
