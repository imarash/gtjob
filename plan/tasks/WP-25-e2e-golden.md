# WP-25: End-to-end tests on goldens (the skill path, with no API)

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 5 | Waves 1-4 (WP-20 private goldens, WP-04 junior goldens) | Sonnet (`cv-builder`) | L |

## Goal

Prove that the whole skill pipeline works the way a host agent drives it: real `cvt` subprocess calls in a
temporary workspace, with the "AI" stages replaced by copying golden artifacts. Cover the canonical
exchange, every interaction case, attestation reuse on a second JD, resume from any stage, and the
truthfulness guards against tampering.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: interfaces.md sections 3, 6, 7, 8, and 10. Fixtures:
  - `tests/fixtures/expected/interaction-cases.yaml`
  - `tests/fixtures/private/sample/**`, which is git-ignored; skip the test when it is absent
  - The junior goldens in `tests/fixtures/golden/junior/**` (exact paths in `plan/tasks/WP-04-junior-golden.md`)
- Run every test in a temporary workspace: `GTJOB_HOME=<tmp>` with copies of the inputs, so `out/` and `profiles/`
  never touch the repo. Call `cvt` as a subprocess (`sys.executable` + `cvt.py`, or `uv run` when
  `GTJOB_E2E_UV=1`), exactly as the skill instructs.

## Owned files

- `tests/e2e/conftest.py` (fixtures: `workspace`, `cvt(*args) -> CompletedProcess` with a `--json` envelope parsed,
  and `agent_step(run, artifact, src)`, which copies a golden file to where the AI stage would write it)
- `tests/e2e/test_junior_flow.py`
- `tests/e2e/test_sample_canonical.py`
- `tests/e2e/test_interaction_cases.py`
- `tests/e2e/test_resume.py`
- `tests/e2e/test_truthfulness_guards.py`
- `plan/reports/WP-25.md`

## Steps

1. `test_junior_flow.py`: run the full stage sequence on the junior goldens, from `init` through `report`. After
   every command, assert:
   - the exit code
   - `state.stage`
   - that `next_action` names the next expected command

   Then assert:
   - `final/*.pdf` exists, with ≤ 1 page (junior page target 1)
   - every gate in `validation.json` passes
   - `report.md` contains each section header from WP-19
2. `test_sample_canonical.py` (skips if the private goldens are absent):
   - Replay WP-20 through checkpoint 1 with `answers.canonical.round.json`.
   - `--dry-run` output lists:
     - service mesh, Istio, and TypeScript as skills
     - SLOs and error budgets scoped `role_label: SRE`
     - the resolved items `exp-2.e4` and `exp-2.e5`
   - Commit, then assert the store holds `att-001`…`att-005` with those types, placements, and resolved scopes, and
     status `proposed`.
   - Follow-ups: add, then commit the skip round.
   - Tailor, using the saved `tailor-plan.json` → `assemble` exit 0 (and `check-tailored` exit 0 on the result).
   - Approve → the attestations become `active`.
   - Fit → 2 pages. Validate → pass. Assert the expectations under `interaction-cases.yaml` `canonical.final_cv`
     against the PDF text from `pdftotext`.
   - Second JD: `init` + `ingest` + `profile-cache --lookup` hit, then `jd.json` and `questions.naive.json` →
     `cvt questions`. Assert that no pending question mentions any term in `second_run_must_not_ask_about`, and that
     the suppressed ones carry `suppressed_reason` naming the attestation.
3. `test_interaction_cases.py`: for each non-canonical case (rejection, correction, ambiguous scope, followup-skip,
   edit-earlier), apply the golden round or edits to a fresh copy of the run at the right stage. Assert the YAML
   expectations:
   - created attestation fields, or none
   - exit 6 and a pending `confirm_scope` follow-up for the ambiguous case
   - the correction applied in `profile-show --merged`
   - the earlier-experience line absent from the re-rendered PDF
4. `test_resume.py`: for every stage in the stage table, build a run stopped at that stage, run `cvt status --json`,
   execute the command named by `next_action` (supplying the golden AI artifact where the action says "write X"),
   and assert progress. This is the contract that `/cv-continue`, natural-language replies, and `gtjob continue` all
   rely on. Also assert:
   - `status --all` ordering
   - `latest` resolution
   - that editing `profile.json` after `matched` marks `match`, `questions`, and `tailored` stale, and `status`
     says so
5. `test_truthfulness_guards.py`, mutating the approved junior or sample `tailored.json` and asserting exit 1 with
   the exact violation code and message format from section 8:
   - Add "Linkerd" to a bullet. The message must match exactly:
     `bullet <id> mentions 'Linkerd'; not found in refs [...]`.
   - Add an unsupported number ("cut costs 40%").
   - Change a date or employer.
   - Cite a nonexistent ref.
   - Cite a revoked attestation, after `attest revoke`.
   - Add a salary line.
   - Inject `#import "x.typ"` or `]` / `#` markup into a bullet → it renders literally, and the PDF text contains it
     verbatim.
   - Use the injection JD fixture: `jd.json` from the golden has `injection_flags`, and the report shows the notice.

## Token-efficiency requirements (interfaces.md section 14)

- The flows go through the new contract: `profile-map.json` → `profile-build`, and `tailor-plan.json` → `assemble`.
  Use the junior golden and the private sample's saved maps and plans.
- Budget assertions:
  - On the junior and sample runs, every `cvt brief` packet's `est_tokens` is ≤ its budget.
  - On the second-JD (new-JD) flow, the sum of the packet estimates is ≤ 20,000.
  - The second-JD flow confirms the profile-cache hit, and that a seed is offered when its score is ≥ 0.6.
- The truthfulness guards also mutate `tailor-plan.json`, expecting `assemble` exit 1 with these codes:
  - an invented employer in a rewrite
  - a `keep` with text
  - an `attested` bullet out of scope
  - an unsupported skill

## Acceptance criteria

```bash
uv run pytest -q tests/e2e                     # passes; sample tests skip only if private goldens are absent
uv run pytest -q tests/e2e -rs | grep -c SKIP  # 0 on the orchestrator's machine (private goldens present)
```

## Definition of done

The common definition of done. The report lists every e2e test and whether it passed or was skipped.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-25.md` under `## ESCALATION`. Do not change it.
