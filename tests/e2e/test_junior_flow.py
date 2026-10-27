"""WP-25: the whole junior run through real `cvt` subprocesses, `init` -> `report`, as a host agent drives it.

The AI stages are played by the junior goldens (profile map, jd, match, questions, answers round, tailor plan, edits).
After every command the test asserts the exit code, `state.stage`, and that `next_action` names the next command.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from pypdf import PdfReader

from cvtlib import jsonio

from .conftest import (
    EXIT_AWAITING_USER, JUNIOR_CV, JUNIOR_GOLDEN, JUNIOR_JD, JUNIOR_PERSON, Cvt, Scenario, assert_next_action, packet,
)

JUNIOR_PAGE_TARGET = 1
SEED_MARKER = "# Seed (run "
HELM_REPLY = "I used Helm at Brightfield to package two internal services"
CHANGE_REPLY = "Say 'cutting' in the monitoring bullet and approve the rest."
REPORT_SECTIONS = (
    "## Coverage", "## Confirmed facts used", "## Remaining gaps", "## Source issues to confirm",
    "## Items to confirm", "## Recruiter asks", "## Interview talking points", "## What was left out",
    "## Defaults applied", "## Validation", "## Critique", "## Token usage",
)


def _step(cvt: Cvt, run: str, stage: str, *args: str, code: int = 0) -> dict:
    """Run one command, assert its exit code, the stage in the envelope and state.json, and the next_action."""
    env = cvt(*args, code=code).envelope
    assert env["exit_code"] == code
    assert env["stage"] == stage, f"{args[0]}: stage {env['stage']!r}, wanted {stage!r}"
    assert cvt.json(run, "state.json")["stage"] == stage
    if code == 0 and "--dry-run" not in args:
        assert_next_action(env, stage, run)
    # exit 6 and dry runs print their own payload and carry no next_action in the envelope, so ask `status`
    assert_next_action(cvt.status(run), stage, run)
    return env


def test_junior_run_init_to_report(workspace: Path, cvt: Cvt, agent_step) -> None:
    inputs = workspace / "inputs"
    inputs.mkdir()
    cv, jd = inputs / JUNIOR_CV.name, inputs / JUNIOR_JD.name
    shutil.copyfile(JUNIOR_CV, cv)
    shutil.copyfile(JUNIOR_JD, jd)
    packets: dict[str, dict] = {}

    init = cvt("init", "--cv", str(cv), "--jd", str(jd), "--slug", "golden-junior",
                "--page-target", str(JUNIOR_PAGE_TARGET)).envelope
    run = init["data"]["run_slug"]
    assert init["stage"] == "initialized" and (cvt.out(run) / "inputs").is_dir()
    assert_next_action(init, "initialized", run)

    _step(cvt, run, "ingested", "ingest", run)
    assert (cvt.out(run) / "cv.txt").is_file() and (cvt.out(run) / "jd.txt").is_file()

    hit = cvt("profile-cache", run, "--lookup").envelope
    assert hit["data"]["hit"] is False and hit["stage"] == "ingested"
    packets["profile"] = packet(cvt, "profile", run)
    agent_step(run, "profile-map.json", JUNIOR_GOLDEN / "profile-map.json")
    _step(cvt, run, "profiled", "profile-build", run)
    built, golden = cvt.json(run, "profile.json"), jsonio.load_json(JUNIOR_GOLDEN / "profile.json")
    volatile = ("created_at", "source_issues")  # the script adds its own issues (for example missing_contact)
    assert {k: v for k, v in built.items() if k not in volatile} == {k: v for k, v in golden.items() if k not in volatile}
    assert built["source_issues"][0] == golden["source_issues"][0]
    assert cvt("profile-cache", run, "--store").envelope["ok"] is True

    packets["jd"] = packet(cvt, "jd", run)
    agent_step(run, "jd.json", JUNIOR_GOLDEN / "jd.json")
    _step(cvt, run, "jd_analyzed", "jd-check", run)

    packets["match"] = packet(cvt, "match", run)
    agent_step(run, "match.json", JUNIOR_GOLDEN / "match.json")
    _step(cvt, run, "matched", "match-check", run)

    packets["questions"] = packet(cvt, "questions", run)
    agent_step(run, "questions.json", JUNIOR_GOLDEN / "questions.json")
    pending = _step(cvt, run, "awaiting_answers", "questions", run, code=EXIT_AWAITING_USER)
    assert pending["data"]["pending"] and cvt.json(run, "state.json")["pending"]["kind"] != "none"

    packets["answer_parse"] = packet(cvt, "answer_parse", run, "--reply", HELM_REPLY)
    round_file = agent_step(run, "answers.round.json", JUNIOR_GOLDEN / "answers.round.json")
    dry = _step(cvt, run, "awaiting_answers", "answers-apply", run, "--round", str(round_file), "--dry-run")
    assert dry["data"]["dry_run"] is True and not (cvt.out(run) / "answers.json").exists()
    store_file = workspace / "profiles" / JUNIOR_PERSON / "attestations.json"
    assert not store_file.exists() or not cvt.store(JUNIOR_PERSON)["attestations"]  # a dry run stores nothing
    _step(cvt, run, "answers_applied", "answers-apply", run, "--round", str(round_file), "--commit")
    store = cvt.store(JUNIOR_PERSON)["attestations"]
    assert [(a["id"], a["claim"], a["status"]) for a in store] == [("att-001", "Helm", "proposed")]

    packets["tailor"] = packet(cvt, "tailor", run)
    agent_step(run, "tailor-plan.json", JUNIOR_GOLDEN / "tailor-plan.json")
    _step(cvt, run, "tailored", "assemble", run)
    assert cvt.json(run, "tailored.json")["version"] == 1

    _step(cvt, run, "awaiting_approval", "diff", run)
    packets["change_request"] = packet(cvt, "change_request", run, "--reply", CHANGE_REPLY)
    applied = cvt("apply-edits", run, str(JUNIOR_GOLDEN / "edits-001.json")).envelope
    assert applied["stage"] == "approved"  # the batch ends with approve_all and nothing is left pending
    _step(cvt, run, "approved", "approve", run)
    assert [a["status"] for a in cvt.store(JUNIOR_PERSON)["attestations"]] == ["active"]

    _step(cvt, run, "rendered", "fit", run)
    assert cvt.json(run, "fit.json")["pages"] <= JUNIOR_PAGE_TARGET
    _step(cvt, run, "validated", "validate", run)
    packets["critic"] = packet(cvt, "critic", run)
    _step(cvt, run, "reported", "report", run)

    finals = sorted((cvt.out(run) / "final").glob("*.pdf"))
    assert len(finals) == 1
    assert 1 <= len(PdfReader(str(finals[0])).pages) <= JUNIOR_PAGE_TARGET
    validation = cvt.json(run, "validation.json")
    assert validation["gates"] and all(g["status"] == "pass" for g in validation["gates"]), validation["gates"]
    report_text = (cvt.out(run) / "report.md").read_text(encoding="utf-8")
    for heading in REPORT_SECTIONS:
        assert heading in report_text, heading
    assert report_text.index(REPORT_SECTIONS[0]) < report_text.index(REPORT_SECTIONS[-1])

    # every packet built above fits its budget and was logged once
    assert set(packets) == {"profile", "jd", "match", "questions", "answer_parse", "tailor", "change_request", "critic"}
    assert all(p["est_tokens"] <= p["budget"] for p in packets.values())
    usage_lines = (cvt.out(run) / "usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(usage_lines) == len(packets)
    final_state = cvt.json(run, "state.json")
    assert final_state["checkpoints"] == {"cp1": "done", "cp2": "done"}
    assert final_state["attestations_used"] == ["att-001"]


def test_repeat_jd_reuses_cache_and_offers_a_seed(workspace: Path, cvt: Cvt, junior: Scenario) -> None:
    """A new run on the same CV and JD: profile cache hit, cached jd.json (no jd packet), and the approved run as seed."""
    junior.restore("reported", cvt)
    inputs = workspace / "inputs"
    run = cvt("init", "--cv", str(inputs / JUNIOR_CV.name), "--jd", str(inputs / JUNIOR_JD.name), "--slug", "repeat",
              "--page-target", str(JUNIOR_PAGE_TARGET)).envelope["data"]["run_slug"]
    assert run != junior.run_slug
    cvt("ingest", run)
    hit = cvt("profile-cache", run, "--lookup").envelope
    assert hit["data"]["hit"] is True and hit["stage"] == "profiled"
    cached = cvt("brief", "jd", run).envelope["data"]
    assert cached["cache_hit"] is True and cached["cache_from"] == junior.run_slug
    assert cvt("jd-check", run).envelope["stage"] == "jd_analyzed"
    shutil.copyfile(JUNIOR_GOLDEN / "match.json", cvt.out(run) / "match.json")
    cvt("match-check", run)
    shutil.copyfile(JUNIOR_GOLDEN / "questions.json", cvt.out(run) / "questions.json")
    cvt("questions", run, code=None)
    cvt("answers-apply", run, "--auto", "--commit")
    data = packet(cvt, "tailor", run)
    assert f"{SEED_MARKER}{junior.run_slug})" in data["packet"]  # similar-run score 1.0 >= seed_min_score 0.6
    assert f'set seed_run to "{junior.run_slug}"' in data["packet"]
