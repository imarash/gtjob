# gtjob Studio — architecture

Studio is a local Next.js app in `web/`. One person opens it on loopback and runs the search loop: see what needs attention, judge a role, open the tailored CV gtjob already produced, and track the application. Studio does not tailor, score, or submit. Those stay in the tools that already do them.

## The loop

1. **See.** Today lists what needs a person: follow-ups the career-ops cadence script marks due, tracker rows in `Evaluated`, and gtjob runs whose `state.json` is waiting on a checkpoint. Counts come from files. Zero is shown as zero.
2. **Judge.** An application page shows the score and legitimacy line stored on the career-ops report, and liveness only after `check-liveness.mjs --no-record`. Until that run, the line is "not checked".
3. **Tailor.** A run under `out/<slug>/` is produced by `uv run gtjob` or `cvt`. Studio lists it and serves the PDF and the match report. It does not rewrite bullets.
4. **Track.** Applications are the career-ops tracker. The board and the table are two views of those rows. Status text on disk stays the career-ops token.
5. **Act.** The page links the tailored PDF, the gtjob report, and the career-ops report path. Status changes go through `set-status.mjs`. Nothing in Studio clicks Submit, Send, or Apply.

## Decision table

Defaults from the session brief. One row is adjusted.

| Capability | Choice | What Studio does |
| --- | --- | --- |
| Fact-checked CV, gap questions, attestations, PDF, match report | Integrate | Reads `out/<slug>/`. Does not call the model and does not reimplement the fact gate. |
| Fit score, legitimacy, archived JD path, follow-up dates, canonical status | Integrate | Reads the tracker, report headers, `data/follow-ups.md`, and `data/status-log.tsv`. Due follow-ups come from `followup-cadence.mjs --json` when that script runs. Writes go through `set-status.mjs` only. |
| career-ops `web/` | Leave it | Not imported. Not edited. |
| Today, applications table, application detail, runs, settings, empty states | Implement | `web/` |
| Kanban | Implement, lightly | Five columns, cards link to the detail page. No drag-and-drop. |
| Cover letter, Gmail, calendar, job-board search, profile theme builder, Postgres | Later | No code in this slice. |
| FastAPI `gtjob serve` | Do not build | `pyproject.toml` `web` extra stays unused. |
| Which `out/` directory is a run | Adjusted | A directory counts when it has `report.md`, a `final/*.pdf`, or a `*.pdf` directly inside the directory. |

The run rule is wider than "report or `final/*.pdf`" because `/cv-polish` writes the three template PDFs in the run directory itself (`out/<slug>-generic/*.pdf`), not under `final/`. `inputs/` and `build/` are ignored, so a copied source CV or a fit draft does not make a directory a run. `20261026-golden-second` has only `inputs/cv.pdf` and stays hidden. A symlink is not followed, so a link such as `out/golden-sample` does not show up a second time beside the directory it points at. When `final/` already has PDFs, a source `cv.pdf` sitting next to them is not listed.

`CAREER_OPS_ROOT` is required for tracking. A sibling checkout at `../career-ops` is mentioned on Settings and is not used until the variable is set. The tracker path follows career-ops read resolution: `data/applications.md` when that file exists, otherwise `applications.md` at the root. A missing file is an empty state that names the path. A file that is not a recognizable table is an error on Settings and on Applications.

## Status columns

Stored status is the career-ops label (`Evaluated`, `Applied`, …). Columns are display-only.

| Column | States |
| --- | --- |
| Review | `Evaluated` |
| In progress | `Applied`, `Responded`, `Assessment` |
| Interview | `Interview` |
| Offer | `Offer`, `Hired` |
| Closed | `Rejected`, `Discarded`, `SKIP` |

A score that parses below `4.0` shows "Do not apply" next to the fraction as stored (`3.4/5`). `N/A`, `—`, and `-` are not numeric scores.

## Linking a run

The tracker notes cell may contain `gtjob-run:<slug>`. Studio writes that token with `set-status.mjs --row <id> <current status> --note gtjob-run:<slug>`. The note is one argv element. Company, role, and posting URL are never interpolated into a shell command. The same company and role on a run and a row is a hint on the run page, not a write.

Slugs are a single path segment: letters, digits, `.`, `_`, `-`. Status values must be labels in `templates/states.yml` at `CAREER_OPS_ROOT`.

Liveness, when requested, is `node check-liveness.mjs --no-record <url>` with the URL as its own argv element. The flag is required so a spot check does not append to `data/scan-history.tsv`.

Pasted roles are stored in gitignored `.studio/inbox.json`. Studio does not append to `data/pipeline.md` and does not start an evaluation. The dialog shows the career-ops pipeline command the person runs themselves.

## License boundary

New code lives in this repo (gtjob, MIT for the tailoring skill; Studio source is part of gtjob). career-ops is MIT and is invoked as a sibling process, not vendored. Dossier is AGPL-3.0. This session used it for screen names and for the shape of an application (posting, match, documents, status history, next interview, notes). No Dossier file, Prisma schema, or component is copied. No import reaches outside gtjob except reading career-ops files and spawning its scripts when `CAREER_OPS_ROOT` is set.

Personal trees stay gitignored: `CVs/`, `JDs/`, `out/`, `profiles/`, `.cache/`, `.studio/`, `web/.env`, `web/.env.local`.

## Later slices, in order

1. **Evaluate a pasted URL through career-ops.** Hand the inbox item to the career-ops pipeline and show the report when it exists. Still no model call inside Studio.
2. **Checkpoint questions in the browser.** Read `cvt` questions and post answers through `cvt`, still with the fact gate in Python.
3. **Follow-up cadence UI.** Log a follow-up through the career-ops writer, and draft the message without sending it.
4. **Cover letter.** A document next to the tailored CV, facts still from the profile.
5. **Find jobs.** A scan surface over career-ops portals. Dossier's find-jobs screen is the UX reference.

Still out of scope after those: editing CV bullets in the browser, accounts, Postgres, Gmail, calendar, deploying off loopback, and any edit under `../career-ops` or `../dossier`.
