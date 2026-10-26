# WP-G1 gate report: wave 1

## Verdict

**FIX-UPS.** Every WP's own acceptance tests pass, and the full suite passes: 270 tests (`.cache/logs/G1/suite.log`).
There are four blocking findings: two foundation defects, one guide-content gap, and PII in the frozen contracts. The
last one, together with the WP-I1 escalation, needs a contract change, which is applied only after the user agrees
(`plan/reports/WP-G1-contract-change.md`).

## Acceptance results (re-run by the gate)

| WP | Command | Result |
| --- | --- | --- |
| 01 | `pytest -q tests/unit/test_schemas.py tests/unit/test_foundation.py tests/unit/test_state.py` | PASS, 101 passed |
| 01 | `cvt.py --help` | PASS, exit 0, lists `validate-artifact` |
| 01 | `cvt.py --json validate-artifact nope jd` | PASS, one-line envelope, `E_RUN_NOT_FOUND`, exit=4 |
| 01 | `diff -r plan/contracts assets/schemas \| grep -v interfaces.md` | PASS, no output |
| 01 | `git check-ignore -q out/x CVs/x JDs/x profiles/x tests/fixtures/private/x` | Command broken: git 2.42 prints `fatal: --quiet is only valid with a single pathname`. Checked one path at a time: all ignored, PASS |
| 01 | `python -c "...ensure_path(); import cvtlib.state; print('ok')"` | PASS, `ok` |
| 02 | `pytest -q tests/unit/test_render_assets.py` | PASS, 10 passed |
| 02 | `ls assets/fonts/*/OFL.txt`; `du -sh assets/fonts` | PASS, 2 files; 2.4M |
| 03 | `pytest -q tests/unit/test_text_fixtures.py`; `grep -c . ...checkpoint1.txt` | PASS, 29 passed; `1` |
| 04 | `pytest -q tests/unit/test_junior_golden.py` | PASS, 23 passed |
| 05 | `pytest -q tests/unit/test_refs_writing.py`; `wc -l` | PASS, 18 passed; 139/125/138 lines |
| 06 | `pytest -q tests/unit/test_refs_stages_a.py` | PASS, 16 passed |
| 07 | `pytest -q tests/unit/test_refs_stages_b.py` | PASS, 20 passed |
| I1 | `pytest -q tests/unit tests/integration/test_wave1.py` | PASS, 270 passed |
| I1 | `git status --porcelain` | PASS: only wave-1 files, `tests/integration/`, and `plan/reports/`, plus the orchestrator's `plan/STATUS.md` and the user's untracked `prompts/` |
| G | `pytest -q tests/unit tests/integration` | PASS, 270 passed in 2.55s |
| G | `uv lock --check` | PASS |

## Findings

### Blocking

1. **`.gitignore` hides the synthetic JD fixtures** (WP-01, as specified by its brief). `JDs/` is unanchored, and with
   `core.ignorecase=true` it matches `tests/fixtures/jds/`. `git check-ignore -v tests/fixtures/jds/injection-test.md`
   prints `.gitignore:6:JDs/`. All 5 JD fixtures, including the junior golden's JD (whose SHA-256 is baked into
   the goldens), would be left out of the wave-1 commit, and a fresh clone would fail the tests. Fix: WP-FIX-1-1.
2. **`--json` usage errors print no envelope** (WP-01, contract section 4: the envelope is "always a single JSON
   object" on stdout). `cvt --json validate-artifact`, `cvt --json bogus`, and `cvt --json` print a human error to
   stderr and nothing on stdout (exit 2). Every later command inherits this. Fix: WP-FIX-1-1.
3. **Exit-1 handling is missing from three Cores** (WP-05, WP-07). Packets contain only the Core section.
   `answer-parsing` and `checkpoint-questions` explain exit 1 only in Details. `critic-rubric` does not explain it at
   all. The gate focus requires every stage guide to say what to do on exit 1. Fix: WP-FIX-1-2.
4. **The sample candidate's PII is in the frozen contracts, so it ships in the skill.**
   `profile.schema.json:11` (slug), `render-model.schema.json:16` (full name), and `:53` (email) are copied
   byte-for-byte into `assets/schemas/`, and from there into `dist/tailoring-cvs.zip`. WP-I5's package PII grep
   would fail. This needs a contract change (C1), then WP-FIX-1-3.

### Escalation decision (WP-I1: `--visual` vs `--critic-visual`)

The contract must change, but nothing is renamed. These are two surfaces:

- `cvt brief critic --visual` is the packet flag, as section 13 and `critic-rubric.md` already use it.
- `gtjob tailor --critic-visual` is the CLI flag, as section 14.6, WP-21, and WP-22 already use it.

The gap is that neither flag is defined in its command table: section 3 for `brief`, section 12 for `gtjob tailor`.
The proposed contract change (C2) adds both and clarifies sections 13 and 14.6. WP-FIX-1-3 then removes the
`UNDOCUMENTED_FLAGS` allowlist entry.

### Non-blocking

- Foundation passes: command auto-discovery; envelope keys, order, and minified form (section 4); `save` sets
  `updated_at`, recomputes `next_action`, validates, and refuses invalid state; `resolve_run("latest"/None)` (probed
  in a temporary `GTJOB_HOME`); the cascade stales only later stages, `usage` has no stage, and stale artifacts give
  exit 4; `next_action` templates match section 6 verbatim; `pyproject` installs and `uv.lock` is current.
- A failed run's `next_action` takes its rerun command from the last history event. If a failing command skips
  `add_history`, the agent is told `rerun: cvt init <slug>` (reproduced). See notes for the next wave.
- `usage_totals` silently skips malformed `usage.jsonl` lines. Acceptable for telemetry.
- Fixtures pass: every claim, number, tool, and date in the junior `tailored.json` traces to the CV. Helm comes only
  from `att-001` (`skills_and_bullets`, scope `exp-1`). All companies are invented, and the injection JD carries the
  expected lines.
- The junior CV links `github.com/jamierivera-dev`, an invented handle on a real domain. Changing it would re-hash the
  goldens, so leave it unless the user objects.
- Other `morattab|arashmor` hits outside `prompts/` are plan-mandated: `plan/*` (already committed), the default
  private CV path in `tests/conftest.py`, and the PII-marker lists in `tests/unit/test_refs_*.py`. None ship in the
  skill. Whether they belong in a public repo is the user's call.
- Guides pass: each Core names its check and output, and treats documents as untrusted. `truthfulness.md` follows
  section 8 rules 1-10 with the same numbering. The canonical reply is quoted verbatim and mapped to five
  attestations. Examples are anonymized.
- Section 13 asks every Core to record injections in `jd.injection_flags`, but only the `jd` stage writes `jd.json`.
  Reword it in a later contract pass.
- Fonts are `Version 3.052` and `7.051;RELEASE` (read from the OTF name tables), with OFL 1.1 for both, 2.4 MB total.
- Schema probe on `tailored.json` rejected empty bullet refs, a bad ref, a `Feb 2024` date, `origin: invented`, and
  unknown keys. Empty skills-item refs pass by design. Invented tool, number, and scope probes wait for WP-13 at G2.
  No templates exist yet, so there are no PNGs to review.
- No `eval`/`exec`, network use in unit tests, or swallowed exceptions. The one magic constant, `return 130` in
  `cli.py`, is fixed in WP-FIX-1-1.

## Fix-up WPs

| Brief | Owner | Files | Order |
| --- | --- | --- | --- |
| `plan/tasks/WP-FIX-1-1-foundation-ignore-json.md` | Sonnet (`cv-builder`) | `.gitignore`, `cvtlib/cli.py`, `tests/unit/test_foundation.py` | now |
| `plan/tasks/WP-FIX-1-2-core-exit1.md` | Sonnet (`cv-builder`) | 3 reference Cores, `tests/integration/test_wave1.py` | now, in parallel with FIX-1-1 |
| `plan/tasks/WP-FIX-1-3-sync-contract-change.md` | Sonnet (`cv-builder`) | 2 asset schema copies, `test_wave1.py` constant | after the user approves the contract change and after FIX-1-2 |

Contract change: `plan/reports/WP-G1-contract-change.md` (C1 PII, C2 critic flags). **Apply it only after the user
agrees.** Then run a delta re-gate.

## Notes for next wave

- Every command that fails after loading state must call `state.add_history(st, "<command>")` before
  `add_error` + `save`. Otherwise the failed-run `next_action` names the wrong rerun command. Use `E_CHECK_FAILED` (or
  `E_SCHEMA`) for exit-1 errors so the `brief fix` template is chosen. WP-08 tests should cover this.
- Acceptance commands that use `git check-ignore -q` with several paths fail on git 2.42. Use one path per call
  (WP-I5).
- WP-13 must enforce rule 1 for skills items after `assemble` resolves refs, because the schema allows `[]`.
- WP-29 `build_brief` must print `jd_sha256`, `source.kind`/`source.ref`, and the run slug (WP-06 open issues). It
  must also implement `brief critic --visual` once C2 is applied.
- WP-11 must confirm that the first attestation in a fresh run gets `att-001`. The goldens assume it (WP-04).
- In Typst, Semibold faces register as separate families (`Source Sans 3 Semibold`, `Libertinus Serif Semibold`).
  Templates (WP-12, WP-17) must select them by family name.

## Re-gate 1

**Verdict: FIX-UPS.** Blocking findings 1, 2, 3, and 4 (C1 PII) are fixed, and the full suite passes (286 tests,
`.cache/logs/G1/re1/suite.log`). One item is still open: WP-FIX-1-3 step 2 (C2) was not applied, although its report
says it was. Fix: `plan/tasks/WP-FIX-1-4-drop-visual-allowlist.md` (Haiku, one file).

The contract change in `plan/contracts/` matches `WP-G1-contract-change.md` C1 and C2 line for line
(`git diff HEAD -- plan/contracts/`).

| Source | Command | Result |
| --- | --- | --- |
| FIX-1-1 | `pytest -q tests/unit/test_foundation.py` | PASS, 30 passed |
| FIX-1-1 | `git check-ignore -q` for out, CVs, JDs, profiles, and private (one path per call) | PASS, no output |
| FIX-1-1 | `git check-ignore tests/fixtures/jds/junior-devops-engineer.md` | PASS, exit=1 |
| FIX-1-1 | `git status --porcelain --untracked-files=all tests/fixtures/jds \| wc -l` | PASS, 5 |
| FIX-1-1 | `cvt.py --json validate-artifact` | PASS, one envelope line, `E_USAGE`, exit=2, stderr empty |
| FIX-1-2 | `pytest -q test_refs_writing test_refs_stages_b test_wave1` | PASS, 99 passed |
| FIX-1-3 | `diff -r plan/contracts assets/schemas \| grep -v interfaces.md` | PASS, no output |
| FIX-1-3 | `git grep --untracked -i -c -E "morattab\|arashmor" -- .claude/skills` | PASS, `no PII in skill` |
| WP-01 | `pytest -q test_schemas test_foundation test_state` | PASS, 109 passed |
| WP-01 | `cvt --help`; `--json validate-artifact nope jd` | PASS; `E_RUN_NOT_FOUND`, exit=4 |
| WP-01 | `check-ignore`, one path per call; `ensure_path` import | PASS, all 5 ignored; `ok` |
| WP-05 | `pytest -q test_refs_writing`; `wc -l` | PASS, 18 passed; 139/125/139 lines |
| WP-07 | `pytest -q test_refs_stages_b` | PASS, 20 passed |
| WP-I1 | `pytest -q tests/unit tests/integration/test_wave1.py` | PASS, 286 passed |
| G | `pytest -q tests/unit tests/integration` | PASS, 286 passed in 2.44s |

**Ownership.** I checked files modified after the contract-change proposal. Only the fix-up-owned files, the three
contract files (applied by the orchestrator after the user approved), `plan/STATUS.md`, and `plan/reports/` changed.
No out-of-ownership edits.

### Blocking

5. **The `--visual` allowlist is still in `tests/integration/test_wave1.py:61-63`** (WP-FIX-1-3 step 2). The file's
   mtime (21:35) is FIX-1-2's edit, which is earlier than the FIX-1-3 report (22:34). The FIX-1-3 report says the
   allowlist is `()` and the comments were deleted, but neither is true. The FIX-1-3 acceptance commands do not
   check this, so the gap went unnoticed. While the entry stays, the test cannot catch `--visual` being dropped from
   section 3, and WP-29 depends on that flag. I confirmed that `_section3_flags()` now contains `--visual`, so an
   empty allowlist passes. Fix: WP-FIX-1-4.

### Non-blocking

- FIX-1-1 review: `_UsageError`, the `E_USAGE` envelope, `_first_command`, the `--json` no-command path, and the
  `EXIT_INTERRUPTED` constant all match the brief. Probes pass: unknown command (`command:""`), extra flags,
  `--json --help` (exit 0), and a human usage error with a single hint. Other fixture dirs (cv, golden, render) are
  not ignored.
- An unrecognized option after a subcommand (`validate-artifact nope jd --bogus`) is reported by the top-level
  parser, so the hint is `cvt --help` rather than `cvt validate-artifact --help`. This is argparse behavior. It is
  still an actionable hint.
- The FIX-1-2 lines match the brief verbatim, and each Core keeps its rule next to its `Check:` line.
- Worker reports can claim edits that never reached disk. For later fix-ups whose acceptance commands do not cover
  every step, a gate should grep for each step's result.

Next: run WP-FIX-1-4, then delta re-gate 2. That re-gate only needs to run WP-FIX-1-4's acceptance commands.

## Re-gate 2

**Verdict: APPROVE.** Blocking finding 5 is fixed. All five blocking findings from this gate are now closed, and the
full suite passes: 286 tests (`.cache/logs/G1/re2/suite.log`). Wave 1 is ready to commit.

| Source | Command | Result |
| --- | --- | --- |
| FIX-1-4 | `grep -n "UNDOCUMENTED_FLAGS = \|UNDOCUMENTED_FLAGS: " tests/integration/test_wave1.py` | PASS, one line: `61:UNDOCUMENTED_FLAGS: tuple[str, ...] = ()` |
| FIX-1-4 | `grep -c -- '"--visual"' tests/integration/test_wave1.py` | PASS, `0` |
| FIX-1-4 | `pytest -q tests/integration/test_wave1.py -k flags` | PASS, 1 passed, 60 deselected |
| FIX-1-4 / G | `pytest -q tests/unit tests/integration` | PASS, 286 passed in 2.88s |
| G | Mutation probe: copy `interfaces.md` to `.cache/g1re2/`, rename `--visual` in section 3, run `test_reference_flags_exist_in_section_3` against it | PASS: baseline passes; the mutant fails with `['critic-rubric.md: --visual']` (`.cache/logs/G1/re2/probe.log`) |

**Ownership.** Since re-gate 1, only `tests/integration/test_wave1.py`, `plan/reports/WP-FIX-1-4.md`, and the
orchestrator's `plan/STATUS.md` changed (by mtime against this report; no tracked diff exists because the wave is
uncommitted). The two comment lines are gone and the test count is unchanged at 286, so nothing else in the file was
added or removed. No out-of-ownership edits.

### Non-blocking

- The FIX-1-4 report matches what is on disk this time. Its acceptance commands check the end state directly, so
  the gap noted in re-gate 1 does not apply here.
- Carry-forward notes for wave 2 are unchanged (see "Notes for next wave" above). In particular, WP-29 must implement
  `brief critic --visual`. The integration test now fails if section 3 drops that flag.
