"""WP-21: config precedence, the Anthropic client (stubbed SDK), FakeClient, the local cache. No network except `live`."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import anthropic
import pytest

from cvtlib import schemas, state
from cvtlib.errors import CvtError, ExitCode
from gtjob import config as gcfg
from gtjob import llm, stages
from gtjob.cache import LLMCache, cache_key

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
JD_SCHEMA = schemas.load_schema("jd")
OK_JSON = {"x": 1}
SYSTEM = [{"type": "text", "text": "system", "cache_control": {"type": "ephemeral"}}]
BLOCKS = [{"type": "text", "text": "hello"}]


# --- config -------------------------------------------------------------------------------------------------
def test_defaults_follow_the_routing_table():
    cfg = gcfg.load_config(root=Path("/nonexistent"), env={})
    haiku = {s for s in gcfg.STAGES if cfg.model_for(s) == gcfg.MODEL_HAIKU}
    assert haiku == {"jd", "answer_parse", "change_request"}
    assert cfg.model_for("critic") == gcfg.MODEL_OPUS
    assert {cfg.model_for(s) for s in ("profile", "match", "questions", "tailor")} == {gcfg.MODEL_SONNET}


def test_model_resolution_precedence(tmp_path: Path):
    (tmp_path / "gtjob.toml").write_text('[models]\ntailor = "from-toml"\nmatch = "toml-match"\njd = "toml-jd"\n')
    env = {"GTJOB_MODEL_TAILOR": "from-env", "GTJOB_MODEL_MATCH": "env-match"}
    cfg = gcfg.load_config(root=tmp_path, env=env, cli_models=["tailor=from-cli"])
    assert cfg.model_for("tailor") == "from-cli"  # --model beats env and toml
    assert cfg.model_for("match") == "env-match"  # env beats toml
    assert cfg.model_for("jd") == "toml-jd"  # toml beats the default
    assert cfg.model_for("critic") == gcfg.MODEL_OPUS  # default
    assert cfg.model_source("tailor") == "cli" and cfg.model_source("jd") == "toml"


def test_escalation_only_moves_a_haiku_default(tmp_path: Path):
    cfg = gcfg.load_config(root=tmp_path, env={})
    assert cfg.model_for("jd", escalate=True) == gcfg.MODEL_SONNET
    assert cfg.model_for("tailor", escalate=True) == gcfg.MODEL_SONNET
    assert cfg.model_for("critic", escalate=True) == gcfg.MODEL_OPUS
    pinned = gcfg.load_config(root=tmp_path, env={"GTJOB_MODEL_JD": gcfg.MODEL_HAIKU})
    assert pinned.model_for("jd", escalate=True) == gcfg.MODEL_HAIKU


def test_bad_model_arguments_are_actionable(tmp_path: Path):
    for bad in ("tailor", "tailor=", "bogus=claude-x"):
        with pytest.raises(CvtError) as exc:
            gcfg.parse_model_args([bad])
        assert exc.value.code == ExitCode.USAGE and exc.value.hint
    (tmp_path / "gtjob.toml").write_text("[models\n")
    with pytest.raises(CvtError) as exc:
        gcfg.load_config(root=tmp_path, env={})
    assert exc.value.err_id == "E_CONFIG"


def test_thinking_is_off_unless_enabled(tmp_path: Path):
    assert gcfg.load_config(root=tmp_path, env={}).thinking_budget("tailor") == 0
    (tmp_path / "gtjob.toml").write_text("[thinking]\ntailor = true\nmatch = 2048\njd = false\n")
    cfg = gcfg.load_config(root=tmp_path, env={})
    assert cfg.thinking_budget("tailor") == gcfg.DEFAULT_THINKING_BUDGET
    assert cfg.thinking_budget("match") == 2048 and cfg.thinking_budget("jd") == 0
    (tmp_path / "gtjob.toml").write_text("[thinking]\ntailor = 5\n")
    with pytest.raises(CvtError):
        gcfg.load_config(root=tmp_path, env={})


# --- enum normalization -------------------------------------------------------------------------------------
def test_normalize_enums_maps_case_through_refs_and_arrays():
    schema = {
        "$defs": {"kind": {"enum": ["must", "nice"]}},
        "type": "object",
        "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
            "kind": {"$ref": "#/$defs/kind"}, "text": {"type": "string"}}}}},
    }
    data = {"items": [{"kind": "MUST", "text": "MUST stay"}, {"kind": "Nice", "text": "x"}, {"kind": "other", "text": "y"}]}
    out = llm.normalize_enums(data, schema)
    assert [i["kind"] for i in out["items"]] == ["must", "nice", "other"] and out["items"][0]["text"] == "MUST stay"


# --- AnthropicClient with a stub SDK -------------------------------------------------------------------------
def _response(text: str = json.dumps(OK_JSON), stop: str = "end_turn", **usage) -> SimpleNamespace:
    counts = {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 7, "cache_creation_input_tokens": 3, **usage}
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=stop,
                           usage=SimpleNamespace(**counts))


def _status_error(status: int) -> anthropic.APIStatusError:
    resp = SimpleNamespace(status_code=status, headers={}, request=SimpleNamespace(), text="boom")
    cls = {429: anthropic.RateLimitError, 401: anthropic.AuthenticationError, 400: anthropic.BadRequestError}.get(
        status, anthropic.InternalServerError)
    return cls("boom", response=resp, body=None)


class StubSDK:
    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _client(*outcomes, sleeps: list | None = None) -> tuple[llm.AnthropicClient, StubSDK]:
    sdk = StubSDK(*outcomes)
    return llm.AnthropicClient(sdk=sdk, sleep=(sleeps if sleeps is not None else []).append), sdk


def test_request_has_structured_output_config_without_schema_ids():
    client, sdk = _client(_response())
    out = client.complete_json(SYSTEM, BLOCKS, JD_SCHEMA, "claude-haiku-5-5", 777, stage="jd")
    assert out == OK_JSON
    req = sdk.requests[0]
    sent = req["output_config"]["format"]
    assert sent["type"] == "json_schema" and "$schema" not in sent["schema"] and "$id" not in sent["schema"]
    assert "$schema" in JD_SCHEMA  # the stored contract is untouched
    assert req["model"] == "claude-haiku-5-5" and req["max_tokens"] == 777 and req["system"] == SYSTEM
    assert req["messages"] == [{"role": "user", "content": BLOCKS}] and "thinking" not in req


def test_history_and_thinking_are_sent_when_given():
    client, sdk = _client(_response())
    history = [{"role": "user", "content": BLOCKS}, {"role": "assistant", "content": "{}"}]
    client.complete_json(SYSTEM, BLOCKS, JD_SCHEMA, "m", 100, history=history, thinking_budget=2048)
    req = sdk.requests[0]
    assert req["messages"][:2] == history and req["messages"][2]["role"] == "user"
    assert req["thinking"] == {"type": "enabled", "budget_tokens": 2048} and req["max_tokens"] == 100 + 2048


def test_usage_fields_are_mapped():
    client, _ = _client(_response())
    client.complete_json(SYSTEM, BLOCKS, JD_SCHEMA, "m", 100)
    assert client.last_usage == {"input_tokens": 10, "cache_read_tokens": 7, "cache_write_tokens": 3, "output_tokens": 5}


def test_enum_casing_is_normalized_in_replies():
    client, _ = _client(_response(json.dumps({"kind": "MUST"})))
    schema = {"type": "object", "properties": {"kind": {"enum": ["must", "nice"]}}}
    assert client.complete_json(SYSTEM, BLOCKS, schema, "m", 100) == {"kind": "must"}


def test_retries_429_and_5xx_with_exponential_backoff():
    sleeps: list[float] = []
    client, sdk = _client(_status_error(429), _status_error(503), _response(), sleeps=sleeps)
    assert client.complete_json(SYSTEM, BLOCKS, JD_SCHEMA, "m", 100) == OK_JSON
    assert len(sdk.requests) == 3 and sleeps == [llm.BACKOFF_BASE_SECONDS, llm.BACKOFF_BASE_SECONDS * llm.BACKOFF_FACTOR]


def test_gives_up_after_three_retries():
    sleeps: list[float] = []
    client, sdk = _client(*[_status_error(500)] * 4, sleeps=sleeps)
    with pytest.raises(CvtError) as exc:
        client.complete_json(SYSTEM, BLOCKS, JD_SCHEMA, "m", 100)
    assert exc.value.err_id == "E_API" and len(sdk.requests) == llm.MAX_RETRIES + 1 and len(sleeps) == llm.MAX_RETRIES


def test_client_errors_are_not_retried():
    client, sdk = _client(_status_error(400))
    with pytest.raises(CvtError) as exc:
        client.complete_json(SYSTEM, BLOCKS, JD_SCHEMA, "m", 100)
    assert exc.value.err_id == "E_API" and len(sdk.requests) == 1
    client, _ = _client(_status_error(401))
    with pytest.raises(CvtError) as exc:
        client.complete_json(SYSTEM, BLOCKS, JD_SCHEMA, "m", 100)
    assert exc.value.err_id == "E_API_KEY" and exc.value.code == ExitCode.MISSING_DEPENDENCY


def test_refusal_and_max_tokens_have_actionable_errors():
    client, _ = _client(_response("", stop="refusal"))
    with pytest.raises(CvtError) as exc:
        client.complete_json(SYSTEM, BLOCKS, JD_SCHEMA, "m", 100, stage="jd")
    assert exc.value.err_id == "E_REFUSAL" and "jd" in exc.value.message and exc.value.hint
    client, _ = _client(_response("{", stop="max_tokens"))
    with pytest.raises(CvtError) as exc:
        client.complete_json(SYSTEM, BLOCKS, JD_SCHEMA, "m", 321, stage="jd")
    assert exc.value.err_id == "E_MAX_TOKENS" and "321" in exc.value.message and "budgets.json" in exc.value.hint


def test_non_json_reply_is_an_error():
    client, _ = _client(_response("not json"))
    with pytest.raises(CvtError) as exc:
        client.complete_json(SYSTEM, BLOCKS, JD_SCHEMA, "m", 100)
    assert exc.value.err_id == "E_MODEL_JSON"


def test_missing_api_key_is_actionable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(CvtError) as exc:
        llm.AnthropicClient()
    assert exc.value.err_id == "E_API_KEY" and exc.value.code == ExitCode.MISSING_DEPENDENCY
    assert "export ANTHROPIC_API_KEY=" in exc.value.hint and "Cursor/Claude Code" in exc.value.hint


# --- FakeClient and cache ------------------------------------------------------------------------------------
def test_fake_client_returns_in_order_and_records_prompts():
    fake = llm.FakeClient({"jd": [{"a": 1}, {"a": 2}]})
    assert fake.complete_json(SYSTEM, BLOCKS, {}, "m", 10, stage="jd") == {"a": 1}
    assert fake.complete_json(SYSTEM, BLOCKS, {}, "m", 10, stage="jd") == {"a": 2}
    assert [c["stage"] for c in fake.calls] == ["jd", "jd"] and fake.calls[0]["blocks"] == BLOCKS
    assert fake.last_usage["input_tokens"] > 0 and fake.last_usage["output_tokens"] > 0
    with pytest.raises(CvtError) as exc:
        fake.complete_json(SYSTEM, BLOCKS, {}, "m", 10, stage="jd")
    assert exc.value.err_id == "E_FAKE_EXHAUSTED"


def _key(**changes) -> str:
    base = {"model": "m", "system": SYSTEM, "blocks": BLOCKS, "history": [], "schema": JD_SCHEMA, "max_tokens": 10}
    return cache_key(**{**base, **changes})


def test_cache_key_covers_every_input():
    base = _key()
    assert base == _key() and len(base) == 64
    for change in ({"model": "n"}, {"system": []}, {"blocks": []}, {"history": [{"role": "user", "content": "x"}]},
                   {"schema": {}}, {"max_tokens": 11}, {"thinking_budget": 1024}):
        assert _key(**change) != base


def test_cache_roundtrip_and_read_switch(tmp_path: Path):
    cache = LLMCache(tmp_path / "llm")
    assert cache.get("k") is None
    cache.put("k", {"a": 1}, {"input_tokens": 2})
    assert cache.get("k")["response"] == {"a": 1}
    assert LLMCache(tmp_path / "llm", read=False).get("k") is None
    (tmp_path / "llm" / "bad.json").write_text("{", encoding="utf-8")
    assert cache.get("bad") is None


# --- live smoke test -----------------------------------------------------------------------------------------
@pytest.mark.live
def test_live_jd_stage_returns_schema_valid_jd(workspace: Path):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    cv = FIXTURES / "cv" / "jamie-rivera-junior.txt"
    jd_file = FIXTURES / "jds" / "senior-frontend-react.md"
    run_dir = state.create_run(cv, "file", str(jd_file), None, {"page_target": 1}, slug="live")
    st = state.load(run_dir)
    (run_dir / "cv.txt").write_text(cv.read_text(encoding="utf-8"), encoding="utf-8")
    (run_dir / "jd.txt").write_text(jd_file.read_text(encoding="utf-8"), encoding="utf-8")
    state.record_artifact(run_dir, st, "cv_txt", "cv.txt", cascade=False)
    state.record_artifact(run_dir, st, "jd_txt", "jd.txt", cascade=False)
    state.set_stage(st, "profiled")
    state.save(run_dir, st)
    path = stages.run_stage_checked("jd", run_dir, client=llm.AnthropicClient(), config=gcfg.load_config(root=workspace))
    assert schemas.validate(json.loads(path.read_text(encoding="utf-8")), "jd") == []
