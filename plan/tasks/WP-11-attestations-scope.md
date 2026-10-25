# WP-11: Attestation store, scope resolution, `attest` command

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 | WP-01 (uses WP-04 fixtures) | Sonnet (`cv-builder`) | M |

## Goal

Implement the durable attestation store and its rules: the only writer of `attestations.json`, the
scope resolver that turns "the SRE related cv items" into concrete profile IDs, and the `cvt attest`
command used by `/cv-profile`.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: `attestations.schema.json`, `answers.schema.json` (`$defs/proposed_attestation`, `$defs/scope`),
  interfaces.md section 5 (WP-11 `attestations.py` / `scope.py` block, implemented here), section 7 (applying a
  reply, scope mapping), and section 8 (usable attestations).
- Read profile files with `jsonio.load_json`. Do not import WP-10's `profile.py` (it is being written in
  parallel). The only profile fields you need are `work[].id/name/position`, `engagements[].id/name/role_label`,
  and `kind`.
- Scope semantics:
  - `global` → `item_ids: []`, usable anywhere.
  - `role_label` → every work or engagement whose `role_label` (for work: `position`) matches case-insensitively
    on whole words. "SRE" matches "Role: SRE", not "PreSRE".
  - `items` → validate that each ID exists.
  - `unresolved` → `item_ids: []`, never usable until confirmed.
- On the sample CV, `role_label: SRE` must resolve to `["exp-2.e4", "exp-2.e5"]`. The test fixture below encodes
  the same structure.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/attestations.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/scope.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/commands/attest.py`
- `tests/unit/test_attestations.py`
- `tests/fixtures/profile/nested-engagements.json` (synthetic profile shaped like the sample: 3 employers, 10
  engagements, two with `role_label: SRE`; invented names)
- `plan/reports/WP-11.md`

## Steps

1. `attestations.py`:
   - `load_store` creates an empty valid store (`next_seq: 1`) in memory when the file is missing.
   - `save_store` validates against the schema and writes atomically.
   - `add` assigns `att-%03d` from `next_seq` and increments it, sets `status: proposed`, the timestamps, and
     `run_id`/`question_id`, and copies every field from the proposal.
   - `set_status` validates transitions: proposed → active | revoked, and active → revoked. Anything else raises
     `CvtError(CHECK_FAILED,"E_ATTEST_TRANSITION")`.
   - `usable(store, run_id, include_proposed)`.
   - `find_by_terms(store, terms)`: a helper for question suppression (WP-15) that returns active attestations
     whose `terms` intersect, case-insensitively.
2. `scope.py`:
   - `resolve(scope, profile)` returns a new scope with `item_ids` filled and sorted in document order. An
     unknown ID in `items` raises `CvtError(CHECK_FAILED,"E_SCOPE_UNKNOWN_ID")`.
   - `describe_mapping` returns labels like `"Royal Bank of Canada (RBC) — SRE (at Mobia)"`.
   - `candidates(description, profile, limit=4)` ranks items for an unresolved scope's words. Rank by role-label
     match, then employer or client name match, then keyword overlap; return at most `limit` items, labelled as in
     `describe_mapping`. Test: "the bank roles" on the nested fixture returns the bank engagement first.
   - `candidates(profile)` lists every engagement or work item with its label. It is used for unresolved-scope
     question skeletons.
3. `cvt attest` subcommands: `list` (table: id, type, claim, status, placement, scope summary, created run), `show
   ID` (full JSON), `revoke ID` (asks nothing, since the agent confirms with the user first), and `activate ID`.
   Address the store with `RUN` (its `person_slug`) or `--person P`. `--json` is supported throughout.
4. Tests:
   - ID assignment and `next_seq` that is never reused after a revoke.
   - Transitions.
   - Schema-valid writes.
   - `role_label` resolution (SRE → the two engagements; case and whole-word handling).
   - Unknown IDs.
   - `unresolved` handling.
   - `usable` filtering (revoked never; proposed only for the same run when `include_proposed`).
   - CLI list/show/revoke via `run_cvt`.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_attestations.py   # passes
```

## Definition of done

The common definition of done.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-11.md` under `## ESCALATION`. Do not change it.
