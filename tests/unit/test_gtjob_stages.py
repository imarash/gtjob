"""WP-21: stage prompts (cache blocks), stage runners, the validator fix loop, usage telemetry. No network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cvtlib import briefs, jsonio, state
from cvtlib.errors import CvtError
from gtjob import config as gcfg
from gtjob import prompts, stages
from gtjob.llm import FakeClient

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
GOLDEN = FIXTURES / "golden" / "junior"
CV = FIXTURES / "cv" / "jamie-rivera-junior.txt"
JD_FILE = FIXTURES / "jds" / "junior-devops-engineer.md"
INJECTION_JD = FIXTURES / "jds" / "injection-test.md"
PERSON = "jamie-rivera"
INVENTED_TOOL = "Linkerd"
REPLY = "I used Helm at Brightfield to package two internal services"
CP1_DONE = {"cp1": "done", "cp2": "not_started"}
PNG_BYTES = b"\x89PNG\r\n\x1a\n"


def _golden(name: str) -> dict:
    return json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))


def _make_run(workspace: Path, *, stage: str, jd_file: Path = JD_FILE, artifacts: tuple[str, ...] = (),
              tailored: bool = False) -> Path:
    run_dir = state.create_run(CV, "file", str(jd_file), None, {"page_target": 1}, slug="jr")
    st = state.load(run_dir)
    st["person_slug"] = PERSON
    (run_dir / "cv.txt").write_text(CV.read_text(encoding="utf-8"), encoding="utf-8")
    (run_dir / "jd.txt").write_text(jd_file.read_text(encoding="utf-8"), encoding="utf-8")
    state.record_artifact(run_dir, st, "cv_txt", "cv.txt", cascade=False)
    state.record_artifact(run_dir, st, "jd_txt", "jd.txt", cascade=False)
    for art in artifacts:
        (run_dir / f"{art}.json").write_bytes((GOLDEN / f"{art}.json").read_bytes())
        state.record_artifact(run_dir, st, art, f"{art}.json", cascade=False)
    if tailored:
        t = _golden("tailored")
        t["run_id"] = run_dir.name
        jsonio.dump_json(t, run_dir / "tailored.json")
        state.record_artifact(run_dir, st, "tailored", "tailored.json", cascade=False)
    if "match" in artifacts:
        rnd = _golden("answers.round")
        jsonio.dump_json({"schema_version": "1", "run_id": run_dir.name, "rounds": [rnd]}, run_dir / "answers.json")
    state.set_stage(st, stage)
    st["checkpoints"] = dict(CP1_DONE)
    state.save(run_dir, st)
    atts = json.loads((FIXTURES / "provenance" / "attestations.json").read_text(encoding="utf-8"))
    store = {"schema_version": "1", "person_slug": PERSON, "next_seq": 2,
             "attestations": [dict(a, run_id=run_dir.name) for a in atts if a["id"] == "att-001"]}
    jsonio.dump_json(store, workspace / "profiles" / PERSON / "attestations.json")
    return run_dir


@pytest.fixture
def config(workspace: Path) -> gcfg.GtjobConfig:
    return gcfg.load_config(root=workspace, env={})


def _usage_rows(run_dir: Path) -> list[dict]:
    return [json.loads(x) for x in (run_dir / "usage.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


def _text(blocks: list[dict]) -> str:
    return "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")


# --- prompts ------------------------------------------------------------------------------------------------
def test_prompt_block_order_and_cache_breakpoints(workspace, config):
    run_dir = _make_run(workspace, stage="jd_analyzed", artifacts=("profile", "jd"))
    prompt = prompts.build_prompt("match", run_dir, config=config)
    digest = (run_dir / "digest.txt").read_text(encoding="utf-8").strip()
    assert len(prompt.system) == 1 and prompt.system[0]["cache_control"] == {"type": "ephemeral"}
    assert prompt.system[0]["text"].startswith(prompts.PREAMBLE.splitlines()[0])
    assert "## Rules" in prompt.system[0]["text"] and "## Inputs" not in prompt.system[0]["text"]
    assert len(prompt.blocks) == 2
    first, second = prompt.blocks
    assert digest in first["text"] and first["cache_control"] == {"type": "ephemeral"}
    assert digest not in second["text"] and "cache_control" not in second
    assert "# Stage: match" in second["text"] and "## Output" in second["text"]


def test_interactive_runs_use_one_hour_ttl_on_both_breakpoints(workspace):
    run_dir = _make_run(workspace, stage="jd_analyzed", artifacts=("profile", "jd"))
    cfg = gcfg.load_config(root=workspace, env={}, interactive=True)
    prompt = prompts.build_prompt("match", run_dir, config=cfg)
    one_hour = {"type": "ephemeral", "ttl": "1h"}
    assert prompt.system[0]["cache_control"] == one_hour  # a 1h breakpoint may not follow a 5m one
    assert prompt.blocks[0]["cache_control"] == one_hour


def test_stage_without_digest_has_one_user_block(workspace, config):
    run_dir = _make_run(workspace, stage="ingested")
    prompt = prompts.build_prompt("profile", run_dir, config=config)
    assert len(prompt.blocks) == 1 and "cache_control" not in prompt.blocks[0]
    assert prompt.system[0]["cache_control"] == {"type": "ephemeral"}
    assert prompt.schema_name == "profile-map"


def test_documents_are_wrapped_as_untrusted(workspace, config):
    run_dir = _make_run(workspace, stage="ingested")
    cv_prompt = prompts.build_prompt("profile", run_dir, config=config)
    assert '<untrusted_document name="cv.txt">' in _text(cv_prompt.blocks)
    assert prompts.PREAMBLE.splitlines()[0] in cv_prompt.system[0]["text"]
    assert "jd.injection_flags" in cv_prompt.system[0]["text"]
    jd_run = _make_run(workspace, stage="profiled", jd_file=INJECTION_JD, artifacts=("profile",))
    jd_prompt = prompts.build_prompt("jd", jd_run, config=config)
    body = _text(jd_prompt.blocks)
    assert '<untrusted_document name="jd.txt">' in body and body.count("</untrusted_document>") >= 1
    assert prompts.OUTPUT_HEADING.strip() in body  # the real Output section survives a JD with its own headings


SENTINEL = "SENTINEL-IGNORE-PREVIOUS"


def _inject_sentinel(run_dir: Path) -> None:
    profile = _golden("profile")
    for w in profile["work"]:
        for holder in (w, *w["engagements"]):
            for h in holder["highlights"]:
                h["text"] = f"{SENTINEL} {h['text']}"
    jd = _golden("jd")
    for r in jd["requirements"]:
        r["text"] = f"{SENTINEL} {r['text']}"
        r["keywords"] = [*r["keywords"], SENTINEL]
    st = state.load(run_dir)
    for art, obj in (("profile", profile), ("jd", jd)):
        jsonio.dump_json(obj, run_dir / f"{art}.json")
        state.record_artifact(run_dir, st, art, f"{art}.json", cascade=False)
    state.save(run_dir, st)


@pytest.mark.parametrize("stage,artifacts,run_stage", [("match", ("profile", "jd"), "jd_analyzed"),
                                                      ("tailor", ("profile", "jd", "match"), "answers_applied")])
def test_prompt_text_keeps_cv_and_jd_text_inside_untrusted_wrappers(workspace, config, stage, artifacts, run_stage):
    run_dir = _make_run(workspace, stage=run_stage, artifacts=artifacts)
    _inject_sentinel(run_dir)
    prompt = prompts.build_prompt(stage, run_dir, config=config)
    text = "\n".join([_text(prompt.system), _text(prompt.blocks)])
    open_tag, close_tag = '<untrusted_document name="', "</untrusted_document>"  # the prose rule names the bare tag
    assert text.count(open_tag) == text.count(close_tag)
    found = [i for i in range(len(text)) if text.startswith(SENTINEL, i)]
    assert found
    for pos in found:
        assert text.rfind(open_tag, 0, pos) > text.rfind(close_tag, 0, pos) and text.find(close_tag, pos) > pos
    digest_block = prompt.blocks[0]["text"]
    assert digest_block.startswith(prompts.DIGEST_BLOCK_HEADER) and open_tag in digest_block and SENTINEL in digest_block
    inputs = prompt.blocks[1]["text"]
    assert prompts.DIGEST_PLACEHOLDER in inputs and f'name="{briefs.PROFILE_DIGEST_NAME}"' not in inputs
    assert "\n".join([_text(prompt.system), _text(prompt.blocks)]).count(prompts.DIGEST_PLACEHOLDER) == 1
    assert prompt.system[0]["cache_control"] and digest_block and prompt.blocks[0]["cache_control"]


def test_split_packet_finds_output_section_from_the_end():
    packet = "# Stage: x\n\n## Rules\n\nr\n\n## Inputs\n\ndoc\n## Output\nfake\n\n## Output\n\nreal\n"
    header, rules, inputs, output = prompts.split_packet(packet)
    assert header == "# Stage: x\n" and rules.strip() == "r" and "fake" in inputs and output.strip() == "real"
    with pytest.raises(CvtError):
        prompts.split_packet("no sections")


def test_answer_parse_prompt_uses_round_subschema_and_reply(workspace, config):
    run_dir = _make_run(workspace, stage="matched", artifacts=("profile", "jd", "match", "questions"))
    prompt = prompts.build_prompt("answer_parse", run_dir, config=config, extra={"reply": REPLY})
    assert REPLY in _text(prompt.blocks)
    assert "$schema" not in prompt.schema and "$defs" in prompt.schema
    assert prompt.schema_name == "answers#/$defs/round"
    with pytest.raises(CvtError) as exc:
        prompts.build_prompt("answer_parse", run_dir, config=config)
    assert exc.value.err_id == "E_REPLY_REQUIRED"


def test_critic_images_only_with_visual(workspace):
    run_dir = _make_run(workspace, stage="tailored", artifacts=("profile", "jd", "match"), tailored=True)
    (run_dir / "pages").mkdir()
    (run_dir / "pages" / "page-1.png").write_bytes(PNG_BYTES)
    text_only = prompts.build_prompt("critic", run_dir, config=gcfg.load_config(root=workspace, env={}))
    assert all(b["type"] == "text" for b in text_only.blocks)
    visual = prompts.build_prompt("critic", run_dir, config=gcfg.load_config(root=workspace, env={}, visual=True))
    images = [b for b in visual.blocks if b["type"] == "image"]
    assert len(images) == 1 and images[0]["source"]["media_type"] == "image/png"


def test_unknown_stage_is_a_usage_error(workspace, config):
    run_dir = _make_run(workspace, stage="ingested")
    with pytest.raises(CvtError) as exc:
        prompts.build_prompt("fix", run_dir, config=config)
    assert exc.value.err_id == "E_STAGE_NAME"


# --- run_stage ----------------------------------------------------------------------------------------------
def test_run_stage_writes_output_file_and_records_usage(workspace, config):
    run_dir = _make_run(workspace, stage="profiled", artifacts=("profile",))
    client = FakeClient({"jd": [_golden("jd")]})
    path = stages.run_stage("jd", run_dir, client=client, config=config)
    assert path == run_dir / "jd.json" and jsonio.load_json(path) == _golden("jd")
    assert client.calls[0]["model"] == gcfg.MODEL_HAIKU
    rows = [r for r in _usage_rows(run_dir) if r["kind"] == "api"]
    assert len(rows) == 1 and rows[0]["stage"] == "jd" and rows[0]["model"] == gcfg.MODEL_HAIKU
    assert rows[0]["input_tokens"] > 0 and rows[0]["output_tokens"] > 0 and rows[0]["attempt"] == 1
    assert any(r["kind"] == "packet" for r in _usage_rows(run_dir))


def test_max_tokens_comes_from_budgets(workspace, config, monkeypatch):
    run_dir = _make_run(workspace, stage="profiled", artifacts=("profile",))
    real = briefs.budgets()
    patched = {**real, "stages": {**real["stages"], "jd": {"input": 3000, "output": 1234}}}
    monkeypatch.setattr(briefs, "budgets", lambda: patched)
    client = FakeClient({"jd": [_golden("jd")]})
    stages.run_stage("jd", run_dir, client=client, config=config)
    assert client.calls[0]["max_tokens"] == 1234
    assert config.max_tokens("jd", fix=True) == max(1234, patched["stages"]["fix"]["output"])


def test_change_request_edits_file_goes_to_edits_dir(workspace, config):
    run_dir = _make_run(workspace, stage="tailored", artifacts=("profile", "jd", "match"), tailored=True)
    edits = _golden("edits-001")
    client = FakeClient({"change_request": [edits]})
    path = stages.run_stage("change_request", run_dir, client=client, config=config,
                            extra={"reply": "Make t-exp-1.b2 shorter"})
    assert path == run_dir / "edits" / "next.json" and jsonio.load_json(path) == edits


# --- local response cache -----------------------------------------------------------------------------------
def test_identical_second_call_hits_the_local_cache(workspace, config):
    run_dir = _make_run(workspace, stage="profiled", artifacts=("profile",))
    client = FakeClient({"jd": [_golden("jd"), _golden("jd")]})
    stages.run_stage("jd", run_dir, client=client, config=config)
    (run_dir / "jd.json").unlink()
    stages.run_stage("jd", run_dir, client=client, config=config)
    assert len(client.calls) == 1
    assert jsonio.load_json(run_dir / "jd.json") == _golden("jd")
    assert len([r for r in _usage_rows(run_dir) if r["kind"] == "api"]) == 1
    assert list((workspace / ".cache" / "gtjob" / "llm").glob("*.json"))


def test_no_cache_bypasses_reads_but_still_writes(workspace):
    run_dir = _make_run(workspace, stage="profiled", artifacts=("profile",))
    client = FakeClient({"jd": [_golden("jd")] * 3})
    stages.run_stage("jd", run_dir, client=client, config=gcfg.load_config(root=workspace, env={}))
    fresh = gcfg.load_config(root=workspace, env={}, no_cache=True)
    stages.run_stage("jd", run_dir, client=client, config=fresh)
    assert len(client.calls) == 2
    stages.run_stage("jd", run_dir, client=client, config=gcfg.load_config(root=workspace, env={}))
    assert len(client.calls) == 2  # the --no-cache run wrote its answer, so a normal run reads it


# --- fix loop -----------------------------------------------------------------------------------------------
def _tailor_run(workspace: Path) -> Path:
    return _make_run(workspace, stage="answers_applied", artifacts=("profile", "jd", "match", "questions"))


def _bad_plan() -> dict:
    plan = _golden("tailor-plan")
    plan["experience"][0]["bullets"][1]["text"] += f" Rolled out {INVENTED_TOOL} for service-to-service traffic."
    return plan


def test_tailor_fix_loop_reprompts_with_exact_violation_then_passes(workspace, config):
    run_dir = _tailor_run(workspace)
    client = FakeClient({"tailor": [_bad_plan(), _golden("tailor-plan")]})
    path = stages.run_stage_checked("tailor", run_dir, client=client, config=config)
    assert path == run_dir / "tailor-plan.json" and (run_dir / "tailored.json").is_file()
    assert len(client.calls) == 2
    first, second = client.calls
    fix_text = _text(second["blocks"])
    assert INVENTED_TOOL in fix_text and "# Stage: fix" in fix_text
    assert second["system"] == first["system"]  # the cached prefix is replayed unchanged
    assert [m["role"] for m in second["history"]] == ["user", "assistant"]
    assert second["history"][0]["content"] == first["blocks"]
    assert INVENTED_TOOL in second["history"][1]["content"]
    first_size = len(json.dumps(first["system"] + first["blocks"]))
    assert len(json.dumps(second["blocks"])) < first_size
    assert jsonio.load_json(path) == _golden("tailor-plan")
    rows = [r for r in _usage_rows(run_dir) if r["kind"] == "api"]
    assert [r["attempt"] for r in rows] == [1, 2] and all(r["stage"] == "tailor" for r in rows)
    assert any(r["kind"] == "packet" and r["stage"] == "fix" for r in _usage_rows(run_dir))


def test_violation_message_is_quoted_verbatim_in_the_fix_packet(workspace, config):
    run_dir = _tailor_run(workspace)
    client = FakeClient({"tailor": [_bad_plan(), _golden("tailor-plan")]})
    stages.run_stage_checked("tailor", run_dir, client=client, config=config)
    result = stages.run_check("tailor", run_dir)  # the plan is fixed now; the check passes
    assert result.code == 0
    packet = (run_dir / "briefs" / "fix.md").read_text(encoding="utf-8")
    violation_lines = [x for x in packet.splitlines() if INVENTED_TOOL in x and x.startswith("- ")]
    assert violation_lines and violation_lines[0][2:] in _text(client.calls[1]["blocks"])


def test_fix_loop_gives_up_after_max_attempts_with_violations(workspace, config):
    run_dir = _tailor_run(workspace)
    client = FakeClient({"tailor": [_bad_plan(), _bad_plan()]})
    with pytest.raises(CvtError) as exc:
        stages.run_stage_checked("tailor", run_dir, client=client, config=config)
    assert exc.value.err_id == "E_CHECK_FAILED" and exc.value.violations
    assert len(client.calls) == 2


def test_haiku_stage_escalates_to_sonnet_after_one_failed_check(workspace, config):
    run_dir = _make_run(workspace, stage="profiled", artifacts=("profile",))
    bad = dict(_golden("jd"), jd_sha256="0" * 64)
    client = FakeClient({"jd": [bad, _golden("jd")]})
    stages.run_stage_checked("jd", run_dir, client=client, config=config)
    assert [c["model"] for c in client.calls] == [gcfg.MODEL_HAIKU, gcfg.MODEL_SONNET]
    assert [r["model"] for r in _usage_rows(run_dir) if r["kind"] == "api"] == [gcfg.MODEL_HAIKU, gcfg.MODEL_SONNET]


def test_user_model_override_is_not_escalated(workspace):
    run_dir = _make_run(workspace, stage="profiled", artifacts=("profile",))
    cfg = gcfg.load_config(root=workspace, env={}, cli_models=["jd=claude-haiku-5-5"])
    bad = dict(_golden("jd"), jd_sha256="0" * 64)
    client = FakeClient({"jd": [bad, _golden("jd")]})
    stages.run_stage_checked("jd", run_dir, client=client, config=cfg)
    assert [c["model"] for c in client.calls] == [gcfg.MODEL_HAIKU, gcfg.MODEL_HAIKU]


def test_checked_stage_passes_first_time_without_a_fix_call(workspace, config):
    run_dir = _tailor_run(workspace)
    client = FakeClient({"tailor": [_golden("tailor-plan")]})
    stages.run_stage_checked("tailor", run_dir, client=client, config=config)
    assert len(client.calls) == 1
    assert [r["attempt"] for r in _usage_rows(run_dir) if r["kind"] == "api"] == [1]


def test_answer_parse_checked_runs_dry_run_apply(workspace, config):
    run_dir = _make_run(workspace, stage="awaiting_answers", artifacts=("profile", "jd", "match", "questions"))
    client = FakeClient({"answer_parse": [_golden("answers.round")]})
    path = stages.run_stage_checked("answer_parse", run_dir, client=client, config=config, extra={"reply": REPLY})
    assert path == run_dir / "answers.round.json"
    assert client.calls[0]["model"] == gcfg.MODEL_HAIKU


def test_non_check_failure_exit_is_raised_without_a_reprompt(workspace, config, monkeypatch):
    run_dir = _tailor_run(workspace)
    monkeypatch.setattr(stages, "run_check", lambda stage, rd: stages.CheckResult(
        4, {"error": {"id": "E_STATE", "message": "wrong stage", "hint": "run status"}}, []))
    client = FakeClient({"tailor": [_golden("tailor-plan")]})
    with pytest.raises(CvtError) as exc:
        stages.run_stage_checked("tailor", run_dir, client=client, config=config)
    assert exc.value.err_id == "E_STATE" and int(exc.value.code) == 4 and len(client.calls) == 1


def test_check_argv_resolves_out_paths_and_run_slug(workspace):
    run_dir = _make_run(workspace, stage="matched", artifacts=("profile", "jd", "match", "questions"))
    argv = stages.check_argv("answer_parse", run_dir)
    assert argv[:2] == ["answers-apply", run_dir.name]
    assert str(workspace / "out" / run_dir.name / "answers.round.json") in argv and "--dry-run" in argv


def test_fix_prompt_without_failed_state_uses_the_given_violations(workspace):
    run_dir = _tailor_run(workspace)
    fix = prompts.build_fix_prompt("answer_parse", run_dir, violations=[{"item_id": "q-1", "message": "unknown choice"}])
    assert "q-1: unknown choice" in _text(fix.blocks)
    with pytest.raises(CvtError):
        prompts.build_fix_prompt("answer_parse", run_dir)
