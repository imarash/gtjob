"""`cvt report RUN` and `cvt critique-save RUN FILE`."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .. import jsonio, output, paths, report, schemas, state
from ..errors import CvtError, ExitCode

REPORT_ARTIFACT = "report"
CRITIQUE_ARTIFACT = "critique"
CRITIQUE_FILE = "critique.json"
CRITIQUE_SCHEMA = "critique"
REPORT_MIN_STAGE = "validated"
REPORTED_STAGE = "reported"
FENCE_PATTERN = re.compile(r"```[ \t]*([A-Za-z0-9_-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)
JSON_FENCE_LANGUAGE = "json"
GATE_STATUSES = ("pass", "warn", "fail", "skipped")
NO_VALIDATION_LINE = "gates: not run"


def _gate_summary(run_dir: Path) -> tuple[str, dict]:
    path = run_dir / report.OPTIONAL_FILES["validation"]
    if not path.is_file():
        return NO_VALIDATION_LINE, {}
    validation = jsonio.load_json(path)
    counts = {s: sum(1 for g in validation["gates"] if g["status"] == s) for s in GATE_STATUSES}
    text = ", ".join(f"{n} {s}" for s, n in counts.items() if n)
    return f"gates: {text or 'none'} ({'passed' if validation['passed'] else 'did not pass'})", counts


def _report(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    text = report.build_report(run_dir)
    (run_dir / report.REPORT_FILE).write_text(text, encoding="utf-8")
    state.record_artifact(run_dir, st, REPORT_ARTIFACT, report.REPORT_FILE)
    complete = state.stage_index(st["stage"]) >= state.stage_index(REPORT_MIN_STAGE)
    if complete:
        state.set_stage(st, REPORTED_STAGE)
    state.add_history(st, "report", "" if complete else "draft report")
    state.save(run_dir, st)
    gates, counts = _gate_summary(run_dir)
    lines = [
        f"report: {report.REPORT_FILE}" + ("" if complete else f" (draft report: stage is {st['stage']})"),
        f"pdf: {report.final_pdf(run_dir, st)}",
        gates,
        report.token_summary(run_dir),
    ]
    data = {
        "report": report.REPORT_FILE, "final_pdf": report.final_pdf(run_dir, st), "gates": counts,
        "draft_report": not complete, "tokens": report.token_summary(run_dir).removeprefix("tokens: "),
    }
    return output.emit(args, run=run_dir.name, stage=st["stage"], data=data, human="\n".join(lines),
                       next_action=st["next_action"])


def extract_json_text(text: str) -> str:
    """The JSON text in `text`: the whole text when it is JSON, else the first fenced block that starts with `{`."""
    stripped = text.strip()
    if stripped.startswith("{"):
        return stripped
    blocks = [(lang.lower(), body.strip()) for lang, body in FENCE_PATTERN.findall(text)]
    ordered = [b for lang, b in blocks if lang == JSON_FENCE_LANGUAGE] + [b for lang, b in blocks if lang != JSON_FENCE_LANGUAGE]
    for body in ordered:
        if body.startswith("{"):
            return body
    raise CvtError(
        ExitCode.CHECK_FAILED, "E_CRITIQUE_NO_JSON", "no JSON object found in the critique file",
        hint="the critic must put one fenced ```json block (a critique.schema.json object) in its reply",
    )


def _parse(text: str) -> dict:
    body = extract_json_text(text)
    try:
        obj = json.loads(body)
    except json.JSONDecodeError as exc:
        raise CvtError(
            ExitCode.CHECK_FAILED, "E_CRITIQUE_JSON",
            f"the critique JSON is invalid (line {exc.lineno}, column {exc.colno}): {exc.msg}",
            hint="fix the JSON syntax in the critique block and rerun critique-save",
        ) from None
    if not isinstance(obj, dict):
        raise CvtError(ExitCode.CHECK_FAILED, "E_CRITIQUE_JSON", "the critique JSON must be an object",
                       hint="use the critique.schema.json shape: {schema_version, run_id, model, ...}")
    return obj


def _critique_save(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    source = Path(args.file)
    if not source.is_file():
        raise CvtError(ExitCode.INPUT, "E_FILE_NOT_FOUND", f"{source} not found",
                       hint="pass the path of the file the critic wrote")
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CvtError(ExitCode.INPUT, "E_FILE_UNREADABLE", f"cannot read {source}: {exc}",
                       hint="the critique file must be UTF-8 text") from None
    critique = _parse(text)
    schemas.require_valid(critique, CRITIQUE_SCHEMA, str(source))
    tailored_path = state.require_artifact(run_dir, st, "tailored", allow_stale=True)
    current = jsonio.load_json(tailored_path).get("version")
    if critique["tailored_version"] != current:
        raise CvtError(
            ExitCode.CHECK_FAILED, "E_CRITIQUE_VERSION",
            f"critique is for tailored version {critique['tailored_version']} but the run is at version {current}",
            hint="rerun the critic on the current CV (cvt brief critic RUN), then save its output again",
        )
    jsonio.dump_json(critique, run_dir / CRITIQUE_FILE)
    state.record_artifact(run_dir, st, CRITIQUE_ARTIFACT, CRITIQUE_FILE)
    state.add_history(st, "critique-save", f"verdict={critique['verdict']}")
    state.save(run_dir, st)
    lines = [f"{s['criterion']}: {s['score']}/5" for s in critique["scores"]]
    lines.append(f"verdict: {critique['verdict']} ({len(critique['issues'])} issues) -> {CRITIQUE_FILE}")
    data = {
        "path": CRITIQUE_FILE, "verdict": critique["verdict"], "issues": len(critique["issues"]),
        "scores": {s["criterion"]: s["score"] for s in critique["scores"]},
    }
    return output.emit(args, run=run_dir.name, stage=st["stage"], data=data, human="\n".join(lines))


def register(subparsers) -> None:
    p = subparsers.add_parser("report", help="write report.md, the honest companion to the CV")
    p.add_argument("run", metavar="RUN", nargs="?", default=None, help="run slug, run directory, or 'latest'")
    p.set_defaults(func=_report)
    c = subparsers.add_parser("critique-save", help="validate and save the critic's output as critique.json")
    c.add_argument("run", metavar="RUN", help="run slug, run directory, or 'latest'")
    c.add_argument("file", metavar="FILE", help="critique JSON, or Markdown containing one fenced JSON block")
    c.set_defaults(func=_critique_save)
