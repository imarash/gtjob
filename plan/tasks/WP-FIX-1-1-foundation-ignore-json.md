# WP-FIX-1-1: Anchor root .gitignore paths and always emit the --json envelope on usage errors

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 1 (fix-up from WP-G1) | WP-01 | Sonnet (`cv-builder`) | S |

## Goal

Fix two blocking foundation defects found by the wave-1 gate (`plan/reports/WP-G1.md`):

1. **`.gitignore` hides the synthetic JD fixtures.** The patterns `JDs/` and `CVs/` are unanchored. On macOS,
   `core.ignorecase=true` makes `JDs/` match `tests/fixtures/jds/`, so all five committed-by-design JD fixtures
   (`tests/fixtures/jds/*.md`, including the junior golden JD) are ignored and would never be committed. A fresh clone
   would then fail the test suite. Proof: `git check-ignore -v tests/fixtures/jds/injection-test.md` prints
   `.gitignore:6:JDs/`.
2. **`--json` usage errors print no envelope.** Section 4 says the `--json` envelope is "stdout, always a single JSON
   object". Today `cvt --json validate-artifact` (missing args), `cvt --json bogus` (unknown command), and `cvt --json`
   (no command) print only a human error on stderr. Stdout is empty, and the exit code is 2.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contract: `plan/contracts/interfaces.md` section 4. Extract it with `sed -n '/^## 4\./,/^## 5\./p' plan/contracts/interfaces.md`.
- Code: `.claude/skills/tailoring-cvs/scripts/cvtlib/cli.py` (`_Parser.error`, `main`), and `cvtlib/output.py`
  (`fail(args, err)`), which already builds the error envelope. Read `output.py`, but do not edit it.

## Owned files

- `.gitignore`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/cli.py`
- `tests/unit/test_foundation.py`
- `plan/reports/WP-FIX-1-1.md`

## Do not touch

`plan/contracts/*`, `cvtlib/output.py`, and every other file.

## Steps

1. `.gitignore`: anchor the root-only directories with a leading slash: `/out/`, `/profiles/`, `/dist/`, `/CVs/`,
   `/JDs/`. Keep `.cache/`, `__pycache__/`, `*.pyc`, `.venv/`, `.pytest_cache/`, and `.DS_Store` unanchored. Keep
   `tests/fixtures/private/` and `evals/results/` as they are, because a pattern with an inner slash is already
   anchored.
2. `cli.py`, usage errors:
   - Define a private exception, for example `class _UsageError(Exception)`, carrying `message` and `prog`.
   - Make `_Parser.error` raise it instead of printing and raising `SystemExit`.
   - In `main`, catch it around `parser.parse_args(argv)`. Return
     `output.fail(probe, CvtError(ExitCode.USAGE, "E_USAGE", message, hint=f"run `{prog} --help`"))`.
   - Set `probe.command` to the subcommand name when the first non-flag token in `argv` is a registered command.
     Otherwise use `""`.
   - Keep the `except SystemExit` path for `--help` (exit 0).
   - The human stderr text must keep the existing format, `cvt: error[E_USAGE]: <message>` followed by
     `  hint: run `<prog> --help``. This also removes today's duplicated hint (`cvt --help or cvt --help`).
3. `cli.py`, no command given: when `args.func` is missing and `--json` was passed, return
   `output.fail(probe, CvtError(ExitCode.USAGE, "E_USAGE", "no command given", hint="run `cvt --help` to list commands"))`.
   Without `--json`, keep the current behavior (help on stderr, exit 2).
4. `cli.py`: replace the literal `return 130` for `KeyboardInterrupt` with a named module constant.
5. `tests/unit/test_foundation.py`, add these tests and keep all existing ones passing:
   - For each of `["--json", "validate-artifact"]`, `["--json", "bogus"]`, `["--json"]`, and
     `["validate-artifact", "--json"]`: the return code is 2, stdout is exactly one line that parses as JSON with
     `ok == false`, `exit_code == 2`, and `error.id == "E_USAGE"`, and stderr is empty.
   - Without `--json`, `["validate-artifact"]` gives return code 2, empty stdout, and stderr starting with
     `cvt: error[E_USAGE]:`.
   - `.gitignore` anchors `CVs/`, `JDs/`, `out/`, `profiles/`, and `dist/` with a leading `/`. Parse the file and
     assert that the lines are exactly `/CVs/` and so on.
   - When `git` is on PATH and the repo root is a git work tree (otherwise `pytest.skip`):
     `git check-ignore -q <path>` exits 0 for each of `out/x`, `CVs/x`, `JDs/x`, `profiles/x`, and
     `tests/fixtures/private/x`. Use one path per call. It exits 1 for `tests/fixtures/jds/junior-devops-engineer.md`
     and `tests/fixtures/cv/jamie-rivera-junior.txt`.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_foundation.py                                    # passes
for p in out/x CVs/x JDs/x profiles/x tests/fixtures/private/x; do git check-ignore -q $p || echo "NOT ignored: $p"; done   # no output
git check-ignore tests/fixtures/jds/junior-devops-engineer.md; echo "exit=$?"     # exit=1
git status --porcelain --untracked-files=all tests/fixtures/jds | wc -l           # 5
uv run .claude/skills/tailoring-cvs/scripts/cvt.py --json validate-artifact; echo "exit=$?"   # one JSON line, E_USAGE, exit=2
uv run pytest -q tests/unit tests/integration                                     # passes
```
