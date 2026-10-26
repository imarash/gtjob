# WP-FIX-3-1: Stage packets carry their output shape and every value the model must copy

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 (fix-up from WP-G3) | WP-29, WP-I3 | Sonnet (`cv-builder`) | M |

## Goal

A model that sees only a `cvt brief <stage> RUN` packet cannot produce a passing output today, for two reasons:

1. **No output shape.** `## Output` names the schema (`schema: tailor-plan`) but never shows its JSON structure.
   JSON examples appear only with `--full`, which exceeds the budget (profile ~3,350 / 2,041; tailor ~8,060 / 8,000).
   Wave 4's CLI (WP-21) sends these packets as the whole prompt, so they must be self-sufficient.
2. **Values to copy are missing.** The jd Rules say "`jd_sha256`: copy it from the packet. `source`: copy `kind` and
   `ref` from the packet", but the jd packet contains neither. `jd-check` enforces the hash, so the check fails, and
   the `fix` packet shows only a 12-character prefix.

At the gate, with the junior run, `jd.json` with a wrong `jd_sha256` failed `jd-check`, and neither the jd nor the
fix packet held the full hash.

## Context

- Read `plan/tasks/_COMMON.md` and `plan/tasks/WP-29-briefs-assemble.md` step 6 (packet layout).
- Contract: `sed -n '/^## 14\./,/^## 15\./p' plan/contracts/interfaces.md` (budgets, trimming order).
- Schemas: `.claude/skills/tailoring-cvs/assets/schemas/*.schema.json` (load them through `cvtlib.schemas`; do not
  hard-code paths).
- The jd source and hash live in `state.json` under `inputs.jd` (`kind`, `original_ref`, `sha256`). Use the same
  `ref` that `cvt init` records (look at how the golden `tests/fixtures/golden/junior/jd.json` sets `source.ref`
  versus `state.inputs.jd`, and keep `jd-check` passing for the golden).

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/briefs.py`
- `tests/unit/test_briefs.py`
- `.claude/skills/tailoring-cvs/assets/budgets.json` (raise a stage `input` only if a packet no longer fits; say so in
  the report)
- `plan/reports/WP-FIX-3-1.md`

## Steps

1. Add `schema_skeleton(schema_name: str) -> str` to `briefs.py`. It returns minified JSON built deterministically
   from the schema:
   - Resolve local `$ref`/`$defs`. For the answer_parse stage, use the `round` definition (`answers#/$defs/round`).
   - Objects list their `required` keys in schema order. `const` gives its value; an `enum` gives a string
     `"a|b|c"`; a string gives `""`; integer and number give `0`; boolean gives `false`; arrays hold exactly one
     skeleton element; for `oneOf`/`anyOf`, use the first branch.
   - Name module-level constants for the separators. No magic numbers.
2. In every AI-stage packet (`profile`, `jd`, `match`, `questions`, `answer_parse`, `tailor`, `change_request`,
   `critic`), add a line `shape: <skeleton>` to `## Output`, after `schema:`. Trimming never removes it; treat it
   like Rules. The `fix` packet adds it only when a violation is a schema error.
3. In the `jd` packet's `## Inputs`, before the `<untrusted_document>`, add two lines from `state.inputs.jd`:
   `jd_sha256: <full 64-hex hash>` and `source: kind=<kind> ref=<ref>`. When the failed command is `jd-check`, the
   `fix` packet's Inputs repeat these two lines.
4. Audit each stage's Core rules for "copy … from the packet" or "the … from the packet". Every such value must be
   printed in that packet (`match`: `run_id` = the run slug, already in the title; make it an explicit
   `run_id: <slug>` line in Inputs for `match`, `questions`, `change_request`, and `critic`).
5. Tests in `test_briefs.py`:
   - For every AI stage on the junior golden run, the `shape:` line parses as JSON, and its top-level keys equal the
     schema's `required` list.
   - The jd packet contains the run's full `jd_sha256` and `source: kind=`.
   - After `jd-check` fails on a wrong hash, the fix packet contains the full hash.
   - Every stage still fits its budget (the existing budget test must keep passing).
   - Two builds stay byte-identical.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_briefs.py tests/unit/test_assemble.py     # passes
uv run pytest -q tests/integration/test_wave3.py                           # passes (budgets, no budget warnings)
uv run pytest -q tests/unit tests/integration                              # passes
```

In the report, paste the junior `est_tokens`/`budget` table for every stage after the change, and the `shape:` line
of the `jd` and `tailor` packets.
