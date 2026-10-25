# WP-29: Stage packets (`brief`), `assemble`, budgets

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 | WP-10, WP-11, WP-13 | Sonnet (`cv-builder`) | L |

## Goal

Make every AI stage cheap and deterministic to set up:

- `cvt brief <stage>` prints a **stage packet**: the only context a model needs for that stage, inside a fixed token
  budget.
- `cvt assemble` turns the AI's small `tailor-plan.json` into a full `tailored.json`. Scripts copy every fact
  (employers, titles, dates, kept bullets, certifications, education), so the AI never retypes them.

Together with `profile-build` (WP-10), these two pieces carry the token-efficiency design.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts. Read only these sections of interfaces.md:
  - Section 13 (the stage table and the fix loop).
  - Section 14 (all of it; it is normative for this WP).
  - Section 5, the WP-29 block (signatures), plus the WP-10, WP-11, and WP-13 blocks you call.
  - Section 3, the `brief` and `assemble` rows.
  - Section 6, the `next_action` templates that mention `brief` or `assemble`.
  - Schemas: `tailor-plan`, `tailored`, `match`, `jd`, `answers`, `questions`.
- Use these functions from earlier WPs: `profile.merged_view`, `profile.item_text`, `profile.iter_items`,
  `attestations.load_store`, `scope.resolve`, `lexicon.supports` and `lexicon.synonyms`, `provenance.check_tailored`,
  and `profile_map.numbered_cv`.
- Guides (`references/*.md`, WP-05/06/07) start with `## Core`. `guide_core` extracts that section. If a guide
  lacks Core (wave-1 drift), raise `CvtError(VALIDATION, "E_GUIDE_NO_CORE")`. Do not fall back to the whole file.
- Use the junior golden run (`tests/fixtures/golden/junior/`) for tests. It includes `tailor-plan.json`, and the
  plan must assemble to exactly the golden `tailored.json`.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/briefs.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/assemble.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/commands/brief.py` (`brief`, `assemble`)
- `.claude/skills/tailoring-cvs/assets/budgets.json`
- `tests/unit/test_briefs.py`, `tests/unit/test_assemble.py`
- `plan/reports/WP-29.md`

## Steps

1. `assets/budgets.json`: `{"chars_per_token": 3.8, "core_max_lines": 60, "seed_min_score": 0.6,
   "max_fix_attempts": 2, "excerpt_chars": 240, "outline_excerpt_chars": 80, "stages": {"<stage>": {"input":
   N, "output": N}}}` with the section 14.4 values. For `profile`, `input` covers only the non-CV part.
2. `briefs.estimate_tokens` and `guide_core`. Core is the text from `## Core` up to the next `## ` heading. Warn
   (do not fail) when it is over `core_max_lines`.
3. `briefs.profile_digest(profile, attestations, jd, budget)` uses the section 14.3 format exactly.
   - Relevance: the sum, over JD requirements, of `weight × hits`, where hits counts the requirement's keywords and
     synonyms found by `lexicon.supports`. Multiply by 1.5 when the item's end date is within 5 years. Add 2 when an
     active attestation's resolved scope covers the item.
   - Fill order: all work and engagement header lines first (always), then highlights by descending relevance until
     the budget is reached. Hidden bullets get `(+N bullets hidden; cvt brief <stage> RUN --item ID)` on their
     parent line. Then skills, then attestations (always, one line each).
   - Deterministic: ties break by profile order. With `jd=None` (no JD yet), use profile order.
4. `briefs.prematch`: for each requirement, the top 5 items by hits, with the matched terms.
5. `briefs.similar_runs`: scan `out/*/state.json` for the same `person_slug` with `jd.json`, excluding the current
   run.
   - Score: weighted Jaccard over requirement keywords (must = 2, nice = 1).
   - Set `approved` when that run's checkpoint 2 is approved.
   - Return the list sorted by score, descending.
6. `briefs.build_brief(stage, run_dir, *, reply, full, item)` produces Markdown in this fixed layout:
   1. `# Stage: <stage> (run <slug>)`.
   2. A 3-line preamble: the untrusted-input rule, the output path and schema, and the check command.
   3. `## Rules`: the Core section(s) named in section 13 (plus Details and Examples with `--full`).
   4. `## Inputs`: the stage inputs in section 14.3 formats, CV/JD text wrapped in `<untrusted_document>`.
   5. `## Output`: the file path, the schema name, the check command, and the "patch, don't regenerate" note on
      `fix`.

   Per-stage specifics:
   - `profile`: `numbered_cv(cv.txt)`.
   - `jd`: the line-numbered `jd.txt`. **JD cache:** if an earlier run of any person has the same `jd_sha256` and a
     checked `jd.json`, copy it, print `cache hit: jd.json copied from <run>`, and set `data.cache_hit`. Exit 0
     with `next_action` = `jd-check`.
   - `match`: the JD digest, the profile digest (match budget), prematch, and the attestations. Write `digest.txt`
     on first use.
   - `questions`: the gaps (requirements with partial/none strength), the source issues, the item header lines, the
     role labels, and the attestations.
   - `answer_parse`: the pending questions (one line each: ID, type, prompt, choices `id=label`), the reply
     (required; exit 2 without it), item headers and role labels, and the attestations.
   - `tailor`: the JD digest, `digest.txt` (re-filled to the tailor budget, with every item that has a strong or
     partial match in full), match strengths, an answers summary, the attestations, and **Seed** (the compact
     `tailor-plan.json` of the best approved similar run with score ≥ `seed_min_score`, else omitted).
   - `change_request`: the tailored outline (IDs + 80-character excerpts), the reply, and the full text of every ID
     the reply names, matched by `t-...` ID, by employer or client name, or by `[N]` diff index.
   - `fix`: read the last failing check from `state.errors[-1]` and `validation.json`/the command record, list at
     most 10 violations, and include only the offending items (from each violation's `item_id`). It also contains
     the failed stage's Core `Rules` lines only, and the attempt counter. On attempt > `max_fix_attempts`, print
     `stop: show these violations to the user` and exit 1.
   - `critic`: the tailored outline, the JD digest, and a validation summary. No images.

   Other behavior:
   - `--item ID` prints only that item's full text (any stage) and records no stage.
   - Over budget: trim in the section 14.4 order (hidden bullets, then seed, then excerpts). If the packet is still
     over budget, append a `budget` warning line. Never trim Rules, must-have requirements, attestations, or the
     reply.
   - Save the packet to `out/<run>/briefs/<stage>.md` and print it to stdout. `--json` puts the packet in
     `data.packet` with `data.est_tokens`; this is the one documented exception to "data never embeds whole
     artifacts".
   - Call `usage.record_usage` (WP-01) with `kind: packet`.
7. `assemble.assemble(plan, profile, attestations, jd, state)`:
   - Header: comes from `profile.basics`. `headline` is from the plan, and `source_refs` is `[basics]` plus the
     plan refs.
   - Target: from `jd.title`, `jd.company`, and the `state.options` `page_target` and `template`, plus
     `plan.emphasis`.
   - Summary: `plan.summary`.
   - Skills: for each item with empty `source_refs`, resolve it to the skill groups and highlights where
     `lexicon.supports(name, text)` holds, then to attestations whose `terms` include it. If none, add a violation
     `skill_unsupported`.
   - Experience: employer, location, title, and dates come from the profile entry. `intro.mode` is `keep`
     (verbatim summary), `rewrite` (plan text), or `none`.
   - Bullets:
     - `keep`: verbatim `item_text(from[0])`, with origin `kept`. Plan `text` must be empty.
     - `rewrite`: plan text, origin `rewritten`.
     - `merge`: plan text with at least 2 `from`, origin `merged`.
     - `attested`: plan text with at least 1 `extra_refs` `att-*`, origin `attested`.
     - `source_refs` is `from` + `extra_refs`.
   - Engagements: kind, name, and role_label come from the profile.
   - Certifications: the profile name, or `short_name` when it is a contiguous substring of the profile name.
   - Education: from the profile; `details` only when `include_details`.
   - `earlier_experience`: from the profile entries.
   - IDs: assign `t-...` IDs by tailored position (section 1). Set `review: pending` everywhere, or `auto` when
     `state.options.auto`.
   - Copy `talking_points`, `omitted`, and `open_items` from the plan.
   - Violations (code `plan_ref`): unknown IDs, a `keep` bullet with text, a `merge` with fewer than 2 `from`, an
     `attested` bullet with no active attestation in scope, or a `from` that is not a bullet of the referenced
     entry. Then run `provenance.check_tailored` on the result and return all violations together.
8. Commands:
   - `cvt brief STAGE [RUN] [--reply TEXT | --reply-file F] [--full] [--item ID]`.
   - `cvt assemble RUN [--draft]`:
     - Requires stage ≥ `answers_applied` (or `matched` when checkpoint 1 was skipped).
     - Validate `tailor-plan.json` against its schema, assemble, then write `tailored.json`.
     - It goes through the same versioning, renumbering, and history snapshot as `check-tailored`, and saves
       `validation.json`. Reuse the WP-13 command path; do not duplicate it.
     - Record `tailor_plan` and `tailored`.
     - On pass, stage `tailored` and `next_action` per section 6. On violations, exit 1 with at most 10 lines,
       ending with `cvt brief fix RUN`.
9. Usage: use `usage.record_usage` (WP-01). Do not write `usage.jsonl` any other way.
10. Tests:
    - `test_briefs.py`:
      - Every stage builds for the junior golden run and fits its budget (assert `est_tokens <= input`).
      - A synthetic 40-highlight profile triggers trimming with the hidden-bullet hints, and must-have requirements
        and attestations survive.
      - Deterministic output: two builds are byte-identical.
      - The JD cache hit copies `jd.json` and reports `data.cache_hit`.
      - The seed is included when the score is ≥ 0.6 and omitted otherwise (two synthetic runs).
      - The fix packet lists only the offending items.
      - Untrusted text is wrapped.
      - A guide without Core raises `E_GUIDE_NO_CORE`.
      - `usage.jsonl` gets one line per packet.
    - `test_assemble.py`:
      - The golden plan assembles to the golden `tailored.json` (ignoring timestamps).
      - Each `plan_ref` violation has its own mutation.
      - An unsupported skill.
      - An invented employer name inside a `rewrite` bullet is caught by the provenance rules (rule 2).
      - An `attested` bullet outside the attestation scope is rejected.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_briefs.py tests/unit/test_assemble.py     # passes
CVT=.claude/skills/tailoring-cvs/scripts/cvt.py
uv run "$CVT" --help | grep -E "brief|assemble"                             # both listed
```

## Definition of done

The common definition of done. The report lists each stage's packet size for the junior golden run, as estimated
tokens against the budget.

## Escalation

If the junior golden `tailored.json` disagrees with what the contract implies for the golden `tailor-plan.json`
(for example an ID or a header field), the fixture is wrong, not your code. List the exact differences in your
report under `## Fixture mismatches`, mark that test `xfail(reason="WP-I3 fixes fixture")`, and WP-I3 corrects the
fixture.


If a budget cannot be met on the junior golden without dropping must-have content, do not change
`budgets.json`. Report the measured sizes under `## ESCALATION`.
