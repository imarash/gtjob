"""Load and apply the JSON Schemas in assets/schemas/."""

from __future__ import annotations

import copy
import functools
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from . import jsonio, paths
from .errors import CvtError, ExitCode

SCHEMA_NAMES = (
    "profile", "profile-map", "attestations", "jd", "match", "questions", "answers", "edits",
    "tailor-plan", "tailored", "render-model", "fit", "validation", "critique", "state",
)
API_DROPPED_KEYS = ("$schema", "$id")
SCHEMA_CODE = "schema"


@functools.lru_cache(maxsize=None)
def _load_cached(name: str) -> dict:
    if name not in SCHEMA_NAMES:
        raise CvtError(
            ExitCode.USAGE, "E_SCHEMA_UNKNOWN", f"unknown schema '{name}'",
            hint=f"valid names: {', '.join(SCHEMA_NAMES)}",
        )
    return jsonio.load_json(paths.schema_file(name))


def load_schema(name: str) -> dict:
    return copy.deepcopy(_load_cached(name))


def _format_path(parts: list[Any]) -> str:
    out = "$"
    for part in parts:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


@functools.lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(_load_cached(name), format_checker=FormatChecker())


def validate(obj: Any, name: str) -> list[str]:
    """Return `"$.path: message"` strings sorted by path; empty means valid."""
    errors = sorted(
        _validator(name).iter_errors(obj),
        key=lambda e: (_format_path(list(e.absolute_path)), e.message),
    )
    return [f"{_format_path(list(e.absolute_path))}: {e.message}" for e in errors]


def to_violations(messages: list[str]) -> list[dict]:
    """Convert `validate` strings to validation.schema.json violation objects."""
    out = []
    for msg in messages:
        where, _, text = msg.partition(": ")
        out.append({"code": SCHEMA_CODE, "item_id": where, "message": text or msg})
    return out


def require_valid(obj: Any, name: str, label: str) -> None:
    problems = validate(obj, name)
    if problems:
        raise CvtError(
            ExitCode.CHECK_FAILED, "E_SCHEMA",
            f"{label} does not match the {name} schema ({len(problems)} violations)",
            hint=f"first problem: {problems[0]}. Patch only the listed items and rerun",
            violations=to_violations(problems),
        )


def subschema(name: str, def_name: str) -> dict:
    schema = load_schema(name)
    defs = schema.get("$defs", {})
    if def_name not in defs:
        raise CvtError(
            ExitCode.INTERNAL, "E_SCHEMA_DEF", f"{name} schema has no $defs/{def_name}",
            hint=f"available: {', '.join(sorted(defs))}",
        )
    return {"$defs": defs, **defs[def_name]}


def api_schema(schema: dict) -> dict:
    out = copy.deepcopy(schema)
    for key in API_DROPPED_KEYS:
        out.pop(key, None)
    return out
