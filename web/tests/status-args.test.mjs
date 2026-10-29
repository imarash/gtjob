import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { readStateLabels } from "../src/lib/states.mjs";
import { attachRunNote, buildLivenessArgs, buildSetStatusArgs } from "../src/lib/status-args.mjs";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "career-ops");

test("status argv is an argument array and rejects labels the fake states file does not list", () => {
  const labels = readStateLabels(root);
  assert.equal(labels.ok, true);
  const script = path.join(root, "set-status.mjs");
  const args = buildSetStatusArgs({
    script,
    row: 12,
    status: "Applied",
    note: attachRunNote("example-run"),
    allowed: labels.labels,
  });
  assert.deepEqual(args, [script, "--row", "12", "Applied", "--note", "gtjob-run:example-run"]);
  assert.equal(args.includes("Acme"), false);
  assert.throws(() =>
    buildSetStatusArgs({
      script,
      row: 12,
      status: "Dreaming",
      allowed: labels.labels,
    }),
  );
  assert.throws(() => attachRunNote("../example-run"));
});

test("liveness argv keeps the URL as one argument and does not record history", () => {
  const args = buildLivenessArgs("/tmp/check-liveness.mjs", "https://jobs.example.test/acme/1");
  assert.deepEqual(args, [
    "/tmp/check-liveness.mjs",
    "--no-record",
    "https://jobs.example.test/acme/1",
  ]);
  assert.throws(() => buildLivenessArgs("/tmp/check-liveness.mjs", "https://jobs.example.test/a b"));
});
