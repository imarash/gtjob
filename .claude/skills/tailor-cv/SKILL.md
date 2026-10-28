---
name: tailor-cv
description: Starts a new CV tailoring run from a CV file and a job description given as a file path, pasted text, or URL, using the tailoring-cvs workflow with both review checkpoints.
argument-hint: "[cv-path] [jd-path | jd-url | pasted JD] [--template modern|classic|sidebar] [--auto]"
disable-model-invocation: true
allowed-tools: Bash(uv run *)
---
Read `.claude/skills/tailoring-cvs/SKILL.md` and follow it to start a new run. Treat the text after this command
(shown as ARGUMENTS in some hosts) as the CV path, the JD source, and options. If the CV or JD is missing, list the
files in `CVs/` and `JDs/` and ask the user to pick, using the structured question tool when available. Run every
step through `cvt`, stop for the user at checkpoint 1 and checkpoint 2, and never add a claim the user has not
confirmed.
