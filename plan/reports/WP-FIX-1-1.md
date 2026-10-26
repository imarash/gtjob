# WP-FIX-1-1 report

## Summary
- `.gitignore`: `/out/`, `/profiles/`, `/dist/`, `/CVs/`, `/JDs/` are now anchored to the repo root. The synthetic JD fixtures under `tests/fixtures/jds/` are no longer ignored.
- `cli.py`: `_Parser.error` now raises a private `_UsageError(message, prog)`. `main` catches it and calls `output.fail` with `E_USAGE`. In `--json` mode stdout gets one envelope and stderr stays empty. Otherwise stderr gets the old human format with one hint (`run \`<prog> --help\``).
- `probe.command` is set to the first non-flag token when it names a registered command, otherwise `""`.
- With `--json` and no command, `main` returns an `E_USAGE` "no command given" envelope. Without `--json` it still prints help on stderr and exits 2.
- `return 130` is replaced by the `EXIT_INTERRUPTED` module constant.
- `tests/unit/test_foundation.py` has 8 new tests: 4 parametrized `--json` usage cases, command-name probing, the human usage error, `.gitignore` anchoring, and `git check-ignore` effects.

## Files changed
- `.gitignore`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/cli.py`
- `tests/unit/test_foundation.py`
- `plan/reports/WP-FIX-1-1.md`

## Acceptance (logs in `.cache/logs/WP-FIX-1-1/`)
1. `uv run pytest -q tests/unit/test_foundation.py` (`a1.log`)
   ```
   30 passed in 1.50s
   ```
2. `for p in out/x CVs/x JDs/x profiles/x tests/fixtures/private/x; do git check-ignore -q $p || echo "NOT ignored: $p"; done`: no output.
3. `git check-ignore tests/fixtures/jds/junior-devops-engineer.md; echo "exit=$?"`: `exit=1`
4. `git status --porcelain --untracked-files=all tests/fixtures/jds | wc -l`: `5`
5. `uv run .../cvt.py --json validate-artifact; echo "exit=$?"`
   ```
   {"ok":false,"command":"validate-artifact","exit_code":2,"run":"","stage":"","data":{},"messages":[],"next_action":"run `cvt validate-artifact --help`","error":{"id":"E_USAGE","message":"the following arguments are required: RUN, NAME","hint":"run `cvt validate-artifact --help`"}}
   exit=2
   ```
6. `uv run pytest -q tests/unit tests/integration` (`a6.log`)
   ```
   286 passed in 2.59s
   ```

## Deviations
None.

## Open issues
None.
