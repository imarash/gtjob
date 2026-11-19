---
kind: plan
repo: gtjob
date: 2026-11-03
option: single-loop
reads:
  - docs/architecture/current-state.md
  - docs/architecture/options.md
---

# Plan: One agent, cvt as the harness

## Target

One capped **Single agent** (ReAct) in this repo tailors one CV to one job description. The model proposes the next tool. `cvt` executes that tool only when `state.json` allows the transition, then returns a schema or provenance result. The runner loads the **Skill** `tailoring-cvs`; the model does not pick a skill. Writes stay inside the run folder and `profiles/<person>/`. The loop pauses at the **Human gate** stages `awaiting_answers` and `awaiting_approval`, persists `state.json`, and resumes from that file. CLI, Studio, and the slash starters all start this loop. Orchestration is the model among legal tools, and code for the refusal. Polish stays a separate request on the same tools: code extracts text, one writing call fills `render.json`, code renders the three layouts. Budget band M: one product surface, one capped tool loop per tailor.

## Delta

| Today (path) | Target |
| --- | --- |
| `src/gtjob/flow.py` `drive` walks `HANDLERS` and re-prompts each writing stage. `MAX_STEPS` 200 only stops a handler that never advances | The same file hosts the tool loop. The model proposes one tool. Code executes it only when the stage allows it, then repeats until a gate, `reported`, or the cap |
| `src/gtjob/stages.py` `run_stage_checked`, `DEFAULT_MAX_ATTEMPTS` 2 | Still validates one structured output before it is stored. A second failed check of that tool escalates. The loop is the only decider of the next tool |
| `src/gtjob/llm.py` `AnthropicClient` on the CLI; `web/scripts/infer-worker.mjs` hardcodes `composer-2.5` | `LLMClient` in `src/gtjob/llm.py` is the only writing seam. A run uses one adapter. `FakeClient` stays the test double |
| `web/scripts/infer-worker.mjs` `Agent.create` / `Agent.resume` with `local.cwd` set to the repo | Studio starts the Python loop. That worker does not create a Cursor agent and does not give a model a repo shell |
| `web/src/lib/infer-prompt.mjs` tells a host model to follow the skill and do only `next_action` | The runner loads `tailoring-cvs` and passes `cvt brief` packets. This prompt file is not the writing procedure |
| `web/src/lib/cvt-args.mjs` builds an allowlisted argv for Studio buttons | Same allowlist. Every command it can emit is also in the legal-tool table |
| `.claude/skills/tailoring-cvs/scripts/cvtlib/state.py` `_NEXT_ACTIONS` is prose for a host chat that writes stage JSON | A structured legal-tool table beside that prose. `status` can still show `next_action`. The harness refuses any other tool |
| `.claude/skills/tailor-cv/SKILL.md`, `.claude/skills/cv-continue/SKILL.md`, `.claude/skills/cv-reply/SKILL.md` tell the host chat to write stage JSON | Those starters invoke the runner and surface exit code 6 (`ExitCode.AWAITING_USER`) |
| `.claude/skills/cv-polish/SKILL.md` plus the Studio polish prompt: a host agent writes `render.json` and runs `polish_render` | Code extracts (`polish_render.py` `extract`). One writing call through the seam fills `render.json`. Code renders `modern`, `classic`, and `sidebar` |
| `cvtlib/briefs.py` wraps CV and JD text as `<untrusted_document>` and records `injection_flags` | Unchanged, and it is the only document context the loop sends |
| `out/<slug>/state.json`, `profiles/<person>/` | Same durable state. Gates resume from `state.json`. Answer and approve commits stay idempotent |

## Work packages

Ordered. Each package is one agent session.

### 1. Legal tool table

- Depends on: none
- Touches: `.claude/skills/tailoring-cvs/scripts/cvtlib/state.py` (`STAGES`, `_NEXT_ACTIONS`); `web/src/lib/cvt-args.mjs`; schema for `state.json` history only if a tool result needs a field the current history entry lacks (`state.add_history` already records the command)
- Done when: for each stage in `STAGES`, the table lists the commands that may run. A proposal outside that list is refused and `state.json` is unchanged. `buildToolArgv` cannot emit a command the table omits. Writes named by the table stay under `out/<slug>/` or `profiles/<person>/`.
- Risk: a stage whose only legal command was left out of the table cannot advance.
- Pattern: no agent change
- Production rules: deterministic work stays in code. The model does not gain a host shell. Path-bounded writes. Mutating commits (`answers-apply`, `approve`) stay idempotent. Validate a tool result before the next step reads it.

### 2. One model seam

- Depends on: none
- Touches: `src/gtjob/llm.py` (`LLMClient`, `AnthropicClient`, `FakeClient`); `src/gtjob/config.py` (`DEFAULT_MODELS`); `src/gtjob/prompts.py` (the preamble and `cvt brief` packets stay the call context)
- Done when: `flow` and `stages` call `LLMClient.complete_json` and do not import a vendor SDK. `GTJOB_FAKE_LLM` still replays canned JSON. A second adapter can be constructed as an `LLMClient` without a second prompt preamble. The package does not delete `AnthropicClient` and does not hardcode `composer-2.5`.
- Risk: a provider whose structured-output shape differs can break `complete_json` unless the adapter normalizes to one object.
- Pattern: no agent change
- Production rules: one model seam. Structured output. Timeouts, retries, and errors that surface (the existing 429/5xx backoff in `AnthropicClient` stays on that adapter). Version the prompt text with the skill packets.

### 3. Tool loop in `flow.drive`

- Depends on: 1, 2
- Touches: `src/gtjob/flow.py` (`drive`, `HANDLERS`, `MAX_STEPS`); `src/gtjob/stages.py` (`run_stage_checked`); `.claude/skills/tailoring-cvs/SKILL.md` (loaded by the runner); `.claude/skills/tailoring-cvs/scripts/cvtlib/briefs.py`; `.claude/skills/tailoring-cvs/scripts/cvtlib/state.py` (`save` already writes `state.json` before a return)
- Done when: with `GTJOB_FAKE_LLM`, `drive` reaches `awaiting_answers`, `awaiting_approval`, or `reported`. Each model turn proposes one tool from the table in package 1. An illegal proposal does not run. A check failure returns the violation to the next turn. The second consecutive failure of the same tool stops (`DEFAULT_MAX_ATTEMPTS` is 2) and leaves `state.json` resumable. Hitting the iteration cap stops the same way. `state.json` history plus the usage artifact record the tool name and the result. CV and JD text enter the call only through a `cvt brief` packet.
- Risk: a model that keeps proposing legal tools which do not change the stage burns the cap. The fallback is the stop above. Package 3 does not add a second decider.
- Pattern: Single agent (ReAct), Skill, Human gate
- Production rules: the model decides only the next legal tool. Validate before the next step consumes a file. Cap the loop and stop at the gate or at the cap. Consecutive tool failures escalate. Persist `state.json` at the human gate. Scan CV and JD text before it enters context. Trace each tool call and result. The loader, not the model, selects `tailoring-cvs`. Compact a failed check to the violation list, not the transcript.

The iteration cap is a named constant in `flow.py`. It is not `MAX_STEPS` 200. The integer and the exit code for a cap hit are open in Human decisions. Package 3 does not land until those two are chosen.

### 4. CLI tailor, polish, and reply

- Depends on: 3
- Touches: `src/gtjob/cli.py` (`tailor`, `continue`, `edit`, `polish`); `.claude/skills/tailoring-cvs/scripts/polish_render.py`; `.claude/skills/cv-reply/SKILL.md` and its reply guide under `.claude/skills/cv-reply/` (the runner reads the guide only after `reported`, and only when a reply was requested)
- Done when: `gtjob tailor` and `gtjob continue` call `drive` and exit 6 at a gate with the pending items printed. `gtjob polish` extracts text, makes one `complete_json` call that fills `render.json`, and renders the three layouts. It does not call `cvt init`. A requested reply is one `complete_json` call after `reported` that writes `out/<slug>/reply.md` and does not re-enter the tool loop. `status`, `render`, and `profile` still do not call the model.
- Risk: a polish or reply call that writes outside the run folder.
- Pattern: Single agent (ReAct) for tailor; Sequential for polish (extract, one writing call, render) and for the reply call after `reported`
- Production rules: same as package 3 for the tailor path. Polish and reply are one structured call each, validated before render or before the file is treated as done. Path-bounded writes. No host shell.

### 5. Studio uses the same runner

- Depends on: 4
- Touches: `web/scripts/infer-worker.mjs`; `web/src/lib/infer-prompt.mjs`; `web/src/lib/infer-stop.mjs`; `web/src/app/api/infer/route.ts`; `web/src/lib/infer-status.mjs`; `web/src/components/studio/infer-panel.tsx`; `web/src/components/studio/toolbox-form.tsx`; `web/src/lib/polish-run.mjs`; `web/src/app/api/cvt/route.ts` (init and the deterministic advance stay)
- Done when: a toolbox tailor posts to `/api/infer` and the process that writes stage JSON is `gtjob` / `drive`, which a test can show by the absence of `Agent.create` and `Agent.resume` on that path. The page still polls `/api/infer` and still shows the two gates. Choice answers still commit with `answers-apply` in the browser, then the loop resumes. Approval is still `cvt approve` in the browser, then the loop resumes. A written note still resumes from `.studio/infer/<slug>.reply.txt` as user text, scanned as data. Polish mode calls the package 4 polish command and finishes only when `modern`, `classic`, and `sidebar` PDFs exist. “Write a reply” calls the package 4 reply call.
- Risk: a detached Node child that still holds a Cursor session id in `.studio/infer/<slug>.json` can look “running” after the Python loop has stopped.
- Pattern: Single agent (ReAct), Human gate
- Production rules: same loop and cap as package 3. Persist `state.json` at the gate so the browser can resume without replaying earlier tools. Idempotent answer and approve commits. No repo-cwd shell. Studio remains request-response on loopback. No daemon.

### 6. Slash starters

- Depends on: 4
- Touches: `.claude/skills/tailor-cv/SKILL.md`; `.claude/skills/cv-continue/SKILL.md`; `.claude/skills/cv-reply/SKILL.md`; `.claude/skills/cv-polish/SKILL.md`
- Done when: each of those files tells the host to run the matching `gtjob` command and to stop when the exit code is 6, printing the pending gate. A run started this way records host `cli` in `state.json` history. The host chat is not instructed to write `profile-map.json`, `jd.json`, `match.json`, `questions.json`, or `tailor-plan.json`. `cv-polish` runs the polish command from package 4.
- Risk: a host that still follows an old copy of the skill will write stage JSON beside the runner.
- Pattern: Skill, Human gate
- Production rules: the loader selects the skill (package 3). These files are starters. Skill text stays versioned in the repo. CV and JD text stay data.

Leave these as they are. They do not write model JSON: `.claude/skills/cv-status/SKILL.md`, `.claude/skills/cv-profile/SKILL.md`, `.claude/skills/cv-render/SKILL.md`. `/runs` buttons in `web/src/components/studio/skill-actions.tsx` stay direct `cvt` calls.

### 7. Trajectory check

- Depends on: 3, 5, 6
- Touches: `evals/` (new fixture file under this existing directory); `src/gtjob/flow.py` usage table; `out/<slug>/state.json` history
- Done when: one offline fixture (`GTJOB_FAKE_LLM`) records the tools proposed, a refused illegal tool, a second check failure that escalates, a gate resume that does not replay earlier stages, and token totals from the usage artifact. The fixture fails if `infer-worker.mjs` calls `Agent.create` or if a slash starter instructs the host to write stage JSON.
- Risk: a fixture that only compares the final PDF string will pass a loop that skipped the checks.
- Pattern: no agent change
- Production rules: grade the trajectory (tools used, recovery, spend), not an exact string match. Spend here is the usage artifact’s token counts. This package adds no billing store.

## Sequence

Wave A, packages 1 and 2 together. After this wave, `gtjob tailor`, Studio infer, and the slash skills behave as they do today. The legal-tool table and the seam are present and unused by Studio.

Wave B, package 3, then package 4. After this wave, `gtjob tailor`, `continue`, `edit`, `polish`, and a requested reply use the loop or the one-call paths. Studio and the slash skills still have their old writers. That split is temporary. Provenance, placeholder rejection, the two-page tailor PDF, and exit 6 still hold on the CLI. `/applications` and the run-folder buttons still call `cvt` and the career-ops scripts they call today.

Wave C, packages 5 and 6 together. After this wave, CLI, Studio, and the slash starters share the runner. A toolbox run does not start a Cursor agent. A slash run does not write stage JSON in the host chat. Today, the inbox, and the applications board still do not score or submit.

Wave D, package 7. The fixture is the check that waves B and C stayed one loop.

## Out of scope

From this option’s deferred list: a PDF critic on the default path, a trained QA model, a cloud sandbox, fine-tuning, inbox scoring, application submit.

Other options: `easy-stages` (code walks the stages and the model does not choose tools) and `checked-pdf` (a capped revise loop on the rendered PDF). The existing `gtjob tailor --critic` one-pass flag and `.claude/agents/cv-critic.md` stay off this plan. Magentic, a task ledger, a database, a daemon, tenancy, and billing stay out.

Also untouched: `web/src/app/api/applications/[id]/liveness/route.ts`, `web/src/app/api/applications/[id]/status/route.ts`, `.studio/inbox.json` scoring, and the architect skills.

## Human decisions

The packages must not pick these.

- Default adapter behind `LLMClient` for a real run. `AnthropicClient` exists. `composer-2.5` exists only as the Studio worker’s model id. A run uses one adapter, chosen in config (`gtjob.toml`, `GTJOB_MODEL_<STAGE>`, or the existing `--model`). The plan does not make `composer-2.5` the default and does not remove Anthropic.
- Tool-loop iteration cap. A person sets the integer before package 3. The constant lives in `src/gtjob/flow.py` and is separate from `MAX_STEPS` 200.
- Exit when that cap is hit. Stay on `ExitCode.INTERNAL` (7) with a stable error id, or add an exit code. Package 3 does not add an `ExitCode` member unless that choice is to add one.
- Whether `gtjob tailor --critic` remains available as today’s one-pass flag. Packages 3–6 do not call it and do not delete it.

Settled by the option, so the packages treat them as given: no new data store (`out/<slug>/state.json` and `profiles/<person>/` stay); slash `tailor-cv`, `cv-continue`, and `cv-reply` stop being the writer of stage JSON; Studio stops creating a Cursor agent with `local.cwd` set to the repo.

## Verification

Without rereading the repo:

- `gtjob tailor` with `GTJOB_FAKE_LLM` exits 6 at `awaiting_answers` with `state.json` saved, resumes after committed answers, exits 6 at `awaiting_approval`, and after `cvt approve` reaches `reported` with a PDF of at most two pages. A claim that cites neither the CV nor an attestation fails validation.
- The package 7 fixture shows the tool sequence, one refused illegal tool, escalation on the second consecutive check failure, a resume that does not replay earlier tools, and token totals from the usage artifact.
- `web/scripts/infer-worker.mjs` has no `Agent.create` and no `local.cwd` assignment. `/api/infer` on a tailor reaches the same gates as the CLI.
- `.claude/skills/tailor-cv/SKILL.md`, `cv-continue`, `cv-reply`, and `cv-polish` name a `gtjob` command and exit code 6, and do not tell the host to write stage JSON.
- A polish run produces `modern`, `classic`, and `sidebar` from one writing call. A requested reply produces `reply.md` only after `report.md`.
- No route in `web/src/app/api/` submits an application. A report score under 4.0/5 stays labeled Do not apply.
