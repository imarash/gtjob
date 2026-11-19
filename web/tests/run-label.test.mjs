import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import {
  cvLabel,
  extractJob,
  extractPosition,
  formatRunDate,
  formatRunTitle,
  readRunProgress,
} from "../src/lib/run-label.mjs";

const now = new Date("2026-11-06T18:00:00Z");

test("a posting's first lines yield the role and the company", () => {
  const posted = extractJob(`LPL Financial

Principal Solution Architect

About the job

Where Ambition Meets Innovation
`);
  assert.deepEqual(posted, { title: "Principal Solution Architect", company: "LPL Financial" });
  const labeled = extractJob("# Junior DevOps Engineer\n\nCompany: Harbor Point Software\nLocation: Columbus, OH\n");
  assert.equal(labeled.title, "Junior DevOps Engineer");
  assert.equal(labeled.company, "Harbor Point Software");
  const emailed = extractJob(`Hope you’re doing well
Greetings from Tanisha Systems Inc
Please find the below job description and Kindly share me your updated resume if interested:

Role: Principal Developer / Technical Architect & Delivery Lead
Location : Remote, USA
`);
  assert.equal(emailed.title, "Principal Developer / Technical Architect & Delivery Lead");
  assert.equal(emailed.company, "");
});

test("the current role comes from the experience line, not a skills headline", () => {
  const text = `Jamie Rivera
Junior DevOps Engineer
Columbus, OH | jamie.rivera@example.com

EXPERIENCE
Brightfield Logistics | Junior DevOps Engineer | Columbus, OH | Feb 2024 - Present
- Built pipelines
`;
  assert.equal(extractPosition(text), "Junior DevOps Engineer");
  const skills = `Arash Morattab
Cloud DevOps · Kubernetes · Terraform · GCP · AI Agents
me@arashmor.com
`;
  assert.equal(extractPosition(skills), "");
});

test("the title mixes the job, the CV position, the CV, and the date", () => {
  assert.equal(cvLabel("/CVs/Arash-Morattab-CV-classic-wl.pdf"), "Arash Morattab CV");
  assert.equal(formatRunDate("20261106", now), "Nov 6");
  assert.equal(formatRunDate("20251106", now), "Nov 6, 2025");
  assert.equal(
    formatRunTitle({
      jobTitle: "Principal Solution Architect",
      company: "LPL Financial",
      position: "Cloud DevOps Architect",
      cv: "Arash Morattab CV",
      date: "Nov 6",
    }),
    "Principal Solution Architect, LPL Financial · Cloud DevOps Architect · Arash Morattab CV · Nov 6",
  );
  assert.equal(
    formatRunTitle({
      jobTitle: "Junior DevOps Engineer",
      company: "Harbor Point Software",
      position: "Junior DevOps Engineer",
      cv: "Jamie Rivera",
      date: "Nov 6",
    }),
    "Junior DevOps Engineer, Harbor Point Software · Jamie Rivera · Nov 6",
  );
});

test("a run folder supplies the title and the current step", () => {
  const out = mkdtempSync(`${tmpdir()}/run-label-`);
  const slug = "20261106-lpl-financial";
  const dir = path.join(out, slug);
  mkdirSync(path.join(dir, "inputs"), { recursive: true });
  writeFileSync(
    path.join(dir, "state.json"),
    JSON.stringify({
      stage: "profiled",
      created_at: "2026-11-06T06:43:35Z",
      inputs: { cv: { original_path: "/CVs/Arash-Morattab-CV-classic-wl.pdf" } },
    }),
  );
  writeFileSync(
    path.join(dir, "jd.json"),
    JSON.stringify({ title: "Principal Solution Architect", company: "LPL Financial" }),
  );
  writeFileSync(
    path.join(dir, "profile.json"),
    JSON.stringify({ work: [{ position: "Cloud DevOps Architect", end_date: "present" }] }),
  );
  const progress = readRunProgress(out, slug, now);
  assert.equal(progress.stage, "profiled");
  assert.equal(progress.step, 2);
  assert.equal(progress.title, "Reading the job");
  assert.match(progress.detail, /few minutes/);
  assert.equal(
    progress.label,
    "Principal Solution Architect, LPL Financial · Cloud DevOps Architect · Arash Morattab CV · Nov 6",
  );
  assert.equal(readRunProgress(out, "../secret", now), null);
});
