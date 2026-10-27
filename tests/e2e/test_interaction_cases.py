"""WP-25: every non-canonical checkpoint interaction case from `interaction-cases.yaml`, on the private sample.

Each test restores a fresh copy of the golden run at the right stage, applies the golden round or edits with real
`cvt` subprocesses, and asserts the YAML expectations (adjusted where the code and the YAML disagree: see the
comments and the WP-25 report).
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import yaml

from cvtlib import attestations, jsonio
from cvtlib.profile import merged_view

from .conftest import (
    EXIT_AWAITING_USER, EXIT_CHECK_FAILED, INTERACTION_CASES, SAMPLE_GOLDEN, SAMPLE_PERSON, Cvt, Scenario,
    assert_next_action,
)

CASES = yaml.safe_load(INTERACTION_CASES.read_text(encoding="utf-8"))
EARLIER_EMPLOYERS = ("Mindgeek", "Synchromedia", "LASSENA")  # exp-5..7: the "Earlier experience" line
UNSUPPORTED_ATTESTED_OP = "attested"
ATTESTATION_PREFIX = "att-"
GAP_ONLY_SKILLS = ("Service mesh", "Istio", "TypeScript")


def _round(sample: Scenario, cvt: Cvt, run: str, golden_name: str) -> Path:
    dest = cvt.out(run) / "answers.round.json"
    shutil.copyfile(SAMPLE_GOLDEN / golden_name, dest)
    return dest


def _text(tailored: dict) -> str:
    return json.dumps(tailored, ensure_ascii=False).lower()


# ------------------------------------------------------------------------------------------------------ rejection
def test_rejection_creates_nothing_and_the_cv_stays_clean(workspace: Path, cvt: Cvt, sample: Scenario) -> None:
    case = CASES["rejection"]
    run = sample.restore("awaiting_answers", cvt)
    round_file = _round(sample, cvt, run, "answers.rejection.round.json")
    dry = cvt("answers-apply", run, "--round", str(round_file), "--dry-run").envelope["data"]["plan"]
    assert dry["attestations"] == [] and dry["skeletons"] == []
    committed = cvt("answers-apply", run, "--round", str(round_file), "--commit", code=case["exit_code"]).envelope
    assert committed["stage"] == "answers_applied" and committed["data"]["created"] == []
    assert committed["data"]["pending"] == [] and committed["data"]["unresolved"] == []
    assert case["new_attestation_count"] == 0 == len(cvt.store(SAMPLE_PERSON)["attestations"])
    assert not [q for q in cvt.json(run, "questions.json")["questions"] if q["status"] == "pending"]
    assert case["followup_questions_created"] == 0

    # the golden plan cites the canonical attestations, so it must not assemble here; the same plan without them does
    plan = jsonio.load_json(SAMPLE_GOLDEN / "tailor-plan.json")
    shutil.copyfile(SAMPLE_GOLDEN / "tailor-plan.json", cvt.out(run) / "tailor-plan.json")
    failed = cvt("assemble", run, code=EXIT_CHECK_FAILED).envelope
    assert failed["ok"] is False and failed["data"]["violations"], failed

    clean = copy.deepcopy(plan)
    dropped = {name.lower() for name in (*GAP_ONLY_SKILLS, *case["final_cv"]["skills_not_contain"])}
    for group in clean["skills"]:
        group["items"] = [i for i in group["items"] if i["name"].lower() not in dropped]
    for job in clean["experience"]:
        for holder in (job, *job["engagements"]):
            holder["bullets"] = [b for b in holder["bullets"] if b["op"] != UNSUPPORTED_ATTESTED_OP]
    clean["talking_points"] = [t for t in clean["talking_points"]
                               if not any(ref.startswith(ATTESTATION_PREFIX) for ref in t["source_refs"])]
    # notes that talk about the declined claims would be about things the user does not have
    banned = [t.lower() for t in (*case["forbidden_terms_in_final_cv"], *GAP_ONLY_SKILLS)]
    clean["open_items"] = [o for o in clean["open_items"] if not any(b in o["text"].lower() for b in banned)]
    jsonio.dump_json(clean, cvt.out(run) / "tailor-plan.json")
    assert cvt("assemble", run).envelope["stage"] == "tailored"
    tailored = _text(cvt.json(run, "tailored.json"))
    for term in case["forbidden_terms_in_final_cv"]:
        assert term.lower() not in tailored, term
    skills = [i["name"].lower() for g in cvt.json(run, "tailored.json")["skills"] for i in g["items"]]
    for name in case["final_cv"]["skills_not_contain"]:
        assert name.lower() not in skills, name

    cvt("diff", run)
    cvt("apply-edits", run, str(SAMPLE_GOLDEN / "edits.approve-all.json"))
    cvt("approve", run)
    cvt("fit", run)
    assert cvt("validate", run).envelope["stage"] == "validated"  # claims_without_evidence: 0
    assert case["final_cv"]["claims_without_evidence"] == 0
    validation = cvt.json(run, "validation.json")
    assert next(g for g in validation["gates"] if g["name"] == "provenance")["status"] == "pass"
    (final,) = sorted((cvt.out(run) / "final").glob("*.pdf"))
    pdf = cvt.pdf_text(final).lower()
    for term in ("istio", "service mesh", "soc 2"):
        assert term not in pdf, term


# ------------------------------------------------------------------------------------------------------ correction
def test_correction_is_a_single_correction_only_attestation(workspace: Path, cvt: Cvt, sample: Scenario) -> None:
    case = CASES["correction"]
    run = sample.restore("awaiting_answers", cvt)
    round_file = _round(sample, cvt, run, "answers.correction.round.json")
    plan = cvt("answers-apply", run, "--round", str(round_file), "--dry-run").envelope["data"]["plan"]
    assert len(plan["attestations"]) == 1 and plan["attestations"][0]["correction"]["item_id"] == "exp-5"
    committed = cvt("answers-apply", run, "--round", str(round_file), "--commit", code=case["exit_code"]).envelope
    assert committed["stage"] == "answers_applied" and committed["data"]["pending"] == []
    store = cvt.store(SAMPLE_PERSON)["attestations"]
    assert len(store) == case["new_attestation_count"] == 1
    (att,) = store
    spec = case["attestations"][0]
    assert (att["type"], att["placement"], att["scope"]["kind"]) == (spec["type"], spec["placement"], spec["scope_kind"])
    assert att["scope"]["item_ids"] == spec["resolved_item_ids"] == ["exp-5"]
    assert att["status"] == "proposed"
    # interaction-cases.yaml expects separate start_date/end_date corrections; the contract allows one correction per
    # attestation, so the golden uses one `date_text` correction that carries both years (see the WP-25 report)
    correction = att["correction"]
    assert correction["item_id"] == "exp-5" and correction["field"] == "date_text"
    for wanted in spec["corrections"]:
        assert wanted["new_value_contains"] in correction["new_value"]
    assert att["terms"] == [] and att["detail"] == ""  # no new skills or bullets
    assert not any(word in " ".join(att["terms"]).lower() for word in case["forbidden_in_attestation_terms"])
    assert cvt.status(run)["stage"] == "answers_applied" and case["followup_questions_created"] == 0

    # a proposed correction is not applied until it is active; `profile-show --merged` reflects an active one
    profile = cvt.json(run, "profile.json")
    before = next(w for w in merged_view(profile, cvt.store(SAMPLE_PERSON)["attestations"])["work"] if w["id"] == "exp-5")
    assert before["date_text"] == correction["old_value"]
    cvt("attest", "activate", att["id"], run)
    shown = cvt("profile-show", run, "--merged").envelope["data"]
    assert shown["merged"] is True and [(a["id"], a["status"]) for a in shown["attestations"]] == [(att["id"], "active")]
    after = next(w for w in merged_view(profile, cvt.store(SAMPLE_PERSON)["attestations"])["work"] if w["id"] == "exp-5")
    assert after["date_text"] == correction["new_value"]
    assert all(token in after["date_text"] for token in ("2016", "2017"))
    assert after["position"] == before["position"] and after["name"] == before["name"]  # nothing else changed


# ------------------------------------------------------------------------------------------------- ambiguous scope
def test_ambiguous_scope_blocks_with_a_pending_scope_question(workspace: Path, cvt: Cvt, sample: Scenario) -> None:
    case = CASES["ambiguous_scope"]
    run = sample.restore("awaiting_answers", cvt)
    round_file = _round(sample, cvt, run, "answers.ambiguous.round.json")
    dry = cvt("answers-apply", run, "--round", str(round_file), "--dry-run").envelope["data"]["plan"]
    assert dry["unresolved"] == ["Kafka"] and len(dry["skeletons"]) == 1
    skeleton = dry["skeletons"][0]
    wanted = case["scope_question"]
    assert (skeleton["type"], skeleton["topic"], skeleton["checkpoint"]) == (wanted["type"], wanted["topic"], wanted["checkpoint"])

    committed = cvt("answers-apply", run, "--round", str(round_file), "--commit", code=6).envelope
    assert case["exit_code"] == 6 and committed["stage"] == "awaiting_answers"
    assert committed["data"]["unresolved"] == ["att-001"]
    status = cvt.status(run)
    assert status["stage"] == "awaiting_answers" and "scope unresolved for Kafka" in status["data"]["state"]["pending"]["message"]
    store = cvt.store(SAMPLE_PERSON)
    (att,) = store["attestations"]
    assert att["claim"] == "Kafka" and att["scope"]["kind"] == "unresolved"
    assert attestations.usable(store, run_id=run, include_proposed=True) == []  # unresolved is never usable
    assert case["usable_attestation_count"] == 0

    # the AI adds the scope question from the skeleton; it is a pending checkpoint-1 scope_confirm with a default
    skeleton["links"]["attestation_ids"] = [att["id"]]
    followups = cvt.home / "followups.json"
    followups.write_text(json.dumps({"schema_version": "1", "run_id": run, "questions": [skeleton]}), encoding="utf-8")
    cvt("questions", run, "--add", str(followups), code=EXIT_AWAITING_USER)
    question = next(q for q in cvt.json(run, "questions.json")["questions"] if q["id"] == skeleton["id"])
    assert question["status"] == "pending" and question["type"] == "scope_confirm" and question["topic"] == "scope"
    assert question["checkpoint"] == 1 and all(m in question["prompt"] for m in case["scope_question"]["parent_question_mentions"])
    assert question["default"]["choice_ids"] and question["links"]["attestation_ids"] == [att["id"]]
    assert cvt.status(run)["data"]["state"]["pending"]["kind"] == "followups"
    assert "kafka" not in _text(cvt.json(run, "profile.json"))  # nothing about Kafka reached any CV input


# ------------------------------------------------------------------------------------------------- followup skip
def test_followup_skip_leaves_nothing_open(workspace: Path, cvt: Cvt, sample: Scenario) -> None:
    case = CASES["followup_skip"]
    run = sample.restore("awaiting_answers", cvt)
    canonical = _round(sample, cvt, run, "answers.canonical.round.json")
    cvt("answers-apply", run, "--round", str(canonical), "--commit")
    cvt("questions", run, "--add", str(SAMPLE_GOLDEN / "followups.json"), code=EXIT_AWAITING_USER)
    before = cvt.store(SAMPLE_PERSON)["attestations"]
    followups = [q["id"] for q in cvt.json(run, "questions.json")["questions"] if q["status"] == "pending"]
    assert followups == ["q-9", "q-10"]

    skip_round = _round(sample, cvt, run, "answers.followups-skip.round.json")
    dry = cvt("answers-apply", run, "--round", str(skip_round), "--dry-run").envelope["data"]["plan"]
    assert dry["attestations"] == [] and dry["pending_after"] == []
    done = cvt("answers-apply", run, "--round", str(skip_round), "--commit", code=case["exit_code"]).envelope
    assert done["stage"] == "answers_applied" and done["data"]["created"] == []
    after = cvt.store(SAMPLE_PERSON)["attestations"]
    assert len(after) == len(before) and len(after) - len(before) == case["new_attestation_count"] == 0
    questions = cvt.json(run, "questions.json")["questions"]
    assert not [q for q in questions if q["status"] == "pending"]  # open_question_count_after: 0
    # the YAML says `defaulted`; a `skip` item marks a question `skipped` (WP-20 feedback 5): both mean "default used"
    assert {q["status"] for q in questions if q["id"] in followups} == {"skipped"}
    scope_att = next(a for a in after if a["claim"] == "SLOs")
    assert scope_att["scope"]["item_ids"] == ["exp-2.e4", "exp-2.e5"]  # the default (all listed items) stands
    assert_next_action(cvt.status(run), "answers_applied", run)


# ------------------------------------------------------------------------------------------------------ edit earlier
def test_edit_earlier_drops_only_the_earlier_experience_line(workspace: Path, cvt: Cvt, sample: Scenario) -> None:
    case = CASES["edit_earlier"]
    run = sample.restore("reported", cvt)
    (before_pdf,) = sorted((cvt.out(run) / "final").glob("*.pdf"))
    before_text = cvt.pdf_text(before_pdf)
    assert all(name in before_text for name in EARLIER_EMPLOYERS)
    before = cvt.json(run, "tailored.json")

    edits = jsonio.load_json(SAMPLE_GOLDEN / "edits.drop-earlier.json")
    assert [(o["op"], o.get("field")) for o in edits["ops"]] == [("set_field", "include_earlier_experience")]
    assert len(edits["ops"]) == case["op_count"] == 1 and edits["source"] in case["edits"]["source_any"]
    applied = cvt("apply-edits", run, str(SAMPLE_GOLDEN / "edits.drop-earlier.json"), code=case["exit_code"]).envelope
    assert applied["stage"] == "awaiting_approval"  # a later edit re-enters checkpoint 2 (interfaces.md section 6)
    assert cvt("check-tailored", run).envelope["ok"] is True  # check_tailored_must_pass
    after = cvt.json(run, "tailored.json")
    assert after["version"] == before["version"] + 1
    assert before["earlier_experience"]["include"] is True and after["earlier_experience"]["include"] is False

    cvt("approve", run)
    cvt("fit", run)
    assert cvt("validate", run).envelope["stage"] == "validated"
    (final,) = sorted((cvt.out(run) / "final").glob("*.pdf"))
    text = cvt.pdf_text(final)
    for name in EARLIER_EMPLOYERS:  # the earlier-experience line is absent from the re-rendered PDF
        assert name not in text, name
    for section in ("header", "summary", "skills", "experience", "certifications", "education", "talking_points"):
        assert after[section] == before[section], section  # no other items changed
    assert "Royal Bank of Canada" in text
