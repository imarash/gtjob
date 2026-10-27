"""Shared fixtures for the live evals (WP-23).

Nothing here talks to a model by itself. Tests that do are marked `live` and request `needs_key` (Anthropic API) or
`claude_cli` (Claude Code headless), which skip cleanly when the credential or binary is missing.
Results go to `evals/results/<run id>/` only (git-ignored).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
SKILL_DIR = REPO_ROOT / ".claude" / "skills" / "tailoring-cvs"
SCRIPTS_DIR = SKILL_DIR / "scripts"
CVT_PY = SCRIPTS_DIR / "cvt.py"
RESULTS_ROOT = EVALS_DIR / "results"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
GOLDEN_JUNIOR = FIXTURES / "golden" / "junior"
JUNIOR_CV = FIXTURES / "cv" / "jamie-rivera-junior.txt"
JUNIOR_JD = FIXTURES / "jds" / "junior-devops-engineer.md"
INTERACTION_CASES = FIXTURES / "expected" / "interaction-cases.yaml"
TRIGGERS_FILE = EVALS_DIR / "triggers.yaml"
PRIVATE_SAMPLE = FIXTURES / "private" / "sample"
PRIVATE_SAMPLE_FILES = ("profile-map.json", "jd.json", "match.json", "questions.json")
DEFAULT_SAMPLE_CV = REPO_ROOT / "CVs" / "ArashMorattab-CV-2026-10.pdf"
STAFF_JD = REPO_ROOT / "JDs" / "staff-platform-sre.md"
REAL_JD_DIR = REPO_ROOT / "JDs"

# Environment names. HOME_ENV and HOST_ENV match tests/conftest.py (some tests import them from `conftest`).
HOME_ENV = "GTJOB_HOME"
HOST_ENV = "GTJOB_HOST"
SAMPLE_CV_ENV = "GTJOB_SAMPLE_CV"
API_KEY_ENV = "ANTHROPIC_API_KEY"
RUN_ID_ENV = "GTJOB_EVAL_RUN_ID"
ALL_JDS_ENV = "GTJOB_EVAL_ALL_JDS"
TOKENS_ENV = "GTJOB_EVAL_TOKENS"
HOST_DETECT_PREFIXES = ("CURSOR_",)
HOST_DETECT_NAMES = ("CLAUDECODE",)

EXIT_OK, EXIT_CHECK_FAILED, EXIT_AWAITING_USER = 0, 1, 6
CLAUDE_PREFLIGHT_TIMEOUT_S = 90
GTJOB_TIMEOUT_S = 1800
RUN_ID_FORMAT = "%Y%m%d-%H%M%S"

for _path in (SCRIPTS_DIR, EVALS_DIR, REPO_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


def clean_env(home: Path | None = None) -> dict[str, str]:
    """os.environ without host-detection variables, pointed at `home` as the workspace root."""
    env = dict(os.environ)
    env.pop(HOST_ENV, None)
    for key in list(env):
        if key.startswith(HOST_DETECT_PREFIXES) or key in HOST_DETECT_NAMES:
            env.pop(key)
    if home is not None:
        env[HOME_ENV] = str(home)
    return env


class Cvt:
    """Runs `cvt.py` as a subprocess against one workspace root."""

    def __init__(self, home: Path) -> None:
        self.home = home
        home.mkdir(parents=True, exist_ok=True)

    def raw(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(CVT_PY), *args], cwd=self.home, env=clean_env(self.home),
                              capture_output=True, text=True, check=False)

    def run(self, *args: str, code: int | tuple[int, ...] = EXIT_OK) -> dict:
        """Run with --json, assert the exit code, return the envelope."""
        proc = self.raw(*args, "--json")
        wanted = (code,) if isinstance(code, int) else code
        assert proc.returncode in wanted, (
            f"cvt {' '.join(args)} exited {proc.returncode}, wanted {wanted}:\n{proc.stdout}\n{proc.stderr}")
        return json.loads(proc.stdout)

    def out(self, run: str) -> Path:
        return self.home / "out" / run

    def json(self, run: str, name: str) -> dict:
        return json.loads((self.out(run) / name).read_text(encoding="utf-8"))

    def attestations(self, person: str) -> list[dict]:
        path = self.home / "profiles" / person / "attestations.json"
        if not path.is_file():
            return []
        return json.loads(path.read_text(encoding="utf-8"))["attestations"]


def seed_to_matched(cvt: Cvt, *, cv: Path, jd: Path, artifacts: Path, slug: str) -> str:
    """init -> ingest -> profile-build -> jd-check -> match-check with pre-made artifacts (no model). Returns the slug."""
    run = cvt.run("init", "--cv", str(cv), "--jd", str(jd), "--slug", slug)["data"]["run_slug"]
    cvt.run("ingest", run)
    shutil.copy(artifacts / "profile-map.json", cvt.out(run) / "profile-map.json")
    cvt.run("profile-build", run)
    shutil.copy(artifacts / "jd.json", cvt.out(run) / "jd.json")
    cvt.run("jd-check", run)
    shutil.copy(artifacts / "match.json", cvt.out(run) / "match.json")
    cvt.run("match-check", run)
    return run


def seed_to_awaiting(cvt: Cvt, *, cv: Path, jd: Path, artifacts: Path, slug: str) -> str:
    """Like seed_to_matched, then `questions` with the golden checkpoint-1 questions (exit 6, awaiting_answers)."""
    run = seed_to_matched(cvt, cv=cv, jd=jd, artifacts=artifacts, slug=slug)
    shutil.copy(artifacts / "questions.json", cvt.out(run) / "questions.json")
    env = cvt.run("questions", run, code=EXIT_AWAITING_USER)
    assert env["stage"] == "awaiting_answers", env
    return run


def run_gtjob(home: Path, *args: str, timeout: int = GTJOB_TIMEOUT_S) -> subprocess.CompletedProcess:
    """Run `gtjob <args>` in-process-equivalent (python -c) with `home` as the workspace. Never uses a TTY."""
    code = "import sys; from gtjob.cli import main; sys.exit(main())"
    return subprocess.run([sys.executable, "-c", code, *args], cwd=home, env=clean_env(home), capture_output=True,
                          text=True, timeout=timeout, check=False, stdin=subprocess.DEVNULL)


def write_answers_yaml(path: Path, *, checkpoint1: dict, followups: object = "default",
                       checkpoint2: object = "approve_all") -> Path:
    """Write an `--answers` YAML (interfaces.md section 12) and return its path."""
    doc = {"checkpoint1": checkpoint1, "followups": followups, "checkpoint2": checkpoint2}
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def sample_cv_file() -> Path | None:
    path = Path(os.environ.get(SAMPLE_CV_ENV, DEFAULT_SAMPLE_CV))
    return path if path.is_file() else None


def private_sample_ready() -> tuple[bool, str]:
    """(ready, reason): the private golden artifacts the sample cases need."""
    missing = [name for name in PRIVATE_SAMPLE_FILES if not (PRIVATE_SAMPLE / name).is_file()]
    if sample_cv_file() is None:
        missing.append("sample CV")
    if not STAFF_JD.is_file():
        missing.append("JDs/staff-platform-sre.md")
    return (not missing, "private sample not available: " + ", ".join(missing))


# ------------------------------------------------------------------ fixtures
@pytest.fixture
def eval_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty workspace root (also the process's GTJOB_HOME, so in-process cvtlib calls use it)."""
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.setenv(HOME_ENV, str(root))
    for key in (HOST_ENV, *HOST_DETECT_NAMES):
        monkeypatch.delenv(key, raising=False)
    for key in list(os.environ):
        if key.startswith(HOST_DETECT_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    return root


@pytest.fixture
def cvt(eval_home: Path) -> Cvt:
    return Cvt(eval_home)


@pytest.fixture(scope="session")
def results_dir() -> Path:
    """`evals/results/<run id>/`, shared by every module in one pytest session. The run id is a timestamp."""
    run_id = os.environ.get(RUN_ID_ENV) or dt.datetime.now().strftime(RUN_ID_FORMAT)
    path = RESULTS_ROOT / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def needs_key() -> None:
    if not os.environ.get(API_KEY_ENV):
        pytest.skip(f"{API_KEY_ENV} is not set")


@pytest.fixture
def sample_cv() -> Path:
    path = sample_cv_file()
    if path is None:
        pytest.skip("private sample CV not present")
    return path


@pytest.fixture
def private_sample() -> Path:
    ready, reason = private_sample_ready()
    if not ready:
        pytest.skip(reason)
    return PRIVATE_SAMPLE


@pytest.fixture(scope="session")
def interaction_cases() -> dict[str, dict]:
    return yaml.safe_load(INTERACTION_CASES.read_text(encoding="utf-8"))


@pytest.fixture
def gtjob() -> Callable[..., subprocess.CompletedProcess]:
    return run_gtjob


@pytest.fixture
def stage_env(needs_key) -> tuple[object, object, Callable]:
    """(client, config, run_stage) from WP-21 (`gtjob.llm`, `gtjob.config`, `gtjob.stages`), built for a real key.

    Skips when WP-21 is not installed or its factory names differ, so a signature drift shows up as a skip reason.
    """
    try:
        from gtjob import config as gt_config
        from gtjob import llm as gt_llm
        from gtjob import stages as gt_stages
    except ImportError as exc:  # pragma: no cover - depends on the build state
        pytest.skip(f"gtjob AI layer not available ({exc})")
    factory = next((getattr(gt_config, name) for name in ("load_config", "load", "Config") if hasattr(gt_config, name)),
                   None)
    if factory is None or not hasattr(gt_llm, "AnthropicClient") or not hasattr(gt_stages, "run_stage"):
        pytest.skip("gtjob.config/llm/stages do not expose load_config()/AnthropicClient/run_stage()")
    return gt_llm.AnthropicClient(), factory(), gt_stages.run_stage
