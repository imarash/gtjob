"""Expand a compact `tailor-plan.json` into a full `tailored.json` (interfaces.md sections 1, 5 and 8).

Scripts copy every fact (header, employers, titles, dates, kept bullets, certifications, education) from the merged
profile, so the AI only picks IDs, priorities and rewrites. Plan mistakes are reported as `plan_ref` violations;
`provenance.check_tailored` then runs on the result and all violations come back together.
"""

from __future__ import annotations

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


def _skills(plan: dict, ix: _Index, review: str, out_violations: list[dict]) -> list[dict]:
    groups = []
    for n, group in enumerate(plan["skills"], start=1):
        gid, items = f"t-skl-{n}", []
        for item in group["items"]:
            refs = list(item["source_refs"]) or _skill_refs(item["name"], ix)
            if not refs:
                out_violations.append(_violation(
                    gid, f"skill '{item['name']}' in {gid} is not supported by any profile skill, highlight or "
                         f"usable attestation; remove it or ask the user", SKILL_UNSUPPORTED))
                continue
            items.append({"name": item["name"], "source_refs": refs})
        groups.append({"id": gid, "label": group["label"], "items": items, "priority": group["priority"],
                       "review": review})
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
            bad.append(_violation(tid, f"intro of {tid} is 'keep' but profile {work['id']} has no summary"))
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


def _certifications(plan: dict, ix: _Index, bad: list[dict]) -> list[dict]:
    out: list[dict] = []
    for pc in plan["certifications"]:
        cert = ix.certs.get(pc["profile_id"])
        if cert is None:
            bad.append(_violation(pc["profile_id"], f"certification {pc['profile_id']} is not in the profile"))
            continue
        short = pc["short_name"]
        name = short if short and prof.comparable(short) in prof.comparable(cert["name"]) else cert["name"]
        item = {"id": f"t-cert-{len(out) + 1}", "profile_id": cert["id"], "name": name, "priority": pc["priority"]}
        url = (cert.get("url") or "").strip()
        if url:
            item["url"] = url
        out.append(item)
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
        "certifications": _certifications(plan, ix, bad),
        "education": _education(plan, ix, bad),
        "talking_points": [{"text": t["text"], "source_refs": list(t["source_refs"])} for t in plan["talking_points"]],
        "omitted": [dict(o) for o in plan["omitted"]],
        "open_items": [{"kind": o["kind"], "text": o["text"], "item_ids": list(o["item_ids"])}
                       for o in plan["open_items"]],
    }
    violations = bad + provenance.check_tailored(tailored, profile, attestations, run_id=run_slug, draft=True)
    violations.sort(key=lambda v: (v["item_id"], v["code"], v["message"]))
    return tailored, violations
