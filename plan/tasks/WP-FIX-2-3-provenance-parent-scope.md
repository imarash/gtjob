# WP-FIX-2-3: Provenance rule 3a — a bullet cites only its own job

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 (fix-up from WP-G2) | WP-13, WP-I2, **user approval of `plan/reports/WP-G2-contract-change.md` C1** | Sonnet (`cv-builder`) | S-M |

Dispatch only after the orchestrator has applied C1 to `plan/contracts/interfaces.md`.

## Goal

Today a bullet under one job can cite another job's highlight and pass `check-tailored`. At the gate, a bullet under
`t-exp-2` (Cedar Valley College) with the text and ref of `exp-1.b1` (Brightfield Logistics) exited 0. Implement
interfaces.md section 8 rule 3a (contract change C1) so that it fails with `ref_out_of_scope`.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contract: `sed -n '/^## 8\./,/^## 9\./p' plan/contracts/interfaces.md` (rule 3a after the change).
- `cvtlib/provenance.py`: find where rule 3 (`ref_out_of_scope` for attestations) is checked for bullets and intros.
  Add rule 3a next to it. Reuse the existing violation shape (`item_id` first in the message).
- Tailored shape: `experience[]` items have `profile_id` (`exp-N`), `intro`, `bullets[]`, and `engagements[]`. Each
  engagement has `profile_id` (`exp-N.eK`) and `bullets[]`.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/provenance.py`
- `tests/unit/test_provenance.py`
- `tests/fixtures/provenance/mutations.json` (add mutations only)
- `.claude/skills/tailoring-cvs/references/truthfulness.md` (rule 3 summary line 15 and the rule 3 example around
  lines 43 and 107-110 only)
- `plan/reports/WP-FIX-2-3.md`

## Steps

1. In `provenance.py`, add a function that returns the allowed `exp-*` refs for a parent `profile_id`:
   - for work `exp-N`, `exp-N` itself or any ref starting with `exp-N.`;
   - for engagement `exp-N.eK`, `exp-N.eK`, any ref starting with `exp-N.eK.`, or a work-level highlight matching
     `^exp-N\.b\d+$`.
2. For every experience `intro` with non-empty text, every work bullet, and every engagement bullet:
   - Report each `exp-*` ref outside the allowed set as `ref_out_of_scope`, with the message
     `bullet <id> cites <ref> from another job; parent is <profile_id>` (use `intro` for intros).
   - If the element has no ref in the allowed set and no usable in-scope attestation, report one `ref_out_of_scope`:
     `bullet <id> has no ref from its own job; parent is <profile_id>`.
3. Add mutations to `mutations.json`, each failing with `ref_out_of_scope`:
   - `cross_employer_bullet`: a bullet under `t-exp-2` with the text and refs of `exp-1.b1`;
   - `bullet_only_skill_ref`: a bullet under `t-exp-1` whose only ref is `skl-1`.
   - Add one positive (passes): a bullet under `t-exp-1` citing `exp-1.b6` (the tools line) and `exp-1.b3`.
4. Add a unit test with a small synthetic profile that has engagements (you may load
   `tests/fixtures/profile/nested-engagements.json`). The test asserts that:
   - an engagement bullet citing a sibling engagement's highlight fails;
   - citing its own work's `exp-N.bJ` passes;
   - citing the bare work `exp-N` from an engagement bullet fails.
5. `truthfulness.md`: extend the rule 3 line and example with one sentence each, for example: "Forbidden: a bullet
   under one job that cites another job's lines." Keep the guide's numbering and style.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_provenance.py tests/unit/test_checks.py tests/unit/test_lexicon.py   # passes
uv run pytest -q tests/integration/test_wave2.py           # passes (the junior golden still passes check-tailored)
uv run pytest -q tests/unit tests/integration               # passes
```
