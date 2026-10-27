# WP-G4 contract-change proposal: sync the section 14.4 output column with `budgets.json`

Status: proposed. Apply only after the user agrees. WP-FIX-4-5 does not depend on it, because section 14.4 says
budgets are "tunable without a contract change". This keeps the contract table in step with the file.

Reason: the private sample's AI outputs (jd ≈ 2,300–2,900 tokens, tailor ≈ 3,300–4,100) exceed or meet today's CLI
`max_tokens` (2,000 and 4,000). `E_MAX_TOKENS` is not retried, so a live `gtjob tailor` on the staff JD would fail.

## Diff (`plan/contracts/interfaces.md`, section 14.4)

```diff
 | Packet | Max input tokens (estimate) | CLI `max_tokens` (output) |
 | --- | --- | --- |
-| profile | 1,500 + the numbered CV | 4,000 |
-| jd | 3,000 | 2,000 |
-| match | 7,000 | 3,000 |
-| questions | 4,000 | 1,500 |
-| answer_parse | 2,500 | 1,000 |
-| tailor | 8,000 | 4,000 |
-| change_request | 3,000 | 1,000 |
+| profile | 1,500 + the numbered CV | 8,000 |
+| jd | 3,000 | 5,000 |
+| match | 7,000 | 6,000 |
+| questions | 4,000 | 3,000 |
+| answer_parse | 2,500 | 2,000 |
+| tailor | 8,000 | 8,000 |
+| change_request | 3,000 | 2,000 |
 | fix | 2,500 | 1,500 |
-| critic | 4,000 | 1,500 |
+| critic | 4,000 | 3,000 |
```

Optional wording clarification for section 7 (no behaviour change; it matches WP-I4 plus WP-FIX-4-4):

```diff
-1. Validates schema and rules (violations: more than 8 pending cp1 questions, missing default, `allow_free_text` false,
+1. Validates schema and rules (violations: more than 8 pending cp1 questions in the initial batch (no `parent_id`) or in one follow-up round, missing default, `allow_free_text` false,
```
