"""Exit codes and the single exception type used by every command."""

from __future__ import annotations

import enum


class ExitCode(enum.IntEnum):
    OK = 0
    CHECK_FAILED = 1
    USAGE = 2
    MISSING_DEPENDENCY = 3
    STATE = 4
    INPUT = 5
    AWAITING_USER = 6
    INTERNAL = 7


class CvtError(Exception):
    """An actionable failure: stable id, message, hint, optional violation list."""

    def __init__(
        self,
        code: ExitCode,
        err_id: str,
        message: str,
        hint: str = "",
        violations: list[dict] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = ExitCode(code)
        self.err_id = err_id
        self.message = message
        self.hint = hint
        self.violations: list[dict] = list(violations or [])
