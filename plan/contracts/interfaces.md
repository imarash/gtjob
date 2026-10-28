# Interfaces contract: `tailoring-cvs`

This file and the `*.schema.json` files next to it are the frozen Wave-0 contracts. Workers
implement against them exactly. If a contract looks wrong, stop and report (see
`plan/tasks/_COMMON.md`); never change a contract inside a WP.

## Contents

1. Conventions
2. Directory layout
3. `cvt` script commands
4. Exit codes, errors, output envelope
5. Python library API (`cvtlib`)
6. Run lifecycle and `state.json`
7. Checkpoint protocol (questions, answers, scopes, attestations)
8. Truthfulness rules (provenance validator)
9. Render, template data contract, and fit
10. Validation gates (ATS, coverage, leaks, typography)
11. Slash commands (Cursor and Claude Code)
12. `gtjob` CLI
13. AI stages: prompts, inputs, outputs (shared by IDE agents and the CLI)
14. Token efficiency (budgets, stage packets, output rules, model routing)

---

## 1. Conventions

**Schema conventions (structured-output compatible).** All contracts use a JSON Schema
2020-12 subset that the Claude API structured outputs accept, so the same file validates
locally and constrains API output:

- Every object has `additionalProperties: false` and lists every property in `required`.
- No nullable or union types. "Unknown/absent" is `""` (strings), `[]` (arrays), `false`.
- No `minLength`/`maxLength`/`minimum`/`maximum`; use `enum` or simple `pattern`. `minItems`
  only 0 or 1. Only local `$ref` into `$defs`; no recursion; no free-form maps (use arrays of
  named objects instead).
- Enum values are lowercase snake_case; compare case-insensitively when reading AI output.
- `schema_version` is the string `"1"` everywhere.
- Before sending a schema to the API, `cvtlib.schemas.api_schema()` drops `$schema` and `$id`.

**Field naming.** snake_case everywhere. JSON Resume compatibility is provided by
`cvt export-jsonresume` (lossless mapping), not by mixing naming styles.

**IDs.**

| Kind | Pattern | Example | Assigned by |
| --- | --- | --- | --- |
| Profile basics | `basics` | `basics` | AI, fixed |
| Profile summary | `sum-N` | `sum-2` | `profile-build` (array order of the profile map); renumbered by `profile-verify` after direct edits |
| Work (employer) | `exp-N` | `exp-2` | `profile-build` (array order) |
| Engagement | `exp-N.eK` | `exp-2.e4` (RBC) | `profile-build` (array order) |
| Highlight | `exp-N.bM`, `exp-N.eK.bM` | `exp-2.e4.b1` | `profile-build` (array order) |
| Education / cert / skills / other | `edu-N`, `cert-N`, `skl-N`, `oth-N` | `cert-3` | `profile-build` (array order) |
| Source issue | `iss-N` | `iss-1` | AI or script |
| Attestation | `att-NNN` (zero-padded, 3+ digits) | `att-004` | script only |
| JD requirement | `req-N` | `req-7` | AI |
| Question | `q-N` (unique per run, never reused) | `q-9` | script (`cvt questions --add` renumbers) or AI for the first batch |
| Tailored items | `t-` + profile-shaped suffix by tailored position | `t-exp-2.e4.b1`, `t-skl-1`, `t-sum` | `assemble`; renumbered by `check-tailored` |

Numbering is 1-based in CV reading order. `profile-verify` and `check-tailored` renumber IDs
canonically and rewrite all internal references consistently, so AI numbering slips are
harmless.

**Files.** JSON is UTF-8, 2-space indent, `ensure_ascii=False`, key order as produced,
trailing newline, written atomically (temp file + rename). Times are UTC ISO-8601 with `Z`,
seconds precision. Hashes are lowercase hex SHA-256; `sha12` is the first 12 characters.

**Working directory.** All commands run from the workspace root (the repo root), or with
`GTJOB_HOME=<root>` set. Paths stored in JSON are relative to the run dir unless noted.

---

## 2. Directory layout

```text
<repo>/
├── .claude/
│   ├── skills/
│   │   ├── tailoring-cvs/                  # core skill: portable, zip-uploadable, self-contained
│   │   │   ├── SKILL.md
│   │   │   ├── LICENSE.txt
│   │   │   ├── references/                 # stage guides (also the CLI's system prompts)
│   │   │   │   ├── commands.md  host-notes.md  generic-cv.md  style-guide.md  truthfulness.md
│   │   │   │   ├── stage-profile.md  stage-jd.md  stage-match.md  stage-tailor.md
│   │   │   │   └── checkpoint-questions.md  answer-parsing.md  change-requests.md  critic-rubric.md
│   │   │   ├── scripts/
│   │   │   │   ├── cvt.py                  # PEP 723 entry point: uv run .../scripts/cvt.py <cmd>
│   │   │   │   ├── polish_render.py        # generic CV: extract, then render every template
│   │   │   │   └── cvtlib/                 # library + commands/ (one module per command group)
│   │   │   └── assets/
│   │   │       ├── schemas/*.schema.json   # byte-identical copies of plan/contracts/*.schema.json
│   │   │       ├── templates/{common,modern,classic,sidebar}.typ  presets.json
│   │   │       ├── fonts/{source-sans-3,libertinus}/*.otf + OFL.txt   FONTS.md
│   │   │       └── lexicon/{tech-terms.txt,synonyms.json,common-words.txt,logistics-patterns.json}
│   │   ├── tailor-cv/SKILL.md              # thin wrappers (host-specific frontmatter allowed)
│   │   ├── cv-continue/SKILL.md
│   │   ├── cv-status/SKILL.md
│   │   ├── cv-render/SKILL.md
│   │   ├── cv-profile/SKILL.md
│   │   └── cv-polish/SKILL.md              # generic CV, no job description
│   └── agents/{cv-builder,cv-reviewer,cv-critic}.md      # Claude Code subagents
├── .cursor/agents/{cv-builder,cv-reviewer,cv-critic}.md  # Cursor subagents (take precedence in Cursor)
├── pyproject.toml                          # gtjob CLI package + dev deps (pytest)
├── src/gtjob/                              # CLI: wraps cvtlib, adds Anthropic API calls
├── tests/{unit,integration,e2e}/  tests/fixtures/{jds,cv,answers,golden,private}/
├── evals/                                  # live evals, judge rubric runner, trigger tests, host checklist
├── plan/                                   # this plan (contracts, tasks, reports, STATUS.md)
├── CVs/  JDs/                              # user inputs (git-ignored)
├── out/<run-slug>/                         # runs (git-ignored)
├── profiles/<person-slug>/                 # durable profile store (git-ignored)
├── .cache/                                 # uv and LLM caches (git-ignored)
└── dist/                                   # packaged skill zip (git-ignored)
```

**Run directory** `out/<run-slug>/`:

| Path | Artifact name | Producer |
| --- | --- | --- |
| `state.json` | (state) | `cvtlib.state` |
| `inputs/cv.<ext>`, `inputs/jd.md` | (inputs) | `cvt init` |
| `cv.txt`, `jd.txt` | `cv_txt`, `jd_txt` | `cvt ingest` |
| `profile-map.json` | `profile_map` | AI (profile packet) |
| `profile.json` | `profile` | `cvt profile-build`, or `cvt profile-cache --lookup` |
| `briefs/<stage>.md`, `digest.txt` | `digest` (digest only) | `cvt brief` |
| `usage.jsonl` | `usage` | `cvt brief`, `gtjob` API calls |
| `jd.json` | `jd` | AI + `cvt jd-check` |
| `match.json` | `match` | AI + `cvt match-check` |
| `questions.json` | `questions` | AI + `cvt questions` |
| `answers.round.json` (scratch) → `answers.json` | `answers` | AI + `cvt answers-apply` |
| `tailor-plan.json` | `tailor_plan` | AI (tailor packet) |
| `tailored.json`, `tailored.history/v<N>.json` | `tailored` | `cvt assemble`, `cvt apply-edits` |
| `edits/<NNN>.json` | `edits` | AI + `cvt apply-edits` |
| `fit.json` | `fit` | `cvt fit` |
| `build/render.json`, `build/cv.typ`, `build/*.typ` | `render_model`, `typst_source` | `cvt render` |
| `cv.pdf` | `pdf` | `cvt render` |
| `pages/page-<N>.png` | `pages_png` | `cvt render --png` |
| `cv.md` | `markdown_fallback` | `cvt render` (always; the only output when Typst is missing) |
| `validation.json` | `validation` | `cvt check-tailored`, `cvt validate` |
| `critique.json` | `critique` | cv-critic + `cvt critique-save` |
| `report.md` | `report` | `cvt report` |
| `final/<Name>-<Title>.pdf` | `final_pdf` | `cvt validate` (non-draft, all gates passed) |

**Profile store** `profiles/<person-slug>/`: `profile.<cv-sha12>.json` (verified profile, one
per distinct CV file) and `attestations.json` (schema `attestations`).

**Run slug**: `YYYYMMDD-<stem>` where `<stem>` is `--slug`, else `slugify(jd file stem)`, else
`slugify(first 6 words of the JD title line)` for pasted text/URLs, else `jd-<sha6>`. Collision
suffix `-2`, `-3`. The slug never changes after `init`. The final PDF name uses `jd.title`
(for example `final/Alex-Chen-Staff-Platform-Reliability-Engineer.pdf`); the company is
appended only when `jd.company` is non-empty.

---

## 3. `cvt` script commands

Invocation (from the workspace root):

```bash
uv run .claude/skills/tailoring-cvs/scripts/cvt.py <command> [args]   # preferred
python3 .claude/skills/tailoring-cvs/scripts/cvt.py <command> [args]  # if deps already installed
```

`cvt.py` carries PEP 723 metadata: `requires-python = ">=3.11"`, dependencies
`jsonschema>=4.23`, `pypdf>=6.0`, `typst>=0.15`. Every command accepts `--json` (machine
envelope, section 4), either before or after the subcommand (`cvt --json status` and `cvt status --json`
are equivalent). `RUN` is a run slug, a run directory path, or `latest` (default when
omitted where marked `[RUN]`).

| Command | Arguments | Reads | Writes | Stage effect | Exit codes | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| `init` | `--cv PATH` and one of `--jd PATH` / `--jd-text TEXT` / `--jd-stdin` / `--jd-url URL`; `--template modern\|classic\|sidebar` (modern); `--auto`; `--draft`; `--page-target 1\|2` (2); `--paper us-letter\|a4` (us-letter); `--slug S`; `--host cursor\|claude_code\|cli\|api\|unknown` | inputs | run dir, `inputs/`, `state.json` | → `initialized` | 0, 2, 5 | WP-08 |
| `status` | `[RUN]`; `--all` | `state.json`, `questions.json` | — | none | 0, 4 | WP-08 |
| `ingest` | `RUN` | `inputs/` | `cv.txt`, `jd.txt`, `state.ingest` | → `ingested` | 0, 3, 5 | WP-09 |
| `profile-cache` | `RUN` and `--lookup` or `--store` | store / `profile.json` | `profile.json` (lookup hit) / store file | lookup hit → `profiled` | 0 (hit or miss; `data.hit`), 1, 4 | WP-10 |
| `profile-build` | `RUN` | `profile-map.json`, `cv.txt` | `profile.json` (verbatim text from ranges, canonical IDs, script issues) | → `profiled` | 0, 1, 4 | WP-10 |
| `profile-verify` | `RUN` | `profile.json`, `cv.txt` | `profile.json` (renumbered, script issues added); used after direct edits to `profile.json` | → `profiled` | 0, 1, 4 | WP-10 |
| `profile-show` | `RUN` or `--person P`; `--merged` | profile, attestations | — | none | 0, 4 | WP-10 |
| `export-jsonresume` | `RUN` | `profile.json` | `jsonresume.json` | none | 0, 4 | WP-10 |
| `validate-artifact` | `RUN NAME` (`profile\|profile-map\|jd\|match\|questions\|answers\|tailor-plan\|tailored\|edits\|fit\|validation\|critique`); `--file PATH` | the file | — | none | 0, 1, 4 | WP-01 |
| `brief` | `STAGE [RUN]` where STAGE is `profile\|jd\|match\|questions\|answer_parse\|tailor\|change_request\|fix\|critic`; `--reply TEXT` / `--reply-file F` (answer_parse, change_request); `--full` (append the guide's Details and Examples); `--item ID` (expand one item); `--visual` (critic only: the packet also lists the `pages/page-N.png` files to attach, rendered at 80 ppi) | run artifacts, guides, budgets | `briefs/<stage>.md`, `digest.txt` (first match/tailor brief), `usage.jsonl` (packet size) | none | 0, 1 (`brief jd` reuses a cached `jd.json` → `data.cache_hit`), 4 | WP-29 |
| `jd-check` | `RUN` | `jd.json`, `jd.txt` | `jd.json` (normalized) | → `jd_analyzed` | 0, 1, 4 | WP-13 |
| `match-check` | `RUN` | `match.json`, `jd.json`, `profile.json`, attestations | `match.json` (coverage recomputed) | → `matched` | 0, 1, 4 | WP-13 |
| `questions` | `RUN`; `--format chat\|host\|json` (chat); `--host cursor\|claude_code`; `--add FILE` | `questions.json`, attestations | `questions.json` | → `awaiting_answers` if any pending, else `answers_applied` (cp1 skipped) | 0, 1, 4, 6 | WP-15 |
| `answers-apply` | `RUN` and `--round FILE` or `--select q-N=CHOICE[,CHOICE]` (repeatable; `q-N=skip`) with `--default-rest`, each with `--dry-run` or `--commit`; or `--auto`. `--select` builds a `host_tool` round deterministically (no AI) | round file, `questions.json`, profile, store | `answers.json`, `questions.json`, `attestations.json` | → `answers_applied` (no pending) or stays `awaiting_answers` | 0, 1, 4, 6 | WP-15 |
| `attest` | `list\|show ID\|revoke ID\|activate ID` with `RUN` or `--person P` | store | store | none | 0, 1, 4 | WP-11 |
| `assemble` | `RUN`; `--draft` | `tailor-plan.json`, merged profile, attestations, `jd.json` | `tailored.json` (then runs the `check-tailored` checks) | → `tailored` on pass | 0, 1, 4 | WP-29 |
| `check-tailored` | `RUN`; `--draft` | `tailored.json`, profile, attestations, `jd.json` | `tailored.json` (renumbered), `tailored.history/v<N>.json`, `validation.json` (pre-render gates) | → `tailored` on pass | 0, 1, 4 | WP-13 |
| `diff` | `RUN`; `--against profile\|previous` (profile); `--format md\|json` (md); `--full` (default output is compact: changed items only, 160-character excerpts, counts for kept items) | tailored, profile, history | — | → `awaiting_approval` (`cp2=pending`), or straight to `approved` in auto mode | 0, 4 | WP-16 |
| `apply-edits` | `RUN FILE` | edits file, tailored | `tailored.json` (version+1), history, `edits/NNN.json` | → `awaiting_approval` (or `approved` when the batch contains `approve_all` and nothing is pending) | 0, 1, 4 | WP-16 |
| `approve` | `RUN`; `--all` | tailored, store | `tailored.json`, `attestations.json` | → `approved` (`cp2=done`) | 0, 1, 4 | WP-16 |
| `render` | `RUN`; `--template T`; `--density D`; `--draft`; `--png`; `--ppi N` (110); `--pages N[,N]` (view-only: rasterize these pages of the existing `cv.pdf` to `pages/`, no rebuild, no stage change, no staleness) | tailored, `fit.json` | `build/`, `cv.pdf`, `cv.md`, `pages/` | → `rendered` when stage ≥ `approved` | 0, 1, 3, 4 | WP-12 |
| `fit` | `RUN`; `--png` | tailored | `fit.json`, render outputs | → `rendered` | 0, 1, 3, 4 | WP-14 |
| `validate` | `RUN`; `--draft` | everything above | `validation.json`, `final/*.pdf` | → `validated` on pass | 0, 1, 4 | WP-14 |
| `critique-save` | `RUN FILE` | critique file | `critique.json` | none | 0, 1, 4 | WP-19 |
| `report` | `RUN` | all artifacts | `report.md` | → `reported` | 0, 4 | WP-19 |
| `lint-skill` | `[SKILL_DIR]` (core skill); `--wrapper`; `--all` (core + wrappers) | skill folder | — | none | 0, 1 | WP-18 |
| `package-skill` | `--out DIR` (`dist/`) | skill folder | `dist/tailoring-cvs.zip` | none | 0, 1 | WP-18 |
| `export` (optional, wave 6) | `RUN --format latex\|md\|jsonresume` | tailored, `fit.json` | `export/cv.tex` / `cv.md` / `jsonresume.json` | none | 0, 1, 4 | WP-28 |

---

## 4. Exit codes, errors, output envelope

| Code | Name | Meaning | Agent's reaction |
| --- | --- | --- | --- |
| 0 | `OK` | Success | Continue with `next_action` |
| 1 | `CHECK_FAILED` | Schema or gate violations in an artifact | Run `cvt brief fix RUN`, patch only the listed items, rerun (max 2 fix attempts, then ask the user) |
| 2 | `USAGE` | Bad arguments | Fix the command |
| 3 | `MISSING_DEPENDENCY` | Typst/pdftotext/pypdf/jsonschema missing | Show the printed install hint; continue with fallbacks where printed |
| 4 | `STATE` | Run not found, wrong stage, artifact missing or stale | Run `cvt status RUN` and follow `next_action` |
| 5 | `INPUT` | Unreadable, empty, or scanned input | Tell the user; ask for a text-based CV or pasted text |
| 6 | `AWAITING_USER` | Questions or approval pending | Present pending items and end the turn |
| 7 | `INTERNAL` | Bug | Report the traceback path |

Human error format (stderr):

```text
cvt: error[E_ARTIFACT_MISSING]: jd.json not found in out/20261023-staff-platform-sre
  hint: write jd.json following references/stage-jd.md, then run: cvt jd-check 20261023-staff-platform-sre
```

`--json` envelope (stdout, always a single JSON object):

```json
{"ok": true, "command": "status", "exit_code": 0, "run": "20261023-staff-platform-sre",
 "stage": "awaiting_answers", "data": {}, "messages": ["..."], "next_action": "...",
 "error": {"id": "", "message": "", "hint": ""}}
```

Check-style commands put violations in `data.violations` as `validation.schema.json#/$defs/violation`
objects.

**Terse output (binding, every command).** Human output is at most `MAX_HUMAN_LINES = 15` lines. Lists are capped at
`MAX_LIST_ITEMS = 10` entries plus a `+N more (use --all)` line. Every command that lists things accepts `--all`.
The `--json` envelope is minified (one line, no indentation) and `data` never embeds whole artifacts. It carries
IDs, counts, paths, and capped violation lists. Artifacts that scripts write are pretty-printed for humans.
Artifacts the AI writes may be compact JSON. Scripts reformat them on save.

---

## 5. Python library API (`cvtlib`)

Location: `.claude/skills/tailoring-cvs/scripts/cvtlib/`. Pure functions where possible;
commands in `cvtlib/commands/<group>.py` are thin wrappers. Each command module exposes
`register(subparsers) -> None` and sets `func(args) -> int`. `cvtlib.cli.main(argv) -> int`
auto-discovers `cvtlib/commands/*.py` (so no WP edits a shared dispatcher). The `gtjob` CLI
imports these functions directly after `gtjob._skill.ensure_path()` puts `scripts/` on `sys.path`.

### WP-01 foundation (`errors.py`, `paths.py`, `jsonio.py`, `schemas.py`, `state.py`, `cli.py`, `output.py`, `usage.py`)

```python
# errors.py
class ExitCode(enum.IntEnum): OK=0; CHECK_FAILED=1; USAGE=2; MISSING_DEPENDENCY=3; STATE=4; INPUT=5; AWAITING_USER=6; INTERNAL=7
class CvtError(Exception):
    def __init__(self, code: ExitCode, err_id: str, message: str, hint: str = "", violations: list[dict] | None = None): ...

# paths.py
SKILL_ROOT: pathlib.Path                      # .../tailoring-cvs
def workspace_root() -> Path                  # $GTJOB_HOME or cwd
def out_dir() -> Path                         # workspace_root()/"out"
def profiles_dir() -> Path                    # workspace_root()/"profiles"
def resolve_run(run: str | Path | None) -> Path   # slug | path | "latest" | None→latest; CvtError(STATE,"E_RUN_NOT_FOUND")
def latest_run() -> Path | None               # max updated_at over out/*/state.json
def asset(*parts: str) -> Path                # SKILL_ROOT/"assets"/...
def schema_file(name: str) -> Path            # assets/schemas/<name>.schema.json
def person_dir(person_slug: str) -> Path      # profiles/<slug>/ (created on demand)
def attestations_path(person_slug: str) -> Path
def slugify(text: str, max_len: int = 48) -> str  # ascii-fold, lowercase, [a-z0-9-], collapse dashes
def new_run_slug(stem: str, today: datetime.date | None = None) -> str   # YYYYMMDD-stem[-N], unique in out/

# jsonio.py
def load_json(path: Path) -> Any              # CvtError(INPUT,"E_JSON") with line/col
def dump_json(obj: Any, path: Path) -> str    # atomic; returns sha256 of bytes written
def append_jsonl(path: Path, obj: Any) -> None # one minified line, flushed + fsynced
def sha256_file(path: Path) -> str
def sha256_bytes(data: bytes) -> str
def now_iso() -> str

# usage.py (section 14.7)
def record_usage(run_dir: Path, entry: dict) -> None          # validates keys, fills 'at', appends to out/<run>/usage.jsonl
def usage_totals(run_dir: Path) -> dict      # {"packets": {stage: est}, "api": {stage: {model, input, cache_read, cache_write, output}}, "total_est": int}; {} when no file

# schemas.py
SCHEMA_NAMES = ("profile","profile-map","attestations","jd","match","questions","answers","edits","tailor-plan","tailored","render-model","fit","validation","critique","state")
def load_schema(name: str) -> dict
def validate(obj: Any, name: str) -> list[str]          # ["$.work[0].id: 'x' does not match ..."]; [] = valid
def require_valid(obj: Any, name: str, label: str) -> None  # CvtError(CHECK_FAILED,"E_SCHEMA", violations=[{code:"schema",...}])
def subschema(name: str, def_name: str) -> dict          # {"$defs": all defs, **defs[def_name]}; for LLM output of one round/op
def api_schema(schema: dict) -> dict                     # deep copy without $schema/$id

# state.py
STAGES: tuple[str, ...]                        # order in section 6
ARTIFACT_STAGE: dict[str, str]                 # artifact name -> producing stage (section 6)
def create_run(cv_path: Path, jd_kind: str, jd_ref: str, jd_text: str | None, options: dict, slug: str | None = None) -> Path
def load(run_dir: Path) -> dict                # schema-validated
def save(run_dir: Path, st: dict) -> None      # sets updated_at, recomputes next_action, validates, atomic
def record_artifact(run_dir: Path, st: dict, name: str, rel_path: str, cascade: bool = True) -> None
def artifact(st: dict, name: str) -> dict | None
def require_artifact(run_dir: Path, st: dict, name: str, allow_stale: bool = False) -> Path   # CvtError(STATE,...)
def set_stage(st: dict, stage: str, status: str = "ok", pending: dict | None = None) -> None
def stage_index(stage: str) -> int
def require_stage(st: dict, minimum: str) -> None   # CvtError(STATE,"E_STAGE") with next_action as hint
def current_host() -> str                    # $GTJOB_HOST, else cvtlib.hostdetect.detect() if importable, else "unknown"
def add_history(st: dict, event: str, detail: str = "") -> None   # appends {at, event, stage, host: current_host(), detail}; also sets options.host
def add_error(st: dict, code: str, message: str) -> None
def next_action_for(st: dict, run_slug: str) -> str  # table in section 6

# output.py
def emit(args, *, run: str = "", stage: str = "", data: dict | None = None, messages: list[str] | None = None,
         human: str = "", next_action: str = "", exit_code: int = 0) -> int
def fail(args, err: CvtError) -> int

# cli.py
def main(argv: list[str] | None = None) -> int
```

### WP-08 `hostdetect.py`

```python
def detect() -> str                               # claude_code | cursor | cli | unknown (env heuristics; see WP-08)
```

### WP-09 `ingest.py`

```python
@dataclass
class Extraction: text: str; method: str; pages: int; scanned_suspect: bool; warnings: list[str]
def extract_cv(path: Path) -> Extraction          # .pdf (pdftotext -layout, else pypdf layout+NFKC), .txt, .md; .docx -> CvtError(INPUT) unless stretch implemented
def clean_cv_text(raw: str) -> tuple[str, list[str]]   # strip repeated headers/footers, page numbers, U+200B, decorative glyphs; keep reading order
def load_jd(kind: str, ref: str, stored: Path) -> str  # file/text/url (url: urllib with 15s timeout; CvtError(INPUT,"E_JD_FETCH") with hint to paste text)
def clean_jd_text(raw: str) -> str                     # whitespace/nbsp normalization only; no semantic stripping (AI does that)
```

### WP-10 `profile.py`, `profile_store.py`

```python
def normalize_ids(profile: dict) -> dict                    # canonical renumbering (section 1)
def normalize_text(s: str) -> str                           # NFKC, collapse whitespace, unify dashes/quotes, strip glyphs; used for verbatim checks
def verify_verbatim(profile: dict, cv_text: str) -> list[dict]  # violations code "fact_mismatch" for texts not found,
    # dates inconsistent with date_text, and titles/role labels that drop a seniority qualifier (as build_profile)
def script_source_issues(profile: dict, cv_text: str, today: datetime.date) -> list[dict]
def iter_items(profile: dict) -> Iterator[tuple[str, str, dict]]  # (id, kind, obj) for every addressable item
def item_text(profile: dict, item_id: str) -> str           # text of item; for exp-N/exp-N.eK includes all descendant texts + names + role label + dates
def merged_view(profile: dict, attestations: list[dict]) -> dict   # applies ACTIVE correction attestations
def lookup(cv_sha256: str) -> Path | None                    # profiles/*/profile.<sha12>.json
def store(run_dir: Path) -> Path
# profile_map.py
def numbered_cv(cv_text: str) -> str                         # "  41| text" per line; the exact numbering profile-map ranges refer to
def build_profile(pmap: dict, cv_text: str, *, person_slug: str, cv_sha256: str) -> tuple[dict, list[dict]]
    # verbatim text from ranges (leading bullet markers stripped, wrapped lines joined with one space), canonical IDs,
    # violations: range_error (out of bounds/overlap), unmapped_line (non-blank line not covered or ignored),
    # not_verbatim (name/employer/title/client/role label/cert/institution/degree area/study type not found in its
    # cited lines; each comma-separated part of a work, education, or basics location not found in its cited lines;
    # start_date/end_date inconsistent with date_text, or an education end_date / certificate date whose year is not
    # in its cited lines). Date consistency: the year must appear in date_text; a month (YYYY-MM) must appear as its
    # English name or 3-4 letter abbreviation ("Sep"/"Sept") or its number; `present` needs Present/Current/Now/Today;
    # "" is always allowed.
    # A title or role label is also not_verbatim when, at every occurrence in its cited lines, the word directly
    # before or after it (only spaces or a hyphen in between) is a seniority qualifier left out of the value
    # (`profile.SENIORITY_QUALIFIERS`: junior, intern, trainee, assistant, associate, co-, …). Example: title
    # "DevOps Engineer" from "Junior DevOps Engineer".
```

### WP-11 `attestations.py`, `scope.py`

```python
# attestations.py
def load_store(person_slug: str) -> dict                     # creates empty store if missing
def save_store(person_slug: str, store: dict) -> None
def add(store: dict, proposed: dict, *, run_id: str, question_id: str) -> dict   # assigns att-NNN, status proposed
def set_status(store: dict, att_id: str, status: str) -> dict
def usable(store: dict, *, run_id: str, include_proposed: bool) -> list[dict]   # active (+ proposed from run_id); never revoked/unresolved
# scope.py
def resolve(scope: dict, profile: dict) -> dict              # fills item_ids for role_label/items; validates ids; returns new scope
def describe_mapping(scope: dict, profile: dict) -> list[dict]   # [{item_id, label: "Royal Bank of Canada (RBC) — SRE (Mobia)"}]
def candidates(description: str, profile: dict, limit: int = 4) -> list[dict]   # ranked [{item_id, label}] for an unresolved scope's words: role-label, then employer/client name, then keyword overlap
```

### WP-15 `questions.py`, `answers.py`

```python
# questions.py
MAX_CP1_QUESTIONS = 8
def check(questions: dict, attestations: list[dict]) -> tuple[dict, list[dict]]   # (questions with suppressions, violations)
def add(questions: dict, new: list[dict]) -> dict            # assigns q-N, round = max+1 unless given
def render_chat(questions: dict) -> str
def render_host(questions: dict, host: str) -> dict          # section 7
# answers.py
def select_round(questions: dict, selections: dict[str, list[str]], *, default_rest: bool, now: str) -> dict  # host_tool round from --select (no AI); [] = skip; section 7 gap mapping
def plan_round(run_dir: Path, round_obj: dict) -> dict      # dry-run result: mapping, proposed attestations, unresolved, question status changes
def commit_round(run_dir: Path, round_obj: dict) -> dict    # applies plan; returns {created: [att ids], pending: [q ids]}
def auto_round(run_dir: Path) -> dict
```

### WP-12 `render.py`

```python
PRESETS_FILE = "templates/presets.json"
def build_render_model(tailored: dict, *, dropped_ids: set[str], density: str, draft: bool, paper: str, template: str) -> dict
def write_build(run_dir: Path, model: dict, template: str) -> Path   # build/render.json + build/cv.typ (+ common.typ), returns cv.typ
def compile_pdf(run_dir: Path, typ: Path, out_pdf: Path) -> int       # returns page count; backend: python typst, else typst binary, else CvtError(MISSING_DEPENDENCY)
def compile_png(run_dir: Path, typ: Path, out_dir: Path, ppi: int = 110) -> list[Path]
def render_markdown(model: dict) -> str
@dataclass
class RenderResult: pdf: Path | None; pages: int; pngs: list[Path]; backend: str
def render_run(run_dir: Path, *, template: str | None = None, density: str | None = None, dropped_ids: set[str] | None = None,
               draft: bool | None = None, png: bool = False, out_pdf: Path | None = None) -> RenderResult
```

### WP-13 `lexicon.py`, `provenance.py`, `checks.py`

```python
# lexicon.py
def tech_terms() -> list[str]                  # assets/lexicon/tech-terms.txt (longest first)
def synonyms() -> list[list[str]]              # equivalence classes from synonyms.json
def common_words() -> set[str]
def logistics_patterns() -> list[dict]         # [{kind, regex}]
def find_terms(text: str) -> list[str]         # lexicon terms + acronyms + CamelCase + mid-sentence capitalized words
def numbers(text: str) -> list[str]            # normalized numeric tokens ("800+"->"800", "99.99%"->"99.99", "8-member"->"8")
def supports(term: str, source_text: str) -> bool   # case-insensitive, plural/possessive tolerant, synonym-aware
# provenance.py
def check_tailored(tailored: dict, profile: dict, attestations: list[dict], *, run_id: str, draft: bool) -> list[dict]  # violations
def check_logistics(tailored: dict, jd: dict) -> list[dict]
def find_placeholders(tailored: dict) -> list[dict]
# checks.py
def check_jd(jd: dict, jd_text: str, jd_sha256: str) -> list[dict]
def check_match(match: dict, jd: dict, profile: dict, attestations: list[dict]) -> tuple[dict, list[dict]]   # (match with recomputed coverage, violations)
```

### WP-14 `fit.py`, `ats.py`, `coverage.py`, `validate.py`

```python
def drop_order(tailored: dict) -> list[str]                       # section 9
def fit_run(run_dir: Path, *, png: bool = False) -> dict          # fit.json object
def extract_pdf_text(pdf: Path) -> str                            # pdftotext -layout else pypdf; NFKC
def ats_check(pdf_text: str, model: dict, jd: dict) -> list[dict]
def coverage(pdf_text: str, jd: dict) -> dict                     # validation.coverage object
def validate_run(run_dir: Path, *, draft: bool) -> dict           # validation.json object
```

### WP-16 `diff.py`, `edits.py`

```python
def diff_items(tailored: dict, profile: dict, previous: dict | None) -> list[dict]   # [{id, section, kind: kept|rewritten|merged|attested|dropped|added|changed, before, after, source_refs, review}]
def outline(tailored: dict) -> str
def render_diff_md(items: list[dict], outline: str) -> str
def apply_ops(tailored: dict, ops: list[dict], profile: dict) -> dict   # pure; raises CvtError(CHECK_FAILED) on bad target
```

### WP-29 `briefs.py`, `assemble.py`

```python
# briefs.py (section 14 is normative)
def estimate_tokens(text: str) -> int                        # ceil(len(text) / budgets.chars_per_token)
def guide_core(name: str) -> str                             # the '## Core' section of references/<name>.md
def profile_digest(profile: dict, attestations: list[dict], jd: dict | None, budget: int) -> str   # section 14.3 format, relevance-filled to budget
def prematch(profile: dict, attestations: list[dict], jd: dict) -> dict   # {req_id: [{ref, terms}]} lexical+synonym candidates
def similar_runs(person_slug: str, jd: dict, exclude: str) -> list[dict] # [{run_slug, score, approved}] weighted keyword Jaccard
def build_brief(stage: str, run_dir: Path, *, reply: str = "", full: bool = False, item: str = "") -> str
# assemble.py
def assemble(plan: dict, profile: dict, attestations: list[dict], jd: dict, state: dict) -> tuple[dict, list[dict]]   # (tailored, violations)
```

### WP-19 `report.py`

```python
def build_report(run_dir: Path) -> str
```

### WP-18 `skillcheck.py`

```python
def lint_skill(skill_dir: Path, *, wrapper: bool = False) -> list[dict]   # violations [{code, item_id: relative path, message}]
def package_skill(skill_dir: Path, out_dir: Path) -> Path               # lint first; zip as tailoring-cvs/...; returns zip path
```

---

## 6. Run lifecycle and `state.json`

Stages in order (`STAGES`):

| # | Stage | Entered by | `status` | `next_action` text (template; `{run}` = slug, `{cvt}` = `uv run .claude/skills/tailoring-cvs/scripts/cvt.py`) |
| --- | --- | --- | --- | --- |
| 0 | `initialized` | `init` | ok | `Run: {cvt} ingest {run}` |
| 1 | `ingested` | `ingest` | ok | `Run {cvt} profile-cache {run} --lookup; on a miss run {cvt} brief profile {run}, write out/{run}/profile-map.json, then {cvt} profile-build {run}` |
| 2 | `profiled` | `profile-build`, `profile-verify`, `profile-cache --lookup` hit | ok | `Run {cvt} brief jd {run} (it may reuse a cached jd.json), write out/{run}/jd.json, then {cvt} jd-check {run}` |
| 3 | `jd_analyzed` | `jd-check` | ok | `Run {cvt} brief match {run}, write out/{run}/match.json, then {cvt} match-check {run}` |
| 4 | `matched` | `match-check` | ok | `Run {cvt} brief questions {run}, write out/{run}/questions.json, then {cvt} questions {run}` |
| 5 | `awaiting_answers` | `questions`, `answers-apply` (pending follow-ups) | awaiting_user | `Ask the pending questions ({cvt} questions {run} --format host). Choice answers: {cvt} answers-apply {run} --select q-N=CHOICE --default-rest --dry-run. Free text: {cvt} brief answer_parse {run} --reply-file F, write out/{run}/answers.round.json, then {cvt} answers-apply {run} --round out/{run}/answers.round.json --dry-run` |
| 6 | `answers_applied` | `answers-apply` (nothing pending), `questions` (none to ask), `--auto` | ok | `Run {cvt} brief tailor {run}, write out/{run}/tailor-plan.json, then {cvt} assemble {run}` |
| 7 | `tailored` | `assemble` or `check-tailored` pass | ok | `Run {cvt} diff {run} and present checkpoint 2` |
| 8 | `awaiting_approval` | `diff`, `apply-edits` | awaiting_user | `Present the compact diff. Free-text changes: {cvt} brief change_request {run} --reply-file F, write out/{run}/edits/next.json, then {cvt} apply-edits {run} out/{run}/edits/next.json. When approved: {cvt} approve {run}` |
| 9 | `approved` | `approve`, auto mode | ok | `Run {cvt} fit {run}` |
| 10 | `rendered` | `fit`, `render` (stage ≥ approved) | ok | `Run {cvt} validate {run}` |
| 11 | `validated` | `validate` pass | ok | `Run {cvt} report {run}` |
| 12 | `reported` | `report` | ok | `Done. Deliverables: final/*.pdf, report.md. Send change requests any time; they re-enter at checkpoint 2.` |

When a command fails, `status` becomes `failed` and the stage stays unchanged; `errors[]` gets an entry; `next_action` is
`Fix the reported problem, then rerun: {cvt} <command> {run}`. For exit 1 it is `Run {cvt} brief fix {run}, patch the listed
items, then rerun: {cvt} <command> {run}`.

**Artifact → producing stage (`ARTIFACT_STAGE`)**: `cv_txt`, `jd_txt` → `ingested`; `profile_map`, `profile` → `profiled`;
`jd`, `digest` → `jd_analyzed`; `match` → `matched`; `questions` → `awaiting_answers`; `answers` → `answers_applied`;
`tailor_plan`, `tailored`, `edits` → `tailored`; `fit`, `render_model`, `typst_source`, `pdf`, `pages_png`, `markdown_fallback` → `rendered`;
`validation`, `final_pdf` → `validated`; `critique`, `report` → `reported`. `usage` (`usage.jsonl`) is append-only,
has no stage, and is never stale.

**Staleness**: `record_artifact(..., cascade=True)` marks every artifact whose producing stage index is greater than
the recorded artifact's stage index as `stale: true`. Use `cascade=False` for in-place updates that do not change
downstream meaning (`questions` follow-up appends, `tailored` review-flag updates by `approve`). `require_artifact`
rejects stale artifacts unless `allow_stale=True`.

**Regression**: any edit to `tailored.json` after approval (`apply-edits` from a later free-text instruction) sets the
stage back to `awaiting_approval`; `approve` → `fit` → `validate` → `report` repeat. Re-answering questions after
tailoring (new attestation via `/cv-continue`) sets stage to `answers_applied` and marks `tailored` stale; the AI
re-tailors (keeping approved items unless affected) and proceeds.

**Auto mode** (`options.auto`): `questions` defaults every question and goes to `answers_applied`; `answers-apply
--auto` writes a `channel: auto` round; no attestation is ever created; `diff` marks every item `review: auto` and goes
to `approved`; the report lists every default applied.

---

## 7. Checkpoint protocol

### Checkpoint 1 (after `matched`)

The AI writes `questions.json` (≤ 8 pending, every question `allow_free_text: true` with a `default`). Topics:
`gap` (multi_select of partial/none requirements ordered by JD weight; choices map to `req_id` values), `source_issue`,
`metric` (3-5 bullets, free_text, default "no number"), `strategy` (template, emphasis, earlier-experience line).
`cvt questions RUN` then:

1. Validates schema and rules (violations: more than 8 pending cp1 questions in the initial batch (no `parent_id`) or in one follow-up round, missing default, `allow_free_text` false,
   duplicate ids, unknown req/item ids).
2. Suppresses questions answered by usable attestations: a `gap` choice whose requirement keywords are all covered by the
   `terms` of an active attestation is removed; a question left with no choices gets `status: suppressed` and
   `suppressed_reason: "answered by att-002 (Istio)"`. Suppressed items are listed in `data.suppressed`.
3. Renders for the host:
   - `--format chat`: numbered Markdown list; each question shows choices as `a)`, `b)`, ... and `Default: ...`; the
     footer says "Answer by number/letter or in your own words; anything you skip uses the default."
   - `--format host --host cursor`: `{"title": "...", "questions": [{"id": "q-1", "prompt": "...", "options": [{"id": "...", "label": "..."}], "allow_multiple": true}]}`
     (Cursor's ask-questions tool shape; it always offers free text). `yes_no` → two options.
   - `--format host --host claude_code`: `{"calls": [[{"question": "...", "header": "<=12 chars", "multiSelect": true, "options": [{"label": "...", "description": "..."}]}]]}`
     with at most 4 questions per call and at most 4 options per question (a question with more choices is split into
     parts "Gaps (1/2)", "Gaps (2/2)"). Free text comes through "Other". A timed-out dialog counts as "skip" (default).
4. Sets `awaiting_answers` / `cp1: pending` with `pending.question_ids`, and exits 6 so the agent ends its turn after
   asking. With no pending questions, sets `cp1: skipped` and `answers_applied`.

### Parsing a reply

Choice selections from a host question tool are applied directly with `cvt answers-apply --select q-N=CHOICE ...
--default-rest` (no AI output). A selected choice on a `topic: gap` question becomes a skills-only attestation
(`type: skill`, `claim` = choice label, `terms` = choice `value` split on `|`, `scope.kind: global`, `placement: skills`);
gap choice values are written as `term|synonym`. Narrower scopes come only from free text or a `scope_confirm`
follow-up. Free-text replies (in any later turn) go through the `answer_parse` packet: the AI turns
them into one `answers.schema.json#/$defs/round` object at `out/<run>/answers.round.json`, following
`references/answer-parsing.md`. Required behavior for the canonical
exchange (also an eval):

- "add service mesh, istio, typescript" → three `attest` items with `type: skill`, `placement: skills`,
  `scope.kind: global`, claims "Service mesh", "Istio", "TypeScript", terms e.g. `["service mesh"]`, `["Istio"]`,
  `["TypeScript"]`. Istio carries a caveat (hard to defend without role context; skills section only unless the user
  names a role).
- "add slo and error budget to the sre related cv items" → two `attest` items with `type: practice`, `placement: bullets`,
  `scope: {kind: role_label, role_label: "SRE", description: "the sre related cv items"}`, terms
  `["SLO", "SLOs", "service level objective", "service level objectives"]` and `["error budget", "error budgets"]`.
- SOC 2 and startup are not mentioned → listed in `unmentioned_question_ids` only if the whole question is unaddressed;
  otherwise the gap choices simply stay unselected. They remain gaps, are not re-asked in this run, and are reported once.
- No numbers, durations, team sizes, or certifications are added that the user did not state.

### Applying a reply

`cvt answers-apply RUN --round F --dry-run` validates the round and prints:

- the attestations that would be created (claim, type, placement, scope),
- the scope mapping per scoped attestation: for `role_label: SRE` on the sample → `exp-2.e4` Royal Bank of Canada (RBC)
  and `exp-2.e5` Lululemon (matching is case-insensitive on whole words of `role_label`),
- a suggested `scope_confirm` question skeleton (choices = resolved items, all default-selected) the AI may extend with
  reliability-adjacent optional items (for example `exp-2.e2` Sun Life DR, `exp-4` Morgan Stanley monitoring/on-call),
- `unresolved` scopes (for example "add Kafka to the relevant roles") with a skeleton question listing candidate
  engagements and default "skills section only".

The AI then appends follow-ups (scope confirmations plus only the content follow-ups that change the output, each with
a default) via `cvt questions RUN --add followups.json`, and runs `--commit`. Commit appends the round to `answers.json`,
creates attestations with `status: proposed` (scope `item_ids` resolved; `unresolved` stays unusable), marks answered/
defaulted/skipped questions, and exits 6 while follow-ups are pending (stage stays `awaiting_answers`, `pending.kind:
followups`), else 0 (`answers_applied`). A later `confirm_scope` item with `choice_ids` replaces the linked
attestation's `scope.item_ids` (via `links.attestation_ids` on the scope question). Corrections create `type:
correction` attestations with `placement: correction_only`.

### Checkpoint 2 (after `tailored`)

`cvt diff RUN` prints the section outline and per-item before/after (before = referenced profile text; for later
rounds, the previous tailored version), with origin labels and attestation IDs. The user approves all, approves/
rejects/edits items, or gives free-text instructions. The AI converts the reply into an `edits` file per
`references/change-requests.md`; `cvt apply-edits` applies it atomically (whole batch rejected on any violation) and
reprints the diff of what changed. `cvt approve RUN` (or an `approve_all` op followed by `approve`) requires no
`pending` items, flips this run's `proposed` attestations with resolved scopes to `active`, records
`state.attestations_used`, and sets `approved`.

---

## 8. Truthfulness rules (provenance validator)

Implemented in `cvtlib/provenance.py` (WP-13); run by `check-tailored`, `apply-edits`, and `validate`. Sources:

- `source_text(ref)`: for profile refs, `profile.item_text(ref)` on the **merged view** (active corrections applied);
  for `exp-N` / `exp-N.eK` this includes all descendant highlights (so a tools line supports its siblings), names,
  role label, and dates. For `att-NNN`: `claim + " " + detail + " " + " ".join(terms)`.
- Usable attestations: `active`, plus `proposed` from this run (with `--draft` or before approval). `revoked` and
  `unresolved`-scope attestations are never usable.

Rules per tailored element (violation code in parentheses):

1. Every bullet has ≥ 1 ref; summary, headline, skills items, and `intro` with non-empty text have ≥ 1 ref (`missing_refs`).
2. Every ref exists in the profile or the usable attestation set (`unknown_ref`).
3. An attestation cited by a bullet must have `placement` `bullets` or `skills_and_bullets` (`placement`), and the
   bullet's parent engagement or work ID must be in `scope.item_ids` unless `scope.kind` is `global` (`ref_out_of_scope`).
   An attestation cited by a skills item must have `placement` `skills` or `skills_and_bullets`.
3a. A bullet or `intro` under tailored work `exp-N` may cite profile refs `exp-N` or any ref starting with `exp-N.`.
   Under tailored engagement `exp-N.eK` it may cite `exp-N.eK`, refs starting with `exp-N.eK.`, and work-level
   highlights `exp-N.bJ` (for example a tools line). Any other `exp-*` ref is `ref_out_of_scope`. Non-experience refs
   (`basics`, `sum-*`, `skl-*`, `cert-*`, `edu-*`) are allowed, but each bullet needs at least one ref that is in its
   allowed `exp-*` set or a usable attestation in scope (`ref_out_of_scope`). Message:
   `"bullet <id> cites <ref> from another job; parent is <parent profile_id>"`.
4. Every term from `lexicon.find_terms(text)` must be supported by the union of the element's sources, using
   `lexicon.supports` (case-insensitive, singular/plural, possessive, `synonyms.json` equivalence classes) (`unsupported_term`).
   Terms present in `common-words.txt` are ignored.
5. Every number from `lexicon.numbers(text)` must appear in the sources (`unsupported_number`). Years inside
   `start_date`/`end_date` fields are checked by rule 6 instead.
6. Employer, title, location, dates, client names, role labels, certification names, and degrees must equal the merged
   profile values (certification `name` may be a contiguous shortened substring) (`fact_mismatch`, `cert_unsupported`).
   Header name must equal `basics.name`; header email/phone/url/links must be profile values.
7. Every skills item name must be supported by any profile text or a usable skill attestation (`skill_unsupported`).
8. `[[CONFIRM: ...]]` placeholders are reported (`placeholder`): warn with `--draft`, fail otherwise.
9. No text from jd `noise` items of kind `compensation`, `visa`, `recruiter_contact`, `recruiter_question`, and no match
   of `logistics-patterns.json` (salary figures, "visa", "work authorization", recruiter emails) appears anywhere in
   `tailored.json` (`logistics_leak`).
10. In a non-draft final build, every cited attestation must be `active` (`attestation_not_active`).

Message format is exact: `"<element kind> <id> mentions '<term>'; not found in refs [<ref>, <ref>]"`, for example
`bullet t-exp-2.e4.b1 mentions 'Linkerd'; not found in refs [exp-2.e4, att-002]`.

---

## 9. Render, template data contract, and fit

**Template contract.** `render-model.schema.json` is the only input to templates. `build_render_model` maps:
header (name, headline, contacts in order email, phone, location, website, linkedin, github); sections in this order
unless `target.emphasis` says otherwise: `summary`, `skills`, `experience`, `earlier` (only when included and
non-empty), `certifications`, `education`. Experience entries map `t-exp-N` to `entry` and engagements to `subentries`;
engagements with no remaining bullets fold into `collapsed_line` ("Also: Trilliant (Solutions Architect) · IDS
(Solutions Architect)"). Dates format as `Mon YYYY – Mon YYYY` / `Present`, year-only when the profile has only years.

**Templates** (`assets/templates/`): `common.typ` (helpers: section rule, entry block, contact line, placeholder
highlight), `modern.typ`, `classic.typ`, `sidebar.typ`. `sidebar` is two-column: summary and experience in the main
column, and skills, certifications, and education in a right rail. It is less ATS-safe than `modern` and `classic`.
Each template starts with
`#let data = json(sys.inputs.at("data", default: "render.json"))` and
`#let presets = json(sys.inputs.at("presets", default: "presets.json"))`; it never calls `eval`. Data strings are
inserted as text, never as markup. PDF metadata comes from `meta` via `set document(title:, author:, keywords:)`.

**Presets** (`assets/templates/presets.json`, read by templates and validators):

```json
{"floor": {"body_pt": 9.5, "margin_in": 0.5},
 "comfortable": {"body_pt": 10.5, "margin_in": 0.7, "leading_em": 0.62, "section_gap_pt": 9},
 "standard":    {"body_pt": 10.0, "margin_in": 0.6, "leading_em": 0.58, "section_gap_pt": 7},
 "compact":     {"body_pt": 9.5,  "margin_in": 0.5, "leading_em": 0.55, "section_gap_pt": 5}}
```

**Compilation.** `write_build` copies the chosen template, `common.typ`, and `presets.json` into `build/`, writes
`build/render.json`, and compiles with root = `build/`, `font_paths = [assets/fonts]`, `ignore_system_fonts = True`,
`sys_inputs = {"data": "render.json", "presets": "presets.json"}`. Backend order: Python `typst` module → `typst` binary
on PATH (`typst compile --root build --font-path <fonts> --ignore-system-fonts --input data=render.json ...`) → no
compiler: write `build/` and `cv.md`, exit 3 with hint `uv pip install typst` or `brew install typst`.

**Fit algorithm** (`fit_run`, deterministic and monotone, so it cannot oscillate):

1. `units = drop_order(tailored)`: all bullets, certifications, and skills groups with `priority > 1`, sorted by
   priority descending (5 first), then by entry age (oldest employer first), then by position (last bullet first).
   Priority-1 items are never dropped. An engagement's or entry's own priority is inherited as a floor for its bullets
   (a bullet's effective priority is `max(bullet.priority, parent.priority)`).
2. For density in `comfortable`, `standard`, `compact`: render with nothing dropped. If `pages ≤ page_target`, stop.
3. Otherwise, with `compact`, binary-search the smallest `k` such that dropping `units[:k]` gives `pages ≤ page_target`
   (page count is non-increasing in `k`). Record `dropped_ids = units[:k]`.
4. If even `k = len(units)` overflows, exit 1 with the message "content with priority 1 exceeds N pages; lower some
   priorities or shorten bullets".
5. `underfilled = pages < page_target` (reported; never padded automatically).
6. Write `fit.json`, render the final PDF (and PNGs with `--png`), set stage `rendered`.

---

## 10. Validation gates (`cvt validate`)

| Gate | Fails when | Status options |
| --- | --- | --- |
| `schema` | any artifact invalid | pass/fail |
| `provenance` | any rule-1..7 violation | pass/fail |
| `placeholders` | placeholders exist and not `--draft` | pass/warn(draft)/fail |
| `logistics_leak` | rule 9 | pass/fail |
| `attestation_status` | rule 10 (non-draft) | pass/warn(draft)/fail |
| `page_count` | pages ≠ page_target (1 allowed when `page_target` 2 and `underfilled`, reported as warn) | pass/warn/fail |
| `typography_floor` | `theme.density` not a preset or preset below `floor` | pass/fail |
| `ats_roundtrip` | extracted PDF text lacks name, email or website (when present in profile), any section title, any employer; section titles out of order; an employer's first bullet appears before its heading; `(cid:` or U+FFFD present; extracted text < 90% of render-model text characters | pass/fail |
| `keyword_coverage` | never fails; reports must-have keyword coverage (term or synonym found, case-insensitive) | pass/warn (< 70%) |
| `layout` | never fails; warns on a last page under `MIN_LAST_PAGE_FILL`, an underfilled page, or an orphaned section heading (section 14.5) | pass/warn |

On pass without `--draft`, copy `cv.pdf` to `final/<Name>-<TitleSlug>.pdf` and record `final_pdf`.

---

## 11. Slash commands (Cursor and Claude Code)

All are thin wrapper skills in `.claude/skills/<name>/SKILL.md` with `disable-model-invocation: true`. Both hosts
list them under `/`. They never use `$ARGUMENTS` or `${CLAUDE_SKILL_DIR}` (Claude Code-only substitutions); instead
the body says "the text the user typed after the command (Claude Code appends it as `ARGUMENTS:`)".

| Command | Arguments | Action |
| --- | --- | --- |
| `/tailor-cv` | `[cv-path] [jd-path-or-text]` | Start a run. Missing args: list `CVs/*` and `JDs/*` as choices with the structured question tool. Then follow the core skill from `init`. |
| `/cv-continue` | `[free-text answer or instruction]` | Load the latest run (`cvt status --json`); treat the text as the reply to pending questions (stage `awaiting_answers`) or as a change request (stage ≥ `tailored`); resume from `next_action`. |
| `/cv-status` | `[run-slug]` | Show stage, pending questions (chat format), artifact paths, next action. No changes. |
| `/cv-render` | `[template] [run-slug]` | `cvt render` + `cvt fit` + `cvt validate` with the given template (`modern`, `classic`, or `sidebar`); no AI content changes. |
| `/cv-profile` | `[list\|revoke att-NNN\|show]` | Show the profile summary and attestations (`cvt profile-show --merged`, `cvt attest list`); revoke on request after confirming. |
| `/cv-polish` | `[cv-path]` | Generic CV, no job description. Keep every fact, aim for 2–3 pages, render modern, classic, and sidebar. Does not call `cvt init` or `cvt fit`. |

---

## 12. `gtjob` CLI

Package `gtjob` in `src/gtjob/` (root `pyproject.toml`, entry point `gtjob = "gtjob.cli:main"`). Run with
`uv run gtjob ...`. It imports `cvtlib` (via `gtjob._skill.ensure_path()`) and adds the AI stages via the Anthropic API.

| Command | Arguments | Behavior |
| --- | --- | --- |
| `gtjob tailor` | `--cv PATH` and `--jd PATH` / `--jd-text TEXT` / `--jd-url URL`; `--template`; `--auto`; `--answers FILE.yaml`; `--draft`; `--critic`; `--critic-visual` (implies `--critic`; same as `cvt brief critic --visual`, section 14.6); `--slug`; `--page-target`; `--paper`; `--model STAGE=MODEL` (repeatable); `--no-cache` | Full pipeline with terminal prompts at both checkpoints (unless `--auto`/`--answers`). |
| `gtjob continue` | `[RUN]`; `--answers FILE.yaml`; `--text TEXT` | Resume any run (including ones started in Cursor/Claude Code) from `state.json`. |
| `gtjob status` | `[RUN]` | Same output as `cvt status`. |
| `gtjob render` | `RUN`; `--template T` (`modern`, `classic`, or `sidebar`); `--draft` | fit + validate, no AI. |
| `gtjob polish` | `extract CV` or `render MODEL OUT` | Generic CV, no job description. `extract` prints CV text with the same reader as `ingest`. `render` writes every template into `OUT`. The host model writes `MODEL` from `references/generic-cv.md`. No `init`, no `fit`, no API key. |
| `gtjob edit` | `RUN --text TEXT` | change-request stage → `apply-edits` → diff → approve prompt → fit → validate → report. |
| `gtjob profile` | `list\|show\|revoke ID`; `--person P` | Same as `/cv-profile`. |
| `gtjob package-skill` | `--out DIR` | Same as `cvt package-skill`. |

Exit codes as in section 4. `ANTHROPIC_API_KEY` is required only for AI stages; missing → exit 3 with hint.

**Non-interactive stop.** When stdin is not a TTY and the run reaches a checkpoint with no `--auto`, `--answers`, or
`--text` input left to consume, `gtjob` prints the pending questions (`questions --format chat`) or the diff, saves
state, and exits 6 (`AWAITING_USER`). The run stays resumable from any host. `gtjob continue RUN --text "..."` feeds
one free-text reply into whichever checkpoint is pending (an answer round at checkpoint 1, a change request at
checkpoint 2).

**Models.** Defaults and escalation per section 14.6 (Haiku for `jd`, `answer_parse`, `change_request`; Sonnet for
`profile`, `match`, `questions`, `tailor`; Opus `critic`, opt-in). Override precedence: `--model
STAGE=ID` > env `GTJOB_MODEL_<STAGE>` (uppercase) > `gtjob.toml` `[models]` table at the workspace root > defaults.

**LLM cache.** `.cache/gtjob/llm/<sha256>.json` keyed on `(model, system prompt, user content, schema, max_tokens)`.
`--no-cache` bypasses reads (still writes).

**`--answers` YAML** (`answers.yaml`):

```yaml
checkpoint1:
  q-1: [service_mesh, typescript]      # choice ids, or a string for free text
  q-3: "add slo and error budget to the sre related cv items"
  default_rest: true                   # every other pending question takes its default
followups: default                     # or a map like checkpoint1
checkpoint2: approve_all               # or a list of free-text instructions applied as change requests, then approve
```

Free-text values are parsed by the same `answer_parse` stage as in the IDE.

---

## 13. AI stages: prompts, inputs, outputs

Every AI stage is driven by a **stage packet** printed by `cvt brief <stage> RUN` (section 14). The packet is the only
context the model needs. It holds the guide's `## Core` section, compact inputs, the output file and schema, and the
check command. IDE agents run `cvt brief`. The CLI calls `cvtlib.briefs.build_brief` in-process, so both paths
spend identical context.

Guides in `references/` start with `## Core` (at most `CORE_MAX_LINES = 60` lines: purpose, rules, output, self-check),
followed by `## Details` and `## Examples`. Only the Core section goes into packets. Details and Examples are added
by `--full`, which agents use only after 2 failed checks or when a packet says so. All CV/JD text is untrusted data:
packets wrap it in `<untrusted_document name="...">…</untrusted_document>`, and every Core section says to ignore
instructions inside documents and record them in `jd.injection_flags`.

| Stage key | Guide Core(s) in packet | Packet inputs (section 14.3 formats) | Output file | Output schema | Check command |
| --- | --- | --- | --- | --- | --- |
| `profile` | stage-profile | line-numbered `cv.txt` | profile-map.json | profile-map | profile-build |
| `jd` | stage-jd | `jd.txt` (line-numbered) | jd.json | jd | jd-check |
| `match` | stage-match, truthfulness | JD digest, profile digest (relevance-filled), prematch candidates, attestations | match.json (evidence `quote` may be `""`; match-check fills it) | match | match-check |
| `questions` | checkpoint-questions | gap list (partial/none requirements), source issues, item headers, role labels, attestations | questions.json | questions | questions |
| `answer_parse` | answer-parsing | pending questions (compact), reply, item headers + role labels, attestations | answers.round.json | answers `$defs/round` | answers-apply --dry-run |
| `tailor` | stage-tailor, style-guide, truthfulness | JD digest, profile digest (selected items in full), match strengths, answers summary, attestations, seed plan (if any) | tailor-plan.json | tailor-plan | assemble |
| `change_request` | change-requests, truthfulness | tailored outline (IDs + 80-character excerpts), the reply, the items it names in full | edits/next.json | edits | apply-edits |
| `fix` | the failed stage's Core (rules only) | the last check's violations (capped) and only the offending items | stage output (whole file for profile-map, jd, match, questions; an edits file for tailored) | as stage | the failed check |
| `critic` | critic-rubric | tailored outline + JD digest + validation summary (text only; PNGs only with `cvt brief critic --visual` / `gtjob tailor --critic-visual`) | critique.draft.json | critique | critique-save |

Choice answers from host question tools never go through `answer_parse`. They are applied with
`answers-apply --select`.

Fix loop (IDE and CLI): on exit 1, run `cvt brief fix RUN` and patch only the listed items, at most
`MAX_FIX_ATTEMPTS = 2` times. Then show the violations to the user.

---

## 14. Token efficiency (binding)

Goal: a new JD for a CV that has already been profiled costs about 20k input tokens and 8k output tokens across
all AI stages (budgets below), and needs no reading of raw artifacts. Every rule here is enforced by code or by a
test.

### 14.1 Agent rules (core SKILL.md must state them)

1. Get context only from `cvt brief`, `cvt status`, and command output. In the happy path, never Read `cv.txt`,
   `profile.json`, `tailored.json`, `match.json`, or `references/*.md`.
2. Write AI outputs as compact JSON to the file the packet names.
3. Do not re-run a command just to see its output again; `cvt status` summarizes.
4. Do not look at page PNGs unless `validate` reports a `layout` warning, a gate fails, or the user asks. Then
   view only the flagged page.
5. Run `cv-critic` only when the user asks.
6. In chat, give short summaries: questions go through the host question tool; diffs are shown compactly
   (counts + changed items); deliverables are linked by path, never pasted.
7. Fixes are patches, not regenerations (section 13 fix loop).
8. Start each new JD in a new chat. `cvt status`, the profile cache, and the attestation store carry everything
   over, and a long chat re-sends its whole history every turn.

### 14.2 Reuse across runs (new JD, same CV)

- **Profile:** `profile-cache --lookup` by CV SHA-256. On a hit, the profile stage is skipped (0 tokens).
- **JD:** `brief jd` checks earlier runs for an identical `jd_sha256`. On a hit it copies that run's `jd.json`
  (`data.cache_hit`), and the agent goes straight to `jd-check`.
- **Questions:** active attestations suppress questions they already answer (section 7). Unchanged.
- **Seed plan:** `brief tailor` runs `similar_runs`. If the best approved run scores ≥ `SEED_MIN_SCORE = 0.6`
  (weighted keyword Jaccard), the packet includes that run's `tailor-plan.json` (compact) as **Seed**, with the
  instruction "start from the seed; change only what this JD needs; set `seed_run`". The report names the seed.
- **Digest:** `digest.txt` is computed once per run (first `brief match`) and reused by the questions, tailor, and
  change_request packets, so the CLI's prompt cache hits within a run.

### 14.3 Compact formats used in packets

```text
# profile digest (one item per line; IDs first; '|' separated; highlights indented)
exp-2 Mobia | Solutions Architect | Toronto, ON | 2021-07..2024-01 | consultant
 exp-2.e4 [client] Royal Bank of Canada (RBC) | role: SRE
  b1 Built Terraform modules for ... (text truncated at 240 chars with '…')
 exp-2.e5 [client] Lululemon | role: SRE  (+4 bullets hidden; cvt brief tailor --item exp-2.e5)
skl-3 Cloud: GCP, AWS, Azure, ...
att-004 practice "SLOs" scope role_label=SRE -> exp-2.e4, exp-2.e5 [active]
# JD digest
req-3 must w5 infra-as-code | Terraform, Helm, ArgoCD, GitOps
# prematch
req-3: exp-1.e1.b2 (terraform, helm); exp-2.e2.b1 (argocd)
```

The digest is filled by relevance until the stage budget is reached. The relevance score combines JD keyword and
synonym hits weighted by requirement weight, a recency boost, and an attested-scope boost. Items that don't fit
appear as header lines with a `+N bullets hidden` hint. Header lines for every work entry and engagement are
always included, so the model can see the whole career.

### 14.4 Budgets (`assets/budgets.json`, tunable without a contract change)

| Packet | Max input tokens (estimate) | CLI `max_tokens` (output) |
| --- | --- | --- |
| profile | 1,500 + the numbered CV | 8,000 |
| jd | 3,000 | 5,000 |
| match | 7,000 | 6,000 |
| questions | 4,000 | 3,000 |
| answer_parse | 2,500 | 2,000 |
| tailor | 8,000 | 8,000 |
| change_request | 3,000 | 2,000 |
| fix | 2,500 | 1,500 |
| critic | 4,000 | 3,000 |

`estimate_tokens = ceil(chars / chars_per_token)`, where `chars_per_token` is 3.8. When a packet would exceed its
budget, `build_brief` trims in a fixed order: hidden bullets first, then the seed plan, then the remaining
excerpts. It never trims Core rules, must-have requirements, attestations, or the reply. If the packet is still
over budget, it prints a `budget` warning. Unit tests assert that the junior and synthetic packets fit their
budgets. The e2e tests assert the same for the private sample.

### 14.5 Images

`fit` does not render PNGs by default (`--png` opts in). `validate` adds a `layout` gate (warn only):

- the last page is filled less than `MIN_LAST_PAGE_FILL = 0.25`
- the page is underfilled
- a section heading sits within the bottom `ORPHAN_HEADING_LINES = 2` lines of a page (when detectable from
  pdftotext bounding boxes)

The agent looks at PNGs only per rule 14.1.4, using `cvt render RUN --pages N --ppi 80` (view-only; it does not
change the stage).

### 14.6 Model routing and caching (CLI)

| Stage | Default model | Escalation |
| --- | --- | --- |
| `jd`, `answer_parse`, `change_request`, `fix` (of those) | `claude-haiku-5-5` | Re-run once on `claude-sonnet-5-5` after one failed check |
| `profile`, `match`, `questions`, `tailor`, `fix` (of those) | `claude-sonnet-5-5` | None (after 2 failures, ask the user) |
| `critic` (opt-in) | `claude-opus-5-5`, text only | `gtjob tailor --critic-visual` (= `cvt brief critic --visual`) adds page PNGs at 80 ppi |

The CLI puts stable content first and marks it with `cache_control` breakpoints:

1. The preamble plus the Core section(s).
2. `digest.txt`.
3. Run-specific inputs and the reply.

In interactive runs, the breakpoint on block 2 uses the 1-hour TTL, so it survives checkpoint pauses. Elsewhere it
uses the 5-minute default. Extended thinking is off by default. `gtjob.toml [thinking]` may enable it per stage
only when evals show a quality gain.

### 14.7 Telemetry

Every packet and API call appends one line to `out/<run>/usage.jsonl`:
`{at, stage, kind: packet|api, model, est_tokens, input_tokens, cache_read_tokens, cache_write_tokens,
output_tokens, attempt}`. Packets give estimates; API calls give actuals.

- `cvt status` prints a one-line total.
- `gtjob` prints a per-stage table at the end of a run.
- `report.md` ends with a `## Token usage` section.
- WP-23 live evals assert that the new-JD run stays within 1.25 × the budget totals.
