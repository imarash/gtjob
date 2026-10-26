"""Provenance validator: every claim in `tailored.json` must trace to CV text or an attestation.

Implements interfaces.md section 8 (rules 1-10, including 3a). Violations are `validation.schema.json#/$defs/violation` objects
whose messages name the item first, so `cvt brief fix` can select only the offending items by `item_id`.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Iterator
from dataclasses import dataclass

from . import attestations, lexicon
from . import profile as prof
from .profile import comparable

# --- violation codes (validation.schema.json) ---------------------------------------------------------------
MISSING_REFS = "missing_refs"
UNKNOWN_REF = "unknown_ref"
OUT_OF_SCOPE = "ref_out_of_scope"
PLACEMENT = "placement"
UNSUPPORTED_TERM = "unsupported_term"
UNSUPPORTED_NUMBER = "unsupported_number"
FACT_MISMATCH = "fact_mismatch"
CERT_UNSUPPORTED = "cert_unsupported"
SKILL_UNSUPPORTED = "skill_unsupported"
NOT_ACTIVE = "attestation_not_active"
PLACEHOLDER = "placeholder"
LOGISTICS_LEAK = "logistics_leak"
PROVENANCE_CODES = (
    MISSING_REFS, UNKNOWN_REF, OUT_OF_SCOPE, PLACEMENT, UNSUPPORTED_TERM, UNSUPPORTED_NUMBER, FACT_MISMATCH,
    CERT_UNSUPPORTED, SKILL_UNSUPPORTED,
)

# --- element kinds and ids ----------------------------------------------------------------------------------
KIND_BULLET, KIND_SUMMARY, KIND_HEADLINE = "bullet", "summary", "headline"
KIND_SKILL, KIND_INTRO, KIND_TALKING = "skill", "intro", "talking point"
HEADER_ID = "t-header"
TARGET_ID = "target"
TALKING_ID = "talking_points[{i}]"

# --- job scope (rule 3a) ------------------------------------------------------------------------------------
EXP_PREFIX = "exp-"
REF_SEP = "."
WORK_HIGHLIGHT_SUFFIX = r"\.b\d+"

# --- attestation vocabulary ---------------------------------------------------------------------------------
STATUS_ACTIVE, STATUS_PROPOSED, STATUS_REVOKED = "active", "proposed", "revoked"
SCOPE_GLOBAL, SCOPE_UNRESOLVED = "global", "unresolved"
TYPE_CORRECTION = "correction"
BULLET_PLACEMENTS = ("bullets", "skills_and_bullets")
SKILL_PLACEMENTS = ("skills", "skills_and_bullets")

# --- logistics (rule 9) -------------------------------------------------------------------------------------
LOGISTICS_NOISE_KINDS = ("compensation", "visa", "recruiter_contact", "recruiter_question")
SKIP_STRING_KEYS = frozenset({"schema_version", "run_id", "person_slug", "profile_sha256", "jd_sha256"})
CONTACT_PATHS = (("header", "email"), ("header", "phone"), ("header", "links"))
UNSCANNED_SECTIONS = ("open_items", "omitted")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_MONEY_RE = re.compile(r"[$€£]\s?\d[\d,]*(?:\.\d+)?\s?[kK]?")
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
MAX_QUOTE_CHARS = 60
PLACEHOLDER_RE = re.compile(r"\[\[\s*CONFIRM\s*:[^\]]*\]\]", re.IGNORECASE)


# --- profile and attestation helpers (delegated to cvtlib.profile / cvtlib.attestations) ---------------------
def _same(a: str, b: str) -> bool:
    return prof.normalize_text(a) == prof.normalize_text(b)


def _join(parts: list[str]) -> str:
    return " ".join(p for p in parts if p)


def _usable(atts: list[dict], run_id: str, include_proposed: bool) -> list[dict]:
    """Active attestations, plus this run's proposed ones when asked. Never revoked or unresolved-scope."""
    return attestations.usable({"attestations": atts}, run_id=run_id, include_proposed=include_proposed)


def _merged(profile: dict, atts: list[dict], statuses: tuple[str, ...] = (STATUS_ACTIVE,)) -> dict:
    """Deep copy of `profile` with every correction attestation in `statuses` applied to its target field."""
    return prof.merged_view(profile, atts, statuses=statuses)


def _item_texts(profile: dict) -> dict[str, str]:
    """Text of every addressable profile item. Work and engagements include descendants, names, labels, dates."""
    return {iid: prof.item_text(profile, iid) for iid, _kind, _obj in prof.iter_items(profile)}


def _att_text(att: dict) -> str:
    return _join([att["claim"], att["detail"], *att["terms"]])


def strip_placeholders(text: str) -> str:
    return PLACEHOLDER_RE.sub(" ", text)


# --- tailored elements --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class _Element:
    kind: str
    item_id: str
    text: str
    refs: tuple[str, ...]
    parents: tuple[str, ...] = ()  # profile work/engagement IDs a cited attestation's scope must cover (bullets, intros)
    label: str = ""                # skills group label (checked against the whole profile)


def _elements(t: dict) -> list[_Element]:
    out = [_Element(KIND_HEADLINE, HEADER_ID, t["header"]["headline"], tuple(t["header"]["source_refs"]))]
    s = t["summary"]
    out.append(_Element(KIND_SUMMARY, s["id"], s["text"], tuple(s["source_refs"])))
    for g in t["skills"]:
        for item in g["items"]:
            out.append(_Element(KIND_SKILL, g["id"], item["name"], tuple(item["source_refs"]), label=g["label"]))
    for entry in t["experience"]:
        intro = entry["intro"]
        out.append(_Element(KIND_INTRO, entry["id"], intro["text"], tuple(intro["source_refs"]),
                            (entry["profile_id"],)))
        for b in entry["bullets"]:
            out.append(_Element(KIND_BULLET, b["id"], b["text"], tuple(b["source_refs"]), (entry["profile_id"],)))
        for eng in entry["engagements"]:
            for b in eng["bullets"]:
                out.append(_Element(KIND_BULLET, b["id"], b["text"], tuple(b["source_refs"]),
                                    (eng["profile_id"], entry["profile_id"])))
    for i, tp in enumerate(t["talking_points"]):
        out.append(_Element(KIND_TALKING, TALKING_ID.format(i=i), tp["text"], tuple(tp["source_refs"])))
    return out


def _violation(code: str, item_id: str, message: str) -> dict:
    return {"code": code, "item_id": item_id, "message": message}


def _refs_label(refs: tuple[str, ...]) -> str:
    return "[" + ", ".join(refs) + "]"


# --- rules 1-5 ----------------------------------------------------------------------------------------------
def _ref_problem(ref: str, usable: dict[str, dict], all_atts: dict[str, dict], known: set[str]) -> str:
    """'' when `ref` resolves; otherwise why it does not."""
    if ref in known or ref in usable:
        return ""
    att = all_atts.get(ref)
    if att is None:
        return "does not exist in the profile or the attestation store"
    if att["status"] == STATUS_REVOKED:
        return "is revoked and cannot be used"
    if att["scope"]["kind"] == SCOPE_UNRESOLVED:
        return "has an unresolved scope; answer the scope question first"
    return f"is {att['status']} in run {att['run_id']!r} and cannot be used in this run"


def _check_att_use(el: _Element, att: dict) -> list[dict]:
    out: list[dict] = []
    allowed = SKILL_PLACEMENTS if el.kind == KIND_SKILL else BULLET_PLACEMENTS
    exempt = el.kind in (KIND_SUMMARY, KIND_HEADLINE, KIND_TALKING) and att["type"] == TYPE_CORRECTION
    if att["placement"] not in allowed and not exempt:
        out.append(_violation(PLACEMENT, el.item_id,
                              f"{el.kind} {el.item_id} cites {att['id']} whose placement is '{att['placement']}'; "
                              f"allowed here: {', '.join(allowed)}"))
    scope = att["scope"]
    if el.parents and scope["kind"] != SCOPE_GLOBAL and not set(el.parents) & set(scope["item_ids"]):
        out.append(_violation(OUT_OF_SCOPE, el.item_id,
                              f"{el.kind} {el.item_id} cites {att['id']} outside its scope "
                              f"[{', '.join(scope['item_ids'])}]; parent is {el.parents[0]}"))
    return out


def allowed_job_ref(ref: str, parents: tuple[str, ...]) -> bool:
    """Rule 3a: may a bullet or intro under `parents` (closest first: engagement then work, or work only) cite `ref`?

    Work `exp-N` allows `exp-N` and `exp-N.*`. Engagement `exp-N.eK` allows itself, `exp-N.eK.*` and work-level
    highlights `exp-N.bJ` (for example a tools line), but not the bare work or a sibling engagement.
    """
    work = parents[-1]
    if len(parents) == 1:
        return ref == work or ref.startswith(work + REF_SEP)
    engagement = parents[0]
    return (ref == engagement or ref.startswith(engagement + REF_SEP)
            or re.fullmatch(re.escape(work) + WORK_HIGHLIGHT_SUFFIX, ref) is not None)


def _check_job_scope(el: _Element, usable: dict[str, dict]) -> list[dict]:
    """Rule 3a: a bullet or intro cites `exp-*` refs only from its own job, and needs one own-job ref or attestation."""
    out: list[dict] = []
    parent = el.parents[0]
    for ref in el.refs:
        if ref.startswith(EXP_PREFIX) and not allowed_job_ref(ref, el.parents):
            out.append(_violation(OUT_OF_SCOPE, el.item_id,
                                  f"{el.kind} {el.item_id} cites {ref} from another job; parent is {parent}"))
    for ref in el.refs:
        att = usable.get(ref)
        if att is not None:
            scope = att["scope"]
            if scope["kind"] == SCOPE_GLOBAL or set(el.parents) & set(scope["item_ids"]):
                return out
        elif allowed_job_ref(ref, el.parents):
            return out
    out.append(_violation(OUT_OF_SCOPE, el.item_id,
                          f"{el.kind} {el.item_id} has no ref from its own job; parent is {parent}"))
    return out


def _check_element(
    el: _Element, texts: dict[str, str], usable: dict[str, dict], all_atts: dict[str, dict], whole_profile: str,
    att_pool: str,
) -> list[dict]:
    out: list[dict] = []
    text = strip_placeholders(el.text)
    if not el.refs:
        if el.kind == KIND_BULLET or text.strip():
            out.append(_violation(MISSING_REFS, el.item_id, f"{el.kind} {el.item_id} has no source_refs"))
        return out
    known = set(texts)
    sources: list[str] = []
    for ref in el.refs:
        problem = _ref_problem(ref, usable, all_atts, known)
        if problem:
            out.append(_violation(UNKNOWN_REF, el.item_id, f"{el.kind} {el.item_id} cites {ref}, which {problem}"))
        elif ref in usable:
            out.extend(_check_att_use(el, usable[ref]))
            sources.append(_att_text(usable[ref]))
        else:
            sources.append(texts[ref])
    if el.parents and (el.kind == KIND_BULLET or text.strip()):
        out.extend(_check_job_scope(el, usable))
    if not text.strip():
        return out
    source = "\n".join(sources)
    if el.kind == KIND_SKILL and not lexicon.supports(text.strip(), whole_profile + "\n" + att_pool):
        out.append(_violation(SKILL_UNSUPPORTED, el.item_id,
                              f"skill {el.item_id} lists '{text.strip()}'; not found in profile text or any "
                              f"usable attestation"))
        return out
    for term in lexicon.find_terms(text):
        if not lexicon.supports(term, source):
            out.append(_violation(UNSUPPORTED_TERM, el.item_id,
                                  f"{el.kind} {el.item_id} mentions '{term}'; not found in refs "
                                  f"{_refs_label(el.refs)}"))
    known_numbers = set(lexicon.numbers(source))
    for number in lexicon.numbers(text):
        if number not in known_numbers:
            out.append(_violation(UNSUPPORTED_NUMBER, el.item_id,
                                  f"{el.kind} {el.item_id} mentions number '{number}'; not found in refs "
                                  f"{_refs_label(el.refs)}"))
    return out


def _check_group_labels(t: dict, whole_profile: str, att_pool: str) -> list[dict]:
    out: list[dict] = []
    pool = whole_profile + "\n" + att_pool
    for g in t["skills"]:
        for term in lexicon.find_terms(g["label"]):
            if not lexicon.supports(term, pool):
                out.append(_violation(SKILL_UNSUPPORTED, g["id"],
                                      f"skill group {g['id']} label mentions '{term}'; not found in profile text "
                                      f"or any usable attestation"))
    return out


# --- rule 6: facts ------------------------------------------------------------------------------------------
def _location_forms(basics: dict, atts: list[dict]) -> set[str]:
    loc = basics["location"]
    city, region, country = loc["city"], loc["region"], loc["country"]
    forms = {"", city, ", ".join(p for p in (city, region) if p), ", ".join(p for p in (city, region, country) if p),
             ", ".join(p for p in (city, country) if p), ", ".join(p for p in (region, country) if p)}
    for att in atts:
        if att["type"] == TYPE_CORRECTION and att["correction"]["field"] == "location":
            forms.add(att["correction"]["new_value"])
    return {comparable(f) for f in forms}


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", comparable(text)))


DEGREE_FILLER = frozenset({"in", "of", "and", "with"})


def _degree_ok(degree: str, edu: dict) -> bool:
    allowed = _words(edu["study_type"]) | _words(edu["area"])
    if not allowed:
        allowed = _words(edu["text"])
    got = _words(degree)
    return got <= allowed | DEGREE_FILLER and _words(edu["study_type"]) <= got


def _mismatch(item_id: str, what: str, got: str, want: str) -> dict:
    return _violation(FACT_MISMATCH, item_id, f"{item_id} {what} '{got}' does not equal profile value '{want}'")


def _check_header(t: dict, merged: dict, usable: list[dict]) -> list[dict]:
    h, b = t["header"], merged["basics"]
    out: list[dict] = []
    if not _same(h["name"], b["name"]):
        out.append(_mismatch(HEADER_ID, "name", h["name"], b["name"]))
    for field in ("email", "phone"):
        if h[field] and not _same(h[field], b[field]):
            out.append(_mismatch(HEADER_ID, field, h[field], b[field]))
    if comparable(h["location"]) not in _location_forms(b, usable):
        out.append(_mismatch(HEADER_ID, "location", h["location"], _location_forms_text(b)))
    urls = {b["url"], *[p["url"] for p in b["profiles"]]} - {""}
    for link in h["links"]:
        if link["url"] not in urls:
            out.append(_violation(FACT_MISMATCH, HEADER_ID,
                                  f"{HEADER_ID} link '{link['url']}' is not a profile url"))
    return out


def _location_forms_text(basics: dict) -> str:
    loc = basics["location"]
    return ", ".join(p for p in (loc["city"], loc["region"], loc["country"]) if p)


def _check_entry(entry: dict, work: dict | None) -> list[dict]:
    iid = entry["id"]
    if work is None:
        return [_violation(UNKNOWN_REF, iid, f"entry {iid} has profile_id '{entry['profile_id']}', "
                                              f"which is not in the profile")]
    out = []
    pairs = (("employer", work["name"]), ("title", work["position"]), ("start_date", work["start_date"]),
             ("end_date", work["end_date"]))
    for field, want in pairs:
        if not _same(entry[field], want):
            out.append(_mismatch(iid, field, entry[field], want))
    if entry["location"] and not _same(entry["location"], work["location"]):
        out.append(_mismatch(iid, "location", entry["location"], work["location"]))
    engagements = {e["id"]: e for e in work["engagements"]}
    for eng in entry["engagements"]:
        src = engagements.get(eng["profile_id"])
        if src is None:
            out.append(_violation(UNKNOWN_REF, eng["id"], f"engagement {eng['id']} has profile_id "
                                  f"'{eng['profile_id']}', which is not under {work['id']}"))
            continue
        for field, want in (("name", src["name"]), ("role_label", src["role_label"]), ("kind", src["kind"])):
            if not _same(eng[field], want):
                out.append(_mismatch(eng["id"], field, eng[field], want))
    return out


def _check_earlier(t: dict, works: dict[str, dict]) -> list[dict]:
    out: list[dict] = []
    for item in t["earlier_experience"]["items"]:
        work = works.get(item["profile_id"])
        iid = item["profile_id"]
        if work is None:
            out.append(_violation(UNKNOWN_REF, iid, f"earlier experience {iid} is not in the profile"))
            continue
        for field, want in (("employer", work["name"]), ("title", work["position"]),
                            ("start_date", work["start_date"]), ("end_date", work["end_date"])):
            if not _same(item[field], want):
                out.append(_mismatch(iid, field, item[field], want))
    return out


def _check_certs_and_education(t: dict, merged: dict) -> list[dict]:
    out: list[dict] = []
    certs = {c["id"]: c for c in merged["certificates"]}
    for c in t["certifications"]:
        src = certs.get(c["profile_id"])
        if src is None:
            out.append(_violation(CERT_UNSUPPORTED, c["id"],
                                  f"certification {c['id']} cites {c['profile_id']}, which is not in the profile"))
        elif comparable(c["name"]) not in comparable(src["name"]):
            out.append(_violation(CERT_UNSUPPORTED, c["id"],
                                  f"certification {c['id']} name '{c['name']}' is not part of profile name "
                                  f"'{src['name']}'"))
    edus = {e["id"]: e for e in merged["education"]}
    for e in t["education"]:
        src = edus.get(e["profile_id"])
        if src is None:
            out.append(_violation(UNKNOWN_REF, e["id"], f"education {e['id']} cites {e['profile_id']}, "
                                                        f"which is not in the profile"))
            continue
        for field, want in (("institution", src["institution"]), ("location", src["location"]),
                            ("end_date", src["end_date"])):
            if not _same(e[field], want):
                out.append(_mismatch(e["id"], field, e[field], want))
        if not _degree_ok(e["degree"], src):
            out.append(_mismatch(e["id"], "degree", e["degree"], _join([src["study_type"], src["area"]])))
        if e["details"] and comparable(e["details"]) not in comparable(src["text"]):
            out.append(_violation(FACT_MISMATCH, e["id"],
                                  f"education {e['id']} details '{e['details']}' are not in the profile entry"))
    return out


# --- public API ---------------------------------------------------------------------------------------------
def check_attestation_status(tailored: dict, attestations: list[dict], *, run_id: str) -> list[dict]:
    """Rule 10: every attestation cited by a usable element must be `active` (proposed ones are reported)."""
    usable = {a["id"]: a for a in _usable(attestations, run_id, include_proposed=True)}
    out: list[dict] = []
    for el in _elements(tailored):
        for ref in el.refs:
            att = usable.get(ref)
            if att is not None and att["status"] != STATUS_ACTIVE:
                out.append(_violation(NOT_ACTIVE, el.item_id,
                                      f"{el.kind} {el.item_id} cites {ref}, which is {att['status']}; "
                                      f"it becomes active at approval"))
    return sorted(out, key=lambda v: (v["item_id"], v["message"]))


def check_tailored(
    tailored: dict, profile: dict, attestations: list[dict], *, run_id: str, draft: bool,
) -> list[dict]:
    """Rules 1-7 (and rule 10 unless `draft`). `attestations` is the whole store; sorted by item_id."""
    usable_list = _usable(attestations, run_id, include_proposed=True)
    usable = {a["id"]: a for a in usable_list}
    all_atts = {a["id"]: a for a in attestations}
    merged = _merged(profile, usable_list, statuses=(STATUS_ACTIVE, STATUS_PROPOSED))
    texts = _item_texts(merged)
    whole_profile = "\n".join(texts.values())
    att_pool = "\n".join(_att_text(a) for a in usable_list if a["placement"] != "correction_only")
    out: list[dict] = []
    for el in _elements(tailored):
        out.extend(_check_element(el, texts, usable, all_atts, whole_profile, att_pool))
    out.extend(_check_group_labels(tailored, whole_profile, att_pool))
    works = {w["id"]: w for w in merged["work"]}
    out.extend(_check_header(tailored, merged, usable_list))
    for entry in tailored["experience"]:
        out.extend(_check_entry(entry, works.get(entry["profile_id"])))
    out.extend(_check_earlier(tailored, works))
    out.extend(_check_certs_and_education(tailored, merged))
    if not draft:
        out.extend(check_attestation_status(tailored, attestations, run_id=run_id))
    return sorted(out, key=lambda v: (v["item_id"], v["message"]))


def _skip_path(path: tuple, skip_contact: bool) -> bool:
    if path and path[0] in UNSCANNED_SECTIONS:
        return True
    return skip_contact and any(path[: len(p)] == p for p in CONTACT_PATHS)


def _walk_strings(node, item_id: str, path: tuple) -> Iterator[tuple[str, tuple, str]]:
    if isinstance(node, str):
        yield item_id, path, node
    elif isinstance(node, dict):
        current = node["id"] if isinstance(node.get("id"), str) and node["id"] else item_id
        for key, value in node.items():
            if key == "id" or key in SKIP_STRING_KEYS:
                continue
            yield from _walk_strings(value, current, (*path, key))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            child = TALKING_ID.format(i=i) if path and path[-1] == "talking_points" else item_id
            yield from _walk_strings(value, child, (*path, i))


def _tailored_strings(tailored: dict, *, skip_contact: bool) -> Iterator[tuple[str, tuple, str]]:
    """(item_id, path, text) for every string a reader could see, minus notes sections and (optionally) contact."""
    for key, value in tailored.items():
        if key in SKIP_STRING_KEYS:
            continue
        top_id = {"header": HEADER_ID, "target": TARGET_ID}.get(key, "")
        for item_id, path, text in _walk_strings(value, top_id, (key,)):
            if text and not _skip_path(path, skip_contact):
                yield item_id or key, path, text


def find_placeholders(tailored: dict) -> list[dict]:
    """Rule 8: `[[CONFIRM: ...]]` placeholders anywhere a reader could see them (the caller decides warn or fail)."""
    out = []
    for item_id, _path, text in _tailored_strings(tailored, skip_contact=False):
        for m in PLACEHOLDER_RE.finditer(text):
            out.append(_violation(PLACEHOLDER, item_id, f"{item_id} contains placeholder '{m.group(0)}'"))
    return sorted(out, key=lambda v: (v["item_id"], v["message"]))


@functools.cache
def _logistics_regexes() -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple((p["kind"], re.compile(p["regex"], re.IGNORECASE)) for p in lexicon.logistics_patterns())


def _noise_probes(text: str) -> list[str]:
    """Distinctive fragments of a noise text: the whole text, emails, money amounts and phone numbers."""
    probes = [text, *_EMAIL_RE.findall(text), *_MONEY_RE.findall(text), *_PHONE_RE.findall(text)]
    return [comparable(p) for p in probes if comparable(p)]


def check_logistics(tailored: dict, jd: dict) -> list[dict]:
    """Rule 9: no compensation/visa/recruiter text from the JD and no logistics pattern in the CV content."""
    probes: list[tuple[str, str]] = []
    for noise in jd["noise"]:
        if noise["kind"] in LOGISTICS_NOISE_KINDS:
            probes.extend((noise["kind"], p) for p in _noise_probes(noise["text"]))
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item_id, _path, text in _tailored_strings(tailored, skip_contact=True):
        norm = comparable(text)
        for kind, probe in probes:
            if probe in norm and (item_id, probe) not in seen:
                seen.add((item_id, probe))
                shown = probe if len(probe) <= MAX_QUOTE_CHARS else probe[:MAX_QUOTE_CHARS].rstrip() + "..."
                out.append(_violation(LOGISTICS_LEAK, item_id,
                                      f"{item_id} contains {kind} text from the JD: '{shown}'"))
        for kind, regex in _logistics_regexes():
            for m in regex.finditer(text):
                key = (item_id, m.group(0).casefold())
                if key not in seen:
                    seen.add(key)
                    out.append(_violation(LOGISTICS_LEAK, item_id,
                                          f"{item_id} contains {kind} text '{m.group(0).strip()}'"))
    return sorted(out, key=lambda v: (v["item_id"], v["message"]))
