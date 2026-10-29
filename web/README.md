# gtjob Studio

A local web app for one person. It shows gtjob runs under `out/` and, when `CAREER_OPS_ROOT` is set, the career-ops tracker. The Toolbox tailors a CV to a job, or polishes a CV with no job. It does not score a job or submit an application.

## Install and start

From this directory:

```bash
npm install
npm run dev
```

Open http://127.0.0.1:3847. The server binds to loopback.

```bash
npm test
npm run typecheck
```

## Where data lives

| Path | What it is |
| --- | --- |
| `../out/<slug>/` | A gtjob run. Studio reads `report.md` and PDFs, and calls `cvt` when you use a skill button. |
| `../.claude/` | Skills and agents. Studio lists them and runs the allowlisted `cvt` commands. |
| `../.studio/inbox.json` | Roles pasted on Today. Gitignored. Not scored. |
| `$CAREER_OPS_ROOT` | career-ops checkout. Unset means tracking is off. |
| `$CAREER_OPS_ROOT/data/applications.md` or `applications.md` | The tracker. Status changes go through `set-status.mjs`. |
| `../dossier` | Shown on Settings when the folder exists. Not connected. |

Set the checkout before starting:

```bash
export CAREER_OPS_ROOT=/absolute/path/to/career-ops
npm run dev
```

Point that variable at a scratch checkout if you change a status. Studio writes the real tracker when the variable points at it.

## Invariants

- A CV fact comes from a gtjob run or from `cvt`. Studio does not edit a bullet in the browser. Choice answers, approval, render, fit, validate, and report go through `cvt`.
- The Toolbox runs the model stages with a local Cursor agent (`@cursor/sdk`). Connect Cursor once, or set `CURSOR_API_KEY`. The IDE login is not reused. Tailor follows the tailoring skill and stops for questions and approval. Polish follows the cv-polish skill, keeps every fact, and renders modern, classic, and sidebar.
- Application status is the career-ops token. The board columns are labels on top of it.
- `set-status.mjs` is the only tracker write. A linked run is the note `gtjob-run:<slug>`.
- No route clicks Submit, Send, or Apply.
- Pasted job text is stored and shown. It is not an instruction.
- Liveness is the output of `check-liveness.mjs --no-record`, or "not checked".
- A score below `4.0/5` is marked "Do not apply".
