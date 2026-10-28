"""`gtjob`: the terminal front end of the tailoring-cvs skill (interfaces.md section 12).

`tailor`, `continue` and `edit` drive `gtjob.flow`; `status`, `render`, `profile`, `polish` and `package-skill`
delegate to the deterministic commands. `main()` marks the host as `cli` so state history shows who wrote what.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import importlib.util
import os
import sys
from pathlib import Path

from gtjob import _skill, answers_yaml, flow, interact
from gtjob.llm import FAKE_LLM_ENV

_skill.ensure_path()

from cvtlib import cli as cvt_cli  # noqa: E402
from cvtlib import paths, state  # noqa: E402
from cvtlib.commands.run import PAGE_TARGETS, PAPERS, TEMPLATES  # noqa: E402
from cvtlib.errors import CvtError, ExitCode  # noqa: E402

PROG = "gtjob"
HOST_ENV, HOST_CLI = "GTJOB_HOST", "cli"
EXIT_INTERRUPTED = 130  # shell convention: 128 + SIGINT
DEFAULT_TEMPLATE, DEFAULT_PAPER, DEFAULT_PAGE_TARGET = "modern", "us-letter", 2
UNCHECKED_STAGES = ("questions", "change_request")  # the flow runs their check command itself (see ApiRunner)
WEB_MODULE = "gtjob.web.serve"
STAGE_TAILORED = "tailored"
DOCX_SUFFIX = ".docx"
PROFILE_ACTIONS = ("list", "show", "revoke", "activate")
JD_KINDS = {"jd": "file", "jd_text": "text", "jd_url": "url"}
JD_TEXT_REF = "text"


class ApiRunner:
    """The production `flow.Runner`: WP-21's stage functions over the Anthropic API.

    The API key is checked on the first AI call, so a run that needs no AI (a cached profile and JD, `render`) works
    without one. `questions` and `change_request` use the unchecked `run_stage` because the flow runs their check
    commands itself (`questions` exits 6 by design; `apply-edits` is not idempotent).
    """

    def __init__(self, *, cli_models: list[str] | None = None, no_cache: bool = False, critic_visual: bool = False) -> None:
        from gtjob import config as config_mod  # noqa: PLC0415

        self._config = config_mod.load_config(cli_models=cli_models or (), no_cache=no_cache, visual=critic_visual)
        self._client = None

    def _get_client(self):
        if self._client is None:
            from gtjob import llm  # noqa: PLC0415

            # AnthropicClient raises CvtError(MISSING_DEPENDENCY, E_API_KEY) without a key; GTJOB_FAKE_LLM replays canned files
            self._client = llm.default_client()
        return self._client

    def run_stage(self, stage: str, run_dir: Path, *, extra: dict | None = None, interactive: bool = False) -> Path:
        client = self._get_client()
        from gtjob import stages  # noqa: PLC0415

        config = dataclasses.replace(self._config, interactive=interactive)
        fake_dir = os.environ.get(FAKE_LLM_ENV)
        if fake_dir:  # keep canned answers out of the real response cache
            config = dataclasses.replace(config, root=Path(fake_dir))
        run = stages.run_stage if stage in UNCHECKED_STAGES else stages.run_stage_checked
        return run(stage, run_dir, client=client, config=config, extra=extra)


# --- parser -------------------------------------------------------------------------------------------------
def _add_json(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="print the cvt JSON envelope instead of text")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROG, description="Tailor a CV to a job description without inventing facts.")
    sub = parser.add_subparsers(dest="command", metavar="<command>", required=True)

    t = sub.add_parser("tailor", help="full pipeline with prompts at both checkpoints")
    t.add_argument("--cv", required=True, metavar="PATH", help="CV file (PDF, Markdown or text)")
    jd = t.add_mutually_exclusive_group(required=True)
    jd.add_argument("--jd", metavar="PATH", help="job description file")
    jd.add_argument("--jd-text", metavar="TEXT", help="job description text")
    jd.add_argument("--jd-url", metavar="URL", help="job posting URL")
    t.add_argument("--template", choices=TEMPLATES, default=DEFAULT_TEMPLATE)
    t.add_argument("--auto", action="store_true", help="default every question and approve; nothing is attested")
    t.add_argument("--answers", metavar="FILE.yaml", help="non-interactive answers for both checkpoints")
    t.add_argument("--draft", action="store_true", help="allow unresolved placeholders (marked DRAFT)")
    t.add_argument("--critic", action="store_true", help="hiring-manager critique (Opus, text only)")
    t.add_argument("--critic-visual", action="store_true", help="critique with page images (implies --critic)")
    t.add_argument("--slug", metavar="S", help="run slug suffix")
    t.add_argument("--page-target", type=int, choices=PAGE_TARGETS, default=DEFAULT_PAGE_TARGET)
    t.add_argument("--paper", choices=PAPERS, default=DEFAULT_PAPER)
    _add_model_flags(t)
    t.set_defaults(handler=_cmd_tailor)

    c = sub.add_parser("continue", help="resume any run, including ones started in Cursor or Claude Code")
    c.add_argument("run", nargs="?", default=None, metavar="RUN", help="run slug, directory or 'latest'")
    c.add_argument("--answers", metavar="FILE.yaml")
    c.add_argument("--text", metavar="TEXT", help="a free-text reply for whichever checkpoint is pending")
    c.add_argument("--critic", action="store_true")
    c.add_argument("--critic-visual", action="store_true")
    _add_model_flags(c)
    c.set_defaults(handler=_cmd_continue)

    s = sub.add_parser("status", help="where a run stands and what happens next")
    s.add_argument("run", nargs="?", default=None, metavar="RUN")
    _add_json(s)
    s.set_defaults(handler=_cmd_status)

    r = sub.add_parser("render", help="fit and validate an approved run again (no AI)")
    r.add_argument("run", metavar="RUN")
    r.add_argument("--template", choices=TEMPLATES)
    r.add_argument("--draft", action="store_true")
    _add_json(r)
    r.set_defaults(handler=_cmd_render)

    pol = sub.add_parser("polish", help="generic CV with no job description (extract text, or render every template)")
    pol_sub = pol.add_subparsers(dest="polish_command", metavar="<extract|render>", required=True)
    ex = pol_sub.add_parser("extract", help="print CV text (same reader as cvt ingest)")
    ex.add_argument("cv", type=Path, help="CV file (PDF, Markdown, or text)")
    ex.set_defaults(handler=_cmd_polish_extract)
    rn = pol_sub.add_parser("render", help="render a render.json with every template")
    rn.add_argument("model", type=Path, help="render-model JSON")
    rn.add_argument("out", type=Path, help="output directory, usually out/<slug>-generic")
    rn.set_defaults(handler=_cmd_polish_render)

    e = sub.add_parser("edit", help="apply a free-text change to a tailored run, then re-approve and re-render")
    e.add_argument("run", metavar="RUN")
    e.add_argument("--text", required=True, metavar="TEXT", help="the change, in your own words")
    _add_model_flags(e)
    e.set_defaults(handler=_cmd_edit)

    p = sub.add_parser("profile", help="list, show, revoke or activate stored experience facts")
    p.add_argument("action", choices=PROFILE_ACTIONS)
    p.add_argument("id", nargs="?", default="", metavar="ID", help="attestation id (show, revoke, activate)")
    p.add_argument("--person", default="", metavar="P", help="person slug (default: the latest run's person)")
    p.add_argument("--yes", action="store_true", help="revoke without asking (needed when not on a terminal)")
    _add_json(p)
    p.set_defaults(handler=_cmd_profile)

    k = sub.add_parser("package-skill", help="zip the core skill for claude.ai or the Skills API")
    k.add_argument("--out", metavar="DIR", default="")
    _add_json(k)
    k.set_defaults(handler=_cmd_package)

    _register_web(sub)
    return parser


def _add_model_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--model", action="append", default=[], metavar="STAGE=MODEL", help="override a stage's model (repeatable)")
    p.add_argument("--no-cache", action="store_true", help="skip the local LLM cache on reads")


def _register_web(sub: argparse._SubParsersAction) -> None:
    """Wave 6 adds `gtjob serve`; without `gtjob.web.serve` there is no such command."""
    try:
        found = importlib.util.find_spec(WEB_MODULE)
    except (ModuleNotFoundError, ValueError):
        found = None
    if found is not None:
        importlib.import_module(WEB_MODULE).register(sub)


# --- helpers ------------------------------------------------------------------------------------------------
def _usage_error(message: str, hint: str) -> CvtError:
    return CvtError(ExitCode.USAGE, "E_USAGE", message, hint=hint)


def _delegate(argv: list[str]) -> int:
    return int(cvt_cli.main(argv))


def _json_flag(args: argparse.Namespace) -> list[str]:
    return ["--json"] if getattr(args, "json", False) else []


class _Services:
    """The runner and terminal for one command; `main(runner=..., io=...)` injects fakes."""

    def __init__(self, runner: flow.Runner | None, io: interact.IO | None) -> None:
        self.runner = runner
        self.io = io or interact.TerminalIO()

    def runner_for(self, args: argparse.Namespace) -> flow.Runner:
        if self.runner is not None:
            return self.runner
        return ApiRunner(
            cli_models=getattr(args, "model", []), no_cache=getattr(args, "no_cache", False),
            critic_visual=getattr(args, "critic_visual", False),
        )


def _drive(args: argparse.Namespace, svc: _Services, run_dir: Path, *, reply: str | None = None) -> int:
    spec = answers_yaml.load(args.answers) if getattr(args, "answers", None) else None
    critic_visual = bool(getattr(args, "critic_visual", False))
    return flow.drive(
        run_dir, runner=svc.runner_for(args), io=svc.io, answers=spec, auto=bool(getattr(args, "auto", False)),
        reply=reply, critic=bool(getattr(args, "critic", False)) or critic_visual, critic_visual=critic_visual,
    )


# --- commands -----------------------------------------------------------------------------------------------
def _cmd_tailor(args: argparse.Namespace, svc: _Services) -> int:
    if args.auto and args.answers:
        raise _usage_error("--auto and --answers cannot be combined", "use --auto to default everything, or --answers to say what you want")
    if args.answers:
        answers_yaml.load(args.answers)  # fail with exit 2 before a run directory exists
    cv = Path(args.cv)
    if cv.suffix.lower() == DOCX_SUFFIX:
        raise CvtError(ExitCode.INPUT, "E_CV_FORMAT", ".docx CVs are not supported yet",
                       hint="export to PDF or paste the text into a .txt file, then pass that with --cv")
    if args.jd is not None:
        kind, ref, text = "file", args.jd, None
    elif args.jd_text is not None:
        kind, ref, text = "text", JD_TEXT_REF, args.jd_text
    else:
        kind, ref, text = "url", args.jd_url, None
    options = {"template": args.template, "auto": args.auto, "draft": args.draft,
               "page_target": args.page_target, "paper": args.paper}
    run_dir = state.create_run(cv, kind, ref, text, options, slug=args.slug)
    svc.io.say(f"run: {run_dir.name}")
    return _drive(args, svc, run_dir)


def _cmd_continue(args: argparse.Namespace, svc: _Services) -> int:
    run_dir = paths.resolve_run(args.run)
    svc.io.say(f"run: {run_dir.name} ({state.load(run_dir)['stage']})")
    return _drive(args, svc, run_dir, reply=args.text)


def _cmd_edit(args: argparse.Namespace, svc: _Services) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    state.require_stage(st, STAGE_TAILORED)
    return _drive(args, svc, run_dir, reply=args.text)


def _cmd_status(args: argparse.Namespace, svc: _Services) -> int:
    return _delegate(["status", *([args.run] if args.run else []), *_json_flag(args)])


def _cmd_polish_extract(args: argparse.Namespace, svc: _Services) -> int:
    """Print CV text. Same reader and cleaner as `cvt ingest`. No API key."""
    import polish_render  # noqa: PLC0415

    text = polish_render.extract_text(args.cv)
    sys.stdout.write(text if text.endswith("\n") or not text else text + "\n")
    return int(ExitCode.OK)


def _cmd_polish_render(args: argparse.Namespace, svc: _Services) -> int:
    """Render every template from a render-model JSON. No API key."""
    import polish_render  # noqa: PLC0415

    return polish_render.render_all(args.model, args.out)


def _cmd_render(args: argparse.Namespace, svc: _Services) -> int:
    """fit + validate, no AI. `--template` renders with that template instead of fitting (render keeps the fit density)."""
    base = [*_json_flag(args)]
    draft = ["--draft"] if args.draft else []
    first = ["render", args.run, "--template", args.template, *draft] if args.template else ["fit", args.run]
    code = _delegate([*first, *base])
    if code != int(ExitCode.OK):
        return code
    return _delegate(["validate", args.run, *draft, *base])


def _cmd_profile(args: argparse.Namespace, svc: _Services) -> int:
    person = ["--person", args.person] if args.person else []
    flags = _json_flag(args)
    if args.action == "list":
        return _delegate(["attest", "list", *person, *flags])
    if args.action == "show" and not args.id:
        return _delegate(["profile-show", *person, *flags])
    if not args.id:
        raise _usage_error(f"profile {args.action} needs an attestation id", f"run: {PROG} profile list")
    if args.action == "show":
        return _delegate(["attest", "show", args.id, *person, *flags])
    if args.action == "revoke" and not args.yes:
        shown = _delegate(["attest", "show", args.id, *person])
        if shown != int(ExitCode.OK):
            return shown
        if not svc.io.interactive:
            raise _usage_error("revoking needs confirmation", "rerun with --yes to revoke without asking")
        svc.io.say("Revoked facts are no longer used; runs that cite them must be re-tailored.")
        if not svc.io.confirm(f"Revoke {args.id}?", default=False):
            svc.io.say("not revoked")
            return int(ExitCode.OK)
    return _delegate(["attest", args.action, args.id, *person, *flags])


def _cmd_package(args: argparse.Namespace, svc: _Services) -> int:
    return _delegate(["package-skill", *(["--out", args.out] if args.out else []), *_json_flag(args)])


def main(argv: list[str] | None = None, *, runner: flow.Runner | None = None, io: interact.IO | None = None) -> int:
    os.environ.setdefault(HOST_ENV, HOST_CLI)  # before anything touches state, so history records the CLI as host
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:  # argparse: --help exits 0, a usage error exits 2
        return int(exc.code or 0)
    svc = _Services(runner, io)
    try:
        handler = getattr(args, "handler", None)
        return int(handler(args, svc) if handler else args.func(args))  # `func`: commands from optional modules
    except CvtError as err:
        svc.io.error(flow.format_error(err.err_id, err.message, err.hint, err.violations))
        return int(err.code)
    except KeyboardInterrupt:
        svc.io.error("interrupted; state is saved, resume with: gtjob continue")
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(main())
