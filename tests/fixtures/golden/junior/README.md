# Junior golden run (`golden-junior`)

Fully synthetic data for the invented person Jamie Rivera (`jamie-rivera`). Every file was
hand-authored to play the AI stages and is interlinked: IDs, refs and quotes agree across files.
Inputs live next to it: `../../cv/jamie-rivera-junior.txt` and `../../jds/junior-devops-engineer.md`.

| File | What it represents | Schema |
| --- | --- | --- |
| `profile-map.json` | Output of the profile stage: line ranges into the CV text (1-based). Every non-blank line is covered once or ignored. | `profile-map` |
| `profile.json` | What `cvt profile-build` must produce from the map: verbatim text, canonical IDs, `iss-1` (2-month date overlap, `origin: ai`). | `profile` |
| `jd.json` | JD analysis: `req-1..9` (6 must, 3 nice), keywords, posting boilerplate in `noise`. `jd_sha256` is the hash of the JD file. | `jd` |
| `match.json` | Requirement-to-evidence match. Helm (`req-6`) is `none`; Python/Bash (`req-5`) is `partial`; all quotes are verbatim. | `match` |
| `questions.json` | Three pending checkpoint-1 questions: gap multi-select (Helm, Python/Bash), metric, strategy (template). Each has a default. | `questions` |
| `answers.round.json` | Parsed reply "I used Helm at Brightfield to package two internal services": one `attest` item (skill, `skills_and_bullets`, scope `[exp-1]`). | `answers#/$defs/round` |
| `tailor-plan.json` | Output of the tailor stage: `keep` bullets (empty text), two `rewrite`, one `attested` bullet (`extra_refs: [att-001]`), skills with empty refs. | `tailor-plan` |
| `tailored.json` | What `cvt assemble` must produce from the plan: 1 page, `modern`, refs resolved, every `review: pending`, `att-001` is the ID the store would assign to the Helm attestation. | `tailored` |
| `edits-001.json` | Checkpoint-2 batch: `replace_text` (with refs), `reject` (restores the original Terraform bullet), `approve_all`. | `edits` |

`tailored.json.profile_sha256` is the SHA-256 of `profile.json` as committed; regenerate it if
`profile.json` changes. `tests/unit/test_junior_golden.py` checks all of the above.
