"""WP-02: bundled fonts, presets, and render-model fixtures."""

from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

import jsonschema
import pytest
import typst
from pypdf import PdfReader

from conftest import REPO_ROOT, SKILL_DIR

ASSETS = SKILL_DIR / "assets"
FONTS = ASSETS / "fonts"
PRESETS = ASSETS / "templates" / "presets.json"
SCHEMA = ASSETS / "schemas" / "render-model.schema.json"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "render"
FONTS_DOC = FONTS / "FONTS.md"

SPEC_PRESETS = {
    "floor": {"body_pt": 9.5, "margin_in": 0.5},
    "comfortable": {"body_pt": 10.5, "margin_in": 0.7, "leading_em": 0.62, "section_gap_pt": 9},
    "standard": {"body_pt": 10.0, "margin_in": 0.6, "leading_em": 0.58, "section_gap_pt": 7},
    "compact": {"body_pt": 9.5, "margin_in": 0.5, "leading_em": 0.55, "section_gap_pt": 5},
}
FAMILIES = ("Source Sans 3", "Libertinus Serif")
FONT_FILE_COUNT = 8
MAX_FONTS_BYTES = 6 * 1024 * 1024
SHA256_RE = re.compile(r"`([0-9a-f]{64})`")
SENIOR_EMPLOYERS = 4
SENIOR_CERTS = 8
SENIOR_CLIENT_SUBENTRIES = 3
JUNIOR_ROLES = 2


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _section(model: dict, kind: str) -> dict:
    return next(s for s in model["sections"] if s["kind"] == kind)


@pytest.mark.parametrize("name", ["senior-render.json", "junior-render.json"])
def test_fixture_validates(name: str) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(_load(name))


def test_senior_fixture_shape() -> None:
    model = _load("senior-render.json")
    assert model["meta"]["draft"] is True
    assert json.dumps(model).count("[[CONFIRM: number of services]]") == 1
    entries = _section(model, "experience")["entries"]
    assert len(entries) == SENIOR_EMPLOYERS
    assert any(len(e.get("subentries", [])) == SENIOR_CLIENT_SUBENTRIES for e in entries)
    assert _section(model, "earlier")["lines"]
    assert len(_section(model, "certifications")["lines"]) == SENIOR_CERTS
    assert _section(model, "education")["entries"]


def test_junior_fixture_shape() -> None:
    model = _load("junior-render.json")
    assert model["meta"]["draft"] is False
    assert len(_section(model, "experience")["entries"]) == JUNIOR_ROLES


def test_presets_match_spec() -> None:
    assert json.loads(PRESETS.read_text(encoding="utf-8")) == SPEC_PRESETS


def test_compact_equals_floor() -> None:
    presets = json.loads(PRESETS.read_text(encoding="utf-8"))
    for key, value in presets["floor"].items():
        assert presets["compact"][key] == value


def test_font_licenses_and_size() -> None:
    assert len(list(FONTS.glob("*/OFL.txt"))) == 2
    otfs = list(FONTS.glob("*/*.otf"))
    assert len(otfs) == FONT_FILE_COUNT
    assert sum(p.stat().st_size for p in FONTS.rglob("*") if p.is_file()) < MAX_FONTS_BYTES


def test_fonts_md_checksums_match_files() -> None:
    documented = set(SHA256_RE.findall(FONTS_DOC.read_text(encoding="utf-8")))
    actual = {hashlib.sha256(p.read_bytes()).hexdigest() for p in FONTS.glob("*/*.otf")}
    assert documented == actual


@pytest.mark.parametrize("family", FAMILIES)
def test_family_compiles_and_embeds(family: str) -> None:
    source = f'#set text(font: "{family}", size: 12pt)\nHello fonts, 0123456789 *bold* _italic_\n'
    pdf = typst.compile(
        input=source.encode("utf-8"),
        font_paths=[str(FONTS)],
        ignore_system_fonts=True,
    )
    reader = PdfReader(io.BytesIO(pdf))
    names: set[str] = set()
    for page in reader.pages:
        resources = page.get("/Resources", {})
        for ref in resources.get("/Font", {}).values():
            names.add(str(ref.get_object().get("/BaseFont", "")))
    compact = family.replace(" ", "").lower()
    assert any(compact in n.replace(" ", "").lower() for n in names), names
