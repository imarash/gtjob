"""WP-18: skill linter, packager, and the real skill/wrapper files."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from cvtlib import skillcheck
from conftest import CVT_PY, REPO_ROOT, SKILL_DIR

SKILLS_ROOT = SKILL_DIR.parent
GOOD_DESCRIPTION = "Does one thing well. Use when the user asks for that thing, for example in a test."
FORBIDDEN_ARGS = "$" + "ARGUMENTS"


def _write_skill(root: Path, name: str = "demo-skill", description: str = GOOD_DESCRIPTION,
                 extra_front: str = "", body: str = "# Demo\n\nBody.\n") -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n{extra_front}---\n{body}", encoding="utf-8")
    return folder


def _errors(folder: Path, wrapper: bool = False, contracts: Path | None = None) -> list[str]:
    found = skillcheck.lint_skill(folder, wrapper=wrapper, contracts_dir=contracts or folder / "no-contracts")
    return [f.message for f in found if f.severity == skillcheck.SEVERITY_ERROR]


def _has(messages: list[str], needle: str) -> bool:
    return any(needle in m for m in messages)


def test_real_core_skill_lints_clean() -> None:
    found = skillcheck.lint_skill(SKILL_DIR, contracts_dir=REPO_ROOT / "plan" / "contracts")
    assert [f for f in found if f.severity == skillcheck.SEVERITY_ERROR] == []


@pytest.mark.parametrize("name", skillcheck.WRAPPER_NAMES)
def test_real_wrappers_lint_clean(name: str) -> None:
    found = skillcheck.lint_skill(SKILLS_ROOT / name, wrapper=True)
    assert [f for f in found if f.severity == skillcheck.SEVERITY_ERROR] == []


def test_real_core_description_is_within_budget() -> None:
    keys, body, problem = skillcheck.parse_frontmatter((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))
    assert problem == ""
    assert len(keys["description"]) <= skillcheck.DESCRIPTION_WARN
    assert len(body.splitlines()) <= skillcheck.CORE_BODY_MAX_LINES
    assert "## Token rules" in body


def test_good_synthetic_skill_passes(tmp_path: Path) -> None:
    assert _errors(_write_skill(tmp_path)) == []


def test_unknown_key_fails(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path, extra_front="argument-hint: x\n")
    assert _has(_errors(folder), "unknown key 'argument-hint'")
    assert not _has(_errors(folder, wrapper=True), "unknown key")


def test_angle_bracket_in_description_fails(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path, description="Reads <b>bold</b> files. Use when asked.")
    assert _has(_errors(folder), "'<' or '>'")


def test_name_mismatch_fails(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path, name="demo-skill")
    text = (folder / "SKILL.md").read_text(encoding="utf-8").replace("name: demo-skill", "name: other-skill")
    (folder / "SKILL.md").write_text(text, encoding="utf-8")
    assert _has(_errors(folder), "must equal the folder name")


@pytest.mark.parametrize("bad", ["claude-helper", "-lead", "double--hyphen", "Upper"])
def test_bad_names_fail(tmp_path: Path, bad: str) -> None:
    assert _errors(_write_skill(tmp_path, name=bad)) != []


def test_501_line_body_fails(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path, body="line\n" * (skillcheck.BODY_MAX_LINES + 1))
    assert _has(_errors(folder), "under 500")
    assert _has(_errors(folder, wrapper=True), "under 500")


def test_core_body_cap_applies_only_to_core(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path, body="line\n" * (skillcheck.CORE_BODY_MAX_LINES + 5))
    assert _has(_errors(folder), "cap is 200")
    assert not _has(_errors(folder, wrapper=True), "cap is 200")


def test_readme_present_fails(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path)
    (folder / "README.md").write_text("hi", encoding="utf-8")
    assert _has(_errors(folder), "README.md")


def test_arguments_placeholder_fails(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path, body=f"Do {FORBIDDEN_ARGS} now.\n")
    assert _has(_errors(folder), FORBIDDEN_ARGS)
    assert _has(_errors(folder, wrapper=True), FORBIDDEN_ARGS)


def test_claude_skill_dir_placeholder_fails(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path, body="Run ${" + "CLAUDE_SKILL_DIR}/x.\n")
    assert _has(_errors(folder), "CLAUDE_")


def test_unresolved_and_misdirected_links_fail(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path, body="[a](references/missing.md) and [b](notes/x.md)\n")
    messages = _errors(folder)
    assert _has(messages, "does not resolve")
    assert _has(messages, "must point into")


def test_nested_reference_link_in_skill_fails(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path, body="[a](references/deep/x.md)\n")
    (folder / "references" / "deep").mkdir(parents=True)
    (folder / "references" / "deep" / "x.md").write_text("x\n", encoding="utf-8")
    assert _has(_errors(folder), "one level deep")


def test_reference_linking_another_reference_fails(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path)
    refs = folder / "references"
    refs.mkdir()
    (refs / "a.md").write_text("see [b](b.md)\n", encoding="utf-8")
    (refs / "b.md").write_text("b\n", encoding="utf-8")
    assert _has(_errors(folder), "links to another file")


def test_anchor_links_inside_reference_are_fine(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path)
    refs = folder / "references"
    refs.mkdir()
    (refs / "a.md").write_text("see [core](#core)\n\n## Core\nrules\n", encoding="utf-8")
    assert _errors(folder) == []


def test_long_reference_needs_contents(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path)
    refs = folder / "references"
    refs.mkdir()
    (refs / "long.md").write_text("x\n" * (skillcheck.REFERENCE_TOC_THRESHOLD + 1), encoding="utf-8")
    assert _has(_errors(folder), "## Contents")
    (refs / "long.md").write_text("## Contents\n" + "x\n" * (skillcheck.REFERENCE_TOC_THRESHOLD + 1), encoding="utf-8")
    assert _errors(folder) == []


def test_core_section_rules(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path)
    refs = folder / "references"
    refs.mkdir()
    (refs / "stage-x.md").write_text("no core here\n", encoding="utf-8")
    assert _has(_errors(folder), "missing '## Core'")
    body = "## Core\n" + "rule\n" * (skillcheck.CORE_SECTION_MAX_LINES + 1) + "## Details\nd\n"
    (refs / "stage-x.md").write_text(body, encoding="utf-8")
    assert _has(_errors(folder), "limit is 60")
    (refs / "stage-x.md").write_text("## Core\nrule\n## Details\n" + "d\n" * 100, encoding="utf-8")
    assert _has(_errors(folder), "## Contents")


def test_listing_limit_and_warning(tmp_path: Path) -> None:
    long = "Does a thing. " * 60
    folder = _write_skill(tmp_path, description=long[:900])
    found = skillcheck.lint_skill(folder, contracts_dir=tmp_path / "none")
    assert any(f.severity == skillcheck.SEVERITY_WARNING and "aim for" in f.message for f in found)
    folder2 = _write_skill(tmp_path / "b", name="other", description=long[:900],
                           extra_front=f"{skillcheck.LISTING_EXTRA_KEY}: {'x' * 700}\n")
    assert _has(_errors(folder2), "limit is 1536")


def test_unquoted_colon_value_fails(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path, description="Does things: many of them. Use when asked.")
    assert _has(_errors(folder), "quote it")


def test_wrapper_must_disable_model_invocation(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path)
    assert _has(_errors(folder, wrapper=True), "disable-model-invocation")


def test_schema_drift_is_caught(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path)
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    (contracts / "x.schema.json").write_text("{}", encoding="utf-8")
    assert _has(_errors(folder, contracts=contracts), "missing")
    schemas = folder / "assets" / "schemas"
    schemas.mkdir(parents=True)
    (schemas / "x.schema.json").write_text('{"a": 1}', encoding="utf-8")
    assert _has(_errors(folder, contracts=contracts), "differs from")
    (schemas / "x.schema.json").write_text("{}", encoding="utf-8")
    assert _errors(folder, contracts=contracts) == []


def test_missing_skill_file(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    assert _has(_errors(tmp_path / "empty"), "not found")


def test_build_zip_contents_and_exclusions(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path, name="tailoring-cvs")
    (folder / "__pycache__").mkdir()
    (folder / "__pycache__" / "x.pyc").write_bytes(b"x")
    (folder / "scripts").mkdir()
    (folder / "scripts" / "a.pyc").write_bytes(b"x")
    (folder / "scripts" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (folder / ".DS_Store").write_bytes(b"x")
    target, size, count = skillcheck.build_zip(folder, tmp_path / "dist")
    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
    assert sorted(names) == ["tailoring-cvs/SKILL.md", "tailoring-cvs/scripts/a.py"]
    assert (size, count) == (target.stat().st_size, 2)
    assert skillcheck.verify_zip(target) == []


def _run_cvt(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CVT_PY), *args], cwd=cwd, capture_output=True, text=True, timeout=120)


def test_cli_lint_all_and_json() -> None:
    proc = _run_cvt("lint-skill", "--all", "--json")
    assert proc.returncode == 0, proc.stderr
    env = json.loads(proc.stdout)
    assert env["ok"] and len(env["data"]["skills"]) == 1 + len(skillcheck.WRAPPER_NAMES)


def test_cli_lint_bad_dir_exits_1(tmp_path: Path) -> None:
    folder = _write_skill(tmp_path, extra_front="bogus: 1\n")
    proc = _run_cvt("lint-skill", str(folder), "--json")
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["error"]["id"] == "E_SKILL_LINT"


def test_cli_package_skill_zip(tmp_path: Path) -> None:
    proc = _run_cvt("package-skill", "--out", str(tmp_path / "dist"), "--json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)["data"]
    with zipfile.ZipFile(data["zip"]) as zf:
        names = zf.namelist()
    assert "tailoring-cvs/SKILL.md" in names
    assert len(names) == data["files"]
    assert not [n for n in names if n.split("/")[1:2] in (["out"], ["profiles"])]
    assert not [n for n in names if "__pycache__" in n or n.endswith(".pyc") or n.endswith(".DS_Store")]
