"""WP-29: `assemble` (tailor-plan.json -> tailored.json) on the junior golden run."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from cvtlib import assemble, cli, jsonio, state

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
GOLDEN = FIXTURES / "golden" / "junior"
CV = FIXTURES / "cv" / "jamie-rivera-junior.txt"
JD_FILE = FIXTURES / "jds" / "junior-devops-engineer.md"
PERSON = "jamie-rivera"
GOLDEN_SLUG = "golden-junior"


def _golden(name: str) -> dict:
    return json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))


def _atts(*ids: str, **changes) -> list[dict]:
    rows = json.loads((FIXTURES / "provenance" / "attestations.json").read_text(encoding="utf-8"))
    return [dict(a, **changes) for a in rows if a["id"] in ids]


def _unit_state(**options) -> dict:
    sha = hashlib.sha256((GOLDEN / "profile.json").read_bytes()).hexdigest()
    return {"run_slug": GOLDEN_SLUG, "options": {"auto": False, "page_target": 1, "template": "modern", **options},
            "artifacts": [{"name": "profile", "sha256": sha}]}


def _run(plan: dict, atts: list[dict] | None = None, **options) -> tuple[dict, list[dict]]:
    atts = _atts("att-001") if atts is None else atts
    return assemble.assemble(plan, _golden("profile"), atts, _golden("jd"), _unit_state(**options))


def _bullets(plan: dict) -> list[dict]:
    return plan["experience"][0]["bullets"]


# --- the golden plan ----------------------------------------------------------------------------------------
def test_golden_plan_assembles_to_golden_tailored():
    tailored, violations = _run(_golden("tailor-plan"))
    assert violations == []
    assert tailored == _golden("tailored")


def test_auto_mode_marks_review_auto():
    tailored, violations = _run(_golden("tailor-plan"), auto=True)
    assert violations == []
    reviews = {tailored["summary"]["review"], tailored["skills"][0]["review"], tailored["experience"][0]["review"],
               tailored["experience"][0]["bullets"][0]["review"]}
    assert reviews == {"auto"}


def test_kept_bullets_are_verbatim_profile_text():
    tailored, _v = _run(_golden("tailor-plan"))
    profile = _golden("profile")
    first = tailored["experience"][0]["bullets"][0]
    assert first["origin"] == "kept" and first["text"] == profile["work"][0]["highlights"][0]["text"]


def test_short_name_used_only_when_a_contiguous_substring():
    plan = _golden("tailor-plan")
    plan["certifications"][0]["short_name"] = "Cloud Practitioner"
    assert _run(plan)[0]["certifications"][0]["name"] == "Cloud Practitioner"
    plan["certifications"][0]["short_name"] = "Practitioner Cloud"
    assert _run(plan)[0]["certifications"][0]["name"] == "AWS Certified Cloud Practitioner"


def test_education_details_only_when_requested():
    plan = _golden("tailor-plan")
    plan["education"][0]["include_details"] = True
    edu = _run(plan)[0]["education"][0]
    assert edu["details"] == _golden("profile")["education"][0]["text"]


# --- plan_ref violations: one mutation each ----------------------------------------------------------------
def _plan_ref(violations: list[dict]) -> list[dict]:
    return [v for v in violations if v["code"] == "plan_ref"]


def test_unknown_experience_id():
    plan = _golden("tailor-plan")
    plan["experience"][1]["profile_id"] = "exp-9"
    found = _plan_ref(_run(plan)[1])
    assert [v["item_id"] for v in found] == ["exp-9"]


def test_keep_bullet_with_text():
    plan = _golden("tailor-plan")
    _bullets(plan)[0]["text"] = "Built pipelines."
    found = _plan_ref(_run(plan)[1])
    assert found and "keep bullet must have empty text" in found[0]["message"]
    assert found[0]["item_id"] == "t-exp-1.b1"


def test_merge_with_fewer_than_two_from():
    plan = _golden("tailor-plan")
    _bullets(plan)[1].update(op="merge")
    found = _plan_ref(_run(plan)[1])
    assert found and "at least 2 from" in found[0]["message"]


def test_attested_bullet_without_attestation_in_scope():
    plan = _golden("tailor-plan")
    att = _atts("att-001", scope={"kind": "items", "role_label": "", "item_ids": ["exp-2"], "description": ""})
    found = _plan_ref(_run(plan, att)[1])
    assert found and "no active attestation in scope" in found[0]["message"]


def test_attested_bullet_with_unknown_attestation():
    plan = _golden("tailor-plan")
    _bullets(plan)[3]["extra_refs"] = ["att-099"]
    found = _plan_ref(_run(plan)[1])
    assert found and "no active attestation in scope" in found[0]["message"]


def test_attested_bullet_with_revoked_attestation():
    found = _plan_ref(_run(_golden("tailor-plan"), _atts("att-001", status="revoked"))[1])
    assert found and "no active attestation in scope" in found[0]["message"]


def test_attested_bullet_without_att_ref():
    plan = _golden("tailor-plan")
    _bullets(plan)[3]["extra_refs"] = []
    found = _plan_ref(_run(plan)[1])
    assert found and "att-* id" in found[0]["message"]


def test_from_not_a_bullet_of_the_entry():
    plan = _golden("tailor-plan")
    _bullets(plan)[0]["from"] = ["exp-2.b1"]
    found = _plan_ref(_run(plan)[1])
    assert found and "not an item of exp-1" in found[0]["message"]


def test_from_unknown_id():
    plan = _golden("tailor-plan")
    _bullets(plan)[0]["from"] = ["exp-1.b99"]
    found = _plan_ref(_run(plan)[1])
    assert found and "not in the profile" in found[0]["message"]


def test_keep_from_must_be_a_highlight():
    plan = _golden("tailor-plan")
    _bullets(plan)[0]["from"] = ["exp-1"]
    found = _plan_ref(_run(plan)[1])
    assert found and "not a bullet" in found[0]["message"]


def test_unknown_certification_and_education_ids():
    plan = _golden("tailor-plan")
    plan["certifications"][0]["profile_id"] = "cert-7"
    plan["education"][0]["profile_id"] = "edu-7"
    assert {v["item_id"] for v in _plan_ref(_run(plan)[1])} == {"cert-7", "edu-7"}


def test_engagement_must_belong_to_the_entry():
    plan = _golden("tailor-plan")
    plan["experience"][0]["engagements"] = [{"profile_id": "exp-1.e3", "priority": 2, "bullets": []}]
    assert [v["item_id"] for v in _plan_ref(_run(plan)[1])] == ["exp-1.e3"]


# --- skills and provenance ---------------------------------------------------------------------------------
def test_unsupported_skill():
    plan = _golden("tailor-plan")
    plan["skills"][0]["items"].append({"name": "Kubernetes", "source_refs": []})
    _tailored, violations = _run(plan)
    found = [v for v in violations if v["code"] == "skill_unsupported"]
    assert found and found[0]["item_id"] == "t-skl-1" and "Kubernetes" in found[0]["message"]


def test_skill_resolves_to_attestation_when_no_group_has_it():
    tailored, violations = _run(_golden("tailor-plan"))
    helm = next(i for g in tailored["skills"] for i in g["items"] if i["name"] == "Helm")
    assert violations == [] and helm["source_refs"] == ["att-001"]


def test_skill_falls_back_to_highlights():
    plan = _golden("tailor-plan")
    profile = _golden("profile")
    profile["skills"][0]["keywords"].remove("Docker")
    tailored, violations = assemble.assemble(plan, profile, _atts("att-001"), _golden("jd"), _unit_state())
    docker = next(i for g in tailored["skills"] for i in g["items"] if i["name"] == "Docker")
    assert docker["source_refs"] == ["exp-1.b3", "exp-1.b6"] and violations == []


def test_invented_employer_in_rewrite_bullet_is_caught_by_provenance():
    plan = _golden("tailor-plan")
    _bullets(plan)[1]["text"] = "Replaced manual console changes at Contoso Labs with Terraform modules."
    _tailored, violations = _run(plan)
    found = [v for v in violations if v["code"] == "unsupported_term"]
    assert found and found[0]["item_id"] == "t-exp-1.b2" and "Contoso" in found[0]["message"]


def test_invented_metric_in_rewrite_bullet_is_caught():
    plan = _golden("tailor-plan")
    _bullets(plan)[1]["text"] = "Replaced manual console changes across 40 environments with Terraform modules."
    assert any(v["code"] == "unsupported_number" for v in _run(plan)[1])


def test_violations_are_returned_together():
    plan = copy.deepcopy(_golden("tailor-plan"))
    _bullets(plan)[0]["text"] = "x"
    plan["skills"][0]["items"].append({"name": "Kubernetes", "source_refs": []})
    codes = {v["code"] for v in _run(plan)[1]}
    assert {"plan_ref", "skill_unsupported"} <= codes


# --- the command --------------------------------------------------------------------------------------------
def _make_run(workspace: Path, *, plan: dict | None = None, stage: str = "answers_applied") -> Path:
    run_dir = state.create_run(CV, "file", str(JD_FILE), None, {"page_target": 1}, slug="jr")
    st = state.load(run_dir)
    st["person_slug"] = PERSON
    (run_dir / "cv.txt").write_text(CV.read_text(encoding="utf-8"), encoding="utf-8")
    (run_dir / "jd.txt").write_text(JD_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    for name, art, fname in (("profile", "profile", "profile.json"), ("jd", "jd", "jd.json"),
                             ("match", "match", "match.json"), ("questions", "questions", "questions.json")):
        (run_dir / fname).write_bytes((GOLDEN / fname).read_bytes())
        state.record_artifact(run_dir, st, art, fname, cascade=False)
    state.record_artifact(run_dir, st, "cv_txt", "cv.txt", cascade=False)
    state.record_artifact(run_dir, st, "jd_txt", "jd.txt", cascade=False)
    state.set_stage(st, stage)
    st["checkpoints"] = {"cp1": "done", "cp2": "not_started"}
    state.save(run_dir, st)
    store = {"schema_version": "1", "person_slug": PERSON, "next_seq": 2,
             "attestations": _atts("att-001", run_id=run_dir.name)}
    jsonio.dump_json(store, workspace / "profiles" / PERSON / "attestations.json")
    jsonio.dump_json(plan if plan is not None else _golden("tailor-plan"), run_dir / "tailor-plan.json")
    return run_dir


def _cvt(capsys, *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_assemble_command_writes_tailored_and_advances(workspace, capsys):
    run_dir = _make_run(workspace)
    code, out, err = _cvt(capsys, "--json", "assemble", run_dir.name)
    assert code == 0, (out, err)
    env = json.loads(out)
    assert env["command"] == "assemble" and env["stage"] == "tailored" and "diff" in env["next_action"]
    tailored = json.loads((run_dir / "tailored.json").read_text(encoding="utf-8"))
    expected = _golden("tailored")
    assert {**tailored, "run_id": ""} == {**expected, "run_id": ""}
    assert tailored["run_id"] == run_dir.name
    st = state.load(run_dir)
    names = {a["name"] for a in st["artifacts"]}
    assert {"tailor_plan", "tailored"} <= names and (run_dir / "validation.json").is_file() and st["stage"] == "tailored"
    assert (run_dir / "tailored.history" / "v1.json").is_file()


def test_assemble_twice_does_not_bump_version(workspace, capsys):
    run_dir = _make_run(workspace)
    assert _cvt(capsys, "assemble", run_dir.name)[0] == 0
    assert _cvt(capsys, "--json", "assemble", run_dir.name)[0] == 0
    assert json.loads((run_dir / "tailored.json").read_text(encoding="utf-8"))["version"] == 1


def test_assemble_requires_stage_and_plan(workspace, capsys):
    run_dir = _make_run(workspace, stage="matched")
    code, _out, err = _cvt(capsys, "assemble", run_dir.name)
    assert code == 4 and "E_STAGE" in err
    st = state.load(run_dir)
    st["checkpoints"]["cp1"] = "skipped"
    state.save(run_dir, st)
    assert _cvt(capsys, "assemble", run_dir.name)[0] == 0  # cp1 skipped: matched is enough
    run2 = _make_run(workspace)
    (run2 / "tailor-plan.json").unlink()
    code, _out, err = _cvt(capsys, "assemble", run2.name)
    assert code == 4 and "E_ARTIFACT_MISSING" in err


def test_assemble_failure_is_terse_and_points_to_brief_fix(workspace, capsys):
    plan = _golden("tailor-plan")
    for b in _bullets(plan):
        b.update(op="keep", text="x")
    run_dir = _make_run(workspace, plan=plan)
    code, out, err = _cvt(capsys, "assemble", run_dir.name)
    lines = err.strip().splitlines()
    assert code == 1 and out == "" and len(lines) <= 10
    assert lines[0].startswith("cvt: error[E_CHECK_FAILED]") and lines[-1].endswith(f"cvt.py brief fix {run_dir.name}")
    st = state.load(run_dir)
    assert st["status"] == "failed" and st["history"][-1]["event"] == "assemble"
    assert "brief fix" in st["next_action"] and not (run_dir / "tailored.json").exists()
    validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    assert validation["passed"] is False


def test_assemble_failure_json_envelope(workspace, capsys):
    plan = _golden("tailor-plan")
    _bullets(plan)[1]["text"] = "Replaced manual changes at Contoso Labs with Terraform modules."
    run_dir = _make_run(workspace, plan=plan)
    code, out, _err = _cvt(capsys, "--json", "assemble", run_dir.name)
    env = json.loads(out)
    assert code == 1 and env["ok"] is False and env["data"]["violations"][0]["item_id"] == "t-exp-1.b2"
    assert env["error"]["hint"].endswith(f"brief fix {run_dir.name}")
    st = state.load(run_dir)
    assert st["history"][-1]["event"] == "assemble" and st["status"] == "failed"
    assert (run_dir / "tailored.json").is_file()  # provenance failures keep the version for the fix loop


def test_assemble_schema_invalid_plan(workspace, capsys):
    plan = _golden("tailor-plan")
    del plan["summary"]
    run_dir = _make_run(workspace, plan=plan)
    code, _out, err = _cvt(capsys, "assemble", run_dir.name)
    assert code == 1 and "E_SCHEMA" in err
