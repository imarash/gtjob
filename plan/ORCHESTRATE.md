# Orchestrating the build

This file tells you, the human, and the orchestrating agent how to run the plan:

- Waves of parallel Sonnet workers (`cv-builder`), with Haiku (`cv-builder-lite`) for the small briefs whose
  header says so.
- After each wave, an integration WP, then an Opus gate (`cv-reviewer`).
- After each approved gate, a commit by the orchestrator.

The progress log is `plan/STATUS.md`. It is the single source of truth for resuming, which is why every wave can
start in a **fresh chat**. That keeps the orchestrator's context small; a single long chat would re-send every
earlier wave's history on each turn.

## Contents

1. Before you start (once)
2. Cursor (primary)
3. Claude Code
4. Headless and API alternatives
5. Failure handling and resuming
6. Wave reference
7. Keeping the build cheap

---

## 1. Before you start (once)

1. Commit the plan and agent definitions **with explicit paths**. `CVs/` and `JDs/` are not ignored until WP-01
   writes `.gitignore`, so never use `git add -A` before then.

   ```bash
   git add plan .cursor/agents .claude/agents && git commit -m "plan: tailoring-cvs execution plan"
   git status --porcelain   # CVs/, JDs/, prompts/ remain untracked; that is expected
   ```

2. Check the tools: `uv --version`, `pdftotext -v`, and `typst --version` (optional; the Python wheel is primary).
3. Check that the sample CV is at `CVs/ArashMorattab-CV-2026-10.pdf`. WP-20 and the private tests need it; set
   `GTJOB_SAMPLE_CV` if you move it.
4. Optional, for wave 4-5 live evals only: `export ANTHROPIC_API_KEY=...` in the shell Cursor or Claude Code runs in.
5. Answer or accept the open questions in `plan/PLAN.md` section 12. The defaults are used if you do nothing.

## 2. Cursor (primary)

### 2.1 Models

- **Orchestrator:** the chat's own model. Pick **Claude Sonnet 5.5** in the Agent model picker. The orchestrator
  only dispatches, updates `STATUS.md`, and commits; the judgment lives in the Opus gates. Switch the chat to Opus
  only to decide a contract-change proposal.
- **Workers:** `.cursor/agents/cv-builder.md` pins `claude-sonnet-5-5-high`. `cv-builder-lite.md` pins
  `claude-haiku-5-5` (WP-02, WP-24, WP-I1, and mechanical fix-ups).
- **Gates:** `.cursor/agents/cv-reviewer.md` pins `claude-opus-5-5-high`.

If your Cursor build does not accept the bracket syntax (the subagent visibly runs on another model, or Cursor flags
the field), change `model:` to the plain ID shown in Settings → Models (for example `claude-sonnet-5-5`). As a last
resort use `inherit`, which runs workers on the orchestrator's model and costs more.

### 2.2 Kickoff prompt (paste into a new Agent chat)

```text
You are the orchestrator for the gtjob tailoring-cvs build. You dispatch, track, and commit; you do not write
product code and you do not read product code or briefs beyond their header row.

Read plan/STATUS.md and section 6 of plan/ORCHESTRATE.md (the wave table) only. Continue from the first wave in
STATUS.md that is not APPROVED. Do exactly one wave in this chat.

For that wave:
1. Dispatch every build WP of the wave IN PARALLEL, all in the same message. The agent comes from the brief's
   header row ("Owner model"): cv-builder-lite when it says Haiku, otherwise cv-builder. Each subagent prompt is
   exactly:
   "Execute plan/tasks/<brief file>. Read plan/tasks/_COMMON.md first. Report to plan/reports/<WP id>.md."
   For wave 4, dispatch WP-20 first in that batch (it is the longest).
2. When all return, update plan/STATUS.md (one row per WP: DONE/PARTIAL/ESCALATED and a one-line note).
   Re-dispatch PARTIAL WPs once with: "Continue <brief>. Your previous progress is in plan/reports/<WP id>.md
   and on disk; do not redo finished parts." A PARTIAL from cv-builder-lite is re-dispatched to cv-builder.
   Do not open the reports yourself; the workers' final messages are enough for STATUS.md.
3. Dispatch the wave's integration brief (WP-I<N>) to the agent its header names.
4. Dispatch the gate brief (WP-G<N>) to cv-reviewer.
5. If the verdict is FIX-UPS, dispatch all plan/tasks/WP-FIX-<N>-*.md briefs in parallel (agent per header), then
   re-run the gate with the prompt "Delta re-gate <k> of plan/tasks/WP-G<N>-*.md per _GATE.md". At most 2 fix-up
   rounds; after that, stop and ask me.
   If the gate wrote a contract-change proposal, stop and show it to me. Apply it to plan/contracts/ only after I
   agree (I may switch this chat to Opus for that), then re-dispatch the affected WPs.
6. On APPROVE: make sure `git status --porcelain` shows no CVs/, JDs/, out/, profiles/, .cache/ or
   tests/fixtures/private/ paths (from wave 1 on, .gitignore covers them), then
   `git add -A && git commit -m "wave <N>: <titles> (gate WP-G<N> approved)"`. Mark the wave APPROVED in STATUS.md
   and commit that too.
7. Stop and give me a 5-line summary: wave, verdict, fix-up rounds, anything I must decide, and the next wave.
   I will start the next wave in a new chat with this same prompt.

Rules: workers never commit; you never edit product files; subagents must not spawn subagents; keep every
subagent prompt to the single line above so the briefs stay the source of truth.
```

### 2.3 Running gates by hand

You can run any gate yourself in a fresh chat: "Use the cv-reviewer subagent on plan/tasks/WP-G2-gate-wave2.md".
The quick health check between waves:

```bash
uv run pytest -q tests/unit tests/integration
uv run .claude/skills/tailoring-cvs/scripts/cvt.py lint-skill --all   # from wave 3 on
```

### 2.4 Cursor specifics

- Workers share the checkout. Do **not** enable per-subagent worktrees, because ownership is disjoint by design and
  the git-ignored private fixtures do not exist in worktrees.
- If the sandbox blocks `uv` cache writes, workers use `UV_CACHE_DIR=.cache/uv` (stated in `_COMMON.md`).
- Final acceptance (G5) needs you to execute `evals/HOST-CHECKLIST.md` in Cursor and Claude Code. Paste the ticked
  list into chat, and the orchestrator saves it to `plan/reports/WP-G5-host-checklist.md`.

## 3. Claude Code

### 3.1 Subagents (recommended)

```bash
cd /path/to/gtjob && claude --model sonnet   # one session per wave
```

Paste the same kickoff prompt as in section 2.2, replacing "cv-builder subagent" with "the cv-builder agent via the
Task tool" (and the same for cv-builder-lite and cv-reviewer). Claude Code reads `.claude/agents/cv-builder.md`
(Sonnet; tools Read, Write, Edit, Bash, Glob, Grep), `cv-builder-lite.md` (Haiku), and `cv-reviewer.md` (Opus). Several Task calls in one assistant
message run in parallel.

- No `isolation: worktree` is set. Claude Code worktrees branch from the default branch rather than your current
  HEAD, and they lack git-ignored private fixtures.
- Pre-approve the tools for long waves (`/permissions`, or `--permission-mode acceptEdits`) so workers don't block
  on prompts. Keep the `git` commit step with the orchestrator.

### 3.2 Agent teams (if your Claude Code version has them enabled)

If you use the experimental agent-teams feature, check the current docs for the flag. Make the lead the Sonnet
orchestrator with the kickoff prompt. Each wave's teammates get one brief each, with the same one-line prompt and
the cv-builder rules (paste `.claude/agents/cv-builder.md`'s body as the teammate instructions). The integration WP
and the gate run only after every teammate in the wave has reported. Teammates must not message each other about
file changes, because ownership is disjoint by design.

## 4. Headless and API alternatives

### 4.1 Claude Code headless, one process per WP

```bash
run_wp() {  # $1 = brief path, $2 = model alias (haiku uses the lite agent body)
  local agent=cv-builder; [ "$2" = haiku ] && agent=cv-builder-lite
  claude -p "$(sed '1,/^---$/d' .claude/agents/$agent.md)
Execute $1. Read plan/tasks/_COMMON.md first. Report to plan/reports/$(basename "$1" .md | cut -d- -f1-2).md." \
    --model "$2" --allowedTools "Read,Write,Edit,Bash,Glob,Grep" --permission-mode acceptEdits \
    > ".cache/logs/$(basename "$1" .md).log" 2>&1
}
mkdir -p .cache/logs
for b in plan/tasks/WP-0{1,3,4,5,6,7}-*.md; do run_wp "$b" sonnet & done
run_wp plan/tasks/WP-02-render-assets.md haiku & wait   # wave 1
run_wp plan/tasks/WP-I1-integrate-wave1.md haiku
claude -p "Follow plan/tasks/_GATE.md for plan/tasks/WP-G1-gate-wave1.md" --model opus \
  --allowedTools "Read,Glob,Grep,Bash,Write" --permission-mode acceptEdits
# Read plan/reports/WP-G1.md; on APPROVE commit, then continue with wave 2 (WP-08..WP-13), and so on.
```

### 4.2 Claude Agent SDK (plain API with tools)

The raw Messages API needs a tool loop (bash and file editing) that you would have to build. The Agent SDK
provides it. Sketch (Python, `claude-agent-sdk`):

```python
import asyncio, pathlib
from claude_agent_sdk import query, ClaudeAgentOptions

BUILDER = pathlib.Path(".claude/agents/cv-builder.md").read_text().split("---", 2)[2]

async def run_wp(brief: str, model: str = "claude-sonnet-5-5") -> None:
    opts = ClaudeAgentOptions(model=model, cwd=".", system_prompt=BUILDER,
                              allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                              permission_mode="acceptEdits")
    async for _ in query(prompt=f"Execute {brief}. Read plan/tasks/_COMMON.md first.", options=opts):
        pass

async def wave(briefs: list[str]) -> None:
    await asyncio.gather(*(run_wp(b) for b in briefs))
# then run_wp(integration brief), then the gate with model="claude-opus-5-5" and the cv-reviewer body.
```

Verify the option names against the installed SDK version before use.

## 5. Failure handling and resuming

| Situation | Action |
| --- | --- |
| A worker returns PARTIAL (context ran out) | Re-dispatch once with the "Continue …" prompt (section 2.2, step 2). WP-20 has a planned Part A/B split |
| A worker reports `## ESCALATION` | Let the gate decide. If the contract must change, the gate writes `WP-G<N>-contract-change.md`; only the orchestrator applies it, after your OK |
| An acceptance command fails for reasons outside the WP | The integration WP fixes the join, or the gate writes a fix-up |
| A lite (Haiku) worker returns PARTIAL or its gate finds quality problems | Re-dispatch the same brief to `cv-builder` |
| A gate says FIX-UPS twice | Stop. Read the gate report, decide, and adjust the brief or contract |
| The chat or session died mid-wave | Open a new orchestrator chat with the kickoff prompt. STATUS.md and `plan/reports/` show what finished. Files on disk persist; uncommitted work in progress is kept (workers never reset) |
| Out-of-ownership edits found | The gate lists them. The orchestrator reverts them with `git checkout -- <file>` (orchestrator only) or accepts them in a fix-up |
| Live evals are not possible (no key) | G4/G5 record "not run". You run `uv run pytest -q evals -m live` later and attach the output |

## 6. Wave reference

| Wave | Build WPs (parallel) | Then | Gate |
| --- | --- | --- | --- |
| 1 | WP-01 … WP-07 (WP-02 lite) | WP-I1 (lite) | WP-G1 |
| 2 | WP-08 … WP-13 | WP-I2 | WP-G2 |
| 3 | WP-14 … WP-19, WP-29 | WP-I3 | WP-G3 |
| 4 | WP-20 (first), WP-21, WP-22, WP-23, WP-24 (lite) | WP-I4 | WP-G4 |
| 5 | WP-25, WP-26 | WP-I5 | WP-G5 (final; plus the human host checklist) |
| 6 (optional) | WP-27, WP-28 | — | WP-G6 |

## 7. Keeping the build cheap

The rules that matter most, with where each one is enforced:

| Rule | Where |
| --- | --- |
| Workers read only the cited `interfaces.md` sections (`sed` extraction), never the whole file | `_COMMON.md` section 1, agent bodies |
| Focused tests while iterating; full suite once; long output goes to `.cache/logs/` | `_COMMON.md` section 6 |
| Reports ≤ 80 lines (gates ≤ 120), with command summaries instead of full logs | `_COMMON.md` section 6, `_GATE.md` |
| Haiku for small, mechanical briefs and fix-ups | brief headers, `cv-builder-lite` |
| Sonnet orchestrator, one fresh chat per wave, no report reading | section 2.2 |
| Delta re-gates after fix-ups instead of full reviews | `_GATE.md` |
| One-line subagent prompts (briefs are the source of truth) | section 2.2 |

Record the approximate tokens per wave (from your host's usage view) in the `Build tokens` column of `STATUS.md`.
That shows whether a rule is not paying off.

