"""Argument parsing and dispatch. Commands in cvtlib/commands/ are discovered automatically."""

from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys
import traceback
from typing import Any

from . import commands as commands_pkg
from . import output, paths
from .errors import CvtError, ExitCode

PROG = "cvt"
LAST_ERROR_FILE = ("cvt-last-error.txt",)
CACHE_DIR = ".cache"
DEPENDENCY_HINT = "run with: uv run .claude/skills/tailoring-cvs/scripts/cvt.py <command> ..."
EXIT_INTERRUPTED = 130  # shell convention: 128 + SIGINT


class _UsageError(Exception):
    """Raised by the parser so `main` can report usage errors in human or `--json` form."""

    def __init__(self, message: str, prog: str) -> None:
        super().__init__(message)
        self.message = message
        self.prog = prog


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise _UsageError(message, self.prog)


COMMON_FLAGS = (
    ("--json", "print one minified JSON envelope on stdout"),
    ("--all", "lift the output caps (15 lines, 10 list items)"),
)


def _add_common_flags(parser: argparse.ArgumentParser, suppress: bool) -> None:
    """Add `--json` / `--all`. The subparser copy uses SUPPRESS so it never overwrites the global value.

    A command that already defines its own `--all` (for example `approve --all`) keeps its definition.
    """
    default: Any = argparse.SUPPRESS if suppress else False
    for flag, help_text in COMMON_FLAGS:
        if flag not in parser._option_string_actions:
            parser.add_argument(flag, action="store_true", default=default, help=help_text)


class _Subparsers:
    """Wraps the subparsers action: sets a `command` default and adds the shared flags after registration."""

    def __init__(self, action: Any) -> None:
        self._action = action
        self.created: list[argparse.ArgumentParser] = []

    def add_parser(self, name: str, **kwargs: Any) -> argparse.ArgumentParser:
        parser = self._action.add_parser(name, **kwargs)
        parser.set_defaults(command=name)
        self.created.append(parser)
        return parser

    def finalize(self) -> None:
        for parser in self.created:
            _add_common_flags(parser, suppress=True)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._action, item)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog=PROG, description="Tailor a CV to a job description without inventing facts.")
    _add_common_flags(parser, suppress=False)
    action = parser.add_subparsers(dest="command", metavar="<command>", parser_class=_Parser)
    subparsers = _Subparsers(action)
    for info in sorted(pkgutil.iter_modules(commands_pkg.__path__), key=lambda i: i.name):
        module = importlib.import_module(f"{commands_pkg.__name__}.{info.name}")
        register = getattr(module, "register", None)
        if register is not None:
            register(subparsers)
    subparsers.finalize()
    return parser


def _internal_failure(args: Any, exc: BaseException) -> int:
    err_path = paths.workspace_root().joinpath(CACHE_DIR, *LAST_ERROR_FILE)
    try:
        err_path.parent.mkdir(parents=True, exist_ok=True)
        err_path.write_text("".join(traceback.format_exception(exc)), encoding="utf-8")
        where = f"traceback saved to {CACHE_DIR}/{LAST_ERROR_FILE[0]}"
    except OSError:
        where = "traceback could not be saved; rerun with the same arguments to reproduce"
    return output.fail(args, CvtError(
        ExitCode.INTERNAL, "E_INTERNAL", f"{type(exc).__name__}: {exc}", hint=where,
    ))


def _first_command(parser: argparse.ArgumentParser, argv: list[str]) -> str:
    """The first non-flag token of `argv` if it names a registered command, else an empty string."""
    registered: set[str] = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            registered.update(action.choices)
    token = next((t for t in argv if not t.startswith("-")), "")
    return token if token in registered else ""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    probe = argparse.Namespace(json="--json" in argv, all="--all" in argv, command="", run="")
    try:
        parser = build_parser()
    except ModuleNotFoundError as exc:
        return output.fail(probe, CvtError(
            ExitCode.MISSING_DEPENDENCY, "E_DEPENDENCY", f"missing Python module: {exc.name}",
            hint=DEPENDENCY_HINT,
        ))
    except Exception as exc:  # noqa: BLE001 - a broken command module must not hide the traceback
        return _internal_failure(probe, exc)
    try:
        args = parser.parse_args(argv)
    except _UsageError as exc:
        probe.command = _first_command(parser, argv)
        return output.fail(probe, CvtError(
            ExitCode.USAGE, "E_USAGE", exc.message, hint=f"run `{exc.prog} --help`",
        ))
    except SystemExit as exc:
        return int(exc.code or 0)
    if not getattr(args, "func", None):
        if probe.json:
            return output.fail(probe, CvtError(
                ExitCode.USAGE, "E_USAGE", "no command given", hint=f"run `{PROG} --help` to list commands",
            ))
        parser.print_help(sys.stderr)
        return int(ExitCode.USAGE)
    try:
        return int(args.func(args))
    except CvtError as err:
        return output.fail(args, err)
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except Exception as exc:  # noqa: BLE001
        return _internal_failure(args, exc)
