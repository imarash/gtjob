"""Deterministic checks for the AI-written `jd.json` and `match.json` (interfaces.md sections 3 and 5)."""

from __future__ import annotations

import copy
import re

from . import lexicon
from .profile import comparable
from .provenance import (
    STATUS_REVOKED, SCOPE_UNRESOLVED, UNKNOWN_REF, _att_text, _item_texts, _violation,
)

CODE_SCHEMA = "schema"
CODE_NOT_VERBATIM = "not_verbatim"
KIND_MUST, KIND_NICE = "must", "nice"
STRENGTH_NONE, STRENGTH_STRONG, STRENGTH_PARTIAL = "none", "strong", "partial"
STRENGTHS = (STRENGTH_STRONG, STRENGTH_PARTIAL, STRENGTH_NONE)
MAX_METRIC_OPPORTUNITIES = 5
QUOTE_FALLBACK_CHARS = 120
REQ_ID_FORMAT = "req-{n}"
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_ATT_ID_RE = re.compile(r"^att-\d{3,}$")


# --- jd.json ------------------------------------------------------------------------------------------------
def check_jd(jd: dict, jd_text: str, jd_sha256: str) -> list[dict]:
    """Violations of the deterministic jd rules: sha, requirement ids, keyword refs, a must, verbatim noise/company."""
    out: list[dict] = []
    if jd["jd_sha256"] != jd_sha256:
        out.append(_violation(CODE_SCHEMA, "jd_sha256", f"jd_sha256 {jd['jd_sha256'][:12]} does not match the "
                                                         f"run's JD ({jd_sha256[:12]}); copy it from the packet"))
    ids = [r["id"] for r in jd["requirements"]]
    for pos, rid in enumerate(ids, start=1):
        want = REQ_ID_FORMAT.format(n=pos)
        if ids.count(rid) > 1:
            out.append(_violation(CODE_SCHEMA, rid, f"requirement id {rid} is used more than once"))
        elif rid != want:
            out.append(_violation(CODE_SCHEMA, rid, f"requirement at position {pos} is {rid}; ids must run "
                                                     f"{REQ_ID_FORMAT.format(n=1)}, {REQ_ID_FORMAT.format(n=2)}, ... in order"))
    known = set(ids)
    for i, kw in enumerate(jd["keywords"]):
        for rid in kw["req_ids"]:
            if rid not in known:
                out.append(_violation(UNKNOWN_REF, f"keywords[{i}]", f"keyword '{kw['term']}' cites {rid}, "
                                                                      f"which is not a requirement"))
    if not any(r["kind"] == KIND_MUST for r in jd["requirements"]):
        out.append(_violation(CODE_SCHEMA, "requirements", "no requirement has kind 'must'; mark the "
                                                           "non-negotiable requirements as must"))
    haystack = comparable(jd_text)
    for i, noise in enumerate(jd["noise"]):
        if comparable(noise["text"]) not in haystack:
            out.append(_violation(CODE_NOT_VERBATIM, f"noise[{i}]", f"noise item {i} ({noise['kind']}) is not a "
                                                                    f"substring of jd.txt; copy the segment verbatim"))
    if jd["company"] and comparable(jd["company"]) not in haystack:
        out.append(_violation(CODE_NOT_VERBATIM, "company", f"company '{jd['company']}' does not appear in jd.txt; "
                                                            f"use '' when the posting does not name it"))
    return sorted(out, key=lambda v: (v["item_id"], v["message"]))


def normalize_jd(jd: dict) -> dict:
    """Trim strings; merge keywords with the same term (union synonyms and req_ids, max weight); heaviest first."""
    out = _trim(copy.deepcopy(jd))
    merged: dict[str, dict] = {}
    for kw in out["keywords"]:
        key = kw["term"].casefold()
        cur = merged.get(key)
        if cur is None:
            merged[key] = kw
            continue
        cur["weight"] = max(cur["weight"], kw["weight"])
        cur["synonyms"] += [s for s in kw["synonyms"] if s not in cur["synonyms"]]
        cur["req_ids"] += [r for r in kw["req_ids"] if r not in cur["req_ids"]]
    out["keywords"] = sorted(merged.values(), key=lambda k: -k["weight"])
    return out


def _trim(node):
    if isinstance(node, str):
        return node.strip()
    if isinstance(node, list):
        return [_trim(v) for v in node]
    if isinstance(node, dict):
        return {k: _trim(v) for k, v in node.items()}
    return node


# --- match.json ---------------------------------------------------------------------------------------------
def _quote_from(text: str, keywords: list[str]) -> str:
    """The sentence of `text` holding the first matched keyword, else its first QUOTE_FALLBACK_CHARS characters."""
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    for kw in keywords:
        for sentence in sentences:
            if lexicon.supports(kw, sentence):
                return sentence
    if len(text) <= QUOTE_FALLBACK_CHARS:
        return text.strip()
    cut = text[:QUOTE_FALLBACK_CHARS]
    return (cut.rsplit(" ", 1)[0] if " " in cut and text[QUOTE_FALLBACK_CHARS] != " " else cut).strip()


def _req_keywords(req: dict, jd: dict) -> list[str]:
    terms = list(req["keywords"])
    for kw in jd["keywords"]:
        if req["id"] in kw["req_ids"] or kw["term"] in terms:
            terms += [kw["term"], *kw["synonyms"]]
    return list(dict.fromkeys(terms))


def check_match(
    match: dict, jd: dict, profile: dict, attestations: list[dict],
) -> tuple[dict, list[dict]]:
    """(match with recomputed coverage and filled empty quotes, violations). `attestations` are the usable ones."""
    out = copy.deepcopy(match)
    texts = _item_texts(profile)
    atts = {a["id"]: a for a in attestations
            if a["status"] != STATUS_REVOKED and a["scope"]["kind"] != SCOPE_UNRESOLVED}
    reqs = {r["id"]: r for r in jd["requirements"]}
    violations: list[dict] = []
    seen: dict[str, int] = {}
    for rm in out["requirements"]:
        rid = rm["req_id"]
        seen[rid] = seen.get(rid, 0) + 1
        if rid not in reqs:
            violations.append(_violation(UNKNOWN_REF, rid, f"{rid} is not a requirement of jd.json"))
            continue
        _check_req_match(rm, reqs[rid], jd, texts, atts, violations)
    for rid in reqs:
        n = seen.get(rid, 0)
        if n != 1:
            violations.append(_violation(CODE_SCHEMA, rid, f"{rid} appears {n} times in match.json; "
                                                           f"each jd requirement must appear exactly once"))
    for i, mo in enumerate(out["metric_opportunities"]):
        if mo["item_id"] not in texts:
            violations.append(_violation(UNKNOWN_REF, mo["item_id"], f"metric_opportunities[{i}] cites "
                                                                      f"{mo['item_id']}, which is not in the profile"))
    if len(out["metric_opportunities"]) > MAX_METRIC_OPPORTUNITIES:
        violations.append(_violation(CODE_SCHEMA, "metric_opportunities",
                                     f"{len(out['metric_opportunities'])} metric opportunities; keep at most "
                                     f"{MAX_METRIC_OPPORTUNITIES}"))
    out["coverage"] = recompute_coverage(out, jd)
    return out, sorted(violations, key=lambda v: (v["item_id"], v["message"]))


def _check_req_match(
    rm: dict, req: dict, jd: dict, texts: dict[str, str], atts: dict[str, dict], violations: list[dict],
) -> None:
    rid = rm["req_id"]
    if rm["strength"] == STRENGTH_NONE and rm["evidence"]:
        violations.append(_violation(CODE_SCHEMA, rid, f"{rid} has strength 'none' but lists evidence; "
                                                       f"use [] or raise the strength"))
    if rm["strength"] != STRENGTH_NONE and not rm["evidence"]:
        violations.append(_violation(CODE_SCHEMA, rid, f"{rid} has strength '{rm['strength']}' but no evidence"))
    keywords = _req_keywords(req, jd)
    for ev in rm["evidence"]:
        ref = ev["ref"]
        source = texts.get(ref) if not _ATT_ID_RE.match(ref) else (_att_text(atts[ref]) if ref in atts else None)
        if source is None:
            violations.append(_violation(UNKNOWN_REF, rid, f"{rid} evidence cites {ref}, which is not in the "
                                                           f"profile or the usable attestations"))
            continue
        if not ev["quote"].strip():
            ev["quote"] = _quote_from(atts[ref]["claim"] if ref in atts else source, keywords)
        elif comparable(ev["quote"]) not in comparable(source):
            violations.append(_violation(CODE_NOT_VERBATIM, rid, f"{rid} quote for {ref} is not a substring of "
                                                                 f"its text: '{ev['quote'][:60]}'"))


def recompute_coverage(match: dict, jd: dict) -> dict:
    """Counts of must/nice requirements by strength, from the jd kinds and the match strengths."""
    kinds = {r["id"]: r["kind"] for r in jd["requirements"]}
    cov = {f"{k}_{s}": 0 for k in (KIND_MUST, KIND_NICE) for s in ("total", *STRENGTHS)}
    for rm in match["requirements"]:
        kind = kinds.get(rm["req_id"])
        if kind in (KIND_MUST, KIND_NICE):
            cov[f"{kind}_total"] += 1
            cov[f"{kind}_{rm['strength']}"] += 1
    return {k: cov[k] for k in (
        "must_total", "must_strong", "must_partial", "must_none",
        "nice_total", "nice_strong", "nice_partial", "nice_none",
    )}


# --- tailored.json ids --------------------------------------------------------------------------------------
def renumber_tailored(tailored: dict) -> tuple[dict, dict[str, str]]:
    """Canonical `t-` ids by position (keeping `source_refs`); returns (new tailored, old id -> new id).

    Summary is `t-sum`; skills groups, certifications and education are numbered by position; entries and
    engagements take `t-<profile_id>`; bullets are numbered by position inside their parent. `open_items[].item_ids`
    are rewritten to the new ids.
    """
    out = copy.deepcopy(tailored)
    idmap: dict[str, str] = {}

    def setid(obj: dict, new: str) -> None:
        if obj["id"] != new:
            idmap[obj["id"]] = new
            obj["id"] = new

    setid(out["summary"], "t-sum")
    for i, group in enumerate(out["skills"], start=1):
        setid(group, f"t-skl-{i}")
    for entry in out["experience"]:
        base = f"t-{entry['profile_id']}"
        setid(entry, base)
        for j, bullet in enumerate(entry["bullets"], start=1):
            setid(bullet, f"{base}.b{j}")
        for eng in entry["engagements"]:
            ebase = f"t-{eng['profile_id']}"
            setid(eng, ebase)
            for j, bullet in enumerate(eng["bullets"], start=1):
                setid(bullet, f"{ebase}.b{j}")
    for i, cert in enumerate(out["certifications"], start=1):
        setid(cert, f"t-cert-{i}")
    for i, edu in enumerate(out["education"], start=1):
        setid(edu, f"t-edu-{i}")
    for item in out["open_items"]:
        item["item_ids"] = [idmap.get(x, x) for x in item["item_ids"]]
    return out, idmap
