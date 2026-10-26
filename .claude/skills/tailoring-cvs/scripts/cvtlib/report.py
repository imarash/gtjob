"""report.md: the honest companion to the CV, built from run artifacts alone (interfaces.md section 3, WP-19).

`build_report(run_dir)` reads the run directory and returns Markdown. Optional artifacts (validation, critique,
fit, answers, usage, profile) that are missing produce a "not run" or "not recorded" line, never an error.
Text taken from the CV or JD is rendered as data (single-line, table-safe), never interpreted.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

from . import jsonio, profile_store, state, usage
from .errors import CvtError, ExitCode

REPORT_FILE = "report.md"
CV_PDF_FILE = "cv.pdf"
REQUIRED_ARTIFACTS = ("jd.json", "match.json", "tailored.json")
OPTIONAL_FILES = {
    "validation": "validation.json", "critique": "critique.json", "fit": "fit.json",
    "answers": "answers.json", "questions": "questions.json", "profile": "profile.json",
    "plan": "tailor-plan.json",
}
UNNAMED_COMPANY = "unnamed company"
DRAFT_REPORT_BANNER = (
    "> **Draft report.** The run has not passed validation yet (stage `{stage}`), so the gates and page "
    "count below may be incomplete. Run `report` again after `validate`."
)
CONFIRM_PATTERN = re.compile(r"\[\[CONFIRM:[^\]]*\]\]")
ATT_ID_PATTERN = re.compile(r"^att-[0-9]{3,}$")
QUOTE_MAX_CHARS = 60
EVIDENCE_MAX_PER_REQ = 3
CRITIQUE_TOP_ISSUES = 5
SEVERITY_ORDER = ("high", "medium", "low")
STATUS_PROPOSED = "proposed"
STATUS_ACTIVE = "active"
RECRUITER_ASKS_NOTE = (
    "The recruiter asked these questions separately. Answer them in your reply to the recruiter; "
    "they are never placed in the CV."
)
NOT_CONFIRMED_NOTE = "Not added, as you didn't confirm it."
REJECTED_NOTE = " You answered that you don't have it."
INJECTION_NOTE = (
    "The job description contained text that reads like instructions to an AI. It was treated as plain "
    "content and not followed. Review the quoted text below if it matters to you."
)
DEFAULT_ACTION_REJECT = "reject"
CHANNEL_AUTO = "auto"
DEFAULT_QUESTION_STATUSES = ("defaulted", "skipped")
DASH = "-"
NOT_RECORDED = "not recorded"


def _artifact_error(name: str, run_dir: Path) -> CvtError:
    return CvtError(
        ExitCode.STATE, "E_ARTIFACT_MISSING", f"{name} not found in {Path(run_dir).name}",
        hint="the report needs jd.json, match.json and tailored.json; run `cvt status` for the next step",
    )


def _load_optional(run_dir: Path, name: str) -> dict | None:
    path = run_dir / OPTIONAL_FILES[name]
    return jsonio.load_json(path) if path.is_file() else None


def _cell(value: Any) -> str:
    """One table cell: single line, pipes escaped."""
    text = " ".join(str(value).split())
    return text.replace("|", "\\|") or DASH


def _line(value: Any) -> str:
    """Untrusted text on one line, with backticks neutralised so it cannot open a code span."""
    return " ".join(str(value).split()).replace("`", "'")


def _short(text: str, limit: int) -> str:
    text = _line(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return out


def _walk_refs(obj: Any) -> Iterator[str]:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "source_refs" and isinstance(value, list):
                yield from (v for v in value if isinstance(v, str))
            else:
                yield from _walk_refs(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_refs(value)


def _walk_strings(obj: Any, where: str) -> Iterator[tuple[str, str]]:
    """(nearest id, string) for every string in `obj`."""
    if isinstance(obj, dict):
        where = obj["id"] if isinstance(obj.get("id"), str) else where
        for value in obj.values():
            yield from _walk_strings(value, where)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_strings(value, where)
    elif isinstance(obj, str):
        yield where, obj


def _cited_attestations(tailored: dict, store: list[dict]) -> list[tuple[str, dict | None]]:
    by_id = {a["id"]: a for a in store}
    cited = sorted({r for r in _walk_refs(tailored) if ATT_ID_PATTERN.match(r)})
    return [(att_id, by_id.get(att_id)) for att_id in cited]


def _scope_label(scope: dict) -> str:
    kind = scope.get("kind", "")
    if kind == "role_label":
        label = f"role label '{_line(scope.get('role_label', ''))}'"
    elif kind == "items":
        label = "items " + ", ".join(scope.get("item_ids", []))
    else:
        label = kind
    if kind == "role_label" and scope.get("item_ids"):
        label += " (" + ", ".join(scope["item_ids"]) + ")"
    words = _line(scope.get("description", ""))
    return f"{label}; \"{words}\"" if words else label


def _is_usable(att: dict | None, run_id: str) -> bool:
    if att is None or att.get("scope", {}).get("kind") == "unresolved":
        return False
    if att["status"] == STATUS_ACTIVE:
        return True
    return att["status"] == STATUS_PROPOSED and att.get("run_id") == run_id


# --- sections ---------------------------------------------------------------------------------------------


def final_pdf(run_dir: Path, st: dict) -> str:
    final = state.artifact(st, "final_pdf")
    if final:
        return final["path"]
    if (run_dir / CV_PDF_FILE).is_file():
        return f"{CV_PDF_FILE} (not a final build)"
    return "not built"


def _header(run_dir: Path, st: dict, tailored: dict, jd: dict, ctx: dict) -> list[str]:
    target = tailored.get("target", {})
    title = target.get("title") or jd.get("title", "")
    company = target.get("company") or jd.get("company", "") or UNNAMED_COMPANY
    fit, validation = ctx["fit"], ctx["validation"]
    draft = validation["draft"] if validation else st["options"]["draft"]
    seed = (ctx["plan"] or {}).get("seed_run", "")
    lines = [f"# Match report: {_line(title)} at {_line(company)}", ""]
    if state.stage_index(st["stage"]) < state.stage_index("validated"):
        lines += [DRAFT_REPORT_BANNER.format(stage=st["stage"]), ""]
    lines += [
        f"- Run: `{st['run_slug']}`",
        f"- Date: {st['created_at'][:10]}",
        f"- Template: {target.get('template', st['options']['template'])}",
        f"- Pages: {fit['pages'] if fit else 'not rendered'} (target {target.get('page_target', DASH)})",
        f"- Final PDF: {final_pdf(run_dir, st)}",
        f"- Draft: {'yes' if draft else 'no'}",
        f"- Seed run: {seed or 'none'}",
    ]
    return lines


def _evidence_text(req: dict) -> str:
    parts = [
        f"{ev['ref']} “{_short(ev['quote'], QUOTE_MAX_CHARS)}”" for ev in req.get("evidence", [])[:EVIDENCE_MAX_PER_REQ]
    ]
    hidden = len(req.get("evidence", [])) - EVIDENCE_MAX_PER_REQ
    return "; ".join(parts) + (f"; +{hidden} more" if hidden > 0 else "")


def _pdf_check(validation: dict | None, req_id: str) -> str:
    if validation is None:
        return "not validated"
    row = next((r for r in validation["coverage"]["by_requirement"] if r["req_id"] == req_id), None)
    if row is None:
        return DASH
    found, missing = len(row["found_terms"]), len(row["missing_terms"])
    total = found + missing
    if total == 0:
        return DASH
    word = "yes" if not missing else ("no" if not found else "partial")
    return f"{word} ({found}/{total})"


def _covering_attestations(req: dict, match_req: dict, cited: list[tuple[str, dict | None]], run_id: str) -> list[str]:
    """Cited, usable attestations that license one of the requirement's keywords or are evidence for it."""
    keywords = {k.casefold() for k in req.get("keywords", [])}
    evidence_refs = {ev["ref"] for ev in match_req.get("evidence", [])}
    out = []
    for att_id, att in cited:
        if not _is_usable(att, run_id):
            continue
        if att_id in evidence_refs or keywords & {t.casefold() for t in att.get("terms", [])}:
            out.append(att_id)
    return out


def _coverage(ctx: dict) -> tuple[list[str], list[dict]]:
    """The coverage section plus the remaining gaps `[{req, match, kind}]`."""
    jd, match, validation = ctx["jd"], ctx["match"], ctx["validation"]
    match_by_id = {m["req_id"]: m for m in match["requirements"]}
    rows, gaps = [], []
    tally = {"strong": 0, "confirmed": 0, "partial": 0, "none": 0}
    for req in jd["requirements"]:
        m = match_by_id.get(req["id"], {"strength": "none", "evidence": [], "advice": "", "gap_question": ""})
        covered = _covering_attestations(req, m, ctx["cited"], ctx["run_id"]) if m["strength"] != "strong" else []
        strength = m["strength"] if not covered else f"{m['strength']} → confirmed ({', '.join(covered)})"
        if req["kind"] == "must":
            tally["strong" if m["strength"] == "strong" else "confirmed" if covered else m["strength"]] += 1
        if m["strength"] != "strong" and not covered:
            gaps.append({"req": req, "match": m})
        rows.append([
            f"{req['id']} {_short(req['text'], QUOTE_MAX_CHARS * 2)}", req["kind"], req.get("weight", DASH),
            strength, _evidence_text(m), _pdf_check(validation, req["id"]),
        ])
    lines = ["## Coverage", ""]
    lines += _table(["Requirement", "Kind", "Weight", "Strength", "Evidence", "Found in PDF"], rows)
    total = sum(tally.values())
    if total:
        percent = round(100 * (tally["strong"] + tally["confirmed"]) / total)
        lines += [
            "",
            f"Must-have coverage: {tally['strong'] + tally['confirmed']} of {total} ({percent}%) strong or "
            f"covered by a fact you confirmed; {tally['partial']} partial, {tally['none']} not covered.",
        ]
    else:
        lines += ["", "Must-have coverage: this job description lists no must-have requirements."]
    if validation:
        cov = validation["coverage"]
        lines.append(
            f"Must-have keywords found in the PDF text: {cov['must_keywords_found']} of {cov['must_keywords_total']}"
            + (f"; missing: {', '.join(_line(k) for k in cov['missing'])}." if cov["missing"] else "."),
        )
    return lines, gaps


def _confirmed_facts(ctx: dict) -> list[str]:
    lines = ["## Confirmed facts used", ""]
    if not ctx["cited"]:
        return lines + ["No confirmed facts were needed: every claim comes from your CV text."]
    rows = []
    for att_id, att in ctx["cited"]:
        if att is None:
            rows.append([att_id, "not found in your attestation store", DASH, DASH, DASH, DASH, DASH])
            continue
        rows.append([
            att_id, att["claim"], att["type"], _scope_label(att["scope"]), f"“{_line(att['verbatim'])}”",
            att["status"], ctx["run_slug"] if att.get("run_id") == ctx["run_id"] else att.get("run_id", DASH),
        ])
    lines += _table(["ID", "Claim", "Type", "Scope", "Your words", "Status", "Run"], rows)
    if any(att and att["status"] == STATUS_PROPOSED for _, att in ctx["cited"]):
        lines += ["", "Facts marked `proposed` become reusable (`active`) when you approve the CV."]
    return lines


def _rejected_req_ids(ctx: dict) -> set[str]:
    questions = {q["id"]: q for q in (ctx["questions"] or {}).get("questions", [])}
    rejected: set[str] = set()
    for rnd in (ctx["answers"] or {}).get("rounds", []):
        for item in rnd["items"]:
            if item["action"] == DEFAULT_ACTION_REJECT and item["question_id"] in questions:
                rejected.update(questions[item["question_id"]]["links"]["req_ids"])
    return rejected


def _remaining_gaps(ctx: dict, gaps: list[dict]) -> list[str]:
    lines = ["## Remaining gaps", ""]
    if not gaps:
        return lines + ["No gaps: every requirement is backed by your CV or by a fact you confirmed."]
    rejected = _rejected_req_ids(ctx)
    for gap in gaps:
        req, m = gap["req"], gap["match"]
        advice = _line(m.get("advice", "")) or "No advice recorded."
        note = NOT_CONFIRMED_NOTE + (REJECTED_NOTE if req["id"] in rejected else "")
        lines.append(
            f"- **{req['id']}** ({req['kind']}, {m['strength']}) {_short(req['text'], QUOTE_MAX_CHARS * 2)}. "
            f"{note} How to address it honestly: {advice}",
        )
    return lines


def _source_issues(ctx: dict) -> list[str]:
    lines = ["## Source issues to confirm", ""]
    profile = ctx["profile"]
    if profile is None:
        return lines + ["Profile not available in this run directory, so source issues were not checked."]
    corrected = {
        a["correction"]["item_id"] for a in ctx["store"]
        if a["type"] == "correction" and _is_usable(a, ctx["run_id"])
    }
    open_issues = [i for i in profile.get("source_issues", []) if not corrected & set(i["item_ids"])]
    resolved = len(profile.get("source_issues", [])) - len(open_issues)
    if not open_issues:
        lines.append("No unresolved source issues.")
    for issue in open_issues:
        lines.append(
            f"- **{issue['id']}** ({issue['severity']}, {issue['kind']}) {_line(issue['message'])} "
            f"Items: {', '.join(issue['item_ids']) or DASH}.",
        )
    if resolved:
        lines += ["", f"{resolved} issue(s) already resolved by your corrections."]
    return lines


def _confirm_placeholders(tailored: dict) -> list[tuple[str, str]]:
    found = []
    for where, text in _walk_strings(tailored, "tailored"):
        found += [(where, m.group(0)) for m in CONFIRM_PATTERN.finditer(text)]
    return found


def _items_to_confirm(tailored: dict) -> list[str]:
    lines = ["## Items to confirm", ""]
    placeholders = _confirm_placeholders(tailored)
    open_items = tailored.get("open_items", [])
    if not placeholders and not open_items:
        return lines + ["Nothing to confirm."]
    lines += [f"- `{where}`: {_line(text)}" for where, text in placeholders]
    lines += [
        f"- ({item['kind']}) {_line(item['text'])}" + (f" Items: {', '.join(item['item_ids'])}." if item["item_ids"] else "")
        for item in open_items
    ]
    return lines


def _recruiter_asks(jd: dict) -> list[str]:
    lines = ["## Recruiter asks", ""]
    asks = jd.get("recruiter_asks", [])
    if not asks:
        return lines + ["The job description has no separate recruiter questions."]
    return lines + [RECRUITER_ASKS_NOTE, ""] + [f"- {_line(a)}" for a in asks]


def _talking_points(tailored: dict) -> list[str]:
    lines = ["## Interview talking points", ""]
    points = tailored.get("talking_points", [])
    if not points:
        return lines + ["No talking points were recorded."]
    return lines + [f"- {_line(p['text'])} (refs: {', '.join(p['source_refs']) or DASH})" for p in points]


def _left_out(tailored: dict, fit: dict | None) -> list[str]:
    lines = ["## What was left out", ""]
    omitted = tailored.get("omitted", [])
    dropped = (fit or {}).get("dropped_ids", [])
    if not omitted and not dropped:
        return lines + ["Nothing was left out."]
    lines += [f"- `{o['profile_id']}`: {_line(o['reason'])}" for o in omitted]
    if dropped:
        lines.append(
            f"- Removed to fit {fit['page_target']} page(s) at {fit['density']} density: "
            + ", ".join(f"`{d}`" for d in dropped),
        )
    return lines


def _defaults(st: dict, ctx: dict) -> list[str]:
    lines = ["## Defaults applied", ""]
    questions = (ctx["questions"] or {}).get("questions", [])
    by_id = {q["id"]: q for q in questions}
    skipped = {q["id"] for q in questions if q["status"] in DEFAULT_QUESTION_STATUSES}
    auto_round = False
    for rnd in (ctx["answers"] or {}).get("rounds", []):
        skipped.update(i for i in rnd["unmentioned_question_ids"] if i in by_id)
        skipped.update(i["question_id"] for i in rnd["items"] if i["action"] == "skip" and i["question_id"] in by_id)
        auto_round = auto_round or rnd["channel"] == CHANNEL_AUTO
    notes = []
    if st["options"]["auto"] or auto_round:
        notes.append("Auto mode was on: every question took its default and no new facts were recorded.")
    for qid in sorted(skipped, key=lambda q: int(q.split("-")[1])):
        q = by_id[qid]
        notes.append(f"{qid} ({q['topic']}): {_short(q['prompt'], QUOTE_MAX_CHARS * 2)} Default taken: "
                     f"{_line(q['default']['description']) or _line(q['default']['text']) or DASH}")
    if not notes:
        return lines + ["No defaults were applied."]
    return lines + [f"- {n}" for n in notes]


def _validation(validation: dict | None) -> list[str]:
    lines = ["## Validation", ""]
    if validation is None:
        return lines + ["Not run yet (`validate` has not produced validation.json)."]
    rows = []
    for gate in validation["gates"]:
        first = _short(gate["details"][0], QUOTE_MAX_CHARS * 2) if gate["details"] else DASH
        rows.append([gate["name"], gate["status"], len(gate["violations"]), first])
    lines += _table(["Gate", "Status", "Violations", "Details"], rows)
    lines += ["", f"Overall: {'passed' if validation['passed'] else 'did not pass'} "
                  f"(tailored version {validation['tailored_version']}, draft: {'yes' if validation['draft'] else 'no'})."]
    return lines


def _critique(critique: dict | None, tailored: dict) -> list[str]:
    lines = ["## Critique", ""]
    if critique is None:
        return lines + ["Not run (the hiring-manager critique is opt-in)."]
    lines.append(
        f"Verdict: {critique['verdict']} (model {critique['model']}, tailored version {critique['tailored_version']}).",
    )
    if critique["tailored_version"] != tailored.get("version"):
        lines.append(f"Note: the CV is now version {tailored.get('version')}; this critique may be out of date.")
    lines += [""] + _table(
        ["Criterion", "Score (1-5)", "Why"],
        [[s["criterion"], s["score"], _short(s["justification"], QUOTE_MAX_CHARS * 2)] for s in critique["scores"]],
    )
    issues = sorted(critique["issues"], key=lambda i: SEVERITY_ORDER.index(i["severity"]))[:CRITIQUE_TOP_ISSUES]
    if issues:
        lines += ["", "Top issues (suggestions are proposals; nothing is changed without your approval):"]
        lines += [
            f"- ({i['severity']}) `{_line(i['item_id'])}` {_line(i['message'])} Suggestion: {_line(i['suggestion'])}"
            for i in issues
        ]
    return lines


def _injection(jd: dict) -> list[str]:
    flags = jd.get("injection_flags", [])
    if not flags:
        return []
    return ["## Prompt-injection notice", "", INJECTION_NOTE, ""] + [f"> {_line(f)}" for f in flags]


def token_rows(totals: dict) -> tuple[list[list[Any]], list[Any]]:
    """(stage rows, total row) for the token table from `usage.usage_totals`."""
    rows: list[list[Any]] = []
    for stage, est in totals["packets"].items():
        rows.append([stage, "packet", DASH, f"~{est:,}", DASH, DASH])
    sums = {"input": 0, "cache_read": 0, "output": 0}
    for stage, acc in totals["api"].items():
        rows.append([stage, "api", acc["model"] or DASH, f"{acc['input']:,}", f"{acc['cache_read']:,}", f"{acc['output']:,}"])
        for key in sums:
            sums[key] += acc[key]
    if totals["api"]:
        total = ["total", "api", DASH, f"{sums['input']:,}", f"{sums['cache_read']:,}", f"{sums['output']:,}"]
    else:
        total = ["total", "packet (estimate)", DASH, f"~{totals['total_est']:,}", DASH, DASH]
    return rows, total


def token_summary(run_dir: Path) -> str:
    """One short phrase for command output, for example `~12,400 input tokens (estimated)`."""
    totals = usage.usage_totals(run_dir)
    if not totals:
        return f"tokens: {NOT_RECORDED}"
    _, total = token_rows(totals)
    return f"tokens: {total[3]} input ({'actual' if totals['api'] else 'estimated'}), output {total[5]}"


def _token_usage(run_dir: Path, plan: dict | None) -> list[str]:
    lines = ["## Token usage", ""]
    totals = usage.usage_totals(run_dir)
    if not totals:
        lines.append(f"Token usage: {NOT_RECORDED}.")
    else:
        rows, total = token_rows(totals)
        lines += _table(["Stage", "Kind", "Model", "Est/actual input", "Cache read", "Output"], rows + [total])
    seed = (plan or {}).get("seed_run", "")
    lines += ["", f"Seed run: {seed}" if seed else "Seed run: none."]
    return lines


# --- entry point ------------------------------------------------------------------------------------------


def build_report(run_dir: Path) -> str:
    run_dir = Path(run_dir)
    for name in REQUIRED_ARTIFACTS:
        if not (run_dir / name).is_file():
            raise _artifact_error(name, run_dir)
    st = state.load(run_dir)
    jd = jsonio.load_json(run_dir / "jd.json")
    match = jsonio.load_json(run_dir / "match.json")
    tailored = jsonio.load_json(run_dir / "tailored.json")
    store = profile_store.load_attestations(st["person_slug"]) if st["person_slug"] else []
    ctx: dict = {
        "jd": jd, "match": match, "store": store, "run_id": st["run_id"], "run_slug": st["run_slug"],
        "cited": _cited_attestations(tailored, store),
        **{name: _load_optional(run_dir, name) for name in OPTIONAL_FILES},
    }
    coverage_lines, gaps = _coverage(ctx)
    sections = [
        _header(run_dir, st, tailored, jd, ctx), coverage_lines, _confirmed_facts(ctx), _remaining_gaps(ctx, gaps),
        _source_issues(ctx), _items_to_confirm(tailored), _recruiter_asks(jd), _talking_points(tailored),
        _left_out(tailored, ctx["fit"]), _defaults(st, ctx), _validation(ctx["validation"]),
        _critique(ctx["critique"], tailored), _injection(jd), _token_usage(run_dir, ctx["plan"]),
    ]
    return "\n\n".join("\n".join(s) for s in sections if s) + "\n"
