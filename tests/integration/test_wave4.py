"""WP-I4: the offline `GTJOB_FAKE_LLM` replay through `gtjob`, the private sample golden through `cvt`, the README, evals.

No network and no API key: the fake client plays the AI stages from the junior golden artifacts.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import CVT_PY, HOME_ENV, HOST_ENV, REPO_ROOT
from cvtlib import jsonio, state
from cvtlib import questions as qmod
from gtjob import cli, interact
from gtjob.llm import FAKE_LLM_ENV, FakeClient

FIXTURES = REPO_ROOT / "tests" / "fixtures"
GOLDEN = FIXTURES / "golden" / "junior"
CV_FIXTURE = FIXTURES / "cv" / "jamie-rivera-junior.txt"
JD_FIXTURE = FIXTURES / "jds" / "junior-devops-engineer.md"
PRIVATE_SAMPLE = FIXTURES / "private" / "sample"
SAMPLE_JD = REPO_ROOT / "JDs" / "staff-platform-sre.md"
README = REPO_ROOT / "README.md"
EXIT_OK, EXIT_AWAITING = 0, 6
HELM_REPLY = "I used Helm at Brightfield to package two internal services"
ANSWERS_YAML = f'checkpoint1:\n  q-1: "{HELM_REPLY}"\n  default_rest: true\nfollowups: default\ncheckpoint2: approve_all\n'
CHANGE_YAML = (
    f'checkpoint1:\n  q-1: "{HELM_REPLY}"\n  default_rest: true\nfollowups: default\n'
    "checkpoint2:\n  - \"Say 'cutting' in the monitoring bullet\"\n"
)
# the junior goldens, renamed to the stage that produces them
FAKE_FILES = {
    "profile": "profile-map.json", "jd": "jd.json", "match": "match.json", "questions": "questions.json",
    "answer_parse": "answers.round.json", "tailor": "tailor-plan.json", "change_request": "edits-001.json",
}
SAMPLE_GOLDEN_ARTIFACTS = ("profile", "jd", "match", "questions", "tailored", "fit", "validation")
SAMPLE_ARTIFACT_FILES = {name: f"{name}.json" for name in SAMPLE_GOLDEN_ARTIFACTS}
README_GTJOB_RE = re.compile(r"uv run gtjob ([a-z-]+)((?: [^\n`|]*)?)")
FLAG_RE = re.compile(r"(?<![\w-])(--[a-z][a-z-]*)")
EVALS_DIR = REPO_ROOT / "evals"


@pytest.fixture(autouse=True)
def _restore_host_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """`gtjob.cli.main` sets GTJOB_HOST; make monkeypatch undo it after each test."""
    monkeypatch.setenv(HOST_ENV, "placeholder")
    monkeypatch.delenv(HOST_ENV)


@pytest.fixture
def fake_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "fake-llm"
    directory.mkdir()
    for stage, name in FAKE_FILES.items():
        shutil.copy(GOLDEN / name, directory / f"{stage}.json")
    monkeypatch.setenv(FAKE_LLM_ENV, str(directory))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return directory


def run_gtjob(argv: list[str]) -> tuple[int, interact.ScriptedIO]:
    io = interact.ScriptedIO(inputs=[], interactive=False)
    return cli.main(argv, io=io), io


def only_run(workspace: Path) -> Path:
    runs = sorted((workspace / "out").iterdir())
    assert len(runs) == 1
    return runs[0]


# ---------------------------------------------------------------- GTJOB_FAKE_LLM hook
def test_fake_llm_tailor_answers_reaches_reported(workspace: Path, fake_dir: Path, tmp_path: Path) -> None:
    answers = tmp_path / "answers.yaml"
    answers.write_text(ANSWERS_YAML, encoding="utf-8")
    code, io = run_gtjob(["tailor", "--cv", str(CV_FIXTURE), "--jd", str(JD_FIXTURE), "--answers", str(answers)])
    assert code == EXIT_OK, io.errors
    run = only_run(workspace)
    st = state.load(run)
    assert st["stage"] == "reported" and st["checkpoints"] == {"cp1": "done", "cp2": "done"}
    assert len(list((run / "final").glob("*.pdf"))) == 1
    rows = [json.loads(line) for line in (run / "usage.jsonl").read_text(encoding="utf-8").splitlines()]
    api_stages = {r["stage"] for r in rows if r.get("kind") == "api"}
    assert {"profile", "jd", "match", "questions", "answer_parse", "tailor"} <= api_stages
    assert not (workspace / ".cache" / "gtjob" / "llm").exists()  # canned answers never reach the real response cache
    assert (fake_dir / ".cache" / "gtjob" / "llm").is_dir()
    attestations = jsonio.load_json(workspace / "profiles" / "jamie-rivera" / "attestations.json")["attestations"]
    assert [(a["claim"], a["status"]) for a in attestations] == [("Helm", "active")]


def test_fake_llm_change_request_stage_runs_at_checkpoint_2(workspace: Path, fake_dir: Path, tmp_path: Path) -> None:
    answers = tmp_path / "answers.yaml"
    answers.write_text(CHANGE_YAML, encoding="utf-8")
    code, io = run_gtjob(["tailor", "--cv", str(CV_FIXTURE), "--jd", str(JD_FIXTURE), "--answers", str(answers)])
    assert code == EXIT_OK, io.errors
    run = only_run(workspace)
    assert state.load(run)["stage"] == "reported"
    stages = [json.loads(line)["stage"] for line in (run / "usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert "change_request" in stages


def test_fake_llm_non_tty_stops_at_checkpoint_1(workspace: Path, fake_dir: Path) -> None:
    code, io = run_gtjob(["tailor", "--cv", str(CV_FIXTURE), "--jd", str(JD_FIXTURE)])
    assert code == EXIT_AWAITING and "Which of these requirements" in io.output
    assert state.load(only_run(workspace))["stage"] == "awaiting_answers"


def test_fake_llm_missing_stage_file_is_actionable(workspace: Path, fake_dir: Path) -> None:
    (fake_dir / "jd.json").unlink()
    code, io = run_gtjob(["tailor", "--cv", str(CV_FIXTURE), "--jd", str(JD_FIXTURE), "--auto"])
    assert code != EXIT_OK
    assert "E_FAKE_EXHAUSTED" in "\n".join(io.errors) and "hint:" in "\n".join(io.errors)


def test_fake_llm_dir_must_exist(workspace: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(FAKE_LLM_ENV, str(tmp_path / "missing"))
    code, io = run_gtjob(["tailor", "--cv", str(CV_FIXTURE), "--jd", str(JD_FIXTURE), "--auto"])
    assert code != EXIT_OK and "E_FAKE_LLM_DIR" in "\n".join(io.errors)


def test_fake_client_from_dir_orders_numbered_attempts(tmp_path: Path) -> None:
    for number, marker in ((10, "tenth"), (2, "second")):
        (tmp_path / f"jd.{number}.json").write_text(json.dumps({"marker": marker}), encoding="utf-8")
    (tmp_path / "match.json").write_text(json.dumps({"marker": "only"}), encoding="utf-8")
    (tmp_path / "notes.json").write_text("{}", encoding="utf-8")  # not a stage: ignored
    client = FakeClient.from_dir(tmp_path)
    assert [client._responses["jd"][i]["marker"] for i in range(2)] == ["second", "tenth"]
    assert client._responses["match"] == [{"marker": "only"}] and "notes" not in client._responses


def test_fake_llm_is_off_by_default(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(FAKE_LLM_ENV, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    code, io = run_gtjob(["tailor", "--cv", str(CV_FIXTURE), "--jd", str(JD_FIXTURE), "--auto"])
    assert code == 3 and "E_API_KEY" in "\n".join(io.errors)


# ---------------------------------------------------------------- private sample golden
@pytest.fixture
def sample_run(workspace: Path, sample_cv_path: Path) -> tuple[str, "Cvt"]:
    if not (PRIVATE_SAMPLE / "validation.json").is_file() or not SAMPLE_JD.is_file():
        pytest.skip("private sample golden or JDs/staff-platform-sre.md not present")
    cvt = Cvt(workspace)
    run = cvt.run("init", "--cv", str(sample_cv_path), "--jd", str(SAMPLE_JD))["data"]["run_slug"]
    cvt.run("ingest", run)
    shutil.copy(PRIVATE_SAMPLE / "profile-map.json", cvt.out(run) / "profile-map.json")
    assert cvt.run("profile-build", run)["stage"] == "profiled"
    shutil.copy(PRIVATE_SAMPLE / "jd.json", cvt.out(run) / "jd.json")
    assert cvt.run("jd-check", run)["stage"] == "jd_analyzed"
    shutil.copy(PRIVATE_SAMPLE / "match.json", cvt.out(run) / "match.json")
    assert cvt.run("match-check", run)["stage"] == "matched"
    return run, cvt


class Cvt:
    """Runs `cvt.py` as a subprocess against one workspace root."""

    def __init__(self, home: Path) -> None:
        self.home = home

    def raw(self, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, HOME_ENV: str(self.home)}
        env.pop(HOST_ENV, None)
        return subprocess.run([sys.executable, str(CVT_PY), *args], cwd=self.home, env=env,
                              capture_output=True, text=True, check=False)

    def run(self, *args: str, code: int = EXIT_OK) -> dict:
        proc = self.raw(*args, "--json")
        assert proc.returncode == code, f"cvt {' '.join(args)} exited {proc.returncode}:\n{proc.stdout}\n{proc.stderr}"
        return json.loads(proc.stdout)

    def out(self, run: str) -> Path:
        return self.home / "out" / run


def test_private_sample_replays_through_cvt(sample_run: tuple[str, Cvt]) -> None:
    run, cvt = sample_run
    for name, file_name in SAMPLE_ARTIFACT_FILES.items():
        envelope = cvt.run("validate-artifact", run, name, "--file", str(PRIVATE_SAMPLE / file_name))
        assert envelope["ok"] is True, name
    validation = jsonio.load_json(PRIVATE_SAMPLE / "validation.json")
    assert validation["passed"] is True
    assert not [g for g in validation["gates"] if g["status"] == "fail"]


SAMPLE_FAKE_FILES = {
    "profile": "profile-map.json", "jd": "jd.json", "match": "match.json", "questions": "questions.json",
    "answer_parse": "answers.canonical.round.json", "tailor": "tailor-plan.json",
}
SAMPLE_ANSWERS_YAML = (
    'checkpoint1:\n  q-1: "I have worked with all of these in production"\n  default_rest: true\n'
    "followups: default\ncheckpoint2: approve_all\n"
)


def test_private_sample_full_run_with_fake_llm(workspace: Path, sample_cv_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               tmp_path: Path) -> None:
    """Eight round-1 questions plus a round-2 scope follow-up (the cap is per round) reach `reported` offline."""
    if not (PRIVATE_SAMPLE / "validation.json").is_file() or not SAMPLE_JD.is_file():
        pytest.skip("private sample golden or JDs/staff-platform-sre.md not present")
    directory = tmp_path / "fake-sample"
    directory.mkdir()
    for stage, name in SAMPLE_FAKE_FILES.items():
        shutil.copy(PRIVATE_SAMPLE / name, directory / f"{stage}.json")
    answers = tmp_path / "answers.yaml"
    answers.write_text(SAMPLE_ANSWERS_YAML, encoding="utf-8")
    monkeypatch.setenv(FAKE_LLM_ENV, str(directory))
    code, io = run_gtjob(["tailor", "--cv", str(sample_cv_path), "--jd", str(SAMPLE_JD), "--answers", str(answers)])
    assert code == EXIT_OK, io.errors
    run = only_run(workspace)
    assert state.load(run)["stage"] == "reported"
    questions = jsonio.load_json(run / "questions.json")["questions"]
    assert {q["round"] for q in questions} == {1, 2} and not [q for q in questions if q["status"] == "pending"]
    assert not [g for g in jsonio.load_json(run / "validation.json")["gates"] if g["status"] == "fail"]


def _pending(round_no: int, count: int, start: int) -> list[dict]:
    template = jsonio.load_json(GOLDEN / "questions.json")["questions"][1]
    return [{**template, "id": f"q-{start + n}", "round": round_no} for n in range(count)]


def test_pending_question_limit_is_per_round() -> None:
    # the initial batch (empty parent_id, any round) is capped as a whole; follow-ups (parent_id set) get a cap per round
    base = jsonio.load_json(GOLDEN / "questions.json")
    template = base["questions"][1]

    def cp1(n: int, round_no: int, parent_id: str = "") -> dict:
        return {**template, "id": f"q-{n}", "round": round_no, "parent_id": parent_id}

    def capped(rows: list[dict]) -> list[str]:
        base["questions"] = rows
        return [v["message"] for v in qmod.check(base, [])[1] if "pending checkpoint-1" in v["message"]]

    initial = [cp1(n, 1) for n in range(1, qmod.MAX_CP1_QUESTIONS + 1)]
    # a follow-up beside a full initial batch is allowed (the WP-I4 case)
    assert capped(initial + [cp1(9, 2, "q-1")]) == []
    # nine follow-ups in one round exceed that round's cap
    over = capped(initial + [cp1(n, 2, "q-1") for n in range(9, 18)])
    assert len(over) == 1 and "round 2 follow-ups" in over[0]
    # each follow-up round has its own cap
    assert capped(initial + [cp1(n, 2, "q-1") for n in range(9, 17)] + [cp1(n, 3, "q-1") for n in range(17, 25)]) == []
    # initial questions in a later round still count against the initial batch
    mixed = capped([cp1(n, 1) for n in range(1, qmod.MAX_CP1_QUESTIONS + 1)] + [cp1(9, 2)])
    assert len(mixed) == 1 and "initial batch" in mixed[0]


# ---------------------------------------------------------------- README and evals
def test_readme_commands_exist() -> None:
    gtjob_help = subprocess.run([sys.executable, "-c", "import sys; from gtjob.cli import main; sys.exit(main(['--help']))"],
                                capture_output=True, text=True, check=False)
    assert gtjob_help.returncode == 0 and "tailor" in gtjob_help.stdout
    cvt_help = subprocess.run([sys.executable, str(CVT_PY), "--help"], capture_output=True, text=True, check=False)
    assert cvt_help.returncode == 0 and "validate-artifact" in cvt_help.stdout

    text = README.read_text(encoding="utf-8")
    assert "not yet available" not in text and "(planned)" not in text
    parser = cli.build_parser()
    subparsers = next(a for a in parser._actions if hasattr(a, "choices") and a.choices).choices
    mentioned = README_GTJOB_RE.findall(text)
    assert {name for name, _ in mentioned} >= {"tailor", "continue"}
    for name, rest in mentioned:
        assert name in subparsers, f"README mentions `gtjob {name}`, which does not exist"
        known = {opt for action in subparsers[name]._actions for opt in action.option_strings}
        unknown = [f for f in FLAG_RE.findall(rest) if f not in known]
        assert not unknown, f"README `gtjob {name}` uses unknown flags {unknown}"


def test_evals_collect_without_errors() -> None:
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "--co", str(EVALS_DIR)], cwd=REPO_ROOT,
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout[-1500:] + proc.stderr[-500:]
    assert "error" not in proc.stdout.lower().split("tests collected")[-1]
