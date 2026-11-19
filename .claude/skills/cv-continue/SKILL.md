---
name: cv-continue
description: Resumes the latest or a named CV tailoring run from its saved state, applying any answers or change instructions given with the command.
argument-hint: "[run-slug] [answers or change instructions]"
disable-model-invocation: true
allowed-tools: Bash(uv run *)
---
Run `uv run gtjob continue` for the run named in the text after this command, or the latest run.
Pass a free-text reply with `--text`. Pass an answers file with `--answers`.

Stop when the exit code is 6. Print the pending gate that the command printed.
Do not write profile-map.json, jd.json, match.json, questions.json, or tailor-plan.json.
A run started this way records host `cli` in `state.json` history.
