# Troubleshooting

Each problem below starts with the message you will see, then the fix. Error messages follow the form
`cvt: error[E_ID]: message` with a `hint:` line. Exit codes are listed in the
[command reference](../.claude/skills/tailoring-cvs/references/commands.md). Replace `RUN` with your run slug, for
example `20261023-staff-platform-sre`, or use `latest`.

## Contents

- [Typst is missing (exit 3)](#typst-is-missing-exit-3)
- [The CV is a scanned PDF (exit 5)](#the-cv-is-a-scanned-pdf-exit-5)
- [uv cannot write its cache in the sandbox](#uv-cannot-write-its-cache-in-the-sandbox)
- [Provenance violations (exit 1)](#provenance-violations-exit-1)
- [Page overflow with priority-1 content](#page-overflow-with-priority-1-content)
- [The Claude Code question dialog timed out](#the-claude-code-question-dialog-timed-out)

## Typst is missing (exit 3)

**You see:** `error[E_TYPST_MISSING]: no Typst compiler found` with the hint `install a Typst backend ...`.

**Why:** the PDF is produced by Typst. gtjob uses the Python `typst` package first, then a `typst` program on your PATH.

**Fix:** install one of them, then render again:

```bash
uv pip install typst        # Python package (preferred)
brew install typst          # or the command-line program on macOS
uv run .claude/skills/tailoring-cvs/scripts/cvt.py render RUN
```

**Until then:** the run still produces `build/cv.typ` and `cv.md` (the Markdown version of the CV). You can open
`cv.md` or compile `build/cv.typ` yourself. Exit code 3 means the run is usable, but there is no PDF yet.

## The CV is a scanned PDF (exit 5)

**You see:** `error[E_CV_SCANNED]: this PDF has almost no extractable text`, with the hint `this PDF looks scanned ...`.

**Why:** the PDF is an image of a page, not text. gtjob does not run OCR yet, and OCR output can silently change names,
dates, and numbers.

**Fix:** either export a text-based PDF from the original document (in Word, Pages, or Google Docs, choose "Save as
PDF" rather than printing to an image), or paste the CV text, or give a Markdown or text file. Then start the run again
with the new file.

## uv cannot write its cache in the sandbox

**You see:** a `uv` error about the cache directory, such as `failed to create directory` or `Operation not permitted`,
when you run any `uv run` command in Cursor or another sandboxed host.

**Fix:** point uv's cache at the repo's `.cache/` folder for that command:

```bash
UV_CACHE_DIR=.cache/uv uv run .claude/skills/tailoring-cvs/scripts/cvt.py status
```

Use the same prefix for every `cvt` and test command in that session. If your host is not sandboxed, the normal
command works.

## Provenance violations (exit 1)

**You see:** `check-tailored` or `validate` fails with violations such as:

```text
bullet t-exp-2.e4.b1 mentions 'Linkerd'; not found in refs [exp-2.e4, att-002]
```

**Why:** the bullet uses a tool, number, date, or entity that does not appear in the CV items it cites. gtjob does not
allow this, even when the claim is likely true. The rule is there so that nothing is invented.

**How to resolve it:**

- **The claim is true.** Tell the assistant in chat, for example "yes, I used Linkerd in the payments platform role".
  The assistant records your answer as an attestation scoped to that role (you can see and revoke it later), then
  cites it from the bullet. Nothing is recorded until you answer.
- **The claim is not true, or you do not want it.** Ask for the term to be removed from that bullet, for example "drop
  Linkerd from that bullet". The change goes through the normal review at checkpoint 2.
- **Only the wording differs.** Ask for the bullet to be reworded using the CV's own terms.

Fixes are patches, not rewrites. The assistant runs `cvt brief fix RUN`, changes only the listed items, and checks
again. After two failed attempts it shows you the remaining violations and waits for your decision.

Attestations you confirmed earlier are reused automatically in later runs, so the same question is not asked again for
that scope.

## Page overflow with priority-1 content

**You see:** `error[E_FIT_OVERFLOW]: content with priority 1 exceeds 2 pages; lower some priorities or shorten bullets`.

**Why:** items at priority 1 are never dropped to make the CV fit. Even with every lower-priority item removed, the
priority-1 content is too long for the page target.

**Fix, in order of preference:**

1. Lower the priority of some priority-1 bullets that are less relevant to this job. Ask in chat, for example "make the
   2019 platform migration bullets lower priority". This is a `set_priority` change and goes through checkpoint 2.
2. Shorten long bullets. Ask for a shorter version of the named bullets.

Then run `uv run .claude/skills/tailoring-cvs/scripts/cvt.py fit RUN`.

A generic CV from `/cv-polish` does not use this fit. If the script says a template is still over 3 pages at
`compact`, shorten wording and render again. Do not drop a fact. An `E_SCHEMA` error on that command is a
`render.json` shape problem, not a page-count problem.

## The Claude Code question dialog timed out

**You see:** the `AskUserQuestion` dialog closed without an answer, and the run continued with defaults.

**Why:** a timed-out dialog counts as a skip, so every unanswered question takes its default. That is by design, so a
run never stalls.

**Fix:**

1. Run `/cv-status` to see what was applied. The report (`out/<run-slug>/report.md`) also lists every default.
2. If you want a different answer, reply in chat with it, or run `/cv-continue <your answer>`:
   - while the run is still waiting for answers, the reply is applied as an answer (dry run first, then commit);
   - after the diff is shown, the reply is a change request at checkpoint 2.
