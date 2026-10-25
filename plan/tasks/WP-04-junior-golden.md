# WP-04: Synthetic junior CV and golden artifacts

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 1 | Wave 0 contracts | Sonnet (`cv-builder`) | M |

## Goal

Create a short, synthetic junior CV in plain text, with a matching junior JD and a complete set of
hand-authored golden AI-stage artifacts. These are committed, contain no real PII, and let every code WP
in waves 2-3 test against valid, interlinked data. They also prove that the pipeline generalizes and
can produce a 1-page CV.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: every schema in `plan/contracts/`, interfaces.md sections 1 (IDs), 7 (checkpoint protocol), and 8
  (truthfulness rules). Your goldens must satisfy section 8. Every tailored term and number must appear in
  the referenced profile text or attestation.
- You play the role of the AI stages yourself: write the JSON the stage guides would produce. The
  stage guides do not exist yet, so follow the schemas and the field descriptions in them.

## Owned files

- `tests/fixtures/cv/jamie-rivera-junior.txt`
- `tests/fixtures/jds/junior-devops-engineer.md`
- `tests/fixtures/golden/junior/profile-map.json`, `profile.json`, `jd.json`, `match.json`, `questions.json`, `answers.round.json`, `tailor-plan.json`, `tailored.json`, `edits-001.json`
- `tests/fixtures/golden/junior/README.md` (what each file represents)
- `tests/unit/test_junior_golden.py`
- `plan/reports/WP-04.md`

## Steps

1. `jamie-rivera-junior.txt`: an invented person, "Jamie Rivera", 40-60 lines:
   - Contact: invented email `jamie.rivera@example.com`, GitHub URL, and a city.
   - A 2-line summary.
   - Experience: 2 roles (Junior DevOps Engineer at "Brightfield Logistics", 2024-present; IT Support Intern at
     "Cedar Valley College", 2023). Give each 3-5 bullets with a few numbers.
   - Skills: 3 groups. Education: a BSc in 2023. Certifications: 1 (AWS Cloud Practitioner).
   - Include one deliberate source issue: a role date that overlaps education by 2 months.
2. `junior-devops-engineer.md`: an invented company posting with 6 must-haves and 3 nice-to-haves, including one
   requirement Jamie lacks (for example Helm).
3. Golden artifacts. Use `run_id: "golden-junior"` and `person_slug: "jamie-rivera"`, with real SHA-256
   values (compute them with `shasum -a 256`):
   - `profile-map.json` (what the AI writes): line ranges into `jamie-rivera-junior.txt`, 1-based. Every non-blank
     line is covered exactly once or listed in `ignored_lines`. Keep the CV free of form feeds and decorative glyphs so
     `cvt ingest` leaves its lines unchanged (WP-09 guarantees that for clean text).
   - `profile.json` (what `profile-build` must produce from the map):
     - Every `text` is the verbatim text of its ranges (leading bullet marker stripped, wrapped lines joined with one
       space).
     - Canonical IDs follow interfaces.md section 1.
     - `source_issues` includes the overlap, with `origin: ai`.
   - `jd.json`: requirements `req-1..`, with weights and keywords; `noise` lists the posting boilerplate.
   - `match.json`:
     - Every requirement appears exactly once.
     - Every evidence `quote` is a substring of its ref's text.
     - The Helm requirement has `strength: none`.
   - `questions.json`: 3 pending checkpoint-1 questions (a gap multi-select including Helm, one metric
     question, one strategy question with a template choice), each with a default.
   - `answers.round.json`: a round answering the gap with "I used Helm at Brightfield to package two internal
     services". It should yield one `attest` item: type skill, placement `skills_and_bullets`, scope `items`
     `[exp-1]`, terms `["Helm"]`, detail "packaged two internal services".
   - `tailor-plan.json` (what the AI writes): `op: keep` for unchanged bullets (empty `text`), at least two
     `rewrite`, one `attested` bullet with `extra_refs: [att-001]`, and skills with empty `source_refs`.
   - `tailored.json` (what `assemble` must produce from the plan):
     - `page_target: 1`, `template: modern`.
     - Bullets for both roles, with `source_refs`.
     - One rewritten bullet cites the Helm attestation as `att-001`, because the store would assign that ID.
     - Priorities 1-5; every `review` is `pending`.
     - `earlier_experience.include: false`.
     - `talking_points`: 2 items.
   - `edits-001.json`: a checkpoint-2 batch with one `replace_text` (with `source_refs`), one `reject`, and one
     `approve_all`.
4. `test_junior_golden.py`:
   - Validates every golden against its schema, using `jsonschema` directly, so there is no dependency on
     later WPs.
   - Checks that every profile `text` occurs in the normalized CV text (NFKC plus collapsed whitespace).
   - Checks that the map's ranges are in bounds and non-overlapping, cover every non-blank line (or are ignored),
     and that joining each highlight range gives the matching `profile.json` text, in order.
   - Checks that the plan and `tailored.json` line up one-to-one, in order: `keep` bullets have the profile text
     verbatim; written bullets have identical text and `source_refs = from + extra_refs`.
   - Checks that every match `quote` occurs in its ref's text.
   - Checks that every tailored `source_refs` entry exists in the profile or equals `att-001`.
   - Checks that the SHA values match the files.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_junior_golden.py   # passes
```

## Definition of done

The common definition of done. The data is fully synthetic.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-04.md` under `## ESCALATION`. Do not change it.
