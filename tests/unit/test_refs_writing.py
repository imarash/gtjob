"""Structure and anonymization checks for the writing reference guides (WP-05)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REFS_DIR = REPO_ROOT / ".claude" / "skills" / "tailoring-cvs" / "references"

CONTENTS_THRESHOLD_LINES = 100
CORE_MAX_LINES = {"style-guide": 25, "truthfulness": 20, "critic-rubric": 60}
MIN_BEFORE_AFTER_PAIRS = 8
TRUTH_RULE_COUNT = 10
ALLOWED_EMAIL_DOMAIN = "example.com"
EMAIL_RE = re.compile(r"[\w.+-]*@[\w.-]+")
DETAILS_SUBSECTIONS = ["### Purpose", "### Inputs", "### Rules", "### Output", "### Self-check"]

GUIDES = sorted(CORE_MAX_LINES)


def _read(name: str) -> str:
    return (REFS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _h2_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def _core_line_count(text: str) -> int:
    lines = text.splitlines()
    start = lines.index("## Core")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return end - start


@pytest.mark.parametrize("name", GUIDES)
def test_file_exists(name: str) -> None:
    assert (REFS_DIR / f"{name}.md").is_file()


@pytest.mark.parametrize("name", GUIDES)
def test_guide_layout(name: str) -> None:
    text = _read(name)
    headings = [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]
    expected = ["Core", "Details", "Examples"]
    if len(text.splitlines()) > CONTENTS_THRESHOLD_LINES:
        expected = ["Contents", *expected]
    assert headings == expected
    details = "\n".join(_h2_sections(text)["Details"])
    positions = [details.find(h) for h in DETAILS_SUBSECTIONS]
    assert all(p >= 0 for p in positions), f"missing Details subsection in {name}"
    assert positions == sorted(positions)


@pytest.mark.parametrize("name", GUIDES)
def test_core_size(name: str) -> None:
    assert _core_line_count(_read(name)) <= CORE_MAX_LINES[name]


@pytest.mark.parametrize("name", GUIDES)
def test_no_personal_data(name: str) -> None:
    text = _read(name)
    assert "Morattab" not in text
    assert "arashmor" not in text.lower()
    for match in EMAIL_RE.findall(text):
        assert match.endswith(ALLOWED_EMAIL_DOMAIN), f"unexpected email-like text: {match}"
    for line in text.splitlines():
        if "@" in line:
            assert ALLOWED_EMAIL_DOMAIN in line


@pytest.mark.parametrize("name", GUIDES)
def test_no_cross_reference_links(name: str) -> None:
    assert not re.search(r"\]\([^)]*\.md[^)]*\)", _read(name))


def test_truthfulness_mentions_rules_1_to_10() -> None:
    text = _read("truthfulness")
    for number in range(1, TRUTH_RULE_COUNT + 1):
        assert re.search(rf"^{number}\. ", text, re.M), f"rule {number} missing"
        assert f"**{number}." in text, f"rule {number} details missing"


def test_style_guide_before_after_pairs() -> None:
    text = _read("style-guide")
    assert text.count("Before:") >= MIN_BEFORE_AFTER_PAIRS
    assert text.count("After:") >= MIN_BEFORE_AFTER_PAIRS


def test_critic_rubric_covers_criteria() -> None:
    text = _read("critic-rubric")
    for criterion in ["relevance", "impact", "concision", "readability", "visual", "truthfulness", "questions"]:
        assert f"**{criterion}**" in text
    assert "--visual" in text
    assert "Baseline comparison" in text
