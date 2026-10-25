# WP-24: User documentation (root README, privacy notes)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 4 | Waves 1-3 | Haiku (`cv-builder-lite`; re-dispatch to `cv-builder` on PARTIAL) | S |

## Goal

Write the user-facing docs: how to tailor a CV in Cursor, in Claude Code, and from the terminal; how runs
resume across hosts; what is stored where; and how personal data is handled.

## Context

- Read `plan/tasks/_COMMON.md`.
- Sources:
  - `plan/PLAN.md`, sections "Host integration" and "Key decisions".
  - interfaces.md sections 2, 3, 11, and 12.
  - The real `SKILL.md` and wrappers (WP-18).
- The `README.md` is at the repo root. A `README.md` inside the skill folder is forbidden.

## Owned files

- `README.md` (root; replace the current placeholder)
- `docs/privacy.md`
- `docs/troubleshooting.md`
- `plan/reports/WP-24.md`

## Steps

1. `README.md`, with these sections:
   - What it does.
   - Quick start in Cursor (put files in `CVs/` and `JDs/`, type `/tailor-cv`, answer the questions, approve;
     Custom Mode tip).
   - Quick start in Claude Code (`claude`, then `/tailor-cv`).
   - Quick start in the CLI (`uv run gtjob tailor --cv ... --jd ...`, with `--auto` and `--answers` examples).
   - Resuming (`/cv-continue`, `gtjob continue`).
   - Templates (with the PNG previews from `.cache/test-artifacts`, if the user copies them into `docs/img/`;
     otherwise describe them).
   - Truthfulness guarantees (in plain words).
   - Where files live (`out/`, `profiles/`, `final/`).
   - Packaging for claude.ai.
   - Running tests and evals.
2. `docs/privacy.md`:
   - What is sent to which provider in each mode (the IDE host's model provider; the Anthropic API in the CLI).
   - That Skills API and claude.ai uploads are not ZDR-covered, while the skill zip has no personal data.
   - What is git-ignored, the cache locations, and how to delete a person's data (`rm -r profiles/<slug> out/*`).
   - Recruiter PII in pasted JDs.
3. `docs/troubleshooting.md`: Typst missing (exit 3), a scanned PDF (exit 5), a sandbox uv cache error
   (`UV_CACHE_DIR=.cache/uv`), provenance violations (how to answer or attest), page overflow with priority-1
   content, and the Claude Code question dialog timing out.

## Acceptance criteria

```bash
test -s README.md && grep -q "/tailor-cv" README.md && grep -q "gtjob tailor" README.md && echo ok
ls .claude/skills/tailoring-cvs/README.md 2>/dev/null && echo "FORBIDDEN" || echo "no skill README"
```

## Definition of done

The common definition of done.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-24.md` under `## ESCALATION`. Do not change it.
