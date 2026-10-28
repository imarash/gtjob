"""Pure, ordered application of checkpoint-2 edit ops to tailored.json (interfaces.md sections 5 and 7).

`apply_ops` never mutates its input and never touches the disk. Any bad op raises `CvtError(CHECK_FAILED)` naming the
op, so the caller rejects the whole batch. Provenance is NOT checked here; the caller runs `provenance.check_tailored`
on the result.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Callable

from . import profile as profile_lib
from . import provenance, render
from .errors import CvtError, ExitCode

ERR_TARGET = "E_EDIT_TARGET"
ERR_OP = "E_EDIT_OP"
ERR_VALUE = "E_EDIT_VALUE"
ERR_REFS = "E_EDIT_REFS"

HEADER_ID = provenance.HEADER_ID
SUMMARY_ID = "t-sum"
EARLIER_ID = "t-earlier"
REVIEW_PENDING, REVIEW_APPROVED, REVIEW_AUTO = "pending", "approved", "auto"
SETTLED_REVIEWS = (REVIEW_APPROVED, REVIEW_AUTO)
ORIGIN_KEPT, ORIGIN_REWRITTEN, ORIGIN_MERGED, ORIGIN_ATTESTED = "kept", "rewritten", "merged", "attested"
RESTORED_PRIORITY = 3
PRIORITY_VALUES = (1, 2, 3, 4, 5)
TEMPLATES = render.TEMPLATES
PAGE_TARGETS = (1, 2)
PAPERS = ("us-letter", "a4")
BOOL_TRUE, BOOL_FALSE = "true", "false"
FIELDS = ("headline", "summary", "template", "include_earlier_experience", "emphasis", "page_target", "paper")
NON_RENDERED = ("omitted", "talking_points")  # sections whose refs do not put an item on the page
REASON_DROPPED = "Dropped at checkpoint 2."
REASON_REJECTED = "Rejected at checkpoint 2."

ATT_REF_RE = re.compile(r"^att-\d{3,}$")
HIGHLIGHT_RE = re.compile(r"^exp-\d+(\.e\d+)?\.b\d+$")
ENGAGEMENT_RE = re.compile(r"^exp-\d+\.e\d+$")
ENTRY_RE = re.compile(r"^exp-\d+$")
BULLET_NUMBER_RE = re.compile(r"\.b(\d+)$")
SKILL_ID_RE = re.compile(r"^t-skl-\d+$")

KIND_HEADER, KIND_SUMMARY, KIND_SKILL, KIND_ENTRY = "header", "summary", "skill", "entry"
KIND_ENGAGEMENT, KIND_BULLET, KIND_CERT, KIND_EARLIER = "engagement", "bullet", "cert", "earlier"
REVIEWABLE = (KIND_SUMMARY, KIND_SKILL, KIND_ENTRY, KIND_ENGAGEMENT, KIND_BULLET, KIND_EARLIER)
PRIORITIZED = (KIND_SKILL, KIND_ENTRY, KIND_ENGAGEMENT, KIND_BULLET, KIND_CERT)


def _err(err_id: str, message: str, hint: str = "") -> CvtError:
    return CvtError(ExitCode.CHECK_FAILED, err_id, message, hint=hint)


# --- locating items -------------------------------------------------------------------------------------
def locate(t: dict, target: str) -> tuple[str, Any, list | None]:
    """(kind, object, container list or None) for a tailored ID. Unknown ID -> E_EDIT_TARGET."""
    if target == HEADER_ID:
        return KIND_HEADER, t["header"], None
    if target == SUMMARY_ID:
        return KIND_SUMMARY, t["summary"], None
    if target == EARLIER_ID:
        return KIND_EARLIER, t["earlier_experience"], None
    for group in t["skills"]:
        if group["id"] == target:
            return KIND_SKILL, group, t["skills"]
    for cert in t["certifications"]:
        if cert["id"] == target:
            return KIND_CERT, cert, t["certifications"]
    for entry in t["experience"]:
        if entry["id"] == target:
            return KIND_ENTRY, entry, t["experience"]
        for b in entry["bullets"]:
            if b["id"] == target:
                return KIND_BULLET, b, entry["bullets"]
        for eng in entry["engagements"]:
            if eng["id"] == target:
                return KIND_ENGAGEMENT, eng, entry["engagements"]
            for b in eng["bullets"]:
                if b["id"] == target:
                    return KIND_BULLET, b, eng["bullets"]
    raise _err(ERR_TARGET, f"no item '{target}' in tailored.json",
               hint="use the t-... IDs printed by `cvt diff RUN` (the [N] number is not an ID)")


def _bullet_lists(t: dict) -> list[list[dict]]:
    out: list[list[dict]] = []
    for entry in t["experience"]:
        out.append(entry["bullets"])
        out.extend(eng["bullets"] for eng in entry["engagements"])
    return out


def all_refs(node: Any) -> set[str]:
    """Every string in any `source_refs` list below `node`."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "source_refs" and isinstance(value, list):
                found.update(v for v in value if isinstance(v, str))
            else:
                found |= all_refs(value)
    elif isinstance(node, list):
        for value in node:
            found |= all_refs(value)
    return found


def attestation_refs(t: dict) -> list[str]:
    """Sorted `att-NNN` IDs cited anywhere in `t`."""
    return sorted(r for r in all_refs(t) if ATT_REF_RE.match(r))


def bullet_refs(bullet: dict) -> list[str]:
    """The bullet-level profile refs (`exp-N[.eM].bK`) of a tailored bullet."""
    return [r for r in bullet["source_refs"] if HIGHLIGHT_RE.match(r)]


# --- review state ---------------------------------------------------------------------------------------
def _children(kind: str, obj: dict) -> list[dict]:
    if kind == KIND_ENTRY:
        return [*obj["bullets"], *obj["engagements"]]
    if kind == KIND_ENGAGEMENT:
        return list(obj["bullets"])
    return []


def _set_review(kind: str, obj: dict, value: str, cascade: bool) -> None:
    obj["review"] = value
    if cascade:
        for child in _children(kind, obj):
            child_kind = KIND_ENGAGEMENT if "bullets" in child else KIND_BULLET
            _set_review(child_kind, child, value, cascade=True)


def settle_containers(t: dict) -> None:
    """Entries and engagements with bullets follow their bullets: pending -> approved once none is pending."""
    for entry in t["experience"]:
        for eng in entry["engagements"]:
            if eng["bullets"] and eng["review"] == REVIEW_PENDING and not _any_pending(eng["bullets"]):
                eng["review"] = REVIEW_APPROVED
        if entry["bullets"] or entry["engagements"]:
            kids = [*entry["bullets"], *entry["engagements"]]
            if entry["review"] == REVIEW_PENDING and not _any_pending(kids):
                entry["review"] = REVIEW_APPROVED


def _any_pending(items: list[dict]) -> bool:
    return any(i["review"] == REVIEW_PENDING for i in items)


def pending_ids(t: dict) -> list[str]:
    """IDs of items still `review: pending`, in document order. Containers with bullets are not listed."""
    out: list[str] = []
    if t["summary"]["review"] == REVIEW_PENDING:
        out.append(SUMMARY_ID)
    out += [g["id"] for g in t["skills"] if g["review"] == REVIEW_PENDING]
    for entry in t["experience"]:
        if not entry["bullets"] and not entry["engagements"] and entry["review"] == REVIEW_PENDING:
            out.append(entry["id"])
        out += [b["id"] for b in entry["bullets"] if b["review"] == REVIEW_PENDING]
        for eng in entry["engagements"]:
            if not eng["bullets"] and eng["review"] == REVIEW_PENDING:
                out.append(eng["id"])
            out += [b["id"] for b in eng["bullets"] if b["review"] == REVIEW_PENDING]
    if t["earlier_experience"]["review"] == REVIEW_PENDING and t["earlier_experience"]["include"]:
        out.append(EARLIER_ID)
    return out


def _all_reviewable(t: dict) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = [(KIND_SUMMARY, t["summary"]), (KIND_EARLIER, t["earlier_experience"])]
    out += [(KIND_SKILL, g) for g in t["skills"]]
    for entry in t["experience"]:
        out.append((KIND_ENTRY, entry))
        out += [(KIND_BULLET, b) for b in entry["bullets"]]
        for eng in entry["engagements"]:
            out.append((KIND_ENGAGEMENT, eng))
            out += [(KIND_BULLET, b) for b in eng["bullets"]]
    return out


def mark_pending(t: dict, review: str) -> int:
    """Set every `pending` review to `review` (in place). Returns how many items changed."""
    changed = 0
    for _kind, obj in _all_reviewable(t):
        if obj["review"] == REVIEW_PENDING:
            obj["review"] = review
            changed += 1
    return changed


# --- omitted bookkeeping --------------------------------------------------------------------------------
def _record_omitted(t: dict, profile_ids: list[str], reason: str) -> None:
    cited = all_refs({k: v for k, v in t.items() if k not in NON_RENDERED})
    have = {o["profile_id"] for o in t["omitted"]}
    for pid in profile_ids:
        if pid and pid not in have and pid not in cited:
            t["omitted"].append({"profile_id": pid, "reason": reason})
            have.add(pid)


def _forget_omitted(t: dict, profile_id: str) -> None:
    t["omitted"] = [
        o for o in t["omitted"] if o["profile_id"] != profile_id and not o["profile_id"].startswith(profile_id + ".")
    ]


def _dropped_profile_ids(kind: str, obj: dict) -> list[str]:
    if kind == KIND_BULLET:
        return bullet_refs(obj)
    if kind in (KIND_ENTRY, KIND_ENGAGEMENT):
        return [obj["profile_id"]]
    if kind == KIND_CERT:
        return [obj["profile_id"]]
    return []


# --- op handlers ----------------------------------------------------------------------------------------
def _targets(op: dict) -> list[str]:
    found = [x for x in [op["target_id"], *op["items"]] if x]
    if not found:
        raise _err(ERR_TARGET, f"op '{op['op']}' needs target_id", hint="set target_id to a t-... ID")
    return found


def _op_approve_all(t: dict, op: dict, profile: dict) -> None:
    mark_pending(t, REVIEW_APPROVED)


def _op_approve(t: dict, op: dict, profile: dict) -> None:
    for target in _targets(op):
        kind, obj, _ = locate(t, target)
        if kind not in REVIEWABLE:
            raise _err(ERR_TARGET, f"'{target}' has no review state", hint="approve a bullet, skills group, summary or role")
        _set_review(kind, obj, REVIEW_APPROVED, cascade=kind in (KIND_ENTRY, KIND_ENGAGEMENT))


def _remove(container: list, obj: dict) -> None:
    container[:] = [x for x in container if x is not obj]


def _drop_item(t: dict, target: str, reason: str) -> None:
    kind, obj, container = locate(t, target)
    if kind == KIND_EARLIER:
        t["earlier_experience"]["include"] = False
        return
    if container is None:
        raise _err(ERR_TARGET, f"'{target}' cannot be removed", hint="replace its text with replace_text or set_field instead")
    ids = _dropped_profile_ids(kind, obj)
    _remove(container, obj)
    _record_omitted(t, ids, reason)


def _restore_text(t: dict, kind: str, obj: dict, profile: dict, target: str) -> bool:
    """Put the original profile text back where exactly one source exists. Returns False when it cannot."""
    if kind == KIND_BULLET:
        refs = bullet_refs(obj)
        if len(refs) != 1:
            return False
        others = {r for b_list in _bullet_lists(t) for b in b_list if b is not obj for r in b["source_refs"]}
        if refs[0] in others:
            return False  # the original is already on the page through another bullet
        obj.update({"text": profile_lib.item_text(profile, refs[0]), "source_refs": [refs[0]],
                    "origin": ORIGIN_KEPT, "review": REVIEW_PENDING})
        return True
    if kind == KIND_SUMMARY:
        refs = [r for r in obj["source_refs"] if r.startswith("sum-")]
        if len(refs) != 1:
            raise _err(ERR_TARGET, "the summary has no single profile source to restore",
                       hint="use replace_text on t-sum with source_refs, or set_field summary")
        obj.update({"text": profile_lib.item_text(profile, refs[0]), "source_refs": [refs[0]], "review": REVIEW_PENDING})
        return True
    if kind == KIND_HEADER:
        label = profile["basics"]["label"]
        if not label:
            raise _err(ERR_TARGET, "the profile has no headline to restore", hint="use set_field headline")
        obj["headline"] = label
        obj["source_refs"] = ["basics"]
        return True
    return False


def _op_reject(t: dict, op: dict, profile: dict) -> None:
    for target in _targets(op):
        kind, obj, _ = locate(t, target)
        if kind in (KIND_SUMMARY, KIND_HEADER):
            _restore_text(t, kind, obj, profile, target)
        elif kind == KIND_BULLET and obj["origin"] != ORIGIN_KEPT and _restore_text(t, kind, obj, profile, target):
            continue
        else:
            _drop_item(t, target, REASON_REJECTED)


def _op_drop(t: dict, op: dict, profile: dict) -> None:
    for target in _targets(op):
        if target in (SUMMARY_ID, HEADER_ID):
            raise _err(ERR_TARGET, f"'{target}' cannot be dropped", hint="use replace_text or set_field to change it")
        _drop_item(t, target, REASON_DROPPED)


def _origin_for(refs: list[str]) -> str:
    if any(ATT_REF_RE.match(r) for r in refs):
        return ORIGIN_ATTESTED
    return ORIGIN_MERGED if len([r for r in refs if r != "basics"]) > 1 else ORIGIN_REWRITTEN


def _require_refs(op: dict) -> list[str]:
    if not op["source_refs"]:
        raise _err(ERR_REFS, f"op '{op['op']}' on '{op['target_id']}' needs source_refs",
                   hint="cite the profile IDs or att-NNN the new text is based on")
    return list(op["source_refs"])


def _op_replace_text(t: dict, op: dict, profile: dict) -> None:
    kind, obj, _ = locate(t, op["target_id"])
    value = op["value"].strip()
    if not value:
        raise _err(ERR_VALUE, "replace_text needs a non-empty value", hint="use drop to remove an item")
    refs = _require_refs(op)
    if kind == KIND_BULLET:
        obj.update({"text": value, "source_refs": refs, "origin": _origin_for(refs), "review": REVIEW_PENDING})
    elif kind == KIND_SUMMARY:
        obj.update({"text": value, "source_refs": refs, "review": REVIEW_PENDING})
    elif kind == KIND_HEADER:
        obj.update({"headline": value, "source_refs": refs})
    elif kind == KIND_ENTRY:
        obj["intro"] = {"text": value, "source_refs": refs}
    else:
        raise _err(ERR_TARGET, f"replace_text cannot change '{op['target_id']}'",
                   hint="target a bullet (t-exp-N.bM), t-sum, t-header, or a role (intro line)")


def _highlight_order(profile: dict, parent_pid: str) -> list[str]:
    for w in profile["work"]:
        if w["id"] == parent_pid:
            return [h["id"] for h in w["highlights"]]
        for e in w["engagements"]:
            if e["id"] == parent_pid:
                return [h["id"] for h in e["highlights"]]
    return []


def _insert_index(items: list[dict], new_pos: int, position_of: Callable[[dict], int | None]) -> int:
    for i, item in enumerate(items):
        pos = position_of(item)
        if pos is not None and pos > new_pos:
            return i
    return len(items)


def _next_bullet_id(parent_tid: str, bullets: list[dict]) -> str:
    top = 0
    for b in bullets:
        m = BULLET_NUMBER_RE.search(b["id"])
        top = max(top, int(m.group(1)) if m else 0)
    return f"{parent_tid}.b{top + 1}"


def _kept_bullet(bullet_id: str, hid: str, text: str) -> dict:
    return {"id": bullet_id, "text": text, "source_refs": [hid], "priority": RESTORED_PRIORITY,
            "origin": ORIGIN_KEPT, "review": REVIEW_PENDING}


def _work(profile: dict, pid: str) -> dict:
    for w in profile["work"]:
        if w["id"] == pid:
            return w
    raise _err(ERR_TARGET, f"profile has no experience item '{pid}'", hint="list IDs with: cvt profile-show RUN")


def _engagement_entry(w: dict, e: dict) -> dict:
    tid = f"t-{e['id']}"
    bullets = [_kept_bullet(f"{tid}.b{i}", h["id"], h["text"]) for i, h in enumerate(e["highlights"], start=1)]
    return {"id": tid, "profile_id": e["id"], "kind": e["kind"], "name": e["name"], "role_label": e["role_label"],
            "bullets": bullets, "priority": RESTORED_PRIORITY, "review": REVIEW_PENDING}


def _work_entry(w: dict) -> dict:
    tid = f"t-{w['id']}"
    bullets = [_kept_bullet(f"{tid}.b{i}", h["id"], h["text"]) for i, h in enumerate(w["highlights"], start=1)]
    return {
        "id": tid, "profile_id": w["id"], "employer": w["name"], "location": w["location"], "title": w["position"],
        "start_date": w["start_date"], "end_date": w["end_date"], "intro": {"text": "", "source_refs": []},
        "bullets": bullets, "engagements": [_engagement_entry(w, e) for e in w["engagements"]],
        "priority": RESTORED_PRIORITY, "review": REVIEW_PENDING,
    }


def _restore_bullet(t: dict, profile: dict, hid: str) -> None:
    parent_pid = hid.rsplit(".", 1)[0]
    try:
        kind, parent, _ = locate(t, f"t-{parent_pid}")
    except CvtError:
        raise _err(ERR_TARGET, f"cannot restore {hid}: its role or engagement t-{parent_pid} is not in the CV",
                   hint=f"restore the role first: set target_id to {parent_pid}") from None
    if hid in all_refs(parent):
        raise _err(ERR_TARGET, f"{hid} is already in the CV", hint="nothing to restore")
    text = profile_lib.item_text(profile, hid)
    order = _highlight_order(profile, parent_pid)
    new_pos = order.index(hid) if hid in order else len(order)

    def position_of(b: dict) -> int | None:
        refs = bullet_refs(b)
        return min((order.index(r) for r in refs if r in order), default=None)

    bullets = parent["bullets"]
    bullet = _kept_bullet(_next_bullet_id(parent["id"], bullets), hid, text)
    bullets.insert(_insert_index(bullets, new_pos, position_of), bullet)


def _restore_engagement(t: dict, profile: dict, eid: str) -> None:
    pid = eid.split(".")[0]
    kind, entry, _ = locate(t, f"t-{pid}")  # raises E_EDIT_TARGET when the role itself is absent
    if any(e["profile_id"] == eid for e in entry["engagements"]):
        raise _err(ERR_TARGET, f"{eid} is already in the CV", hint="nothing to restore")
    w = _work(profile, pid)
    src = next((e for e in w["engagements"] if e["id"] == eid), None)
    if src is None:
        raise _err(ERR_TARGET, f"profile has no engagement '{eid}'", hint="list IDs with: cvt profile-show RUN")
    order = [e["id"] for e in w["engagements"]]
    new = _engagement_entry(w, src)
    pos = lambda e: order.index(e["profile_id"]) if e["profile_id"] in order else None  # noqa: E731
    entry["engagements"].insert(_insert_index(entry["engagements"], order.index(eid), pos), new)


def _restore_entry(t: dict, profile: dict, pid: str) -> None:
    if any(e["profile_id"] == pid for e in t["experience"]):
        raise _err(ERR_TARGET, f"{pid} is already in the CV", hint="nothing to restore")
    w = _work(profile, pid)
    order = [x["id"] for x in profile["work"]]
    pos = lambda e: order.index(e["profile_id"]) if e["profile_id"] in order else None  # noqa: E731
    t["experience"].insert(_insert_index(t["experience"], order.index(pid), pos), _work_entry(w))


def _op_restore(t: dict, op: dict, profile: dict) -> None:
    for target in _targets(op):
        if HIGHLIGHT_RE.match(target):
            _restore_bullet(t, profile, target)
        elif ENGAGEMENT_RE.match(target):
            _restore_engagement(t, profile, target)
        elif ENTRY_RE.match(target):
            _restore_entry(t, profile, target)
        else:
            raise _err(ERR_TARGET, f"cannot restore '{target}'",
                       hint="give a profile experience ID: exp-N (role), exp-N.eM (engagement) or exp-N[.eM].bK (bullet)")
        _forget_omitted(t, target)


def _op_move_before(t: dict, op: dict, profile: dict) -> None:
    kind, obj, container = locate(t, op["target_id"])
    kind2, other, container2 = locate(t, op["value"])
    if container is None or container is not container2 or obj is other:
        raise _err(ERR_TARGET, f"cannot move '{op['target_id']}' before '{op['value']}'",
                   hint="both IDs must be different siblings (same role or engagement, or both skills groups or roles)")
    container[:] = [x for x in container if x is not obj]
    container.insert(next(i for i, x in enumerate(container) if x is other), obj)


def _parse_bool(value: str) -> bool:
    low = value.strip().casefold()
    if low not in (BOOL_TRUE, BOOL_FALSE):
        raise _err(ERR_VALUE, f"expected '{BOOL_TRUE}' or '{BOOL_FALSE}', got '{value}'")
    return low == BOOL_TRUE


def _parse_choice(value: str, choices: tuple, what: str) -> Any:
    for choice in choices:
        if str(choice) == value.strip():
            return choice
    raise _err(ERR_VALUE, f"{what} must be one of {', '.join(map(str, choices))}, got '{value}'")


def _op_set_field(t: dict, op: dict, profile: dict) -> None:
    field, value = op["field"], op["value"]
    if field not in FIELDS:
        raise _err(ERR_OP, f"set_field needs field to be one of {', '.join(FIELDS)}, got '{field}'")
    if field == "headline":
        if not value.strip():
            raise _err(ERR_VALUE, "headline cannot be empty")
        t["header"]["headline"] = value.strip()
        t["header"]["source_refs"] = sorted({*t["header"]["source_refs"], *op["source_refs"]})
    elif field == "summary":
        if not value.strip():
            raise _err(ERR_VALUE, "summary cannot be empty")
        t["summary"].update({"text": value.strip(), "review": REVIEW_PENDING})
        if op["source_refs"]:
            t["summary"]["source_refs"] = list(op["source_refs"])
    elif field == "template":
        t["target"]["template"] = _parse_choice(value, TEMPLATES, "template")
    elif field == "include_earlier_experience":
        t["earlier_experience"]["include"] = _parse_bool(value)
    elif field == "emphasis":
        t["target"]["emphasis"] = value.strip()
    elif field == "page_target":
        t["target"]["page_target"] = _parse_choice(value, PAGE_TARGETS, "page_target")
    else:
        _parse_choice(value, PAPERS, "paper")  # stored in state.options by the command, not in tailored.json


def _skill_group(t: dict, target: str) -> dict:
    kind, obj, _ = locate(t, target)
    if kind != KIND_SKILL:
        raise _err(ERR_TARGET, f"'{target}' is not a skills group", hint="use a t-skl-N ID")
    return obj


def _op_add_skill(t: dict, op: dict, profile: dict) -> None:
    group = _skill_group(t, op["target_id"])
    name = op["value"].strip()
    if not name:
        raise _err(ERR_VALUE, "add_skill needs the skill name in value")
    refs = _require_refs(op)
    if any(i["name"].casefold() == name.casefold() for i in group["items"]):
        return
    group["items"].append({"name": name, "source_refs": refs})
    group["review"] = REVIEW_PENDING


def _op_remove_skill(t: dict, op: dict, profile: dict) -> None:
    group = _skill_group(t, op["target_id"])
    name = op["value"].strip().casefold()
    kept = [i for i in group["items"] if i["name"].casefold() != name]
    if len(kept) == len(group["items"]):
        raise _err(ERR_TARGET, f"'{op['value']}' is not in {op['target_id']}",
                   hint="skills: " + ", ".join(i["name"] for i in group["items"]))
    group["items"] = kept
    if not kept:
        t["skills"][:] = [g for g in t["skills"] if g is not group]


def _op_set_priority(t: dict, op: dict, profile: dict) -> None:
    value = _parse_choice(op["value"], tuple(str(p) for p in PRIORITY_VALUES), "priority")
    for target in _targets(op):
        kind, obj, _ = locate(t, target)
        if kind not in PRIORITIZED:
            raise _err(ERR_TARGET, f"'{target}' has no priority", hint="use a bullet, skills group, role, engagement or certification")
        obj["priority"] = int(value)


_HANDLERS: dict[str, Callable[[dict, dict, dict], None]] = {
    "approve_all": _op_approve_all, "approve": _op_approve, "reject": _op_reject, "replace_text": _op_replace_text,
    "drop": _op_drop, "restore": _op_restore, "move_before": _op_move_before, "set_field": _op_set_field,
    "add_skill": _op_add_skill, "remove_skill": _op_remove_skill, "set_priority": _op_set_priority,
}
OP_NAMES = tuple(_HANDLERS)


def apply_ops(tailored: dict, ops: list[dict], profile: dict) -> dict:
    """A new tailored dict with every op applied in order. Raises CvtError(CHECK_FAILED) on the first bad op."""
    t = copy.deepcopy(tailored)
    for number, raw in enumerate(ops, start=1):
        op = {"target_id": "", "field": "", "value": "", "source_refs": [], "items": [], **raw}
        handler = _HANDLERS.get(op["op"])
        label = f"op {number} ({op['op']} {op['target_id']})".replace(" )", ")")
        if handler is None:
            raise CvtError(ExitCode.CHECK_FAILED, ERR_OP, f"{label}: unknown op '{op['op']}'",
                           hint=f"valid ops: {', '.join(OP_NAMES)}",
                           violations=[{"code": ERR_OP, "item_id": op["target_id"], "message": f"unknown op '{op['op']}'"}])
        try:
            handler(t, op, profile)
        except CvtError as err:
            raise CvtError(
                err.code, err.err_id, f"{label}: {err.message}", hint=err.hint,
                violations=[{"code": err.err_id, "item_id": op["target_id"], "message": err.message}],
            ) from None
    settle_containers(t)
    return t
