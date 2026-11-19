"""Expand a compact `tailor-plan.json` into a full `tailored.json` (interfaces.md sections 1, 5 and 8).

Scripts copy every fact (header, employers, titles, dates, kept bullets, certifications, education) from the merged
profile, so the AI only picks IDs, priorities and rewrites. Plan mistakes are reported as `plan_ref` violations;
`provenance.check_tailored` then runs on the result and all violations come back together.
"""

from __future__ import annotations

import re

from . import attestations as att_store
from . import lexicon, provenance
from . import profile as prof

SCHEMA_VERSION = "1"
INITIAL_VERSION = 1
PLAN_REF = "plan_ref"
SKILL_UNSUPPORTED = "skill_unsupported"
REVIEW_PENDING, REVIEW_AUTO = "pending", "auto"
OP_KEEP, OP_REWRITE, OP_MERGE, OP_ATTESTED = "keep", "rewrite", "merge", "attested"
ORIGIN_BY_OP = {OP_KEEP: "kept", OP_REWRITE: "rewritten", OP_MERGE: "merged", OP_ATTESTED: "attested"}
MIN_MERGE_SOURCES = 2
INTRO_NONE, INTRO_KEEP, INTRO_REWRITE = "none", "keep", "rewrite"
BASICS_REF = "basics"
ATT_PREFIX = "att-"
MAX_SKILL_HIGHLIGHT_REFS = 3
MAX_FALLBACK_REFS = 2
# A headline longer than a tagline that also opens the summary is a pasted paragraph, not a second title.
HEADLINE_PARAGRAPH_CHARS = 120
_HEADLINE_SEGMENT = re.compile(r"\s*·\s*")
SKILL_SPLIT = re.compile(r"\s*[,;]\s*")
REF_RE = re.compile(
    r"^(?:basics|exp-[0-9]+(?:\.e[0-9]+)?(?:\.b[0-9]+)?|sum-[0-9]+|skl-[0-9]+|cert-[0-9]+|edu-[0-9]+|oth-[0-9]+|att-[0-9]{3,})$"
)
REF_LIST_KEYS = ("source_refs", "extra_refs", "from")
FALLBACK_LABEL = "Selected"
SKILL_PLACEMENTS = ("skills", "skills_and_bullets")
BULLET_PLACEMENTS = ("bullets", "skills_and_bullets")
CORRECTION_TYPE = "correction"
LOCATION_FIELD = "location"
SCOPE_GLOBAL = "global"
STATUSES_FOR_MERGE = (att_store.STATUS_ACTIVE, att_store.STATUS_PROPOSED)
NETWORK_LABELS = {"github": "GitHub", "linkedin": "LinkedIn", "website": "Website", "gitlab": "GitLab"}
WEBSITE_LABEL = "Website"
OTHER_LINK_LABEL = "Link"
DEGREE_SEPARATOR = ", "
LOCATION_SEPARATOR = ", "
HEADER_ITEM = "t-header"
KEPT_CERT_PRIORITY = 1  # a certificate the plan omitted is still kept; page-fit cannot drop priority 1


def _violation(item_id: str, message: str, code: str = PLAN_REF) -> dict:
    return {"code": code, "item_id": item_id, "message": message}


def _dedupe(refs: list[str]) -> list[str]:
    return list(dict.fromkeys(refs))


def _location(basics: dict, usable: list[dict]) -> str:
    for att in usable:
        c = att["correction"]
        if att["type"] == CORRECTION_TYPE and c["field"] == LOCATION_FIELD and c["item_id"] in ("", BASICS_REF):
            return c["new_value"]
    loc = basics["location"]
    return LOCATION_SEPARATOR.join(p for p in (loc["city"], loc["region"], loc["country"]) if p)


def _links(basics: dict) -> list[dict]:
    links: list[dict] = []
    seen: set[str] = set()
    if basics["url"]:
        links.append({"label": WEBSITE_LABEL, "url": basics["url"]})
        seen.add(basics["url"])
    for p in basics["profiles"]:
        if p["url"] and p["url"] not in seen:
            label = NETWORK_LABELS.get(p["network"].casefold(), p["network"].title() or OTHER_LINK_LABEL)
            links.append({"label": label, "url": p["url"]})
            seen.add(p["url"])
    return links


class _Index:
    """Lookups over the merged profile used by every section."""

    def __init__(self, merged: dict, usable: list[dict]) -> None:
        self.merged = merged
        self.usable = {a["id"]: a for a in usable}
        self.usable_list = usable
        self.works = {w["id"]: w for w in merged["work"]}
        self.engagements = {e["id"]: (e, w) for w in merged["work"] for e in w["engagements"]}
        self.highlights = {h["id"]: h for _i, kind, h in prof.iter_items(merged) if kind == prof.KIND_HIGHLIGHT}
        self.certs = {c["id"]: c for c in merged["certificates"]}
        self.edus = {e["id"]: e for e in merged["education"]}
        self.item_ids = {iid for iid, _k, _o in prof.iter_items(merged)}


def _skill_refs(name: str, ix: _Index) -> list[str]:
    groups = [g["id"] for g in ix.merged["skills"] if lexicon.supports(name, ", ".join(g["keywords"]))]
    if groups:
        return groups
    texts = [(hid, h["text"]) for hid, h in ix.highlights.items() if lexicon.supports(name, h["text"])]
    if texts:
        return [hid for hid, _t in texts[:MAX_SKILL_HIGHLIGHT_REFS]]
    return [a["id"] for a in ix.usable_list
            if a["placement"] in SKILL_PLACEMENTS and lexicon.supports(name, " ".join(a["terms"]))]


def legalize_refs(plan: dict) -> list[str]:
    """Drop source ids the tailor-plan schema cannot store, such as a match field cited as a ref."""
    dropped: list[str] = []

    def scrub(refs: list) -> list:
        kept = []
        for ref in refs:
            if isinstance(ref, str) and REF_RE.match(ref):
                kept.append(ref)
            else:
                dropped.append(str(ref))
        return kept

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key in REF_LIST_KEYS:
                if isinstance(node.get(key), list):
                    node[key] = scrub(node[key])
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(plan)
    return dropped


def _skill_pool(ix: _Index) -> str:
    parts = [prof.item_text(ix.merged, iid) for iid, _kind, _obj in prof.iter_items(ix.merged)]
    parts += [" ".join([a.get("claim", ""), a.get("detail", ""), *a.get("terms", [])]) for a in ix.usable_list]
    return "\n".join(parts)


def _skill_atoms(name: str, pool: str) -> list[str]:
    """One profile-backed skill per comma-separated entry. A phrase the profile does not contain is reduced to
    the terms inside it that the profile does contain."""
    chunks = [c.strip(" .") for c in SKILL_SPLIT.split(name) if c.strip(" .")]
    atoms: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        candidates = [chunk] if lexicon.supports(chunk, pool) else [
            term for term in lexicon.find_terms(chunk)
            if len(term) >= 3 and lexicon.supports(term, pool)
        ]
        for atom in candidates:
            key = atom.casefold()
            if key not in seen:
                seen.add(key)
                atoms.append(atom)
    return atoms


def _atom_refs(name: str, ix: _Index, texts: dict[str, str]) -> list[str]:
    refs = _skill_refs(name, ix)
    if refs:
        return refs
    return [iid for iid, text in texts.items() if text and lexicon.supports(name, text)][:MAX_SKILL_HIGHLIGHT_REFS]


def _skills(plan: dict, ix: _Index, review: str, out_violations: list[dict]) -> list[dict]:
    pool = _skill_pool(ix)
    texts = {iid: prof.item_text(ix.merged, iid) for iid, _kind, _obj in prof.iter_items(ix.merged)}
    groups = []
    for group in plan["skills"]:
        items = []
        for item in group["items"]:
            atoms = _skill_atoms(item["name"], pool)
            if not atoms:
                gid = f"t-skl-{len(groups) + 1}"
                out_violations.append(_violation(
                    gid, f"skill '{item['name']}' in {gid} is not supported by any profile skill, highlight or "
                         f"usable attestation; remove it or ask the user", SKILL_UNSUPPORTED))
                continue
            for atom in atoms:
                refs = _atom_refs(atom, ix, texts)
                if refs:
                    items.append({"name": atom, "source_refs": refs})
        if not items:
            continue
        groups.append({"id": f"t-skl-{len(groups) + 1}", "label": group["label"], "items": items,
                       "priority": group["priority"], "review": review})
    return groups


def _allowed_from(ref: str, parents: tuple[str, ...]) -> bool:
    return ref.startswith("exp-") and provenance.allowed_job_ref(ref, parents)


def _att_in_scope(att: dict, parents: tuple[str, ...]) -> bool:
    scope = att["scope"]
    return scope["kind"] == SCOPE_GLOBAL or bool(set(parents) & set(scope["item_ids"]))


def _bullet(b: dict, tid: str, parents: tuple[str, ...], ix: _Index, review: str, bad: list[dict]) -> dict | None:
    op, sources = b["op"], b["from"]
    problems: list[str] = []
    for ref in sources:
        is_bullet = ref in ix.highlights
        known = ref in ix.item_ids
        if not known:
            problems.append(f"from '{ref}' is not in the profile")
        elif not _allowed_from(ref, parents):
            problems.append(f"from '{ref}' is not an item of {parents[0]}")
        elif op != OP_ATTESTED and not is_bullet:
            problems.append(f"from '{ref}' is not a bullet (highlight) of {parents[0]}")
    if op == OP_KEEP:
        if b["text"]:
            problems.append("keep bullet must have empty text; use rewrite to change the wording")
        if len(sources) != 1:
            problems.append("keep bullet needs exactly one from")
    elif op == OP_REWRITE:
        if len(sources) != 1:
            problems.append("rewrite bullet needs exactly one from; use merge for several")
        if not b["text"].strip():
            problems.append("rewrite bullet has empty text")
    elif op == OP_MERGE:
        if len(sources) < MIN_MERGE_SOURCES:
            problems.append(f"merge bullet needs at least {MIN_MERGE_SOURCES} from items")
        if not b["text"].strip():
            problems.append("merge bullet has empty text")
    elif op == OP_ATTESTED:
        problems.extend(_attested_problems(b, parents, ix))
    for message in problems:
        bad.append(_violation(tid, f"bullet {tid}: {message}"))
    if problems:
        return None
    text = prof.item_text(ix.merged, sources[0]) if op == OP_KEEP else b["text"]
    return {"id": tid, "text": text, "source_refs": _dedupe([*sources, *b["extra_refs"]]),
            "priority": b["priority"], "origin": ORIGIN_BY_OP[op], "review": review}


def _attested_problems(b: dict, parents: tuple[str, ...], ix: _Index) -> list[str]:
    if not b["text"].strip():
        return ["attested bullet has empty text"]
    refs = [r for r in b["extra_refs"] if r.startswith(ATT_PREFIX)]
    if not refs:
        return ["attested bullet needs at least one att-* id in extra_refs"]
    in_scope = [r for r in refs if r in ix.usable and ix.usable[r]["placement"] in BULLET_PLACEMENTS
                and _att_in_scope(ix.usable[r], parents)]
    if not in_scope:
        return [f"attested bullet has no active attestation in scope of {parents[0]} among [{', '.join(refs)}]"]
    return []


def _bullets(items: list[dict], base: str, parents: tuple[str, ...], ix: _Index, review: str, bad: list[dict]) -> list[dict]:
    out: list[dict] = []
    for n, b in enumerate(items, start=1):
        made = _bullet(b, f"{base}.b{n}", parents, ix, review, bad)
        if made is not None:
            out.append(made)
    return out


def _intro(plan_intro: dict, work: dict, tid: str, bad: list[dict]) -> dict:
    mode = plan_intro["mode"]
    if mode == INTRO_KEEP:
        if not work["summary"]:
            return {"text": "", "source_refs": []}
        return {"text": work["summary"], "source_refs": [work["id"]]}
    if mode == INTRO_REWRITE:
        if not plan_intro["text"].strip():
            bad.append(_violation(tid, f"intro of {tid} is 'rewrite' but has no text"))
        return {"text": plan_intro["text"], "source_refs": list(plan_intro["source_refs"])}
    return {"text": "", "source_refs": []}


def _entry(pe: dict, ix: _Index, review: str, bad: list[dict]) -> dict | None:
    work = ix.works.get(pe["profile_id"])
    if work is None:
        bad.append(_violation(pe["profile_id"], f"experience {pe['profile_id']} is not in the profile"))
        return None
    tid = f"t-{work['id']}"
    engagements = []
    for pg in pe["engagements"]:
        found = ix.engagements.get(pg["profile_id"])
        if found is None or found[1]["id"] != work["id"]:
            bad.append(_violation(pg["profile_id"], f"engagement {pg['profile_id']} is not under {work['id']}"))
            continue
        eng = found[0]
        etid = f"t-{eng['id']}"
        engagements.append({
            "id": etid, "profile_id": eng["id"], "kind": eng["kind"], "name": eng["name"],
            "role_label": eng["role_label"],
            "bullets": _bullets(pg["bullets"], etid, (eng["id"], work["id"]), ix, review, bad),
            "priority": pg["priority"], "review": review,
        })
    return {
        "id": tid, "profile_id": work["id"], "employer": work["name"], "location": work["location"],
        "title": work["position"], "start_date": work["start_date"], "end_date": work["end_date"],
        "intro": _intro(pe["intro"], work, tid, bad),
        "bullets": _bullets(pe["bullets"], tid, (work["id"],), ix, review, bad),
        "engagements": engagements, "priority": pe["priority"], "review": review,
    }


def _earlier(plan: dict, ix: _Index, review: str, bad: list[dict]) -> dict:
    plan_e = plan["earlier_experience"]
    items: list[dict] = []
    for pid in plan_e["profile_ids"] if plan_e["include"] else []:
        work = ix.works.get(pid)
        if work is None:
            bad.append(_violation(pid, f"earlier experience {pid} is not in the profile"))
            continue
        items.append({"profile_id": pid, "employer": work["name"], "title": work["position"],
                      "start_date": work["start_date"], "end_date": work["end_date"]})
    return {"include": bool(plan_e["include"]), "items": items, "review": review}


def _cert_item(cert: dict, priority: int, name: str | None = None) -> dict:
    item = {
        "id": "", "profile_id": cert["id"], "name": name if name is not None else cert["name"],
        "priority": priority,
    }
    url = (cert.get("url") or "").strip()
    if url:
        item["url"] = url
    return item


def _certifications(plan: dict, ix: _Index, certificates: list[dict], bad: list[dict]) -> list[dict]:
    out: list[dict] = []
    for pc in plan["certifications"]:
        cert = ix.certs.get(pc["profile_id"])
        if cert is None:
            bad.append(_violation(pc["profile_id"], f"certification {pc['profile_id']} is not in the profile"))
            continue
        short = pc["short_name"]
        name = short if short and prof.comparable(short) in prof.comparable(cert["name"]) else cert["name"]
        out.append(_cert_item(cert, pc["priority"], name))
    seen = {item["profile_id"] for item in out}
    for cert in certificates:
        if cert["id"] not in seen:
            out.append(_cert_item(cert, KEPT_CERT_PRIORITY))
    for index, item in enumerate(out, 1):
        item["id"] = f"t-cert-{index}"
    return out


def _education(plan: dict, ix: _Index, bad: list[dict]) -> list[dict]:
    out: list[dict] = []
    for pe in plan["education"]:
        edu = ix.edus.get(pe["profile_id"])
        if edu is None:
            bad.append(_violation(pe["profile_id"], f"education {pe['profile_id']} is not in the profile"))
            continue
        degree = DEGREE_SEPARATOR.join(p for p in (edu["study_type"], edu["area"]) if p)
        out.append({
            "id": f"t-edu-{len(out) + 1}", "profile_id": edu["id"], "degree": degree or edu["text"],
            "institution": edu["institution"], "location": edu["location"], "end_date": edu["end_date"],
            "details": edu["text"] if pe["include_details"] else "",
        })
    return out


def _profile_texts(merged: dict) -> dict[str, str]:
    return {iid: prof.item_text(merged, iid) for iid, _kind, _obj in prof.iter_items(merged)}


def _fallback_text(refs: list[str], texts: dict[str, str]) -> tuple[str, list[str]]:
    """Profile lines the element already cites, summaries first, capped so a fallback stays a paragraph."""
    backed = [ref for ref in refs if texts.get(ref, "").strip()]
    chosen = [ref for ref in backed if ref.startswith("sum-")] or backed
    chosen = chosen[:MAX_FALLBACK_REFS]
    return " ".join(texts[ref] for ref in chosen), chosen


def _patch_text(node: dict, texts: dict[str, str]) -> bool:
    text, refs = _fallback_text(list(node.get("source_refs", [])), texts)
    if not text:
        return False
    node["text"] = text
    node["source_refs"] = refs
    return True


def _flat(text: str) -> str:
    return " ".join((text or "").split())


def headline_repeats_summary(headline: str, summary: str) -> bool:
    """True when the headline is the summary paragraph, or a long prefix of it.

    A short tagline may share its opening words with the summary. A paragraph pasted into the
    headline prints twice: once under the name and again under Summary.
    """
    head, body = _flat(headline), _flat(summary)
    if not head or not body:
        return False
    if head == body:
        return True
    shorter, longer = (head, body) if len(head) <= len(body) else (body, head)
    return len(shorter) >= HEADLINE_PARAGRAPH_CHARS and longer.startswith(shorter)


def _cited_source(refs: list[str], texts: dict[str, str]) -> tuple[str, list[str]]:
    kept = [ref for ref in refs if texts.get(ref, "").strip()]
    return "\n".join(texts[ref] for ref in kept), kept


def _headline_backed(text: str, source: str) -> bool:
    if not text.strip():
        return False
    if any(not lexicon.supports(term, source) for term in lexicon.find_terms(text)):
        return False
    known = set(lexicon.numbers(source))
    if any(number not in known for number in lexicon.numbers(text)):
        return False
    element = provenance._Element(provenance.KIND_HEADLINE, provenance.HEADER_ID, text, ())
    return not provenance._check_seniority(element, text, source)


def _ground_headline(header: dict, texts: dict[str, str]) -> None:
    """Keep the backed ` · ` segments. Never replace the headline with the summary paragraphs it cites."""
    source, refs = _cited_source(list(header.get("source_refs", [])), texts)
    parts = [part.strip() for part in _HEADLINE_SEGMENT.split(header.get("headline", "")) if part.strip()]
    kept = [part for part in parts if _headline_backed(part, source)]
    headline = " · ".join(kept)
    if headline and _headline_backed(headline, source):
        header["headline"] = headline
        header["source_refs"] = _dedupe([BASICS_REF, *refs])
        return
    header["headline"] = ""
    header["source_refs"] = [BASICS_REF]


def _clear_repeated_headline(header: dict, summary_text: str) -> None:
    if headline_repeats_summary(header.get("headline", ""), summary_text):
        header["headline"] = ""
        header["source_refs"] = [BASICS_REF]


def _ground_claims(tailored: dict, texts: dict[str, str], violations: list[dict]) -> None:
    """Replace prose the profile does not support with the lines it cites, except the headline.

    Skill lines are already reduced to backed terms. A summary, talking point, intro, or bullet
    that names something its sources do not is replaced with those source lines. An invented bullet
    therefore ships as the profile line it cites. The headline stays a short tagline: a ` · `
    segment the cited lines do not support is dropped, and the headline is never replaced with
    summary paragraphs (that prints the same paragraph under the name and again under Summary).
    """
    prose = {v["item_id"] for v in violations if v["code"] in {
        provenance.UNSUPPORTED_TERM, provenance.UNSUPPORTED_NUMBER, provenance.PLACEMENT, provenance.UNKNOWN_REF,
        provenance.OUT_OF_SCOPE,
    }}
    labels = {v["item_id"] for v in violations if v["code"] == SKILL_UNSUPPORTED and "skill group" in v["message"]}
    header = tailored["header"]
    summary = tailored["summary"]
    if prose or labels:
        if provenance.HEADER_ID in prose:
            _ground_headline(header, texts)
        if summary["id"] in prose:
            _patch_text(summary, texts)
    kept_points = []
    for index, point in enumerate(tailored["talking_points"]):
        if provenance.TALKING_ID.format(i=index) not in prose or _patch_text(point, texts):
            kept_points.append(point)
    tailored["talking_points"] = kept_points
    for entry in tailored["experience"]:
        if entry["id"] in prose:
            _patch_text(entry["intro"], texts)
        for bullet in entry["bullets"]:
            if bullet["id"] in prose:
                _patch_text(bullet, texts)
        for engagement in entry["engagements"]:
            for bullet in engagement["bullets"]:
                if bullet["id"] in prose:
                    _patch_text(bullet, texts)
    for group in tailored["skills"]:
        if group["id"] in labels:
            group["label"] = FALLBACK_LABEL
    _clear_repeated_headline(header, summary.get("text", ""))


def _profile_sha(state: dict) -> str:
    for entry in state.get("artifacts", []):
        if entry.get("name") == "profile":
            return entry.get("sha256", "")
    return ""


def assemble(plan: dict, profile: dict, attestations: list[dict], jd: dict, state: dict) -> tuple[dict, list[dict]]:
    """Return (tailored, violations). `attestations` is the person's whole store list."""
    run_slug = state["run_slug"]
    usable = att_store.usable({"attestations": attestations}, run_id=run_slug, include_proposed=True)
    merged = prof.merged_view(profile, usable, statuses=STATUSES_FOR_MERGE)
    ix = _Index(merged, usable)
    options = state["options"]
    review = REVIEW_AUTO if options.get("auto") else REVIEW_PENDING
    bad: list[dict] = []
    basics = merged["basics"]
    experience = [e for pe in plan["experience"] if (e := _entry(pe, ix, review, bad)) is not None]
    certs = _certifications(plan, ix, merged["certificates"], bad)
    kept_certs = {c["profile_id"] for c in certs}
    tailored = {
        "schema_version": SCHEMA_VERSION, "run_id": run_slug, "person_slug": profile["person_slug"],
        "profile_sha256": _profile_sha(state), "jd_sha256": jd["jd_sha256"], "version": INITIAL_VERSION,
        "target": {"title": jd["title"], "company": jd["company"], "page_target": options["page_target"],
                   "template": options["template"], "emphasis": plan["emphasis"]},
        "header": {
            "name": basics["name"], "headline": plan["headline"]["text"], "location": _location(basics, usable),
            "email": basics["email"], "phone": basics["phone"], "links": _links(basics),
            "source_refs": _dedupe([BASICS_REF, *plan["headline"]["source_refs"]]),
        },
        "summary": {"id": "t-sum", "text": plan["summary"]["text"],
                    "source_refs": list(plan["summary"]["source_refs"]), "review": review},
        "skills": _skills(plan, ix, review, bad),
        "experience": experience,
        "earlier_experience": _earlier(plan, ix, review, bad),
        "certifications": certs,
        "education": _education(plan, ix, bad),
        "talking_points": [{"text": t["text"], "source_refs": list(t["source_refs"])} for t in plan["talking_points"]],
        "omitted": [dict(o) for o in plan["omitted"] if o["profile_id"] not in kept_certs],
        "open_items": [{"kind": o["kind"], "text": o["text"], "item_ids": list(o["item_ids"])}
                       for o in plan["open_items"]],
    }
    texts = _profile_texts(merged)
    found = provenance.check_tailored(tailored, profile, attestations, run_id=run_slug, draft=True)
    _ground_claims(tailored, texts, found)
    violations = bad + provenance.check_tailored(tailored, profile, attestations, run_id=run_slug, draft=True)
    violations.sort(key=lambda v: (v["item_id"], v["code"], v["message"]))
    return tailored, violations
