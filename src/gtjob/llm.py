"""LLM clients for the AI stages: the Anthropic Messages API (structured outputs) and a canned `FakeClient` for tests."""

from __future__ import annotations

import copy
import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from gtjob import _skill

_skill.ensure_path()

from cvtlib import briefs, schemas  # noqa: E402
from cvtlib.errors import CvtError, ExitCode  # noqa: E402

API_KEY_ENV = "ANTHROPIC_API_KEY"
API_KEY_HINT = "export ANTHROPIC_API_KEY=... or run the skill inside Cursor/Claude Code"
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_FACTOR = 2.0
RATE_LIMIT_STATUS = 429
SERVER_ERROR_MIN_STATUS = 500
STOP_REFUSAL, STOP_MAX_TOKENS = "refusal", "max_tokens"
FORMAT_TYPE = "json_schema"
THINKING_TYPE = "enabled"
USAGE_KEYS = ("input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens")
REF_PREFIX = "#/"
FAKE_LLM_ENV = "GTJOB_FAKE_LLM"  # offline replay hook for tests and evals: a directory of canned stage outputs
FAKE_ATTEMPT_RE = re.compile(r"^(?P<stage>[a-z_]+)\.(?P<n>[0-9]+)\.json$")
FAKE_SINGLE_SUFFIX = ".json"


class LLMClient(Protocol):
    """`complete_json` returns the parsed JSON object; `last_usage` holds `USAGE_KEYS` of the latest call."""

    last_usage: dict

    def complete_json(
        self, system: list[dict], blocks: list[dict], schema: dict, model: str, max_tokens: int, *,
        stage: str = "", history: list[dict] | None = None, thinking_budget: int = 0,
    ) -> dict: ...


def _empty_usage() -> dict:
    return dict.fromkeys(USAGE_KEYS, 0)


def _deref(root: dict, node: dict) -> dict:
    seen = 0
    while isinstance(node, dict) and "$ref" in node and seen < len(root.get("$defs", {})) + 1:
        ref = node["$ref"]
        target: object = root
        for part in ref[len(REF_PREFIX):].split("/") if ref.startswith(REF_PREFIX) else []:
            target = target.get(part.replace("~1", "/").replace("~0", "~"), {}) if isinstance(target, dict) else {}
        node = target if isinstance(target, dict) else {}
        seen += 1
    return node


def normalize_enums(data: object, schema: dict) -> object:
    """Map enum strings to the schema's canonical casing (API enum casing is not guaranteed)."""

    def walk(value: object, node: dict) -> object:
        node = _deref(schema, node)
        if isinstance(value, str) and isinstance(node.get("enum"), list):
            for option in node["enum"]:
                if isinstance(option, str) and option.lower() == value.lower():
                    return option
            return value
        if isinstance(value, dict) and isinstance(node.get("properties"), dict):
            return {k: walk(v, node["properties"].get(k, {})) for k, v in value.items()}
        if isinstance(value, list) and isinstance(node.get("items"), dict):
            return [walk(v, node["items"]) for v in value]
        return value

    return walk(data, schema)


def _api_error(message: str, hint: str, code: ExitCode = ExitCode.INTERNAL, err_id: str = "E_API") -> CvtError:
    return CvtError(code, err_id, message, hint=hint)


class AnthropicClient:
    """Structured-output calls to `client.messages.create` with 429/5xx exponential backoff."""

    def __init__(
        self, api_key: str | None = None, *, sdk: object | None = None,
        sleep: Callable[[float], None] = time.sleep, max_retries: int = MAX_RETRIES,
    ) -> None:
        key = api_key or os.environ.get(API_KEY_ENV, "")
        if sdk is None and not key:
            raise CvtError(ExitCode.MISSING_DEPENDENCY, "E_API_KEY", f"{API_KEY_ENV} is not set", hint=API_KEY_HINT)
        if sdk is None:
            import anthropic

            sdk = anthropic.Anthropic(api_key=key, max_retries=0)  # retries are ours, so backoff is visible and tested
        self._sdk = sdk
        self._sleep = sleep
        self._max_retries = max_retries
        self.last_usage: dict = _empty_usage()

    # --- request ---------------------------------------------------------------------------------------------
    def _request(
        self, system: list[dict], blocks: list[dict], schema: dict, model: str, max_tokens: int,
        history: list[dict], thinking_budget: int,
    ) -> dict:
        request: dict = {
            "model": model,
            "max_tokens": max_tokens + thinking_budget,
            "system": system,
            "messages": [*history, {"role": "user", "content": blocks}],
            "output_config": {"format": {"type": FORMAT_TYPE, "schema": schemas.api_schema(schema)}},
        }
        if thinking_budget:
            request["thinking"] = {"type": THINKING_TYPE, "budget_tokens": thinking_budget}
        return request

    def _send(self, request: dict) -> object:
        import anthropic

        retriable = (anthropic.APIConnectionError,)
        for attempt in range(self._max_retries + 1):
            try:
                return self._sdk.messages.create(**request)  # type: ignore[attr-defined]
            except anthropic.AuthenticationError:
                raise CvtError(ExitCode.MISSING_DEPENDENCY, "E_API_KEY", f"{API_KEY_ENV} was rejected by the API",
                               hint=API_KEY_HINT) from None
            except anthropic.APIStatusError as exc:
                status = int(getattr(exc, "status_code", 0))
                if status != RATE_LIMIT_STATUS and status < SERVER_ERROR_MIN_STATUS:
                    raise _api_error(f"API error {status}: {exc}", "check the model id and request, then rerun") from None
                if attempt == self._max_retries:
                    raise _api_error(f"API error {status} after {self._max_retries} retries: {exc}",
                                     "wait a minute and rerun; finished stages are cached") from None
            except retriable as exc:
                if attempt == self._max_retries:
                    raise _api_error(f"cannot reach the API after {self._max_retries} retries: {exc}",
                                     "check your network connection and rerun; finished stages are cached") from None
            self._sleep(BACKOFF_BASE_SECONDS * BACKOFF_FACTOR ** attempt)
        raise AssertionError("unreachable")  # pragma: no cover

    # --- response --------------------------------------------------------------------------------------------
    def _usage(self, response: object) -> dict:
        usage = getattr(response, "usage", None)

        def num(name: str) -> int:
            return int(getattr(usage, name, 0) or 0)

        return {
            "input_tokens": num("input_tokens"),
            "cache_read_tokens": num("cache_read_input_tokens"),
            "cache_write_tokens": num("cache_creation_input_tokens"),
            "output_tokens": num("output_tokens"),
        }

    def complete_json(
        self, system: list[dict], blocks: list[dict], schema: dict, model: str, max_tokens: int, *,
        stage: str = "", history: list[dict] | None = None, thinking_budget: int = 0,
    ) -> dict:
        response = self._send(self._request(system, blocks, schema, model, max_tokens, history or [], thinking_budget))
        self.last_usage = self._usage(response)
        stop = getattr(response, "stop_reason", "")
        label = f" for stage {stage}" if stage else ""
        if stop == STOP_REFUSAL:
            raise CvtError(ExitCode.INPUT, "E_REFUSAL", f"the model refused to answer{label}",
                           hint="inspect the CV/JD text for content the model objects to, edit it, and rerun")
        if stop == STOP_MAX_TOKENS:
            raise CvtError(ExitCode.INTERNAL, "E_MAX_TOKENS", f"the answer{label} was cut off at {max_tokens} tokens",
                           hint="raise the stage's output cap in .claude/skills/tailoring-cvs/assets/budgets.json and rerun")
        text = "".join(getattr(b, "text", "") for b in getattr(response, "content", []) if getattr(b, "type", "") == "text")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CvtError(ExitCode.INTERNAL, "E_MODEL_JSON", f"the model reply{label} is not valid JSON: {exc.msg}",
                           hint="rerun with --no-cache; if it repeats, report the stage and model") from None
        if not isinstance(data, dict):
            raise CvtError(ExitCode.INTERNAL, "E_MODEL_JSON", f"the model reply{label} is not a JSON object",
                           hint="rerun with --no-cache; if it repeats, report the stage and model")
        return normalize_enums(data, schema)  # type: ignore[return-value]


class FakeClient:
    """Returns canned outputs in order per stage and records every call (for tests; no network)."""

    def __init__(self, responses: dict[str, list[dict]]) -> None:
        self._responses = {stage: list(items) for stage, items in responses.items()}
        self.calls: list[dict] = []
        self.last_usage: dict = _empty_usage()

    def complete_json(
        self, system: list[dict], blocks: list[dict], schema: dict, model: str, max_tokens: int, *,
        stage: str = "", history: list[dict] | None = None, thinking_budget: int = 0,
    ) -> dict:
        self.calls.append({
            "stage": stage, "model": model, "system": copy.deepcopy(system), "blocks": copy.deepcopy(blocks),
            "history": copy.deepcopy(history or []), "schema": schema, "max_tokens": max_tokens,
            "thinking_budget": thinking_budget,
        })
        queue = self._responses.get(stage) or []
        if not queue:
            raise CvtError(ExitCode.INTERNAL, "E_FAKE_EXHAUSTED", f"FakeClient has no response left for stage '{stage}'",
                           hint="add another canned response to the FakeClient for this stage")
        data = normalize_enums(copy.deepcopy(queue.pop(0)), schema)
        sent = json.dumps([system, history or [], blocks], ensure_ascii=False)
        self.last_usage = {
            "input_tokens": briefs.estimate_tokens(sent), "cache_read_tokens": 0, "cache_write_tokens": 0,
            "output_tokens": briefs.estimate_tokens(json.dumps(data, ensure_ascii=False)),
        }
        return data  # type: ignore[return-value]

    @classmethod
    def from_dir(cls, directory: str | Path) -> FakeClient:
        """Canned responses from `<dir>/<stage>.json` (one attempt) or `<dir>/<stage>.N.json` (attempts in N order)."""
        root = Path(directory)
        if not root.is_dir():
            raise CvtError(ExitCode.INPUT, "E_FAKE_LLM_DIR", f"{FAKE_LLM_ENV} is not a directory: {root}",
                           hint=f"point {FAKE_LLM_ENV} at a folder of <stage>.json files, or unset it to use the API")
        attempts: dict[str, list[tuple[int, Path]]] = {}
        for path in sorted(root.glob("*.json")):
            numbered = FAKE_ATTEMPT_RE.match(path.name)
            if numbered:
                attempts.setdefault(numbered["stage"], []).append((int(numbered["n"]), path))
            elif path.stem in briefs.STAGE_SPECS:
                attempts.setdefault(path.stem, []).append((0, path))
        responses = {
            stage: [json.loads(path.read_text(encoding="utf-8")) for _, path in sorted(items)]
            for stage, items in attempts.items()
        }
        return cls(responses)


def default_client() -> LLMClient:
    """`FakeClient` over `$GTJOB_FAKE_LLM` when it is set (offline replay), otherwise the real `AnthropicClient`."""
    fake = os.environ.get(FAKE_LLM_ENV)
    return FakeClient.from_dir(fake) if fake else AnthropicClient()
