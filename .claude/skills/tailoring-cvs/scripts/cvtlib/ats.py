"""ATS round-trip: extract the PDF text the way an applicant tracking system would and compare it with the render model."""

from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

from .errors import CvtError, ExitCode

PDFTOTEXT_BINARY = "pdftotext"
PDFTOTEXT_ARGS = ("-layout", "-enc", "UTF-8")
PAGE_BREAK = "\n\f\n"
NORMAL_FORM = "NFKC"
GARBAGE_MARKERS = ("(cid:", "\ufffd")
MIN_TEXT_RATIO = 0.90  # extracted non-space characters / render-model non-space characters
BULLET_PROBE_WORDS = 6  # leading words of a bullet used to find it in the extracted text
CODE_MISSING, CODE_ORDER, CODE_GARBAGE = "ats_missing", "ats_order", "ats_garbage"
_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return unicodedata.normalize(NORMAL_FORM, text)


def extract_pdf_text(pdf: Path) -> str:
    """`pdftotext -layout` when installed, else pypdf. NFKC-normalized."""
    pdf = Path(pdf)
    if not pdf.is_file():
        raise CvtError(ExitCode.STATE, "E_ARTIFACT_MISSING", f"{pdf.name} not found", hint="build it first: cvt fit RUN")
    binary = shutil.which(PDFTOTEXT_BINARY)
    if binary:
        proc = subprocess.run([binary, *PDFTOTEXT_ARGS, str(pdf), "-"], capture_output=True, text=True, check=False)
        if proc.returncode == 0:
            return _normalize(proc.stdout)
    from pypdf import PdfReader

    pages = [page.extract_text() or "" for page in PdfReader(str(pdf)).pages]
    return _normalize(PAGE_BREAK.join(pages))


def collapse(text: str) -> str:
    """Casefolded text with every whitespace run reduced to one space (layout mode pads columns)."""
    return _WHITESPACE.sub(" ", _normalize(text)).strip().casefold()


def _squash(text: str) -> str:
    return _WHITESPACE.sub("", _normalize(text)).casefold()


def _found(haystack: str, squashed: str, needle: str) -> bool:
    return collapse(needle) in haystack or _squash(needle) in squashed


def _non_space_len(text: str) -> int:
    return len(_WHITESPACE.sub("", text))


def model_strings(model: dict) -> list[str]:
    """Every string a reader can see in the render model, in reading order."""
    head = model["header"]
    out = [head["name"], head["headline"], *[c["text"] for c in head["contacts"]]]
    for sec in model["sections"]:
        out += [sec["title"], *sec["paragraphs"], *sec["lines"]]
        out += [s for row in sec["skill_rows"] for s in (row["label"], row["items_text"])]
        for entry in sec["entries"]:
            out += [entry["heading"], entry["subheading"], entry["location"], entry["dates"], entry["intro"], *entry["bullets"]]
            for sub in entry["subentries"]:
                out += [sub["heading"], sub["subheading"], *sub["bullets"]]
            out.append(entry["collapsed_line"])
    return [s for s in out if s]


def _title_position(text: str, title: str, start: int = 0) -> int:
    """Index of the section title in collapsed `text`: a line of its own, else any word-bounded match."""
    needle = re.escape(collapse(title))
    for pattern in (rf"(?m)^{needle}$", rf"(?<!\w){needle}(?!\w)"):
        match = re.compile(pattern).search(text, start)
        if match:
            return match.start()
    return -1


def _line_collapsed(text: str) -> str:
    """Casefolded text keeping line breaks (so headings can be anchored to their own line)."""
    lines = (_WHITESPACE.sub(" ", line).strip() for line in _normalize(text).splitlines())
    return "\n".join(line.casefold() for line in lines if line)


def _violation(code: str, item_id: str, message: str) -> dict:
    return {"code": code, "item_id": item_id, "message": message}


def _required_strings(model: dict) -> list[tuple[str, str, str]]:
    """(item_id, label, text) for name, email and website plus every section title and employer."""
    head = model["header"]
    items = [("header.name", "name", head["name"])]
    for kind in ("email", "website"):
        for contact in head["contacts"]:
            if contact["kind"] == kind and contact["text"]:
                items.append((f"header.{kind}", kind, contact["text"]))
                break
    for sec in model["sections"]:
        items.append((f"section.{sec['kind']}", "section title", sec["title"]))
    for sec in model["sections"]:
        if sec["kind"] == "experience":
            items += [(f"employer.{i + 1}", "employer", e["heading"]) for i, e in enumerate(sec["entries"])]
    return items


def _check_missing(text: str, model: dict) -> list[dict]:
    squashed = _squash(text)
    collapsed = collapse(text)
    return [
        _violation(CODE_MISSING, item_id, f"{label} '{value}' is missing from the extracted PDF text")
        for item_id, label, value in _required_strings(model) if not _found(collapsed, squashed, value)
    ]


def _check_section_order(lines_text: str, model: dict) -> list[dict]:
    positions = [(sec["title"], _title_position(lines_text, sec["title"])) for sec in model["sections"]]
    out = []
    last_title, last_pos = "", -1
    for title, pos in positions:
        if pos < 0:
            continue
        if pos < last_pos:
            out.append(_violation(CODE_ORDER, f"section.{title.casefold()}",
                                  f"section '{title}' appears before '{last_title}' in the extracted text; expected the reverse"))
        else:
            last_title, last_pos = title, pos
    return out


def _first_bullet(entry: dict) -> str:
    if entry["bullets"]:
        return entry["bullets"][0]
    for sub in entry["subentries"]:
        if sub["bullets"]:
            return sub["bullets"][0]
    return ""


def _check_employer_order(lines_text: str, model: dict) -> list[dict]:
    out = []
    flat = lines_text.replace("\n", " ")
    for sec in model["sections"]:
        if sec["kind"] != "experience":
            continue
        start = max(_title_position(lines_text, sec["title"]), 0)
        for entry in sec["entries"]:
            bullet = _first_bullet(entry)
            if not bullet:
                continue
            probe = " ".join(collapse(bullet).split()[:BULLET_PROBE_WORDS])
            head_at = flat.find(collapse(entry["heading"]), start)
            bullet_at = flat.find(probe, start)
            if head_at >= 0 and 0 <= bullet_at < head_at:
                out.append(_violation(
                    CODE_ORDER, f"employer.{entry['heading']}",
                    f"first bullet of '{entry['heading']}' appears before its heading in the extracted text"))
    return out


def _check_garbage(text: str, model: dict) -> list[dict]:
    out = []
    for marker in GARBAGE_MARKERS:
        if marker in text:
            shown = "U+FFFD" if marker == "\ufffd" else marker
            out.append(_violation(CODE_GARBAGE, "pdf", f"extracted text contains {shown}: fonts lack a text mapping"))
    expected = sum(_non_space_len(s) for s in model_strings(model))
    got = _non_space_len(text)
    if expected and got < expected * MIN_TEXT_RATIO:
        out.append(_violation(
            CODE_GARBAGE, "pdf",
            f"extracted text has {got} characters, {got * 100 // expected}% of the {expected} in the render model "
            f"(minimum {int(MIN_TEXT_RATIO * 100)}%)"))
    return out


def ats_check(pdf_text: str, model: dict, jd: dict) -> list[dict]:
    """Violations (`ats_missing`, `ats_order`, `ats_garbage`) of the ats_roundtrip gate. `jd` is accepted for the
    contract signature; the gate compares the PDF with the render model only."""
    del jd
    text = _normalize(pdf_text)
    lines_text = _line_collapsed(text)
    return [
        *_check_missing(text, model),
        *_check_section_order(lines_text, model),
        *_check_employer_order(lines_text, model),
        *_check_garbage(text, model),
    ]
