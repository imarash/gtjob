# Privacy

This page explains where your CV, job descriptions, and profile data go, what stays on your machine, and how to
delete it. It covers the three ways to run gtjob: Cursor, Claude Code, and the CLI. For setup, see the
[README](../README.md).

## Contents

- [What is sent, and where](#what-is-sent-and-where)
- [What stays on your machine](#what-stays-on-your-machine)
- [Recruiter details in pasted job descriptions](#recruiter-details-in-pasted-job-descriptions)
- [Deleting data](#deleting-data)

## What is sent, and where

Your CV and job description text reach a model provider in every mode. The scripts themselves run locally and make no
network calls, except to fetch a job description from a `--jd-url` and to install packages.

| Mode | What leaves your machine | Goes to |
| --- | --- | --- |
| Cursor | The CV and JD text that the assistant reads for each stage, and the chat | The model provider behind Cursor, under your Cursor settings and terms |
| Claude Code | The same stage text and chat | Anthropic, under your Claude Code account and terms |
| CLI (`gtjob`) | The stage packets for the AI stages (profile map, JD analysis, match, questions, tailor plan, and optional critic) | The Anthropic API, using your `ANTHROPIC_API_KEY` |
| claude.ai or Skills API | Whatever you attach or paste into the conversation | Anthropic, under the claude.ai or API terms |

Details by mode:

- **Cursor and Claude Code.** The assistant reads the CV and JD through `cvt brief`, which prints only the parts of
  those files a stage needs. The `cv-critic` subagent runs on the same host and sees the critique packet.
- **CLI.** Each AI stage sends a packet to the Anthropic API. Model responses are cached on disk under
  `.cache/gtjob/llm/`, so an identical request is not sent twice. Use `--no-cache` to skip reading the cache.
- **Skills API and claude.ai uploads.** These are not covered by zero data retention (ZDR). Anything you upload or
  paste there is processed under that service's retention terms, not under a ZDR agreement. Upload only what you are
  willing to share with that service. The skill zip has no personal data, so uploading it is safe. Your CV is not.

## What stays on your machine

Everything personal is git-ignored, so it cannot be committed by accident:

| Path | Contents | Git-ignored |
| --- | --- | --- |
| `CVs/`, `JDs/` | Your input CVs and job descriptions | yes |
| `out/` | Every tailoring run, and a generic CV from `/cv-polish` (`out/<slug>-generic/`): parsed text, questions, the report, and the PDFs | yes |
| `profiles/<person-slug>/` | Your verified profile, one file per CV version, plus `attestations.json` (the claims you confirmed) | yes |
| `.cache/` | LLM response cache (`.cache/gtjob/llm/`), uv cache, logs | yes |
| `tests/fixtures/private/` | Any private golden fixtures you add for testing | yes |
| `dist/` | The packaged skill zip | yes |

The repo's committed files use invented people in examples and fixtures. Do not add real CVs, job descriptions, or
profile data to committed files.

## Recruiter details in pasted job descriptions

Job descriptions often contain personal data about the recruiter or hiring contact: names, email addresses, phone
numbers, and sometimes salary or visa details that name individuals. gtjob handles them like this:

- Recruiter contact details and recruiter questions are stored in the run's JD analysis and shown in `report.md`.
- They are never written into the tailored CV. A check in code fails the run if logistics text, such as a salary
  figure or a recruiter email, appears in the CV.
- They do stay in the run folder (`out/<run-slug>/`) and in the chat or API messages that carried the job description.

If you do not want those details kept, delete the run after you have finished with it, or remove the recruiter
lines from the JD file before you start a run.

## Deleting data

Deleting a run removes its intermediate files, report, and final PDF. It does not change your profile.

```bash
# One run
rm -r out/20261023-staff-platform-sre

# Every run, including finished PDFs (cannot be undone; profiles/ is not touched)
rm -r out/*

# One person's durable profile and confirmed answers
rm -r profiles/<person-slug>
```

Also delete the source files you copied into `CVs/` and `JDs/`, and clear caches if you want no trace of the runs:

```bash
rm -r .cache/gtjob/llm     # cached model responses
rm -r .cache/logs          # build and test logs
```

To withdraw one confirmed claim without deleting the profile, revoke it instead of deleting files: in Cursor or Claude
Code, run `/cv-profile revoke att-NNN`, or from the terminal run `cvt attest revoke att-NNN --person <person-slug>`.
A revoked claim is never used again.

In a chat host, the conversation history is kept by that host. Delete the conversation there, and check the host's
settings for retention.
