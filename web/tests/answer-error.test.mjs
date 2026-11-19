import assert from "node:assert/strict";
import test from "node:test";
import { formatAnswerViolations, formatEnvelopeAnswerFailure } from "../src/lib/answer-error.mjs";
import { formatRunError as formatInferError } from "../src/lib/infer-status.mjs";

const questions = [
  {
    id: "q-6",
    prompt: "BDC (exp-3.e3): What was the scope of PCI DSS controls you worked on?",
  },
];

test("answer failure text names the question, the user line, and a fix", () => {
  const text = formatAnswerViolations(
    [
      {
        question_id: "q-6",
        code: "unsupported_term",
        message: "term 'PCI DSS' in items[0].attestations[0] is not something the user said or chose",
      },
    ],
    questions,
    { "q-6": "infrastructure only" },
  );
  assert.match(text, /q-6/);
  assert.match(text, /infrastructure only/);
  assert.match(text, /PCI DSS/);
  assert.match(text, /How to fix:/);
});

test("envelope failures merge the guided block", () => {
  const guided = formatEnvelopeAnswerFailure(
    {
      ok: false,
      error: { message: "the answers round has 1 problems" },
      data: {
        violations: [
          {
            question_id: "q-6",
            message: "term 'PCI DSS' in items[0].attestations[0] is not something the user said or chose",
          },
        ],
      },
    },
    questions,
    { "q-6": "infrastructure only" },
  );
  assert.match(guided, /problems/);
  assert.match(guided, /Your answers could not be saved/);
});

test("infer stderr keeps the guided answer block", () => {
  const stderr = [
    "cvt: error[E_CHECK_FAILED]: answer_parse still fails its check after 2 attempts (1 violations)",
    "  hint: patch only the listed items",
    "",
    "Your answers could not be saved:",
    "  • q-6 (BDC (exp-3.e3))",
    "    Your answer: infrastructure only",
    "    Issue: term 'PCI DSS' is not something the user said or chose",
    "    How to fix: add the term yourself or shorten the answer.",
  ].join("\n");
  const message = formatInferError(stderr);
  assert.match(message, /answer_parse still fails/);
  assert.match(message, /q-6/);
  assert.match(message, /infrastructure only/);
  assert.match(message, /How to fix:/);
});
