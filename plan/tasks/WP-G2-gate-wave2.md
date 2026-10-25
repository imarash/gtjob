# WP-G2: Gate for wave 2

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 2 (after WP-I2) | WP-08…WP-13, WP-I2 | Opus (`cv-reviewer`, read-only) | M-L |

Follow `plan/tasks/_GATE.md`. Your report goes to `plan/reports/WP-G2.md`.

**WPs in this wave:** WP-08, WP-09, WP-10, WP-11, WP-12, WP-13, WP-I2.

**Focus:**

1. **Provenance validator** (the core truthfulness guarantee). Probe it yourself on a copy of the junior golden
   tailored file, in a temp `GTJOB_HOME`. Introduce each of these and confirm exit 1 with the section 8 message
   format:
   - An unsupported tool.
   - An unsupported number.
   - A changed date.
   - A citation of a revoked attestation.
   - An SLO bullet cited outside the scope of its attestation.
   - A logistics line.

   Also confirm that synonyms (`k8s`/Kubernetes) are accepted and that plurals and possessives are tolerated.
2. **Ingest on the real sample** (if present): reading order keeps the employer and dates together, headers are
   deduplicated, and the email is kept once.
3. **Scope resolution:** `role_label: SRE` resolves to exactly `exp-2.e4` and `exp-2.e5` on the sample profile (if
   private goldens are absent, use the WP-11 synthetic test). An ambiguous label yields `unresolved`, never a
   guess.
4. **Render safety:**
   - Templates read only `json(sys.inputs.data)`. There is no `eval`, and no string interpolation into Typst
     source.
   - Markup-like CV text renders literally.
   - PDF metadata (title and author) is set.
   - Fonts are embedded.
5. **The attestation store:** status transitions, `next_seq` monotonic, and atomic writes.
6. **`profile-build` (token efficiency + truthfulness):** on a copy of the junior map, shift a range by one line, drop a
   line, and type an employer name that is not in its cited lines. Each must fail with the right code. Confirm `cv.txt`
   line numbering is identical across two `ingest` runs of the same input.

Look at the rendered junior PNG (`.cache/test-artifacts/render/`) and comment on visual quality.
