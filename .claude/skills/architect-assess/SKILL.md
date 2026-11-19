---
name: architect-assess
description: >-
  Documents the current architecture of a repository as an agentic system:
  agents, skills, tools, memory, orchestration, and which design patterns are
  already in use. Use when the user asks to assess, document, or map the
  current state of a repo before proposing a future architecture. Writes
  docs/architecture/current-state.md. Does not propose solutions or edit
  application code.
disable-model-invocation: true
---

# Architect: current state

Document the repo as it is. A later skill proposes future states. This one does not.

## Reads

1. Read `~/.cursor/skills/agentic-patterns/PATTERNS.md`. Use its canonical pattern names. Do not fetch the source URLs.
2. Read the repo the user named. If they did not name one, use the workspace root they have open. Stay inside that repo.

A business goal, strategy note, or job description in the conversation is out of scope. If one is present, record its path under "Parked inputs" and do not score the repo against it.

## Write

Write `docs/architecture/current-state.md` at the repo root. Create the directory if needed. If the file exists, replace it.

Front matter:

```yaml
---
kind: current-state
repo: <directory name>
date: <YYYY-MM-DD>
---
```

## How to look

Map what exists onto the six parts in the pattern library: loop, runtime, tools, skills, memory, guardrails. Then name the orchestration: code, model, or both. Under Runtime, say whether a harness (sandbox, path bounds, verification) exists, and who owns the loop (this repo, a daemon, or a managed platform). Under Memory, say which of short-term, episodic, and semantic exist.

Search for entry points, agent loops, skill files, prompts, MCP or A2A definitions, model-provider clients, stored state, human approval points, traces, sandboxes, checkpoint stores, and watchdogs. Cite a path for every claim. If a part is absent, write "none found" with where you looked.

Label each flow with one canonical pattern from the library. Evidence is a path plus the behavior, not a guess from the folder name. Do not label a triage router as Handoff; that is Router. Do not invent names for daemon, managed platform, or graph runtime.

## Output

```markdown
# Current state

## What this repo is
Two or three sentences. Who it is for and what it does today.

## Shape
| Part | What exists | Evidence |
| --- | --- | --- |
| Loop | | |
| Runtime | | |
| Tools | | |
| Skills | | |
| Memory | | |
| Guardrails | | |

Orchestration: <code, model, or both>. <one sentence>

## Flows
One subsection per user-visible flow.

### <flow name>
- Pattern: <canonical name>
- Steps: <what actually happens, in order>
- Evidence: `<path>`

## Distribution
How a person runs it today (CLI, plugin, web, bot, library), and whether each flow is request-response, a daemon, or a managed platform. "None found" is a valid answer.

## Coupling
Where the model provider, prompts, and product logic meet. Quote the seam if one exists.

## Parked inputs
Paths of goal or strategy files seen and not used.

## Open questions
Facts you could not confirm from the repo. No recommendations.
```

## Stop

Stop after the file is written. Do not propose options, budgets, or an implementation plan. Do not edit application code. Do not refetch pattern sources.
