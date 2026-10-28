"""Authoring-rule linter and zip packager for the skill folders (`cvt lint-skill`, `cvt package-skill`)."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import paths

SKILL_FILE = "SKILL.md"
FRONTMATTER_FENCE = "---"
REFERENCES_DIR = "references"
LINKABLE_DIRS = (REFERENCES_DIR, "scripts", "assets")
SCHEMAS_SUBPATH = ("assets", "schemas")
SCHEMA_GLOB = "*.schema.json"
CONTRACTS_SUBPATH = ("plan", "contracts")
CORE_HEADING = "## Core"
CONTENTS_HEADING = "## Contents"
SECTION_PREFIX = "## "

PORTABLE_KEYS = frozenset({"name", "description", "license", "compatibility", "metadata"})
WRAPPER_EXTRA_KEYS = frozenset({"argument-hint", "disable-model-invocation", "allowed-tools"})
NAME_MAX = 64
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NAME_FORBIDDEN_WORDS = ("claude", "anthropic")
DESCRIPTION_MAX = 1024
DESCRIPTION_WARN = 700
LISTING_MAX = 1536
LISTING_EXTRA_KEY = "when_to_use"
BODY_MAX_LINES = 500
CORE_BODY_MAX_LINES = 200
REFERENCE_TOC_THRESHOLD = 100
CORE_SECTION_MAX_LINES = 60
CORE_REQUIRED_PATTERNS = (
    "stage-*.md", "checkpoint-questions.md", "answer-parsing.md", "change-requests.md",
    "style-guide.md", "truthfulness.md", "critic-rubric.md",
)
FIRST_PERSON_STARTS = ("i ", "you ", "we ", "use this")
FORBIDDEN_STRINGS = ("$" + "ARGUMENTS", "${" + "CLAUDE_")
TEXT_SUFFIXES = frozenset({".md", ".py", ".txt", ".json", ".typ", ".toml", ".yaml", ".yml"})
IGNORED_PARTS = frozenset({"__pycache__", ".DS_Store"})
IGNORED_SUFFIXES = frozenset({".pyc"})
WRAPPER_NAMES = ("tailor-cv", "cv-continue", "cv-status", "cv-render", "cv-profile", "cv-polish")
WRAPPER_REQUIRED_KEY = "disable-model-invocation"
WRAPPER_REQUIRED_VALUE = "true"
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:")
YAML_PLAIN_BREAKERS = (": ", " #")
SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
ZIP_ROOT = "tailoring-cvs"
ZIP_NAME = "tailoring-cvs.zip"


@dataclass(frozen=True)
class Finding:
    severity: str
    where: str
    message: str


def parse_frontmatter(text: str) -> tuple[dict, str, str]:
    """Return (keys, body, error). A small YAML subset: scalars, quotes, one nested mapping level."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return {}, text, "SKILL.md must start with a '---' frontmatter block"
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == FRONTMATTER_FENCE), -1)
    if end < 0:
        return {}, text, "frontmatter is not closed with '---'"
    keys: dict = {}
    current = ""
    for raw in lines[1:end]:
        if not raw.strip():
            continue
        if raw[0] in " \t":
            if current and isinstance(keys.get(current), dict):
                sub, _, value = raw.strip().partition(":")
                keys[current][sub.strip()] = _unquote(value)
            continue
        key, sep, value = raw.partition(":")
        if not sep:
            return {}, "", f"frontmatter line is not 'key: value': {raw!r}"
        key, current = key.strip(), key.strip()
        keys[key] = {} if not value.strip() else _unquote(value)
        if value.strip() and not _is_quoted(value) and any(b in value.strip() for b in YAML_PLAIN_BREAKERS):
            keys.setdefault("__yaml_errors__", []).append(key)
    return keys, "\n".join(lines[end + 1:]), ""


def _is_quoted(value: str) -> bool:
    v = value.strip()
    return len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'"


def _unquote(value: str) -> str:
    v = value.strip()
    return v[1:-1] if _is_quoted(v) else v


def _text_files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix in TEXT_SUFFIXES and not IGNORED_PARTS.intersection(p.parts)
    )


def _error(where: str, message: str) -> Finding:
    return Finding(SEVERITY_ERROR, where, message)


def _warn(where: str, message: str) -> Finding:
    return Finding(SEVERITY_WARNING, where, message)


def _check_name(name: str, folder: str) -> list[Finding]:
    found: list[Finding] = []
    if not name:
        return [_error("name", "missing 'name' in frontmatter")]
    if name != folder:
        found.append(_error("name", f"name '{name}' must equal the folder name '{folder}'"))
    if len(name) > NAME_MAX:
        found.append(_error("name", f"name is {len(name)} characters; the limit is {NAME_MAX}"))
    if not NAME_PATTERN.match(name):
        found.append(_error("name", "name must be [a-z0-9-] with no leading, trailing, or double hyphens"))
    for word in NAME_FORBIDDEN_WORDS:
        if word in name:
            found.append(_error("name", f"name must not contain '{word}'"))
    return found


def _check_description(keys: dict, wrapper: bool) -> list[Finding]:
    desc = keys.get("description", "")
    if not isinstance(desc, str) or not desc.strip():
        return [_error("description", "missing or empty 'description'")]
    found: list[Finding] = []
    if len(desc) > DESCRIPTION_MAX:
        found.append(_error("description", f"description is {len(desc)} characters; the limit is {DESCRIPTION_MAX}"))
    if "<" in desc or ">" in desc:
        found.append(_error("description", "description must not contain '<' or '>'"))
    if desc.lower().startswith(FIRST_PERSON_STARTS):
        found.append(_error("description", "description must be third person (no leading 'I', 'You', 'Use this')"))
    if not wrapper and len(desc) > DESCRIPTION_WARN:
        found.append(_warn("description", f"description is {len(desc)} characters; aim for at most {DESCRIPTION_WARN}"))
    extra = keys.get(LISTING_EXTRA_KEY, "")
    listing = len(desc) + (len(extra) if isinstance(extra, str) else 0)
    if listing > LISTING_MAX:
        found.append(_error("description", f"description plus {LISTING_EXTRA_KEY} is {listing}; the limit is {LISTING_MAX}"))
    return found


def _check_keys(keys: dict, wrapper: bool) -> list[Finding]:
    allowed = PORTABLE_KEYS | (WRAPPER_EXTRA_KEYS if wrapper else frozenset())
    found = [
        _error("frontmatter", f"unknown key '{k}' (allowed: {', '.join(sorted(allowed))})")
        for k in keys if k != "__yaml_errors__" and k not in allowed
    ]
    found += [_error("frontmatter", f"'{k}' has an unquoted value containing ': ' or ' #'; quote it")
              for k in keys.get("__yaml_errors__", [])]
    if wrapper and str(keys.get(WRAPPER_REQUIRED_KEY, "")).lower() != WRAPPER_REQUIRED_VALUE:
        found.append(_error("frontmatter", f"wrapper skills must set {WRAPPER_REQUIRED_KEY}: {WRAPPER_REQUIRED_VALUE}"))
    return found


def _links(text: str) -> list[str]:
    return [m.group(1) for m in LINK_PATTERN.finditer(text)
            if not m.group(1).startswith(EXTERNAL_PREFIXES) and not m.group(1).startswith("#")]


def _check_body_links(skill: Path, body: str) -> list[Finding]:
    found: list[Finding] = []
    for link in _links(body):
        target = link.split("#", 1)[0]
        parts = Path(target).parts
        if not parts or parts[0] not in LINKABLE_DIRS:
            found.append(_error(SKILL_FILE, f"link '{link}' must point into {', '.join(LINKABLE_DIRS)}"))
        elif not (skill / target).exists():
            found.append(_error(SKILL_FILE, f"link '{link}' does not resolve"))
        elif parts[0] == REFERENCES_DIR and len(parts) != 2:
            found.append(_error(SKILL_FILE, f"link '{link}' is nested; references are linked one level deep"))
    return found


def _core_section_lines(lines: list[str]) -> int | None:
    """Number of lines in the `## Core` section, or None when the file has none."""
    start = next((i for i, ln in enumerate(lines) if ln.strip() == CORE_HEADING), -1)
    if start < 0:
        return None
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(SECTION_PREFIX)), len(lines))
    return end - start


def _check_references(skill: Path) -> list[Finding]:
    refs = skill / REFERENCES_DIR
    if not refs.is_dir():
        return []
    found: list[Finding] = []
    for ref in sorted(refs.glob("*.md")):
        where = f"{REFERENCES_DIR}/{ref.name}"
        text = ref.read_text(encoding="utf-8")
        lines = text.splitlines()
        if len(lines) > REFERENCE_TOC_THRESHOLD and not any(ln.strip() == CONTENTS_HEADING for ln in lines):
            found.append(_error(where, f"{len(lines)} lines but no '{CONTENTS_HEADING}' section"))
        for link in _links(text):
            if link.split("#", 1)[0].endswith(".md"):
                found.append(_error(where, f"links to another file ('{link}'); references link nowhere else"))
        core = _core_section_lines(lines)
        required = any(ref.match(p) for p in CORE_REQUIRED_PATTERNS)
        if core is None and required:
            found.append(_error(where, f"missing '{CORE_HEADING}' section"))
        elif core is not None and core > CORE_SECTION_MAX_LINES:
            found.append(_error(where, f"'{CORE_HEADING}' is {core} lines; the limit is {CORE_SECTION_MAX_LINES}"))
    return found


def _check_schemas(skill: Path, contracts: Path) -> list[Finding]:
    if not contracts.is_dir():
        return []
    assets = skill.joinpath(*SCHEMAS_SUBPATH)
    found: list[Finding] = []
    for source in sorted(contracts.glob(SCHEMA_GLOB)):
        copy = assets / source.name
        where = "/".join((*SCHEMAS_SUBPATH, source.name))
        if not copy.is_file():
            found.append(_error(where, f"missing; copy it from {'/'.join(CONTRACTS_SUBPATH)}"))
        elif copy.read_bytes() != source.read_bytes():
            found.append(_error(where, f"differs from {'/'.join(CONTRACTS_SUBPATH)}/{source.name}"))
    return found


def _check_forbidden(skill: Path) -> list[Finding]:
    found: list[Finding] = []
    for path in _text_files(skill):
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in FORBIDDEN_STRINGS:
            if needle in text:
                found.append(_error(path.relative_to(skill).as_posix(), f"contains '{needle}' (host-specific substitution)"))
    return found


def lint_skill(skill_dir: Path, wrapper: bool = False, contracts_dir: Path | None = None) -> list[Finding]:
    """Apply every authoring rule to one skill folder. Errors fail the lint; warnings do not."""
    skill = Path(skill_dir)
    skill_file = skill / SKILL_FILE
    if not skill_file.is_file():
        return [_error(SKILL_FILE, f"not found in {skill}")]
    keys, body, problem = parse_frontmatter(skill_file.read_text(encoding="utf-8"))
    if problem:
        return [_error(SKILL_FILE, problem)]
    found = _check_keys(keys, wrapper)
    found += _check_name(str(keys.get("name", "")), skill.name)
    found += _check_description(keys, wrapper)
    body_lines = len(body.splitlines())
    if body_lines >= BODY_MAX_LINES:
        found.append(_error(SKILL_FILE, f"body is {body_lines} lines; it must stay under {BODY_MAX_LINES}"))
    elif not wrapper and body_lines > CORE_BODY_MAX_LINES:
        found.append(_error(SKILL_FILE, f"body is {body_lines} lines; this skill's cap is {CORE_BODY_MAX_LINES}"))
    if any(p.name.lower() == "readme.md" for p in skill.rglob("*") if not IGNORED_PARTS.intersection(p.parts)):
        found.append(_error("README.md", "skill folders must not contain a README.md"))
    found += _check_forbidden(skill)
    if not wrapper:
        found += _check_body_links(skill, body)
        found += _check_references(skill)
        contracts = contracts_dir if contracts_dir is not None else paths.workspace_root().joinpath(*CONTRACTS_SUBPATH)
        found += _check_schemas(skill, contracts)
    return found


def _skip_in_zip(path: Path) -> bool:
    return bool(IGNORED_PARTS.intersection(path.parts)) or path.suffix in IGNORED_SUFFIXES


def build_zip(skill_dir: Path, out_dir: Path) -> tuple[Path, int, int]:
    """Zip the skill as `tailoring-cvs/...`; return (zip path, bytes, file count)."""
    skill = Path(skill_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / ZIP_NAME
    files = sorted(p for p in skill.rglob("*") if p.is_file() and not _skip_in_zip(p.relative_to(skill)))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, f"{ZIP_ROOT}/{path.relative_to(skill).as_posix()}")
    return target, target.stat().st_size, len(files)


def verify_zip(zip_path: Path) -> list[Finding]:
    """Re-read the zip and check the packaged SKILL.md frontmatter and that no run data is inside."""
    found: list[Finding] = []
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        entry = f"{ZIP_ROOT}/{SKILL_FILE}"
        if entry not in names:
            return [_error(zip_path.name, f"{entry} is missing from the zip")]
        keys, _, problem = parse_frontmatter(zf.read(entry).decode("utf-8"))
    if problem:
        found.append(_error(entry, problem))
    elif keys.get("name") != ZIP_ROOT or not keys.get("description"):
        found.append(_error(entry, f"packaged frontmatter must have name '{ZIP_ROOT}' and a description"))
    for name in names:
        if name.split("/")[1:2] in (["out"], ["profiles"]):
            found.append(_error(name, "personal-data folder inside the zip"))
    return found
