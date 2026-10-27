"""Live check of the checkpoint-1 interaction cases (WP-23).

Live tests run the real `answer_parse` stage (WP-21 `gtjob.stages.run_stage`) on each reply in
`tests/fixtures/expected/interaction-cases.yaml`, then `cvt answers-apply --dry-run` and `--commit`, and assert the
case's expectations. `canonical` also runs the whole CLI with `--answers` and checks the final CV, provenance with `att-`
IDs cited, and that a second JD does not re-ask answered gaps. `edit_earlier` runs the CLI with a checkpoint-2
instruction. Sample cases skip without the private sample CV, JD, and golden artifacts.

The checkers are pure functions. Unmarked replay tests feed them the golden rounds from `tests/fixtures/checkpoint/`
through the real deterministic commands, so the assertion code itself is exercised without a model.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import (EXIT_AWAITING_USER, EXIT_OK, FIXTURES, REPO_ROOT, STAFF_JD, Cvt, run_gtjob, seed_to_awaiting,
                      write_answers_yaml)

CHECKPOINT = FIXTURES / "checkpoint"
SYNTHETIC_PROFILE = FIXTURES / "profile" / "nested-engagements.json"
SYNTHETIC_PERSON = "sam-testperson"
SAMPLE_SLUG = "sample-cp1"
FIRST_QUESTION = "q-1"
ACCEPTED_EXIT_CODES = (EXIT_OK, EXIT_AWAITING_USER)
LIVE_CASES = ("canonical", "rejection", "correction", "ambiguous_scope", "followup_skip")
# A case that needs follow-up questions already open: apply this case's round first.
SETUP_CASE = {"followup_skip": "canonical"}
ATTEST_ACTIONS = ("attest", "correct")
ANSWERED_STATUSES = ("answered", "skipped", "defaulted", "suppressed")
EARLIER_LABEL = "Earlier experience"
IGNORED_KEYS = ("review", "version")


# ------------------------------------------------------------------ pure checkers
def round_attestations(round_obj: dict) -> list[dict]:
    return [att for item in round_obj.get("items", []) if item.get("action") in ATTEST_ACTIONS
            for att in item.get("attestations", [])]


def claim_text(att: dict) -> str:
    return " ".join([att.get("claim", ""), *att.get("terms", [])]).lower()


def find_attestation(atts: list[dict], spec: dict) -> dict | None:
    wanted = [c.lower() for c in spec.get("claim_any", [])]
    for att in atts:
        if wanted and not any(w in claim_text(att) for w in wanted):
            continue
        if not wanted and att.get("type") != spec.get("type"):
            continue
        return att
    return None


def check_round(round_obj: dict, case: dict) -> list[str]:
    """Problems with a parsed `answers.round.json` against the case (claims, types, placements, scopes, numbers)."""
    problems: list[str] = []
    atts = round_attestations(round_obj)
    expected = case.get("attestations", [])
    if not expected and atts:
        problems.append(f"expected no attestations, got {[a['claim'] for a in atts]}")
    for spec in expected:
        att = find_attestation(atts, spec)
        label = spec.get("claim_any", [spec.get("type")])[0]
        if att is None:
            problems.append(f"no attestation for {label}")
            continue
        if att.get("type") != spec["type"]:
            problems.append(f"{label}: type {att.get('type')} != {spec['type']}")
        if "placement" in spec and att.get("placement") != spec["placement"]:
            problems.append(f"{label}: placement {att.get('placement')} != {spec['placement']}")
        scope = att.get("scope", {})
        if scope.get("kind") != spec["scope_kind"]:
            problems.append(f"{label}: scope kind {scope.get('kind')} != {spec['scope_kind']}")
        if "role_label" in spec and spec["role_label"].lower() not in scope.get("role_label", "").lower():
            problems.append(f"{label}: role_label {scope.get('role_label')!r} lacks {spec['role_label']!r}")
        if spec.get("caveat_nonempty") and not att.get("caveat", "").strip():
            problems.append(f"{label}: caveat is empty")
        for fix in spec.get("corrections", []):
            got = att.get("correction", {})
            if (got.get("item_id"), got.get("field")) != (fix["item_id"], fix["field"]) \
                    or fix["new_value_contains"] not in got.get("new_value", ""):
                problems.append(f"{label}: correction {got} does not match {fix}")
    forbidden = case.get("forbidden_number_regex")
    if forbidden:
        for att in atts:
            blob = " ".join([att.get("claim", ""), att.get("detail", ""), att.get("caveat", ""), *att.get("terms", [])])
            if re.search(forbidden, blob):
                problems.append(f"invented number in {att.get('claim')!r}")
    for word in case.get("forbidden_in_attestation_terms", []):
        for att in atts:
            if word in att.get("type", "") or word in att.get("placement", ""):
                problems.append(f"attestation {att.get('claim')!r} is a {word} (forbidden for this case)")
    return problems


def check_commit(case: dict, *, code: int, before: dict, after: dict) -> list[str]:
    """Problems after `answers-apply --commit`. `before`/`after` = {"atts", "questions", "state"} snapshots."""
    problems: list[str] = []
    wanted_code = case.get("exit_code")
    if wanted_code is not None and code != wanted_code:
        problems.append(f"exit {code} != {wanted_code}")
    if wanted_code is None and code not in ACCEPTED_EXIT_CODES:
        problems.append(f"exit {code} not in {ACCEPTED_EXIT_CODES}")
    known = {a["id"] for a in before["atts"]}
    new = [a for a in after["atts"] if a["id"] not in known]
    if "new_attestation_count" in case and len(new) != case["new_attestation_count"]:
        problems.append(f"{len(new)} new attestations != {case['new_attestation_count']}")
    for spec in case.get("attestations", []):
        att = find_attestation(new, spec)
        if att is None:
            continue  # check_round reports the missing claim
        if "resolved_item_ids" in spec and sorted(att["scope"]["item_ids"]) != sorted(spec["resolved_item_ids"]):
            problems.append(f"{spec.get('claim_any', [''])[0]}: resolved {att['scope']['item_ids']} != "
                            f"{spec['resolved_item_ids']}")
        if spec.get("usable") is False and att["scope"]["kind"] != "unresolved":
            problems.append(f"{att['claim']} should stay unusable (unresolved)")
    if "usable_attestation_count" in case:
        usable = [a for a in new if a["scope"]["kind"] != "unresolved" and a["status"] != "revoked"]
        if len(usable) != case["usable_attestation_count"]:
            problems.append(f"{len(usable)} usable attestations != {case['usable_attestation_count']}")
    licensed = " ".join(claim_text(a) for a in after["atts"])
    for gap in (*case.get("remain_gaps", []), *case.get("declined_gaps", [])):
        if gap.lower() in licensed:
            problems.append(f"gap {gap!r} must not be licensed by an attestation")
    created = [q for q in after["questions"] if q["id"] not in {x["id"] for x in before["questions"]}]
    if "followup_questions_created" in case and len(created) != case["followup_questions_created"]:
        problems.append(f"{len(created)} follow-up questions created != {case['followup_questions_created']}")
    if "scope_question" in case:
        problems += check_scope_question(case["scope_question"], created, after["questions"])
    if case.get("exit_state") == "AWAITING_USER" and after["state"]["stage"] != "awaiting_answers":
        problems.append(f"stage {after['state']['stage']} != awaiting_answers")
    if "open_question_count_after" in case:
        open_count = sum(1 for q in after["questions"] if q["status"] == "pending")
        if open_count != case["open_question_count_after"]:
            problems.append(f"{open_count} open questions != {case['open_question_count_after']}")
    if "question_status_after" in case:
        was_open = {q["id"] for q in before["questions"] if q["status"] == "pending" and q.get("topic") in
                    ("scope", "followup")}
        bad = [q["id"] for q in after["questions"] if q["id"] in was_open and q["status"] != case["question_status_after"]]
        if bad or not was_open:
            problems.append(f"follow-ups {sorted(was_open) or 'missing'} not all {case['question_status_after']}: {bad}")
    return problems


def check_scope_question(spec: dict, created: list[dict], everything: list[dict]) -> list[str]:
    scope = [q for q in created if q.get("topic") == spec["topic"]]
    if spec.get("created") and not scope:
        return ["no scope question was created"]
    problems = []
    for question in scope:
        parent = next((q for q in everything if q["id"] == question.get("parent_id")), {})
        text = f"{question.get('prompt', '')} {parent.get('prompt', '')}".lower()
        if question.get("type") != spec["type"] or question.get("checkpoint") != spec["checkpoint"]:
            problems.append(f"scope question is {question.get('type')}/cp{question.get('checkpoint')}")
        for term in spec.get("parent_question_mentions", []):
            if term.lower() not in text:
                problems.append(f"scope question does not mention {term}")
        default = question.get("default") or {}
        if spec.get("has_default") and not (default.get("choice_ids") or default.get("text")):
            problems.append("scope question has no default")
    return problems


def check_forbidden_terms(text: str, terms: list[str]) -> list[str]:
    return [f"{term!r} appears in the final CV" for term in terms if term.lower() in text.lower()]


def tailored_skills(tailored: dict) -> list[str]:
    return [item["name"] for group in tailored.get("skills", []) for item in group.get("items", [])]


def bullets_under(node: object, profile_ids: list[str]) -> list[dict]:
    """Every bullet of any tailored work/engagement whose `profile_id` is in `profile_ids` (recursive)."""
    found: list[dict] = []
    if isinstance(node, dict):
        if node.get("profile_id") in profile_ids:
            found += node.get("bullets", [])
        for value in node.values():
            found += bullets_under(value, profile_ids)
    elif isinstance(node, list):
        for value in node:
            found += bullets_under(value, profile_ids)
    return found


def cited_attestations(node: object) -> set[str]:
    """Every `att-NNN` cited in `source_refs` anywhere in a tailored document."""
    cited: set[str] = set()
    if isinstance(node, dict):
        cited |= {ref for ref in node.get("source_refs", []) if isinstance(ref, str) and ref.startswith("att-")}
        for value in node.values():
            cited |= cited_attestations(value)
    elif isinstance(node, list):
        for value in node:
            cited |= cited_attestations(value)
    return cited


def check_final_cv(spec: dict, tailored: dict) -> list[str]:
    problems = []
    skills = [s.lower() for s in tailored_skills(tailored)]
    for name in spec.get("skills_contain", []):
        if name.lower() not in skills:
            problems.append(f"skill {name} missing from the final CV")
    for name in spec.get("skills_not_contain", []):
        if name.lower() in skills:
            problems.append(f"skill {name} must not be in the final CV")
    rule = spec.get("bullets_in_any_of")
    if rule:
        texts = [b["text"].lower() for b in bullets_under(tailored.get("experience", []), rule["items"])]
        if not any(word.lower() in text for text in texts for word in rule["contain_any"]):
            problems.append(f"no bullet under {rule['items']} contains any of {rule['contain_any']}")
    return problems


def strip_volatile(node: object) -> object:
    """Drop review markers and versions so two tailored versions can be compared for content changes."""
    if isinstance(node, dict):
        return {k: strip_volatile(v) for k, v in node.items() if k not in IGNORED_KEYS}
    if isinstance(node, list):
        return [strip_volatile(v) for v in node]
    return node


# ------------------------------------------------------------------ snapshots and seeding
def snapshot(cvt: Cvt, run: str, person: str) -> dict:
    return {"atts": copy.deepcopy(cvt.attestations(person)),
            "questions": copy.deepcopy(cvt.json(run, "questions.json")["questions"]),
            "state": cvt.json(run, "state.json")}


def apply_round(cvt: Cvt, run: str, round_path: Path, person: str, case: dict) -> list[str]:
    """dry-run, add the suggested scope skeletons as follow-ups (what the host agent does), commit; return problems."""
    dry = cvt.run("answers-apply", run, "--round", str(round_path), "--dry-run")
    before = snapshot(cvt, run, person)
    skeletons = dry["data"]["plan"]["skeletons"]
    if skeletons:
        follow = cvt.home / f"followups-{round_path.stem}.json"
        follow.write_text(json.dumps(skeletons), encoding="utf-8")
        cvt.run("questions", run, "--add", str(follow), code=EXIT_AWAITING_USER)
    proc = cvt.raw("answers-apply", run, "--round", str(round_path), "--commit", "--json")
    return check_commit(case, code=proc.returncode, before=before, after=snapshot(cvt, run, person))


def synthetic_run(cvt: Cvt, slug: str = "replay") -> str:
    """A run with the synthetic profile at awaiting_answers (the same setup as tests/unit/test_answers.py)."""
    from cvtlib import state

    cv = cvt.home / "cv.txt"
    cv.write_text("Sam Testperson\nsam@example.invalid\n", encoding="utf-8")
    run_dir = state.create_run(cv, "text", "", "Platform Reliability Engineer at Example Co.", {}, slug=slug)
    shutil.copy(SYNTHETIC_PROFILE, run_dir / "profile.json")
    for name in ("jd.json", "questions.json"):
        shutil.copy(CHECKPOINT / name, run_dir / name)
    st = state.load(run_dir)
    st["person_slug"] = SYNTHETIC_PERSON
    state.record_artifact(run_dir, st, "profile", "profile.json")
    state.record_artifact(run_dir, st, "jd", "jd.json")
    state.record_artifact(run_dir, st, "questions", "questions.json", cascade=False)
    state.set_stage(st, "awaiting_answers", "awaiting_user",
                    pending={"kind": "questions", "question_ids": ["q-1", "q-2", "q-3"], "message": "3 questions"})
    st["checkpoints"]["cp1"] = "pending"
    state.save(run_dir, st)
    return run_dir.name


def person_of(cvt: Cvt, run: str) -> str:
    return cvt.json(run, "state.json")["person_slug"]


# ------------------------------------------------------------------ replay tests (no model)
REPLAY_ROUNDS = {"canonical": "round-canonical.json", "rejection": "round-reject.json",
                 "ambiguous_scope": "round-ambiguous.json"}


def correction_round(item_id: str = "exp-5", old_value: str = "") -> dict:
    """A parsed reply for the correction case, as the model should produce it (no golden round exists for exp-5)."""
    return {"round": 1, "checkpoint": 1, "received_at": "2026-01-01T00:00:00Z", "channel": "chat",
            "raw_text": "Mindgeek was 2016 to 2017", "unmentioned_question_ids": ["q-1", "q-2", "q-3"],
            "items": [{"question_id": "", "action": "correct", "choice_ids": [], "instruction": "", "note": "",
                       "attestations": [{
                           "type": "correction", "claim": "Mindgeek dates are 2016 - 2017", "terms": [], "detail": "",
                           "scope": {"kind": "items", "role_label": "", "item_ids": [item_id], "description": ""},
                           "placement": "correction_only",
                           "correction": {"item_id": item_id, "field": "start_date", "old_value": old_value, "new_value": "2016"},
                           "verbatim": "Mindgeek was 2016 to 2017", "caveat": ""}]}]}


@pytest.mark.parametrize("name", sorted(REPLAY_ROUNDS))
def test_checkers_accept_the_golden_rounds(name: str, interaction_cases: dict) -> None:
    round_obj = json.loads((CHECKPOINT / REPLAY_ROUNDS[name]).read_text(encoding="utf-8"))
    case = interaction_cases[name]
    assert check_round(round_obj, case) == []


def test_checkers_reject_a_wrong_round(interaction_cases: dict) -> None:
    round_obj = json.loads((CHECKPOINT / "round-canonical.json").read_text(encoding="utf-8"))
    bad = copy.deepcopy(round_obj)
    istio = next(a for a in round_attestations(bad) if "istio" in a["claim"].lower())
    istio.update(caveat="", placement="bullets")
    istio["scope"]["kind"] = "items"
    next(a for a in round_attestations(bad) if "slo" in a["claim"].lower())["detail"] = "cut MTTR by 40%"
    problems = check_round(bad, interaction_cases["canonical"])
    assert len(problems) >= 4, problems
    assert check_round(round_obj, interaction_cases["rejection"])  # the canonical reply is not a rejection


def test_correction_checker(interaction_cases: dict) -> None:
    case = interaction_cases["correction"]
    assert check_round(correction_round(), {**case, "attestations": [
        {**case["attestations"][0], "corrections": [case["attestations"][0]["corrections"][0]]}]}) == []
    assert check_round(correction_round(), case)  # the end_date correction is absent from this single-field round


def test_final_cv_checker(interaction_cases: dict) -> None:
    tailored = {"skills": [{"items": [{"name": "Istio"}, {"name": "TypeScript"}]}],
                "experience": [{"profile_id": "exp-2", "bullets": [], "engagements": [
                    {"profile_id": "exp-2.e4", "bullets": [{"text": "Defined SLOs for the platform."}]}]}]}
    assert check_final_cv(interaction_cases["canonical"]["final_cv"], tailored) == []
    assert check_final_cv(interaction_cases["rejection"]["final_cv"], tailored)
    assert check_forbidden_terms("Istio on GKE", ["istio", "kafka"]) == ["'istio' appears in the final CV"]
    assert cited_attestations({"a": [{"source_refs": ["att-001", "exp-1"]}]}) == {"att-001"}


@pytest.mark.parametrize("name", sorted(REPLAY_ROUNDS))
def test_replay_through_the_real_commands(name: str, cvt: Cvt, interaction_cases: dict) -> None:
    """Golden round -> `answers-apply --dry-run/--commit` on the synthetic run -> commit expectations."""
    run = synthetic_run(cvt)
    case = interaction_cases[name]
    problems = apply_round(cvt, run, CHECKPOINT / REPLAY_ROUNDS[name], person_of(cvt, run), case)
    assert problems == [], problems


def test_replay_followup_skip_after_canonical(cvt: Cvt, interaction_cases: dict) -> None:
    """The canonical exchange leaves scope follow-ups open; "skip the rest, use your defaults" defaults them all."""
    run = synthetic_run(cvt)
    person = person_of(cvt, run)
    assert apply_round(cvt, run, CHECKPOINT / "round-canonical.json", person, interaction_cases["canonical"]) == []
    pending = [q["id"] for q in cvt.json(run, "questions.json")["questions"] if q["status"] == "pending"]
    assert pending, "the canonical exchange should leave scope follow-ups open"
    skip = json.loads((CHECKPOINT / "round-skip.json").read_text(encoding="utf-8"))
    skip.update(items=[], unmentioned_question_ids=pending, raw_text="skip the rest, use your defaults")
    skip_path = cvt.home / "skip.round.json"
    skip_path.write_text(json.dumps(skip), encoding="utf-8")
    assert apply_round(cvt, run, skip_path, person, interaction_cases["followup_skip"]) == []


def test_replay_correction_round(cvt: Cvt, interaction_cases: dict) -> None:
    run = synthetic_run(cvt)
    path = cvt.home / "correction.round.json"
    path.write_text(json.dumps(correction_round("exp-3", "2015-01")), encoding="utf-8")  # no exp-5 in the synthetic profile
    cvt.run("answers-apply", run, "--round", str(path), "--dry-run")
    proc = cvt.raw("answers-apply", run, "--round", str(path), "--commit", "--json")
    assert proc.returncode == EXIT_OK, proc.stdout
    att = cvt.attestations(person_of(cvt, run))[-1]
    assert att["type"] == "correction" and att["placement"] == "correction_only" and att["scope"]["item_ids"] == ["exp-3"]


# ------------------------------------------------------------------ live tests
def sample_run(cvt: Cvt, sample_cv: Path, private_sample: Path) -> str:
    return seed_to_awaiting(cvt, cv=sample_cv, jd=STAFF_JD, artifacts=private_sample, slug=SAMPLE_SLUG)


def parse_reply(stage_env, cvt: Cvt, run: str, reply: str) -> Path:
    client, config, run_stage = stage_env
    path = run_stage("answer_parse", cvt.out(run), client=client, config=config, extra={"reply": reply})
    return Path(path)


@pytest.mark.live
@pytest.mark.parametrize("name", LIVE_CASES)
def test_answer_parse_live(name: str, stage_env, sample_cv: Path, private_sample: Path, cvt: Cvt,
                           interaction_cases: dict) -> None:
    case = interaction_cases[name]
    run = sample_run(cvt, sample_cv, private_sample)
    person = person_of(cvt, run)
    setup = SETUP_CASE.get(name)
    if setup:
        setup_case = interaction_cases[setup]
        setup_path = parse_reply(stage_env, cvt, run, (REPO_ROOT / setup_case["reply_file"]).read_text().strip())
        assert apply_round(cvt, run, setup_path, person, setup_case) == []
    reply = (REPO_ROOT / case["reply_file"]).read_text(encoding="utf-8").strip()
    round_path = parse_reply(stage_env, cvt, run, reply)
    problems = check_round(json.loads(round_path.read_text(encoding="utf-8")), case)
    problems += apply_round(cvt, run, round_path, person, case)
    assert problems == [], "\n".join(problems)


def final_pdf_text(run_dir: Path) -> str:
    from judge import pdf_text

    return pdf_text(run_dir / "cv.pdf")


def run_cli(cvt: Cvt, *args: str, code: int = EXIT_OK) -> subprocess.CompletedProcess:
    proc = run_gtjob(cvt.home, *args)
    assert proc.returncode == code, f"gtjob {' '.join(args[:2])} exited {proc.returncode}:\n{proc.stderr[-1500:]}"
    return proc


def only_run(cvt: Cvt, slug: str) -> Path:
    runs = sorted((cvt.home / "out").glob(f"*{slug}*"))
    assert runs, f"no run for {slug}"
    return runs[-1]


@pytest.mark.live
def test_canonical_end_to_end_and_second_jd(needs_key, sample_cv: Path, private_sample: Path, cvt: Cvt,
                                            interaction_cases: dict, tmp_path: Path) -> None:
    case = interaction_cases["canonical"]
    reply = (REPO_ROOT / case["reply_file"]).read_text(encoding="utf-8").strip()
    answers = write_answers_yaml(tmp_path / "answers.yaml", checkpoint1={FIRST_QUESTION: reply, "default_rest": True})
    run_cli(cvt, "tailor", "--cv", str(sample_cv), "--jd", str(STAFF_JD), "--slug", "canonical", "--answers", str(answers))
    run_dir = only_run(cvt, "canonical")
    tailored = json.loads((run_dir / "tailored.json").read_text(encoding="utf-8"))
    validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    problems = check_final_cv(case["final_cv"], tailored)
    cited = cited_attestations(tailored)
    store = {a["id"]: a for a in cvt.attestations(person_of(cvt, run_dir.name))}
    if not cited:
        problems.append("no att- ID is cited in tailored.json")
    problems += [f"{att_id} is not active" for att_id in cited if store.get(att_id, {}).get("status") != "active"]
    gates = {gate["name"]: gate["status"] for gate in validation["gates"]}
    if gates.get("provenance") != "pass" or not validation.get("passed"):
        problems.append(f"validation did not pass: {gates}")
    text = final_pdf_text(run_dir)
    problems += [f"{word!r} missing from the PDF text" for word in case["final_cv"]["skills_contain"] if word not in text]
    assert problems == [], "\n".join(problems)

    # Same CV, second JD: answered gaps must not come back. Non-interactive, so it stops at checkpoint 1 (exit 6).
    second = REPO_ROOT / case["second_run_jd"]
    run_cli(cvt, "tailor", "--cv", str(sample_cv), "--jd", str(second), "--slug", "second", code=EXIT_AWAITING_USER)
    pending = [q for q in json.loads((only_run(cvt, "second") / "questions.json").read_text(encoding="utf-8"))["questions"]
               if q["status"] == "pending"]
    asked = " ".join([q["prompt"] + " " + " ".join(c["label"] for c in q["choices"]) for q in pending]).lower()
    repeated = [term for term in case["second_run_must_not_ask_about"] if term.lower() in asked]
    assert not repeated, f"second run re-asks about {repeated}"


@pytest.mark.live
def test_edit_earlier_end_to_end(needs_key, sample_cv: Path, private_sample: Path, cvt: Cvt, interaction_cases: dict,
                                 tmp_path: Path) -> None:
    case = interaction_cases["edit_earlier"]
    instruction = (REPO_ROOT / case["reply_file"]).read_text(encoding="utf-8").strip()
    answers = write_answers_yaml(tmp_path / "answers.yaml", checkpoint1={"default_rest": True},
                                 checkpoint2=[instruction])
    run_cli(cvt, "tailor", "--cv", str(sample_cv), "--jd", str(STAFF_JD), "--slug", "edit-earlier", "--answers", str(answers))
    run_dir = only_run(cvt, "edit-earlier")
    edits = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((run_dir / "edits").glob("*.json"))]
    spec = case["edits"]["ops"][0]
    ops = [(e["source"], op) for e in edits for op in e["ops"] if op["op"] == spec["op"] and op["field"] == spec["field"]]
    problems = []
    if not ops or ops[-1][1]["value"].lower() != spec["value"]:
        problems.append(f"no set_field {spec['field']}={spec['value']} op in {[e['ops'] for e in edits]}")
    if ops and ops[-1][0] not in case["edits"]["source_any"]:
        problems.append(f"edit source {ops[-1][0]} not in {case['edits']['source_any']}")
    tailored = json.loads((run_dir / "tailored.json").read_text(encoding="utf-8"))
    if tailored["earlier_experience"]["include"] is not False:
        problems.append("earlier_experience.include is still true")
    if EARLIER_LABEL in final_pdf_text(run_dir):
        problems.append(f"{EARLIER_LABEL!r} still in the PDF")
    if case.get("check_tailored_must_pass"):
        proc = cvt.raw("check-tailored", run_dir.name, "--json")
        if proc.returncode != EXIT_OK:
            problems.append("check-tailored failed after the edit")
    history = sorted((run_dir / "tailored.history").glob("v*.json"))
    if case["final_cv"].get("no_other_items_changed") and history:
        first = strip_volatile(json.loads(history[0].read_text(encoding="utf-8")))
        last = strip_volatile(tailored)
        first.pop("earlier_experience", None), last.pop("earlier_experience", None)
        changed = [k for k in last if last[k] != first.get(k)]
        if changed:
            problems.append(f"other sections changed by the edit: {changed}")
    assert problems == [], "\n".join(problems)
