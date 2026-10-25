# WP-07: Stage guides B: checkpoint questions, answer parsing, tailoring, change requests

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 1 | Wave 0 contracts | Sonnet (`cv-builder`) | M |

## Goal

Write the four guides that drive the interactive loop and the tailoring itself. The canonical
exchange must be reproducible from these guides alone.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts:
  - `questions.schema.json`, `answers.schema.json` (especially `$defs/round`), `tailor-plan.schema.json` (the tailor
    stage's output), `tailored.schema.json` (what `assemble` makes of it), `edits.schema.json`.
  - interfaces.md section 14 (packets, compact formats, seed plans, fix loop).
  - interfaces.md sections 6 (lifecycle), 7 (checkpoint protocol, which these guides must match), 8
    (truthfulness), 9 (priorities and fit), and 13.
- **Guide layout (interfaces.md section 13, binding):** `## Contents` (only when over 100 lines), then `## Core`, then
  `## Details` (with `### Purpose`, `### Inputs`, `### Rules`, `### Output`, `### Self-check`), then `## Examples`.
  `## Core` is at most 60 lines and self-contained: the rules that matter most, the output file and format, and the
  check command. `cvt brief` embeds **only** Core into every stage packet, so Core is paid for on every run. Write
  it tight: no preamble, no restating rules that live in another guide's Core, and imperative one-line rules. Details
  and Examples are read only after repeated check failures (`cvt brief <stage> --full`).
- Anonymize the examples, as in WP-05. The canonical user
  reply is not PII and is quoted verbatim.
- Canonical exchange:
  - Assistant: "Your CV doesn't currently show: service mesh; SOC 2 (you have PCI DSS); TypeScript (only React
    and Next.js are listed); explicit SLOs and error budgets; working at a startup as an employee. Which of
    these do you actually have experience with?"
  - User: "add service mesh, istio, typescript. and add slo and error budget to the sre related cv items"

## Owned files

- `.claude/skills/tailoring-cvs/references/checkpoint-questions.md`
- `.claude/skills/tailoring-cvs/references/answer-parsing.md`
- `.claude/skills/tailoring-cvs/references/stage-tailor.md`
- `.claude/skills/tailoring-cvs/references/change-requests.md`
- `tests/unit/test_refs_stages_b.py`
- `plan/reports/WP-07.md`

## Steps

1. `checkpoint-questions.md`:
   - Checkpoint 1 is one batched message with at most 8 questions, every one skippable with a stated
     default, in this order:
     1. The gap multi-select (gaps ordered by JD weight; wording like the canonical assistant message). Each gap
        choice's `value` is its terms joined with `|` (for example `Istio|service mesh`); `--select` turns it into
        a skills-only attestation. Ask a `scope_confirm` follow-up only when bullets could use the term.
     2. Source issues to confirm.
     3. Metric questions (3-5, each specific to one bullet; default "no number").
     4. Strategy (template, emphasis, earlier-experience line; recommended defaults first).
   - Follow-up rules:
     - Ask only follow-ups that change the output, batched, each with a default.
     - Scope confirmations come from the `answers-apply --dry-run` skeletons, extended with adjacent
       optional items.
     - Never re-ask, in the same run, things the user left unmentioned.
   - Host rendering: run `cvt questions <run> --format host --host cursor|claude_code` and pass the JSON to the
     structured question tool (Cursor's ask-questions tool, or Claude Code's `AskUserQuestion`). Apply the
     selections with `cvt answers-apply <run> --select q-N=CHOICE ... --default-rest --dry-run` (no JSON to write). Otherwise
     use `--format chat` and end the turn. Never answer on the user's behalf.
   - Auto mode: no questions are asked.
   - Example: the full checkpoint-1 `questions.json` for the sample JD (5 gaps, 2 source issues, 3 metrics, 1
     strategy = 8 questions after merging the source issues into one).
2. `answer-parsing.md`:
   - Scope: **free-text** replies only (numbered answers, or prose, possibly in a later turn or via `/cv-continue`).
     Tool selections never come here; they use `answers-apply --select`. Turn the reply into one `$defs/round`
     object at `out/<run>/answers.round.json`, using the `answer_parse` packet.
   - Rules:
     - Split the reply into clauses.
     - A bare skill becomes `type: skill`, `placement: skills`, `scope: global`, unless the user names a role
       or project. A practice applied to "items" or "roles" becomes `placement: bullets` with a scope
       selector. Phrases such as "the SRE related items" map to `kind: role_label` with the label as written
       on the CV (case-insensitive).
     - Vague scopes ("the relevant roles", "where it fits") map to `kind: unresolved`. Never guess.
     - New specifics the user volunteers (Istio) are recorded as their own attestation and preferred over the
       generic term where space is tight.
     - Corrections become `type: correction` with `placement: correction_only` and an exact
       old/new value.
     - Rejections ("none of those") become `action: reject` with no attestations.
     - Instructions about the CV itself ("drop the Earlier experience line") become `action: instruct`, to be
       applied later as edits.
     - `terms` lists every surface form the claim licenses (SLO, SLOs, service level objective(s)).
     - `verbatim` is the exact clause.
     - Never add numbers, durations, scale, or certifications the user did not say.
     - Add the one-time defensibility `caveat` when a claim has no role context (Istio).
   - Then run `cvt answers-apply <run> --round out/<run>/answers.round.json --dry-run`, show the mapping, add
     follow-ups via `cvt questions <run> --add followups.json`, and `--commit`.
   - Under `## Examples`, a worked example: the canonical reply → the exact round JSON:
     - 5 attestations.
     - SOC 2 and startup unselected.
     - Then the expected dry-run mapping: SRE → RBC engagement (`exp-2.e4`) and Lululemon engagement
       (`exp-2.e5`) by default; the Sun Life DR engagement (`exp-2.e2`) and Morgan Stanley (`exp-4`)
       monitoring/on-call offered as optional.
     - Then the follow-up batch, each with a default:
       - "Was Istio/service mesh used in a specific role?" (default: skills section only).
       - "TypeScript: skills only, or a project?" (default: skills only).
       - "Any SLO targets or numbers?" (default: none; never invent 99.9%).
   - Also show short examples for each case in `tests/fixtures/answers/case-*.txt` (rejection, correction,
     ambiguous scope, edit instruction, skip).
3. `stage-tailor.md`:
   - Write `tailor-plan.json` from the tailor packet (digest, JD digest, match strengths, answers, attestations,
     and an optional seed plan), following the style-guide and truthfulness Cores that the packet includes (name
     the files in plain text, without links). `cvt assemble` turns the plan into `tailored.json`.
   - Never retype facts: header, employers, titles, dates, education, and certifications come from the profile.
     Unchanged bullets are `op: keep` with an empty `text`. Write text only for `rewrite`, `merge`, and `attested`.
   - Skills may leave `source_refs` empty; assemble resolves them, or fails with `skill_unsupported`.
   - With a **Seed** in the packet: start from it, change only what this JD needs, and set `seed_run`.
   - Selection: lead with JD-relevant engagements, keep the Employer → client engagements structure,
     collapse weak engagements, and add an "Earlier experience" line for roles older than about 12 years.
   - Every written bullet has `from` (and `extra_refs` for attestations).
   - Attested practices are integrated only into in-scope items. Example: an RBC bullet combining SLO and
     error-budget ownership with the existing Dynatrace, Prometheus, and RCA evidence, refs
     `from: [exp-2.e4]`, `extra_refs: [att-004, att-005]`.
   - Attested skills go into the curated skills block.
   - Use `[[CONFIRM: ...]]` where a number would help but none was given.
   - Seniority framing comes from `match.seniority_fit`.
   - `omitted` lists every dropped profile item with a reason.
   - `open_items` and `talking_points` (3-6) are filled in.
   - Self-check: `cvt assemble <run>`. On exit 1, `cvt brief fix <run>` and patch only the listed items, at most 2
     attempts.
4. `change-requests.md`:
   - Work from the `change_request` packet (outline IDs + excerpts; named items in full). Map a checkpoint-2 reply
     or a free-text instruction to a minimal `edits` file at `out/<run>/edits/next.json`,
     then run `cvt apply-edits <run> out/<run>/edits/next.json` (the script assigns the NNN number).
   - Cover the "approve all", approve, reject, and edit item N phrasings, plus "make the summary
     punchier" (a `replace_text` with refs), "drop Mindgeek" (`drop` the entry), "lead with the banking
     work" (`move_before` + `set_field emphasis`), and "drop the Earlier experience line" (`set_field
     include_earlier_experience` = `"false"`).
   - Instructions that would add unsupported claims are refused, with a short explanation and an offer to
     record an attestation instead.
   - After applying, show the compact diff (`cvt diff <run> --against previous`).
5. `test_refs_stages_b.py`:
   - The guide layout holds: each `## Core` is at most 60 lines and names its output file and check command;
     `## Contents` is present when needed.
   - The tailor example's JSON validates against `tailor-plan` when marked `<!-- schema: tailor-plan -->`.
   - The canonical reply appears verbatim in `answer-parsing.md`.
   - Every JSON code block in the four guides parses. A block marked with a following
     `<!-- schema: answers#round -->` comment validates against that (sub)schema, using `jsonschema`
     directly.
   - No candidate PII.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_refs_stages_b.py   # passes
```

## Definition of done

The common definition of done.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-07.md` under `## ESCALATION`. Do not change it.
