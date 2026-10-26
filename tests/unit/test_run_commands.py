"""WP-08: `cvt init` and `cvt status`, plus host detection."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cvtlib import hostdetect, jsonio, state, usage

JD_TEXT = "Platform Engineer at Acme. Must have Kubernetes."
CV_TEXT = "Jane Doe\njane@example.com\n"


@pytest.fixture
def cv(workspace: Path) -> Path:
    path = workspace / "cv.txt"
    path.write_text(CV_TEXT, encoding="utf-8")
    return path


def _json(proc: subprocess.CompletedProcess) -> dict:
    return json.loads(proc.stdout)


def _init(run_cvt, cv: Path, *extra: str) -> subprocess.CompletedProcess:
    return run_cvt("--json", "init", "--cv", str(cv), *extra)


def _questions(run_dir: Path, run_id: str, rows: list[dict]) -> None:
    (run_dir / "questions.json").write_text(
        json.dumps({"schema_version": "1", "run_id": run_id, "questions": rows}), encoding="utf-8",
    )


def _question(qid: str, prompt: str, status: str = "pending") -> dict:
    return {
        "id": qid, "checkpoint": 1, "round": 1, "type": "yes_no", "topic": "gap", "prompt": prompt,
        "choices": [], "allow_free_text": True,
        "default": {"choice_ids": [], "text": "", "description": "Keep as gaps; nothing is added."},
        "links": {"req_ids": [], "item_ids": [], "issue_ids": [], "attestation_ids": []},
        "parent_id": "", "status": status, "suppressed_reason": "",
    }


def test_init_jd_text(run_cvt, cv, workspace):
    proc = _init(run_cvt, cv, "--jd-text", JD_TEXT, "--slug", "smoke")
    assert proc.returncode == 0, proc.stderr
    env = _json(proc)
    assert env["ok"] and env["command"] == "init" and env["stage"] == "initialized"
    assert env["run"].endswith("-smoke")
    assert set(env["data"]) == {"run_dir", "run_slug", "inputs"}
    assert Path(env["data"]["run_dir"]) == (workspace / "out" / env["run"]).resolve()
    assert env["data"]["inputs"]["jd"]["kind"] == "text"
    assert "ingest" in env["next_action"]


def test_init_jd_file(run_cvt, cv, workspace):
    jd = workspace / "Staff SRE Role.md"
    jd.write_text(JD_TEXT, encoding="utf-8")
    env = _json(_init(run_cvt, cv, "--jd", str(jd)))
    assert env["run"].endswith("-staff-sre-role")
    assert env["data"]["inputs"]["jd"]["kind"] == "file"
    assert (workspace / "out" / env["run"] / "inputs" / "jd.md").read_text(encoding="utf-8") == JD_TEXT


def test_init_jd_stdin(workspace, cv):
    env = {**os.environ, "GTJOB_HOME": str(workspace)}
    env.pop("GTJOB_HOST", None)
    script = Path(__file__).resolve().parents[2] / ".claude/skills/tailoring-cvs/scripts/cvt.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--json", "init", "--cv", str(cv), "--jd-stdin"],
        input=JD_TEXT, cwd=workspace, env=env, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["data"]["inputs"]["jd"]["original_ref"] == "stdin"
    assert out["run"].endswith("-platform-engineer-at-acme-must-have")


def test_init_jd_url(run_cvt, cv, workspace):
    url = "https://example.com/jobs/123"
    env = _json(_init(run_cvt, cv, "--jd-url", url, "--slug", "urljob"))
    assert env["data"]["inputs"]["jd"] == {**env["data"]["inputs"]["jd"], "kind": "url", "original_ref": url}
    assert url in (workspace / "out" / env["run"] / "inputs" / "jd.md").read_text(encoding="utf-8")


def test_init_options_and_host_override(run_cvt, cv, workspace):
    env = _json(_init(
        run_cvt, cv, "--jd-text", JD_TEXT, "--template", "classic", "--auto", "--draft",
        "--page-target", "1", "--paper", "a4", "--host", "cli",
    ))
    st = state.load(workspace / "out" / env["run"])
    assert st["options"] == {
        "template": "classic", "auto": True, "draft": True, "page_target": 1, "paper": "a4", "host": "cli",
    }


def test_init_human_output_is_three_lines(run_cvt, cv):
    proc = run_cvt("init", "--cv", str(cv), "--jd-text", JD_TEXT, "--slug", "smoke")
    lines = proc.stdout.splitlines()
    assert proc.returncode == 0 and len(lines) == 3
    assert lines[0].startswith("run: ") and lines[1].startswith("dir: ") and lines[2].startswith("next: ")


def test_init_slug_collisions(run_cvt, cv):
    slugs = [_json(_init(run_cvt, cv, "--jd-text", JD_TEXT, "--slug", "same"))["run"] for _ in range(3)]
    assert slugs[1] == slugs[0] + "-2" and slugs[2] == slugs[0] + "-3"


@pytest.mark.parametrize("extra", [
    [], ["--jd-text", "a", "--jd-url", "https://x.example"], ["--jd", "a.md", "--jd-stdin"],
])
def test_init_requires_exactly_one_jd_source(run_cvt, cv, extra):
    proc = _init(run_cvt, cv, *extra)
    assert proc.returncode == 2
    assert _json(proc)["error"]["id"] == "E_JD_SOURCE"
    assert "--jd-text" in _json(proc)["error"]["hint"]


def test_init_missing_cv_exits_5(run_cvt, workspace):
    proc = run_cvt("--json", "init", "--cv", str(workspace / "nope.txt"), "--jd-text", JD_TEXT)
    assert proc.returncode == 5 and _json(proc)["error"]["id"] == "E_CV_NOT_FOUND"


@pytest.mark.parametrize("name", ["cv.docx", "cv.rtf"])
def test_init_unsupported_cv_format_exits_5(run_cvt, workspace, name):
    path = workspace / name
    path.write_bytes(b"x")
    proc = _init(run_cvt, path, "--jd-text", JD_TEXT)
    assert proc.returncode == 5
    err = _json(proc)["error"]
    assert err["id"] == "E_CV_FORMAT"
    if name.endswith("docx"):
        assert "export to PDF or paste text" in err["hint"]


def test_init_empty_and_missing_jd_exit_5(run_cvt, cv, workspace):
    assert _init(run_cvt, cv, "--jd-text", "  ").returncode == 5
    assert _init(run_cvt, cv, "--jd", str(workspace / "missing.md")).returncode == 5


def test_status_fresh_run_and_latest(run_cvt, cv):
    run = _json(_init(run_cvt, cv, "--jd-text", JD_TEXT, "--slug", "smoke"))["run"]
    proc = run_cvt("--json", "status", "latest")
    env = _json(proc)
    assert proc.returncode == 0 and env["command"] == "status" and env["run"] == run
    assert env["stage"] == "initialized" and "ingest" in env["next_action"]
    assert set(env["data"]) >= {"state", "pending_questions"} and "runs" not in env["data"]
    assert env["data"]["state"]["stage"] == "initialized"
    assert "inputs" not in env["data"]["state"] and "history" not in env["data"]["state"]
    assert env["data"]["pending_questions"] == []
    # RUN omitted, slug, and `--json` after the subcommand all resolve the same run
    assert _json(run_cvt("status", run, "--json"))["run"] == run
    assert _json(run_cvt("--json", "status"))["run"] == run


def test_status_human_fresh_is_short(run_cvt, cv):
    run = _json(_init(run_cvt, cv, "--jd-text", JD_TEXT, "--slug", "smoke"))["run"]
    lines = run_cvt("status").stdout.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith(f"{run} | initialized | ok") and lines[1].startswith("next: ")


def test_status_pending_questions_errors_stale_tokens(run_cvt, cv, workspace):
    run = _json(_init(run_cvt, cv, "--jd-text", JD_TEXT, "--slug", "smoke"))["run"]
    run_dir = workspace / "out" / run
    st = state.load(run_dir)
    long_prompt = "Did you lead the Kubernetes migration? " + "x" * 120
    _questions(run_dir, st["run_id"], [
        _question("q-1", long_prompt), _question("q-2", "Second?"), _question("q-3", "Third?"),
        _question("q-4", "Fourth?"), _question("q-5", "Done already", status="answered"),
    ])
    (run_dir / "cv.txt").write_text("cv", encoding="utf-8")
    (run_dir / "jd.txt").write_text("jd", encoding="utf-8")
    state.record_artifact(run_dir, st, "cv_txt", "cv.txt")
    state.record_artifact(run_dir, st, "jd_txt", "jd.txt")
    st["artifacts"][0]["stale"] = True
    state.set_stage(st, "awaiting_answers", pending={
        "kind": "questions", "question_ids": ["q-1", "q-2", "q-3", "q-4"], "message": "answer",
    })
    state.add_error(st, "E_SCHEMA", "match.json is not valid\nsecond line")
    state.save(run_dir, st)
    usage.record_usage(run_dir, {"stage": "match", "kind": "packet", "est_tokens": 1200})
    usage.record_usage(run_dir, {
        "stage": "match", "kind": "api", "model": "m", "input_tokens": 900, "output_tokens": 300,
    })

    env = _json(run_cvt("--json", "status", run))
    qs = env["data"]["pending_questions"]
    assert [q["id"] for q in qs] == ["q-1", "q-2", "q-3", "q-4"]
    assert qs[0]["default"] == "Keep as gaps; nothing is added."
    assert env["data"]["state"]["artifacts"][0] == {"name": "cv_txt", "path": "cv.txt", "stale": True}
    assert env["data"]["tokens"] == {"packet_est": 1200, "input": 900, "output": 300}

    lines = run_cvt("status", run).stdout.splitlines()
    assert len(lines) <= 8
    assert "pending: questions 4 question(s)" in lines[0]
    assert lines[1].startswith("  q-1: Did you lead") and lines[1].endswith("…")
    assert len(lines[1]) <= len("  q-1: ") + 80
    assert sum(line.startswith("  q-") for line in lines) == 3
    assert "stale: cv_txt" in lines
    assert any(line.startswith("error: [E_SCHEMA] match.json is not valid second line") for line in lines)
    assert "tokens: ~1200 packet est. / 900 in, 300 out (api)" in lines
    assert lines[-1].startswith("next: ") and "questions" in lines[-1]


def test_status_all_lists_runs_newest_first(run_cvt, cv, workspace):
    first = _json(_init(run_cvt, cv, "--jd-text", JD_TEXT, "--slug", "one"))["run"]
    second = _json(_init(run_cvt, cv, "--jd-text", JD_TEXT, "--slug", "two"))["run"]
    first_dir = workspace / "out" / first
    st = state.load(first_dir)
    st["updated_at"] = "2099-01-01T00:00:00Z"
    jsonio.dump_json(st, first_dir / "state.json")  # bypass save() so updated_at stays in the future

    env = _json(run_cvt("--json", "status", "--all"))
    assert [r["run_slug"] for r in env["data"]["runs"]] == [first, second]
    assert set(env["data"]["runs"][0]) == {"run_slug", "stage", "status", "updated_at"}
    assert env["data"]["state"]["run_slug"] == first and "history" in env["data"]["state"]
    assert env["run"] == first  # latest resolves by updated_at

    lines = run_cvt("status", "--all").stdout.splitlines()
    assert lines[0].startswith(f"{first} | initialized | ok | 2099-01-01T00:00:00Z")
    assert lines[1].startswith(second)


def test_status_without_runs_exits_4(run_cvt):
    for argv in (["status"], ["--json", "status", "latest"], ["status", "--all"]):
        proc = run_cvt(*argv)
        assert proc.returncode == 4
    assert _json(run_cvt("--json", "status"))["error"]["id"] == "E_RUN_NOT_FOUND"
    assert "cvt init" in run_cvt("status").stderr


def test_status_unknown_run_exits_4(run_cvt, cv):
    _init(run_cvt, cv, "--jd-text", JD_TEXT)
    assert run_cvt("status", "nope").returncode == 4


def test_status_failed_run_shows_rerun_action(run_cvt, cv, workspace):
    run = _json(_init(run_cvt, cv, "--jd-text", JD_TEXT, "--slug", "smoke"))["run"]
    run_dir = workspace / "out" / run
    st = state.load(run_dir)
    st["status"] = "failed"
    state.add_error(st, "E_X", "boom")
    state.save(run_dir, st)
    env = _json(run_cvt("--json", "status", run))
    assert env["stage"] == "initialized" and "Fix the reported problem" in env["next_action"]
    assert env["data"]["state"]["status"] == "failed"


def test_hostdetect(monkeypatch):
    for key in [k for k in os.environ if k.startswith("CURSOR_") or k == "CLAUDECODE"]:
        monkeypatch.delenv(key)
    assert hostdetect.detect() == "unknown"
    monkeypatch.setenv("CURSOR_TRACE_ID", "x")
    assert hostdetect.detect() == "cursor"
    monkeypatch.setenv("CLAUDECODE", "1")
    assert hostdetect.detect() == "claude_code"
    monkeypatch.delenv("CLAUDECODE")
    monkeypatch.delenv("CURSOR_TRACE_ID")
    monkeypatch.setenv("GTJOB_HOST", "api")
    assert state.current_host() == "api"
