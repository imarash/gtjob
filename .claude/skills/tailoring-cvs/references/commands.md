# `cvt` command reference

Run from the repo root as `uv run .claude/skills/tailoring-cvs/scripts/cvt.py <cmd>`; `$CVT` in this file stands for that
prefix. Type it out in full each time (do not assign it to a shell variable: zsh does not split it). Without `uv`:
`python3 .claude/skills/tailoring-cvs/scripts/cvt.py` (needs `jsonschema`, `pypdf`, `typst`).

`RUN` is a run slug, a run directory, or `latest` (the default where shown as `[RUN]`). Every command accepts
`--json` (one minified line: `ok`, `command`, `exit_code`, `run`, `stage`, `data`, `messages`, `next_action`,
`error`) before or after the subcommand, and `--all` to lift output caps (15 lines, 10 list items).

## Contents

- [Exit codes](#exit-codes)
- [Run setup and state](#run-setup-and-state): `init`, `status`, `ingest`
- [Profile](#profile): `profile-cache`, `profile-build`, `profile-verify`, `profile-show`, `export-jsonresume`
- [Analysis stages](#analysis-stages): `brief`, `validate-artifact`, `jd-check`, `match-check`
- [Checkpoint 1](#checkpoint-1): `questions`, `answers-apply`, `attest`
- [Tailoring and checkpoint 2](#tailoring-and-checkpoint-2): `assemble`, `check-tailored`, `diff`, `apply-edits`, `approve`
- [Render and deliver](#render-and-deliver): `render`, `fit`, `validate`, `critique-save`, `report`
- [Skill maintenance](#skill-maintenance): `lint-skill`, `package-skill`

## Exit codes

| Code | Name | Meaning |
| --- | --- | --- |
| 0 | OK | Success |
| 1 | CHECK_FAILED | Schema or gate violations: `brief fix`, patch, rerun (max 2) |
| 2 | USAGE | Bad arguments |
| 3 | MISSING_DEPENDENCY | Typst, pdftotext, pypdf, or jsonschema missing; follow the printed hint |
| 4 | STATE | Run not found, wrong stage, artifact missing or stale: `status`, follow `next_action` |
| 5 | INPUT | Unreadable, empty, or scanned input |
| 6 | AWAITING_USER | Questions or approval pending: ask, end the turn |
| 7 | INTERNAL | Bug: report the traceback path |

Errors print `cvt: error[E_ID]: message` and `  hint: ...` on stderr (in `--json`, the `error` object).

## Run setup and state

- `init --cv PATH` plus one of `--jd PATH`, `--jd-text TEXT`, `--jd-stdin`, `--jd-url URL`. Options:
  `--template modern|classic` (modern), `--auto`, `--draft`, `--page-target 1|2` (2), `--paper us-letter|a4`
  (us-letter), `--slug S`, `--host cursor|claude_code|cli|api|unknown`. Creates `out/<run>/`, `inputs/`,
  `state.json`. Stage → `initialized`. Exit 0, 2, 5.
  Example: `$CVT init --cv CVs/me.pdf --jd JDs/sre.md --template modern`
- `status [RUN] [--all]`: stage, pending questions, stale artifacts, `next_action`; `--all` lists every run.
  Writes nothing. Exit 0, 4.
- `ingest RUN`: extracts `cv.txt` and `jd.txt` from `inputs/`. Stage → `ingested`. Exit 0, 3, 5.

## Profile

- `profile-cache RUN --lookup | --store`: looks the CV SHA-256 up in `profiles/` (a hit sets `profile.json` and
  stage `profiled`; `data.hit` says which) or stores the built profile. Exit 0, 1, 4.
- `profile-build RUN`: builds `profile.json` from `profile-map.json` and `cv.txt` (verbatim text from line ranges,
  canonical IDs, script-found issues). Stage → `profiled`. Exit 0, 1, 4.
- `profile-verify RUN`: renumbers and re-checks `profile.json` after direct edits. Exit 0, 1, 4.
- `profile-show (RUN | --person P) [--merged]`: summary of the profile and attestations. No writes. Exit 0, 4.
- `export-jsonresume RUN`: writes `jsonresume.json`. Exit 0, 4.

## Analysis stages

- `brief STAGE [RUN]`: prints the stage packet. STAGE is `profile|jd|match|questions|answer_parse|tailor|
  change_request|fix|critic`. Options: `--reply TEXT` / `--reply-file F` (answer_parse, change_request), `--full`
  (append the guide's Details and Examples), `--item ID` (expand one item), `--visual` (critic: list page PNGs).
  Writes `briefs/<stage>.md`, `digest.txt`, `usage.jsonl`. `brief jd` may reuse a cached `jd.json`
  (`data.cache_hit`). Exit 0, 1, 4.
- `validate-artifact RUN NAME [--file PATH]`: schema-check one artifact (`profile`, `profile-map`, `jd`, `match`,
  `questions`, `answers`, `tailor-plan`, `tailored`, `edits`, `fit`, `validation`, `critique`). Exit 0, 1, 4.
- `jd-check RUN`: validates and normalizes `jd.json`. Stage → `jd_analyzed`. Exit 0, 1, 4.
- `match-check RUN`: validates `match.json` and recomputes coverage and quotes. Stage → `matched`. Exit 0, 1, 4.

## Checkpoint 1

- `questions RUN [--format chat|host|json] [--host cursor|claude_code] [--add FILE]`: validates `questions.json`,
  suppresses questions that active attestations already answer, renders them for the host. Stage →
  `awaiting_answers` (exit 6) or `answers_applied` when nothing is pending. `--add` appends follow-ups.
  Example: `$CVT questions latest --format host --host cursor`
- `answers-apply RUN`, with one of:
  - `--select q-N=CHOICE[,CHOICE]` (repeatable; `q-N=skip`) plus `--default-rest`: deterministic, no AI;
  - `--round FILE`: an `answers.round.json` from the `answer_parse` stage;
  - `--auto`: defaults only (no attestation);
  and `--dry-run` (print attestations and scope mapping) or `--commit`. Writes `answers.json`, `questions.json`,
  `attestations.json`. Exit 0 (stage `answers_applied`), 6 (follow-ups pending), 1, 4.
  Example: `$CVT answers-apply latest --select q-1=terraform --default-rest --dry-run`
- `attest list|show ID|revoke ID|activate ID (RUN | --person P)`: the durable attestation store. Confirm with the
  user before `revoke`. Exit 0, 1, 4.

## Tailoring and checkpoint 2

- `assemble RUN [--draft]`: builds `tailored.json` from `tailor-plan.json`, the merged profile, and attestations,
  then runs the `check-tailored` checks. Stage → `tailored`. Exit 0, 1, 4.
- `check-tailored RUN [--draft]`: re-checks `tailored.json` after edits; writes `validation.json` (pre-render
  gates) and history. Exit 0, 1, 4.
- `diff RUN [--against profile|previous] [--format md|json] [--full]`: compact by default (changed items with
  160-character excerpts, counts for kept items). Stage → `awaiting_approval` (auto mode: `approved`). Exit 0, 4.
- `apply-edits RUN FILE`: applies an `edits` file atomically (whole batch rejected on any violation); bumps the
  `tailored.json` version. Stage → `awaiting_approval`. Exit 0, 1, 4.
- `approve RUN [--all]`: requires no pending items; activates this run's proposed attestations. Stage → `approved`.
  Exit 0, 1, 4.

## Render and deliver

- `render RUN [--template T] [--density D] [--draft] [--png] [--ppi N] [--pages N[,N]]`: builds `build/`,
  `cv.pdf`, `cv.md`, `pages/`. `--pages` is view-only: rasterizes those pages of the existing PDF, changes no
  stage. Without Typst it writes `build/cv.typ` and `cv.md` and exits 3. Exit 0, 1, 3, 4.
  Example: `$CVT render latest --pages 2 --ppi 80`
- `fit RUN [--png]`: finds the density that meets the page target; writes `fit.json`. Stage → `rendered`.
  Exit 0, 1, 3, 4.
- `validate RUN [--draft]`: all gates (ATS text, page count, provenance, layout warnings); writes
  `validation.json` and `final/*.pdf`. Stage → `validated` on pass. Exit 0, 1, 4.
- `critique-save RUN FILE`: stores the critic's JSON as `critique.json`. Exit 0, 1, 4.
- `report RUN`: writes `report.md`. Stage → `reported`. Exit 0, 4.

## Skill maintenance

- `lint-skill [SKILL_DIR] [--wrapper] [--all]`: checks the authoring rules (default: the core skill; `--all`: core
  plus the five wrappers). Exit 0, or 1 with the violations listed.
- `package-skill [--out DIR]`: lints, then writes `DIR/tailoring-cvs.zip` (default `dist/`) for claude.ai or the
  Skills API, and re-reads it to verify the frontmatter. Exit 0, 1.
