"""`cvt render RUN [--template] [--density] [--draft] [--png] [--ppi N] [--pages N[,N]]`."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import output, paths, render, state
from ..errors import CvtError, ExitCode

MIN_PPI = 20
MAX_PPI = 600
FIRST_PNG_ARTIFACT = "pages_png"


def parse_pages(text: str) -> list[int]:
    """`1` or `1,2` -> [1, 2]. Anything else is a usage error."""
    try:
        pages = [int(part) for part in text.split(",") if part.strip()]
    except ValueError:
        pages = []
    if not pages or any(n < 1 for n in pages):
        raise CvtError(
            ExitCode.USAGE, "E_USAGE", f"invalid --pages value '{text}'",
            hint="use 1-based page numbers separated by commas, for example --pages 1,2",
        )
    return list(dict.fromkeys(pages))


def _rel(run_dir: Path, path: Path) -> str:
    return path.relative_to(run_dir).as_posix()


def _pages_only(args: argparse.Namespace, run_dir: Path) -> int:
    """View-only: never rebuilds, never touches state, never marks anything stale."""
    pngs = render.rasterize_pages(run_dir, parse_pages(args.pages), args.ppi)
    shown, hidden = output.cap_list(args, [_rel(run_dir, p) for p in pngs])
    lines = [f"rasterized {len(pngs)} page(s) of {render.PDF_NAME} at {args.ppi} ppi (view-only)", *shown]
    if hidden:
        lines.append(output.MORE_LINE.format(n=hidden))
    st = state.load(run_dir)
    return output.emit(
        args, run=run_dir.name, stage=st["stage"], data={"pngs": shown, "pngs_more": hidden, "ppi": args.ppi},
        human="\n".join(lines),
    )


def _record(run_dir: Path, st: dict, result: render.RenderResult) -> None:
    state.record_artifact(run_dir, st, "render_model", _rel(run_dir, result.model_path))
    state.record_artifact(run_dir, st, "typst_source", _rel(run_dir, result.typst_path))
    if result.markdown is not None:
        state.record_artifact(run_dir, st, "markdown_fallback", _rel(run_dir, result.markdown))
    if result.pdf is not None:
        state.record_artifact(run_dir, st, "pdf", _rel(run_dir, result.pdf))
    if result.pngs:
        state.record_artifact(run_dir, st, FIRST_PNG_ARTIFACT, _rel(run_dir, result.pngs[0]))


def _run(args: argparse.Namespace) -> int:
    if not MIN_PPI <= args.ppi <= MAX_PPI:
        raise CvtError(ExitCode.USAGE, "E_USAGE", f"--ppi {args.ppi} is out of range",
                       hint=f"use a value from {MIN_PPI} to {MAX_PPI}")
    run_dir = paths.resolve_run(args.run)
    if args.pages:
        return _pages_only(args, run_dir)
    st = state.load(run_dir)
    state.require_stage(st, "tailored")
    state.require_artifact(run_dir, st, "tailored")
    try:
        result = render.render_run(
            run_dir, template=args.template or None, density=args.density or None,
            draft=True if args.draft else None, png=args.png, ppi=args.ppi,
        )
    except CvtError as err:
        if err.err_id == "E_TYPST_MISSING":  # build/ and cv.md exist: keep them tracked
            _record_fallback(run_dir, st)
        raise
    _record(run_dir, st, result)
    if state.stage_index(st["stage"]) >= state.stage_index(render.DRAFT_STAGE_LIMIT):
        state.set_stage(st, render.RENDERED_STAGE)
    state.add_history(st, "render", f"{result.template}/{result.density} pages={result.pages} draft={result.draft}")
    state.save(run_dir, st)
    return _report(args, run_dir, st, result)


def _record_fallback(run_dir: Path, st: dict) -> None:
    build = run_dir / render.BUILD_DIR
    state.record_artifact(run_dir, st, "render_model", _rel(run_dir, build / render.RENDER_JSON))
    state.record_artifact(run_dir, st, "typst_source", _rel(run_dir, build / render.TYPST_ENTRY))
    state.record_artifact(run_dir, st, "markdown_fallback", render.MARKDOWN_NAME)
    state.save(run_dir, st)


def _report(args: argparse.Namespace, run_dir: Path, st: dict, result: render.RenderResult) -> int:
    pngs = [_rel(run_dir, p) for p in result.pngs]
    shown, hidden = output.cap_list(args, pngs)
    lines = [
        f"rendered {result.pages} page(s): {result.template}/{result.density}"
        f"{', draft' if result.draft else ''}{'' if result.fitted else ', unfitted'}",
        f"pdf: {_rel(run_dir, result.pdf)}",
        f"markdown: {_rel(run_dir, result.markdown)}",
    ]
    if shown:
        lines.append(f"png: {', '.join(shown)}" + (f" {output.MORE_LINE.format(n=hidden)}" if hidden else ""))
    lines += [f"warning: {w}" for w in result.warnings]
    data = {
        "pages": result.pages, "pdf": _rel(run_dir, result.pdf), "markdown": _rel(run_dir, result.markdown),
        "pngs": shown, "pngs_more": hidden, "template": result.template, "density": result.density,
        "draft": result.draft, "fitted": result.fitted, "backend": result.backend,
    }
    return output.emit(
        args, run=run_dir.name, stage=st["stage"], data=data, messages=result.warnings, human="\n".join(lines),
        next_action=st["next_action"],
    )


def register(subparsers) -> None:
    p = subparsers.add_parser("render", help="render tailored.json to cv.pdf, cv.md and optional page PNGs")
    p.add_argument("run", metavar="RUN", nargs="?", default=None, help="run slug, run directory, or 'latest'")
    p.add_argument("--template", default=None, choices=render.TEMPLATES, help="template (default: the run's template)")
    p.add_argument("--density", default=None, choices=render.DENSITIES, help="density (default: fit.json, else standard)")
    p.add_argument("--draft", action="store_true", help="force the draft look (red placeholders, DRAFT footer)")
    p.add_argument("--png", action="store_true", help="also write pages/page-<N>.png")
    p.add_argument("--ppi", type=int, default=render.DEFAULT_PPI, help=f"PNG resolution ({render.DEFAULT_PPI})")
    p.add_argument("--pages", default="", help="view-only: rasterize these pages of the existing cv.pdf, e.g. 1,2")
    p.set_defaults(func=_run)
