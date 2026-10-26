"""`cvt init` and `cvt status`: the entry and resume points of every run."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .. import jsonio, output, paths, state, usage
from ..errors import CvtError, ExitCode

QUESTIONS_FILE = "questions.json"
PENDING_STATUS = "pending"
PROMPT_MAX_CHARS = 80
ERROR_MAX_CHARS = 100
PENDING_PROMPTS_SHOWN = 3
ERRORS_SHOWN = 3
ELLIPSIS = "…"
TEMPLATES = ("modern", "classic")
PAPERS = ("us-letter", "a4")
PAGE_TARGETS = (1, 2)
DOCX_FORMAT = "docx"
JD_STDIN_REF = "stdin"
JD_TEXT_REF = "text"
JD_STDIN_FLAG = "jd_stdin"
UNREADABLE_STAGE = "unreadable"
HOST_OVERRIDE_ENV = state.HOST_ENV


def _truncate(text: str, limit: int) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + ELLIPSIS


def _select_jd(args: argparse.Namespace) -> tuple[str, str, str | None]:
    """Return (kind, ref, text) for the single JD source; exit 2 unless exactly one was given."""
    chosen = {
        "--jd": args.jd, "--jd-text": args.jd_text, "--jd-url": args.jd_url,
        "--jd-stdin": True if getattr(args, JD_STDIN_FLAG) else None,
    }
    given = [flag for flag, value in chosen.items() if value is not None]
    if len(given) != 1:
        found = ", ".join(given) if given else "none"
        raise CvtError(
            ExitCode.USAGE, "E_JD_SOURCE", f"exactly one JD source is required (got: {found})",
            hint="pass one of --jd PATH, --jd-text TEXT, --jd-stdin, --jd-url URL",
        )
    if args.jd is not None:
        return "file", args.jd, None
    if args.jd_text is not None:
        return "text", JD_TEXT_REF, args.jd_text
    if args.jd_url is not None:
        return "url", args.jd_url, None
    try:
        return "text", JD_STDIN_REF, sys.stdin.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise CvtError(
            ExitCode.INPUT, "E_JD_UNREADABLE", f"cannot read the JD from stdin: {exc}",
            hint="pipe UTF-8 text into --jd-stdin, or use --jd PATH",
        ) from None


def _check_cv(cv: str) -> Path:
    path = Path(cv)
    if path.suffix.lower().lstrip(".") == DOCX_FORMAT:
        raise CvtError(
            ExitCode.INPUT, "E_CV_FORMAT", ".docx CVs are not supported yet",
            hint="export to PDF or paste text into a .txt file, then pass that with --cv",
        )
    return path


def _init(args: argparse.Namespace) -> int:
    kind, ref, text = _select_jd(args)
    cv_path = _check_cv(args.cv)
    if args.host:
        os.environ[HOST_OVERRIDE_ENV] = args.host  # state.current_host reads it first
    options = {
        "template": args.template, "auto": args.auto, "draft": args.draft,
        "page_target": args.page_target, "paper": args.paper,
    }
    run_dir = state.create_run(cv_path, kind, ref, text, options, slug=args.slug)
    st = state.load(run_dir)
    slug = st["run_slug"]
    return output.emit(
        args, run=slug, stage=st["stage"],
        data={"run_dir": str(run_dir), "run_slug": slug, "inputs": st["inputs"]},
        human=f"run: {slug}\ndir: {run_dir}", next_action=st["next_action"],
    )


def _pending_questions(run_dir: Path) -> list[dict]:
    path = run_dir / QUESTIONS_FILE
    if not path.is_file():
        return []
    try:
        rows = jsonio.load_json(path).get("questions", [])
    except (CvtError, AttributeError):
        return []
    return [
        {"id": q.get("id", ""), "prompt": q.get("prompt", ""),
         "default": (q.get("default") or {}).get("description", "")}
        for q in rows if isinstance(q, dict) and q.get("status") == PENDING_STATUS
    ]


def _token_summary(run_dir: Path) -> dict:
    if not usage.usage_path(run_dir).is_file():
        return {}
    totals = usage.usage_totals(run_dir)
    if not totals:
        return {}
    api = totals["api"].values()
    return {
        "packet_est": totals["total_est"],
        "input": sum(a["input"] + a["cache_read"] + a["cache_write"] for a in api),
        "output": sum(a["output"] for a in api),
    }


def _list_runs() -> list[dict]:
    rows = []
    for state_path in paths.out_dir().glob(f"*/{paths.STATE_FILE}"):
        try:
            st = json.loads(state_path.read_text(encoding="utf-8"))
            row = {
                "run_slug": str(st.get("run_slug") or state_path.parent.name),
                "stage": str(st.get("stage", "")), "status": str(st.get("status", "")),
                "updated_at": str(st.get("updated_at", "")),
            }
        except (OSError, ValueError, AttributeError):
            row = {"run_slug": state_path.parent.name, "stage": UNREADABLE_STAGE, "status": "", "updated_at": ""}
        rows.append(row)
    return sorted(rows, key=lambda r: (r["updated_at"], r["run_slug"]), reverse=True)


def _state_summary(st: dict) -> dict:
    return {
        "run_slug": st["run_slug"], "stage": st["stage"], "status": st["status"],
        "checkpoints": st["checkpoints"], "pending": st["pending"], "options": st["options"],
        "artifacts": [{"name": a["name"], "path": a["path"], "stale": a["stale"]} for a in st["artifacts"]],
        "errors": st["errors"][-ERRORS_SHOWN:], "updated_at": st["updated_at"],
    }


def _status_lines(st: dict, pending: list[dict], tokens: dict) -> list[str]:
    cps = st["checkpoints"]
    head = f"{st['run_slug']} | {st['stage']} | {st['status']} | cp1={cps['cp1']} cp2={cps['cp2']}"
    lines = [head]
    kind = st["pending"]["kind"]
    if pending or kind != "none":
        count = f"{len(pending)} question(s)" if pending else _truncate(st["pending"]["message"], PROMPT_MAX_CHARS)
        lines[0] += f" | pending: {kind} {count}".rstrip()
    lines += [f"  {q['id']}: {_truncate(q['prompt'], PROMPT_MAX_CHARS)}" for q in pending[:PENDING_PROMPTS_SHOWN]]
    stale = [a["name"] for a in st["artifacts"] if a["stale"]]
    if stale:
        lines.append(f"stale: {', '.join(stale)}")
    if st["errors"]:
        last = st["errors"][-1]
        lines.append(f"error: [{last['code']}] {_truncate(last['message'], ERROR_MAX_CHARS)}")
    if tokens:
        lines.append(f"tokens: ~{tokens['packet_est']} packet est. / {tokens['input']} in, {tokens['output']} out (api)")
    return lines


def _status(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    pending = _pending_questions(run_dir)
    tokens = _token_summary(run_dir)
    slug = st["run_slug"]
    data: dict = {"state": _state_summary(st), "pending_questions": pending}
    if tokens:
        data["tokens"] = tokens
    if args.all:
        runs = _list_runs()
        data["state"] = st
        data["runs"] = runs
        human = "\n".join(
            f"{r['run_slug']} | {r['stage']} | {r['status']} | {r['updated_at']}" for r in runs
        )
    else:
        human = "\n".join(_status_lines(st, pending, tokens))
    return output.emit(args, run=slug, stage=st["stage"], data=data, human=human, next_action=st["next_action"])


def register(subparsers) -> None:
    p = subparsers.add_parser("init", help="create a run from a CV and a job description")
    p.add_argument("--cv", required=True, metavar="PATH", help="CV file (.pdf, .txt, .md)")
    p.add_argument("--jd", metavar="PATH", default=None, help="JD file")
    p.add_argument("--jd-text", metavar="TEXT", default=None, help="JD text pasted inline")
    p.add_argument("--jd-stdin", action="store_true", help="read the JD from stdin")
    p.add_argument("--jd-url", metavar="URL", default=None, help="JD URL (the host fetches it into inputs/jd.md)")
    p.add_argument("--template", choices=TEMPLATES, default=state.DEFAULT_OPTIONS["template"])
    p.add_argument("--auto", action="store_true", help="auto mode: default every question, no checkpoints")
    p.add_argument("--draft", action="store_true", help="draft mode: warnings instead of blocking gates")
    p.add_argument("--page-target", type=int, choices=PAGE_TARGETS, default=state.DEFAULT_OPTIONS["page_target"])
    p.add_argument("--paper", choices=PAPERS, default=state.DEFAULT_OPTIONS["paper"])
    p.add_argument("--slug", default=None, metavar="S", help="run slug stem (default: from the JD)")
    p.add_argument("--host", choices=state.HOSTS, default=None, help="override host detection")
    p.set_defaults(func=_init)

    s = subparsers.add_parser("status", help="show where a run stands and what to do next")
    s.add_argument("run", nargs="?", default=paths.LATEST_RUN, metavar="RUN",
                   help="run slug, run directory, or 'latest' (default)")
    s.set_defaults(func=_status)
