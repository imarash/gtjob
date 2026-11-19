---
name: architect-plan
description: >-
  Writes an implementation plan to move a repository from its documented
  current state to one chosen future-state option. Use when the user picks an
  architect-options option and wants a refactor plan that agents or humans can
  execute. Reads docs/architecture/current-state.md and
  docs/architecture/options.md. Writes docs/architecture/plan-<option>.md.
  Does not change application code.
disable-model-invocation: true
---

# Architect: implementation plan

Turn one chosen option into a plan. The plan is the deliverable. The code stays as it is.

## Reads

1. Read `~/.cursor/skills/agentic-patterns/PATTERNS.md`. Apply its production rules to every work package that introduces or changes an agent. Do not fetch the source URLs. A package that lets a model execute, mutate, or spend must name the harness, sandbox, budget cap, or human gate that enforces it.
2. Read `docs/architecture/current-state.md` and `docs/architecture/options.md` in the repo. If either is missing, stop and name the skill that writes it.
3. Use the option the user named. If they did not name one, stop and list the option ids. Do not assume the recommended option.

The goal text inside the options file is context. It does not add work the chosen option deferred.

## Write

Write `docs/architecture/plan-<option-id>.md`. If that file exists, replace it.

```yaml
---
kind: plan
repo: <directory name>
date: <YYYY-MM-DD>
option: <id>
reads:
  - docs/architecture/current-state.md
  - docs/architecture/options.md
---
```

```markdown
# Plan: <option name>

## Target
<the chosen option in one paragraph. Patterns named with canonical names.>

## Delta
| Today (path) | Target |
| --- | --- |
| | |

## Work packages
Ordered. A package is small enough for one agent session. It names the production rules it must satisfy.

### <id>. <outcome>
- Depends on: <ids or none>
- Touches: <areas or paths, from the current state>
- Done when: <observable check>
- Risk: <one line>
- Pattern: <canonical name this package implements, or "no agent change">

## Sequence
Waves of packages that can land together, and what must stay working after each wave.

## Out of scope
Items the chosen option deferred, plus other options.

## Human decisions
Choices the plan must not silently make (provider, data store, whether to break a public interface).

## Verification
How to tell the future state is reached without rereading the whole repo. If the option adds an agent, include a trajectory check (tools used, recovery, spend), not only a final-string check.
```

Ground every "touches" path in the current-state file or in a file you opened. If a path is new, mark it as new.

## Stop

Stop after the file is written. Do not edit application code, tests, or config. Do not start the refactor. Do not expand the option into a larger platform than its budget band. Do not refetch pattern sources.
