# WP-FIX-3-5: SKILL.md commands that work in zsh, and the profile cache gets stored

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 (fix-up from WP-G3) | WP-18, WP-I3 | Haiku (`cv-builder-lite`) | S |

## Goal

Two defects in the core skill's instructions:

1. **`$CVT` fails in zsh.** `SKILL.md` line 40 and `references/commands.md` line 3 say
   `CVT="uv run .claude/skills/tailoring-cvs/scripts/cvt.py"`, then run `$CVT status`. zsh (the macOS default and
   the shell Cursor uses) does not split an unquoted variable, so it fails with exit 127: "no such file or directory:
   uv run …". Some hosts also keep no shell variables between tool calls.
2. **The profile cache is never written.** No workflow step or `next_action` runs `cvt profile-cache RUN --store`.
   At the gate, a second run on the same CV missed the cache, which defeats interfaces.md 14.2 and Token rule 8.

## Owned files

- `.claude/skills/tailoring-cvs/SKILL.md`
- `.claude/skills/tailoring-cvs/references/commands.md`
- `plan/reports/WP-FIX-3-5.md`

## Steps

1. `SKILL.md` "Running the scripts": replace the `CVT=...` code block with a sentence and a code line. Keep `$CVT` as
   the notation in the examples, because `tests/integration/test_wave3.py` parses `$CVT <cmd>` examples:
   - Say that `$CVT` below stands for `uv run .claude/skills/tailoring-cvs/scripts/cvt.py`, and that each command
     must be typed with that prefix written out (do not store it in a shell variable: zsh does not split it, and
     some hosts drop variables between calls).
   - Show one example line: `uv run .claude/skills/tailoring-cvs/scripts/cvt.py status`.
2. `SKILL.md` workflow, second checklist line: after `$CVT profile-build RUN`, add `then $CVT profile-cache RUN --store`.
3. `references/commands.md` line 3: the same change as step 1 (no `CVT=` assignment; state the prefix).
4. Keep the `SKILL.md` body ≤ 150 lines. Add no new flags beyond interfaces.md section 3 (`--store` is listed).

## Acceptance criteria

```bash
uv run .claude/skills/tailoring-cvs/scripts/cvt.py lint-skill --all                                # exit 0
uv run pytest -q tests/unit/test_skillcheck.py tests/integration/test_wave3.py tests/integration/test_wave1.py   # passes
rg -n 'CVT=' .claude/skills/tailoring-cvs/SKILL.md .claude/skills/tailoring-cvs/references/commands.md   # no matches
rg -n 'profile-cache RUN --store' .claude/skills/tailoring-cvs/SKILL.md                            # 1 match
wc -l .claude/skills/tailoring-cvs/SKILL.md                                                       # body ≤ 150
```
