"""WP-I1: integration checks across the wave 1 outputs.

Checks that the fixtures validate through the real `cvtlib.schemas`, that the bundled schemas, presets, fonts and
reference guides match the frozen contracts in `plan/contracts/interfaces.md`, and that the guide layout and
token budgets hold. Everything here is offline and uses only committed files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from cvtlib import schemas

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / ".claude" / "skills" / "tailoring-cvs"
ASSETS = SKILL / "assets"
REFS = SKILL / "references"
FONTS = ASSETS / "fonts"
TEMPLATES = ASSETS / "templates"
CONTRACTS = REPO / "plan" / "contracts"
INTERFACES = CONTRACTS / "interfaces.md"
WP03_TASK = REPO / "plan" / "tasks" / "WP-03-text-fixtures.md"
PROMPT = REPO / "prompts" / "opus-plan-cv-tailor.md"
GOLDEN = REPO / "tests/fixtures/golden/junior"
RENDER = REPO / "tests/fixtures/render"
ANSWERS = REPO / "tests/fixtures/answers"
INTERACTION_CASES = REPO / "tests/fixtures/expected/interaction-cases.yaml"

CORE_MAX_LINES = 60
TAILOR_PACKET_CORE_MAX_LINES = 110
HEADING_PREFIX = "## "
CORE_HEADING = "## Core"
CONTENTS_HEADING = "## Contents"
LONG_REFERENCE_LINES = 100
PRESET_NAMES = ("floor", "comfortable", "standard", "compact")
CVT_GLOBAL_FLAGS = ("--json", "--help")

# Stage guides and the writing guides, with the output file (section 13 table) and check command they name.
STAGE_GUIDES = {
    "stage-profile.md": ("profile-map.json", "profile-build"),
    "stage-jd.md": ("jd.json", "jd-check"),
    "stage-match.md": ("match.json", "match-check"),
    "checkpoint-questions.md": ("questions.json", "questions"),
    "answer-parsing.md": ("answers.round.json", "answers-apply"),
    "stage-tailor.md": ("tailor-plan.json", "assemble"),
    "change-requests.md": ("edits/next.json", "apply-edits"),
    "critic-rubric.md": ("critique.draft.json", "critique-save"),
}
WRITING_GUIDES = {
    "style-guide.md": "assemble",
    "truthfulness.md": "check-tailored",
}
TAILOR_PACKET_GUIDES = ("stage-tailor.md", "style-guide.md", "truthfulness.md")

UNDOCUMENTED_FLAGS: tuple[str, ...] = ()

GOLDEN_SCHEMA_BY_FILE = {
    "profile-map.json": "profile-map",
    "profile.json": "profile",
    "jd.json": "jd",
    "match.json": "match",
    "questions.json": "questions",
    "tailor-plan.json": "tailor-plan",
    "tailored.json": "tailored",
    "edits-001.json": "edits",
}
ANSWERS_ROUND_FILE = "answers.round.json"
ROUND_DEF = "round"
RENDER_SCHEMA = "render-model"
GOLDEN_README = "README.md"


# --- helpers -------------------------------------------------------------------------------------------------------


def _interfaces_section(number: int) -> str:
    lines = INTERFACES.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{HEADING_PREFIX}{number}. "))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith(HEADING_PREFIX))
    return "\n".join(lines[start:end])


def _section_lines(text: str, heading: str) -> list[str]:
    """Lines of the block that starts at `heading` and ends before the next `## ` heading (heading included)."""
    lines = text.splitlines()
    start = lines.index(heading)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(HEADING_PREFIX)), len(lines))
    return lines[start:end]


def _core(path: Path) -> list[str]:
    return _section_lines(path.read_text(encoding="utf-8"), CORE_HEADING)


def _validate_with(schema: dict, obj: object) -> list[str]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in validator.iter_errors(obj)]


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _section3_commands() -> set[str]:
    commands = set()
    for line in _interfaces_section(3).splitlines():
        match = re.match(r"\|\s*`([a-z][a-z0-9-]*)`", line)
        if match:
            commands.add(match.group(1))
    return commands


def _section3_flags() -> set[str]:
    flags = set(CVT_GLOBAL_FLAGS)
    for line in _interfaces_section(3).splitlines():
        if re.match(r"\|\s*`[a-z][a-z0-9-]*`", line):
            flags.update(re.findall(r"--[a-z][a-z0-9-]*", line))
    return flags


def _section3_stages() -> set[str]:
    match = re.search(r"STAGE is `([^`]+)`", _interfaces_section(3))
    assert match, "section 3 no longer lists the brief STAGE values"
    return set(match.group(1).split("\\|"))


def _golden_ids_from_wp03() -> set[str]:
    ids = set()
    for line in WP03_TASK.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*\|\s*`((?:exp)-[^`]+)`\s*\|", line)
        if match:
            ids.add(match.group(1))
    return ids


def _reference_files() -> list[Path]:
    return sorted(REFS.glob("*.md"))


# --- schemas, presets, and fonts -----------------------------------------------------------------------------------


def test_golden_junior_files_validate() -> None:
    files = sorted(p for p in GOLDEN.glob("*.json"))
    assert files, "no golden JSON files found"
    for path in files:
        obj = _load(path)
        if path.name == ANSWERS_ROUND_FILE:
            schema = schemas.subschema("answers", ROUND_DEF)
        elif path.name in GOLDEN_SCHEMA_BY_FILE:
            schema = schemas.load_schema(GOLDEN_SCHEMA_BY_FILE[path.name])
        else:
            pytest.fail(f"golden file {path.name} has no schema mapping in test_wave1.py")
        problems = _validate_with(schema, obj)
        assert not problems, f"{path.name}: {problems[:3]}"


def test_golden_mapping_covers_every_file() -> None:
    expected = set(GOLDEN_SCHEMA_BY_FILE) | {ANSWERS_ROUND_FILE}
    actual = {p.name for p in GOLDEN.glob("*.json")}
    assert actual == expected


def test_render_fixtures_validate_against_render_model() -> None:
    files = sorted(RENDER.glob("*.json"))
    assert files
    for path in files:
        problems = schemas.validate(_load(path), RENDER_SCHEMA)
        assert not problems, f"{path.name}: {problems[:3]}"


def test_golden_profile_map_and_tailor_plan_validate() -> None:
    for name, schema in (("profile-map.json", "profile-map"), ("tailor-plan.json", "tailor-plan")):
        assert schemas.validate(_load(GOLDEN / name), schema) == [], name


def test_asset_schemas_are_byte_equal_to_contracts() -> None:
    contract_files = {p.name.removesuffix(".schema.json"): p for p in CONTRACTS.glob("*.schema.json")}
    asset_files = {p.name.removesuffix(".schema.json"): p for p in (ASSETS / "schemas").glob("*.schema.json")}
    assert asset_files.keys() == contract_files.keys()
    for name, contract in contract_files.items():
        assert asset_files[name].read_bytes() == contract.read_bytes(), f"{name}.schema.json differs"


def test_presets_match_section_9() -> None:
    section = _interfaces_section(9)
    blocks = re.findall(r"```json\n(.*?)```", section, re.S)
    contract = next(json.loads(block) for block in blocks if '"floor"' in block)
    presets = _load(TEMPLATES / "presets.json")
    for name in PRESET_NAMES:
        assert name in presets, f"presets.json lacks '{name}'"
    assert presets == contract


def test_font_files_named_in_fonts_md_exist_with_ofl() -> None:
    fonts_md = (FONTS / "FONTS.md").read_text(encoding="utf-8")
    named = re.findall(r"`((?:source-sans-3|libertinus)/[^`]+\.otf)`", fonts_md)
    assert len(named) == 8, f"expected 4 OTF weights per family, found {named}"
    for rel in named:
        path = FONTS / rel
        assert path.is_file(), f"missing font {rel}"
        assert (path.parent / "OFL.txt").is_file(), f"no OFL.txt beside {rel}"


def test_template_font_references_exist() -> None:
    """Any template that names an OTF file or a font family must use bundled fonts only."""
    allowed_families = {"Source Sans 3", "Source Sans 3 Semibold", "Libertinus Serif", "Libertinus Serif Semibold"}
    for typ in sorted(TEMPLATES.glob("*.typ")):
        text = typ.read_text(encoding="utf-8")
        for name in re.findall(r"[\w.-]+\.otf", text):
            assert any(FONTS.rglob(name)), f"{typ.name} names missing font {name}"
        for family in re.findall(r'font:\s*"([^"]+)"', text):
            assert family in allowed_families, f"{typ.name} uses unbundled font family '{family}'"


# --- references: commands, flags, layout --------------------------------------------------------------------------


def test_reference_cvt_commands_exist_in_section_3() -> None:
    known = _section3_commands()
    assert "assemble" in known and "validate-artifact" in known, "section 3 table did not parse"
    unknown = []
    for path in _reference_files():
        for match in re.finditer(r"\bcvt(?:\.py)?\s+([a-z][a-z0-9-]*)", path.read_text(encoding="utf-8")):
            if match.group(1) not in known:
                unknown.append(f"{path.name}: {match.group(0)}")
    assert not unknown, unknown


def test_reference_brief_stages_exist_in_section_3() -> None:
    stages = _section3_stages()
    unknown = []
    for path in _reference_files():
        for match in re.finditer(r"\bcvt(?:\.py)?\s+brief\s+([a-z_]+)", path.read_text(encoding="utf-8")):
            if match.group(1) not in stages:
                unknown.append(f"{path.name}: brief {match.group(1)}")
    assert not unknown, unknown


def test_reference_flags_exist_in_section_3() -> None:
    known = _section3_flags() | set(UNDOCUMENTED_FLAGS)
    assert "--dry-run" in known and "--select" in known, "section 3 flags did not parse"
    unknown = []
    for path in _reference_files():
        for flag in set(re.findall(r"--[a-z][a-z0-9-]*", path.read_text(encoding="utf-8"))):
            if flag not in known:
                unknown.append(f"{path.name}: {flag}")
    assert not unknown, unknown


def test_reference_guides_are_all_present() -> None:
    names = {p.name for p in _reference_files()}
    assert set(STAGE_GUIDES) | set(WRITING_GUIDES) <= names


@pytest.mark.parametrize("path", _reference_files(), ids=lambda p: p.name)
def test_long_references_have_contents(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if len(text.splitlines()) > LONG_REFERENCE_LINES:
        assert CONTENTS_HEADING in text.splitlines(), f"{path.name} is over {LONG_REFERENCE_LINES} lines"


@pytest.mark.parametrize("path", _reference_files(), ids=lambda p: p.name)
def test_references_do_not_link_to_other_references(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)]+)\)", text):
        assert target.startswith("#") or target.startswith("http"), f"{path.name} links to {target}"


@pytest.mark.parametrize("name", sorted(STAGE_GUIDES) + sorted(WRITING_GUIDES), ids=str)
def test_guide_core_is_small_and_names_its_check(name: str) -> None:
    path = REFS / name
    core = _core(path)
    assert len(core) <= CORE_MAX_LINES, f"{name} Core is {len(core)} lines (max {CORE_MAX_LINES})"
    core_text = "\n".join(core)
    check = STAGE_GUIDES[name][1] if name in STAGE_GUIDES else WRITING_GUIDES[name]
    assert check in core_text, f"{name} Core does not name the check command '{check}'"


@pytest.mark.parametrize("name", sorted(STAGE_GUIDES), ids=str)
def test_stage_guide_core_names_its_output_file(name: str) -> None:
    output = STAGE_GUIDES[name][0]
    assert output in "\n".join(_core(REFS / name)), f"{name} Core does not name output '{output}'"


@pytest.mark.parametrize("name", sorted(STAGE_GUIDES), ids=str)
def test_stage_guide_core_says_what_to_do_on_exit_1(name: str) -> None:
    core_text = "\n".join(_core(REFS / name)).lower()
    assert "exit 1" in core_text, f"{name} Core does not say what to do on exit 1"
    assert "brief fix" in core_text or "at most 2" in core_text, (
        f"{name} Core names neither 'brief fix' nor 'at most 2'"
    )


def test_tailor_packet_core_budget() -> None:
    total = sum(len(_core(REFS / name)) for name in TAILOR_PACKET_GUIDES)
    assert total <= TAILOR_PACKET_CORE_MAX_LINES, f"tailor packet Core is {total} lines"


# --- prompt, canonical exchange, interaction cases -----------------------------------------------------------------


def _quoted_after(text: str, lead: str) -> str:
    match = re.search(re.escape(lead) + r'"(.*?)"', text, re.S)
    assert match, f"prompt no longer contains '{lead}'"
    return " ".join(match.group(1).split())


def test_canonical_reply_matches_prompt() -> None:
    if not PROMPT.is_file():
        pytest.skip("prompts/opus-plan-cv-tailor.md is not present")
    text = PROMPT.read_text(encoding="utf-8")
    # The prompt soft-wraps the quoted exchange; joining the wrapped lines with a single space restores it.
    question = _quoted_after(text, "The assistant (Checkpoint 1) said: ")
    reply = _quoted_after(text, "The user replied: ")
    question_file = (ANSWERS / "staff-platform-sre.checkpoint1.question.txt").read_bytes()
    reply_file = (ANSWERS / "staff-platform-sre.checkpoint1.txt").read_bytes()
    assert question_file == question.encode("utf-8")
    assert reply_file == reply.encode("utf-8")


def _walk_strings(node: object):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _walk_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_strings(value)


def test_interaction_cases_parse_and_use_known_item_ids() -> None:
    cases = yaml.safe_load(INTERACTION_CASES.read_text(encoding="utf-8"))
    assert isinstance(cases, dict) and cases, "interaction-cases.yaml did not parse to a mapping"
    known = _golden_ids_from_wp03()
    assert {"exp-1", "exp-2.e4", "exp-5"} <= known, "WP-03 ID map did not parse"
    used = set()
    for value in _walk_strings(cases):
        used.update(re.findall(r"exp-\d+(?:\.e\d+)?", value))
    assert used, "no item IDs found in interaction-cases.yaml"
    assert used <= known, f"unknown item IDs: {sorted(used - known)}"
