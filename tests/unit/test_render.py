"""WP-12: render model, Typst build, PDF/PNG/Markdown outputs, and `cvt render`."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from pypdf import PdfReader

from conftest import REPO_ROOT, SKILL_DIR
from cvtlib import cli, jsonio, render, schemas, state
from cvtlib.errors import CvtError, ExitCode

FIXTURES = REPO_ROOT / "tests" / "fixtures"
JUNIOR_TAILORED = FIXTURES / "golden" / "junior" / "tailored.json"
ARTIFACT_DIR = REPO_ROOT / ".cache" / "test-artifacts" / "render"
TEMPLATES = SKILL_DIR / "assets" / "templates"
SENIOR_COMPACT_MAX_PAGES = 3
JUNIOR_PAGES = 1
SECTION_ORDER = ("SUMMARY", "SKILLS", "EXPERIENCE", "CERTIFICATIONS", "EDUCATION")
MARKUP_PROBE = '#eval("1") and *bold* and _under_ and $x^2$ and #raw("z")'
FONT_FILE_KEYS = ("/FontFile", "/FontFile2", "/FontFile3")

needs_pdftotext = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext not installed")


def _fixture(name: str, **theme: str) -> dict:
    model = json.loads((FIXTURES / "render" / name).read_text(encoding="utf-8"))
    model["theme"].update({"template": "modern", **theme})
    return model


def _tailored() -> dict:
    return json.loads(JUNIOR_TAILORED.read_text(encoding="utf-8"))


def _build(tailored: dict, **kw) -> dict:
    opts = {"dropped_ids": set(), "density": "standard", "draft": False, "paper": "us-letter", "template": "modern"}
    return render.build_render_model(tailored, **{**opts, **kw})


def _compile(tmp_path: Path, model: dict, name: str = "cv.pdf") -> tuple[Path, int]:
    typ = render.write_build(tmp_path, model, "modern")
    pdf = tmp_path / name
    return pdf, render.compile_pdf(tmp_path, typ, pdf)


def _fonts_embedded(reader: PdfReader) -> bool:
    found = False
    for page in reader.pages:
        for font in (page["/Resources"].get("/Font") or {}).values():
            font = font.get_object()
            descendants = [d.get_object() for d in font.get("/DescendantFonts", [])] or [font]
            for d in descendants:
                descriptor = d["/FontDescriptor"].get_object()
                if not any(key in descriptor for key in FONT_FILE_KEYS):
                    return False
                found = True
    return found


@pytest.fixture
def run_dir(workspace: Path, tmp_path: Path) -> Path:
    cv = tmp_path / "cv.txt"
    cv.write_text("Jamie Rivera\n", encoding="utf-8")
    run = state.create_run(cv, "text", "pasted", "Junior DevOps Engineer", {"template": "modern"}, slug="render-test")
    shutil.copyfile(JUNIOR_TAILORED, run / "tailored.json")
    st = state.load(run)
    state.record_artifact(run, st, "tailored", "tailored.json")
    state.set_stage(st, "approved")
    state.save(run, st)
    return run


def _set_stage(run: Path, stage: str) -> None:
    st = state.load(run)
    state.set_stage(st, stage)
    state.save(run, st)


# ---------------------------------------------------------------- render model


def test_junior_model_validates_and_orders_sections() -> None:
    model = _build(_tailored())
    assert schemas.validate(model, "render-model") == []
    assert [s["kind"] for s in model["sections"]] == ["summary", "skills", "experience", "certifications", "education"]
    assert model["meta"]["title"] == "Jamie Rivera — CV — Junior DevOps Engineer"
    assert model["meta"]["author"] == "Jamie Rivera"
    assert model["theme"]["accent"] == render.DEFAULT_ACCENT
    assert model["meta"]["keywords"] == model["meta"]["keywords"][: render.MAX_KEYWORDS]
    assert len(model["meta"]["keywords"]) <= render.MAX_KEYWORDS and model["meta"]["keywords"]


def test_certification_links_follow_the_profile_url() -> None:
    tailored = _tailored()
    cert = tailored["certifications"][0]
    cert["url"] = "https://www.credly.com/badges/example"
    model = _build(tailored)
    section = next(s for s in model["sections"] if s["kind"] == "certifications")
    assert section["link_lines"][0] == {"text": cert["name"], "url": cert["url"]}
    assert f"[{cert['name']}]({cert['url']})" in render.render_markdown(model)


def test_contacts_order_and_labels() -> None:
    t = _tailored()
    t["header"].update({
        "phone": "+1 (555) 010-0100",
        "links": [
            {"label": "GitHub", "url": "https://github.com/jamie-dev/"},
            {"label": "Site", "url": "www.jamie.example/?utm=1"},
            {"label": "LinkedIn", "url": "https://www.linkedin.com/in/jamie-r"},
        ],
    })
    contacts = _build(t)["header"]["contacts"]
    assert [c["kind"] for c in contacts] == ["email", "phone", "location", "website", "linkedin", "github"]
    assert contacts[0]["url"] == "mailto:jamie.rivera@example.com"
    assert contacts[1]["url"] == "tel:+15550100100"
    assert contacts[2]["url"] == ""
    assert [c["text"] for c in contacts[3:]] == ["jamie.example", "linkedin.com/in/jamie-r", "github.com/jamie-dev"]
    assert contacts[3]["url"] == "https://www.jamie.example/?utm=1"


def test_dropped_ids_fold_engagements_into_collapsed_line() -> None:
    t = _tailored()
    bullet = copy.deepcopy(t["experience"][0]["bullets"][0])
    engagements = []
    for n, (name, role, count) in enumerate((("Acme Corp", "SRE", 2), ("Globex", "Platform Engineer", 1), ("Initech", "Consultant", 0)), 1):
        bullets = []
        for m in range(1, count + 1):
            b = copy.deepcopy(bullet)
            b["id"] = f"t-exp-1.e{n}.b{m}"
            bullets.append(b)
        engagements.append({"id": f"t-exp-1.e{n}", "profile_id": f"exp-1.e{n}", "kind": "client", "name": name,
                            "role_label": role, "bullets": bullets, "priority": 2, "review": "pending"})
    t["experience"][0]["engagements"] = engagements
    assert schemas.validate(t, "tailored") == []

    entry = _build(t)["sections"][2]["entries"][0]
    assert [s["heading"] for s in entry["subentries"]] == ["Acme Corp", "Globex"]
    assert entry["collapsed_line"] == "Also: Initech (Consultant)"

    entry = _build(t, dropped_ids={"t-exp-1.e2.b1", "t-exp-1.b6"})["sections"][2]["entries"][0]
    assert [s["heading"] for s in entry["subentries"]] == ["Acme Corp"]
    assert entry["collapsed_line"] == "Also: Globex (Platform Engineer) · Initech (Consultant)"
    assert len(entry["bullets"]) == 5


def test_dropped_certification_and_skill_group_disappear() -> None:
    t = _tailored()
    model = _build(t, dropped_ids={"t-cert-1", t["skills"][0]["id"]})
    kinds = [s["kind"] for s in model["sections"]]
    assert "certifications" not in kinds
    skills = next(s for s in model["sections"] if s["kind"] == "skills")
    assert len(skills["skill_rows"]) == len(t["skills"]) - 1


def test_earlier_experience_lines() -> None:
    t = _tailored()
    t["earlier_experience"] = {
        "include": True, "review": "pending",
        "items": [{"profile_id": "exp-9", "employer": "Pinecrest Hosting", "title": "Systems Administrator", "start_date": "2010-03", "end_date": "2010-11"}],
    }
    section = next(s for s in _build(t)["sections"] if s["kind"] == "earlier")
    assert section["lines"] == ["Pinecrest Hosting — Systems Administrator (2010)"]
    t["earlier_experience"]["include"] = False
    assert "earlier" not in [s["kind"] for s in _build(t)["sections"]]


@pytest.mark.parametrize(("start", "end", "expected"), [
    ("2024-02", "present", "Feb 2024 – Present"),
    ("2019-06", "2022-02", "Jun 2019 – Feb 2022"),
    ("2016", "2019", "2016 – 2019"),
    ("2016", "", "2016"),
    ("", "2023-08", "Aug 2023"),
    ("", "", ""),
])
def test_format_range(start: str, end: str, expected: str) -> None:
    assert render.format_range(start, end) == expected


def test_format_date() -> None:
    assert [render.format_date(d) for d in ("2024-12", "present", "2020", "")] == ["Dec 2024", "Present", "2020", ""]


def test_invalid_density_is_usage_error() -> None:
    with pytest.raises(CvtError) as exc:
        _build(_tailored(), density="tiny")
    assert exc.value.code == ExitCode.USAGE


def test_markdown_has_sections_and_bullets() -> None:
    md = render.render_markdown(_build(_tailored()))
    assert md.startswith("# Jamie Rivera")
    assert "## Recent Experience" in md and "### Brightfield Logistics — Junior DevOps Engineer" in md
    assert "*Columbus, OH · Feb 2024 – Present*" in md and "- Built GitHub Actions pipelines" in md


# ---------------------------------------------------------------- compile


def test_junior_fixture_is_one_page_with_metadata(tmp_path: Path) -> None:
    pdf, pages = _compile(tmp_path, _fixture("junior-render.json"))
    assert pages == JUNIOR_PAGES
    reader = PdfReader(str(pdf))
    assert reader.metadata.title == "Jamie Rivera — CV — Junior Data Analyst"
    assert reader.metadata.author == "Jamie Rivera"
    assert _fonts_embedded(reader)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf, ARTIFACT_DIR / "junior.pdf")


def test_senior_compact_fits_three_pages_and_png_count_matches(tmp_path: Path) -> None:
    model = _fixture("senior-render.json", density="compact")
    pdf, pages = _compile(tmp_path, model)
    assert 1 <= pages <= SENIOR_COMPACT_MAX_PAGES
    pngs = render.compile_png(tmp_path, tmp_path / "build" / "cv.typ", tmp_path / "pages", ppi=60)
    assert len(pngs) == pages
    assert [p.name for p in pngs] == [f"page-{n}.png" for n in range(1, pages + 1)]
    assert all(p.stat().st_size > 0 for p in pngs)


def test_senior_standard_artifacts_for_reviewer(tmp_path: Path) -> None:
    pdf, pages = _compile(tmp_path, _fixture("senior-render.json", density="standard"))
    pngs = render.compile_png(tmp_path, tmp_path / "build" / "cv.typ", tmp_path / "pages", ppi=render.DEFAULT_PPI)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for png in pngs:
        shutil.copyfile(png, ARTIFACT_DIR / f"senior-standard-{png.name}")
    shutil.copyfile(pdf, ARTIFACT_DIR / "senior-standard.pdf")
    assert (ARTIFACT_DIR / "senior-standard-page-1.png").is_file()
    assert len(pngs) == pages


@needs_pdftotext
def test_text_extraction_keeps_dates_on_employer_line_and_section_order(tmp_path: Path) -> None:
    model = _build(_tailored(), density="comfortable")
    pdf, _ = _compile(tmp_path, model)
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    assert re.search(r"Brightfield Logistics\s+Feb 2024 – Present", text)
    assert re.search(r"Cedar Valley College\s+Jul 2023 – Dec 2023", text)
    positions = [text.upper().find(name) for name in SECTION_ORDER]
    assert all(p >= 0 for p in positions), positions
    assert positions == sorted(positions)


def test_pdf_is_tagged_single_language_and_has_page_numbers(tmp_path: Path) -> None:
    pdf, pages = _compile(tmp_path, _build(_tailored()))
    reader = PdfReader(str(pdf))
    assert "/StructTreeRoot" in reader.trailer["/Root"]
    assert reader.trailer["/Root"].get("/Lang") == "en"
    assert f"{pages} / {pages}" in reader.pages[-1].extract_text()


def test_markup_in_data_renders_literally(tmp_path: Path) -> None:
    t = _tailored()
    t["experience"][0]["bullets"][0]["text"] = MARKUP_PROBE
    t["header"]["headline"] = "*Headline* #panic()"
    pdf, _ = _compile(tmp_path, _build(t))
    text = " ".join(page.extract_text() for page in PdfReader(str(pdf)).pages)
    for piece in ("#eval(", "*bold*", "_under_", "$x^2$", "#raw(", "*Headline* #panic()"):
        assert piece in text, piece


def test_draft_footer_and_confirm_highlight(tmp_path: Path) -> None:
    model = _build(_tailored(), draft=True)
    model["sections"][0]["paragraphs"] = ["Ran [[CONFIRM: number of services]] services."]
    pdf, _ = _compile(tmp_path, model)
    text = PdfReader(str(pdf)).pages[0].extract_text()
    assert "DRAFT: unconfirmed items" in text and "[[CONFIRM: number of services]]" in text
    (tmp_path / "final").mkdir()
    final, _ = _compile(tmp_path / "final", _build(_tailored(), draft=False))
    assert "DRAFT" not in PdfReader(str(final)).pages[0].extract_text()


# ---------------------------------------------------------------- run-level behavior


def test_render_run_writes_all_outputs(run_dir: Path) -> None:
    result = render.render_run(run_dir, png=True, ppi=60)
    assert result.pages == JUNIOR_PAGES and result.pdf == run_dir / "cv.pdf" and result.pdf.is_file()
    assert (run_dir / "cv.md").is_file() and (run_dir / "build" / "render.json").is_file()
    assert (run_dir / "build" / "cv.typ").is_file() and (run_dir / "build" / "common.typ").is_file()
    assert len(result.pngs) == result.pages
    assert "not fitted; run cvt fit" in result.warnings
    assert schemas.validate(jsonio.load_json(run_dir / "build" / "render.json"), "render-model") == []


def test_render_run_uses_matching_fit_and_ignores_stale_fit(run_dir: Path) -> None:
    tailored = jsonio.load_json(run_dir / "tailored.json")
    fit = {
        "schema_version": "1", "run_id": "x", "tailored_version": tailored["version"], "page_target": 1, "pages": 1,
        "density": "compact", "dropped_ids": ["t-exp-2.b1"], "renders": 1, "underfilled": True, "log": [],
    }
    jsonio.dump_json(fit, run_dir / "fit.json")
    result = render.render_run(run_dir)
    assert result.fitted and result.density == "compact" and not result.warnings
    model = jsonio.load_json(run_dir / "build" / "render.json")
    assert model["theme"]["density"] == "compact"
    assert "Resolved about 30 support tickets" not in json.dumps(model)
    fit["tailored_version"] += 1
    jsonio.dump_json(fit, run_dir / "fit.json")
    result = render.render_run(run_dir)
    assert not result.fitted and result.density == render.DEFAULT_DENSITY and result.warnings


def test_render_command_stage_and_artifacts(run_dir: Path, capsys: pytest.CaptureFixture) -> None:
    assert cli.main(["render", run_dir.name, "--json"]) == 0
    env = json.loads(capsys.readouterr().out)
    assert env["ok"] and env["data"]["pages"] == JUNIOR_PAGES and env["data"]["pdf"] == "cv.pdf"
    st = state.load(run_dir)
    assert st["stage"] == "rendered"
    names = {a["name"] for a in st["artifacts"]}
    assert {"render_model", "typst_source", "pdf", "markdown_fallback"} <= names
    assert state.artifact(st, "pdf")["stale"] is False


def test_render_before_approval_is_draft_and_keeps_stage(run_dir: Path, capsys: pytest.CaptureFixture) -> None:
    _set_stage(run_dir, "awaiting_approval")
    assert cli.main(["render", run_dir.name, "--json"]) == 0
    env = json.loads(capsys.readouterr().out)
    assert env["data"]["draft"] is True
    assert state.load(run_dir)["stage"] == "awaiting_approval"
    assert jsonio.load_json(run_dir / "build" / "render.json")["meta"]["draft"] is True


def test_pages_flag_is_view_only(run_dir: Path, capsys: pytest.CaptureFixture) -> None:
    assert cli.main(["render", run_dir.name]) == 0
    _set_stage(run_dir, "validated")
    before = (run_dir / "state.json").read_bytes()
    pdf_hash = jsonio.sha256_file(run_dir / "cv.pdf")
    capsys.readouterr()
    assert cli.main(["render", run_dir.name, "--pages", "1", "--ppi", "50", "--json"]) == 0
    env = json.loads(capsys.readouterr().out)
    assert env["stage"] == "validated" and env["data"]["pngs"] == ["pages/page-1.png"]
    assert (run_dir / "pages" / "page-1.png").is_file()
    assert (run_dir / "state.json").read_bytes() == before
    assert state.load(run_dir)["stage"] == "validated"
    assert jsonio.sha256_file(run_dir / "cv.pdf") == pdf_hash
    assert not any(a["stale"] for a in state.load(run_dir)["artifacts"])


def test_pages_without_pdf_is_state_error(run_dir: Path, capsys: pytest.CaptureFixture) -> None:
    assert cli.main(["render", run_dir.name, "--pages", "1"]) == int(ExitCode.STATE)
    assert "cvt fit" in capsys.readouterr().err


def test_pages_out_of_range_and_garbage_are_usage_errors(run_dir: Path) -> None:
    assert cli.main(["render", run_dir.name]) == 0
    assert cli.main(["render", run_dir.name, "--pages", "9"]) == int(ExitCode.USAGE)
    assert cli.main(["render", run_dir.name, "--pages", "one"]) == int(ExitCode.USAGE)


def test_classic_template_requires_installation(run_dir: Path, capsys: pytest.CaptureFixture) -> None:
    code = cli.main(["render", run_dir.name, "--template", "classic"])
    if (TEMPLATES / "classic.typ").is_file():
        assert code == 0
    else:
        assert code == int(ExitCode.USAGE)
        assert "not installed" in capsys.readouterr().err


def test_missing_backend_writes_markdown_and_exits_3(
    run_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.setattr(render, "detect_backend", lambda: "none")
    assert cli.main(["render", run_dir.name]) == int(ExitCode.MISSING_DEPENDENCY)
    assert "E_TYPST_MISSING" in capsys.readouterr().err
    assert (run_dir / "cv.md").is_file() and (run_dir / "build" / "render.json").is_file()
    assert not (run_dir / "cv.pdf").exists()
    assert state.artifact(state.load(run_dir), "markdown_fallback") is not None


def test_render_run_is_deterministic(run_dir: Path) -> None:
    render.render_run(run_dir)
    first = hashlib.sha256((run_dir / "cv.pdf").read_bytes()).hexdigest()
    render.render_run(run_dir)
    assert hashlib.sha256((run_dir / "cv.pdf").read_bytes()).hexdigest() == first


@pytest.mark.skipif(shutil.which("typst") is None, reason="typst binary not installed")
def test_binary_backend_matches_python_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = _build(_tailored())
    (tmp_path / "py").mkdir()
    _, python_pages = _compile(tmp_path / "py", model)
    monkeypatch.setattr(render, "detect_backend", lambda: "binary")
    (tmp_path / "bin").mkdir()
    pdf, pages = _compile(tmp_path / "bin", model)
    assert pages == python_pages and PdfReader(str(pdf)).metadata.author == "Jamie Rivera"
    pngs = render.compile_png(tmp_path / "bin", tmp_path / "bin" / "build" / "cv.typ", tmp_path / "bin" / "pages", ppi=50)
    assert [p.name for p in pngs] == [f"page-{n}.png" for n in range(1, pages + 1)]


def test_pages_fallback_without_pdftoppm(run_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    render.render_run(run_dir)
    real_which = shutil.which
    monkeypatch.setattr(render.shutil, "which", lambda name, *a, **k: None if name == render.PDFTOPPM_BINARY else real_which(name, *a, **k))
    assert [p.name for p in render.rasterize_pages(run_dir, [1], ppi=50)] == ["page-1.png"]
    assert (run_dir / "pages" / "page-1.png").stat().st_size > 0
