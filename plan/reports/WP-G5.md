# WP-G5 report: final acceptance

## Verdict

**FIX-UPS**: 4 small fix-ups (WP-FIX-5-1..5-4), then a delta re-gate. After that, the verdict can be "APPROVE pending
live evals and host checklist". Hard gates 1-3 pass. Hard gate 4 passes only with a strict xfail that hides a visible
re-ask. Gate 6 (live) was not run, because there is no `ANTHROPIC_API_KEY` here. Gate 7 (host checklist) is missing.
No contract change is proposed.

## Acceptance results

All commands were re-run by the reviewer (logs in `.cache/logs/G5/`). Commands that rewrite `.venv` or create dot-directories
ran outside the sandbox. The sandbox blocks `.git/`, `.claude/`, and `.venv/` writes under `.cache/fresh`.

| # | Check | Result | Decisive output |
| --- | --- | --- | --- |
| 1 | `uv run pytest -q tests -rs -rx` (private goldens present) | PASS* | `1284 passed, 1 deselected, 2 xfailed`; 0 skipped. *The 2 strict xfails are the WP-25 escalations (blocking B1, B2) |
| 2a | `cvt lint-skill --all` | PASS | `lint ok: tailoring-cvs, tailor-cv, cv-continue, cv-status, cv-render, cv-profile` |
| 2b | `cvt package-skill` + name grep | PASS | 96 files; only SKILL.md/LICENSE.txt/references/scripts/assets; grep `0` → "no PII in package" |
| 2c | Extra PII grep (real email, employer names Mobia/Softchoice, name) over the zip and all tracked + new files | PASS | 0 hits in 392 files |
| 3 | `git clone . .cache/fresh` + `uv run pytest -q tests/unit` | PASS | `1121 passed, 3 skipped` (private sample only) |
| 3b | Same clone + uncommitted `tests/e2e` + `tests/integration`, no private data | PASS | `133 passed, 29 skipped`; every skip says "private … absent" |
| 4 | Canonical exchange (`test_canonical_exchange_to_report`) | PASS | att-001..005 created; SLOs/Error budgets scope `role_label=SRE` → exp-2.e4, exp-2.e5; final PDF 2 pages; no gate fails |
| 4 | Second JD does not re-ask | **PARTIAL** | No choice is re-offered (test passes), but the q-1 *prompt* still says "Your CV doesn't currently show: … service mesh …" (strict xfail) → B2 |
| 5 | Truthfulness guard tests (20) | PASS | All pass. Adversarial probes found 2 gaps → B3, B4 |
| 6 | `uv run pytest -q evals -m live` | NOT RUN | No API key. 13 live tests collect; `evals/results/*` dirs are empty. Offline evals: `36 passed` |
| 7 | `plan/reports/WP-G5-host-checklist.md` | MISSING | Orchestrator or user to supply |
| - | WP-26 `test_cli_offline.py test_cross_host.py` | PASS | Part of #1. No API use (`ANTHROPIC_API_KEY` removed by fixture) |
| - | Real `out/`, `profiles/` untouched by the suite | PASS | No files newer than the run start |

## Findings

### Blocking

- **B1** (contract 14.4, WP-29 `briefs.py`): the sample `answer_parse` packet is ~3,045 tokens against a 2,500 budget.
  14.4 says "The e2e tests assert the same for the private sample". The waste is per-line `--item` commands (~275 tokens)
  and full summary paragraphs in "item headers" (~250 tokens). The fix compacts them and must not raise the budget,
  because `test_briefs.py` pins the table. → WP-FIX-5-1.
- **B2** (hard gate 4, WP-15 `questions.py`): `suppress` drops the covered choice but leaves its name in the prompt. The
  user is told their CV "doesn't show" service mesh right after confirming it. → WP-FIX-5-2.
- **B3** (truthfulness rule 5, `lexicon.numbers`): invented multiplier metrics pass `check_tailored`: ", tripling
  throughput", ", doubling release frequency", ", halving incident count", ", a tenfold improvement". → WP-FIX-5-3.
- **B4** (never invent titles): seniority inflation is prompt-only. On the junior golden, headline "Senior/Staff …"
  and summary "Principal DevOps architect …" all pass. → WP-FIX-5-4.

### Probes that held (no action)

"Kubernetes", "K8s", "Podman", "SOC 2", "CKA" (unsupported_term); "40%", "10x", "$2M" → 2000000, "15+ years"
(unsupported_number); shifted `end_date` and a "Senior " title prefix (fact_mismatch). "twelve" and "Terraform" passed
correctly, because both are in the source.

### Non-blocking

- N1: same-number reuse passes. "; led a team of 8" is accepted because "8 minutes" is in the bullet. Numbers are
  checked as a set, not in context. This needs a semantic check; v2.
- N2: rule 9 says logistics text must not appear "anywhere in `tailored.json`", but `UNSCANNED_SECTIONS` skips
  `open_items`/`omitted` (report-only fields; the report shows recruiter asks on purpose). Reword the rule to "anywhere
  rendered in the CV" at the next contract revision.
- N3: `.cursor/agents/cv-critic.md` still has `model: claude-opus-5-5[effort=high]`. Commit 3094a9f moved the other
  agents to plain IDs. Use `claude-opus-5-5-high` before the host checklist, or the Cursor critique may not start.
- N4: `tests/e2e/__init__.py` (empty) is outside WP-25's owned list. It is needed for the relative imports; accept it.
- N5: `questions` exit 6 and `--dry-run` envelopes carry an empty `next_action` (WP-25 note). `status` has it. This
  is minor for hosts.
- N6: `report.md` "Found in PDF: no" for req-12 "production reliability" while the PDF says "Site Reliability Engineer".
  The phrase match is literal, so keyword coverage (69%) understates the real coverage.
- N7: `pdfinfo` prints "Suspects object is wrong type (boolean)" on Typst PDFs. Page count and text round-trip are fine.

## Final review (hiring manager, sample: Staff Platform & Reliability Engineer)

Verdict: **a credible, honest 2-page CV I would phone-screen.** It scans quickly: the discipline headline (not the JD
title), a summary grounded in sum-2, and skills grouped toward the JD. Confirmed facts (service mesh, Istio, TypeScript,
SLOs/error budgets on the two SRE engagements only) land exactly in scope. Nothing invented. The report is the best
part: honest gap advice, recruiter asks kept out of the CV, and talking points.

Top 3 improvements for v2:
1. **Fill the page target.** Page 2 is ~45% empty while ~30 relevant bullets were "left out: lower priority", and the
   missing keywords (incident response, secrets management, network policies) sit in some of them. `fit` should
   back-fill by relevance up to the page target, not only trim.
2. **Metric strength.** Few bullets carry numbers (200 clusters / 800+ nodes, 8-member team). The metric questions
   (q-3..q-5) were defaulted to "no figure". Ask at most 2 high-value metric questions first, and make "skip" cost
   one keystroke.
3. **Bullet quality pass.** Weak lines survive as-is: "Tools in use: OpenShift, …" (a tool list as a bullet),
   "Oversaw a Kubernetes-friendly production environment", and generic Altimetrik lead bullets. Add a rewrite-only
   style pass, checked by the same provenance rules, for tool-list bullets and vague verbs.

## Open-question defaults (PLAN.md section 12) the build proved wrong

- Q4: bracket model IDs (`[effort=high]`) do not work in Cursor. Plain IDs were adopted, but cv-critic was missed (N3).
- Q15: seeding at ≥ 0.6 never fires on a real 2-page CV. The sample plan alone is ~5,400 tokens, so with the seed the
  tailor packet exceeds 8,000 and the seed is always trimmed (WP-25). Either send a compact seed (ids + ops only) or
  drop the feature.
- Q9: Morgan Stanley stayed a full entry (its on-call bullet supports req-14), against the "Morgan Stanley and older
  collapse" default. The relevance-driven choice is better; update the default text.
- Q14 (Haiku for jd/answer_parse/change_request) and Q13 (no Cursor rule) stay unproven until gates 6 and 7 run.
- Q7 (page target 2) is right, but see improvement 1: the target is used as a cap, not a goal.

## Fix-up WPs

Run them in this order: 5-1 before 5-2, because both edit `tests/e2e/test_sample_canonical.py`. 5-3 and 5-4 can run in
parallel with them.

- `plan/tasks/WP-FIX-5-1-answer-parse-budget.md` (Sonnet): `briefs.py`, `test_briefs.py`, e2e marker removal.
- `plan/tasks/WP-FIX-5-2-suppressed-prompt-terms.md` (Sonnet): `questions.py`, `test_questions.py`, e2e marker removal.
- `plan/tasks/WP-FIX-5-3-multiplier-words.md` (Sonnet): `lexicon.py`, `test_lexicon.py`.
- `plan/tasks/WP-FIX-5-4-seniority-claims.md` (Sonnet): `provenance.py`, `test_provenance.py`.

## Notes for next wave / orchestrator

- Delta re-gate: `uv run pytest -q tests -rx` must show `0 skipped, 0 xfailed`. Then re-run my probe script
  `.cache/g5probe/probe.py` (git-ignored); B3 and B4 lines must read CAUGHT, except "headline Lead" (allowed).
- Gate 6 needs `ANTHROPIC_API_KEY`. Record the judge mean, minimum criterion, truthfulness versus baseline, trigger
  recall and false positives, 3-run consistency, and per-stage input / cache-read / output tokens plus cost for the
  new-JD run (≤ 1.25 × budget totals).
- Gate 7: fix N3 first, then have the user run `evals/HOST-CHECKLIST.md` in Cursor and Claude Code and paste the result
  into `plan/reports/WP-G5-host-checklist.md`. The Q13 decision depends on its follow-up-trigger rows.
- In the Cursor sandbox, use `uv run --no-sync pytest` (plain `uv run` cannot rewrite `.venv/bin/gtjob`). The
  fresh-clone check needs to run unsandboxed (dot-directories under `.cache/`).

## Re-gate 1

**Verdict: FIX-UPS** (2 extra-small Haiku fix-ups, which can run in parallel because their files don't overlap). B1-B4 are fixed, and every
acceptance command passes. But my new edge probes found two evasions of the B3/B4 guarantees: "twice as fast" and
"Sr. DevOps Engineer". After WP-FIX-5-5 and 5-6, the next delta re-gate can give "APPROVE pending live evals (gate 6)
and host checklist (gate 7)".

| Check | Result | Decisive output |
| --- | --- | --- |
| Ownership (`git diff --stat HEAD`, `git status`) | PASS | Only the 4 fix-ups' owned files + `plan/STATUS.md`. `tests/e2e/` is untracked (WP-25) |
| FIX-5-1..5-4 unit files (`test_briefs/questions/lexicon/provenance`) | PASS | `346 passed` |
| `tests/e2e/test_sample_canonical.py -rx` | PASS | `5 passed`. No `xfail` or `enforce_budget` left in the file |
| Full suite `uv run --no-sync pytest -q tests -rs -rx` | PASS | `1334 passed, 1 deselected`, 0 skipped, 0 xfailed (`.cache/logs/G5/re1/suite.log`) |
| Sample `answer_parse` packet | PASS | `est_tokens` 2441 ≤ 2500, no budget warning. `--item exp-2.e4` expands in full |
| `lint-skill --all`, `package-skill` | PASS | lint ok (6 skills). 96 files. Only PII-like hits are the frozen schemas' "Royal Bank of Canada (RBC)" example |
| Probe `.cache/g5probe/probe.py` | PASS | B3 (doubled/halved/tenfold/tripling) and B4 (Senior/Staff/Principal) now CAUGHT. "headline Lead" is allowed |
| Edge probe `.cache/g5probe/probe3.py` | **FAIL** | See R1, R2 |

FIX-5-4's "flaky" `test_answer_parse_packet_fits_budget_on_sample` is not flaky. The packet size is deterministic
(chars / 3.8). Its one failure came from FIX-5-1 editing `briefs.py` at the same moment. It passes alone and in the full run.

### FIX-5-1 deviation (location and `| role:` dropped from compact header lines): accepted, non-blocking

- Section 14.3 is an example format. Its normative sentence still holds: every work entry and engagement keeps its own
  header line, with the `+N bullets hidden` count. Section 13's `answer_parse` row ("item headers + role labels") also
  holds: the packet keeps a role-labels block, `SRE (exp-2.e4, exp-2.e5)`.
- `answer-parsing.md` says "Resolve scopes by role label only; the script maps labels to item ids". So the model never
  needs a per-line role to scope. Employer, client, position, and dates stay on every line.
- Location is only needed for a location correction's exact `old_value`. A wrong guess is rejected by the dry run,
  which prints the profile's current value (`answers.py:304`), and `--item` gives the full item. One retry recovers it.
- Costs (notes, no fix now): (a) The 80-character prompt clip cuts the free-text metric questions q-3..q-5 mid-sentence
  ("Roughly how many OpenShift environments or…"). (b) The margin is thin, 59 tokens. Cheaper cuts for v2: drop
  `| unknown` employment types (about 30 tokens on the sample) and collapse `cert-N` lines into one id list (about 150
  tokens). Then restore the 160-character prompt clip. (c) At the next contract revision, note in 14.3 that
  `answer_parse` uses compact headers. No contract change is needed now.

### Blocking

- **R1** (never invent titles; evasion of B4): headline "Sr. DevOps Engineer · AWS", "Snr DevOps Engineer", and the
  summary "Sr. DevOps engineer …" all pass on the junior golden. "SENIOR", "Senior-level", "Head of", "VP", and "CTO" are
  caught. → WP-FIX-5-5.
- **R2** (rule 5; evasion of B3): ", twice as fast", ", deploying thrice as often", and ", quintupling throughput" pass.
  "2-fold", "two-fold", and "3×" are caught. → WP-FIX-5-6.

### Non-blocking

- R3: FIX-5-2's removal is whole-word on the label, so a hyphenated "service-mesh" in an AI-written prompt survives
  (both the label and the term miss it). The real sample prompt is clean, and the e2e test passes. In v2, normalize
  hyphens to spaces before matching.
- R4: multiplier false positives are conservative (flagged, then rewritten by the fix stage): "doubling down on
  automation" → 2, "first half of 2023" / "half-day" → 50, "doubles as a dashboard" → 2.
- R5: "an order of magnitude faster" and "x3 throughput" still pass. This is the known semantic limit, like N1.
- R6: seniority in bullets ("As senior engineer, …") is unchecked by design (FIX-5-4 brief). Rule 6 still guards titles.
- N3 is still open: `.cursor/agents/cv-critic.md` has `model: claude-opus-5-5[effort=high]`. Fix it before gate 7.

### Fix-up WPs (round 2)

- `plan/tasks/WP-FIX-5-5-seniority-abbreviations.md` (Haiku): `provenance.py`, `test_provenance.py`.
- `plan/tasks/WP-FIX-5-6-twice-thrice.md` (Haiku): `lexicon.py`, `test_lexicon.py`.

Re-gate 2: re-run both briefs' acceptance commands, `probe.py`, and `probe3.py` (every R1/R2 line must read CAUGHT),
then the full suite with 0 skipped and 0 xfailed.

## Re-gate 2

**Verdict: APPROVE pending live evals (gate 6) and host checklist (gate 7).** R1 and R2 are fixed. Hard gates 1-5
pass, there are no blocking findings, and no contract change is needed. Gate 6 is still not run (no `ANTHROPIC_API_KEY`),
and `plan/reports/WP-G5-host-checklist.md` is still missing.

| Check | Result | Decisive output |
| --- | --- | --- |
| Ownership (`git status`, `git diff --stat HEAD`) | PASS | The new changes are only in `provenance.py`, `lexicon.py`, `test_provenance.py`, `test_lexicon.py`, and the two reports. No `plan/contracts/` or `.cursor/` edits |
| FIX-5-5 + FIX-5-6: `pytest -q tests/unit/test_provenance.py tests/unit/test_lexicon.py` | PASS | `224 passed` |
| Full suite `uv run --no-sync pytest -q tests -rs -rx` | PASS | `1349 passed, 1 deselected` (`live`), 0 skipped, 0 xfailed (`.cache/logs/G5/re2/suite.log`) |
| `lint-skill --all` | PASS | `lint ok` for all 6 skills. PII grep of the fix-up diffs: 0 hits |
| `probe.py` | PASS | All B3/B4 lines CAUGHT. The expected MISSED lines did not change: "twelve" and Terraform (both in the source), "led a team of 8" (N1), negation flip (semantic), "headline Lead" (allowed) |
| `probe3.py` R1 | PASS | The headlines "Sr. DevOps Engineer" and "Snr DevOps Engineer" and the summary "Sr." are all CAUGHT as `unsupported_term` 'Sr'/'Snr' |
| `probe3.py` R2 | PASS | ", twice as fast", ", deploying thrice as often", and ", quintupling throughput" are all CAUGHT as `unsupported_number` |
| Extra probes | PASS | "Sr/Staff", "SR. DEVOPS", "Sr.DevOps", "TWICE", "twice-weekly", "sextupled", and "decupling" are all CAUGHT. "SRE", "entwice", and "thricely" give no false hits. "Jr."/"Jnr" pass on the junior golden, which is correct because the profile says "Junior" |

### Non-blocking

- R7: the summary "Seasoned DevOps engineer" (in place of "Junior") passes. "Seasoned" is a soft adjective, not a
  level word, and rule 6 still guards titles. This has the same semantic limit as R5 and R6; v2.
- R8: a source that names "SR-IOV" (or a client called "SR …") would count as support for "Senior". Real risk is
  negligible, and the brief specified this behaviour.
- N3 is **still open**: `.cursor/agents/cv-critic.md` line 4 still has `model: claude-opus-5-5[effort=high]`. The
  orchestrator must change it to `claude-opus-5-5-high` before the user runs gate 7, or the Cursor critique row
  may fail. It is a one-line edit, so no fix-up brief.

### Remaining before final APPROVE

1. Gate 6: `uv run pytest -q evals -m live` with an API key. Record the numbers listed in "Notes for next wave".
2. Gate 7: fix N3, then the user runs `evals/HOST-CHECKLIST.md` in Cursor and Claude Code. Paste the result into
   `plan/reports/WP-G5-host-checklist.md`.
