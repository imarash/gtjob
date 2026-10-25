# WP-10: Profile tools (verify, renumber, source issues, cache, merged view, JSON Resume export)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 | WP-01 (uses WP-04 fixtures) | Sonnet (`cv-builder`) | M-L |

## Goal

Make the AI-produced `profile.json` trustworthy and reusable:

- Renumber IDs canonically.
- Prove every text is verbatim from `cv.txt`.
- Add deterministic source issues.
- Cache verified profiles by CV hash, so later runs skip parsing.
- Expose a merged view that applies active corrections.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: `profile.schema.json`, `attestations.schema.json` (read-only here; the writer is WP-11), interfaces.md
  section 1 (IDs), section 2 (profile store), section 3 (`profile-cache`, `profile-verify`, `profile-show`,
  `export-jsonresume` rows), section 5 (WP-10 block, implemented here as `profile.py` and `profile_store.py`), and
  section 8 (`item_text` semantics, merged view).
- Read attestations by loading `paths.attestations_path(slug)` with `jsonio.load_json`. Do not import WP-11's
  `attestations.py`, which is being written in parallel. A missing store means no attestations.
- Fixtures: `tests/fixtures/cv/jamie-rivera-junior.txt` and `tests/fixtures/golden/junior/profile.json` (WP-04).

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/profile.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/profile_store.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/commands/profile.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/profile_map.py`
- `tests/unit/test_profile.py`, `tests/unit/test_profile_map.py`
- `plan/reports/WP-10.md`

## Steps

1. `normalize_text`:
   - NFKC, then map curly quotes to straight and all dash variants (– — ‐ −) to `-`.
   - Strip the glyphs listed in `ingest.DECORATIVE_GLYPHS`. Import it if WP-09 is present, otherwise use a local
     constant with the same value and a comment that it must match.
   - Collapse whitespace and lowercase only for comparison purposes (keep two functions:
     `normalize_text` and `comparable`).
2. `normalize_ids`:
   - Renumber `sum-N`, `exp-N`, `exp-N.eK`, `exp-N(.eK).bM`, `edu-N`, `cert-N`, `skl-N`, `oth-N`, and `iss-N` in
     document order.
   - Rewrite `source_issues[].item_ids` through an old → new map, and return the map.
3. `verify_verbatim`: for every text-bearing field (summary text, highlight text, work/engagement summary,
   education text, certificate name, skill keywords, names, role labels, and `date_text`), `comparable(field)`
   must be a substring of `comparable(cv_text)`. Each failure is a violation with code `fact_mismatch`, its
   `item_id`, and a message quoting the first 80 chars.
4. `script_source_issues(profile, cv_text, today)`. Each check yields an issue with `origin: script`. Before adding
   them, replace any previous issues with `origin: script`, so that reruns are idempotent. The checks:
   - Overlapping or touching work date ranges, with severity `info` for touching (same boundary month) and `warn`
     for overlaps of 2 months or more.
   - Education end date inside a full-time work range, or two degrees with the same year.
   - Missing `email`, `phone`, or `location`, as one `missing_contact` issue listing the fields.
   - Contact present only in repeated header text: if the email's only occurrences are in lines that also
     contain the name, record it as info.
   - Stale "Updated: <Mon YYYY>" lines older than 6 months relative to `today`.
   - Skills languages missing compared with summary text: for example, the summary names a language that is
     absent from skills.
5. `item_text(profile, item_id)` and `iter_items` as specified. `merged_view(profile, attestations)` applies
   **active** correction attestations (field replacement on the target item) and returns a deep copy.
6. `profile_store.lookup(cv_sha256)` scans `profiles/*/profile.<sha12>.json`. `store(run_dir)` copies the
   verified profile into `profiles/<person>/profile.<sha12>.json`, and creates an empty `attestations.json` if
   none exists (`next_seq: 1`).
7. Commands:
   - `profile-verify RUN`:
     - Load, validate the schema, renumber, verify verbatim, add script issues, and write back.
     - Record the artifact, and set `person_slug` in state. Stage → `profiled` on success.
     - Exit 1 on violations, listing all of them.
   - `profile-cache RUN --lookup|--store`: `--lookup` is a hit when the cached profile's `cv_sha256` equals the
     run's CV hash. On a hit, copy the profile to `profile.json`, set the state stage, and set `data.hit: true`.
   - `profile-show RUN|--person P [--merged]`: a compact human summary (employers → engagements with role labels,
     counts, source issues) plus attestations (id, claim, status, scope).
   - `export-jsonresume RUN`: maps to JSON Resume (`basics`, `work` with `highlights` as strings, where each
     engagement becomes its own `work` entry named "Client — Employer"; `education`; `certificates`; `skills`).
8. Tests, on the junior golden and synthetic mutations:
   - A tampered text → `fact_mismatch`.
   - Shuffled IDs → canonical numbering.
   - Overlap detection, both touching and real overlaps.
   - Idempotent script issues.
   - Cache store/lookup round trip.
   - The merged view applies only active corrections.
   - JSON Resume export shape.
   - A `sample` test that runs `profile-verify` on the private golden
     `tests/fixtures/private/sample/profile.json`. This file arrives in WP-20, so skip if it is absent.

## Token-efficiency requirements (interfaces.md section 14)

- **`profile-build` (new; the normal path).** The AI writes `profile-map.json` (line ranges) instead of retyping the
  CV. Implement `cvtlib/profile_map.py` per interfaces.md section 5 (`numbered_cv`, `build_profile`) and
  `cvt profile-build RUN` in `commands/profile.py`. It validates the map, builds `profile.json` (verbatim text from
  ranges, canonical IDs, `basics.location` from city/region/country), runs `verify_verbatim` and
  `script_source_issues`, then saves, records `profile_map` and `profile`, and sets stage `profiled`.
- Violations (exit 1, capped list):
  - `range_error`: out of bounds, reversed, or overlapping.
  - `unmapped_line`: a non-blank line is neither covered nor ignored. Show the line number and the first 60
    characters.
  - `not_verbatim`: a typed name, employer, title, client, role label, certificate, or institution is not found in
    its cited lines (NFKC, case-insensitive).
- Skills: strip a leading `Label:` and split on `, ; | •` into keywords, trimming each.
- `numbered_cv` format: `f"{n:>4}| {line}"`, 1-based, blank lines included. `cvt brief profile` (WP-29) prints it.
- `profile-show` prints a compact outline (one line per item, at most 15 lines; `--all` lists everything).
- Tests:
  - The junior golden `profile-map.json` builds a profile equal to the golden `profile.json` (ignoring
    `created_at`).
  - Each violation kind is triggered by a synthetic mutation.
  - A 2-employer synthetic CV with an engagement and a tools line builds correctly.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_profile.py   # passes
```

## Definition of done

The common definition of done.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-10.md` under `## ESCALATION`. Do not change it.
