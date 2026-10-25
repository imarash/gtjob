# WP-I5: Integrate wave 5 (e2e suites) and prepare final acceptance

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 5 (after WP-25, WP-26, before G5) | WP-25, WP-26 | Sonnet (`cv-builder`) | S-M |

## Goal

Make the whole suite green (unit, integration, e2e), resolve the failures the e2e suites exposed with
minimal fixes, and leave the repo ready for final acceptance.

## Context

- Read `plan/tasks/_COMMON.md`, `plan/reports/WP-25.md`, and `plan/reports/WP-26.md`.
- You may make **minimal** fixes anywhere in product code (not in `plan/contracts/*`), each listed in your report.
  If a failure needs more than about 40 changed lines or a contract change, stop and escalate it to the gate.

## Owned files

- Minimal fixes (listed in your report)
- `plan/reports/WP-I5.md`

## Steps

1. Run `uv run pytest -q tests` and fix failures.
2. Run the release checks:
   - `lint-skill --all`
   - `package-skill --out dist/`, then unzip it and confirm it has no personal data: grep the zip for the sample
     name, the email, and the phone number. Expect no hits.
   - `git status --porcelain --ignored` confirms that `out/`, `profiles/`, `CVs/`, `JDs/`, and
     `tests/fixtures/private/` are ignored.
   - `rg -n "eval\(|exec\(" .claude src`: no hits on input-derived strings.
3. Produce the real sample artifacts for the gate reviewer, in a temp workspace and using the private goldens:
   `final/*.pdf`, `pages/*.png`, and `report.md`. Copy the PNGs to `.cache/review/` (git-ignored).

## Acceptance criteria

```bash
uv run pytest -q tests                                                  # passes
uv run .claude/skills/tailoring-cvs/scripts/cvt.py package-skill --out dist/
unzip -p dist/tailoring-cvs.zip | grep -c -i -E "morattab|arashmor" ; test $? -eq 1 && echo "no PII in package"
```

## Definition of done

The common definition of done.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-I5.md` under `## ESCALATION`. Do not change it.
