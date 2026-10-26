"""`cvt lint-skill` and `cvt package-skill`: enforce the skill authoring rules and build the uploadable zip."""

from __future__ import annotations

import argparse
from pathlib import Path

from .. import output, paths, skillcheck
from ..errors import CvtError, ExitCode

DEFAULT_OUT_DIR = "dist"
VIOLATION_CODE = "schema"
LINT_ERROR_ID = "E_SKILL_LINT"
KIB = 1024


def _violation(skill: str, finding: skillcheck.Finding) -> dict:
    return {"code": VIOLATION_CODE, "item_id": f"{skill}:{finding.where}", "message": finding.message}


def _targets(args: argparse.Namespace) -> list[tuple[Path, bool]]:
    if args.all:
        wrappers = [(paths.SKILL_ROOT.parent / name, True) for name in skillcheck.WRAPPER_NAMES]
        return [(paths.SKILL_ROOT, False), *wrappers]
    if args.skill_dir:
        given = Path(args.skill_dir)
        return [(given if given.is_absolute() else paths.workspace_root() / given, args.wrapper)]
    return [(paths.SKILL_ROOT, args.wrapper)]


def _lint(args: argparse.Namespace) -> int:
    errors: list[dict] = []
    warnings: list[str] = []
    linted: list[str] = []
    for skill, wrapper in _targets(args):
        linted.append(skill.name)
        for finding in skillcheck.lint_skill(skill, wrapper=wrapper):
            if finding.severity == skillcheck.SEVERITY_ERROR:
                errors.append(_violation(skill.name, finding))
            else:
                warnings.append(f"{skill.name}:{finding.where}: {finding.message}")
    if errors:
        raise CvtError(
            ExitCode.CHECK_FAILED, LINT_ERROR_ID, f"{len(errors)} lint error(s) in {', '.join(linted)}",
            hint="fix the listed items, then rerun: cvt lint-skill" + (" --all" if args.all else ""),
            violations=errors,
        )
    return output.emit(
        args, data={"skills": linted, "warnings": warnings},
        messages=[f"lint ok: {', '.join(linted)}", *warnings],
    )


def _package(args: argparse.Namespace) -> int:
    errors = [
        _violation(paths.SKILL_ROOT.name, f)
        for f in skillcheck.lint_skill(paths.SKILL_ROOT) if f.severity == skillcheck.SEVERITY_ERROR
    ]
    if errors:
        raise CvtError(
            ExitCode.CHECK_FAILED, LINT_ERROR_ID, f"cannot package: {len(errors)} lint error(s)",
            hint="run: cvt lint-skill, fix the listed items, then rerun package-skill", violations=errors,
        )
    out_dir = Path(args.out)
    out_dir = out_dir if out_dir.is_absolute() else paths.workspace_root() / out_dir
    target, size, count = skillcheck.build_zip(paths.SKILL_ROOT, out_dir)
    problems = skillcheck.verify_zip(target)
    if problems:
        raise CvtError(
            ExitCode.CHECK_FAILED, "E_SKILL_ZIP", f"packaged zip failed verification: {problems[0].message}",
            hint="fix SKILL.md frontmatter, then rerun: cvt package-skill",
            violations=[_violation(target.name, f) for f in problems],
        )
    return output.emit(
        args, data={"zip": str(target), "bytes": size, "files": count},
        messages=[f"packaged {target} ({size / KIB:.0f} KiB, {count} files); frontmatter verified"],
    )


def register(subparsers) -> None:
    lint = subparsers.add_parser("lint-skill", help="lint a skill folder against the authoring rules")
    lint.add_argument("skill_dir", nargs="?", default="", metavar="SKILL_DIR", help="skill folder (default: the core skill)")
    lint.add_argument("--wrapper", action="store_true", help="lint as a slash-command wrapper (host keys allowed)")
    lint.add_argument("--all", action="store_true", help="lint the core skill and the five wrappers")
    lint.set_defaults(func=_lint)
    package = subparsers.add_parser("package-skill", help="lint, then zip the core skill for claude.ai / Skills API")
    package.add_argument("--out", default=DEFAULT_OUT_DIR, metavar="DIR", help=f"output folder ({DEFAULT_OUT_DIR}/)")
    package.set_defaults(func=_package)
