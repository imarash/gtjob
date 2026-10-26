"""Keyword coverage of the rendered PDF text against the JD (interfaces.md section 10, gate `keyword_coverage`)."""

from __future__ import annotations

import re
import unicodedata

WARN_BELOW = 0.70  # must-have keyword coverage under this ratio warns
MUST_KIND = "must"
_WHITESPACE = re.compile(r"\s+")


def _fold(text: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", text)).strip().casefold()


def _contains(haystack: str, term: str) -> bool:
    """Case-insensitive, whitespace-tolerant, word-bounded (`C++` and `CI/CD` are matched as whole tokens)."""
    needle = _fold(term)
    if not needle:
        return False
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


def _alternatives(jd: dict) -> dict[str, list[str]]:
    """Folded keyword -> every spelling that counts as a hit (the keyword, its entry's synonyms, entries listing it)."""
    groups: dict[str, list[str]] = {}
    for entry in jd["keywords"]:
        spellings = [entry["term"], *entry["synonyms"]]
        for spelling in spellings:
            bucket = groups.setdefault(_fold(spelling), [])
            bucket += [s for s in spellings if s not in bucket]
    return groups


def coverage(pdf_text: str, jd: dict) -> dict:
    """`validation.coverage`: per-requirement found/missing keywords, plus the must-have keyword totals."""
    haystack = _fold(pdf_text)
    alternatives = _alternatives(jd)
    verdicts: dict[str, bool] = {}

    def hit(keyword: str) -> bool:
        key = _fold(keyword)
        if key not in verdicts:
            verdicts[key] = any(_contains(haystack, s) for s in [keyword, *alternatives.get(key, [])])
        return verdicts[key]

    by_requirement = []
    must_order: list[str] = []
    for req in jd["requirements"]:
        found = [k for k in req["keywords"] if hit(k)]
        by_requirement.append({
            "req_id": req["id"], "kind": req["kind"], "found_terms": found,
            "missing_terms": [k for k in req["keywords"] if k not in found],
        })
        if req["kind"] == MUST_KIND:
            must_order += [k for k in req["keywords"] if _fold(k) not in {_fold(m) for m in must_order}]
    found_must = [k for k in must_order if hit(k)]
    return {
        "must_keywords_total": len(must_order), "must_keywords_found": len(found_must),
        "missing": [k for k in must_order if k not in found_must], "by_requirement": by_requirement,
    }


def ratio(cov: dict) -> float:
    """Found / total must-have keywords; 1.0 when the JD lists none."""
    total = cov["must_keywords_total"]
    return cov["must_keywords_found"] / total if total else 1.0
