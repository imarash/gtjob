from __future__ import annotations

import datetime
import json

import pytest

from cvtlib import jsonio, schemas, state
from cvtlib.errors import CvtError, ExitCode

CVT = state.CVT_COMMAND
JD_TEXT = "# Staff Platform & Reliability Engineer at Example Corp\n\nBuild and run things.\n"


@pytest.fixture
def cv_file(tmp_path):
    p = tmp_path / "cv.txt"
    p.write_text("Jane Example\nSRE at Initech\n", encoding="utf-8")
    return p


def _new_run(cv_file, **kw):
    kw.setdefault("jd_kind", "text")
    kw.setdefault("jd_ref", "pasted")
    kw.setdefault("jd_text", JD_TEXT)
    kw.setdefault("options", {})
    return state.create_run(cv_file, kw["jd_kind"], kw["jd_ref"], kw["jd_text"], kw["options"], kw.get("slug"))


def _write(run_dir, rel, text="{}"):
    p = run_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return rel


def test_stage_tables_match_contract():
    assert state.STAGES[0] == "initialized" and state.STAGES[-1] == "reported" and len(state.STAGES) == 13
    assert state.ARTIFACT_STAGE["profile_map"] == "profiled"
    assert state.ARTIFACT_STAGE["digest"] == "jd_analyzed"
    assert state.ARTIFACT_STAGE["tailor_plan"] == "tailored"
    assert "usage" not in state.ARTIFACT_STAGE
    assert set(state.ARTIFACT_STAGE.values()) <= set(state.STAGES)
    schema_names = set(schemas.load_schema("state")["properties"]["artifacts"]["items"]["properties"]["name"]["enum"])
    assert set(state.ARTIFACT_STAGE) | {"usage"} == schema_names


def test_create_run_layout(workspace, cv_file):
    run = _new_run(cv_file)
    today = datetime.date.today().strftime("%Y%m%d")
    assert run == workspace / "out" / f"{today}-staff-platform-reliability-engineer-at"
    assert (run / "inputs" / "cv.txt").read_bytes() == cv_file.read_bytes()
    assert (run / "inputs" / "jd.md").read_text(encoding="utf-8") == JD_TEXT
    st = state.load(run)
    assert st["stage"] == "initialized" and st["status"] == "ok"
    assert st["ingest"]["method"] == "none" and st["checkpoints"] == {"cp1": "not_started", "cp2": "not_started"}
    assert st["inputs"]["cv"]["sha256"] == jsonio.sha256_file(run / "inputs" / "cv.txt")
    assert st["inputs"]["jd"]["sha256"] == jsonio.sha256_file(run / "inputs" / "jd.md")
    assert st["inputs"]["cv"]["format"] == "txt" and st["inputs"]["jd"]["kind"] == "text"
    assert st["options"]["template"] == "modern" and st["options"]["page_target"] == 2
    assert st["next_action"] == f"Run: {CVT} ingest {st['run_slug']}"
    assert st["history"][0]["event"] == "init" and st["history"][0]["host"] == "unknown"
    assert schemas.validate(st, "state") == []


def test_slug_rules(workspace, cv_file, tmp_path):
    jd_file = tmp_path / "Staff Platform SRE.md"
    jd_file.write_text(JD_TEXT, encoding="utf-8")
    run = state.create_run(cv_file, "file", str(jd_file), None, {})
    assert run.name.endswith("-staff-platform-sre")
    assert (run / "inputs" / "jd.md").read_text(encoding="utf-8") == JD_TEXT
    again = state.create_run(cv_file, "file", str(jd_file), None, {})
    assert again.name == run.name + "-2"
    custom = _new_run(cv_file, slug="My Custom Role")
    assert custom.name.endswith("-my-custom-role")
    anon = _new_run(cv_file, jd_text="!!!\n???\n")
    sha6 = jsonio.sha256_bytes(b"!!!\n???\n")[:6]
    assert anon.name.endswith(f"-jd-{sha6}")


def test_url_without_text_writes_placeholder(workspace, cv_file):
    run = state.create_run(cv_file, "url", "https://example.com/jobs/1", None, {"template": "classic"})
    assert (run / "inputs" / "jd.md").read_text() == "<!-- jd-url: https://example.com/jobs/1 -->\n"
    st = state.load(run)
    assert st["inputs"]["jd"]["kind"] == "url" and st["options"]["template"] == "classic"


def test_create_run_rejects_bad_input(workspace, tmp_path, cv_file):
    with pytest.raises(CvtError) as info:
        state.create_run(tmp_path / "missing.pdf", "text", "", "x", {})
    assert info.value.err_id == "E_CV_NOT_FOUND" and info.value.code == ExitCode.INPUT
    rtf = tmp_path / "cv.rtf"
    rtf.write_text("x")
    with pytest.raises(CvtError) as info:
        state.create_run(rtf, "text", "", "x", {})
    assert info.value.err_id == "E_CV_FORMAT"
    with pytest.raises(CvtError) as info:
        state.create_run(cv_file, "text", "", "   ", {})
    assert info.value.err_id == "E_JD_EMPTY"
    with pytest.raises(CvtError):
        state.create_run(cv_file, "text", "", "jd", {"template": "fancy"})  # fails schema on save


@pytest.mark.parametrize("stage", state.STAGES)
def test_next_action_per_stage(workspace, cv_file, stage):
    run = _new_run(cv_file)
    st = state.load(run)
    slug = st["run_slug"]
    state.set_stage(st, stage)
    text = state.next_action_for(st, slug)
    assert "{" not in text
    if stage != "reported":
        assert CVT in text and (slug in text or stage == "awaiting_approval")
    expected_fragment = {
        "initialized": f"ingest {slug}", "ingested": "profile-cache", "profiled": "brief jd",
        "jd_analyzed": "brief match", "matched": "brief questions", "awaiting_answers": "answers-apply",
        "answers_applied": "brief tailor", "tailored": "diff", "awaiting_approval": "approve",
        "approved": "fit", "rendered": "validate", "validated": "report", "reported": "Done.",
    }[stage]
    assert expected_fragment in text
    state.save(run, st)
    assert state.load(run)["next_action"] == text


def test_next_action_failed_variants(workspace, cv_file):
    run = _new_run(cv_file)
    st = state.load(run)
    slug = st["run_slug"]
    st["status"] = "failed"
    state.add_history(st, "jd-check")
    state.add_error(st, "E_STATE", "boom")
    assert state.next_action_for(st, slug) == f"Fix the reported problem, then rerun: {CVT} jd-check {slug}"
    state.add_error(st, "E_SCHEMA", "bad")
    assert state.next_action_for(st, slug) == (
        f"Run {CVT} brief fix {slug}, patch the listed items, then rerun: {CVT} jd-check {slug}"
    )


def test_staleness_cascade(workspace, cv_file):
    run = _new_run(cv_file)
    st = state.load(run)
    for name, rel in [("cv_txt", "cv.txt"), ("profile", "profile.json"), ("jd", "jd.json"),
                      ("match", "match.json"), ("tailored", "tailored.json")]:
        state.record_artifact(run, st, name, _write(run, rel))
    assert not any(a["stale"] for a in st["artifacts"])
    state.record_artifact(run, st, "profile", "profile.json")
    stale = {a["name"] for a in st["artifacts"] if a["stale"]}
    assert stale == {"jd", "match", "tailored"}
    assert state.artifact(st, "profile")["stale"] is False and state.artifact(st, "cv_txt")["stale"] is False
    assert len(st["artifacts"]) == 5  # re-recording replaces
    state.record_artifact(run, st, "jd", "jd.json")  # refresh jd: clears its own flag, stales match+tailored
    assert state.artifact(st, "jd")["stale"] is False
    assert state.artifact(st, "match")["stale"] is True


def test_cascade_false_leaves_downstream_alone(workspace, cv_file):
    run = _new_run(cv_file)
    st = state.load(run)
    state.record_artifact(run, st, "questions", _write(run, "questions.json"))
    state.record_artifact(run, st, "tailored", _write(run, "tailored.json"))
    state.record_artifact(run, st, "questions", "questions.json", cascade=False)
    assert state.artifact(st, "tailored")["stale"] is False
    state.record_artifact(run, st, "questions", "questions.json")
    assert state.artifact(st, "tailored")["stale"] is True


def test_usage_artifact_never_stale_and_no_cascade(workspace, cv_file):
    run = _new_run(cv_file)
    st = state.load(run)
    state.record_artifact(run, st, "tailored", _write(run, "tailored.json"))
    state.record_artifact(run, st, "usage", _write(run, "usage.jsonl", ""))
    state.record_artifact(run, st, "cv_txt", _write(run, "cv.txt"))
    assert state.artifact(st, "usage")["stale"] is False and state.artifact(st, "usage")["stage"] == ""
    assert state.artifact(st, "tailored")["stale"] is True
    state.save(run, st)  # still schema-valid


def test_require_artifact(workspace, cv_file):
    run = _new_run(cv_file)
    st = state.load(run)
    with pytest.raises(CvtError) as info:
        state.require_artifact(run, st, "jd")
    assert info.value.err_id == "E_ARTIFACT_MISSING" and info.value.code == ExitCode.STATE
    state.record_artifact(run, st, "jd", _write(run, "jd.json"))
    state.record_artifact(run, st, "profile", _write(run, "profile.json"))
    assert state.require_artifact(run, st, "jd", allow_stale=True) == run / "jd.json"
    with pytest.raises(CvtError) as info:
        state.require_artifact(run, st, "jd")
    assert info.value.err_id == "E_ARTIFACT_STALE" and info.value.code == ExitCode.STATE
    (run / "profile.json").unlink()
    with pytest.raises(CvtError) as info:
        state.require_artifact(run, st, "profile")
    assert info.value.err_id == "E_ARTIFACT_MISSING"


def test_unknown_artifact_name(workspace, cv_file):
    run = _new_run(cv_file)
    with pytest.raises(CvtError) as info:
        state.record_artifact(run, state.load(run), "bogus", "x")
    assert info.value.err_id == "E_ARTIFACT_NAME"


def test_require_stage(workspace, cv_file):
    run = _new_run(cv_file)
    st = state.load(run)
    state.require_stage(st, "initialized")
    with pytest.raises(CvtError) as info:
        state.require_stage(st, "ingested")
    assert info.value.err_id == "E_STAGE" and info.value.hint == st["next_action"]
    state.set_stage(st, "matched")
    state.require_stage(st, "jd_analyzed")
    assert state.stage_index("matched") == 4


def test_set_stage_pending_default_and_custom(workspace, cv_file):
    st = state.load(_new_run(cv_file))
    pending = {"kind": "questions", "question_ids": ["q-1"], "message": "ask"}
    state.set_stage(st, "awaiting_answers", "awaiting_user", pending)
    assert st["status"] == "awaiting_user" and st["pending"] == pending
    state.set_stage(st, "answers_applied")
    assert st["pending"] == {"kind": "none", "question_ids": [], "message": ""}
    with pytest.raises(CvtError):
        state.set_stage(st, "nonsense")


def test_save_guards_invalid_state(workspace, cv_file):
    run = _new_run(cv_file)
    st = state.load(run)
    before = (run / "state.json").read_bytes()
    st["stage"] = "bogus-stage"
    with pytest.raises(CvtError):
        state.save(run, st)
    st["stage"] = "ingested"
    st["status"] = "weird"
    with pytest.raises(CvtError) as info:
        state.save(run, st)
    assert info.value.err_id == "E_STATE_INVALID" and info.value.code == ExitCode.INTERNAL
    assert (run / "state.json").read_bytes() == before


def test_load_rejects_corrupt_state(workspace, cv_file):
    run = _new_run(cv_file)
    data = json.loads((run / "state.json").read_text())
    del data["stage"]
    (run / "state.json").write_text(json.dumps(data))
    with pytest.raises(CvtError) as info:
        state.load(run)
    assert info.value.err_id == "E_STATE_INVALID"


def test_host_detection_and_history(workspace, cv_file, monkeypatch):
    run = _new_run(cv_file)
    st = state.load(run)
    monkeypatch.setenv("GTJOB_HOST", "claude_code")
    assert state.current_host() == "claude_code"
    state.add_history(st, "ingest", "pdftotext")
    assert st["history"][-1]["host"] == "claude_code" and st["options"]["host"] == "claude_code"
    assert st["history"][-1]["stage"] == "initialized" and st["history"][-1]["detail"] == "pdftotext"
    monkeypatch.setenv("GTJOB_HOST", "bogus")
    assert state.current_host() == "unknown"
    state.save(run, st)


def test_save_updates_timestamp_and_roundtrips(workspace, cv_file):
    run = _new_run(cv_file)
    st = state.load(run)
    st["updated_at"] = "2000-01-01T00:00:00Z"
    state.save(run, st)
    assert state.load(run)["updated_at"] != "2000-01-01T00:00:00Z"
