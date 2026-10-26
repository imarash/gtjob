"""WP-17: the `classic` Typst template compiles both render fixtures and keeps the shared template contract."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from pypdf import PdfReader

from conftest import REPO_ROOT, SKILL_DIR
from cvtlib import render

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "render"
ARTIFACT_DIR = REPO_ROOT / ".cache" / "test-artifacts" / "render"
TEMPLATE = SKILL_DIR / "assets" / "templates" / "classic.typ"
TEMPLATE_NAME = "classic"
JUNIOR_PAGES = 1
SENIOR_COMPACT_MAX_PAGES = 3
FONT_FAMILY = "Libertinus"
FONT_FILE_KEYS = ("/FontFile", "/FontFile2", "/FontFile3")
SECTION_ORDER = ("SUMMARY", "SKILLS", "EXPERIENCE", "CERTIFICATIONS", "EDUCATION")
MARKUP_PROBE = '#eval("1") and *bold* and _under_ and $x^2$ and #raw("z")'
ARTIFACT_PPI = 80

needs_pdftotext = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext not installed")
needs_backend = pytest.mark.skipif(render.detect_backend() == "none", reason="no Typst backend installed")
pytestmark = needs_backend


def _model(name: str, **theme: str) -> dict:
    model = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    model["theme"].update({"template": TEMPLATE_NAME, **theme})
    return model


def _compile(tmp_path: Path, model: dict) -> tuple[Path, int]:
    typ = render.write_build(tmp_path, model, TEMPLATE_NAME)
    pdf = tmp_path / "cv.pdf"
    return pdf, render.compile_pdf(tmp_path, typ, pdf)


def _font_names(reader: PdfReader) -> list[str]:
    names: list[str] = []
    for page in reader.pages:
        for font in (page["/Resources"].get("/Font") or {}).values():
            font = font.get_object()
            names.append(str(font.get("/BaseFont", "")))
            for d in font.get("/DescendantFonts", []):
                descriptor = d.get_object()["/FontDescriptor"].get_object()
                assert any(key in descriptor for key in FONT_FILE_KEYS), "font not embedded"
    return names


def _png_artifacts(tmp_path: Path, label: str) -> list[Path]:
    pngs = render.compile_png(tmp_path, tmp_path / "build" / "cv.typ", tmp_path / "pages", ppi=ARTIFACT_PPI)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for png in pngs:
        dest = ARTIFACT_DIR / f"classic-{label}-{png.name}"
        shutil.copyfile(png, dest)
        out.append(dest)
    return out


def test_template_file_has_no_eval_and_reads_only_contract_inputs() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")
    assert "eval(" not in source
    assert 'json(sys.inputs.at("data", default: "render.json"))' in source
    assert 'json(sys.inputs.at("presets", default: "presets.json"))' in source


def test_junior_fixture_fits_one_page_with_libertinus_and_metadata(tmp_path: Path) -> None:
    pdf, pages = _compile(tmp_path, _model("junior-render.json"))
    assert pages == JUNIOR_PAGES
    reader = PdfReader(str(pdf))
    assert reader.metadata.title == "Jamie Rivera — CV — Junior Data Analyst"
    assert reader.metadata.author == "Jamie Rivera"
    fonts = _font_names(reader)
    assert fonts and all(FONT_FAMILY in f for f in fonts), fonts
    shutil.copyfile(pdf, (ARTIFACT_DIR.mkdir(parents=True, exist_ok=True) or ARTIFACT_DIR) / "classic-junior.pdf")
    assert (_png_artifacts(tmp_path, "junior")[0]).is_file()


def test_senior_compact_fits_three_pages(tmp_path: Path) -> None:
    pdf, pages = _compile(tmp_path, _model("senior-render.json", density="compact"))
    assert 1 <= pages <= SENIOR_COMPACT_MAX_PAGES
    assert all(FONT_FAMILY in f for f in _font_names(PdfReader(str(pdf))))
    shutil.copyfile(pdf, (ARTIFACT_DIR.mkdir(parents=True, exist_ok=True) or ARTIFACT_DIR) / "classic-senior-compact.pdf")
    pngs = _png_artifacts(tmp_path, "senior-compact")
    assert len(pngs) == pages and all(p.stat().st_size > 0 for p in pngs)


@needs_pdftotext
def test_text_extraction_keeps_section_order_and_employer_with_dates(tmp_path: Path) -> None:
    pdf, _ = _compile(tmp_path, _model("junior-render.json", density="comfortable"))
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    lines = [line.strip().upper() for line in text.splitlines()]
    positions = [lines.index(name) if name in lines else -1 for name in SECTION_ORDER]
    assert all(p >= 0 for p in positions), positions
    assert positions == sorted(positions)
    model = _model("junior-render.json")
    entry = next(s for s in model["sections"] if s["kind"] == "experience")["entries"][0]
    assert re.search(re.escape(entry["heading"]) + r"\s+" + re.escape(entry["dates"]), text)
    assert " ".join(text.split()).upper().startswith(model["header"]["name"].upper())


def test_markup_in_data_renders_literally(tmp_path: Path) -> None:
    model = _model("junior-render.json")
    experience = next(s for s in model["sections"] if s["kind"] == "experience")
    experience["entries"][0]["bullets"][0] = MARKUP_PROBE
    model["header"]["headline"] = "*Headline* #panic()"
    pdf, _ = _compile(tmp_path, model)
    text = " ".join(page.extract_text() for page in PdfReader(str(pdf)).pages)
    for piece in ("#eval(", "*bold*", "_under_", "$x^2$", "#raw(", "*Headline* #panic()"):
        assert piece in text, piece


def test_draft_footer_and_confirm_text_match_modern_behavior(tmp_path: Path) -> None:
    model = _model("junior-render.json")
    model["meta"]["draft"] = True
    summary = next(s for s in model["sections"] if s["kind"] == "summary")
    summary["paragraphs"] = ["Ran [[CONFIRM: number of services]] services."]
    pdf, _ = _compile(tmp_path, model)
    text = PdfReader(str(pdf)).pages[0].extract_text()
    assert "DRAFT: unconfirmed items" in text and "[[CONFIRM: number of services]]" in text
    model["meta"]["draft"] = False
    (tmp_path / "final").mkdir()
    final, _ = _compile(tmp_path / "final", model)
    assert "DRAFT" not in PdfReader(str(final)).pages[0].extract_text()
