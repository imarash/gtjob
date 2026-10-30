"""WP-16: edits.apply_ops (pure) plus `cvt apply-edits` and `cvt approve` on the junior golden."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from cvtlib import attestations, cli, edits, jsonio, state
from cvtlib.errors import CvtError

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "tests" / "fixtures" / "golden" / "junior"
PERSON = "jamie-rivera"
SLUG = "junior"
CV_TEXT = "Jamie Rivera\njamie.rivera@example.com\n"
EXIT_OK, EXIT_CHECK, EXIT_STATE, EXIT_AWAITING = 0, 1, 4, 6


@pytest.fixture
def profile() -> dict:
    return jsonio.load_json(GOLDEN / "profile.json")


@pytest.fixture
def tailored() -> dict:
    return jsonio.load_json(GOLDEN / "tailored.json")


def op(name: str, target: str = "", **kw) -> dict:
    base = {"op": name, "target_id": target, "field": "", "value": "", "source_refs": [], "items": []}
    return {**base, **kw}


def bullet(t: dict, bid: str) -> dict:
    return edits.locate(t, bid)[1]


def apply_one(t: dict, profile: dict, *ops: dict) -> dict:
    return edits.apply_ops(t, list(ops), profile)


# --- pure ops -----------------------------------------------------------------------------------------
def test_apply_ops_is_pure(tailored, profile):
    before = copy.deepcopy(tailored)
    out = apply_one(tailored, profile, op("approve_all"), op("drop", "t-exp-1.b1"))
    assert tailored == before
    assert out is not tailored and not edits.pending_ids(out)


def test_approve_all_and_approve(tailored, profile):
    out = apply_one(tailored, profile, op("approve", "t-exp-1.b1", items=["t-sum"]))
    assert bullet(out, "t-exp-1.b1")["review"] == "approved" and out["summary"]["review"] == "approved"
    assert bullet(out, "t-exp-1.b2")["review"] == "pending"
    role = apply_one(tailored, profile, op("approve", "t-exp-1"))
    assert all(b["review"] == "approved" for b in role["experience"][0]["bullets"])
    assert bullet(role, "t-exp-2.b1")["review"] == "pending"
    assert not edits.pending_ids(apply_one(tailored, profile, op("approve_all")))


def test_reject_kept_drops_and_records_omitted(tailored, profile):
    out = apply_one(tailored, profile, op("reject", "t-exp-1.b1"))
    assert "t-exp-1.b1" not in [b["id"] for b in out["experience"][0]["bullets"]]
    assert {"profile_id": "exp-1.b1", "reason": edits.REASON_REJECTED} in out["omitted"]


def test_reject_rewritten_restores_original_text(tailored, profile):
    out = apply_one(tailored, profile, op("reject", "t-exp-1.b2"))
    b = bullet(out, "t-exp-1.b2")
    assert b["origin"] == "kept" and b["source_refs"] == ["exp-1.b2"]
    assert b["text"] == next(h["text"] for h in profile["work"][0]["highlights"] if h["id"] == "exp-1.b2")


def test_reject_attested_with_original_elsewhere_drops(tailored, profile):
    out = apply_one(tailored, profile, op("reject", "t-exp-1.b4"))  # exp-1.b3 is already t-exp-1.b3
    assert "t-exp-1.b4" not in [b["id"] for b in out["experience"][0]["bullets"]]


def test_reject_summary_restores_profile_summary_or_errors(tailored, profile):
    t = copy.deepcopy(tailored)
    t["summary"]["source_refs"] = ["sum-1"]
    out = apply_one(t, profile, op("reject", "t-sum"))
    assert out["summary"]["text"] == profile["summary"][0]["text"] and out["summary"]["source_refs"] == ["sum-1"]
    t["summary"]["source_refs"] = ["exp-1", "cert-1"]
    with pytest.raises(CvtError) as exc:
        apply_one(t, profile, op("reject", "t-sum"))  # no single sum-N source
    assert exc.value.err_id == edits.ERR_TARGET


def test_replace_text_sets_origin_and_needs_refs(tailored, profile):
    out = apply_one(tailored, profile, op("replace_text", "t-exp-1.b1", value="Built GitHub Actions pipelines.",
                                          source_refs=["exp-1.b1"]))
    b = bullet(out, "t-exp-1.b1")
    assert b["text"] == "Built GitHub Actions pipelines." and b["origin"] == "rewritten" and b["review"] == "pending"
    merged = apply_one(tailored, profile, op("replace_text", "t-exp-1.b1", value="x y", source_refs=["exp-1.b1", "exp-1.b2"]))
    assert bullet(merged, "t-exp-1.b1")["origin"] == "merged"
    attested = apply_one(tailored, profile, op("replace_text", "t-exp-1.b1", value="x y", source_refs=["exp-1.b1", "att-001"]))
    assert bullet(attested, "t-exp-1.b1")["origin"] == "attested"
    summary = apply_one(tailored, profile, op("replace_text", "t-sum", value="New summary.", source_refs=["sum-1"]))
    assert summary["summary"]["text"] == "New summary."
    with pytest.raises(CvtError) as exc:
        apply_one(tailored, profile, op("replace_text", "t-exp-1.b1", value="no refs"))
    assert exc.value.err_id == edits.ERR_REFS


def test_drop_items_and_extra_targets(tailored, profile):
    out = apply_one(tailored, profile, op("drop", "t-exp-1.b1", items=["t-exp-1.b3"]))
    ids = [b["id"] for b in out["experience"][0]["bullets"]]
    assert "t-exp-1.b1" not in ids and "t-exp-1.b3" not in ids
    assert "exp-1.b1" in [o["profile_id"] for o in out["omitted"]]
    assert "exp-1.b3" not in [o["profile_id"] for o in out["omitted"]]  # still cited by t-exp-1.b4
    role = apply_one(tailored, profile, op("drop", "t-exp-2"))
    assert [e["id"] for e in role["experience"]] == ["t-exp-1"]
    group = apply_one(tailored, profile, op("drop", "t-skl-3"))
    assert "t-skl-3" not in [g["id"] for g in group["skills"]]
    with pytest.raises(CvtError):
        apply_one(tailored, profile, op("drop", "t-sum"))


def test_drop_earlier_line_via_drop_and_set_field(tailored, profile):
    t = copy.deepcopy(tailored)
    t["earlier_experience"] = {"include": True, "review": "pending", "items": [{
        "profile_id": "exp-2", "employer": "Cedar Valley College", "title": "IT Support Intern",
        "start_date": "2023-07", "end_date": "2023-12"}]}
    assert apply_one(t, profile, op("drop", "t-earlier"))["earlier_experience"]["include"] is False
    off = apply_one(t, profile, op("set_field", field="include_earlier_experience", value="false"))
    assert off["earlier_experience"]["include"] is False
    on = apply_one(off, profile, op("set_field", field="include_earlier_experience", value="true"))
    assert on["earlier_experience"]["include"] is True


def test_restore_bullet_in_profile_order(tailored, profile):
    dropped = apply_one(tailored, profile, op("drop", "t-exp-1.b1"))
    assert "exp-1.b1" in [o["profile_id"] for o in dropped["omitted"]]
    out = apply_one(dropped, profile, op("restore", "exp-1.b1"))
    first = out["experience"][0]["bullets"][0]
    assert first["source_refs"] == ["exp-1.b1"] and first["origin"] == "kept" and first["priority"] == 3
    assert first["id"] not in [b["id"] for b in dropped["experience"][0]["bullets"]]
    assert "exp-1.b1" not in [o["profile_id"] for o in out["omitted"]]
    appended = apply_one(tailored, profile, op("restore", "exp-1.b6"))
    assert appended["experience"][0]["bullets"][-1]["source_refs"] == ["exp-1.b6"]
    assert "exp-1.b6" not in [o["profile_id"] for o in appended["omitted"]]


def test_restore_certification(tailored, profile):
    dropped = apply_one(tailored, profile, op("drop", "t-cert-1"))
    assert dropped["certifications"] == []
    assert "cert-1" in [o["profile_id"] for o in dropped["omitted"]]
    back = apply_one(dropped, profile, op("restore", "cert-1"))
    cert = back["certifications"][0]
    assert cert["id"] == "t-cert-1" and cert["profile_id"] == "cert-1"
    assert cert["name"] == "AWS Certified Cloud Practitioner" and cert["priority"] == 3
    assert "cert-1" not in [o["profile_id"] for o in back["omitted"]]
    with pytest.raises(CvtError) as present:
        apply_one(back, profile, op("restore", "cert-1"))
    assert present.value.err_id == edits.ERR_TARGET
    with pytest.raises(CvtError) as missing:
        apply_one(tailored, profile, op("restore", "cert-9"))
    assert missing.value.err_id == edits.ERR_TARGET


def test_restore_certification(tailored, profile):
    dropped = apply_one(tailored, profile, op("drop", "t-cert-1"))
    assert dropped["certifications"] == []
    dropped["omitted"].append({"profile_id": "cert-1", "reason": "test"})
    back = apply_one(dropped, profile, op("restore", "cert-1"))
    cert = back["certifications"][0]
    assert cert["id"] == "t-cert-1" and cert["profile_id"] == "cert-1"
    assert cert["name"] == "AWS Certified Cloud Practitioner" and cert["priority"] == 3
    assert "cert-1" not in [item["profile_id"] for item in back["omitted"]]
    with pytest.raises(CvtError) as present:
        apply_one(back, profile, op("restore", "cert-1"))
    assert present.value.err_id == edits.ERR_TARGET
    with pytest.raises(CvtError) as missing:
        apply_one(tailored, profile, op("restore", "cert-9"))
    assert missing.value.err_id == edits.ERR_TARGET


def test_restore_role_and_errors(tailored, profile):
    dropped = apply_one(tailored, profile, op("drop", "t-exp-1"))
    back = apply_one(dropped, profile, op("restore", "exp-1"))
    assert [e["id"] for e in back["experience"]] == ["t-exp-1", "t-exp-2"]
    assert back["experience"][0]["employer"] == "Brightfield Logistics" and len(back["experience"][0]["bullets"]) == 6
    with pytest.raises(CvtError) as exc:
        apply_one(dropped, profile, op("restore", "exp-1.b1"))  # its role is gone
    assert exc.value.err_id == edits.ERR_TARGET
    with pytest.raises(CvtError):
        apply_one(tailored, profile, op("restore", "exp-1.b1"))  # already present
    with pytest.raises(CvtError):
        apply_one(tailored, profile, op("restore", "skl-1"))


def test_move_before(tailored, profile):
    out = apply_one(tailored, profile, op("move_before", "t-exp-1.b3", value="t-exp-1.b1"))
    assert [b["id"] for b in out["experience"][0]["bullets"]][:3] == ["t-exp-1.b3", "t-exp-1.b1", "t-exp-1.b2"]
    skills = apply_one(tailored, profile, op("move_before", "t-skl-4", value="t-skl-1"))
    assert skills["skills"][0]["id"] == "t-skl-4"
    roles = apply_one(tailored, profile, op("move_before", "t-exp-2", value="t-exp-1"))
    assert roles["experience"][0]["id"] == "t-exp-2"
    with pytest.raises(CvtError):
        apply_one(tailored, profile, op("move_before", "t-exp-1.b1", value="t-exp-2.b1"))  # different parents


def test_set_field_each_field(tailored, profile):
    out = apply_one(
        tailored, profile,
        op("set_field", field="headline", value="Platform Engineering", source_refs=["exp-1"]),
        op("set_field", field="summary", value="Short summary.", source_refs=["sum-1"]),
        op("set_field", field="template", value="classic"),
        op("set_field", field="emphasis", value="Terraform"),
        op("set_field", field="page_target", value="2"),
        op("set_field", field="paper", value="a4"),
    )
    assert out["header"]["headline"] == "Platform Engineering" and "exp-1" in out["header"]["source_refs"]
    assert out["summary"]["text"] == "Short summary." and out["summary"]["source_refs"] == ["sum-1"]
    assert out["target"]["template"] == "classic" and out["target"]["emphasis"] == "Terraform"
    assert apply_one(out, profile, op("set_field", field="template", value="sidebar"))["target"]["template"] == "sidebar"
    assert out["target"]["page_target"] == 2
    for bad in (("template", "fancy"), ("page_target", "3"), ("paper", "legal"),
                ("include_earlier_experience", "maybe"), ("colour", "red")):
        with pytest.raises(CvtError):
            apply_one(tailored, profile, op("set_field", field=bad[0], value=bad[1]))


def test_add_and_remove_skill(tailored, profile):
    out = apply_one(tailored, profile, op("add_skill", "t-skl-2", value="Make", source_refs=["skl-2"]))
    assert "Make" in [i["name"] for i in out["skills"][1]["items"]]
    again = apply_one(out, profile, op("add_skill", "t-skl-2", value="make", source_refs=["skl-2"]))
    assert len(again["skills"][1]["items"]) == len(out["skills"][1]["items"])
    gone = apply_one(out, profile, op("remove_skill", "t-skl-2", value="git"))
    assert "Git" not in [i["name"] for i in gone["skills"][1]["items"]]
    with pytest.raises(CvtError) as exc:
        apply_one(tailored, profile, op("remove_skill", "t-skl-2", value="Rust"))
    assert exc.value.err_id == edits.ERR_TARGET
    with pytest.raises(CvtError) as exc:
        apply_one(tailored, profile, op("add_skill", "t-skl-2", value="Make"))
    assert exc.value.err_id == edits.ERR_REFS
    emptied = apply_one(tailored, profile, *[op("remove_skill", "t-skl-3", value=n) for n in ("Python", "Bash", "PowerShell")])
    assert "t-skl-3" not in [g["id"] for g in emptied["skills"]]


def test_set_priority(tailored, profile):
    out = apply_one(tailored, profile, op("set_priority", "t-exp-1.b1", value="5", items=["t-skl-1", "t-exp-2"]))
    assert bullet(out, "t-exp-1.b1")["priority"] == 5 and out["skills"][0]["priority"] == 5
    assert out["experience"][1]["priority"] == 5
    for bad in ("0", "six", ""):
        with pytest.raises(CvtError):
            apply_one(tailored, profile, op("set_priority", "t-exp-1.b1", value=bad))
    with pytest.raises(CvtError):
        apply_one(tailored, profile, op("set_priority", "t-sum", value="1"))


def test_unknown_target_and_op_name_the_op(tailored, profile):
    with pytest.raises(CvtError) as exc:
        apply_one(tailored, profile, op("approve_all"), op("drop", "t-exp-9.b9"))
    assert exc.value.err_id == edits.ERR_TARGET and exc.value.message.startswith("op 2 (drop t-exp-9.b9)")
    assert exc.value.violations[0]["item_id"] == "t-exp-9.b9"
    with pytest.raises(CvtError) as exc:
        apply_one(tailored, profile, op("explode", "t-sum"))
    assert exc.value.err_id == edits.ERR_OP


# --- commands -----------------------------------------------------------------------------------------
@pytest.fixture
def run(workspace: Path) -> Path:
    cv = workspace / "cv.txt"
    cv.write_text(CV_TEXT, encoding="utf-8")
    run_dir = state.create_run(cv, "text", "jd", "Junior DevOps Engineer at Harbor Point", {}, slug=SLUG)
    st = state.load(run_dir)
    for name, art in (("profile.json", "profile"), ("jd.json", "jd"), ("tailored.json", "tailored")):
        shutil.copy(GOLDEN / name, run_dir / name)
        state.record_artifact(run_dir, st, art, name, cascade=False)
    st["person_slug"] = PERSON
    state.set_stage(st, "tailored")
    state.save(run_dir, st)
    store = attestations.load_store(PERSON)
    proposal = jsonio.load_json(GOLDEN / "answers.round.json")["items"][0]["attestations"][0]
    attestations.add(store, proposal, run_id=st["run_slug"], question_id="q-1")
    attestations.save_store(PERSON, store)
    return run_dir


def cvt(capsys, *args: str) -> tuple[int, dict]:
    code = cli.main(["--json", *args])
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else {}


def write_edits(run_dir: Path, *ops: dict, name: str = "next.json") -> Path:
    path = run_dir / "edits" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"schema_version": "1", "run_id": SLUG, "source": "checkpoint2",
                                "raw_text": "test", "ops": list(ops)}), encoding="utf-8")
    return path


def test_golden_edits_001_approves_and_activates(run, capsys):
    shutil.copy(GOLDEN / "edits-001.json", run / "edits-001.json")
    code, env = cvt(capsys, "apply-edits", run.name, str(run / "edits-001.json"))
    assert code == EXIT_OK, env
    assert env["stage"] == "approved" and env["data"]["version"] == 2 and env["data"]["activated"] == ["att-001"]
    t = jsonio.load_json(run / "tailored.json")
    assert t["version"] == 2 and not edits.pending_ids(t)
    assert "cutting" in bullet(t, "t-exp-1.b5")["text"] and bullet(t, "t-exp-1.b2")["origin"] == "kept"
    assert (run / "edits" / "001.json").is_file()
    assert (run / "tailored.history" / "v1.json").is_file() and (run / "tailored.history" / "v2.json").is_file()
    assert attestations.get(attestations.load_store(PERSON), "att-001")["status"] == "active"
    st = state.load(run)
    assert st["checkpoints"]["cp2"] == "done" and st["attestations_used"] == ["att-001"]
    assert state.artifact(st, "edits")["path"] == "edits/001.json"
    changed = {i["id"]: i["kind"] for i in env["data"]["items"]}
    assert changed == {"t-exp-1.b2": "changed", "t-exp-1.b5": "changed"}


def test_batch_is_atomic_on_bad_op(run, capsys):
    before = (run / "tailored.json").read_bytes()
    path = write_edits(run, op("drop", "t-exp-1.b1"), op("drop", "t-exp-9.b9"))
    code, env = cvt(capsys, "apply-edits", run.name, str(path))
    assert code == EXIT_CHECK and env["error"]["id"] == edits.ERR_TARGET
    assert (run / "tailored.json").read_bytes() == before
    assert not (run / "edits" / "001.json").exists() and not (run / "tailored.history").exists()
    st = state.load(run)
    assert st["stage"] == "tailored" and st["status"] == "failed"


def test_invented_tool_is_rejected(run, capsys):
    before = (run / "tailored.json").read_bytes()
    text = "Built GitHub Actions pipelines for 12 services with Linkerd, cutting deploy time from 25 minutes to 8 minutes."
    path = write_edits(run, op("replace_text", "t-exp-1.b1", value=text, source_refs=["exp-1.b1"]), op("approve_all"))
    code, env = cvt(capsys, "apply-edits", run.name, str(path))
    assert code == EXIT_CHECK and env["error"]["id"] == "E_CHECK_FAILED"
    assert any("Linkerd" in v["message"] for v in env["data"]["violations"])
    assert (run / "tailored.json").read_bytes() == before


def test_invalid_edits_file_is_rejected(run, capsys):
    path = run / "edits" / "bad.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"schema_version": "1", "ops": []}), encoding="utf-8")
    code, env = cvt(capsys, "apply-edits", run.name, str(path))
    assert code == EXIT_CHECK and env["error"]["id"] == "E_SCHEMA"
    code, env = cvt(capsys, "apply-edits", run.name, str(run / "missing.json"))
    assert code != EXIT_OK and env["error"]["id"] == "E_EDITS_NOT_FOUND"


def test_apply_edits_with_pending_items_awaits_approval(run, capsys):
    path = write_edits(run, op("drop", "t-exp-1.b1"))
    code, env = cvt(capsys, "apply-edits", run.name, str(path))
    assert code == EXIT_OK and env["stage"] == "awaiting_approval"
    assert env["data"]["pending"] and env["data"]["items"] == [
        dict(env["data"]["items"][0], id="t-exp-1.b1", kind="dropped")]
    st = state.load(run)
    assert st["status"] == "awaiting_user" and st["pending"]["kind"] == "approval" and st["checkpoints"]["cp2"] == "pending"
    assert attestations.get(attestations.load_store(PERSON), "att-001")["status"] == "proposed"


def test_edit_numbers_increment_and_options_reach_state(run, capsys):
    for name in ("one.json", "two.json"):
        path = write_edits(run, op("set_field", field="template", value="classic"),
                           op("set_field", field="page_target", value="2"), op("set_field", field="paper", value="a4"),
                           name=name)
        code, _ = cvt(capsys, "apply-edits", run.name, str(path))
        assert code == EXIT_OK
    assert (run / "edits" / "001.json").is_file() and (run / "edits" / "002.json").is_file()
    opts = state.load(run)["options"]
    assert (opts["template"], opts["page_target"], opts["paper"]) == ("classic", 2, "a4")
    assert jsonio.load_json(run / "tailored.json")["version"] == 3


def test_approve_lists_pending_then_all_activates(run, capsys):
    code, env = cvt(capsys, "approve", run.name)
    assert code == EXIT_AWAITING and env["error"]["id"] == "E_PENDING_ITEMS"
    ids = [v["item_id"] for v in env["data"]["violations"]]
    assert "t-sum" in ids and "t-exp-1.b1" in ids
    assert state.load(run)["stage"] == "awaiting_approval"
    assert attestations.get(attestations.load_store(PERSON), "att-001")["status"] == "proposed"
    code, env = cvt(capsys, "approve", run.name, "--all")
    assert code == EXIT_OK and env["stage"] == "approved" and env["data"]["activated"] == ["att-001"]
    t = jsonio.load_json(run / "tailored.json")
    assert not edits.pending_ids(t) and t["experience"][0]["review"] == "approved"
    assert attestations.get(attestations.load_store(PERSON), "att-001")["status"] == "active"
    st = state.load(run)
    assert st["attestations_used"] == ["att-001"] and st["checkpoints"]["cp2"] == "done" and st["status"] == "ok"
    assert state.artifact(st, "tailored")["stale"] is False


def test_approve_after_individual_approvals_needs_no_flag(run, capsys):
    path = write_edits(run, op("approve", "t-sum"), op("approve", "t-skl-1", items=["t-skl-2", "t-skl-3", "t-skl-4"]),
                       op("approve", "t-exp-1"), op("approve", "t-exp-2"))
    code, env = cvt(capsys, "apply-edits", run.name, str(path))
    assert code == EXIT_OK and env["stage"] == "awaiting_approval" and env["data"]["pending"] == []
    code, env = cvt(capsys, "approve", run.name)
    assert code == EXIT_OK and env["stage"] == "approved"


def test_approve_leaves_unresolved_scope_proposed(run, capsys):
    store = attestations.load_store(PERSON)
    proposal = {**jsonio.load_json(GOLDEN / "answers.round.json")["items"][0]["attestations"][0],
                "claim": "Kafka", "terms": ["Kafka"], "placement": "skills",
                "scope": {"kind": "unresolved", "role_label": "", "item_ids": [], "description": "the relevant roles"}}
    attestations.add(store, proposal, run_id=run.name, question_id="q-2")
    attestations.save_store(PERSON, store)
    code, env = cvt(capsys, "approve", run.name, "--all")
    assert code == EXIT_OK and env["data"]["activated"] == ["att-001"] and env["data"]["unresolved"] == ["att-002"]
    assert attestations.get(attestations.load_store(PERSON), "att-002")["status"] == "proposed"


def test_regression_after_approval_returns_to_awaiting_approval(run, capsys):
    assert cvt(capsys, "approve", run.name, "--all")[0] == EXIT_OK
    path = write_edits(run, op("drop", "t-exp-2.b2"))
    code, env = cvt(capsys, "apply-edits", run.name, str(path))
    assert code == EXIT_OK and env["stage"] == "awaiting_approval"
    st = state.load(run)
    assert st["checkpoints"]["cp2"] == "pending" and st["pending"]["kind"] == "approval"
    code, env = cvt(capsys, "approve", run.name)  # nothing pending: a plain approve is enough
    assert code == EXIT_OK and env["stage"] == "approved"


def test_approve_does_not_regress_a_rendered_run(run, capsys):
    assert cvt(capsys, "approve", run.name, "--all")[0] == EXIT_OK
    st = state.load(run)
    state.set_stage(st, "rendered")
    state.save(run, st)
    code, env = cvt(capsys, "approve", run.name)
    assert code == EXIT_OK and env["stage"] == "rendered"


def test_drop_earlier_line_command(run, capsys):
    t = jsonio.load_json(run / "tailored.json")
    t["earlier_experience"] = {"include": True, "review": "approved", "items": [{
        "profile_id": "exp-2", "employer": "Cedar Valley College", "title": "IT Support Intern",
        "start_date": "2023-07", "end_date": "2023-12"}]}
    jsonio.dump_json(t, run / "tailored.json")
    path = write_edits(run, op("set_field", field="include_earlier_experience", value="false"))
    code, env = cvt(capsys, "apply-edits", run.name, str(path))
    assert code == EXIT_OK
    assert jsonio.load_json(run / "tailored.json")["earlier_experience"]["include"] is False
    assert any(i["id"] == "t-earlier" and i["kind"] == "dropped" for i in env["data"]["items"])


def test_stage_before_tailored_is_refused(run, capsys):
    st = state.load(run)
    state.set_stage(st, "answers_applied")
    state.save(run, st)
    for args in (("approve", run.name), ("apply-edits", run.name, str(write_edits(run, op("approve_all"))))):
        code, env = cvt(capsys, *args)
        assert code == EXIT_STATE and env["error"]["id"] == "E_STAGE"
