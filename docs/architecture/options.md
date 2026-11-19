---
kind: options
repo: gtjob
date: 2026-11-02
reads:
  - docs/architecture/current-state.md
  - pasted
recommended: single-loop
---

# Future-state options

## Goal

Rearchitect gtjob as a vertical harness for one task: tailor one CV to one job description and finish an ATS-oriented PDF plus a match report. In the sense of the pasted Gamma discussion, the agent is one high-level model loop, and the harness is the tools that loop uses to act, to check its work, and to ask the user. Each model job stays small enough that an off-the-shelf model can do it. The user sees one finished output. Judgment about what “good” looks like stays with the person. A custom model is out of scope until real usage shows a check the off-the-shelf models do poorly.

## Constraints

- Facts in the PDF and the report must trace to the CV or to an attestation. Placeholders fail validation. CV and job text stay untrusted data (`injection_flags`).
- A person still answers questions and approves the diff. State persists at those gates so the run resumes. Nothing in this repo submits an application. A report under 4.0/5 stays labeled Do not apply.
- A tailored PDF is at most two pages. The polish path keeps every fact and aims at about two or three pages. One run is one folder under `out/`.
- Deterministic work stays in `cvtlib`: schema, provenance, ingest, Typst, allowlisted argv. The model does not gain a host shell.
- Local and request-response. No database, no daemon, no tenancy or billing. Profile memory stays `profiles/<person>/`.
- One model seam, so the writing model can be swapped. CLI (`AnthropicClient`) and Studio (`composer-2.5` in `web/scripts/infer-worker.mjs`) do not remain two writers.
- The niche stays this CV task. Inbox scoring, career-ops liveness, and other verticals stay out.

## Recommendation

single-loop: the selection order stops at one agent. The domain is one CV task, the tools already exist, and the path of a failed check is not a fixed script. A skill already holds the procedure; another agent does not fix the three loop owners or the repo shell. The user chooses. This is not a plan.

## Option single-loop: One agent, cvt as the harness

- Patterns: Single agent (ReAct), Skill, Human gate
- Shape: One capped loop in this repo. The model proposes the next tool; `cvt` executes it only when `state.json` allows that transition, then returns a schema or provenance result. `tailoring-cvs` is loaded by the runner. Writes stay inside the run folder and `profiles/<person>/`. The loop pauses at `awaiting_answers` and `awaiting_approval` and resumes from `state.json`. CLI, Studio, and the slash skills start that same loop. Polish stays a separate request on the same tools: code extracts text, one writing call fills `render.json`, code renders the three layouts. Orchestration is the model among legal tools, and code for the refusal.
- What changes from today:
  - `src/gtjob/flow.py` hosts the tool loop. `drive` stops being a second decider that re-prompts each writing stage on its own.
  - `web/scripts/infer-worker.mjs` stops creating a Cursor agent with `local.cwd` set to the repo. The tree shows no path sandbox on that agent.
  - `web/src/lib/infer-prompt.mjs` stops telling a host model to follow the skill and do only `next_action`.
  - `.claude/skills/tailor-cv` and the other slash wrappers stop writing stage JSON in the host chat. They start or resume the run and surface exit code 6.
  - `web/src/lib/cvt-args.mjs` is the tool allowlist. `src/gtjob/llm.py` becomes the single client seam. Stage packets from `cvt brief` remain the context for each call.
- Pros:
  - One loop uses the tools to draft, observe a failed check, and ask the user, which is the harness the goal describes.
  - Illegal transitions and a repo shell never run. Today the CLI re-prompts once (`DEFAULT_MAX_ATTEMPTS` 2) and Studio depends on the agent obeying the prompt.
  - Each tool result is one small job, so the writing model stays replaceable.
  - Question and approval gates, attestations, and the two-page PDF stay as they are.
- Cons:
  - Step count varies with retries, up to the cap. A weak model can spend that cap on legal calls that do not improve the draft.
  - CLI, Studio, and slash entry points have to share this runner or the three writers return.
  - Page taste still waits for the person at approval. This option adds no PDF critic.
- Production rules: Deterministic work stays in code. Validate before the next step consumes a file. Cap the loop and stop at the gate or at the cap. Consecutive tool failures escalate. Persist `state.json` at the human gate. Answer and approve commits stay idempotent. Path-bounded writes, no host shell. Scan CV and JD text before it enters context. Trace each tool call and result. One model seam. The loader, not the model, selects the skill.
- Budget: M. Build: a few weeks, one product surface shared by CLI and Studio. Run: one capped tool loop per tailor. Deferred: a PDF critic, a trained QA model, a cloud sandbox, fine-tuning, inbox scoring, application submit.

## Option easy-stages: Code walks the stages

- Patterns: Sequential, Skill, Human gate
- Shape: Code keeps the stage list in `cvtlib/state.py`. `next_action_for` chooses the step. The model returns one JSON object for that stage and does not choose tools. `run_stage_checked` retries on check failure, then stops and asks. The harness is the same boundary as single-loop: schema, provenance, allowlisted argv, path-bounded writes, no repo shell. This repo runs the loop for every entry point. Gates and polish stay as they are. Orchestration is code.
- What changes from today:
  - Studio’s writing path becomes `ApiRunner` (the CLI runner), not `Agent.create` / `Agent.resume` in `web/scripts/infer-worker.mjs`.
  - The hardcoded `composer-2.5` worker and `AnthropicClient` fold into one client seam. Prompts still come from `cvt brief`.
  - Slash skills stop being a third writer of profile, match, questions, and tailor JSON. They call the same runner and stop at exit code 6.
  - `src/gtjob/flow.py`, the stage list, and both checkpoints stay.
- Pros:
  - Each model call stays one schema, which is the goal’s rule to make the model’s job easy, and it is how `flow.drive` already works.
  - The audit trail stays linear. High control over truthfulness stays in code.
  - The unsandboxed Cursor shell leaves the product without a new decision loop.
- Cons:
  - Recovery from a bad draft is one re-prompt, then a person. The model cannot look at a failed check and choose a different legal tool.
  - The outer loop is code. The goal’s one-sentence harness is a model loop that uses tools.
  - A new check is a new stage in `cvtlib`.
- Production rules: Code decides every next step. Structured output is validated before it is stored. The existing attempt cap stays, and the fallback is the human gate. Mutating commits stay idempotent. No host shell. Untrusted CV and JD text is wrapped before the prompt. Trace the stage, the check, and the result. One model seam. Skill text is versioned and loaded by the runner.
- Budget: S. Build: days, one path, entry points call the existing runner. Run: about one model call per writing stage, or one tool-backed check. Deferred: model-chosen tools, a PDF critic, a trained QA model, fine-tuning, other niches.

## Option checked-pdf: One loop, then a rubric on the PDF

- Patterns: Single agent (ReAct), Skill, Evaluator loop, Human gate
- Shape: The single-loop harness, plus a critic after render and before the approval gate. The rubric is code for what code can decide (page count, schema, provenance, placeholders) and a written taste rubric for bullets and layout. The critic revises through the same tools. Iterations are capped. At the cap, the best PDF is what the person sees at `awaiting_approval`. A provenance failure cannot be voted through. A failed pass is stored as a short lesson on the run, not the transcript. `cv-critic` today runs only when asked; this puts that check on the product path. Orchestration is code between the writer loop and the critic, then the existing human gate.
- What changes from today:
  - Everything in single-loop.
  - The CLI `--critic` flag is one pass between `validate` and the report. It becomes a capped revise loop on the rendered PDF, on by default for a tailor run.
  - `.claude/agents/cv-critic.md` is no longer only a side request from the host chat. Studio’s worker today stops when `report.md` exists and does not grade the PDF.
  - The approval screen shows the critic’s rubric result next to the diff. The person still approves.
- Pros:
  - The finished artifact is checked before the user is asked to approve it, which is the goal’s point about output details.
  - Fact checks stay in code, so the critic cannot talk a false claim into the PDF.
  - The fallback is the gate the product already has.
- Cons:
  - Every revision is another full round of calls. Cost varies with how often the rubric fails.
  - Taste still disagrees between readers. The gate remains the decision.
  - The critic shares the failure mode of any second model call: a vague rubric lets weak drafts pass.
- Production rules: All single-loop rules. The critic’s rubric is validated in code before a revision starts. Cap the rounds; at the cap, escalate to the approval gate. Feed the next attempt a lesson, not the transcript. The critic gets read access to the run artifacts and no extra tools. Trace the rubric score beside the generator’s tool trace.
- Budget: M. Build: a few weeks, one product surface, one capped critic on the tailor path. Run: one capped critic loop after the tool loop. Deferred: a model trained for PDF QA, pixel-level visual QA, fine-tuning, a cloud sandbox, other niches.

## Not proposed

Magentic. A task ledger and an open-ended sandbox run are what the Gamma walkthrough resembles (many models, a path that looks unplanned). gtjob’s tailor stages are already a known list, and a ledger does not make a claim cite the CV or take the shell away from the Cursor worker.
