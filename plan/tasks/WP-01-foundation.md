# WP-01: Foundation (packaging, cvtlib core, run state, schema copies)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 1 | Wave 0 contracts | Sonnet (`cv-builder`) | L (~450 lines incl. tests) |

## Goal

Create the Python skeleton that every later WP builds on: the root `pyproject.toml`, `.gitignore`,
the skill folder skeleton, the `cvt.py` entry point with auto-discovered commands, the `cvtlib`
core modules (`errors`, `paths`, `jsonio`, `schemas`, `state`, `output`, `cli`), the
`validate-artifact` command, byte-identical schema copies, and the shared test harness.

## Context

- Read `plan/tasks/_COMMON.md` first.
- Contracts: `plan/contracts/interfaces.md` sections 1-6 (conventions, layout, command table, exit codes and
  envelope, the WP-01 API block in section 5, and the lifecycle in section 6), plus all `plan/contracts/*.schema.json`.
- The core skill must stay self-contained and zip-uploadable: nothing in `.claude/skills/tailoring-cvs/`
  may import from `src/gtjob/`. The CLI imports the skill, never the reverse.
- Scripts run via `uv run .claude/skills/tailoring-cvs/scripts/cvt.py`, so `cvt.py` needs PEP 723 inline
  metadata, and `scripts/` must be importable (`cvtlib` sits next to `cvt.py`).

## Owned files

- `pyproject.toml`, `uv.lock`, `.gitignore`
- `src/gtjob/__init__.py`, `src/gtjob/_skill.py`, `src/gtjob/cli.py` (stub only)
- `.claude/skills/tailoring-cvs/LICENSE.txt`
- `.claude/skills/tailoring-cvs/scripts/cvt.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/{__init__,errors,paths,jsonio,schemas,state,output,usage,cli}.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/commands/__init__.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/commands/artifacts.py`
- `.claude/skills/tailoring-cvs/assets/schemas/*.schema.json` (15 copies)
- `tests/conftest.py`, `tests/unit/test_schemas.py`, `tests/unit/test_foundation.py`, `tests/unit/test_state.py`
- `plan/reports/WP-01.md`

## Do not touch

`plan/contracts/*`, `.claude/skills/tailoring-cvs/SKILL.md`, `references/`, `assets/` other than `assets/schemas/`, `CVs/`, `JDs/`.

## Steps

1. `pyproject.toml`: project `gtjob`, version `0.1.0`, `requires-python = ">=3.11"`, src layout with the
   `hatchling` build backend (`[tool.hatch.build.targets.wheel] packages = ["src/gtjob"]`). Dependencies:
   `anthropic>=2.3`, `jsonschema>=4.23`, `pypdf>=6.0`, `typst>=0.15`, `pyyaml>=6.0`. Optional extra
   `web = ["fastapi>=0.110", "uvicorn>=0.29", "python-multipart>=0.0.9", "jinja2>=3.1", "httpx>=0.27"]`. Dependency group
   `dev = ["pytest>=8.0"]`. Script entry `gtjob = "gtjob.cli:main"`. Pytest config:
   `testpaths = ["tests"]` and `markers = ["live: needs network or API key", "sample: needs the private sample CV"]`.
   Run `uv lock` once.
2. `.gitignore`: `out/`, `profiles/`, `.cache/`, `dist/`, `CVs/`, `JDs/`, `tests/fixtures/private/`,
   `evals/results/`, `__pycache__/`, `*.pyc`, `.venv/`, `.pytest_cache/`, `.DS_Store`.
3. `LICENSE.txt`: MIT license text for the skill code, with copyright "gtjob contributors". Add a final
   paragraph saying the fonts under `assets/fonts/` are under the SIL Open Font License 1.1 (see the
   `OFL.txt` files).
4. `cvt.py`: the PEP 723 block (`requires-python = ">=3.11"`, dependencies `jsonschema>=4.23`, `pypdf>=6.0`,
   `typst>=0.15`), then `sys.path.insert(0, str(Path(__file__).resolve().parent))`, then
   `raise SystemExit(cvtlib.cli.main())`. If a dependency import fails, print
   `cvt: error[E_DEPENDENCY]: ...` with the hint `run with: uv run <path>/cvt.py ...`, and exit 3.
5. `cvtlib/errors.py`, `paths.py`, `jsonio.py`, `schemas.py`, `output.py`: implement exactly the signatures
   in interfaces.md section 5 (WP-01 block). Requirements:
   - `paths.SKILL_ROOT` resolves from `__file__`.
   - `slugify` ASCII-folds with `unicodedata` (`"Staff Platform & Reliability"` → `staff-platform-reliability`).
   - `new_run_slug` uses a `today` parameter, to keep tests deterministic.
   - `schemas.validate` uses `Draft202012Validator` with `FormatChecker`, and returns
     `"$.path: message"` strings sorted by path.
   - `output.emit` prints the human text, or the JSON envelope (section 4) when `args.json` is set,
     and returns the exit code.
   - `output.fail` prints the human error format to stderr, or the envelope with `ok: false`.
6. `cvtlib/state.py`:
   - Implement the WP-01 API.
   - `STAGES` and `ARTIFACT_STAGE` come exactly from section 6.
   - `current_host()`: the env var `GTJOB_HOST` if it is one of the enum values, else
     `importlib.import_module("cvtlib.hostdetect").detect()` if that module exists (WP-08 adds it in wave 2), else
     `"unknown"`. `add_history` stamps every entry with it and updates `options.host`.
   - `next_action_for` uses the section 6 table. `{cvt}` renders as
     `uv run .claude/skills/tailoring-cvs/scripts/cvt.py` and `{run}` as the slug.
   - `create_run`:
     - Computes the slug with `paths.new_run_slug` (stem rules in section 2).
     - Creates `out/<slug>/inputs/` and copies the CV as `inputs/cv.<ext>`.
     - Writes the JD to `inputs/jd.md`. For `url` with no text yet, it writes a file containing only
       the URL line `<!-- jd-url: ... -->`, and `ingest` fetches later.
     - Computes the SHA-256 of both stored files and validates the options.
     - Writes `state.json` at stage `initialized`, with empty `ingest` (`method: none`) and checkpoints
       `not_started`.
   - `save` always validates against the `state` schema before writing. An invalid state raises
     `CvtError(INTERNAL, "E_STATE_INVALID")`.
7. `cvtlib/cli.py`:
   - `main(argv)` builds an `argparse` parser with a global `--json`. It is accepted before or after the subcommand:
     add it to a shared parent parser used by every subparser, with `default=argparse.SUPPRESS` on the subparser
     copy so it does not overwrite the global value. Test both positions.
   - Discovers every module in `cvtlib/commands/` (`pkgutil.iter_modules`) and calls its
     `register(subparsers)`.
   - Dispatches to `args.func(args)`, catches `CvtError` (→ `output.fail`) and unexpected exceptions
     (→ exit 7, with the traceback written to `.cache/cvt-last-error.txt`).
8. `commands/artifacts.py`:
   - `validate-artifact RUN NAME [--file PATH]` validates `out/<run>/<NAME>.json`, or the given file,
     against the named schema.
   - Exits 0 with `data.valid=true`, or 1 with violations (code `schema`).
   - Never changes state.
9. Copy every `plan/contracts/*.schema.json` byte-for-byte into `assets/schemas/`.
10. `src/gtjob/_skill.py`: `ensure_path()` inserts `<repo>/.claude/skills/tailoring-cvs/scripts` into
    `sys.path`. It locates the repo through `GTJOB_HOME`, else by walking up from `__file__`.
    `src/gtjob/cli.py`: a `main()` stub that prints "gtjob CLI not implemented yet (WP-22)" and returns 7.
11. Tests:
    - `tests/conftest.py`:
      - Puts the skill `scripts/` dir on `sys.path`.
      - Fixture `workspace(tmp_path, monkeypatch)` sets `GTJOB_HOME` to a temp dir and returns it.
      - Fixture `sample_cv_path` returns `$GTJOB_SAMPLE_CV` or `CVs/ArashMorattab-CV-2026-10.pdf`, and
        skips if missing.
      - Fixture `run_cvt(*args) -> CompletedProcess` runs `sys.executable cvt.py ...` with cwd = workspace.
    - `test_schemas.py`:
      - All 15 schemas pass `check_schema`.
      - Structured-output lint: every object closed, `required` equals the property keys, no type
        arrays, no forbidden keywords (`minLength`, `maxLength`, `minimum`, `maximum`, `multipleOf`,
        `oneOf`, `not`, `if`, `patternProperties`), and `minItems` only 0/1.
      - Each `assets/schemas` file is byte-identical to its `plan/contracts` file.
    - `test_foundation.py`: `slugify`, `new_run_slug` collisions, `dump_json` atomic and hash,
      `resolve_run("latest")`, the error envelope format, `validate-artifact` exit codes.
    - `test_state.py`: `create_run` layout, `next_action` per stage, the staleness cascade, `cascade=False`,
      `require_artifact` with stale artifacts, and the invalid-state guard.

## Token-efficiency requirements (interfaces.md section 14)

- `output.py`:
  - Enforce the terse-output rules from section 4: `MAX_HUMAN_LINES = 15` and `MAX_LIST_ITEMS = 10`, with a
    `+N more (use --all)` line.
  - Add a global `--all` (same parent-parser technique as `--json`) that lifts the caps.
  - The `--json` envelope is minified (`separators=(",", ":")`).
- `jsonio.dump_json` pretty-prints for humans. Add `jsonio.append_jsonl(path, obj)` (atomic append of one minified
  line) for `usage.jsonl`.
- `usage.py` (`record_usage`, `usage_totals`, section 5): the one place that writes and sums `usage.jsonl`, so
  `status` (WP-08), `report` (WP-19), `brief` (WP-29), and `gtjob` (WP-21/22) share it. Test with a synthetic file
  holding packet and API lines.
- `schemas.SCHEMA_NAMES` includes `profile-map` and `tailor-plan` (15 schemas). `ARTIFACT_STAGE` includes
  `profile_map`, `digest`, `tailor_plan`. `usage` has no stage and is never marked stale.
- `state.next_action_for` uses the section 6 templates exactly (they now route every AI stage through `cvt brief`).
- Tests:
  - Human output is truncated at the caps, and `--all` lifts them.
  - The JSON envelope is one line.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_schemas.py tests/unit/test_foundation.py tests/unit/test_state.py   # all pass
uv run .claude/skills/tailoring-cvs/scripts/cvt.py --help                                           # lists validate-artifact
uv run .claude/skills/tailoring-cvs/scripts/cvt.py --json validate-artifact nope jd; echo "exit=$?"  # JSON envelope, ok:false, exit=4
diff -r plan/contracts .claude/skills/tailoring-cvs/assets/schemas | grep -v interfaces.md            # no output except "Only in plan/contracts: interfaces.md"
git check-ignore -q out/x CVs/x JDs/x profiles/x tests/fixtures/private/x && echo ignored             # prints: ignored
uv run python -c "import gtjob._skill as s; s.ensure_path(); import cvtlib.state; print('ok')"        # prints: ok
```

## Definition of done

The common definition of done in `_COMMON.md`, plus: no other module needs to touch `cli.py` to add a
command.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-01.md` under `## ESCALATION`. Do not change it.
