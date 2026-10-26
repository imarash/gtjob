"""Build `profile.json` from the AI's `profile-map.json` (line ranges) and `cv.txt` (interfaces.md section 5).

The AI never retypes CV text: every text field here is copied from the cited lines. CV text is untrusted data.
"""

from __future__ import annotations

import re

from . import jsonio
from .profile import (
    DATE_RE, DECORATIVE_GLYPHS, comparable, date_consistency, dropped_qualifier, normalize_text, has_year,
)

CODE_RANGE, CODE_UNMAPPED, CODE_NOT_VERBATIM = "range_error", "unmapped_line", "not_verbatim"
LINE_NUMBER_FORMAT = "{n:>4}| {line}"
UNMAPPED_QUOTE_CHARS = 60
VALUE_QUOTE_CHARS = 80
SCHEMA_VERSION = "1"
ORIGIN_AI = "ai"
SKILL_SEPARATORS = ",;|\u2022"
OPEN_BRACKETS, CLOSE_BRACKETS = "([{", ")]}"
SKILL_LABEL_RE = re.compile(r"^[^%s:]{1,80}:\s+" % re.escape(SKILL_SEPARATORS))
LEADING_MARKER_RE = re.compile(r"^\s*(?:[-*\u2013\u2014]|[%s])\s+" % re.escape(DECORATIVE_GLYPHS))
LEADING_GLYPH_RE = re.compile(r"^\s*[%s]\s*" % re.escape(DECORATIVE_GLYPHS))
RANGE_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


def cv_lines(cv_text: str) -> list[str]:
    """The lines `numbered_cv` numbers (1-based). A trailing newline does not add an empty line."""
    lines = cv_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def numbered_cv(cv_text: str) -> str:
    """`'  41| text'` per line, blank lines included: the numbering profile-map ranges refer to."""
    return "\n".join(LINE_NUMBER_FORMAT.format(n=n, line=line) for n, line in enumerate(cv_lines(cv_text), 1))


def _strip_marker(line: str) -> str:
    return LEADING_GLYPH_RE.sub("", LEADING_MARKER_RE.sub("", line, count=1), count=1).strip()


class _Builder:
    def __init__(self, cv_text: str) -> None:
        self.lines = cv_lines(cv_text)
        self.cv_comparable = comparable(cv_text)
        self.claims: dict[int, str] = {}  # line number -> label of the range that claimed it
        self.violations: list[dict] = []
        self.overlap_pairs: set[tuple[str, str]] = set()

    def _violate(self, code: str, item_id: str, message: str) -> None:
        self.violations.append({"code": code, "item_id": item_id, "message": message})

    def span(self, rng: str, label: str) -> tuple[int, int]:
        """Validate and claim a range. Returns (start, end), or (0, -1) (empty) after a `range_error`."""
        m = RANGE_RE.match(rng)
        if not m:
            self._violate(CODE_RANGE, label, f"{label}: '{rng}' is not a line range like '41' or '41-43'")
            return 0, -1
        start, end = int(m.group(1)), int(m.group(2) or m.group(1))
        if start < 1 or end > len(self.lines):
            self._violate(CODE_RANGE, label,
                          f"{label}: range {rng} is out of bounds (the CV has lines 1-{len(self.lines)})")
            return 0, -1
        if start > end:
            self._violate(CODE_RANGE, label, f"{label}: range {rng} is reversed")
            return 0, -1
        for n in range(start, end + 1):
            owner = self.claims.setdefault(n, label)
            if owner != label and (owner, label) not in self.overlap_pairs:
                self.overlap_pairs.add((owner, label))
                self._violate(CODE_RANGE, label, f"{label}: line {n} is already claimed by {owner}")
        return start, end

    def raw(self, rng: str, label: str) -> list[str]:
        start, end = self.span(rng, label)
        return self.lines[start - 1:end] if end >= start else []

    @staticmethod
    def join(lines: list[str]) -> str:
        """Lines joined with single spaces; leading bullet marker stripped; whitespace collapsed."""
        if lines:
            lines = [_strip_marker(lines[0]), *lines[1:]]
        return " ".join(" ".join(lines).split())

    def text(self, rng: str, label: str) -> str:
        return self.join(self.raw(rng, label))

    def texts(self, ranges: list[str], label: str) -> str:
        return " ".join(t for t in (self.text(r, label) for r in ranges) if t)

    def check_in(self, value: str, cited: list[str], label: str, what: str) -> None:
        needle = comparable(value)
        if needle and needle not in comparable(" ".join(cited)):
            self._violate(CODE_NOT_VERBATIM, label,
                          f"{what} '{value[:VALUE_QUOTE_CHARS]}' not found in its cited lines")

    def check_qualifier(self, value: str, cited: list[str], label: str, what: str) -> None:
        """A title or role label must keep every seniority qualifier its cited lines give it."""
        if reason := dropped_qualifier(value, " ".join(cited)):
            self._violate(CODE_NOT_VERBATIM, label,
                          f"{label}: {what} '{value[:VALUE_QUOTE_CHARS]}' {reason} in its cited lines; "
                          f"copy the full {what}")

    def check_parts(self, location: str, cited: list[str], label: str, what: str) -> None:
        """Each comma-separated part of a location must be in the cited lines."""
        for part in location.split(","):
            self.check_in(part, cited, label, what)

    def check_year(self, value: str, cited: list[str], label: str, what: str) -> None:
        """The year of a normalized date must be a whole number in the cited lines."""
        m = DATE_RE.match(value)
        if m and not has_year(m.group(1), normalize_text(" ".join(cited))):
            self._violate(CODE_NOT_VERBATIM, label, f"{what} year {m.group(1)} not found in its cited lines")

    def check_dates(self, obj: dict, label: str) -> None:
        date_text = obj.get("date_text", "")
        if not date_text:
            return
        for field in ("start_date", "end_date"):
            if field in obj and (reason := date_consistency(obj[field], date_text)):
                self._violate(CODE_NOT_VERBATIM, label,
                              f"{label}: {field} '{obj[field]}' is not consistent with date_text "
                              f"'{date_text[:VALUE_QUOTE_CHARS]}' ({reason})")

    def check_anywhere(self, value: str, label: str, what: str) -> None:
        needle = comparable(value)
        if needle and needle not in self.cv_comparable:
            self._violate(CODE_NOT_VERBATIM, label, f"{what} '{value[:VALUE_QUOTE_CHARS]}' not found in the CV")

    def highlights(self, items: list[dict], prefix: str) -> list[dict]:
        out = []
        for n, h in enumerate(items, 1):
            out.append({"id": f"{prefix}.b{n}", "kind": h["kind"], "text": self.text(h["lines"], f"{prefix}.b{n}")})
        return out

    def keywords(self, ranges: list[str], name: str, label: str) -> list[str]:
        lines = [ln for r in ranges for ln in self.raw(r, label)]
        if not lines:
            return []
        lines = [_strip_marker(ln) for ln in lines]
        if name:
            lines[0] = SKILL_LABEL_RE.sub("", lines[0], count=1)
        return split_keywords(" ".join(lines))


def split_keywords(text: str) -> list[str]:
    """Split on `, ; | •`, ignoring separators inside brackets; trim each keyword and drop empties."""
    parts, buf, depth = [], [], 0
    for ch in text:
        if ch in OPEN_BRACKETS:
            depth += 1
        elif ch in CLOSE_BRACKETS:
            depth = max(depth - 1, 0)
        if ch in SKILL_SEPARATORS and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [" ".join(p.split()) for p in parts if p.strip()]


def build_profile(pmap: dict, cv_text: str, *, person_slug: str, cv_sha256: str) -> tuple[dict, list[dict]]:
    """Build the profile from a (schema-valid) map. Returns (profile, violations); violations means do not use."""
    b = _Builder(cv_text)
    mb = pmap["basics"]
    header_lines = [ln for r in mb["lines"] for ln in b.raw(r, "basics")]
    b.check_in(mb["name"], header_lines, "basics", "name")
    for key in ("city", "region", "country"):
        b.check_in(mb[key], header_lines, "basics", key)
    b.check_anywhere(mb["email"], "basics", "email")
    basics = {
        "id": "basics", "name": mb["name"], "label": mb["label"], "email": mb["email"], "phone": mb["phone"],
        "url": mb["url"], "location": {"city": mb["city"], "region": mb["region"], "country": mb["country"]},
        "profiles": [dict(p) for p in mb["profiles"]],
    }
    summary = [{"id": f"sum-{n}", "text": b.text(r, f"sum-{n}")} for n, r in enumerate(pmap["summary_lines"], 1)]

    work = []
    for wn, w in enumerate(pmap["work"], 1):
        wid = f"exp-{wn}"
        head = b.raw(w["header_lines"], wid)
        b.check_in(w["name"], head, wid, "employer")
        b.check_in(w["position"], head, wid, "title")
        b.check_qualifier(w["position"], head, wid, "title")
        b.check_in(w["date_text"], head, wid, "date_text")
        b.check_parts(w["location"], head, wid, "location")
        b.check_dates(w, wid)
        engagements = []
        for en, e in enumerate(w["engagements"], 1):
            eid = f"{wid}.e{en}"
            ehead = b.raw(e["header_lines"], eid)
            b.check_in(e["name"], ehead, eid, "client")
            b.check_in(e["role_label"], ehead, eid, "role label")
            b.check_qualifier(e["role_label"], ehead, eid, "role label")
            b.check_dates(e, eid)
            engagements.append({
                "id": eid, "kind": e["kind"], "name": e["name"], "role_label": e["role_label"],
                "summary": b.texts(e["summary_lines"], eid), "highlights": b.highlights(e["highlights"], eid),
            })
        work.append({
            "id": wid, "name": w["name"], "location": w["location"], "position": w["position"],
            "employment_type": w["employment_type"], "start_date": w["start_date"], "end_date": w["end_date"],
            "date_text": w["date_text"], "summary": b.texts(w["summary_lines"], wid),
            "highlights": b.highlights(w["highlights"], wid), "engagements": engagements,
        })

    education = []
    for n, ed in enumerate(pmap["education"], 1):
        eid = f"edu-{n}"
        cited = b.raw(ed["lines"], eid)
        b.check_in(ed["institution"], cited, eid, "institution")
        b.check_in(ed["area"], cited, eid, "degree area")
        b.check_in(ed["study_type"], cited, eid, "degree type")
        b.check_parts(ed["location"], cited, eid, "location")
        b.check_year(ed["end_date"], cited, eid, "end_date")
        education.append({
            "id": eid, "institution": ed["institution"], "area": ed["area"], "study_type": ed["study_type"],
            "location": ed["location"], "end_date": ed["end_date"], "text": b.join(cited),
        })

    certificates = []
    for n, c in enumerate(pmap["certificates"], 1):
        cid = f"cert-{n}"
        cert_lines = b.raw(c["lines"], cid)
        b.check_in(c["name"], cert_lines, cid, "certificate")
        b.check_year(c["date"], cert_lines, cid, "date")
        certificates.append({"id": cid, "name": c["name"], "issuer": c["issuer"], "date": c["date"]})

    skills = [
        {"id": f"skl-{n}", "name": g["name"], "keywords": b.keywords(g["lines"], g["name"], f"skl-{n}")}
        for n, g in enumerate(pmap["skills"], 1)
    ]
    other = [
        {"id": f"oth-{n}", "title": o["title"], "text": b.texts(o["lines"], f"oth-{n}")}
        for n, o in enumerate(pmap["other_sections"], 1)
    ]
    for rng in pmap["ignored_lines"]:
        b.span(rng, "ignored_lines")
    for n, line in enumerate(b.lines, 1):
        if line.strip() and n not in b.claims:
            b._violate(CODE_UNMAPPED, f"L{n}", f"line {n} is not mapped: '{line.strip()[:UNMAPPED_QUOTE_CHARS]}'")

    issues = [
        {"id": f"iss-{n}", "kind": i["kind"], "severity": i["severity"], "message": i["message"],
         "item_ids": list(i["item_ids"]), "origin": ORIGIN_AI}
        for n, i in enumerate(pmap["source_issues"], 1)
    ]
    profile = {
        "schema_version": SCHEMA_VERSION, "person_slug": person_slug, "cv_sha256": cv_sha256,
        "created_at": jsonio.now_iso(), "basics": basics, "summary": summary, "work": work,
        "education": education, "certificates": certificates, "skills": skills, "other_sections": other,
        "source_issues": issues,
    }
    return profile, b.violations
