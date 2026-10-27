"""Model resolution and per-stage limits for the AI stages (interfaces.md sections 12 and 14.6).

Precedence for a stage's model: `--model STAGE=ID` > env `GTJOB_MODEL_<STAGE>` > `gtjob.toml [models]` > routing default.
`max_tokens` comes from the skill's `assets/budgets.json`; thinking is off unless `gtjob.toml [thinking]` enables it.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from gtjob import _skill

_skill.ensure_path()

from cvtlib import briefs, paths  # noqa: E402
from cvtlib.errors import CvtError, ExitCode  # noqa: E402

STAGES = ("profile", "jd", "match", "questions", "answer_parse", "tailor", "change_request", "critic")
FIX_STAGE = "fix"

MODEL_HAIKU = "claude-haiku-5-5"
MODEL_SONNET = "claude-sonnet-5-5"
MODEL_OPUS = "claude-opus-5-5"
DEFAULT_MODELS: dict[str, str] = {
    "profile": MODEL_SONNET,
    "jd": MODEL_HAIKU,
    "match": MODEL_SONNET,
    "questions": MODEL_SONNET,
    "answer_parse": MODEL_HAIKU,
    "tailor": MODEL_SONNET,
    "change_request": MODEL_HAIKU,
    "critic": MODEL_OPUS,
}
ESCALATION_MODEL = MODEL_SONNET  # a failed check on a Haiku-default stage re-runs once here (section 14.6)

CONFIG_FILE = "gtjob.toml"
ENV_MODEL_PREFIX = "GTJOB_MODEL_"
MODEL_ARG_SEP = "="
TOML_MODELS, TOML_THINKING = "models", "thinking"
DEFAULT_THINKING_BUDGET = 1024  # tokens, used when gtjob.toml sets `stage = true`
MIN_THINKING_BUDGET = 1024  # API minimum for extended thinking


def _bad_stage(name: str, where: str) -> CvtError:
    return CvtError(
        ExitCode.USAGE, "E_MODEL_STAGE", f"unknown stage '{name}' in {where}",
        hint=f"use one of: {', '.join(STAGES)}",
    )


def parse_model_args(items: Iterable[str]) -> dict[str, str]:
    """`--model STAGE=ID` (repeatable) -> {stage: id}."""
    out: dict[str, str] = {}
    for item in items:
        stage, sep, model = item.partition(MODEL_ARG_SEP)
        stage, model = stage.strip().lower(), model.strip()
        if not sep or not model:
            raise CvtError(ExitCode.USAGE, "E_MODEL_ARG", f"bad --model value '{item}'",
                           hint="use --model STAGE=MODEL_ID, for example --model tailor=claude-opus-5-5")
        if stage not in STAGES:
            raise _bad_stage(stage, "--model")
        out[stage] = model
    return out


def _read_toml(root: Path) -> dict:
    path = root / CONFIG_FILE
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise CvtError(ExitCode.INPUT, "E_CONFIG", f"cannot read {path.name}: {exc}",
                       hint=f"fix the TOML syntax in {path} or delete the file") from None


def _toml_models(table: object) -> dict[str, str]:
    out: dict[str, str] = {}
    for stage, model in (table if isinstance(table, dict) else {}).items():
        if stage not in STAGES:
            raise _bad_stage(stage, f"{CONFIG_FILE} [{TOML_MODELS}]")
        if not isinstance(model, str) or not model:
            raise CvtError(ExitCode.INPUT, "E_CONFIG", f"{CONFIG_FILE} [{TOML_MODELS}] {stage} must be a model id string",
                           hint=f'for example: {stage} = "{DEFAULT_MODELS[stage]}"')
        out[stage] = model
    return out


def _toml_thinking(table: object) -> dict[str, int]:
    out: dict[str, int] = {}
    for stage, value in (table if isinstance(table, dict) else {}).items():
        if stage not in STAGES:
            raise _bad_stage(stage, f"{CONFIG_FILE} [{TOML_THINKING}]")
        if value is True:
            out[stage] = DEFAULT_THINKING_BUDGET
        elif isinstance(value, int) and not isinstance(value, bool) and value >= MIN_THINKING_BUDGET:
            out[stage] = value
        elif value is not False:
            raise CvtError(
                ExitCode.INPUT, "E_CONFIG",
                f"{CONFIG_FILE} [{TOML_THINKING}] {stage} must be true, false, or a token budget >= {MIN_THINKING_BUDGET}",
                hint=f"for example: {stage} = {DEFAULT_THINKING_BUDGET}",
            )
    return out


@dataclass(frozen=True)
class GtjobConfig:
    cli_models: Mapping[str, str] = field(default_factory=dict)
    toml_models: Mapping[str, str] = field(default_factory=dict)
    thinking: Mapping[str, int] = field(default_factory=dict)
    env: Mapping[str, str] = field(default_factory=dict)
    no_cache: bool = False
    interactive: bool = False  # block 2 of the prompt uses the 1-hour cache TTL
    visual: bool = False  # critic: attach page PNGs
    root: Path = field(default_factory=Path.cwd)

    def model_source(self, stage: str) -> str:
        if stage in self.cli_models:
            return "cli"
        if self.env.get(f"{ENV_MODEL_PREFIX}{stage.upper()}"):
            return "env"
        if stage in self.toml_models:
            return "toml"
        return "default"

    def model_for(self, stage: str, *, escalate: bool = False) -> str:
        """Model for `stage`. `escalate` is the retry after a failed check: a Haiku default moves to Sonnet."""
        if stage not in DEFAULT_MODELS:
            raise _bad_stage(stage, "model lookup")
        base = stage
        source = self.model_source(base)
        model = {
            "cli": lambda: self.cli_models[base],
            "env": lambda: self.env[f"{ENV_MODEL_PREFIX}{base.upper()}"],
            "toml": lambda: self.toml_models[base],
            "default": lambda: DEFAULT_MODELS[base],
        }[source]()
        if escalate and source == "default" and model == MODEL_HAIKU:
            return ESCALATION_MODEL
        return model

    def max_tokens(self, stage: str, *, fix: bool = False) -> int:
        """Output cap from budgets.json; a fix re-run may rewrite the whole file, so it takes the larger cap."""
        table = briefs.budgets()["stages"]
        cap = int(table[stage]["output"])
        return max(cap, int(table[FIX_STAGE]["output"])) if fix else cap

    def thinking_budget(self, stage: str) -> int:
        return int(self.thinking.get(stage, 0))


def load_config(
    *,
    cli_models: Iterable[str] = (),
    no_cache: bool = False,
    interactive: bool = False,
    visual: bool = False,
    root: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> GtjobConfig:
    root = Path(root) if root is not None else paths.workspace_root()
    toml = _read_toml(root)
    return GtjobConfig(
        cli_models=parse_model_args(cli_models),
        toml_models=_toml_models(toml.get(TOML_MODELS)),
        thinking=_toml_thinking(toml.get(TOML_THINKING)),
        env=dict(os.environ if env is None else env),
        no_cache=no_cache,
        interactive=interactive,
        visual=visual,
        root=root,
    )
