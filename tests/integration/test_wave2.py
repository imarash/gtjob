"""WP-I2: wave 2 commands chained on the junior golden: init, ingest, profile, jd, match, check-tailored, render.

Runs `cvt` as a subprocess inside a temporary `GTJOB_HOME` workspace. The AI-written stages are played by copying the
golden artifacts. Wave 3 transitions (answers-apply, assemble, approve) do not exist yet, so the stage is forced
through `cvtlib.state` and the Helm attestation is added through `cvtlib.attestations`.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from pypdf import PdfReader

from cvtlib import attestations, jsonio, state

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures"
GOLDEN = FIXTURES / "golden" / "junior"
CV_FIXTURE = FIXTURES / "cv" / "jamie-rivera-junior.txt"
JD_FIXTURE = FIXTURES / "jds" / "junior-devops-engineer.md"
ROUND_FIXTURE = GOLDEN / "answers.round.json"

PERSON = "jamie-rivera"
CV_TXT = "cv.txt"
EXPECTED_PAGES = 1
PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,2}\s*$")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
SAMPLE_PRIVATE_FILE = FIXTURES / "private" / "sample-ingest.json"  # git-ignored; holds the real sample's literals
SAMPLE_FORBIDDEN_CHARS = ("\u2756", "\u200b")  # decorative diamond glyph, zero-width space
EXIT_OK = 0
TIMESTAMP_KEY = "created_at"
SCRIPT_ORIGIN = "script"
MISSING_CONTACT = "missing_contact"

STAGE_FOR_NEXT_ACTION = {
    "initialized": "ingest",
    "ingested": "profile-cache",
    "profiled": "brief jd",
    "jd_analyzed": "brief match",
    "matched": "brief questions",
    "answers_applied": "brief tailor",
    "tailored": " diff ",
    "approved": " fit ",
    "rendered": " validate ",
}


def _cvt(run_cvt, *args: str) -> dict:
    """Run a `cvt` command with --json; returns the envelope. Fails the test with stderr when it does not exit 0."""
    proc = run_cvt(*args, "--json")
    assert proc.returncode == EXIT_OK, f"cvt {' '.join(args)} failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
    return json.loads(proc.stdout)


def _assert_next_action(env: dict, stage: str) -> None:
    assert env["stage"] == stage
    assert STAGE_FOR_NEXT_ACTION[stage] in env["next_action"], env["next_action"]


def _status(run_cvt, run: str, stage: str) -> None:
    _assert_next_action(_cvt(run_cvt, "status", run), stage)


def _force_stage(workspace: Path, run: str, stage: str) -> None:
    """Move a run to `stage` the way a wave 3 command would (state + refreshed next_action)."""
    run_dir = workspace / "out" / run
    st = state.load(run_dir)
    state.set_stage(st, stage)
    state.save(run_dir, st)


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


@pytest.fixture
def junior_run(workspace: Path, run_cvt) -> str:
    env = _cvt(run_cvt, "init", "--cv", str(CV_FIXTURE), "--jd", str(JD_FIXTURE))
    return env["data"]["run_slug"]


def test_junior_flow_init_to_render(workspace: Path, run_cvt, junior_run: str) -> None:
    run = junior_run
    run_dir = workspace / "out" / run
    _status(run_cvt, run, "initialized")

    # ingest: cv.txt lines equal the fixture's
    _assert_next_action(_cvt(run_cvt, "ingest", run), "ingested")
    assert _lines(run_dir / CV_TXT) == _lines(CV_FIXTURE)
    _status(run_cvt, run, "ingested")

    # profile: map -> profile-build equals the golden profile
    shutil.copy(GOLDEN / "profile-map.json", run_dir / "profile-map.json")
    _assert_next_action(_cvt(run_cvt, "profile-build", run), "profiled")
    built = jsonio.load_json(run_dir / "profile.json")
    golden_profile = jsonio.load_json(GOLDEN / "profile.json")
    # the golden has no phone, so profile-build adds one script-origin info issue (WP-10); everything else is equal
    script_issues = [i for i in built["source_issues"] if i["origin"] == SCRIPT_ORIGIN]
    assert [(i["kind"], i["severity"]) for i in script_issues] == [(MISSING_CONTACT, "info")]
    built["source_issues"] = [i for i in built["source_issues"] if i["origin"] != SCRIPT_ORIGIN]
    assert built.pop(TIMESTAMP_KEY) and golden_profile.pop(TIMESTAMP_KEY)
    assert built == golden_profile
    stored = _cvt(run_cvt, "profile-cache", run, "--store")
    assert stored["data"]["stored"] is True
    assert (workspace / "profiles" / PERSON).is_dir()
    _status(run_cvt, run, "profiled")

    # jd and match
    shutil.copy(GOLDEN / "jd.json", run_dir / "jd.json")
    _assert_next_action(_cvt(run_cvt, "jd-check", run), "jd_analyzed")
    _status(run_cvt, run, "jd_analyzed")
    shutil.copy(GOLDEN / "match.json", run_dir / "match.json")
    _assert_next_action(_cvt(run_cvt, "match-check", run), "matched")
    _status(run_cvt, run, "matched")

    # wave 3 stand-in: answers applied (the golden Helm attestation is att-001, proposed in this run)
    store = attestations.load_store(PERSON)
    round_ = jsonio.load_json(ROUND_FIXTURE)
    item = round_["items"][0]
    attestations.add(store, item["attestations"][0], run_id=run, question_id=item["question_id"])
    attestations.save_store(PERSON, store)
    _force_stage(workspace, run, "answers_applied")
    _status(run_cvt, run, "answers_applied")

    # check-tailored: the proposed attestation only warns before approval
    shutil.copy(GOLDEN / "tailored.json", run_dir / "tailored.json")
    checked = _cvt(run_cvt, "check-tailored", run)
    gates = checked["data"]["gates"]
    assert gates["provenance"] == "pass"
    assert gates["attestation_status"] == "warn"
    _assert_next_action(checked, "tailored")
    _status(run_cvt, run, "tailored")

    # approval activates the attestation; then render
    store = attestations.load_store(PERSON)
    attestations.set_status(store, "att-001", attestations.STATUS_ACTIVE)
    attestations.save_store(PERSON, store)
    _force_stage(workspace, run, "approved")
    rechecked = _cvt(run_cvt, "check-tailored", run)
    assert "fail" not in rechecked["data"]["gates"].values()
    assert rechecked["data"]["gates"]["attestation_status"] == "pass"
    _status(run_cvt, run, "approved")

    rendered = _cvt(run_cvt, "render", run)
    _assert_next_action(rendered, "rendered")
    _status(run_cvt, run, "rendered")
    pdf = run_dir / "cv.pdf"
    assert pdf.is_file()
    assert len(PdfReader(str(pdf)).pages) == EXPECTED_PAGES
    assert "Jamie Rivera" in PdfReader(str(pdf)).pages[0].extract_text()


def test_profile_cache_lookup_hits_after_store(workspace: Path, run_cvt, junior_run: str) -> None:
    run_dir = workspace / "out" / junior_run
    _cvt(run_cvt, "ingest", junior_run)
    shutil.copy(GOLDEN / "profile-map.json", run_dir / "profile-map.json")
    _cvt(run_cvt, "profile-build", junior_run)
    _cvt(run_cvt, "profile-cache", junior_run, "--store")
    second = _cvt(run_cvt, "init", "--cv", str(CV_FIXTURE), "--jd", str(JD_FIXTURE), "--slug", "second")
    second_run = second["data"]["run_slug"]
    _cvt(run_cvt, "ingest", second_run)
    hit = _cvt(run_cvt, "profile-cache", second_run, "--lookup")
    assert hit["data"]["hit"] is True
    assert hit["stage"] == "profiled"


def test_attest_list_on_empty_store(workspace: Path, run_cvt) -> None:
    env = _cvt(run_cvt, "attest", "list", "--person", PERSON)
    assert env["ok"] is True
    assert not env["data"].get("attestations")


def test_sample_cv_ingest(workspace: Path, run_cvt, sample_cv_path: Path) -> None:
    if not SAMPLE_PRIVATE_FILE.is_file():
        pytest.skip(f"private sample expectations not found: {SAMPLE_PRIVATE_FILE.relative_to(REPO)}")
    required_text = jsonio.load_json(SAMPLE_PRIVATE_FILE)["required_text"]
    env = _cvt(run_cvt, "init", "--cv", str(sample_cv_path), "--jd", str(JD_FIXTURE))
    run = env["data"]["run_slug"]
    _cvt(run_cvt, "ingest", run)
    text = (workspace / "out" / run / CV_TXT).read_text(encoding="utf-8")
    lines = text.splitlines()
    assert not [ln for ln in lines if PAGE_NUMBER_RE.match(ln)]
    header_lines = [ln.strip() for ln in lines if EMAIL_RE.search(ln)]
    assert len(header_lines) == len(set(header_lines))
    for needle in required_text:
        assert needle in text
    for char in SAMPLE_FORBIDDEN_CHARS:
        assert char not in text


def test_no_wave2_stand_ins_left() -> None:
    skill = REPO / ".claude" / "skills" / "tailoring-cvs" / "scripts" / "cvtlib"
    marker = "TODO(" + "I-2)"
    offenders = [p.name for p in skill.rglob("*.py") if marker in p.read_text(encoding="utf-8")]
    assert offenders == []
    profile_src = (skill / "profile.py").read_text(encoding="utf-8")
    assert "from .ingest import DECORATIVE_GLYPHS" in profile_src
