"""WP-10: profile-map -> profile.json (numbered_cv, build_profile, `cvt profile-build`)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cvtlib import cli, jsonio, profile as prof, profile_map, schemas, state

REPO = Path(__file__).resolve().parents[2]
CV_FILE = REPO / "tests/fixtures/cv/jamie-rivera-junior.txt"
GOLDEN_DIR = REPO / "tests/fixtures/golden/junior"
JD_TEXT = "# Junior DevOps Engineer at Example Corp\n\nAutomate things.\n"
SHA = "a" * 64

SYNTHETIC_CV = """Morgan Ellis
Platform Consultant
Austin, TX | morgan.ellis@example.com | +1 555 010 0199

SUMMARY
Consultant focused on delivery platforms.

EXPERIENCE
Northwind Consulting | Consultant | Austin, TX | Mar 2019 - Present
Client: Contoso Retail | Role: SRE
Automated release pipelines for 40 services.
\u2022 Reduced incident volume by 20% using runbooks.
Tools in use: Kubernetes, Terraform, Argo CD

Fabrikam Labs | Developer | Remote | Jan 2016 - Feb 2019
- Built internal tooling in Go
  and Python for support teams.

SKILLS
Languages: Go, Python; Bash | Rust
Platforms: Cloud (AWS, GCP) \u2022 Linux

EDUCATION
BSc Mathematics | Example University | Austin, TX | 2015
"""


def golden(name: str) -> dict:
    return json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))


def cv_text() -> str:
    return CV_FILE.read_text(encoding="utf-8")


def strip_created(profile: dict) -> dict:
    return {k: v for k, v in profile.items() if k != "created_at"}


def build_golden(pmap: dict | None = None, cv: str | None = None) -> tuple[dict, list[dict]]:
    p = golden("profile.json")
    return profile_map.build_profile(
        pmap or golden("profile-map.json"), cv if cv is not None else cv_text(),
        person_slug=p["person_slug"], cv_sha256=p["cv_sha256"])


def codes(violations: list[dict]) -> list[str]:
    return [v["code"] for v in violations]


def make_run(cv: str) -> Path:
    src = Path(state.paths.workspace_root()) / "cv-src.txt"
    src.write_text(cv, encoding="utf-8")
    run_dir = state.create_run(src, "text", "pasted", JD_TEXT, {}, slug="build")
    (run_dir / "cv.txt").write_text(cv, encoding="utf-8")
    st = state.load(run_dir)
    state.record_artifact(run_dir, st, "cv_txt", "cv.txt")
    state.set_stage(st, "ingested")
    state.save(run_dir, st)
    return run_dir


def cvt(capsys, *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


# --- numbered_cv ------------------------------------------------------------------------------------------
def test_numbered_cv_format_includes_blank_lines():
    text = "a\n\nb\n"
    assert profile_map.numbered_cv(text) == "   1| a\n   2| \n   3| b"
    lines = profile_map.numbered_cv(cv_text()).splitlines()
    assert lines[0] == "   1| Jamie Rivera" and lines[3] == "   4| " and lines[40].startswith("  41| validate")
    assert len(lines) == 41


# --- golden equality --------------------------------------------------------------------------------------
def test_golden_map_builds_golden_profile():
    profile, violations = build_golden()
    assert violations == []
    assert strip_created(profile) == strip_created(golden("profile.json"))
    assert schemas.validate(profile, "profile") == []
    assert prof.verify_verbatim(profile, cv_text()) == []


# --- violations -------------------------------------------------------------------------------------------
def test_range_errors_out_of_bounds_reversed_and_overlap():
    pmap = golden("profile-map.json")
    pmap["work"][0]["highlights"][0]["lines"] = "99"
    pmap["work"][0]["highlights"][1]["lines"] = "14-13"
    pmap["work"][1]["highlights"][0]["lines"] = "21-23"  # overlaps the work header (21) and the first bullet (22-23)
    _profile, violations = build_golden(pmap)
    msgs = [v["message"] for v in violations if v["code"] == "range_error"]
    assert any("out of bounds" in m and "99" in m for m in msgs)
    assert any("reversed" in m for m in msgs)
    assert any("already claimed" in m for m in msgs)
    pmap = golden("profile-map.json")
    pmap["summary_lines"] = ["5-6"]  # line 5 is also in ignored_lines
    assert "range_error" in codes(build_golden(pmap)[1])


def test_unmapped_line_reports_number_and_first_60_chars():
    pmap = golden("profile-map.json")
    pmap["ignored_lines"].remove("39")
    pmap["other_sections"][0]["lines"] = ["40"]
    _profile, violations = build_golden(pmap)
    unmapped = [v for v in violations if v["code"] == "unmapped_line"]
    assert [v["item_id"] for v in unmapped] == ["L39", "L41"]
    assert "line 39" in unmapped[0]["message"] and "PROJECTS" in unmapped[0]["message"]
    assert len(unmapped[1]["message"]) < 100


@pytest.mark.parametrize(("path", "value", "needle"), [
    (("work", 0, "name"), "Brightfield Systems", "employer"),
    (("work", 1, "position"), "IT Support Manager", "title"),
    (("work", 0, "date_text"), "Feb 2020 - Present", "date_text"),
    (("education", 0, "institution"), "Harvard", "institution"),
    (("certificates", 0, "name"), "AWS Certified Solutions Architect", "certificate"),
    (("basics", None, "name"), "Jamie Q. Rivera", "name"),
    (("basics", None, "email"), "other@example.com", "email"),
])
def test_not_verbatim_typed_values(path, value, needle):
    pmap = golden("profile-map.json")
    section, idx, key = path
    (pmap[section] if idx is None else pmap[section][idx])[key] = value
    _profile, violations = build_golden(pmap)
    bad = [v for v in violations if v["code"] == "not_verbatim"]
    # a wrong date_text also disagrees with the (unchanged) normalized start_date
    assert len(bad) == (2 if needle == "date_text" else 1) and needle in bad[0]["message"], violations


def test_not_verbatim_is_case_insensitive_and_nfkc():
    pmap = golden("profile-map.json")
    pmap["work"][0]["name"] = "BRIGHTFIELD LOGISTICS"
    cv = cv_text().replace("Feb 2024 - Present", "Feb 2024 \u2013 Present")
    pmap["work"][0]["date_text"] = "Feb 2024 - Present"
    assert [v for v in build_golden(pmap, cv)[1] if v["code"] == "not_verbatim"] == []


@pytest.mark.parametrize(("path", "value", "needle"), [
    (("work", 0, "start_date"), "2023-02", "start_date '2023-02' is not consistent with date_text"),
    (("work", 1, "end_date"), "2025-01", "end_date '2025-01' is not consistent with date_text"),
    (("work", 0, "start_date"), "2024-03", "start_date '2024-03'"),  # right year, wrong month
    (("work", 1, "end_date"), "present", "end_date 'present'"),  # no Present/Current/Now/Today
    (("work", 0, "location"), "Austin, TX", "location"),
    (("education", 0, "area"), "Computer Engineering", "degree area"),
    (("education", 0, "study_type"), "MSc", "degree type"),
    (("education", 0, "location"), "Columbus, KS", "location"),
    (("education", 0, "end_date"), "2022-08", "end_date year 2022"),
    (("certificates", 0, "date"), "2021", "date year 2021"),
    (("basics", None, "city"), "Chicago", "city"),
    (("basics", None, "region"), "KS", "region"),
    (("basics", None, "country"), "Canada", "country"),
])
def test_not_verbatim_dates_locations_and_degrees(path, value, needle):
    pmap = golden("profile-map.json")
    section, idx, key = path
    (pmap[section] if idx is None else pmap[section][idx])[key] = value
    _profile, violations = build_golden(pmap)
    bad = [v for v in violations if v["code"] == "not_verbatim"]
    assert bad and any(needle in v["message"] for v in bad), violations
    assert {v["code"] for v in violations} == {"not_verbatim"}


def test_not_verbatim_role_label_in_engagement():
    pmap = copy.deepcopy(golden("profile-map.json"))
    pmap["work"][0]["engagements"] = [{
        "kind": "client", "name": "Brightfield Logistics", "role_label": "Staff Wizard", "header_lines": "10",
        "summary_lines": [], "highlights": []}]
    bad = [v for v in build_golden(pmap)[1] if v["code"] == "not_verbatim"]
    assert any("role label" in v["message"] and v["item_id"] == "exp-1.e1" for v in bad), bad


def test_golden_dates_pass_and_message_names_item():
    pmap = golden("profile-map.json")
    pmap["work"][1]["end_date"] = "2025-01"
    bad = [v for v in build_golden(pmap)[1] if v["code"] == "not_verbatim"]
    assert bad[0]["item_id"] == "exp-2"
    assert bad[0]["message"].startswith("exp-2: end_date '2025-01' is not consistent with date_text 'Jul 2023")


@pytest.mark.parametrize(("date_text", "start", "end"), [
    ("Sept 2014 - March 2017", "2014-09", "2017-03"),
    ("2019 - 2021", "2019", "2021"),
    ("Jan 2020 - Current", "2020-01", "present"),
    ("09/2014 - 3/2017", "2014-09", "2017-03"),
    ("Today 2020", "", "present"),
])
def test_date_consistency_accepts_cv_spellings(date_text, start, end):
    assert prof.date_consistency(start, date_text) is None
    assert prof.date_consistency(end, date_text) is None


def test_date_consistency_rules():
    assert prof.date_consistency("", "anything") is None
    assert prof.date_consistency("2023", "Aug 12023") is not None  # whole-number year only
    assert prof.date_consistency("2024-02", "Jan 2024 - 2025") is not None
    assert prof.date_consistency("present", "Jan 2020 - Dec 2021") is not None
    assert prof.date_consistency("2024-02", "Feb 2024") is None and prof.date_consistency("2024-02", "2 2024") is None
    assert prof.date_consistency("2024-02", "Marketing 2024") is not None  # prefix of a word is not a month


# --- synthetic: two employers, engagement, tools line, skills --------------------------------------------
def test_synthetic_two_employers_with_engagement_and_tools():
    lines = SYNTHETIC_CV.splitlines()

    def at(prefix: str) -> str:
        return str(next(n for n, ln in enumerate(lines, 1) if ln.startswith(prefix)))

    def span(a: str, b: str) -> str:
        return f"{at(a)}-{at(b)}"

    pmap = {
        "schema_version": "1",
        "basics": {"name": "Morgan Ellis", "label": "Platform Consultant", "email": "morgan.ellis@example.com",
                   "phone": "+1 555 010 0199", "url": "", "city": "Austin", "region": "TX", "country": "",
                   "profiles": [], "lines": [span("Morgan", "Austin")]},
        "summary_lines": [at("Consultant focused")],
        "work": [
            {"name": "Northwind Consulting", "location": "Austin, TX", "position": "Consultant",
             "employment_type": "consultant", "start_date": "2019-03", "end_date": "present",
             "date_text": "Mar 2019 - Present", "header_lines": at("Northwind"), "summary_lines": [],
             "highlights": [], "engagements": [{
                 "kind": "client", "name": "Contoso Retail", "role_label": "SRE", "header_lines": at("Client:"),
                 "summary_lines": [at("Automated release")],
                 "highlights": [{"kind": "bullet", "lines": at("\u2022 Reduced")},
                                {"kind": "tools", "lines": at("Tools in use")}]}]},
            {"name": "Fabrikam Labs", "location": "Remote", "position": "Developer", "employment_type": "employee",
             "start_date": "2016-01", "end_date": "2019-02", "date_text": "Jan 2016 - Feb 2019",
             "header_lines": at("Fabrikam"), "summary_lines": [],
             "highlights": [{"kind": "bullet", "lines": span("- Built", "  and Python")}], "engagements": []},
        ],
        "education": [{"institution": "Example University", "area": "Mathematics", "study_type": "BSc",
                       "location": "Austin, TX", "end_date": "2015", "lines": at("BSc")}],
        "certificates": [],
        "skills": [{"name": "Languages", "lines": [at("Languages")]}, {"name": "Platforms", "lines": [at("Platforms")]}],
        "other_sections": [],
        "ignored_lines": [at("SUMMARY"), at("EXPERIENCE"), at("SKILLS"), at("EDUCATION")],
        "source_issues": [],
    }
    assert schemas.validate(pmap, "profile-map") == []
    profile, violations = profile_map.build_profile(pmap, SYNTHETIC_CV, person_slug="morgan-ellis", cv_sha256=SHA)
    assert violations == []
    assert schemas.validate(profile, "profile") == []
    assert prof.verify_verbatim(profile, SYNTHETIC_CV) == []
    n1, n2 = profile["work"]
    assert (n1["id"], n2["id"]) == ("exp-1", "exp-2")
    eng = n1["engagements"][0]
    assert eng["id"] == "exp-1.e1" and eng["name"] == "Contoso Retail" and eng["role_label"] == "SRE"
    assert eng["summary"] == "Automated release pipelines for 40 services."
    assert [(h["id"], h["kind"]) for h in eng["highlights"]] == [("exp-1.e1.b1", "bullet"), ("exp-1.e1.b2", "tools")]
    assert eng["highlights"][0]["text"] == "Reduced incident volume by 20% using runbooks."  # glyph stripped
    assert eng["highlights"][1]["text"] == "Tools in use: Kubernetes, Terraform, Argo CD"
    assert n2["highlights"][0] == {"id": "exp-2.b1", "kind": "bullet",
                                   "text": "Built internal tooling in Go and Python for support teams."}
    assert profile["skills"][0]["keywords"] == ["Go", "Python", "Bash", "Rust"]
    assert profile["skills"][1]["keywords"] == ["Cloud (AWS, GCP)", "Linux"]
    assert profile["education"][0]["text"] == "BSc Mathematics | Example University | Austin, TX | 2015"
    assert "SRE" in prof.item_text(profile, "exp-1.e1")


def test_split_keywords_strips_separators_and_empties():
    assert profile_map.split_keywords(" a , b;c | d \u2022 e ,, ") == ["a", "b", "c", "d", "e"]
    assert profile_map.split_keywords("Cloud (AWS, GCP), Linux") == ["Cloud (AWS, GCP)", "Linux"]


# --- the command ------------------------------------------------------------------------------------------
def test_profile_build_command_happy_path(workspace, capsys):
    run_dir = make_run(cv_text())
    jsonio.dump_json(golden("profile-map.json"), run_dir / "profile-map.json")
    code, out, _ = cvt(capsys, "--json", "profile-build", run_dir.name)
    env = json.loads(out)
    assert code == 0 and env["stage"] == "profiled" and env["data"]["person_slug"] == "jamie-rivera"
    p = jsonio.load_json(run_dir / "profile.json")
    st = state.load(run_dir)
    assert p["cv_sha256"] == st["inputs"]["cv"]["sha256"] and st["person_slug"] == "jamie-rivera"
    assert {a["name"] for a in st["artifacts"]} >= {"cv_txt", "profile_map", "profile"}
    ai = [i for i in p["source_issues"] if i["origin"] == "ai"]
    assert ai == golden("profile.json")["source_issues"]
    assert any(i["origin"] == "script" for i in p["source_issues"])
    expected = golden("profile.json")
    expected.update(cv_sha256=p["cv_sha256"], source_issues=p["source_issues"], created_at=p["created_at"])
    assert p == expected
    assert cvt(capsys, "profile-verify", run_dir.name)[0] == 0  # build output passes verify


def test_profile_build_command_reports_violations(workspace, capsys):
    run_dir = make_run(cv_text())
    pmap = golden("profile-map.json")
    pmap["ignored_lines"].remove("39")
    pmap["work"][0]["name"] = "Nowhere Inc"
    pmap["work"][0]["highlights"][0]["lines"] = "99"
    jsonio.dump_json(pmap, run_dir / "profile-map.json")
    code, out, _ = cvt(capsys, "--json", "profile-build", run_dir.name, "--all")
    env = json.loads(out)
    assert code == 1 and env["error"]["id"] == "E_CHECK_FAILED"
    assert set(codes(env["data"]["violations"])) == {"range_error", "unmapped_line", "not_verbatim"}
    assert not (run_dir / "profile.json").exists()
    st = state.load(run_dir)
    assert st["status"] == "failed" and st["stage"] == "ingested" and "brief fix" in st["next_action"]
    code, _out, err = cvt(capsys, "profile-build", run_dir.name)
    assert code == 1 and "5 problems" in err and "L39" in err and "hint:" in err


def test_profile_build_command_missing_map_and_bad_schema(workspace, capsys):
    run_dir = make_run(cv_text())
    code, _out, err = cvt(capsys, "profile-build", run_dir.name)
    assert code == 4 and "E_ARTIFACT_MISSING" in err and "hint:" in err
    bad = copy.deepcopy(golden("profile-map.json"))
    del bad["basics"]["name"]
    jsonio.dump_json(bad, run_dir / "profile-map.json")
    code, _out, err = cvt(capsys, "profile-build", run_dir.name)
    assert code == 1 and "E_SCHEMA" in err


# --- titles and role labels keep their seniority qualifiers ----------------------------------------------
QUALIFIER_CV = """Pat Quinn
pat.quinn@example.com
Acme Works | Co-Founder | Remote | 2020 - Present
Bolt Retail | Assistant Manager | Remote | 2018 - 2020
Client: Dune Co | Role: Senior Engineer (Contract)
"""


def qualifier_map(position: str, role_label: str = "Senior Engineer") -> dict:
    def job(name: str, title: str, line: str, start: str, end: str, text: str, engagements: list[dict]) -> dict:
        return {"name": name, "location": "Remote", "position": title, "employment_type": "unknown",
                "start_date": start, "end_date": end, "date_text": text, "header_lines": line,
                "summary_lines": [], "highlights": [], "engagements": engagements}

    engagement = {"kind": "client", "name": "Dune Co", "role_label": role_label, "header_lines": "5",
                  "summary_lines": [], "highlights": []}
    return {
        "schema_version": "1",
        "basics": {"name": "Pat Quinn", "label": "", "email": "pat.quinn@example.com", "phone": "", "url": "",
                   "city": "", "region": "", "country": "", "profiles": [], "lines": ["1-2"]},
        "summary_lines": [],
        "work": [job("Acme Works", position, "3", "2020", "present", "2020 - Present", [engagement]),
                 job("Bolt Retail", "Assistant Manager", "4", "2018", "2020", "2018 - 2020", [])],
        "education": [], "certificates": [], "skills": [], "other_sections": [], "ignored_lines": [],
        "source_issues": [],
    }


def build_qualifier(pmap: dict, cv: str = QUALIFIER_CV) -> list[dict]:
    assert schemas.validate(pmap, "profile-map") == []
    return profile_map.build_profile(pmap, cv, person_slug="pat-quinn", cv_sha256=SHA)[1]


@pytest.mark.parametrize(("index", "value", "qualifier"), [
    (0, "DevOps Engineer", "junior"),
    (1, "IT Support", "intern"),
])
def test_junior_title_dropping_qualifier_is_not_verbatim(index, value, qualifier):
    pmap = golden("profile-map.json")
    pmap["work"][index]["position"] = value
    bad = [v for v in build_golden(pmap)[1] if v["code"] == "not_verbatim"]
    assert len(bad) == 1 and bad[0]["item_id"] == f"exp-{index + 1}"
    assert f"title '{value}' drops the qualifier '{qualifier}' in its cited lines" in bad[0]["message"]
    assert "copy the full title" in bad[0]["message"]


@pytest.mark.parametrize(("position", "qualifier"), [("Founder", "co"), ("Manager", "assistant")])
def test_synthetic_title_dropping_qualifier_is_not_verbatim(position, qualifier):
    pmap = qualifier_map("Co-Founder")
    pmap["work"][0 if position == "Founder" else 1]["position"] = position
    bad = build_qualifier(pmap)
    assert [v["code"] for v in bad] == ["not_verbatim"] and f"'{qualifier}'" in bad[0]["message"], bad


def test_role_label_dropping_qualifier_is_not_verbatim():
    cv = QUALIFIER_CV.replace("Role: Senior Engineer (Contract)", "Role: Engineering Intern")
    assert build_qualifier(qualifier_map("Co-Founder", "Engineering Intern"), cv) == []
    bad = build_qualifier(qualifier_map("Co-Founder", "Engineering"), cv)
    assert [(v["code"], v["item_id"]) for v in bad] == [("not_verbatim", "exp-1.e1")]
    assert "role label 'Engineering' drops the qualifier 'intern'" in bad[0]["message"]


def test_full_titles_pass_and_trailing_parenthetical_is_not_a_qualifier():
    assert build_qualifier(qualifier_map("Co-Founder")) == []  # also covers "Senior Engineer" from "... (Contract)"
    assert build_qualifier(qualifier_map("Co-Founder", "Senior Engineer")) == []


@pytest.mark.parametrize(("value", "text", "expected"), [
    ("Engineer", "Junior Engineer | Remote", "drops the qualifier 'junior'"),
    ("Engineer", "Software Engineer Intern", "drops the qualifier 'intern'"),
    ("Founder", "Co\u2013Founder", "drops the qualifier 'co'"),
    ("Software Engineer", "Software Engineer-Intern", "drops the qualifier 'intern'"),
    ("Software Engineer", "Software Engineer\u2013Intern", "drops the qualifier 'intern'"),
    ("Software Engineer", "Software Engineer - Intern", None),  # a spaced dash ends the token
    ("Engineer", "Jr. Engineer", "drops the qualifier 'jr'"),
    ("Engineer", "Junior Engineer; Engineer II", None),  # once with a qualifier, once without
    ("Engineer", "Junior Engineer | Engineer", None),
    ("Engineer", "Junior - Engineer", None),  # a spaced dash ends the token
    ("Engineer", "Junior, Engineer", None),
    ("Engineer", "Senior Engineer working at Acme", None),
    ("Engineer", "Senior Engineer", None),
    ("", "Junior Engineer", None),
    ("Engineer", "Developer", None),  # absent: the verbatim check reports it
])
def test_dropped_qualifier_unit(value, text, expected):
    assert prof.dropped_qualifier(value, text) == expected
