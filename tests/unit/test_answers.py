"""WP-15: `cvtlib.answers` (plan, commit, select, auto) and the `cvt answers-apply` command."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from cvtlib import answers, attestations, jsonio, state

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CHECKPOINT = FIXTURES / "checkpoint"
PROFILE = FIXTURES / "profile" / "nested-engagements.json"
PERSON = "sam-testperson"
JD_TEXT = "Platform Reliability Engineer at Example Co. Service mesh, SLOs, SOC 2."
CV_TEXT = "Sam Testperson\nsam@example.invalid\n"
SRE_ITEMS = ["exp-2.e4", "exp-2.e5"]


def load(name: str) -> dict:
    return json.loads((CHECKPOINT / name).read_text(encoding="utf-8"))


def make_run(workspace: Path, *, slug: str = "cp1", asked: bool = True) -> Path:
    """A run with the synthetic profile and jd; with `asked`, `cvt questions` has already put it at awaiting_answers."""
    cv = workspace / "cv.txt"
    cv.write_text(CV_TEXT, encoding="utf-8")
    run_dir = state.create_run(cv, "text", "", JD_TEXT, {}, slug=slug)
    shutil.copy(PROFILE, run_dir / "profile.json")
    shutil.copy(CHECKPOINT / "jd.json", run_dir / "jd.json")
    shutil.copy(CHECKPOINT / "questions.json", run_dir / "questions.json")
    st = state.load(run_dir)
    st["person_slug"] = PERSON
    state.record_artifact(run_dir, st, "profile", "profile.json")
    state.record_artifact(run_dir, st, "jd", "jd.json")
    state.record_artifact(run_dir, st, "questions", "questions.json", cascade=False)
    if asked:
        state.set_stage(st, "awaiting_answers", "awaiting_user",
                        pending={"kind": "questions", "question_ids": ["q-1", "q-2", "q-3"], "message": "3 questions"})
        st["checkpoints"]["cp1"] = "pending"
    else:
        state.set_stage(st, "matched")
    state.save(run_dir, st)
    return run_dir


def cvt_json(run_cvt, *args: str) -> tuple[int, dict]:
    proc = run_cvt("--json", *args)
    return proc.returncode, json.loads(proc.stdout)


def status_of(run_dir: Path, qid: str) -> str:
    rows = jsonio.load_json(run_dir / "questions.json")["questions"]
    return next(q["status"] for q in rows if q["id"] == qid)


def apply_round(run_cvt, run_dir: Path, round_obj: dict, mode: str = "--commit") -> tuple[int, dict]:
    path = run_dir / "answers.round.json"
    path.write_text(json.dumps(round_obj), encoding="utf-8")
    return cvt_json(run_cvt, "answers-apply", run_dir.name, "--round", str(path), mode)


def commit_canonical_with_followups(run_cvt, workspace: Path, run_dir: Path) -> tuple[int, dict]:
    """The full canonical exchange: dry-run, add the scope skeletons, commit."""
    code, env = apply_round(run_cvt, run_dir, load("round-canonical.json"), "--dry-run")
    assert code == 0, env
    follow = workspace / "followups.json"
    follow.write_text(json.dumps(env["data"]["plan"]["skeletons"]), encoding="utf-8")
    code, _ = cvt_json(run_cvt, "questions", run_dir.name, "--add", str(follow))
    assert code == 6
    return apply_round(run_cvt, run_dir, load("round-canonical.json"))


def projection(att: dict) -> dict:
    keys = ("type", "claim", "terms", "placement")
    return {**{k: att[k] for k in keys}, "scope": att["scope"]["kind"]}


# --- plan (dry run) ----------------------------------------------------------------------------------------
def test_canonical_plan(workspace: Path) -> None:
    run_dir = make_run(workspace)
    plan = answers.plan_round(run_dir, load("round-canonical.json"))
    claims = [e["claim"] for e in plan["attestations"]]
    assert claims == ["Service mesh", "Istio", "TypeScript", "SLOs", "Error budgets"]
    skills = plan["attestations"][:3]
    assert [(e["scope_kind"], e["placement"], e["needs_confirmation"]) for e in skills] == [("global", "skills", False)] * 3
    for entry in plan["attestations"][3:]:
        assert entry["scope_kind"] == "role_label" and entry["placement"] == "bullets"
        assert [i["item_id"] for i in entry["items"]] == SRE_ITEMS
        assert entry["items"][0]["label"].startswith("Harborline Bank")
        assert entry["needs_confirmation"] is True and entry["unresolved"] is False
    assert len(plan["skeletons"]) == 2
    skeleton = plan["skeletons"][0]
    assert (skeleton["id"], skeleton["type"], skeleton["topic"], skeleton["parent_id"]) == ("q-4", "scope_confirm", "scope", "q-1")
    assert [c["value"] for c in skeleton["choices"]] == SRE_ITEMS
    assert skeleton["default"]["choice_ids"] == [c["id"] for c in skeleton["choices"]]
    assert skeleton["links"]["attestation_ids"] == ["pending"] and skeleton["status"] == "pending"
    assert plan["unresolved"] == []
    changes = {c["question_id"]: c["to"] for c in plan["question_changes"]}
    assert changes == {"q-1": "answered", "q-2": "defaulted", "q-3": "defaulted"}
    assert not (run_dir / "answers.json").exists()  # a dry run writes nothing
    assert attestations.load_store(PERSON)["attestations"] == []


def test_plan_table_is_terse(workspace: Path) -> None:
    run_dir = make_run(workspace)
    lines = answers.plan_table(answers.plan_round(run_dir, load("round-canonical.json")))
    assert len(lines) <= 15
    assert lines[0].startswith("round 1") and sum(line.startswith("+ ") for line in lines) == 5
    assert any("role_label=SRE -> exp-2.e4" in line and "exp-2.e5" in line for line in lines)


def test_ambiguous_scope_gets_candidates(workspace: Path) -> None:
    run_dir = make_run(workspace)
    plan = answers.plan_round(run_dir, load("round-ambiguous.json"))
    assert plan["unresolved"] == ["Kafka"] and plan["attestations"][0]["unresolved"] is True
    skeleton = plan["skeletons"][0]
    values = [c["value"] for c in skeleton["choices"]]
    assert values[-1] == "skills_only" and {"exp-2.e6", "exp-3.e2"} <= set(values)
    assert skeleton["default"]["choice_ids"] == ["skills_only"]


def test_vague_scope_offers_only_skills_only(workspace: Path) -> None:
    run_dir = make_run(workspace)
    skeleton = answers.plan_round(run_dir, load("round-relevant-roles.json"))["skeletons"][0]
    assert [c["id"] for c in skeleton["choices"]] == ["skills_only"]


def test_role_label_without_a_match_becomes_unresolved(workspace: Path) -> None:
    run_dir = make_run(workspace)
    round_obj = load("round-canonical.json")
    round_obj["items"] = round_obj["items"][3:4]
    round_obj["raw_text"] = "add slo to the sre related cv items"
    round_obj["items"][0]["attestations"][0]["scope"]["role_label"] = "Kubernetes Wrangler"
    plan = answers.plan_round(run_dir, round_obj)
    assert plan["attestations"][0]["scope_kind"] == "unresolved" and "Kubernetes Wrangler" in plan["attestations"][0]["note"]


def test_unknown_items_in_scope_are_rejected(workspace: Path) -> None:
    from cvtlib.errors import CvtError

    run_dir = make_run(workspace)
    round_obj = load("round-canonical.json")
    scope = round_obj["items"][3]["attestations"][0]["scope"]
    scope.update(kind="items", role_label="", item_ids=["exp-9.e9"])
    with pytest.raises(CvtError) as exc:
        answers.plan_round(run_dir, round_obj)
    assert exc.value.err_id == answers.FAILED_ID and exc.value.violations[0]["code"] == "unknown_ref"


@pytest.mark.parametrize(("mutate", "code", "needle"), [
    (lambda r: r["items"][0].update(question_id="q-42"), "unknown_ref", "not in questions.json"),
    (lambda r: r["items"][0]["attestations"][0].update(verbatim="kubernetes"), "fact_mismatch", "verbatim"),
    (lambda r: r["items"][0]["attestations"][0].update(detail="ran it for 7 years"), "unsupported_number", "7"),
    (lambda r: r["items"][0]["attestations"][0].update(terms=[]), "schema", "terms is empty"),
    (lambda r: r["items"][0].update(action="choose"), "schema", "must not carry attestations"),
    (lambda r: r["items"][0]["attestations"][0].update(type="correction"), "placement", "correction"),
    (lambda r: r.update(unmentioned_question_ids=["q-99"]), "unknown_ref", "not a pending question"),
    (lambda r: r["items"][0]["attestations"][0].pop("claim"), "schema", "claim"),
])
def test_invalid_rounds_are_rejected(workspace: Path, mutate, code: str, needle: str) -> None:
    from cvtlib.errors import CvtError

    run_dir = make_run(workspace)
    round_obj = copy.deepcopy(load("round-canonical.json"))
    mutate(round_obj)
    with pytest.raises(CvtError) as exc:
        answers.plan_round(run_dir, round_obj)
    assert any(v["code"] == code and needle in v["message"] for v in exc.value.violations), exc.value.violations


def test_answering_a_settled_question_is_rejected(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    assert apply_round(run_cvt, run_dir, load("round-reject.json"))[0] == 0
    code, env = apply_round(run_cvt, run_dir, load("round-reject.json"))
    assert code == 1 and "only pending questions" in env["data"]["violations"][0]["message"]


def test_correction_must_name_a_profile_item(workspace: Path) -> None:
    from cvtlib.errors import CvtError

    run_dir = make_run(workspace)
    round_obj = load("round-correction.json")
    round_obj["items"][0]["attestations"][0]["correction"]["item_id"] = "exp-9"
    with pytest.raises(CvtError) as exc:
        answers.plan_round(run_dir, round_obj)
    assert "not a profile item" in exc.value.violations[0]["message"]


# --- commit: the canonical exchange ------------------------------------------------------------------------
def test_canonical_exchange_end_to_end(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    code, env = commit_canonical_with_followups(run_cvt, workspace, run_dir)
    assert code == 6 and env["stage"] == "awaiting_answers"
    assert env["data"]["created"] == ["att-001", "att-002", "att-003", "att-004", "att-005"]
    assert env["data"]["pending"] == ["q-4", "q-5"] and env["data"]["unresolved"] == []
    st = state.load(run_dir)
    assert (st["stage"], st["status"], st["checkpoints"]["cp1"]) == ("awaiting_answers", "awaiting_user", "pending")
    assert st["pending"]["kind"] == "followups" and st["pending"]["question_ids"] == ["q-4", "q-5"]
    assert {a["name"] for a in st["artifacts"]} >= {"answers", "questions"}

    store = attestations.load_store(PERSON)["attestations"]
    assert [a["status"] for a in store] == ["proposed"] * 5
    assert [a["run_id"] for a in store] == [run_dir.name] * 5
    assert [projection(a)["claim"] for a in store] == ["Service mesh", "Istio", "TypeScript", "SLOs", "Error budgets"]
    assert [a["scope"]["kind"] for a in store] == ["global"] * 3 + ["role_label"] * 2
    assert store[3]["scope"]["item_ids"] == SRE_ITEMS and store[3]["scope"]["role_label"] == "SRE"
    assert store[3]["terms"] == ["SLO", "SLOs", "service level objective", "service level objectives"]
    assert "Istio" in store[1]["caveat"] or "defend" in store[1]["caveat"]
    assert all(a["question_id"] == "q-1" for a in store)

    rows = {q["id"]: q for q in jsonio.load_json(run_dir / "questions.json")["questions"]}
    assert [rows[i]["status"] for i in ("q-1", "q-2", "q-3", "q-4", "q-5")] == [
        "answered", "defaulted", "defaulted", "pending", "pending"]
    assert rows["q-4"]["links"]["attestation_ids"] == ["att-004"]
    assert rows["q-5"]["links"]["attestation_ids"] == ["att-005"]
    rounds = jsonio.load_json(run_dir / "answers.json")["rounds"]
    assert len(rounds) == 1 and rounds[0]["round"] == 1 and rounds[0]["channel"] == "chat"

    # the user trims the SLO scope to the bank and accepts the default for the other question
    code, env = apply_round(run_cvt, run_dir, load("round-confirm.json"))
    assert code == 0 and env["stage"] == "answers_applied" and env["data"]["scope_updates"] == ["att-004"]
    store = attestations.load_store(PERSON)["attestations"]
    assert store[3]["scope"]["kind"] == "items" and store[3]["scope"]["item_ids"] == ["exp-2.e4"]
    assert store[3]["scope"]["role_label"] == "" and store[3]["scope"]["description"] == "the sre related cv items"
    assert store[4]["scope"]["kind"] == "role_label" and store[4]["scope"]["item_ids"] == SRE_ITEMS
    assert [status_of(run_dir, q) for q in ("q-4", "q-5")] == ["answered", "defaulted"]
    st = state.load(run_dir)
    assert (st["stage"], st["status"], st["checkpoints"]["cp1"], st["pending"]["kind"]) == ("answers_applied", "ok", "done", "none")
    assert [r["round"] for r in jsonio.load_json(run_dir / "answers.json")["rounds"]] == [1, 2]


def test_commit_without_followups_added_still_pends_nothing_but_unresolved(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    code, env = apply_round(run_cvt, run_dir, load("round-canonical.json"))
    assert code == 0 and env["stage"] == "answers_applied"  # scoped and resolved: usable as proposed


def test_ambiguous_commit_waits_for_the_scope_answer(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    code, env = apply_round(run_cvt, run_dir, load("round-ambiguous.json"))
    assert code == 6 and env["data"]["unresolved"] == ["att-001"] and env["data"]["pending"] == []
    st = state.load(run_dir)
    assert st["stage"] == "awaiting_answers" and "scope unresolved" in st["pending"]["message"]
    att = attestations.load_store(PERSON)["attestations"][0]
    assert att["scope"]["kind"] == "unresolved" and att["scope"]["item_ids"] == []
    assert attestations.usable(attestations.load_store(PERSON), run_id=run_dir.name, include_proposed=True) == []


def test_ambiguous_scope_is_resolved_by_the_followup_answer(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    _, plan = apply_round(run_cvt, run_dir, load("round-ambiguous.json"), "--dry-run")
    follow = workspace / "followups.json"
    follow.write_text(json.dumps(plan["data"]["plan"]["skeletons"]), encoding="utf-8")
    assert cvt_json(run_cvt, "questions", run_dir.name, "--add", str(follow))[0] == 6
    code, env = apply_round(run_cvt, run_dir, load("round-ambiguous.json"))
    assert code == 6 and env["data"]["pending"] == ["q-4"] and env["data"]["unresolved"] == ["att-001"]
    assert jsonio.load_json(run_dir / "questions.json")["questions"][3]["links"]["attestation_ids"] == ["att-001"]
    confirm = {**load("round-confirm.json"), "raw_text": "the backend developer one",
               "items": [{**load("round-confirm.json")["items"][0], "choice_ids": ["exp_2_e6"]}], "unmentioned_question_ids": []}
    code, env = apply_round(run_cvt, run_dir, confirm)
    assert code == 0 and env["stage"] == "answers_applied"
    att = attestations.load_store(PERSON)["attestations"][0]
    assert att["scope"]["kind"] == "items" and att["scope"]["item_ids"] == ["exp-2.e6"] and att["placement"] == "skills_and_bullets"


def test_skills_only_answer_makes_the_claim_global(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    _, plan = apply_round(run_cvt, run_dir, load("round-ambiguous.json"), "--dry-run")
    follow = workspace / "followups.json"
    follow.write_text(json.dumps(plan["data"]["plan"]["skeletons"]), encoding="utf-8")
    cvt_json(run_cvt, "questions", run_dir.name, "--add", str(follow))
    apply_round(run_cvt, run_dir, load("round-ambiguous.json"))
    confirm = {**load("round-confirm.json"), "items": [{**load("round-confirm.json")["items"][0], "choice_ids": ["skills_only"]}],
               "unmentioned_question_ids": []}
    code, _ = apply_round(run_cvt, run_dir, confirm)
    att = attestations.load_store(PERSON)["attestations"][0]
    assert code == 0 and att["scope"]["kind"] == "global" and att["placement"] == "skills"


def test_confirm_scope_with_unlinked_question_is_rejected(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    code, env = apply_round(run_cvt, run_dir, load("round-confirm.json"), "--dry-run")
    assert code == 1 and any(v["code"] == "unknown_ref" for v in env["data"]["violations"])


# --- other rounds ------------------------------------------------------------------------------------------
def test_rejection_round_creates_nothing(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    code, env = apply_round(run_cvt, run_dir, load("round-reject.json"))
    assert code == 0 and env["data"]["created"] == [] and env["stage"] == "answers_applied"
    assert attestations.load_store(PERSON)["attestations"] == []
    assert [status_of(run_dir, q) for q in ("q-1", "q-2", "q-3")] == ["answered", "defaulted", "defaulted"]


def test_correction_round_creates_a_correction_attestation(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    code, env = apply_round(run_cvt, run_dir, load("round-correction.json"))
    assert code == 0 and env["data"]["created"] == ["att-001"]
    att = attestations.load_store(PERSON)["attestations"][0]
    assert (att["type"], att["placement"], att["status"], att["question_id"]) == ("correction", "correction_only", "proposed", "")
    assert att["correction"] == {"item_id": "exp-1", "field": "start_date", "old_value": "2023-01", "new_value": "2022-06"}
    assert [status_of(run_dir, q) for q in ("q-1", "q-2", "q-3")] == ["defaulted"] * 3


def test_skip_and_unmentioned_statuses(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    code, _ = apply_round(run_cvt, run_dir, load("round-skip.json"))
    assert code == 0
    assert [status_of(run_dir, q) for q in ("q-1", "q-2", "q-3")] == ["skipped", "defaulted", "defaulted"]
    assert attestations.load_store(PERSON)["attestations"] == []


def test_instructions_are_kept_for_tailoring(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    round_obj = load("round-skip.json")
    round_obj["items"].append({"question_id": "", "action": "instruct", "choice_ids": [], "attestations": [],
                               "instruction": "lead with the platform work", "note": ""})
    code, env = apply_round(run_cvt, run_dir, round_obj)
    assert code == 0 and env["data"]["instructions"] == [{"question_id": "", "instruction": "lead with the platform work"}]
    assert jsonio.load_json(run_dir / "answers.json")["rounds"][0]["items"][-1]["instruction"] == "lead with the platform work"


def test_partial_round_leaves_the_rest_pending(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    round_obj = load("round-skip.json")
    round_obj["unmentioned_question_ids"] = ["q-2"]
    code, env = apply_round(run_cvt, run_dir, round_obj)
    assert code == 6 and env["data"]["pending"] == ["q-3"] and env["stage"] == "awaiting_answers"
    assert state.load(run_dir)["pending"]["kind"] == "questions"


def test_second_run_suppresses_a_gap_answered_by_an_active_attestation(workspace: Path, run_cvt) -> None:
    first = make_run(workspace, slug="first")
    assert apply_round(run_cvt, first, load("round-canonical.json"))[0] == 0
    store = attestations.load_store(PERSON)
    for att_id in ("att-001", "att-002", "att-003"):
        attestations.set_status(store, att_id, "active")  # what `cvt approve` does at checkpoint 2
    attestations.save_store(PERSON, store)
    second = make_run(workspace, slug="second", asked=False)
    code, env = cvt_json(run_cvt, "questions", second.name)
    assert code == 6
    suppressed = {s["choice_id"]: s["reason"] for s in env["data"]["suppressed"]}
    assert suppressed["service_mesh"] == "answered by att-001 (Service mesh)"
    assert set(suppressed) == {"service_mesh", "istio", "typescript"}
    left = [c["id"] for c in jsonio.load_json(second / "questions.json")["questions"][0]["choices"]]
    assert left == ["slo", "soc2", "startup"]


# --- --select, --auto and command rules --------------------------------------------------------------------
def test_select_round_matches_the_golden_round_for_choice_parts(workspace: Path, run_cvt) -> None:
    golden_dir = make_run(workspace, slug="golden")
    apply_round(run_cvt, golden_dir, load("round-canonical.json"))
    golden = [projection(a) for a in attestations.load_store(PERSON)["attestations"][:3]]
    shutil.rmtree(workspace / "profiles")
    run_dir = make_run(workspace, slug="selected")
    code, env = cvt_json(run_cvt, "answers-apply", run_dir.name, "--select", "q-1=service_mesh,istio,typescript",
                         "--default-rest", "--commit")
    assert code == 0 and env["data"]["created"] == ["att-001", "att-002", "att-003"]
    store = attestations.load_store(PERSON)["attestations"]
    assert [projection(a) for a in store] == golden
    assert all(a["scope"] == {"kind": "global", "role_label": "", "item_ids": [], "description": ""} for a in store)
    assert all(a["status"] == "proposed" and a["caveat"] for a in store)
    assert [status_of(run_dir, q) for q in ("q-1", "q-2", "q-3")] == ["answered", "defaulted", "defaulted"]
    rnd = jsonio.load_json(run_dir / "answers.json")["rounds"][0]
    assert rnd["channel"] == "host_tool" and rnd["raw_text"] == "q-1: Service mesh, Istio, TypeScript"
    assert rnd["unmentioned_question_ids"] == ["q-2", "q-3"]


def test_select_terms_split_the_value_on_pipes(workspace: Path) -> None:
    questions = load("questions.json")
    rnd = answers.select_round(questions, {"q-1": ["slo"]}, default_rest=False, now="2026-01-01T00:00:00Z")
    prop = rnd["items"][0]["attestations"][0]
    assert prop["terms"] == ["slo", "slos", "error budget", "error budgets"]
    assert (prop["type"], prop["placement"], prop["detail"], prop["verbatim"]) == ("skill", "skills", prop["claim"], prop["claim"])
    assert rnd["unmentioned_question_ids"] == []


def test_select_without_default_rest_leaves_others_pending(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    code, env = cvt_json(run_cvt, "answers-apply", run_dir.name, "--select", "q-1=istio", "--select", "q-3=classic",
                         "--commit")
    assert code == 6 and env["data"]["pending"] == ["q-2"]
    assert [status_of(run_dir, q) for q in ("q-1", "q-2", "q-3")] == ["answered", "pending", "answered"]
    rnd = jsonio.load_json(run_dir / "answers.json")["rounds"][0]
    assert rnd["items"][1] == {"question_id": "q-3", "action": "choose", "choice_ids": ["classic"], "attestations": [],
                               "instruction": "", "note": ""}


def test_select_skip_and_labels(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    code, env = cvt_json(run_cvt, "answers-apply", run_dir.name, "--select", "q-1=skip", "--select", "q-3=Classic",
                         "--default-rest", "--dry-run")
    assert code == 0
    changes = {c["question_id"]: c["to"] for c in env["data"]["plan"]["question_changes"]}
    assert changes == {"q-1": "skipped", "q-3": "answered", "q-2": "defaulted"}


@pytest.mark.parametrize("select", ["q-9=istio", "q-1=nonsense", "q-1", "x=1", "q-3=modern,classic", "q-2=anything"])
def test_select_usage_errors_exit_2(workspace: Path, run_cvt, select: str) -> None:
    run_dir = make_run(workspace)
    code, env = cvt_json(run_cvt, "answers-apply", run_dir.name, "--select", select, "--dry-run")
    assert code == 2 and env["error"]["id"] in {"E_SELECT", "E_USAGE"}


def test_select_scope_question_confirms_scope(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    commit_canonical_with_followups(run_cvt, workspace, run_dir)
    code, env = cvt_json(run_cvt, "answers-apply", run_dir.name, "--select", "q-4=exp_2_e5", "--default-rest", "--commit")
    assert code == 0 and env["data"]["scope_updates"] == ["att-004"]
    assert attestations.load_store(PERSON)["attestations"][3]["scope"]["item_ids"] == ["exp-2.e5"]


def test_dry_run_output_is_capped(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    path = run_dir / "answers.round.json"
    path.write_text(json.dumps(load("round-canonical.json")), encoding="utf-8")
    proc = run_cvt("answers-apply", run_dir.name, "--round", str(path), "--dry-run")
    assert proc.returncode == 0 and len(proc.stdout.splitlines()) <= 15
    assert "role_label=SRE" in proc.stdout


def test_auto_flag_defaults_everything(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    code, env = cvt_json(run_cvt, "answers-apply", run_dir.name, "--auto")
    assert code == 0 and env["stage"] == "answers_applied" and env["data"]["created"] == []
    assert jsonio.load_json(run_dir / "answers.json")["rounds"][0]["channel"] == "auto"
    assert {status_of(run_dir, q) for q in ("q-1", "q-2", "q-3")} == {"defaulted"}


def test_command_argument_and_stage_rules(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    path = run_dir / "answers.round.json"
    path.write_text(json.dumps(load("round-skip.json")), encoding="utf-8")
    assert cvt_json(run_cvt, "answers-apply", run_dir.name)[0] == 2
    assert cvt_json(run_cvt, "answers-apply", run_dir.name, "--round", str(path))[0] == 2
    assert cvt_json(run_cvt, "answers-apply", run_dir.name, "--round", str(path), "--select", "q-1=skip", "--dry-run")[0] == 2
    assert cvt_json(run_cvt, "answers-apply", run_dir.name, "--round", str(path), "--dry-run", "--commit")[0] == 2
    assert cvt_json(run_cvt, "answers-apply", run_dir.name, "--round", str(path), "--default-rest", "--dry-run")[0] == 2
    early = make_run(workspace, slug="early", asked=False)
    code, env = apply_round(run_cvt, early, load("round-skip.json"))
    assert code == 4 and env["error"]["id"] == "E_STAGE"


def test_invalid_commit_marks_the_run_failed_without_writing(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    round_obj = load("round-canonical.json")
    round_obj["items"][0]["attestations"][0]["verbatim"] = "kubernetes"
    code, env = apply_round(run_cvt, run_dir, round_obj)
    assert code == 1 and env["error"]["id"] == "E_ANSWERS_INVALID" and env["data"]["violations"]
    assert not (run_dir / "answers.json").exists()
    assert attestations.load_store(PERSON)["attestations"] == []
    assert state.load(run_dir)["status"] == "failed"
    assert status_of(run_dir, "q-1") == "pending"


# --- WP-FIX-3-3: licensed terms must come from the user's words ----------------------------------------------
HELM_RAW = "I used Helm at Brightfield to package two internal services"


def term_round(raw_text: str, claim: str, terms: list[str], detail: str = "") -> dict:
    round_obj = copy.deepcopy(load("round-canonical.json"))
    round_obj["raw_text"] = raw_text
    round_obj["items"] = round_obj["items"][:1]
    prop = round_obj["items"][0]["attestations"][0]
    prop.update(claim=claim, terms=terms, detail=detail, verbatim=raw_text)
    round_obj["unmentioned_question_ids"] = ["q-2", "q-3"]
    return round_obj


def term_violations(workspace: Path, round_obj: dict) -> list[dict]:
    from cvtlib.errors import CvtError

    run_dir = make_run(workspace)
    with pytest.raises(CvtError) as exc:
        answers.plan_round(run_dir, round_obj)
    return exc.value.violations


@pytest.mark.parametrize(("raw", "claim", "terms", "named"), [
    (HELM_RAW, "Kubernetes", ["Kubernetes"], ["Kubernetes"]),
    (HELM_RAW, "Helm", ["Helm", "Kubernetes", "ArgoCD"], ["Kubernetes", "ArgoCD"]),
    ("add Linux to the relevant roles", "Bash", ["Bash"], ["Bash"]),
])
def test_ungrounded_terms_are_rejected(workspace: Path, raw: str, claim: str, terms: list[str], named: list[str]) -> None:
    violations = term_violations(workspace, term_round(raw, claim, terms))
    messages = [v["message"] for v in violations if v["code"] == "unsupported_term"]
    for term in named:
        assert any(f"'{term}'" in m and "items[0].attestations[0]" in m for m in messages), violations


def test_ungrounded_term_in_claim_or_detail_is_rejected(workspace: Path) -> None:
    violations = term_violations(workspace, term_round(HELM_RAW, "Helm", ["Helm"], detail="Helm with Terraform"))
    assert any(v["code"] == "unsupported_term" and "'Terraform'" in v["message"] for v in violations)


def test_grounded_terms_pass(workspace: Path) -> None:
    run_dir = make_run(workspace)
    plan = answers.plan_round(run_dir, term_round(HELM_RAW, "Helm", ["Helm"], detail="Helm to package two services"))
    assert [e["claim"] for e in plan["attestations"]] == ["Helm"]


def test_slo_round_with_synonym_terms_passes(workspace: Path) -> None:
    raw = "add slo and error budget to the sre related cv items"
    round_obj = term_round(raw, "SLOs", ["SLO", "SLOs", "service level objective"])
    round_obj["items"][0]["attestations"][0]["verbatim"] = "slo and error budget"
    assert answers.plan_round(make_run(workspace), round_obj)["attestations"][0]["terms"] == [
        "SLO", "SLOs", "service level objective"]


def test_chosen_option_text_grounds_terms(workspace: Path) -> None:
    round_obj = term_round("yes, that one", "Istio", ["Istio"])
    round_obj["items"][0]["attestations"][0]["verbatim"] = "that one"
    assert any(v["code"] == "unsupported_term" for v in term_violations(workspace, round_obj))
    round_obj["items"][0]["choice_ids"] = ["istio"]
    assert answers.plan_round(make_run(workspace, slug="chosen"), round_obj)["attestations"][0]["claim"] == "Istio"


def test_grounded_correction_round_passes(workspace: Path) -> None:
    plan = answers.plan_round(make_run(workspace), load("round-correction.json"))
    assert plan["attestations"][0]["type"] == "correction"


# --- WP-FIX-3-7: corrections are grounded in the user's words and shown in the dry run -----------------------
QUILLMARK_RAW = "I started at Quillmark in 2022-06, the CV is wrong"


def correction_round(raw_text: str, item_id: str, field: str, old: str, new: str, terms: list[str] | None = None) -> dict:
    round_obj = copy.deepcopy(load("round-correction.json"))
    round_obj["raw_text"] = raw_text
    prop = round_obj["items"][0]["attestations"][0]
    prop["correction"] = {"item_id": item_id, "field": field, "old_value": old, "new_value": new}
    prop["claim"], prop["verbatim"] = "fix a bullet", raw_text
    prop["terms"] = terms or []
    return round_obj


def test_ungrounded_correction_values_are_rejected(workspace: Path) -> None:
    text = correction_round(QUILLMARK_RAW, "sum-1", "text", "Synthetic platform engineer used only for tests.",
                            "Led the Kubernetes migration for Walmart across ArgoCD and Istio")
    violations = term_violations(workspace, text)
    messages = [v["message"] for v in violations if v["code"] == "unsupported_term"]
    for term in ("Kubernetes", "Walmart"):
        assert any(f"'{term}'" in m and "items[0].attestations[0].correction.new_value" in m for m in messages), violations
    position = correction_round(QUILLMARK_RAW, "exp-1", "position", "Platform Engineer", "Principal Kubernetes Architect")
    violations = term_violations(workspace, position)
    assert any(v["code"] == "unsupported_term" and "'Kubernetes'" in v["message"] for v in violations), violations


def test_correction_with_terms_is_a_schema_violation(workspace: Path) -> None:
    round_obj = correction_round(QUILLMARK_RAW, "exp-1", "start_date", "2023-01", "2022-06", terms=["Kubernetes"])
    violations = term_violations(workspace, round_obj)
    assert [v["code"] for v in violations] == ["schema"]
    assert "a correction carries no terms" in violations[0]["message"]


def test_correction_value_grounded_in_raw_text_passes(workspace: Path) -> None:
    raw = "my title at Quillmark was Principal Kubernetes Architect"
    round_obj = correction_round(raw, "exp-1", "position", "Platform Engineer", "Principal Kubernetes Architect")
    plan = answers.plan_round(make_run(workspace), round_obj)
    assert plan["attestations"][0]["correction"]["new_value"] == "Principal Kubernetes Architect"


def test_correction_dry_run_line_shows_the_change(workspace: Path) -> None:
    lines = answers.plan_table(answers.plan_round(make_run(workspace), load("round-correction.json")))
    plus = next(line for line in lines if line.startswith("+ correction"))
    assert plus.endswith(" exp-1.start_date: 2023-01 -> 2022-06") and len(lines) <= 15
    long_value = "my title was " + "Principal " * 12
    round_obj = correction_round(long_value, "exp-1", "position", "Platform Engineer", long_value)
    shown = next(line for line in answers.plan_table(answers.plan_round(make_run(workspace, slug="long"), round_obj))
                 if line.startswith("+ correction"))
    assert shown.endswith("…")


def test_dry_run_line_shows_multi_term_attestations(workspace: Path) -> None:
    raw = "add slo and error budget to the sre related cv items"
    round_obj = term_round(raw, "SLOs", ["SLO", "SLOs", "service level objective"])
    round_obj["items"][0]["attestations"][0]["verbatim"] = "slo and error budget"
    lines = answers.plan_table(answers.plan_round(make_run(workspace), round_obj))
    plus = next(line for line in lines if line.startswith("+ "))
    assert plus.endswith(" terms=SLO, SLOs, service level objective") and len(lines) <= 15
    single = answers.plan_table(answers.plan_round(make_run(workspace, slug="single"), load("round-canonical.json")))
    single_term = [line for line in single if line.startswith("+ skill")]
    assert single_term and not any("terms=" in line for line in single_term)


# --- WP-FIX-3-10: a correction uses only the user's words and names the real old value ----------------------
SUM1_TEXT = "Synthetic platform engineer used only for tests."


@pytest.mark.parametrize(("field", "item_id", "old", "new", "first_word", "later_word"), [
    ("position", "exp-1", "Platform Engineer", "Principal Architect", "Principal", "Architect"),
    ("position", "exp-1", "Platform Engineer", "Head of Engineering", "Head", "Engineering"),
    ("text", "sum-1", SUM1_TEXT, "Led the company-wide platform migration and managed the team", "Led", "managed"),
    ("text", "sum-1", SUM1_TEXT, "led the cloud migration for walmart", "led", "walmart"),
])
def test_correction_words_must_all_be_the_users(workspace: Path, field: str, item_id: str, old: str, new: str,
                                                first_word: str, later_word: str) -> None:
    violations = term_violations(workspace, correction_round(QUILLMARK_RAW, item_id, field, old, new))
    assert all(v["code"] == "unsupported_term" for v in violations), violations
    assert f"'{first_word}'" in violations[0]["message"], violations
    assert any(f"'{later_word}'" in v["message"] for v in violations), violations


@pytest.mark.parametrize("old", ["", "1999-01"])
def test_correction_old_value_must_match_the_profile(workspace: Path, old: str) -> None:
    violations = term_violations(workspace, correction_round(QUILLMARK_RAW, "exp-1", "start_date", old, "2022-06"))
    assert [v["code"] for v in violations] == ["fact_mismatch"]
    assert "does not match the profile's exp-1.start_date '2023-01'" in violations[0]["message"]


def test_correction_with_the_real_old_value_passes(workspace: Path) -> None:
    round_obj = correction_round(QUILLMARK_RAW, "exp-1", "start_date", "2023-01", "2022-06")
    assert answers.plan_round(make_run(workspace), round_obj)["attestations"][0]["correction"]["old_value"] == "2023-01"


@pytest.mark.parametrize(("raw", "item_id", "field", "old", "new"), [
    ("my title at Quillmark was Principal Architect", "exp-1", "position", "Platform Engineer", "Principal Architect"),
    ("the summary should say I led the platform migration", "sum-1", "text", SUM1_TEXT, "Led the platform migration"),
])
def test_correction_in_the_users_words_passes(workspace: Path, raw: str, item_id: str, field: str, old: str,
                                              new: str) -> None:
    plan = answers.plan_round(make_run(workspace), correction_round(raw, item_id, field, old, new))
    assert plan["attestations"][0]["correction"]["new_value"] == new


def test_dry_run_shows_the_profile_value_not_the_given_one(workspace: Path) -> None:
    round_obj = correction_round("my title at Quillmark was Principal Architect", "exp-1", "position",
                                 "platform  engineer", "Principal Architect")
    plus = next(line for line in answers.plan_table(answers.plan_round(make_run(workspace), round_obj))
                if line.startswith("+ correction"))
    assert plus.endswith(" exp-1.position: Platform Engineer -> Principal Architect")
