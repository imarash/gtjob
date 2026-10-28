---
name: cv-polish
description: Polishes a CV into a generic resume with no job description, keeps every fact, aims for about 2-3 pages, and renders the modern, classic, and sidebar templates.
argument-hint: "[cv-path]"
disable-model-invocation: true
allowed-tools: Bash(uv run *)
---
Read `.claude/skills/tailoring-cvs/references/generic-cv.md` and follow it for the CV path in the text after
this command. This is not a job-description run: do not call `cvt init`, and do not drop facts to fit a page limit.
