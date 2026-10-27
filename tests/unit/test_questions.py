"""WP-15: `cvtlib.questions` (check, suppression, add, rendering) and the `cvt questions` command."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from cvtlib import attestations, jsonio, questions as qmod, state

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CHECKPOINT = FIXTURES / "checkpoint"
PROFILE = FIXTURES / "profile" / "nested-engagements.json"
PERSON = "sam-testperson"
JD_TEXT = "Platform Reliability Engineer at Example Co. Service mesh, SLOs, SOC 2."
CV_TEXT = "Sam Testperson\nsam@example.invalid\n"


def load(name: str) -> dict:
    return json.loads((CHECKPOINT / name).read_text(encoding="utf-8"))


def make_run(workspace: Path, *, auto: bool = False, slug: str = "cp1") -> Path:
    """A run at stage `matched` with the synthetic profile, jd.json and first-batch questions.json."""
    cv = workspace / "cv.txt"
    cv.write_text(CV_TEXT, encoding="utf-8")
    run_dir = state.create_run(cv, "text", "", JD_TEXT, {"auto": auto}, slug=slug)
    shutil.copy(PROFILE, run_dir / "profile.json")
    shutil.copy(CHECKPOINT / "jd.json", run_dir / "jd.json")
    shutil.copy(CHECKPOINT / "questions.json", run_dir / "questions.json")
    st = state.load(run_dir)
    st["person_slug"] = PERSON
    state.record_artifact(run_dir, st, "profile", "profile.json")
    state.record_artifact(run_dir, st, "jd", "jd.json")
    state.set_stage(st, "matched")
    state.save(run_dir, st)
    return run_dir


def add_attestation(claim: str, terms: list[str], *, status: str = "active") -> dict:
    store = attestations.load_store(PERSON)
    proposal = {
        "type": "skill", "claim": claim, "terms": terms, "detail": "",
        "scope": {"kind": "global", "role_label": "", "item_ids": [], "description": ""},
        "placement": "skills", "correction": {"item_id": "", "field": "", "old_value": "", "new_value": ""},
        "verbatim": claim, "caveat": "",
    }
    att = attestations.add(store, proposal, run_id="earlier-run", question_id="q-1")
    if status == "active":
        attestations.set_status(store, att["id"], "active")
    attestations.save_store(PERSON, store)
    return att


def cvt_json(run_cvt, *args: str) -> tuple[int, dict]:
    proc = run_cvt("--json", *args)
    return proc.returncode, json.loads(proc.stdout)


def test_check_accepts_first_batch() -> None:
    checked, violations = qmod.check(load("questions.json"), [], jd=load("jd.json"))
    assert violations == []
    assert all(q["status"] == "pending" for q in checked["questions"])


def test_check_rule_violations() -> None:
    base = load("questions.json")
    cases = {
        "allow_free_text": lambda q: q["questions"][0].update(allow_free_text=False),
        "default.description": lambda q: q["questions"][0]["default"].update(description="  "),
        "duplicate question id": lambda q: q["questions"][1].update(id="q-1"),
        "has no choices": lambda q: q["questions"][2].update(choices=[], default={**q["questions"][2]["default"], "choice_ids": []}),
        "links.req_ids unknown": lambda q: q["questions"][0]["links"].update(req_ids=["req-99"]),
        "default.choice_ids not in choices": lambda q: q["questions"][0]["default"].update(choice_ids=["nope"]),
        "parent_id": lambda q: q["questions"][1].update(parent_id="q-77"),
    }
    for needle, mutate in cases.items():
        broken = copy.deepcopy(base)
        mutate(broken)
        _, violations = qmod.check(broken, [], jd=load("jd.json"))
        assert any(needle in v["message"] for v in violations), (needle, violations)


def test_check_limit_of_pending_checkpoint_questions() -> None:
    rows = load("questions.json")
    template = rows["questions"][1]
    rows["questions"] = [{**copy.deepcopy(template), "id": f"q-{n}"} for n in range(1, qmod.MAX_CP1_QUESTIONS + 2)]
    _, violations = qmod.check(rows, [])
    assert any("pending checkpoint-1 questions" in v["message"] for v in violations)
    rows["questions"].pop()
    assert qmod.check(rows, [])[1] == []


def _cp1_question(n: int, round_no: int, parent_id: str = "") -> dict:
    template = load("questions.json")["questions"][1]
    return {**copy.deepcopy(template), "id": f"q-{n}", "round": round_no, "parent_id": parent_id}


def _cap_violations(violations: list[dict]) -> list[dict]:
    return [v for v in violations if "pending checkpoint-1 questions" in v["message"]]


def test_check_caps_initial_batch_across_rounds() -> None:
    # labelling initial questions as round 2 must not dodge the cap
    rows = load("questions.json")
    rows["questions"] = [_cp1_question(n, 1) for n in range(1, 9)] + [_cp1_question(n, 2) for n in range(9, 15)]
    capped = _cap_violations(qmod.check(rows, [])[1])
    assert len(capped) == 1, capped
    assert "initial batch" in capped[0]["message"] and "14 pending" in capped[0]["message"]
    assert "the limit is 8" in capped[0]["message"]


def test_check_allows_follow_up_beside_full_initial_batch() -> None:
    # the WP-I4 case: 8 pending round-1 questions plus a follow-up added in round 2
    rows = load("questions.json")
    rows["questions"] = [_cp1_question(n, 1) for n in range(1, 9)] + [_cp1_question(9, 2, parent_id="q-1")]
    assert _cap_violations(qmod.check(rows, [])[1]) == []


def test_check_caps_follow_ups_per_round() -> None:
    rows = load("questions.json")
    rows["questions"] = [_cp1_question(1, 1)] + [_cp1_question(n, 2, parent_id="q-1") for n in range(2, 11)]
    capped = _cap_violations(qmod.check(rows, [])[1])
    assert len(capped) == 1, capped
    assert "round 2 follow-ups" in capped[0]["message"] and "9 pending" in capped[0]["message"]


def test_check_schema_and_profile_links() -> None:
    bad = load("questions.json")
    del bad["questions"][0]["prompt"]
    assert qmod.check(bad, [])[1][0]["code"] == "schema"
    rows = load("questions.json")
    rows["questions"][0]["links"]["item_ids"] = ["exp-9.e9"]
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    _, violations = qmod.check(rows, [], profile=profile)
    assert violations and violations[0]["code"] == "unknown_ref"
    rows["questions"][0]["links"]["item_ids"] = ["exp-2.e4"]
    assert qmod.check(rows, [], profile=profile)[1] == []


def test_pending_placeholder_attestation_link_is_allowed() -> None:
    rows = load("questions.json")
    rows["questions"][0]["links"]["attestation_ids"] = ["pending"]
    assert qmod.check(rows, [])[1] == []


def test_suppression_removes_covered_choice(workspace: Path) -> None:
    att = add_attestation("Service mesh", ["service mesh"])
    store = attestations.load_store(PERSON)
    checked, suppressed = qmod.suppress(load("questions.json"), store["attestations"])
    gap = checked["questions"][0]
    assert "service_mesh" not in [c["id"] for c in gap["choices"]]
    assert gap["status"] == "pending"
    assert suppressed == [{
        "question_id": "q-1", "choice_id": "service_mesh", "question_suppressed": False,
        "reason": f"answered by {att['id']} (Service mesh)",
    }]


GAP_LABELS = ["LLM serving (vLLM or similar)", "GPU scheduling on Kubernetes", "RAG pipelines", "Service mesh",
              "Agent frameworks such as LangGraph"]
LISTED_PROMPT = ("Your CV doesn't currently show: LLM serving (vLLM or similar); GPU scheduling on Kubernetes; "
                 "RAG pipelines; service mesh; agent frameworks such as LangGraph (multi-agent work shown). "
                 "Which of these do you actually have experience with?")


def _listed_gap_questions(prompt: str) -> dict:
    rows = load("questions.json")
    gap = rows["questions"][0]
    gap["prompt"] = prompt
    gap["choices"] = [{"id": f"c{i}", "label": label, "value": label.lower()} for i, label in enumerate(GAP_LABELS)]
    gap["default"]["choice_ids"] = []
    rows["questions"] = [gap]
    return rows


def test_suppression_removes_dropped_label_from_prompt(workspace: Path) -> None:
    add_attestation("Service mesh", ["service mesh"])
    store = attestations.load_store(PERSON)
    checked, _ = qmod.suppress(_listed_gap_questions(LISTED_PROMPT), store["attestations"])
    prompt = checked["questions"][0]["prompt"]
    assert "service mesh" not in prompt.lower()
    for label in ("LLM serving", "GPU scheduling on Kubernetes", "RAG pipelines", "agent frameworks such as LangGraph"):
        assert label in prompt
    assert "; ;" not in prompt and "  " not in prompt and prompt.endswith("Which of these do you actually have experience with?")


def test_suppression_rewrites_prompt_when_term_cannot_be_removed(workspace: Path) -> None:
    add_attestation("Service mesh", ["service mesh"])
    store = attestations.load_store(PERSON)
    prompt = "Does your Service-Mesh work (the service mesh kind) count? Pick any."
    checked, _ = qmod.suppress(_listed_gap_questions(prompt), store["attestations"])
    kept = [label for label in GAP_LABELS if label != "Service mesh"]
    assert checked["questions"][0]["prompt"] == qmod.GAP_PROMPT_REWRITE.format(labels="; ".join(kept))


def test_suppression_prompt_rewrite_is_idempotent_and_noop_without_drops(workspace: Path) -> None:
    add_attestation("Service mesh", ["service mesh"])
    store = attestations.load_store(PERSON)
    once, _ = qmod.suppress(_listed_gap_questions(LISTED_PROMPT), store["attestations"])
    twice, again = qmod.suppress(once, store["attestations"])
    assert twice == once and again == []
    untouched, none = qmod.suppress(_listed_gap_questions(LISTED_PROMPT), [])
    assert none == [] and untouched["questions"][0]["prompt"] == LISTED_PROMPT


def test_question_without_choices_is_suppressed_with_reason(workspace: Path) -> None:
    rows = load("questions.json")
    rows["questions"][0]["choices"] = rows["questions"][0]["choices"][:2]
    add_attestation("Service mesh", ["service mesh"])
    add_attestation("Istio", ["Istio"])
    store = attestations.load_store(PERSON)
    checked, violations = qmod.check(rows, store["attestations"])
    assert violations == []
    gap = checked["questions"][0]
    assert gap["status"] == "suppressed"
    assert "att-001 (Service mesh)" in gap["suppressed_reason"] and "att-002 (Istio)" in gap["suppressed_reason"]


def test_suppression_ignores_proposed_attestations(workspace: Path) -> None:
    add_attestation("Service mesh", ["service mesh"], status="proposed")
    store = attestations.load_store(PERSON)
    checked, suppressed = qmod.suppress(load("questions.json"), store["attestations"])
    assert suppressed == []
    assert len(checked["questions"][0]["choices"]) == 6


def test_suppression_of_synonym_value_needs_any_part_covered(workspace: Path) -> None:
    # "slo|slos|error budget|error budgets": one active attestation covering "SLO" suppresses the choice
    add_attestation("SLOs", ["SLO", "SLOs"])
    store = attestations.load_store(PERSON)
    checked, suppressed = qmod.suppress(load("questions.json"), store["attestations"])
    assert [(s["choice_id"], s["question_suppressed"]) for s in suppressed] == [("slo", False)]
    assert "slo" not in [c["id"] for c in checked["questions"][0]["choices"]]
    assert len(checked["questions"][0]["choices"]) == 5


def test_golden_helm_choice_is_suppressed_by_active_attestation(workspace: Path) -> None:
    golden = json.loads((FIXTURES / "golden" / "junior" / "questions.json").read_text(encoding="utf-8"))
    add_attestation("Helm", ["Helm"])
    store = attestations.load_store(PERSON)
    checked, suppressed = qmod.suppress(golden, store["attestations"])
    assert suppressed == [{
        "question_id": "q-1", "choice_id": "helm", "question_suppressed": False,
        "reason": "answered by att-001 (Helm)",
    }]
    assert [c["id"] for c in checked["questions"][0]["choices"]] == ["python_bash"]
    assert checked["questions"][0]["status"] == "pending"


def test_golden_helm_choice_not_suppressed_by_proposed_attestation(workspace: Path) -> None:
    golden = json.loads((FIXTURES / "golden" / "junior" / "questions.json").read_text(encoding="utf-8"))
    add_attestation("Helm", ["Helm"], status="proposed")
    store = attestations.load_store(PERSON)
    checked, suppressed = qmod.suppress(golden, store["attestations"])
    assert suppressed == []
    assert len(checked["questions"][0]["choices"]) == 2


def test_requirement_choice_needs_every_keyword_covered(workspace: Path) -> None:
    rows = load("questions.json")
    gap = rows["questions"][0]
    gap["choices"] = [{"id": "reliability", "label": "SLO work", "value": "req-2"}]
    add_attestation("SLOs", ["SLO"])  # req-2 has keywords "SLO" and "error budget"; only one is covered
    store = attestations.load_store(PERSON)
    checked, suppressed = qmod.suppress(rows, store["attestations"], jd=load("jd.json"))
    assert suppressed == []
    assert [c["id"] for c in checked["questions"][0]["choices"]] == ["reliability"]


def test_suppression_uses_requirement_keywords_for_req_valued_choices(workspace: Path) -> None:
    rows = load("questions.json")
    gap = rows["questions"][0]
    gap["choices"] = [{"id": "reliability", "label": "SLO work", "value": "req-2"}, *gap["choices"][:1]]
    add_attestation("SLOs and error budgets", ["SLO", "error budget"])
    store = attestations.load_store(PERSON)
    checked, suppressed = qmod.suppress(rows, store["attestations"], jd=load("jd.json"))
    assert [s["choice_id"] for s in suppressed] == ["reliability"]
    assert [c["id"] for c in checked["questions"][0]["choices"]] == ["service_mesh"]


def test_add_numbers_after_max_and_sets_round() -> None:
    base = load("questions.json")
    follow = copy.deepcopy(base["questions"][1])
    follow.update(id="q-1", topic="followup", parent_id="q-1")
    for key in ("checkpoint", "choices", "allow_free_text", "status", "suppressed_reason", "round"):
        follow.pop(key)
    extra = {**copy.deepcopy(follow), "id": "tmp-b", "parent_id": "tmp-a", "round": 7}
    follow["id"] = "tmp-a"
    out = qmod.add(base, [follow, extra])
    new = out["questions"][3:]
    assert [q["id"] for q in new] == ["q-4", "q-5"]
    assert [q["round"] for q in new] == [2, 7]
    assert new[0]["status"] == "pending" and new[0]["checkpoint"] == 1 and new[0]["allow_free_text"] is True
    assert new[1]["parent_id"] == "q-4"  # a reference inside the batch is renumbered with it
    assert new[0]["parent_id"] == "q-1"  # a reference to an existing question is kept
    assert len(base["questions"]) == 3  # input untouched
    assert qmod.check(out, [])[1] == []


def test_add_rejects_incomplete_question() -> None:
    from cvtlib.errors import CvtError

    with pytest.raises(CvtError) as exc:
        qmod.add(load("questions.json"), [{"prompt": "no type"}])
    assert exc.value.err_id == "E_QUESTION_FIELDS"


def test_render_chat_is_one_line_per_question() -> None:
    text = qmod.render_chat(load("questions.json"))
    lines = text.splitlines()
    assert len(lines) == 4  # three questions and the footer
    assert lines[0].startswith("1. [q-1]") and "a) Service mesh" in lines[0] and "f) Startup employee" in lines[0]
    assert "[Default: Keep as gaps; nothing is added.]" in lines[0]
    assert lines[-1] == qmod.CHAT_FOOTER
    assert qmod.render_chat({"schema_version": "1", "run_id": "x", "questions": []}) == ""


def test_render_host_cursor_shape() -> None:
    rows = load("questions.json")
    rows["questions"].append({**copy.deepcopy(rows["questions"][2]), "id": "q-4", "type": "yes_no", "choices": []})
    payload = qmod.render_host(rows, "cursor")
    assert set(payload) == {"title", "questions"}
    first = payload["questions"][0]
    assert first["id"] == "q-1" and first["allow_multiple"] is True
    assert first["options"][0] == {"id": "service_mesh", "label": "Service mesh"} and len(first["options"]) == 6
    assert payload["questions"][1]["options"] == [] and payload["questions"][1]["allow_multiple"] is False
    assert payload["questions"][2]["allow_multiple"] is False
    assert payload["questions"][3]["options"] == [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}]


def test_render_host_claude_code_splits_long_choice_lists() -> None:
    payload = qmod.render_host(load("questions.json"), "claude_code")
    asked = [q for call in payload["calls"] for q in call]
    gaps = [q for q in asked if q["header"].startswith("Gaps")]
    assert [q["header"] for q in gaps] == ["Gaps (1/2)", "Gaps (2/2)"]
    assert [len(q["options"]) for q in gaps] == [3, 3]
    assert all(q["multiSelect"] for q in gaps)
    assert gaps[0]["question"].startswith("[q-1] ")
    assert all(len(q["header"]) <= qmod.CLAUDE_HEADER_MAX for q in asked)
    assert all(len(q["options"]) <= qmod.CLAUDE_MAX_OPTIONS and len(q["options"]) >= 2 for q in asked)
    assert all(set(o) == {"label", "description"} for q in asked for o in q["options"])
    assert all(len(call) <= qmod.CLAUDE_MAX_QUESTIONS_PER_CALL for call in payload["calls"])


def test_render_host_claude_code_groups_calls_of_four() -> None:
    rows = load("questions.json")
    template = rows["questions"][2]
    rows["questions"] = [{**copy.deepcopy(template), "id": f"q-{n}"} for n in range(1, 7)]
    payload = qmod.render_host(rows, "claude_code")
    assert [len(c) for c in payload["calls"]] == [4, 2]


def test_render_host_rejects_unknown_host() -> None:
    from cvtlib.errors import CvtError

    with pytest.raises(CvtError) as exc:
        qmod.render_host(load("questions.json"), "vim")
    assert exc.value.err_id == "E_HOST_FORMAT"


# --- the command -------------------------------------------------------------------------------------------
def test_command_pending_exits_6_and_waits(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    code, env = cvt_json(run_cvt, "questions", run_dir.name)
    assert code == 6 and env["stage"] == "awaiting_answers"
    assert env["data"]["pending"] == ["q-1", "q-2", "q-3"] and env["data"]["format"] == "chat"
    st = state.load(run_dir)
    assert (st["stage"], st["status"], st["checkpoints"]["cp1"]) == ("awaiting_answers", "awaiting_user", "pending")
    assert st["pending"]["kind"] == "questions" and st["pending"]["question_ids"] == ["q-1", "q-2", "q-3"]
    assert state.artifact(st, "questions") is not None


def test_command_prints_host_json_minified(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    proc = run_cvt("questions", run_dir.name, "--format", "host", "--host", "claude_code")
    assert proc.returncode == 6
    lines = proc.stdout.strip().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["calls"]
    proc = run_cvt("questions", run_dir.name, "--format", "host", "--host", "cursor")
    assert json.loads(proc.stdout)["title"] == qmod.CURSOR_TITLE
    proc = run_cvt("questions", run_dir.name, "--format", "json")
    assert [q["id"] for q in json.loads(proc.stdout)["questions"]] == ["q-1", "q-2", "q-3"]


def test_command_chat_output_is_terse(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    proc = run_cvt("questions", run_dir.name)
    assert proc.returncode == 6
    assert "1. [q-1]" in proc.stdout and qmod.CHAT_FOOTER in proc.stdout
    assert len(proc.stdout.splitlines()) <= 15


def test_command_without_pending_skips_checkpoint(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    rows = load("questions.json")
    for q in rows["questions"]:
        q["status"] = "answered"
    jsonio.dump_json(rows, run_dir / "questions.json")
    code, env = cvt_json(run_cvt, "questions", run_dir.name)
    assert code == 0 and env["stage"] == "answers_applied"
    st = state.load(run_dir)
    assert (st["stage"], st["checkpoints"]["cp1"], st["status"]) == ("answers_applied", "skipped", "ok")


def test_command_suppresses_on_second_run(workspace: Path, run_cvt) -> None:
    add_attestation("Service mesh", ["service mesh"])
    run_dir = make_run(workspace)
    code, env = cvt_json(run_cvt, "questions", run_dir.name)
    assert code == 6
    assert env["data"]["suppressed"][0]["choice_id"] == "service_mesh"
    written = jsonio.load_json(run_dir / "questions.json")
    assert "service_mesh" not in [c["id"] for c in written["questions"][0]["choices"]]
    assert "Service mesh" not in run_cvt("questions", run_dir.name).stdout.splitlines()[0]


def test_command_suppressing_every_question_applies_answers(workspace: Path, run_cvt) -> None:
    rows = load("questions.json")
    rows["questions"] = [rows["questions"][0]]
    rows["questions"][0]["choices"] = rows["questions"][0]["choices"][:1]
    add_attestation("Service mesh", ["service mesh"])
    run_dir = make_run(workspace)
    jsonio.dump_json(rows, run_dir / "questions.json")
    code, env = cvt_json(run_cvt, "questions", run_dir.name)
    assert code == 0 and env["stage"] == "answers_applied"
    assert jsonio.load_json(run_dir / "questions.json")["questions"][0]["status"] == "suppressed"


def test_command_violations_exit_1(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    rows = load("questions.json")
    rows["questions"][0]["allow_free_text"] = False
    jsonio.dump_json(rows, run_dir / "questions.json")
    code, env = cvt_json(run_cvt, "questions", run_dir.name)
    assert code == 1 and env["error"]["id"] == "E_CHECK_FAILED"
    assert env["data"]["violations"][0]["item_id"] == "q-1"
    assert state.load(run_dir)["status"] == "failed"


def test_command_requires_matched_stage_and_file(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    (run_dir / "questions.json").unlink()
    code, env = cvt_json(run_cvt, "questions", run_dir.name)
    assert code == 4 and env["error"]["id"] == "E_ARTIFACT_MISSING"
    other = make_run(workspace, slug="early")
    st = state.load(other)
    state.set_stage(st, "profiled")
    state.save(other, st)
    code, env = cvt_json(run_cvt, "questions", other.name)
    assert code == 4 and env["error"]["id"] == "E_STAGE"


def test_command_add_appends_followups(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace)
    follow = {k: v for k, v in load("questions.json")["questions"][1].items() if k in ("type", "prompt", "default")}
    follow.update(topic="followup", parent_id="q-3")
    path = workspace / "followups.json"
    path.write_text(json.dumps([follow]), encoding="utf-8")
    code, env = cvt_json(run_cvt, "questions", run_dir.name, "--add", str(path))
    assert code == 6 and env["data"]["pending"] == ["q-1", "q-2", "q-3", "q-4"]
    assert state.load(run_dir)["pending"]["kind"] == "followups"
    added = jsonio.load_json(run_dir / "questions.json")["questions"][3]
    assert (added["id"], added["round"], added["parent_id"]) == ("q-4", 2, "q-3")


def test_command_auto_mode_defaults_everything(workspace: Path, run_cvt) -> None:
    run_dir = make_run(workspace, auto=True)
    code, env = cvt_json(run_cvt, "questions", run_dir.name)
    assert code == 0 and env["stage"] == "answers_applied" and env["data"]["auto_defaulted"] == 3
    rows = jsonio.load_json(run_dir / "questions.json")["questions"]
    assert {q["status"] for q in rows} == {"defaulted"}
    rounds = jsonio.load_json(run_dir / "answers.json")["rounds"]
    assert rounds[0]["channel"] == "auto" and rounds[0]["items"] == []
    assert attestations.load_store(PERSON)["attestations"] == []
    assert state.load(run_dir)["checkpoints"]["cp1"] == "done"
