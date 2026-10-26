# WP-FIX-1-3: Sync the approved WP-G1 contract change into the skill and the wave-1 test

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 1 (fix-up from WP-G1) | User approval of `plan/reports/WP-G1-contract-change.md` applied to `plan/contracts/`; WP-FIX-1-2 done (both edit `test_wave1.py`) | Sonnet (`cv-builder`) | XS |

**Do not start until the orchestrator confirms that the contract change was applied to `plan/contracts/`.**

## Goal

1. Make `assets/schemas/` byte-identical again to the edited `plan/contracts/*.schema.json`. This removes the sample
   candidate's PII from the skill package.
2. Remove the `--visual` allowlist entry from the wave-1 integration test, because section 3 now defines it.

## Context

- Read `plan/tasks/_COMMON.md` and `plan/reports/WP-G1-contract-change.md`.

## Owned files

- `.claude/skills/tailoring-cvs/assets/schemas/profile.schema.json`
- `.claude/skills/tailoring-cvs/assets/schemas/render-model.schema.json`
- `tests/integration/test_wave1.py` (only the `UNDOCUMENTED_FLAGS` constant and its comment)
- `plan/reports/WP-FIX-1-3.md`

## Do not touch

`plan/contracts/*` (the orchestrator applies it), and every other file.

## Steps

1. `cp plan/contracts/profile.schema.json plan/contracts/render-model.schema.json .claude/skills/tailoring-cvs/assets/schemas/`.
2. In `tests/integration/test_wave1.py`, set `UNDOCUMENTED_FLAGS = ()` and delete the two comment lines above it that
   explain the escalation.

## Acceptance criteria

```bash
diff -r plan/contracts .claude/skills/tailoring-cvs/assets/schemas | grep -v interfaces.md        # no output
git grep --untracked -i -c -E "morattab|arashmor" -- .claude/skills; test $? -eq 1 && echo "no PII in skill"   # prints: no PII in skill
uv run pytest -q tests/unit tests/integration                                                      # passes
```
