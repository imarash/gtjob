"""`cvt fit RUN [--png]` and `cvt validate RUN [--draft]`."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import fit, output, paths, render, state, validate
from ..errors import CvtError, ExitCode

FIT_MIN_STAGE, FIT_DRAFT_MIN_STAGE = "approved", "tailored"
VALIDATE_MIN_STAGE = "rendered"
MAX_GATE_LINES = 6  # non-pass gate lines shown (the whole human output stays within 10 lines)
MAX_LINE_CHARS = 160
VALIDATION_FAILED_ID = "E_VALIDATION_FAILED"
DRAFT_NEXT_ACTION = (
    "Draft validation passed; no final PDF is published. Resolve placeholders and proposed attestations, "
    "then rerun: {cvt} validate {run}"
)
FIX_HINT = "run `cvt brief fix {run}`, patch only the listed items, then rerun: cvt fit {run} && cvt validate {run}"


def _rel(run_dir: Path, path: Path) -> str:
    return path.relative_to(run_dir).as_posix()


def _clip(text: str) -> str:
    return text if len(text) <= MAX_LINE_CHARS else text[: MAX_LINE_CHARS - 1] + "…"


# --- fit ----------------------------------------------------------------------------------------------------
def _record_fit(run_dir: Path, st: dict, png: bool) -> None:
    build = run_dir / render.BUILD_DIR
    state.record_artifact(run_dir, st, "fit", render.FIT_FILE)
    state.record_artifact(run_dir, st, "render_model", _rel(run_dir, build / render.RENDER_JSON))
    state.record_artifact(run_dir, st, "typst_source", _rel(run_dir, build / render.TYPST_ENTRY))
    state.record_artifact(run_dir, st, "markdown_fallback", render.MARKDOWN_NAME)
    state.record_artifact(run_dir, st, "pdf", render.PDF_NAME)
    first_png = run_dir / render.PAGES_DIR / render.PNG_PATTERN.format(n=1)
    if png and first_png.is_file():
        state.record_artifact(run_dir, st, "pages_png", _rel(run_dir, first_png))


def _fit(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    if st["options"]["draft"]:
        state.require_stage(st, FIT_DRAFT_MIN_STAGE)
    else:
        state.require_stage(st, FIT_MIN_STAGE)
    state.require_artifact(run_dir, st, "tailored")
    try:
        result = fit.fit_run(run_dir, png=bool(args.png))
    except CvtError as err:
        if err.err_id == "E_FIT_OVERFLOW":
            st["status"] = "failed"
            state.add_error(st, err.err_id, err.message)
            state.add_history(st, "fit", f"failed: {err.err_id}")
            state.save(run_dir, st)
        raise
    _record_fit(run_dir, st, bool(args.png))
    if state.stage_index(st["stage"]) >= state.stage_index(FIT_MIN_STAGE):
        state.set_stage(st, render.RENDERED_STAGE)
    state.add_history(st, "fit", f"{result['density']} pages={result['pages']} dropped={len(result['dropped_ids'])}")
    state.save(run_dir, st)
    shown, hidden = output.cap_list(args, result["log"])
    lines = [
        f"fitted {result['pages']}/{result['page_target']} page(s): {result['density']}, "
        f"dropped {len(result['dropped_ids'])} unit(s), {result['renders']} compile(s)"
        f"{', underfilled' if result['underfilled'] else ''}",
        f"pdf: {render.PDF_NAME}",
        *shown,
    ]
    if hidden:
        lines.append(output.MORE_LINE.format(n=hidden))
    data = {
        "pages": result["pages"], "page_target": result["page_target"], "density": result["density"],
        "dropped": len(result["dropped_ids"]), "dropped_ids": result["dropped_ids"][:output.MAX_LIST_ITEMS],
        "renders": result["renders"], "underfilled": result["underfilled"], "pdf": render.PDF_NAME,
        "fit_json": render.FIT_FILE, "log": shown,
    }
    return output.emit(args, run=run_dir.name, stage=st["stage"], data=data, human="\n".join(lines), next_action=st["next_action"])


# --- validate -----------------------------------------------------------------------------------------------
def _gate_line(gate: dict) -> str:
    detail = gate["details"][0] if gate["details"] else (gate["violations"][0]["message"] if gate["violations"] else "")
    return _clip(f"{gate['status']} {gate['name']}: {detail}".rstrip(": "))


def _validate(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    draft = bool(args.draft or st["options"]["draft"])
    if state.stage_index(st["stage"]) < state.stage_index(VALIDATE_MIN_STAGE) and draft:
        state.require_stage(st, FIT_DRAFT_MIN_STAGE)
    else:
        state.require_stage(st, VALIDATE_MIN_STAGE)
    validation = validate.validate_run(run_dir, draft=draft)
    st = state.load(run_dir)
    gates = validation["gates"]
    counts = {s: sum(g["status"] == s for g in gates) for s in ("pass", "warn", "fail", "skipped")}
    cov = validation["coverage"]
    cov_pct = f"{cov['must_keywords_found'] * 100 // cov['must_keywords_total']}%" if cov["must_keywords_total"] else "n/a"
    summary = (f"gates: {counts['pass']} pass, {counts['warn']} warn, {counts['fail']} fail, {counts['skipped']} skipped; "
               f"keyword coverage {cov_pct}")
    if not validation["passed"]:
        failing = [v for g in gates if g["status"] == "fail" for v in g["violations"]]
        names = ", ".join(g["name"] for g in gates if g["status"] == "fail")
        st["status"] = "failed"
        state.add_error(st, VALIDATION_FAILED_ID, f"gates failed: {names}")
        state.add_history(st, "validate", f"failed: {names}")
        state.save(run_dir, st)
        raise CvtError(
            ExitCode.CHECK_FAILED, VALIDATION_FAILED_ID, f"validation failed ({names}); {summary}",
            hint=FIX_HINT.format(run=run_dir.name), violations=failing,
        )
    final = state.artifact(st, "final_pdf")
    shown_gates = [g for g in gates if g["status"] != "pass"]
    lines = [summary, *[_gate_line(g) for g in shown_gates[:MAX_GATE_LINES]]]
    if len(shown_gates) > MAX_GATE_LINES:
        lines.append(output.MORE_LINE.format(n=len(shown_gates) - MAX_GATE_LINES))
    if final is not None and not draft:
        lines.append(f"final pdf: {final['path']}")
    next_action = (
        DRAFT_NEXT_ACTION.replace("{cvt}", state.CVT_COMMAND).replace("{run}", run_dir.name)
        if draft else st["next_action"]
    )
    data = {
        "passed": True, "draft": draft, "gates": {g["name"]: g["status"] for g in gates}, "coverage_pct": cov_pct,
        "missing_keywords": cov["missing"][:output.MAX_LIST_ITEMS], "final_pdf": final["path"] if final and not draft else "",
        "layout_warnings": [v["message"] for g in gates if g["name"] == "layout" for v in g["violations"]][:output.MAX_LIST_ITEMS],
        "validation": validate.VALIDATION_FILE,
    }
    return output.emit(args, run=run_dir.name, stage=st["stage"], data=data, human="\n".join(lines), next_action=next_action)


def register(subparsers) -> None:
    p = subparsers.add_parser("fit", help="fit the CV to the page target (density, then drops) and render cv.pdf")
    p.add_argument("run", metavar="RUN", nargs="?", default=None, help="run slug, run directory, or 'latest'")
    p.add_argument("--png", action="store_true", help="also write pages/page-<N>.png (off by default)")
    p.set_defaults(func=_fit)
    p = subparsers.add_parser("validate", help="run every validation gate and publish final/<Name>-<Title>.pdf")
    p.add_argument("run", metavar="RUN", nargs="?", default=None, help="run slug, run directory, or 'latest'")
    p.add_argument("--draft", action="store_true", help="placeholders and proposed attestations warn instead of fail")
    p.set_defaults(func=_validate)
