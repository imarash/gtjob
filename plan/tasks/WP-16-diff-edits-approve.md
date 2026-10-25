# WP-16: Checkpoint 2 commands (`diff`, `apply-edits`, `approve`)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 | WP-10 (profile), WP-11 (attestations), WP-13 (provenance) | Sonnet (`cv-builder`) | M-L |

## Goal

Show the proposed CV as per-item before/after diffs with a section outline. Apply approvals, rejections, edits,
and free-text change requests atomically and safely. On approval, promote this run's attestations to active, so
future runs reuse them.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: interfaces.md section 7 (checkpoint 2), section 3 (`diff`, `apply-edits`, `approve` rows), section 5
  (WP-16 block, implemented here), section 6 (regression rules), `edits.schema.json` (op semantics in the
  descriptions are normative), and `tailored.schema.json`.
- APIs you call:
  - `cvtlib.provenance.check_tailored` / `check_logistics` (WP-13). `apply-edits` rejects the whole batch on any
    violation.
  - `cvtlib.profile.item_text` / `merged_view` (WP-10).
  - `cvtlib.attestations` (WP-11).
  - `cvtlib.state`.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/diff.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/edits.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/commands/review.py` (`diff`, `apply-edits`, `approve`)
- `tests/unit/test_diff.py`, `tests/unit/test_edits.py`
- `plan/reports/WP-16.md`

## Steps

1. `diff.diff_items(tailored, profile, previous)`:
   - Against the profile: before = the joined `item_text` of the bullet's profile-ID refs (bullet-level refs
     preferred), after = the tailored text.
   - `kind`: `kept` when the normalized texts are equal, otherwise from the bullet's `origin`.
   - Also emit `dropped` entries for `omitted`.
   - Against the previous version: compare by ID and text → `added`/`changed`/`dropped`.
   - Include the summary, headline, skills groups, and the earlier line.
2. `diff.outline(tailored)` lists the sections with the employers, engagements, and bullet counts, plus an estimated
   page count using `ESTIMATED_LINES_PER_PAGE = 58` as a named constant, labeled "estimate".
   `render_diff_md(items, outline)` produces numbered items (`[3] t-exp-2.e4.b1 (rewritten; refs exp-2.e4, att-004,
   att-005)`), with before/after as blockquotes, so the user can say "reject 3".
3. `edits.apply_ops(tailored, ops, profile)`: a pure, ordered application of every op in `edits.schema.json`.
   - `reject` on `origin: kept` → drop. On rewritten/merged/attested → restore the original profile text when
     exactly one bullet ref exists, else drop.
   - `restore` re-adds an omitted profile item as a new bullet (origin `kept`, priority 3), in profile order.
   - `set_field` handles `headline`, `summary`, `template`, `include_earlier_experience`, `emphasis`,
     `page_target`, and `paper`. The run options `template`, `page_target`, and `paper` are also written to
     state by the command.
   - `approve_all` sets every `review: pending` → `approved`.
   - An unknown target → `CvtError(CHECK_FAILED,"E_EDIT_TARGET")`.
4. `cvt diff RUN [--against profile|previous] [--format md|json]` requires stage ≥ `tailored`. Set
   `awaiting_approval` and `cp2: pending`, or in auto mode mark everything `review: auto` and go to `approved`.
5. `cvt apply-edits RUN FILE`:
   - Validate the edits file and copy it to `edits/NNN.json` (next number).
   - Apply the ops to a copy, run the provenance and logistics checks. Any violation → exit 1, leaving
     `tailored.json` unchanged.
   - Otherwise bump the version, write the history snapshot, save, and print `diff --against previous`.
   - Stage handling follows section 6 regression rules.
6. `cvt approve RUN [--all]`:
   - With `--all`, approve all pending items first. Otherwise any pending item → exit 6, listing them.
   - Flip this run's proposed attestations to `active` when their scope is resolved. Unresolved ones stay proposed
     and are listed.
   - Set `state.attestations_used` (all `att-` refs cited in tailored), stage `approved`, `cp2: done`.
7. Tests on the junior goldens (`tailored.json`, `edits-001.json`) and synthetic ops:
   - Every op type.
   - Batch atomicity: one bad op means no change.
   - A violation from a `replace_text` adding "Linkerd" → exit 1.
   - Diff kinds.
   - Numbered markdown.
   - `approve` activating attestations, and the store reflecting it.
   - Regression after an approved run: apply-edits → `awaiting_approval`.
   - Auto mode.
   - "drop the Earlier experience line" via `set_field include_earlier_experience=false`.

## Token-efficiency requirements (interfaces.md section 14)

- `diff` default output is **compact**:
  - The outline as at most 12 lines.
  - Then only changed items (rewritten, merged, attested, dropped, added), each as one line with ID, kind, refs, and
    the after-excerpt (160 characters); the before-excerpt only for rewritten items.
  - Kept items are counted (`kept: 23 bullets`), not listed.
- `--full` gives the previous full rendering. `--format json` follows the same compact or full split.
- `apply-edits` prints the compact `diff --against previous` (changed items only).
- Tests: compact output on the junior golden stays under 40 lines, and `--full` lists every item.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_diff.py tests/unit/test_edits.py   # passes
```

## Definition of done

The common definition of done.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-16.md` under `## ESCALATION`. Do not change it.
