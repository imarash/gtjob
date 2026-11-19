---
name: cv-reply
description: >-
  Tailors a CV to a job and, when that job arrives as a recruiter email, LinkedIn
  message, InMail, or Teams chat, also drafts the reply to send with the PDF.
  Use when the user pastes a hiring message plus a CV, asks for a LinkedIn, email,
  or Teams reply to HR or a recruiter, or invokes /cv-reply. Visa, salary, and
  location questions stay in the reply, never in the CV. Not a cover letter and
  not a LinkedIn profile rewrite.
argument-hint: "[cv-path] [pasted message or JD]"
disable-model-invocation: true
allowed-tools: Bash(uv run *)
---

# CV plus recruiter reply

Run `uv run gtjob tailor` for a new CV and JD, or `uv run gtjob continue` for a run that already exists.
The runner loads tailoring-cvs. This chat does not write the CV.

Stop when the exit code is 6. Print the pending gate that the command printed.
Do not write profile-map.json, jd.json, match.json, questions.json, or tailor-plan.json.

When the user asked for a reply, or the job text is a recruiter message, and `report.md` exists, run
`uv run gtjob reply RUN`. That command is one writing call. It does not tailor again.
A bare posting gets the CV only. Do not draft the reply before `report.md` exists.

A later turn that only edits the message runs `uv run gtjob reply RUN --text "..."` again.
A run started this way records host `cli` in `state.json` history.
