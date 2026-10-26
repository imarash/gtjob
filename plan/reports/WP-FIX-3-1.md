# WP-FIX-3-1: Stage packets carry their output shape and every value the model must copy

Status: DONE. No contract change; no escalation.

## Summary

- `briefs.schema_skeleton(name)` builds minified JSON from a schema (`answers#/$defs/round` supported). It resolves local
  `$ref`s, lists `required` keys in schema order, and uses `const` values, `"a|b|c"` for enums, `""`/`0`/`false`
  for scalars, one element per array, and the first `oneOf`/`anyOf` branch. Separators and the depth cap are
  module-level constants.
- Every AI-stage packet's `## Output` has `shape: <skeleton>` directly after `schema:`. It sits outside the trimmed
  inputs, so trimming never removes it. The `fix` packet adds it only when a violation is a schema-path error (item id
  starting with `$`). A wrong `jd_sha256` is not a schema error, so that fix packet has no shape.
- The `jd` packet's Inputs start with `jd_sha256: <64-hex>` and `source: kind=<kind> ref=<original_ref>` (from
  `state.inputs.jd`), before `<untrusted_document>`. The `fix` packet for `jd-check` repeats both lines.
- Audit of Core rules ("copy ... from the packet"): `jd` (hash, source) and `match` (`run_id`) were the only values
  not printed. `run_id: <slug>` is now an explicit Inputs line for `match`, `questions`, `change_request`, `critic`.
  The tailor `seed_run` slug was already in the `# Seed (run X)` header.
- `budgets.json` is unchanged; every stage still fits.

## Files changed

- `.claude/skills/tailoring-cvs/scripts/cvtlib/briefs.py`
- `tests/unit/test_briefs.py`
- `plan/reports/WP-FIX-3-1.md`

## Junior est_tokens / budget (after change)

| stage | est / budget |
| --- | --- |
| profile | 1827 / 2041 |
| jd | 1677 / 3000 |
| match | 2214 / 7000 |
| questions | 1369 / 4000 |
| answer_parse | 1457 / 2500 |
| tailor | 2793 / 8000 |
| change_request | 1749 / 3000 |
| critic | 1086 / 4000 |

`shape:` of the `jd` packet:

```
{"schema_version":"1","jd_sha256":"","source":{"kind":"file|text|url","ref":"","format":"posting|recruiter_email|scraped_page|other"},"title":"","company":"","location":"","seniority":"intern|junior|mid|senior|staff|principal|lead|manager|director|unknown","years_experience_text":"","ic_or_manager":"ic|manager|either|unknown","domain":[""],"role_summary":"","requirements":[{"id":"","kind":"must|nice|responsibility","text":"","category":"cloud|containers|iac|language|cicd|reliability|observability|security|compliance|domain|ai_tools|leadership|startup|data|frontend|presales|other","keywords":[""],"weight":"1|2|3|4|5"}],"keywords":[{"term":"","synonyms":[""],"weight":"1|2|3|4|5","req_ids":[""]}],"implicit_signals":[{"signal":"scale|availability_target|leadership|on_call|ic_depth|ownership|startup_pace|regulated|customer_facing|presales|other","evidence_text":""}],"noise":[{"kind":"email_header|greeting|signoff|recruiter_contact|compensation|visa|work_arrangement|location_logistics|recruiter_question|marketing|other","text":""}],"recruiter_asks":[""],"injection_flags":[""]}
```

`shape:` of the `tailor` packet:

```
{"schema_version":"1","seed_run":"","emphasis":"","headline":{"text":"","source_refs":[""]},"summary":{"text":"","source_refs":[""]},"skills":[{"label":"","priority":"1|2|3|4|5","items":[{"name":"","source_refs":[""]}]}],"experience":[{"profile_id":"","priority":"1|2|3|4|5","intro":{"mode":"none|keep|rewrite","text":"","source_refs":[""]},"bullets":[{"op":"keep|rewrite|merge|attested","from":[""],"text":"","extra_refs":[""],"priority":"1|2|3|4|5"}],"engagements":[{"profile_id":"","priority":"1|2|3|4|5","bullets":[{"op":"keep|rewrite|merge|attested","from":[""],"text":"","extra_refs":[""],"priority":"1|2|3|4|5"}]}]}],"earlier_experience":{"include":false,"profile_ids":[""]},"certifications":[{"profile_id":"","short_name":"","priority":"1|2|3|4|5"}],"education":[{"profile_id":"","include_details":false}],"talking_points":[{"text":"","source_refs":[""]}],"omitted":[{"profile_id":"","reason":""}],"open_items":[{"kind":"confirm_placeholder|gap|source_issue|unconfirmed_suggestion","text":"","item_ids":[""]}]}
```

## Acceptance commands

1. `uv run pytest -q tests/unit/test_briefs.py tests/unit/test_assemble.py`
   - Result: `109 passed in 1.74s` (log: `.cache/logs/WP-FIX-3-1/a1.log`, rerun after the final edit passed).
2. `uv run pytest -q tests/integration/test_wave3.py`
   - Result: `8 passed in 15.47s` (log: `.cache/logs/WP-FIX-3-1/wave3.log`).
3. `uv run pytest -q tests/unit tests/integration`
   - Result: `995 passed, 1 skipped in 58.88s` (log: `.cache/logs/WP-FIX-3-1/all.log`).

## New tests (`tests/unit/test_briefs.py`)

- The `shape:` line of every AI stage parses as JSON, its top-level keys equal the schema's `required` list, and it
  follows `schema:`.
- `schema_skeleton` rules (const, enum, array, `answers#/$defs/round`, deterministic, minified).
- The shape survives an extreme trim (tailor `input` = 1).
- The `jd` packet has the full `jd_sha256` and `source: kind=` before the document.
- `run_id:` lines for `match`, `questions`, `change_request`, `critic`.
- After `jd-check` fails on a wrong hash, the fix packet has the full hash and source and no `shape:`.
- A schema-error `jd-check` failure gives a fix packet with the `shape:`.
- The existing budget, determinism and layout tests all pass unchanged.

## Deviations

- `test_match_packet_trims_synthetic_profile_and_keeps_must_haves` used an artificial 1,800-token match budget. The
  fixed text (rules plus the new `shape:`) no longer fits that, so I introduced `MATCH_TRIM_BUDGET = 2300` in the
  test. The real budget in `budgets.json` is unchanged.
- The skeleton prints numeric enums (weight, priority) as `"1|2|3|4|5"` strings, as the brief specifies. The model
  must write them as integers, because the schema requires that. The Core guides already say so.

## Open issues

None.
