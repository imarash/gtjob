import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { belowApplyBar } from "../src/lib/columns.mjs";
import { extractHttpUrl, parseTrackerMarkdown, readTrackerFile, runSlugFromNotes } from "../src/lib/tracker.mjs";

const fixtures = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");

test("extracts an http URL from a markdown link and a bare URL", () => {
  assert.equal(extractHttpUrl("[ashby](https://jobs.example.test/acme/1)"), "https://jobs.example.test/acme/1");
  assert.equal(extractHttpUrl("https://jobs.example.test/globex/2 extra"), "https://jobs.example.test/globex/2");
  assert.equal(extractHttpUrl("—"), "");
  assert.equal(extractHttpUrl("[1](reports/001-acme.md)"), "");
});

test("parses the header by name and keeps status text as stored", () => {
  const parsed = parseTrackerMarkdown(
    pathToText(path.join(fixtures, "tracker.md")),
  );
  assert.equal(parsed.ok, true);
  if (!parsed.ok) return;
  assert.equal(parsed.rows.length, 3);
  assert.equal(parsed.rows[0].company, "Acme");
  assert.equal(parsed.rows[0].status, "Evaluated");
  assert.equal(parsed.rows[0].score, "4.2/5");
  assert.equal(parsed.rows[0].url, "https://jobs.example.test/acme/1");
  assert.equal(parsed.rows[0].reportHref, "reports/001-acme.md");
  assert.equal(parsed.rows[0].runSlug, "example-run");
  assert.equal(parsed.rows[1].url, "https://jobs.example.test/globex/2");
  assert.equal(parsed.rows[2].score, "N/A");
  assert.equal(belowApplyBar(parsed.rows[1].score), true);
  assert.equal(belowApplyBar(parsed.rows[0].score), false);
  assert.equal(belowApplyBar(parsed.rows[2].score), false);
});

test("a missing tracker is empty and a broken table is an error", () => {
  const missing = readTrackerFile(path.join(fixtures, "no-such-tracker.md"));
  assert.equal(missing.ok, true);
  assert.equal(missing.missing, true);
  assert.deepEqual(missing.rows, []);

  const broken = readTrackerFile(path.join(fixtures, "tracker-broken.md"));
  assert.equal(broken.ok, false);
  assert.match(broken.error, /header/);

  const directory = readTrackerFile(fixtures);
  assert.equal(directory.ok, false);
  assert.equal(directory.missing, false);
});

test("the run token is the last gtjob-run slug in notes", () => {
  assert.equal(runSlugFromNotes("gtjob-run:one; gtjob-run:two"), "two");
  assert.equal(runSlugFromNotes("no token"), "");
});

function pathToText(file) {
  return readFileSync(file, "utf8");
}
