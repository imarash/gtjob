---
name: cv-polish
description: Polishes a CV into a generic resume with no job description, keeps every fact, aims for about 2-3 pages, and renders the modern, classic, and sidebar templates.
argument-hint: "[cv-path]"
disable-model-invocation: true
allowed-tools: Bash(uv run *)
---
Run `uv run gtjob polish run --cv CV --out out/<slug>-generic` for the CV path in the text after this command.
That command extracts the text, makes one writing call, and renders modern, classic, and sidebar.

This command has no checkpoint. Exit code 6 is the tailor gate, used by `gtjob tailor` and `gtjob continue`; stop and print the pending gate if you see it there. Do not call `cvt init`. Do not write render.json yourself.
