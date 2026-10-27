"""End-to-end fixtures: real `cvt` subprocess calls in a temporary `GTJOB_HOME`, with the AI-written stages replaced
by golden artifacts copied into the run directory.

`workspace`  an empty workspace root (copies of the inputs go in `inputs/`; `out/` and `profiles/` never touch the repo)
`cvt`        callable: `cvt(*args, code=None)` runs `cvt.py <args> --json` and returns a `CompletedProcess` whose
             `.envelope` is the parsed `--json` envelope; `cvt.raw(...)` skips `--json`
`agent_step` callable: `agent_step(run, artifact, src)` copies a golden file to where the AI stage would write it
`junior`, `sample`  session-scoped `Scenario` objects. `scenario.restore(stage, cvt)` returns the slug of a run that
             stopped at `stage`, built once with the real commands and copied into the test's workspace.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pytest

from conftest import CVT_PY, DEFAULT_SAMPLE_CV, HOME_ENV, HOST_ENV, REPO_ROOT, SAMPLE_CV_ENV
from cvtlib import jsonio
from cvtlib.state import STAGES

FIXTURES = REPO_ROOT / "tests" / "fixtures"
JUNIOR_GOLDEN = FIXTURES / "golden" / "junior"
JUNIOR_CV = FIXTURES / "cv" / "jamie-rivera-junior.txt"
JUNIOR_JD = FIXTURES / "jds" / "junior-devops-engineer.md"
SAMPLE_GOLDEN = FIXTURES / "private" / "sample"
SAMPLE_JD = REPO_ROOT / "JDs" / "staff-platform-sre.md"
SECOND_JD = FIXTURES / "jds" / "ai-llm-platform-engineer.md"
INJECTION_JD = FIXTURES / "jds" / "injection-test.md"
INTERACTION_CASES = FIXTURES / "expected" / "interaction-cases.yaml"
BUDGETS = REPO_ROOT / ".claude" / "skills" / "tailoring-cvs" / "assets" / "budgets.json"

EXIT_OK, EXIT_CHECK_FAILED, EXIT_USAGE, EXIT_STATE, EXIT_AWAITING_USER = 0, 1, 2, 4, 6
JUNIOR_PERSON = "jamie-rivera"
SAMPLE_PERSON = "arash-morattab"
CVT_PREFIX = "uv run .claude/skills/tailoring-cvs/scripts/cvt.py"
E2E_UV_ENV = "GTJOB_E2E_UV"
CURSOR_ENV_PREFIX = "CURSOR_"
CLAUDE_ENV_NAME = "CLAUDECODE"


class Cvt:
    """Runs `cvt.py` as a subprocess against one workspace root, exactly as the skill instructs."""

    def __init__(self, home: Path) -> None:
        self.home = home
        home.mkdir(parents=True, exist_ok=True)

    def _command(self) -> list[str]:
        if os.environ.get(E2E_UV_ENV) == "1":
            return ["uv", "run", str(CVT_PY)]
        return [sys.executable, str(CVT_PY)]

    def _env(self) -> dict[str, str]:
        env = {**os.environ, HOME_ENV: str(self.home)}
        env.pop(HOST_ENV, None)
        for key in list(env):
            if key.startswith(CURSOR_ENV_PREFIX) or key == CLAUDE_ENV_NAME:
                env.pop(key)
        return env

    def raw(self, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([*self._command(), *args], cwd=self.home, env=self._env(), input=stdin,
                              capture_output=True, text=True, check=False)

    def __call__(self, *args: str, code: int | None = EXIT_OK) -> subprocess.CompletedProcess:
        """Run with `--json`. `code` is the expected exit code (None: do not assert). `.envelope` is the parsed output."""
        proc = self.raw(*args, "--json")
        try:
            envelope = json.loads(proc.stdout)
        except ValueError:
            envelope = {}
        proc.envelope = envelope  # type: ignore[attr-defined]
        if code is not None:
            assert proc.returncode == code, (
                f"cvt {' '.join(args)} exited {proc.returncode}, wanted {code}:\n{proc.stdout}\n{proc.stderr}")
        return proc

    def out(self, run: str) -> Path:
        return self.home / "out" / run

    def json(self, run: str, name: str) -> dict:
        return jsonio.load_json(self.out(run) / name)

    def store(self, person: str) -> dict:
        return jsonio.load_json(self.home / "profiles" / person / "attestations.json")

    def status(self, run: str) -> dict:
        return self("status", run).envelope

    def pdf_text(self, pdf: Path) -> str:
        proc = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty workspace root with `GTJOB_HOME` pointing at it and the host-detection variables cleared."""
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.setenv(HOME_ENV, str(root))
    monkeypatch.delenv(HOST_ENV, raising=False)
    monkeypatch.delenv(CLAUDE_ENV_NAME, raising=False)
    for key in list(os.environ):
        if key.startswith(CURSOR_ENV_PREFIX):
            monkeypatch.delenv(key, raising=False)
    return root


@pytest.fixture
def cvt(workspace: Path) -> Cvt:
    return Cvt(workspace)


@pytest.fixture
def agent_step(cvt: Cvt) -> Callable[[str, str, Path], Path]:
    """`agent_step(run, artifact, src)`: copy a golden file to out/<run>/<artifact>, where the AI stage writes it."""

    def _step(run: str, artifact: str, src: Path) -> Path:
        dest = cvt.out(run) / artifact
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        return dest

    return _step


# ------------------------------------------------------------------------------- scenarios built stage by stage
@dataclass
class Scenario:
    """One golden run, built once per session with real commands; every stage's workspace is snapshotted."""

    name: str
    person: str
    cv: Path
    jd: Path
    golden: Path
    slug: str
    files: dict[str, Path]
    commit_steps: Callable[["Scenario", Cvt, str], None]
    init_args: tuple[str, ...] = ()
    snapshots: dict[str, Path] = field(default_factory=dict)
    run_slug: str = ""
    root: Path = Path()

    def agent(self, cvt: Cvt, run: str, artifact: str, key: str) -> None:
        dest = cvt.out(run) / artifact
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.files[key], dest)

    def _snap(self, cvt: Cvt, stage: str) -> None:
        dest = self.root / "snapshots" / stage
        dest.mkdir(parents=True)
        for sub in ("out", "profiles"):
            if (cvt.home / sub).exists():
                shutil.copytree(cvt.home / sub, dest / sub, symlinks=True)
        self.snapshots[stage] = dest

    def build(self, root: Path) -> None:
        self.root = root
        cvt = Cvt(root / "build")
        inputs = cvt.home / "inputs"
        inputs.mkdir()
        cv, jd = inputs / self.cv.name, inputs / self.jd.name
        shutil.copyfile(self.cv, cv)
        shutil.copyfile(self.jd, jd)
        run = cvt("init", "--cv", str(cv), "--jd", str(jd), "--slug", self.slug, *self.init_args).envelope["data"]["run_slug"]
        self.run_slug = run
        self._snap(cvt, "initialized")
        cvt("ingest", run)
        self._snap(cvt, "ingested")
        self.agent(cvt, run, "profile-map.json", "profile-map")
        cvt("profile-build", run)
        cvt("profile-cache", run, "--store")
        self._snap(cvt, "profiled")
        self.agent(cvt, run, "jd.json", "jd")
        cvt("jd-check", run)
        self._snap(cvt, "jd_analyzed")
        self.agent(cvt, run, "match.json", "match")
        cvt("match-check", run)
        self._snap(cvt, "matched")
        self.agent(cvt, run, "questions.json", "questions")
        cvt("questions", run, code=EXIT_AWAITING_USER)
        self._snap(cvt, "awaiting_answers")
        self.commit_steps(self, cvt, run)
        self._snap(cvt, "answers_applied")
        self.agent(cvt, run, "tailor-plan.json", "tailor-plan")
        cvt("assemble", run)
        self._snap(cvt, "tailored")
        cvt("diff", run)
        self._snap(cvt, "awaiting_approval")
        cvt("apply-edits", run, str(self.files["edits"]))
        cvt("approve", run)
        self._snap(cvt, "approved")
        cvt("fit", run)
        self._snap(cvt, "rendered")
        cvt("validate", run)
        self._snap(cvt, "validated")
        cvt("report", run)
        self._snap(cvt, "reported")

    def restore(self, stage: str, cvt: Cvt) -> str:
        """Copy the snapshot taken when the run reached `stage` into `cvt`'s workspace; return the run slug."""
        assert stage in self.snapshots, f"no snapshot for {stage}; known: {sorted(self.snapshots)}"
        src = self.snapshots[stage]
        for sub in ("out", "profiles"):
            if (src / sub).exists():
                shutil.copytree(src / sub, cvt.home / sub, symlinks=True, dirs_exist_ok=True)
        inputs = cvt.home / "inputs"
        inputs.mkdir(exist_ok=True)
        shutil.copyfile(self.cv, inputs / self.cv.name)
        shutil.copyfile(self.jd, inputs / self.jd.name)
        return self.run_slug


def _junior_commit(scn: Scenario, cvt: Cvt, run: str) -> None:
    scn.agent(cvt, run, "answers.round.json", "round")
    cvt("answers-apply", run, "--round", str(cvt.out(run) / "answers.round.json"), "--commit")


def _sample_commit(scn: Scenario, cvt: Cvt, run: str) -> None:
    scn.agent(cvt, run, "answers.round.json", "round")
    cvt("answers-apply", run, "--round", str(cvt.out(run) / "answers.round.json"), "--commit")
    cvt("questions", run, "--add", str(scn.files["followups"]), code=EXIT_AWAITING_USER)
    shutil.copyfile(scn.files["followups-skip"], cvt.out(run) / "answers.round.json")
    cvt("answers-apply", run, "--round", str(cvt.out(run) / "answers.round.json"), "--commit")


@pytest.fixture(scope="session")
def junior(tmp_path_factory: pytest.TempPathFactory) -> Scenario:
    scn = Scenario(
        name="junior", person=JUNIOR_PERSON, cv=JUNIOR_CV, jd=JUNIOR_JD, golden=JUNIOR_GOLDEN, slug="golden-junior",
        files={
            "profile-map": JUNIOR_GOLDEN / "profile-map.json", "jd": JUNIOR_GOLDEN / "jd.json",
            "match": JUNIOR_GOLDEN / "match.json", "questions": JUNIOR_GOLDEN / "questions.json",
            "round": JUNIOR_GOLDEN / "answers.round.json", "tailor-plan": JUNIOR_GOLDEN / "tailor-plan.json",
            "edits": JUNIOR_GOLDEN / "edits-001.json",
        },
        commit_steps=_junior_commit, init_args=("--page-target", "1"),
    )
    scn.build(tmp_path_factory.mktemp("junior"))
    return scn


def sample_cv_path() -> Path:
    return Path(os.environ.get(SAMPLE_CV_ENV, DEFAULT_SAMPLE_CV))


def require_private_sample() -> None:
    if not sample_cv_path().is_file() or not SAMPLE_GOLDEN.is_dir() or not SAMPLE_JD.is_file():
        pytest.skip("private sample CV, JD, or goldens are absent")


@pytest.fixture(scope="session")
def sample(tmp_path_factory: pytest.TempPathFactory) -> Scenario:
    require_private_sample()
    scn = Scenario(
        name="sample", person=SAMPLE_PERSON, cv=sample_cv_path(), jd=SAMPLE_JD, golden=SAMPLE_GOLDEN,
        slug="golden-sample",
        files={
            "profile-map": SAMPLE_GOLDEN / "profile-map.json", "jd": SAMPLE_GOLDEN / "jd.json",
            "match": SAMPLE_GOLDEN / "match.json", "questions": SAMPLE_GOLDEN / "questions.json",
            "round": SAMPLE_GOLDEN / "answers.canonical.round.json", "followups": SAMPLE_GOLDEN / "followups.json",
            "followups-skip": SAMPLE_GOLDEN / "answers.followups-skip.round.json",
            "tailor-plan": SAMPLE_GOLDEN / "tailor-plan.json", "edits": SAMPLE_GOLDEN / "edits.approve-all.json",
        },
        commit_steps=_sample_commit,
    )
    scn.build(tmp_path_factory.mktemp("sample"))
    return scn


def stage_index(stage: str) -> int:
    return STAGES.index(stage)


# What `next_action` must name at each stage (interfaces.md section 6): the next expected command.
NEXT_ACTION_NAMES: dict[str, str] = {
    "initialized": f"{CVT_PREFIX} ingest",
    "ingested": f"{CVT_PREFIX} profile-cache",
    "profiled": f"{CVT_PREFIX} brief jd",
    "jd_analyzed": f"{CVT_PREFIX} brief match",
    "matched": f"{CVT_PREFIX} brief questions",
    "awaiting_answers": f"{CVT_PREFIX} answers-apply",
    "answers_applied": f"{CVT_PREFIX} brief tailor",
    "tailored": f"{CVT_PREFIX} diff",
    "awaiting_approval": f"{CVT_PREFIX} approve",
    "approved": f"{CVT_PREFIX} fit",
    "rendered": f"{CVT_PREFIX} validate",
    "validated": f"{CVT_PREFIX} report",
    "reported": "Done.",
}


def assert_next_action(envelope: dict, stage: str, run: str) -> None:
    assert envelope["stage"] == stage, envelope
    action = envelope["next_action"]
    assert NEXT_ACTION_NAMES[stage] in action, f"{stage}: next_action {action!r} lacks {NEXT_ACTION_NAMES[stage]!r}"
    if stage != "reported":
        assert run in action, f"{stage}: next_action does not name the run {run}"


def stage_budget(stage: str) -> int:
    return jsonio.load_json(BUDGETS)["stages"][stage]["input"]


def packet(cvt: Cvt, stage: str, run: str, *extra: str, enforce_budget: bool = True) -> dict:
    """Run `cvt brief` and assert the packet fits its budget; returns `data` (with `est_tokens`)."""
    data = cvt("brief", stage, run, *extra).envelope["data"]
    assert data["packet"].strip(), stage
    assert data["budget"] >= stage_budget(stage), f"{stage}: budget {data['budget']} below the table"
    if enforce_budget:
        assert data["est_tokens"] <= data["budget"], f"{stage}: {data['est_tokens']} tokens > budget {data['budget']}"
        assert not [w for w in data["warnings"] if "budget" in w.lower()], (stage, data["warnings"])
    return data
