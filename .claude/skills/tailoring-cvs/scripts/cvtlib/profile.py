"""Profile helpers (interfaces.md section 5, WP-10): ID renumbering, verbatim check, script source issues,
item addressing, and the merged view that applies active correction attestations.

CV text is untrusted data: nothing here evaluates or follows it.
"""

from __future__ import annotations

import copy
import datetime
import re
import unicodedata
from typing import Iterator

from .errors import CvtError, ExitCode
from .ingest import DECORATIVE_GLYPHS, INVISIBLE_CHARS

VIOLATION_FACT_MISMATCH = "fact_mismatch"
QUOTE_CHARS = 80  # characters of a failing text quoted in a violation message
ORIGIN_SCRIPT = "script"
SEVERITY_INFO = "info"
SEVERITY_WARN = "warn"
WARN_OVERLAP_MONTHS = 2  # overlaps of at least this many months are warnings; shorter ones are info
STALE_METADATA_MONTHS = 6  # "Updated: Mon YYYY" lines older than this are stale
PRESENT = "present"
STATUS_ACTIVE = "active"
FULL_TIME_TYPES = ("employee",)
CONTACT_FIELDS = ("email", "phone", "location")
HEADER_ONLY_FIELDS = ("email", "phone")
MONTHS_PER_YEAR = 12
FIRST_MONTH, LAST_MONTH = 1, 12
MONTH_NAMES = (
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
)
MONTH_FULL_NAMES = (
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
    "november", "december",
)
MONTH_ABBREVIATION_LENGTHS = (3, 4)  # "Sep", "Sept"
PRESENT_WORDS = ("present", "current", "now", "today")
PROGRAMMING_LANGUAGES = (  # canonical spellings; matched case-sensitively with token boundaries
    "Python", "Java", "JavaScript", "TypeScript", "Golang", "Rust", "C++", "C#", "Ruby", "PHP", "Kotlin",
    "Swift", "Scala", "Bash", "PowerShell", "SQL", "Perl", "Lua", "Haskell", "Elixir", "Clojure", "Groovy",
)
SENIORITY_QUALIFIERS = (  # lowercase words that lower seniority when dropped from a title or role label
    "junior", "jr", "intern", "internship", "trainee", "apprentice", "assistant", "associate", "graduate",
    "entry-level", "student", "volunteer", "deputy", "acting", "interim", "co", "part-time", "temporary", "temp",
    "placement",
)
TITLE_TOKEN_CHARS = r"[\w.-]"  # a title token: a run of these characters; other punctuation ends it
TOKEN_TRIM_CHARS = "-."
UPDATED_RE = re.compile(r"\bupdated\s*:?\s*([A-Za-z]{3,9})\.?\s+(\d{4})", re.IGNORECASE)
DATE_RE = re.compile(r"^(\d{4})(?:-(\d{2}))?$")
WHITESPACE_RE = re.compile(r"\s+")
QUOTE_MAP = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u2033": '"',
}
DASH_CHARS = "\u2013\u2014\u2010\u2212\u2011\u2012\u2015"  # en, em, hyphen, minus, nb-hyphen, figure, bar
TRANSLATION = {ord(k): v for k, v in QUOTE_MAP.items()}
TRANSLATION.update({ord(c): "-" for c in DASH_CHARS})
STRIP_CHARS = {ord(c): None for c in (*DECORATIVE_GLYPHS, *INVISIBLE_CHARS)}

# ID patterns (interfaces.md section 1)
KIND_BASICS, KIND_SUMMARY, KIND_WORK, KIND_ENGAGEMENT = "basics", "summary", "work", "engagement"
KIND_HIGHLIGHT, KIND_EDUCATION, KIND_CERT = "highlight", "education", "certificate"
KIND_SKILL, KIND_OTHER = "skill", "other"
BASICS_ID = "basics"
EXP_ID_RE = re.compile(r"^exp-\d+$")
ENG_ID_RE = re.compile(r"^exp-\d+\.e\d+$")


# --- text normalization ---------------------------------------------------------------------------------
def normalize_text(s: str) -> str:
    """NFKC, unify quotes and dashes, strip decorative glyphs and invisible characters, collapse whitespace."""
    text = unicodedata.normalize("NFKC", s).translate(STRIP_CHARS).translate(TRANSLATION)
    return WHITESPACE_RE.sub(" ", text).strip()


def comparable(s: str) -> str:
    """`normalize_text` lowercased: the form used for substring checks (comparison only)."""
    return normalize_text(s).casefold()


_TOKEN_BEFORE_RE = re.compile(rf"({TITLE_TOKEN_CHARS}*) *$")
_TOKEN_AFTER_RE = re.compile(rf" *({TITLE_TOKEN_CHARS}*)")


def dropped_qualifier(value: str, text: str) -> str | None:
    """A short reason when `value` (a title or role label) occurs in `text` only next to a seniority qualifier
    it leaves out (e.g. "DevOps Engineer" from "Junior DevOps Engineer"), else None.

    None when `value` is empty or does not occur at all (the plain verbatim check reports that). One occurrence
    with no qualifier beside it is enough to pass. Only spaces or a hyphen may separate the value from the neighbouring
    token; `|`, `,`, `(` or a spaced ` - ` end a token."""
    needle, haystack = comparable(value), comparable(text)
    if not needle:
        return None
    found: str | None = None
    start = haystack.find(needle)
    while start != -1:
        end = start + len(needle)
        tokens = (
            _TOKEN_BEFORE_RE.search(haystack[:start]).group(1).strip(TOKEN_TRIM_CHARS),
            _TOKEN_AFTER_RE.match(haystack[end:]).group(1).strip(TOKEN_TRIM_CHARS),
        )
        hit = next((t for t in tokens if t in SENIORITY_QUALIFIERS), None)
        if hit is None:
            return None
        found = found or hit
        start = haystack.find(needle, start + 1)
    return f"drops the qualifier '{found}'" if found else None


# --- iteration and item text ----------------------------------------------------------------------------
def iter_items(profile: dict) -> Iterator[tuple[str, str, dict]]:
    """(id, kind, obj) for every addressable item in document order. Source issues are not addressable."""
    yield BASICS_ID, KIND_BASICS, profile["basics"]
    for s in profile["summary"]:
        yield s["id"], KIND_SUMMARY, s
    for w in profile["work"]:
        yield w["id"], KIND_WORK, w
        for h in w["highlights"]:
            yield h["id"], KIND_HIGHLIGHT, h
        for e in w["engagements"]:
            yield e["id"], KIND_ENGAGEMENT, e
            for h in e["highlights"]:
                yield h["id"], KIND_HIGHLIGHT, h
    for key, kind in (("education", KIND_EDUCATION), ("certificates", KIND_CERT), ("skills", KIND_SKILL),
                      ("other_sections", KIND_OTHER)):
        for obj in profile[key]:
            yield obj["id"], kind, obj


def _join(parts: list[str]) -> str:
    return " ".join(p for p in parts if p)


def _highlight_texts(obj: dict) -> list[str]:
    return [h["text"] for h in obj["highlights"]]


def _engagement_text(e: dict, dates: str) -> str:
    return _join([e["name"], e["role_label"], dates, e["summary"], *_highlight_texts(e)])


def _item_text(kind: str, obj: dict, parent: dict | None) -> str:
    if kind == KIND_BASICS:
        loc = obj["location"]
        return _join([obj["name"], obj["label"], obj["email"], obj["phone"], obj["url"],
                      loc["city"], loc["region"], loc["country"],
                      *[f"{p['network']} {p['url']}" for p in obj["profiles"]]])
    if kind in (KIND_SUMMARY, KIND_HIGHLIGHT):
        return obj["text"]
    if kind == KIND_WORK:
        dates = _join([obj["date_text"], obj["start_date"], obj["end_date"]])
        parts = [obj["name"], obj["position"], obj["location"], dates, obj["summary"], *_highlight_texts(obj)]
        parts += [_engagement_text(e, "") for e in obj["engagements"]]
        return _join(parts)
    if kind == KIND_ENGAGEMENT:
        dates = _join([parent["date_text"], parent["start_date"], parent["end_date"]]) if parent else ""
        return _engagement_text(obj, dates)
    if kind == KIND_EDUCATION:
        return _join([obj["text"], obj["institution"], obj["area"], obj["study_type"], obj["location"],
                      obj["end_date"]])
    if kind == KIND_CERT:
        return _join([obj["name"], obj["issuer"], obj["date"]])
    if kind == KIND_SKILL:  # as the CV lists it: "Name: kw1, kw2" (match quotes and provenance rely on this form)
        return _join([f"{obj['name']}:" if obj["name"] else "", ", ".join(obj["keywords"])])
    return _join([obj["title"], obj["text"]])


def _parent_work(profile: dict, item_id: str) -> dict | None:
    root = item_id.split(".")[0]
    return next((w for w in profile["work"] if w["id"] == root), None)


def item_text(profile: dict, item_id: str) -> str:
    """Text of one item. Work and engagement items include descendant texts, names, role label and dates."""
    for iid, kind, obj in iter_items(profile):
        if iid == item_id:
            parent = _parent_work(profile, iid) if kind == KIND_ENGAGEMENT else None
            return _item_text(kind, obj, parent)
    raise CvtError(ExitCode.CHECK_FAILED, "E_UNKNOWN_ITEM", f"profile has no item '{item_id}'",
                   hint="list item IDs with: cvt profile-show RUN --all")


# --- ID normalization -----------------------------------------------------------------------------------
def normalize_ids(profile: dict) -> dict:
    """Renumber every ID canonically in document order (in place). Returns the old -> new ID map."""
    mapping: dict[str, str] = {}

    def assign(obj: dict, new_id: str) -> None:
        mapping.setdefault(obj["id"], new_id)
        obj["id"] = new_id

    def renumber(items: list[dict], prefix: str) -> None:
        for n, obj in enumerate(items, 1):
            assign(obj, f"{prefix}{n}")

    renumber(profile["summary"], "sum-")
    for wn, w in enumerate(profile["work"], 1):
        assign(w, f"exp-{wn}")
        renumber(w["highlights"], f"exp-{wn}.b")
        for en, e in enumerate(w["engagements"], 1):
            assign(e, f"exp-{wn}.e{en}")
            renumber(e["highlights"], f"exp-{wn}.e{en}.b")
    renumber(profile["education"], "edu-")
    renumber(profile["certificates"], "cert-")
    renumber(profile["skills"], "skl-")
    renumber(profile["other_sections"], "oth-")
    renumber(profile["source_issues"], "iss-")
    for issue in profile["source_issues"]:
        issue["item_ids"] = [mapping.get(i, i) for i in issue["item_ids"]]
    return mapping


# --- verbatim verification ------------------------------------------------------------------------------
def _text_fields(profile: dict) -> Iterator[tuple[str, str, str]]:
    """(item_id, field label, value) for every text-bearing field that must come from the CV."""
    b = profile["basics"]
    yield BASICS_ID, "name", b["name"]
    yield BASICS_ID, "label", b["label"]
    yield BASICS_ID, "email", b["email"]
    for s in profile["summary"]:
        yield s["id"], "text", s["text"]
    for w in profile["work"]:
        for field in ("name", "position", "date_text", "summary"):
            yield w["id"], field, w[field]
        for h in w["highlights"]:
            yield h["id"], "text", h["text"]
        for e in w["engagements"]:
            for field in ("name", "role_label", "summary"):
                yield e["id"], field, e[field]
            for h in e["highlights"]:
                yield h["id"], "text", h["text"]
    for ed in profile["education"]:
        yield ed["id"], "text", ed["text"]
        yield ed["id"], "institution", ed["institution"]
    for c in profile["certificates"]:
        yield c["id"], "name", c["name"]
    for g in profile["skills"]:
        yield g["id"], "name", g["name"]
        for kw in g["keywords"]:
            yield g["id"], "keyword", kw
    for o in profile["other_sections"]:
        yield o["id"], "text", o["text"]


def has_year(year: str, text: str) -> bool:
    """True when `year` appears in `text` as a whole number (`2023` does not match `12023`)."""
    return re.search(rf"(?<!\d){re.escape(year)}(?!\d)", text) is not None


def _month_pattern(month: int) -> re.Pattern[str]:
    full = MONTH_FULL_NAMES[month - 1]
    names = {full, *(full[:n] for n in MONTH_ABBREVIATION_LENGTHS)}
    alternatives = "|".join(sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<![a-z])(?:{alternatives})(?![a-z])|(?<!\d)0?{month}(?!\d)", re.IGNORECASE)


def date_consistency(date_value: str, date_text: str) -> str | None:
    """None when the normalized date agrees with the CV's `date_text`, else a short reason.

    `""` is always allowed; `present` needs Present/Current/Now/Today; `YYYY` needs the year; `YYYY-MM` also
    needs the month as its English name, a 3-4 letter abbreviation, or its number.
    """
    if not date_value:
        return None
    text = normalize_text(date_text)
    if date_value == PRESENT:
        words = "|".join(PRESENT_WORDS)
        if re.search(rf"(?<![a-z])(?:{words})(?![a-z])", text, re.IGNORECASE):
            return None
        return "no Present/Current/Now/Today in date_text"
    m = DATE_RE.match(date_value)
    if not m:
        return "not 'YYYY', 'YYYY-MM', or 'present'"
    year, month = m.group(1), m.group(2)
    if not has_year(year, text):
        return f"year {year} not in date_text"
    if month:
        number = int(month)
        if not FIRST_MONTH <= number <= LAST_MONTH:
            return f"month {month} is not 01-12"
        if not _month_pattern(number).search(text):
            return f"month {month} not in date_text"
    return None


def _dated_items(profile: dict) -> Iterator[tuple[str, dict]]:
    """Work items and engagements that carry dates (`start_date`, `end_date`, `date_text`)."""
    for w in profile["work"]:
        yield w["id"], w
        for e in w["engagements"]:
            if "date_text" in e:
                yield e["id"], e


def verify_verbatim(profile: dict, cv_text: str) -> list[dict]:
    """A `fact_mismatch` violation for every text field that is not a substring of the CV (comparable form),
    and for every normalized date that disagrees with its `date_text`."""
    haystack = comparable(cv_text)
    violations = []
    for item_id, obj in _dated_items(profile):
        for field in ("start_date", "end_date"):
            reason = date_consistency(obj.get(field, ""), obj["date_text"]) if obj.get("date_text") else None
            if reason:
                violations.append({
                    "code": VIOLATION_FACT_MISMATCH, "item_id": item_id,
                    "message": f"{field} '{obj.get(field, '')}' is not consistent with date_text "
                               f"'{normalize_text(obj['date_text'])[:QUOTE_CHARS]}' ({reason})",
                })
    for item_id, field, value in _text_fields(profile):
        needle = comparable(value)
        if needle and needle not in haystack:
            violations.append({
                "code": VIOLATION_FACT_MISMATCH, "item_id": item_id,
                "message": f"{field} not found verbatim in cv.txt: '{normalize_text(value)[:QUOTE_CHARS]}'",
            })
    for item_id, field, value in _title_fields(profile):
        if reason := dropped_qualifier(value, cv_text):
            violations.append({
                "code": VIOLATION_FACT_MISMATCH, "item_id": item_id,
                "message": f"{field} '{normalize_text(value)[:QUOTE_CHARS]}' {reason} in cv.txt; copy the full {field}",
            })
    return violations


def _title_fields(profile: dict) -> Iterator[tuple[str, str, str]]:
    """(item_id, field label, value) for work titles and engagement role labels."""
    for w in profile["work"]:
        yield w["id"], "position", w["position"]
        for e in w["engagements"]:
            yield e["id"], "role_label", e["role_label"]


# --- deterministic source issues ------------------------------------------------------------------------
def _month_index(value: str, *, end: bool, today: datetime.date) -> int | None:
    """Months since year 0 for 'YYYY-MM' / 'YYYY' / 'present'. A bare year is its first (or last) month."""
    if value == PRESENT:
        return today.year * MONTHS_PER_YEAR + today.month - 1
    m = DATE_RE.match(value)
    if not m:
        return None
    month = int(m.group(2)) if m.group(2) else (LAST_MONTH if end else FIRST_MONTH)
    return int(m.group(1)) * MONTHS_PER_YEAR + month - 1


def _label(name: str, text: str) -> str:
    return f"{name} ({text})" if text else name


def _work_ranges(profile: dict, today: datetime.date) -> list[tuple[dict, int, int]]:
    out = []
    for w in profile["work"]:
        start = _month_index(w["start_date"], end=False, today=today)
        end = _month_index(w["end_date"], end=True, today=today)
        if start is not None and end is not None:
            out.append((w, start, end))
    return out


def _issue(kind: str, severity: str, message: str, item_ids: list[str]) -> dict:
    return {"id": "", "kind": kind, "severity": severity, "message": message, "item_ids": item_ids,
            "origin": ORIGIN_SCRIPT}


def _check_work_overlaps(profile: dict, today: datetime.date) -> list[dict]:
    ranges = _work_ranges(profile, today)
    issues = []
    for w, start, end in ranges:
        if end < start:
            issues.append(_issue("date_conflict", SEVERITY_WARN,
                                 f"{w['name']} ends ({w['end_date']}) before it starts ({w['start_date']}).",
                                 [w["id"]]))
    for i, (a, a_start, a_end) in enumerate(ranges):
        for b, b_start, b_end in ranges[i + 1:]:
            if a_end < a_start or b_end < b_start:
                continue
            overlap = min(a_end, b_end) - max(a_start, b_start)
            if overlap < 0:
                continue
            names = f"{_label(a['name'], a['date_text'])} and {_label(b['name'], b['date_text'])}"
            if overlap == 0:
                msg, sev = f"{names} touch in the same boundary month.", SEVERITY_INFO
            else:
                sev = SEVERITY_WARN if overlap >= WARN_OVERLAP_MONTHS else SEVERITY_INFO
                msg = f"{names} overlap by {overlap} month{'s' if overlap != 1 else ''}."
            issues.append(_issue("date_overlap", sev, msg, [a["id"], b["id"]]))
    return issues


def _check_education_dates(profile: dict, today: datetime.date) -> list[dict]:
    issues = []
    full_time = [(w, s, e) for w, s, e in _work_ranges(profile, today) if w["employment_type"] in FULL_TIME_TYPES]
    for ed in profile["education"]:
        end = _month_index(ed["end_date"], end=True, today=today)
        if end is None:
            continue
        for w, start, w_end in full_time:
            if start <= end <= w_end:
                issues.append(_issue(
                    "date_overlap", SEVERITY_INFO,
                    f"{ed['study_type'] or 'Degree'} at {ed['institution']} ends {ed['end_date']}, "
                    f"inside the full-time role at {w['name']} ({w['date_text']}).", [w["id"], ed["id"]]))
    seen_years: dict[str, dict] = {}
    for ed in profile["education"]:
        year = ed["end_date"][:4]
        if not year:
            continue
        if year in seen_years:
            other = seen_years[year]
            issues.append(_issue("date_conflict", SEVERITY_INFO,
                                 f"Two degrees ({other['institution']} and {ed['institution']}) share the year {year}.",
                                 [other["id"], ed["id"]]))
        else:
            seen_years[year] = ed
    return issues


def _check_contact(profile: dict, cv_text: str) -> list[dict]:
    b = profile["basics"]
    missing = [f for f in CONTACT_FIELDS if not (any(b["location"].values()) if f == "location" else b[f])]
    issues = []
    if missing:
        sev = SEVERITY_WARN if "email" in missing else SEVERITY_INFO
        issues.append(_issue("missing_contact", sev, f"No {', '.join(missing)} found in the CV.", [BASICS_ID]))
    name = comparable(b["name"])
    for fld in HEADER_ONLY_FIELDS:
        value = comparable(b[fld])
        if not value:
            continue
        lines = [comparable(ln) for ln in cv_text.splitlines() if value in comparable(ln)]
        if lines and name and all(name in ln for ln in lines):
            issues.append(_issue(
                "extraction", SEVERITY_INFO,
                f"The {fld} appears only in repeated header lines that also hold the name; confirm it is current.",
                [BASICS_ID]))
    return issues


def _months_ago(month_name: str, year: int, today: datetime.date) -> int | None:
    key = month_name[:3].lower()
    if key not in MONTH_NAMES:
        return None
    return (today.year - year) * MONTHS_PER_YEAR + today.month - (MONTH_NAMES.index(key) + 1)


def _check_stale(cv_text: str, today: datetime.date) -> list[dict]:
    issues = []
    for line in cv_text.splitlines():
        m = UPDATED_RE.search(line)
        age = _months_ago(m.group(1), int(m.group(2)), today) if m else None
        if age is not None and age > STALE_METADATA_MONTHS:
            issues.append(_issue("stale_metadata", SEVERITY_INFO,
                                 f"The CV says '{normalize_text(m.group(0))}', {age} months ago; "
                                 "confirm nothing has changed since.", []))
    return issues


def _mentions(text: str, term: str) -> bool:
    return re.search(r"(?<![\w+#])%s(?![\w+#])" % re.escape(term), text) is not None


def _check_summary_languages(profile: dict) -> list[dict]:
    skills_text = normalize_text(" ".join(kw for g in profile["skills"] for kw in g["keywords"]))
    absent: dict[str, list[str]] = {}
    for s in profile["summary"]:
        text = normalize_text(s["text"])
        for lang in PROGRAMMING_LANGUAGES:
            if _mentions(text, lang) and not _mentions(skills_text, lang):
                absent.setdefault(lang, []).append(s["id"])
    if not absent:
        return []
    ids = sorted({i for v in absent.values() for i in v})
    return [_issue("inconsistency", SEVERITY_INFO,
                   f"The summary mentions {', '.join(absent)} but the skills section does not list it.", ids)]


def script_source_issues(profile: dict, cv_text: str, today: datetime.date) -> list[dict]:
    """The deterministic issues (`origin: script`), numbered after the profile's existing non-script issues.

    A script issue is skipped when an AI issue of the same kind already covers the same items.
    """
    kept = [i for i in profile["source_issues"] if i["origin"] != ORIGIN_SCRIPT]
    covered = {(i["kind"], frozenset(i["item_ids"])) for i in kept}
    found = [
        *_check_work_overlaps(profile, today), *_check_education_dates(profile, today),
        *_check_contact(profile, cv_text), *_check_stale(cv_text, today), *_check_summary_languages(profile),
    ]
    fresh = [i for i in found if (i["kind"], frozenset(i["item_ids"])) not in covered]
    for n, issue in enumerate(fresh, len(kept) + 1):
        issue["id"] = f"iss-{n}"
    return fresh


def apply_script_issues(profile: dict, cv_text: str, today: datetime.date) -> list[dict]:
    """Replace previous script issues with fresh ones (idempotent). Returns the new script issues."""
    profile["source_issues"] = [i for i in profile["source_issues"] if i["origin"] != ORIGIN_SCRIPT]
    normalize_ids(profile)
    fresh = script_source_issues(profile, cv_text, today)
    profile["source_issues"].extend(fresh)
    return fresh


# --- merged view ----------------------------------------------------------------------------------------
def active_corrections(attestations: list[dict], statuses: tuple[str, ...] = (STATUS_ACTIVE,)) -> list[dict]:
    return [a for a in attestations if a["type"] == "correction" and a["status"] in statuses
            and a["correction"]["item_id"] and a["correction"]["field"]]


def merged_view(profile: dict, attestations: list[dict], *, statuses: tuple[str, ...] = (STATUS_ACTIVE,)) -> dict:
    """Deep copy of `profile` with every correction attestation in `statuses` (default: ACTIVE only) applied."""
    merged = copy.deepcopy(profile)
    corrections = active_corrections(attestations, statuses)
    if not corrections:
        return merged
    items = {iid: obj for iid, _kind, obj in iter_items(merged)}
    for att in corrections:
        c = att["correction"]
        target = items.get(c["item_id"])
        if target is not None and isinstance(target.get(c["field"]), str):
            target[c["field"]] = c["new_value"]
    return merged
