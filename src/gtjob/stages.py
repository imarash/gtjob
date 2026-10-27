"""Run one AI stage against a run directory, with the validator fix loop (interfaces.md sections 13 and 14).

`run_stage` asks the model and writes the stage's output file. `run_stage_checked` also runs the stage's check
command in-process (`cvtlib.cli.main([... , "--json"])`) and, on exit 1, re-prompts with the `fix` packet as a new
user turn on top of the original turn and the model's previous output.
"""

from __future__ import annotations

import contextlib
import io
import json
import shlex
from dataclasses import dataclass
from pathlib import Path

from gtjob import _skill, prompts
from gtjob.cache import LLMCache, cache_dir, cache_key
from gtjob.config import GtjobConfig
from gtjob.llm import LLMClient

_skill.ensure_path()

from cvtlib import briefs, jsonio, usage  # noqa: E402
from cvtlib import cli as cvt_cli  # noqa: E402
from cvtlib import paths as cvt_paths  # noqa: E402
from cvtlib.errors import CvtError, ExitCode  # noqa: E402

DEFAULT_MAX_ATTEMPTS = 2  # total model calls per checked stage: the first answer plus one fix re-prompt
JSON_FLAG = "--json"
OUT_PREFIX = "out/"
CURRENT_FILE_HEADER = "# Current file ({name})"
CHECK_FAILED_ID = "E_CHECK_FAILED"
CHECK_FAILED_HINT = "show these violations to the user, edit {out} by hand or rerun with another --model, then rerun the stage"
ROLE_USER, ROLE_ASSISTANT = "user", "assistant"
COMPACT_SEPARATORS = (",", ":")


@dataclass
class CheckResult:
    code: int
    envelope: dict
    violations: list[dict]


def output_path(stage: str, run_dir: Path) -> Path:
    return Path(run_dir) / briefs.STAGE_SPECS[stage].out


def _complete(
    prompt: prompts.Prompt, system: list[dict], *, client: LLMClient, config: GtjobConfig, run_dir: Path, stage: str,
    model: str, history: list[dict], attempt: int, fix: bool,
) -> dict:
    max_tokens = config.max_tokens(stage, fix=fix)
    thinking = config.thinking_budget(stage)
    cache = LLMCache(cache_dir(config.root), read=not config.no_cache)
    key = cache_key(model=model, system=system, blocks=prompt.blocks, history=history, schema=prompt.schema,
                    max_tokens=max_tokens, thinking_budget=thinking)
    hit = cache.get(key)
    if hit is not None:
        return hit["response"]
    response = client.complete_json(system, prompt.blocks, prompt.schema, model, max_tokens, stage=stage,
                                    history=history, thinking_budget=thinking)
    spent = dict(client.last_usage)
    usage.record_usage(Path(run_dir), {"stage": stage, "kind": "api", "model": model, "attempt": attempt, **spent})
    cache.put(key, response, spent)
    return response


def _write(stage: str, run_dir: Path, response: dict) -> Path:
    path = output_path(stage, run_dir)
    jsonio.dump_json(response, path)
    return path


def run_stage(stage: str, run_dir: Path, *, client: LLMClient, config: GtjobConfig, extra: dict | None = None) -> Path:
    """Ask the model for `stage` and write its output file (named in section 13). Returns that path."""
    run_dir = Path(run_dir)
    prompt = prompts.build_prompt(stage, run_dir, config=config, extra=extra)
    if prompt.cache_hit_from:
        return output_path(stage, run_dir)
    response = _complete(prompt, prompt.system, client=client, config=config, run_dir=run_dir, stage=stage,
                         model=config.model_for(stage), history=[], attempt=1, fix=False)
    return _write(stage, run_dir, response)


# --- checks -------------------------------------------------------------------------------------------------
def check_argv(stage: str, run_dir: Path) -> list[str]:
    """The stage's check command (section 13 table) as an argv list for `cvtlib.cli.main`, paths made absolute."""
    spec = briefs.STAGE_SPECS[stage]
    root = cvt_paths.workspace_root()
    tokens = shlex.split(spec.check.format(run=Path(run_dir).name))
    return [str(root / t) if t.startswith(OUT_PREFIX) else t for t in tokens]


def run_check(stage: str, run_dir: Path) -> CheckResult:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cvt_cli.main([*check_argv(stage, run_dir), JSON_FLAG])
    envelope: dict = {}
    for line in reversed(out.getvalue().splitlines()):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            envelope = parsed
            break
    data = envelope.get("data") or {}
    violations = [v for v in data.get("violations", []) if isinstance(v, dict)]
    return CheckResult(code, envelope, violations)


def _check_error(stage: str, result: CheckResult) -> CvtError:
    err = result.envelope.get("error") or {}
    return CvtError(
        ExitCode(result.code) if result.code in {int(c) for c in ExitCode} else ExitCode.INTERNAL,
        err.get("id") or "E_CHECK",
        err.get("message") or f"the {stage} check failed with exit code {result.code}",
        hint=err.get("hint") or "run the check by hand with --json for details",
        violations=result.violations,
    )


def run_stage_checked(
    stage: str, run_dir: Path, *, client: LLMClient, config: GtjobConfig, extra: dict | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> Path:
    """`run_stage` plus the check command. Exit 1 re-prompts with the fix packet (a Haiku default escalates to
    Sonnet); other non-zero exits raise at once. After `max_attempts` model calls the violations are raised."""
    run_dir = Path(run_dir)
    if max_attempts < 1:
        raise CvtError(ExitCode.USAGE, "E_USAGE", "max_attempts must be at least 1", hint="use the default of 2")
    prompt = prompts.build_prompt(stage, run_dir, config=config, extra=extra)
    path = output_path(stage, run_dir)
    result = CheckResult(0, {}, [])
    for attempt in range(1, max_attempts + 1):
        if attempt == 1:
            if not prompt.cache_hit_from:
                response = _complete(prompt, prompt.system, client=client, config=config, run_dir=run_dir, stage=stage,
                                     model=config.model_for(stage), history=[], attempt=attempt, fix=False)
                path = _write(stage, run_dir, response)
        else:
            path = _fix(stage, run_dir, prompt, result, client=client, config=config, attempt=attempt)
        result = run_check(stage, run_dir)
        if result.code == 0:
            return path
        if result.code != int(ExitCode.CHECK_FAILED):
            raise _check_error(stage, result)
    raise CvtError(
        ExitCode.CHECK_FAILED, CHECK_FAILED_ID,
        f"{stage} still fails its check after {max_attempts} attempts ({len(result.violations)} violations)",
        hint=CHECK_FAILED_HINT.format(out=briefs.STAGE_SPECS[stage].out), violations=result.violations,
    )


def _fix(
    stage: str, run_dir: Path, original: prompts.Prompt, failed: CheckResult, *, client: LLMClient,
    config: GtjobConfig, attempt: int,
) -> Path:
    fix = prompts.build_fix_prompt(stage, run_dir, violations=failed.violations)
    previous = json.dumps(jsonio.load_json(output_path(stage, run_dir)), ensure_ascii=False, separators=COMPACT_SEPARATORS)
    if original.blocks:
        history = [{"role": ROLE_USER, "content": original.blocks}, {"role": ROLE_ASSISTANT, "content": previous}]
        system = original.system
    else:  # jd copied from an earlier run: there is no original turn to replay, so quote the file instead
        history, system = [], []
        fix.blocks.append(prompts.text_block(f"{CURRENT_FILE_HEADER.format(name=briefs.STAGE_SPECS[stage].out)}\n{previous}"))
    response = _complete(fix, system, client=client, config=config, run_dir=run_dir, stage=stage,
                         model=config.model_for(stage, escalate=True), history=history, attempt=attempt, fix=True)
    return _write(stage, run_dir, response)
