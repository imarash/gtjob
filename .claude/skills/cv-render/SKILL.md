---
name: cv-render
description: Re-renders, page-fits, and validates an approved CV run, optionally with another template, density, or draft watermark, and refreshes the report.
argument-hint: "[run-slug] [--template modern|classic] [--draft]"
disable-model-invocation: true
allowed-tools: Bash(uv run *)
---
Read `.claude/skills/tailoring-cvs/SKILL.md` and follow its render, validate, and report steps for the run and
options in the text after this command (the latest run by default). Show the page images, the final PDF path, and
any failed gates with how to fix them.
