---
name: tailor-cv
description: Starts a new CV tailoring run from a CV file and a job description given as a file path, pasted text, or URL, using the tailoring-cvs workflow with both review checkpoints.
argument-hint: "[cv-path] [jd-path | jd-url | pasted JD] [--template modern|classic|sidebar] [--auto]"
disable-model-invocation: true
allowed-tools: Bash(uv run *)
---
Run `uv run gtjob tailor` with the CV path, the JD source, and the options in the text after this command.
The runner loads tailoring-cvs. This chat does not.

Stop when the exit code is 6. Print the pending checkpoint that the command printed.
Do not write profile-map.json, jd.json, match.json, questions.json, or tailor-plan.json.
A run started this way records host `cli` in `state.json` history.
