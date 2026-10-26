# WP-G2 contract-change proposal

Status: C1 and C2 **APPLIED (user agreed 2026-10-26).** After it is applied, dispatch
`plan/tasks/WP-FIX-2-3-provenance-parent-scope.md` (C1) and `plan/tasks/WP-FIX-2-4-profile-build-dates.md` (C2).

C3 (re-gate 1, at the end of this file): **APPLIED (user agreed 2026-10-26).** Implemented by
`plan/tasks/WP-FIX-2-6-profile-title-qualifiers.md`; the right-hand hyphen case is completed by WP-FIX-2-7.

Two changes, both found by adversarial probes at the gate. Neither changes a schema, a field, an exit code, a stage
transition, or a violation-code enum: both reuse codes already in `validation.schema.json` (`ref_out_of_scope`,
`not_verbatim`). Only `plan/contracts/interfaces.md` changes, and it is not copied into the skill package. The junior
golden fixtures already comply with both rules (checked at the gate).

## C1. A bullet may cite only its own job's profile items (blocking)

**Problem.** Rule 3 scopes *attestations* to the bullet's parent, but nothing scopes *profile* refs. A bullet under
`t-exp-2` (Cedar Valley College, the internship) with the text and ref of `exp-1.b1` (a Brightfield Logistics
achievement) passes `check-tailored` (exit 0). The claim traces to CV text, but the CV now says it happened at a
different employer. The same hole exists between engagements of one employer (client A's work shown under client B),
because an engagement bullet can cite a sibling engagement's highlights.

```diff
--- plan/contracts/interfaces.md  (section 8, after rule 3, line 608)
    An attestation cited by a skills item must have `placement` `skills` or `skills_and_bullets`.
+3a. A bullet or `intro` under tailored work `exp-N` may cite profile refs `exp-N` or any ref starting with `exp-N.`.
+   Under tailored engagement `exp-N.eK` it may cite `exp-N.eK`, refs starting with `exp-N.eK.`, and work-level
+   highlights `exp-N.bJ` (for example a tools line). Any other `exp-*` ref is `ref_out_of_scope`. Non-experience refs
+   (`basics`, `sum-*`, `skl-*`, `cert-*`, `edu-*`) are allowed, but each bullet needs at least one ref that is in its
+   allowed `exp-*` set or a usable attestation in scope (`ref_out_of_scope`). Message:
+   `"bullet <id> cites <ref> from another job; parent is <parent profile_id>"`.
```

## C2. `profile-build` must verify dates, locations, and degrees against the cited lines (blocking)

**Problem.** Provenance rule 6 checks the tailored CV's dates, location, and degree against `profile.json`. The
profile itself is only partly verified. `profile-build` checks `date_text` verbatim, but the typed `start_date` /
`end_date` that rule 6 and the renderer actually use are not checked against it. Location and the degree's `area` /
`study_type` are not checked at all. Probes on the junior map, each exiting 0:

- `start_date: 2023-02` with `date_text: "Feb 2024 - Present"` (the PDF then shows "Feb 2023 – Present");
- `end_date: 2025-01` with `date_text: "Jul 2023 - Dec 2023"`;
- work `location: "Austin, TX"` (the CV says Columbus, OH);
- education `area: "Computer Engineering"` (the CV says Computer Science).

So "a changed date" is caught in `tailored.json` but not one step earlier, where it is just as easy to make.

```diff
--- plan/contracts/interfaces.md  (section 5, WP-10 block, lines 348-349)
     # violations: range_error (out of bounds/overlap), unmapped_line (non-blank line not covered or ignored),
-    # not_verbatim (name/employer/title/client/cert/institution not found in its cited lines)
+    # not_verbatim (name/employer/title/client/role label/cert/institution/degree area/study type not found in its
+    # cited lines; each comma-separated part of a work, education, or basics location not found in its cited lines;
+    # start_date/end_date inconsistent with date_text, or an education end_date / certificate date whose year is not
+    # in its cited lines). Date consistency: the year must appear in date_text; a month (YYYY-MM) must appear as its
+    # English name or 3-4 letter abbreviation ("Sep"/"Sept") or its number; `present` needs Present/Current/Now/Today;
+    # "" is always allowed.
```

`profile.verify_verbatim` (the `profile-verify` path for hand-written profiles) gets the same date-consistency check
for work and engagements, through one shared helper in `profile.py`.

## C3 (re-gate 1). A title or role label may not drop a seniority qualifier (blocking, APPLIED - user agreed 2026-10-26)

**Problem.** `profile-build` checks typed values with a bare substring test. A title that drops its seniority word
appears in the cited line as a substring, so it passes. Probes on the junior map, each exiting 0:

- work[0] `position: "DevOps Engineer"` (the CV says `Junior DevOps Engineer`);
- work[1] `position: "IT Support"` (the CV says `IT Support Intern`).

Rule 6 then requires the tailored title to equal that profile title, so the promoted title reaches the PDF.
`truthfulness.md` rule 6 forbids exactly this ("promoting a title"). This is the same class as C2: a profile value
that is easy to get wrong one step before `check-tailored`.

I considered a strict whole-field rule (the title must sit between separators). I rejected it because CV formats vary
(prose such as "worked as a junior engineer at …", or unspaced em dashes), and an honest map could then fail with no
fix. The targeted rule below can only fail when a lowering qualifier sits right next to the typed value and was left
out. That is never an honest map.

No schema, field, exit code, stage, or violation code changes. The junior golden complies (both titles sit between
`|` separators).

```diff
--- plan/contracts/interfaces.md  (section 5, WP-10 block, after line 354)
     # English name or 3-4 letter abbreviation ("Sep"/"Sept") or its number; `present` needs Present/Current/Now/Today;
     # "" is always allowed.
+    # A title or role label is also not_verbatim when, at every occurrence in its cited lines, the word directly
+    # before or after it (only spaces or a hyphen in between) is a seniority qualifier left out of the value
+    # (`profile.SENIORITY_QUALIFIERS`: junior, intern, trainee, assistant, associate, co-, …). Example: title
+    # "DevOps Engineer" from "Junior DevOps Engineer".
```

```diff
--- plan/contracts/interfaces.md  (section 5, WP-10 block, line 337)
-def verify_verbatim(profile: dict, cv_text: str) -> list[dict]  # violations code "fact_mismatch" for texts not found
+def verify_verbatim(profile: dict, cv_text: str) -> list[dict]  # violations code "fact_mismatch" for texts not found,
+    # dates inconsistent with date_text, and titles/role labels that drop a seniority qualifier (as build_profile)
```
