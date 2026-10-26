"""CV and JD text extraction and cleanup (interfaces.md section 5, WP-09).

Pure functions: `extract_cv`, `clean_cv_text`, `load_jd`, `clean_jd_text`. The `cvt ingest` command in
cvtlib/commands/ingest.py is a thin wrapper. CV and JD text is untrusted data: nothing here evaluates or
follows it.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from .errors import CvtError, ExitCode

# --- extraction -------------------------------------------------------------------------------------------
MIN_CHARS_PER_PAGE = 200  # below this average of extractable characters per page, a PDF is "scanned"
PDFTOTEXT_BIN = "pdftotext"
PDFTOTEXT_TIMEOUT_S = 60
PAGE_BREAK = "\f"
EXTRAS_MODULE = "cvtlib.extras"
EXTRACT_DOCX_FN = "extract_docx"
OCR_PDF_FN = "ocr_pdf"
METHOD_PDFTOTEXT = "pdftotext"
METHOD_PYPDF = "pypdf"
METHOD_TEXT = "text"
METHOD_MARKDOWN = "markdown"
METHOD_DOCX = "docx"
METHOD_OCR = "ocr"
LATIN1_WARNING = "input was not valid UTF-8; decoded as latin-1 (check accents and symbols)"
OCR_WARNING = "scanned PDF: text came from OCR, so check names, dates, and numbers against the original"

# --- CV cleanup -------------------------------------------------------------------------------------------
HEADER_SCAN_LINES = 4  # first and last N non-empty lines of each page are header/footer candidates
MIN_HEADER_PAGES = 2
MIN_HEADER_KEY_CHARS = 4
MAX_DIGIT_VARIANT_CHARS = 40  # longer lines only count as repeated when identical (digits included)
MAX_SPACE_RUN = 2
MAX_BLANK_RUN = 1  # runs of 3 or more blank lines collapse to this many
BLANK_RUN_TRIGGER = 3
BULLET = "- "
MID_LINE_SEPARATOR = " | "
SEPARATOR_GLYPHS = "\u2666\u25c6"  # black diamond suit (Google Docs header separator) and black diamond
DECORATIVE_GLYPHS = (
    "\u2756\u27a2\u2022\u25aa\u25e6\u25cf\u25a0\u2666"  # ❖ ➢ • ▪ ◦ ● ■ ♦
    "\u25c6\u25c7\u25ba\u25b8\u2023\u2043\u2219\u25cb\u25a1\u27a4\u2713\u2714\u2605"  # ◆ ◇ ► ▸ ‣ ⁃ ∙ ○ □ ➤ ✓ ✔ ★
)
INVISIBLE_CHARS = ("\u200b", "\ufeff", "\u00ad")  # zero-width space, BOM, soft hyphen
PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,2}\s*$")
DIGITS_RE = re.compile(r"\d+")
SPACES_RE = re.compile(r" {%d,}" % (MAX_SPACE_RUN + 1))
WHITESPACE_RE = re.compile(r"\s+")
LEADING_GLYPH_RE = re.compile(r"^(\s*)[%s]\s*" % re.escape(DECORATIVE_GLYPHS))
MID_SEPARATOR_RE = re.compile(r"\s*[%s]\s*" % re.escape(SEPARATOR_GLYPHS))
UPDATED_RE = re.compile(r"Updated:\s*[A-Za-z]+\s+\d{4}", re.IGNORECASE)


@dataclass
class Extraction:
    text: str
    method: str
    pages: int
    scanned_suspect: bool
    warnings: list[str] = field(default_factory=list)


def _load_extras():
    """The optional extras module, or None. Works for real modules and for fakes placed in sys.modules."""
    mod = sys.modules.get(EXTRAS_MODULE)
    if mod is not None:
        return mod
    try:
        spec = importlib.util.find_spec(EXTRAS_MODULE)
    except (ImportError, ValueError):
        return None
    return importlib.import_module(EXTRAS_MODULE) if spec is not None else None


def _count_visible_chars(text: str) -> int:
    for ch in INVISIBLE_CHARS:
        text = text.replace(ch, "")
    return len(WHITESPACE_RE.sub("", text))


def _read_text_file(path: Path) -> tuple[str, list[str]]:
    data = path.read_bytes()
    try:
        return data.decode("utf-8"), []
    except UnicodeDecodeError:
        return data.decode("latin-1"), [LATIN1_WARNING]


def _pdf_page_count(path: Path, fallback_text: str = "") -> int:
    try:
        from pypdf import PdfReader
    except ImportError:
        return max(1, len([p for p in fallback_text.split(PAGE_BREAK) if p.strip()]))
    try:
        return len(PdfReader(str(path)).pages)
    except Exception as exc:  # noqa: BLE001 - pypdf raises many exception types for broken files
        raise CvtError(
            ExitCode.INPUT, "E_CV_UNREADABLE", f"cannot read PDF {path.name}: {exc}",
            hint="re-export the CV as a text PDF, or paste the CV as text into a .txt file",
        ) from None


def _pdftotext(path: Path) -> str | None:
    binary = shutil.which(PDFTOTEXT_BIN)
    if not binary:
        return None
    try:
        proc = subprocess.run(
            [binary, "-layout", "-enc", "UTF-8", str(path), "-"],
            capture_output=True, check=False, timeout=PDFTOTEXT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", errors="replace")


def _pypdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        raise CvtError(
            ExitCode.MISSING_DEPENDENCY, "E_MISSING_DEPENDENCY",
            "neither pdftotext nor pypdf is available to read the PDF",
            hint="brew install poppler, or uv pip install pypdf",
        ) from None
    try:
        reader = PdfReader(str(path))
        pages = [p.extract_text(extraction_mode="layout") or "" for p in reader.pages]
    except Exception as exc:  # noqa: BLE001
        raise CvtError(
            ExitCode.INPUT, "E_CV_UNREADABLE", f"cannot read PDF {path.name}: {exc}",
            hint="re-export the CV as a text PDF, or paste the CV as text into a .txt file",
        ) from None
    return PAGE_BREAK.join(unicodedata.normalize("NFKC", p) for p in pages)


def _scanned_error() -> CvtError:
    return CvtError(
        ExitCode.INPUT, "E_CV_SCANNED", "this PDF has almost no extractable text",
        hint="this PDF looks scanned; export a text PDF or paste the CV as text (OCR is not supported yet)",
    )


def _extract_pdf(path: Path) -> Extraction:
    text = _pdftotext(path)
    method = METHOD_PDFTOTEXT
    if text is None:
        method = METHOD_PYPDF
        text = _pypdf_text(path)
    pages = _pdf_page_count(path, text)
    scanned = _count_visible_chars(text) < MIN_CHARS_PER_PAGE * max(pages, 1)
    warnings: list[str] = []
    if scanned:
        extras = _load_extras()
        ocr = getattr(extras, OCR_PDF_FN, None) if extras is not None else None
        if ocr is None:
            raise _scanned_error()
        return Extraction(str(ocr(path)), METHOD_OCR, pages, True, [OCR_WARNING])
    return Extraction(text, method, pages, False, warnings)


def extract_cv(path: Path) -> Extraction:
    """Raw text of a stored CV. Exit 5 for scanned PDFs and unsupported formats unless extras handle them."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix in (".txt", ".md"):
        text, warnings = _read_text_file(path)
        method = METHOD_MARKDOWN if suffix == ".md" else METHOD_TEXT
        pages = max(1, len([p for p in text.split(PAGE_BREAK) if p.strip()]))
        return Extraction(text, method, pages, False, warnings)
    if suffix == ".docx":
        extras = _load_extras()
        extract = getattr(extras, EXTRACT_DOCX_FN, None) if extras is not None else None
        if extract is None:
            raise CvtError(
                ExitCode.INPUT, "E_CV_DOCX", "reading .docx files is not supported in this install",
                hint="export the CV as PDF or text",
            )
        return Extraction(str(extract(path)), METHOD_DOCX, 1, False, [])
    raise CvtError(
        ExitCode.INPUT, "E_CV_FORMAT", f"unsupported CV format '{suffix}'",
        hint="use a .pdf, .txt or .md file, or paste the CV as text",
    )


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    for ch in INVISIBLE_CHARS:
        text = text.replace(ch, "")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _loose_key(line: str) -> str:
    return WHITESPACE_RE.sub(" ", DIGITS_RE.sub("", line)).strip()


def _exact_key(line: str) -> str:
    return WHITESPACE_RE.sub(" ", line).strip()


def _candidate_positions(lines: list[str]) -> tuple[list[int], int]:
    """Indices of header/footer candidate lines on a page, and how many of them are header (top) lines."""
    filled = [i for i, line in enumerate(lines) if line.strip()]
    top = filled[:HEADER_SCAN_LINES]
    bottom = [i for i in filled[-HEADER_SCAN_LINES:] if i not in top]
    return top + bottom, len(top)


def _repeated_groups(pages: list[list[str]]) -> list[list[tuple[int, int, bool]]]:
    """Occurrence groups (page, line, is_top) of lines repeated on 2+ pages, in document order.

    Lines match when equal after whitespace normalization. Short lines also match when they differ only
    in digits ("Page 2 of 6"). Bullet lines are content, never headers.
    """
    loose: dict[str, list[tuple[int, int, bool]]] = {}
    for p_idx, lines in enumerate(pages):
        cands, n_top = _candidate_positions(lines)
        for rank, l_idx in enumerate(cands):
            line = lines[l_idx]
            key = _loose_key(line)
            if len(key) >= MIN_HEADER_KEY_CHARS and not LEADING_GLYPH_RE.match(line):
                loose.setdefault(key, []).append((p_idx, l_idx, rank < n_top))
    groups: list[list[tuple[int, int, bool]]] = []
    for key, occurrences in loose.items():
        if len(key) <= MAX_DIGIT_VARIANT_CHARS:
            groups.append(occurrences)
            continue
        exact: dict[str, list[tuple[int, int, bool]]] = {}
        for occ in occurrences:
            exact.setdefault(_exact_key(pages[occ[0]][occ[1]]), []).append(occ)
        groups.extend(exact.values())
    return [g for g in groups if len({p for p, _, _ in g}) >= MIN_HEADER_PAGES]


def _strip_repeated_headers(pages: list[list[str]]) -> tuple[list[list[str]], list[str], list[str]]:
    """Drop repeated header/footer lines (keep the first). Returns pages, kept-header lines to hoist, warnings."""
    first_content_page = next((i for i, lines in enumerate(pages) if any(x.strip() for x in lines)), 0)
    removed = 0
    hoisted: list[tuple[int, int, str]] = []
    drop: set[tuple[int, int]] = set()
    for occurrences in _repeated_groups(pages):
        (keep_p, keep_l, keep_is_top), rest = occurrences[0], occurrences[1:]
        drop.update((p, l) for p, l, _ in rest)
        removed += len(rest)
        if keep_is_top and keep_p > first_content_page:
            hoisted.append((keep_p, keep_l, pages[keep_p][keep_l]))
            drop.add((keep_p, keep_l))
    cleaned = [[line for l_idx, line in enumerate(lines) if (p_idx, l_idx) not in drop]
               for p_idx, lines in enumerate(pages)]
    hoisted.sort(key=lambda h: (h[0], h[1]))
    warnings = []
    if removed:
        warnings.append(f"removed {removed} repeated header/footer lines")
    if hoisted:
        warnings.append(f"moved {len(hoisted)} repeated header line(s) to the top of the CV")
    return cleaned, [h[2] for h in hoisted], warnings


def _clean_line(line: str) -> str:
    line = line.rstrip()
    line = LEADING_GLYPH_RE.sub(lambda m: m.group(1) + BULLET, line)
    line = MID_SEPARATOR_RE.sub(MID_LINE_SEPARATOR, line)
    return SPACES_RE.sub(" " * MAX_SPACE_RUN, line)


def _collapse_blank_runs(lines: list[str]) -> list[str]:
    out: list[str] = []
    run = 0
    for line in lines:
        if line:
            if run >= BLANK_RUN_TRIGGER:
                out.extend([""] * MAX_BLANK_RUN)
            else:
                out.extend([""] * run)
            run = 0
            out.append(line)
        else:
            run += 1
    return out  # trailing blanks are dropped


def clean_cv_text(raw: str) -> tuple[str, list[str]]:
    """Strip extraction artifacts but keep content and reading order. Returns (text, warnings)."""
    text = _normalize(raw)
    pages = [
        [line.rstrip() for line in page.split("\n") if not PAGE_NUMBER_RE.match(line)]
        for page in text.split(PAGE_BREAK)
    ]
    pages, hoisted, warnings = _strip_repeated_headers(pages)
    lines = [*hoisted, *(line for page in pages for line in page)]
    cleaned = _collapse_blank_runs([_clean_line(line) for line in lines])
    while cleaned and not cleaned[0]:
        cleaned.pop(0)
    for line in cleaned:
        match = UPDATED_RE.search(line)
        if match:
            warnings.append(f"stale '{match.group(0)}' line kept for review")
            break
    return ("\n".join(cleaned) + "\n" if cleaned else ""), warnings


# --- job description --------------------------------------------------------------------------------------
JD_FETCH_TIMEOUT_S = 15
JD_USER_AGENT = "gtjob/0.1"
JD_MAX_BYTES = 2_000_000
JD_URL_SCHEMES = ("http", "https")
JD_FETCH_ERROR_ID = "E_JD_FETCH"
JD_FETCH_HINT = "paste the JD text with --jd-text or save it to a file"
JD_URL_COMMENT_RE = re.compile(r"^\s*<!--\s*jd-url:.*?-->\s*", re.DOTALL)
JD_URL_COMMENT = "<!-- jd-url: {url} -->\n"
JD_DEFAULT_CHARSET = "utf-8"
SKIP_TAGS = frozenset({"script", "style", "nav", "noscript", "template"})
BLOCK_TAGS = frozenset({
    "p", "div", "br", "li", "ul", "ol", "tr", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "footer", "table", "dl", "dt", "dd", "blockquote", "main", "aside", "hr",
})
LIST_ITEM_TAG = "li"
TITLE_TAG = "title"


class _TextExtractor(HTMLParser):
    """HTML to plain text: drops script/style/nav content, breaks lines at block tags, bullets list items."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in SKIP_TAGS:
            self._skip += 1
        elif not self._skip and tag in BLOCK_TAGS:
            self._chunks.append("\n")
            if tag == LIST_ITEM_TAG:
                self._chunks.append(BULLET)

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self._skip = max(self._skip - 1, 0)
        elif not self._skip and (tag in BLOCK_TAGS or tag == TITLE_TAG):
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._chunks.append(WHITESPACE_RE.sub(" ", data))

    def text(self) -> str:
        lines = [WHITESPACE_RE.sub(" ", line).strip() for line in "".join(self._chunks).split("\n")]
        return "\n".join(_collapse_blank_runs([line if line != BULLET.strip() else "" for line in lines]))


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return parser.text()


def _fetch_error(message: str) -> CvtError:
    return CvtError(ExitCode.INPUT, JD_FETCH_ERROR_ID, message, hint=JD_FETCH_HINT)


def _fetch_url(url: str) -> str:
    if urlparse(url).scheme.lower() not in JD_URL_SCHEMES:
        raise _fetch_error(f"cannot fetch '{url}': only http and https URLs are supported")
    request = urllib.request.Request(url, headers={"User-Agent": JD_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=JD_FETCH_TIMEOUT_S) as resp:  # noqa: S310 - scheme checked
            charset = resp.headers.get_content_charset() or JD_DEFAULT_CHARSET
            body = resp.read(JD_MAX_BYTES)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise _fetch_error(f"cannot fetch {url}: {getattr(exc, 'reason', exc)}") from None
    try:
        html = body.decode(charset, errors="replace")
    except LookupError:
        html = body.decode(JD_DEFAULT_CHARSET, errors="replace")
    text = html_to_text(html)
    if not text.strip():
        raise _fetch_error(f"{url} returned no readable text (the page may need JavaScript)")
    return text


def load_jd(kind: str, ref: str, stored: Path) -> str:
    """JD text for a run. `file`/`text` read the stored copy; `url` fetches once and saves into `stored`."""
    stored = Path(stored)
    try:
        saved = stored.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CvtError(
            ExitCode.INPUT, "E_JD_UNREADABLE", f"cannot read stored JD {stored.name}: {exc}",
            hint="rerun init with --jd, --jd-text or --jd-stdin",
        ) from None
    if kind != "url":
        return saved
    body = JD_URL_COMMENT_RE.sub("", saved, count=1)
    if body.strip():
        return body
    fetched = _fetch_url(ref)
    stored.write_text(JD_URL_COMMENT.format(url=ref) + fetched + "\n", encoding="utf-8")
    return fetched


def clean_jd_text(raw: str) -> str:
    """Whitespace and non-breaking-space normalization only. Semantic cleanup is the AI's job."""
    text = raw.replace("\u00a0", " ")
    for ch in INVISIBLE_CHARS:
        text = text.replace(ch, "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = _collapse_blank_runs([line.rstrip() for line in text.split("\n")])
    while lines and not lines[0]:
        lines.pop(0)
    return "\n".join(lines) + "\n" if lines else ""
