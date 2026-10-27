"""WP-25: resume from any stage. The contract that `/cv-continue`, natural-language replies, and `gtjob continue` rely on.

For every stage in the stage table a run stopped at that stage is restored from a real build. `cvt status --json` must
name the next command; executing that command (after the golden AI artifact when the action says "write X") must make
progress. Also: `status --all` ordering, `latest` resolution, and staleness after editing `profile.json`.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from cvtlib import jsonio

from .conftest import EXIT_AWAITING_USER, EXIT_STATE, NEXT_ACTION_NAMES, STAGES, Cvt, Scenario, stage_index

CLOCK_TICK_SECONDS = 1.1  # `updated_at` has one-second resolution
CVT_COMMAND_RE = re.compile(r"cvt\.py ([a-z][a-z-]*)")
STALE_AFTER_PROFILE_EDIT = {"jd", "match", "answers", "questions", "tailor_plan", "tailored"}


@dataclass(frozen=True)
class Step:
    """What a host agent does at one stage: write an AI artifact (optional), then run one command."""

    artifact: str  # file the AI stage writes under out/<run>/ ("" = none)
    source: str  # key into Scenario.files
    args: tuple[str, ...]  # `{run}` and `{artifact}` are substituted
    code: int
    expected_stage: str


RESUME: dict[str, Step] = {
    "initialized": Step("", "", ("ingest", "{run}"), 0, "ingested"),
    "ingested": Step("profile-map.json", "profile-map", ("profile-build", "{run}"), 0, "profiled"),
    "profiled": Step("jd.json", "jd", ("jd-check", "{run}"), 0, "jd_analyzed"),
    "jd_analyzed": Step("match.json", "match", ("match-check", "{run}"), 0, "matched"),
    "matched": Step("questions.json", "questions", ("questions", "{run}"), EXIT_AWAITING_USER, "awaiting_answers"),
    "awaiting_answers": Step("answers.round.json", "round",
                             ("answers-apply", "{run}", "--round", "{artifact}", "--commit"), 0, "answers_applied"),
    "answers_applied": Step("tailor-plan.json", "tailor-plan", ("assemble", "{run}"), 0, "tailored"),
    "tailored": Step("", "", ("diff", "{run}"), 0, "awaiting_approval"),
    "awaiting_approval": Step("edits/next.json", "edits", ("apply-edits", "{run}", "{artifact}"), 0, "approved"),
    "approved": Step("", "", ("fit", "{run}"), 0, "rendered"),
    "rendered": Step("", "", ("validate", "{run}"), 0, "validated"),
    "validated": Step("", "", ("report", "{run}"), 0, "reported"),
}


def test_every_stage_has_a_resume_step() -> None:
    assert tuple(RESUME) + ("reported",) == tuple(STAGES), "the stage table changed: update RESUME"
    assert set(NEXT_ACTION_NAMES) == set(STAGES)


@pytest.fixture(params=["junior", "sample"])
def scenario(request: pytest.FixtureRequest) -> Scenario:
    return request.getfixturevalue(request.param)


@pytest.mark.parametrize("stage", list(RESUME))
def test_resume_from_stage(stage: str, workspace: Path, cvt: Cvt, scenario: Scenario) -> None:
    run = scenario.restore(stage, cvt)
    step = RESUME[stage]

    status = cvt("status", run).envelope  # what `/cv-continue` reads first
    assert status["stage"] == stage and status["data"]["state"]["stage"] == stage
    action = status["next_action"]
    assert NEXT_ACTION_NAMES[stage] in action and run in action, action
    named = set(CVT_COMMAND_RE.findall(action))
    assert step.args[0] in named, f"{stage}: next_action does not name {step.args[0]}: {action}"
    for command in named:  # every command the action names exists
        assert cvt.raw(command, "--help").returncode == 0, command
    assert (status["data"]["state"]["status"] == "awaiting_user") == (stage in {"awaiting_answers", "awaiting_approval"})

    path = ""
    if step.artifact:  # "write X": the host agent's AI stage
        dest = cvt.out(run) / step.artifact
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(scenario.files[step.source].read_bytes())
        path = str(dest)
    args = tuple(a.format(run=run, artifact=path) for a in step.args)
    done = cvt(*args, code=step.code).envelope
    assert done["stage"] == step.expected_stage and stage_index(step.expected_stage) > stage_index(stage)
    after = cvt.status(run)
    assert after["stage"] == step.expected_stage
    assert after["next_action"], "progress always leaves a next action"
    if stage == "validated":  # the last executable step: `reported` says it is done
        assert "Done." in after["next_action"] and (cvt.out(run) / "report.md").is_file()


def test_reported_run_is_done_and_new_runs_start_clean(workspace: Path, cvt: Cvt, scenario: Scenario) -> None:
    run = scenario.restore("reported", cvt)
    status = cvt("status", run).envelope
    assert status["stage"] == "reported" and "Done." in status["next_action"]
    assert status["data"]["state"]["checkpoints"] == {"cp1": "done", "cp2": "done"}


def test_status_all_orders_runs_newest_first_and_latest_follows_activity(
    workspace: Path, cvt: Cvt, junior: Scenario,
) -> None:
    oldest = junior.restore("reported", cvt)
    inputs = workspace / "inputs"
    cv, jd = inputs / junior.cv.name, inputs / junior.jd.name
    slugs = [oldest]
    for name in ("second", "third"):
        time.sleep(CLOCK_TICK_SECONDS)
        slugs.append(cvt("init", "--cv", str(cv), "--jd", str(jd), "--slug", name).envelope["data"]["run_slug"])
    listed = cvt("status", slugs[-1], "--all").envelope["data"]["runs"]
    assert [r["run_slug"] for r in listed] == list(reversed(slugs))
    assert {r["run_slug"]: r["stage"] for r in listed} == {slugs[0]: "reported", slugs[1]: "initialized", slugs[2]: "initialized"}
    assert [r["updated_at"] for r in listed] == sorted((r["updated_at"] for r in listed), reverse=True)
    assert cvt("status", "latest").envelope["run"] == slugs[2]

    time.sleep(CLOCK_TICK_SECONDS)  # work on an older run makes it the latest
    cvt("ingest", slugs[1])
    assert cvt("status", "latest").envelope["run"] == slugs[1]
    assert cvt("status", "--all").envelope["data"]["runs"][0]["run_slug"] == slugs[1]
    assert cvt("status", code=None).envelope["run"] == slugs[1]  # RUN defaults to latest
    missing = cvt("status", "20200101-nothing", code=EXIT_STATE).envelope
    assert missing["error"]["id"] == "E_RUN_NOT_FOUND" and missing["error"]["hint"]


def test_editing_profile_marks_downstream_artifacts_stale(workspace: Path, cvt: Cvt, junior: Scenario) -> None:
    run = junior.restore("tailored", cvt)
    state = cvt.status(run)["data"]["state"]
    assert not [a["name"] for a in state["artifacts"] if a["stale"]]

    profile = cvt.json(run, "profile.json")
    profile["source_issues"][0]["message"] += " (edited by hand)"
    jsonio.dump_json(profile, cvt.out(run) / "profile.json")
    verified = cvt("profile-verify", run).envelope
    assert verified["stage"] == "profiled"

    status = cvt("status", run).envelope
    stale = {a["name"] for a in status["data"]["state"]["artifacts"] if a["stale"]}
    assert {"match", "questions", "tailored"} <= stale and stale == STALE_AFTER_PROFILE_EDIT
    human = next(ln for ln in cvt.raw("status", run).stdout.splitlines() if ln.startswith("stale:"))
    assert set(human.removeprefix("stale:").replace(" ", "").split(",")) == STALE_AFTER_PROFILE_EDIT
    assert status["stage"] == "profiled" and "brief jd" in status["next_action"]  # re-enter after the profile

    # stale artifacts are refused, with an actionable error, until their stage is redone
    blocked = cvt("diff", run, code=EXIT_STATE).envelope
    assert blocked["ok"] is False and blocked["error"]["id"] and blocked["error"]["hint"]
