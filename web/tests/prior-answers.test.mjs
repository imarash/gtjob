import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { priorAnswers } from "../src/lib/prior-answers.mjs";

function writeRun(out, slug, questions, rounds) {
  const dir = path.join(out, slug);
  mkdirSync(dir, { recursive: true });
  writeFileSync(path.join(dir, "questions.json"), JSON.stringify({ questions }));
  writeFileSync(path.join(dir, "answers.json"), JSON.stringify({ rounds }));
}

function question(partial) {
  return {
    status: "pending",
    choices: [],
    links: { item_ids: [] },
    topic: "metric",
    type: "free_text",
    prompt: "",
    ...partial,
  };
}

test("a repeated bullet offers the latest earlier answer, not a different bullet's number", () => {
  const out = mkdtempSync(`${tmpdir()}/priors-`);
  writeRun(
    out,
    "20261029-remote",
    [
      question({
        id: "q-4",
        prompt: "For the RBC SRE engagement: any count of clusters?",
        links: { item_ids: ["exp-2.e4.b1"] },
      }),
    ],
    [
      {
        received_at: "2026-10-30T04:01:25Z",
        items: [{ question_id: "q-4", action: "attest", choice_ids: [], attestations: [{ verbatim: "200" }] }],
      },
    ],
  );
  writeRun(
    out,
    "20261113-frost",
    [
      question({
        id: "q-4",
        prompt: "RBC SRE: how many OpenShift clusters?",
        links: { item_ids: ["exp-2.e4.b1"] },
      }),
      question({
        id: "q-7",
        type: "single_select",
        topic: "strategy",
        prompt: "Which CV layout template should we use?",
        choices: [
          { id: "modern", label: "Modern" },
          { id: "classic", label: "Classic" },
        ],
      }),
    ],
    [
      {
        received_at: "2026-11-13T17:05:00Z",
        items: [
          {
            question_id: "q-4",
            action: "attest",
            choice_ids: [],
            attestations: [{ verbatim: "~50 OpenShift clusters / tenant workloads" }],
          },
          { question_id: "q-7", action: "choose", choice_ids: ["modern"], attestations: [] },
        ],
      },
    ],
  );
  writeRun(
    out,
    "20261117-ash",
    [
      question({
        id: "q-3",
        prompt: "Retail edge OpenShift: what cluster and node counts?",
        links: { item_ids: ["exp-2.e1.b1"] },
      }),
      question({
        id: "q-6",
        prompt: "At RBC platform SRE: how many OpenShift clusters?",
        links: { item_ids: ["exp-2.e4.b1"] },
      }),
      question({
        id: "q-7",
        type: "single_select",
        topic: "strategy",
        prompt: "Which CV layout template should we use for this run?",
        choices: [
          { id: "modern", label: "Modern" },
          { id: "classic", label: "Classic" },
          { id: "sidebar", label: "Sidebar" },
        ],
      }),
      question({
        id: "q-2",
        type: "multi_select",
        topic: "source_issue",
        prompt: "The packet flagged these CV source issues.",
        choices: [{ id: "iss_1", label: "Overlap" }],
      }),
    ],
    [],
  );

  const priors = priorAnswers(out, "20261117-ash");
  assert.equal(priors["q-3"], undefined);
  assert.equal(priors["q-6"].text, "~50 OpenShift clusters / tenant workloads");
  assert.equal(priors["q-6"].kind, "text");
  assert.deepEqual(priors["q-7"].choiceIds, ["modern"]);
  assert.equal(priors["q-7"].summary, "Modern");
  assert.equal(priors["q-2"], undefined);
});

test("a gap choice is offered only when that same choice was selected before", () => {
  const out = mkdtempSync(`${tmpdir()}/priors-gap-`);
  writeRun(
    out,
    "20261113-frost",
    [
      question({
        id: "q-1",
        type: "multi_select",
        topic: "gap",
        prompt: "Your CV doesn't currently show: Spring Boot.",
        choices: [
          { id: "spring_boot", label: "Spring Boot" },
          { id: "people_leadership", label: "Formal people leadership" },
        ],
      }),
    ],
    [
      {
        received_at: "2026-11-13T17:00:18Z",
        items: [{ question_id: "q-1", action: "attest", choice_ids: ["spring_boot"], attestations: [{ verbatim: "Spring Boot" }] }],
      },
    ],
  );
  writeRun(
    out,
    "20261117-ash",
    [
      question({
        id: "q-1",
        type: "multi_select",
        topic: "gap",
        prompt: "Your CV doesn't currently show: leadership.",
        choices: [
          { id: "people_leadership", label: "Formal people leadership" },
          { id: "spring_boot", label: "Spring Boot" },
        ],
      }),
    ],
    [],
  );
  const priors = priorAnswers(out, "20261117-ash");
  assert.deepEqual(priors["q-1"].choiceIds, ["spring_boot"]);
});

test("skipped answers and the current run are not offered", () => {
  const out = mkdtempSync(`${tmpdir()}/priors-skip-`);
  writeRun(
    out,
    "20261117-ash",
    [
      question({
        id: "q-8",
        type: "yes_no",
        topic: "strategy",
        prompt: "Include an earlier-experience summary line?",
        choices: [
          { id: "yes", label: "Yes" },
          { id: "no", label: "No" },
        ],
      }),
    ],
    [
      {
        received_at: "2026-11-17T20:00:00Z",
        items: [{ question_id: "q-8", action: "choose", choice_ids: ["no"], attestations: [] }],
      },
    ],
  );
  writeRun(
    out,
    "20261113-frost",
    [
      question({
        id: "q-2",
        type: "multi_select",
        topic: "source_issue",
        prompt: "Source issues",
        choices: [],
      }),
      question({
        id: "q-8",
        type: "yes_no",
        topic: "strategy",
        prompt: "Include an earlier-experience summary line (pre-2014 roles)?",
        choices: [
          { id: "yes", label: "Yes" },
          { id: "no", label: "No" },
        ],
      }),
    ],
    [
      {
        received_at: "2026-11-13T17:00:18Z",
        items: [
          { question_id: "q-2", action: "skip", choice_ids: [], attestations: [] },
          { question_id: "q-8", action: "choose", choice_ids: ["yes"], attestations: [] },
        ],
      },
    ],
  );
  const priors = priorAnswers(out, "20261117-ash");
  assert.deepEqual(priors["q-8"].choiceIds, ["yes"]);
  assert.equal(priorAnswers(out, "../escape")["q-8"], undefined);
});
