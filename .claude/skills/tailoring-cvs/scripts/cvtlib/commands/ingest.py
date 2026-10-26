"""`cvt ingest RUN`: turn the stored CV and JD into clean text (`cv.txt`, `jd.txt`) and fill `state.ingest`."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .. import ingest, jsonio, output, paths, state
from ..errors import CvtError, ExitCode

COMMAND = "ingest"
CV_TXT = "cv.txt"
JD_TXT = "jd.txt"
CV_ARTIFACT = "cv_txt"
JD_ARTIFACT = "jd_txt"
NEXT_STAGE = "ingested"
# state.schema.json limits ingest.method to these values; OCR has no value of its own (see report).
STATE_METHODS = ("none", "pdftotext", "pypdf", "text", "markdown", "docx")
OCR_STATE_METHOD = "none"
MAX_JSON_WARNINGS = 10


def _write_text(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _state_method(method: str) -> str:
    return method if method in STATE_METHODS else OCR_STATE_METHOD


def _ingest(run_dir: Path, st: dict) -> dict:
    inputs = st["inputs"]
    extraction = ingest.extract_cv(run_dir / inputs["cv"]["stored_path"])
    cv_text, clean_warnings = ingest.clean_cv_text(extraction.text)
    if not cv_text.strip():
        raise CvtError(
            ExitCode.INPUT, "E_CV_EMPTY", "the CV has no readable text",
            hint="pass a CV with text content (.pdf, .txt or .md)",
        )
    jd_input = inputs["jd"]
    jd_path = run_dir / jd_input["stored_path"]
    jd_text = ingest.clean_jd_text(ingest.load_jd(jd_input["kind"], jd_input["original_ref"], jd_path))
    if not jd_text.strip():
        raise CvtError(
            ExitCode.INPUT, "E_JD_EMPTY", "the job description is empty",
            hint="pass a non-empty JD with --jd, --jd-text, --jd-stdin or --jd-url",
        )
    jd_input["sha256"] = jsonio.sha256_file(jd_path)  # a fetched URL rewrites inputs/jd.md
    return {
        "cv_text": cv_text, "jd_text": jd_text,
        "ingest": {
            "method": _state_method(extraction.method), "pages": extraction.pages, "chars": len(cv_text),
            "scanned_suspect": extraction.scanned_suspect,
            "warnings": [*extraction.warnings, *clean_warnings],
        },
    }


def _unchanged(st: dict, run_dir: Path, result: dict) -> bool:
    """True when both texts are byte-identical to the recorded artifacts and the run is already past ingest."""
    if state.stage_index(st["stage"]) < state.stage_index(NEXT_STAGE):
        return False
    for name, rel, text in ((CV_ARTIFACT, CV_TXT, result["cv_text"]), (JD_ARTIFACT, JD_TXT, result["jd_text"])):
        entry = state.artifact(st, name)
        if entry is None or entry["stale"] or not (run_dir / rel).is_file():
            return False
        if entry["sha256"] != jsonio.sha256_bytes(text.encode("utf-8")):
            return False
    return True


def _run(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    try:
        result = _ingest(run_dir, st)
    except CvtError as err:
        st["status"] = "failed"
        state.add_error(st, err.err_id, err.message)
        state.add_history(st, COMMAND, f"failed: {err.err_id}")
        state.save(run_dir, st)
        raise
    unchanged = _unchanged(st, run_dir, result)
    if not unchanged:
        _write_text(run_dir / CV_TXT, result["cv_text"])
        _write_text(run_dir / JD_TXT, result["jd_text"])
        state.record_artifact(run_dir, st, CV_ARTIFACT, CV_TXT)
        state.record_artifact(run_dir, st, JD_ARTIFACT, JD_TXT)
        state.set_stage(st, NEXT_STAGE)
    else:
        st["status"] = "ok"
    st["ingest"] = result["ingest"]
    state.add_history(st, COMMAND, "unchanged" if unchanged else f"method={st['ingest']['method']}")
    state.save(run_dir, st)

    info = st["ingest"]
    warnings = info["warnings"]
    shown = warnings[:MAX_JSON_WARNINGS] if not getattr(args, "all", False) else warnings
    data = {
        "method": info["method"], "pages": info["pages"], "chars": info["chars"],
        "jd_chars": len(result["jd_text"]), "scanned_suspect": info["scanned_suspect"],
        "warning_count": len(warnings), "warnings": shown,
        "cv_txt": CV_TXT, "jd_txt": JD_TXT, "unchanged": unchanged,
    }
    human = "\n".join([
        f"method: {info['method']}, pages: {info['pages']}",
        f"chars: cv={info['chars']} jd={len(result['jd_text'])}",
        f"warnings: {len(warnings)}",
    ])
    return output.emit(args, run=run_dir.name, stage=st["stage"], data=data, human=human,
                       next_action=st["next_action"])


def register(subparsers) -> None:
    p = subparsers.add_parser("ingest", help="extract and clean the CV and JD text (cv.txt, jd.txt)")
    p.add_argument("run", metavar="RUN", help="run slug, run directory, or 'latest'")
    p.set_defaults(func=_run)
