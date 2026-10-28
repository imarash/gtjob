"""Checkpoint-1 answers: build rounds (select/auto), plan them (dry-run) and commit them (interfaces.md section 7).

The AI parses free text into one `answers.schema.json#/$defs/round`; this module validates it, resolves scopes,
proposes scope-confirmation skeletons, records the round, and creates `proposed` attestations. It never invents
attestation IDs or facts: every created attestation cites the user's own words (`verbatim`) from `raw_text`.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from . import attestations as attmod
from . import jsonio
from . import lexicon
from . import profile as profmod
from . import questions as qmod
from . import render as render_mod
from . import schemas, state
from . import scope as scopemod
from .errors import CvtError, ExitCode

ANSWERS_FILE, QUESTIONS_FILE = "answers.json", "questions.json"
ANSWERS_ARTIFACT, QUESTIONS_ARTIFACT = "answers", "questions"
STAGE_AWAITING, STAGE_APPLIED = "awaiting_answers", "answers_applied"
STATUS_AWAITING = "awaiting_user"
CP1_PENDING, CP1_DONE = "pending", "done"

CHANNEL_HOST_TOOL, CHANNEL_AUTO = "host_tool", "auto"
AUTO_RAW_TEXT = "(auto mode: every question takes its default)"
SKIP_WORD = "skip"
CHECKPOINT_1 = 1

ACTION_ATTEST, ACTION_REJECT, ACTION_CORRECT = "attest", "reject", "correct"
ACTION_CHOOSE, ACTION_CONFIRM, ACTION_INSTRUCT, ACTION_SKIP = "choose", "confirm_scope", "instruct", "skip"
NO_ATTESTATION_ACTIONS = (ACTION_REJECT, ACTION_CHOOSE, ACTION_CONFIRM, ACTION_INSTRUCT, ACTION_SKIP)
NEEDS_QUESTION_ACTIONS = (ACTION_CHOOSE, ACTION_CONFIRM)

TYPE_CORRECTION, PLACEMENT_CORRECTION = "correction", "correction_only"
TYPE_SKILL, PLACEMENT_SKILLS = "skill", "skills"
SCOPED_KINDS = (scopemod.SCOPE_ROLE_LABEL, scopemod.SCOPE_ITEMS)
SKILLS_ONLY_ID, SKILLS_ONLY_LABEL = "skills_only", "Skills section only"
SKILLS_ONLY_DESCRIPTION = "Skills section only; no role bullets are changed."
SCOPE_USE_ALL_DESCRIPTION = "Use all of the listed items."
GAP_CAVEAT = "Picked from a list with no role context; placed in the skills section only unless you name a role."
EMPTY_CORRECTION = {"item_id": "", "field": "", "old_value": "", "new_value": ""}
GLOBAL_SCOPE = {"kind": scopemod.SCOPE_GLOBAL, "role_label": "", "item_ids": [], "description": ""}
SKELETON_PROMPT = 'Use "{claims}" on these items? (you said: "{description}")'
SKELETON_PROMPT_NO_WORDS = 'Use "{claims}" on these items?'
UNRESOLVED_PROMPT = 'Which roles should "{claims}" go on? (you said: "{description}")'
UNRESOLVED_PROMPT_NO_WORDS = 'Which roles should "{claims}" go on?'
RAW_TEXT_SEP, RAW_ITEM_SEP = ", ", "; "
CHOICE_ID_RE = re.compile(r"[^a-z0-9]+")
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
PLAN_PROMPT_WIDTH = 60
CORRECTION_VALUE_WIDTH = 60
CORRECTION_TERMS_MESSAGE = "a correction carries no terms; put the new value in correction.new_value"
PENDING_MESSAGE = "{n} question(s) await an answer: {ids}"
UNRESOLVED_MESSAGE = "scope unresolved for {claims}; add the scope question (cvt questions RUN --add) and ask it"
AUTO_DETAIL = "auto round: {n} defaulted"

CODE_SCHEMA, CODE_UNKNOWN_REF = "schema", "unknown_ref"
CODE_PLACEMENT, CODE_NUMBER, CODE_VERBATIM = "placement", "unsupported_number", "fact_mismatch"
CODE_TERM = "unsupported_term"
CORRECTION_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#]*")
# Function words carry no claim, so a correction's new value need not quote them from the user.
CORRECTION_FUNCTION_WORDS = frozenset({"a", "an", "the", "of", "and", "or", "for", "to", "in", "at", "on", "with", "by", "as", "from"})
TERMS_LABEL = " terms="
CHOICE_VALUE_SEP = "|"
FAILED_ID = "E_ANSWERS_INVALID"


def _violation(code: str, item_id: str, message: str) -> dict:
    return {"code": code, "item_id": item_id, "message": message}


def _path(parts) -> str:
    out = "$"
    for part in parts:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


def _numbers(text: str) -> set[str]:
    return set(NUMBER_RE.findall(text))


def _grounding(raw_text: str, q: dict | None, choice_ids: list[str]) -> str:
    """What the user said or chose: raw_text plus the label and value of each chosen option on the question."""
    parts = [raw_text]
    if q is not None:
        chosen = set(choice_ids)
        for choice in qmod._options(q):
            if choice["id"] in chosen:
                parts.extend([choice["label"], choice["value"].replace(CHOICE_VALUE_SEP, " ")])
    return " ".join(parts)


def _term_violations(where: str, prop: dict, grounding: str) -> list[dict]:
    """Every licensed term, and every claim-bearing term in claim/detail, must be grounded in `grounding`."""
    common = lexicon.common_words()
    wanted = [t for t in prop["terms"] if t.strip()]
    wanted += [t for t in lexicon.find_terms(f"{prop['claim']} {prop['detail']}") if t.casefold() not in common]
    out: list[dict] = []
    seen: set[str] = set()
    for term in wanted:
        key = term.casefold()
        if key in seen:
            continue
        seen.add(key)
        if not lexicon.supports(term, grounding):
            out.append(_violation(CODE_TERM, where, f"term '{term}' in {where} is not something the user said or chose"))
    return out


def _correction_term_violations(where: str, new_value: str, grounding: str) -> list[dict]:
    """A correction's new value becomes a profile fact, so every word in it must be the user's (function words aside)."""
    out: list[dict] = []
    seen: set[str] = set()
    for word in CORRECTION_WORD_RE.findall(new_value):
        key = word.casefold()
        if key in CORRECTION_FUNCTION_WORDS or key in seen:
            continue
        seen.add(key)
        if not lexicon.supports(word, grounding):
            out.append(_violation(CODE_TERM, where, f"term '{word}' in {where} is not something the user said or chose"))
    return out


def _current_value(profile: dict, item_id: str, field_name: str) -> str:
    """The profile's present value of `item_id.field_name` ("" when the item or field is missing or None)."""
    obj = next((o for iid, _k, o in profmod.iter_items(profile) if iid == item_id), {})
    value = obj.get(field_name)
    return "" if value is None else str(value)


def _choice_key(text: str) -> str:
    return CHOICE_ID_RE.sub("_", text.lower()).strip("_")


# --- context -----------------------------------------------------------------------------------------------
@dataclass
class _Ctx:
    run_dir: Path
    st: dict
    questions: dict
    profile: dict  # raw profile with active corrections applied
    store: dict
    qs: dict[str, dict] = field(default_factory=dict)


def _context(run_dir: Path) -> _Ctx:
    run_dir = Path(run_dir)
    st = state.load(run_dir)
    path = run_dir / QUESTIONS_FILE
    if not path.is_file():
        raise CvtError(ExitCode.STATE, "E_ARTIFACT_MISSING", f"{QUESTIONS_FILE} not found in {run_dir.name}",
                       hint=st["next_action"])
    questions = jsonio.load_json(path)
    schemas.require_valid(questions, "questions", QUESTIONS_FILE)
    raw = jsonio.load_json(state.require_artifact(run_dir, st, "profile"))
    store = attmod.load_store(raw["person_slug"])
    merged = profmod.merged_view(raw, store["attestations"])
    return _Ctx(run_dir, st, questions, merged, store, {q["id"]: q for q in questions["questions"]})


def _load_answers(ctx: _Ctx) -> dict:
    path = ctx.run_dir / ANSWERS_FILE
    if path.is_file():
        answers = jsonio.load_json(path)
        schemas.require_valid(answers, "answers", ANSWERS_FILE)
        return answers
    return {"schema_version": "1", "run_id": ctx.questions["run_id"], "rounds": []}


def _next_round_number(ctx: _Ctx) -> int:
    path = ctx.run_dir / ANSWERS_FILE
    if not path.is_file():
        return 1
    return max((r["round"] for r in jsonio.load_json(path)["rounds"]), default=0) + 1


# --- rounds built without the AI ---------------------------------------------------------------------------
def _selection_error(message: str, hint: str) -> CvtError:
    return CvtError(ExitCode.USAGE, "E_SELECT", message, hint=hint)


def _find_choice(q: dict, token: str) -> dict:
    """The choice a `--select` token names: its id, else its label (case-insensitive)."""
    options = qmod._options(q)
    for choice in options:
        if choice["id"] == token:
            return choice
    for choice in options:
        if choice["label"].casefold() == token.casefold():
            return choice
    known = ", ".join(c["id"] for c in options) or "(free text only)"
    raise _selection_error(f"{q['id']} has no choice '{token}'", f"choices for {q['id']}: {known}, or '{SKIP_WORD}'")


def _gap_attestation(choice: dict) -> dict:
    value = choice["value"].strip()
    terms = [] if qmod.REQ_ID_RE.match(value) else [p.strip() for p in value.split(qmod.VALUE_SEPARATOR) if p.strip()]
    return {
        "type": TYPE_SKILL, "claim": choice["label"], "terms": terms or [choice["label"]], "detail": choice["label"],
        "scope": copy.deepcopy(GLOBAL_SCOPE), "placement": PLACEMENT_SKILLS,
        "correction": dict(EMPTY_CORRECTION), "verbatim": choice["label"], "caveat": GAP_CAVEAT,
    }


def _item(qid: str, action: str, choice_ids: list[str], attestations: list[dict]) -> dict:
    return {"question_id": qid, "action": action, "choice_ids": choice_ids, "attestations": attestations,
            "instruction": "", "note": ""}


def select_round(questions: dict, selections: dict[str, list[str]], *, default_rest: bool, now: str) -> dict:
    """A `host_tool` round from `--select q-N=CHOICE[,CHOICE]` (`[]` = skip). No AI involved.

    A selected choice on a gap question becomes a skills-only `skill` attestation (section 7). Unknown question or
    choice ids raise `E_SELECT` (usage, exit 2). With `default_rest`, every other pending question is defaulted.
    """
    by_id = {q["id"]: q for q in questions["questions"]}
    pending = {q["id"] for q in qmod.pending_questions(questions)}
    items: list[dict] = []
    said: list[str] = []
    for qid, tokens in selections.items():
        q = by_id.get(qid)
        if q is None:
            raise _selection_error(f"unknown question '{qid}'", f"pending: {', '.join(sorted(pending)) or 'none'}")
        if qid not in pending:
            raise _selection_error(f"{qid} is {q['status']}, not pending", "select only pending questions")
        if not tokens:
            items.append(_item(qid, ACTION_SKIP, [], []))
            said.append(f"{qid}: {SKIP_WORD}")
            continue
        if q["type"] == qmod.TYPE_FREE:
            raise _selection_error(f"{qid} is free text", f"answer it in words, or use {qid}={SKIP_WORD}")
        if q["type"] in (qmod.TYPE_SINGLE, qmod.TYPE_YES_NO) and len(tokens) > 1:
            raise _selection_error(f"{qid} accepts one choice", f"pass a single choice for {qid}")
        chosen: list[dict] = []
        for token in tokens:
            choice = _find_choice(q, token)
            if choice not in chosen:
                chosen.append(choice)
        ids = [c["id"] for c in chosen]
        said.append(f"{qid}: {RAW_TEXT_SEP.join(c['label'] for c in chosen)}")
        if q["topic"] == qmod.TOPIC_GAP:
            items.append(_item(qid, ACTION_ATTEST, ids, [_gap_attestation(c) for c in chosen]))
        elif q["type"] == qmod.TYPE_SCOPE:
            items.append(_item(qid, ACTION_CONFIRM, ids, []))
        else:
            items.append(_item(qid, ACTION_CHOOSE, ids, []))
    unmentioned = sorted((pending - set(selections)) if default_rest else set(), key=qmod._number)
    rounds = [by_id[i]["round"] for i in [*selections, *unmentioned] if i in by_id]
    return {
        "round": max(rounds, default=1), "checkpoint": CHECKPOINT_1, "received_at": now,
        "channel": CHANNEL_HOST_TOOL, "raw_text": RAW_ITEM_SEP.join(said), "items": items,
        "unmentioned_question_ids": unmentioned,
    }


def _apply_strategy_choices(st: dict, questions: dict, items: list[dict]) -> None:
    """Persist template (and similar) strategy answers into run options for assemble/render."""
    by_id = {q["id"]: q for q in questions["questions"]}
    for item in items:
        if item["action"] != ACTION_CHOOSE:
            continue
        q = by_id.get(item["question_id"])
        if q is None or q.get("topic") != "strategy":
            continue
        choice_ids = item.get("choice_ids") or []
        if not choice_ids:
            continue
        values = {c["id"]: c["value"] for c in qmod._options(q)}
        value = values.get(choice_ids[0], choice_ids[0])
        if "template" in q["prompt"].casefold() and value in render_mod.TEMPLATES:
            st["options"]["template"] = value


def auto_round(run_dir: Path) -> dict:
    """An `auto` round: every pending question takes its default; no attestation is created."""
    ctx = _context(run_dir)
    pending = qmod.pending_questions(ctx.questions)
    return {
        "round": _next_round_number(ctx), "checkpoint": CHECKPOINT_1, "received_at": jsonio.now_iso(),
        "channel": CHANNEL_AUTO, "raw_text": AUTO_RAW_TEXT, "items": [],
        "unmentioned_question_ids": [q["id"] for q in pending],
    }


# --- validation --------------------------------------------------------------------------------------------
def _schema_violations(round_obj: dict) -> list[dict]:
    validator = Draft202012Validator(schemas.subschema("answers", "round"), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(round_obj), key=lambda e: (_path(list(e.absolute_path)), e.message))
    return [_violation(CODE_SCHEMA, _path(list(e.absolute_path)), e.message) for e in errors]


def _valid_choice_ids(q: dict) -> set[str]:
    return {c["id"] for c in qmod._options(q)}


def _proposal_violations(where: str, action: str, prop: dict, raw_norm: str, raw_nums: set[str],
                         item_ids: set[str], grounding: str, profile: dict) -> list[dict]:
    out: list[dict] = []
    is_correction = action == ACTION_CORRECT
    if is_correction != (prop["type"] == TYPE_CORRECTION) or is_correction != (prop["placement"] == PLACEMENT_CORRECTION):
        out.append(_violation(CODE_PLACEMENT, where, "corrections use type 'correction' with placement 'correction_only', "
                              "and only with action 'correct'"))
    if is_correction:
        corr = prop["correction"]
        if corr["item_id"] not in item_ids:
            out.append(_violation(CODE_UNKNOWN_REF, where, f"correction.item_id '{corr['item_id']}' is not a profile item"))
        if not corr["field"] or not corr["new_value"].strip():
            out.append(_violation(CODE_SCHEMA, where, "a correction needs correction.field and correction.new_value"))
        if [t for t in prop["terms"] if t.strip()]:
            out.append(_violation(CODE_SCHEMA, where, CORRECTION_TERMS_MESSAGE))
        if corr["item_id"] in item_ids and corr["field"]:
            current = _current_value(profile, corr["item_id"], corr["field"])
            if profmod.comparable(corr["old_value"]) != profmod.comparable(current):
                out.append(_violation(CODE_VERBATIM, where, f"correction.old_value '{corr['old_value']}' does not match "
                                      f"the profile's {corr['item_id']}.{corr['field']} '{current}'"))
    elif not [t for t in prop["terms"] if t.strip()]:
        out.append(_violation(CODE_SCHEMA, where, "terms is empty; list the exact terms the user licensed"))
    verbatim = profmod.comparable(prop["verbatim"])
    if not verbatim or verbatim not in raw_norm:
        out.append(_violation(CODE_VERBATIM, where, f"verbatim '{prop['verbatim']}' is not an exact part of raw_text"))
    stated = " ".join([prop["claim"], prop["detail"], *prop["terms"], prop["correction"]["new_value"]])
    extra = sorted(_numbers(stated) - raw_nums)
    if extra:
        out.append(_violation(CODE_NUMBER, where, f"numbers not stated by the user: {', '.join(extra)}"))
    if is_correction:
        out.extend(_correction_term_violations(f"{where}.correction.new_value", prop["correction"]["new_value"], grounding))
    else:
        out.extend(_term_violations(where, prop, grounding))
    return out


def _item_violations(ctx: _Ctx, round_obj: dict) -> list[dict]:
    out: list[dict] = []
    pending = {q["id"] for q in qmod.pending_questions(ctx.questions)}
    item_ids = {iid for iid, _k, _o in profmod.iter_items(ctx.profile)}
    raw_norm, raw_nums = profmod.comparable(round_obj["raw_text"]), _numbers(round_obj["raw_text"])
    for i, item in enumerate(round_obj["items"]):
        where, action, qid = f"items[{i}]", item["action"], item["question_id"]
        q = ctx.qs.get(qid) if qid else None
        if qid and q is None:
            out.append(_violation(CODE_UNKNOWN_REF, where, f"question_id {qid} is not in questions.json"))
        elif qid and qid not in pending:
            out.append(_violation(CODE_UNKNOWN_REF, where, f"{qid} is {q['status']}; only pending questions can be answered"))
        if action in NEEDS_QUESTION_ACTIONS and not qid:
            out.append(_violation(CODE_SCHEMA, where, f"action '{action}' needs a question_id"))
        if q is not None:
            valid = _valid_choice_ids(q)
            bad = [c for c in item["choice_ids"] if c not in valid]
            if bad:
                out.append(_violation(CODE_UNKNOWN_REF, where, f"{qid} has no choice: {', '.join(bad)}"))
        if action == ACTION_CONFIRM and q is not None:
            linked = [a for a in q["links"]["attestation_ids"] if a != qmod.PENDING_ATTESTATION]
            if q["type"] != qmod.TYPE_SCOPE or not linked:
                out.append(_violation(CODE_UNKNOWN_REF, where, f"{qid} is not a scope question with linked attestations yet"))
            for att_id in linked:
                found = next((a for a in ctx.store["attestations"] if a["id"] == att_id), None)
                if found is None or found["status"] != attmod.STATUS_PROPOSED:
                    out.append(_violation(CODE_UNKNOWN_REF, where, f"{att_id} is not a proposed attestation"))
        if action == ACTION_INSTRUCT and not item["instruction"].strip():
            out.append(_violation(CODE_SCHEMA, where, "action 'instruct' needs the instruction text"))
        if action in (ACTION_ATTEST, ACTION_CORRECT) and not item["attestations"]:
            out.append(_violation(CODE_SCHEMA, where, f"action '{action}' needs at least one attestation"))
        if action in NO_ATTESTATION_ACTIONS and item["attestations"]:
            out.append(_violation(CODE_SCHEMA, where, f"action '{action}' must not carry attestations"))
        grounding = _grounding(round_obj["raw_text"], q, item["choice_ids"])
        for j, prop in enumerate(item["attestations"]):
            if action in (ACTION_ATTEST, ACTION_CORRECT):
                out.extend(_proposal_violations(f"{where}.attestations[{j}]", action, prop, raw_norm, raw_nums, item_ids,
                                                grounding, ctx.profile))
    for qid in round_obj["unmentioned_question_ids"]:
        if qid not in pending:
            out.append(_violation(CODE_UNKNOWN_REF, "unmentioned_question_ids", f"{qid} is not a pending question"))
    return out


# --- planning ----------------------------------------------------------------------------------------------
def _resolve_scope(prop: dict, profile: dict) -> tuple[dict, str]:
    """(resolved scope, note). A role_label/items scope that matches nothing becomes `unresolved`."""
    resolved = scopemod.resolve(prop["scope"], profile)
    if resolved["kind"] in SCOPED_KINDS and not resolved["item_ids"]:
        words = " ".join(w for w in (prop["scope"]["description"], prop["scope"]["role_label"]) if w).strip()
        note = f"no profile item matches '{prop['scope']['role_label'] or words}'"
        return {**resolved, "kind": scopemod.SCOPE_UNRESOLVED, "role_label": "", "description": words}, note
    return resolved, ""


def _skeleton_choices(items: list[dict]) -> list[dict]:
    return [{"id": _choice_key(i["item_id"]), "label": i["label"], "value": i["item_id"]} for i in items]


def _skeleton(qid: str, round_no: int, parent: str, claims: list[str], scope: dict, mapped: list[dict],
              cands: list[dict]) -> dict:
    joined, words = ", ".join(claims), scope["description"]
    unresolved = scope["kind"] == scopemod.SCOPE_UNRESOLVED
    if unresolved:
        choices = [*_skeleton_choices(cands), {"id": SKILLS_ONLY_ID, "label": SKILLS_ONLY_LABEL, "value": SKILLS_ONLY_ID}]
        default = {"choice_ids": [SKILLS_ONLY_ID], "text": "", "description": SKILLS_ONLY_DESCRIPTION}
        prompt = (UNRESOLVED_PROMPT if words else UNRESOLVED_PROMPT_NO_WORDS).format(claims=joined, description=words)
        linked = [i["item_id"] for i in cands]
    else:
        choices = _skeleton_choices(mapped)
        default = {"choice_ids": [c["id"] for c in choices], "text": "", "description": SCOPE_USE_ALL_DESCRIPTION}
        prompt = (SKELETON_PROMPT if words else SKELETON_PROMPT_NO_WORDS).format(claims=joined, description=words)
        linked = [i["item_id"] for i in mapped]
    return {
        "id": qid, "checkpoint": CHECKPOINT_1, "round": round_no, "type": qmod.TYPE_SCOPE, "topic": "scope",
        "prompt": prompt, "choices": choices, "allow_free_text": True, "default": default,
        "links": {"req_ids": [], "item_ids": linked, "issue_ids": [], "attestation_ids": [qmod.PENDING_ATTESTATION]},
        "parent_id": parent, "status": qmod.STATUS_PENDING, "suppressed_reason": "",
    }


@dataclass
class _Built:
    plan: dict
    proposals: list[tuple[dict, dict]]  # (round item, proposal with resolved scope)
    scope_updates: list[dict]
    changes: dict[str, str]


def _chosen_items(q: dict, choice_ids: list[str]) -> list[str]:
    """Item ids a confirm_scope reply selects (empty replies take the question default; skills-only drops out)."""
    by_id = {c["id"]: c["value"] for c in q["choices"]}
    values = [by_id[i] for i in (choice_ids or q["default"]["choice_ids"]) if i in by_id]
    return [v for v in values if v != SKILLS_ONLY_ID]


def _new_scope(ctx: _Ctx, att: dict, items: list[str]) -> tuple[dict, str]:
    if not items:
        return copy.deepcopy({**GLOBAL_SCOPE, "description": att["scope"]["description"]}), PLACEMENT_SKILLS
    resolved = scopemod.resolve(
        {"kind": scopemod.SCOPE_ITEMS, "role_label": "", "item_ids": items, "description": att["scope"]["description"]},
        ctx.profile,
    )
    if att["scope"]["kind"] == scopemod.SCOPE_ROLE_LABEL and set(resolved["item_ids"]) == set(att["scope"]["item_ids"]):
        return copy.deepcopy(att["scope"]), att["placement"]
    return resolved, att["placement"]


def _plan_correction(profile: dict, corr: dict) -> dict:
    """The correction as the dry run shows it: `old_value` is what the profile holds now."""
    if not corr["item_id"]:
        return dict(corr)
    return {**corr, "old_value": _current_value(profile, corr["item_id"], corr["field"])}


def _build(ctx: _Ctx, round_obj: dict) -> _Built:
    violations = _schema_violations(round_obj) or _item_violations(ctx, round_obj)
    proposals: list[tuple[dict, dict]] = []
    entries: list[dict] = []
    groups: list[tuple[int, dict, dict, list[str], str]] = []  # (item index, item, scope, claims, note)
    if not violations:
        for i, item in enumerate(round_obj["items"]):
            for j, prop in enumerate(item["attestations"]):
                try:
                    scope, note = _resolve_scope(prop, ctx.profile)
                except CvtError as err:
                    code = CODE_UNKNOWN_REF if err.err_id == "E_SCOPE_UNKNOWN_ID" else CODE_SCHEMA
                    violations.append(_violation(code, f"items[{i}].attestations[{j}]", err.message))
                    continue
                resolved = {**prop, "scope": scope, "correction": _plan_correction(ctx.profile, prop["correction"])}
                proposals.append((item, resolved))
                scoped = prop["type"] != TYPE_CORRECTION and scope["kind"] in (*SCOPED_KINDS, scopemod.SCOPE_UNRESOLVED)
                mapped = scopemod.describe_mapping(scope, ctx.profile) if scope["kind"] in SCOPED_KINDS else []
                entries.append({
                    "item_index": i, "question_id": item["question_id"], "claim": prop["claim"], "terms": list(prop["terms"]),
                    "type": prop["type"], "placement": prop["placement"], "scope_kind": scope["kind"], "role_label": scope["role_label"],
                    "description": scope["description"], "items": mapped, "needs_confirmation": scoped,
                    "unresolved": scope["kind"] == scopemod.SCOPE_UNRESOLVED, "caveat": prop["caveat"], "note": note,
                    "correction": resolved["correction"],
                })
                if scoped:
                    groups.append((i, item, scope, [prop["claim"]], note))
    if violations:
        raise CvtError(
            ExitCode.CHECK_FAILED, FAILED_ID, f"the answers round has {len(violations)} problems",
            hint="patch only the listed items in the round file and rerun the same command", violations=violations,
        )

    # one scope question per (round item, distinct scope)
    merged: list[tuple[int, dict, dict, list[str]]] = []
    for i, item, scope, claims, _note in groups:
        key = (i, scope["kind"], tuple(scope["item_ids"]), scope["description"])
        hit = next((m for m in merged if (m[0], m[2]["kind"], tuple(m[2]["item_ids"]), m[2]["description"]) == key), None)
        if hit:
            hit[3].extend(claims)
        else:
            merged.append((i, item, scope, list(claims)))
    next_n = max((qmod._number(q["id"]) for q in ctx.questions["questions"]), default=0)
    round_no = max((q["round"] for q in ctx.questions["questions"]), default=0) + 1
    skeletons = []
    for i, item, scope, claims in merged:
        next_n += 1
        mapped = scopemod.describe_mapping(scope, ctx.profile) if scope["kind"] in SCOPED_KINDS else []
        cands = []
        if scope["kind"] == scopemod.SCOPE_UNRESOLVED:
            cands = scopemod.candidates(scope["description"], ctx.profile)
        skeletons.append(_skeleton(qmod.QUESTION_ID_FORMAT % next_n, round_no, item["question_id"], claims, scope, mapped, cands))

    changes: dict[str, str] = {}
    for item in round_obj["items"]:
        qid = item["question_id"]
        if qid:
            new = "skipped" if item["action"] == ACTION_SKIP else "answered"
            if changes.get(qid) != "answered":
                changes[qid] = new
    for qid in round_obj["unmentioned_question_ids"]:
        changes.setdefault(qid, "defaulted")

    updates: list[dict] = []
    for item in round_obj["items"]:
        if item["action"] != ACTION_CONFIRM:
            continue
        q = ctx.qs[item["question_id"]]
        chosen = _chosen_items(q, item["choice_ids"])
        for att_id in (a for a in q["links"]["attestation_ids"] if a != qmod.PENDING_ATTESTATION):
            att = attmod.get(ctx.store, att_id)
            scope, placement = _new_scope(ctx, att, chosen)
            updates.append({
                "attestation_id": att_id, "claim": att["claim"], "from_kind": att["scope"]["kind"],
                "to_kind": scope["kind"], "item_ids": scope["item_ids"], "scope": scope, "placement": placement,
                "items": scopemod.describe_mapping(scope, ctx.profile) if scope["kind"] in SCOPED_KINDS else [],
            })

    still_pending = [q["id"] for q in qmod.pending_questions(ctx.questions) if q["id"] not in changes]
    plan = {
        "round": _next_round_number(ctx), "channel": round_obj["channel"], "attestations": entries,
        "skeletons": skeletons,
        "unresolved": [e["claim"] for e in entries if e["unresolved"]],
        "scope_updates": [{k: v for k, v in u.items() if k != "scope"} for u in updates],
        "question_changes": [{"question_id": q, "from": qmod.STATUS_PENDING, "to": to} for q, to in changes.items()],
        "instructions": [
            {"question_id": it["question_id"], "instruction": it["instruction"]}
            for it in round_obj["items"] if it["action"] == ACTION_INSTRUCT
        ],
        "pending_after": still_pending,
    }
    return _Built(plan, proposals, updates, changes)


def plan_round(run_dir: Path, round_obj: dict) -> dict:
    """Dry run: validate the round and describe what committing it would do. Writes nothing."""
    return _build(_context(run_dir), round_obj).plan


def _clip(text: str, width: int = PLAN_PROMPT_WIDTH) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def plan_table(plan: dict) -> list[str]:
    """Human lines for a plan: one per created attestation, then statuses, scope updates and follow-up skeletons."""
    lines = [
        f"round {plan['round']} ({plan['channel']}): {len(plan['attestations'])} attestation(s), "
        f"{len(plan['skeletons'])} scope question(s), {len(plan['unresolved'])} unresolved",
    ]
    for e in plan["attestations"]:
        if e["scope_kind"] in SCOPED_KINDS:
            where = f"{e['scope_kind']}={e['role_label'] or e['description']} -> " + (
                ", ".join(f"{i['item_id']} {i['label']}" for i in e["items"]) or "no items")
        else:
            where = e["scope_kind"] + (f" ({e['note']})" if e["note"] else "")
        shown = f"+ {e['type']} \"{e['claim']}\" [{e['placement']}] {where}"
        corr = e["correction"]
        if e["type"] == TYPE_CORRECTION:
            shown += (f" {corr['item_id']}.{corr['field']}: {_clip(corr['old_value'], CORRECTION_VALUE_WIDTH)}"
                      f" -> {_clip(corr['new_value'], CORRECTION_VALUE_WIDTH)}")
        if e["terms"] and [t.casefold() for t in e["terms"]] != [e["claim"].casefold()]:
            shown += TERMS_LABEL + RAW_TEXT_SEP.join(e["terms"])
        lines.append(shown)
    by_status: dict[str, list[str]] = {}
    for c in plan["question_changes"]:
        by_status.setdefault(c["to"], []).append(c["question_id"])
    if by_status:
        lines.append("questions: " + "; ".join(f"{s} {', '.join(ids)}" for s, ids in by_status.items()))
    for u in plan["scope_updates"]:
        lines.append(f"~ {u['attestation_id']} \"{u['claim']}\": {u['from_kind']} -> {u['to_kind']} ({len(u['item_ids'])} item(s))")
    for s in plan["skeletons"]:
        lines.append(f"? follow-up {s['id']} {s['type']}: {_clip(s['prompt'])}")
    if plan["instructions"]:
        lines.append(f"instructions kept for tailoring: {len(plan['instructions'])}")
    return lines


# --- commit ------------------------------------------------------------------------------------------------
def _fill_links(questions: dict, created: list[tuple[dict, dict]]) -> None:
    """Replace the `pending` placeholder of scope questions with the attestations created for their parent."""
    for q in questions["questions"]:
        links = q["links"]["attestation_ids"]
        if q["type"] != qmod.TYPE_SCOPE or q["status"] != qmod.STATUS_PENDING or qmod.PENDING_ATTESTATION not in links:
            continue
        cands = [(att, item) for att, item in created
                 if item["question_id"] == q["parent_id"] and att["scope"]["kind"] != scopemod.SCOPE_GLOBAL
                 and att["type"] != TYPE_CORRECTION]
        exact = [c for c in cands if f'"{c[0]["claim"]}"' in q["prompt"]]
        same_items = [c for c in (exact or cands) if set(c[0]["scope"]["item_ids"]) == set(q["links"]["item_ids"])]
        chosen = same_items or exact or cands
        if not chosen:
            continue
        keep = [i for i in links if i != qmod.PENDING_ATTESTATION]
        q["links"]["attestation_ids"] = keep + [att["id"] for att, _ in chosen if att["id"] not in keep]


def pending_kind(questions: list[dict]) -> str:
    follow = any(q["parent_id"] or q["topic"] in ("scope", "followup") for q in questions)
    return "followups" if follow else "questions"


def commit_round(run_dir: Path, round_obj: dict) -> dict:
    """Apply a round: append it to answers.json, update question statuses, create `proposed` attestations,
    apply scope confirmations, then set the stage. Returns `{created, pending, unresolved, instructions, ...}`.
    """
    ctx = _context(run_dir)
    built = _build(ctx, round_obj)
    st, store = ctx.st, ctx.store
    run_slug = st["run_slug"]

    for upd in built.scope_updates:
        att = attmod.get(store, upd["attestation_id"])
        att["scope"], att["placement"] = upd["scope"], upd["placement"]
    created: list[tuple[dict, dict]] = []
    for item, prop in built.proposals:
        att = attmod.add(store, prop, run_id=run_slug, question_id=item["question_id"])
        created.append((att, item))
    attmod.save_store(ctx.profile["person_slug"], store)

    questions = copy.deepcopy(ctx.questions)
    for q in questions["questions"]:
        if q["id"] in built.changes:
            q["status"] = built.changes[q["id"]]
    _fill_links(questions, created)

    answers = _load_answers(ctx)
    stored = copy.deepcopy(round_obj)
    stored["round"] = built.plan["round"]
    answers["rounds"].append(stored)
    schemas.require_valid(answers, "answers", ANSWERS_FILE)
    jsonio.dump_json(answers, ctx.run_dir / ANSWERS_FILE)
    jsonio.dump_json(questions, ctx.run_dir / QUESTIONS_FILE)

    pending_qs = qmod.pending_questions(questions)
    pending = [q["id"] for q in pending_qs]
    unresolved = [a["id"] for a in store["attestations"]
                  if a["run_id"] == run_slug and a["status"] == attmod.STATUS_PROPOSED
                  and a["scope"]["kind"] == scopemod.SCOPE_UNRESOLVED]
    awaiting = bool(pending or unresolved)
    if awaiting:
        claims = ", ".join(a["claim"] for a in store["attestations"] if a["id"] in unresolved)
        message = PENDING_MESSAGE.format(n=len(pending), ids=", ".join(pending)) if pending else \
            UNRESOLVED_MESSAGE.format(claims=claims)
        state.set_stage(st, STAGE_AWAITING, STATUS_AWAITING,
                        pending={"kind": pending_kind(pending_qs), "question_ids": pending, "message": message})
        st["checkpoints"]["cp1"] = CP1_PENDING
    else:
        state.set_stage(st, STAGE_APPLIED)
        st["checkpoints"]["cp1"] = CP1_DONE
    _apply_strategy_choices(st, questions, stored["items"])
    state.record_artifact(ctx.run_dir, st, ANSWERS_ARTIFACT, ANSWERS_FILE, cascade=True)
    state.record_artifact(ctx.run_dir, st, QUESTIONS_ARTIFACT, QUESTIONS_FILE, cascade=False)
    state.add_history(st, "answers-apply", f"round={stored['round']} created={len(created)} pending={len(pending)}")
    state.save(ctx.run_dir, st)
    return {
        "round": stored["round"], "created": [a["id"] for a, _ in created], "pending": pending,
        "unresolved": unresolved, "instructions": built.plan["instructions"],
        "scope_updates": [u["attestation_id"] for u in built.scope_updates],
        "question_changes": built.plan["question_changes"], "awaiting": awaiting, "stage": st["stage"],
    }
