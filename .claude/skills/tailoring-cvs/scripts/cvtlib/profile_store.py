"""Durable profile store: `profiles/<person-slug>/profile.<cv-sha12>.json` (interfaces.md section 2)."""

from __future__ import annotations

from pathlib import Path

from . import jsonio, paths, schemas, state
from .errors import CvtError, ExitCode

SHA_SHORT = 12
PROFILE_FILE = "profile.json"
PROFILE_PATTERN = "profile.{sha12}.json"
STORE_PROFILE_GLOB = "profile.*.json"
SCHEMA_VERSION = "1"
FIRST_ATTESTATION_SEQ = 1


def cache_name(cv_sha256: str) -> str:
    return PROFILE_PATTERN.format(sha12=cv_sha256[:SHA_SHORT])


def lookup(cv_sha256: str) -> Path | None:
    """The stored profile whose `cv_sha256` equals the argument, or None. Never creates directories."""
    if len(cv_sha256) < SHA_SHORT:
        return None
    root = paths.profiles_dir()
    if not root.is_dir():
        return None
    for candidate in sorted(root.glob(f"*/{cache_name(cv_sha256)}")):
        try:
            data = jsonio.load_json(candidate)
        except CvtError:
            continue
        if isinstance(data, dict) and data.get("cv_sha256") == cv_sha256:
            return candidate
    return None


def latest_for_person(person_slug: str) -> Path | None:
    """Newest stored profile of one person, or None."""
    folder = paths.profiles_dir() / person_slug
    found = sorted(folder.glob(STORE_PROFILE_GLOB), key=lambda p: p.stat().st_mtime) if folder.is_dir() else []
    return found[-1] if found else None


def store(run_dir: Path) -> Path:
    """Copy the run's verified `profile.json` into the store; create an empty attestations file if none exists."""
    run_dir = Path(run_dir)
    st = state.load(run_dir)
    state.require_stage(st, "profiled")
    source = state.require_artifact(run_dir, st, "profile")
    profile = jsonio.load_json(source)
    schemas.require_valid(profile, "profile", source.name)
    slug = profile["person_slug"]
    dest = paths.person_dir(slug) / cache_name(profile["cv_sha256"])
    jsonio.dump_json(profile, dest)
    att_path = paths.attestations_path(slug)
    if not att_path.exists():
        jsonio.dump_json({"schema_version": SCHEMA_VERSION, "person_slug": slug,
                          "next_seq": FIRST_ATTESTATION_SEQ, "attestations": []}, att_path)
    if not st["person_slug"]:
        st["person_slug"] = slug
        state.save(run_dir, st)
    return dest


def load_attestations(person_slug: str) -> list[dict]:
    """Attestations of one person; a missing store means none. Does not create directories."""
    path = paths.profiles_dir() / person_slug / "attestations.json"
    if not path.is_file():
        return []
    data = jsonio.load_json(path)
    return list(data.get("attestations", [])) if isinstance(data, dict) else []
