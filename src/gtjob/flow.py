"""The stage loop behind `gtjob tailor`, `continue` and `edit` (interfaces.md sections 6, 7 and 12).

`drive` reads `state.json`, acts on the current stage, and repeats until the run is `reported` or waits for a person.
Deterministic steps run `cvtlib` commands in-process (`cvtlib.cli.main`); AI stages go through the injected `Runner`
(WP-21 in production, a fake in tests). Because every step reads state first, a run started in Cursor or Claude Code
resumes here and the reverse.
"""

from __future__ import annotations

import contextlib
import io as stdio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from gtjob import _skill, answers_yaml, interact

_skill.ensure_path()

from cvtlib import answers as answers_lib  # noqa: E402
from cvtlib import jsonio, state, usage  # noqa: E402
from cvtlib import cli as cvt_cli  # noqa: E402
from cvtlib import questions as qmod  # noqa: E402
from cvtlib.errors import CvtError, ExitCode  # noqa: E402

OK, CHECK_FAILED, AWAITING_USER = int(ExitCode.OK), int(ExitCode.CHECK_FAILED), int(ExitCode.AWAITING_USER)
MAX_STEPS = 200  # a run has 13 stages; this only stops a handler that never advances
MAX_ERROR_VIOLATIONS = 5
MAX_PLAN_LINES = 15
QUESTIONS_FILE, EDITS_NEXT = "questions.json", "edits/next.json"
FOLLOWUPS_FILE = "followups.json"
SELECT_ROUND_FILE = "answers.select.json"
REPORT_FILE, FINAL_DIR = "report.md", "final"
STAGE_APPROVED, STAGE_AWAITING_APPROVAL, STAGE_AWAITING_ANSWERS = "approved", "awaiting_approval", "awaiting_answers"
CP2_KEY = "checkpoint2"
USAGE_HEADER = ("stage", "model", "input", "cache read", "output")
USAGE_TOTAL_LABEL = "total"
CONTINUE_HINT = 'gtjob continue {run} --text "..."   (or --answers FILE.yaml)'
RESUME_HINT = "state saved; resume from any host with: gtjob continue {run}"


class Runner(Protocol):
    """The AI half of the pipeline. `run_stage` writes the stage's output file and returns its path.

    Production: `gtjob.cli.ApiRunner` over WP-21 (`stages.run_stage_checked`). Stages that go through a checked run may
    already have advanced `state.stage`; the flow only runs a follow-up check command when the stage did not move.
    """

    def run_stage(self, stage: str, run_dir: Path, *, extra: dict | None = None, interactive: bool = False) -> Path: ...


class _Stop(Exception):
    """Unwinds to `drive` with an exit code (the problem has already been printed)."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class CvtResult:
    code: int
    env: dict
    text: str
    err: str

    @property
    def data(self) -> dict:
        return self.env.get("data", {}) if self.env else {}


@dataclass
class _Ctx:
    run_dir: Path
    runner: Runner
    io: interact.IO
    answers: answers_yaml.AnswersSpec | None
    auto: bool
    reply: str | None
    critic: bool
    critic_visual: bool
    used: set[str] = field(default_factory=set)
    diff_shown: bool = False
    critic_done: bool = False
    help_shown: bool = False

    @property
    def slug(self) -> str:
        return self.run_dir.name


# --- running cvt commands in-process ------------------------------------------------------------------------
def run_cvt(argv: list[str], *, as_json: bool = True) -> CvtResult:
    """Run `cvtlib.cli.main` with output captured. `as_json` parses the envelope; otherwise `text` is the human body."""
    out, err = stdio.StringIO(), stdio.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cvt_cli.main([*argv, "--json"] if as_json else list(argv))
    env: dict = {}
    if as_json:
        lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]
        try:
            env = json.loads(lines[-1]) if lines else {}
        except json.JSONDecodeError:
            env = {}
    return CvtResult(code, env, out.getvalue().rstrip("\n"), err.getvalue().rstrip("\n"))


def format_error(err_id: str, message: str, hint: str = "", violations: list[dict] | None = None) -> str:
    lines = [f"cvt: error[{err_id}]: {message}"]
    if hint:
        lines.append(f"  hint: {hint}")
    shown = (violations or [])[:MAX_ERROR_VIOLATIONS]
    lines += [f"  - {v.get('item_id', '')}: {v.get('message', '')}".rstrip() for v in shown]
    if violations and len(violations) > len(shown):
        lines.append(f"  +{len(violations) - len(shown)} more (cvt validate-artifact / cvt status)")
    return "\n".join(lines)


def _show_failure(ctx: _Ctx, res: CvtResult) -> None:
    if res.env and res.env.get("error", {}).get("id"):
        e = res.env["error"]
        ctx.io.error(format_error(e["id"], e["message"], e.get("hint", ""), res.data.get("violations")))
    elif res.err:
        ctx.io.error(res.err)
    elif res.text:
        ctx.io.error(res.text)


def cvt(ctx: _Ctx, argv: list[str], *, ok: tuple[int, ...] | None = (OK,), as_json: bool = True) -> CvtResult:
    """Run one command. A code outside `ok` prints the error and stops the flow; `ok=None` never stops."""
    res = run_cvt(argv, as_json=as_json)
    if ok is not None and res.code not in ok:
        _show_failure(ctx, res)
        raise _Stop(res.code)
    return res


def _fail_cvt(ctx: _Ctx, err: CvtError) -> None:
    ctx.io.error(format_error(err.err_id, err.message, err.hint, err.violations))


def _stage(ctx: _Ctx) -> str:
    return state.load(ctx.run_dir)["stage"]


def _says(ctx: _Ctx, lines: list[str], cap: int = MAX_PLAN_LINES) -> None:
    shown = lines[:cap]
    if len(lines) > len(shown):
        shown.append(f"+{len(lines) - len(shown)} more")
    ctx.io.say("\n".join(shown))


# --- usage table --------------------------------------------------------------------------------------------
def usage_table(run_dir: Path) -> list[str]:
    """Per-stage API usage (section 14.7): stage, model, input, cache read, output, plus the total. [] when none."""
    totals = usage.usage_totals(run_dir)
    api = totals.get("api", {}) if totals else {}
    if not api:
        return [f"token usage: ~{totals['total_est']:,} tokens estimated, no API calls"] if totals else []
    rows = [
        (stage, a["model"], a["input"], a["cache_read"], a["output"]) for stage, a in api.items()
    ]
    total = ("", "", sum(r[2] for r in rows), sum(r[3] for r in rows), sum(r[4] for r in rows))
    body = [(s, m, f"{i:,}", f"{c:,}", f"{o:,}") for s, m, i, c, o in rows]
    body.append((USAGE_TOTAL_LABEL, "", f"{total[2]:,}", f"{total[3]:,}", f"{total[4]:,}"))
    table = [USAGE_HEADER, *body]
    widths = [max(len(r[i]) for r in table) for i in range(len(USAGE_HEADER))]
    out = []
    for n, row in enumerate(table):
        out.append("  ".join(cell.ljust(widths[i]) if i < 2 else cell.rjust(widths[i]) for i, cell in enumerate(row)).rstrip())
        if n == 0:
            out.append("  ".join("-" * w for w in widths))
    return out


# --- stage handlers -----------------------------------------------------------------------------------------
def _h_initialized(ctx: _Ctx, st: dict) -> int | None:
    ctx.io.say("ingest: reading the CV and JD")
    cvt(ctx, ["ingest", ctx.slug])
    return None


def _h_ingested(ctx: _Ctx, st: dict) -> int | None:
    hit = cvt(ctx, ["profile-cache", ctx.slug, "--lookup"]).data.get("hit")
    if hit:
        ctx.io.say("profile: reused the stored profile for this CV (no AI call)")
        return None
    ctx.io.say("profile: reading the CV")
    ctx.runner.run_stage("profile", ctx.run_dir, interactive=ctx.io.interactive)
    if _stage(ctx) == "ingested":
        cvt(ctx, ["profile-build", ctx.slug])
    cvt(ctx, ["profile-cache", ctx.slug, "--store"], ok=None)  # reuse for the next JD; failure is not fatal
    return None


def _h_profiled(ctx: _Ctx, st: dict) -> int | None:
    ctx.io.say("jd: analysing the job description")
    from cvtlib import briefs  # noqa: PLC0415 - heavy import, only needed here

    if not (ctx.run_dir / "jd.json").is_file() and briefs.find_cached_jd(ctx.run_dir, st):
        ctx.io.say("jd: same JD analysed in an earlier run (no AI call)")
        cvt(ctx, ["brief", "jd", ctx.slug])  # copies the cached jd.json
    else:
        ctx.runner.run_stage("jd", ctx.run_dir, interactive=ctx.io.interactive)
    if _stage(ctx) == "profiled":
        cvt(ctx, ["jd-check", ctx.slug])
    return None


def _h_jd_analyzed(ctx: _Ctx, st: dict) -> int | None:
    ctx.io.say("match: comparing the CV with the requirements")
    ctx.runner.run_stage("match", ctx.run_dir, interactive=ctx.io.interactive)
    if _stage(ctx) == "jd_analyzed":
        cvt(ctx, ["match-check", ctx.slug])
    return None


def _h_matched(ctx: _Ctx, st: dict) -> int | None:
    ctx.io.say("questions: preparing checkpoint 1")
    ctx.runner.run_stage("questions", ctx.run_dir, interactive=ctx.io.interactive)
    if _stage(ctx) == "matched":
        cvt(ctx, ["questions", ctx.slug], ok=(OK, AWAITING_USER))
    return None


def _pending_cp1(run_dir: Path) -> tuple[dict, list[dict]]:
    questions = jsonio.load_json(run_dir / QUESTIONS_FILE)
    return questions, [q for q in qmod.pending_questions(questions) if q["checkpoint"] == 1]


def _pause_cp1(ctx: _Ctx, questions: dict) -> int:
    ctx.io.say(qmod.render_chat(questions))
    ctx.io.say(f"{RESUME_HINT.format(run=ctx.slug)}\nanswer with: {CONTINUE_HINT.format(run=ctx.slug)}")
    return AWAITING_USER


def _h_awaiting_answers(ctx: _Ctx, st: dict) -> int | None:
    if st["options"]["auto"]:
        cvt(ctx, ["answers-apply", ctx.slug, "--auto"], ok=(OK, AWAITING_USER))
        return _stuck_cp1(ctx) if _stage(ctx) == STAGE_AWAITING_ANSWERS else None
    questions, pending = _pending_cp1(ctx.run_dir)
    if not pending:
        return _stuck_cp1(ctx)
    kind = st["pending"]["kind"] if st["pending"]["kind"] == "followups" else "checkpoint1"
    key = answers_yaml.KEY_FOLLOWUPS if kind == "followups" else answers_yaml.KEY_CP1
    if ctx.reply is not None:
        text, ctx.reply = ctx.reply, None
        return _apply_cp1(ctx, before={q["id"] for q in pending}, texts_reply=text, confirm=False)
    if ctx.answers is not None and key not in ctx.used:
        ctx.used.add(key)
        section = ctx.answers.section(key)
        if section is not None:
            answers_yaml.check_question_ids(section, {q["id"] for q in questions["questions"]})
            return _apply_cp1(
                ctx, before={q["id"] for q in pending}, choices=section.choices, texts_reply=answers_yaml.free_text_reply(section),
                default_rest=section.default_rest, confirm=False,
            )
    if ctx.io.interactive:
        given = interact.prompt_questions(ctx.io, pending)
        if given is None:
            ctx.io.say(RESUME_HINT.format(run=ctx.slug))
            return AWAITING_USER
        reply = "\n".join(f"{qid}: {text}" for qid, text in given.texts.items())
        return _apply_cp1(
            ctx, before={q["id"] for q in pending}, choices=given.choices, texts_reply=reply,
            default_rest=given.default_rest, confirm=True,
        )
    return _pause_cp1(ctx, questions)


def _stuck_cp1(ctx: _Ctx) -> int:
    st = state.load(ctx.run_dir)
    ctx.io.error(format_error(
        "E_STATE", f"checkpoint 1 is waiting but no question can be answered here ({st['pending']['message']})",
        hint=st["next_action"],
    ))
    return AWAITING_USER


def _apply_cp1(
    ctx: _Ctx, *, before: set[str], choices: dict[str, list[str]] | None = None, texts_reply: str = "",
    default_rest: bool = False, confirm: bool,
) -> int | None:
    """One reply to checkpoint 1: free text through `answer_parse`, choices through `answers.select_round`.

    `before` is what was pending when the reply was given: `default_rest` defaults only those questions, so a
    follow-up that the free-text round just created is still asked (and answered by the `followups` section).
    """
    if texts_reply and _apply_text_round(ctx, texts_reply, confirm=confirm):
        return None  # interactive only: the round was not applied, back to the prompt
    if _stage(ctx) != STAGE_AWAITING_ANSWERS:
        return None
    questions, pending = _pending_cp1(ctx.run_dir)
    pending_ids = {q["id"] for q in pending}
    picked = dict(choices or {})
    defaulted = sorted((pending_ids & before) - set(picked), key=_question_number) if default_rest else []
    if not picked and not defaulted:
        return None
    round_obj = answers_lib.select_round(questions, picked, default_rest=False, now=jsonio.now_iso())
    round_obj["unmentioned_question_ids"] = defaulted
    path = ctx.run_dir / SELECT_ROUND_FILE
    jsonio.dump_json(round_obj, path)
    cvt(ctx, ["answers-apply", ctx.slug, "--round", str(path), "--commit"], ok=(OK, AWAITING_USER))
    return None


def _question_number(qid: str) -> int:
    return int(qid.rsplit("-", 1)[-1])


def _apply_text_round(ctx: _Ctx, reply: str, *, confirm: bool) -> bool:
    """answer_parse -> dry run (shown) -> follow-up questions -> commit. True when the round was not applied."""
    path = ctx.runner.run_stage("answer_parse", ctx.run_dir, extra={"reply": reply}, interactive=ctx.io.interactive)
    round_obj = jsonio.load_json(path)
    try:
        plan = answers_lib.plan_round(ctx.run_dir, round_obj)
    except CvtError as err:
        _fail_cvt(ctx, err)
        if ctx.io.interactive:
            return True
        raise _Stop(int(err.code)) from None
    _says(ctx, answers_lib.plan_table(plan))
    if confirm and not ctx.io.confirm("Apply this?"):
        ctx.io.say("discarded; answer again")
        return True
    if plan["skeletons"]:
        followups = ctx.run_dir / FOLLOWUPS_FILE
        jsonio.dump_json({"questions": plan["skeletons"]}, followups)
        cvt(ctx, ["questions", ctx.slug, "--add", str(followups)], ok=(OK, AWAITING_USER))
    cvt(ctx, ["answers-apply", ctx.slug, "--round", str(path), "--commit"], ok=(OK, AWAITING_USER))
    return False


def _h_answers_applied(ctx: _Ctx, st: dict) -> int | None:
    ctx.io.say("tailor: planning the CV")
    ctx.runner.run_stage("tailor", ctx.run_dir, interactive=ctx.io.interactive)
    if _stage(ctx) == "answers_applied":
        cvt(ctx, ["assemble", ctx.slug, *(["--draft"] if st["options"]["draft"] else [])])
    return None


def _show_diff(ctx: _Ctx, *, full: bool = False) -> None:
    res = cvt(ctx, ["diff", ctx.slug, *(["--full"] if full else [])], as_json=False)
    ctx.io.say(res.text)
    ctx.diff_shown = True


def _h_tailored(ctx: _Ctx, st: dict) -> int | None:
    res = cvt(ctx, ["diff", ctx.slug], as_json=False)
    if _stage(ctx) == STAGE_AWAITING_APPROVAL:
        ctx.io.say(res.text)
        ctx.diff_shown = True
    else:
        ctx.io.say("auto mode: every item marked review=auto; run approved")
    return None


def _apply_change(ctx: _Ctx, text: str, *, strict: bool) -> bool:
    """change_request -> apply-edits. True when applied. Violations are shown; `strict` stops the flow on them."""
    path = ctx.runner.run_stage("change_request", ctx.run_dir, extra={"reply": text}, interactive=ctx.io.interactive)
    return _apply_edits_file(ctx, path, strict=strict)


def _apply_edits_file(ctx: _Ctx, path: Path, *, strict: bool) -> bool:
    res = run_cvt(["apply-edits", ctx.slug, str(path)], as_json=False)
    if res.code == OK:
        ctx.io.say(res.text)
        ctx.diff_shown = True
        return True
    _show_failure(ctx, res)
    if strict or res.code != CHECK_FAILED:
        raise _Stop(res.code)
    ctx.io.say("nothing changed; rephrase the request, or approve with a")
    return False


def _write_edit(ctx: _Ctx, op: dict, raw_text: str) -> Path:
    path = ctx.run_dir / EDITS_NEXT
    path.parent.mkdir(parents=True, exist_ok=True)
    batch = {"schema_version": "1", "run_id": state.load(ctx.run_dir)["run_id"], "source": "cli",
             "raw_text": raw_text, "ops": [op]}
    jsonio.dump_json(batch, path)
    return path


def _op(kind: str, target: str, value: str = "", refs: list[str] | None = None) -> dict:
    return {"op": kind, "target_id": target, "field": "", "value": value, "source_refs": refs or [], "items": []}


def _item_by_number(ctx: _Ctx, n: int) -> dict | None:
    items = cvt(ctx, ["diff", ctx.slug, "--full"]).data.get("items", [])
    return next((i for i in items if i.get("n") == n), None)


def _approve_all(ctx: _Ctx) -> None:
    if _stage(ctx) != STAGE_APPROVED:
        cvt(ctx, ["approve", ctx.slug, "--all"])
    ctx.io.say("approved")


def _pause_cp2(ctx: _Ctx) -> int:
    if not ctx.diff_shown:
        _show_diff(ctx)
    ctx.io.say(f"{RESUME_HINT.format(run=ctx.slug)}\nrequest changes with: {CONTINUE_HINT.format(run=ctx.slug)}\n"
               "approve with an --answers file containing: checkpoint2: approve_all")
    return AWAITING_USER


def _review_once(ctx: _Ctx) -> int | None:
    cmd = interact.ask_review(ctx.io)
    if cmd is None or cmd.kind == "quit":
        ctx.io.say(RESUME_HINT.format(run=ctx.slug))
        return AWAITING_USER
    if cmd.kind == "help":
        ctx.io.say(interact.CP2_HELP)
    elif cmd.kind == "bad":
        ctx.io.error(f"  {cmd.text}")
    elif cmd.kind == "approve":
        _approve_all(ctx)
    elif cmd.kind == "full":
        _show_diff(ctx, full=True)
    elif cmd.kind == "change":
        _apply_change(ctx, cmd.text, strict=False)
    else:
        item = _item_by_number(ctx, cmd.n)
        if item is None:
            ctx.io.error(f"  no item {cmd.n} in the diff; d shows every item")
        elif cmd.kind == "reject":
            _apply_edits_file(ctx, _write_edit(ctx, _op("reject", item["id"]), f"r {cmd.n}"), strict=False)
        else:
            op = _op("replace_text", item["id"], cmd.text, list(item.get("source_refs", [])))
            _apply_edits_file(ctx, _write_edit(ctx, op, f"e {cmd.n} {cmd.text}"), strict=False)
    return None


def _h_awaiting_approval(ctx: _Ctx, st: dict) -> int | None:
    if not ctx.diff_shown:
        _show_diff(ctx)
    if ctx.reply is not None:
        text, ctx.reply = ctx.reply, None
        _apply_change(ctx, text, strict=True)
        return None
    if ctx.answers is not None and CP2_KEY not in ctx.used:
        ctx.used.add(CP2_KEY)
        cp2 = ctx.answers.checkpoint2
        if cp2 is not None:
            for instruction in cp2.instructions:
                _apply_change(ctx, instruction, strict=True)
            _approve_all(ctx)
            return None
    if ctx.io.interactive:
        if not ctx.help_shown:
            ctx.help_shown = True
            ctx.io.say(interact.CP2_HELP)
        return _review_once(ctx)
    return _pause_cp2(ctx)


def _h_approved(ctx: _Ctx, st: dict) -> int | None:
    ctx.io.say("fit: rendering to the page target")
    res = cvt(ctx, ["fit", ctx.slug, *(["--png"] if ctx.critic_visual else [])])
    d = res.data
    ctx.io.say(f"fit: {d.get('pages')}/{d.get('page_target')} page(s), {d.get('density')}")
    return None


def _h_rendered(ctx: _Ctx, st: dict) -> int | None:
    res = cvt(ctx, ["validate", ctx.slug])
    gates = res.data.get("gates", {})
    flagged = ", ".join(f"{n} {s}" for n, s in gates.items() if s != "pass")
    ctx.io.say(f"validate: {flagged}" if flagged else "validate: all gates pass")
    return None


def _h_validated(ctx: _Ctx, st: dict) -> int | None:
    if ctx.critic and not ctx.critic_done:
        ctx.critic_done = True
        ctx.io.say("critic: reviewing as a hiring manager")
        path = ctx.runner.run_stage("critic", ctx.run_dir, interactive=ctx.io.interactive)
        cvt(ctx, ["critique-save", ctx.slug, str(path)])
    cvt(ctx, ["report", ctx.slug])
    return None


def _h_reported(ctx: _Ctx, st: dict) -> int | None:
    finals = sorted((ctx.run_dir / FINAL_DIR).glob("*.pdf"))
    for pdf in finals:
        ctx.io.say(f"cv:     {pdf}")
    ctx.io.say(f"report: {ctx.run_dir / REPORT_FILE}")
    return OK


HANDLERS = {
    "initialized": _h_initialized,
    "ingested": _h_ingested,
    "profiled": _h_profiled,
    "jd_analyzed": _h_jd_analyzed,
    "matched": _h_matched,
    "awaiting_answers": _h_awaiting_answers,
    "answers_applied": _h_answers_applied,
    "tailored": _h_tailored,
    "awaiting_approval": _h_awaiting_approval,
    "approved": _h_approved,
    "rendered": _h_rendered,
    "validated": _h_validated,
    "reported": _h_reported,
}
POST_APPROVAL_STAGES = ("approved", "rendered", "validated", "reported")


def _prepare(ctx: _Ctx) -> None:
    """Make `auto` stick in state, and turn a reply sent after approval into a change request (re-enter checkpoint 2)."""
    st = state.load(ctx.run_dir)
    if ctx.auto and not st["options"]["auto"]:
        st["options"]["auto"] = True
        state.add_history(st, "gtjob", "auto")
        state.save(ctx.run_dir, st)
    if ctx.reply is not None and st["stage"] in POST_APPROVAL_STAGES:
        text, ctx.reply = ctx.reply, None
        _apply_change(ctx, text, strict=True)


def _loop(ctx: _Ctx) -> int:
    _prepare(ctx)
    for _ in range(MAX_STEPS):
        st = state.load(ctx.run_dir)
        code = HANDLERS[st["stage"]](ctx, st)
        if code is not None:
            return code
    raise CvtError(ExitCode.INTERNAL, "E_FLOW_LOOP", f"the run did not advance after {MAX_STEPS} steps",
                   hint=f"run: gtjob status {ctx.slug}")


def drive(
    run_dir: Path, *, runner: Runner, io: interact.IO, answers: answers_yaml.AnswersSpec | None = None,
    auto: bool = False, reply: str | None = None, critic: bool = False, critic_visual: bool = False,
) -> int:
    """Drive a run to `reported` or to the next user wait. Returns an exit code (0, or 6 at a checkpoint)."""
    ctx = _Ctx(Path(run_dir), runner, io, answers, auto, reply, critic or critic_visual, critic_visual)
    try:
        code = _loop(ctx)
    except _Stop as stop:
        code = stop.code
    except CvtError as err:
        _fail_cvt(ctx, err)
        code = int(err.code)
    if ctx.reply is not None and code == OK:
        io.say("note: --text was not used because the run was not at a checkpoint")
    table = usage_table(ctx.run_dir)
    if table:
        io.say("\n".join(table))
    return code

