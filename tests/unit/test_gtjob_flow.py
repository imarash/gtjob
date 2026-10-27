"""WP-22: `gtjob.flow` stage loop, `answers_yaml`, and `interact`, driven by a fake runner and the junior goldens."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import REPO_ROOT
from cvtlib import jsonio, state, usage
from gtjob import answers_yaml, flow, interact

FIXTURES = REPO_ROOT / "tests" / "fixtures"
GOLDEN = FIXTURES / "golden" / "junior"
CV_FIXTURE = FIXTURES / "cv" / "jamie-rivera-junior.txt"
JD_FIXTURE = FIXTURES / "jds" / "junior-devops-engineer.md"
OPTIONS = {"template": "modern", "auto": False, "draft": False, "page_target": 2, "paper": "us-letter"}
EXIT_OK, EXIT_CHECK_FAILED, EXIT_USAGE, EXIT_AWAITING = 0, 1, 2, 6
HELM_REPLY = "I used Helm at Brightfield to package two internal services"
HELM_CP1 = f'checkpoint1:\n  q-1: "{HELM_REPLY}"\nfollowups: default\n'  # the golden round asks one scope follow-up
REJECTED_ITEM = "t-exp-1.b2"
STAGE_FILES = {
    "profile": "profile-map.json", "jd": "jd.json", "match": "match.json", "questions": "questions.json",
    "tailor": "tailor-plan.json",
}


@pytest.fixture(autouse=True)
def _restore_host_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """`gtjob.cli.main` sets GTJOB_HOST; make monkeypatch undo it after each test."""
    monkeypatch.setenv("GTJOB_HOST", "placeholder")
    monkeypatch.delenv("GTJOB_HOST")


def plan_variant(kind: str) -> dict:
    """The golden tailor plan: `full` (with the Helm bullet), `skills_only` (Helm skill, no bullet), or `none` (no Helm)."""
    plan = jsonio.load_json(GOLDEN / "tailor-plan.json")
    if kind == "full":
        return plan
    for entry in plan["experience"]:
        entry["bullets"] = [b for b in entry["bullets"] if b["op"] != "attested"]
    plan["talking_points"] = [t for t in plan["talking_points"] if "att-001" not in t["source_refs"]]
    if kind == "none":
        for group in plan["skills"]:
            group["items"] = [i for i in group["items"] if i["name"] != "Helm"]
    return plan


class FakeRunner:
    """Plays the AI stages with golden files. Unchecked by default; `checked=True` also runs the profile check."""

    def __init__(self, *, plan: str = "full", leave_pending: bool = False, checked: bool = False,
                 api_usage: bool = False) -> None:
        self.plan, self.leave_pending, self.checked, self.api_usage = plan, leave_pending, checked, api_usage
        self.calls: list[tuple[str, dict | None, bool]] = []

    def stages(self) -> list[str]:
        return [c[0] for c in self.calls]

    def run_stage(self, stage: str, run_dir: Path, *, extra: dict | None = None, interactive: bool = False) -> Path:
        self.calls.append((stage, extra, interactive))
        if self.api_usage:
            usage.record_usage(run_dir, {"stage": stage, "kind": "api", "model": "claude-fake-1", "est_tokens": 0,
                                         "input_tokens": 100, "cache_read_tokens": 50, "cache_write_tokens": 0,
                                         "output_tokens": 20, "attempt": 1})
        if stage in STAGE_FILES and stage != "tailor":
            dest = run_dir / STAGE_FILES[stage]
            shutil.copyfile(GOLDEN / STAGE_FILES[stage], dest)
            if stage == "profile" and self.checked:
                flow.run_cvt(["profile-build", run_dir.name])
            return dest
        if stage == "tailor":
            dest = run_dir / STAGE_FILES[stage]
            jsonio.dump_json(plan_variant(self.plan), dest)
            return dest
        if stage == "answer_parse":
            round_obj = jsonio.load_json(GOLDEN / "answers.round.json")
            if self.leave_pending:
                round_obj["unmentioned_question_ids"] = []
            dest = run_dir / "answers.round.json"
            jsonio.dump_json(round_obj, dest)
            return dest
        if stage == "change_request":
            dest = run_dir / "edits" / "next.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(GOLDEN / "edits-001.json", dest)
            return dest
        raise AssertionError(f"unexpected stage {stage}")


def new_run() -> Path:
    return state.create_run(CV_FIXTURE, "file", str(JD_FIXTURE), None, dict(OPTIONS))


def drive(run: Path, runner: FakeRunner, io: interact.ScriptedIO, **kwargs) -> int:
    return flow.drive(run, runner=runner, io=io, **kwargs)


def history_events(run: Path) -> list[str]:
    return [h["event"] for h in state.load(run)["history"]]


# --- answers_yaml ---------------------------------------------------------------------------------------------
def test_yaml_parses_choices_text_and_default_rest() -> None:
    spec = answers_yaml.parse(
        'checkpoint1:\n  q-1: [helm]\n  q-2: "about 12 incidents a month"\n  q-3: []\n  default_rest: true\n'
        "followups: default\ncheckpoint2:\n  - drop the earlier role\n",
    )
    cp1 = spec.checkpoint1
    assert cp1.choices == {"q-1": ["helm"], "q-3": []} and cp1.texts == {"q-2": "about 12 incidents a month"}
    assert cp1.default_rest and spec.followups.default_rest
    assert spec.checkpoint2.instructions == ("drop the earlier role",) and not spec.checkpoint2.approve_all
    assert answers_yaml.free_text_reply(cp1) == "q-2: about 12 incidents a month"
    assert answers_yaml.parse("checkpoint2: approve_all").checkpoint2.approve_all


@pytest.mark.parametrize("text", [
    "checkpoint1: [unclosed", "", "- a\n- b", "bogus: 1", "checkpoint1:\n  not-a-question: [x]",
    "checkpoint1:\n  q-1: 5", "checkpoint1:\n  q-1: [true]", "checkpoint1:\n  default_rest: maybe", "checkpoint2: 7",
    "checkpoint2: []",
])
def test_yaml_rejects_bad_input_with_usage_error(text: str) -> None:
    with pytest.raises(Exception) as caught:
        answers_yaml.parse(text)
    assert int(caught.value.code) == EXIT_USAGE and caught.value.hint


def test_yaml_unknown_question_ids_are_usage_errors() -> None:
    section = answers_yaml.parse("checkpoint1:\n  q-9: [x]").checkpoint1
    with pytest.raises(Exception) as caught:
        answers_yaml.check_question_ids(section, {"q-1", "q-2"})
    assert int(caught.value.code) == EXIT_USAGE and "q-9" in caught.value.message


# --- interact ---------------------------------------------------------------------------------------------------
GAP_Q = {"id": "q-1", "topic": "gap", "type": "multi_select", "prompt": "Which?",
         "choices": [{"id": "helm", "label": "Helm"}, {"id": "python", "label": "Python"}, {"id": "ts", "label": "TS"}],
         "default": {"text": "Keep as gaps", "description": "Keep as gaps; nothing is added."}}
SINGLE_Q = {**GAP_Q, "id": "q-3", "topic": "strategy", "type": "single_select"}
FREE_Q = {**GAP_Q, "id": "q-2", "topic": "metric", "type": "free_text", "choices": []}


@pytest.mark.parametrize(("text", "expected"), [
    ("1,3", ["helm", "ts"]), ("2", ["python"]), ("a", ["helm"]), ("a c", ["helm", "ts"]), ("helm", ["helm"]),
    ("1, helm", ["helm"]), ("add service mesh", None), ("I used it daily", None),
])
def test_parse_selection(text: str, expected: list[str] | None) -> None:
    assert interact.parse_selection(GAP_Q, text) == expected


def test_parse_selection_rules() -> None:
    assert interact.parse_selection(FREE_Q, "40") is None  # no choices: a number is text
    with pytest.raises(ValueError, match="no choice"):
        interact.parse_selection(GAP_Q, "9")
    with pytest.raises(ValueError, match="one choice"):
        interact.parse_selection(SINGLE_Q, "1,2")


def test_format_question_is_two_lines_with_numbered_choices_and_default() -> None:
    lines = interact.format_question(GAP_Q)
    assert len(lines) == 2 and "1) Helm" in lines[1] and "3) TS" in lines[1] and "default: Keep as gaps" in lines[1]


def test_prompt_questions_collects_choices_text_skip_and_quit() -> None:
    io = interact.ScriptedIO(["1,2", "about 12 a month", "skip"])
    got = interact.prompt_questions(io, [GAP_Q, FREE_Q, SINGLE_Q])
    assert got.choices == {"q-1": ["helm", "python"], "q-3": []} and got.texts == {"q-2": "about 12 a month"}
    io = interact.ScriptedIO(["9", "", ""])
    got = interact.prompt_questions(io, [GAP_Q, FREE_Q])  # bad number is re-asked, blanks take defaults
    assert got.choices == {} and got.texts == {} and io.errors
    assert interact.prompt_questions(interact.ScriptedIO(["q"]), [GAP_Q]) is None
    assert interact.prompt_questions(interact.ScriptedIO([]), [GAP_Q]) is None


@pytest.mark.parametrize(("text", "kind", "n", "rest"), [
    ("a", "approve", 0, ""), ("done", "approve", 0, ""), ("r 2", "reject", 2, ""), ("e 3 Led a team", "edit", 3, "Led a team"),
    ("d", "full", 0, ""), ("q", "quit", 0, ""), ("", "help", 0, ""), ("?", "help", 0, ""), ("r", "bad", 0, ""),
    ("e 2", "bad", 0, ""), ("say cutting in the monitoring bullet", "change", 0, "say cutting in the monitoring bullet"),
    ("a bullet about Terraform", "change", 0, "a bullet about Terraform"),
])
def test_parse_review(text: str, kind: str, n: int, rest: str) -> None:
    cmd = interact.parse_review(text)
    assert (cmd.kind, cmd.n) == (kind, n)
    if rest:
        assert cmd.text == rest


def test_terminal_io_without_tty_never_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    class _NoTty:
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr("sys.stdin", _NoTty())
    terminal = interact.TerminalIO()
    assert not terminal.interactive and terminal.ask("> ") is None and terminal.confirm("ok?") is True


# --- flow --------------------------------------------------------------------------------------------------------
def test_usage_table_lists_stages_models_and_total(workspace: Path) -> None:
    run = new_run()
    assert flow.usage_table(run) == []
    for stage, tokens in (("tailor", 1000), ("jd", 10)):
        usage.record_usage(run, {"stage": stage, "kind": "api", "model": f"m-{stage}", "est_tokens": 0,
                                 "input_tokens": tokens, "cache_read_tokens": 5, "cache_write_tokens": 0,
                                 "output_tokens": 2, "attempt": 1})
    table = flow.usage_table(run)
    assert table[0].split() == ["stage", "model", "input", "cache", "read", "output"]
    assert "m-tailor" in table[2] and "1,000" in table[2]
    assert table[-1].split() == ["total", "1,010", "10", "4"]


def test_full_run_with_answers_yaml_reaches_reported(workspace: Path) -> None:
    """Free text goes through answer_parse, choice ids through --select, the rest default; checkpoint 2 approves all."""
    spec = answers_yaml.parse(
        'checkpoint1:\n  q-1: "I used Helm at Brightfield to package two internal services"\n'
        "  q-3: [classic]\n  default_rest: true\nfollowups: default\ncheckpoint2: approve_all\n",
    )
    run, runner, io = new_run(), FakeRunner(leave_pending=True), interact.ScriptedIO(interactive=False)
    assert drive(run, runner, io, answers=spec) == EXIT_OK
    st = state.load(run)
    assert st["stage"] == "reported" and st["checkpoints"] == {"cp1": "done", "cp2": "done"}
    assert runner.stages() == ["profile", "jd", "match", "questions", "answer_parse", "tailor"]
    assert runner.calls[4][1] == {"reply": "q-1: I used Helm at Brightfield to package two internal services"}
    rounds = jsonio.load_json(run / "answers.json")["rounds"]
    assert [r["channel"] for r in rounds] == ["chat", "host_tool", "host_tool"]  # text, choices, follow-up defaults
    questions = {q["id"]: q["status"] for q in jsonio.load_json(run / "questions.json")["questions"]}
    assert questions == {"q-1": "answered", "q-2": "defaulted", "q-3": "answered", "q-4": "defaulted"}  # q-4: scope follow-up
    assert list((run / "final").glob("*.pdf")) and (run / "report.md").is_file()
    assert "report:" in io.output


def test_auto_defaults_everything_and_attests_nothing(workspace: Path) -> None:
    run = state.create_run(CV_FIXTURE, "file", str(JD_FIXTURE), None, {**OPTIONS, "auto": True})
    runner, io = FakeRunner(plan="none"), interact.ScriptedIO(interactive=False)
    assert drive(run, runner, io, auto=True) == EXIT_OK
    assert "answer_parse" not in runner.stages() and "change_request" not in runner.stages()
    answers = jsonio.load_json(run / "answers.json")
    assert [r["channel"] for r in answers["rounds"]] == ["auto"]
    assert {q["status"] for q in jsonio.load_json(run / "questions.json")["questions"]} == {"defaulted"}
    assert not (workspace / "profiles" / "jamie-rivera" / "attestations.json").is_file() or not jsonio.load_json(
        workspace / "profiles" / "jamie-rivera" / "attestations.json")["attestations"]
    assert state.load(run)["stage"] == "reported" and not state.load(run)["attestations_used"]


def test_auto_flag_sticks_in_state_when_run_was_not_created_auto(workspace: Path) -> None:
    run = new_run()
    assert drive(run, FakeRunner(plan="none"), interact.ScriptedIO(interactive=False), auto=True) == EXIT_OK
    assert state.load(run)["options"]["auto"] is True


def test_non_tty_stops_at_checkpoint_1_with_questions_printed(workspace: Path) -> None:
    run, runner, io = new_run(), FakeRunner(), interact.ScriptedIO(interactive=False)
    assert drive(run, runner, io) == EXIT_AWAITING
    st = state.load(run)
    assert st["stage"] == "awaiting_answers" and st["status"] == "awaiting_user"
    assert "Which of these requirements" in io.output and "gtjob continue" in io.output and not io.prompts
    assert runner.stages() == ["profile", "jd", "match", "questions"]


def test_reply_resumes_checkpoint_1_then_stops_at_checkpoint_2(workspace: Path) -> None:
    run, runner = new_run(), FakeRunner()
    assert drive(run, runner, interact.ScriptedIO(interactive=False)) == EXIT_AWAITING
    io = interact.ScriptedIO(interactive=False)
    assert drive(run, runner, io, reply=HELM_REPLY) == EXIT_AWAITING  # the Helm scope follow-up is still open
    st = state.load(run)
    assert st["stage"] == "awaiting_answers" and st["pending"]["kind"] == "followups" and "Helm" in io.output
    io = interact.ScriptedIO(interactive=False)
    assert drive(run, runner, io, answers=answers_yaml.parse("followups: default")) == EXIT_AWAITING
    assert state.load(run)["stage"] == "awaiting_approval"
    assert "answer_parse" in runner.stages() and runner.stages()[-1] == "tailor"
    assert "Helm" in io.output and "request changes with" in io.output
    io = interact.ScriptedIO(interactive=False)
    assert drive(run, runner, io, reply="Say 'cutting' in the monitoring bullet and approve the rest.") == EXIT_OK
    assert state.load(run)["stage"] == "reported" and runner.stages()[-1] == "change_request"


def test_cross_host_run_left_by_an_ide_agent_resumes(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An IDE agent ran `questions` and ended its turn; `drive` takes over from state.json alone."""
    monkeypatch.setenv("GTJOB_HOST", "cursor")
    run = new_run()
    for cmd in (["ingest", run.name], ["profile-build", run.name], ["jd-check", run.name], ["match-check", run.name]):
        if cmd[0] == "profile-build":
            shutil.copyfile(GOLDEN / "profile-map.json", run / "profile-map.json")
        if cmd[0] == "jd-check":
            shutil.copyfile(GOLDEN / "jd.json", run / "jd.json")
        if cmd[0] == "match-check":
            shutil.copyfile(GOLDEN / "match.json", run / "match.json")
        assert flow.run_cvt(cmd).code == EXIT_OK
    shutil.copyfile(GOLDEN / "questions.json", run / "questions.json")
    assert flow.run_cvt(["questions", run.name]).code == EXIT_AWAITING
    assert state.load(run)["stage"] == "awaiting_answers"

    monkeypatch.setenv("GTJOB_HOST", "cli")
    runner, io = FakeRunner(), interact.ScriptedIO(interactive=False)
    assert drive(run, runner, io, reply=HELM_REPLY) == EXIT_AWAITING  # stops at the scope follow-up
    assert runner.stages()[:1] == ["answer_parse"]  # nothing before checkpoint 1 was redone
    hosts = {h["host"] for h in state.load(run)["history"]}
    assert {"cursor", "cli"} <= hosts


def test_checked_runner_that_already_advanced_the_stage_is_not_checked_twice(workspace: Path) -> None:
    run, runner = new_run(), FakeRunner(checked=True)
    assert drive(run, runner, interact.ScriptedIO(interactive=False)) == EXIT_AWAITING
    assert history_events(run).count("profile-build") == 1


def test_interactive_prompts_at_both_checkpoints_and_review_loop_reject_then_approve(workspace: Path) -> None:
    """Checkpoint 1: choose Helm (1), default q-2, pick the classic template (2). Checkpoint 2: `r N` then `a`."""
    run = new_run()

    def reject_input() -> str:
        items = flow.run_cvt(["diff", run.name, "--full"]).data["items"]
        return f"r {next(i['n'] for i in items if i['id'] == REJECTED_ITEM)}"

    io = interact.ScriptedIO(["1", "", "2", reject_input, "a"])
    runner = FakeRunner(plan="skills_only")
    assert drive(run, runner, io) == EXIT_OK
    assert all(interactive for _, _, interactive in runner.calls)  # 1-hour cache TTL path
    assert "answer_parse" not in runner.stages() and "change_request" not in runner.stages()
    st = state.load(run)
    assert st["stage"] == "reported"
    batch = jsonio.load_json(run / "edits" / "001.json")
    assert batch["source"] == "cli" and [(o["op"], o["target_id"]) for o in batch["ops"]] == [("reject", REJECTED_ITEM)]
    tailored = jsonio.load_json(run / "tailored.json")
    assert tailored["version"] == 2
    assert "Replaced manual console changes" not in json.dumps(tailored["experience"])
    rounds = jsonio.load_json(run / "answers.json")["rounds"]
    assert [r["channel"] for r in rounds] == ["host_tool"]
    assert "[q-1] gap:" in io.output and "1) Helm" in io.output


def test_review_edit_command_replaces_text_with_item_refs(workspace: Path) -> None:
    run = new_run()
    spec = answers_yaml.parse("checkpoint1: default")

    def edit_input() -> str:
        items = flow.run_cvt(["diff", run.name, "--full"]).data["items"]
        number = next(i["n"] for i in items if i["id"] == "t-exp-1.b4")
        return f"e {number} Built Prometheus and Grafana dashboards and alerts for incident detection."

    io = interact.ScriptedIO([edit_input, "a"])
    assert drive(run, FakeRunner(plan="none"), io, answers=spec) == EXIT_OK
    op = jsonio.load_json(run / "edits" / "001.json")["ops"][0]
    assert op["op"] == "replace_text" and op["target_id"] == "t-exp-1.b4" and op["source_refs"]
    assert "incident detection" in json.dumps(jsonio.load_json(run / "tailored.json")["experience"])


def test_review_free_text_goes_through_change_request_and_bad_commands_reprompt(workspace: Path) -> None:
    run = new_run()
    spec = answers_yaml.parse("checkpoint1: default")
    io = interact.ScriptedIO(["r", "r 99", "?", "d", "Say 'cutting' in the monitoring bullet"])
    runner = FakeRunner(plan="full")
    # the golden edits batch needs the Helm bullet present, so answer checkpoint 1 with free text instead
    assert drive(run, runner, io, answers=answers_yaml.parse(HELM_CP1)) == EXIT_OK
    assert "needs an item number" in "\n".join(io.errors) and "no item 99" in "\n".join(io.errors)
    assert runner.stages()[-1] == "change_request" and spec  # edits-001 ends with approve_all: no `a` needed
    assert state.load(run)["stage"] == "reported"


def test_review_quit_saves_state_and_exits_6(workspace: Path) -> None:
    run = new_run()
    io = interact.ScriptedIO(["q"])
    assert drive(run, FakeRunner(plan="none"), io, answers=answers_yaml.parse("checkpoint1: default")) == EXIT_AWAITING
    assert state.load(run)["stage"] == "awaiting_approval" and "gtjob continue" in io.output


def test_checkpoint_1_quit_saves_state(workspace: Path) -> None:
    run = new_run()
    assert drive(run, FakeRunner(), interact.ScriptedIO(["q"])) == EXIT_AWAITING
    assert state.load(run)["stage"] == "awaiting_answers"


def test_yaml_unknown_question_id_exits_2_before_applying(workspace: Path) -> None:
    run = new_run()
    spec = answers_yaml.parse("checkpoint1:\n  q-9: [helm]\n")
    io = interact.ScriptedIO(interactive=False)
    assert drive(run, FakeRunner(), io, answers=spec) == EXIT_USAGE
    assert state.load(run)["stage"] == "awaiting_answers" and "E_ANSWERS_UNKNOWN_QUESTION" in "\n".join(io.errors)


def test_yaml_instructions_at_checkpoint_2_are_applied_then_approved(workspace: Path) -> None:
    run = new_run()
    spec = answers_yaml.parse(
        HELM_CP1 + "checkpoint2:\n  - Say cutting in the monitoring bullet\n")
    runner = FakeRunner()
    assert drive(run, runner, interact.ScriptedIO(interactive=False), answers=spec) == EXIT_OK
    assert runner.stages().count("change_request") == 1 and state.load(run)["stage"] == "reported"


def test_edit_after_report_reenters_checkpoint_2(workspace: Path) -> None:
    run = new_run()
    spec = answers_yaml.parse(HELM_CP1 + "checkpoint2: approve_all\n")
    runner = FakeRunner()
    assert drive(run, runner, interact.ScriptedIO(interactive=False), answers=spec) == EXIT_OK
    version = jsonio.load_json(run / "tailored.json")["version"]
    io = interact.ScriptedIO(interactive=False)
    assert drive(run, runner, io, reply="Say 'cutting' in the monitoring bullet") == EXIT_OK
    assert jsonio.load_json(run / "tailored.json")["version"] == version + 1
    assert runner.stages()[-1] == "change_request" and state.load(run)["stage"] == "reported"


def test_reply_that_no_checkpoint_consumes_is_reported(workspace: Path) -> None:
    run = new_run()
    spec = answers_yaml.parse(HELM_CP1 + "checkpoint2: approve_all\n")
    assert drive(run, FakeRunner(), interact.ScriptedIO(interactive=False), answers=spec) == EXIT_OK
    io = interact.ScriptedIO(interactive=False)
    state.save(run, {**state.load(run), "stage": "ingested"})  # a run that still has to profile: no checkpoint is pending
    runner = FakeRunner()
    drive(run, runner, io, reply="hello", answers=spec)
    assert "answer_parse" in runner.stages() or "note: --text was not used" in io.output


def test_format_error_lists_hint_and_violations() -> None:
    assert flow.format_error("E_X", "m", "h", [{"item_id": "a", "message": "b"}]).splitlines() == [
        "cvt: error[E_X]: m", "  hint: h", "  - a: b"]


def test_token_table_is_printed_at_the_end(workspace: Path) -> None:
    run = new_run()
    io = interact.ScriptedIO(interactive=False)
    assert drive(run, FakeRunner(api_usage=True), io) == EXIT_AWAITING  # a stop prints the table too
    assert "claude-fake-1" in io.output and "total" in io.output


def test_cvt_failure_prints_error_and_hint_and_returns_its_code(workspace: Path) -> None:
    run = new_run()
    (run / "inputs" / "jd.md").unlink()  # ingest cannot proceed
    io = interact.ScriptedIO(interactive=False)
    code = drive(run, FakeRunner(), io)
    assert code != EXIT_OK and "cvt: error[" in "\n".join(io.errors)
