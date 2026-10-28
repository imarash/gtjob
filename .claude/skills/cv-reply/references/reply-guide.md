# Recruiter reply

Read this only after `out/<run>/report.md` exists. Write `out/<run>/reply.md`.

## Channel

| Channel | How you know | Length |
| --- | --- | --- |
| `email` | From, Subject, Dear, or the user says email | Subject plus 120–180 words |
| `teams` | User says Teams or Slack, or it is a short chat thread | 40–90 words |
| `linkedin` | LinkedIn, InMail, a hiring post, or a short note to a named person | 70–130 words, no subject |

If several fit, use the one the user named. Otherwise use `linkedin` for a social post and `email` when there is a subject line.

## What you may say

From `report.md`:

- Role title and location as written in the message (location is fine in the reply).
- One or two **strong** must-haves that the PDF actually contains.
- Confirmed facts, in the user's wording, shortened. Do not upgrade "identity federation" into "Workforce Identity Federation" unless that phrase is in the confirmed fact.
- A honest hedge when coverage is partial: "closest work is …" rather than "I have done this requirement."

From the user in this chat only: visa type, prior relationship, tone, anything they asked you to include.

Never add employers, metrics, certifications, or tools that are not in the report or the user's message.

## Shape

```markdown
channel: linkedin
to: <name or "">
attach: <pdf filename>

<subject line, email only>

<body>
```

Body, in this order:

1. Greeting plus the role name, so they can match the thread.
2. The user's logistics question, if any, as a direct question.
3. One or two sentences of fit from strong matches or confirmed facts.
4. Prior contact, one sentence, only if the user said so.
5. Close: CV attached, offer to talk. Sign with the candidate's first name from the CV.

## Examples

LinkedIn, user asked about TN and said they had spoken before:

```text
Hi Anisha,

I saw your Cloud Engineer – Google Cloud Platform (GCP) post for Plano, Texas.

Do you support TN visa transfer for this opening? If yes, I would like to be considered. I have done several GCP engagements covering IAM, Terraform, and CI/CD, including organization setup with Terraform and identity federation.

We have connected on other roles before. I have attached my CV for this one.

Thanks,
Arash
```

Email subject:

```text
Subject: Cloud Engineer – GCP (Plano) — CV attached
```

Teams:

```text
Hi Anisha — saw the GCP Cloud Engineer role (Plano). Does this one support TN visa transfer? If yes, I'm interested; CV attached covers GCP IAM, Terraform, and CI/CD from recent client work. Happy to jump on a call.
```
