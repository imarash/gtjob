"""WP-10: profile helpers, profile commands, profile store, merged view, JSON Resume export."""

from __future__ import annotations

import copy
import datetime
import json
import re
from pathlib import Path

import pytest

from cvtlib import cli, jsonio, paths, profile as prof, profile_store, schemas, state

REPO = Path(__file__).resolve().parents[2]
CV_FILE = REPO / "tests/fixtures/cv/jamie-rivera-junior.txt"
GOLDEN = REPO / "tests/fixtures/golden/junior/profile.json"
PRIVATE_PROFILE = REPO / "tests/fixtures/private/sample/profile.json"
JD_TEXT = "# Junior DevOps Engineer at Example Corp\n\nAutomate things.\n"
TODAY = datetime.date(2026, 10, 25)


def golden() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def cv_text() -> str:
    return CV_FILE.read_text(encoding="utf-8")


def make_run(cv_path: Path = CV_FILE, cv: str | None = None) -> Path:
    run_dir = state.create_run(cv_path, "text", "pasted", JD_TEXT, {}, slug="junior")
    (run_dir / "cv.txt").write_text(cv if cv is not None else cv_path.read_text(encoding="utf-8"), encoding="utf-8")
    st = state.load(run_dir)
    state.record_artifact(run_dir, st, "cv_txt", "cv.txt")
    state.set_stage(st, "ingested")
    state.save(run_dir, st)
    return run_dir


def put_profile(run_dir: Path, profile: dict) -> None:
    profile["cv_sha256"] = state.load(run_dir)["inputs"]["cv"]["sha256"]
    jsonio.dump_json(profile, run_dir / "profile.json")


def cvt(capsys, *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def attestation(att_id: str, **over) -> dict:
    base = {
        "id": att_id, "type": "correction", "claim": "Intern title correction", "terms": [],
        "detail": "", "scope": {"kind": "items", "role_label": "", "item_ids": ["exp-2"], "description": ""},
        "placement": "correction_only",
        "correction": {"item_id": "exp-2", "field": "position", "old_value": "IT Support Intern",
                       "new_value": "IT Support Assistant"},
        "verbatim": "it was Assistant", "question_id": "q-1", "run_id": "r", "created_at": "2026-10-25T00:00:00Z",
        "status": "active", "status_changed_at": "2026-10-25T00:00:00Z", "caveat": "",
    }
    return {**base, **over}


# --- text normalization -----------------------------------------------------------------------------------
def test_normalize_text_maps_quotes_dashes_glyphs():
    raw = "\u2022 Don\u2019t \u201cpanic\u201d \u2013 it\u2014is\u2212fine\u200b   ok"
    assert prof.normalize_text(raw) == "Don't \"panic\" - it-is-fine ok"
    assert prof.comparable("  A\u00a0B ") == "a b"
    assert prof.normalize_text("\ufb01x") == "fix"  # NFKC ligature


# --- verbatim ---------------------------------------------------------------------------------------------
def test_golden_is_verbatim_and_tamper_is_caught():
    p = golden()
    assert prof.verify_verbatim(p, cv_text()) == []
    p["work"][0]["highlights"][0]["text"] = "Built GitHub Actions pipelines for 120 services."
    p["certificates"][0]["name"] = "AWS Certified Solutions Architect"
    p["skills"][0]["keywords"].append("Kubernetes")
    bad = prof.verify_verbatim(p, cv_text())
    assert {v["code"] for v in bad} == {"fact_mismatch"}
    assert [v["item_id"] for v in bad] == ["exp-1.b1", "cert-1", "skl-1"]
    assert "120 services" in bad[0]["message"]
    assert all(set(v) == {"code", "item_id", "message"} for v in bad)


def test_verify_verbatim_flags_date_inconsistent_with_date_text():
    p = golden()
    p["work"][0]["start_date"] = "2023-02"
    p["work"][1]["end_date"] = "2025-01"
    bad = prof.verify_verbatim(p, cv_text())
    assert [(v["code"], v["item_id"]) for v in bad] == [("fact_mismatch", "exp-1"), ("fact_mismatch", "exp-2")]
    assert "start_date '2023-02' is not consistent with date_text" in bad[0]["message"]


def test_date_consistency_unit():
    assert prof.date_consistency("2017-03", "Sept 2014 - March 2017") is None
    assert prof.date_consistency("2017-04", "Sept 2014 - March 2017") is not None
    assert prof.date_consistency("present", "Jan 2020 - Current") is None
    assert prof.date_consistency("2020", "2020 - 2021") is None and prof.date_consistency("2020", "12020") is not None


def test_verbatim_quotes_first_80_chars():
    p = golden()
    p["summary"][0]["text"] = "x" * 200
    msg = prof.verify_verbatim(p, cv_text())[0]["message"]
    assert "x" * 80 in msg and "x" * 81 not in msg


def test_verbatim_tolerates_dash_quote_and_whitespace_variants():
    p = golden()
    cv = cv_text().replace("Feb 2024 - Present", "Feb 2024 \u2013 Present").replace("  from 25", "\n\n   from 25")
    assert prof.verify_verbatim(p, cv) == []


# --- IDs --------------------------------------------------------------------------------------------------
def _shuffle_ids(p: dict) -> dict:
    sh = copy.deepcopy(p)

    def new(i: str) -> str:
        i = re.sub(r"^exp-(\d+)", lambda m: f"exp-{int(m[1]) * 3 + 4}", i)
        i = re.sub(r"\.b(\d+)$", lambda m: f".b{int(m[1]) * 2 + 5}", i)
        i = re.sub(r"^(sum|edu|cert|skl|oth|iss)-(\d+)", lambda m: f"{m[1]}-{int(m[2]) + 40}", i)
        return i

    for _iid, kind, obj in list(prof.iter_items(sh)):
        if kind != "basics":
            obj["id"] = new(obj["id"])
    for issue in sh["source_issues"]:
        issue["id"] = new(issue["id"])
        issue["item_ids"] = [new(i) for i in issue["item_ids"]]
    return sh


def test_normalize_ids_restores_canonical_numbering_and_issue_refs():
    sh = _shuffle_ids(golden())
    assert sh["work"][1]["id"] == "exp-10" and sh["work"][0]["highlights"][0]["id"] == "exp-7.b7"
    mapping = prof.normalize_ids(sh)
    assert sh == golden()
    assert mapping["exp-10"] == "exp-2" and mapping["exp-7.b7"] == "exp-1.b1"
    assert sh["source_issues"][0]["item_ids"] == ["exp-2", "edu-1"]


def test_normalize_ids_numbers_engagements_and_their_highlights():
    p = golden()
    w = p["work"][0]
    w["engagements"] = [
        {"id": "exp-9.e7", "kind": "client", "name": "A", "role_label": "", "summary": "",
         "highlights": [{"id": "exp-9.e7.b3", "kind": "bullet", "text": "t"}]},
        {"id": "exp-9.e2", "kind": "client", "name": "B", "role_label": "", "summary": "", "highlights": []},
    ]
    prof.normalize_ids(p)
    assert [e["id"] for e in p["work"][0]["engagements"]] == ["exp-1.e1", "exp-1.e2"]
    assert p["work"][0]["engagements"][0]["highlights"][0]["id"] == "exp-1.e1.b1"
    assert schemas.validate(p, "profile") == []


# --- script source issues ---------------------------------------------------------------------------------
def _issues(p: dict, cv: str | None = None, kind: str = "") -> list[dict]:
    found = prof.script_source_issues(p, cv_text() if cv is None else cv, TODAY)
    return [i for i in found if not kind or i["kind"] == kind]


@pytest.mark.parametrize(("end", "severity", "word"), [
    ("2024-03", "info", "1 month"), ("2024-04", "warn", "2 months"),
])
def test_work_overlap_severity(end, severity, word):
    p = golden()
    p["work"][1]["end_date"] = end
    found = [i for i in _issues(p, kind="date_overlap") if i["item_ids"] == ["exp-1", "exp-2"]]
    assert len(found) == 1
    assert found[0]["severity"] == severity and word in found[0]["message"] and found[0]["origin"] == "script"


def test_boundary_month_is_not_an_overlap():
    p = golden()
    p["work"][1]["end_date"] = "2024-02"
    assert [i for i in _issues(p, kind="date_overlap") if i["item_ids"] == ["exp-1", "exp-2"]] == []


def test_no_overlap_when_ranges_do_not_meet():
    assert [i for i in _issues(golden(), kind="date_overlap") if i["item_ids"] == ["exp-1", "exp-2"]] == []
    p = golden()
    p["work"][1]["end_date"] = "2024-01"
    assert [i for i in _issues(p, kind="date_overlap") if i["item_ids"] == ["exp-1", "exp-2"]] == []


def test_education_inside_full_time_work_is_flagged_unless_ai_already_did():
    p = golden()
    assert _issues(p, kind="date_overlap") == []  # the AI issue iss-1 covers [exp-2, edu-1] already
    p["source_issues"] = []
    found = _issues(p, kind="date_overlap")
    assert [i["item_ids"] for i in found] == [["exp-2", "edu-1"]]
    p["work"][1]["employment_type"] = "contractor"
    assert _issues(p, kind="date_overlap") == []


def test_two_degrees_same_year():
    p = golden()
    p["education"].append({**p["education"][0], "id": "edu-2", "institution": "Other College"})
    found = _issues(p, kind="date_conflict")
    assert [i["item_ids"] for i in found] == [["edu-1", "edu-2"]]


def test_missing_contact_is_one_issue_listing_fields():
    found = _issues(golden(), kind="missing_contact")
    assert len(found) == 1 and "phone" in found[0]["message"] and "email" not in found[0]["message"]
    p = golden()
    p["basics"]["email"] = ""
    p["basics"]["location"] = {"city": "", "region": "", "country": ""}
    found = _issues(p, kind="missing_contact")
    assert len(found) == 1 and found[0]["severity"] == "warn"
    assert "email, phone, location" in found[0]["message"]


def test_contact_only_in_repeated_header_is_info():
    cv = "Jamie Rivera | jamie.rivera@example.com\nBody\nJamie Rivera | jamie.rivera@example.com\n"
    found = _issues(golden(), cv, kind="extraction")
    assert len(found) == 1 and found[0]["severity"] == "info" and "email" in found[0]["message"]
    assert _issues(golden(), kind="extraction") == []


def test_stale_updated_line():
    old = _issues(golden(), cv_text() + "\nUpdated: Jan 2026\n", kind="stale_metadata")
    assert len(old) == 1 and "9 months" in old[0]["message"]
    assert _issues(golden(), cv_text() + "\nUpdated: Jul 2026\n", kind="stale_metadata") == []


def test_summary_language_missing_from_skills():
    p = golden()
    p["summary"][0]["text"] = "Writes Python and Rust tooling."
    found = _issues(p, kind="inconsistency")
    assert len(found) == 1 and "Rust" in found[0]["message"] and "Python" not in found[0]["message"]
    assert found[0]["item_ids"] == ["sum-1"]


def test_script_issues_are_idempotent_and_replace_old_ones():
    p = golden()
    first = prof.apply_script_issues(p, cv_text(), TODAY)
    snapshot = copy.deepcopy(p)
    prof.apply_script_issues(p, cv_text(), TODAY)
    assert p == snapshot
    ids = [i["id"] for i in p["source_issues"]]
    assert ids == [f"iss-{n}" for n in range(1, len(ids) + 1)]
    assert p["source_issues"][0]["origin"] == "ai" and all(i["origin"] == "script" for i in p["source_issues"][1:])
    assert len(first) == len(p["source_issues"]) - 1
    p["source_issues"].append({**first[0], "id": "iss-99", "message": "stale leftover"})
    prof.apply_script_issues(p, cv_text(), TODAY)
    assert p == snapshot
    assert schemas.validate(p, "profile") == []


# --- items and merged view --------------------------------------------------------------------------------
def test_iter_items_and_item_text():
    p = golden()
    p["work"][0]["engagements"] = [{
        "id": "exp-1.e1", "kind": "client", "name": "Acme Retail", "role_label": "SRE", "summary": "Intro.",
        "highlights": [{"id": "exp-1.e1.b1", "kind": "tools", "text": "Tools: Linkerd"}],
    }]
    ids = [i for i, _k, _o in prof.iter_items(p)]
    assert ids[0] == "basics" and "exp-1.e1.b1" in ids and ids.index("exp-1") < ids.index("exp-1.b1")
    assert len(ids) == len(set(ids))
    work = prof.item_text(p, "exp-1")
    for needle in ("Brightfield Logistics", "Junior DevOps Engineer", "Feb 2024 - Present", "GitHub Actions pipelines",
                   "Acme Retail", "SRE", "Linkerd"):
        assert needle in work
    eng = prof.item_text(p, "exp-1.e1")
    assert "Linkerd" in eng and "SRE" in eng and "Feb 2024" in eng and "Terraform modules" not in eng
    assert prof.item_text(p, "exp-1.b2").startswith("Wrote Terraform")
    assert "Docker" in prof.item_text(p, "skl-1") and "Lakeshore" in prof.item_text(p, "edu-1")
    with pytest.raises(Exception, match="no item"):
        prof.item_text(p, "exp-99")


def test_merged_view_applies_only_active_corrections():
    p = golden()
    atts = [
        attestation("att-001"),
        attestation("att-002", status="proposed", correction={
            "item_id": "exp-1", "field": "position", "old_value": "", "new_value": "PROPOSED"}),
        attestation("att-003", status="revoked", correction={
            "item_id": "exp-1", "field": "name", "old_value": "", "new_value": "REVOKED"}),
        attestation("att-004", type="skill", claim="Helm", placement="skills", correction={
            "item_id": "exp-1", "field": "location", "old_value": "", "new_value": "NOT A CORRECTION"}),
        attestation("att-005", correction={
            "item_id": "exp-2", "field": "end_date", "old_value": "2023-12", "new_value": "2024-01"}),
        attestation("att-006", correction={
            "item_id": "exp-77", "field": "name", "old_value": "", "new_value": "missing target"}),
        attestation("att-007", correction={
            "item_id": "basics", "field": "phone", "old_value": "", "new_value": "+1 555 010 0100"}),
    ]
    store = {"schema_version": "1", "person_slug": "jamie-rivera", "next_seq": 8, "attestations": atts}
    assert schemas.validate(store, "attestations") == []
    before = copy.deepcopy(p)
    merged = prof.merged_view(p, atts)
    assert p == before and merged is not p
    assert merged["work"][1]["position"] == "IT Support Assistant"
    assert merged["work"][1]["end_date"] == "2024-01"
    assert merged["basics"]["phone"] == "+1 555 010 0100"
    assert merged["work"][0]["position"] == p["work"][0]["position"]
    assert merged["work"][0]["name"] == p["work"][0]["name"] and merged["work"][0]["location"] == "Columbus, OH"
    assert "IT Support Assistant" in prof.item_text(merged, "exp-2")
    assert prof.merged_view(p, []) == p


# --- store and cache --------------------------------------------------------------------------------------
def test_store_lookup_round_trip(workspace, capsys):
    run_dir = make_run()
    put_profile(run_dir, golden())
    assert cvt(capsys, "profile-verify", run_dir.name)[0] == 0
    sha = state.load(run_dir)["inputs"]["cv"]["sha256"]
    assert profile_store.lookup(sha) is None
    code, out, _ = cvt(capsys, "--json", "profile-cache", run_dir.name, "--store")
    assert code == 0 and json.loads(out)["data"]["stored"] is True
    stored = profile_store.lookup(sha)
    assert stored == workspace / "profiles" / "jamie-rivera" / f"profile.{sha[:12]}.json"
    assert profile_store.lookup("0" * 64) is None and profile_store.lookup("") is None
    att = jsonio.load_json(workspace / "profiles" / "jamie-rivera" / "attestations.json")
    assert att["next_seq"] == 1 and att["attestations"] == [] and schemas.validate(att, "attestations") == []
    att["next_seq"] = 5
    jsonio.dump_json(att, workspace / "profiles" / "jamie-rivera" / "attestations.json")
    profile_store.store(run_dir)  # a second store must not reset the attestation store
    assert jsonio.load_json(workspace / "profiles" / "jamie-rivera" / "attestations.json")["next_seq"] == 5

    # a new run of the same CV file hits the cache and skips parsing
    second = make_run()
    assert second != run_dir
    code, out, _ = cvt(capsys, "--json", "profile-cache", second.name, "--lookup")
    env = json.loads(out)
    assert code == 0 and env["data"]["hit"] is True and env["stage"] == "profiled"
    assert (second / "profile.json").is_file()
    st = state.load(second)
    assert st["stage"] == "profiled" and st["person_slug"] == "jamie-rivera"
    assert state.artifact(st, "profile") is not None
    assert jsonio.load_json(second / "profile.json")["cv_sha256"] == sha


def test_cache_miss_exits_zero_with_hit_false(workspace, capsys):
    run_dir = make_run()
    code, out, _ = cvt(capsys, "--json", "profile-cache", run_dir.name, "--lookup")
    env = json.loads(out)
    assert code == 0 and env["data"] == {"hit": False} and env["stage"] == "ingested"
    assert not (run_dir / "profile.json").exists()


def test_cache_requires_exactly_one_mode(workspace, capsys):
    run_dir = make_run()
    assert cvt(capsys, "profile-cache", run_dir.name)[0] == 2


# --- profile-verify command -------------------------------------------------------------------------------
def test_profile_verify_renumbers_adds_issues_and_advances_stage(workspace, capsys):
    run_dir = make_run()
    put_profile(run_dir, _shuffle_ids(golden()))
    code, out, _ = cvt(capsys, "--json", "profile-verify", run_dir.name)
    env = json.loads(out)
    assert code == 0 and env["ok"] and env["stage"] == "profiled" and "\n" not in out.strip()
    p = jsonio.load_json(run_dir / "profile.json")
    assert p["work"][1]["id"] == "exp-2" and p["source_issues"][0]["item_ids"] == ["exp-2", "edu-1"]
    assert any(i["origin"] == "script" and i["kind"] == "missing_contact" for i in p["source_issues"])
    st = state.load(run_dir)
    assert st["stage"] == "profiled" and st["person_slug"] == "jamie-rivera"
    assert state.artifact(st, "profile")["sha256"] == jsonio.sha256_file(run_dir / "profile.json")
    before = (run_dir / "profile.json").read_bytes()
    assert cvt(capsys, "profile-verify", run_dir.name)[0] == 0
    assert (run_dir / "profile.json").read_bytes() == before  # idempotent


def test_profile_verify_lists_all_violations_and_exits_1(workspace, capsys):
    run_dir = make_run()
    p = golden()
    p["work"][0]["highlights"][0]["text"] = "Invented achievement."
    p["work"][1]["name"] = "Made Up Corp"
    put_profile(run_dir, p)
    code, out, err = cvt(capsys, "--json", "profile-verify", run_dir.name, "--all")
    env = json.loads(out)
    assert code == 1 and not env["ok"] and env["error"]["id"] == "E_CHECK_FAILED"
    assert [v["item_id"] for v in env["data"]["violations"]] == ["exp-1.b1", "exp-2"]
    assert all(v["code"] == "fact_mismatch" for v in env["data"]["violations"])
    st = state.load(run_dir)
    assert st["status"] == "failed" and st["stage"] == "ingested"
    assert "brief fix" in st["next_action"]
    code, _out, err = cvt(capsys, "profile-verify", run_dir.name)
    assert code == 1 and err.startswith("cvt: error[E_CHECK_FAILED]") and "hint:" in err


def test_profile_verify_rejects_schema_violations_and_missing_file(workspace, capsys):
    run_dir = make_run()
    code, _out, err = cvt(capsys, "profile-verify", run_dir.name)
    assert code == 4 and "E_ARTIFACT_MISSING" in err and "hint:" in err
    (run_dir / "profile.json").write_text('{"schema_version": "1"}', encoding="utf-8")
    code, _out, err = cvt(capsys, "profile-verify", run_dir.name)
    assert code == 1 and "E_SCHEMA" in err


def test_profile_verify_needs_ingested_stage(workspace, capsys):
    run_dir = state.create_run(CV_FILE, "text", "pasted", JD_TEXT, {})
    code, _out, err = cvt(capsys, "profile-verify", run_dir.name)
    assert code == 4 and "E_STAGE" in err


# --- profile-show -----------------------------------------------------------------------------------------
def test_profile_show_outline_run_and_person_and_merged(workspace, capsys):
    run_dir = make_run()
    put_profile(run_dir, golden())
    assert cvt(capsys, "profile-verify", run_dir.name)[0] == 0
    assert cvt(capsys, "profile-cache", run_dir.name, "--store")[0] == 0
    store = paths.attestations_path("jamie-rivera")
    jsonio.dump_json({"schema_version": "1", "person_slug": "jamie-rivera", "next_seq": 3,
                      "attestations": [attestation("att-001"), attestation("att-002", status="proposed")]}, store)

    code, out, _ = cvt(capsys, "profile-show", run_dir.name)
    lines = out.strip().splitlines()
    assert code == 0 and len(lines) <= 15 and "Jamie Rivera" in lines[0]
    assert any(ln.startswith("exp-2 Cedar Valley College") and "IT Support Intern" in ln for ln in lines)
    assert any("att-001" in ln and "[active]" in ln for ln in lines)
    assert "| IT Support Intern |" in out and "| IT Support Assistant |" not in out

    code, out, _ = cvt(capsys, "profile-show", "--person", "jamie-rivera", "--merged")
    assert code == 0 and "| IT Support Assistant |" in out and "| IT Support Intern |" not in out

    code, out, _ = cvt(capsys, "profile-show", run_dir.name, "--all")
    assert code == 0 and "exp-1.b1 [bullet]" in out and len(out.splitlines()) > 15

    code, out, _ = cvt(capsys, "--json", "profile-show", "--person", "jamie-rivera")
    env = json.loads(out)
    assert code == 0 and env["data"]["attestation_count"] == 2 and env["data"]["work"] == 2
    assert cvt(capsys, "profile-show", "--person", "nobody")[0] == 4


# --- export-jsonresume ------------------------------------------------------------------------------------
def test_jsonresume_shape_with_engagements(workspace, capsys):
    run_dir = make_run()
    p = golden()
    p["work"][0]["engagements"] = [{
        "id": "exp-1.e1", "kind": "client", "name": "Acme Retail", "role_label": "SRE", "summary": "Platform work.",
        "highlights": [{"id": "exp-1.e1.b1", "kind": "bullet", "text": "Did a thing."}],
    }]
    put_profile(run_dir, p)
    code, out, _ = cvt(capsys, "--json", "export-jsonresume", run_dir.name)
    assert code == 0 and json.loads(out)["data"]["path"] == "jsonresume.json"
    jr = jsonio.load_json(run_dir / "jsonresume.json")
    assert set(jr) == {"basics", "work", "education", "certificates", "skills"}
    assert jr["basics"]["name"] == "Jamie Rivera" and jr["basics"]["location"]["city"] == "Columbus"
    assert jr["basics"]["profiles"] == [{"network": "github", "url": "https://github.com/jamierivera-dev"}]
    names = [w["name"] for w in jr["work"]]
    assert names == ["Brightfield Logistics", "Acme Retail \u2014 Brightfield Logistics", "Cedar Valley College"]
    assert all(isinstance(h, str) for w in jr["work"] for h in w["highlights"])
    eng = jr["work"][1]
    assert eng["position"] == "SRE" and eng["highlights"] == ["Did a thing."] and eng["startDate"] == "2024-02"
    assert "endDate" not in jr["work"][0] and jr["work"][2]["endDate"] == "2023-12"
    assert jr["education"][0] == {"institution": "Lakeshore State University", "area": "Computer Science",
                                  "studyType": "BSc", "endDate": "2023-08"}
    assert jr["certificates"][0]["name"] == "AWS Certified Cloud Practitioner"
    assert jr["skills"][0] == {"name": "Cloud & Infrastructure", "keywords": p["skills"][0]["keywords"]}
    assert state.load(run_dir)["stage"] == "ingested"  # no stage effect


# --- sample (private golden) ------------------------------------------------------------------------------
def test_sample_profile_verifies(workspace, capsys, sample_cv_path):
    if not PRIVATE_PROFILE.is_file():
        pytest.skip("private sample profile not present (arrives with WP-20)")
    from cvtlib import ingest

    extraction = ingest.extract_cv(sample_cv_path)
    text, _warnings = ingest.clean_cv_text(extraction.text)
    run_dir = make_run(sample_cv_path, cv=text)
    put_profile(run_dir, json.loads(PRIVATE_PROFILE.read_text(encoding="utf-8")))
    code, out, err = cvt(capsys, "profile-verify", run_dir.name, "--all")
    assert code == 0, out + err


def test_verify_verbatim_flags_title_and_role_label_dropping_a_qualifier():
    p = golden()
    p["work"][0]["position"] = "DevOps Engineer"
    p["work"][1]["position"] = "IT Support"
    bad = prof.verify_verbatim(p, cv_text())
    assert [(v["code"], v["item_id"]) for v in bad] == [("fact_mismatch", "exp-1"), ("fact_mismatch", "exp-2")]
    assert "drops the qualifier 'junior'" in bad[0]["message"] and "drops the qualifier 'intern'" in bad[1]["message"]
    p = golden()
    p["work"][0]["engagements"] = [{"id": "exp-1.e1", "kind": "client", "name": "X", "role_label": "Wizard",
                                    "summary": "", "highlights": []}]
    cv = cv_text() + "\nClient: X | Role: Junior Wizard\n"
    cv_both = cv + "Role: Wizard\n"
    assert [v["item_id"] for v in prof.verify_verbatim(p, cv) if "role_label" in v["message"]] == ["exp-1.e1"]
    assert not [v for v in prof.verify_verbatim(p, cv_both) if "role_label" in v["message"]]
