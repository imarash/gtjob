"""Skill-triggering eval for Claude Code (WP-23).

Each query in `evals/triggers.yaml` is sent to `claude -p` in a scratch workspace that carries only a copy of `.claude/`.
The session is limited to the `Skill` and `Read` tools (`--tools`), so the model can load the skill but can never run
`cvt`, write files, or tailor anything. "Triggered" means a `Skill` tool call naming `tailoring-cvs`, or a `Read` of its
`SKILL.md`. Follow-up queries run in a scratch workspace whose `out/` holds a run at `awaiting_answers`.

Unmarked tests cover the stream parser and the metrics (no network). The `live` test skips without `claude` on PATH or
when a one-turn preflight fails (no login, no network).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

from conftest import (GOLDEN_JUNIOR, JUNIOR_CV, JUNIOR_JD, REPO_ROOT, TRIGGERS_FILE, CLAUDE_PREFLIGHT_TIMEOUT_S, Cvt,
                      clean_env, seed_to_awaiting)

SKILL_NAME = "tailoring-cvs"
SKILL_FILE_MARKER = f"{SKILL_NAME}/SKILL.md"
CLAUDE_TOOLS = "Skill,Read"
QUERY_TIMEOUT_S = 150
QUERY_BUDGET_USD = "0.50"
MAX_PARALLEL = 3
MIN_RECALL = 0.9
SEEDED_SLUG = "trigger-seed"
# Queries that only make sense with a run in progress; they run in the seeded workspace.
FOLLOWUP_QUERIES = frozenset({
    "yes, add SLOs to the SRE roles",
    "add Istio to my CV skills",
    "re-render my CV with the classic template",
    "shorten my tailored CV to one page",
    "drop the Earlier experience line from the CV you made",
})


class ClaudeUnavailable(RuntimeError):
    """The `claude` session produced no assistant output (not logged in, offline, or crashed)."""


# ------------------------------------------------------------------ pure helpers
def parse_stream(text: str) -> list[dict]:
    """Parse `--output-format stream-json` lines, ignoring anything that is not a JSON object."""
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def tool_uses(events: list[dict]) -> list[tuple[str, dict]]:
    """(tool name, input) for every tool_use block in assistant events."""
    uses = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        for block in (event.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                uses.append((str(block.get("name", "")), block.get("input") or {}))
    return uses


def is_triggered(events: list[dict]) -> bool:
    for name, args in tool_uses(events):
        if name == "Skill" and SKILL_NAME in json.dumps(args):
            return True
        if name == "Read" and SKILL_FILE_MARKER in str(args.get("file_path", "")):
            return True
    return False


def has_assistant_output(events: list[dict]) -> bool:
    return any(event.get("type") == "assistant" for event in events)


def metrics(results: dict[str, tuple[bool, bool]]) -> dict:
    """`results[query] = (expected_trigger, triggered)` -> precision, recall, and the misses."""
    tp = [q for q, (want, got) in results.items() if want and got]
    fn = [q for q, (want, got) in results.items() if want and not got]
    fp = [q for q, (want, got) in results.items() if not want and got]
    precision = len(tp) / (len(tp) + len(fp)) if tp or fp else 1.0
    recall = len(tp) / (len(tp) + len(fn)) if tp or fn else 1.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "false_negatives": fn, "false_positives": fp}


def load_queries() -> tuple[list[str], list[str]]:
    doc = yaml.safe_load(TRIGGERS_FILE.read_text(encoding="utf-8"))
    return list(doc["should_trigger"]), list(doc["should_not_trigger"])


def claude_command(query: str) -> list[str]:
    return ["claude", "-p", query, "--output-format", "stream-json", "--verbose", "--tools", CLAUDE_TOOLS,
            "--allowedTools", CLAUDE_TOOLS, "--setting-sources", "project", "--no-session-persistence",
            "--max-budget-usd", QUERY_BUDGET_USD]


STREAM_SAMPLE = "\n".join([
    "not json",
    json.dumps({"type": "system", "subtype": "init"}),
    json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "I'll use the skill."},
        {"type": "tool_use", "name": "Skill", "input": {"skill": SKILL_NAME}}]}}),
])


def test_parse_stream_and_trigger_detection() -> None:
    events = parse_stream(STREAM_SAMPLE)
    assert len(events) == 2 and tool_uses(events) == [("Skill", {"skill": SKILL_NAME})]
    assert is_triggered(events) and has_assistant_output(events)
    other = parse_stream(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": "pdf"}}]}}))
    assert not is_triggered(other)
    read = parse_stream(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": f"/x/.claude/skills/{SKILL_FILE_MARKER}"}}]}}))
    assert is_triggered(read)
    assert not has_assistant_output(parse_stream(json.dumps({"type": "result", "is_error": True})))


def test_metrics() -> None:
    result = metrics({"a": (True, True), "b": (True, False), "c": (False, True), "d": (False, False)})
    assert result == {"precision": 0.5, "recall": 0.5, "false_negatives": ["b"], "false_positives": ["c"]}
    assert metrics({"a": (True, True)})["precision"] == 1.0


def test_query_sets_are_consistent() -> None:
    positive, negative = load_queries()
    assert positive and negative and not set(positive) & set(negative)
    assert FOLLOWUP_QUERIES <= set(positive), "FOLLOWUP_QUERIES must be a subset of should_trigger"


def test_claude_command_never_enables_write_tools() -> None:
    cmd = claude_command("hello")
    assert cmd[2] == "hello" and cmd[cmd.index("--tools") + 1] == CLAUDE_TOOLS
    assert not {"Bash", "Edit", "Write"} & set(CLAUDE_TOOLS.split(","))


# ------------------------------------------------------------------ live
def ask(scratch: Path, query: str) -> list[dict]:
    """Run one headless query; stop as soon as the skill is triggered. Raises ClaudeUnavailable on no output."""
    proc = subprocess.Popen(claude_command(query), cwd=scratch, env=clean_env(scratch), stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    watchdog = threading.Timer(QUERY_TIMEOUT_S, proc.kill)
    watchdog.start()
    events: list[dict] = []
    try:
        for line in proc.stdout:
            events.extend(parse_stream(line))
            if is_triggered(events):
                break
    finally:
        watchdog.cancel()
        proc.kill()
        proc.wait()
    if not has_assistant_output(events):
        raise ClaudeUnavailable(f"no assistant output for {query!r}")
    return events


def make_scratch(root: Path, name: str, *, seeded: bool) -> Path:
    """A workspace with a copy of `.claude/` (skills and agents) and, when `seeded`, a run at awaiting_answers."""
    scratch = root / name
    shutil.copytree(REPO_ROOT / ".claude", scratch / ".claude", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if seeded:
        seed_to_awaiting(Cvt(scratch), cv=JUNIOR_CV, jd=JUNIOR_JD, artifacts=GOLDEN_JUNIOR, slug=SEEDED_SLUG)
    return scratch


@pytest.fixture(scope="module")
def claude_cli() -> str:
    path = shutil.which("claude")
    if path is None:
        pytest.skip("`claude` is not on PATH")
    try:
        proc = subprocess.run([path, "-p", "Reply with OK.", "--output-format", "json", "--tools", "",
                               "--no-session-persistence"], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              timeout=CLAUDE_PREFLIGHT_TIMEOUT_S, check=False)
        reply = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        pytest.skip(f"`claude` preflight failed ({type(exc).__name__})")
    if proc.returncode != 0 or reply.get("is_error"):
        pytest.skip("`claude` preflight failed (not logged in or offline)")
    return path


@pytest.mark.live
def test_skill_triggering(claude_cli, tmp_path_factory: pytest.TempPathFactory, results_dir: Path) -> None:
    positive, negative = load_queries()
    root = tmp_path_factory.mktemp("triggers")
    clean = make_scratch(root, "clean", seeded=False)
    seeded = make_scratch(root, "seeded", seeded=True)
    jobs = [(q, True, seeded if q in FOLLOWUP_QUERIES else clean) for q in positive]
    jobs += [(q, False, clean) for q in negative]

    def one(job: tuple[str, bool, Path]) -> tuple[str, bool, bool]:
        query, want, scratch = job
        return query, want, is_triggered(ask(scratch, query))

    started = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
            rows = list(pool.map(one, jobs))
    except ClaudeUnavailable as exc:
        pytest.skip(str(exc))
    outcome = metrics({query: (want, got) for query, want, got in rows})
    outcome["seconds"] = round(time.monotonic() - started)
    (results_dir / "triggers.json").write_text(json.dumps(outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert not outcome["false_positives"], f"triggered on negatives: {outcome['false_positives']}"
    assert outcome["recall"] >= MIN_RECALL, (
        f"recall {outcome['recall']} < {MIN_RECALL}; missed: {outcome['false_negatives']}")
