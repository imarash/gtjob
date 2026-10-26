# WP-FIX-3-3: Attestation claims and terms must come from the user's words

## Summary

`answers-apply` now rejects any non-correction attestation whose licensed terms are not grounded in what the user said
or chose, and the dry run shows multi-term attestations.

- Grounding text = `raw_text` + `label` and `value` (`|` → space) of each `choice_ids` entry on the item's question.
- `unsupported_term` violation (message `term 'X' in items[i].attestations[j] is not something the user said or chose`)
  for (a) every entry of `terms` failing `lexicon.supports(term, grounding)`, and (b) every
  `lexicon.find_terms(claim + " " + detail)` term, minus `common-words.txt` words, failing the same check.
- Corrections are not checked. `select_round` is unchanged; its rounds pass by construction (choice label/value are grounding).
- `plan_table`: appends ` terms=a, b, c` to a `+ …` line when `terms` differ from `[claim]` (case-insensitive).
  Plan attestation entries gained an additive `terms` key. Line count is unchanged (≤ 15).

## Files changed

- `.claude/skills/tailoring-cvs/scripts/cvtlib/answers.py`
- `tests/unit/test_answers.py` (new tests appended)
- `plan/reports/WP-FIX-3-3.md`

## Acceptance

```
uv run pytest -q tests/unit/test_answers.py tests/unit/test_questions.py
82 passed in 10.56s            (log: .cache/logs/WP-FIX-3-3/a.log)
```

```
uv run pytest -q tests/unit tests/integration
995 passed, 1 skipped in 58.32s   (log: .cache/logs/WP-FIX-3-3/c.log)
```

The first full run (`b.log`) had one failure, `tests/unit/test_briefs.py::test_match_packet_trims_synthetic_profile_and_keeps_must_haves`
(1899 > 1800 tokens). That file is untracked and belongs to another WP being edited concurrently; it passed standalone and
in the rerun. It has nothing to do with `answers.py`.

New tests: gate rounds (Kubernetes, Kubernetes/ArgoCD in a Helm round, Bash for "add Linux") → `unsupported_term` naming each;
ungrounded term in `detail`; grounded Helm round passes; SLO round with `SLO`/`SLOs`/`service level objective` passes;
choice option text grounds terms; corrections skip the check; dry-run line shows `terms=` for multi-term attestations only.
Existing golden junior round, all `round-*.json` rounds and the `--select` parity test still pass; no fixture was edited.

## Deviations

- Added a `terms` key to plan attestation entries (needed by `plan_table`, which takes only the plan). Additive; no schema covers the plan.

## Open issues

None.
