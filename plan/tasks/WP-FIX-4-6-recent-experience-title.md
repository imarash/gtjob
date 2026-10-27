# WP-FIX-4-6: the experience section is titled "Recent Experience"; make tests, validator and docs agree

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 4 (fix-up from WP-G4, user decision) | WP-12, WP-FIX-4-5 | Haiku (`cv-builder-lite`) | XS |

## Goal

The user changed `SECTION_TITLES["experience"]` in `.claude/skills/tailoring-cvs/scripts/cvtlib/render.py` from
"Experience" to "Recent Experience" on purpose (uncommitted edit; keep it, do not revert it). Two tests now fail
because of it:

- `tests/unit/test_render.py::test_markdown_has_sections_and_bullets` expects `## Experience` in the markdown.
- `tests/unit/test_validate.py::test_layout_orphan_heading_names_the_page` expects an orphan "EXPERIENCE" heading to
  produce a `warn` from `validate._layout_gate`; it now passes with no violation.

Make the code, tests and docs agree on the new title.

## Context

- Read `plan/tasks/_COMMON.md`.
- `validate._layout_gate` and how it finds section headings (it probably matches the model's section titles,
  upper-cased). If it matches against `render.SECTION_TITLES` or the model, the real fix may be in the test's fake page
  text ("RECENT EXPERIENCE"). If the gate hard-codes "EXPERIENCE", make it use the title from the render model so the
  two cannot drift.
- Search for other places that hard-code the old title: `grep -rn "Experience" tests/unit tests/integration
  .claude/skills/tailoring-cvs/references README.md docs` (ignore "Earlier experience" and prose uses).

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/validate.py` (only the heading match, if it needs a change)
- `tests/unit/test_render.py`, `tests/unit/test_validate.py`
- Any doc line that names the section "Experience" as a rendered heading (`README.md`, `docs/*.md`)
- `plan/reports/WP-FIX-4-6.md`

Do not edit `render.py`.

## Acceptance

```bash
uv run --no-sync pytest -q tests/unit/test_render.py tests/unit/test_validate.py
uv run --no-sync pytest -q tests/unit tests/integration
```

Both must pass with no failures. Report which of the three options (test text, validator, docs) you changed.
