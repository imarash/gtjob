"""`cvt brief STAGE [RUN]` (stage packets) and `cvt assemble RUN` (tailor-plan.json -> tailored.json)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .. import assemble as assemble_lib
from .. import briefs, jsonio, output, paths, schemas, state
from ..errors import CvtError, ExitCode
from . import checks as check_cmds

PLAN_LEVEL_CODES = (assemble_lib.PLAN_REF, assemble_lib.SKILL_UNSUPPORTED)  # the plan cannot be expanded
PLAN_ARTIFACT, PLAN_FILE, TAILORED_FILE = "tailor_plan", "tailor-plan.json", "tailored.json"
STAGE_ANSWERS, STAGE_MATCHED = "answers_applied", "matched"
COMMAND = "assemble"
CHECK_COMMAND = "check-tailored"
MAX_ASSEMBLE_ERROR_LINES = 10
ASSEMBLE_FAIL_HINT = "list the offending items with: {cvt} brief fix {run}"
JD_CACHE_NEXT = "Run {cvt} jd-check {run}"
GATE_SCHEMA, GATE_PROVENANCE = "schema", "provenance"
ASSEMBLE_SKIPPED = "assemble failed"


# --- brief --------------------------------------------------------------------------------------------------
def _read_reply(args: argparse.Namespace) -> str:
    if args.reply and args.reply_file:
        raise CvtError(ExitCode.USAGE, "E_USAGE", "give --reply or --reply-file, not both",
                       hint="use --reply-file for anything longer than one line")
    if args.reply_file:
        try:
            return Path(args.reply_file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CvtError(ExitCode.INPUT, "E_REPLY_FILE", f"cannot read reply file {args.reply_file}: {exc}",
                           hint="pass a UTF-8 text file, or use --reply TEXT") from None
    return args.reply or ""


def _brief(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    result = briefs.build_packet(
        args.stage, run_dir, reply=_read_reply(args), full=bool(args.full), item=args.item or "",
        visual=bool(args.visual),
    )
    run = run_dir.name
    if result.cache_hit_from:
        next_action = JD_CACHE_NEXT.format(cvt=state.CVT_COMMAND, run=run)
        data = {"stage": args.stage, "cache_hit": True, "cache_from": result.cache_hit_from, "jd_json": "jd.json"}
        human = f"{result.packet}\nnext: {next_action}"
        if getattr(args, "json", False):
            return output.emit(args, run=run, stage=state.load(run_dir)["stage"], data=data,
                               messages=[result.packet], next_action=next_action)
        print(human)
        return int(ExitCode.OK)
    data = {
        "stage": args.stage, "cache_hit": False, "packet": result.packet, "est_tokens": result.est_tokens,
        "budget": result.budget, "path": "" if result.path is None else str(result.path.relative_to(run_dir)),
        "warnings": result.warnings, "attempt": result.attempt,
    }
    if getattr(args, "json", False):
        return output.emit(args, run=run, stage=state.load(run_dir)["stage"], data=data)
    sys.stdout.write(result.packet if result.packet.endswith("\n") else result.packet + "\n")
    return int(ExitCode.OK)


# --- assemble -----------------------------------------------------------------------------------------------
def _store_list(person_slug: str) -> list[dict]:
    return check_cmds._store_attestations(person_slug)


def _gate(name: str, violations: list[dict], skipped: bool = False) -> dict:
    if skipped:
        return check_cmds._gate(name, "skipped", [ASSEMBLE_SKIPPED])
    status = "fail" if violations else "pass"
    return check_cmds._gate(name, status, [f"{len(violations)} violations"] if violations else [], violations)


def _write_failure_validation(run_dir: Path, run: str, draft: bool, violations: list[dict]) -> None:
    plan = [v for v in violations if v["code"] in PLAN_LEVEL_CODES]
    gates = [_gate(GATE_SCHEMA, plan), _gate(GATE_PROVENANCE, [v for v in violations if v not in plan])]
    gates += [check_cmds._gate(n, "skipped", [ASSEMBLE_SKIPPED]) for n in check_cmds.PRE_RENDER_GATES[2:]]
    gates += [check_cmds._gate(n, "skipped", [check_cmds.SKIPPED_DETAIL]) for n in check_cmds.POST_RENDER_GATES]
    check_cmds._write_validation(run_dir, check_cmds._validation(run, 0, draft, gates))


def _render_check_failure(args: argparse.Namespace, err: CvtError, run: str) -> int:
    """At most MAX_ASSEMBLE_ERROR_LINES lines on stderr, ending with the `brief fix` hint."""
    hint = ASSEMBLE_FAIL_HINT.format(cvt=state.CVT_COMMAND, run=run)
    if getattr(args, "json", False):
        return output.fail(args, CvtError(err.code, err.err_id, err.message, hint=hint, violations=err.violations))
    room = MAX_ASSEMBLE_ERROR_LINES - 2
    shown = err.violations if getattr(args, "all", False) or len(err.violations) <= room else err.violations[: room - 1]
    lines = [f"cvt: error[{err.err_id}]: {err.message}"]
    lines += [f"  - {v['item_id']}: {v['message']}" for v in shown]
    if len(shown) < len(err.violations):
        lines.append("  " + output.MORE_LINE.format(n=len(err.violations) - len(shown)))
    lines.append(f"  hint: {hint}")
    print("\n".join(lines), file=sys.stderr)
    return int(err.code)


def _rename_last_event(run_dir: Path, command: str) -> None:
    """The check ran on behalf of `assemble`: make the failure rerun `assemble`, not `check-tailored`."""
    st = state.load(run_dir)
    if st["history"] and st["history"][-1]["event"] == CHECK_COMMAND:
        st["history"][-1]["event"] = command
        state.save(run_dir, st)


def _record_plan(run_dir: Path, st: dict, plan: dict) -> None:
    sha = jsonio.dump_json(plan, run_dir / PLAN_FILE)
    entry = state.artifact(st, PLAN_ARTIFACT)
    changed = entry is None or entry["sha256"] != sha
    if changed or entry["stale"]:
        state.record_artifact(run_dir, st, PLAN_ARTIFACT, PLAN_FILE, cascade=changed)


def _assemble(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    run, draft = run_dir.name, bool(args.draft)
    if st["stage"] == STAGE_MATCHED and st["checkpoints"]["cp1"] == briefs.CP1_SKIPPED:
        state.set_stage(st, STAGE_ANSWERS)
        state.save(run_dir, st)
    state.require_stage(st, STAGE_ANSWERS)
    try:
        plan = check_cmds._load_artifact(run_dir, PLAN_FILE, st)
        schemas.require_valid(plan, "tailor-plan", PLAN_FILE)
        jd = jsonio.load_json(state.require_artifact(run_dir, st, "jd"))
        profile = jsonio.load_json(state.require_artifact(run_dir, st, "profile"))
    except CvtError as err:
        check_cmds._fail(run_dir, st, COMMAND, err)
    _record_plan(run_dir, st, plan)
    tailored, violations = assemble_lib.assemble(plan, profile, _store_list(profile["person_slug"]), jd, st)
    plan_level = [v for v in violations if v["code"] in PLAN_LEVEL_CODES]
    if plan_level:
        _write_failure_validation(run_dir, run, draft, violations)
        err = CvtError(ExitCode.CHECK_FAILED, check_cmds.CHECK_FAILED_ID,
                       f"{PLAN_FILE} assembles with {len(violations)} violations", violations=violations)
        try:
            check_cmds._fail(run_dir, st, COMMAND, err)
        except CvtError as failed:
            return _render_check_failure(args, failed, run)
    jsonio.dump_json(tailored, run_dir / TAILORED_FILE)
    state.save(run_dir, st)
    try:
        code = check_cmds._check_tailored(args)
    except CvtError as err:
        if err.err_id in state.CHECK_FAILED_ERROR_CODES and err.violations:
            _rename_last_event(run_dir, COMMAND)
            return _render_check_failure(args, err, run)
        raise
    done = state.load(run_dir)
    state.add_history(done, COMMAND, f"from {PLAN_FILE}")
    state.save(run_dir, done)
    return code


def register(subparsers) -> None:
    p = subparsers.add_parser("brief", help="print the stage packet: the only context a model needs for one stage")
    p.add_argument("stage", metavar="STAGE", choices=briefs.STAGE_NAMES, help="one of: " + ", ".join(briefs.STAGE_NAMES))
    p.add_argument("run", metavar="RUN", nargs="?", default=None, help="run slug, run directory, or 'latest' (default)")
    p.add_argument("--reply", default="", help="the user's reply text (answer_parse, change_request)")
    p.add_argument("--reply-file", default="", help="read the user's reply from this file")
    p.add_argument("--full", action="store_true", help="append the guide's Details and Examples")
    p.add_argument("--item", default="", metavar="ID", help="print only this item's full text; no stage packet")
    p.add_argument("--visual", action="store_true", help="critic: also list the page PNGs to attach")
    p.set_defaults(func=_brief)
    p = subparsers.add_parser("assemble", help="expand tailor-plan.json into tailored.json and check it")
    p.add_argument("run", metavar="RUN", help="run slug, run directory, or 'latest'")
    p.add_argument("--draft", action="store_true", help="placeholders and proposed attestations warn instead of fail")
    p.set_defaults(func=_assemble)
