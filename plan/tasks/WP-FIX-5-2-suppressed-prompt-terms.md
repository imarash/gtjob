# WP-FIX-5-2: a suppressed gap choice also disappears from the question prompt

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 5 (fix-up from WP-G5) | WP-15, WP-25; run **after** WP-FIX-5-1 (both edit `test_sample_canonical.py`) | Sonnet (`cv-builder`) | S |

## Goal

Hard gate 4 of WP-G5: "The second JD run does not re-ask about service mesh, Istio, or TypeScript." `cvt questions`
(`cvtlib/questions.py::suppress`) already drops the gap *choice* that an active attestation covers. But the question
*prompt* still names it. On the private sample's second JD, pending `q-1` reads:

> Your CV doesn't currently show: LLM serving (vLLM or similar); GPU scheduling on Kubernetes; RAG pipelines; service
> mesh; agent frameworks such as LangGraph (multi-agent work shown). Which of these do you actually have experience with?

Its choices no longer include "Service mesh". The user, who confirmed service mesh last run, is told the CV doesn't show
it. WP-25 recorded this as a strict xfail:
`tests/e2e/test_sample_canonical.py::test_second_jd_prompts_do_not_mention_suppressed_terms`.

## Context

- Read `plan/tasks/_COMMON.md`.
- `interfaces.md` section 7 (questions): `sed -n '/^## 7\./,/^## 8\./p' plan/contracts/interfaces.md`.
- `.claude/skills/tailoring-cvs/scripts/cvtlib/questions.py`: `suppress`, `_choice_covering`, `choice_terms`.
- Do not add fields to `questions.json` (the schema is frozen).

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/questions.py` (`suppress` and new private helpers)
- `tests/unit/test_questions.py`
- `tests/e2e/test_sample_canonical.py` (only the xfail decorator named in step 3)
- `plan/reports/WP-FIX-5-2.md`

## Steps

1. In `suppress`, when a question keeps some choices but loses others, rewrite `q["prompt"]`:
   a. For each dropped choice, remove its label from the prompt (case-insensitive, whole words) together with one adjacent
      list separator (`; `, `, `, ` and `, ` or `). Tidy doubled separators and spaces.
   b. Then, if any dropped choice's label or any of its `choice_terms` still appears in the prompt (case-insensitive,
      word boundary), replace the whole prompt with a named module constant, for example
      `GAP_PROMPT_REWRITE = "Your CV doesn't currently show: {labels}. Which of these do you actually have experience with?"`,
      with the kept choices' labels joined by `"; "`.
   Fully suppressed questions keep their prompt, since they are not shown. Non-gap questions are untouched. The function
   must stay idempotent: running `suppress` twice gives the same output.
2. Unit tests in `test_questions.py`:
   - The prompt above, with "Service mesh" covered by an active attestation → the prompt no longer contains
     "service mesh", and still names the other 4 labels.
   - A prompt that names the dropped term in a form step 1a cannot remove cleanly → the template prompt, listing only
     kept labels.
   - Idempotence, plus no change when nothing is dropped.
3. In `tests/e2e/test_sample_canonical.py`, remove only the `@pytest.mark.xfail(...)` decorator above
   `test_second_jd_prompts_do_not_mention_suppressed_terms`.

## Acceptance criteria

Plain `uv run` cannot rewrite `.venv/bin/gtjob` inside the Cursor sandbox. If it fails there, use `uv run --no-sync`.

```bash
uv run pytest -q tests/unit/test_questions.py                                  # passes
uv run pytest -q tests/e2e/test_sample_canonical.py -rx                        # passes with no xfail left (after WP-FIX-5-1)
uv run pytest -q tests                                                         # passes, 0 skipped on the orchestrator machine
```
