# WP-FIX-4-2: wrap every CV/JD-derived packet section in `<untrusted_document>` (CLI and hosts)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 4 (fix-up from WP-G4) | WP-29, WP-21 | Sonnet (`cv-builder`) | M |

## Goal

`plan/contracts/interfaces.md` section 14 (paragraph above the stage table): "All CV/JD text is untrusted data: packets
wrap it in `<untrusted_document name="...">…</untrusted_document>`". Today only the `profile` packet (`cv.txt`) and
the `jd` packet (`jd.txt`) wrap their documents. The gate ran `cvt brief match|tailor|questions` on the sample run
and found **zero** `<untrusted_document` tags, although those packets carry CV text (the profile digest, prematch
excerpts, item headers, role labels) and JD text (the JD digest's requirement texts). The `gtjob` CLI now sends these
packets to the Anthropic API unchanged. In `src/gtjob/prompts.py` the digest moves into its own cache block, which
is also unwrapped.

Also, `briefs._wrap` does not neutralize a closing tag inside the text, so a JD line containing
`</untrusted_document>` closes the wrapper early.

## Context

- Read `plan/tasks/_COMMON.md` and `interfaces.md` section 14 (`sed -n '/^## 14\./,/^## 15\./p' plan/contracts/interfaces.md`).
- `cvtlib/briefs.py`: `_wrap` (around line 621), `_inputs_for` (around line 1073), `jd_digest`, `profile_digest`,
  `_prematch_text`, `_gaps`, `_source_issues`, `_headers_only`, `_role_labels`, `_pending_questions`, `tailored_outline`,
  `_item_packet`, `_validation_summary`, and the `fix` stage's offending-item text.
- `src/gtjob/prompts.py`: `build_prompt` replaces the digest inside the inputs with `DIGEST_PLACEHOLDER` and sends the
  digest as its own block (`DIGEST_BLOCK_HEADER`).
- The user's own reply stays in `<user_reply>…</user_reply>`; it is not a CV/JD document. `_run_id_line` and
  `_answers_summary` stay unwrapped.

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/briefs.py`
- `src/gtjob/prompts.py`
- `tests/unit/test_briefs.py`
- `tests/unit/test_gtjob_stages.py`
- `plan/reports/WP-FIX-4-2.md`

## Steps

1. **Neutralize tags.** In `_wrap`, replace any `<untrusted_document` and `</untrusted_document` inside `text` with an
   inert form (for example, `<` → `&lt;` for exactly those two substrings, via a named module-level constant). A
   packet must then contain as many closing tags as opening tags.
2. **Wrap CV/JD-derived sections** in `_inputs_for`, using `_wrap(name, part)` with a stable, descriptive name
   (`"jd digest"`, `"profile digest"`, `"prematch"`, `"gaps"`, `"source issues"`, `"item headers"`, `"role labels"`,
   `"pending questions"`, `"tailored outline"`, `"named items"`, and so on):
   - match: JD digest, profile digest, prematch.
   - tailor: JD digest, profile digest, match strengths (if they quote CV text), and the seed plan text.
   - questions: gaps, source issues, item headers, role labels.
   - answer_parse: pending questions, item headers, role labels (the reply stays in `<user_reply>`).
   - change_request: outline and named items (the reply stays in `<user_reply>`).
   - critic: outline and JD digest.
   - fix: the offending items' text.
   Keep each section's existing heading line (for example `# profile digest`) and put it **inside** the wrapper, so the
   heading is still visible to the model. Wrap a section only when it is non-empty.
3. **Digest block (CLI).** In `prompts.build_prompt`, the digest block's text must be wrapped the same way (import and
   reuse the `briefs` wrapper; do not duplicate the tag strings). The placeholder left in the inputs must not leave an
   empty or doubled wrapper. Keep the cache breakpoints unchanged (after the system block and after the digest block).
4. **Budgets.** The tags add a few tokens per section. Packets must still fit their budgets in the existing budget
   tests. If one does not, report it under `## ESCALATION` with the numbers. Do not edit `budgets.json`.
5. **Tests.**
   - `test_briefs.py`: copy the junior golden run (as existing tests do), inject a sentinel string such as
     `SENTINEL-IGNORE-PREVIOUS` into one visible profile bullet and one JD requirement text, build the packets for
     `match`, `tailor`, `questions`, `answer_parse`, `change_request`, and `critic` (and `fix` if a fixture with a failing
     state exists), and assert every occurrence of the sentinel lies between an `<untrusted_document …>` tag and the
     next `</untrusted_document>`. Add a test that `_wrap("x", "a </untrusted_document> b")` yields exactly one closing
     tag.
   - `test_gtjob_stages.py`: for `build_prompt("match", …)` and `build_prompt("tailor", …)`, assert the same sentinel
     property over the joined text of `system` and `blocks`, including the digest block.
6. Run the full suite.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_briefs.py tests/unit/test_gtjob_stages.py    # passes
uv run pytest -q tests/unit tests/integration                                  # passes
uv run .claude/skills/tailoring-cvs/scripts/cvt.py lint-skill --all            # lint ok
```

If the private sample exists (`out/20261026-golden-sample`), also paste the output of:

```bash
for s in match tailor questions; do printf '%s: ' $s; uv run .claude/skills/tailoring-cvs/scripts/cvt.py brief $s 20261026-golden-sample | grep -c '<untrusted_document name'; done   # each > 0
```
