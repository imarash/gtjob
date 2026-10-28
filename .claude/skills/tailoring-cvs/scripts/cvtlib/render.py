"""Render pipeline: tailored.json -> render model -> Typst source -> PDF / PNG / Markdown (interfaces.md sections 5, 9).

`build_render_model` is a pure function. Templates receive the model as JSON and insert every string as text, so
nothing here builds Typst markup from data. Backends: the Python `typst` module, then the `typst` binary, then none
(the build folder and `cv.md` are still written and the caller gets MISSING_DEPENDENCY).
"""

from __future__ import annotations

import io
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from . import jsonio, paths, schemas, state
from .errors import CvtError, ExitCode

PRESETS_FILE = "templates/presets.json"
TEMPLATES_DIR = "templates"
COMMON_TEMPLATE = "common.typ"
FONTS_DIR = "fonts"
BUILD_DIR = "build"
RENDER_JSON = "render.json"
PRESETS_NAME = "presets.json"
TYPST_ENTRY = "cv.typ"
PDF_NAME = "cv.pdf"
MARKDOWN_NAME = "cv.md"
PAGES_DIR = "pages"
PNG_PATTERN = "page-{n}.png"
TAILORED_FILE = "tailored.json"
FIT_FILE = "fit.json"
TEMPLATES = ("modern", "classic", "sidebar")
DENSITIES = ("comfortable", "standard", "compact")
DEFAULT_DENSITY = "standard"
PAPERS = ("us-letter", "a4")
DEFAULT_PAPER = "us-letter"
DEFAULT_ACCENT = "#1F4E79"
DEFAULT_PPI = 110
MAX_KEYWORDS = 12
DRAFT_STAGE_LIMIT = "approved"
RENDERED_STAGE = "rendered"
BACKENDS = ("python", "binary", "none")
TYPST_BINARY = "typst"
PDFTOPPM_BINARY = "pdftoppm"
TITLE_SEPARATOR = " — "
RANGE_SEPARATOR = " – "
CONTACT_KINDS_ORDER = ("website", "linkedin", "github")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
SECTION_TITLES = {
    "summary": "Summary", "skills": "Skills", "experience": "Recent Experience", "earlier": "Earlier experience",
    "certifications": "Certifications", "education": "Education",
}
INSTALL_HINT = "install a Typst backend with `uv pip install typst` or `brew install typst`, then rerun: cvt render RUN"
_MONTH_DATE = re.compile(r"^(\d{4})-(\d{2})$")
_YEAR_DATE = re.compile(r"^\d{4}$")
_PHONE_STRIP = re.compile(r"[^\d+]")


@dataclass
class RenderResult:
    pdf: Path | None
    pages: int
    pngs: list[Path]
    backend: str
    markdown: Path | None = None
    model_path: Path | None = None
    typst_path: Path | None = None
    density: str = DEFAULT_DENSITY
    draft: bool = False
    template: str = "modern"
    fitted: bool = False
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- render model


def format_date(value: str) -> str:
    """`2024-02` -> `Feb 2024`, `present` -> `Present`, year-only and empty stay as they are."""
    value = (value or "").strip()
    match = _MONTH_DATE.match(value)
    if match:
        month = int(match.group(2))
        if 1 <= month <= len(MONTHS):
            return f"{MONTHS[month - 1]} {match.group(1)}"
        return match.group(1)
    if value.lower() == "present":
        return "Present"
    return value


def format_range(start: str, end: str) -> str:
    first, last = format_date(start), format_date(end)
    if first and last and first != last:
        return f"{first}{RANGE_SEPARATOR}{last}"
    return first or last


def _year(value: str) -> str:
    value = (value or "").strip()
    if value.lower() == "present":
        return "Present"
    return value[:4] if value[:4].isdigit() else value


def _year_range(start: str, end: str) -> str:
    first, last = _year(start), _year(end)
    if first and last and first != last:
        return f"{first}{RANGE_SEPARATOR}{last}"
    return first or last


def _with_scheme(url: str) -> str:
    url = url.strip()
    if not url or "://" in url or re.match(r"^(mailto|tel):", url):
        return url
    return f"https://{url}"


def _bare_link(url: str, label: str) -> str:
    """Display text for a link: the bare domain plus path, no scheme, `www.`, query, or trailing slash."""
    if not url:
        return label
    parsed = urlparse(_with_scheme(url))
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return label or url
    host = parsed.netloc.lower().removeprefix("www.")
    return f"{host}{parsed.path.rstrip('/')}"


def _link_kind(url: str) -> str:
    host = urlparse(_with_scheme(url)).netloc.lower()
    if "linkedin.com" in host:
        return "linkedin"
    if "github.com" in host:
        return "github"
    return "website"


def _contacts(header: dict) -> list[dict]:
    out: list[dict] = []
    if header["email"]:
        out.append({"kind": "email", "text": header["email"], "url": f"mailto:{header['email']}"})
    if header["phone"]:
        digits = _PHONE_STRIP.sub("", header["phone"])
        out.append({"kind": "phone", "text": header["phone"], "url": f"tel:{digits}" if digits else ""})
    if header["location"]:
        out.append({"kind": "location", "text": header["location"], "url": ""})
    links = []
    for link in header["links"]:
        url = _with_scheme(link["url"])
        kind = _link_kind(url) if url else "other"
        links.append({"kind": kind, "text": _bare_link(url, link["label"]), "url": url})
    rank = {kind: i for i, kind in enumerate(CONTACT_KINDS_ORDER)}
    links.sort(key=lambda c: rank.get(c["kind"], len(rank)))
    return out + links


def _empty_section(kind: str) -> dict:
    return {"kind": kind, "title": SECTION_TITLES[kind], "paragraphs": [], "skill_rows": [], "entries": [], "lines": []}


def _experience_entry(entry: dict, dropped: set[str]) -> dict:
    subentries: list[dict] = []
    collapsed: list[str] = []
    for eng in entry["engagements"]:
        bullets = [b["text"] for b in eng["bullets"] if b["id"] not in dropped]
        if bullets:
            subentries.append({"heading": eng["name"], "subheading": eng["role_label"], "bullets": bullets})
        else:
            collapsed.append(f"{eng['name']} ({eng['role_label']})" if eng["role_label"] else eng["name"])
    return {
        "heading": entry["employer"], "subheading": entry["title"], "location": entry["location"],
        "dates": format_range(entry["start_date"], entry["end_date"]), "intro": entry["intro"]["text"],
        "bullets": [b["text"] for b in entry["bullets"] if b["id"] not in dropped],
        "subentries": subentries,
        "collapsed_line": f"Also: {' · '.join(collapsed)}" if collapsed else "",
    }


def _sections(tailored: dict, dropped: set[str]) -> list[dict]:
    sections: list[dict] = []
    if tailored["summary"]["text"].strip():
        sec = _empty_section("summary")
        sec["paragraphs"] = [tailored["summary"]["text"]]
        sections.append(sec)
    rows = [
        {"label": g["label"], "items_text": ", ".join(i["name"] for i in g["items"])}
        for g in tailored["skills"] if g["id"] not in dropped and g["items"]
    ]
    if rows:
        sec = _empty_section("skills")
        sec["skill_rows"] = rows
        sections.append(sec)
    if tailored["experience"]:
        sec = _empty_section("experience")
        sec["entries"] = [_experience_entry(e, dropped) for e in tailored["experience"]]
        sections.append(sec)
    earlier = tailored["earlier_experience"]
    if earlier["include"] and earlier["items"]:
        sec = _empty_section("earlier")
        sec["lines"] = [
            f"{i['employer']}{TITLE_SEPARATOR}{i['title']} ({_year_range(i['start_date'], i['end_date'])})"
            for i in earlier["items"]
        ]
        sections.append(sec)
    certs = [c["name"] for c in tailored["certifications"] if c["id"] not in dropped]
    if certs:
        sec = _empty_section("certifications")
        sec["lines"] = certs
        sections.append(sec)
    if tailored["education"]:
        sec = _empty_section("education")
        sec["entries"] = [
            {
                "heading": e["institution"], "subheading": e["degree"], "location": e["location"],
                "dates": format_date(e["end_date"]), "intro": e["details"], "bullets": [], "subentries": [],
                "collapsed_line": "",
            }
            for e in tailored["education"]
        ]
        sections.append(sec)
    return sections


def _keywords(tailored: dict, dropped: set[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in tailored["skills"]:
        if group["id"] in dropped:
            continue
        for item in group["items"]:
            key = item["name"].strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(item["name"].strip())
    return out[:MAX_KEYWORDS]


def build_render_model(
    tailored: dict, *, dropped_ids: set[str], density: str, draft: bool, paper: str, template: str,
) -> dict:
    """Pure mapping tailored.json -> render-model.schema.json. Dropped IDs are removed, never rewritten."""
    for value, allowed, label in ((density, DENSITIES, "density"), (paper, PAPERS, "paper"), (template, TEMPLATES, "template")):
        if value not in allowed:
            raise CvtError(ExitCode.USAGE, "E_USAGE", f"unknown {label} '{value}'", hint=f"use one of: {', '.join(allowed)}")
    header = tailored["header"]
    name, target = header["name"], tailored["target"]["title"]
    return {
        "schema_version": "1",
        "meta": {
            "title": f"{name}{TITLE_SEPARATOR}CV{TITLE_SEPARATOR}{target}" if target else f"{name}{TITLE_SEPARATOR}CV",
            "author": name, "subject": target, "keywords": _keywords(tailored, dropped_ids), "draft": bool(draft),
        },
        "theme": {"template": template, "paper": paper, "density": density, "accent": DEFAULT_ACCENT},
        "header": {"name": name, "headline": header["headline"], "contacts": _contacts(header)},
        "sections": _sections(tailored, set(dropped_ids)),
    }


# ---------------------------------------------------------------- markdown


def render_markdown(model: dict) -> str:
    """Clean Markdown CV (always written as `cv.md`; the only output when no Typst backend exists)."""
    head = model["header"]
    lines = [f"# {head['name']}", ""]
    if head["headline"]:
        lines += [f"**{head['headline']}**", ""]
    contacts = [f"[{c['text']}]({c['url']})" if c["url"] else c["text"] for c in head["contacts"]]
    if contacts:
        lines += [" · ".join(contacts), ""]
    for sec in model["sections"]:
        lines += [f"## {sec['title']}", ""]
        lines += [f"{p}\n" for p in sec["paragraphs"]]
        lines += [f"- **{r['label']}:** {r['items_text']}" for r in sec["skill_rows"]]
        if sec["skill_rows"]:
            lines.append("")
        for e in sec["entries"]:
            lines.append(f"### {e['heading']}" + (f" — {e['subheading']}" if e["subheading"] else ""))
            meta = " · ".join(x for x in (e["location"], e["dates"]) if x)
            if meta:
                lines.append(f"*{meta}*")
            lines.append("")
            if e["intro"]:
                lines += [e["intro"], ""]
            lines += [f"- {b}" for b in e["bullets"]]
            for s in e["subentries"]:
                lines += ["", f"**{s['heading']}**" + (f" — *{s['subheading']}*" if s["subheading"] else "")]
                lines += [f"- {b}" for b in s["bullets"]]
            if e["collapsed_line"]:
                lines += ["", f"*{e['collapsed_line']}*"]
            lines.append("")
        if sec["kind"] == "certifications":
            lines += [f"- {x}" for x in sec["lines"]]
        else:
            lines += [f"{x}  " for x in sec["lines"]]
        if sec["lines"]:
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------- build + compile


def _template_source(template: str) -> Path:
    src = paths.asset(TEMPLATES_DIR, f"{template}.typ")
    if not src.is_file():
        raise CvtError(
            ExitCode.USAGE, "E_TEMPLATE_MISSING", f"template '{template}' not installed",
            hint=f"use --template modern (installed: {', '.join(t for t in TEMPLATES if paths.asset(TEMPLATES_DIR, f'{t}.typ').is_file())})",
        )
    return src


def write_build(run_dir: Path, model: dict, template: str) -> Path:
    """Write build/render.json, build/cv.typ (the chosen template), common.typ and presets.json. Returns cv.typ."""
    schemas.require_valid(model, "render-model", "render model")
    source = _template_source(template)
    build = Path(run_dir) / BUILD_DIR
    build.mkdir(parents=True, exist_ok=True)
    jsonio.dump_json(model, build / RENDER_JSON)
    shutil.copyfile(source, build / TYPST_ENTRY)
    shutil.copyfile(paths.asset(TEMPLATES_DIR, COMMON_TEMPLATE), build / COMMON_TEMPLATE)
    shutil.copyfile(paths.asset(PRESETS_FILE), build / PRESETS_NAME)
    return build / TYPST_ENTRY


def detect_backend() -> str:
    """`python` (typst wheel), `binary` (typst on PATH), or `none`."""
    try:
        import typst  # noqa: F401
        return "python"
    except ImportError:
        pass
    return "binary" if shutil.which(TYPST_BINARY) else "none"


def _missing_backend() -> CvtError:
    return CvtError(
        ExitCode.MISSING_DEPENDENCY, "E_TYPST_MISSING", "no Typst compiler found (python module `typst` or `typst` binary)",
        hint=f"{INSTALL_HINT}; build/ and {MARKDOWN_NAME} were written",
    )


def _inputs() -> dict[str, str]:
    return {"data": RENDER_JSON, "presets": PRESETS_NAME}


def _compile_error(detail: str) -> CvtError:
    return CvtError(
        ExitCode.INTERNAL, "E_TYPST_COMPILE", f"Typst failed to compile the CV: {detail.strip()[:400]}",
        hint=f"inspect build/{TYPST_ENTRY} and build/{RENDER_JSON}; this is a template bug",
    )


def _run_binary(typ: Path, target: str, extra: list[str]) -> None:
    cmd = [
        TYPST_BINARY, "compile", "--root", str(typ.parent), "--font-path", str(paths.asset(FONTS_DIR)),
        "--ignore-system-fonts", *[a for k, v in _inputs().items() for a in ("--input", f"{k}={v}")],
        *extra, str(typ), target,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise _compile_error(proc.stderr)


def _python_compile(typ: Path, fmt: str, ppi: int | None = None):
    import typst

    kwargs = {"ppi": float(ppi)} if ppi else {}
    try:
        return typst.compile(
            str(typ), root=str(typ.parent), font_paths=[str(paths.asset(FONTS_DIR))], ignore_system_fonts=True,
            format=fmt, sys_inputs=_inputs(), **kwargs,
        )
    except Exception as exc:  # noqa: BLE001 - typst raises plain RuntimeError subclasses with the diagnostics
        raise _compile_error(str(exc)) from None


def _page_count(pdf_bytes: bytes) -> int:
    from pypdf import PdfReader

    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


def compile_pdf(run_dir: Path, typ: Path, out_pdf: Path) -> int:
    """Compile `typ` to `out_pdf` and return the page count."""
    backend = detect_backend()
    if backend == "none":
        raise _missing_backend()
    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_pdf.with_name(out_pdf.name + ".tmp")
    if backend == "python":
        data = _python_compile(Path(typ), "pdf")
        tmp.write_bytes(data)
    else:
        _run_binary(Path(typ), str(tmp), ["--format", "pdf"])
        data = tmp.read_bytes()
    tmp.replace(out_pdf)
    return _page_count(data)


def _clear_pngs(out_dir: Path) -> None:
    for old in out_dir.glob("page-*.png"):
        old.unlink()


def compile_png(run_dir: Path, typ: Path, out_dir: Path, ppi: int = DEFAULT_PPI) -> list[Path]:
    """Rasterize every page of `typ` to `out_dir/page-<N>.png` (1-based) and return the paths in page order."""
    backend = detect_backend()
    if backend == "none":
        raise _missing_backend()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _clear_pngs(out_dir)
    if backend == "python":
        result = _python_compile(Path(typ), "png", ppi)
        pages = [result] if isinstance(result, (bytes, bytearray)) else list(result)
        written = []
        for n, blob in enumerate(pages, start=1):
            path = out_dir / PNG_PATTERN.format(n=n)
            path.write_bytes(blob)
            written.append(path)
        return written
    _run_binary(Path(typ), str(out_dir / PNG_PATTERN.replace("{n}", "{p}")), ["--format", "png", "--ppi", str(ppi)])
    return sorted(out_dir.glob("page-*.png"), key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)))


# ---------------------------------------------------------------- run-level rendering


def load_fit(run_dir: Path, tailored: dict) -> dict | None:
    """The run's `fit.json` when it is valid and applies to this tailored version, else None."""
    path = Path(run_dir) / FIT_FILE
    if not path.is_file():
        return None
    fit = jsonio.load_json(path)
    if schemas.validate(fit, "fit") or fit["tailored_version"] != tailored["version"]:
        return None
    return fit


def _is_draft_stage(st: dict) -> bool:
    return state.stage_index(st["stage"]) < state.stage_index(DRAFT_STAGE_LIMIT)


def render_run(
    run_dir: Path, *, template: str | None = None, density: str | None = None, dropped_ids: set[str] | None = None,
    draft: bool | None = None, png: bool = False, out_pdf: Path | None = None, ppi: int = DEFAULT_PPI,
) -> RenderResult:
    """Build and compile a run. Defaults come from `fit.json` (when it matches), state options, and the stage.

    With `out_pdf` set (trial compiles from `cvt fit`) the PDF goes there and `cv.md` and `pages/` are left alone.
    """
    run_dir = Path(run_dir)
    st = state.load(run_dir)
    tailored = jsonio.load_json(run_dir / TAILORED_FILE)
    fit = load_fit(run_dir, tailored)
    warnings: list[str] = []
    if fit is None and (dropped_ids is None or density is None):
        warnings.append("not fitted; run cvt fit")
    if dropped_ids is None:
        dropped_ids = set(fit["dropped_ids"]) if fit else set()
    if density is None:
        density = fit["density"] if fit else DEFAULT_DENSITY
    template = template or tailored["target"]["template"] or st["options"]["template"]
    draft = (st["options"]["draft"] or _is_draft_stage(st)) if draft is None else draft
    model = build_render_model(
        tailored, dropped_ids=dropped_ids, density=density, draft=draft, paper=st["options"]["paper"], template=template,
    )
    typ = write_build(run_dir, model, template)
    final = out_pdf is None
    markdown = None
    if final:
        markdown = run_dir / MARKDOWN_NAME
        markdown.write_text(render_markdown(model), encoding="utf-8")
    result = RenderResult(
        pdf=None, pages=0, pngs=[], backend=detect_backend(), markdown=markdown, model_path=typ.parent / RENDER_JSON,
        typst_path=typ, density=density, draft=bool(draft), template=template, fitted=fit is not None, warnings=warnings,
    )
    pdf_path = Path(out_pdf) if out_pdf else run_dir / PDF_NAME
    result.pages = compile_pdf(run_dir, typ, pdf_path)
    result.pdf = pdf_path
    if png:
        result.pngs = compile_png(run_dir, typ, run_dir / PAGES_DIR, ppi)
    return result


# ---------------------------------------------------------------- view-only page images


def rasterize_pages(run_dir: Path, pages: list[int], ppi: int = DEFAULT_PPI) -> list[Path]:
    """Rasterize pages of the existing `cv.pdf` to `pages/page-<N>.png` without touching any other artifact."""
    run_dir = Path(run_dir)
    pdf = run_dir / PDF_NAME
    if not pdf.is_file():
        raise CvtError(
            ExitCode.STATE, "E_ARTIFACT_MISSING", f"{PDF_NAME} not found in {run_dir.name}",
            hint=f"build it first with: cvt fit {run_dir.name}",
        )
    from pypdf import PdfReader

    total = len(PdfReader(str(pdf)).pages)
    bad = [n for n in pages if not 1 <= n <= total]
    if bad:
        raise CvtError(
            ExitCode.USAGE, "E_USAGE", f"page {bad[0]} is out of range ({PDF_NAME} has {total} page(s))",
            hint=f"use --pages with values from 1 to {total}",
        )
    out_dir = run_dir / PAGES_DIR
    out_dir.mkdir(exist_ok=True)
    if shutil.which(PDFTOPPM_BINARY):
        written = []
        for n in pages:
            stem = out_dir / f"page-{n}"
            proc = subprocess.run(
                [PDFTOPPM_BINARY, "-f", str(n), "-l", str(n), "-r", str(ppi), "-png", "-singlefile", str(pdf), str(stem)],
                capture_output=True, text=True, check=False,
            )
            if proc.returncode != 0:
                raise _compile_error(proc.stderr)
            written.append(stem.with_suffix(".png"))
        return written
    typ = run_dir / BUILD_DIR / TYPST_ENTRY
    if not typ.is_file():
        raise CvtError(
            ExitCode.STATE, "E_ARTIFACT_MISSING", f"{BUILD_DIR}/{TYPST_ENTRY} not found in {run_dir.name}",
            hint=f"install Poppler (`brew install poppler`) or rebuild with: cvt fit {run_dir.name} --png",
        )
    scratch = run_dir / BUILD_DIR / PAGES_DIR
    shutil.rmtree(scratch, ignore_errors=True)
    rendered = compile_png(run_dir, typ, scratch, ppi)
    written = []
    for n in pages:
        dest = out_dir / PNG_PATTERN.format(n=n)
        shutil.copyfile(rendered[n - 1], dest)
        written.append(dest)
    shutil.rmtree(scratch, ignore_errors=True)
    return written
