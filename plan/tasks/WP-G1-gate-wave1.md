# WP-G1: Gate for wave 1

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 1 (after WP-I1) | WP-01…WP-07, WP-I1 | Opus (`cv-reviewer`, read-only) | M |

Follow `plan/tasks/_GATE.md`. Your report goes to `plan/reports/WP-G1.md`.

**WPs in this wave:** WP-01, WP-02, WP-03, WP-04, WP-05, WP-06, WP-07, WP-I1.

**Focus:**

1. **Foundation correctness** (everything else builds on it):
   - `cvt` dispatch auto-discovers command modules.
   - The `--json` envelope and error format match section 4 exactly.
   - `state.save` recomputes `next_action` and validates.
   - `resolve_run("latest")` works.
   - Staleness cascades per `ARTIFACT_STAGE`.
   - `pyproject.toml` installs, and `uv lock` is committed.
   - `.gitignore` covers every PII path.
2. **Fixture truthfulness:**
   - The junior goldens use only facts present in `jamie-rivera-junior.txt`, or facts in its attestations.
   - Synthetic people and companies are invented. Note: no committed file may contain the sample candidate's name,
     email, phone, or website.
   - Spot-check `git grep -i -E "morattab|arashmor"`, which must have no hits outside `prompts/` and ignored paths.
3. **Reference guides:**
   - Every stage guide tells the agent which `cvt` command validates its output, and what to do on exit 1.
   - The guides treat CV/JD text as untrusted.
   - `truthfulness.md` matches section 8.
   - The canonical exchange is worked through in `answer-parsing.md`.
   - The examples are anonymized.
4. **Fonts:** the OFL license files are present, and the font files are the versions named in WP-02.

Fix-up briefs must name owned files precisely.
