"""`cvt validate`: every gate of interfaces.md section 10 on the rendered PDF, then `validation.json` and `final/`."""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import ats, attestations, coverage as coverage_mod, jsonio, provenance, render, schemas, state
from .errors import CvtError, ExitCode

VALIDATION_FILE = "validation.json"
FINAL_DIR = "final"
PROFILE_ARTIFACT, JD_ARTIFACT, TAILORED_ARTIFACT = "profile", "jd", "tailored"
FIT_ARTIFACT, PDF_ARTIFACT, MODEL_ARTIFACT = "fit", "pdf", "render_model"
VALIDATED_STAGE = "validated"
SCHEMA_VERSION = "1"
GATE_NAMES = (
    "schema", "provenance", "placeholders", "logistics_leak", "attestation_status", "page_count", "typography_floor",
    "ats_roundtrip", "keyword_coverage", "layout",
)
POST_RENDER_GATES = GATE_NAMES[5:]
PRESET_FLOOR_KEY = "floor"
FLOOR_FIELDS = ("body_pt", "margin_in")  # preset fields compared with the floor
POINTS_PER_INCH = 72.0
MIN_LAST_PAGE_FILL = 0.25  # the last page's text must reach this share of the usable height (section 14.5)
ORPHAN_HEADING_LINES = 2  # a section title among the last N text lines of a page is orphaned
LINE_Y_TOLERANCE_PT = 3.0  # words whose tops differ by less than this share a text line
PDFTOTEXT_BINARY = "pdftotext"
_PAGE_RE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', re.S)
_WORD_RE = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="[\d.]+" yMax="([\d.]+)">(.*?)</word>', re.S)
_NON_SLUG = re.compile(r"[^A-Za-z0-9]+")


# ---------------------------------------------------------------- helpers
def _gate(name: str, status: str, details: list[str] | None = None, violations: list[dict] | None = None) -> dict:
    return {"name": name, "status": status, "details": details or [], "violations": violations or []}


def _violation(code: str, item_id: str, message: str) -> dict:
    return {"code": code, "item_id": item_id, "message": message}


def _skipped(names: tuple[str, ...], why: str) -> list[dict]:
    return [_gate(name, "skipped", [why]) for name in names]


def _soft(violations: list[dict], draft: bool) -> str:
    return "pass" if not violations else ("warn" if draft else "fail")


def name_slug(text: str) -> str:
    """`Alex Chen` -> `Alex-Chen`: ASCII-folded, case kept, runs of other characters become one dash."""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return _NON_SLUG.sub("-", folded).strip("-")


def final_pdf_name(tailored: dict, jd: dict) -> str:
    """`<Name>-<TitleSlug>[-<CompanySlug>].pdf` (interfaces.md section 2)."""
    parts = [name_slug(tailored["header"]["name"]), name_slug(jd["title"]), name_slug(jd["company"])]
    return "-".join(p for p in parts if p) + ".pdf"


# ---------------------------------------------------------------- layout (bbox lines)
@dataclass
class PageText:
    height: float
    lines: list[tuple[float, float, str]]  # (top, bottom, text), top-down, footer lines included


def _group_lines(words: list[tuple[float, float, float, str]]) -> list[tuple[float, float, str]]:
    lines: list[list[tuple[float, float, float, str]]] = []
    for word in sorted(words, key=lambda w: (w[1], w[0])):
        if lines and word[1] - lines[-1][0][1] <= LINE_Y_TOLERANCE_PT:
            lines[-1].append(word)
        else:
            lines.append([word])
    out = []
    for line in lines:
        text = " ".join(w[3] for w in sorted(line, key=lambda w: w[0]))
        out.append((min(w[1] for w in line), max(w[2] for w in line), text))
    return out


def _bbox_pages(pdf: Path) -> list[PageText] | None:
    binary = shutil.which(PDFTOTEXT_BINARY)
    if not binary:
        return None
    proc = subprocess.run([binary, "-bbox", str(pdf), "-"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return None
    pages = []
    for _width, height, body in _PAGE_RE.findall(proc.stdout):
        words = [(float(x), float(y0), float(y1), html.unescape(t).strip()) for x, y0, y1, t in _WORD_RE.findall(body)]
        pages.append(PageText(float(height), _group_lines([w for w in words if w[3]])))
    return pages


def _pypdf_pages(pdf: Path) -> list[PageText]:
    """Fallback without bounding boxes: one pseudo-line per text operation, enough for the last-page fill."""
    from pypdf import PdfReader

    pages = []
    for page in PdfReader(str(pdf)).pages:
        height = float(page.mediabox.height)
        found: list[tuple[float, float, str]] = []

        def visit(text, cm, tm, _font, _size, found=found, height=height) -> None:
            if text.strip():
                y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
                found.append((height - y, height - y, text.strip()))

        page.extract_text(visitor_text=visit)
        pages.append(PageText(height, sorted(found)))
    return pages


def _content_lines(page: PageText, margin_pt: float) -> list[tuple[float, float, str]]:
    return [line for line in page.lines if line[0] < page.height - margin_pt]  # drops the page-number footer


def _layout_gate(pdf: Path, model: dict, margin_pt: float, fit: dict) -> dict:
    bbox = _bbox_pages(pdf)
    pages = bbox if bbox is not None else _pypdf_pages(pdf)
    titles = {sec["title"].casefold() for sec in model["sections"]}
    out: list[dict] = []
    if fit["underfilled"]:
        out.append(_violation("layout", f"page-{fit['pages']}", f"page {fit['pages']}: content fits in {fit['pages']} of "
                              f"{fit['page_target']} target pages (underfilled; nothing is padded automatically)"))
    last = len(pages)
    for number, page in enumerate(pages, start=1):
        lines = _content_lines(page, margin_pt)
        if not lines:
            continue
        if number == last:
            usable = page.height - 2 * margin_pt
            fill = max(0.0, min(1.0, (lines[-1][1] - margin_pt) / usable)) if usable > 0 else 1.0
            if fill < MIN_LAST_PAGE_FILL:
                out.append(_violation("layout", f"page-{number}", f"page {number}: last page is only {fill:.0%} filled "
                                      f"(minimum {MIN_LAST_PAGE_FILL:.0%})"))
        if bbox is None:
            continue
        tail = lines[-1:] if number == last else lines[-ORPHAN_HEADING_LINES:]  # a short final section may end the CV
        for _top, _bottom, text in tail:
            if text.casefold() in titles:
                out.append(_violation("layout", f"page-{number}", f"page {number}: section heading '{text}' is orphaned "
                                      f"at the bottom of the page"))
    return _gate("layout", "warn" if out else "pass", [v["message"] for v in out], out)


# ---------------------------------------------------------------- gates
def _artifact_path(run_dir: Path, st: dict, name: str) -> Path:
    return state.require_artifact(run_dir, st, name)


def _schema_gate(run_dir: Path, tailored: dict, extras: list[tuple[str, dict, str]]) -> dict:
    violations: list[dict] = []
    checked = ["tailored.json"]
    for problem in schemas.to_violations(schemas.validate(tailored, "tailored")):
        violations.append({**problem, "item_id": f"tailored.json {problem['item_id']}"})
    for label, obj, schema in extras:
        checked.append(label)
        violations += [{**p, "item_id": f"{label} {p['item_id']}"} for p in schemas.to_violations(schemas.validate(obj, schema))]
    return _gate("schema", "fail" if violations else "pass", [f"checked {', '.join(checked)}"], violations)


def _page_count_gate(tailored: dict, fit: dict, pdf_pages: int) -> dict:
    target = int(tailored["target"]["page_target"])
    problems: list[str] = []
    if fit["tailored_version"] != tailored["version"]:
        problems.append(f"fit.json is for tailored v{fit['tailored_version']} but tailored.json is v{tailored['version']}")
    if fit["page_target"] != target:
        problems.append(f"fit.json used page_target {fit['page_target']} but tailored.json says {target}")
    if fit["pages"] != pdf_pages:
        problems.append(f"fit.json says {fit['pages']} pages but cv.pdf has {pdf_pages}")
    if pdf_pages > target:
        problems.append(f"cv.pdf has {pdf_pages} pages, target is {target}")
    elif pdf_pages < target and not fit["underfilled"]:
        problems.append(f"cv.pdf has {pdf_pages} pages, target is {target}, and fit.json does not report it underfilled")
    if problems:
        return _gate("page_count", "fail", problems, [_violation("page_count", "cv.pdf", p) for p in problems])
    if pdf_pages < target:
        return _gate("page_count", "warn", [f"{pdf_pages} of {target} target pages (underfilled)"])
    return _gate("page_count", "pass", [f"{pdf_pages} of {target} pages"])


def _typography_gate(model: dict, presets: dict) -> dict:
    density = model["theme"]["density"]
    floor = presets[PRESET_FLOOR_KEY]
    preset = presets.get(density)
    if density == PRESET_FLOOR_KEY or not isinstance(preset, dict):
        message = f"density '{density}' is not a preset (use one of: {', '.join(render.DENSITIES)})"
        return _gate("typography_floor", "fail", [message], [_violation("typography", "theme.density", message)])
    problems = [
        f"density '{density}' {field} {preset[field]} is below the floor {floor[field]}"
        for field in FLOOR_FIELDS if preset[field] < floor[field]
    ]
    return _gate("typography_floor", "fail" if problems else "pass", problems or [f"{density} at or above the floor"],
                 [_violation("typography", "theme.density", p) for p in problems])


def _ats_gate(pdf_text: str, model: dict, jd: dict) -> dict:
    violations = ats.ats_check(pdf_text, model, jd)
    return _gate("ats_roundtrip", "fail" if violations else "pass", [f"{len(violations)} violations"] if violations else [], violations)


def _coverage_gate(cov: dict) -> dict:
    share = coverage_mod.ratio(cov)
    details = [f"must-have keywords {cov['must_keywords_found']}/{cov['must_keywords_total']} ({share:.0%})"]
    if cov["missing"]:
        details.append(f"missing: {', '.join(cov['missing'])}")
    return _gate("keyword_coverage", "warn" if share < coverage_mod.WARN_BELOW else "pass", details)


def _pre_render_gates(
    run_dir: Path, tailored: dict, profile: dict, jd: dict, extras: list[tuple[str, dict, str]], run_id: str, draft: bool,
) -> list[dict]:
    schema = _schema_gate(run_dir, tailored, extras)
    if schema["status"] == "fail":
        return [schema, *_skipped(GATE_NAMES[1:], "schema invalid")]
    store = attestations.load_store(profile["person_slug"])["attestations"]
    prov = provenance.check_tailored(tailored, profile, store, run_id=run_id, draft=True)
    holders = provenance.find_placeholders(tailored)
    leaks = provenance.check_logistics(tailored, jd)
    inactive = provenance.check_attestation_status(tailored, store, run_id=run_id)
    return [
        schema,
        _gate("provenance", "fail" if prov else "pass", [f"{len(prov)} violations"] if prov else [], prov),
        _gate("placeholders", _soft(holders, draft), [f"{len(holders)} placeholders"] if holders else [], holders),
        _gate("logistics_leak", "fail" if leaks else "pass", [f"{len(leaks)} violations"] if leaks else [], leaks),
        _gate("attestation_status", _soft(inactive, draft), ["run cvt approve first"] if inactive else [], inactive),
    ]


def _post_render_gates(run_dir: Path, st: dict, tailored: dict, jd: dict) -> tuple[list[dict], dict]:
    fit = jsonio.load_json(_artifact_path(run_dir, st, FIT_ARTIFACT))
    pdf = _artifact_path(run_dir, st, PDF_ARTIFACT)
    model = jsonio.load_json(_artifact_path(run_dir, st, MODEL_ARTIFACT))
    presets = jsonio.load_json(run_dir / render.BUILD_DIR / render.PRESETS_NAME)
    from pypdf import PdfReader

    pdf_pages = len(PdfReader(str(pdf)).pages)
    text = ats.extract_pdf_text(pdf)
    cov = coverage_mod.coverage(text, jd)
    margin_pt = presets[model["theme"]["density"]]["margin_in"] * POINTS_PER_INCH if model["theme"]["density"] in presets else 0.0
    gates = [
        _page_count_gate(tailored, fit, pdf_pages), _typography_gate(model, presets), _ats_gate(text, model, jd),
        _coverage_gate(cov), _layout_gate(pdf, model, margin_pt, fit),
    ]
    return gates, cov


def _extras(run_dir: Path, st: dict, profile: dict, jd: dict) -> list[tuple[str, dict, str]]:
    extras = [("profile.json", profile, "profile"), ("jd.json", jd, "jd")]
    for artifact, schema in ((FIT_ARTIFACT, "fit"), (MODEL_ARTIFACT, "render-model")):
        path = _artifact_path(run_dir, st, artifact)
        extras.append((path.relative_to(run_dir).as_posix(), jsonio.load_json(path), schema))
    return extras


# ---------------------------------------------------------------- public API
def validate_run(run_dir: Path, *, draft: bool) -> dict:
    """Run every gate in section 10 order, write `validation.json`, and on a clean non-draft pass publish `final/`."""
    run_dir = Path(run_dir)
    st = state.load(run_dir)
    tailored = jsonio.load_json(_artifact_path(run_dir, st, TAILORED_ARTIFACT))
    profile = jsonio.load_json(_artifact_path(run_dir, st, PROFILE_ARTIFACT))
    jd = jsonio.load_json(_artifact_path(run_dir, st, JD_ARTIFACT))
    gates = _pre_render_gates(run_dir, tailored, profile, jd, _extras(run_dir, st, profile, jd), st["run_slug"], draft)
    cov = {"must_keywords_total": 0, "must_keywords_found": 0, "missing": [], "by_requirement": []}
    if gates[0]["status"] == "fail":
        gates += _skipped(POST_RENDER_GATES, "schema invalid")
    else:
        post, cov = _post_render_gates(run_dir, st, tailored, jd)
        gates += post
    passed = all(g["status"] != "fail" for g in gates)
    validation = {
        "schema_version": SCHEMA_VERSION, "run_id": st["run_slug"], "created_at": jsonio.now_iso(), "draft": draft,
        "tailored_version": int(tailored["version"]), "passed": passed, "gates": gates, "coverage": cov,
    }
    schemas.require_valid(validation, "validation", VALIDATION_FILE)
    jsonio.dump_json(validation, run_dir / VALIDATION_FILE)
    state.record_artifact(run_dir, st, "validation", VALIDATION_FILE, cascade=passed)
    if passed and not draft:
        final = run_dir / FINAL_DIR / final_pdf_name(tailored, jd)
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(run_dir / render.PDF_NAME, final)
        state.record_artifact(run_dir, st, "final_pdf", final.relative_to(run_dir).as_posix())
        state.set_stage(st, VALIDATED_STAGE)
        state.add_history(st, "validate", f"passed; {final.name}")
    state.save(run_dir, st)
    return validation
