"""JSON helpers: atomic writes, hashes, timestamps."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .errors import CvtError, ExitCode

JSON_INDENT = 2
HASH_CHUNK_BYTES = 1 << 20


def now_iso() -> str:
    """UTC ISO-8601 with `Z`, seconds precision."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise CvtError(
            ExitCode.INPUT, "E_FILE_NOT_FOUND", f"{path} not found",
            hint="check the path, or create the file first",
        ) from None
    except (OSError, UnicodeDecodeError) as exc:
        raise CvtError(
            ExitCode.INPUT, "E_FILE_UNREADABLE", f"cannot read {path}: {exc}",
            hint="the file must be UTF-8 text",
        ) from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise CvtError(
            ExitCode.INPUT, "E_JSON",
            f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}): {exc.msg}",
            hint=f"fix the JSON syntax near line {exc.lineno} and rerun",
        ) from None


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def dump_json(obj: Any, path: Path) -> str:
    """Write pretty JSON atomically (temp file + rename). Returns the SHA-256 of the bytes written."""
    data = (json.dumps(obj, indent=JSON_INDENT, ensure_ascii=False) + "\n").encode("utf-8")
    _atomic_write(Path(path), data)
    return sha256_bytes(data)


def append_jsonl(path: Path, obj: Any) -> None:
    """Append one minified JSON line with a single write call, flushed and fsynced."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)
