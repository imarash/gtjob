# WP-FIX-3-8: The `shape:` line must not contradict the schema for numeric enums

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 (fix-up from WP-G3 re-gate 1) | WP-FIX-3-1 | Haiku (`cv-builder-lite`) | S |

## Goal

WP-FIX-3-1 added `shape: <skeleton>` to every AI-stage packet. Enums render as one string, `"a|b|c"`, which is right
for string enums but wrong for integer enums: the tailor shape shows `"priority":"1|2|3|4|5"`, the jd shape
`"weight":"1|2|3|4|5"`, and the answer_parse shape `"checkpoint":"1|2"`. No packet line explains the notation. A model
that copies the shape writes `"priority":"1"`. At the re-gate, `validate-artifact … tailor-plan` rejected exactly
that ("'1' is not of type 'integer'"), and the same for `jd` with `"weight":"5"`. Wave 4's CLI sends packets as the
whole prompt, so the shape must be safe to copy.

## Context

- Read `plan/tasks/_COMMON.md`.
- `cvtlib/briefs.py`: `_skeleton` (the `enum` branch near `SHAPE_ENUM_SEP`), `schema_skeleton`, and `_render` (the
  `shape = [...]` line near `show_shape`).
- Schemas through `cvtlib.schemas`; do not hard-code paths.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/briefs.py`
- `tests/unit/test_briefs.py`
- `plan/reports/WP-FIX-3-8.md`

## Steps

1. In `_skeleton`, an `enum` whose values are all integers renders as the **bare integer** of its first value (for
   example `1`). String enums keep the `"a|b|c"` form. Mixed enums keep the string form.
2. In `_render`, directly after the `shape:` line (only when it is printed), add one fixed line from a module-level
   constant:
   `shape key: "" = text, 0 = integer, false = boolean, "a|b" = write exactly one of a or b, [x] = a list of x.`
   It is part of the fixed Output block, so trimming never removes it.
3. Tests in `test_briefs.py`:
   - The tailor shape has `"priority":1` (an int after `json.loads`), the jd shape has `"weight":1`, and the
     answer_parse shape has `"checkpoint":1`. String enums (for example jd `source.kind`) still read `"file|text|url"`.
   - Every packet with a `shape:` line has the `shape key:` line right after it; the fix packet without a shape has
     neither.
   - The existing shape, budget, determinism, and trimming tests still pass. If a stage no longer fits its budget,
     report it; do not edit `budgets.json` (not owned).

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_briefs.py tests/unit/test_assemble.py     # passes
uv run pytest -q tests/integration/test_wave3.py                           # passes (no budget warnings)
uv run pytest -q tests/unit tests/integration                              # passes
```

In the report, paste the `shape:` and `shape key:` lines of the `tailor` packet for the junior golden run.
