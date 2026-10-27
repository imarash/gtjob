# Build status (maintained by the orchestrator)

Status values: TODO, RUNNING, DONE, PARTIAL, ESCALATED, FIX-UP. Waves: TODO, IN PROGRESS, APPROVED.

| Wave | State | Gate verdict | Fix-up rounds | Commit | Build tokens (approx.) |
| --- | --- | --- | --- | --- | --- |
| 1 | APPROVED | APPROVE (re-gate 2) | 2 | bdbdb19 | |
| 2 | APPROVED | APPROVE (re-gate 3) | 3 | 73a6a31 | |
| 3 | APPROVED | ACCEPTED by user after re-gate 4 (known limit: plural/glued scale words; FIX-3-12 not run) | 4 | 51727b5 | |
| 4 | APPROVED | APPROVE (re-gate 1) | 1 | 10ea6b7 | |
| 5 | APPROVED (pending live evals + host checklist) | APPROVE (re-gate 2) | 2 | | |
| 6 (optional) | TODO | | | | |

| WP | Wave | Status | Note |
| --- | --- | --- | --- |
| WP-01 | 1 | DONE | 6/6 acceptance, 207 unit tests |
| WP-02 | 1 | DONE | finished by cv-builder after lite run was interrupted; Semibold is its own Typst family (select by name, not weight) |
| WP-03 | 1 | DONE | 4 JDs, checkpoint fixtures, triggers |
| WP-04 | 1 | DONE | Jamie Rivera CV + 9 golden artifacts |
| WP-05 | 1 | DONE | style-guide, truthfulness, critic-rubric |
| WP-06 | 1 | DONE | profile/jd/match stage guides |
| WP-07 | 1 | DONE | questions/answers/tailor/change stage guides |
| WP-I1 | 1 | DONE | lite; 270 tests pass; flagged --visual vs --critic-visual naming gap for gate |
| WP-G1 | 1 | DONE | APPROVE after 2 fix-up rounds |
| WP-08 | 2 | DONE | init/status commands |
| WP-09 | 2 | DONE | ingest (cv.txt, jd.txt) |
| WP-10 | 2 | DONE | profile tools |
| WP-11 | 2 | DONE | attestations, scope, attest |
| WP-12 | 2 | DONE | modern render; 3 unit failures belong to other WPs (for WP-I2) |
| WP-13 | 2 | DONE | 126 tests; flags for I2: skills keyword join (comma vs space) vs WP-10 item_text; test_state host=cursor failures (env) |
| WP-I2 | 2 | DONE | 573 pass; 2 test_state failures only inside Cursor (CURSOR_* host detection; conftest fix not owned by WP) |
| WP-G2 | 2 | DONE | APPROVE (re-gate 3) after 3 fix-up rounds; C1+C2+C3 applied |
| WP-14 | 3 | DONE | 33 fit/validate tests; unit 661 pass; undated drop-order tie-break |
| WP-15 | 3 | DONE | questions + answers-apply; 69 tests; unit 779 pass |
| WP-16 | 3 | DONE | diff, apply-edits, approve; 49 tests; unit 710 pass |
| WP-17 | 3 | DONE | classic.typ; sidebar skipped; unit 570 pass |
| WP-18 | 3 | DONE | SKILL.md, wrappers, cv-critic, lint/package; 4/4 acceptance |
| WP-19 | 3 | DONE | report + critique-save; 23 tests; unit 628 pass |
| WP-29 | 3 | DONE | brief + assemble; 92 tests; golden tailor-plan assembles |
| WP-I3 | 3 | DONE | 949 pass, 1 skipped; lint-skill --all exit 0 |
| WP-G3 | 3 | DONE | accepted by user after 4 fix-up rounds (FIX-3-1..3-11); FIX-3-12 deferred as non-blocking |
| WP-20 | 4 | DONE | sample golden A+B; 5/5; flags: question cap order, interaction-cases correction/skip, seed offer, 2 packets over budget |
| WP-21 | 4 | DONE | AI layer + fake client; 1035 pass; live skipped; answer_parse needs stage awaiting_answers (WP-22) |
| WP-22 | 4 | DONE | gtjob CLI, 7 commands; 1107 pass; ApiRunner not run live; README gtjob note to remove |
| WP-23 | 4 | DONE | evals harness; 35 non-live pass, 13 live skipped; I4 to confirm config factory name + run_stage return |
| WP-24 | 4 | DONE | lite; README + docs; gtjob examples marked "not yet available" until WP-22 |
| WP-I4 | 4 | DONE | 1197 pass; questions.py cap now per round (confirm at gate); GTJOB_FAKE_LLM hook; 5 guide items deferred |
| WP-G4 | 4 | DONE | APPROVE after 1 fix-up round (FIX-4-1..4-6; contract change applied) |
| WP-25 | 5 | DONE (xfails resolved by FIX-5-1/5-2) | 70 e2e pass + 2 strict xfails (answer_parse packet ~3067 vs 2500 budget; suppressed gap name left in question prompt); fixtures vs contract mismatch on correction/skip; next_action empty on exit 6/dry-run; rule 9 scan gap. Escalations left to gate |
| WP-26 | 5 | DONE | 11 offline CLI tests pass; cross-host resume; use `uv run --no-sync` in sandbox |
| WP-I5 | 5 | DONE | 1284 pass; lint ok; package clean |
| WP-G5 | 5 | DONE | APPROVE after 2 fix-up rounds (FIX-5-1..5-6); gates 6 (live evals, needs ANTHROPIC_API_KEY) and 7 (host checklist) pending user |
| WP-27 | 6 | TODO | optional |
| WP-28 | 6 | TODO | optional |
| WP-G6 | 6 | TODO | optional |

## Log

- 2026-10-23: plan written (contracts, 39 briefs, agents). Waiting for wave 1 kickoff.
- 2026-10-23: token-efficiency redesign: WP-29 added (40 briefs), `cv-builder-lite` agent, delta re-gates.
- 2026-10-25: wave 1 build dispatched; session interrupted. WP-01,03-07 DONE; WP-02 PARTIAL, re-dispatching to cv-builder.
- 2026-10-25: WP-02 DONE (3/3 acceptance, tests/unit 217 pass). Next: WP-I1, then WP-G1.
- 2026-10-25: WP-I1 DONE (270 pass). Escalation for gate: critic visual flag name (--visual in s13 vs --critic-visual in s14.6). Next: WP-G1.
- 2026-10-25: WP-G1 FIX-UPS (round 1). User approved WP-G1-contract-change (C1 PII removal, C2 critic flag names); applied to plan/contracts/. Dispatched FIX-1-1, FIX-1-2; FIX-1-3 next.
- 2026-10-25: FIX-1-1 DONE (286 pass), FIX-1-2 DONE (278 pass). Dispatched FIX-1-3.
- 2026-10-25: FIX-1-3 DONE (286 pass). Dispatching delta re-gate 1.
- 2026-10-25: Re-gate 1 FIX-UPS (round 2 pending): UNDOCUMENTED_FLAGS allowlist not actually removed. Dispatched FIX-1-4 (lite).
- 2026-10-25: FIX-1-4 DONE (allowlist verified empty on disk, 286 pass). Dispatching delta re-gate 2.
- 2026-10-25: WP-G1 APPROVE after 2 fix-up rounds (FIX-1-1..1-4; contract change C1+C2 applied). Committing wave 1.
- 2026-10-26: wave 2 dispatch of WP-08..13 hung (tool interrupted after ~77 min). WP-08..12 finished and wrote reports; WP-13 produced nothing. Re-dispatching WP-13 alone.
- 2026-10-26: WP-13 DONE on re-dispatch (background). Wave 2 build complete. Dispatching WP-I2.
- 2026-10-26: WP-I2 DONE. Dispatching WP-G2.
- 2026-10-26: WP-G2 FIX-UPS (round 1). 4 findings: host env isolation (2-1), PII in tests (2-2), cross-job provenance refs (2-3, needs C1), profile-build date/location checks (2-4, needs C2). Contract change proposal plan/reports/WP-G2-contract-change.md awaiting user. Dispatched 2-1 and 2-2.
- 2026-10-26: FIX-2-1 DONE (575 pass inside Cursor, 0 fail). FIX-2-2 still running; C1/C2 awaiting user.
- 2026-10-26: FIX-2-2 DONE (575 pass; real sample values moved to git-ignored tests/fixtures/private/sample-ingest.json). Residual PII-grep hits in 3 schemas + senior-render.json unchecked (likely surname literal) - for re-gate. Waiting on user for C1/C2, then FIX-2-3, FIX-2-4.
- 2026-10-26: user approved WP-G2 C1+C2; applied to plan/contracts/interfaces.md. Dispatching FIX-2-3, FIX-2-4.
- 2026-10-26: FIX-2-4 DONE (608 pass). Known limit: date check not positional (start 2020-12 passes vs 'Jan 2020 - Dec 2021'). FIX-2-3 running.
- 2026-10-26: FIX-2-3 DONE (608 pass). Dispatching delta re-gate 1.
- 2026-10-26: Re-gate 1 FIX-UPS (round 2 pending): integration __init__.py not restored (FIX-2-5, lite); profile-build accepts titles dropping Junior/Intern (FIX-2-6, needs contract change C3 awaiting user). Dispatching FIX-2-5.
- 2026-10-26: FIX-2-5 DONE (init restored, 608 pass). FIX-2-6 waiting on user approval of C3.
- 2026-10-26: user approved C3; applied to plan/contracts/interfaces.md. Dispatching FIX-2-6 (round 2).
- 2026-10-26: FIX-2-6 DONE (627 pass). Known limit: hyphenated suffix qualifiers (Founder-Intern) not caught. Dispatching delta re-gate 2.
- 2026-10-26: Re-gate 2 FIX-UPS: one blocker left (FIX-2-7 lite: trailing-hyphen qualifier, rstrip->strip). 2-round fix-up limit reached; stopped, awaiting user decision.
- 2026-10-26: Re-gate 2 FIX-UPS: one blocker left (FIX-2-7 lite: trailing-hyphen qualifier, rstrip->strip). 2-round fix-up limit reached; stopped, awaiting user decision.
- 2026-10-26: user allowed round 3. Dispatching FIX-2-7.
- 2026-10-26: FIX-2-7 DONE (630 pass). Dispatching delta re-gate 3.
- 2026-10-26: WP-G2 APPROVE after 3 fix-up rounds (FIX-2-1..2-7; contract changes C1+C2+C3 applied). Non-blocking: 'Engineer- Intern' (hyphen+space) missed; PII-grep residual hits in schemas/senior-render.json unchecked. Committing wave 2.
- 2026-10-26: wave 2 committed (73a6a31) and marked APPROVED. Next: wave 3.
- 2026-10-26: wave 3 dispatched (WP-14, WP-15, WP-16, WP-17, WP-18, WP-19, WP-29) to cv-builder in parallel.
- 2026-10-26: WP-14..19 and WP-29 all DONE. No PARTIAL. Dispatching WP-I3.
- 2026-10-26: WP-I3 DONE (949 pass, 1 skipped; lint-skill exit 0). Dispatching WP-G3.
- 2026-10-26: WP-G3 FIX-UPS (round 1). 5 blockers, no contract change. Dispatching FIX-3-1..3-5 in parallel. FIX-3-4 and FIX-3-5 are lite; claude-haiku-5-5 is not in this session's model list, so they run with inherit.
- 2026-10-26: FIX-3-1 DONE (packets show output shape; unit+integration 995 pass). FIX-3-2 DONE (number words; "Five years" still passes on junior golden because digit 5 exists). FIX-3-3 DONE (attestation terms grounded; 995 pass). FIX-3-5 DONE (zsh invocation + profile-cache --store). FIX-3-4 PARTIAL (lite; suite failed on another WP's test). Re-dispatching FIX-3-4 to cv-builder.
- 2026-10-26: FIX-3-4 DONE on cv-builder (995 pass, 1 skipped). Dispatching delta re-gate 1.
- 2026-10-26: Re-gate 1 FIX-UPS (round 2). 3 new blockers (correction grounding, number-word articles, shape legend). No contract change. Dispatching FIX-3-6 (lite/inherit), FIX-3-7 (cv-builder), FIX-3-8 (lite/inherit).
- 2026-10-26: FIX-3-6 DONE (a/an/one + multiplier; 1019 pass). FIX-3-7 DONE (correction grounding; 1019 pass). FIX-3-8 DONE (integer enums in shape; 1019 pass). Dispatching delta re-gate 2.
- 2026-10-26: Re-gate 2 FIX-UPS: two blockers left (FIX-3-9 billion as a number, lite; FIX-3-10 correction exact values, Sonnet). 2-round fix-up limit reached; stopped, awaiting user decision. No contract change.
- 2026-10-26: user allowed fix-up round 3 for WP-G3. Dispatching FIX-3-9 (lite/inherit) and FIX-3-10 (cv-builder).
- 2026-10-26: FIX-3-9 DONE (billion; 1027 pass). FIX-3-10 DONE (correction exact values; 1037 pass). Dispatching delta re-gate 3.
- 2026-10-26: Re-gate 3 FIX-UPS: one blocker (FIX-3-11 lite: 2bn/2mn/2T/trillion scale suffixes pass number check). Round 3 used; stopped, awaiting user decision. No contract change.
- 2026-10-26: user allowed round 4. Dispatching FIX-3-11 (lite/inherit).
- 2026-10-26: FIX-3-11 DONE (scale suffixes; 1070 pass). Dispatching delta re-gate 4.
- 2026-10-26: Re-gate 4 FIX-UPS: one blocker (FIX-3-12 lite: plural scale words "2 crores"/"2 billions", glued "2bln", stacked scales). Round 4 used; stopped, awaiting user decision. Gate recommends further scale-word gaps be non-blocking. No contract change.
- 2026-10-26: user accepted wave 3 with known limit (plural 'crores'/'billions', glued '2bln', stacked scales; FIX-3-12 deferred). 1070 pass. Committing wave 3.
- 2026-10-26: wave 3 committed (51727b5), APPROVED. Dispatching wave 4: WP-20 first, then WP-21, 22, 23, 24 (lite).
- 2026-10-26: WP-24 DONE (README + docs/privacy + docs/troubleshooting; gtjob CLI still stub pending WP-22; gate should drop "not yet available" note once WP-22 lands). Waiting on WP-20..23.
- 2026-10-26: WP-21 DONE (AI layer, fake client, cache, stage runners; 1035 pass; live test skipped, no API key). Note for WP-22/gate: answer_parse needs questions run first (awaiting_answers). Waiting on WP-20, WP-22, WP-23.
- 2026-10-26: WP-20 DONE (Parts A+B; 5/5 acceptance, 1035 pass; golden CV 2 pages, 9 gates pass + 1 warn). Flags for gate: 8-question cap vs follow-up order, interaction-cases.yaml correction/skip cases unmeetable, seed offer unconfirmed (score 0.1023 vs 0.6), profile and answer_parse packets over budget. Waiting on WP-22, WP-23.
- 2026-10-26: WP-22 DONE (gtjob CLI: tailor/continue/status/render/edit/profile/package-skill; 72 CLI tests, 1107 pass; not run live). Flags: ApiRunner untested live; questions/change_request use unchecked run_stage; default_rest needs followups: default. README "not yet available" note for gtjob should now be removed (gate). Waiting on WP-23.
- 2026-10-26: WP-23 DONE (evals harness; 35 non-live pass, 13 live skipped; no API key). Flags for I4: confirm stage_env factory name in gtjob.config and run_stage return value; --answers targets q-1. Wave 4 build complete. Dispatching WP-I4.
- 2026-10-26: WP-I4 DONE (1197 pass, 1 skipped; lint ok). I4 changed wave-3 questions.py: 8-question limit now per round (gate to confirm). GTJOB_FAKE_LLM hook added. 5 guide-feedback items (2,6,7,8,11) deferred to fix-up. ApiRunner never run live. Dispatching WP-G4.
- 2026-10-26: WP-G4 FIX-UPS (round 1). 5 blockers (FIX-4-1 live tests off by default, 4-2 untrusted wrapping, 4-3 judge gate status, 4-4 question cap initial batch, 4-5 output token caps). Optional contract-change proposal plan/reports/WP-G4-contract-change.md awaiting user. FIX-4-2 and 4-5 both edit test_briefs.py: run sequentially.
- 2026-10-26: user approved WP-G4 contract change; applied to plan/contracts/interfaces.md (14.4 output caps; section 7 cap wording). Dispatching FIX-4-1, 4-3, 4-4 (lite/inherit), FIX-4-2 (cv-builder) in parallel, then FIX-4-5 after 4-2.
- 2026-10-26: FIX-4-3 DONE (judge reads gate name/status; evals unit 36 pass). Waiting on FIX-4-1, 4-2, 4-4; FIX-4-5 after 4-2.
- 2026-10-26: FIX-4-1 DONE (addopts -m "not live"; 1197 pass, 1 deselected with fake key). Waiting on FIX-4-2, 4-4; FIX-4-5 after 4-2.
- 2026-10-26: FIX-4-4 ESCALATED (cap fix done, 3 new tests pass; tests/integration/test_wave4.py::test_pending_question_limit_is_per_round contradicts new rule, file owned by WP-I4). Orchestrator extended FIX-4-4 ownership to that one test (rewrite to new rule); re-dispatching same worker.
- 2026-10-26: FIX-4-4 DONE (old test rewritten; 1212 pass). Waiting on FIX-4-2; then FIX-4-5.
- 2026-10-26: FIX-4-2 DONE (untrusted_document wrapping for all CV/JD packet sections + CLI digest; 1212 pass). Dispatching FIX-4-5.
- 2026-10-26: FIX-4-5 PARTIAL->owned work DONE (caps raised; 141+36 pass) but 2 suite failures from user's uncommitted render.py edit (Experience -> Recent Experience). User confirmed intentional. Wrote WP-FIX-4-6 (tests/validator/docs follow the new title); dispatching lite/inherit.
- 2026-10-26: FIX-4-6 DONE (tests follow Recent Experience; 1214 pass). FIX-4-5 DONE. Round 1 fix-ups complete (4-1..4-6). Dispatching delta re-gate 1.
- 2026-10-26: WP-G4 APPROVE (re-gate 1). Non-blocking: 8-question cap dodgeable via fake parent_id; live evals and ApiRunner never run (no API key). Committing wave 4.
- 2026-10-26: wave 4 committed (10ea6b7) and marked APPROVED. Next: wave 5.
- 2026-10-26: WP-26 DONE. WP-25 PARTIAL (product-defect escalations outside its files, 2 strict xfails; not re-dispatched since remaining work is not in its ownership). Dispatching WP-I5.
- 2026-10-26: WP-G5 FIX-UPS round 1 (5-1..5-4) then round 2 (5-5, 5-6); re-gate 2 APPROVE (1349 pass, 0 xfail). Open for user: set .cursor/agents/cv-critic.md model to claude-opus-5-5-high, run live evals, run evals/HOST-CHECKLIST.md. Committing wave 5.
