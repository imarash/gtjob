# WP-G3 gate report: wave 3

## Verdict

**FIX-UPS.** Every acceptance command passes, and the full suite is green (949 passed, 1 skipped). A by-hand junior
session in a temp `GTJOB_HOME` (logs in `.cache/logs/G3/`, workspace `.cache/g3ws/`) found 5 blocking defects: 2 break
truthfulness, 2 make the packets or `SKILL.md` unusable on their own, and 1 breaks suppression. No contract change is
needed. All five fix-ups own disjoint files and can run in parallel.

## Acceptance results

| WP | Command | Result |
| --- | --- | --- |
| 14 | `pytest tests/unit/test_fit.py tests/unit/test_validate.py` | pass (33 passed) |
| 15 | `pytest tests/unit/test_questions.py tests/unit/test_answers.py` | pass (69 passed) |
| 16 | `pytest tests/unit/test_diff.py tests/unit/test_edits.py` | pass (49 passed) |
| 17 | `pytest tests/unit/test_template_classic.py`; `ls …/classic-*.png` | pass (6 passed; 2 PNGs, regenerated fresh) |
| 18 | `pytest tests/unit/test_skillcheck.py` | pass (35 passed) |
| 18 | `cvt lint-skill --all` | exit 0 (`lint ok: tailoring-cvs, tailor-cv, cv-continue, cv-status, cv-render, cv-profile`) |
| 18 | `cvt package-skill --out .cache/g3dist/` + `unzip -l` | pass (96 files, 1930 KiB, no `out/`, `profiles/`, `.cache/`, or `__pycache__`) |
| 18 | `wc -l SKILL.md` | 134 (< 500; body cap 150 met) |
| 19 | `pytest tests/unit/test_report.py` | pass (23 passed) |
| 29 | `pytest tests/unit/test_briefs.py tests/unit/test_assemble.py`; `cvt --help \| grep` | pass (92 passed; both commands listed) |
| I3 | `pytest tests/unit tests/integration` | pass (949 passed, 1 skipped; `.cache/logs/G3/suite.log`) |
| I3 | `cvt lint-skill --all` | exit 0 |

Ownership: `git status --porcelain` shows only wave-3 owned files, wave reports, and `plan/STATUS.md` (the
orchestrator's). WP-I3 edited `tests/unit/test_validate.py` and `references/host-notes.md` as listed minimal fixes;
both are acceptable. `prompts/` was untracked before this wave.

## Findings

### Blocking

1. **Packets are not self-sufficient (WP-29).**
   - No packet shows the JSON shape of its output. `## Output` only names the schema, and examples appear only with
     `--full`, which exceeds the budget (profile ~3,350/2,041, tailor ~8,060/8,000). A model must open the 4–7 KB
     schema files, and wave 4's CLI sends packets as the whole prompt.
   - The jd Rules say "copy `jd_sha256`/`source` from the packet", but the packet has neither. `jd-check` enforces
     the hash, and the fix packet prints only a 12-character prefix, so the check cannot pass from the packet alone.
   - Fix-up: `WP-FIX-3-1`.
2. **Spelled-out numbers bypass rule 5.** `lexicon.numbers` reads only digits. `assemble` exited 0 for an invented
   summary sentence "Five years of AWS experience." and for "pipelines for twenty services" (the source says 12).
   Fix-up: `WP-FIX-3-2`.
3. **Attestation terms are not grounded in the user's words (WP-15).** With the reply "I used Helm at Brightfield …",
   a round with claim "Kubernetes" passed the dry run. A round with claim Helm and terms `[Helm, Kubernetes, ArgoCD]`
   also passed, and the dry-run line showed only "Helm", so the user would approve tools they never saw. Rule 4 then
   accepts a "Kubernetes" bullet citing that attestation. "add Linux …" → claim "Bash" also passed. Fix-up:
   `WP-FIX-3-3`.
4. **Suppression fails in the canonical case (WP-15).** `_covering` requires every `term|synonym` part to be covered.
   After `att-001` (Helm, terms `["Helm"]`) became active, a second run on the same CV and JD re-asked "a) Helm"
   (the golden value is `Helm|Helm charts`). Fix-up: `WP-FIX-3-4`.
5. **`SKILL.md` is broken on the default shell and never stores the profile (WP-18).**
   - `CVT="uv run …"; $CVT status` exits 127 under zsh. Verified: zsh fails, bash works.
   - Nothing runs `profile-cache --store`, so a second run on the same CV missed the cache (section 14.2 and Token
     rule 8). After a manual `--store`, lookup hit and the JD cache hit.
   - Fix-up: `WP-FIX-3-5`.

### Non-blocking (orchestrator: carry into WP-I4 or a later fix-up)

- `cvt status` keeps printing `error: [E_CHECK_FAILED] …` from an earlier failure after later commands succeed, even at
  `reported`. A resuming agent may chase an error that no longer applies. This is wave-2 `status` code.
- Ambiguous scope: commit exits 6 ("add the scope question (`questions --add`)"), but `next_action` says "Ask the
  pending questions". If the agent skipped `--add`, `questions` then reports "no questions" and moves to
  `answers_applied`, and the unresolved attestation is silently unused. The answer_parse packet does instruct
  `--add`, so the main path works.
- An underfilled 1-page junior run (default `page_target` 2) always raises a `layout` warning, and Token rule 4 then
  has the agent view a PNG on every short CV. Consider making `underfilled` informational, or the default page
  target seniority-aware.
- The render fixture at `standard` density leaves page 2 holding only Education (6% filled). The layout gate flags
  it correctly, but neither `SKILL.md` nor `next_action` gives a remedy (tighter density, or `set_field page_target`).
- `classic` breaks a URL mid-string in the contact line (`github.com/` | `alexchen-example`). `modern` wraps at a
  separator.
- Lowercase invented names ("for the client contoso") pass provenance. This is a known limit of lexical checks;
  the user sees them at checkpoint 2.
- Every packet repeats the untrusted-input rule up to 4 times and the check command 3 times (~100–150 tokens).
- `change_request` gives 80-character excerpts. A reply like "the monitoring bullet" is not matched to full text, so
  `replace_text` needs a `--item` call.
- `cv-render` wrapper says "Show the page images", which conflicts with Token rule 4.
- Approval activates every resolved proposed attestation of the run (as interfaces.md section 7 says), not only the
  cited ones. `attestations_used` is exact. The gate brief's wording differs from the contract, and the contract
  wins.
- `briefs._diff_index` still has an import fallback that swallows `KeyError`/`CvtError`. If it fires, `[N]` would no
  longer match the diff the user saw. Remove it now that `diff.py` exists.
- `cp2` stays `done` after a late answer regresses the run; the Cursor `cv-critic` model string is unverified.

### Verified good

- Packets: profile 1,569/2,041, jd ~1,350/3,000, match ~2,070/7,000, questions 1,252/4,000, answer_parse ~1,280/2,500,
  tailor 2,550/8,000, change_request ~1,640/3,000. Digests, prematch, and attestation lines follow 14.3.
- `assemble` copies facts. A `keep` with mutated (or identical) text fails, and so do a rewrite naming "Walmart", an
  invented tool (either case), a digit number, a date, "CKA", an attested bullet out of scope, an unsupported skill,
  and a headline "Senior SRE at Google".
- Checkpoint 1: the dry run writes nothing and shows the mapping; `--select --default-rest` gives one global skills
  attestation; bad IDs exit 2 with hints; the cap is 8; Claude Code calls hold ≤ 4 questions with ≤ 4 options.
- Checkpoint 2: the compact diff (21 lines) shows before and after with refs; bad batches are rejected atomically; a
  late answer at `reported` makes every downstream artifact stale.
- Fit: priority 1 pinned, density before drops, monotone search. Junior lands on 1 page (`underfilled` reported);
  the render fixture lands on 2. Report: recruiter asks in their own section, honest gaps, defaults, token usage.
- Visuals: `classic` is close to Jake's Resume; `modern` has a clear hierarchy. `cv-critic` is read-only on both
  hosts; wrappers are one paragraph; no `eval`/`exec`, network use in tests, PII, or absolute paths.

## Fix-up WPs

| Brief | Owner | Files |
| --- | --- | --- |
| `plan/tasks/WP-FIX-3-1-packet-output-shapes.md` | Sonnet | `briefs.py`, `test_briefs.py`, `budgets.json` |
| `plan/tasks/WP-FIX-3-2-number-words.md` | Sonnet | `lexicon.py`, `test_lexicon.py` |
| `plan/tasks/WP-FIX-3-3-attestation-term-grounding.md` | Sonnet | `answers.py`, `test_answers.py` |
| `plan/tasks/WP-FIX-3-4-suppression-synonyms.md` | Haiku | `questions.py`, `test_questions.py` |
| `plan/tasks/WP-FIX-3-5-skill-invocation-and-profile-store.md` | Haiku | `SKILL.md`, `references/commands.md` |

The owned files are disjoint, so all five can run in parallel. Then do a delta re-gate.

## Notes for next wave

- WP-21 (CLI) must call `profile-cache --store` after `profile-build`, and must rely on the `shape:` line from
  WP-FIX-3-1 rather than on schema files.
- WP-22/WP-25: add an e2e check that a second JD for the same CV hits the profile and JD caches, and that the questions
  already answered are suppressed.

## Re-gate 1

**Verdict: FIX-UPS.** The five fix-ups did what their briefs asked. Every acceptance command passes, and the full suite
is green (995 passed, 1 skipped; `.cache/logs/G3/re1/suite.log`). Adversarial probes found 3 new blocking defects in
the areas the fix-ups covered: 2 truthfulness holes, and 1 shape line that contradicts the schema. No contract change
is needed. The three new fix-ups own disjoint files.

Ownership: only the fix-ups' owned files changed since the gate report (`briefs.py`, `lexicon.py`, `answers.py`,
`questions.py`, `SKILL.md`, `commands.md`, their tests, and the reports), plus the orchestrator's `STATUS.md`.
`budgets.json` is unchanged. The workers' flaky failures (budget 1879/1800, `KeyError: 'terms'`) came from parallel
edits in progress; neither reproduces.

| Scope | Command | Result |
| --- | --- | --- |
| FIX-3-1, WP-29 | `pytest test_briefs.py test_assemble.py`; `cvt --help \| grep` | pass (109); both listed |
| FIX-3-1 | `pytest tests/integration/test_wave3.py` | pass (8) |
| FIX-3-2, WP-13 | `pytest test_lexicon test_provenance test_assemble test_checks`; `wc -l tech-terms.txt` | pass (181); 686 |
| FIX-3-3/3-4, WP-15 | `pytest test_answers.py test_questions.py` | pass (82) |
| FIX-3-5, WP-18 | `pytest test_skillcheck test_wave3 test_wave1`; `lint-skill --all` | pass (108); exit 0 |
| FIX-3-5, WP-18 | `rg 'CVT='` / `rg 'profile-cache RUN --store'` / `wc -l SKILL.md` | no match / 1 match / 138 |
| WP-18 | `package-skill --out .cache/g3dist-re1/` | 96 files, 1933 KiB, no `out/`/`profiles/`/`.cache`/`__pycache__` |
| all | `pytest tests/unit tests/integration` | pass (995 passed, 1 skipped) |

Verified fixed: jd packet has the full `jd_sha256` and `source: kind=file ref=…`. `run_id:` is printed in match and
questions. Every AI packet has a `shape:` line. "twenty services" and "two thousand hosts" now fail rule 5. Gate rounds
for Kubernetes, ArgoCD, and Bash fail `unsupported_term`; EKS → Kubernetes, Java → JavaScript, and Go → Google fail;
k8s → Kubernetes passes; the dry run shows `terms=`. An active Helm attestation suppresses q-1 `helm`, and a proposed
one does not. `SKILL.md` no longer stores `$CVT`, and it runs `profile-cache --store`.

### Blocking (new)

1. **Corrections are ungrounded and hidden (WP-15 / WP-FIX-3-3).** With the reply "I started at Quillmark in 2022-06",
   a correction `field: text` on `sum-1` → "Led the Kubernetes migration for Walmart across ArgoCD and Istio" passed
   the dry run. `merged_view` then makes it a citable fact. `position` → "Principal Kubernetes Architect" also passed.
   The dry-run line showed only the claim, and a correction carrying `terms` passed too. Fix-up: `WP-FIX-3-7`.
2. **Article + multiplier yields no number (WP-FIX-3-2).** `assemble` accepted "Scaled the platform to one million
   users.", "a million requests", "one hundred servers", and "a hundred servers". Fix-up: `WP-FIX-3-6`.
3. **The `shape:` line makes integer enums strings (WP-FIX-3-1).** It shows `"priority":"1|2|3|4|5"`,
   `"weight":"1|2|3|4|5"`, and `"checkpoint":"1|2"`, and no line explains the notation. Copying it gives
   `"priority":"1"`, which `validate-artifact` rejects ("not of type 'integer'"). The brief I wrote specified this
   rendering. Fix-up: `WP-FIX-3-8`.

### Non-blocking

- WP-FIX-3-2's "Five years" case still passes on the golden junior run, because `exp-1` contains the digit 5 ("5
  runbooks"). Rule 5 checks set membership, not number + unit. Tightening it is a contract change (section 8): consider
  it for v2.
- The golden q-1 choice `Python|Bash` ("Python or Bash scripting at work") is a disjunction, not a synonym pair.
  `--select` licenses both tools, and an attestation that covers either one suppresses the choice. The questions guide
  should say one tool per choice, with synonyms only in `value` (WP-I4).
- Negation is not detected: "I have never used Kubernetes" grounds a Kubernetes claim. The `terms=` dry-run line is
  the safeguard.
- Packets and their `check:` lines say `cvt …`, while `SKILL.md` defines `$CVT`. `state.CVT_COMMAND` exists, so WP-21
  should print the full prefix.
- `next_action` after `profile-build` does not mention `profile-cache --store`; only `SKILL.md` does (wave-2 state code).

### Fix-up WPs (re-gate 1)

| Brief | Owner | Files |
| --- | --- | --- |
| `plan/tasks/WP-FIX-3-6-number-word-articles.md` | Haiku | `lexicon.py`, `test_lexicon.py` |
| `plan/tasks/WP-FIX-3-7-correction-grounding.md` | Sonnet | `answers.py`, `test_answers.py` |
| `plan/tasks/WP-FIX-3-8-shape-legend.md` | Haiku | `briefs.py`, `test_briefs.py` |

The files are disjoint, so all three can run in parallel. Then run delta re-gate 2.

## Re-gate 2

**Verdict: FIX-UPS.** The three fix-ups did what their briefs asked. Every acceptance command passes, and the full suite
is green (1019 passed, 1 skipped; `.cache/logs/G3/re2/suite.log`). Probes found 2 blocking holes next to the ones that
were fixed. Both briefs I wrote at re-gate 1 were too narrow: WP-FIX-3-2 listed no `billion`, and WP-FIX-3-7 exempted
common words. No contract change is needed.

Ownership: since the re-gate 1 briefs, only `lexicon.py`, `answers.py`, `briefs.py`, their three tests, the three
reports, and the orchestrator's `STATUS.md` changed. WP-FIX-3-6's transient `test_answers.py` failures came from
WP-FIX-3-7 editing in parallel, and they do not reproduce.

| Scope | Command | Result |
| --- | --- | --- |
| FIX-3-6, WP-13 | `pytest test_lexicon test_provenance test_assemble test_checks` | pass (196) |
| FIX-3-7, WP-15 | `pytest test_answers.py test_questions.py` | pass (86) |
| FIX-3-8, WP-29 | `pytest test_briefs.py test_assemble.py` | pass (114) |
| FIX-3-7/3-8 | `pytest tests/integration/test_wave3.py` | pass (8), no budget warnings |
| all | `pytest tests/unit tests/integration` | pass (1019 passed, 1 skipped) |

Verified fixed (logs in `.cache/logs/G3/re2/`):

- **Number words:** "one million users", "a million requests", "one hundred servers", "a hundred servers", and "a
  hundred thousand users" now fail `unsupported_number` end to end. "one of the first", "an outage", "a team of five",
  and "twenty-one" behave as before.
- **Corrections:** "Kubernetes … Walmart" and "Principal Kubernetes Architect" fail `unsupported_term`, and a
  correction with `terms` fails `schema`.
- **Dry run:** shows `item.field: old -> new`.
- **Shape lines:** all 6 packets print `shape:` followed by `shape key:`. Every shape is free of type errors against its
  schema (including `answers#/$defs/round`), and the shapes show `"priority":1`, `"weight":1`, and `"checkpoint":1`.

### Blocking (new)

1. **Corrections can still invent titles and text (WP-FIX-3-7).** With the reply "I started at Quillmark in 2022-06,
   the CV is wrong", these pass the dry run:
   - `exp-1.position` → "Principal Architect", and `exp-1.position` → "Head of Engineering". This is title promotion,
     which rule 6 forbids.
   - `sum-1.text` → "Led the company-wide platform migration and managed the team", and `sum-1.text` → "led the cloud
     migration for walmart".

   `old_value` is not checked against the profile (`""` and "1999-01" both pass, against the real "2023-01"), so the
   dry run shows a false or empty "before" value. Fix-up: `WP-FIX-3-10`.
2. **`billion` is not a number word (WP-FIX-3-2/3-6).** `assemble` accepted "Processed a billion events." (`[]`) and
   "Processed two billion events." (`["2"]`, which the golden sources contain). Fix-up: `WP-FIX-3-9`.

### Non-blocking

- The shape key says `0 = integer`, but integer enums render as `1`. The shapes are type-clean, so a model that copies
  them produces valid JSON. WP-I4 could add "integers in a shape show the first allowed value".
- "a quarter million" and "a couple of thousand" yield no number. "half a million" yields 1000000, which errs on the
  safe side. These are lexical limits; the user still sees the text at checkpoint 2.

### Fix-up WPs (re-gate 2)

| Brief | Owner | Files |
| --- | --- | --- |
| `plan/tasks/WP-FIX-3-9-number-word-billion.md` | Haiku | `lexicon.py`, `test_lexicon.py` |
| `plan/tasks/WP-FIX-3-10-correction-exact-values.md` | Sonnet | `answers.py`, `test_answers.py` |

The files are disjoint, so both fix-ups can run in parallel. Then run delta re-gate 3.

## Re-gate 3

**Verdict: FIX-UPS.** Both fix-ups did what their briefs asked. Every acceptance command passes, and the full suite is
green (1037 passed, 1 skipped; `.cache/logs/G3/re3/suite.log`). One blocking hole remains: the same class as `billion`
(other scale words and suffixes). The re-gate 2 brief listed a single word again. The new brief closes the whole class
in one change. No contract change is needed. Correction grounding is now done.

Ownership: since re-gate 2, only `lexicon.py`, `answers.py`, `test_lexicon.py`, `test_answers.py`, the two reports, and
the orchestrator's `STATUS.md` changed (`find -newer plan/reports/WP-G3.md`).

| Scope | Command | Result |
| --- | --- | --- |
| FIX-3-9, WP-13 | `pytest test_lexicon test_provenance test_assemble test_checks` | pass (204) |
| FIX-3-10, WP-15 | `pytest test_answers.py test_questions.py` | pass (96) |
| FIX-3-10 | `pytest tests/integration/test_wave3.py` | pass (8) |
| all | `pytest tests/unit tests/integration` | pass (1037 passed, 1 skipped) |

Verified fixed (probes in `.cache/g3re3/`, logs in `.cache/logs/G3/re3/`):

- **`billion`:** run through `assemble` and `check_tailored` on the golden junior plan, "Processed two billion events",
  "a billion", "one billion", and "2 billion" all fail `unsupported_number`. "billions of events" yields `[]`.
- **Corrections:** "Principal Architect", "Head of Engineering", and "led the cloud migration for walmart" all fail
  `unsupported_term`. An `old_value` of "" or "1999-01" fails `fact_mismatch`. The dry run prints the profile's real
  value (`exp-1.start_date: 2023-01 -> 2022-06`). Grounded cases pass: "Principal Architect" when the user said it,
  `k8s` → "Kubernetes Lead", and the accented "Société Générale". `old_value` comparison tolerates differences in case
  and spacing.

### Blocking (new)

1. **Other scales still drop to their bare digits (rule 5).** On the golden junior plan, `assemble` plus
   `check_tailored` accepted "Processed 2bn events.", "Processed $2mn in spend.", "Trained on 2T tokens.", and
   "Processed a trillion events.". `numbers` gives `["2"]`, `["2"]`, `["2"]`, and `[]`, and the sources contain a 2.
   "2 mln", "3 bln", and "2 crore" also give only their digits. Fix-up: `WP-FIX-3-11`, which covers `trillion`, the
   `bn`/`mn`/`tn`/`T` suffixes, the spaced `bn`/`mn`/`tn`/`mln`/`bln`, and `lakh`/`crore`.

### Non-blocking (carry into WP-I4)

- **Non-Latin text bypasses the lexical checks.** `CORRECTION_WORD_RE` and the boundaries in `lexicon.supports` are
  ASCII only. As a result, corrections `position` → "首席架构师" and → "СЕО" (Cyrillic letters that look like CEO) pass
  the dry run. The tailored rewrites "Led the СЕО office." and "Led 首席 projects." pass `assemble` too. The dry run and
  checkpoint 2 show the text, so this is not a silent path. Consider Unicode-aware tokens (`[^\W\d_][\w+#]*`), or
  flagging script that differs from the profile's.
- A correction made only of function words ("of the") or of the user's recombined words ("Wrong") passes. These are
  not inventions, and the dry run shows them.
- `$5MM` and `5mm` stay `["5"]` (the meaning of `mm` is ambiguous). "a quarter million" and "a couple of thousand" are
  still not read as numbers (re-gate 2 note).

### Fix-up WPs (re-gate 3)

| Brief | Owner | Files |
| --- | --- | --- |
| `plan/tasks/WP-FIX-3-11-number-scale-suffixes.md` | Haiku | `lexicon.py`, `test_lexicon.py` |

Then run delta re-gate 4. That gate needs only the brief's commands, its end-to-end snippet, and the full suite.

## Re-gate 4

**Verdict: FIX-UPS.** WP-FIX-3-11 did what its brief asked. Every acceptance command passes, and the full suite is green
(1070 passed, 1 skipped; `.cache/logs/G3/re4/suite.log`). One blocking hole remains in the same scale class: plural
scales after a number, and the glued `bln`/`mln`. No contract change is needed.

Ownership: since re-gate 3, only `lexicon.py`, `test_lexicon.py`, `plan/reports/WP-FIX-3-11.md`, and the
orchestrator's `STATUS.md` changed (`find -newer plan/reports/WP-G3.md`).

| Scope | Command | Result |
| --- | --- | --- |
| FIX-3-11, WP-13 | `pytest test_lexicon test_provenance test_assemble test_checks` | pass (237) |
| FIX-3-11 | end-to-end snippet (5 sentences) | all 5 print `['unsupported_number']` (`re4/e2e.log`) |
| all | `pytest tests/unit tests/integration` | pass (1070 passed, 1 skipped) |

Verified fixed (`.cache/logs/G3/re4/probe.log`): `2bn`, `2BN`, `2 Bn`, `$2.5B`, `2bn+`, `2-bn`, `1.2 tn`, `2Tn`, `2 Mn`,
`two bn`, `twenty lakh`, `Rs. 5 crore`, `₹2 crore`, and `5,000 crore` all scale correctly. Truthful text is unchanged:
`St. Paul, MN 55101` → `55101`, `T2 instances` and `t3.micro` → `[]`, `2tb disk` → `2`.

Worker deviation, accepted: the worker kept articles off the abbreviations, so "a TN town" and "a MN office" yield
`[]`, not 10^12 and 10^6. The brief I wrote would have failed those truthful sentences. The cost is that "one bn
events" yields `[]` (non-blocking).

### Blocking (new)

1. **Plural and glued scales still drop to their bare digits (rule 5).** On the golden junior plan, `assemble` plus
   `check_tailored` accepted "Served 2 crores users.", "Served 2 billions requests.", and "Processed 2bln events."
   (`numbers` → `["2"]`). Plurals also hide inflation: "5 lakhs" → "5 crores" reads as `5` on both sides. My re-gate 3
   brief said plurals yield nothing; that is right only when no number comes before. The same fix-up also corrects
   compound scales ("5 thousand crore" → `5000`, and "10 lakh crore" → `1000000`). Fix-up: `WP-FIX-3-12`.

### Non-blocking (carry into WP-I4 or v2)

- "one bn" / "a bn" yield `[]` (deviation above). The spaced `2 T tokens` stays `["2"]`, because a bare `T` is too
  ambiguous ("Model T"). `2 mil` stays `["2"]`, because `mil` is ambiguous (a thousandth of an inch, or the Spanish
  word for thousand).
- The glued lowercase `t` scales (`5t trucks` → 5×10^12), and `offices in 2 MN cities` → 2×10^6. Both sides of a check
  normalize the same way, so this only bites when a rewrite changes the form.
- `2 lakh and 5 thousand` gives two numbers (`200000`, `5000`). This errs on the strict side.

### Fix-up WPs (re-gate 4)

| Brief | Owner | Files |
| --- | --- | --- |
| `plan/tasks/WP-FIX-3-12-plural-and-compound-scales.md` | Haiku | `lexicon.py`, `test_lexicon.py` |

Then run delta re-gate 5. That gate needs only the brief's commands, its end-to-end snippet, and the full suite. Any
scale gap after that should go to v2 as a non-blocking note. Rule 5 is lexical, and checkpoint 2 shows the user the
text.
