"""WP-09: CV/JD ingest. No network beyond 127.0.0.1, no Anthropic API."""

from __future__ import annotations

import json
import shutil
import sys
import threading
import types
import unicodedata
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from cvtlib import cli, ingest, jsonio, state
from cvtlib.errors import CvtError, ExitCode

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
JUNIOR_CV = FIXTURES / "cv" / "jamie-rivera-junior.txt"
JD_HTML = FIXTURES / "ingest" / "jd-page.html"
PAGED_CV = FIXTURES / "ingest" / "cv-paged.txt"
JD_TEXT = "# Platform Engineer\n\nRun things.\n"
ZWSP = "\u200b"
EMAIL = "avery@sample.test"
SAMPLE_PRIVATE_FILE = FIXTURES / "private" / "sample-ingest.json"  # git-ignored; holds the real sample's literals

TYPST_CV = r"""
#set page(
  paper: "us-letter",
  header: context if counter(page).get().first() > 1 [
    Avery Sample #h(1fr) AVERY_EMAIL #"\u{2666}" www.sample.test
  ] else [
    Avery Sample #h(1fr) www.sample.test
  ],
  footer: align(right)[#context counter(page).display()],
)
#set text(font: ("DejaVu Sans", "Libertinus Serif"), size: 10pt)
#let bullets(tag, n) = for i in range(n) [
  \u{2756}#"\u{200B}" Maintained #tag service number #i and wrote the runbooks for the on-call rotation at scale \
]
= Experience
#grid(columns: (1fr, auto))[Acme Corp, Austin, TX#"\u{200B}"][Feb 2024 - Present]
#bullets("alpha", 8)
#pagebreak()
#grid(columns: (1fr, auto))[Initech, Remote][Jan 2020 - Jan 2024]
#bullets("beta", 8)
#pagebreak()
#grid(columns: (1fr, auto))[Globex, Remote][Jan 2016 - Dec 2019]
#bullets("gamma", 8)
""".replace("AVERY_EMAIL", '#"' + EMAIL + '"')


def _typst_pdf(path: Path, source: str = TYPST_CV) -> Path:
    import typst

    path.write_bytes(typst.compile(source.encode("utf-8")))
    return path


@pytest.fixture
def synthetic_pdf(tmp_path: Path) -> Path:
    return _typst_pdf(tmp_path / "cv.pdf")


def _make_run(cv: Path, jd_kind: str = "text", jd_ref: str = "pasted", jd_text: str | None = JD_TEXT) -> Path:
    return state.create_run(cv, jd_kind, jd_ref, jd_text, {})


def _ingest(run_dir: Path, *extra: str) -> int:
    return cli.main(["ingest", str(run_dir), *extra])


# ---------------------------------------------------------------------------------------------- PDF cleanup
def test_synthetic_pdf_cleaned(synthetic_pdf, workspace):
    ext = ingest.extract_cv(synthetic_pdf)
    assert ext.pages == 3 and not ext.scanned_suspect
    text, warnings = ingest.clean_cv_text(ext.text)
    assert text.count(EMAIL) == 1
    assert text.count("Avery Sample") >= 1
    assert not any(g in text for g in ingest.DECORATIVE_GLYPHS)
    assert ZWSP not in text and "\f" not in text
    assert not [line for line in text.splitlines() if ingest.PAGE_NUMBER_RE.match(line)]
    assert text.index("alpha service number 0") < text.index("alpha service number 7") < text.index("beta service number 0")
    assert text.count("service number 7") == 3  # bullets of all three pages kept
    acme = next(line for line in text.splitlines() if "Acme Corp" in line)
    assert "Feb 2024 - Present" in acme
    assert any("repeated header" in w for w in warnings)


def test_ingest_command_end_to_end(synthetic_pdf, workspace, capsys):
    run_dir = _make_run(synthetic_pdf)
    assert _ingest(run_dir) == 0
    out = capsys.readouterr().out
    assert len(out.splitlines()) <= 4
    st = state.load(run_dir)
    assert st["stage"] == "ingested"
    assert {a["name"] for a in st["artifacts"]} == {"cv_txt", "jd_txt"}
    assert st["ingest"]["pages"] == 3 and st["ingest"]["method"] in ("pdftotext", "pypdf")
    assert st["ingest"]["chars"] == len((run_dir / "cv.txt").read_text(encoding="utf-8"))
    assert (run_dir / "jd.txt").read_text(encoding="utf-8").startswith("# Platform Engineer")


def test_ingest_json_has_no_text_bodies(synthetic_pdf, workspace, capsys):
    run_dir = _make_run(synthetic_pdf)
    assert cli.main(["--json", "ingest", str(run_dir)]) == 0
    raw = capsys.readouterr().out
    env = json.loads(raw)
    assert env["ok"] and env["stage"] == "ingested"
    assert "Maintained service" not in raw and "Run things" not in raw
    assert env["data"]["pages"] == 3 and env["data"]["cv_txt"] == "cv.txt"


def test_reingest_unchanged_keeps_stage(synthetic_pdf, workspace, capsys):
    run_dir = _make_run(synthetic_pdf)
    assert _ingest(run_dir) == 0
    st = state.load(run_dir)
    state.set_stage(st, "profiled")
    state.save(run_dir, st)
    assert _ingest(run_dir) == 0
    assert state.load(run_dir)["stage"] == "profiled"
    capsys.readouterr()


def test_pypdf_fallback_when_pdftotext_missing(synthetic_pdf, monkeypatch):
    monkeypatch.setattr(ingest.shutil, "which", lambda name: None)
    ext = ingest.extract_cv(synthetic_pdf)
    assert ext.method == "pypdf" and ext.pages == 3
    text, _ = ingest.clean_cv_text(ext.text)
    assert "Acme Corp" in text and "service number 0" in text
    assert "\ufb01" not in text  # ligatures normalized


def test_missing_both_backends(synthetic_pdf, monkeypatch):
    monkeypatch.setattr(ingest.shutil, "which", lambda name: None)
    monkeypatch.setitem(sys.modules, "pypdf", None)  # makes `import pypdf` raise ImportError
    with pytest.raises(CvtError) as exc:
        ingest.extract_cv(synthetic_pdf)
    assert exc.value.code == ExitCode.MISSING_DEPENDENCY
    assert "brew install poppler" in exc.value.hint


# ------------------------------------------------------------------------------------------ scanned / extras
def _image_only_pdf(path: Path) -> Path:
    return _typst_pdf(path, "#page(width: 200pt, height: 200pt)[#rect(width: 100pt, height: 100pt, fill: red)]")


def test_scanned_pdf_exits_5(tmp_path, workspace, capsys):
    pdf = _image_only_pdf(tmp_path / "scan.pdf")
    with pytest.raises(CvtError) as exc:
        ingest.extract_cv(pdf)
    assert exc.value.code == ExitCode.INPUT
    assert "looks scanned" in exc.value.hint and "OCR is not supported yet" in exc.value.hint
    run_dir = _make_run(pdf)
    assert _ingest(run_dir) == int(ExitCode.INPUT)
    assert "looks scanned" in capsys.readouterr().err
    st = state.load(run_dir)
    assert st["status"] == "failed" and st["stage"] == "initialized" and st["errors"][-1]["code"] == "E_CV_SCANNED"


def _fake_extras(monkeypatch, **fns):
    mod = types.ModuleType("cvtlib.extras")
    for name, fn in fns.items():
        setattr(mod, name, fn)
    monkeypatch.setitem(sys.modules, "cvtlib.extras", mod)


def test_scanned_pdf_uses_ocr_extra(tmp_path, monkeypatch):
    pdf = _image_only_pdf(tmp_path / "scan.pdf")
    _fake_extras(monkeypatch, ocr_pdf=lambda path: "Ocr Person\nSRE at Initech\n")
    ext = ingest.extract_cv(pdf)
    assert ext.method == "ocr" and ext.scanned_suspect and "Initech" in ext.text
    assert any("OCR" in w for w in ext.warnings)


def test_docx_with_and_without_extras(tmp_path, monkeypatch):
    docx = tmp_path / "cv.docx"
    docx.write_bytes(b"PK fake")
    monkeypatch.delitem(sys.modules, "cvtlib.extras", raising=False)
    monkeypatch.setattr(ingest.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(CvtError) as exc:
        ingest.extract_cv(docx)
    assert exc.value.code == ExitCode.INPUT and exc.value.hint == "export the CV as PDF or text"
    _fake_extras(monkeypatch, extract_docx=lambda path: "Docx Person\nEngineer\n")
    ext = ingest.extract_cv(docx)
    assert ext.method == "docx" and "Docx Person" in ext.text


# ------------------------------------------------------------------------------------------------ text path
@pytest.mark.skipif(not JUNIOR_CV.is_file(), reason="WP-04 fixture absent")
def test_junior_txt_is_line_stable(workspace):
    ext = ingest.extract_cv(JUNIOR_CV)
    assert ext.method == "text" and ext.pages == 1
    cleaned, warnings = ingest.clean_cv_text(ext.text)
    expected = [unicodedata.normalize("NFKC", line).rstrip() for line in ext.text.splitlines()]
    assert cleaned.splitlines() == expected
    assert warnings == []


def test_markdown_and_latin1(tmp_path):
    md = tmp_path / "cv.md"
    md.write_text("# Name\n", encoding="utf-8")
    assert ingest.extract_cv(md).method == "markdown"
    txt = tmp_path / "cv.txt"
    txt.write_bytes("Caf\xe9 Engineer".encode("latin-1"))
    ext = ingest.extract_cv(txt)
    assert "Café" in ext.text and ext.warnings


def test_paged_text_fixture_hoists_header_once():
    raw = PAGED_CV.read_text(encoding="utf-8")
    text, warnings = ingest.clean_cv_text(raw)
    lines = text.splitlines()
    assert lines[0] == "Jordan Sample  jordan@sample.test | www.sample.test"
    assert text.count("jordan@sample.test") == 1
    assert [x for x in lines if x.startswith("- ")] == [
        "- Built a thing", "- Ran a thing", "- Second page bullet", "- Third page bullet",
    ]
    assert "\n\n\n\n" not in text  # the 5-blank-line gap on page 3 collapsed
    assert any("moved" in w for w in warnings)


def test_clean_rules():
    raw = "  \u2756\u200b Item\u00a0one  \n\u2666 Updated: Oct 2025\nA \u2666 B\nx      y\n\n\n\n\nEnd\ufb01\n"
    text, warnings = ingest.clean_cv_text(raw)
    assert text.splitlines() == ["  - Item one", "- Updated: Oct 2025", "A | B", "x  y", "", "Endfi"]
    assert warnings == ["stale 'Updated: Oct 2025' line kept for review"]


def test_clean_is_deterministic():
    raw = PAGED_CV.read_text(encoding="utf-8")
    assert ingest.clean_cv_text(raw) == ingest.clean_cv_text(raw)


def test_clean_jd_text_minimal():
    assert ingest.clean_jd_text("A\u00a0B  \r\n\r\n\r\n\r\n\r\n- C\u200b\n") == "A B\n\n- C\n"


# ------------------------------------------------------------------------------------------------ URL path
@pytest.fixture
def jd_server():
    page = JD_HTML.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        user_agent = ""

        def do_GET(self):  # noqa: N802
            type(self).user_agent = self.headers.get("User-Agent", "")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/job", Handler
    server.shutdown()
    server.server_close()


def test_url_jd_is_fetched_stripped_and_stored(synthetic_pdf, workspace, jd_server, capsys):
    url, handler = jd_server
    run_dir = _make_run(synthetic_pdf, "url", url, None)
    assert _ingest(run_dir) == 0
    text = (run_dir / "jd.txt").read_text(encoding="utf-8")
    assert handler.user_agent == "gtjob/0.1"
    assert "Platform Engineer" in text and "- 3+ years running Kubernetes in production" in text
    assert "Terraform & CI/CD" in text and "Join the team." in text
    for gone in ("SHOULD-NOT-APPEAR", "NAV-LINK-TEXT", "color: red", "<p>"):
        assert gone not in text
    stored = (run_dir / "inputs" / "jd.md").read_text(encoding="utf-8")
    assert stored.startswith("<!-- jd-url:") and "Kubernetes" in stored
    st = state.load(run_dir)
    assert st["inputs"]["jd"]["sha256"] == jsonio.sha256_file(run_dir / "inputs" / "jd.md")
    capsys.readouterr()


def test_url_unreachable_exits_5(synthetic_pdf, workspace, capsys):
    run_dir = _make_run(synthetic_pdf, "url", "http://127.0.0.1:9/never", None)
    assert _ingest(run_dir) == int(ExitCode.INPUT)
    err = capsys.readouterr().err
    assert "E_JD_FETCH" in err and "paste the JD text with --jd-text or save it to a file" in err
    assert not (run_dir / "cv.txt").exists()  # nothing written when the JD fails


def test_url_scheme_is_restricted(tmp_path):
    with pytest.raises(CvtError) as exc:
        ingest.load_jd("url", "file:///etc/passwd", _stored(tmp_path))
    assert exc.value.err_id == "E_JD_FETCH" and exc.value.code == ExitCode.INPUT


def _stored(tmp_path: Path) -> Path:
    path = tmp_path / "jd.md"
    path.write_text("<!-- jd-url: x -->\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------------------------- real sample
@pytest.mark.sample
def test_real_sample_cv(sample_cv_path, workspace, capsys):
    if not SAMPLE_PRIVATE_FILE.is_file():
        pytest.skip(f"private sample expectations not found: {SAMPLE_PRIVATE_FILE.name}")
    private = jsonio.load_json(SAMPLE_PRIVATE_FILE)
    run_dir = _make_run(sample_cv_path)
    assert _ingest(run_dir) == 0
    capsys.readouterr()
    st = state.load(run_dir)
    text = (run_dir / "cv.txt").read_text(encoding="utf-8")
    assert st["ingest"]["pages"] == 6 and not st["ingest"]["scanned_suspect"]
    assert text.count(private["email"]) == 1
    assert ZWSP not in text and "\u2756" not in text and "\u27a2" not in text
    assert text.count("Role: SRE") == 2
    current_line = next(line for line in text.splitlines() if private["current_employer"] in line and "Feb 2024" in line)
    assert "Feb 2024 - Present" in current_line
    assert any("repeated header" in w for w in st["ingest"]["warnings"])
    assert any("Updated: Oct 2025" in w for w in st["ingest"]["warnings"])
    if shutil.which("pdftotext"):
        assert st["ingest"]["method"] == "pdftotext"
