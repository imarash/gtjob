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

Deliver both a tailored CV and, when the job text is a message, a reply the user can send.
The CV always follows [tailoring-cvs](../tailoring-cvs/SKILL.md). This skill only adds the reply.

## When to write a reply

Write `out/<run>/reply.md` when any of these is true:

- The user invoked `/cv-reply`.
- The pasted job is a **message**: it greets a person, is an email (From, Subject, signature), a LinkedIn post or InMail, or a Teams chat. A bare posting (title, responsibilities, requirements, no addressee) is not a message.
- The user asks to reply, follow up, or message the recruiter.

A bare posting still gets the tailored CV. Say that no reply was written, and write one only if they ask.

## Order

1. Read and follow `../tailoring-cvs/SKILL.md` until `report` exists. Same checkpoints, same truth rules. Do not draft the reply before that.
2. Save the original paste as `out/<run>/source-message.md` (verbatim). Pass only the role content to `cvt init --jd-text`. Recruiter logistics never go in the CV.
3. After `report`, read [reply-guide](references/reply-guide.md) and write `out/<run>/reply.md`.
4. In chat, give the PDF path, a match summary of at most 5 lines, and the reply text.

A later turn that only edits the message (`shorter`, `mention TN`, `warmer`) rewrites `reply.md` from `report.md` and `source-message.md`. Do not re-tailor unless they also change the CV.

## Reply rules

- Claims come from `report.md` (strong matches and **Confirmed facts**) or from words the user typed in this chat. Do not claim a **Remaining gap**.
- Ask visa, sponsorship, salary, start date, or onsite only when the user asked to raise it, or when answering a question the message already asked. Those questions stay in the reply.
- Mention a prior conversation only when the user said there was one.
- Use the sender's name when the message or the user gives it. Do not invent a name.
- Name the PDF filename as the attachment. Do not paste the CV into the message.
- Match the channel length in the reply guide. No "passionate" or "results-driven". Fix grammar. No emoji unless the user used them.
