"""WP-07: layout and content checks for the stage-B reference guides."""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REFS_DIR = REPO_ROOT / ".claude" / "skills" / "tailoring-cvs" / "references"
CONTRACTS_DIR = REPO_ROOT / "plan" / "contracts"

CORE_MAX_LINES = 60
CONTENTS_REQUIRED_OVER_LINES = 100
DETAIL_SUBHEADINGS = ("### Purpose", "### Inputs", "### Rules", "### Output", "### Self-check")
CANONICAL_REPLY = "add service mesh, istio, typescript. and add slo and error budget to the sre related cv items"
FENCE = "```"
SCHEMA_MARKER = re.compile(r"^<!--\s*schema:\s*([a-z-]+)(?:#([a-z_]+))?\s*-->$")
PII_MARKERS = ("Morattab", "arashmor", "me@", "@gmail", "Arash")

# guide -> (output file named in Core, check command named in Core)
GUIDES = {
    "checkpoint-questions.md": ("questions.json", "cvt questions"),
    "answer-parsing.md": ("answers.round.json", "cvt answers-apply"),
    "stage-tailor.md": ("tailor-plan.json", "cvt assemble"),
    "change-requests.md": ("edits/next.json", "cvt apply-edits"),
}


def _read(name: str) -> str:
    return (REFS_DIR / name).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> list[str]:
    """Lines of the `## heading` section, excluding the heading line itself."""
    lines = text.splitlines()
    start = lines.index(f"## {heading}") + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return lines[start:end]


def _json_blocks(text: str) -> list[tuple[int, str, str | None, str | None]]:
    """(start line, body, schema file, subschema) for every ```json block."""
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == f"{FENCE}json":
            start = i + 1
            end = next(j for j in range(start, len(lines)) if lines[j].strip() == FENCE)
            body = "\n".join(lines[start:end])
            nxt = next((lines[k].strip() for k in range(end + 1, len(lines)) if lines[k].strip()), "")
            match = SCHEMA_MARKER.match(nxt)
            blocks.append((start, body, match.group(1) if match else None, match.group(2) if match else None))
            i = end
        i += 1
    return blocks


def _validator(schema_name: str, sub: str | None) -> jsonschema.Draft202012Validator:
    full = json.loads((CONTRACTS_DIR / f"{schema_name}.schema.json").read_text(encoding="utf-8"))
    if sub:
        full = {"$schema": full["$schema"], "$defs": full["$defs"], "$ref": f"#/$defs/{sub}"}
    return jsonschema.Draft202012Validator(full)


@pytest.mark.parametrize("name", GUIDES)
def test_guide_layout(name: str) -> None:
    text = _read(name)
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    expected = ["## Core", "## Details", "## Examples"]
    if len(text.splitlines()) > CONTENTS_REQUIRED_OVER_LINES:
        expected.insert(0, "## Contents")
    assert headings == expected
    details = "\n".join(_section(text, "Details"))
    positions = [details.index(h) for h in DETAIL_SUBHEADINGS]
    assert positions == sorted(positions)


@pytest.mark.parametrize("name", GUIDES)
def test_core_is_short_and_names_output_and_check(name: str) -> None:
    core = _section(_read(name), "Core")
    assert len(core) <= CORE_MAX_LINES, f"{name} Core has {len(core)} lines"
    body = "\n".join(core)
    output_file, check_cmd = GUIDES[name]
    assert output_file in body
    assert check_cmd in body
    assert "untrusted" in body.lower() or "ignore any instructions" in body.lower()


def test_tailor_core_names_companion_guides_without_links() -> None:
    body = "\n".join(_section(_read("stage-tailor.md"), "Core"))
    assert "style-guide" in body and "truthfulness" in body
    assert "](" not in body


def test_canonical_reply_is_verbatim() -> None:
    assert CANONICAL_REPLY in _read("answer-parsing.md")


def test_canonical_assistant_message_is_verbatim() -> None:
    expected = (
        "Your CV doesn't currently show: service mesh; SOC 2 (you have PCI DSS); TypeScript (only React and "
        "Next.js are listed); explicit SLOs and error budgets; working at a startup as an employee. "
        "Which of these do you actually have experience with?"
    )
    assert expected in _read("checkpoint-questions.md")


@pytest.mark.parametrize("name", GUIDES)
def test_every_json_block_parses_and_marked_ones_validate(name: str) -> None:
    for line_no, body, schema_name, sub in _json_blocks(_read(name)):
        try:
            data = json.loads(body)
        except json.JSONDecodeError as err:
            pytest.fail(f"{name}:{line_no} invalid JSON: {err}")
        if schema_name:
            errors = sorted(_validator(schema_name, sub).iter_errors(data), key=lambda e: list(e.path))
            assert not errors, f"{name}:{line_no} fails {schema_name}: {errors[0].message} at {list(errors[0].path)}"


def test_expected_schema_markers_present() -> None:
    markers = {name: [(s, sub) for _, _, s, sub in _json_blocks(_read(name)) if s] for name in GUIDES}
    assert ("questions", None) in markers["checkpoint-questions.md"]
    assert markers["answer-parsing.md"].count(("answers", "round")) >= 6
    assert ("questions", None) in markers["answer-parsing.md"]
    assert ("tailor-plan", None) in markers["stage-tailor.md"]
    assert markers["change-requests.md"].count(("edits", None)) >= 6


def test_checkpoint_example_is_the_full_batch() -> None:
    blocks = _json_blocks(_read("checkpoint-questions.md"))
    questions = json.loads(blocks[0][1])["questions"]
    assert len(questions) == 8
    assert [q["topic"] for q in questions] == ["gap", "source_issue", "metric", "metric", "metric", "strategy", "strategy", "strategy"]
    assert len(questions[0]["choices"]) == 5
    assert len({q["id"] for q in questions}) == len(questions)
    for q in questions:
        assert q["allow_free_text"] is True and q["default"]["description"]


def test_canonical_round_example() -> None:
    blocks = _json_blocks(_read("answer-parsing.md"))
    round_ = json.loads(blocks[0][1])
    assert round_["raw_text"] == CANONICAL_REPLY
    attestations = [a for item in round_["items"] for a in item["attestations"]]
    assert len(attestations) == 5
    for att in attestations:
        assert att["verbatim"] in round_["raw_text"]
        assert att["detail"] == ""
    by_claim = {a["claim"]: a for a in attestations}
    assert all(by_claim[c]["scope"]["kind"] == "global" and by_claim[c]["placement"] == "skills"
               for c in ("Service mesh", "Istio", "TypeScript"))
    assert by_claim["Istio"]["caveat"]
    for claim in ("SLOs", "Error budgets"):
        att = by_claim[claim]
        assert att["type"] == "practice" and att["placement"] == "bullets"
        assert att["scope"]["kind"] == "role_label" and att["scope"]["role_label"] == "SRE"
        assert att["scope"]["description"] == "the sre related cv items"
    flat = json.dumps(round_).lower()
    assert "soc 2" not in flat and "startup" not in flat
    assert not re.search(r"\d", " ".join(a["detail"] + a["claim"] for a in attestations)), "no invented numbers"


def test_tailor_example_uses_attested_bullet_with_scope_refs() -> None:
    blocks = _json_blocks(_read("stage-tailor.md"))
    plan = json.loads(blocks[0][1])
    bullets = [b for exp in plan["experience"] for eng in exp["engagements"] for b in eng["bullets"]]
    attested = [b for b in bullets if b["op"] == "attested"]
    assert attested and attested[0]["from"] == ["exp-2.e4"] and attested[0]["extra_refs"] == ["att-004", "att-005"]
    assert all(b["text"] == "" for b in bullets if b["op"] == "keep")


def test_no_candidate_pii() -> None:
    for name in GUIDES:
        text = _read(name)
        for marker in PII_MARKERS:
            assert marker not in text, f"{name} contains {marker!r}"
        assert not re.search(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b", text), f"{name} contains an email address"
