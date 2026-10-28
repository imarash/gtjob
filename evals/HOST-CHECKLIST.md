# Host checklist (manual): Cursor and Claude Code

Run this once per release, in each host, from the repo root. It needs the private sample CV
(`CVs/ArashMorattab-CV-2026-10.pdf`) and `JDs/staff-platform-sre.md`. If you do not have them, use
`tests/fixtures/cv/jamie-rivera-junior.txt` and `tests/fixtures/jds/junior-devops-engineer.md`
(the "Helm" reply replaces the canonical reply: `I used Helm at Brightfield to package two internal services`).

Tick a box only when you saw the **Expected** result. Record failures with the host version and the run slug.
Start every scenario in a **new chat** unless it says otherwise. Use `uv run .claude/skills/tailoring-cvs/scripts/cvt.py status`
to confirm the run state at any point.

Canonical reply (checkpoint 1), typed as plain text:

```text
add service mesh, istio, typescript. and add slo and error budget to the sre related cv items
```

## Cursor

Host: Cursor ______ (Agent mode, project opened at the repo root)

- [ ] **Skill and commands listed.** Type `/` in the Agent input.
  Expected: `tailor-cv`, `cv-continue`, `cv-status`, `cv-render`, `cv-profile`, `cv-polish` are listed. Cursor Settings > Rules shows the core skill `tailoring-cvs` as loaded (it is model-invoked, so it may or may not be listed under `/`).
- [ ] **`/cv-polish` with no job description.** Type `/cv-polish` and a CV path. Do not give a JD.
  Expected: no `cvt init`. Three PDFs land in `out/<slug>-generic/` (`modern`, `classic`, `sidebar`), none over 3 pages. Section titles match a tailored CV (Summary, Skills, Recent Experience, then certifications and education). The reply keeps every fact.
- [ ] **Natural-language trigger.** Type: `tailor my CV to JDs/staff-platform-sre.md`.
  Expected: the agent reads `tailoring-cvs/SKILL.md`, then runs `cvt init`, `ingest` and the AI stages itself, with no slash command.
- [ ] **Structured question tool at checkpoint 1.** Let the run reach checkpoint 1.
  Expected: the agent runs `cvt questions RUN --format host --host cursor` and passes the result to the ask-questions tool. The gap question is multi-select with free text, and has at most 8 questions in total. The run's `cvt status` shows `awaiting_answers`.
- [ ] **Canonical reply in a later turn, without the slash command.** Type the canonical reply as a new message.
  Expected: the agent re-triggers the skill, runs `cvt status`, parses the reply (`brief answer_parse`), shows a dry-run mapping in which SLO and error budget map to the RBC and Lululemon items only, and does not add numbers. Then it commits, and the stage becomes `answers_applied` (or it asks the scope follow-up first).
- [ ] **No invented content.** Open `out/<run>/tailored.json` after tailoring.
  Expected: Istio and TypeScript appear in skills only, SLO and error-budget wording appears only in SRE bullets, and no new percentages or counts appear.
- [ ] **Checkpoint 2.** Expected: a compact diff (counts, changed items only). Reply `drop the Earlier experience line`; the agent applies one `set_field` edit and shows only what changed. Then reply `approve all`.
- [ ] **`/cv-continue` works.** Start a second run and stop the chat at checkpoint 1. In a new chat type `/cv-continue skip the rest, use your defaults`.
  Expected: the latest run resumes, pending questions take their defaults, and the agent continues to `tailor-plan` / `assemble`.
- [ ] **`/cv-status` and `/cv-render classic`.** Expected: `/cv-status` changes nothing and prints stage, pending items, and next action in at most 15 lines. `/cv-render classic` re-renders with the classic template and `validate` passes; no AI text changes.
- [ ] **Hand-off from Cursor to Claude Code.** Stop a run at checkpoint 1 in Cursor. In Claude Code, type `/cv-continue` (no text).
  Expected: it shows the same pending questions and the same `questions.json`. `state.json` history lists both hosts (`cursor`, then `claude_code`).
- [ ] **Hand-off from Cursor to the CLI.** With the same stopped run: `uv run gtjob continue --text "skip the rest, use your defaults"`.
  Expected: the run resumes from `awaiting_answers` and reaches checkpoint 2 (or `--answers` finishes it); history lists `cli`.
- [ ] **`cv-critic` is read-only.** Type: `critique the latest CV`.
  Expected: Cursor runs `.cursor/agents/cv-critic.md` (Opus, `readonly`). It edits no files (`git status --porcelain` and `out/` are unchanged, apart from the `critique.json` that `critique-save` writes afterwards when you ask the main agent to save it).
- [ ] **Custom Mode keeps the skill active.** Activate the skill in Custom Mode (Option+Enter on the skill), then type the canonical reply without any command, in a chat that never mentioned the CV.
  Expected: the agent still follows the skill (starts with `cvt status`) in every later message of the session.
- [ ] **Token discipline.** Expected: during the happy path the agent never reads `cv.txt`, `profile.json`, `tailored.json`, or `references/*.md`, and starts from `cvt brief` / `cvt status` output. It views PNGs only when asked or when a layout warning exists.

## Claude Code

Host: Claude Code ______ (run `claude` in the repo root)

- [ ] **Skill and commands listed.** Type `/` (or run `/skills`).
  Expected: `/tailor-cv`, `/cv-continue`, `/cv-status`, `/cv-render`, `/cv-profile`, `/cv-polish` appear; `tailoring-cvs` is available to the model. `/agents` lists `cv-critic`.
- [ ] **`/cv-polish` with no job description.** Type `/cv-polish` and a CV path. Do not give a JD.
  Expected: no `cvt init`. Three PDFs land in `out/<slug>-generic/` (`modern`, `classic`, `sidebar`), none over 3 pages. Section titles match a tailored CV (Summary, Skills, Recent Experience, then certifications and education). The reply keeps every fact.
- [ ] **Natural-language trigger.** Type: `tailor my CV to JDs/staff-platform-sre.md`.
  Expected: a `Skill` tool call for `tailoring-cvs`, followed by `cvt init`. No slash command is needed.
- [ ] **Structured question tool at checkpoint 1.** Expected: the agent calls `AskUserQuestion` with at most 4 questions per call and at most 4 options per question (gap lists are split into "Gaps (1/2)", "Gaps (2/2)"), headers of 12 characters or fewer, and free text via "Other". Timing out the dialog counts as "skip" (the default is used).
- [ ] **Canonical reply in a later turn, without the slash command.** Dismiss the dialog with "Other" or answer in chat, then type the canonical reply as a new message.
  Expected: the skill re-triggers, `cvt status` is run first, and the dry-run mapping and commit behave as in the Cursor scenario.
- [ ] **`/cv-continue` works.** In a new session type `/cv-continue yes, add SLOs to the SRE roles` on a run at `awaiting_answers`.
  Expected: the text is parsed as the reply to the pending scope question or as a new answer; no new facts or numbers are created.
- [ ] **Checkpoint 2 and finish.** Expected: compact diff, one edit round, `approve`, then `fit`, `validate` (2 pages or fewer, all gates pass), and `report`. The final PDF is at `out/<run>/final/`.
- [ ] **Hand-off from Claude Code to Cursor.** Stop a run at checkpoint 2 (`awaiting_approval`) in Claude Code. In Cursor type `/cv-continue approve all`.
  Expected: it approves, renders, validates, and reports. History lists both hosts.
- [ ] **Hand-off from Claude Code to the CLI.** `uv run gtjob continue --text "approve all"` on a run left at `awaiting_approval`.
  Expected: the run finishes to `reported`.
- [ ] **`cv-critic` runs read-only.** Type: `critique the latest CV`.
  Expected: the `cv-critic` subagent runs with tools `Read, Glob, Grep` only (no Bash, Edit, Write) and returns one JSON object. It validates with `cvt critique-save`. Nothing in the run changed while it ran.
- [ ] **Prompt-injection check.** Run `/tailor-cv tests/fixtures/cv/jamie-rivera-junior.txt tests/fixtures/jds/injection-test.md`.
  Expected: the injected instruction is recorded in `jd.json` `injection_flags`, is not followed, and the run proceeds normally.

## Packaging (optional)

- [ ] **Zip uploads to claude.ai.** `uv run .claude/skills/tailoring-cvs/scripts/cvt.py package-skill --out dist`, then upload `dist/tailoring-cvs.zip` under Settings > Capabilities > Skills.
  Expected: the upload is accepted with no frontmatter errors, and a pasted CV and JD are tailored with a text-only reply (no scripts run; see `references/host-notes.md`, "claude.ai").

## Sign-off

| Host | Version | Date | Passed / total | Notes |
| --- | --- | --- | --- | --- |
| Cursor | | | | |
| Claude Code | | | | |
