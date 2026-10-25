# WP-G6 (optional): Gate for wave 6

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 6 (only if WP-27 and/or WP-28 were dispatched) | WP-27, WP-28 | Opus (`cv-reviewer`, read-only) | S |

Follow `plan/tasks/_GATE.md`. Your report goes to `plan/reports/WP-G6.md`.

**WPs in this wave:** WP-27, WP-28 (whichever ran). The wave 6 gate runs no separate integration WP. Any join
problem (for example the `serve` registration hook or the `cvtlib.extras` hook in `ingest.py`) becomes a fix-up
brief.

**Focus:**

- The web UI binds to localhost only, autoescapes, allowlists file serving, and has no path traversal.
- DOCX and OCR fail gracefully when tools are missing.
- LaTeX escaping is exhaustive.
- `uv run pytest -q tests` remains green.
- The core skill's dependency list is unchanged, and `lint-skill --all` passes.
