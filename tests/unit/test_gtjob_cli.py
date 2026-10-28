"""WP-22: the `gtjob` command line (`gtjob.cli.main`) with a fake runner and scripted terminal."""

from __future__ import annotations

from pathlib import Path

import pytest

from cvtlib import jsonio, state
from gtjob import cli, interact
from test_gtjob_flow import (
    CV_FIXTURE, JD_FIXTURE, FakeRunner, HELM_REPLY, EXIT_AWAITING, EXIT_OK, EXIT_USAGE, _restore_host_env,  # noqa: F401
)

EXIT_MISSING_DEPENDENCY = 3
COMMANDS = ("tailor", "continue", "status", "render", "polish", "edit", "profile", "package-skill")
TAILOR = ["tailor", "--cv", str(CV_FIXTURE), "--jd", str(JD_FIXTURE)]
ANSWERS_YAML = (
    'checkpoint1:\n  q-1: "I used Helm at Brightfield to package two internal services"\n'
    "  q-3: [classic]\n  default_rest: true\nfollowups: default\ncheckpoint2: approve_all\n"
)


def run_main(argv: list[str], runner: FakeRunner | None = None, *, tty: bool = False,
             inputs: list | None = None) -> tuple[int, interact.ScriptedIO]:
    io = interact.ScriptedIO(inputs=list(inputs or []), interactive=tty)
    return cli.main(argv, runner=runner or FakeRunner(), io=io), io


def only_run(workspace: Path) -> Path:
    runs = sorted((workspace / "out").iterdir())
    assert len(runs) == 1
    return runs[0]


def test_help_lists_every_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.build_parser().parse_args(["--help"])
    assert caught.value.code == 0
    out = capsys.readouterr().out
    assert all(name in out for name in COMMANDS) and "serve" not in out


def test_usage_errors_exit_2(workspace: Path) -> None:
    assert run_main([])[0] == EXIT_USAGE
    assert run_main(["tailor", "--cv", str(CV_FIXTURE)])[0] == EXIT_USAGE  # no JD
    assert run_main([*TAILOR, "--jd-text", "x"])[0] == EXIT_USAGE  # two JDs
    assert run_main(["bogus"])[0] == EXIT_USAGE
    code, io = run_main([*TAILOR, "--auto", "--answers", "a.yaml"])
    assert code == EXIT_USAGE and "E_USAGE" in "\n".join(io.errors)


def test_non_tty_tailor_stops_at_checkpoint_1_then_continue_text_resumes(workspace: Path) -> None:
    runner = FakeRunner()
    code, io = run_main(TAILOR, runner)
    assert code == EXIT_AWAITING and "Which of these requirements" in io.output
    run = only_run(workspace)
    st = state.load(run)
    assert st["stage"] == "awaiting_answers" and st["options"]["host"] == "cli"

    code, io = run_main(["continue", "--text", HELM_REPLY], runner)
    assert code == EXIT_AWAITING and state.load(run)["pending"]["kind"] == "followups"
    follow = workspace / "followups.yaml"
    follow.write_text("followups: default\n", encoding="utf-8")
    assert run_main(["continue", run.name, "--answers", str(follow)], runner)[0] == EXIT_AWAITING  # checkpoint 2
    assert state.load(run)["stage"] == "awaiting_approval"
    code, io = run_main(["continue", "--text", "Say 'cutting' in the monitoring bullet"], runner)
    assert code == EXIT_OK and state.load(run)["stage"] == "reported"
    assert {h["host"] for h in state.load(run)["history"]} == {"cli"}


def test_full_tailor_with_answers_yaml_reaches_reported(workspace: Path, tmp_path: Path) -> None:
    answers = tmp_path / "answers.yaml"
    answers.write_text(ANSWERS_YAML, encoding="utf-8")
    runner = FakeRunner(leave_pending=True)
    code, io = run_main([*TAILOR, "--answers", str(answers)], runner)
    assert code == EXIT_OK and state.load(only_run(workspace))["stage"] == "reported"
    assert "report:" in io.output and "run: " in io.output


def test_auto_creates_no_attestations_and_defaults_every_question(workspace: Path) -> None:
    runner = FakeRunner(plan="none")
    code, _ = run_main([*TAILOR, "--auto"], runner)
    run = only_run(workspace)
    assert code == EXIT_OK and state.load(run)["stage"] == "reported" and state.load(run)["options"]["auto"]
    assert "answer_parse" not in runner.stages()
    assert {q["status"] for q in jsonio.load_json(run / "questions.json")["questions"]} == {"defaulted"}
    store = workspace / "profiles" / "jamie-rivera" / "attestations.json"
    assert not store.is_file() or jsonio.load_json(store)["attestations"] == []


def test_bad_yaml_exits_2_before_creating_a_run(workspace: Path, tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("checkpoint1: [unclosed", encoding="utf-8")
    code, io = run_main([*TAILOR, "--answers", str(bad)])
    assert code == EXIT_USAGE and "E_ANSWERS_YAML" in "\n".join(io.errors) and "hint:" in "\n".join(io.errors)
    assert not (workspace / "out").exists() or not list((workspace / "out").iterdir())
    missing = run_main([*TAILOR, "--answers", str(tmp_path / "nope.yaml")])[0]
    assert missing == EXIT_USAGE


def test_missing_api_key_exits_3_with_hint(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    io = interact.ScriptedIO(interactive=False)
    assert cli.main(TAILOR, io=io) == EXIT_MISSING_DEPENDENCY  # the real ApiRunner, no key
    errors = "\n".join(io.errors)
    assert "E_API_KEY" in errors and "ANTHROPIC_API_KEY" in errors and "hint:" in errors
    assert state.load(only_run(workspace))["stage"] == "ingested"  # saved, resumable


def test_bad_model_flag_is_a_usage_error(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-used")
    io = interact.ScriptedIO(interactive=False)
    assert cli.main([*TAILOR, "--model", "bogus=x"], io=io) == EXIT_USAGE
    assert "E_MODEL_STAGE" in "\n".join(io.errors)


def test_interactive_tailor_prompts_at_both_checkpoints(workspace: Path) -> None:
    runner = FakeRunner(plan="skills_only")
    code, io = run_main(TAILOR, runner, tty=True, inputs=["1", "", "", "a"])
    assert code == EXIT_OK and state.load(only_run(workspace))["stage"] == "reported"
    assert "Checkpoint 1: 3 question(s)" in io.output and "Checkpoint 2:" in io.output


def test_edit_applies_free_text_to_a_reported_run(workspace: Path) -> None:
    runner = FakeRunner(leave_pending=True)
    answers = workspace / "answers.yaml"
    answers.write_text(ANSWERS_YAML, encoding="utf-8")
    assert run_main([*TAILOR, "--answers", str(answers)], runner)[0] == EXIT_OK
    run = only_run(workspace)
    version = jsonio.load_json(run / "tailored.json")["version"]
    code, _ = run_main(["edit", run.name, "--text", "Say 'cutting' in the monitoring bullet"], runner)
    assert code == EXIT_OK and jsonio.load_json(run / "tailored.json")["version"] == version + 1
    assert runner.calls[-1][:2] == ("change_request", {"reply": "Say 'cutting' in the monitoring bullet"})


def test_edit_before_tailoring_is_a_state_error(workspace: Path) -> None:
    assert run_main(TAILOR)[0] == EXIT_AWAITING
    code, io = run_main(["edit", only_run(workspace).name, "--text", "drop it"])
    assert code == 4 and "E_STAGE" in "\n".join(io.errors)


def test_status_render_profile_and_package_delegate_to_cvt(workspace: Path, tmp_path: Path,
                                                           capsys: pytest.CaptureFixture[str]) -> None:
    runner = FakeRunner(leave_pending=True)
    answers = workspace / "answers.yaml"
    answers.write_text(ANSWERS_YAML, encoding="utf-8")
    assert run_main([*TAILOR, "--answers", str(answers)], runner)[0] == EXIT_OK
    run = only_run(workspace)
    capsys.readouterr()

    assert run_main(["status", run.name])[0] == EXIT_OK
    assert "reported" in capsys.readouterr().out
    assert run_main(["status", "--json"])[0] == EXIT_OK
    assert '"stage":"reported"' in capsys.readouterr().out

    assert run_main(["render", run.name])[0] == EXIT_OK  # fit + validate, no AI
    assert state.load(run)["stage"] == "validated"
    assert run_main(["render", run.name, "--template", "classic"])[0] == EXIT_OK
    capsys.readouterr()

    assert run_main(["profile", "list", "--person", "jamie-rivera"])[0] == EXIT_OK
    assert "att-001" in capsys.readouterr().out
    assert run_main(["profile", "show", "att-001", "--person", "jamie-rivera"])[0] == EXIT_OK
    assert run_main(["profile", "show", "--person", "jamie-rivera"])[0] == EXIT_OK
    capsys.readouterr()
    code, io = run_main(["profile", "revoke", "att-001", "--person", "jamie-rivera"])
    assert code == EXIT_USAGE and "--yes" in "\n".join(io.errors)  # no terminal, no confirmation
    store = jsonio.load_json(workspace / "profiles" / "jamie-rivera" / "attestations.json")
    assert store["attestations"][0]["status"] != "revoked"
    assert run_main(["profile", "revoke", "att-001", "--person", "jamie-rivera", "--yes"])[0] == EXIT_OK
    assert jsonio.load_json(workspace / "profiles" / "jamie-rivera" / "attestations.json")["attestations"][0]["status"] == "revoked"
    assert run_main(["profile", "revoke", "--person", "jamie-rivera"])[0] == EXIT_USAGE  # no id

    out_dir = tmp_path / "dist"
    assert run_main(["package-skill", "--out", str(out_dir)])[0] == EXIT_OK
    assert (out_dir / "tailoring-cvs.zip").is_file()


def test_revoke_asks_for_confirmation_on_a_terminal(workspace: Path) -> None:
    answers = workspace / "answers.yaml"
    answers.write_text(ANSWERS_YAML, encoding="utf-8")
    assert run_main([*TAILOR, "--answers", str(answers)], FakeRunner(leave_pending=True))[0] == EXIT_OK
    io = interact.ScriptedIO(confirms=[False], interactive=True)
    assert cli.main(["profile", "revoke", "att-001", "--person", "jamie-rivera"], io=io) == EXIT_OK
    assert "not revoked" in io.output
    io = interact.ScriptedIO(confirms=[True], interactive=True)
    assert cli.main(["profile", "revoke", "att-001", "--person", "jamie-rivera"], io=io) == EXIT_OK


def test_main_marks_the_host_as_cli(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GTJOB_HOST", raising=False)
    assert run_main(TAILOR)[0] == EXIT_AWAITING
    assert {h["host"] for h in state.load(only_run(workspace))["history"]} == {"cli"}


def test_polish_extract_prints_cv_text_and_rejects_a_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    code, _io = run_main(["polish", "extract", str(CV_FIXTURE)])
    assert code == EXIT_OK and "Jamie" in capsys.readouterr().out
    code, io = run_main(["polish", "extract", "missing.pdf"])
    assert code == EXIT_USAGE and "E_USAGE" in "\n".join(io.errors)


def test_no_serve_command_without_the_web_module() -> None:
    assert "serve" not in cli.build_parser().format_help()


def test_real_runner_is_not_built_for_commands_that_need_no_ai(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli.main(["status"], io=interact.ScriptedIO()) == 4  # no runs yet: a state error, not a missing key
