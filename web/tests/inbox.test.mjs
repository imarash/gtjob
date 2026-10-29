import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { appendInbox, evaluationHint, readInbox } from "../src/lib/inbox.mjs";

test("a saved role is data, and the hint does not claim a score", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "studio-inbox-"));
  const file = path.join(dir, "inbox.json");
  try {
    const hint = evaluationHint({ careerOpsRoot: "/tmp/career-ops", kind: "url" });
    assert.match(hint, /did not score/);
    const item = appendInbox(file, {
      kind: "url",
      text: "https://jobs.example.test/1",
      hint,
    });
    assert.equal(item.kind, "url");
    const read = readInbox(file);
    assert.equal(read.ok, true);
    assert.equal(read.items[0].text, "https://jobs.example.test/1");
    writeFileSync(file, "{");
    const broken = readInbox(file);
    assert.equal(broken.ok, false);
    assert.match(broken.error, /JSON/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("a missing inbox is empty", () => {
  const read = readInbox(path.join(tmpdir(), "studio-inbox-missing", "inbox.json"));
  assert.equal(read.ok, true);
  assert.equal(read.missing, true);
  assert.deepEqual(read.items, []);
});
