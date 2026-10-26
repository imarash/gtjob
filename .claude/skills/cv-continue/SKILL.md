---
name: cv-continue
description: Resumes the latest or a named CV tailoring run from its saved state, applying any answers or change instructions given with the command.
argument-hint: "[run-slug] [answers or change instructions]"
disable-model-invocation: true
allowed-tools: Bash(uv run *)
---
Read `.claude/skills/tailoring-cvs/SKILL.md`, then run `cvt status` for the run named in the text after this
command (or the latest run) and do exactly what its `next_action` says. If the text contains answers or change
instructions, apply them through the skill's checkpoint procedure (dry-run first, then commit) rather than editing
files directly.
