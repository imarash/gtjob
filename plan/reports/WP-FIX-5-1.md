# WP-FIX-5-1: answer_parse packet fits its 2,500-token budget on the sample

## Summary
Added a `compact` mode to `profile_digest` (and `_parents`), used only by `_headers_only` for the `answer_parse`
stage. `questions`, `match`, and `tailor` packets are unchanged (`compact` defaults to False).

Sample `cvt brief answer_parse` `est_tokens`: **3067 before, 2441 after** (budget 2500). This is above the brief's
2,400 margin target. Steps 1a-1c alone gave 2646, so I added the two extra cuts listed under Deviations.

Compaction applied:
- Per-line `; cvt brief answer_parse RUN --item <id>` removed from the `+N bullets hidden` hints (and the hidden-skills hint).
  One footer line is added: `expand any item: cvt brief answer_parse <RUN> --item <id>` (`EXPAND_FOOTER`).
- Summary lines clipped to id + `ANSWER_PARSE_SUMMARY_CHARS = 40` chars with `…`.
- Pending-question prompts clipped to `ANSWER_PARSE_PROMPT_CHARS = 80` (ids, types, topics, every choice id and label kept).
- Work and engagement header lines drop the location and `| role: X` (deviation, see below).

Kept whole: core rules, reply, role-labels block, attestations, all work/engagement ids, `+N bullets hidden` counts.

## Files changed
- `.claude/skills/tailoring-cvs/scripts/cvtlib/briefs.py` (constants, `_parents`, `profile_digest`, `_headers_only`, `_pending_questions`, answer_parse input branch)
- `tests/unit/test_briefs.py` (4 new tests)
- `tests/e2e/test_sample_canonical.py` (xfail removed, `enforce_budget=False` and escalation comment removed, final assertion covers all packets)
- `plan/reports/WP-FIX-5-1.md`

## Acceptance
`uv run pytest -q tests/unit/test_briefs.py` (log `.cache/logs/WP-FIX-5-1/a1.log`)
```
101 passed in 1.75s
```
`uv run pytest -q tests/e2e/test_sample_canonical.py -rx` (log `.cache/logs/WP-FIX-5-1/a2.log`)
```
XFAIL ...::test_second_jd_prompts_do_not_mention_suppressed_terms (WP-FIX-5-2)
4 passed, 1 xfailed in 14.50s
```
`uv run pytest -q tests` (log `.cache/logs/WP-FIX-5-1/a3.log`)
```
FAILED tests/unit/test_provenance.py::test_seniority_word_supported_by_a_ref_passes
  TypeError: check_tailored() missing 1 required keyword-only argument: 'draft'
1 failed, 1329 passed, 1 deselected, 1 xfailed in 141.57s
```
The one failure is outside my files. `provenance.py` and `test_provenance.py` are modified in the working tree by another
worker (`check_tailored` gained a required `draft` argument; line 371 of the test does not pass it). Not caused by this WP.
`1 xfailed` is the WP-FIX-5-2 test. `1 deselected` is pre-existing config.

## Deviations
- Steps 1a-1c (footer, summary clip 60, prompt clip 160) measured 2646 tokens, which is still over budget. Compacting
  education/certificate lines saved almost nothing, so I did not keep it. To reach 2441 I also:
  - dropped `| role: X` from engagement header lines in compact mode. The packet's separate role-labels block
    already lists every label with its engagement ids (about -117 tokens);
  - dropped the location from work header lines in compact mode;
  - tightened constants: summary 60 to 40 chars, prompt 160 to 80 chars.
  Section 14.3 shows `role: X` and location in header lines. Section 13 only requires "item headers + role labels", which
  the packet still has, and `--item <id>` expands any item in full. If the orchestrator wants them kept, the remaining
  cuts would have to come from the core rules text (not owned here).
- The 2,400 margin was not reached (2441, 59 tokens under budget).

## Open issues
- The sample's margin is thin (2.4%). A CV with more work entries or pending questions could exceed 2,500 again. The
  packet has no automatic trim for `answer_parse` beyond these fixed clips, and it prints `warning[budget]` if over.
- `test_provenance.py` failure above (another worker's in-progress change).
