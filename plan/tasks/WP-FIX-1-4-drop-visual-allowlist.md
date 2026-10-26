# WP-FIX-1-4: Remove the `--visual` allowlist entry from the wave-1 integration test

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 1 (fix-up from WP-G1 re-gate 1) | WP-FIX-1-3 | Haiku (`cv-builder-lite`) | XS |

## Goal

WP-FIX-1-3 step 2 was not applied, although its report says it was. `tests/integration/test_wave1.py` still
allowlists `--visual`. The approved contract change (C2) now defines `--visual` in section 3 of
`plan/contracts/interfaces.md`, so the allowlist must be empty. While the entry stays, the test cannot catch
`--visual` being dropped from section 3.

The current text (around line 61) is:

```python
# Flags that the contract does not define yet. Each one is listed in plan/reports/WP-I1.md under ESCALATION.
# `--visual` is named by section 13 (critic packet) and by test_refs_writing; section 3 has no critic flags.
UNDOCUMENTED_FLAGS = ("--visual",)
```

## Context

- Read `plan/tasks/_COMMON.md`. You do not need to read any other file.

## Owned files

- `tests/integration/test_wave1.py` (only the three lines shown above)
- `plan/reports/WP-FIX-1-4.md`

## Do not touch

Everything else, including the rest of `test_wave1.py` and `plan/contracts/*`.

## Steps

1. Delete the two comment lines shown above.
2. Change `UNDOCUMENTED_FLAGS = ("--visual",)` to `UNDOCUMENTED_FLAGS: tuple[str, ...] = ()`.
3. Re-read the file region after you save it, and confirm that the edit is on disk before you write the report.

## Acceptance criteria

```bash
grep -n "UNDOCUMENTED_FLAGS = \|UNDOCUMENTED_FLAGS: " tests/integration/test_wave1.py   # one line, ending in "= ()"
grep -c -- '"--visual"' tests/integration/test_wave1.py                                 # 0
uv run pytest -q tests/integration/test_wave1.py -k flags                                # passes
uv run pytest -q tests/unit tests/integration                                            # passes (286)
```

Paste the output of all four commands verbatim in the report.
