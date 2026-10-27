# WP-I5 report: integrate wave 5 and prepare final acceptance

Status: DONE. Whole suite green, release checks clean, sample artifacts produced. No product code changed.

## Summary

- `tests` (unit + integration + e2e): 1284 passed, 2 xfailed (strict), 0 failures. No fixes were needed, so no product file was touched.
- The 2 xfails are the open WP-25 escalations (below). Each needs a change to a file owned by an earlier WP (WP-29 `briefs.py`,
  WP-15 `questions.py`) and a product decision, so I did not patch them here.
- Release checks pass: `lint-skill --all`, `package-skill`, no personal data in the zip, ignored paths, no `eval(`/`exec(` hits.
- Sample artifacts (golden `sample`, private goldens, temp workspace) are in `.cache/review/` (git-ignored).

## Files changed

- `plan/reports/WP-I5.md` (this file). Throwaway helper `.cache/review/build_sample.py` (git-ignored).

## Acceptance and release checks (logs in `.cache/logs/WP-I5/`)

Note: plain `uv run` fails in the Cursor sandbox (cannot rewrite `.venv/bin/gtjob`), so pytest ran as `uv run --no-sync`.

```
$ uv run --no-sync pytest -q tests -rs -rx            (.cache/logs/WP-I5/pytest1.log)
1284 passed, 1 deselected, 2 xfailed in 147.27s (0:02:27)
XFAIL test_answer_parse_packet_fits_budget_on_sample - answer_parse packet ~3067 tokens vs 2500 budget
XFAIL test_second_jd_prompts_do_not_mention_suppressed_terms - suppressed term still in question prompt

$ uv run .claude/skills/tailoring-cvs/scripts/cvt.py lint-skill --all
lint ok: tailoring-cvs, tailor-cv, cv-continue, cv-status, cv-render, cv-profile

$ uv run .claude/skills/tailoring-cvs/scripts/cvt.py package-skill --out dist/
packaged .../dist/tailoring-cvs.zip (1935 KiB, 96 files); frontmatter verified

$ unzip -p dist/tailoring-cvs.zip | grep -c -i -E "morattab|arashmor" ; test $? -eq 1 && echo "no PII in package"
0
no PII in package
```

Extra PII checks on the zip: the real email address from the sample CV has 0 hits. The only email-shaped strings are synthetic
(`alex.chen@example.com`, `jordan@example.invalid`, `pat@agency.example`, `recruiter@example.com`). No phone number could be
extracted from the sample CV with a generic regex, so the phone check was not done (the CV text has no recognisable number).

```
$ git status --porcelain --ignored | grep '^!!'
!! .cache/  !! CVs/  !! JDs/  !! out/  !! profiles/  !! dist/  !! tests/fixtures/private/  (+ .venv, .pytest_cache, __pycache__)
$ rg -n "eval\(|exec\(" .claude src
(no hits, exit 1)
```

## Sample artifacts for the gate reviewer

Replayed the sample goldens (`tests/fixtures/private/sample/*`) through real `cvt` commands (`init` to `report`) in a temp workspace
(deleted afterwards): run reached `reported`, `cp1`/`cp2` done, template `modern`, 2 pages (target 2).

- `.cache/review/final/Arash-Morattab-Staff-Platform-Reliability-Engineer.pdf`
- `.cache/review/pages/page-1.png`, `page-2.png`
- `.cache/review/report.md`

Page 1 looks right (header, summary, skills, recent experience). Things for the reviewer to look at in the report:
req-12 "Proven ownership of production reliability" and req-14 "uptime, incident response" show **Found in PDF: no** (0/1, 0/2);
req-14 is only `partial`. Page 1 ends with some white space before the page-2 break. `pdfinfo` printed
`Syntax Error: Suspects object is wrong type (boolean)` (a poppler warning on the Typst PDF; page count is read correctly).

## Deviations

- Sample artifacts come from a throwaway script that mirrors `tests/e2e/conftest.py` (sample scenario) with `fit --png`, instead of a new test.
- `uv run --no-sync` for pytest (sandbox limitation, see above).

## Open issues (unchanged from WP-25, for G5)

1. `briefs.py` (WP-29) / `interfaces.md` 14.4: `answer_parse` packet on the sample is 3067 tokens vs the 2500 budget. Fix: cap the
   item-header digest to the items the questions name, or raise the budget. Then remove the xfail marker.
2. `questions.py` (WP-15): a suppressed gap choice is removed but its name stays in the question prompt on the second run. Fix: strip
   or rewrite suppressed terms in the prompt. Then remove the second xfail marker.
3. `logistics_leak` does not scan `open_items`/`omitted`, and `headline` is unchecked (WP-25 observations).
