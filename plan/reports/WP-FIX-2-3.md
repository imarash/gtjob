# WP-FIX-2-3: provenance rule 3a (a bullet cites only its own job)

Status: DONE. Contract C1 (interfaces.md section 8, rule 3a) was already applied when I started.

## Summary

- `provenance.py` now enforces rule 3a on every work bullet, every engagement bullet, and every intro with non-empty text.
  - `allowed_job_ref(ref, parents)` returns the allowed `exp-*` refs for a parent.
    - Work `exp-N`: `exp-N` and `exp-N.*`.
    - Engagement `exp-N.eK`: itself, `exp-N.eK.*`, and work-level highlights `^exp-N\.b\d+$`. The bare work and sibling engagements are not allowed.
  - `_check_job_scope` reports each foreign `exp-*` ref as `ref_out_of_scope`: `<kind> <id> cites <ref> from another job; parent is <profile_id>`.
  - It also reports `<kind> <id> has no ref from its own job; parent is <profile_id>` when no ref is an own-job ref or a usable in-scope attestation (scope global, or covering the element's engagement or work).
  - Prefix lookalikes such as `exp-20.b1` under `exp-2` are rejected.
  - The new constants `EXP_PREFIX`, `REF_SEP`, and `WORK_HIGHLIGHT_SUFFIX` are named at module level.
- New mutations in `mutations.json`:
  - `cross_employer_bullet`: a `t-exp-2` bullet with the text and ref of `exp-1.b1` fails with `ref_out_of_scope`.
  - `bullet_only_skill_ref`: a `t-exp-1` bullet whose only ref is `skl-1` fails with `ref_out_of_scope`.
  - `own_job_tools_line_ok`: a `t-exp-1` bullet citing `exp-1.b6` and `exp-1.b3` passes.
- New tests in `test_provenance.py` use `nested-engagements.json` with one work-level highlight added in memory. They cover:
  - a sibling engagement's highlight fails;
  - the own work's `exp-2.b1` passes;
  - the bare work `exp-2` from an engagement bullet fails;
  - `exp-20.b1` under `exp-2` fails;
  - an in-scope attestation counts as an own-job ref (`att-001` is accepted under `exp-1` and rejected under `exp-2`);
  - an empty-text intro is not scoped.
- `truthfulness.md`: one sentence added to the rule 3 summary line and one Forbidden example added under "Attestation scope (rule 3)".

## Files changed

- `.claude/skills/tailoring-cvs/scripts/cvtlib/provenance.py`
- `tests/unit/test_provenance.py`
- `tests/fixtures/provenance/mutations.json` (three mutations added)
- `.claude/skills/tailoring-cvs/references/truthfulness.md`
- `plan/reports/WP-FIX-2-3.md`

## Acceptance

```
uv run pytest -q tests/unit/test_provenance.py tests/unit/test_checks.py tests/unit/test_lexicon.py
136 passed in 8.78s            (log: .cache/logs/WP-FIX-2-3/a1.log)

uv run pytest -q tests/integration/test_wave2.py
5 passed in 4.68s              (log: .cache/logs/WP-FIX-2-3/a2.log)

uv run pytest -q tests/unit tests/integration
608 passed, 1 skipped in 26.14s (log: .cache/logs/WP-FIX-2-3/a3.log)

uv run pytest -q tests/unit
542 passed, 1 skipped in 20.47s (log: .cache/logs/WP-FIX-2-3/unit.log)
```

The 1 skip is the existing optional sample CV test.

## Deviations

- An element with no refs reports only `missing_refs` (rule 1), not an extra "no ref from its own job".
- A cross-job bullet gets both messages: one `cites ... from another job` per foreign ref, plus one `has no ref from its own job` if nothing in scope remains. This follows the brief literally.
- `mutations.json` was re-serialized in the original compact one-line-per-field style; the existing entries are unchanged.

## Open issues

- A foreign ref that does not exist, such as `exp-9.b1` in the `unknown_ref` mutation, now produces `ref_out_of_scope` as well as `unknown_ref`. The existing test still passes.
