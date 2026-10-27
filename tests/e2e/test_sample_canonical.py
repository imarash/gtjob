"""WP-25: the canonical exchange on the private sample CV and JD (skips when the private goldens are absent).

Replays WP-20 with real `cvt` subprocesses: the AI stages are the saved golden artifacts, everything else is the real
command. Then a second JD reuses the confirmed attestations, and a repeat of the same JD is offered a seed.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader

from .conftest import (
    EXIT_AWAITING_USER, INTERACTION_CASES, SAMPLE_GOLDEN, SAMPLE_JD, SAMPLE_PERSON, SECOND_JD, Cvt, Scenario,
    assert_next_action, packet, require_private_sample, sample_cv_path,
)

SAMPLE_PAGE_TARGET = 2
CANONICAL_REPLY = "add service mesh, istio, typescript. and add slo and error budget to the sre related cv items"
SECOND_RUN_PACKET_BUDGET = 20_000  # interfaces.md section 14: all packets of a new-JD run on a cached profile
SEED_MARKER = "# Seed (run "
CASES = yaml.safe_load(INTERACTION_CASES.read_text(encoding="utf-8"))
CANONICAL = CASES["canonical"]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _skip_without_private() -> None:
    require_private_sample()


def _init(cvt: Cvt, jd_path: Path, slug: str) -> str:
    inputs = cvt.home / "inputs"
    inputs.mkdir(exist_ok=True)
    cv, jd = inputs / sample_cv_path().name, inputs / jd_path.name
    shutil.copyfile(sample_cv_path(), cv)
    shutil.copyfile(jd_path, jd)
    return cvt("init", "--cv", str(cv), "--jd", str(jd), "--slug", slug).envelope["data"]["run_slug"]


def _bullet_texts(tailored: dict) -> dict[str, list[str]]:
    """engagement/work id (the profile id the tailored element came from) -> bullet texts."""
    found: dict[str, list[str]] = {}
    for job in tailored["experience"]:
        for eng in job.get("engagements", []):
            found.setdefault(eng["profile_id"], []).extend(b["text"] for b in eng.get("bullets", []))
        found.setdefault(job["profile_id"], []).extend(b["text"] for b in job.get("bullets", []))
    return found


def test_canonical_exchange_to_report(workspace: Path, cvt: Cvt, agent_step) -> None:
    _skip_without_private()
    packets: dict[str, dict] = {}
    run = _init(cvt, SAMPLE_JD, "golden-sample")
    cvt("ingest", run)
    assert cvt("profile-cache", run, "--lookup").envelope["data"]["hit"] is False
    packets["profile"] = packet(cvt, "profile", run)
    agent_step(run, "profile-map.json", SAMPLE_GOLDEN / "profile-map.json")
    cvt("profile-build", run)
    cvt("profile-cache", run, "--store")
    packets["jd"] = packet(cvt, "jd", run)
    agent_step(run, "jd.json", SAMPLE_GOLDEN / "jd.json")
    cvt("jd-check", run)
    packets["match"] = packet(cvt, "match", run)
    agent_step(run, "match.json", SAMPLE_GOLDEN / "match.json")
    cvt("match-check", run)
    packets["questions"] = packet(cvt, "questions", run)
    agent_step(run, "questions.json", SAMPLE_GOLDEN / "questions.json")
    cvt("questions", run, code=EXIT_AWAITING_USER)
    assert cvt.status(run)["stage"] == "awaiting_answers"

    # checkpoint 1, canonical reply: dry run first (human output and the structured plan), then commit
    packets["answer_parse"] = packet(cvt, "answer_parse", run, "--reply", CANONICAL_REPLY)
    round_file = agent_step(run, "answers.round.json", SAMPLE_GOLDEN / "answers.canonical.round.json")
    human = cvt.raw("answers-apply", run, "--round", str(round_file), "--dry-run")
    assert human.returncode == 0, human.stderr
    listing = human.stdout
    for claim in ("Service mesh", "Istio", "TypeScript"):
        assert f'skill "{claim}"' in listing, claim
    assert 'practice "SLOs"' in listing and "role_label=SRE" in listing
    assert "exp-2.e4" in listing and "exp-2.e5" in listing
    assert not (cvt.out(run) / "answers.json").exists()
    plan = cvt("answers-apply", run, "--round", str(round_file), "--dry-run").envelope["data"]["plan"]
    scoped = [a for a in plan["attestations"] if a["scope_kind"] == "role_label"]
    assert {a["claim"] for a in scoped} == {"SLOs", "Error budgets"}
    for item in scoped:
        assert item["role_label"] == "SRE"
        assert [i["item_id"] for i in item["items"]] == ["exp-2.e4", "exp-2.e5"]

    committed = cvt("answers-apply", run, "--round", str(round_file), "--commit").envelope
    assert committed["stage"] == "answers_applied" and committed["data"]["created"] == [f"att-00{n}" for n in range(1, 6)]
    store = cvt.store(SAMPLE_PERSON)["attestations"]
    assert [a["id"] for a in store] == [f"att-00{n}" for n in range(1, 6)]
    assert {a["status"] for a in store} == {"proposed"}
    for spec, att in zip(CANONICAL["attestations"], store):
        assert att["claim"].lower() in {c.lower() for c in spec["claim_any"]}, (att["claim"], spec)
        assert (att["type"], att["placement"], att["scope"]["kind"]) == (spec["type"], spec["placement"], spec["scope_kind"])
        if spec.get("caveat_nonempty"):
            assert att["caveat"].strip()
        if spec.get("role_label"):
            assert att["scope"]["role_label"] == spec["role_label"]
            assert att["scope"]["item_ids"] == spec["resolved_item_ids"]
        assert not re.search(CANONICAL["forbidden_number_regex"], f"{att['claim']} {att['detail']} {' '.join(att['terms'])}")

    # follow-ups: add them (exit 6, stage awaiting_answers), then commit the skip round
    cvt("questions", run, "--add", str(SAMPLE_GOLDEN / "followups.json"), code=EXIT_AWAITING_USER)
    assert cvt.status(run)["stage"] == "awaiting_answers"
    skip_round = agent_step(run, "answers.round.json", SAMPLE_GOLDEN / "answers.followups-skip.round.json")
    skipped = cvt("answers-apply", run, "--round", str(skip_round), "--commit").envelope
    assert skipped["stage"] == "answers_applied"
    assert_next_action(cvt.status(run), "answers_applied", run)

    # tailor: saved plan -> assemble -> check-tailored
    packets["tailor"] = packet(cvt, "tailor", run)
    agent_step(run, "tailor-plan.json", SAMPLE_GOLDEN / "tailor-plan.json")
    assert cvt("assemble", run).envelope["stage"] == "tailored"
    assert cvt("check-tailored", run).envelope["ok"] is True

    # checkpoint 2: approve everything; the proposed attestations become active
    cvt("diff", run)
    cvt("apply-edits", run, str(SAMPLE_GOLDEN / "edits.approve-all.json"))
    assert cvt("approve", run).envelope["stage"] == "approved"
    assert {a["status"] for a in cvt.store(SAMPLE_PERSON)["attestations"]} == {"active"}
    assert cvt.json(run, "state.json")["attestations_used"] == [a["id"] for a in store]

    fitted = cvt("fit", run).envelope
    assert fitted["stage"] == "rendered" and cvt.json(run, "fit.json")["pages"] == SAMPLE_PAGE_TARGET
    assert cvt("validate", run).envelope["stage"] == "validated"
    validation = cvt.json(run, "validation.json")
    assert validation["gates"] and not [g["name"] for g in validation["gates"] if g["status"] == "fail"]
    packets["critic"] = packet(cvt, "critic", run)
    assert cvt("report", run).envelope["stage"] == "reported"

    # the expectations under interaction-cases.yaml canonical.final_cv, against the PDF text
    (final,) = sorted((cvt.out(run) / "final").glob("*.pdf"))
    assert len(PdfReader(str(final)).pages) == SAMPLE_PAGE_TARGET
    text = _norm(cvt.pdf_text(final))
    for skill in CANONICAL["final_cv"]["skills_contain"]:
        assert skill.lower() in text, skill
    spec = CANONICAL["final_cv"]["bullets_in_any_of"]
    bullets = _bullet_texts(cvt.json(run, "tailored.json"))
    scoped_text = _norm(" ".join(t for item in spec["items"] for t in bullets.get(item, [])))
    assert any(term.lower() in scoped_text for term in spec["contain_any"]), (spec, bullets.keys())
    assert any(term.lower() in text for term in spec["contain_any"])
    for gap in CANONICAL["remain_gaps"]:  # unconfirmed gaps stay out of the CV and appear in the report
        assert gap.lower() not in text
    assert "SOC 2" in (cvt.out(run) / "report.md").read_text(encoding="utf-8")

    assert all(p["est_tokens"] <= p["budget"] for p in packets.values())
    assert len(packets) == 7


def test_answer_parse_packet_fits_budget_on_sample(workspace: Path, cvt: Cvt, sample: Scenario) -> None:
    run = sample.restore("awaiting_answers", cvt)
    packet(cvt, "answer_parse", run, "--reply", CANONICAL_REPLY)


def test_second_jd_reuses_confirmed_attestations(workspace: Path, cvt: Cvt, sample: Scenario) -> None:
    sample.restore("reported", cvt)  # profile cache, active attestations, and the first run
    first = sample.run_slug
    run = _init(cvt, SECOND_JD, "golden-second")
    assert run != first
    cvt("ingest", run)
    hit = cvt("profile-cache", run, "--lookup").envelope
    assert hit["data"]["hit"] is True and hit["stage"] == "profiled"
    assert_next_action(cvt.status(run), "profiled", run)

    packets = {"jd": packet(cvt, "jd", run)}
    shutil.copyfile(SAMPLE_GOLDEN / "second" / "jd.json", cvt.out(run) / "jd.json")
    cvt("jd-check", run)
    packets["match"] = packet(cvt, "match", run)
    shutil.copyfile(SAMPLE_GOLDEN / "second" / "match.json", cvt.out(run) / "match.json")
    cvt("match-check", run)
    packets["questions"] = packet(cvt, "questions", run)
    shutil.copyfile(SAMPLE_GOLDEN / "second" / "questions.naive.json", cvt.out(run) / "questions.json")
    asked = cvt("questions", run, code=EXIT_AWAITING_USER).envelope["data"]

    # no pending question still offers a choice about a term an active attestation already covers
    questions = cvt.json(run, "questions.json")["questions"]
    pending = [q for q in questions if q["status"] == "pending"]
    assert pending and set(asked["pending"]) == {q["id"] for q in pending}
    for q in pending:
        for term in CANONICAL["second_run_must_not_ask_about"]:
            offered = [c for c in q["choices"] if term.lower() in _norm(c["label"] + " " + c["value"])]
            assert not offered, f"{q['id']} still offers a choice about {term!r}"
    # the suppressed choice is reported with the attestation that answered it
    assert [(row["question_id"], row["choice_id"]) for row in asked["suppressed"]] == [("q-1", "service_mesh")]
    assert "att-002" in asked["suppressed"][0]["reason"] and "Istio" in asked["suppressed"][0]["reason"]
    assert asked["suppressed"][0]["question_suppressed"] is False  # other gap choices keep the question alive

    cvt("answers-apply", run, "--auto", "--commit")
    packets["tailor"] = packet(cvt, "tailor", run)
    assert sum(p["est_tokens"] for p in packets.values()) <= SECOND_RUN_PACKET_BUDGET
    assert "profile" not in packets  # the cached profile saved the profile packet


def test_second_jd_prompts_do_not_mention_suppressed_terms(workspace: Path, cvt: Cvt, sample: Scenario) -> None:
    sample.restore("reported", cvt)
    run = _init(cvt, SECOND_JD, "golden-second")
    cvt("ingest", run)
    cvt("profile-cache", run, "--lookup")
    shutil.copyfile(SAMPLE_GOLDEN / "second" / "jd.json", cvt.out(run) / "jd.json")
    cvt("jd-check", run)
    shutil.copyfile(SAMPLE_GOLDEN / "second" / "match.json", cvt.out(run) / "match.json")
    cvt("match-check", run)
    shutil.copyfile(SAMPLE_GOLDEN / "second" / "questions.naive.json", cvt.out(run) / "questions.json")
    cvt("questions", run, code=EXIT_AWAITING_USER)
    for q in cvt.json(run, "questions.json")["questions"]:
        if q["status"] == "pending":
            for term in CANONICAL["second_run_must_not_ask_about"]:
                assert term.lower() not in _norm(q["prompt"]), (q["id"], term)


def test_same_jd_again_trims_the_oversized_seed(workspace: Path, cvt: Cvt, sample: Scenario) -> None:
    sample.restore("reported", cvt)
    run = _init(cvt, SAMPLE_JD, "golden-repeat")
    cvt("ingest", run)
    assert cvt("profile-cache", run, "--lookup").envelope["data"]["hit"] is True
    cached = cvt("brief", "jd", run).envelope["data"]
    assert cached["cache_hit"] is True and cached["cache_from"] == sample.run_slug  # same JD hash: no packet at all
    cvt("jd-check", run)
    shutil.copyfile(SAMPLE_GOLDEN / "match.json", cvt.out(run) / "match.json")
    cvt("match-check", run)
    shutil.copyfile(SAMPLE_GOLDEN / "questions.json", cvt.out(run) / "questions.json")
    cvt("questions", run, code=None)
    cvt("answers-apply", run, "--auto", "--commit")
    # similar-run score is 1.0 (>= seed_min_score 0.6), but the sample plan alone is ~5,400 tokens: with the seed the
    # packet exceeds the 8,000 budget, so build_brief trims the seed (interfaces.md 14.4) and the packet fits.
    data = packet(cvt, "tailor", run)
    assert SEED_MARKER not in data["packet"] and data["est_tokens"] <= data["budget"]
