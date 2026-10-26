---
name: cv-status
description: Shows the stage, pending questions, stale artifacts, and next step of CV tailoring runs in out/.
argument-hint: "[run-slug | --all]"
disable-model-invocation: true
allowed-tools: Bash(uv run *)
---
Run `uv run .claude/skills/tailoring-cvs/scripts/cvt.py status` with the text after this command as its argument
(`--all` lists every run), and summarize the result for the user in a few lines: the stage, what is pending, and
the next step. Do not advance the run unless the user asks.
