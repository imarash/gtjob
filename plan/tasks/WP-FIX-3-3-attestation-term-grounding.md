# WP-FIX-3-3: Attestation claims and terms must come from the user's words

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 (fix-up from WP-G3) | WP-15 | Sonnet (`cv-builder`) | S-M |

## Goal

`answers-apply` checks that `verbatim` is part of `raw_text` and that numbers were stated by the user, but it never
checks `claim` or `terms`. At the gate, on the junior run, with `raw_text` "I used Helm at Brightfield to package two
internal services", these rounds passed the dry run:

- `claim: "Kubernetes"`, `terms: ["Kubernetes"]`: an invented tool becomes a proposed attestation.
- `claim: "Helm"`, `terms: ["Helm", "Kubernetes", "ArgoCD"]`: the dry-run line shows only `"Helm"`, so the user
  approves Kubernetes and ArgoCD without seeing them. Provenance then accepts a bullet "with Kubernetes" citing that
  attestation, because rule 4 reads `claim + detail + terms`.
- `raw_text` "add Linux to the relevant roles" with `claim/terms` "Bash".

Every licensed term must be grounded in what the user said (or chose), and the dry run must show the terms.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contract: interfaces.md section 7 ("Applying a reply"), lines around `grep -n 'Applying a reply' plan/contracts/interfaces.md`.
- `cvtlib/answers.py`: the per-attestation checks (around `_numbers(stated) - raw_nums`), `select_round`, and
  `plan_table`. Use `lexicon.supports(term, text)` and `lexicon.find_terms(text)`. Both handle case, plurals, and
  `synonyms.json` (verified at the gate: "service level objective" is supported by "add slo …", and "Kubernetes" is
  not supported by the Helm reply).
- Violation codes: reuse the contract's `unsupported_term` code (see `provenance.UNSUPPORTED_TERM`).

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/answers.py`
- `tests/unit/test_answers.py`
- `plan/reports/WP-FIX-3-3.md`

## Steps

1. For every non-correction proposed attestation in a round item, build the grounding text: `raw_text`, plus the
   `label` and `value` (with `|` replaced by a space) of each `choice_ids` entry on the item's question.
2. Violations (`unsupported_term`, message naming the term and `items[i].attestations[j]`):
   - every entry of `terms` must satisfy `lexicon.supports(term, grounding)`;
   - every term that `lexicon.find_terms(claim + " " + detail)` returns, minus `common-words.txt` words, must satisfy
     `lexicon.supports(term, grounding)`.
   - Corrections are not checked (their terms are empty).
3. `select_round` builds terms from the choice value, so its rounds pass by construction. Keep it that way.
4. `plan_table`: when an attestation's `terms` differ from `[claim]` (case-insensitive), append ` terms=a, b, c` to
   its `+ …` line. Keep the total at ≤ 15 lines.
5. Tests:
   - the three gate rounds above → exit 1 with `unsupported_term` naming `Kubernetes`, `ArgoCD`, and `Bash`;
   - the golden junior round, every `tests/fixtures/checkpoint/round-*.json` round, and the `--select` golden-parity
     test still pass;
   - an SLO round (`raw_text` "add slo and error budget to the sre related cv items", terms `SLO`, `SLOs`,
     `service level objective`) passes;
   - the dry-run line shows `terms=` for a multi-term attestation.
   If a committed fixture round fails, report it under `## ESCALATION`; do not edit fixtures.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_answers.py tests/unit/test_questions.py   # passes
uv run pytest -q tests/unit tests/integration                              # passes
```
