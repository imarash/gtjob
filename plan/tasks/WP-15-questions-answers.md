# WP-15: Checkpoint 1 commands (`questions`, `answers-apply`)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 | WP-10 (profile), WP-11 (attestations, scope) | Sonnet (`cv-builder`) | L |

## Goal

Implement the deterministic half of the interactive loop:

- Validate and render checkpoint questions for any host.
- Suppress questions that durable attestations already answer.
- Turn a parsed reply round into a scope mapping preview, follow-up skeletons, recorded answers, and
  proposed attestations.

This is the code that makes the canonical exchange and the "don't ask again" behavior work.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: interfaces.md section 7, which is normative and defines the host formats, suppression,
  dry-run/commit, follow-ups, and confirm_scope. Also section 3 (`questions` and `answers-apply` rows), section 5
  (WP-15 `questions.py` / `answers.py` block, implemented here), section 6 (stages), `questions.schema.json`,
  `answers.schema.json`, and `attestations.schema.json`.
- APIs you call: `cvtlib.attestations` (`load_store`, `save_store`, `add`, `usable`, `find_by_terms`), `cvtlib.scope`
  (`resolve`, `describe_mapping`, `candidates`), and `cvtlib.profile.merged_view` / `iter_items`.
- Cursor's structured question tool takes
  `{"title": str, "questions": [{"id", "prompt", "options": [{"id","label"}], "allow_multiple": bool}]}` and always
  allows free text. Claude Code's `AskUserQuestion` takes questions with `question`, `header` (≤ 12 chars),
  `multiSelect`, and `options: [{label, description}]`. The plan uses a conservative limit of ≤ 4 questions per call and
  ≤ 4 options per question, splitting longer lists into parts. Free text arrives via "Other".

## Owned files

- `.claude/skills/tailoring-cvs/scripts/cvtlib/questions.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/answers.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/commands/checkpoint.py` (`questions`, `answers-apply`)
- `tests/unit/test_questions.py`, `tests/unit/test_answers.py`
- `tests/fixtures/checkpoint/` (synthetic rounds and questions built on `tests/fixtures/profile/nested-engagements.json`
  from WP-11)
- `plan/reports/WP-15.md`

## Steps

1. `questions.check`: schema, plus these rules:
   - ≤ `MAX_CP1_QUESTIONS` pending checkpoint-1 questions.
   - Every question has `allow_free_text: true` and a default with a description.
   - Unique IDs.
   - `links` IDs exist (requirements in `jd.json`, items in the profile, issues, attestations).
   - Choices are non-empty for select types.

   Then suppression: for `gap` questions, drop choices whose linked requirement keywords are covered by
   `find_by_terms`. A question left with no choices becomes `status: suppressed` with a reason. Return the
   suppressed list.
2. `questions.add` assigns `q-N` after the max existing N and sets `round` to max+1 unless given.
   `render_chat` and `render_host` follow section 7 exactly, including the Claude Code splitting rule and headers.
3. `cvt questions RUN [--format chat|host|json] [--host cursor|claude_code] [--add FILE]`:
   - Validate and suppress, then write back with `record_artifact(cascade=False)`.
   - With pending questions: set `awaiting_answers` and `cp1: pending`, print the render, and exit 6.
   - With none: `cp1: skipped`, stage `answers_applied`, exit 0.
   - With the auto option: default everything, write an auto round through `answers.auto_round`, stage
     `answers_applied`, exit 0.
4. `answers.plan_round(run_dir, round)`:
   - Validate against `subschema("answers","round")`.
   - Every `question_id` must be pending or empty.
   - For each proposed attestation, resolve its scope (`scope.resolve`) and produce
     `{claim, type, placement, scope_kind, items:[{item_id,label}], needs_confirmation: bool, unresolved: bool}`.
   - Scope-confirm skeletons: one `scope_confirm` question per role_label/items attestation group. Choices are the
     resolved items, all in the default. `links.attestation_ids` is `"pending"`, filled at commit.
   - Unresolved skeletons: choices from `scope.candidates`, with the default `skills_only`.
   - Question status changes: answered, skipped, or defaulted for `unmentioned_question_ids`.
   - Output this as `data.plan`, plus a human table.
5. `answers.commit_round`:
   - Append the round to `answers.json` (create it if missing) and update question statuses.
   - Create attestations via `attestations.add` (status proposed) with resolved scopes.
   - Fill in `links.attestation_ids` of pending `scope_confirm` questions whose `parent_id` equals the answered
     question. The AI adds those through `--add` before commit.
   - Apply `confirm_scope` items: replace the linked attestations' `scope.item_ids` with the chosen IDs and set the
     kind to `items` when the selection changed.
   - Apply `reject` (no attestation) and `correct` (a correction attestation).
   - `instruct` items are stored for the tailoring stage. List them in `data.instructions`.
   - Exit 6 if pending questions remain or any attestation is unresolved, else 0, with stage `answers_applied`,
     `cp1: done`.
   - Record `answers` (cascade) and `questions` (no cascade).
6. Tests on the synthetic nested profile:
   - **The canonical round**, a hand-written round JSON equivalent to the plan's expected parse: 5 proposed
     attestations; SRE resolves to the two SRE engagements; 2 scope skeletons; skills-only placements for
     Service mesh, Istio, and TypeScript.
   - Rejection round: no attestations.
   - Correction round: a correction attestation.
   - Ambiguous ("Kafka to the relevant roles", unresolved): exit 6 and a skeleton with candidates.
   - The confirm_scope update.
   - Skip / unmentioned → defaulted.
   - Suppression: a second run's gap question about service mesh is suppressed once an active "Service mesh"
     attestation exists.
   - Host rendering for both hosts, including splitting of a 6-choice question.
   - Exit codes and stage transitions.

## Token-efficiency requirements (interfaces.md section 14)

- **`answers-apply --select`** (new; implemented as `answers.select_round`, section 5). Repeatable `q-N=CHOICE[,CHOICE]` or `q-N=skip`, plus `--default-rest`
  (defaults every other pending question). It builds a `channel: host_tool` round deterministically:
  - For non-gap questions, items get `action: choose`.
  - For a selected choice on a `topic: gap` question, the item gets `action: attest` with this proposed
    attestation:
    - `type: skill`, `claim` = the choice label, and `terms` = the choice `value` split on `|`
    - `scope.kind: global`, `placement: skills`, and `detail`/`verbatim` = the label
    - `caveat` from the defensibility rule (no role evidence → skills only)
  - Narrower scopes (`role_label`, `items`) come only from free text (the answer_parse packet) or a
    `scope_confirm` follow-up.
  Then the same dry-run and commit path runs. Unknown question or choice IDs → exit 2.
- `questions --format chat` is compact: one line per question, with numbered choices on one line and the default in
  brackets. `--format host` emits minified JSON.
- The `--dry-run` mapping prints at most 15 lines: one line per created attestation, with claim, scope, and resolved
  items.
- Tests:
  - `--select` on the junior questions produces the same commit result as the golden round, for the choice parts.
  - `--default-rest` sets the rest to defaulted.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_questions.py tests/unit/test_answers.py   # passes
```

## Definition of done

The common definition of done.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-15.md` under `## ESCALATION`. Do not change it.
