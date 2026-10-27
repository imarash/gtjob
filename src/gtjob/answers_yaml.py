"""Parse and validate the `--answers` YAML file (interfaces.md section 12).

The file maps to the same inputs a host question tool produces: choice-id lists become a deterministic `--select`
round, and strings are free text for the `answer_parse` stage. Nothing here talks to the API.

```yaml
checkpoint1:
  q-1: [service_mesh, typescript]
  q-3: "add slo and error budget to the sre related cv items"
  default_rest: true
followups: default
checkpoint2: approve_all
```
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from gtjob import _skill

_skill.ensure_path()

from cvtlib.errors import CvtError, ExitCode  # noqa: E402

KEY_CP1, KEY_FOLLOWUPS, KEY_CP2, KEY_DEFAULT_REST = "checkpoint1", "followups", "checkpoint2", "default_rest"
TOP_LEVEL_KEYS = (KEY_CP1, KEY_FOLLOWUPS, KEY_CP2, KEY_DEFAULT_REST)
DEFAULT_WORD = "default"
APPROVE_ALL_WORDS = ("approve_all", "approve-all", "approve")
QUESTION_ID_RE = re.compile(r"^q-[0-9]+$")
ERR_ID = "E_ANSWERS_YAML"
ERR_UNKNOWN_QUESTION = "E_ANSWERS_UNKNOWN_QUESTION"


@dataclass(frozen=True)
class Section:
    """One checkpoint-1 or follow-up block: selections, free text, and whether the rest take their defaults."""

    choices: dict[str, list[str]] = field(default_factory=dict)  # q-N -> choice ids ([] = skip)
    texts: dict[str, str] = field(default_factory=dict)  # q-N -> free text
    default_rest: bool = False

    def question_ids(self) -> list[str]:
        return [*self.choices, *self.texts]


@dataclass(frozen=True)
class Checkpoint2:
    approve_all: bool = False
    instructions: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnswersSpec:
    checkpoint1: Section | None = None
    followups: Section | None = None
    checkpoint2: Checkpoint2 | None = None

    def section(self, kind: str) -> Section | None:
        return self.followups if kind == KEY_FOLLOWUPS else self.checkpoint1


def _error(message: str, hint: str) -> CvtError:
    return CvtError(ExitCode.USAGE, ERR_ID, message, hint=hint)


def _section(name: str, raw: object, top_default_rest: bool) -> Section:
    if raw == DEFAULT_WORD:
        return Section(default_rest=True)
    if not isinstance(raw, dict):
        raise _error(f"{name} must be a mapping of question ids or the word '{DEFAULT_WORD}'",
                     f"for example:\n{name}:\n  q-1: [choice_id]\n  default_rest: true")
    choices: dict[str, list[str]] = {}
    texts: dict[str, str] = {}
    default_rest = top_default_rest
    for key, value in raw.items():
        if key == KEY_DEFAULT_REST:
            if not isinstance(value, bool):
                raise _error(f"{name}.{KEY_DEFAULT_REST} must be true or false", f"write {KEY_DEFAULT_REST}: true")
            default_rest = value
            continue
        if not isinstance(key, str) or not QUESTION_ID_RE.match(key):
            raise _error(f"{name}: '{key}' is not a question id", "use ids like q-1, or the key default_rest")
        if isinstance(value, list):
            if not all(isinstance(v, str) and v.strip() for v in value):
                raise _error(
                    f"{name}.{key}: choice ids must be non-empty strings",
                    "quote ids that YAML would read as booleans or numbers, for example \"yes\"",
                )
            choices[key] = [v.strip() for v in value]
        elif isinstance(value, str) and value.strip():
            texts[key] = value.strip()
        else:
            raise _error(f"{name}.{key} must be a list of choice ids or a non-empty string",
                         "use [] to skip a question, a list of ids to choose, or text to answer in words")
    return Section(choices=choices, texts=texts, default_rest=default_rest)


def _checkpoint2(raw: object) -> Checkpoint2:
    if isinstance(raw, str) and raw.strip().lower() in APPROVE_ALL_WORDS:
        return Checkpoint2(approve_all=True)
    if isinstance(raw, list) and raw and all(isinstance(v, str) and v.strip() for v in raw):
        return Checkpoint2(instructions=tuple(v.strip() for v in raw))
    raise _error(
        f"{KEY_CP2} must be 'approve_all' or a list of change-request sentences",
        f"for example: {KEY_CP2}: approve_all",
    )


def parse(text: str, source: str = "answers") -> AnswersSpec:
    """Parse YAML text. Raises `CvtError(USAGE)` (exit 2) on bad syntax, unknown keys or malformed values."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise _error(f"{source} is not valid YAML: {exc}", "fix the YAML syntax, then rerun") from None
    if raw is None:
        raise _error(f"{source} is empty", f"add at least one of: {', '.join(TOP_LEVEL_KEYS)}")
    if not isinstance(raw, dict):
        raise _error(f"{source} must be a mapping at the top level", f"use keys: {', '.join(TOP_LEVEL_KEYS)}")
    unknown = [str(k) for k in raw if k not in TOP_LEVEL_KEYS]
    if unknown:
        raise _error(f"{source}: unknown key(s) {', '.join(unknown)}", f"allowed keys: {', '.join(TOP_LEVEL_KEYS)}")
    top_default_rest = raw.get(KEY_DEFAULT_REST, False)
    if not isinstance(top_default_rest, bool):
        raise _error(f"{KEY_DEFAULT_REST} must be true or false", f"write {KEY_DEFAULT_REST}: true")
    return AnswersSpec(
        checkpoint1=_section(KEY_CP1, raw[KEY_CP1], top_default_rest) if KEY_CP1 in raw else None,
        followups=_section(KEY_FOLLOWUPS, raw[KEY_FOLLOWUPS], top_default_rest) if KEY_FOLLOWUPS in raw else None,
        checkpoint2=_checkpoint2(raw[KEY_CP2]) if KEY_CP2 in raw else None,
    )


def load(path: str | Path) -> AnswersSpec:
    """Read and parse an answers file; a missing or unreadable file is a usage error (exit 2)."""
    file = Path(path)
    try:
        text = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _error(f"cannot read answers file {file}: {exc}", "pass the path to a UTF-8 YAML file") from None
    return parse(text, source=file.name)


def check_question_ids(section: Section, known_ids: set[str]) -> None:
    """Every id in `section` must exist in questions.json; unknown ids are a usage error (exit 2)."""
    unknown = [q for q in section.question_ids() if q not in known_ids]
    if unknown:
        raise CvtError(
            ExitCode.USAGE, ERR_UNKNOWN_QUESTION, f"unknown question id(s): {', '.join(unknown)}",
            hint=f"this run has: {', '.join(sorted(known_ids)) or 'no questions'}",
        )


def free_text_reply(section: Section) -> str:
    """The `answer_parse` reply for a section's free-text answers: one `q-N: text` line each."""
    return "\n".join(f"{qid}: {text}" for qid, text in section.texts.items())
