"""WP-13: provenance validator (interfaces.md section 8), checked against mutations of the junior golden.

Rule -> test
  1 missing_refs            test_mutation[missing_refs], test_mutation[skill_without_refs]
  2 unknown_ref             test_mutation[unknown_ref|revoked_att|unresolved_att|other_run_att]
  3 placement / out of scope test_mutation[skills_only_att_in_bullet|att_out_of_scope]
  3a job scope               test_mutation[cross_employer_bullet|bullet_only_skill_ref|own_job_tools_line_ok], test_*scope*
  4 unsupported_term        test_mutation[linkerd|headline_term|skill_wrong_ref], test_exact_message_format
  5 unsupported_number      test_mutation[changed_number|salary_in_summary]
  6 fact_mismatch/cert      test_mutation[employer_date|employer_title|degree_changed|header_name|cert_changed]
  7 skill_unsupported       test_mutation[uncited_skill]
  8 placeholders            test_placeholders_*
  9 logistics_leak          test_logistics_*
 10 attestation_not_active  test_mutation[proposed_cited], test_rule10_*
 positives                  test_golden_passes, test_mutation[synonym_ok|cert_shortened|correction_applies]
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cvtlib import provenance

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
GOLDEN = FIXTURES / "golden" / "junior"
RUN_ID = "golden-junior"
ALL_CODES = {
    "missing_refs", "unknown_ref", "ref_out_of_scope", "placement", "unsupported_term", "unsupported_number",
    "fact_mismatch", "attestation_not_active", "placeholder", "logistics_leak", "skill_unsupported",
    "cert_unsupported",
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def golden() -> dict:
    return {name: _load(GOLDEN / f"{name}.json") for name in ("tailored", "profile", "jd")}


CORRECTION_ID = "att-008"  # corrects exp-2's start date; kept out of the base set so the golden stays valid


@pytest.fixture(scope="module")
def all_atts() -> list[dict]:
    return _load(FIXTURES / "provenance" / "attestations.json")


@pytest.fixture(scope="module")
def atts(all_atts) -> list[dict]:
    return [a for a in all_atts if a["id"] != CORRECTION_ID]


MUTATIONS = _load(FIXTURES / "provenance" / "mutations.json")


def _walk(root, dotted: str):
    node = root
    for part in dotted.split("."):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def mutate(tailored: dict, spec: dict) -> dict:
    out = copy.deepcopy(tailored)
    for path, value in spec.get("set", {}).items():
        *head, last = path.split(".")
        parent = _walk(out, ".".join(head)) if head else out
        parent[int(last) if isinstance(parent, list) else last] = value
    for path, value in spec.get("append", {}).items():
        _walk(out, path).append(copy.deepcopy(value))
    return out


def run(t: dict, golden: dict, atts: list[dict], *, draft: bool = False) -> list[dict]:
    return provenance.check_tailored(t, golden["profile"], atts, run_id=RUN_ID, draft=draft)


def _has(violations: list[dict], want: dict) -> bool:
    return any(
        v["code"] == want["code"] and v["item_id"] == want["item_id"]
        and ("message" not in want or v["message"] == want["message"])
        for v in violations
    )


def test_golden_passes(golden, atts):
    assert run(golden["tailored"], golden, atts) == []
    assert provenance.find_placeholders(golden["tailored"]) == []
    assert provenance.check_logistics(golden["tailored"], golden["jd"]) == []


@pytest.mark.parametrize("name", [n for n, s in MUTATIONS.items() if "expect" in s])
def test_mutation(name, golden, atts, all_atts):
    spec = MUTATIONS[name]
    pool = all_atts if name == "correction_applies" else atts
    violations = run(mutate(golden["tailored"], spec), golden, pool)
    for want in spec["expect"]:
        assert _has(violations, want), (want, violations)
    if not spec["expect"]:
        assert violations == []
    assert {v["code"] for v in violations} <= ALL_CODES
    assert violations == sorted(violations, key=lambda v: (v["item_id"], v["message"]))
    for v in violations:
        assert v["message"].split()[1] == v["item_id"] or v["item_id"] in v["message"]  # item named first


def test_exact_message_format(golden, atts):
    violations = run(mutate(golden["tailored"], MUTATIONS["linkerd"]), golden, atts)
    assert [v["message"] for v in violations] == ["bullet t-exp-1.b2 mentions 'Linkerd'; not found in refs [exp-1.b2]"]


def test_attestation_makes_term_citable(golden, atts):
    t = mutate(golden["tailored"], {"set": {"experience.0.bullets.3.text": "Packaged two internal services with Helm."}})
    assert run(t, golden, atts) == []
    t2 = mutate(t, {"set": {"experience.0.bullets.3.source_refs": ["exp-1.b3"]}})
    assert any(v["code"] == "unsupported_term" and "'Helm'" in v["message"] for v in run(t2, golden, atts))


def test_revoked_and_foreign_attestations_say_why(golden, atts):
    for name, word in (("revoked_att", "revoked"), ("unresolved_att", "unresolved"), ("other_run_att", "other-run")):
        violations = run(mutate(golden["tailored"], MUTATIONS[name]), golden, atts)
        assert word in violations[0]["message"]


def test_correction_attestation_changes_expected_fact(golden, atts, all_atts):
    t = mutate(golden["tailored"], MUTATIONS["correction_applies"])
    assert run(t, golden, atts)[0]["code"] == "fact_mismatch"  # no correction: the profile date is the truth
    assert run(t, golden, all_atts) == []                       # active correction
    proposed = [dict(a, status="proposed") if a["id"] == CORRECTION_ID else a for a in all_atts]
    assert run(t, golden, proposed) == []                       # this run's proposed correction, before approval
    other = [dict(a, status="proposed", run_id="other") if a["id"] == CORRECTION_ID else a for a in all_atts]
    assert run(t, golden, other)[0]["code"] == "fact_mismatch"
    old = golden["tailored"]
    assert run(old, golden, all_atts)[0]["code"] == "fact_mismatch"  # the uncorrected date no longer matches


def test_rule10_proposed_fails_unless_draft(golden, atts):
    t = mutate(golden["tailored"], MUTATIONS["proposed_cited"])
    assert any(v["code"] == "attestation_not_active" for v in run(t, golden, atts, draft=False))
    assert run(t, golden, atts, draft=True) == []
    status = provenance.check_attestation_status(t, atts, run_id=RUN_ID)
    assert [v["item_id"] for v in status] == ["t-sum"] and "att-005" in status[0]["message"]
    active = [dict(a, status="active") if a["id"] == "att-005" else a for a in atts]
    assert run(t, golden, active, draft=False) == []
    assert provenance.check_attestation_status(golden["tailored"], atts, run_id=RUN_ID) == []


def test_header_contact_and_links_must_be_profile_values(golden, atts):
    for path, value in (("header.email", "other@example.com"), ("header.phone", "555-0100"),
                        ("header.location", "Austin, TX")):
        t = mutate(golden["tailored"], {"set": {path: value}})
        assert any(v["code"] == "fact_mismatch" and v["item_id"] == "t-header" for v in run(t, golden, atts)), path
    t = mutate(golden["tailored"], {"append": {"header.links": {"label": "Site", "url": "https://example.org"}}})
    assert any("not a profile url" in v["message"] for v in run(t, golden, atts))
    t = mutate(golden["tailored"], {"set": {"header.location": ""}})
    assert run(t, golden, atts) == []  # unknown location stays empty, never guessed


def test_education_and_experience_facts(golden, atts):
    for path, value, item in (("education.0.institution", "Lakeshore University", "t-edu-1"),
                              ("education.0.end_date", "2022-08", "t-edu-1"),
                              ("education.0.details", "Thesis on robots", "t-edu-1"),
                              ("experience.0.employer", "Brightfield Systems", "t-exp-1"),
                              ("experience.1.end_date", "2024-01", "t-exp-2"),
                              ("experience.0.location", "Austin, OH", "t-exp-1")):
        t = mutate(golden["tailored"], {"set": {path: value}})
        assert any(v["code"] == "fact_mismatch" and v["item_id"] == item for v in run(t, golden, atts)), path
    t = mutate(golden["tailored"], {"set": {"experience.0.profile_id": "exp-9"}})
    assert any(v["code"] == "unknown_ref" and v["item_id"] == "t-exp-1" for v in run(t, golden, atts))


def test_earlier_experience_items_are_fact_checked(golden, atts):
    item = {"profile_id": "exp-2", "employer": "Cedar Valley College", "title": "IT Support Intern",
            "start_date": "2023-07", "end_date": "2023-12"}
    ok = mutate(golden["tailored"], {"set": {"earlier_experience.include": True}, "append": {"earlier_experience.items": item}})
    assert run(ok, golden, atts) == []
    bad = mutate(ok, {"set": {"earlier_experience.items.0.title": "IT Director"}})
    assert any(v["code"] == "fact_mismatch" and v["item_id"] == "exp-2" for v in run(bad, golden, atts))


def test_skill_group_label_is_checked(golden, atts):
    t = mutate(golden["tailored"], {"set": {"skills.0.label": "Kubernetes & Service Mesh"}})
    violations = run(t, golden, atts)
    assert any(v["code"] == "skill_unsupported" and "label" in v["message"] for v in violations)


def test_talking_points_follow_the_same_rules(golden, atts):
    t = mutate(golden["tailored"], {"set": {"talking_points.0.text": "Explain the Linkerd migration."}})
    violations = run(t, golden, atts)
    assert any(v["item_id"] == "talking_points[0]" and "'Linkerd'" in v["message"] for v in violations)
    t = mutate(golden["tailored"], {"set": {"talking_points.0.source_refs": []}})
    assert any(v["code"] == "missing_refs" and v["item_id"] == "talking_points[0]" for v in run(t, golden, atts))


def test_intro_needs_refs_when_not_empty(golden, atts):
    t = mutate(golden["tailored"], {"set": {"experience.0.intro.text": "Platform team of 4 engineers."}})
    assert any(v["code"] == "missing_refs" and v["item_id"] == "t-exp-1" for v in run(t, golden, atts))
    t = mutate(t, {"set": {"experience.0.intro.source_refs": ["exp-1.b1"]}})
    codes = {v["code"] for v in run(t, golden, atts)}
    assert "unsupported_number" in codes and "missing_refs" not in codes


def test_placeholders_are_reported_and_not_treated_as_claims(golden, atts):
    t = mutate(golden["tailored"], MUTATIONS["placeholder"])
    found = provenance.find_placeholders(t)
    assert [(v["code"], v["item_id"]) for v in found] == [("placeholder", "t-exp-1.b1")]
    assert "[[CONFIRM: new deploy time]]" in found[0]["message"]
    assert run(t, golden, atts) == []  # CONFIRM is not an unsupported acronym


def test_placeholders_in_open_items_are_not_reported(golden):
    t = mutate(golden["tailored"], {"append": {"open_items": {
        "kind": "confirm_placeholder", "text": "Confirm [[CONFIRM: x]]", "item_ids": []}}})
    assert provenance.find_placeholders(t) == []


def test_logistics_noise_and_patterns(golden):
    for name in ("salary_in_summary", "noise_in_summary", "visa_in_bullet"):
        spec = MUTATIONS[name]
        got = provenance.check_logistics(mutate(golden["tailored"], spec), golden["jd"])
        for want in spec["expect_logistics"]:
            assert _has(got, want), (name, got)
        assert all(v["code"] == "logistics_leak" for v in got)


def test_logistics_ignores_own_contact_details_and_notes(golden):
    t = mutate(golden["tailored"], {"set": {"header.email": "talent@harborpoint.example"}})
    assert provenance.check_logistics(t, golden["jd"]) == []  # header contact fields are profile-checked instead
    t = mutate(golden["tailored"], {"set": {"experience.0.bullets.0.text": "Reach me at talent@harborpoint.example"}})
    got = provenance.check_logistics(t, golden["jd"])
    assert got and got[0]["item_id"] == "t-exp-1.b1"


def test_logistics_noise_kind_filter(golden):
    jd = copy.deepcopy(golden["jd"])
    jd["noise"] = [{"kind": "marketing", "text": "Harbor Point Software"}]
    assert provenance.check_logistics(golden["tailored"], jd) == []  # only logistics kinds count


# --- rule 3a: a bullet or intro cites only its own job ------------------------------------------------------
OUT_OF_SCOPE = "ref_out_of_scope"
NESTED_PROFILE = FIXTURES / "profile" / "nested-engagements.json"
WORK_HIGHLIGHT = {"id": "exp-2.b1", "kind": "bullet", "text": "Ran weekly delivery reviews with the client leads."}


def _bullet(bid: str, refs: list[str]) -> dict:
    return {"id": bid, "text": "Built a CI pipeline for the claims team.", "source_refs": refs, "priority": 1,
            "origin": "kept", "review": "pending"}


def _nested(engagement_refs: list[str], work_refs: list[str] | None = None) -> tuple[dict, dict]:
    """(tailored, profile): golden tailored whose only job is nested work exp-2 with engagement exp-2.e1."""
    profile = _load(NESTED_PROFILE)
    profile["work"][1]["highlights"].append(WORK_HIGHLIGHT)
    t = copy.deepcopy(_load(GOLDEN / "tailored.json"))
    entry = copy.deepcopy(t["experience"][0])
    entry.update(id="t-exp-2", profile_id="exp-2", bullets=[], engagements=[{
        "id": "t-exp-2.e1", "profile_id": "exp-2.e1", "kind": "client", "name": "Tallgrass Insurance",
        "role_label": "Platform Engineer", "bullets": [_bullet("t-exp-2.e1.b1", engagement_refs)],
    }])
    if work_refs is not None:
        entry["bullets"] = [_bullet("t-exp-2.b1", work_refs)]
    t["experience"] = [entry]
    return t, profile


def _scope(t: dict, profile: dict) -> list[dict]:
    got = provenance.check_tailored(t, profile, [], run_id=RUN_ID, draft=True)
    return [v for v in got if v["code"] == OUT_OF_SCOPE]


def test_cross_employer_bullet_is_out_of_scope(golden, atts):
    violations = run(mutate(golden["tailored"], MUTATIONS["cross_employer_bullet"]), golden, atts)
    messages = [v["message"] for v in violations if v["code"] == OUT_OF_SCOPE]
    assert "bullet t-exp-2.b1 cites exp-1.b1 from another job; parent is exp-2" in messages


def test_engagement_bullet_own_refs_pass():
    for refs in (["exp-2.e1"], ["exp-2.e1.b1"], ["exp-2.e1.b1", "exp-2.b1"], ["exp-2.b1", "skl-1"]):
        t, profile = _nested(refs)
        assert _scope(t, profile) == [], refs


def test_engagement_bullet_citing_sibling_fails():
    t, profile = _nested(["exp-2.e2.b1"])
    got = _scope(t, profile)
    assert [v["message"] for v in got][0] == (
        "bullet t-exp-2.e1.b1 cites exp-2.e2.b1 from another job; parent is exp-2.e1")
    assert len(got) == 2 and "has no ref from its own job" in got[1]["message"]


def test_engagement_bullet_citing_bare_work_fails():
    t, profile = _nested(["exp-2"])
    got = _scope(t, profile)
    assert got and got[0]["item_id"] == "t-exp-2.e1.b1" and "cites exp-2 from another job" in got[0]["message"]


def test_work_bullet_cannot_cite_another_work_or_prefix_lookalike():
    t, profile = _nested(["exp-2.e1.b1"], work_refs=["exp-2.b1", "exp-20.b1"])
    got = _scope(t, profile)
    assert [v["message"] for v in got] == ["bullet t-exp-2.b1 cites exp-20.b1 from another job; parent is exp-2"]


def test_attestation_in_scope_counts_as_own_job_ref(golden, atts):
    # att-001 is a bullets attestation scoped to exp-1: usable as the only ref under exp-1, not under exp-2
    t = mutate(golden["tailored"], {"set": {"experience.0.bullets.3.source_refs": ["att-001"]}})
    assert not [v for v in run(t, golden, atts) if v["code"] == OUT_OF_SCOPE]
    t = mutate(golden["tailored"], {"set": {"experience.1.bullets.0.source_refs": ["att-001"]}})
    assert any(v["code"] == OUT_OF_SCOPE and v["item_id"] == "t-exp-2.b1" for v in run(t, golden, atts))


def test_intro_is_scoped_only_when_not_empty(golden, atts):
    t = mutate(golden["tailored"], {"set": {"experience.0.intro.text": "Platform team.",
                                            "experience.0.intro.source_refs": ["exp-2.b1"]}})
    assert any(v["code"] == OUT_OF_SCOPE and v["message"].startswith("intro t-exp-1 cites exp-2.b1")
               for v in run(t, golden, atts))
    t = mutate(golden["tailored"], {"set": {"experience.0.intro.source_refs": ["exp-2.b1"]}})
    assert run(t, golden, atts) == []  # empty intro text is not a claim


# --- rule 4: seniority words in the headline and summary need support in their refs ---------------------------
def _headline(text: str) -> dict:
    return {"set": {"header.headline": text}}


def _summary(text: str) -> dict:
    return {"set": {"summary.text": text}}


SENIORITY_MUTATIONS = {
    "headline_senior": (_headline("Senior DevOps Engineer"), "headline", "t-header", "Senior"),
    "headline_staff": (_headline("Staff Platform Architect"), "headline", "t-header", "Staff"),
    "summary_senior": (_summary("Senior DevOps engineer who automates AWS deployments with Terraform."),
                       "summary", "t-sum", "Senior"),
    "summary_principal": (_summary("Principal DevOps architect who automates AWS deployments with Terraform."),
                          "summary", "t-sum", "Principal"),
    "headline_sr_dot": (_headline("Sr. DevOps Engineer · AWS"), "headline", "t-header", "Sr"),
    "headline_snr": (_headline("Snr DevOps Engineer"), "headline", "t-header", "Snr"),
    "summary_sr_dot": (_summary("Sr. DevOps engineer who automates AWS deployments with Terraform."),
                       "summary", "t-sum", "Sr"),
}


@pytest.mark.parametrize("name", sorted(SENIORITY_MUTATIONS))
def test_unsupported_seniority_word_is_reported(name, golden, atts):
    spec, kind, item_id, word = SENIORITY_MUTATIONS[name]
    violations = run(mutate(golden["tailored"], spec), golden, atts)
    want = [v for v in violations if v["code"] == "unsupported_term" and f"'{word}'" in v["message"]]
    assert [v["item_id"] for v in want] == [item_id]
    assert want[0]["message"].startswith(f"{kind} {item_id} mentions '{word}'; not found in refs [")


def test_seniority_message_uses_exact_format_and_text_casing(golden, atts):
    t = mutate(golden["tailored"], _headline("Lead DevOps Engineer · STAFF platform"))
    messages = [v["message"] for v in run(t, golden, atts)]
    assert messages == ["headline t-header mentions 'STAFF'; not found in refs [basics, exp-1]"]


def test_lead_is_allowed_by_design(golden, atts):
    assert run(mutate(golden["tailored"], _headline("Lead DevOps Engineer · AWS")), golden, atts) == []


def test_seniority_word_supported_by_a_ref_passes(golden, atts):
    profile = copy.deepcopy(golden["profile"])
    profile["summary"][0]["text"] += " Mentored by a Senior platform engineer."
    t = mutate(golden["tailored"], _summary("Senior platform engineer who automates AWS deployments with Terraform."))
    t["summary"]["source_refs"] = ["sum-1", "exp-1"]
    assert provenance.check_tailored(t, profile, atts, run_id=RUN_ID, draft=False) == []
    assert any(v["code"] == "unsupported_term" for v in run(t, golden, atts))  # unmodified profile: rejected


def test_seniority_is_whole_word_and_only_for_headline_and_summary(golden, atts):
    t = mutate(golden["tailored"], {"set": {"summary.text": "Junior DevOps engineer who headed a Terraform rollout."}})
    assert run(t, golden, atts) == []  # 'headed' is not 'head'
    t = mutate(golden["tailored"], {"set": {"experience.0.bullets.0.text": "Senior reviewers approved the Terraform modules."}})
    assert not any("'Senior'" in v["message"] for v in run(t, golden, atts))


def test_sr_abbreviation_is_supported_by_full_word_in_ref(golden, atts):
    profile = copy.deepcopy(golden["profile"])
    profile["summary"][0]["text"] += " Mentored by a Senior platform engineer."
    t = mutate(golden["tailored"], _summary("Sr. platform engineer who automates AWS deployments with Terraform."))
    t["summary"]["source_refs"] = ["sum-1", "exp-1"]
    assert provenance.check_tailored(t, profile, atts, run_id=RUN_ID, draft=False) == []


def test_full_seniority_word_is_supported_by_abbreviation_in_ref(golden, atts):
    profile = copy.deepcopy(golden["profile"])
    profile["summary"][0]["text"] += " Mentored by a Sr. platform engineer."
    t = mutate(golden["tailored"], _summary("Senior platform engineer who automates AWS deployments with Terraform."))
    t["summary"]["source_refs"] = ["sum-1", "exp-1"]
    assert provenance.check_tailored(t, profile, atts, run_id=RUN_ID, draft=False) == []


def test_sr_inside_sr_iov_is_not_a_seniority_claim(golden, atts):
    profile = copy.deepcopy(golden["profile"])
    profile["summary"][0]["text"] += " Tuned SR-IOV networking for AWS workloads."
    t = mutate(golden["tailored"], _summary("Platform engineer who tunes SR-IOV networking for AWS workloads."))
    t["summary"]["source_refs"] = ["sum-1", "exp-1"]
    violations = provenance.check_tailored(t, profile, atts, run_id=RUN_ID, draft=False)
    assert not any("'SR'" in v["message"] or "'Sr'" in v["message"] for v in violations)
