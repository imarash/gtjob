import assert from "node:assert/strict";
import test from "node:test";
import { draftReply } from "../src/lib/reply.mjs";
import { downloadAllowed, previewFile } from "../src/lib/runs.mjs";
import { renderTemplatePreviews } from "../src/lib/template-previews.mjs";

const REPORT = `# Match report: Engineer at Example Co

- Final PDF: final/Ada-Lovelace-Engineer.pdf

## Coverage

| Requirement | Kind | Weight | Strength | Evidence | Found in PDF |
| --- | --- | --- | --- | --- | --- |
| req-1 Python services | must | 3 | strong | exp-1 | yes (1/1) |
| req-2 Kubernetes | must | 3 | partial | exp-2 | no (0/1) |

## Confirmed facts used

| ID | Claim | Type | Scope | Your words | Status | Run |
| --- | --- | --- | --- | --- | --- | --- |
| att-001 | Python | skill | global | "python" | active | example |

## Remaining gaps

- **req-2** Kubernetes was not confirmed.
`;

test("the email uses strong matches and leaves gaps out", () => {
  const draft = draftReply(REPORT);
  assert.match(draft.markdown, /Subject: Engineer — CV attached/);
  assert.match(draft.markdown, /Python services/);
  assert.match(draft.markdown, /Python/);
  assert.match(draft.markdown, /Thanks,\nAda/);
  assert.equal(draft.markdown.includes("Kubernetes"), false);
  assert.equal(draft.attach, "Ada-Lovelace-Engineer.pdf");
});

test("downloads stay inside the finished files", () => {
  assert.equal(downloadAllowed("final/cv.pdf"), true);
  assert.equal(downloadAllowed("cv.md"), true);
  assert.equal(downloadAllowed("reply.md"), true);
  assert.equal(downloadAllowed("build/cv.typ"), true);
  assert.equal(downloadAllowed("profile.json"), false);
  assert.equal(downloadAllowed("cv.txt"), false);
  assert.equal(downloadAllowed("../cv.pdf"), false);
  assert.equal(downloadAllowed("preview-classic.pdf"), true);
  assert.equal(
    previewFile([{ file: "preview-modern.pdf" }, { file: "cv.pdf" }, { file: "final/Ada.pdf" }]),
    "final/Ada.pdf",
  );
  assert.equal(previewFile([{ file: "preview-modern.pdf" }, { file: "cv.pdf" }]), "cv.pdf");
  assert.equal(
    previewFile([{ file: "Ada-CV-classic.pdf" }, { file: "Ada-CV-modern.pdf" }]),
    "Ada-CV-modern.pdf",
  );
  assert.throws(() => renderTemplatePreviews("/tmp/gtjob", "../secret"), /Name the run/);
});
