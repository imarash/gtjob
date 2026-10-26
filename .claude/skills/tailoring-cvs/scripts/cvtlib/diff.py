"""Checkpoint-2 diff: per-item before/after against the profile or the previous tailored version (interfaces.md 5, 7)."""

from __future__ import annotations

import math
import re
from typing import Any

from . import edits
from . import profile as profile_lib
from .errors import CvtError

ESTIMATED_LINES_PER_PAGE = 58
CHARS_PER_LINE = 105          # rendered characters per body line (page-count estimate only)
HEADER_LINES = 4              # name, headline, contact line, spacing
SECTION_HEADING_LINES = 1
ENTRY_HEADER_LINES = 2
ENGAGEMENT_HEADER_LINES = 1
EXCERPT_CHARS = 160
MAX_OUTLINE_LINES = 12
MAX_OUTLINE_ENTRY_LINES = 6  # 12 lines minus title, header, summary, experience heading, earlier, certifications
OUTLINE_FIELD_CHARS = 100
OUTLINE_ENGAGEMENT_CHARS = 90
ELLIPSIS = "…"

KIND_KEPT, KIND_REWRITTEN, KIND_MERGED, KIND_ATTESTED = "kept", "rewritten", "merged", "attested"
KIND_DROPPED, KIND_ADDED, KIND_CHANGED = "dropped", "added", "changed"
CHANGED_KINDS = (KIND_REWRITTEN, KIND_MERGED, KIND_ATTESTED, KIND_DROPPED, KIND_ADDED, KIND_CHANGED)
WAS_KINDS = (KIND_REWRITTEN, KIND_CHANGED)
SECTION_HEADER, SECTION_SUMMARY, SECTION_SKILLS = "header", "summary", "skills"
SECTION_EXPERIENCE, SECTION_EARLIER, SECTION_OMITTED = "experience", "earlier", "omitted"
AGAINST_PROFILE, AGAINST_PREVIOUS = "profile", "previous"
SKILL_REF_PREFIX, SUMMARY_REF_PREFIX = "skl-", "sum-"
REMOVED_TEXT = "(removed)"
NEWLINE = "\n"
WHITESPACE_RE = re.compile(r"\s+")


# --- text helpers ---------------------------------------------------------------------------------------
def _flat(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def excerpt(text: str, width: int = EXCERPT_CHARS) -> str:
    flat = _flat(text)
    return flat if len(flat) <= width else flat[: width - 1].rstrip() + ELLIPSIS


def _same(a: str, b: str) -> bool:
    return profile_lib.comparable(a) == profile_lib.comparable(b)


def _safe_text(profile: dict, ref: str) -> str:
    try:
        return profile_lib.item_text(profile, ref)
    except CvtError:
        return ""


def _join(parts: list[str]) -> str:
    return " ".join(p for p in parts if p)


def _is_att(ref: str) -> bool:
    return bool(edits.ATT_REF_RE.match(ref))


def _skills_text(group: dict) -> str:
    return f"{group['label']}: {', '.join(i['name'] for i in group['items'])}"


def _earlier_text(t: dict) -> str:
    e = t["earlier_experience"]
    return "; ".join(f"{i['employer']} - {i['title']} ({i['start_date']}-{i['end_date']})" for i in e["items"])


# --- flattening -----------------------------------------------------------------------------------------
def _flatten(t: dict) -> list[dict]:
    """The reviewable items of `t` in document order: {id, section, text, refs, review, origin}."""
    def row(iid: str, section: str, text: str, refs: list[str], review: str, origin: str = "") -> dict:
        return {"id": iid, "section": section, "text": text, "refs": list(refs), "review": review, "origin": origin}

    h = t["header"]
    out = [row(edits.HEADER_ID, SECTION_HEADER, h["headline"], h["source_refs"], "")]
    s = t["summary"]
    out.append(row(s["id"], SECTION_SUMMARY, s["text"], s["source_refs"], s["review"]))
    for g in t["skills"]:
        refs = [r for item in g["items"] for r in item["source_refs"]]
        out.append(row(g["id"], SECTION_SKILLS, _skills_text(g), list(dict.fromkeys(refs)), g["review"]))
    for entry in t["experience"]:
        if entry["intro"]["text"]:
            out.append(row(entry["id"], SECTION_EXPERIENCE, entry["intro"]["text"], entry["intro"]["source_refs"],
                           entry["review"]))
        bullets = [*entry["bullets"], *[b for eng in entry["engagements"] for b in eng["bullets"]]]
        for b in bullets:
            out.append(row(b["id"], SECTION_EXPERIENCE, b["text"], b["source_refs"], b["review"], b["origin"]))
    e = t["earlier_experience"]
    if e["include"] and e["items"]:
        out.append(row(edits.EARLIER_ID, SECTION_EARLIER, _earlier_text(t), [i["profile_id"] for i in e["items"]],
                       e["review"]))
    return out


def _item(row: dict, kind: str, before: str, after: str, note: str = "") -> dict:
    out = {
        "id": row["id"], "section": row["section"], "kind": kind, "before": before, "after": after,
        "source_refs": row["refs"], "review": row["review"], "origin": row["origin"],
    }
    if note:
        out["note"] = note
    return out


# --- against the profile --------------------------------------------------------------------------------
def _profile_before(row: dict, profile: dict) -> str:
    rid = row["id"]
    refs = [r for r in row["refs"] if not _is_att(r)]
    if rid == edits.HEADER_ID:
        return profile["basics"]["label"]
    if rid == edits.EARLIER_ID:
        return row["text"]
    if row["section"] == SECTION_SUMMARY:
        return _join([_safe_text(profile, r) for r in refs if r.startswith(SUMMARY_REF_PREFIX)])
    if row["section"] == SECTION_SKILLS:
        return _join([_safe_text(profile, r) for r in refs if r.startswith(SKILL_REF_PREFIX)])
    bullet_level = [r for r in refs if edits.HIGHLIGHT_RE.match(r)]
    return _join([_safe_text(profile, r) for r in (bullet_level or refs)])


def _profile_kind(row: dict, before: str) -> str:
    if _same(before, row["text"]):
        return KIND_KEPT
    refs = row["refs"]
    if row["origin"] and row["origin"] != KIND_KEPT:
        return row["origin"]
    if row["origin"] == KIND_KEPT:
        return KIND_REWRITTEN
    if any(_is_att(r) for r in refs):
        return KIND_ATTESTED
    if row["section"] == SECTION_SUMMARY and len([r for r in refs if r.startswith(SUMMARY_REF_PREFIX)]) > 1:
        return KIND_MERGED
    return KIND_REWRITTEN


def _dropped_from_omitted(t: dict, profile: dict) -> list[dict]:
    out = []
    for o in t["omitted"]:
        row = {"id": o["profile_id"], "section": SECTION_OMITTED, "refs": [o["profile_id"]], "review": "", "origin": ""}
        out.append(_item(row, KIND_DROPPED, _safe_text(profile, o["profile_id"]), "", note=o["reason"]))
    return out


def _against_profile(tailored: dict, profile: dict) -> list[dict]:
    items = []
    for row in _flatten(tailored):
        before = _profile_before(row, profile)
        items.append(_item(row, _profile_kind(row, before), before, row["text"]))
    return items + _dropped_from_omitted(tailored, profile)


# --- against the previous version -----------------------------------------------------------------------
def _against_previous(tailored: dict, previous: dict) -> list[dict]:
    old = {r["id"]: r for r in _flatten(previous)}
    items = []
    for row in _flatten(tailored):
        was = old.pop(row["id"], None)
        if was is None:
            items.append(_item(row, KIND_ADDED, "", row["text"]))
        elif _same(was["text"], row["text"]):
            items.append(_item(row, KIND_KEPT, was["text"], row["text"]))
        else:
            items.append(_item(row, KIND_CHANGED, was["text"], row["text"]))
    for gone in old.values():
        items.append(_item(gone, KIND_DROPPED, gone["text"], ""))
    return items


def diff_items(tailored: dict, profile: dict, previous: dict | None) -> list[dict]:
    """Items as {id, section, kind, before, after, source_refs, review, origin[, note]}.

    With `previous` None the comparison is against the profile (kept|rewritten|merged|attested, plus `dropped` for
    `omitted`); otherwise against that earlier tailored version by ID (kept|changed|added|dropped).
    """
    return _against_profile(tailored, profile) if previous is None else _against_previous(tailored, previous)


def counts(items: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item["kind"]] = out.get(item["kind"], 0) + 1
    return out


def changed_items(items: list[dict]) -> list[dict]:
    return [i for i in items if i["kind"] in CHANGED_KINDS]


# --- outline --------------------------------------------------------------------------------------------
def _wrap_lines(text: str, width: int = CHARS_PER_LINE) -> int:
    return max(1, math.ceil(len(text) / width))


def estimated_lines(t: dict) -> int:
    lines = HEADER_LINES + SECTION_HEADING_LINES * 2 + _wrap_lines(t["summary"]["text"])
    lines += sum(_wrap_lines(_skills_text(g)) for g in t["skills"])
    for entry in t["experience"]:
        lines += ENTRY_HEADER_LINES + (_wrap_lines(entry["intro"]["text"]) if entry["intro"]["text"] else 0)
        lines += sum(_wrap_lines(b["text"]) for b in entry["bullets"])
        for eng in entry["engagements"]:
            lines += ENGAGEMENT_HEADER_LINES + sum(_wrap_lines(b["text"]) for b in eng["bullets"])
    lines += SECTION_HEADING_LINES
    if t["earlier_experience"]["include"] and t["earlier_experience"]["items"]:
        lines += SECTION_HEADING_LINES + _wrap_lines(_earlier_text(t))
    lines += (SECTION_HEADING_LINES + len(t["certifications"])) if t["certifications"] else 0
    lines += (SECTION_HEADING_LINES + len(t["education"])) if t["education"] else 0
    return lines


def _entry_line(entry: dict) -> str:
    bullets = len(entry["bullets"]) + sum(len(e["bullets"]) for e in entry["engagements"])
    line = f"  {entry['id']} {entry['employer']}, {entry['title']}: {bullets} bullets"
    if entry["engagements"]:
        engs = ", ".join(f"{e['name']} ({len(e['bullets'])})" for e in entry["engagements"])
        line += f"; engagements: {excerpt(engs, OUTLINE_ENGAGEMENT_CHARS)}"
    return line


def outline(tailored: dict) -> str:
    """At most MAX_OUTLINE_LINES lines: sections with employers, engagements and bullet counts, plus a page estimate."""
    t = tailored
    pages = estimated_lines(t) / ESTIMATED_LINES_PER_PAGE
    lines = [f"Outline (estimate: ~{pages:.1f} pages at {ESTIMATED_LINES_PER_PAGE} lines/page; "
             f"target {t['target']['page_target']}; template {t['target']['template']})"]
    lines.append(f"Header: {excerpt(t['header']['name'], OUTLINE_FIELD_CHARS)} | "
                 f"{excerpt(t['header']['headline'], OUTLINE_FIELD_CHARS)}")
    skills = sum(len(g["items"]) for g in t["skills"])
    lines.append(f"Summary: {len(t['summary']['text'])} chars | Skills: {len(t['skills'])} groups, {skills} items")
    entries = t["experience"]
    lines.append(f"Experience: {len(entries)} roles")
    if len(entries) <= MAX_OUTLINE_ENTRY_LINES:
        lines += [_entry_line(e) for e in entries]
    else:
        listed = MAX_OUTLINE_ENTRY_LINES - 1
        lines += [_entry_line(e) for e in entries[:listed]]
        lines.append(f"  +{len(entries) - listed} more roles")
    e = t["earlier_experience"]
    lines.append("Earlier experience: " + (f"included ({len(e['items'])} roles)" if e["include"] else "not included"))
    lines.append(f"Certifications: {len(t['certifications'])} | Education: {len(t['education'])} | "
                 f"Omitted profile items: {len(t['omitted'])}")
    return NEWLINE.join(lines[:MAX_OUTLINE_LINES])


# --- markdown -------------------------------------------------------------------------------------------
def _label(item: dict) -> str:
    refs = ", ".join(item["source_refs"])
    return f"{item['kind']}; refs {refs}" if refs else item["kind"]


def _quote(prefix: str, text: str) -> str:
    return f"> {prefix}{_flat(text) or REMOVED_TEXT}"


def _full_block(number: int, item: dict) -> list[str]:
    head = f"[{number}] {item['id']} ({_label(item)})"
    if item["kind"] == KIND_ADDED:
        return [head, _quote("after: ", item["after"])]
    if item["kind"] == KIND_DROPPED:
        return [head, _quote("before: ", item["before"]), _quote("after: ", "")]
    if _same(item["before"], item["after"]):
        return [head, _quote("", item["after"])]
    return [head, _quote("before: ", item["before"]), _quote("after: ", item["after"])]


def _compact_line(number: int, item: dict) -> str:
    refs = ", ".join(item["source_refs"])
    head = f"[{number}] {item['id']} {item['kind']}" + (f" (refs: {refs})" if refs else "")
    if item["kind"] == KIND_DROPPED:
        return f"{head}: {excerpt(item['before'])}"
    line = f"{head}: {excerpt(item['after'])}"
    if item["kind"] in WAS_KINDS and item["before"]:
        line += f" | was: {excerpt(item['before'])}"
    return line


def _kept_summary(items: list[dict]) -> str:
    kept = [i for i in items if i["kind"] == KIND_KEPT]
    bullets = sum(1 for i in kept if i["section"] == SECTION_EXPERIENCE)
    other = len(kept) - bullets
    text = f"kept (not listed): {bullets} bullets"
    return text + (f", {other} other items" if other else "")


def render_diff_md(items: list[dict], outline: str, *, compact: bool = False) -> str:
    """Numbered markdown. Numbers are positions in the FULL list, so "reject 3" is stable in compact and full views.

    Full: every item with before/after blockquotes. Compact: only changed items, one line each, kept items counted.
    """
    lines = [outline, ""]
    if compact:
        lines.append(_kept_summary(items))
        lines += [_compact_line(n, i) for n, i in enumerate(items, start=1) if i["kind"] in CHANGED_KINDS]
        if not changed_items(items):
            lines.append("no changed items")
        return NEWLINE.join(lines)
    for n, item in enumerate(items, start=1):
        lines += _full_block(n, item)
        lines.append("")
    return NEWLINE.join(lines).rstrip() + NEWLINE


def numbered(items: list[dict], compact: bool = False) -> list[dict[str, Any]]:
    """Items with their stable `n` for JSON output; compact keeps changed items with excerpts only."""
    out = []
    for n, item in enumerate(items, start=1):
        if compact and item["kind"] not in CHANGED_KINDS:
            continue
        row = dict(item, n=n)
        if compact:
            row["after"] = excerpt(item["after"])
            row["before"] = excerpt(item["before"]) if item["kind"] in WAS_KINDS or item["kind"] == KIND_DROPPED else ""
        out.append(row)
    return out
