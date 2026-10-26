"""Shared fixtures. The skill's scripts/ dir is put on sys.path so tests can import `cvtlib`."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / ".claude" / "skills" / "tailoring-cvs"
SCRIPTS_DIR = SKILL_DIR / "scripts"
CVT_PY = SCRIPTS_DIR / "cvt.py"
DEFAULT_SAMPLE_CV = REPO_ROOT / "CVs" / "ArashMorattab-CV-2026-10.pdf"
SAMPLE_CV_ENV = "GTJOB_SAMPLE_CV"
HOME_ENV = "GTJOB_HOME"
HOST_ENV = "GTJOB_HOST"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty workspace root: GTJOB_HOME points at it, GTJOB_HOST is cleared."""
    root = tmp_path / "ws"
    root.mkdir()
    monkeypatch.setenv(HOME_ENV, str(root))
    monkeypatch.delenv(HOST_ENV, raising=False)
    return root


@pytest.fixture
def sample_cv_path() -> Path:
    path = Path(os.environ.get(SAMPLE_CV_ENV, DEFAULT_SAMPLE_CV))
    if not path.is_file():
        pytest.skip(f"private sample CV not present ({path})")
    return path


@pytest.fixture
def run_cvt(workspace: Path):
    """Run cvt.py as a subprocess with cwd = workspace; returns CompletedProcess (text mode)."""

    def _run(*args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, HOME_ENV: str(workspace)}
        env.pop(HOST_ENV, None)
        return subprocess.run(
            [sys.executable, str(CVT_PY), *args], cwd=workspace, env=env,
            capture_output=True, text=True, check=False,
        )

    return _run
