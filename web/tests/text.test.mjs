import assert from "node:assert/strict";
import test from "node:test";
import { dueEntries, nextActionLine } from "../src/lib/followups.mjs";
import { renderMarkdown } from "../src/lib/markdown.mjs";
import { reportHeader } from "../src/lib/report-header.mjs";

test("next action uses a cadence date and otherwise points at the report", () => {
  assert.equal(nextActionLine(null), "Open the report");
  assert.equal(
    nextActionLine({ urgency: "overdue", nextFollowupDate: "2026-06-08" }),
    "Follow up due 2026-06-08",
  );
  assert.equal(
    nextActionLine({ urgency: "waiting", nextFollowupDate: "2026-06-20" }),
    "Next follow-up 2026-06-20",
  );
  assert.deepEqual(
    dueEntries([
      { num: "1", urgency: "overdue", nextFollowupDate: "2026-06-08", company: "Acme", role: "Engineer" },
      { num: "2", urgency: "waiting", nextFollowupDate: "2026-06-20", company: "Globex", role: "Analyst" },
    ]).map((entry) => entry.num),
    ["1"],
  );
});

test("report markdown cannot inject a tag", () => {
  const html = renderMarkdown("Hello <script>alert(1)</script>\n\n**bold**\n\n[ok](javascript:alert(1))\n");
  assert.equal(html.includes("<script"), false);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /<strong>bold<\/strong>/);
  assert.equal(html.includes("javascript:"), false);
});

test("career-ops header fields are read as stored", () => {
  const header = reportHeader("**Score:** 4.2/5\n**URL:** https://jobs.example.test/1\n**Legitimacy:** High Confidence\n");
  assert.equal(header.score, "4.2/5");
  assert.equal(header.url, "https://jobs.example.test/1");
  assert.equal(header.legitimacy, "High Confidence");
});
