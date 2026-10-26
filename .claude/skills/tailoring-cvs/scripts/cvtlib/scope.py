"""Attestation scope resolution: turn "the SRE related cv items" into concrete profile IDs."""

from __future__ import annotations

import copy
import re
from typing import Any

from .errors import CvtError, ExitCode

SCOPE_GLOBAL = "global"
SCOPE_ROLE_LABEL = "role_label"
SCOPE_ITEMS = "items"
SCOPE_UNRESOLVED = "unresolved"
SCOPE_KINDS = (SCOPE_GLOBAL, SCOPE_ROLE_LABEL, SCOPE_ITEMS, SCOPE_UNRESOLVED)
DEFAULT_CANDIDATE_LIMIT = 4
LABEL_DASH = " — "
WORD_CHARS = "A-Za-z0-9"
MIN_TOKEN_LEN = 2
PLURAL_SUFFIX = "s"
MIN_STEM_LEN = 4
# Words of a scope description that carry no selection signal.
STOPWORDS = frozenset({
    "a", "an", "and", "any", "all", "at", "cv", "for", "in", "item", "items", "of", "on", "or", "related",
    "relevant", "role", "roles", "section", "the", "to", "where", "with", "work", "worked", "add", "my",
})


def _words(text: str) -> list[str]:
    return re.findall(rf"[{WORD_CHARS}]+", text.lower())


def _stem(word: str) -> str:
    if len(word) >= MIN_STEM_LEN and word.endswith(PLURAL_SUFFIX):
        return word[: -len(PLURAL_SUFFIX)]
    return word


def whole_word_match(needle: str, haystack: str) -> bool:
    """Case-insensitive match of `needle` on word boundaries ("SRE" matches "Role: SRE", not "PreSRE")."""
    needle = needle.strip()
    if not needle:
        return False
    pattern = rf"(?<![{WORD_CHARS}]){re.escape(needle)}(?![{WORD_CHARS}])"
    return re.search(pattern, haystack, re.IGNORECASE) is not None


def _label(item: dict) -> str:
    if item["is_work"]:
        return f"{item['name']}{LABEL_DASH}{item['role']}" if item["role"] else item["name"]
    base = f"{item['name']}{LABEL_DASH}{item['role']}" if item["role"] else item["name"]
    return f"{base} ({item['employer']})"


def _flatten(profile: dict) -> list[dict]:
    """Every work and engagement item in document order, with the fields scope matching needs."""
    items: list[dict] = []
    for work in profile.get("work", []):
        employer = work.get("name", "")
        items.append({
            "item_id": work["id"], "is_work": True, "name": employer, "role": work.get("position", ""),
            "employer": employer, "kind": "work",
            "text": " ".join([work.get("summary", ""), *(h.get("text", "") for h in work.get("highlights", []))]),
        })
        for eng in work.get("engagements", []):
            items.append({
                "item_id": eng["id"], "is_work": False, "name": eng.get("name", ""),
                "role": eng.get("role_label", ""), "employer": employer, "kind": eng.get("kind", ""),
                "text": " ".join([eng.get("summary", ""), *(h.get("text", "") for h in eng.get("highlights", []))]),
            })
    for item in items:
        item["label"] = _label(item)
    return items


def all_items(profile: dict) -> list[dict]:
    """Every engagement or work item as `{item_id, label}` in document order (scope-question skeletons)."""
    return [{"item_id": i["item_id"], "label": i["label"]} for i in _flatten(profile)]


def _unknown_ids(ids: list[str], known: set[str]) -> list[str]:
    return [i for i in ids if i not in known]


def resolve(scope: dict, profile: dict) -> dict:
    """Return a new scope with `item_ids` filled (document order) for role_label/items; validates IDs."""
    out = copy.deepcopy(scope)
    kind = out.get("kind")
    flat = _flatten(profile)
    order = {i["item_id"]: n for n, i in enumerate(flat)}
    if kind in (SCOPE_GLOBAL, SCOPE_UNRESOLVED):
        out["item_ids"], out["role_label"] = [], ""
    elif kind == SCOPE_ROLE_LABEL:
        label = str(out.get("role_label", "")).strip()
        if not label:
            raise CvtError(
                ExitCode.CHECK_FAILED, "E_SCOPE_EMPTY_LABEL", "scope kind role_label has an empty role_label",
                hint="set scope.role_label (for example 'SRE') or use kind 'unresolved'",
            )
        out["role_label"] = label
        out["item_ids"] = [i["item_id"] for i in flat if whole_word_match(label, i["role"])]
    elif kind == SCOPE_ITEMS:
        ids = list(dict.fromkeys(out.get("item_ids", [])))
        unknown = _unknown_ids(ids, set(order))
        if unknown:
            raise CvtError(
                ExitCode.CHECK_FAILED, "E_SCOPE_UNKNOWN_ID",
                f"scope names item ids not in the profile: {', '.join(unknown)}",
                hint="use ids from the profile (exp-N or exp-N.eK); list them with: cvt profile-show RUN",
            )
        out["item_ids"] = sorted(ids, key=lambda i: order[i])
        out["role_label"] = ""
    else:
        raise CvtError(
            ExitCode.CHECK_FAILED, "E_SCOPE_KIND", f"unknown scope kind '{kind}'",
            hint=f"scope.kind must be one of: {', '.join(SCOPE_KINDS)}",
        )
    return out


def describe_mapping(scope: dict, profile: dict) -> list[dict]:
    """`[{item_id, label}]` for the scope's item_ids, in document order. Resolves the scope first."""
    resolved = resolve(scope, profile)
    wanted = set(resolved["item_ids"])
    return [{"item_id": i["item_id"], "label": i["label"]} for i in _flatten(profile) if i["item_id"] in wanted]


def _tokens(description: str) -> list[str]:
    seen: list[str] = []
    for word in _words(description):
        if word in STOPWORDS or len(word) < MIN_TOKEN_LEN:
            continue
        stem = _stem(word)
        if stem not in seen:
            seen.append(stem)
    return seen


def _hits(tokens: list[str], text: str) -> int:
    stems = {_stem(w) for w in _words(text)}
    return sum(1 for t in tokens if t in stems)


def candidates(description: Any, profile: dict | None = None, limit: int = DEFAULT_CANDIDATE_LIMIT) -> list[dict]:
    """Rank items for an unresolved scope's words: role-label match, then name match, then keyword overlap.

    `candidates(profile)` (a dict as the only argument) lists every item with its label.
    """
    if isinstance(description, dict) and profile is None:
        return all_items(description)
    if profile is None:
        raise TypeError("candidates(description, profile) needs a profile")
    tokens = _tokens(str(description))
    scored: list[tuple[tuple[int, int, int], int, dict]] = []
    for n, item in enumerate(_flatten(profile)):
        score = (
            _hits(tokens, item["role"]),
            _hits(tokens, item["name"]),
            _hits(tokens, f"{item['text']} {item['employer']}"),
        )
        if any(score):
            scored.append((score, n, item))
    scored.sort(key=lambda s: (tuple(-v for v in s[0]), s[1]))
    return [{"item_id": i["item_id"], "label": i["label"]} for _, _, i in scored[: max(limit, 0)]]
