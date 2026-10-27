# WP-FIX-5-1: the `answer_parse` packet fits its 2,500-token budget on the private sample

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 5 (fix-up from WP-G5) | WP-29, WP-25 | Sonnet (`cv-builder`) | S |

## Goal

`interfaces.md` section 14.4 sets the `answer_parse` input budget to 2,500 tokens and says "The e2e tests assert the same
for the private sample". On the sample, `cvt brief answer_parse` builds about 3,045 tokens and prints
`warning[budget]`. WP-25 marked the assertion as a strict xfail
(`tests/e2e/test_sample_canonical.py::test_answer_parse_packet_fits_budget_on_sample`). Make the packet fit, then
remove the xfail.

Measured on the sample (chars / 3.8): core rules and output ≈ 910 tokens, pending questions ≈ 460, item headers ≈ 1,245,
role labels ≈ 85, reply ≈ 30. The item headers come from `_headers_only` → `profile_digest(..., budget 0)`. They hold:
- 4 full summary paragraphs (`sum-1`..`sum-4`)
- 21 work and engagement header lines, each ending with
  `(+N bullets hidden; cvt brief answer_parse RUN --item <id>)` (about 50 characters of repeated command each)
- education, certificate, and hidden-skills lines

## Context

- Read `plan/tasks/_COMMON.md`.
- `interfaces.md` 14.3 (digest format) and 14.4 (budgets):
  `sed -n '/^### 14\.3/,/^### 14\.5/p' plan/contracts/interfaces.md`. The section 13 table row for `answer_parse` says
  the packet holds "pending questions (compact), reply, item headers + role labels, attestations". Keep all five parts.
- `.claude/skills/tailoring-cvs/scripts/cvtlib/briefs.py`: `_inputs_for` (the `answer_parse` branch), `_headers_only`,
  `profile_digest`, `_pending_questions`.
- Do not change `assets/budgets.json` or the 2,500 value. `tests/unit/test_briefs.py` pins the table to the contract.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/briefs.py` (the `answer_parse` header rendering only)
- `tests/unit/test_briefs.py`
- `tests/e2e/test_sample_canonical.py` (only the lines named in step 3)
- `plan/reports/WP-FIX-5-1.md`

## Steps

1. Compact the item headers for `answer_parse` only. Leave the `questions`, `match`, and `tailor` packets byte-identical.
   Apply these in order, stopping once the sample packet is ≤ 2,400 tokens, which leaves margin:
   a. Keep every work-entry and engagement header line (14.3 requires them) and the `+N bullets hidden` count. Drop the
      per-line `; cvt brief answer_parse RUN --item <id>` command. Add one footer line instead:
      `expand any item: cvt brief answer_parse <RUN> --item <id>`.
   b. Clip summary lines to their id plus the first `ANSWER_PARSE_SUMMARY_CHARS` characters (a new module constant, for
      example 60) with `…`.
   c. If the packet is still over 2,400, clip each pending-question prompt in `_pending_questions` for `answer_parse` to a
      named constant (for example 160 characters). Keep the ids, types, topics, and every choice id and label.
   Never drop the reply, role labels, attestations, core rules, or any choice.
2. Unit tests in `test_briefs.py`:
   - The `answer_parse` packet on the junior/synthetic fixtures still lists every work and engagement id, every role
     label, and every pending choice id, and contains the single expand footer.
   - The `questions` packet is unchanged. Compare it with a snapshot taken before your edit, or assert that it still
     contains the per-line `--item` hint.
3. `tests/e2e/test_sample_canonical.py`:
   - Remove the `@pytest.mark.xfail(...)` decorator above `test_answer_parse_packet_fits_budget_on_sample`.
   - In `test_canonical_exchange_to_report`, remove `enforce_budget=False` from the `answer_parse` `packet(...)` call,
     remove the escalation comment above it, and change the final assertion to cover every packet (drop
     `if name != "answer_parse"`).
   Do not touch the other xfail (`test_second_jd_prompts_do_not_mention_suppressed_terms`, owned by WP-FIX-5-2).
4. Report the sample packet's before and after `est_tokens`.

## Acceptance criteria

Plain `uv run` cannot rewrite `.venv/bin/gtjob` inside the Cursor sandbox. If it fails there, use `uv run --no-sync`.

```bash
uv run pytest -q tests/unit/test_briefs.py                                     # passes
uv run pytest -q tests/e2e/test_sample_canonical.py -rx                        # passes; only the WP-FIX-5-2 xfail remains
uv run pytest -q tests                                                         # passes, 0 skipped on the orchestrator machine
```
