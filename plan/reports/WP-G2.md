# WP-G2: Gate for wave 2

## Verdict

**FIX-UPS.** Every acceptance command of WP-08 to WP-13 and WP-I2 passes on re-run, apart from WP-I2's full-suite
command, which fails inside Cursor. The core validators are strong: 34 of 36 adversarial provenance probes behave
correctly, and every focus item in the brief passes. There are four blocking findings: a test-isolation bug that makes
the suite red in the build's own environment, real candidate PII in committed tests, and two truthfulness gaps that
need a contract change. Logs and probe scripts are in `.cache/logs/G2/` and `.cache/g2/`.

## Acceptance results

| WP | Command | Result |
| --- | --- | --- |
| 08 | `pytest tests/unit/test_run_commands.py` | PASS, 22 passed |
| 08 | smoke: `init --slug smoke` then `--json status latest` (temp `GTJOB_HOME`) | PASS, stage `initialized`, next_action `… ingest 20261026-smoke` |
| 09 | `pytest tests/unit/test_ingest.py` | PASS, 19 passed |
| 09 | `pytest tests/unit/test_ingest.py -m sample` | PASS, 1 passed (sample present) |
| 10 | `pytest tests/unit/test_profile.py` (+ `test_profile_map.py`) | PASS, 28 passed / 1 skipped (private golden absent); 17 passed |
| 11 | `pytest tests/unit/test_attestations.py` | PASS, 39 passed |
| 12 | `pytest tests/unit/test_render.py`; `cvtlib.render` import | PASS, 33 passed; `cvtlib.render ok` |
| 13 | `pytest test_lexicon test_provenance test_checks` | PASS, 126 passed |
| 13 | `wc -l tech-terms.txt` | PASS, 686 (≥ 400) |
| I2 | `rg "TODO\(I-2\)"` → none | PASS, `no stand-ins` |
| I2 | `pytest tests/unit tests/integration` | **FAIL in Cursor**: 2 failed, 573 passed, 1 skipped. With `CURSOR_*`/`CLAUDECODE` unset: 575 passed, 1 skipped |

Ownership: `git status --porcelain` shows only wave 2 owned files plus `plan/reports/`, `plan/STATUS.md`
(orchestrator), and `prompts/` (the user's planning prompt, not a worker file). The one out-of-ownership edit is
`tests/integration/__init__.py`, which gained a blank line (WP-01 file, reverted in FIX-2-1). WP-I2's cross-WP edits
in `provenance.py`, `checks.py`, `commands/checks.py`, and `profile.py` are within its brief ("minimal fixes in wave 2
files") and are listed in its report.

## Focus probes (all in temp `GTJOB_HOME`s under `.cache/g2/`)

1. **Provenance** (`.cache/logs/G2/probe.log`). I built a junior run via the CLI with the golden artifacts, then
   added four attestations: Helm (active), SLO scoped to `exp-2` (active), Kubernetes (revoked), and `k8s` (active).
   I ran `check-tailored` on 36 mutations of the golden `tailored.json`.
   - **Exit 1, exact section 8 format:** tools (Linkerd, Kubernetes on `skl-1`, lowercase, invented `Zorbix`, headline,
     Stripe, EKS from a `k8s` attestation, Cyrillic-homoglyph and zero-width tricks); numbers (12→15, 8→5 and 12→2
     substring traps, 40%→60%, `1,200`, injected year); start/end date, title, employer, header email; a revoked
     attestation; the SLO attestation outside its scope; visa, relocation and work-authorization text.
   - **Pass (exit 0):** `k8s`↔Kubernetes both ways, `runbook(s)`, singular `pipeline`, `Grafana's`, `AWS's`.
   - **Gaps:** a bullet under the internship citing a Brightfield highlight **passes** (blocking, C1). "fifteen
     services" passes (known, contract is digits-only; non-blocking).
2. **Ingest on the real sample:** 6 pages, 278 lines. Employer and date share a line for all 6 employers; the email
   appears once (line 1); no page-number lines; 4 repeated header lines removed and the header hoisted. `cv.txt` is
   byte-identical across two ingests (sample and junior).
3. **Scope:** `role_label: SRE` (and `sre`) resolves to exactly `exp-2.e4`, `exp-2.e5` on the WP-11 synthetic fixture
   (no private golden). `unresolved` always gives `item_ids: []`, even when the AI supplies IDs, and is never usable.
   `candidates()` only ranks; it never fills a scope.
4. **Render safety:** templates read only `json(sys.inputs.…)` and are copied byte-for-byte; no `eval`. A bullet with
   `#eval(...)`, `#read("/etc/passwd")`, `#set page(...)`, `$…$`, `<lbl>`, `@ref`, `//`, `\` and "Ignore previous
   instructions…" rendered literally. Title, Author and Keywords metadata are set; all 4 fonts are embedded and subset.
5. **Attestation store:** only proposed→active/revoked and active→revoked are allowed. `next_seq` stays monotonic
   after revokes. Loading a missing store writes nothing. `save_store` refuses a foreign `person_slug` or a
   schema-invalid store and writes atomically (temp + rename).
6. **`profile-build`:** a shifted range gives `range_error` + `unmapped_line`; a dropped line gives `unmapped_line`;
   an employer typo, or an employer taken from another job's lines, gives `not_verbatim`. **Gaps:** `start_date` or
   `end_date` contradicting `date_text`, a wrong work location, and a wrong degree `area` all exit 0 (blocking, C2).

## Findings

### Blocking

1. **Suite red inside Cursor** (`tests/conftest.py`, WP-01 fixture vs WP-08 `hostdetect`). `workspace` clears only
   `GTJOB_HOST`, so `test_state.py` sees host `cursor`. WP-I2's acceptance command fails in the environment where all
   workers and gates run, and every later "unit suite passes" check inherits the noise. → FIX-2-1.
2. **Real candidate PII in committed tests.**
   - `test_ingest.py::test_real_sample_cv` asserts the candidate's email and current employer.
   - `test_wave2.py` `SAMPLE_REQUIRED_TEXT` lists three real employers/clients/university.
   - `test_render.py` copies a real past employer, title, and dates.

   `_COMMON.md` section 4 forbids this. → FIX-2-2 (values move to a git-ignored private file).
3. **Cross-job misattribution passes provenance** (contract gap, section 8). Profile refs are not scoped to the
   bullet's parent job, while attestations are. → contract change C1, then FIX-2-3.
4. **The profile's normalized dates, locations, and degree are unverified** (contract gap, section 5, WP-10).
   An invented date in `profile-map.json` passes `profile-build` and then provenance rule 6, and reaches the PDF.
   → contract change C2, then FIX-2-4.

### Non-blocking

- Spelled-out numbers ("fifteen") are not rule-5 checked (the contract is digits-only). Consider a later contract pass.
- A `role_label` scope matching nothing gives `item_ids: []` silently: unusable in bullets, still usable in skills.
- **Render visuals** (hiring-manager view): clean, single-column, ATS-friendly; dates right-aligned, thin rules, clear
  hierarchy, draft placeholders in red. Weaknesses: the name/headline/contact block is cramped under the 24pt name; a
  1-page CV still shows "1 / 1"; the junior name is grey, not the accent; unfitted senior `standard` orphans Education
  on page 2 (WP-14 `fit`). The test writes no junior PNG (only `junior.pdf`); I rasterized it.
- Raw `pdftotext` splits the 24pt name onto two lines ("Jamie" / "Rivera"); `-layout` and `pypdf` keep it on one line.
- `cv.md` does not escape Markdown (`*bold*` in CV text becomes emphasis). Escape it if `cv.md` is ever shipped.
- Typst 0.15 exposes Semibold as weight 600 of "Source Sans 3" (WP-12); `assets/fonts/FONTS.md` (WP-02) says otherwise.
- `references/answer-parsing.md:136` (wave 1, ships in the skill) quotes a real past employer of the sample candidate
  in an example reply. This is the user's call; FIX-2-2's informational grep will list it.
- WP-13's interpretations are accepted because they match section 7: rule 10 warns before `approved` and fails from
  `approved` on; this run's proposed corrections apply to rule 6.

## Escalations

- **WP-09: the `ingest.method` enum lacks `ocr`. Decision: the contract stands for now.** `cvtlib.extras.ocr_pdf`
  does not exist (stretch, WP-28), so the OCR path is unreachable. Storing `none` with the OCR warning and
  `scanned_suspect=true` is honest meanwhile. WP-28 should add `"ocr"` to `state.schema.json` (both copies) and set
  `OCR_STATE_METHOD = "ocr"` when it implements OCR.

## Fix-up WPs

| Brief | Owner | Blocking finding | Needs contract change |
| --- | --- | --- | --- |
| `plan/tasks/WP-FIX-2-1-host-env-isolation.md` | Haiku (`cv-builder-lite`) | 1 | no |
| `plan/tasks/WP-FIX-2-2-sample-pii-out-of-tests.md` | Sonnet (`cv-builder`) | 2 | no |
| `plan/tasks/WP-FIX-2-3-provenance-parent-scope.md` | Sonnet (`cv-builder`) | 3 | C1 |
| `plan/tasks/WP-FIX-2-4-profile-build-dates.md` | Sonnet (`cv-builder`) | 4 | C2 |

The owned files do not overlap, so all four can run in parallel once C1/C2 are approved. FIX-2-1 and FIX-2-2 can start
now. Contract change: `plan/reports/WP-G2-contract-change.md`. **Apply it only after the user agrees.**

## Notes for next wave

- WP-14: `validate` calls `check_tailored(draft=False)` after approval; `ats_roundtrip` collapses whitespace before
  the name check; `fit` pulls a lone Education section back onto page 1.
- WP-15: treat an empty `role_label` resolution as unresolved, and steer away from generic labels (`Engineer` matches 8).
- WP-16 `apply-edits` owns stage regression when `tailored.json` changes after approval (WP-13 open issue).
- WP-17 (classic): keep the `json(sys.inputs.data)`-only rule and the literal-markup test.

## Re-gate 1

**Verdict: FIX-UPS.** FIX-2-2, 2-3, and 2-4 are fully verified, and FIX-2-1's conftest fix works. Two blockers remain:
FIX-2-1's `__init__.py` restore is not on disk, and a new title-promotion gap needs contract change C3. Logs:
`.cache/logs/G2/rg1/`; probes: `.cache/g2/probe_rg1.py`.

| Fix-up / WP | Command | Result |
| --- | --- | --- |
| 2-1 | `pytest test_state.py test_run_commands.py` (Cursor shell, `CURSOR_*` set) | PASS, 52 passed |
| 2-1 | `git diff --exit-code HEAD -- tests/integration/__init__.py` | **FAIL**: file is 1 byte (`+` blank line), HEAD is 0 |
| 2-2 | `pytest test_ingest test_render test_wave2` | PASS, 57 passed |
| 2-2 | `pytest test_ingest.py -m sample` | PASS, 1 passed (not skipped) |
| 2-2 | `git check-ignore` private file; PII grep on 3 owned files | PASS, `private file ignored`; `no sample PII in owned files` |
| 2-3 | `pytest test_provenance test_checks test_lexicon` | PASS, 136 passed |
| 2-4 | `pytest test_profile test_profile_map` | PASS, 68 passed / 1 skipped (WP-20 private profile) |
| 2-3/2-4/I2 | `pytest tests/integration/test_wave2.py` | PASS, 5 passed |
| 01, 05, 06 | `test_schemas/foundation/state`; `test_refs_writing`, `test_refs_stages_a`; schema `diff -r` | PASS, 109; 34; no diff |
| 09, 10, 12, 13 | WP acceptance commands (unit files, `render` import, `wc -l tech-terms` 686) | PASS, 19; 30+1 skip; 33, `ok`; 686 |
| I2 | `rg "TODO\(I-2\)"`; full suite | PASS, `no stand-ins`; **608 passed, 1 skipped, 0 failed inside Cursor** |

**Ownership.** The tracked diffs are within the briefs: the conftest `workspace` fixture plus two constants;
`truthfulness.md` rule 3 line plus one example; `stage-profile.md` line 35; `interfaces.md` matches the approved C1/C2
text exactly (orchestrator). The only out-of-ownership change is still `tests/integration/__init__.py`. FIX-2-1's report
says "init restored", but that is false on disk.

**Probes.**
- The 36 wave-2 provenance mutations give 35 correct; the miss is the known "fifteen" note.
  - C1 is closed: an internship bullet citing a Brightfield highlight now exits 1, with `cites exp-1.b1 from another
    job; parent is exp-2`.
- Nine new rule 3a edge probes behave as specified: a foreign ref in an intro fails; a bullet that cites only `basics`
  fails; a mixed own-and-foreign bullet fails; re-pointing `t-exp-2.profile_id` to `exp-1`, with or without copying
  exp-1's facts, fails (rule 6 or 3a); a bare own `exp-1` passes; a summary citing both jobs passes.
- All 17 wave-2 profile-map mutations are correct. C2 is closed for start/end dates, location, degree area, and
  `present`.
- New C2 edge probes behave as specified: education year, study type, education location, basics city and country,
  certificate date, and another job's city all fail.

### Blocking

1. **`tests/integration/__init__.py` is still modified** (FIX-2-1 acceptance 2 fails). → FIX-2-5 (Haiku; one
   `git checkout`). The orchestrator may simply run `git checkout HEAD -- tests/integration/__init__.py` instead.
2. **A title can drop its seniority word and pass `profile-build`** (WP-10, same class as C2). `position: "DevOps
   Engineer"` (CV: "Junior DevOps Engineer") and `"IT Support"` (CV: "IT Support Intern") both exit 0. Rule 6 then
   carries the promoted title into the PDF, which `truthfulness.md` rule 6 forbids. The fix needs a contract change.
   → C3 in `plan/reports/WP-G2-contract-change.md` (awaiting the user), then FIX-2-6 (Sonnet).

### Non-blocking

- **Skills-list laundering.** C1 allows non-`exp` refs. A bullet under `t-exp-2` citing `exp-2.b2` + `skl-1` can claim
  Terraform at the internship (exit 0). Consider limiting rule 4 term support for bullets to own-job refs and
  attestations in a later contract pass.
- **Date check is per value, not positional** (FIX-2-4's open issue, confirmed). A current job given `end_date
  2024-02` ("Feb 2024 - Present") passes. "Mar 2020 - Jan 2021" would accept `start_date 2020-01`, a 2-month stretch.
  The education `end_date` month is unchecked (year only, per C2). `study_type "BS"` passes as a substring of "BSc".
- **Cosmetic messages.** The ID is doubled ("exp-1: exp-1: start_date …"), and location parts are quoted unstripped
  (`' TX'`).
- **FIX-2-2's residual grep hits are not new and not blocking.** The 3 schemas and `senior-render.json` all match one
  literal: a large public bank's name. The planner's contracts use it as the example client (`plan/contracts/*`,
  committed in wave 1), and it is also a client in the sample CV. It is the user's call whether to swap it for an
  invented name.
- When a mutation cites an unknown foreign ref, it now reports both `unknown_ref` and `ref_out_of_scope`. That is
  acceptable.

### Fix-up WPs (round 2)

| Brief | Owner | Finding | Needs contract change |
| --- | --- | --- | --- |
| `plan/tasks/WP-FIX-2-5-restore-integration-init.md` | Haiku (`cv-builder-lite`) | 1 | no |
| `plan/tasks/WP-FIX-2-6-profile-title-qualifiers.md` | Sonnet (`cv-builder`) | 2 | C3 |

The two briefs own no files in common, so they can run in parallel. FIX-2-5 can start now; FIX-2-6 starts after the user
approves C3. Re-gate 2 then re-runs only these two briefs' acceptance commands and those of WP-10 and WP-06.

## Re-gate 2

**Verdict: FIX-UPS (one small fix).** FIX-2-5 is verified, and FIX-2-6 closes both C3 gate probes through
`profile-build` and `verify_verbatim`. One blocker remains: the code catches a hyphenated qualifier before the title
but not after it, which C3 requires. Logs: `.cache/logs/G2/rg2/`; probes: `.cache/g2/probe_rg2.py`, `probe_rg2_fix.py`.

| Fix-up / WP | Command (Cursor shell, `CURSOR_*` set) | Result |
| --- | --- | --- |
| 2-5 | `git diff --exit-code HEAD -- tests/integration/__init__.py`; `wc -c` | PASS, `init restored`; `0 bytes` |
| 2-6, 10 | `pytest test_profile.py test_profile_map.py`; WP-10 `pytest test_profile.py` | PASS, 87 passed / 1 skip; 31 / 1 skip |
| 2-6, 06 | `pytest tests/unit/test_refs_stages_a.py` | PASS, 16 passed |
| 2-6 | `pytest tests/integration/test_wave2.py` (golden map still builds) | PASS, 5 passed |
| 2-5, 2-6 | full suite `pytest tests/unit tests/integration` | PASS, **627 passed, 1 skipped, 0 failed** |

**Ownership.** `tests/integration/__init__.py` is no longer in `git status`. FIX-2-5 used `git show HEAD:… >` rather than
`git checkout` (`_COMMON.md` forbids state-changing git); the result is identical, so that is accepted. FIX-2-6 changes only its
owned files. `stage-profile.md` changes only line 35 versus `HEAD`. The C3 text in `interfaces.md` matches the
proposal exactly. No out-of-ownership changes remain.

**Probes.**
- `profile-build` CLI, junior map: `DevOps Engineer` and lowercase `devops engineer` give `not_verbatim … drops the
  qualifier 'junior'`, and `IT Support` gives `… 'intern'` (exit 1). The golden map, the full titles, and `Support
  Intern` (drops `IT`, which is not a qualifier) all exit 0.
- `verify_verbatim` on the junior golden profile: both mutations give `fact_mismatch … copy the full position`; the
  golden profile gives none.
- `dropped_qualifier` catches `Jr.`, upper case, NBSP and thin space, zero-width joins, `Co-`/`Co–Founder`,
  `Entry-Level`, `Part-Time`, and a qualifier after the title. Spaced ` - `, `,`, `(…)`, and `Team Lead` pass, as specified.

### Blocking

1. **A qualifier hyphenated after the title is missed** (C3: "only spaces or a hyphen in between"). `Software
   Engineer` from `Software Engineer-Intern` or `Software Engineer–Intern` (an unspaced en dash, normalized to `-`)
   returns `None`, because only the left-hand token has its hyphen stripped. FIX-2-6's report lists this as a
   deviation, and the brief's wording ("strip a trailing `-`") caused it. The fix changes `rstrip` to `strip` on both
   tokens. I simulated it by monkeypatching: 92 passed, 1 skipped across `test_profile`, `test_profile_map`, and
   `test_wave2`. → FIX-2-7 (Haiku).

### Non-blocking

- **The adjacency rule misses a qualifier that is not next to the value** (allowed by C3's wording). `Engineer` from
  `Junior DevOps Engineer` and `Manager` from `Assistant Project Manager` both pass. A rule over the whole segment
  between separators would catch these, but it would raise false positives (see the next point). Consider it in a later
  contract pass, alongside the skills-list laundering note.
- **`co` gives a false positive when the employer and title share a segment.** `Acme Co Software Engineer 2020` fails
  with no honest fix for the mapper. This is rare, because headers almost always separate the employer and the title.
- **Occurrences are not word-bounded.** In `Junior Developer | DeveloperHub Inc`, the substring inside `DeveloperHub`
  counts as an unqualified occurrence, so `Developer` passes. This is contrived and low risk.
- Fixed the stale C3 status line at the top of `WP-G2-contract-change.md`.

### Fix-up WPs (round 3)

| Brief | Owner | Finding | Needs contract change |
| --- | --- | --- | --- |
| `plan/tasks/WP-FIX-2-7-qualifier-trailing-hyphen.md` | Haiku (`cv-builder-lite`) | 1 | no |

Re-gate 3 re-runs only FIX-2-7's acceptance commands (they include WP-10's) and the full suite. If those pass, the
verdict is APPROVE. I checked that FIX-2-7's `python -c` acceptance line fails on the current code.

## Re-gate 3

**Verdict: APPROVE.** FIX-2-7 is verified and wave 2 has no remaining blocking findings. Logs: `.cache/logs/G2/rg3/`.

| Fix-up / WP | Command (Cursor shell, 10 `CURSOR_*`/`CLAUDECODE` vars set) | Result |
| --- | --- | --- |
| 2-7, 10 | `pytest test_profile.py test_profile_map.py` | PASS, 90 passed / 1 skipped |
| 2-7 | `pytest tests/integration/test_wave2.py` (golden map still builds) | PASS, 5 passed |
| 2-7 | `python -c "… dropped_qualifier …"` | PASS, `hyphen ok` |
| 2-7 | full suite `pytest tests/unit tests/integration` | PASS, **630 passed, 1 skipped, 0 failed** |

**Ownership.** The tracked `git diff --stat HEAD` is unchanged from re-gate 2. The only new path is
`plan/reports/WP-FIX-2-7.md`. Both owned code files are untracked, so there is no diff to compare against. I read
`dropped_qualifier` instead: the only differences are the two `.strip(TOKEN_TRIM_CHARS)` calls and the docstring
sentence, as the brief specifies. The test table gained exactly the three specified rows (lines 407-409).

**Probes** (`.cache/g2/probe_rg2.py`, re-run, plus `.cache/logs/G2/rg3/probe_rg3.log`).
- `Software Engineer` from `Software Engineer-Intern`, `…–Intern` (en dash), `…—Intern` (em dash), `…--Intern`, and
  `… -Intern` now gives `drops the qualifier 'intern'`. The spaced ` - ` and ` -- `, plus `(Intern)`, still give `None`.
- No regressions. Every round-2 `profile-build` CLI and `verify_verbatim` probe is unchanged. The two misses are the
  ones already logged as non-blocking in re-gate 2 (bare `Engineer`, and `DeveloperHub`).
- `Software Engineer-Platform`, a non-qualifier hyphen suffix, gives `None`, so stripping on both sides adds no false
  positive.

### Non-blocking

- A hyphen followed by a space (`Software Engineer- Intern`) gives `None`. The `-` ends the token before the space, so
  the qualifier is never reached. This is contrived. Fold it into the later contract pass on the qualifier rule, along
  with the re-gate 2 notes.