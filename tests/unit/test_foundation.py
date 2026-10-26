from __future__ import annotations

import datetime
import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from cvtlib import cli, jsonio, output, paths, usage
from cvtlib.errors import CvtError, ExitCode

DAY = datetime.date(2026, 10, 23)


def test_slugify():
    assert paths.slugify("Staff Platform & Reliability") == "staff-platform-reliability"
    assert paths.slugify("Café  Müller__Role!!") == "cafe-muller-role"
    assert paths.slugify("a" * 80, max_len=10) == "a" * 10
    assert paths.slugify("---") == ""
    assert paths.slugify("x-y-z", max_len=2) == "x"


def test_new_run_slug_collisions(workspace):
    assert paths.new_run_slug("staff-sre", DAY) == "20261023-staff-sre"
    (workspace / "out" / "20261023-staff-sre").mkdir(parents=True)
    assert paths.new_run_slug("staff-sre", DAY) == "20261023-staff-sre-2"
    (workspace / "out" / "20261023-staff-sre-2").mkdir()
    assert paths.new_run_slug("Staff SRE", DAY) == "20261023-staff-sre-3"
    assert paths.new_run_slug("", DAY) == "20261023-jd"


def test_dump_json_atomic_and_hash(tmp_path):
    target = tmp_path / "sub" / "a.json"
    digest = jsonio.dump_json({"b": 1, "a": "é"}, target)
    raw = target.read_bytes()
    assert digest == jsonio.sha256_bytes(raw) == jsonio.sha256_file(target)
    assert raw.endswith(b"\n") and raw.decode("utf-8") == '{\n  "b": 1,\n  "a": "é"\n}\n'
    assert [p.name for p in target.parent.iterdir()] == ["a.json"]  # no temp files left
    jsonio.dump_json({"x": 2}, target)
    assert json.loads(target.read_text()) == {"x": 2}


def test_dump_json_failure_keeps_old_file(tmp_path):
    target = tmp_path / "a.json"
    jsonio.dump_json({"ok": True}, target)
    with pytest.raises(TypeError):
        jsonio.dump_json({"bad": object()}, target)
    assert json.loads(target.read_text()) == {"ok": True}


def test_load_json_error_has_line_and_column(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{\n  "a": 1,\n  oops\n}', encoding="utf-8")
    with pytest.raises(CvtError) as info:
        jsonio.load_json(bad)
    assert info.value.err_id == "E_JSON" and info.value.code == ExitCode.INPUT
    assert "line 3" in info.value.message


def test_append_jsonl_is_minified_lines(tmp_path):
    path = tmp_path / "u.jsonl"
    threads = [threading.Thread(target=jsonio.append_jsonl, args=(path, {"n": i, "t": "é"})) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 20 and all(" " not in ln for ln in lines)
    assert sorted(json.loads(ln)["n"] for ln in lines) == list(range(20))


def test_now_iso_format():
    assert jsonio.now_iso().endswith("Z") and "." not in jsonio.now_iso()


def _make_run(root, slug, updated_at):
    d = root / "out" / slug
    d.mkdir(parents=True)
    (d / "state.json").write_text(json.dumps({"updated_at": updated_at}), encoding="utf-8")
    return d


def test_resolve_run_forms(workspace):
    old = _make_run(workspace, "20261001-old", "2026-10-01T00:00:00Z")
    new = _make_run(workspace, "20261002-new", "2026-10-02T00:00:00Z")
    assert paths.resolve_run("latest") == new.resolve()
    assert paths.resolve_run(None) == new.resolve()
    assert paths.resolve_run("20261001-old") == old.resolve()
    assert paths.resolve_run(str(old)) == old.resolve()
    with pytest.raises(CvtError) as info:
        paths.resolve_run("nope")
    assert info.value.err_id == "E_RUN_NOT_FOUND" and info.value.code == ExitCode.STATE


def test_resolve_latest_without_runs(workspace):
    with pytest.raises(CvtError) as info:
        paths.resolve_run("latest")
    assert info.value.err_id == "E_RUN_NOT_FOUND"


def test_paths_helpers(workspace):
    assert paths.SKILL_ROOT.name == "tailoring-cvs"
    assert paths.schema_file("jd").is_file()
    assert paths.asset("schemas").is_dir()
    assert paths.person_dir("jane-doe") == workspace / "profiles" / "jane-doe"
    assert paths.attestations_path("jane-doe").name == "attestations.json"


def test_error_envelope_and_human_format(capsys):
    args = type("A", (), {"json": True, "command": "status", "run": "r1"})()
    err = CvtError(ExitCode.STATE, "E_ARTIFACT_MISSING", "jd.json not found", hint="write it")
    assert output.fail(args, err) == 4
    out = capsys.readouterr().out
    assert out.count("\n") == 1 and '": ' not in out and '", ' not in out  # minified
    env = json.loads(out)
    assert env["ok"] is False and env["exit_code"] == 4 and env["command"] == "status"
    assert env["error"] == {"id": "E_ARTIFACT_MISSING", "message": "jd.json not found", "hint": "write it"}
    assert set(env) == {"ok", "command", "exit_code", "run", "stage", "data", "messages", "next_action", "error"}

    args.json = False
    output.fail(args, err)
    assert capsys.readouterr().err == "cvt: error[E_ARTIFACT_MISSING]: jd.json not found\n  hint: write it\n"


def test_emit_json_is_one_line(capsys):
    args = type("A", (), {"json": True, "all": False, "command": "x"})()
    rc = output.emit(args, run="r", stage="ingested", data={"a": [1, 2]}, messages=["hi"], next_action="go")
    out = capsys.readouterr().out
    assert rc == 0 and out.count("\n") == 1
    assert json.loads(out)["data"] == {"a": [1, 2]} and ", " not in out and ": " not in out


def test_human_output_capped_and_all_lifts(capsys):
    text = "\n".join(f"line {i}" for i in range(40))
    args = type("A", (), {"json": False, "all": False, "command": "x"})()
    output.emit(args, human=text, next_action="do it")
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == output.MAX_HUMAN_LINES
    assert lines[-1] == "next: do it" and lines[-2].startswith("+") and "more (use --all)" in lines[-2]
    args.all = True
    output.emit(args, human=text)
    assert len(capsys.readouterr().out.splitlines()) == 40


def test_cap_list():
    args = type("A", (), {"all": False})()
    shown, hidden = output.cap_list(args, list(range(25)))
    assert len(shown) == output.MAX_LIST_ITEMS and hidden == 15
    args.all = True
    assert output.cap_list(args, list(range(25))) == (list(range(25)), 0)


def test_usage_record_and_totals(tmp_path):
    assert usage.usage_totals(tmp_path) == {}
    usage.record_usage(tmp_path, {"stage": "match", "kind": "packet", "est_tokens": 6000})
    usage.record_usage(tmp_path, {"stage": "tailor", "kind": "packet", "est_tokens": 7000})
    usage.record_usage(tmp_path, {"stage": "match", "kind": "api", "model": "claude-sonnet-5-5",
                                  "input_tokens": 100, "cache_read_tokens": 50,
                                  "cache_write_tokens": 20, "output_tokens": 30})
    usage.record_usage(tmp_path, {"stage": "match", "kind": "api", "model": "claude-sonnet-5-5",
                                  "input_tokens": 10, "output_tokens": 5, "attempt": 2})
    totals = usage.usage_totals(tmp_path)
    assert totals["packets"] == {"match": 6000, "tailor": 7000} and totals["total_est"] == 13000
    assert totals["api"]["match"] == {"model": "claude-sonnet-5-5", "input": 110, "cache_read": 50,
                                      "cache_write": 20, "output": 35}
    first = json.loads((tmp_path / "usage.jsonl").read_text().splitlines()[0])
    assert first["at"].endswith("Z") and first["attempt"] == 1


def test_usage_rejects_bad_entries(tmp_path):
    for bad in ({"stage": "x", "kind": "nope"}, {"kind": "packet"}, {"stage": "x", "kind": "api", "foo": 1}):
        with pytest.raises(CvtError):
            usage.record_usage(tmp_path, bad)


def _good_artifact(workspace):
    run = workspace / "out" / "20261023-x"
    run.mkdir(parents=True)
    return run


def test_validate_artifact_exit_codes(workspace, run_cvt):
    run = _good_artifact(workspace)
    r = run_cvt("--json", "validate-artifact", "nope", "jd")
    assert r.returncode == 4 and json.loads(r.stdout)["error"]["id"] == "E_RUN_NOT_FOUND"
    r = run_cvt("validate-artifact", "20261023-x", "jd")
    assert r.returncode == 4 and "E_ARTIFACT_MISSING" in r.stderr
    r = run_cvt("validate-artifact", "20261023-x", "bogus")
    assert r.returncode == 2 and "E_SCHEMA_UNKNOWN" in r.stderr
    (run / "jd.json").write_text("{}", encoding="utf-8")
    r = run_cvt("validate-artifact", "20261023-x", "jd", "--json")
    env = json.loads(r.stdout)
    assert r.returncode == 1 and env["ok"] is False and env["data"]["valid"] is False
    assert env["data"]["violations"][0]["code"] == "schema"
    (run / "jd.json").write_text("{not json", encoding="utf-8")
    assert run_cvt("validate-artifact", "20261023-x", "jd").returncode == 5
    assert not (run / "state.json").exists()  # never changes state


def test_validate_artifact_ok_with_file(workspace, run_cvt):
    _good_artifact(workspace)
    bad = workspace / "bad.json"
    bad.write_text(json.dumps({"schema_version": "1"}), encoding="utf-8")
    assert run_cvt("validate-artifact", "20261023-x", "validation", "--file", str(bad)).returncode == 1
    r = run_cvt("validate-artifact", "20261023-x", "validation", "--file", str(bad), "--json")
    assert json.loads(r.stdout)["data"]["violation_count"] >= 1


def test_json_flag_before_and_after_subcommand(workspace, run_cvt):
    before = run_cvt("--json", "validate-artifact", "nope", "jd")
    after = run_cvt("validate-artifact", "nope", "jd", "--json")
    assert before.returncode == after.returncode == 4
    assert json.loads(before.stdout) == json.loads(after.stdout)
    assert run_cvt("validate-artifact", "nope", "jd").stdout == ""


def test_all_flag_either_position(workspace, run_cvt):
    assert run_cvt("--all", "validate-artifact", "nope", "jd").returncode == 4
    assert run_cvt("validate-artifact", "nope", "jd", "--all").returncode == 4


def test_cli_help_lists_command_and_usage_error(workspace, run_cvt):
    r = run_cvt("--help")
    assert r.returncode == 0 and "validate-artifact" in r.stdout
    r = run_cvt("no-such-command")
    assert r.returncode == 2 and "E_USAGE" in r.stderr
    assert run_cvt().returncode == 2


def test_internal_error_writes_traceback(workspace, monkeypatch, capsys):
    def boom(args):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(cli, "build_parser", lambda: _Boom(boom))
    rc = cli.main(["x"])
    assert rc == 7
    assert "kaboom" in (workspace / ".cache" / "cvt-last-error.txt").read_text()
    assert "E_INTERNAL" in capsys.readouterr().err


class _Boom:
    def __init__(self, func):
        self._func = func

    def parse_args(self, argv):
        import argparse

        return argparse.Namespace(func=self._func, json=False, command="x", run="")


USAGE_JSON_ARGVS = [
    ["--json", "validate-artifact"],
    ["--json", "bogus"],
    ["--json"],
    ["validate-artifact", "--json"],
]
ANCHORED_DIRS = ("CVs", "JDs", "out", "profiles", "dist")
REPO_ROOT = Path(__file__).resolve().parents[2]
IGNORED_PATHS = ("out/x", "CVs/x", "JDs/x", "profiles/x", "tests/fixtures/private/x")
TRACKED_PATHS = ("tests/fixtures/jds/junior-devops-engineer.md", "tests/fixtures/cv/jamie-rivera-junior.txt")


@pytest.mark.parametrize("argv", USAGE_JSON_ARGVS)
def test_json_usage_errors_emit_one_envelope(workspace, capsys, argv):
    rc = cli.main(argv)
    captured = capsys.readouterr()
    assert rc == int(ExitCode.USAGE)
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert len(lines) == 1
    env = json.loads(lines[0])
    assert env["ok"] is False and env["exit_code"] == 2 and env["error"]["id"] == "E_USAGE"


def test_json_usage_error_names_known_command(workspace, capsys):
    cli.main(["--json", "validate-artifact"])
    assert json.loads(capsys.readouterr().out)["command"] == "validate-artifact"
    cli.main(["--json", "bogus"])
    assert json.loads(capsys.readouterr().out)["command"] == ""


def test_human_usage_error_goes_to_stderr(workspace, capsys):
    rc = cli.main(["validate-artifact"])
    captured = capsys.readouterr()
    assert rc == int(ExitCode.USAGE)
    assert captured.out == ""
    assert captured.err.startswith("cvt: error[E_USAGE]:")
    assert captured.err.count("--help") == 1


def test_gitignore_anchors_root_directories():
    lines = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for name in ANCHORED_DIRS:
        assert f"/{name}/" in lines
        assert f"{name}/" not in lines


def _git_check_ignore(path: str) -> int:
    return subprocess.run(
        ["git", "check-ignore", "-q", path], cwd=REPO_ROOT, capture_output=True, check=False,
    ).returncode


def test_gitignore_effects_with_git():
    if shutil.which("git") is None:
        pytest.skip("git not on PATH")
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        pytest.skip("repo root is not a git work tree")
    for path in IGNORED_PATHS:
        assert _git_check_ignore(path) == 0, path
    for path in TRACKED_PATHS:
        assert _git_check_ignore(path) == 1, path
