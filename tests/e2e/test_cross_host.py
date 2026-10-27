"""WP-26: one run moves between the IDE path (raw `cvt` commands, as an agent runs them) and the `gtjob` CLI.

Each test has one host stop at a checkpoint and the other host finish the run from `state.json`. The IDE side is real
`cvt.py` subprocesses with `GTJOB_HOST=cursor`; the CLI side is the real `gtjob` flow with a `FakeClient`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


from conftest import CVT_PY, HOME_ENV, HOST_ENV, REPO_ROOT
from cvtlib import jsonio, state
from .test_cli_offline import (  # noqa: F401  (the autouse fixture is re-exported so it applies here too)
    _isolate_env, ANSWERS_YAML, CP1_ONLY_YAML, CV_FIXTURE, EXIT_AWAITING, EXIT_OK, FAKE_DIR, JD_FIXTURE, load_canned,
    only_run, run_gtjob, stage_models, tailor_argv, usage_rows, write_answers,
)

GOLDEN = REPO_ROOT / "tests" / "fixtures" / "golden" / "junior"
IDE_HOST, CLI_HOST = "cursor", "cli"
PACKET_STAGES = ("profile", "jd", "match", "questions")  # the stages the IDE completes before the CLI takes over
# artifact each AI stage writes, and the canned answer an IDE agent would write into it
IDE_ARTIFACTS = {
    "profile": ("profile-map.json", "profile.json"), "jd": ("jd.json", "jd.json"), "match": ("match.json", "match.json"),
    "questions": ("questions.json", "questions.json"),
}
IDE_CHECKS = {"profile": "profile-build", "jd": "jd-check", "match": "match-check", "questions": "questions"}
STAGE_AFTER_CHECK = {"profile": "profiled", "jd": "jd_analyzed", "match": "matched", "questions": "awaiting_answers"}


class Ide:
    """What an IDE agent does: raw `cvt` subprocesses (host `cursor`), with `--json` so exit codes and stages are visible."""

    def __init__(self, home: Path, host: str = IDE_HOST) -> None:
        self.home, self.host = home, host

    def raw(self, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, HOME_ENV: str(self.home), HOST_ENV: self.host}
        return subprocess.run([sys.executable, str(CVT_PY), *args, "--json"], cwd=self.home, env=env,
                              capture_output=True, text=True, check=False)

    def run(self, *args: str, code: int = EXIT_OK) -> dict:
        proc = self.raw(*args)
        assert proc.returncode == code, f"cvt {' '.join(args)} exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def out(self, run: str) -> Path:
        return self.home / "out" / run

    def init(self) -> str:
        slug = self.run("init", "--cv", str(CV_FIXTURE), "--jd", str(JD_FIXTURE))["data"]["run_slug"]
        assert self.run("ingest", slug)["stage"] == "ingested"
        return slug

    def ai_stage(self, run: str, stage: str, *, code: int = EXIT_OK) -> dict:
        """`brief <stage>` (a packet line in usage.jsonl), write the canned answer, run the stage's check."""
        self.run("brief", stage, run)
        target, canned = IDE_ARTIFACTS[stage]
        shutil.copy(FAKE_DIR / canned, self.out(run) / target)
        envelope = self.run(IDE_CHECKS[stage], run, code=code)
        assert envelope["stage"] == STAGE_AFTER_CHECK[stage]
        return envelope

    def to_checkpoint_1(self) -> str:
        run = self.init()
        for stage in PACKET_STAGES:
            self.ai_stage(run, stage, code=EXIT_AWAITING if stage == "questions" else EXIT_OK)
        assert state.load(self.out(run))["stage"] == "awaiting_answers"
        return run

    def tailor_to_checkpoint_2(self, run: str) -> None:
        """tailor packet, the good plan, assemble, diff: the agent presents checkpoint 2."""
        self.run("brief", "tailor", run)
        shutil.copy(FAKE_DIR / "tailor.2.json", self.out(run) / "tailor-plan.json")
        assert self.run("assemble", run)["stage"] == "tailored"
        assert self.run("diff", run)["stage"] == "awaiting_approval"

    def finish(self, run: str) -> None:
        assert self.run("fit", run)["stage"] == "rendered"
        assert self.run("validate", run)["stage"] == "validated"
        assert self.run("report", run)["stage"] == "reported"


def history_hosts(run: Path) -> list[str]:
    return [entry["host"] for entry in state.load(run)["history"]]


def packet_counts(run: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in usage_rows(run):
        if row["kind"] == "packet":
            counts[row["stage"]] = counts.get(row["stage"], 0) + 1
    return counts


# ---------------------------------------------------------------- IDE -> CLI
def test_ide_to_cli_continue_with_answers(workspace: Path, tmp_path: Path) -> None:
    ide = Ide(workspace)
    slug = ide.to_checkpoint_1()
    run = ide.out(slug)
    assert set(history_hosts(run)) == {IDE_HOST}
    packets_before = packet_counts(run)
    assert set(packets_before) == set(PACKET_STAGES)

    fake = load_canned()
    code, io = run_gtjob(["continue", slug, "--answers", str(write_answers(tmp_path, ANSWERS_YAML))], fake)
    assert code == EXIT_OK, io.errors
    assert state.load(run)["stage"] == "reported"
    # the CLI continues from `next_action`: only the stages after checkpoint 1 spend a model call
    assert [s for s, _ in stage_models(fake)] == ["answer_parse", "tailor", "tailor"]
    packets_after = packet_counts(run)
    assert {s: packets_after[s] for s in PACKET_STAGES} == packets_before  # nothing rebuilt for a completed stage
    assert set(packets_after) - set(PACKET_STAGES) == {"answer_parse", "tailor", "fix"}  # only the CLI's own stages
    assert {r["stage"] for r in usage_rows(run) if r["kind"] == "api"} == {"answer_parse", "tailor"}
    assert set(history_hosts(run)) == {IDE_HOST, CLI_HOST}
    assert history_hosts(run)[0] == IDE_HOST and history_hosts(run)[-1] == CLI_HOST
    assert len(list((run / "final").glob("*.pdf"))) == 1


# ---------------------------------------------------------------- CLI -> IDE
def test_cli_to_ide_checkpoint_1_handoff(workspace: Path) -> None:
    fake = load_canned()
    code, io = run_gtjob(tailor_argv(), fake)  # stdin is not a TTY and there is no --answers
    assert code == EXIT_AWAITING and "Which of these requirements" in io.output
    run = only_run(workspace)
    st = state.load(run)
    assert st["stage"] == "awaiting_answers" and st["checkpoints"]["cp1"] == "pending"
    assert {s for s, _ in stage_models(fake)} == {"profile", "jd", "match", "questions"}
    assert set(history_hosts(run)) == {CLI_HOST}
    cli_packets = packet_counts(run)

    ide = Ide(workspace)
    round_file = ide.out(run.name) / "answers.round.json"
    shutil.copy(GOLDEN / "answers.round.json", round_file)
    applied = ide.run("answers-apply", run.name, "--round", str(round_file), "--commit")
    assert applied["stage"] == "answers_applied" and applied["data"]["created"] == ["att-001"]
    ide.tailor_to_checkpoint_2(run.name)
    assert ide.run("approve", run.name, "--all")["stage"] == "approved"
    ide.finish(run.name)

    assert state.load(run)["stage"] == "reported" and len(list((run / "final").glob("*.pdf"))) == 1
    assert set(history_hosts(run)) == {CLI_HOST, IDE_HOST}
    assert packet_counts(run).get("tailor") == 1
    assert all(packet_counts(run).get(stage, 0) == cli_packets.get(stage, 0) for stage in PACKET_STAGES)
    attestations = jsonio.load_json(workspace / "profiles" / "jamie-rivera" / "attestations.json")["attestations"]
    assert [(a["claim"], a["status"]) for a in attestations] == [("Helm", "active")]


# ---------------------------------------------------------------- checkpoint 2 handoff
def test_cli_stops_at_checkpoint_2_and_ide_approves(workspace: Path, tmp_path: Path) -> None:
    fake = load_canned()
    code, io = run_gtjob(tailor_argv("--answers", str(write_answers(tmp_path, CP1_ONLY_YAML))), fake)
    assert code == EXIT_AWAITING and "gtjob continue" in io.output
    run = only_run(workspace)
    assert state.load(run)["stage"] == "awaiting_approval" and state.load(run)["checkpoints"]["cp2"] == "pending"
    calls_before_handoff = len(fake.calls)
    assert calls_before_handoff >= 6

    ide = Ide(workspace)
    edits = ide.out(run.name) / "edits" / "next.json"
    edits.parent.mkdir(parents=True, exist_ok=True)
    batch = jsonio.load_json(GOLDEN / "edits-001.json")
    batch["ops"] = [op for op in batch["ops"] if op["op"] != "approve_all"]  # the approval is its own `cvt approve`
    jsonio.dump_json({**batch, "run_id": state.load(run)["run_id"]}, edits)
    assert ide.run("apply-edits", run.name, str(edits))["stage"] == "awaiting_approval"
    assert ide.run("approve", run.name, "--all")["stage"] == "approved"

    after = load_canned()
    code, io = run_gtjob(["continue", run.name], after)
    assert code == EXIT_OK, io.errors
    assert after.calls == []  # approved already: fit, validate and report are deterministic
    assert state.load(run)["stage"] == "reported"
    assert set(history_hosts(run)) == {CLI_HOST, IDE_HOST}
    hosts = history_hosts(run)
    assert hosts.index(IDE_HOST) > hosts.index(CLI_HOST) and hosts[-1] == CLI_HOST
    tailored = json.dumps(jsonio.load_json(run / "tailored.json"))
    assert "cutting mean time to detect" in tailored  # the IDE-side edit survived the CLI's re-render


def test_claude_code_host_is_recorded_too(workspace: Path, tmp_path: Path) -> None:
    ide = Ide(workspace, host="claude_code")
    slug = ide.to_checkpoint_1()
    fake = load_canned()
    code, io = run_gtjob(["continue", slug, "--answers", str(write_answers(tmp_path, ANSWERS_YAML))], fake)
    assert code == EXIT_OK, io.errors
    assert set(history_hosts(ide.out(slug))) == {"claude_code", CLI_HOST}
