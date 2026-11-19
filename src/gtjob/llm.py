"""LLM clients for the AI stages: Anthropic, Cursor, and a canned `FakeClient` for tests.

`$GTJOB_PROVIDER` picks the live adapter: `anthropic`, `cursor`, or `auto` (the default).
`auto` uses Anthropic when `ANTHROPIC_API_KEY` is set, and uses Cursor when the key is
missing or Anthropic answers 429. Cursor is one JSON reply through `@cursor/sdk` with no
tools and an in-memory tree, so the model never sees this repo.
"""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from gtjob import _skill

_skill.ensure_path()

from cvtlib import briefs, schemas  # noqa: E402
from cvtlib.errors import CvtError, ExitCode  # noqa: E402

API_KEY_ENV = "ANTHROPIC_API_KEY"
API_KEY_HINT = "export ANTHROPIC_API_KEY=... or set GTJOB_PROVIDER=cursor after signing in to Cursor"
PROVIDER_ENV = "GTJOB_PROVIDER"
CURSOR_KEY_ENV = "CURSOR_API_KEY"
CURSOR_MODEL_ENV = "GTJOB_CURSOR_MODEL"
CURSOR_MODEL = "composer-2.5"
CURSOR_AUTH = Path(".cursor") / "sdk" / "auth.json"
CURSOR_TIMEOUT_SECONDS = 200
PROVIDER_AUTO, PROVIDER_ANTHROPIC, PROVIDER_CURSOR = "auto", "anthropic", "cursor"
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
            elif path.stem in briefs.STAGE_SPECS or path.stem == "propose":
                attempts.setdefault(path.stem, []).append((0, path))
        responses = {
            stage: [json.loads(path.read_text(encoding="utf-8")) for _, path in sorted(items)]
            for stage, items in attempts.items()
        }
        return cls(responses)


def cursor_ready() -> bool:
    """True when a Cursor API key or a Studio/`Cursor.auth.login()` file is present. Does not read the key."""
    if os.environ.get(CURSOR_KEY_ENV, "").strip():
        return True
    return Path.home().joinpath(CURSOR_AUTH).is_file()


def _cursor_model(requested: str) -> str:
    chosen = os.environ.get(CURSOR_MODEL_ENV, "").strip()
    if requested and not requested.startswith("claude"):
        return requested
    return chosen or CURSOR_MODEL


def _node_cursor(payload: dict) -> dict:
    script = _skill.repo_root() / "web" / "scripts" / "cursor-complete.mjs"
    if not script.is_file():
        raise CvtError(ExitCode.INTERNAL, "E_CURSOR", "the Cursor provider script is missing",
                       hint="reinstall gtjob so web/scripts/cursor-complete.mjs is present")
    try:
        done = subprocess.run(
            ["node", str(script)], input=json.dumps(payload), capture_output=True, text=True,
            timeout=CURSOR_TIMEOUT_SECONDS, cwd=script.parent.parent, check=False,
        )
    except FileNotFoundError:
        raise CvtError(ExitCode.MISSING_DEPENDENCY, "E_CURSOR", "node is not installed",
                       hint="install Node 22 or newer so gtjob can call the Cursor SDK") from None
    except subprocess.TimeoutExpired:
        raise CvtError(ExitCode.INTERNAL, "E_CURSOR", "Cursor timed out",
                       hint="rerun; finished stages are cached") from None
    line = (done.stdout or "").strip().splitlines()
    raw = line[-1] if line else ""
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        detail = (done.stderr or "Cursor returned no JSON").strip().splitlines()
        raise CvtError(ExitCode.INTERNAL, "E_CURSOR", detail[-1] if detail else "Cursor returned no JSON",
                       hint="rerun; if it repeats, check that Cursor is signed in") from None
    if not isinstance(data, dict):
        raise CvtError(ExitCode.INTERNAL, "E_CURSOR", "Cursor returned a non-object reply",
                       hint="rerun; finished stages are cached")
    return data


class CursorClient:
    """One structured JSON reply from a Cursor agent that has no tools and cannot see the repo."""

    def __init__(self, *, transport: Callable[[dict], dict] | None = None, require_auth: bool = True) -> None:
        if transport is None and require_auth and not cursor_ready():
            raise CvtError(
                ExitCode.MISSING_DEPENDENCY, "E_CURSOR_AUTH", "Cursor is not signed in",
                hint=f"export {CURSOR_KEY_ENV}=... or connect Cursor from the toolbox",
            )
        self._transport = transport or _node_cursor
        self.last_usage: dict = _empty_usage()

    def complete_json(
        self, system: list[dict], blocks: list[dict], schema: dict, model: str, max_tokens: int, *,
        stage: str = "", history: list[dict] | None = None, thinking_budget: int = 0,
    ) -> dict:
        del thinking_budget  # Cursor's agent decides its own thinking; the call stays one JSON object
        envelope = self._transport({
            "system": system, "blocks": blocks, "history": history or [], "schema": schema,
            "model": _cursor_model(model), "max_tokens": max_tokens, "stage": stage,
        })
        if not envelope.get("ok"):
            err_id = str(envelope.get("id") or "E_CURSOR")
            code = ExitCode.MISSING_DEPENDENCY if err_id == "E_CURSOR_AUTH" else ExitCode.INTERNAL
            raise CvtError(code, err_id, str(envelope.get("message") or "Cursor did not answer"),
                           hint=str(envelope.get("hint") or "rerun; finished stages are cached"))
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise CvtError(ExitCode.INTERNAL, "E_MODEL_JSON", "Cursor did not return a JSON object",
                           hint="rerun; if it repeats, report the stage")
        usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
        self.last_usage = {key: int(usage.get(key, 0) or 0) for key in USAGE_KEYS}
        return normalize_enums(data, schema)  # type: ignore[return-value]


def _quota_exhausted(exc: CvtError) -> bool:
    return exc.err_id == "E_API" and "API error 429" in exc.message


class SwitchingClient:
    """Anthropic first. After a 429, this call and later calls use Cursor."""

    def __init__(self, primary: LLMClient, cursor_factory: Callable[[], LLMClient]) -> None:
        self._primary = primary
        self._cursor_factory = cursor_factory
        self._cursor: LLMClient | None = None
        self.last_usage: dict = _empty_usage()

    def complete_json(
        self, system: list[dict], blocks: list[dict], schema: dict, model: str, max_tokens: int, *,
        stage: str = "", history: list[dict] | None = None, thinking_budget: int = 0,
    ) -> dict:
        active = self._cursor
        if active is None:
            try:
                data = self._primary.complete_json(
                    system, blocks, schema, model, max_tokens, stage=stage, history=history,
                    thinking_budget=thinking_budget,
                )
            except CvtError as exc:
                if not _quota_exhausted(exc):
                    raise
                if not cursor_ready():
                    raise CvtError(
                        ExitCode.MISSING_DEPENDENCY, "E_API_KEY",
                        "Anthropic quota is exhausted and Cursor is not signed in",
                        hint=f"wait and rerun, or export {CURSOR_KEY_ENV}=... and rerun",
                    ) from exc
                self._cursor = active = self._cursor_factory()
            else:
                self.last_usage = dict(self._primary.last_usage)
                return data
        data = active.complete_json(
            system, blocks, schema, model, max_tokens, stage=stage, history=history, thinking_budget=thinking_budget,
        )
        self.last_usage = dict(active.last_usage)
        return data


def _provider() -> str:
    name = os.environ.get(PROVIDER_ENV, PROVIDER_AUTO).strip().lower() or PROVIDER_AUTO
    if name not in {PROVIDER_AUTO, PROVIDER_ANTHROPIC, PROVIDER_CURSOR}:
        raise CvtError(
            ExitCode.USAGE, "E_PROVIDER", f"unknown {PROVIDER_ENV} '{name}'",
            hint=f"set {PROVIDER_ENV} to {PROVIDER_AUTO}, {PROVIDER_ANTHROPIC}, or {PROVIDER_CURSOR}",
        )
    return name


def _neither_provider() -> CvtError:
    return CvtError(
        ExitCode.MISSING_DEPENDENCY, "E_API_KEY",
        "neither ANTHROPIC_API_KEY nor a Cursor login is set",
        hint=f"export {API_KEY_ENV}=... or export {CURSOR_KEY_ENV}=... (or connect Cursor from the toolbox)",
    )


def default_client() -> LLMClient:
    """`FakeClient` when `$GTJOB_FAKE_LLM` is set. Otherwise the provider named by `$GTJOB_PROVIDER` (`auto`)."""
    fake = os.environ.get(FAKE_LLM_ENV)
    if fake:
        return FakeClient.from_dir(fake)
    provider = _provider()
    has_anthropic = bool(os.environ.get(API_KEY_ENV, "").strip())
    if provider == PROVIDER_CURSOR or (provider == PROVIDER_AUTO and not has_anthropic):
        if provider == PROVIDER_AUTO and not cursor_ready():
            raise _neither_provider()
        return CursorClient()
    if provider == PROVIDER_AUTO:
        return SwitchingClient(AnthropicClient(), CursorClient)
    return AnthropicClient()
