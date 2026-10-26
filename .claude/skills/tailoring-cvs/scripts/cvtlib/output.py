"""Human and `--json` output with the terse-output caps (interfaces.md section 4)."""

from __future__ import annotations

import json
import sys
from typing import Any

from .errors import CvtError

MAX_HUMAN_LINES = 15
MAX_LIST_ITEMS = 10
MORE_LINE = "+{n} more (use --all)"
NEXT_PREFIX = "next: "


def _wants_json(args: Any) -> bool:
    return bool(getattr(args, "json", False))


def _wants_all(args: Any) -> bool:
    return bool(getattr(args, "all", False))


def cap_list(args: Any, items: list) -> tuple[list, int]:
    """Return (shown, hidden_count). `--all` lifts the cap."""
    if _wants_all(args) or len(items) <= MAX_LIST_ITEMS:
        return list(items), 0
    return list(items[:MAX_LIST_ITEMS]), len(items) - MAX_LIST_ITEMS


def cap_lines(args: Any, lines: list[str], reserve: int = 0) -> list[str]:
    """Cap to MAX_HUMAN_LINES (minus `reserve` lines kept by the caller) unless `--all`."""
    if _wants_all(args):
        return lines
    room = MAX_HUMAN_LINES - reserve
    if len(lines) <= room:
        return lines
    keep = max(room - 1, 0)
    return [*lines[:keep], MORE_LINE.format(n=len(lines) - keep)]


def _envelope(
    args: Any, *, ok: bool, exit_code: int, run: str, stage: str, data: dict, messages: list[str],
    next_action: str, error: dict,
) -> str:
    env = {
        "ok": ok, "command": getattr(args, "command", "") or "", "exit_code": exit_code, "run": run,
        "stage": stage, "data": data, "messages": messages, "next_action": next_action, "error": error,
    }
    return json.dumps(env, ensure_ascii=False, separators=(",", ":"))


def emit(
    args: Any, *, run: str = "", stage: str = "", data: dict | None = None,
    messages: list[str] | None = None, human: str = "", next_action: str = "", exit_code: int = 0,
) -> int:
    messages = list(messages or [])
    if _wants_json(args):
        print(_envelope(
            args, ok=exit_code == 0, exit_code=exit_code, run=run, stage=stage, data=data or {},
            messages=messages, next_action=next_action, error={"id": "", "message": "", "hint": ""},
        ))
        return exit_code
    body = human.splitlines() if human else list(messages)
    tail = [f"{NEXT_PREFIX}{next_action}"] if next_action else []
    lines = [*cap_lines(args, body, reserve=len(tail)), *tail]
    if lines:
        print("\n".join(lines))
    return exit_code


def _human_error(err: CvtError, args: Any) -> str:
    lines = [f"cvt: error[{err.err_id}]: {err.message}"]
    if err.hint:
        lines.append(f"  hint: {err.hint}")
    shown, hidden = cap_list(args, err.violations)
    lines += [f"  - {v.get('item_id', '')}: {v.get('message', '')}".rstrip() for v in shown]
    if hidden:
        lines.append("  " + MORE_LINE.format(n=hidden))
    return "\n".join(lines)


def fail(args: Any, err: CvtError) -> int:
    if _wants_json(args):
        shown, hidden = cap_list(args, err.violations)
        data: dict = {"violations": shown} if err.violations else {}
        if hidden:
            data["violations_more"] = hidden
        print(_envelope(
            args, ok=False, exit_code=int(err.code), run=str(getattr(args, "run", "") or ""),
            stage="", data=data, messages=[],
            next_action=err.hint, error={"id": err.err_id, "message": err.message, "hint": err.hint},
        ))
    else:
        print(_human_error(err, args), file=sys.stderr)
    return int(err.code)
