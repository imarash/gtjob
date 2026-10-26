from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from conftest import REPO_ROOT, SKILL_DIR
from cvtlib import schemas

CONTRACTS = REPO_ROOT / "plan" / "contracts"
ASSETS = SKILL_DIR / "assets" / "schemas"
FORBIDDEN_KEYWORDS = {
    "minLength", "maxLength", "minimum", "maximum", "multipleOf", "oneOf", "not", "if", "patternProperties",
}
ALLOWED_MIN_ITEMS = (0, 1)


def _walk(node, path="$"):
    """Yield (path, schema-node) for every dict that sits in a schema position."""
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            if key in ("properties", "$defs"):
                for name, sub in value.items():
                    yield from _walk(sub, f"{path}.{name}")
            elif key in ("items", "additionalProperties", "not"):
                yield from _walk(value, f"{path}.{key}")
            elif key in ("anyOf", "allOf", "oneOf"):
                for i, sub in enumerate(value):
                    yield from _walk(sub, f"{path}.{key}[{i}]")


def test_fifteen_schemas():
    assert len(schemas.SCHEMA_NAMES) == 15
    assert {"profile-map", "tailor-plan"} <= set(schemas.SCHEMA_NAMES)
    on_disk = {p.name.removesuffix(".schema.json") for p in ASSETS.glob("*.schema.json")}
    assert on_disk == set(schemas.SCHEMA_NAMES)


@pytest.mark.parametrize("name", schemas.SCHEMA_NAMES)
def test_schema_is_valid(name):
    Draft202012Validator.check_schema(schemas.load_schema(name))


@pytest.mark.parametrize("name", schemas.SCHEMA_NAMES)
def test_structured_output_lint(name):
    for path, node in _walk(schemas.load_schema(name)):
        if node.get("type") == "object" or "properties" in node:
            assert node.get("additionalProperties") is False, f"{name} {path}: object not closed"
            assert sorted(node.get("required", [])) == sorted(node.get("properties", {})), (
                f"{name} {path}: required != property keys"
            )
        assert not isinstance(node.get("type"), list), f"{name} {path}: type array"
        assert not (FORBIDDEN_KEYWORDS & set(node)), f"{name} {path}: forbidden {FORBIDDEN_KEYWORDS & set(node)}"
        if "minItems" in node:
            assert node["minItems"] in ALLOWED_MIN_ITEMS, f"{name} {path}: minItems {node['minItems']}"


@pytest.mark.parametrize("name", schemas.SCHEMA_NAMES)
def test_asset_copy_is_byte_identical(name):
    filename = f"{name}.schema.json"
    assert (ASSETS / filename).read_bytes() == (CONTRACTS / filename).read_bytes()


def test_validate_reports_sorted_paths():
    problems = schemas.validate({"schema_version": "2"}, "state")
    assert problems and all(p.startswith("$") for p in problems)
    assert problems == sorted(problems, key=lambda p: p.split(": ")[0])
    assert any(p.startswith("$.schema_version") for p in problems)


def test_require_valid_raises_check_failed():
    from cvtlib.errors import CvtError, ExitCode

    with pytest.raises(CvtError) as info:
        schemas.require_valid({}, "state", "state.json")
    assert info.value.code == ExitCode.CHECK_FAILED
    assert info.value.err_id == "E_SCHEMA"
    assert info.value.violations[0]["code"] == "schema"


def test_api_schema_drops_ids_and_subschema_keeps_defs():
    full = schemas.load_schema("validation")
    api = schemas.api_schema(full)
    assert "$schema" not in api and "$id" not in api and "$schema" in full
    sub = schemas.subschema("validation", "violation")
    assert "$defs" in sub and sub["type"] == "object"
    json.dumps(sub)
