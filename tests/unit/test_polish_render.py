"""Generic CV extract and render: the same reader as ingest, every installed template, no fact dropping."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import REPO_ROOT
from cvtlib import ingest, render
from cvtlib.errors import CvtError, ExitCode

import polish_render

CV_TEXT = REPO_ROOT / "tests" / "fixtures" / "cv" / "jamie-rivera-junior.txt"
JUNIOR_MODEL = REPO_ROOT / "tests" / "fixtures" / "render" / "junior-render.json"
SIDEBAR = REPO_ROOT / ".claude" / "skills" / "tailoring-cvs" / "assets" / "templates" / "sidebar.typ"
needs_backend = pytest.mark.skipif(render.detect_backend() == "none", reason="no Typst backend installed")


def test_extract_matches_ingest_cleaner() -> None:
    text = polish_render.extract_text(CV_TEXT)
    cleaned, _warnings = ingest.clean_cv_text(ingest.extract_cv(CV_TEXT).text)
    assert text == cleaned
    assert "Jamie Rivera" in text


def test_extract_missing_file_is_usage(tmp_path: Path) -> None:
    with pytest.raises(CvtError) as caught:
        polish_render.extract_text(tmp_path / "missing.pdf")
    assert caught.value.code == ExitCode.USAGE and caught.value.err_id == "E_USAGE"


def test_extract_empty_and_docx_are_input_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("   \n", encoding="utf-8")
    with pytest.raises(CvtError) as caught:
        polish_render.extract_text(empty)
    assert caught.value.code == ExitCode.INPUT and caught.value.err_id == "E_CV_EMPTY"

    docx = tmp_path / "cv.docx"
    docx.write_bytes(b"")
    assert polish_render.main(["extract", str(docx)]) == int(ExitCode.INPUT)
    assert "E_CV_DOCX" in capsys.readouterr().err


def test_render_rejects_a_model_that_fails_the_schema(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    model = tmp_path / "render.json"
    model.write_text('{"schema_version": "1"}\n', encoding="utf-8")
    assert polish_render.main(["render", str(model), str(tmp_path / "out")]) == int(ExitCode.CHECK_FAILED)
    assert "E_SCHEMA" in capsys.readouterr().err


def test_sidebar_template_has_no_eval() -> None:
    source = SIDEBAR.read_text(encoding="utf-8")
    assert "eval(" not in source
    assert "Less ATS-safe" in source
    assert 'json(sys.inputs.at("data", default: "render.json"))' in source


@needs_backend
def test_render_writes_every_template(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "jamie-generic"
    assert polish_render.main(["render", str(JUNIOR_MODEL), str(out)]) == 0
    printed = capsys.readouterr().out
    for template in render.TEMPLATES:
        pdf = out / f"Jamie-Rivera-CV-{template}.pdf"
        assert pdf.is_file(), template
        assert f"{template}\t" in printed
    assert (out / "Jamie-Rivera-CV.md").is_file()
    assert "markdown\t" in printed
    if shutil.which("pdftotext"):
        assert "sidebar-layout\tpage 1" in printed
    assert not (out / ".build").exists()
