# WP-20: Private golden run for the sample CV and JD (AI stages done by the worker)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 4 | Waves 1-3 (all checks and guides) | Sonnet (`cv-builder`) | XL (mostly generated JSON; split into Part A and Part B if needed) |

## Goal

Act as the AI stages yourself, following the skill's own guides. Produce a complete, validated golden
run for the real sample CV and the staff-platform-SRE JD, including the canonical exchange and every
interaction case. These goldens let the e2e tests (WP-25, WP-26) exercise the whole pipeline
deterministically, with no API.

## Context

- Read `plan/tasks/_COMMON.md`, then the core skill (`.claude/skills/tailoring-cvs/SKILL.md`) and the references it
  points to. Follow them exactly, as a host agent would. This WP also tests the guides: record every place a guide
  was unclear in the report under `## Guide feedback`.
- Inputs: `CVs/ArashMorattab-CV-2026-10.pdf` and `JDs/staff-platform-sre.md`, both git-ignored. All outputs go to
  `tests/fixtures/private/sample/` (git-ignored, because they contain personal data). Use `run_id`
  `golden-sample`.
- The expected profile ID map is in `plan/tasks/WP-03-text-fixtures.md`. Your profile must produce exactly those
  IDs, because the expectations depend on them.
- The interaction expectations are in `tests/fixtures/expected/interaction-cases.yaml`.

## Owned files

- `tests/fixtures/private/sample/**` (everything below)
- `tests/fixtures/private/README.md`
- `plan/reports/WP-20.md`

## Steps

### Part A (profile, JD, match, questions)

1. Create a real run:
   `uv run .claude/skills/tailoring-cvs/scripts/cvt.py init --cv CVs/ArashMorattab-CV-2026-10.pdf --jd JDs/staff-platform-sre.md --slug golden-sample`,
   then `ingest`.
2. `cvt brief profile` → write `out/<run>/profile-map.json` → `cvt profile-build` (fix only the reported ranges
   until it exits 0). Copy `profile-map.json` and the built `profile.json` to `tests/fixtures/private/sample/`.
3. `jd.json` per `stage-jd.md` → `cvt jd-check`. Then `match.json` per `stage-match.md` → `cvt match-check`. Then
   `questions.json` per `checkpoint-questions.md` → `cvt questions --format chat`, and save the rendered text as
   `questions.chat.txt`. The gap question must match the canonical assistant message in substance.
4. Copy each validated artifact into `tests/fixtures/private/sample/`.

### Part B (answers, tailoring, edits, variants)

5. Parse `tests/fixtures/answers/staff-platform-sre.checkpoint1.txt` per `answer-parsing.md` →
   `answers.canonical.round.json`. Then `cvt answers-apply --dry-run` (save the output as
   `dryrun.canonical.txt`), write `followups.json`, `cvt questions --add followups.json`, `--commit`. Then parse
   `tests/fixtures/answers/case-followup-skip.txt` → `answers.followups-skip.round.json` → commit.
6. `cvt brief tailor` → `tailor-plan.json` → `cvt assemble` (exit 0; at most 2 `brief fix` rounds). Required
   content:
   - Istio and TypeScript in skills.
   - SLO/error-budget wording only in the RBC/Lululemon bullets, citing `att-004`/`att-005`.
   - No invented numbers.
   - An "Earlier experience" line.
7. `cvt diff` (save as `diff.md`). Write `edits.approve-all.json`, apply it, then `cvt approve`, `cvt fit --png` (PNGs only for this golden),
   `cvt validate`, `cvt report`. Save `fit.json`, `validation.json`, `report.md`, and `pages/` (PNG) here. The
   result must be exactly 2 pages with every gate passing.
8. Variant rounds, each validated by `cvt answers-apply --dry-run` against a copy of the run made before step 5:
   - `answers.rejection.round.json` (`case-rejection.txt`)
   - `answers.correction.round.json` (`case-correction.txt` → correction on `exp-5`)
   - `answers.ambiguous.round.json` (`case-ambiguous-scope.txt` → unresolved scope)
   - `edits.drop-earlier.json` (`case-edit-earlier.txt` → `set_field include_earlier_experience=false`), validated
     with `cvt apply-edits` on a copy of the approved run.
9. Second JD: `init` a second run with `tests/fixtures/jds/ai-llm-platform-engineer.md` (slug `golden-second`).
   - `profile-cache --lookup` must hit.
   - Write `second/jd.json` (→ `jd-check`).
   - Write `second/questions.naive.json`, which deliberately includes a gap choice for service mesh.
   - Save the output of `cvt questions` showing the suppression as `second/questions.suppressed.txt`.
10. `tests/fixtures/private/README.md`: what each file is, and how to regenerate it.

If you run low on context after Part A, finish Part A, write the report with `## STATUS: PART A DONE`, and stop.
The orchestrator dispatches Part B as `WP-20B` with this same brief.

## Token-efficiency requirements (interfaces.md section 14)

- You are the AI for this run, so work exactly as a host agent would. Get each stage's context with
  `cvt brief <stage> RUN` and write only what it asks for:
  - `profile-map.json`, built with `cvt profile-build`.
  - `tailor-plan.json`, built with `cvt assemble`.
  - Do not Read `cv.txt` or other artifacts directly unless a packet tells you to.
- Copy `profile-map.json` and `tailor-plan.json` into `tests/fixtures/private/sample/` as well. WP-25 replays them.
- In your report, list each packet's `est_tokens` against its budget, from `usage.jsonl`. Any packet over budget is
  a finding for the guides or budgets; do not trim the packets yourself.
- Do the second JD (`JDs/` file other than the staff one; pick `tanisha-systems` or the first extra JD) as a
  new-JD run on the cached profile:
  - Confirm the profile-cache hit.
  - Confirm the seed plan offer (score printed by `brief tailor`).
  - Record the total packet tokens for the new-JD run.

## Acceptance criteria

```bash
ls tests/fixtures/private/sample/{profile,jd,match,questions,tailored,fit,validation}.json
for f in profile jd match questions tailored fit validation; do uv run .claude/skills/tailoring-cvs/scripts/cvt.py validate-artifact golden-sample $f --file tests/fixtures/private/sample/$f.json || exit 1; done
uv run .claude/skills/tailoring-cvs/scripts/cvt.py --json status golden-sample | grep -q '"stage": "reported"' && echo reported
python3 -c "import json;v=json.load(open('tests/fixtures/private/sample/validation.json'));print(v['passed'])"   # True
git status --porcelain tests/fixtures/private | wc -l    # 0 (ignored)
```

## Definition of done

The common definition of done. The report embeds page-1 and page-2 PNGs and lists the guide feedback.

## Escalation

If a guide or contract seems wrong, stop and report it in `plan/reports/WP-20.md` under `## ESCALATION`. Do not
change it. Guide edits belong to a fix-up WP.
