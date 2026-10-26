"""`cvt validate-artifact RUN NAME [--file PATH]`: schema-check an artifact. Never changes state."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import jsonio, output, paths, schemas
from ..errors import CvtError, ExitCode

NAME_HELP = "profile|profile-map|jd|match|questions|answers|tailor-plan|tailored|edits|fit|validation|critique"


def _run(args: argparse.Namespace) -> int:
    name = args.name
    if name not in schemas.SCHEMA_NAMES:
        raise CvtError(ExitCode.USAGE, "E_SCHEMA_UNKNOWN", f"unknown artifact name '{name}'",
                       hint=f"valid names: {NAME_HELP}")
    run_dir = paths.resolve_run(args.run)
    target = Path(args.file) if args.file else run_dir / f"{name}.json"
    if not target.is_file():
        raise CvtError(ExitCode.STATE, "E_ARTIFACT_MISSING", f"{target.name} not found in {run_dir.name}",
                       hint=f"write {target.name} following the stage guide, then rerun: "
                            f"cvt validate-artifact {run_dir.name} {name}")
    problems = schemas.validate(jsonio.load_json(target), name)
    base = {"name": name, "file": str(target), "violation_count": len(problems)}
    if not problems:
        return output.emit(args, run=run_dir.name, data={"valid": True, **base},
                           human=f"ok: {target.name} matches the {name} schema")
    shown, hidden = output.cap_list(args, schemas.to_violations(problems))
    data = {"valid": False, **base, "violations": shown}
    if hidden:
        data["violations_more"] = hidden
    human = [f"{target.name} has {len(problems)} schema violations:"]
    human += [f"  {v['item_id']}: {v['message']}" for v in shown]
    if hidden:
        human.append("  " + output.MORE_LINE.format(n=hidden))
    return output.emit(args, run=run_dir.name, data=data, human="\n".join(human),
                       next_action="patch only the listed items, then rerun this command",
                       exit_code=int(ExitCode.CHECK_FAILED))


def register(subparsers) -> None:
    p = subparsers.add_parser("validate-artifact", help="validate an artifact JSON against its schema")
    p.add_argument("run", metavar="RUN", help="run slug, run directory, or 'latest'")
    p.add_argument("name", metavar="NAME", help=NAME_HELP)
    p.add_argument("--file", default="", help="validate this file instead of out/<run>/<NAME>.json")
    p.set_defaults(func=_run)
