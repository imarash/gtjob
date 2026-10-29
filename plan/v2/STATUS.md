# gtjob Studio — status

Branch: `v2-studio` (not merged).

Resume a later session by reading this file and `plan/v2/ARCHITECTURE.md`. Same invariants, same license boundary, same branch until this file says the branch was merged.

## This session

Slice: local web shell. Today, applications (table and board), application detail, runs, settings. Read career-ops tracker and gtjob `out/`. Write status and `gtjob-run:<slug>` only through `set-status.mjs`.

| Step | State |
| --- | --- |
| Branch `v2-studio` | done |
| Architecture note | done |
| Scaffold `web/` with BoardUI | done |
| Tracker and run readers, status argv builder, tests | done |
| Pages and route handlers | done |
| Browser check on 127.0.0.1 | done |
| `web/README.md` and commit | done |

Verified in the browser at `http://127.0.0.1:3847` against this machine's career-ops checkout. The tracker file is absent (`applications.md` does not exist), so Today shows 0 applications and names that path, Applications shows the empty state, and a run detail says there is no tracker to attach to. Settings lists found and missing paths. Add a role saved a URL into gitignored `.studio/inbox.json` and told the user Studio did not score it. Dark mode toggles. No live `set-status.mjs` write: there is no tracker row to update, and the argv builder is covered by unit tests only.

## Next slice

Evaluate a pasted URL through career-ops pipeline. Do not add a model client to Studio. See the ordered list in `ARCHITECTURE.md`.

## Blockers

None.
