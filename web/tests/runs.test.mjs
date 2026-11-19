import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { hintFromHeading, listRuns, resolveRunFile } from "../src/lib/runs.mjs";

const outDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures", "out");

test("lists report and polish runs and skips source copies and caches", () => {
  const listed = listRuns(outDir);
  assert.equal(listed.ok, true);
  const slugs = listed.runs.map((run) => run.slug).sort();
  assert.deepEqual(slugs, ["example-run", "polish-sample"]);
  const example = listed.runs.find((run) => run.slug === "example-run");
  assert.equal(example.waiting, true);
  assert.equal(example.hasReport, true);
  assert.ok(example.pdfs.includes(path.join("final", "example.pdf")));
  const polish = listed.runs.find((run) => run.slug === "polish-sample");
  assert.deepEqual(polish.pdfs, ["example.pdf"]);
  assert.equal(polish.waiting, false);
});

test("a missing out directory is empty, not an error", () => {
  const listed = listRuns(path.join(outDir, "does-not-exist"));
  assert.equal(listed.ok, true);
  assert.equal(listed.missing, true);
  assert.deepEqual(listed.runs, []);
});

test("a run file cannot escape the run directory", () => {
  assert.equal(resolveRunFile(outDir, "example-run", "final/example.pdf")?.endsWith("example.pdf"), true);
  assert.equal(resolveRunFile(outDir, "example-run", "../polish-sample/example.pdf"), null);
  assert.equal(resolveRunFile(outDir, "../example-run", "final/example.pdf"), null);
  assert.equal(resolveRunFile(outDir, "example-run", "report.md"), null);
});

test("company and role hints come from the match report heading", () => {
  assert.deepEqual(hintFromHeading("Match report: Engineer at Example Co"), {
    role: "Engineer",
    company: "Example Co",
  });
  assert.equal(hintFromHeading("Something else"), null);
});
