#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "jsonschema>=4.23",
#     "pypdf>=6.0",
#     "typst>=0.15",
# ]
# ///
"""Polish a generic CV (no job description): extract text, then render every template.

    uv run .claude/skills/tailoring-cvs/scripts/polish_render.py extract CV.pdf
    uv run .claude/skills/tailoring-cvs/scripts/polish_render.py render render.json out/slug-generic

`extract` uses the same reader and cleaner as `cvt ingest`. `render` tries density `standard`, then
`compact` if that template is over 3 pages. It does not drop content. Exit 1 with "still over 3 pages"
means tighten wording and rerun. Exit 1 with E_SCHEMA means the render model does not match the schema.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cvtlib import ingest, jsonio, render, schemas  # noqa: E402
from cvtlib.errors import CvtError, ExitCode  # noqa: E402

PAGE_MAX = 3
DENSITIES = ("standard", "compact")
BUILD_DIR = ".build"
LAYOUT_LINES = 80
SIDEBAR_TEMPLATE = "sidebar"


def extract_text(path: Path) -> str:
    """CV text from the same reader and cleaner as `cvt ingest`. Empty, scanned, and unknown formats raise."""
    path = Path(path)
    if not path.is_file():
        raise CvtError(
            ExitCode.USAGE, "E_USAGE", f"not a file: {path}",
            hint="pass a .pdf, .txt, or .md CV",
        )
    extraction = ingest.extract_cv(path)
    text, warnings = ingest.clean_cv_text(extraction.text)
    for warning in (*extraction.warnings, *warnings):
        print(f"polish_render: {warning}", file=sys.stderr)
    if not text.strip():
        raise CvtError(
            ExitCode.INPUT, "E_CV_EMPTY", "the CV has no readable text",
            hint="pass a CV with text content (.pdf, .txt or .md)",
        )
    return text


def sidebar_layout(pdf: Path) -> str:
    """Page 1 of the sidebar PDF, for the narrow-rail check. Empty when pdftotext is missing."""
    if not pdf.is_file() or not shutil.which("pdftotext"):
        return ""
    proc = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", "-f", "1", "-l", "1", str(pdf), "-"],
        capture_output=True, check=False,
    )
    if proc.returncode != 0:
        return ""
    return "\n".join(proc.stdout.decode("utf-8", errors="replace").splitlines()[:LAYOUT_LINES])


def pdf_stem(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in name.strip())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-")
    return f"{cleaned}-CV" if cleaned else "CV"


def _compile(model: dict, template: str, density: str, out_dir: Path, pdf: Path) -> int:
    trial = {**model, "theme": {**model["theme"], "template": template, "density": density}}
    run = out_dir / BUILD_DIR / template
    typ = render.write_build(run, trial, template)
    return render.compile_pdf(run, typ, pdf)


def render_all(model_path: Path, out_dir: Path) -> int:
    model = jsonio.load_json(model_path)
    schemas.require_valid(model, "render-model", "render model")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = pdf_stem(str(model.get("header", {}).get("name", "")))
    over: list[str] = []
    for template in render.TEMPLATES:
        pdf = out_dir / f"{stem}-{template}.pdf"
        pages, density = 0, DENSITIES[0]
        for density in DENSITIES:
            pages = _compile(model, template, density, out_dir, pdf)
            if pages <= PAGE_MAX:
                break
        print(f"{template}\t{density}\t{pages}\t{pdf}")
        if pages > PAGE_MAX:
            over.append(f"{template} ({pages})")
    md = out_dir / f"{stem}.md"
    md.write_text(render.render_markdown(model), encoding="utf-8")
    print(f"markdown\t{md}")
    layout = sidebar_layout(out_dir / f"{stem}-{SIDEBAR_TEMPLATE}.pdf")
    if layout:
        print("sidebar-layout\tpage 1")
        print(layout)
    shutil.rmtree(out_dir / BUILD_DIR, ignore_errors=True)
    if over:
        print(
            "still over 3 pages at compact: " + ", ".join(over) + ". Tighten wording; do not drop facts.",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract or render a generic CV (no job description).")
    sub = parser.add_subparsers(dest="command", required=True)
    ext = sub.add_parser("extract", help="print CV text to stdout")
    ext.add_argument("cv", type=Path)
    rend = sub.add_parser("render", help="render render.json with every template")
    rend.add_argument("model", type=Path)
    rend.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "extract":
            text = extract_text(args.cv)
            sys.stdout.write(text if text.endswith("\n") or not text else text + "\n")
            return 0
        return render_all(args.model, args.out)
    except CvtError as exc:
        print(f"polish_render: error[{exc.err_id}]: {exc.message}", file=sys.stderr)
        if exc.hint:
            print(f"  hint: {exc.hint}", file=sys.stderr)
        return int(exc.code)


if __name__ == "__main__":
    raise SystemExit(main())
