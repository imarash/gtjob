"""WP-29: stage packets (`cvt brief`), digests, prematch, seeds, fix packets and budgets."""

from __future__ import annotations

import copy
import datetime
import json
import math
from pathlib import Path

import pytest

from cvtlib import briefs, cli, jsonio, state, usage
from cvtlib.errors import CvtError

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
GOLDEN = FIXTURES / "golden" / "junior"
CV = FIXTURES / "cv" / "jamie-rivera-junior.txt"
JD_FILE = FIXTURES / "jds" / "junior-devops-engineer.md"
PERSON = "jamie-rivera"
TODAY = datetime.date(2026, 10, 26)
REPLY = "I used Helm at Brightfield to package two internal services"
STAGES = tuple(briefs.STAGE_SPECS)
MATCH_TRIM_BUDGET = 2300  # fixed packet text (rules + output shape) plus room for a trimmed digest


def _golden(name: str) -> dict:
    return json.loads((GOLDEN / f"{name}.json").read_text(encoding="utf-8"))


def _atts(**changes) -> list[dict]:
    rows = json.loads((FIXTURES / "provenance" / "attestations.json").read_text(encoding="utf-8"))
    return [dict(a, **changes) for a in rows if a["id"] == "att-001"]


def _make_run(workspace: Path, slug: str = "jr", *, stage: str = "tailored", plan: bool = True,
              tailored: bool = True) -> Path:
    run_dir = state.create_run(CV, "file", str(JD_FILE), None, {"page_target": 1}, slug=slug)
    st = state.load(run_dir)
    st["person_slug"] = PERSON
    (run_dir / "cv.txt").write_text(CV.read_text(encoding="utf-8"), encoding="utf-8")
    (run_dir / "jd.txt").write_text(JD_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    state.record_artifact(run_dir, st, "cv_txt", "cv.txt", cascade=False)
    state.record_artifact(run_dir, st, "jd_txt", "jd.txt", cascade=False)
    for art, fname in (("profile", "profile.json"), ("jd", "jd.json"), ("match", "match.json"),
                       ("questions", "questions.json")):
        (run_dir / fname).write_bytes((GOLDEN / fname).read_bytes())
        state.record_artifact(run_dir, st, art, fname, cascade=False)
    rnd = _golden("answers.round")
    jsonio.dump_json({"schema_version": "1", "run_id": run_dir.name, "rounds": [rnd]}, run_dir / "answers.json")
    if plan:
        (run_dir / "tailor-plan.json").write_bytes((GOLDEN / "tailor-plan.json").read_bytes())
    if tailored:
        t = _golden("tailored")
        t["run_id"] = run_dir.name
        jsonio.dump_json(t, run_dir / "tailored.json")
        state.record_artifact(run_dir, st, "tailored", "tailored.json", cascade=False)
    state.set_stage(st, stage)
    st["checkpoints"] = {"cp1": "done", "cp2": "not_started"}
    state.save(run_dir, st)
    store = {"schema_version": "1", "person_slug": PERSON, "next_seq": 2, "attestations": _atts(run_id=run_dir.name)}
    jsonio.dump_json(store, workspace / "profiles" / PERSON / "attestations.json")
    return run_dir


def _cvt(capsys, *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def _build(run_dir: Path, stage: str, **kw) -> briefs.Brief:
    if stage in ("answer_parse", "change_request"):
        kw.setdefault("reply", REPLY if stage == "answer_parse" else "Make t-exp-1.b2 shorter")
    return briefs.build_packet(stage, run_dir, **kw)


def _fail_run(run_dir: Path, plan: dict | None = None) -> None:
    """Leave the run failed after an `assemble` whose plan cites an invented employer."""
    plan = plan or _golden("tailor-plan")
    plan["experience"][0]["bullets"][1]["text"] = "Replaced manual console changes at Contoso Labs with Terraform."
    jsonio.dump_json(plan, run_dir / "tailor-plan.json")
    assert cli.main(["assemble", run_dir.name]) == 1


# --- budgets and core ---------------------------------------------------------------------------------------
def test_estimate_tokens_uses_chars_per_token():
    assert briefs.estimate_tokens("") == 0
    assert briefs.estimate_tokens("x" * 38) == 10
    assert briefs.estimate_tokens("x" * 39) == 11


def test_budgets_file_matches_the_contract():
    cfg = briefs.budgets()
    assert cfg["chars_per_token"] == 3.8 and cfg["core_max_lines"] == 60 and cfg["seed_min_score"] == 0.6
    assert cfg["max_fix_attempts"] == 2 and cfg["excerpt_chars"] == 240 and cfg["outline_excerpt_chars"] == 80
    assert {k: (v["input"], v["output"]) for k, v in cfg["stages"].items()} == {
        "profile": (1500, 8000), "jd": (3000, 5000), "match": (7000, 6000), "questions": (4000, 3000),
        "answer_parse": (2500, 2000), "tailor": (8000, 8000), "change_request": (3000, 2000),
        "fix": (2500, 1500), "critic": (4000, 3000)}


@pytest.mark.parametrize("name", ["stage-profile", "stage-jd", "stage-match", "stage-tailor", "truthfulness",
                                  "style-guide", "checkpoint-questions", "answer-parsing", "change-requests",
                                  "critic-rubric"])
def test_every_guide_has_a_core_within_the_line_limit(name):
    core = briefs.guide_core(name)
    assert core and "## " not in core and len(core.splitlines()) <= briefs.budgets()["core_max_lines"]


def test_guide_without_core_raises(monkeypatch, tmp_path):
    bad = tmp_path / "stage-bad.md"
    bad.write_text("# Stage: bad\n\n## Details\n\nno core here\n", encoding="utf-8")
    monkeypatch.setattr(briefs, "_guide_path", lambda name: bad)
    with pytest.raises(CvtError) as exc:
        briefs.guide_core("stage-bad")
    assert exc.value.err_id == "E_GUIDE_NO_CORE" and exc.value.code == 1


def test_overlong_core_warns_but_builds(workspace, monkeypatch):
    run_dir = _make_run(workspace)
    cfg = copy.deepcopy(briefs.budgets())
    cfg["core_max_lines"] = 5
    monkeypatch.setattr(briefs, "budgets", lambda: cfg)
    result = _build(run_dir, "jd")
    assert any("Core has" in w for w in result.warnings) and "warning[budget]" in result.packet


# --- every stage fits its budget ---------------------------------------------------------------------------
@pytest.mark.parametrize("stage", [s for s in STAGES if s != "fix"])
def test_stage_packet_builds_and_fits_budget(workspace, stage):
    run_dir = _make_run(workspace)
    result = _build(run_dir, stage)
    assert result.est_tokens <= result.budget, (stage, result.est_tokens, result.budget)
    assert result.packet.startswith(f"# Stage: {stage} (run {run_dir.name})")
    for heading in ("## Rules", "## Inputs", "## Output"):
        assert heading in result.packet
    assert "warning[budget]" not in result.packet
    assert (run_dir / "briefs" / f"{stage}.md").read_text(encoding="utf-8") == result.packet


def test_fix_packet_builds_and_fits_budget(workspace):
    run_dir = _make_run(workspace)
    _fail_run(run_dir)
    result = _build(run_dir, "fix")
    assert result.est_tokens <= result.budget and "attempt 1 of 2" in result.packet


def test_packet_layout_and_preamble(workspace):
    run_dir = _make_run(workspace)
    packet = _build(run_dir, "tailor").packet
    head = packet.splitlines()
    assert head[0] == f"# Stage: tailor (run {run_dir.name})" and head[1] == ""
    assert "untrusted_document" in head[2] and head[3].startswith("Write: out/") and head[4].startswith("Check: cvt assemble")
    assert packet.index("## Rules") < packet.index("## Inputs") < packet.index("## Output")
    assert "file: out/" in packet and "schema: tailor-plan" in packet


def test_full_appends_details_and_examples(workspace):
    run_dir = _make_run(workspace)
    short = _build(run_dir, "jd").packet
    full = _build(run_dir, "jd", full=True).packet
    assert "#### Details" not in short and "## Details" in full and len(full) > len(short)


def test_untrusted_text_is_wrapped(workspace):
    run_dir = _make_run(workspace)
    cv_packet = _build(run_dir, "profile").packet
    assert '<untrusted_document name="cv.txt">' in cv_packet and cv_packet.rstrip().count("</untrusted_document>") == 1
    jd_packet = _build(run_dir, "jd").packet
    assert '<untrusted_document name="jd.txt">' in jd_packet
    first_cv_line = CV.read_text(encoding="utf-8").splitlines()[0]
    assert first_cv_line in cv_packet and "1|" in cv_packet


def test_profile_packet_budget_is_input_plus_numbered_cv(workspace):
    result = _build(_make_run(workspace), "profile")
    assert result.budget > briefs.budgets()["stages"]["profile"]["input"]


def test_reply_is_required_and_kept_whole(workspace, capsys):
    run_dir = _make_run(workspace)
    code, _out, err = _cvt(capsys, "brief", "answer_parse", run_dir.name)
    assert code == 2 and "E_REPLY_REQUIRED" in err
    packet = _build(run_dir, "answer_parse").packet
    assert REPLY in packet and "q-1" in packet and "helm=Helm" in packet and "role labels:" in packet


def test_questions_packet_lists_gaps_and_attestations(workspace):
    packet = _build(_make_run(workspace), "questions").packet
    assert "req-6 none must" in packet and "att-001 skill" in packet and "iss-1" in packet


def test_match_packet_has_digests_and_prematch(workspace):
    run_dir = _make_run(workspace)
    packet = _build(run_dir, "match").packet
    assert "# JD digest" in packet and "# profile digest" in packet and "# prematch" in packet
    assert "req-3: " in packet
    digest = (run_dir / "digest.txt").read_text(encoding="utf-8")
    assert digest.startswith("# profile digest")
    st = state.load(run_dir)
    assert state.artifact(st, "digest") is not None and st["stage"] == "tailored"


def test_tailor_packet_contents(workspace):
    packet = _build(_make_run(workspace), "tailor").packet
    for needle in ("# JD digest", "# profile digest", "# match", "# answers", "r1 q-1 attest", "att-001 skill",
                   "seniority:", "Never retype facts"):
        assert needle in packet


def test_stage_requirements(workspace, capsys):
    run_dir = _make_run(workspace, stage="matched")
    code, _out, err = _cvt(capsys, "brief", "tailor", run_dir.name)
    assert code == 4 and "E_STAGE" in err
    st = state.load(run_dir)
    st["checkpoints"]["cp1"] = "skipped"
    state.save(run_dir, st)
    assert _cvt(capsys, "brief", "tailor", run_dir.name)[0] == 0


# --- digest: format, relevance, trimming -------------------------------------------------------------------
def test_digest_format_matches_section_14_3():
    digest = briefs.profile_digest(_golden("profile"), _atts(), _golden("jd"), 5000, today=TODAY)
    lines = digest.splitlines()
    assert lines[0] == "# profile digest"
    assert "exp-1 Brightfield Logistics | Junior DevOps Engineer | Columbus, OH | 2024-02..present | employee" in lines
    assert any(ln.startswith(" b1 Built GitHub Actions") for ln in lines)
    assert 'att-001 skill "Helm" scope items -> exp-1 [active]' in lines
    assert any(ln.startswith("skl-1 Cloud & Infrastructure: AWS, ECS") for ln in lines)
    assert not any("hidden" in ln for ln in lines)


def _big_profile(highlights: int) -> dict:
    profile = _golden("profile")
    work = profile["work"][0]
    work["highlights"] = [{"id": f"exp-1.b{n}", "kind": "bullet",
                           "text": f"Delivered change number {n} for the platform team with steady, careful rollouts "
                                   f"and clear handovers {'and notes ' * 6}"} for n in range(1, highlights + 1)]
    return profile


def test_digest_trims_bullets_with_hidden_hints_and_keeps_headers():
    profile = _big_profile(40)
    digest = briefs.profile_digest(profile, _atts(), _golden("jd"), 300, today=TODAY)
    assert "(+" in digest and "bullets hidden; cvt brief tailor RUN --item exp-1)" in digest
    assert digest.count("\n b") < 40
    for header in ("exp-1 Brightfield", "exp-2 Cedar Valley College"):
        assert header in digest
    assert 'att-001 skill "Helm"' in digest
    assert briefs.estimate_tokens(digest) <= 300 + 60  # headers and attestations are the only overshoot


def test_digest_fill_is_by_relevance_then_profile_order():
    profile = _big_profile(6)
    profile["work"][0]["highlights"][4]["text"] = "Wrote Terraform modules for AWS networking."
    digest = briefs.profile_digest(profile, [], _golden("jd"), 330, today=TODAY)
    assert " b5 Wrote Terraform modules" in digest  # the relevant bullet wins over earlier ones


def test_digest_is_profile_order_without_a_jd():
    digest = briefs.profile_digest(_big_profile(6), [], None, 330, today=TODAY)
    shown = [ln.split()[0] for ln in digest.splitlines() if ln.startswith(" b")]
    assert shown == [f"b{n}" for n in range(1, len(shown) + 1)] and 0 < len(shown) < 6


def test_digest_recency_and_attestation_boost():
    profile = _golden("profile")
    profile["work"][1]["highlights"][1]["text"] = "Wrote Terraform modules for AWS networking."
    jd = _golden("jd")
    plain = briefs._relevance(profile, [], jd, TODAY)
    boosted = briefs._relevance(profile, _atts(), jd, TODAY)
    assert boosted["exp-1.b1"] == plain["exp-1.b1"] + 2 and boosted["exp-2.b1"] == plain["exp-2.b1"]
    assert plain["exp-1.b2"] > 0 and plain["exp-1.b2"] % 1.5 == 0  # the current job gets the 1.5x boost
    # exp-2 ended 2023-12: within 5 years of 2026-10, outside them in 2035
    late = briefs._relevance(profile, [], jd, datetime.date(2035, 1, 1))
    assert plain["exp-2.b2"] > 0 and late["exp-2.b2"] == plain["exp-2.b2"] / 1.5


def test_digest_forced_ids_are_shown_in_full():
    profile = _big_profile(30)
    digest = briefs.profile_digest(profile, [], _golden("jd"), 100, today=TODAY, full_ids=frozenset({"exp-1.b25"}))
    assert " b25 " in digest


def test_prematch_top_candidates_with_terms():
    pm = briefs.prematch(_golden("profile"), _atts(), _golden("jd"))
    req3 = next(r for r in _golden("jd")["requirements"] if r["id"] == "req-3")
    assert pm["req-3"] and all(len(rows) <= 5 for rows in pm.values())
    first = pm["req-3"][0]
    assert first["terms"] and any(t.lower() in " ".join(req3["keywords"]).lower() for t in first["terms"])
    assert any(r["ref"] == "att-001" for r in pm["req-6"])


def test_match_packet_trims_synthetic_profile_and_keeps_must_haves(workspace, monkeypatch):
    run_dir = _make_run(workspace)
    jsonio.dump_json(_big_profile(40), run_dir / "profile.json")
    cfg = copy.deepcopy(briefs.budgets())
    cfg["stages"]["match"]["input"] = MATCH_TRIM_BUDGET
    monkeypatch.setattr(briefs, "budgets", lambda: cfg)
    result = _build(run_dir, "match")
    assert result.est_tokens <= MATCH_TRIM_BUDGET and "bullets hidden; cvt brief" in result.packet
    musts = [r["id"] for r in _golden("jd")["requirements"] if r["kind"] == "must"]
    assert all(f"{rid} must" in result.packet for rid in musts)
    assert 'att-001 skill "Helm"' in result.packet


def test_over_budget_packet_gets_a_budget_warning(workspace, monkeypatch):
    run_dir = _make_run(workspace)
    cfg = copy.deepcopy(briefs.budgets())
    cfg["stages"]["match"]["input"] = 300
    monkeypatch.setattr(briefs, "budgets", lambda: cfg)
    result = _build(run_dir, "match")
    assert "warning[budget]: packet ~" in result.packet.splitlines()[-1]
    assert "req-1 " in result.packet and 'att-001 skill "Helm"' in result.packet  # never trimmed


def test_packets_are_deterministic(workspace):
    run_dir = _make_run(workspace)
    for stage in ("match", "questions", "tailor", "critic", "change_request"):
        assert _build(run_dir, stage).packet == _build(run_dir, stage).packet
    first = (run_dir / "digest.txt").read_bytes()
    _build(run_dir, "tailor")
    assert (run_dir / "digest.txt").read_bytes() == first


# --- reuse across runs --------------------------------------------------------------------------------------
def test_jd_cache_hit_copies_jd_json(workspace, capsys):
    prior = _make_run(workspace, "prior")
    new = _make_run(workspace, "new", stage="profiled")
    (new / "jd.json").unlink()
    code, out, _err = _cvt(capsys, "--json", "brief", "jd", new.name)
    env = json.loads(out)
    assert code == 0 and env["data"]["cache_hit"] is True and env["data"]["cache_from"] == prior.name
    assert env["next_action"].endswith(f"jd-check {new.name}")
    assert (new / "jd.json").read_bytes() == (prior / "jd.json").read_bytes()
    assert "cache hit: jd.json copied from" in env["messages"][0]


def test_jd_cache_miss_builds_a_packet(workspace):
    new = _make_run(workspace, "solo", stage="profiled")
    (new / "jd.json").unlink()
    result = _build(new, "jd")
    assert result.cache_hit_from == "" and "# Stage: jd" in result.packet


def test_jd_cache_ignores_unchecked_or_different_jd(workspace):
    prior = _make_run(workspace, "prior")
    st = state.load(prior)
    st["artifacts"] = [a for a in st["artifacts"] if a["name"] != "jd"]  # never checked
    state.save(prior, st)
    new = _make_run(workspace, "new", stage="profiled")
    (new / "jd.json").unlink()
    assert _build(new, "jd").cache_hit_from == ""


def _make_prior(workspace: Path, *, approved: bool = True, jd_mutate=None) -> Path:
    prior = _make_run(workspace, "prior", stage="approved")
    st = state.load(prior)
    st["checkpoints"]["cp2"] = "done" if approved else "pending"
    state.save(prior, st)
    if jd_mutate:
        jd = _golden("jd")
        jd_mutate(jd)
        jsonio.dump_json(jd, prior / "jd.json")
    return prior


def test_similar_runs_score_and_order(workspace):
    _make_prior(workspace)
    _make_run(workspace, "other")
    jd = _golden("jd")
    rows = briefs.similar_runs(PERSON, jd, exclude="nothing")
    assert len(rows) == 2 and all(r["score"] == 1.0 for r in rows)
    assert {r["run_slug"]: r["approved"] for r in rows}[next(r["run_slug"] for r in rows if "prior" in r["run_slug"])]
    other_person = briefs.similar_runs("someone-else", jd, exclude="")
    assert other_person == []


def _scramble_keywords(jd: dict) -> None:
    for r in jd["requirements"]:
        r["keywords"] = [f"zz{n}-{k}" for n, k in enumerate(r["keywords"])]


def test_seed_included_when_score_is_high_and_run_approved(workspace):
    prior = _make_prior(workspace)
    new = _make_run(workspace, "new")
    packet = _build(new, "tailor").packet
    assert f"# Seed (run {prior.name})" in packet and 'set seed_run to "' in packet
    assert '"schema_version":"1"' in packet


def test_seed_omitted_when_score_is_low_or_run_not_approved(workspace):
    prior = _make_prior(workspace, jd_mutate=_scramble_keywords)
    new = _make_run(workspace, "new")
    assert briefs.similar_runs(PERSON, _golden("jd"), new.name)[0]["score"] < 0.6
    assert "# Seed" not in _build(new, "tailor").packet
    st = state.load(prior)
    st["checkpoints"]["cp2"] = "pending"
    state.save(prior, st)
    (prior / "jd.json").write_bytes((GOLDEN / "jd.json").read_bytes())
    assert "# Seed" not in _build(new, "tailor").packet


def test_seed_is_the_first_thing_trimmed(workspace, monkeypatch):
    prior = _make_prior(workspace)
    new = _make_run(workspace, "new")
    for run_dir in (prior, new):  # the seed needs the same profile (same CV) in both runs
        jsonio.dump_json(_big_profile(40), run_dir / "profile.json")
        st = state.load(run_dir)
        state.record_artifact(run_dir, st, "profile", "profile.json", cascade=False)
        state.save(run_dir, st)
    cfg = copy.deepcopy(briefs.budgets())
    monkeypatch.setattr(briefs, "budgets", lambda: cfg)
    cfg["stages"]["tailor"]["input"] = 6000
    roomy = _build(new, "tailor")
    assert "# Seed" in roomy.packet and roomy.est_tokens <= 6000
    cfg["stages"]["tailor"]["input"] = 3000
    tight = _build(new, "tailor")
    assert tight.est_tokens <= 3000 and "# Seed" not in tight.packet and "bullets hidden" in tight.packet


# --- fix packets --------------------------------------------------------------------------------------------
def test_fix_packet_lists_only_offending_items(workspace):
    run_dir = _make_run(workspace)
    _fail_run(run_dir)
    packet = _build(run_dir, "fix").packet
    assert "failed: assemble (attempt 1 of 2)" in packet and "- t-exp-1.b2:" in packet and "Contoso" in packet
    offending = packet.split("offending items:")[1].split("## Output")[0]
    assert offending.count("\nt-exp-1.b2:") == 1 and "t-exp-1.b1" not in offending and "t-exp-2" not in offending
    assert "Patch, don't regenerate" in packet and "file: out/" in packet and "tailor-plan.json" in packet
    rules = packet.split("## Rules")[1].split("## Inputs")[0]
    assert "Never retype facts" in rules and "Self-check" not in rules and "Details" not in rules


def test_fix_packet_caps_violations_at_ten(workspace):
    run_dir = _make_run(workspace)
    plan = _golden("tailor-plan")
    plan["skills"][0]["items"] = [{"name": f"Zzzskill{n}", "source_refs": []} for n in range(15)]
    jsonio.dump_json(plan, run_dir / "tailor-plan.json")
    assert cli.main(["assemble", run_dir.name]) == 1
    packet = _build(run_dir, "fix").packet
    assert "violations (10 of 15)" in packet and packet.count("\n- t-skl-1:") == 10


def test_fix_stops_after_max_attempts(workspace, capsys):
    run_dir = _make_run(workspace)
    _fail_run(run_dir)
    assert _cvt(capsys, "brief", "fix", run_dir.name)[0] == 0
    assert _cvt(capsys, "brief", "fix", run_dir.name)[0] == 0
    assert cli.main(["assemble", run_dir.name]) == 1  # a patch that still fails does not reset the counter
    capsys.readouterr()
    code, _out, err = _cvt(capsys, "brief", "fix", run_dir.name)
    assert code == 1 and "stop: show these violations to the user" in err and "t-exp-1.b2" in err
    assert len(err.strip().splitlines()) <= 15


def test_fix_attempt_counter_resets_after_a_pass(workspace, capsys):
    run_dir = _make_run(workspace)
    _fail_run(run_dir)
    assert _cvt(capsys, "brief", "fix", run_dir.name)[0] == 0
    jsonio.dump_json(_golden("tailor-plan"), run_dir / "tailor-plan.json")
    assert _cvt(capsys, "assemble", run_dir.name)[0] == 0
    _fail_run(run_dir)
    assert "attempt 1 of 2" in _build(run_dir, "fix").packet


def test_fix_without_a_failure_is_a_state_error(workspace, capsys):
    run_dir = _make_run(workspace)
    code, _out, err = _cvt(capsys, "brief", "fix", run_dir.name)
    assert code == 4 and "E_NOTHING_TO_FIX" in err


def test_fix_for_jd_check_shows_the_offending_requirement(workspace, capsys):
    run_dir = _make_run(workspace, stage="profiled")
    st = state.load(run_dir)
    st["artifacts"] = [a for a in st["artifacts"] if a["name"] != "jd"]
    state.save(run_dir, st)
    jd = _golden("jd")
    jd["requirements"][2]["id"] = "req-1"
    jsonio.dump_json(jd, run_dir / "jd.json")
    assert cli.main(["jd-check", run_dir.name]) == 1
    capsys.readouterr()
    packet = _build(run_dir, "fix").packet
    assert "failed: jd-check" in packet and "req-1" in packet and "file: out/" in packet and "jd.json" in packet


# --- items, change requests, critic ------------------------------------------------------------------------
def test_item_prints_only_that_item_and_records_no_file(workspace):
    run_dir = _make_run(workspace)
    result = _build(run_dir, "tailor", item="exp-1")
    assert result.packet.startswith("exp-1 Brightfield Logistics") and "## Rules" not in result.packet
    assert " exp-1.b6 [tools] " in result.packet
    assert not (run_dir / "briefs" / "tailor.md").exists()
    assert "exp-1.b2" in _build(run_dir, "match", item="exp-1.b2").packet


def test_item_unknown_id_is_a_state_error(workspace, capsys):
    run_dir = _make_run(workspace)
    code, _out, err = _cvt(capsys, "brief", "tailor", run_dir.name, "--item", "exp-9")
    assert code == 4 and "E_UNKNOWN_ITEM" in err


def test_change_request_names_items_by_id_employer_and_index(workspace):
    run_dir = _make_run(workspace)
    packet = _build(run_dir, "change_request", reply="Shorten t-exp-1.b2 and drop the Cedar Valley College role").packet
    assert "# outline" in packet and "t-exp-1.b1 [kept]" in packet
    named = packet.split("# items named in the reply")[1].split("## Output")[0]
    assert "t-exp-1.b2 [rewritten] refs=exp-1.b2: Replaced manual console changes" in named
    assert "t-exp-2 Cedar Valley College" in named and "t-exp-2.b1" in named
    from cvtlib import diff
    order = [row["id"] for row in diff.diff_items(_golden("tailored"), _golden("profile"), None)]
    by_index = _build(run_dir, "change_request", reply="[2] is too long").packet
    assert f"{order[1]}" in by_index.split("# items named in the reply")[1]
    outline = packet.split("# outline")[1].split("# reply")[0]
    assert all(len(ln) < 140 for ln in outline.splitlines())  # 80-character excerpts


def test_critic_packet_has_text_only_unless_visual(workspace):
    run_dir = _make_run(workspace)
    plain = _build(run_dir, "critic").packet
    assert "# validation" in plain and "# pages" not in plain
    (run_dir / "pages").mkdir()
    (run_dir / "pages" / "page-1.png").write_bytes(b"\x89PNG")
    assert "pages/page-1.png" in _build(run_dir, "critic", visual=True).packet


# --- usage and CLI ------------------------------------------------------------------------------------------
def test_usage_jsonl_gets_one_line_per_packet(workspace):
    run_dir = _make_run(workspace)
    for stage in ("jd", "match", "tailor"):
        _build(run_dir, stage)
    rows = [json.loads(ln) for ln in (run_dir / "usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["stage"] for r in rows] == ["jd", "match", "tailor"] and {r["kind"] for r in rows} == {"packet"}
    assert all(r["est_tokens"] > 0 for r in rows)
    assert usage.usage_totals(run_dir)["packets"].keys() == {"jd", "match", "tailor"}


def test_cli_brief_prints_the_packet_and_json_embeds_it(workspace, capsys):
    run_dir = _make_run(workspace)
    code, out, _err = _cvt(capsys, "brief", "match", run_dir.name)
    assert code == 0 and out.startswith("# Stage: match") and out.endswith("\n")
    code, out, _err = _cvt(capsys, "--json", "brief", "match", run_dir.name)
    env = json.loads(out)
    assert code == 0 and env["data"]["packet"].startswith("# Stage: match") and env["data"]["est_tokens"] > 0
    assert env["data"]["path"] == "briefs/match.md" and len(out.strip().splitlines()) == 1


def test_cli_brief_reply_file_and_latest(workspace, capsys, tmp_path):
    run_dir = _make_run(workspace)
    reply = tmp_path / "reply.txt"
    reply.write_text(REPLY, encoding="utf-8")
    code, out, _err = _cvt(capsys, "brief", "answer_parse", "--reply-file", str(reply))
    assert code == 0 and REPLY in out and run_dir.name in out
    code, _out, err = _cvt(capsys, "brief", "answer_parse", "--reply-file", str(tmp_path / "missing.txt"))
    assert code == 5 and "E_REPLY_FILE" in err


def test_cli_brief_unknown_stage_is_a_usage_error(workspace, capsys):
    _make_run(workspace)
    code, _out, err = _cvt(capsys, "brief", "bogus")
    assert code == 2 and "E_USAGE" in err


# --- output shapes and copy-values (WP-FIX-3-1) ------------------------------------------------------------
AI_STAGES = tuple(s for s in STAGES if s != "fix")
FULL_HASH_RE = r"[0-9a-f]{64}"


def _shape_line(packet: str) -> str:
    lines = [ln for ln in packet.splitlines() if ln.startswith("shape: ")]
    assert len(lines) == 1, lines
    return lines[0].removeprefix("shape: ")


def _required_of(schema_name: str) -> list[str]:
    from cvtlib import schemas
    base, _, frag = schema_name.partition("#")
    node = schemas.load_schema(base)
    if frag:
        node = node["$defs"][frag.rsplit("/", 1)[1]]
    return node["required"]


@pytest.mark.parametrize("stage", AI_STAGES)
def test_every_ai_packet_shows_a_shape_whose_keys_are_the_required_ones(workspace, stage):
    run_dir = _make_run(workspace)
    packet = _build(run_dir, stage).packet
    shape = json.loads(_shape_line(packet))
    assert list(shape) == _required_of(briefs.STAGE_SPECS[stage].schema)
    out = packet.split("## Output")[1].splitlines()
    assert out.index(next(ln for ln in out if ln.startswith("shape: "))) == \
        out.index(next(ln for ln in out if ln.startswith("schema: "))) + 1


def test_schema_skeleton_rules():
    shape = json.loads(briefs.schema_skeleton("jd"))
    assert shape["schema_version"] == "1" and shape["jd_sha256"] == "" and shape["noise"] == [shape["noise"][0]]
    assert "|" in shape["requirements"][0]["kind"]
    rnd = json.loads(briefs.schema_skeleton("answers#/$defs/round"))
    assert "items" in rnd and isinstance(rnd["items"], list)
    assert briefs.schema_skeleton("jd") == briefs.schema_skeleton("jd") and " " not in briefs.schema_skeleton("jd")


def test_shape_survives_budget_trimming(workspace, monkeypatch):
    run_dir = _make_run(workspace)
    cfg = copy.deepcopy(briefs.budgets())
    cfg["stages"]["tailor"]["input"] = 1
    monkeypatch.setattr(briefs, "budgets", lambda: cfg)
    assert _shape_line(_build(run_dir, "tailor").packet)


def test_jd_packet_carries_the_full_hash_and_source(workspace):
    run_dir = _make_run(workspace)
    inputs = state.load(run_dir)["inputs"]["jd"]
    packet = _build(run_dir, "jd").packet
    assert f"jd_sha256: {inputs['sha256']}" in packet and len(inputs["sha256"]) == 64
    assert f"source: kind={inputs['kind']} ref={inputs['original_ref']}" in packet
    assert packet.index("jd_sha256:") < packet.index("<untrusted_document name")


@pytest.mark.parametrize("stage", ["match", "questions", "change_request", "critic"])
def test_stages_that_copy_run_id_print_it(workspace, stage):
    run_dir = _make_run(workspace)
    assert f"\nrun_id: {run_dir.name}\n" in _build(run_dir, stage).packet


def test_fix_packet_for_a_wrong_jd_hash_repeats_the_full_hash(workspace, capsys):
    run_dir = _make_run(workspace, stage="profiled")
    st = state.load(run_dir)
    st["artifacts"] = [a for a in st["artifacts"] if a["name"] != "jd"]
    state.save(run_dir, st)
    jd = _golden("jd")
    jd["jd_sha256"] = "0" * 64
    jsonio.dump_json(jd, run_dir / "jd.json")
    assert cli.main(["jd-check", run_dir.name]) == 1
    capsys.readouterr()
    inputs = state.load(run_dir)["inputs"]["jd"]
    packet = _build(run_dir, "fix").packet
    assert f"jd_sha256: {inputs['sha256']}" in packet
    assert f"source: kind={inputs['kind']} ref={inputs['original_ref']}" in packet
    assert "shape: " not in packet  # a hash mismatch is not a schema error


def test_fix_packet_shows_the_shape_only_for_schema_errors(workspace, capsys):
    run_dir = _make_run(workspace, stage="profiled")
    st = state.load(run_dir)
    st["artifacts"] = [a for a in st["artifacts"] if a["name"] != "jd"]
    state.save(run_dir, st)
    jd = _golden("jd")
    del jd["noise"]
    jsonio.dump_json(jd, run_dir / "jd.json")
    assert cli.main(["jd-check", run_dir.name]) == 1
    capsys.readouterr()
    packet = _build(run_dir, "fix").packet
    assert list(json.loads(_shape_line(packet))) == _required_of("jd")


# --- integer enums and the shape key (WP-FIX-3-8) ----------------------------------------------------------
def _values_of(node: object, key: str) -> list[object]:
    """Every value stored under `key` anywhere in a parsed shape."""
    if isinstance(node, dict):
        found = [node[key]] if key in node else []
        return found + [v for child in node.values() for v in _values_of(child, key)]
    if isinstance(node, list):
        return [v for child in node for v in _values_of(child, key)]
    return []


def test_integer_enums_show_a_copyable_integer(workspace):
    run_dir = _make_run(workspace)
    priorities = _values_of(json.loads(_shape_line(_build(run_dir, "tailor").packet)), "priority")
    assert priorities and all(type(v) is int and v == 1 for v in priorities)
    weights = _values_of(json.loads(_shape_line(_build(run_dir, "jd").packet)), "weight")
    assert weights and all(type(v) is int and v == 1 for v in weights)
    checkpoints = _values_of(json.loads(_shape_line(_build(run_dir, "answer_parse").packet)), "checkpoint")
    assert checkpoints and all(type(v) is int and v == 1 for v in checkpoints)


def test_string_enums_keep_the_pipe_form(workspace):
    run_dir = _make_run(workspace)
    jd_shape = json.loads(_shape_line(_build(run_dir, "jd").packet))
    assert "file|text|url" in _values_of(jd_shape, "kind")


def test_every_ai_shape_is_followed_by_the_shape_key(workspace):
    run_dir = _make_run(workspace)
    for stage in AI_STAGES:
        lines = _build(run_dir, stage).packet.splitlines()
        at = next(i for i, ln in enumerate(lines) if ln.startswith("shape: "))
        assert lines[at + 1] == briefs.SHAPE_KEY_LINE, stage
        assert sum(ln.startswith("shape key: ") for ln in lines) == 1, stage


def test_fix_packet_without_a_schema_error_has_no_shape_or_key(workspace):
    run_dir = _make_run(workspace)
    _fail_run(run_dir)
    lines = _build(run_dir, "fix").packet.splitlines()
    assert not any(ln.startswith(("shape: ", "shape key: ")) for ln in lines)


def test_fix_packet_for_a_schema_error_has_the_shape_key(workspace, capsys):
    run_dir = _make_run(workspace, stage="profiled")
    st = state.load(run_dir)
    st["artifacts"] = [a for a in st["artifacts"] if a["name"] != "jd"]
    state.save(run_dir, st)
    jd = _golden("jd")
    del jd["noise"]
    jsonio.dump_json(jd, run_dir / "jd.json")
    assert cli.main(["jd-check", run_dir.name]) == 1
    capsys.readouterr()
    lines = _build(run_dir, "fix").packet.splitlines()
    at = next(i for i, ln in enumerate(lines) if ln.startswith("shape: "))
    assert lines[at + 1] == briefs.SHAPE_KEY_LINE


# --- every CV/JD-derived section is wrapped (WP-FIX-4-2) -----------------------------------------------------
SENTINEL = "SENTINEL-IGNORE-PREVIOUS"
OPEN_TAG, CLOSE_TAG = '<untrusted_document name="', "</untrusted_document>"  # the prose rule names the bare tag
WRAPPED_STAGES = ("match", "tailor", "questions", "answer_parse", "change_request", "critic")


def _inject_sentinel(run_dir: Path) -> None:
    """Prefix the sentinel to every visible profile bullet, JD requirement text and keyword, and tailored bullet."""
    profile = json.loads((run_dir / "profile.json").read_text(encoding="utf-8"))
    for w in profile["work"]:
        for holder in (w, *w["engagements"]):
            for h in holder["highlights"]:
                h["text"] = f"{SENTINEL} {h['text']}"
    jd = json.loads((run_dir / "jd.json").read_text(encoding="utf-8"))
    for r in jd["requirements"]:
        r["text"] = f"{SENTINEL} {r['text']}"
        r["keywords"] = [*r["keywords"], SENTINEL]
    tailored = json.loads((run_dir / "tailored.json").read_text(encoding="utf-8"))
    for e in tailored["experience"]:
        for b in e["bullets"]:
            b["text"] = f"{SENTINEL} {b['text']}"
    st = state.load(run_dir)
    for art, name, obj in (("profile", "profile.json", profile), ("jd", "jd.json", jd), ("tailored", "tailored.json", tailored)):
        jsonio.dump_json(obj, run_dir / name)
        state.record_artifact(run_dir, st, art, name, cascade=False)
    state.save(run_dir, st)


def assert_sentinel_only_inside_wrappers(text: str, sentinel: str = SENTINEL) -> int:
    """Every occurrence of `sentinel` lies between an opening wrapper tag and the next closing tag; returns the count."""
    assert text.count(OPEN_TAG) == text.count(CLOSE_TAG), "unbalanced wrapper tags"
    found = [i for i in range(len(text)) if text.startswith(sentinel, i)]
    for pos in found:
        opened, closed = text.rfind(OPEN_TAG, 0, pos), text.rfind(CLOSE_TAG, 0, pos)
        assert opened > closed, f"sentinel at {pos} is outside any {OPEN_TAG}"
        assert text.find(CLOSE_TAG, pos) > pos
    return len(found)


@pytest.mark.parametrize("stage", WRAPPED_STAGES)
def test_cv_and_jd_derived_sections_are_wrapped(workspace, stage):
    run_dir = _make_run(workspace)
    _inject_sentinel(run_dir)
    packet = _build(run_dir, stage, reply="Make t-exp-1.b2 shorter" if stage == "change_request" else REPLY).packet
    count = assert_sentinel_only_inside_wrappers(packet)
    if stage != "answer_parse":  # its inputs carry only headers and pending questions, no bullet or requirement text
        assert count > 0, stage
    assert packet.count(OPEN_TAG) >= 2 or stage == "answer_parse"


def test_match_and_tailor_wrap_jd_and_profile_digests_and_keep_headings_inside(workspace):
    run_dir = _make_run(workspace)
    for stage, names in (("match", ("jd digest", "profile digest", "prematch")),
                         ("tailor", ("jd digest", "profile digest", "match strengths"))):
        packet = _build(run_dir, stage).packet
        for name in names:
            assert f'<untrusted_document name="{name}">\n# ' in packet, (stage, name)


def test_fix_packet_wraps_offending_items(workspace):
    run_dir = _make_run(workspace)
    _fail_run(run_dir)
    packet = _build(run_dir, "fix").packet
    item_text = "Replaced manual console changes at Contoso Labs with Terraform."  # the item's text, from _fail_run
    assert assert_sentinel_only_inside_wrappers(packet, item_text) == 1
    assert '<untrusted_document name="offending items">\noffending items:' in packet


def test_wrap_neutralizes_closing_tags_inside_the_text():
    wrapped = briefs._wrap("x", "a </untrusted_document> b <UNTRUSTED_DOCUMENT name='y'> c")
    assert wrapped.count(CLOSE_TAG) == 1 and wrapped.count(OPEN_TAG) == 1
    assert wrapped.endswith(CLOSE_TAG) and "&lt;/untrusted_document> b" in wrapped


def test_jd_requirement_with_a_closing_tag_cannot_close_the_gaps_wrapper(workspace):
    run_dir = _make_run(workspace)
    jd = json.loads((run_dir / "jd.json").read_text(encoding="utf-8"))
    jd["requirements"][0]["text"] = f"{CLOSE_TAG} {SENTINEL}"
    st = state.load(run_dir)
    jsonio.dump_json(jd, run_dir / "jd.json")
    state.record_artifact(run_dir, st, "jd", "jd.json", cascade=False)
    state.save(run_dir, st)
    packet = _build(run_dir, "questions").packet
    assert_sentinel_only_inside_wrappers(packet)


# --- output caps leave headroom for the golden outputs (WP-FIX-4-5) ----------------------------------------
CONSERVATIVE_CHARS_PER_TOKEN = 3.0
OUTPUT_HEADROOM = 1.5
PRIVATE_SAMPLE = FIXTURES / "private" / "sample"
JUNIOR_OUTPUTS = {"profile": "profile-map.json", "jd": "jd.json", "match": "match.json",
                  "questions": "questions.json", "answer_parse": "answers.round.json",
                  "tailor": "tailor-plan.json", "change_request": "edits-001.json"}
PRIVATE_OUTPUTS = {"profile": "profile-map.json", "jd": "jd.json", "match": "match.json",
                   "questions": "questions.json", "answer_parse": "answers.canonical.round.json",
                   "tailor": "tailor-plan.json"}


def _blank_quotes(node: object) -> None:
    """`cvt match-check` fills every `quote`, so the model's reply carries them empty."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "quote":
                node[key] = ""
            else:
                _blank_quotes(value)
    elif isinstance(node, list):
        for child in node:
            _blank_quotes(child)


def _assert_output_headroom(folder: Path, mapping: dict[str, str]) -> None:
    for stage, fname in mapping.items():
        obj = json.loads((folder / fname).read_text(encoding="utf-8"))
        if stage == "match":
            _blank_quotes(obj)
        chars = len(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
        cap = briefs.budgets()["stages"][stage]["output"]
        assert math.ceil(chars / CONSERVATIVE_CHARS_PER_TOKEN) * OUTPUT_HEADROOM <= cap, (stage, chars, cap)


def test_output_caps_have_headroom_for_golden_outputs():
    _assert_output_headroom(GOLDEN, JUNIOR_OUTPUTS)


def test_output_caps_have_headroom_for_private_sample_outputs():
    if not PRIVATE_SAMPLE.is_dir():
        pytest.skip("private sample fixtures are absent")
    _assert_output_headroom(PRIVATE_SAMPLE, PRIVATE_OUTPUTS)
