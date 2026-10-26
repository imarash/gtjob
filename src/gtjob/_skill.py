"""Locate the tailoring-cvs skill's scripts/ dir and put it on sys.path (the CLI imports the skill, never the reverse)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

HOME_ENV = "GTJOB_HOME"
SCRIPTS_REL = Path(".claude", "skills", "tailoring-cvs", "scripts")


def repo_root() -> Path:
    home = os.environ.get(HOME_ENV)
    if home and (Path(home) / SCRIPTS_REL).is_dir():
        return Path(home).resolve()
    for parent in Path(__file__).resolve().parents:
        if (parent / SCRIPTS_REL).is_dir():
            return parent
    raise FileNotFoundError(
        f"cannot find {SCRIPTS_REL}; set {HOME_ENV} to the gtjob repo root",
    )


def ensure_path() -> Path:
    scripts = str(repo_root() / SCRIPTS_REL)
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    return Path(scripts)
