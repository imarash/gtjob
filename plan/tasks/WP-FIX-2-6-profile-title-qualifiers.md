# WP-FIX-2-6: `profile-build` rejects a title or role label that drops a seniority qualifier

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 (fix-up from WP-G2 re-gate 1) | WP-FIX-2-4, **user approval of C3 in `plan/reports/WP-G2-contract-change.md`** | Sonnet (`cv-builder`) | S-M |

Dispatch only after the orchestrator has applied C3 to `plan/contracts/interfaces.md`.

## Goal

`profile-build` checks a typed title with a bare substring test, so a title that drops its seniority word passes.
Provenance rule 6 then requires the tailored title to equal that profile title, and the PDF shows the promoted title.
`truthfulness.md` rule 6 forbids promoting a title. Gate probes on the junior `profile-map.json` exit 0 today and must
exit 1 with `not_verbatim`:

| Mutation | CV line says |
| --- | --- |
| work[0] `position: "DevOps Engineer"` | `Brightfield Logistics \| Junior DevOps Engineer \| …` |
| work[1] `position: "IT Support"` | `Cedar Valley College \| IT Support Intern \| …` |

## Context

- Read `plan/tasks/_COMMON.md`.
- Contract after C3: `sed -n '/^### WP-10 /,/^### /p' plan/contracts/interfaces.md`.
- `cvtlib/profile_map.py`: the builder's `check_in(value, cited, label, what)` (around line 93) is called for
  `title` (`w["position"]`, around line 179) and `role label` (`e["role_label"]`, around line 188).
- `cvtlib/profile.py`: `normalize_text` and `comparable` (around lines 67-75) map en and em dashes to `-`.
  `verify_verbatim` (the `profile-verify` path) checks work and engagement fields against the whole CV.
- Junior fixtures: `tests/fixtures/cv/jamie-rivera-junior.txt` and `tests/fixtures/golden/junior/profile-map.json`.
  The golden must still build a profile equal to `golden/junior/profile.json`.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/profile.py` (one constant, one helper, one call in `verify_verbatim`)
- `.claude/skills/tailoring-cvs/scripts/cvtlib/profile_map.py` (the title and role-label checks only)
- `tests/unit/test_profile_map.py`, `tests/unit/test_profile.py`
- `.claude/skills/tailoring-cvs/references/stage-profile.md` (the "Typed values" bullet, line 35, only)
- `plan/reports/WP-FIX-2-6.md`

## Steps

1. In `profile.py`, add a module-level constant `SENIORITY_QUALIFIERS`, a lowercase tuple of at least: `junior`, `jr`,
   `intern`, `internship`, `trainee`, `apprentice`, `assistant`, `associate`, `graduate`, `entry-level`, `student`,
   `volunteer`, `deputy`, `acting`, `interim`, `co`, `part-time`, `temporary`, `temp`, `placement`. Only add words that
   lower seniority when dropped. Do not add common prose words (`working`, `at`, `the`): an honest title followed by one
   of them in a prose line would then fail with no way for the mapper to fix it.
2. In `profile.py`, add `dropped_qualifier(value: str, text: str) -> str | None`. Compare `comparable(value)` with
   `comparable(text)`, and return `None` if the value is empty or does not occur at all (`check_in` reports that case).
   For each occurrence:
   - the token before it is the run of `[\w.-]` characters that ends right before the occurrence, after skipping only
     spaces;
   - the token after it is the run of `[\w.-]` characters that starts right after the occurrence, after skipping only
     spaces;
   - strip a trailing `-` or `.` from each token before comparing.

   Return `None` as soon as one occurrence has neither token in `SENIORITY_QUALIFIERS`. Otherwise return a short
   reason, for example `drops the qualifier 'junior'`.

   Punctuation such as `|`, `,`, `(`, or a spaced ` - ` ends a token, so a full title between separators always passes.
   `Co-Founder` → `Founder` must fail (the token before is `co-`).
3. In `profile_map.build_profile`, for `title` and `role label`, call `dropped_qualifier(value, " ".join(cited))`. Report
   each non-`None` result as `not_verbatim`, for example
   `exp-1: title 'DevOps Engineer' drops the qualifier 'junior' in its cited lines; copy the full title`.
   Skip empty values.
4. In `profile.verify_verbatim`, apply the same check to work `position` and engagement `role_label` against the CV
   text, using code `fact_mismatch`.
5. Tests:
   - in `test_profile_map.py`, one test per mutation in the Goal table, plus `Co-Founder` → `Founder` and
     `Assistant Manager` → `Manager` on a small synthetic CV and map;
   - positives: the full title passes; `Senior Engineer (Contract)` with title `Senior Engineer` passes; a title
     that appears once with a qualifier and once without passes;
   - re-assert that the junior golden builds unchanged;
   - in `test_profile.py`, one `verify_verbatim` case.
6. `stage-profile.md` line 35: append one sentence: "Copy titles and role labels whole, with every qualifier (Junior,
   Intern, Assistant)."

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_profile.py tests/unit/test_profile_map.py   # passes
uv run pytest -q tests/unit/test_refs_stages_a.py                            # passes (stage-profile.md still valid)
uv run pytest -q tests/integration/test_wave2.py                             # passes (golden map still builds)
uv run pytest -q tests/unit tests/integration                                 # passes
```
