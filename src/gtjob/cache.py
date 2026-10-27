"""Local LLM response cache: `.cache/gtjob/llm/<sha256>.json` (interfaces.md section 12).

The key covers everything that can change the answer: model, system prompt, prior turns, user content, schema,
max_tokens and the thinking budget. `--no-cache` skips reads but still writes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from gtjob import _skill

_skill.ensure_path()

from cvtlib import jsonio, paths  # noqa: E402

CACHE_REL = Path(".cache", "gtjob", "llm")
KEY_SEPARATORS = (",", ":")


def cache_dir(root: Path | None = None) -> Path:
    return (Path(root) if root is not None else paths.workspace_root()) / CACHE_REL


def cache_key(
    *, model: str, system: list[dict], blocks: list[dict], history: list[dict], schema: dict, max_tokens: int,
    thinking_budget: int = 0,
) -> str:
    payload = {
        "model": model, "system": system, "history": history, "blocks": blocks, "schema": schema,
        "max_tokens": max_tokens, "thinking_budget": thinking_budget,
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=KEY_SEPARATORS)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LLMCache:
    def __init__(self, root: Path | None = None, *, read: bool = True) -> None:
        self.root = Path(root) if root is not None else cache_dir()
        self.read = read

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict | None:
        """The cached `{"response": dict, "usage": dict}` entry, or None (always None when reads are disabled)."""
        path = self._path(key)
        if not self.read or not path.is_file():
            return None
        try:
            entry = jsonio.load_json(path)
        except Exception:  # noqa: BLE001 - a corrupt cache file is just a miss
            return None
        return entry if isinstance(entry, dict) and isinstance(entry.get("response"), dict) else None

    def put(self, key: str, response: dict, usage: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        jsonio.dump_json({"key": key, "response": response, "usage": usage}, self._path(key))
