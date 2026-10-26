"""Best-effort detection of the host that is driving `cvt`.

Detection looks only at environment variables and can be wrong (a wrapper may strip or add variables):

- `CLAUDECODE` set            -> `claude_code`
- any variable `CURSOR_*` set -> `cursor`
- otherwise                   -> `unknown`

`cli` and `api` are never detected. They are set explicitly through `GTJOB_HOST`, which
`cvtlib.state.current_host` checks before calling `detect()`. `cvt init --host` overrides detection too.
"""

from __future__ import annotations

import os

CLAUDE_CODE_ENV = "CLAUDECODE"
CURSOR_ENV_PREFIX = "CURSOR_"
HOST_CLAUDE_CODE = "claude_code"
HOST_CURSOR = "cursor"
HOST_UNKNOWN = "unknown"


def detect() -> str:
    """Return `claude_code`, `cursor`, or `unknown` from the process environment."""
    env = os.environ
    if env.get(CLAUDE_CODE_ENV):
        return HOST_CLAUDE_CODE
    if any(key.startswith(CURSOR_ENV_PREFIX) for key in env):
        return HOST_CURSOR
    return HOST_UNKNOWN
