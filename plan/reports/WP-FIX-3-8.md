# WP-FIX-3-8 report: shape line must not contradict the schema for numeric enums

## Summary

- Integer enums now render as a bare integer in `shape:` (the first value, for example `1`). Previously they rendered as `"1|2|3|4|5"`, which made a copying model write `"1"` and fail the schema.
- String enums keep the `"a|b|c"` form, and mixed enums keep the string form.
- Every packet that prints a `shape:` line now prints the fixed `shape key:` line directly after it. The line comes from the module-level constant `SHAPE_KEY_LINE`. It sits in the Output block, so trimming never removes it.
- The fix packet prints neither line unless the failure is a schema error (`$`-prefixed violation), which is the same condition that already gated the shape.
- Added 5 tests to `tests/unit/test_briefs.py`. No other file was touched.

## Files changed

- `.claude/skills/tailoring-cvs/scripts/cvtlib/briefs.py`: `SHAPE_KEY_LINE` constant; integer-enum branch in `_skeleton`; docstring of `schema_skeleton`; `_render` emits the key line after `shape:`.
- `tests/unit/test_briefs.py`: new tests for integer enums, string enums, key-line placement, and fix packets with and without schema errors.
- `plan/reports/WP-FIX-3-8.md`: this report.

## Acceptance commands

1. `UV_CACHE_DIR=.cache/uv uv run pytest -q tests/unit/test_briefs.py tests/unit/test_assemble.py`
   - Log: `.cache/logs/WP-FIX-3-8/briefs-assemble.log`
   - Result: `114 passed in 1.78s` (exit 0)

2. `UV_CACHE_DIR=.cache/uv uv run pytest -q tests/integration/test_wave3.py`
   - Log: `.cache/logs/WP-FIX-3-8/wave3.log`
   - Result: `8 passed in 14.33s` (exit 0), no budget warnings

3. `UV_CACHE_DIR=.cache/uv uv run pytest -q tests/unit tests/integration`
   - Log: `.cache/logs/WP-FIX-3-8/full.log`
   - Result: `1019 passed, 1 skipped in 60.45s` (exit 0)

## Tailor shape for the junior golden run

Captured from the junior golden fixture (`_make_run` in `test_briefs.py`) with a throwaway probe outside the repo:

```
schema: tailor-plan
shape: {"schema_version":"1","seed_run":"","emphasis":"","headline":{"text":"","source_refs":[""]},"summary":{"text":"","source_refs":[""]},"skills":[{"label":"","priority":1,"items":[{"name":"","source_refs":[""]}]}],"experience":[{"profile_id":"","priority":1,"intro":{"mode":"none|keep|rewrite","text":"","source_refs":[""]},"bullets":[{"op":"keep|rewrite|merge|attested","from":[""],"text":"","extra_refs":[""],"priority":1}],"engagements":[{"profile_id":"","priority":1,"bullets":[{"op":"keep|rewrite|merge|attested","from":[""],"text":"","extra_refs":[""],"priority":1}]}]}],"earlier_experience":{"include":false,"profile_ids":[""]},"certifications":[{"profile_id":"","short_name":"","priority":1}],"education":[{"profile_id":"","include_details":false}],"talking_points":[{"text":"","source_refs":[""]}],"omitted":[{"profile_id":"","reason":""}],"open_items":[{"kind":"confirm_placeholder|gap|source_issue|unconfirmed_suggestion","text":"","item_ids":[""]}]}
shape key: "" = text, 0 = integer, false = boolean, "a|b" = write exactly one of a or b, [x] = a list of x.
```

`"priority":1` is an integer. The string enums (`"mode"`, `"op"`, `"kind"`) keep the pipe form.

## Deviations

- None from the brief's steps. The `shape key:` line is emitted only when `shape:` is printed. The brief said "directly after the shape line (only when it is printed)", so this matches.

## Open issues

- The 1 skipped test in the full run is outside this WP's files. I did not investigate it. It is most likely the sample-CV or private-fixture skip described in `_COMMON.md`.
- The shape key line adds about 35 tokens to every AI packet. No budget warnings appeared in the wave-3 integration run or in `test_stage_packet_builds_and_fits_budget`, so `budgets.json` was not touched.
