"""`cvt questions` and `cvt answers-apply`: the deterministic half of checkpoint 1 (interfaces.md section 7)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .. import answers, jsonio, output, paths, schemas, state
from .. import attestations as attmod
from .. import questions as qmod
from ..errors import CvtError, ExitCode

QUESTIONS_FILE, JD_FILE = "questions.json", "jd.json"
ANSWERS_FILE = "answers.json"
STAGE_MATCHED, STAGE_AWAITING, STAGE_APPLIED = "matched", "awaiting_answers", "answers_applied"
CP1_PENDING, CP1_DONE, CP1_SKIPPED = "pending", "done", "skipped"
FORMATS = ("chat", "host", "json")
HOSTS = ("cursor", "claude_code")
DEFAULT_FORMAT, FALLBACK_HOST = "chat", "cursor"
CHECK_FAILED_ID = "E_CHECK_FAILED"
FIX_HINT = "patch only the listed questions in questions.json, then rerun: cvt questions {run}"
SELECT_RE = re.compile(r"^q-[0-9]+$")
SKIP_WORD = answers.SKIP_WORD
NO_QUESTIONS_LINE = "ok: no questions to ask ({n} suppressed by earlier answers)"
PENDING_MESSAGE = "{n} question(s) await an answer"
AUTO_LINE = "ok: auto mode defaulted {n} question(s); nothing was attested"
SOURCES = "--round FILE, --select q-N=CHOICE, or --auto"


# --- shared helpers ----------------------------------------------------------------------------------------
def _fail(run_dir: Path, st: dict, command: str, err: CvtError) -> None:
    st["status"] = "failed"
    state.add_error(st, err.err_id, err.message)
    state.add_history(st, command, f"failed: {err.err_id}")
    state.save(run_dir, st)
    raise err


def _load_json_file(path: Path, what: str) -> object:
    if not path.is_file():
        raise CvtError(ExitCode.INPUT, "E_FILE_MISSING", f"{what} not found: {path}", hint=f"check the path to {what}")
    return jsonio.load_json(path)


def _host(args: argparse.Namespace) -> str:
    if args.host:
        return args.host
    return state.current_host() if state.current_host() in HOSTS else FALLBACK_HOST


def _usage(message: str, hint: str) -> CvtError:
    return CvtError(ExitCode.USAGE, "E_USAGE", message, hint=hint)


# --- questions ---------------------------------------------------------------------------------------------
def _new_questions(path: Path) -> list[dict]:
    data = _load_json_file(path, "follow-up questions file")
    rows = data["questions"] if isinstance(data, dict) and "questions" in data else data
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise CvtError(
            ExitCode.CHECK_FAILED, "E_QUESTION_FIELDS", f"{path.name} must be a list of questions (or {{\"questions\": [...]}})",
            hint="write follow-ups as questions.schema.json#/$defs/question objects; ids are reassigned",
        )
    return rows


def _render(questions: dict, fmt: str, host: str) -> object:
    if fmt == "chat":
        return qmod.render_chat(questions)
    if fmt == "host":
        return qmod.render_host(questions, host)
    return {**questions, "questions": qmod.pending_questions(questions)}


def _suppressed_report(before: dict, entries: list[dict]) -> list[dict]:
    earlier = [
        {"question_id": q["id"], "choice_id": "", "reason": q["suppressed_reason"], "question_suppressed": True}
        for q in before["questions"] if q["status"] == qmod.STATUS_SUPPRESSED
    ]
    return earlier + entries


def _questions(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    state.require_stage(st, STAGE_MATCHED)
    command, run = "questions", run_dir.name
    try:
        path = run_dir / QUESTIONS_FILE
        if not path.is_file():
            raise CvtError(ExitCode.STATE, "E_ARTIFACT_MISSING", f"{QUESTIONS_FILE} not found in {run}", hint=st["next_action"])
        questions = jsonio.load_json(path)
        schemas.require_valid(questions, "questions", QUESTIONS_FILE)
        if args.add:
            questions = qmod.add(questions, _new_questions(Path(args.add)))
        profile = jsonio.load_json(state.require_artifact(run_dir, st, "profile"))
        jd_entry = state.artifact(st, "jd")
        jd = jsonio.load_json(run_dir / jd_entry["path"]) if jd_entry and (run_dir / jd_entry["path"]).is_file() else None
        store = attmod.load_store(profile["person_slug"])
        checked, violations = qmod.check(questions, store["attestations"], jd=jd, profile=profile)
        if violations:
            raise CvtError(
                ExitCode.CHECK_FAILED, CHECK_FAILED_ID, f"{QUESTIONS_FILE} has {len(violations)} violations",
                hint=FIX_HINT.format(run=run), violations=violations,
            )
        _, removed = qmod.suppress(questions, store["attestations"], jd=jd)
        jsonio.dump_json(checked, path)
        state.record_artifact(run_dir, st, "questions", QUESTIONS_FILE, cascade=False)
    except CvtError as err:
        _fail(run_dir, st, command, err)
    suppressed = _suppressed_report(questions, removed)
    pending = [q for q in qmod.pending_questions(checked) if q["checkpoint"] == 1]
    base = {"pending": [q["id"] for q in pending], "suppressed": suppressed}

    if pending and st["options"]["auto"]:
        state.add_history(st, command, "auto")
        state.save(run_dir, st)
        result = answers.commit_round(run_dir, answers.auto_round(run_dir))
        after = state.load(run_dir)
        data = {**base, "pending": [], "auto_defaulted": len(result["question_changes"])}
        return output.emit(args, run=run, stage=after["stage"], data=data,
                           human=AUTO_LINE.format(n=data["auto_defaulted"]), next_action=after["next_action"])

    if pending:
        kind = answers.pending_kind(pending)
        message = PENDING_MESSAGE.format(n=len(pending))
        state.set_stage(st, STAGE_AWAITING, "awaiting_user",
                        pending={"kind": kind, "question_ids": base["pending"], "message": message})
        st["checkpoints"]["cp1"] = CP1_PENDING
        state.add_history(st, command, f"pending={len(pending)} suppressed={len(suppressed)}")
        state.save(run_dir, st)
        render = _render(checked, args.format, _host(args))
        data = {**base, "format": args.format, "render": render}
        if not getattr(args, "json", False) and args.format != DEFAULT_FORMAT:
            print(json.dumps(render, ensure_ascii=False, separators=(",", ":")))
            return int(ExitCode.AWAITING_USER)
        human = render if isinstance(render, str) else json.dumps(render, ensure_ascii=False, separators=(",", ":"))
        return output.emit(args, run=run, stage=st["stage"], data=data, human=human, exit_code=int(ExitCode.AWAITING_USER))

    if state.stage_index(st["stage"]) <= state.stage_index(STAGE_AWAITING):
        state.set_stage(st, STAGE_APPLIED)
        st["checkpoints"]["cp1"] = CP1_DONE if (run_dir / ANSWERS_FILE).is_file() else CP1_SKIPPED
    state.add_history(st, command, f"none pending; suppressed={len(suppressed)}")
    state.save(run_dir, st)
    data = {**base, "format": args.format}
    if not getattr(args, "json", False) and args.format != DEFAULT_FORMAT:
        print(json.dumps(_render(checked, args.format, _host(args)), ensure_ascii=False, separators=(",", ":")))
        return int(ExitCode.OK)
    return output.emit(args, run=run, stage=st["stage"], data=data,
                       human=NO_QUESTIONS_LINE.format(n=len(suppressed)), next_action=st["next_action"])


# --- answers-apply -----------------------------------------------------------------------------------------
def _parse_selects(raw: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for text in raw:
        qid, sep, rhs = text.partition("=")
        qid, rhs = qid.strip(), rhs.strip()
        if not sep or not SELECT_RE.match(qid) or not rhs:
            raise _usage(f"bad --select '{text}'", "use --select q-N=CHOICE[,CHOICE] or --select q-N=skip")
        if qid in out:
            raise _usage(f"{qid} is selected twice", "pass --select once per question")
        out[qid] = [] if rhs.casefold() == SKIP_WORD else [t.strip() for t in rhs.split(",") if t.strip()]
    return out


def _cap_plan(args: argparse.Namespace, plan: dict) -> dict:
    shown, hidden = output.cap_list(args, plan["attestations"])
    out = {**plan, "attestations": shown}
    if hidden:
        out["attestations_more"] = hidden
    return out


def _answers_apply(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    run, command = run_dir.name, "answers-apply"
    sources = [bool(args.round), bool(args.select), bool(args.auto)]
    if sum(sources) != 1:
        raise _usage("choose exactly one answer source", f"pass one of: {SOURCES}")
    if args.default_rest and not args.select:
        raise _usage("--default-rest only works with --select", "add --select q-N=CHOICE, or drop --default-rest")
    if args.dry_run and args.commit:
        raise _usage("--dry-run and --commit are exclusive", "run --dry-run first, then --commit")
    if not args.auto and not (args.dry_run or args.commit):
        raise _usage("say whether to preview or apply", "add --dry-run to preview or --commit to apply")
    state.require_stage(st, STAGE_MATCHED if args.auto else STAGE_AWAITING)
    commit = args.commit or (args.auto and not args.dry_run)

    if args.round:
        round_obj = _load_json_file(Path(args.round), "answers round file")
    elif args.select:
        questions = jsonio.load_json(run_dir / QUESTIONS_FILE) if (run_dir / QUESTIONS_FILE).is_file() else None
        if questions is None:
            raise CvtError(ExitCode.STATE, "E_ARTIFACT_MISSING", f"{QUESTIONS_FILE} not found in {run}", hint=st["next_action"])
        schemas.require_valid(questions, "questions", QUESTIONS_FILE)
        round_obj = answers.select_round(questions, _parse_selects(args.select),
                                         default_rest=args.default_rest, now=jsonio.now_iso())
    else:
        round_obj = answers.auto_round(run_dir)

    if not commit:
        plan = answers.plan_round(run_dir, round_obj)
        return output.emit(args, run=run, stage=st["stage"], data={"plan": _cap_plan(args, plan), "dry_run": True},
                           human="\n".join(answers.plan_table(plan)))
    try:
        result = answers.commit_round(run_dir, round_obj)
    except CvtError as err:
        if err.err_id == answers.FAILED_ID:
            _fail(run_dir, st, command, err)
        raise
    after = state.load(run_dir)
    lines = [f"committed round {result['round']}: created {', '.join(result['created']) or 'no attestations'}"]
    if result["scope_updates"]:
        lines.append(f"scope updated: {', '.join(result['scope_updates'])}")
    if result["pending"]:
        lines.append(f"pending: {', '.join(result['pending'])}")
    if result["unresolved"]:
        lines.append(f"unresolved scope: {', '.join(result['unresolved'])}")
    if result["instructions"]:
        lines.append(f"instructions kept for tailoring: {len(result['instructions'])}")
    code = ExitCode.AWAITING_USER if result["awaiting"] else ExitCode.OK
    return output.emit(args, run=run, stage=after["stage"], data=result, human="\n".join(lines),
                       next_action=after["next_action"], exit_code=int(code))


def register(subparsers) -> None:
    p = subparsers.add_parser("questions", help="validate, suppress and render checkpoint-1 questions")
    p.add_argument("run", metavar="RUN", help="run slug, run directory, or 'latest'")
    p.add_argument("--format", choices=FORMATS, default=DEFAULT_FORMAT, help="chat (default), host, or json")
    p.add_argument("--host", choices=HOSTS, default=None, help="host question-tool shape for --format host")
    p.add_argument("--add", metavar="FILE", default="", help="append follow-up questions (ids are reassigned)")
    p.set_defaults(func=_questions)
    p = subparsers.add_parser("answers-apply", help="preview or apply one round of user answers")
    p.add_argument("run", metavar="RUN", help="run slug, run directory, or 'latest'")
    p.add_argument("--round", metavar="FILE", default="", help="answers.round.json written from the answer_parse packet")
    p.add_argument("--select", metavar="q-N=CHOICE[,CHOICE]", action="append", default=[],
                   help="choice answers from a host question tool; q-N=skip skips (repeatable)")
    p.add_argument("--default-rest", action="store_true", help="with --select: every other pending question takes its default")
    p.add_argument("--auto", action="store_true", help="default every pending question (no attestations)")
    p.add_argument("--dry-run", action="store_true", help="validate and print the mapping; write nothing")
    p.add_argument("--commit", action="store_true", help="apply the round")
    p.set_defaults(func=_answers_apply)
