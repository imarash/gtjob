# WP-27 (optional, wave 6): Minimal local web UI

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 6 (optional; dispatch only after G5 approves) | Waves 1-5 | Sonnet (`cv-builder`) | M |

## Goal

Build a single-user local web page (`gtjob serve`) for people who don't use an IDE. It uploads a CV, pastes
or links a JD, answers checkpoint questions in a form, reviews the diff with approve/reject buttons, and
downloads the PDF and report. It is a thin view over the same `flow.drive` and `cvt` functions.

## Context

- Read `plan/tasks/_COMMON.md`.
- Use the `web` optional extra from WP-01 (`fastapi`, `uvicorn`, `python-multipart`, `jinja2`, and `httpx` for
  `TestClient`). Do not edit `pyproject.toml`; escalate if something is missing.
- Bind to `127.0.0.1` only. There is no auth (single user, local), and the README must say so. Uploaded files go
  to `GTJOB_HOME`, which is `out/` by default.

## Owned files

- `src/gtjob/web/__init__.py`, `src/gtjob/web/app.py`, `src/gtjob/web/templates/*.html`
- `src/gtjob/web/serve.py` (registers the `serve` subcommand through a `register(subparsers)` hook that WP-22's
  `cli.py` exposes; if it does not, escalate)
- `tests/unit/test_web.py`
- `plan/reports/WP-27.md`

## Steps

1. Routes:
   - `GET /` lists runs and has a form for a new run.
   - `POST /runs` runs `init` and `drive` until the first checkpoint.
   - `GET /runs/{slug}` shows the stage view.
   - `POST /runs/{slug}/answers` takes choices and free text.
   - `POST /runs/{slug}/edits` takes approve, reject, or a text instruction.
   - `GET /runs/{slug}/files/{name}` serves files, allowlisted to `final/*.pdf`, `report.md`, and `pages/*.png`;
     every path is checked against traversal.
2. All CV/JD-derived text is HTML-escaped (Jinja autoescape on).
3. Tests use FastAPI `TestClient` and the `FakeClient` from WP-26's fixtures: a full flow, a path traversal attempt
   returning 404, and an escaped `<script>` in a JD title.

## Acceptance criteria

```bash
uv run --extra web pytest -q tests/unit/test_web.py   # passes
```

## Definition of done

The common definition of done.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-27.md` under `## ESCALATION`. Do not change it.
