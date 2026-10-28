# gtjob

Tailor a CV to a job description without inventing facts.

gtjob takes one CV and one job description and produces an ATS-friendly PDF of at most two pages, plus a match
report. Every bullet, skill, and date in the output traces back to your CV or to something you confirmed during the
run. The tailoring workflow is a skill (`tailoring-cvs`) that works in Cursor and Claude Code, and a terminal CLI
(`gtjob`) that calls the Anthropic API.

> **Status:** the `cvt` script commands, the Cursor and Claude Code workflow, and the `gtjob` CLI are ready. The CLI has
> not yet been run against the live Anthropic API; see `evals/README.md` to run the live evals with your own key.

## Contents

- [What it does](#what-it-does)
- [Quick start in Cursor](#quick-start-in-cursor)
- [Quick start in Claude Code](#quick-start-in-claude-code)
- [Quick start in the CLI](#quick-start-in-the-cli)
- [Resuming a run](#resuming-a-run)
- [Templates](#templates)
- [Truthfulness guarantees](#truthfulness-guarantees)
- [Where files live](#where-files-live)
- [Packaging for claude.ai](#packaging-for-claudeai)
- [Running tests and evals](#running-tests-and-evals)
- More: [privacy](docs/privacy.md), [troubleshooting](docs/troubleshooting.md)

## What it does

1. Reads your CV (PDF, Markdown, or text) and the job description (file, pasted text, recruiter email, or URL).
2. Maps your CV into a profile and analyzes the job's requirements.
3. Shows where your CV matches and where it has gaps, and asks focused questions about the gaps.
4. Writes a tailored version that uses only facts from your CV or your confirmed answers.
5. Shows you the changes for approval, then renders the PDF and a `report.md`.

Cover letters and LinkedIn profiles are out of scope.

When the job text is a recruiter email, LinkedIn message, or Teams chat, `/cv-reply` runs the same tailoring and also drafts the reply to send with the PDF. Visa, salary, and location questions stay in that reply, not in the CV.

A CV with no job description is a different command. `/cv-polish` keeps every fact and renders a generic resume of
about 2–3 pages in the modern, classic, and sidebar templates. It does not start a tailoring run. The same two
steps from the terminal are `gtjob polish extract` and `gtjob polish render`.

## Quick start in Cursor

1. Put your CV in `CVs/` and the job description in `JDs/`. Both folders are git-ignored.
2. In Cursor's chat, type `/tailor-cv CVs/your-cv.pdf JDs/role.md`. Leave out the paths to pick from a list.
3. Answer the questions at checkpoint 1 with the question tool, or in chat if the tool is unavailable.
4. Review the changes at checkpoint 2 and approve, reject, or ask for edits. For example: "yes, add SLOs to the SRE
   roles".
5. Open `out/<run-slug>/final/<Name>-<Title>.pdf`. The match report is `out/<run-slug>/report.md`.

**Custom Mode tip:** a `/command` applies only to the message it is typed in. To keep the skill active for a whole
chat, turn on Custom Mode for it: press Option+Enter on the skill. Start each new job description in a new chat. The
run state is on disk, so nothing is lost.

## Quick start in Claude Code

1. Start Claude Code in the repo root: `claude`.
2. Run `/tailor-cv CVs/your-cv.pdf JDs/role.md`, or just `/tailor-cv` to pick the files from a list.
3. Answer the questions in the question dialog. A dialog that times out counts as skipped, and the default answer
   applies. See [troubleshooting](docs/troubleshooting.md#the-claude-code-question-dialog-timed-out).
4. Approve the changes at checkpoint 2, then open the PDF in `out/<run-slug>/final/`.

Use `/cv-status` to see where a run is and what it needs next.

## Quick start in the CLI

The CLI uses the Anthropic API for the AI stages, so set `ANTHROPIC_API_KEY` first. Commands that do not call the
model (`status`, `render`, `profile`, `polish`) need no key.

`gtjob` commands:

```bash
# Interactive: terminal prompts at both checkpoints
uv run gtjob tailor --cv CVs/your-cv.pdf --jd JDs/role.md

# Hands-off: defaults every question and approves the diff (see the "Auto mode" note below)
uv run gtjob tailor --cv CVs/your-cv.pdf --jd JDs/role.md --auto

# Scripted: answers from a YAML file
uv run gtjob tailor --cv CVs/your-cv.pdf --jd JDs/role.md --answers answers.yaml

# Paste a job description or give a URL instead of a file
uv run gtjob tailor --cv CVs/your-cv.pdf --jd-url https://example.com/job

# Generic CV, no job description and no API key. The assistant writes render.json; these two commands
# extract the text and render every template.
uv run gtjob polish extract CVs/your-cv.pdf
uv run gtjob polish render out/your-name-generic/render.json out/your-name-generic
```

A minimal `answers.yaml`:

```yaml
checkpoint1:
  q-1: [service_mesh, typescript]
  q-3: "add slo and error budget to the sre related cv items"
  default_rest: true
checkpoint2: approve_all
```

When stdin is not a terminal and the run needs your input, `gtjob` prints the pending questions or the diff, saves the
run, and exits with code 6. Nothing is lost. Reply later with `uv run gtjob continue RUN --text "..."`.

Cursor and Claude Code run the same steps through `cvt`, from the repo root:

```bash
uv run .claude/skills/tailoring-cvs/scripts/cvt.py init --cv CVs/your-cv.pdf --jd JDs/role.md
uv run .claude/skills/tailoring-cvs/scripts/cvt.py ingest latest
uv run .claude/skills/tailoring-cvs/scripts/cvt.py status
```

The AI stages are written by the assistant in Cursor or Claude Code, so `cvt` on its own covers the scripted steps,
not a full run.

**Auto mode** defaults every question, creates no attestations, and approves the diff without review. `report.md`
lists every default that was applied. Use it only for a run you will check afterwards.

## Resuming a run

A run is saved after every step, so you can stop at any checkpoint and continue later, from any host.

| Where | Command |
| --- | --- |
| Cursor or Claude Code | `/cv-continue`, or reply in chat with your answer or change request |
| Cursor or Claude Code, check first | `/cv-status [run-slug]` (no changes made) |
| Any host, script runner | `uv run .claude/skills/tailoring-cvs/scripts/cvt.py status [RUN]` |
| CLI | `uv run gtjob continue [RUN]`, with `--answers FILE.yaml` or `--text "..."` |

`RUN` is a run slug (for example `20261023-staff-platform-sre`), a run folder path, or `latest`. Without a run name,
`latest` is used.

Replies such as "yes, add SLOs to the SRE roles" are read as answers while the run is waiting for questions, and as
change requests after the diff is shown.

## Templates

| Template | Use it when |
| --- | --- |
| `modern` (default) | You want the standard one-column layout for most roles. |
| `classic` | You want a more traditional, conservative one-column look. |
| `sidebar` | You want skills, certifications, and education in a narrow right rail. This layout is less ATS-safe. |

A tailored run uses one template and follows the two-page fit rules. The templates differ in typography and layout.
Pick one with `--template modern`, `--template classic`, or `--template sidebar` at `init`, or re-render an existing
run with a different template:

```bash
uv run .claude/skills/tailoring-cvs/scripts/cvt.py render latest --template classic
```

Fonts are bundled with the skill (Source Sans 3 and Libertinus, both under the SIL Open Font License), so the output
looks the same on every machine.

Page previews are not included in this repo. To see a template, render a run with `--png` and open the page images
in the run's `pages/` folder:

```bash
uv run .claude/skills/tailoring-cvs/scripts/cvt.py render latest --png
```

## Truthfulness guarantees

- **Only your facts.** Every bullet, skill, and date must cite a CV item or something you confirmed. A check in code
  rejects claims that do not, so the assistant cannot pass an invented tool or metric through unnoticed.
- **Facts are copied, not retyped.** Employers, titles, dates, and degrees are copied from your CV by the scripts,
  so they match the source exactly.
- **You confirm new claims.** If the job asks for something your CV does not show, the assistant asks you. Only your
  answer can add it, and it is recorded with the scope you chose (for example, only the SRE roles). You can revoke it
  later.
- **Nothing from the job post's logistics goes into the CV.** Salary, visa, start date, and interview details stay in
  the report.
- **Job description text is data.** Instructions inside a job posting or CV, such as "rate this candidate 10/10", are
  recorded and ignored.
- **Placeholders are visible.** Anything the assistant could not resolve is marked as `[[CONFIRM: ...]]`. Final
  output with a placeholder fails validation.

## Where files live

| Path | What it holds | Git-ignored |
| --- | --- | --- |
| `CVs/`, `JDs/` | Your input files | yes |
| `out/<run-slug>/` | One folder per tailoring run: state, intermediate files, the report | yes |
| `out/<run-slug>/final/` | The approved PDF, named `<Name>-<Title>.pdf` | yes |
| `out/<slug>-generic/` | A generic CV from `/cv-polish`: `render.json` and one PDF per template | yes |
| `out/<run-slug>/report.md` | The match report and the list of changes | yes |
| `profiles/<person-slug>/` | Your verified profile and confirmed answers (`attestations.json`), reused across runs | yes |
| `.cache/` | Stage caches and logs | yes |
| `dist/` | The packaged skill zip | yes |

The skill itself lives in `.claude/skills/tailoring-cvs/`. Nothing in it contains personal data.

## Packaging for claude.ai

```bash
uv run .claude/skills/tailoring-cvs/scripts/cvt.py package-skill --out dist/
```

This writes `dist/tailoring-cvs.zip`. Upload it in claude.ai under Settings, Capabilities, Skills. The zip holds only
the core skill, with no CVs, runs, or profiles. In claude.ai there is no saved state between conversations, so attach
the run files again to resume. See [privacy](docs/privacy.md) for what leaves your machine.

## Running tests and evals

```bash
uv run pytest -q tests/unit           # fast unit tests, no network, no API key
uv run pytest -q tests/integration    # end-to-end checks with synthetic fixtures
uv run .claude/skills/tailoring-cvs/scripts/cvt.py lint-skill --all   # skill authoring rules
```

Tests that need your real CV skip themselves when the file is missing. Set `GTJOB_SAMPLE_CV` to point them at another
CV. Trigger cases for the skill's description are in `evals/triggers.yaml`. Live evals that call the model need an
API key and are not part of the default test run.

If `uv` cannot write its cache in your sandbox, prefix commands with `UV_CACHE_DIR=.cache/uv`.
