# WP-13: Lexicon, provenance validator, `jd-check`, `match-check`, `check-tailored`

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 | WP-01 (uses WP-04 fixtures) | Sonnet (`cv-builder`) | L |

## Goal

Enforce truthfulness in code. Build the term and number lexicon, the provenance validator (rules 1-10),
the logistics-leak and placeholder checks, and the three check commands that gate the AI-written
`jd.json`, `match.json`, and `tailored.json`.

## Context

- Read `plan/tasks/_COMMON.md`.
- Contracts: interfaces.md section 8, which is **normative**: implement every rule and the exact message
  format. Also section 3 (`jd-check`, `match-check`, `check-tailored` rows), section 5 (WP-13 block, implemented
  here), section 10 (gate names), `validation.schema.json` (violation codes), `tailored.schema.json`,
  `match.schema.json`, `jd.schema.json`, and `attestations.schema.json`.
- In this wave, do not import WP-10's `profile.py` or WP-11's `attestations.py`. Implement local helpers:
  - `_item_text(profile, ref)`: the same semantics as interfaces.md section 8. Engagement and work refs include
    all descendant highlight texts, names, role label, and dates.
  - `_merged(profile, atts)`: apply active corrections.
  - `_usable(atts, run_id, include_proposed)`.

  Name them with a leading underscore, plus the comment `# TODO(I-2): switch to cvtlib.profile / cvtlib.attestations`.
  The wave-2 integration WP swaps them.
- Lexicon design: `find_terms(text)` returns the claim-bearing tokens. A term found in sources passes.
  Common English words never count as terms. Candidates are:
  1. Longest-first matches of `tech-terms.txt` entries, case-insensitive, on word boundaries, covering
     multiword terms ("service mesh", "error budget", "SOC 2", "incident response").
  2. Acronyms (2+ capitals or digits: `EKS`, `IAM`, `PCI`).
  3. CamelCase / InnerCaps tokens (`TypeScript`, `GitOps`, `OpenShift`).
  4. Capitalized words not at sentence start that are not in `common-words.txt` (proper nouns such as
     `Linkerd`, `Dynatrace`, client names).
  - Synonym classes (`synonyms.json`) are true equivalences only: `["Kubernetes","k8s"]`,
    `["CI/CD","CICD","continuous integration and delivery"]`, `["IaC","infrastructure as code","IaaC"]`,
    `["SLO","service level objective"]`, `["GCP","Google Cloud","Google Cloud Platform"]`,
    `["AWS","Amazon Web Services"]`, `["Red Hat","Redhat"]`, `["OpenShift","Openshift"]`. Never hypernyms.
    EKS and Kubernetes are not synonyms.
  - `numbers(text)`: integers, decimals, and percentages, normalized (`800+` → `800`, `8-member` → `8`,
    `99.99%` → `99.99`, `5,000` → `5000`, `5k` → `5000`).

## Owned files

- `.claude/skills/tailoring-cvs/assets/lexicon/tech-terms.txt` (≥ 400 entries covering cloud, containers, IaC,
  CI/CD, observability, SRE practices, security/compliance (SOC 2, PCI DSS, ISO 27001, HIPAA, FedRAMP), languages,
  data, AI/LLM tooling (Claude Code, Cursor, Copilot, MCP, RAG, vLLM), frontend, and claim phrases such as
  "startup", "early-stage", "on-call", "error budget", "SLO", "SLA", "SLI", "incident commander", "team lead")
- `.claude/skills/tailoring-cvs/assets/lexicon/synonyms.json`
- `.claude/skills/tailoring-cvs/assets/lexicon/common-words.txt` (about 3000 common English words, plus resume verbs
  such as Led, Designed, Built, Owned, Drove)
- `.claude/skills/tailoring-cvs/assets/lexicon/logistics-patterns.json` (`[{kind, regex}]` for salary/$ ranges,
  "base + equity", visa, sponsorship, work authorization, relocation, onsite N days, recruiter email address
  patterns)
- `.claude/skills/tailoring-cvs/scripts/cvtlib/lexicon.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/provenance.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/checks.py`
- `.claude/skills/tailoring-cvs/scripts/cvtlib/commands/checks.py` (`jd-check`, `match-check`, `check-tailored`)
- `tests/unit/test_lexicon.py`, `tests/unit/test_provenance.py`, `tests/unit/test_checks.py`
- `tests/fixtures/provenance/` (mutated copies of junior golden files for negative tests)
- `plan/reports/WP-13.md`

## Steps

1. Write the lexicon files and `lexicon.py`. Load them once, with `functools.cache`. `supports(term, source)` is
   case-insensitive, tolerant of singular/plural (`s`/`es`) and possessives, synonym-aware, and matches on word
   boundaries for alphanumerics.
2. `provenance.check_tailored(...)`: implement rules 1-7 and 10 from interfaces.md section 8, plus `find_placeholders`
   (rule 8) and `check_logistics` (rule 9). Messages follow the exact format. Return violations sorted by
   `item_id`.
3. `checks.check_jd` covers:
   - The SHA matches `state.inputs.jd.sha256`.
   - Requirement IDs are unique and sequential.
   - Every `keywords[].req_ids` entry exists.
   - At least one `must`.
   - `noise` texts are substrings of `jd.txt`.
   - `company` is non-empty only if it appears in `jd.txt`.
4. `checks.check_match`:
   - Each jd requirement appears exactly once.
   - Refs exist (profile IDs or usable attestations).
   - Each quote is a substring of `comparable(item_text)`, or of the attestation claim/terms.
   - `strength: none` has no evidence.
   - Recompute `coverage`.
   - `metric_opportunities` items exist and number 0-5.
5. Commands:
   - `jd-check RUN` → normalize, write back, record, stage `jd_analyzed`.
   - `match-check RUN` → write the recomputed coverage, record, stage `matched`.
   - `check-tailored RUN [--draft]`:
     - Schema-validate, then renumber `t-` IDs canonically by position (keeping `source_refs`).
     - Increment `version` if the content changed since the last history snapshot, and write
       `tailored.history/v<N>.json`.
     - Run the provenance, placeholder, logistics, and attestation-status checks.
     - Write `validation.json` with the gates `schema`, `provenance`, `placeholders`, `logistics_leak`, and
       `attestation_status`. The other gates are `skipped`, with detail "post-render".
     - Exit 1 on any fail. Stage → `tailored` when passed and the current stage is `answers_applied`.
6. Tests:
   - Every rule has a positive and a negative test, using `tests/fixtures/provenance/` mutations of the junior
     golden. Mutations:
     - Add "Linkerd" to a bullet.
     - Change a number.
     - Cite an attestation outside its scope.
     - Cite a skills-only attestation from a bullet.
     - Change an employer date.
     - Add an uncited skill.
     - Add "$240,000" to the summary.
     - Leave a placeholder.
     - Cite a revoked attestation.
   - The exact-message test: `bullet t-exp-1.b2 mentions 'Linkerd'; not found in refs [exp-1.b2]` (adjust the IDs to
     your fixture, but keep the format).
   - `numbers()` normalization cases.
   - Synonym and hypernym cases: k8s passes for Kubernetes; EKS does not pass from a "Kubernetes" source.
   - `jd-check` and `match-check` on the junior goldens, both pass and tampered.

## Token-efficiency requirements (interfaces.md section 14)

- `match-check` fills empty evidence `quote` values. The quote is the sentence of the ref's text containing the
  first matched keyword or synonym, or the first 120 characters, truncated at a word boundary. A non-empty quote
  must still be a substring of the ref text.
- `check-tailored` is unchanged, but its violation output is capped (section 4).
- Every violation message names the item ID first, so `cvt brief fix` (WP-29) can select only the offending items
  by parsing `item_id`.
- The lexicon must stay small enough to load fast. It is never printed into packets.

## Acceptance criteria

```bash
uv run pytest -q tests/unit/test_lexicon.py tests/unit/test_provenance.py tests/unit/test_checks.py   # passes
wc -l .claude/skills/tailoring-cvs/assets/lexicon/tech-terms.txt   # >= 400
```

## Definition of done

The common definition of done. Every rule in interfaces.md section 8 maps to at least one test, listed in the
report as a rule → test table.

## Escalation

If a contract seems wrong, stop and report it in `plan/reports/WP-13.md` under `## ESCALATION`. Do not change it.
