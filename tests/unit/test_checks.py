"""WP-13: jd-check, match-check, check-tailored (library and commands) on the junior golden."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from cvtlib import checks, jsonio, state

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
GOLDEN = FIXTURES / "golden" / "junior"
CV = FIXTURES / "cv" / "jamie-rivera-junior.txt"
JD_FILE = FIXTURES / "jds" / "junior-devops-engineer.md"
SLUG = "jr"
PERSON = "jamie-rivera"


def _golden(name: str) -> dict:
    return json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))


def _atts() -> list[dict]:
    return json.loads((FIXTURES / "provenance" / "attestations.json").read_text(encoding="utf-8"))


@pytest.fixture
def jd_inputs() -> tuple[dict, str, str]:
    raw = JD_FILE.read_bytes()
    return _golden("jd"), raw.decode("utf-8"), hashlib.sha256(raw).hexdigest()


# --- check_jd -----------------------------------------------------------------------------------------------
def test_check_jd_passes_on_golden(jd_inputs):
    jd, text, sha = jd_inputs
    assert checks.check_jd(jd, text, sha) == []


@pytest.mark.parametrize("name,mutate,item_id", [
    ("sha", lambda jd: jd.update(jd_sha256="0" * 64), "jd_sha256"),
    ("duplicate id", lambda jd: jd["requirements"][2].update(id="req-1"), "req-1"),
    ("gap in ids", lambda jd: jd["requirements"][8].update(id="req-12"), "req-12"),
    ("unknown req_id", lambda jd: jd["keywords"][0]["req_ids"].append("req-99"), "keywords[0]"),
    ("no must", lambda jd: [r.update(kind="nice") for r in jd["requirements"]], "requirements"),
    ("noise not verbatim", lambda jd: jd["noise"][0].update(text="Salary range: $1-$2"), "noise[0]"),
    ("company not in text", lambda jd: jd.update(company="Acme Rocketry"), "company"),
])
def test_check_jd_tampered(jd_inputs, name, mutate, item_id):
    jd, text, sha = jd_inputs
    jd = copy.deepcopy(jd)
    mutate(jd)
    got = checks.check_jd(jd, text, sha)
    assert any(v["item_id"] == item_id for v in got), (name, got)


def test_check_jd_empty_company_is_allowed(jd_inputs):
    jd, text, sha = jd_inputs
    jd = copy.deepcopy(jd)
    jd["company"] = ""
    assert checks.check_jd(jd, text, sha) == []


def test_normalize_jd_merges_keywords_and_orders_by_weight(jd_inputs):
    jd = copy.deepcopy(jd_inputs[0])
    jd["keywords"].append({"term": "terraform", "synonyms": ["tf"], "weight": 5, "req_ids": ["req-1"]})
    out = checks.normalize_jd(jd)
    terms = [k["term"].casefold() for k in out["keywords"]]
    assert terms.count("terraform") == 1
    tf = next(k for k in out["keywords"] if k["term"].casefold() == "terraform")
    assert tf["weight"] == 5 and set(tf["req_ids"]) == {"req-3", "req-1"} and "tf" in tf["synonyms"]
    weights = [k["weight"] for k in out["keywords"]]
    assert weights == sorted(weights, reverse=True)


# --- check_match --------------------------------------------------------------------------------------------
def _match_inputs():
    return _golden("match"), _golden("jd"), _golden("profile")


def test_check_match_passes_and_recomputes_coverage():
    match, jd, profile = _match_inputs()
    match = copy.deepcopy(match)
    match["coverage"] = {k: 99 for k in match["coverage"]}  # AI values are overwritten
    fixed, violations = checks.check_match(match, jd, profile, [])
    assert violations == []
    assert fixed["coverage"] == _golden("match")["coverage"]
    assert fixed["coverage"]["must_total"] == 6 and fixed["coverage"]["must_none"] == 1


def test_check_match_does_not_mutate_input():
    match, jd, profile = _match_inputs()
    before = copy.deepcopy(match)
    match["requirements"][0]["evidence"][0]["quote"] = ""
    snapshot = copy.deepcopy(match)
    checks.check_match(match, jd, profile, [])
    assert match == snapshot and before != snapshot


@pytest.mark.parametrize("name,mutate,item_id", [
    ("missing requirement", lambda m: m["requirements"].pop(3), "req-4"),
    ("duplicate requirement", lambda m: m["requirements"].append(copy.deepcopy(m["requirements"][0])), "req-1"),
    ("unknown requirement", lambda m: m["requirements"][0].update(req_id="req-42"), "req-42"),
    ("unknown ref", lambda m: m["requirements"][0]["evidence"][0].update(ref="exp-9.b1"), "req-1"),
    ("quote not substring", lambda m: m["requirements"][1]["evidence"][0].update(quote="Built 99 pipelines"), "req-2"),
    ("none with evidence", lambda m: m["requirements"][5]["evidence"].append(
        {"ref": "exp-1.b1", "quote": "", "note": ""}), "req-6"),
    ("strong without evidence", lambda m: m["requirements"][1].update(evidence=[]), "req-2"),
    ("unknown metric item", lambda m: m["metric_opportunities"].append(
        {"item_id": "exp-1.b99", "question": "q", "why": "w"}), "exp-1.b99"),
    ("too many metrics", lambda m: m["metric_opportunities"].extend(
        [{"item_id": "exp-1.b1", "question": "q", "why": "w"}] * 6), "metric_opportunities"),
])
def test_check_match_tampered(name, mutate, item_id):
    match, jd, profile = _match_inputs()
    match = copy.deepcopy(match)
    mutate(match)
    _fixed, violations = checks.check_match(match, jd, profile, [])
    assert any(v["item_id"] == item_id for v in violations), (name, violations)


def test_check_match_attestation_refs_must_be_usable():
    match, jd, profile = _match_inputs()
    match = copy.deepcopy(match)
    match["requirements"][5].update(strength="partial", evidence=[{"ref": "att-001", "quote": "Helm", "note": ""}])
    helm = next(a for a in _atts() if a["id"] == "att-001")
    assert checks.check_match(match, jd, profile, [helm])[1] == []
    assert any(v["code"] == "unknown_ref" for v in checks.check_match(match, jd, profile, [])[1])
    revoked = dict(helm, status="revoked")
    assert any(v["code"] == "unknown_ref" for v in checks.check_match(match, jd, profile, [revoked])[1])
    bad_quote = copy.deepcopy(match)
    bad_quote["requirements"][5]["evidence"][0]["quote"] = "Kubernetes"
    assert any(v["code"] == "not_verbatim" for v in checks.check_match(bad_quote, jd, profile, [helm])[1])


def test_check_match_fills_empty_quotes_from_first_matched_keyword():
    match, jd, profile = _match_inputs()
    match = copy.deepcopy(match)
    match["requirements"][0]["evidence"][0]["quote"] = ""  # req-1 keywords AWS, ECS, S3, IAM; ref exp-1.b3
    match["requirements"][4]["evidence"][1]["quote"] = ""  # req-5 keywords Python, Bash; ref exp-2.b2 (no keyword)
    fixed, violations = checks.check_match(match, jd, profile, [])
    assert violations == []
    q0 = fixed["requirements"][0]["evidence"][0]["quote"]
    assert q0 == "Containerized 6 legacy services with Docker and moved them to Amazon ECS."
    q4 = fixed["requirements"][4]["evidence"][1]["quote"]
    assert q4 and q4 in "Automated account provisioning with PowerShell scripts, saving roughly 5 hours per week."


def test_quote_fallback_truncates_at_word_boundary():
    text = "word " * 60
    quote = checks._quote_from(text.strip(), ["nothing-matches-this"])
    assert len(quote) <= checks.QUOTE_FALLBACK_CHARS and not quote.endswith(" ") and quote in text


def test_check_match_attestation_quote_filled_from_claim():
    match, jd, profile = _match_inputs()
    match = copy.deepcopy(match)
    match["requirements"][5].update(strength="partial", evidence=[{"ref": "att-001", "quote": "", "note": ""}])
    helm = next(a for a in _atts() if a["id"] == "att-001")
    fixed, violations = checks.check_match(match, jd, profile, [helm])
    assert violations == [] and fixed["requirements"][5]["evidence"][0]["quote"] == "Helm"


# --- renumber -----------------------------------------------------------------------------------------------
def test_renumber_is_identity_on_golden_and_fixes_slips():
    t = _golden("tailored")
    same, idmap = checks.renumber_tailored(t)
    assert same == t and idmap == {}
    t = copy.deepcopy(t)
    t["experience"][0]["bullets"][1]["id"] = "t-exp-1.b9"
    t["skills"][1]["id"] = "t-skl-7"
    t["certifications"][0]["id"] = "t-cert-4"
    t["open_items"][0]["item_ids"] = ["t-skl-7"]
    fixed, idmap = checks.renumber_tailored(t)
    assert fixed["experience"][0]["bullets"][1]["id"] == "t-exp-1.b2"
    assert fixed["skills"][1]["id"] == "t-skl-2" and fixed["certifications"][0]["id"] == "t-cert-1"
    assert fixed["open_items"][0]["item_ids"] == ["t-skl-2"]
    assert idmap == {"t-exp-1.b9": "t-exp-1.b2", "t-skl-7": "t-skl-2", "t-cert-4": "t-cert-1"}
    assert fixed["experience"][0]["bullets"][1]["source_refs"] == t["experience"][0]["bullets"][1]["source_refs"]


# --- commands -----------------------------------------------------------------------------------------------
def _env(proc) -> dict:
    return json.loads(proc.stdout)


@pytest.fixture
def run_dir(workspace, run_cvt) -> Path:
    proc = run_cvt("--json", "init", "--cv", str(CV), "--jd", str(JD_FILE), "--slug", SLUG)
    assert proc.returncode == 0, proc.stderr
    path = Path(_env(proc)["data"]["run_dir"])
    assert run_cvt("--json", "ingest", path.name).returncode == 0
    shutil.copy(GOLDEN / "profile.json", path / "profile.json")
    st = state.load(path)
    state.record_artifact(path, st, "profile", "profile.json")
    state.set_stage(st, "profiled")
    state.save(path, st)
    return path


def _put(run_dir: Path, name: str, obj: dict) -> None:
    jsonio.dump_json(obj, run_dir / name)


def _set_stage(run_dir: Path, stage: str) -> None:
    st = state.load(run_dir)
    state.set_stage(st, stage)
    state.save(run_dir, st)


def _store(workspace: Path, run_id: str, status: str) -> None:
    att = dict(next(a for a in _atts() if a["id"] == "att-001"), status=status, run_id=run_id)
    store = {"schema_version": "1", "person_slug": PERSON, "next_seq": 2, "attestations": [att]}
    jsonio.dump_json(store, workspace / "profiles" / PERSON / "attestations.json")


def test_jd_check_command_pass_and_state(run_dir, run_cvt):
    _put(run_dir, "jd.json", _golden("jd"))
    proc = run_cvt("--json", "jd-check", run_dir.name)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    env = _env(proc)
    assert env["ok"] and env["stage"] == "jd_analyzed" and env["data"]["requirements"] == 9
    assert "brief match" in env["next_action"]
    st = state.load(run_dir)
    assert state.artifact(st, "jd") is not None and st["stage"] == "jd_analyzed"
    again = _env(run_cvt("--json", "jd-check", run_dir.name))
    assert again["ok"] and again["stage"] == "jd_analyzed"


def test_jd_check_command_tampered_and_missing(run_dir, run_cvt):
    proc = run_cvt("--json", "jd-check", run_dir.name)
    assert proc.returncode == 4 and _env(proc)["error"]["id"] == "E_ARTIFACT_MISSING"
    jd = _golden("jd")
    jd["noise"][0]["text"] = "Salary range: $1-$2"
    jd["keywords"][0]["req_ids"].append("req-77")
    _put(run_dir, "jd.json", jd)
    proc = run_cvt("--json", "jd-check", run_dir.name)
    env = _env(proc)
    assert proc.returncode == 1 and env["error"]["id"] == "E_CHECK_FAILED"
    assert {v["item_id"] for v in env["data"]["violations"]} == {"noise[0]", "keywords[0]"}
    assert "brief fix" in env["next_action"]
    st = state.load(run_dir)
    assert st["status"] == "failed" and st["stage"] == "profiled"
    human = run_cvt("jd-check", run_dir.name)
    assert human.returncode == 1 and "cvt: error[E_CHECK_FAILED]" in human.stderr and "hint:" in human.stderr


def test_jd_check_schema_error_is_reported(run_dir, run_cvt):
    jd = _golden("jd")
    del jd["title"]
    _put(run_dir, "jd.json", jd)
    proc = run_cvt("--json", "jd-check", run_dir.name)
    assert proc.returncode == 1 and _env(proc)["error"]["id"] == "E_SCHEMA"


def test_match_check_command(run_dir, run_cvt):
    _put(run_dir, "jd.json", _golden("jd"))
    assert run_cvt("--json", "jd-check", run_dir.name).returncode == 0
    match = _golden("match")
    match["coverage"] = {k: 0 for k in match["coverage"]}
    match["requirements"][0]["evidence"][0]["quote"] = ""
    _put(run_dir, "match.json", match)
    proc = run_cvt("--json", "match-check", run_dir.name)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    env = _env(proc)
    assert env["stage"] == "matched" and env["data"]["quotes_filled"] == 1
    assert env["data"]["coverage"]["must_total"] == 6
    written = json.loads((run_dir / "match.json").read_text(encoding="utf-8"))
    assert written["coverage"]["must_strong"] == 4
    assert written["requirements"][0]["evidence"][0]["quote"]
    assert (run_dir / "match.json").read_text(encoding="utf-8").startswith('{\n  "schema_version"')
    tampered = copy.deepcopy(written)
    tampered["requirements"][1]["evidence"][0]["quote"] = "Built 99 pipelines"
    _put(run_dir, "match.json", tampered)
    proc = run_cvt("--json", "match-check", run_dir.name)
    assert proc.returncode == 1 and _env(proc)["data"]["violations"][0]["item_id"] == "req-2"


def test_match_check_needs_jd_check_first(run_dir, run_cvt):
    _put(run_dir, "match.json", _golden("match"))
    proc = run_cvt("--json", "match-check", run_dir.name)
    assert proc.returncode == 4 and _env(proc)["error"]["id"] == "E_STAGE"


@pytest.fixture
def tailor_run(run_dir, run_cvt, workspace) -> Path:
    _put(run_dir, "jd.json", _golden("jd"))
    assert run_cvt("--json", "jd-check", run_dir.name).returncode == 0
    _set_stage(run_dir, "answers_applied")
    _store(workspace, run_dir.name, "proposed")
    return run_dir


def _validation(run_dir: Path) -> dict:
    return json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))


def _gates(run_dir: Path) -> dict[str, str]:
    return {g["name"]: g["status"] for g in _validation(run_dir)["gates"]}


def test_check_tailored_pass_writes_history_validation_and_stage(tailor_run, run_cvt):
    _put(tailor_run, "tailored.json", _golden("tailored"))
    proc = run_cvt("--json", "check-tailored", tailor_run.name)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    env = _env(proc)
    assert env["stage"] == "tailored" and env["data"]["version"] == 1
    gates = _gates(tailor_run)
    assert [gates[g] for g in ("schema", "provenance", "placeholders", "logistics_leak")] == ["pass"] * 4
    assert gates["attestation_status"] == "warn"  # att-001 is proposed; it activates at approval
    assert {gates[g] for g in ("page_count", "typography_floor", "ats_roundtrip", "keyword_coverage", "layout")} == {"skipped"}
    assert _validation(tailor_run)["passed"] is True
    assert [p.name for p in (tailor_run / "tailored.history").glob("v*.json")] == ["v1.json"]
    st = state.load(tailor_run)
    assert state.artifact(st, "tailored") is not None
    again = _env(run_cvt("--json", "check-tailored", tailor_run.name))
    assert again["data"]["version"] == 1 and again["data"]["new_snapshot"] is False and again["data"]["changed"] is False


def test_check_tailored_increments_version_on_change_and_fails_on_violation(tailor_run, run_cvt):
    t = _golden("tailored")
    _put(tailor_run, "tailored.json", t)
    assert run_cvt("--json", "check-tailored", tailor_run.name).returncode == 0
    t["experience"][0]["bullets"][1]["text"] += " Added Linkerd."
    t["experience"][0]["bullets"][0]["id"] = "t-exp-1.b7"  # numbering slip is harmless
    _put(tailor_run, "tailored.json", t)
    proc = run_cvt("--json", "check-tailored", tailor_run.name)
    env = _env(proc)
    assert proc.returncode == 1 and env["error"]["id"] == "E_CHECK_FAILED"
    assert [v["item_id"] for v in env["data"]["violations"]] == ["t-exp-1.b2"]
    assert "'Linkerd'" in env["data"]["violations"][0]["message"]
    saved = json.loads((tailor_run / "tailored.json").read_text(encoding="utf-8"))
    assert saved["version"] == 2 and saved["experience"][0]["bullets"][0]["id"] == "t-exp-1.b1"
    assert sorted(p.name for p in (tailor_run / "tailored.history").glob("v*.json")) == ["v1.json", "v2.json"]
    assert _gates(tailor_run)["provenance"] == "fail" and _validation(tailor_run)["passed"] is False
    st = state.load(tailor_run)
    assert st["status"] == "failed" and st["stage"] == "tailored"  # stage unchanged on failure
    assert "brief fix" in st["next_action"]


def test_check_tailored_first_failure_keeps_stage(tailor_run, run_cvt):
    t = _golden("tailored")
    t["summary"]["text"] += " Expecting $240,000 per year."
    _put(tailor_run, "tailored.json", t)
    proc = run_cvt("--json", "check-tailored", tailor_run.name)
    env = _env(proc)
    assert proc.returncode == 1
    assert {v["code"] for v in env["data"]["violations"]} == {"unsupported_number", "logistics_leak"}
    gates = _gates(tailor_run)
    assert gates["provenance"] == "fail" and gates["logistics_leak"] == "fail"
    assert state.load(tailor_run)["stage"] == "answers_applied"


def test_check_tailored_placeholders_warn_in_draft_and_fail_otherwise(tailor_run, run_cvt):
    t = _golden("tailored")
    t["experience"][0]["bullets"][0]["text"] = "Built pipelines for [[CONFIRM: how many services]] services."
    _put(tailor_run, "tailored.json", t)
    proc = run_cvt("--json", "check-tailored", tailor_run.name)
    assert proc.returncode == 1 and _gates(tailor_run)["placeholders"] == "fail"
    proc = run_cvt("--json", "check-tailored", tailor_run.name, "--draft")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    env = _env(proc)
    assert env["data"]["gates"]["placeholders"] == "warn" and env["data"]["warnings"]
    assert _validation(tailor_run)["draft"] is True and _validation(tailor_run)["passed"] is True


def test_check_tailored_attestation_status_gate_after_approval(tailor_run, run_cvt, workspace):
    _put(tailor_run, "tailored.json", _golden("tailored"))
    assert run_cvt("--json", "check-tailored", tailor_run.name).returncode == 0
    _set_stage(tailor_run, "approved")
    proc = run_cvt("--json", "check-tailored", tailor_run.name)
    assert proc.returncode == 1 and _gates(tailor_run)["attestation_status"] == "fail"
    assert _env(proc)["data"]["violations"][0]["code"] == "attestation_not_active"
    _store(workspace, tailor_run.name, "active")
    proc = run_cvt("--json", "check-tailored", tailor_run.name)
    assert proc.returncode == 0 and _gates(tailor_run)["attestation_status"] == "pass"
    assert state.load(tailor_run)["stage"] == "approved"  # only answers_applied advances to tailored


def test_check_tailored_revoked_attestation_fails(tailor_run, run_cvt, workspace):
    _store(workspace, tailor_run.name, "revoked")
    _put(tailor_run, "tailored.json", _golden("tailored"))
    proc = run_cvt("--json", "check-tailored", tailor_run.name)
    assert proc.returncode == 1
    codes = {v["code"] for v in _env(proc)["data"]["violations"]}
    assert "unknown_ref" in codes and "attestation_not_active" not in codes


def test_check_tailored_schema_failure_writes_validation(tailor_run, run_cvt):
    t = _golden("tailored")
    del t["summary"]["text"]
    _put(tailor_run, "tailored.json", t)
    proc = run_cvt("--json", "check-tailored", tailor_run.name)
    assert proc.returncode == 1
    gates = _gates(tailor_run)
    assert gates["schema"] == "fail" and gates["provenance"] == "skipped"
    assert not (tailor_run / "tailored.history").exists()


def test_check_tailored_requires_stage_and_artifact(run_dir, run_cvt):
    proc = run_cvt("--json", "check-tailored", run_dir.name)
    assert proc.returncode == 4 and _env(proc)["error"]["id"] == "E_STAGE"


def test_check_tailored_output_is_capped(tailor_run, run_cvt):
    t = _golden("tailored")
    for i in range(14):
        t["skills"][0]["items"].append({"name": f"Zorblax{i}", "source_refs": ["skl-1"]})
    _put(tailor_run, "tailored.json", t)
    proc = run_cvt("--json", "check-tailored", tailor_run.name)
    env = _env(proc)
    assert proc.returncode == 1 and len(env["data"]["violations"]) == 10 and env["data"]["violations_more"] == 4  # 14 bad skills
    human = run_cvt("check-tailored", tailor_run.name)
    assert human.stderr.count("\n") <= 15 and "+4 more (use --all)" in human.stderr
