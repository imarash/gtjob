"""Human and `--json` output with the terse-output caps (interfaces.md section 4)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from . import answers, jsonio, paths
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
    head, *body = err.message.splitlines() or [err.message]
    lines = [f"cvt: error[{err.err_id}]: {head}"]
    lines.extend(body)
    if err.hint:
        lines.append(f"  hint: {err.hint}")
    shown, hidden = cap_list(args, err.violations)
    for v in shown:
        qid = str(v.get("question_id") or "")
        loc = str(v.get("item_id") or "")
        prefix = f"{qid}: " if qid else (f"{loc}: " if loc else "")
        lines.append(f"  - {prefix}{v.get('message', '')}".rstrip())
    if hidden:
        lines.append("  " + MORE_LINE.format(n=hidden))
    if err.err_id == answers.FAILED_ID and err.violations:
        run_slug = str(getattr(args, "run", "") or "")
        if run_slug:
            try:
                run_dir = paths.resolve_run(run_slug)
                qfile = run_dir / "questions.json"
                questions = jsonio.load_json(qfile) if qfile.is_file() else None
                raw = ""
                round_arg = str(getattr(args, "round", "") or "").strip()
                round_file = Path(round_arg) if round_arg else run_dir / "answers.round.json"
                if round_file.is_file():
                    raw = jsonio.load_json(round_file).get("raw_text", "")
                guide = answers.user_violation_lines(err.violations, questions, raw)
                if guide:
                    lines.extend(["", "Your answers could not be saved:", *guide])
            except CvtError:
                pass
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
