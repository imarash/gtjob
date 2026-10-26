"""usage.jsonl: the one place that writes and sums token telemetry (interfaces.md 14.7)."""

from __future__ import annotations

import json
from pathlib import Path

from . import jsonio
from .errors import CvtError, ExitCode

USAGE_FILE = "usage.jsonl"
KINDS = ("packet", "api")
ENTRY_KEYS = (
    "at", "stage", "kind", "model", "est_tokens", "input_tokens",
    "cache_read_tokens", "cache_write_tokens", "output_tokens", "attempt",
)
REQUIRED_KEYS = ("stage", "kind")
INT_KEYS = ("est_tokens", "input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens", "attempt")
DEFAULT_ATTEMPT = 1


def usage_path(run_dir: Path) -> Path:
    return Path(run_dir) / USAGE_FILE


def record_usage(run_dir: Path, entry: dict) -> None:
    unknown = sorted(set(entry) - set(ENTRY_KEYS))
    missing = [k for k in REQUIRED_KEYS if k not in entry]
    if unknown or missing or entry.get("kind") not in KINDS:
        raise CvtError(
            ExitCode.INTERNAL, "E_USAGE_ENTRY",
            f"bad usage entry (unknown={unknown}, missing={missing}, kind={entry.get('kind')!r})",
            hint=f"allowed keys: {', '.join(ENTRY_KEYS)}; kind is one of {', '.join(KINDS)}",
        )
    full: dict = {
        "at": jsonio.now_iso(), "stage": "", "kind": "", "model": "",
        **{k: 0 for k in INT_KEYS},
    }
    full["attempt"] = DEFAULT_ATTEMPT
    full.update(entry)
    jsonio.append_jsonl(usage_path(run_dir), {k: full[k] for k in ENTRY_KEYS})


def usage_totals(run_dir: Path) -> dict:
    path = usage_path(run_dir)
    if not path.is_file():
        return {}
    packets: dict[str, int] = {}
    api: dict[str, dict] = {}
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        stage = row.get("stage", "")
        if row.get("kind") == "packet":
            est = int(row.get("est_tokens", 0))
            packets[stage] = packets.get(stage, 0) + est
            total += est
        elif row.get("kind") == "api":
            acc = api.setdefault(
                stage, {"model": "", "input": 0, "cache_read": 0, "cache_write": 0, "output": 0},
            )
            acc["model"] = row.get("model", "") or acc["model"]
            acc["input"] += int(row.get("input_tokens", 0))
            acc["cache_read"] += int(row.get("cache_read_tokens", 0))
            acc["cache_write"] += int(row.get("cache_write_tokens", 0))
            acc["output"] += int(row.get("output_tokens", 0))
    if not packets and not api:
        return {}
    return {"packets": packets, "api": api, "total_est": total}
