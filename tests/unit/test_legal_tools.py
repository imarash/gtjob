"""The legal-tool table covers every stage, and Studio cannot emit a command the table omits."""

from __future__ import annotations

import re
from pathlib import Path

from conftest import REPO_ROOT
from cvtlib import state

CVT_ARGS = REPO_ROOT / "web" / "src" / "lib" / "cvt-args.mjs"
CASE_RE = re.compile(r'case "([^"]+)":')


def test_every_stage_has_tools() -> None:
    assert set(state.LEGAL_TOOLS) == set(state.STAGES)
    for stage, tools in state.LEGAL_TOOLS.items():
        assert tools, stage
        assert "status" in tools


def test_studio_argv_is_a_subset_of_the_table() -> None:
    text = CVT_ARGS.read_text(encoding="utf-8")
    commands = set(CASE_RE.findall(text))
    commands.add("polish-extract")
    missing = commands - state.legal_command_names()
    assert not missing, sorted(missing)


def test_a_tool_outside_the_stage_is_refused() -> None:
    assert state.tool_allowed("initialized", "ingest")
    assert not state.tool_allowed("initialized", "approve")
    assert not state.tool_allowed("initialized", "write-jd")
    assert state.tool_allowed("profiled", "write-jd")
    assert "init" in state.legal_command_names()
    assert "polish-extract" in state.legal_command_names()
