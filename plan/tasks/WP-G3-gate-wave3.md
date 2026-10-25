# WP-G3: Gate for wave 3

| Wave | Depends on | Owner model | Effort |
| --- | --- | --- | --- |
| 3 (after WP-I3) | WP-14…WP-19, WP-29, WP-I3 | Opus (`cv-reviewer`, read-only) | L |

Follow `plan/tasks/_GATE.md`. Your report goes to `plan/reports/WP-G3.md`.

**WPs in this wave:** WP-14, WP-15, WP-16, WP-17, WP-18, WP-19, WP-29, WP-I3.

**Focus:**

1. **The skill as a product:** read `SKILL.md` as a host agent would, start to finish.
   - Could an agent with no other context run a full tailoring session and resume it a day later from a plain
     reply?
   - Check the Agent Skills authoring rules: description quality and trigger phrases, body < 500 lines, references
     one level deep, scripts executed rather than read, and no host-only placeholders.
   - The wrappers are one paragraph each.
   - `cv-critic` is read-only on both hosts.
2. **Checkpoint protocol:**
   - Questions are capped and suppressed by existing attestations.
   - The dry run shows the mapping before any write.
   - Unmentioned questions go to defaults with a single "not added" note.
   - Ambiguous scope triggers `confirm_scope`.
   - Follow-ups are limited to one round.
   - Host formats respect ≤ 4 questions and ≤ 4 options.
3. **Page fit:**
   - Monotone (no oscillation): dropping is ordered and never removes priority-1 content before the density floor.
   - `underfilled` is reported.
   - The junior run lands on 1 page and the render fixture lands on 2 pages.
4. **Checkpoint 2:**
   - The diff shows before and after, with refs.
   - Edits are validated as a batch, and regression rules invalidate downstream artifacts.
   - `approve` activates exactly the attestations cited.
5. **Report:** recruiter asks appear only in the report, gaps are stated honestly, and the injection notice is
   present.
6. **Visuals:** inspect the `modern` and `classic` PNGs at `.cache/test-artifacts/render/` against Jake's Resume
   and Awesome-CV quality: hierarchy, whitespace, alignment, consistency.
7. **Token efficiency:**
   - Print every `cvt brief` packet for the junior run and read them as the model would: is each one sufficient on
     its own (no need to open other files), within budget, and free of duplicated rules?
   - Spot-check that `SKILL.md` never tells the agent to Read raw artifacts or references in the happy path.
   - Check that `assemble` copies facts rather than trusting the plan: mutate a `keep` bullet's text and a `rewrite`
     that names a new client; both must fail.
