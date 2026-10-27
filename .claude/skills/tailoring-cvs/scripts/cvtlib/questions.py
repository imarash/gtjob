"""Checkpoint-1 questions: validation, suppression, numbering and host rendering (interfaces.md section 7)."""

from __future__ import annotations

import copy
import math
import re
from typing import Any

from . import attestations as attmod
from . import profile as profmod
from . import schemas
from .errors import CvtError, ExitCode

MAX_CP1_QUESTIONS = 8
CLAUDE_MAX_QUESTIONS_PER_CALL = 4
CLAUDE_MAX_OPTIONS = 4
CLAUDE_MIN_OPTIONS = 2
CLAUDE_HEADER_MAX = 12

STATUS_PENDING, STATUS_SUPPRESSED = "pending", "suppressed"
TYPE_MULTI, TYPE_SINGLE, TYPE_YES_NO = "multi_select", "single_select", "yes_no"
TYPE_FREE, TYPE_SCOPE = "free_text", "scope_confirm"
SELECT_TYPES = (TYPE_MULTI, TYPE_SINGLE, TYPE_SCOPE)
MULTI_TYPES = (TYPE_MULTI, TYPE_SCOPE)
TOPIC_GAP = "gap"
CHECKPOINT_1 = 1
PENDING_ATTESTATION = "pending"  # placeholder in links.attestation_ids until `answers-apply --commit`
VALUE_SEPARATOR = "|"
REQ_ID_RE = re.compile(r"^req-[0-9]+$")
QUESTION_ID_FORMAT = "q-%d"
QUESTION_ID_RE = re.compile(r"^q-([0-9]+)$")

CODE_SCHEMA, CODE_UNKNOWN_REF = "schema", "unknown_ref"
REASON_PREFIX = "answered by "
YES_ID, NO_ID = "yes", "no"
YES_LABEL, NO_LABEL = "Yes", "No"
CURSOR_TITLE = "CV tailoring: a few questions"
CHAT_FOOTER = "Answer by number/letter or in your own words; anything you skip uses the default."
CHAT_DEFAULT_FORMAT = "[Default: {text}]"
HEADERS = {
    "gap": "Gaps", "source_issue": "Source", "metric": "Metrics", "strategy": "Strategy",
    "scope": "Scope", "followup": "Follow-up",
}
FALLBACK_HEADER = "Question"
PART_SUFFIX = " ({part}/{total})"
CLAUDE_QUESTION_FORMAT = "[{qid}] {prompt}"
OPTION_DESCRIPTIONS = {"gap": "I have this experience"}
DEFAULT_OPTION_DESCRIPTION = "Choose this"
DEFAULT_MARK = " (default)"
SKIP_LABEL = "Skip"
USE_DEFAULT_LABEL = "Use default"
SKIP_DESCRIPTION = "Same as the default"

# Fields a new question may omit; `add` fills them in.
QUESTION_DEFAULTS: dict[str, Any] = {
    "checkpoint": CHECKPOINT_1, "choices": [], "allow_free_text": True, "parent_id": "",
    "status": STATUS_PENDING, "suppressed_reason": "",
}
LINK_KEYS = ("req_ids", "item_ids", "issue_ids", "attestation_ids")
REQUIRED_NEW_FIELDS = ("type", "topic", "prompt", "default")
LIST_SEPARATORS = ("; ", ", ", " and ", " or ")  # tried in order when removing a label from a prompt list
LABEL_SEPARATOR = "; "
GAP_PROMPT_REWRITE = ("Your CV doesn't currently show: {labels}. "
                      "Which of these do you actually have experience with?")


def _violation(code: str, item_id: str, message: str) -> dict:
    return {"code": code, "item_id": item_id, "message": message}


def _number(qid: str) -> int:
    m = QUESTION_ID_RE.match(qid)
    return int(m.group(1)) if m else 0


def pending_questions(questions: dict) -> list[dict]:
    return [q for q in questions["questions"] if q["status"] == STATUS_PENDING]


def choice_terms(choice: dict, requirements: dict[str, dict]) -> list[str]:
    """Terms a gap choice stands for: the `term|synonym` parts of its value, or a requirement's keywords."""
    value = choice["value"].strip()
    if REQ_ID_RE.match(value):
        req = requirements.get(value)
        return [k.strip() for k in req["keywords"] if k.strip()] if req else []
    return [part.strip() for part in value.split(VALUE_SEPARATOR) if part.strip()]


def _covering_all(attestations: list[dict], terms: list[str]) -> list[dict]:
    """The attestations that cover every term (a requirement's keywords); [] when any term is uncovered."""
    store = {"attestations": attestations}
    found: list[dict] = []
    for term in terms:
        hit = attmod.find_by_terms(store, [term])
        if not hit:
            return []
        found.extend(a for a in hit if a not in found)
    return found


def _covering_any(attestations: list[dict], terms: list[str]) -> list[dict]:
    """The attestations covering the first term (in order) that any attestation covers; [] when none does."""
    store = {"attestations": attestations}
    for term in terms:
        hit = attmod.find_by_terms(store, [term])
        if hit:
            return hit
    return []


def _choice_covering(choice: dict, attestations: list[dict], reqs: dict[str, dict]) -> list[dict]:
    """A `req-N` value needs every keyword covered; a `term|synonym` value needs any one of its parts covered."""
    terms = choice_terms(choice, reqs)
    if not terms:
        return []
    if REQ_ID_RE.match(choice["value"].strip()):
        return _covering_all(attestations, terms)
    return _covering_any(attestations, terms)


def _word_re(text: str) -> re.Pattern[str]:
    """Case-insensitive whole-word pattern for `text` (word boundaries that also work around punctuation)."""
    return re.compile(rf"(?<!\w){re.escape(text)}(?!\w)", re.IGNORECASE)


def _remove_label(prompt: str, label: str) -> str:
    """Remove `label` plus one adjacent list separator (trailing first, else leading); unchanged when neither exists."""
    seps = "|".join(re.escape(s) for s in LIST_SEPARATORS)
    body = _word_re(label).pattern
    for pattern in (rf"{body}(?:{seps})", rf"(?:{seps}){body}"):
        out, count = re.subn(pattern, "", prompt, count=1, flags=re.IGNORECASE)
        if count:
            return out
    return prompt


def _tidy_prompt(prompt: str) -> str:
    prompt = re.sub(r"([;,])(\s*[;,])+", r"\1", prompt)
    prompt = re.sub(r"\s+([;,.?:])", r"\1", prompt)
    return re.sub(r"\s{2,}", " ", prompt).strip()


def _rewrite_gap_prompt(q: dict, dropped: list[dict], reqs: dict[str, dict]) -> None:
    """Remove dropped choices' labels from a gap prompt; fall back to the template if any term is still named."""
    prompt = q["prompt"]
    for choice in dropped:
        prompt = _remove_label(prompt, choice["label"])
    prompt = _tidy_prompt(prompt)
    named = [choice["label"] for choice in dropped] + [t for c in dropped for t in choice_terms(c, reqs)]
    if any(_word_re(term).search(prompt) for term in named if term.strip()):
        prompt = GAP_PROMPT_REWRITE.format(labels=LABEL_SEPARATOR.join(c["label"] for c in q["choices"]))
    q["prompt"] = prompt


def suppress(questions: dict, attestations: list[dict], *, jd: dict | None = None) -> tuple[dict, list[dict]]:
    """Drop gap choices that active attestations already cover. Returns (questions, suppressed entries).

    Each entry is `{question_id, choice_id, reason, question_suppressed}`. A question left without choices
    becomes `status: suppressed` with `suppressed_reason` set.
    """
    out = copy.deepcopy(questions)
    reqs = {r["id"]: r for r in (jd or {}).get("requirements", [])}
    suppressed: list[dict] = []
    for q in out["questions"]:
        if q["status"] != STATUS_PENDING or q["topic"] != TOPIC_GAP or not q["choices"]:
            continue
        kept, reasons, dropped = [], [], []
        for choice in q["choices"]:
            covering = _choice_covering(choice, attestations, reqs)
            if covering:
                why = REASON_PREFIX + ", ".join(f"{a['id']} ({a['claim']})" for a in covering)
                dropped.append((choice, why))
                if why not in reasons:
                    reasons.append(why)
            else:
                kept.append(choice)
        if not dropped:
            continue
        q["choices"] = kept
        kept_ids = {c["id"] for c in kept}
        q["default"]["choice_ids"] = [i for i in q["default"]["choice_ids"] if i in kept_ids]
        whole = not kept
        if not whole:
            _rewrite_gap_prompt(q, [c for c, _ in dropped], reqs)
        if whole:
            q["status"] = STATUS_SUPPRESSED
            q["suppressed_reason"] = "; ".join(reasons)
        suppressed.extend(
            {"question_id": q["id"], "choice_id": c["id"], "reason": why, "question_suppressed": whole}
            for c, why in dropped
        )
    return out, suppressed


def _rules(questions: dict, attestations: list[dict], jd: dict | None, profile: dict | None) -> list[dict]:
    qs = questions["questions"]
    violations: list[dict] = []
    ids = [q["id"] for q in qs]
    for qid in sorted({i for i in ids if ids.count(i) > 1}):
        violations.append(_violation(CODE_SCHEMA, qid, f"duplicate question id {qid}"))
    # Two groups are capped separately. The initial batch (empty parent_id, any round) is capped as a whole, so an AI
    # cannot hide questions by labelling them as later rounds. Follow-ups (parent_id set) are capped per round, because
    # a follow-up batch is added while round 1 is still uncommitted and must not count against the initial batch.
    initial_open = 0
    follow_ups_by_round: dict[int, int] = {}
    for q in qs:
        if q["status"] == STATUS_PENDING and q["checkpoint"] == CHECKPOINT_1:
            if q["parent_id"]:
                follow_ups_by_round[q["round"]] = follow_ups_by_round.get(q["round"], 0) + 1
            else:
                initial_open += 1
    if initial_open > MAX_CP1_QUESTIONS:
        violations.append(_violation(
            CODE_SCHEMA, "questions",
            f"{initial_open} pending checkpoint-1 questions in the initial batch; the limit is {MAX_CP1_QUESTIONS}",
        ))
    for round_no, count in sorted(follow_ups_by_round.items()):
        if count > MAX_CP1_QUESTIONS:
            violations.append(_violation(
                CODE_SCHEMA, "questions",
                f"{count} pending checkpoint-1 questions in round {round_no} follow-ups; the limit is {MAX_CP1_QUESTIONS}",
            ))
    req_ids = {r["id"] for r in jd["requirements"]} if jd else None
    item_ids = {iid for iid, _kind, _obj in profmod.iter_items(profile)} if profile else None
    issue_ids = {i["id"] for i in profile["source_issues"]} if profile else None
    att_ids = {a["id"] for a in attestations}
    known = set(ids)
    for q in qs:
        qid = q["id"]
        if q["status"] == STATUS_SUPPRESSED:
            continue
        if not q["allow_free_text"]:
            violations.append(_violation(CODE_SCHEMA, qid, "allow_free_text must be true on every question"))
        if not q["default"]["description"].strip():
            violations.append(_violation(CODE_SCHEMA, qid, "default.description is empty; say what happens if skipped"))
        choice_ids = [c["id"] for c in q["choices"]]
        if q["type"] in SELECT_TYPES and not choice_ids:
            violations.append(_violation(CODE_SCHEMA, qid, f"{q['type']} question has no choices"))
        if len(set(choice_ids)) != len(choice_ids):
            violations.append(_violation(CODE_SCHEMA, qid, "duplicate choice ids"))
        stray = [i for i in q["default"]["choice_ids"] if i not in choice_ids]
        if stray:
            violations.append(_violation(CODE_UNKNOWN_REF, qid, f"default.choice_ids not in choices: {', '.join(stray)}"))
        if q["parent_id"] and q["parent_id"] not in known:
            violations.append(_violation(CODE_UNKNOWN_REF, qid, f"parent_id {q['parent_id']} is not a question"))
        links = q["links"]
        for label, wanted, universe in (
            ("req_ids", links["req_ids"], req_ids), ("item_ids", links["item_ids"], item_ids),
            ("issue_ids", links["issue_ids"], issue_ids),
            ("attestation_ids", [i for i in links["attestation_ids"] if i != PENDING_ATTESTATION], att_ids),
        ):
            missing = [i for i in wanted if universe is not None and i not in universe]
            if missing:
                violations.append(_violation(CODE_UNKNOWN_REF, qid, f"links.{label} unknown: {', '.join(missing)}"))
        if q["topic"] == TOPIC_GAP and req_ids is not None:
            bad = [c["value"] for c in q["choices"] if REQ_ID_RE.match(c["value"]) and c["value"] not in req_ids]
            if bad:
                violations.append(_violation(CODE_UNKNOWN_REF, qid, f"choice values name unknown requirements: {', '.join(bad)}"))
    return violations


def check(
    questions: dict, attestations: list[dict], *, jd: dict | None = None, profile: dict | None = None,
) -> tuple[dict, list[dict]]:
    """Validate (schema + rules), then suppress. Returns (questions, violations); violations leave `questions` as is.

    `jd` and `profile` enable the link-existence checks and requirement-keyword suppression.
    """
    problems = schemas.validate(questions, "questions")
    if problems:
        return questions, schemas.to_violations(problems)
    violations = _rules(questions, attestations, jd, profile)
    if violations:
        return questions, violations
    checked, _ = suppress(questions, attestations, jd=jd)
    return checked, []


def _complete(raw: dict) -> dict:
    missing = [f for f in REQUIRED_NEW_FIELDS if f not in raw]
    if missing:
        raise CvtError(
            ExitCode.CHECK_FAILED, "E_QUESTION_FIELDS", f"new question lacks: {', '.join(missing)}",
            hint="every follow-up needs type, topic, prompt and default (see questions.schema.json)",
        )
    q = copy.deepcopy(QUESTION_DEFAULTS)
    q.update(copy.deepcopy(raw))
    q["links"] = {**{k: [] for k in LINK_KEYS}, **(q.get("links") or {})}
    return q


def add(questions: dict, new: list[dict]) -> dict:
    """Append `new` questions with fresh `q-N` ids (after the current max) and round = max round + 1 unless given."""
    out = copy.deepcopy(questions)
    existing = out["questions"]
    known = {q["id"] for q in existing}
    next_n = max((_number(q["id"]) for q in existing), default=0)
    next_round = max((q["round"] for q in existing), default=0) + 1
    renamed: dict[str, str] = {}
    batch: list[dict] = []
    for raw in new:
        q = _complete(raw)
        next_n += 1
        old = q.get("id", "")
        if old and old not in known:
            renamed[old] = QUESTION_ID_FORMAT % next_n
        q["id"] = QUESTION_ID_FORMAT % next_n
        q.setdefault("round", next_round)
        batch.append(q)
    for q in batch:
        q["parent_id"] = renamed.get(q["parent_id"], q["parent_id"])
    out["questions"] = existing + batch
    return out


# --- rendering ---------------------------------------------------------------------------------------------
def _letter(index: int) -> str:
    return chr(ord("a") + index)


def _options(q: dict) -> list[dict]:
    """The question's choices; yes_no without choices gets Yes and No."""
    if q["choices"]:
        return q["choices"]
    if q["type"] == TYPE_YES_NO:
        return [{"id": YES_ID, "label": YES_LABEL, "value": YES_ID}, {"id": NO_ID, "label": NO_LABEL, "value": NO_ID}]
    return []


def render_chat(questions: dict) -> str:
    """One line per pending question: prompt, lettered choices, default in brackets; then the footer."""
    lines = []
    for n, q in enumerate(pending_questions(questions), start=1):
        parts = [f"{n}. [{q['id']}] {q['prompt']}"]
        options = _options(q)
        if options:
            parts.append("  ".join(f"{_letter(i)}) {c['label']}" for i, c in enumerate(options)))
        parts.append(CHAT_DEFAULT_FORMAT.format(text=q["default"]["description"]))
        lines.append(" ".join(parts))
    if lines:
        lines.append(CHAT_FOOTER)
    return "\n".join(lines)


def _render_cursor(pending: list[dict]) -> dict:
    return {
        "title": CURSOR_TITLE,
        "questions": [
            {
                "id": q["id"], "prompt": q["prompt"],
                "options": [{"id": c["id"], "label": c["label"]} for c in _options(q)],
                "allow_multiple": q["type"] in MULTI_TYPES,
            }
            for q in pending
        ],
    }


def _chunks(items: list[dict]) -> list[list[dict]]:
    """Balanced parts of at most CLAUDE_MAX_OPTIONS (5 -> 3+2, never a lone trailing option)."""
    parts = max(math.ceil(len(items) / CLAUDE_MAX_OPTIONS), 1)
    size = max(math.ceil(len(items) / parts), 1)
    return [items[i:i + size] for i in range(0, len(items), size)] or [[]]


def _header(topic: str, part: int, total: int) -> str:
    base = HEADERS.get(topic, FALLBACK_HEADER)
    suffix = PART_SUFFIX.format(part=part, total=total) if total > 1 else ""
    return base[: CLAUDE_HEADER_MAX - len(suffix)] + suffix


def _claude_options(q: dict, chunk: list[dict]) -> list[dict]:
    default_ids = set(q["default"]["choice_ids"])
    what = OPTION_DESCRIPTIONS.get(q["topic"], DEFAULT_OPTION_DESCRIPTION)
    options = [
        {"label": c["label"], "description": what + (DEFAULT_MARK if c["id"] in default_ids else "")}
        for c in chunk
    ]
    if q["type"] == TYPE_FREE:
        options = [{"label": q["default"]["text"] or USE_DEFAULT_LABEL, "description": q["default"]["description"]}]
    if len(options) < CLAUDE_MIN_OPTIONS:
        options.append({"label": SKIP_LABEL, "description": SKIP_DESCRIPTION})
    return options


def _render_claude(pending: list[dict]) -> dict:
    asked: list[dict] = []
    for q in pending:
        chunks = _chunks(_options(q))
        for part, chunk in enumerate(chunks, start=1):
            asked.append({
                "question": CLAUDE_QUESTION_FORMAT.format(qid=q["id"], prompt=q["prompt"]),
                "header": _header(q["topic"], part, len(chunks)),
                "multiSelect": q["type"] in MULTI_TYPES,
                "options": _claude_options(q, chunk),
            })
    size = CLAUDE_MAX_QUESTIONS_PER_CALL
    return {"calls": [asked[i:i + size] for i in range(0, len(asked), size)]}


def render_host(questions: dict, host: str) -> dict:
    """Structured-question payload for `cursor` or `claude_code` (interfaces.md section 7)."""
    pending = pending_questions(questions)
    if host == "cursor":
        return _render_cursor(pending)
    if host == "claude_code":
        return _render_claude(pending)
    raise CvtError(
        ExitCode.USAGE, "E_HOST_FORMAT", f"no host question format for '{host}'",
        hint="use --host cursor or --host claude_code, or --format chat",
    )
