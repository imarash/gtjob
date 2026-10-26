"""Layout, schema, and PII checks for the stage guides written by WP-06 (profile, jd, match)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import jsonschema

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / ".claude" / "skills" / "tailoring-cvs"
REFS = SKILL / "references"
SCHEMA_DIRS = (SKILL / "assets" / "schemas", REPO / "plan" / "contracts")

CORE_MAX_LINES = 60
TOC_THRESHOLD_LINES = 100
DETAIL_SUBSECTIONS = ["### Purpose", "### Inputs", "### Rules", "### Output", "### Self-check"]
FORBIDDEN_PII = ["Morattab", "arashmor"]
CVT_PREFIX = "uv run .claude/skills/tailoring-cvs/scripts/cvt.py"

GUIDES = {
    "stage-profile.md": {"output": "profile-map.json", "check": "profile-build"},
    "stage-jd.md": {"output": "jd.json", "check": "jd-check"},
    "stage-match.md": {"output": "match.json", "check": "match-check"},
}

NUMBERED_LINE = re.compile(r"^\s*(\d+)\| ?(.*)$")
SCHEMA_MARKER = re.compile(r"^<!--\s*schema:\s*([a-z-]+)\s*-->$")


def _read(name: str) -> str:
    return (REFS / name).read_text(encoding="utf-8")


def _h2_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def _core_lines(text: str) -> list[str]:
    lines = _h2_sections(text)["Core"]
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    return lines


def _code_blocks(text: str) -> list[dict]:
    """Fenced blocks with language, body, and the first non-blank line after the closing fence."""
    lines = text.splitlines()
    blocks: list[dict] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("```") and len(lines[i]) > 3:
            lang = lines[i][3:].strip()
            start = i
            i += 1
            body: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            after = lines[j].strip() if j < len(lines) else ""
            before = lines[start - 1].strip() if start > 0 else ""
            blocks.append({"lang": lang, "body": "\n".join(body), "after": after, "before": before})
        i += 1
    return blocks


def _schema(name: str) -> dict:
    for directory in SCHEMA_DIRS:
        path = directory / f"{name}.schema.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    pytest.skip(f"schema {name} not found")


def _expand(rng: str) -> list[int]:
    lo, _, hi = rng.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


@pytest.mark.parametrize("name", GUIDES)
def test_layout(name: str) -> None:
    text = _read(name)
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    expected = ["## Core", "## Details", "## Examples"]
    if len(text.splitlines()) > TOC_THRESHOLD_LINES:
        expected.insert(0, "## Contents")
    assert headings == expected
    core = _core_lines(text)
    assert 0 < len(core) <= CORE_MAX_LINES, f"Core has {len(core)} lines"
    details = [line for line in _h2_sections(text)["Details"] if line.startswith("### ")]
    assert details == DETAIL_SUBSECTIONS


@pytest.mark.parametrize("name,meta", GUIDES.items())
def test_core_names_output_check_and_untrusted_rule(name: str, meta: dict) -> None:
    core = "\n".join(_core_lines(_read(name)))
    assert meta["output"] in core
    assert f"{CVT_PREFIX} {meta['check']} RUN" in core
    assert "untrusted_document" in core
    assert "instruction" in core.lower()


@pytest.mark.parametrize("name", GUIDES)
def test_no_candidate_pii(name: str) -> None:
    text = _read(name).lower()
    for needle in FORBIDDEN_PII:
        assert needle.lower() not in text


@pytest.mark.parametrize("name", GUIDES)
def test_json_blocks_parse_and_validate(name: str) -> None:
    for block in _code_blocks(_read(name)):
        if block["lang"] != "json":
            continue
        data = json.loads(block["body"])
        marker = SCHEMA_MARKER.match(block["after"])
        if marker:
            jsonschema.Draft202012Validator(_schema(marker.group(1))).validate(data)


def test_every_guide_has_a_schema_checked_example() -> None:
    expected = {"stage-profile.md": "profile-map", "stage-jd.md": "jd", "stage-match.md": "match"}
    for name, schema in expected.items():
        markers = [SCHEMA_MARKER.match(b["after"]) for b in _code_blocks(_read(name)) if b["lang"] == "json"]
        assert schema in {m.group(1) for m in markers if m}


def test_profile_example_map_partitions_numbered_cv() -> None:
    """The example map covers each non-blank example line exactly once, and typed values are verbatim."""
    blocks = _code_blocks(_read("stage-profile.md"))
    numbered = next(b for b in blocks if b["before"] == "<!-- numbered-cv -->")
    lines: dict[int, str] = {}
    for raw in numbered["body"].splitlines():
        m = NUMBERED_LINE.match(raw)
        assert m, raw
        lines[int(m.group(1))] = m.group(2)
    pmap = json.loads(next(b for b in blocks if b["after"] == "<!-- schema: profile-map -->")["body"])

    used: list[int] = []

    def take(rng: str) -> str:
        nums = _expand(rng)
        used.extend(nums)
        return "\n".join(lines[n] for n in nums)

    def takes(ranges: list[str]) -> str:
        return "\n".join(take(r) for r in ranges)

    basics_text = takes(pmap["basics"]["lines"])
    for key in ("name", "email", "url"):
        assert pmap["basics"][key] in basics_text
    takes(pmap["summary_lines"])
    for work in pmap["work"]:
        header = take(work["header_lines"])
        for key in ("name", "location", "date_text"):
            assert work[key] in header
        takes(work["summary_lines"])
        for hl in work["highlights"]:
            take(hl["lines"])
        for eng in work["engagements"]:
            header = take(eng["header_lines"])
            assert eng["name"] in header and eng["role_label"] in header
            takes(eng["summary_lines"])
            for hl in eng["highlights"]:
                take(hl["lines"])
    for edu in pmap["education"]:
        text = take(edu["lines"])
        for key in ("institution", "area", "study_type", "location"):
            assert edu[key] in text
    for skill in pmap["skills"]:
        assert skill["name"] in takes(skill["lines"])
    takes(pmap["ignored_lines"])

    non_blank = sorted(n for n, text in lines.items() if text.strip())
    assert sorted(used) == non_blank, "gaps or overlaps in the example map"


def test_jd_example_noise_is_verbatim_and_requirements_sequential() -> None:
    blocks = _code_blocks(_read("stage-jd.md"))
    jd_text = next(b for b in blocks if b["before"] == "<!-- numbered-jd -->")["body"]
    plain = "\n".join((NUMBERED_LINE.match(r).group(2) if NUMBERED_LINE.match(r) else r) for r in jd_text.splitlines())
    jd = json.loads(next(b for b in blocks if b["after"] == "<!-- schema: jd -->")["body"])
    for item in jd["noise"]:
        assert item["text"] in plain, item
    assert [r["id"] for r in jd["requirements"]] == [f"req-{n}" for n in range(1, len(jd["requirements"]) + 1)]
    ids = {r["id"] for r in jd["requirements"]}
    assert all(set(k["req_ids"]) <= ids for k in jd["keywords"])
    assert jd["company"] == ""
    assert any(r["kind"] == "must" for r in jd["requirements"])


def test_match_guide_covers_all_strengths() -> None:
    text = _read("stage-match.md")
    for strength in ("strong", "partial", "none"):
        assert f"`{strength}`" in "\n".join(_core_lines(text))
    example = next(b for b in _code_blocks(text) if b["after"] == "<!-- schema: match -->")
    strengths = {r["strength"] for r in json.loads(example["body"])["requirements"]}
    assert strengths == {"strong", "partial", "none"}
