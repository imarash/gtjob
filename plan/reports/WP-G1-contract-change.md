# WP-G1 contract-change proposal

Status: **PROPOSED. Apply only after the user agrees.** After it is applied, dispatch
`plan/tasks/WP-FIX-1-3-sync-contract-change.md`.

Two changes. Neither changes a schema's structure, a field, an exit code, or a stage transition.

## C1. Remove the sample candidate's PII from the contracts (blocking)

The real candidate's name and email appear in three schema description strings. `assets/schemas/` must be
byte-identical to `plan/contracts/*.schema.json` (WP-01 acceptance, WP-I1 test), so the PII is copied into the
skill folder, and from there into `dist/tailoring-cvs.zip`. WP-I5's package PII grep would then fail. The examples
are replaced with the invented person from `tests/fixtures/render/senior-render.json`.

```diff
--- plan/contracts/profile.schema.json  (line 11)
-    "person_slug": { "type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$", "description": "Lowercase hyphenated full name, e.g. arash-morattab." },
+    "person_slug": { "type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$", "description": "Lowercase hyphenated full name, e.g. alex-chen." },
--- plan/contracts/render-model.schema.json  (line 16)
-        "title": { "type": "string", "description": "PDF title, e.g. 'Arash Morattab — CV — Staff Platform & Reliability Engineer'." },
+        "title": { "type": "string", "description": "PDF title, e.g. 'Alex Chen — CV — Staff Platform & Reliability Engineer'." },
--- plan/contracts/render-model.schema.json  (line 53)
-              "text": { "type": "string", "description": "Display text, e.g. 'me@arashmor.com'." },
+              "text": { "type": "string", "description": "Display text, e.g. 'alex.chen@example.com'." },
--- plan/contracts/interfaces.md  (line 147; not shipped in the package, changed for consistency)
-(for example `final/Arash-Morattab-Staff-Platform-Reliability-Engineer.pdf`); the company is
+(for example `final/Alex-Chen-Staff-Platform-Reliability-Engineer.pdf`); the company is
```

Out of scope, for the user to decide: `plan/PLAN.md`, the WP briefs, `tests/conftest.py` (the default private CV
path), and the PII-marker strings in `tests/unit/test_refs_*.py` also contain the surname. `plan/` is already
committed. None of these ship in the skill package.

## C2. Define the critic visual flags (WP-I1 escalation)

**Decision:** keep both names, because they are two different surfaces. Define each one where it belongs.

- `cvt brief critic RUN --visual` is the IDE/agent packet flag (section 13 already uses this name). It belongs
  in section 3's `brief` row, which today defines no critic flag.
- `gtjob tailor --critic-visual` is the CLI flag. It sits next to `--critic` (section 14.6, PLAN Q16, WP-21, and WP-22
  already use this name). It belongs in section 12's `gtjob tailor` row, which today lists only `--critic`.

Renaming either one would touch more files (critic-rubric, test_refs_writing, WP-21, WP-22) for no gain.

```diff
--- plan/contracts/interfaces.md  section 3, `brief` row, Arguments cell
-... `--full` (append the guide's Details and Examples); `--item ID` (expand one item) | run artifacts, ...
+... `--full` (append the guide's Details and Examples); `--item ID` (expand one item); `--visual` (critic only: the packet also lists the `pages/page-N.png` files to attach, rendered at 80 ppi) | run artifacts, ...
--- plan/contracts/interfaces.md  section 12, `gtjob tailor` row
-... `--draft`; `--critic`; `--slug`; ...
+... `--draft`; `--critic`; `--critic-visual` (implies `--critic`; same as `cvt brief critic --visual`, section 14.6); `--slug`; ...
--- plan/contracts/interfaces.md  section 13, `critic` row
-| tailored outline + JD digest + validation summary (text only; PNGs only with `--visual`) |
+| tailored outline + JD digest + validation summary (text only; PNGs only with `cvt brief critic --visual` / `gtjob tailor --critic-visual`) |
--- plan/contracts/interfaces.md  section 14.6, `critic` row
-| `critic` (opt-in) | `claude-opus-5-5`, text only | `--critic-visual` adds page PNGs at 80 ppi |
+| `critic` (opt-in) | `claude-opus-5-5`, text only | `gtjob tailor --critic-visual` (= `cvt brief critic --visual`) adds page PNGs at 80 ppi |
```

Worker-side consequence: none for wave 1 code. `critic-rubric.md` and `test_refs_writing.py` already use
`--visual`. WP-FIX-1-3 removes the `UNDOCUMENTED_FLAGS` allowlist entry in `tests/integration/test_wave1.py`. WP-29
(`brief`) and WP-21/WP-22 (`gtjob`) implement the flags as defined above.
