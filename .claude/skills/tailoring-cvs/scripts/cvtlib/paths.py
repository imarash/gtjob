"""Filesystem locations. Nothing else in cvtlib hard-codes a path."""

from __future__ import annotations

import datetime
import json
import os
import re
import unicodedata
from pathlib import Path

from .errors import CvtError, ExitCode

SKILL_ROOT: Path = Path(__file__).resolve().parent.parent.parent
HOME_ENV = "GTJOB_HOME"
LATEST_RUN = "latest"
STATE_FILE = "state.json"
DEFAULT_SLUG_MAX_LEN = 48
FALLBACK_STEM = "jd"
COLLISION_START = 2


def workspace_root() -> Path:
    home = os.environ.get(HOME_ENV)
    return Path(home).resolve() if home else Path.cwd()


def out_dir() -> Path:
    return workspace_root() / "out"


def profiles_dir() -> Path:
    return workspace_root() / "profiles"


def asset(*parts: str) -> Path:
    return SKILL_ROOT.joinpath("assets", *parts)


def schema_file(name: str) -> Path:
    return asset("schemas", f"{name}.schema.json")


def person_dir(person_slug: str) -> Path:
    path = profiles_dir() / person_slug
    path.mkdir(parents=True, exist_ok=True)
    return path


def attestations_path(person_slug: str) -> Path:
    return person_dir(person_slug) / "attestations.json"


def slugify(text: str, max_len: int = DEFAULT_SLUG_MAX_LEN) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    return slug[:max_len].strip("-")


def new_run_slug(stem: str, today: datetime.date | None = None) -> str:
    day = today or datetime.date.today()
    clean = slugify(stem) or FALLBACK_STEM
    base = f"{day:%Y%m%d}-{clean}"
    root = out_dir()
    candidate, n = base, COLLISION_START
    while (root / candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def _state_updated_at(state_path: Path) -> str:
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return str(data.get("updated_at", ""))
    except (OSError, ValueError, AttributeError):
        return ""


def latest_run() -> Path | None:
    best: tuple[str, float, Path] | None = None
    for state_path in out_dir().glob(f"*/{STATE_FILE}"):
        key = (_state_updated_at(state_path), state_path.stat().st_mtime, state_path.parent)
        if best is None or key[:2] > best[:2]:
            best = key
    return best[2] if best else None


def resolve_run(run: str | Path | None) -> Path:
    if run is None or str(run) == LATEST_RUN:
        found = latest_run()
        if found is None:
            raise CvtError(
                ExitCode.STATE, "E_RUN_NOT_FOUND", f"no runs found in {out_dir()}",
                hint="start one with: cvt init --cv PATH --jd PATH",
            )
        return found
    text = str(run)
    candidates = [Path(text)] if (os.sep in text or text.startswith(".")) else []
    candidates.append(out_dir() / text)
    for cand in candidates:
        if cand.is_dir():
            return cand.resolve()
    raise CvtError(
        ExitCode.STATE, "E_RUN_NOT_FOUND", f"run '{text}' not found in {out_dir()}",
        hint="list runs with: cvt status latest, or pass a run slug, a run directory, or 'latest'",
    )
