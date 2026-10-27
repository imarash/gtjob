"""WP-26: `gtjob` end to end with the real flow, stages, cache and `cvtlib`; only the network client is a `FakeClient`.

The canned stage answers in `fake_llm/` come from the junior goldens. `tailor.1.json` is deliberately bad (it names a
tool the CV does not support), so every full run also exercises the fix loop. No network and no API key.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import HOST_ENV, REPO_ROOT
from cvtlib import jsonio, state
from gtjob import cli, flow, interact
from gtjob.config import MODEL_HAIKU, MODEL_SONNET
from gtjob.llm import FAKE_LLM_ENV, FakeClient

FIXTURES = REPO_ROOT / "tests" / "fixtures"
CV_FIXTURE = FIXTURES / "cv" / "jamie-rivera-junior.txt"
JD_FIXTURE = FIXTURES / "jds" / "junior-devops-engineer.md"
FAKE_DIR = Path(__file__).resolve().parent / "fake_llm"
EXIT_OK, EXIT_AWAITING = 0, 6
PERSON = "jamie-rivera"
HELM_REPLY = "I used Helm at Brightfield to package two internal services"
ANSWERS_YAML = f'checkpoint1:\n  q-1: "{HELM_REPLY}"\n  default_rest: true\nfollowups: default\ncheckpoint2: approve_all\n'
CP1_ONLY_YAML = f'checkpoint1:\n  q-1: "{HELM_REPLY}"\n  default_rest: true\nfollowups: default\n'
UNSUPPORTED_TOOL = "Kubernetes"
FIX_PACKET_HEADER = "# Stage: fix"
USAGE_TABLE_HEADER = "stage         model"
ROUTING = {
    "profile": MODEL_SONNET, "jd": MODEL_HAIKU, "match": MODEL_SONNET, "questions": MODEL_SONNET,
    "answer_parse": MODEL_HAIKU, "tailor": MODEL_SONNET, "change_request": MODEL_HAIKU,
}
DROPPED_ITEM = "t-exp-2.b2"


# ---------------------------------------------------------------- shared helpers (also used by test_cross_host)
@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The offline hook stays off (these tests inject the client); `cli.main` sets GTJOB_HOST, undone after the test."""
    monkeypatch.delenv(FAKE_LLM_ENV, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv(HOST_ENV, "placeholder")
    monkeypatch.delenv(HOST_ENV)


def load_canned(*, bad_tailor: bool = True, auto_plan: bool = False, bad_jd: bool = False) -> FakeClient:
    """A fresh `FakeClient` over `fake_llm/`. `bad_tailor` keeps the unsupported-tool answer as the first tailor reply."""
    client = FakeClient.from_dir(FAKE_DIR)
    tailor = client._responses["tailor"]
    if auto_plan:  # no attested bullet or Helm skill: a run with no attestations
        client._responses["tailor"] = [jsonio.load_json(FAKE_DIR / "tailor-auto.json")]
    elif not bad_tailor:
        client._responses["tailor"] = tailor[1:]
    if bad_jd:  # the first jd answer fails jd-check (wrong jd_sha256); the retry gets the good one
        client._responses["jd"] = [jsonio.load_json(FAKE_DIR / "jd-bad.json"), *client._responses["jd"]]
    return client


def api_runner(fake: FakeClient, *, no_cache: bool = False) -> cli.ApiRunner:
    """The production runner with the network client swapped for `fake` (cache, config and stages are the real ones)."""
    runner = cli.ApiRunner(no_cache=no_cache)
    runner._client = fake
    return runner


def run_gtjob(argv: list[str], fake: FakeClient, *, inputs: list[str] | None = None, interactive: bool = False,
              no_cache: bool = False) -> tuple[int, interact.ScriptedIO]:
    io = interact.ScriptedIO(inputs=list(inputs or []), interactive=interactive)
    return cli.main(argv, runner=api_runner(fake, no_cache=no_cache), io=io), io


def write_answers(directory: Path, text: str) -> Path:
    path = directory / "answers.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def tailor_argv(*extra: str) -> list[str]:
    return ["tailor", "--cv", str(CV_FIXTURE), "--jd", str(JD_FIXTURE), *extra]


def only_run(workspace: Path) -> Path:
    runs = sorted((workspace / "out").iterdir())
    assert len(runs) == 1
    return runs[0]


def usage_rows(run: Path) -> list[dict]:
    path = run / "usage.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stage_models(fake: FakeClient) -> list[tuple[str, str]]:
    return [(c["stage"], c["model"]) for c in fake.calls]


def call_text(call: dict) -> str:
    return "\n".join(block.get("text", "") for block in call["blocks"])


def check_passes(command: str, run: Path) -> None:
    res = flow.run_cvt([command, run.name])
    assert res.code == EXIT_OK, res.env


# ---------------------------------------------------------------- tailor: the full run
def test_tailor_answers_reaches_reported_through_the_fix_loop(workspace: Path, tmp_path: Path) -> None:
    fake = load_canned()
    code, io = run_gtjob(tailor_argv("--answers", str(write_answers(tmp_path, ANSWERS_YAML))), fake)
    assert code == EXIT_OK, io.errors
    run = only_run(workspace)
    st = state.load(run)
    assert st["stage"] == "reported" and st["checkpoints"] == {"cp1": "done", "cp2": "done"}
    assert len(list((run / "final").glob("*.pdf"))) == 1 and (run / "report.md").is_file()
    check_passes("check-tailored", run)

    # the first tailor answer names an unsupported tool; the retry is the fix packet on top of the original turn
    tailor_calls = [c for c in fake.calls if c["stage"] == "tailor"]
    assert len(tailor_calls) == 2
    assert UNSUPPORTED_TOOL in json.dumps(tailor_calls[0]["history"]) + json.dumps(tailor_calls[1]["history"])
    retry = tailor_calls[1]
    assert [turn["role"] for turn in retry["history"]] == ["user", "assistant"]
    assert len(retry["blocks"]) == 1
    fix_text = call_text(retry)
    assert fix_text.startswith(FIX_PACKET_HEADER) and UNSUPPORTED_TOOL in fix_text
    assert "exp-1.b2" in fix_text or "t-exp-1.b2" in fix_text  # the offending item
    assert "Harbor Point" not in fix_text and "Cloud & Containers" not in fix_text  # not the whole run again
    final_plan = jsonio.load_json(run / "tailor-plan.json")
    assert UNSUPPORTED_TOOL not in json.dumps(final_plan)
    assert UNSUPPORTED_TOOL not in json.dumps(jsonio.load_json(run / "tailored.json"))


def test_routing_models_and_usage_report(workspace: Path, tmp_path: Path) -> None:
    fake = load_canned()
    code, io = run_gtjob(tailor_argv("--answers", str(write_answers(tmp_path, ANSWERS_YAML))), fake)
    assert code == EXIT_OK, io.errors
    for stage, model in stage_models(fake):
        assert model == ROUTING[stage], stage
    assert [s for s, _ in stage_models(fake)].count("jd") == 1  # a passing jd-check never escalates
    assert USAGE_TABLE_HEADER in io.output and "total" in io.output
    run = only_run(workspace)
    api = [r for r in usage_rows(run) if r["kind"] == "api"]
    assert {r["stage"] for r in api} == {"profile", "jd", "match", "questions", "answer_parse", "tailor"}
    assert all(r["input_tokens"] > 0 and r["output_tokens"] > 0 for r in api)  # synthetic usage from FakeClient
    assert sorted(r["attempt"] for r in api if r["stage"] == "tailor") == [1, 2]
    for row in api:
        assert f"{row['stage']}" in io.output and row["model"] in io.output


def test_failed_jd_check_retries_once_on_sonnet(workspace: Path) -> None:
    fake = load_canned(bad_jd=True, auto_plan=True)
    code, io = run_gtjob(tailor_argv("--auto"), fake)
    assert code == EXIT_OK, io.errors
    jd_calls = [(c["stage"], c["model"]) for c in fake.calls if c["stage"] == "jd"]
    assert jd_calls == [("jd", MODEL_HAIKU), ("jd", MODEL_SONNET)]
    retry = next(c for c in fake.calls if c["stage"] == "jd" and c["model"] == MODEL_SONNET)
    assert call_text(retry).startswith(FIX_PACKET_HEADER) and "jd_sha256" in call_text(retry)
    assert state.load(only_run(workspace))["stage"] == "reported"


# ---------------------------------------------------------------- --auto and the LLM cache
def test_auto_produces_no_attestations(workspace: Path) -> None:
    fake = load_canned(auto_plan=True)
    code, io = run_gtjob(tailor_argv("--auto"), fake)
    assert code == EXIT_OK, io.errors
    run = only_run(workspace)
    assert state.load(run)["stage"] == "reported"
    assert "answer_parse" not in {c["stage"] for c in fake.calls}
    store = workspace / "profiles" / PERSON / "attestations.json"
    assert not store.is_file() or jsonio.load_json(store)["attestations"] == []
    assert state.load(run)["attestations_used"] == []


def test_second_identical_run_hits_the_llm_cache(workspace: Path) -> None:
    first = load_canned(auto_plan=True)
    code, io = run_gtjob(tailor_argv("--auto"), first)
    assert code == EXIT_OK, io.errors
    assert {c["stage"] for c in first.calls} == {"profile", "jd", "match", "questions", "tailor"}
    cache_files = list((workspace / ".cache" / "gtjob" / "llm").glob("*.json"))
    assert len(cache_files) == len(first.calls)

    # same CV and JD again (a new run): the stored profile and the earlier jd.json are reused without any model call
    second = load_canned(auto_plan=True)
    code, io = run_gtjob(tailor_argv("--auto"), second)
    assert code == EXIT_OK, io.errors
    assert {c["stage"] for c in second.calls}.isdisjoint({"profile", "jd"})
    assert "no AI call" in io.output

    # the very same run again (same slug, so the same prompts): every AI stage is an LLM-cache hit
    shutil.rmtree(workspace / "out")
    third = load_canned(auto_plan=True)
    code, io = run_gtjob(tailor_argv("--auto"), third)
    assert code == EXIT_OK, io.errors
    assert third.calls == []
    run = only_run(workspace)
    assert state.load(run)["stage"] == "reported"
    assert not [r for r in usage_rows(run) if r["kind"] == "api"]  # a cache hit costs nothing

    # --no-cache bypasses reads (and still writes)
    shutil.rmtree(workspace / "out")
    fourth = load_canned(auto_plan=True)
    code, io = run_gtjob(tailor_argv("--auto", "--no-cache"), fourth, no_cache=True)
    assert code == EXIT_OK, io.errors
    assert {c["stage"] for c in fourth.calls} == {"jd", "match", "questions", "tailor"}


# ---------------------------------------------------------------- status, render, profile, edit
@pytest.fixture
def reported_run(workspace: Path, tmp_path: Path) -> Path:
    fake = load_canned()
    code, io = run_gtjob(tailor_argv("--answers", str(write_answers(tmp_path, ANSWERS_YAML))), fake)
    assert code == EXIT_OK, io.errors
    return only_run(workspace)


def delegated_json(argv: list[str], capsys: pytest.CaptureFixture[str], fake: FakeClient | None = None) -> dict:
    capsys.readouterr()
    code = cli.main([*argv, "--json"], runner=api_runner(fake or load_canned()), io=interact.ScriptedIO(interactive=False))
    assert code == EXIT_OK
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_status_render_and_profile_list(reported_run: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status = delegated_json(["status", reported_run.name], capsys)
    assert status["stage"] == "reported" and status["run"] == reported_run.name

    classic = delegated_json(["render", reported_run.name, "--template", "classic"], capsys)
    assert classic["ok"] is True
    st = state.load(reported_run)
    assert st["status"] == "ok" and st["stage"] in {"rendered", "validated"}
    assert jsonio.load_json(reported_run / "build" / "render.json")["theme"]["template"] == "classic"
    assert (reported_run / "cv.pdf").is_file()

    profile = delegated_json(["profile", "list", "--person", PERSON], capsys)
    claims = [a["claim"] for a in profile["data"]["attestations"]]
    assert claims == ["Helm"]


def test_edit_creates_a_new_version_and_rerenders(reported_run: Path) -> None:
    before = jsonio.load_json(reported_run / "tailored.json")
    assert DROPPED_ITEM in json.dumps(before)
    pdf_before = (reported_run / "cv.pdf").read_bytes()
    fake = load_canned()
    code, io = run_gtjob(["edit", reported_run.name, "--text", "drop the earlier experience line"], fake,
                         inputs=["a"], interactive=True)
    assert code == EXIT_OK, io.errors
    assert stage_models(fake) == [("change_request", MODEL_HAIKU)]
    after = jsonio.load_json(reported_run / "tailored.json")
    assert after["version"] == before["version"] + 1
    assert DROPPED_ITEM not in json.dumps(after)
    assert state.load(reported_run)["stage"] == "reported"
    assert (reported_run / "cv.pdf").read_bytes() != pdf_before
    assert len(list((reported_run / "final").glob("*.pdf"))) >= 1
    assert "approved" in io.output
