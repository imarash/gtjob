"""Consistency checks for the synthetic junior golden fixtures (WP-04).

Uses jsonschema directly so it has no dependency on the skill code.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "plan" / "contracts"
FIX = ROOT / "tests" / "fixtures"
GOLD = FIX / "golden" / "junior"
CV_PATH = FIX / "cv" / "jamie-rivera-junior.txt"
JD_PATH = FIX / "jds" / "junior-devops-engineer.md"

RUN_ID = "golden-junior"
PERSON_SLUG = "jamie-rivera"
HELM_ATT = "att-001"
CV_MIN_LINES = 40
CV_MAX_LINES = 60
MAX_PENDING_CP1 = 8
MIN_REWRITES = 2
EXPECTED_TALKING_POINTS = 2
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
LOGISTICS_MARKERS = ("$", "visa", "talent@", "salary")
ORIGIN_FOR_OP = {"keep": "kept", "rewrite": "rewritten", "merge": "merged", "attested": "attested"}

# golden file -> (schema file, optional $defs entry)
SCHEMAS: dict[str, tuple[str, str]] = {
    "profile-map.json": ("profile-map.schema.json", ""),
    "profile.json": ("profile.schema.json", ""),
    "jd.json": ("jd.schema.json", ""),
    "match.json": ("match.schema.json", ""),
    "questions.json": ("questions.schema.json", ""),
    "answers.round.json": ("answers.schema.json", "round"),
    "tailor-plan.json": ("tailor-plan.schema.json", ""),
    "tailored.json": ("tailored.schema.json", ""),
    "edits-001.json": ("edits.schema.json", ""),
}


# ------------------------------------------------------------------ helpers
def load(name: str) -> Any:
    return json.loads((GOLD / name).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def parse_range(r: str) -> tuple[int, int]:
    a, _, b = r.partition("-")
    return int(a), int(b or a)


def join_range(lines: list[str], r: str) -> str:
    a, b = parse_range(r)
    parts = [ln.strip() for ln in lines[a - 1 : b]]
    if parts and parts[0].startswith("- "):
        parts[0] = parts[0][2:]
    return " ".join(parts)


def schema_for(name: str) -> dict[str, Any]:
    file, sub = SCHEMAS[name]
    schema = json.loads((CONTRACTS / file).read_text(encoding="utf-8"))
    if not sub:
        return schema
    return {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": f"#/$defs/{sub}",
    }


def map_ranges(pmap: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (covered ranges, ignored ranges) from a profile map."""
    covered: list[str] = list(pmap["basics"]["lines"]) + list(pmap["summary_lines"])

    def highlights(items: list[dict[str, Any]]) -> None:
        covered.extend(h["lines"] for h in items)

    for w in pmap["work"]:
        covered.append(w["header_lines"])
        covered.extend(w["summary_lines"])
        highlights(w["highlights"])
        for e in w["engagements"]:
            covered.append(e["header_lines"])
            covered.extend(e["summary_lines"])
            highlights(e["highlights"])
    covered += [e["lines"] for e in pmap["education"]]
    covered += [c["lines"] for c in pmap["certificates"]]
    for s in pmap["skills"]:
        covered.extend(s["lines"])
    for o in pmap["other_sections"]:
        covered.extend(o["lines"])
    return covered, list(pmap["ignored_lines"])


def profile_texts(profile: dict[str, Any]) -> dict[str, str]:
    """ref id -> text (the same view the provenance validator uses for leaf refs)."""
    out: dict[str, str] = {"basics": " ".join(
        [profile["basics"]["name"], profile["basics"]["label"], profile["basics"]["email"]]
        + [p["url"] for p in profile["basics"]["profiles"]]
    )}
    for s in profile["summary"]:
        out[s["id"]] = s["text"]
    for w in profile["work"]:
        leaf = [h for h in w["highlights"]]
        for e in w["engagements"]:
            leaf += e["highlights"]
            out[e["id"]] = " ".join([e["name"], e["role_label"], e["summary"]] + [h["text"] for h in e["highlights"]])
        for h in leaf:
            out[h["id"]] = h["text"]
        out[w["id"]] = " ".join(
            [w["name"], w["position"], w["location"], w["date_text"], w["summary"]] + [h["text"] for h in leaf]
        )
    for e in profile["education"]:
        out[e["id"]] = e["text"]
    for c in profile["certificates"]:
        out[c["id"]] = c["name"]
    for g in profile["skills"]:
        out[g["id"]] = f"{g['name']}: {', '.join(g['keywords'])}"
    for o in profile["other_sections"]:
        out[o["id"]] = o["text"]
    return out


def attestation_text(answers: dict[str, Any]) -> str:
    att = answers["items"][0]["attestations"][0]
    return " ".join([att["claim"], att["detail"], *att["terms"]])


def all_tailored_ids(t: dict[str, Any]) -> set[str]:
    ids = {t["summary"]["id"]}
    ids |= {s["id"] for s in t["skills"]}
    for e in t["experience"]:
        ids.add(e["id"])
        ids |= {b["id"] for b in e["bullets"]}
        for g in e["engagements"]:
            ids.add(g["id"])
            ids |= {b["id"] for b in g["bullets"]}
    ids |= {c["id"] for c in t["certifications"]}
    ids |= {c["id"] for c in t["education"]}
    return ids


def tailored_bullets(t: dict[str, Any]) -> list[dict[str, Any]]:
    return [b for e in t["experience"] for b in e["bullets"]]


def collect_reviews(t: dict[str, Any]) -> list[str]:
    reviews = [t["summary"]["review"], t["earlier_experience"]["review"]]
    reviews += [s["review"] for s in t["skills"]]
    for e in t["experience"]:
        reviews += [e["review"]] + [b["review"] for b in e["bullets"]]
    return reviews


# ----------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def cv_lines() -> list[str]:
    return CV_PATH.read_text(encoding="utf-8").splitlines()


@pytest.fixture(scope="module")
def profile() -> dict[str, Any]:
    return load("profile.json")


@pytest.fixture(scope="module")
def ptexts(profile: dict[str, Any]) -> dict[str, str]:
    return profile_texts(profile)


# -------------------------------------------------------------------- tests
def test_cv_fixture_is_clean_and_synthetic(cv_lines: list[str]) -> None:
    raw = CV_PATH.read_text(encoding="utf-8")
    assert CV_MIN_LINES <= len(cv_lines) <= CV_MAX_LINES
    assert "\f" not in raw
    assert raw.isascii(), "CV must stay free of decorative glyphs"
    assert "jamie.rivera@example.com" in raw
    assert "Jamie Rivera" in raw


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_golden_validates_against_schema(name: str) -> None:
    schema = schema_for(name)
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(load(name)), key=lambda e: list(e.path))
    assert not errors, f"{name}: " + "; ".join(f"{list(e.path)}: {e.message}" for e in errors[:5])


def test_run_identity() -> None:
    assert load("profile.json")["person_slug"] == PERSON_SLUG
    for name in ("match.json", "questions.json", "tailored.json", "edits-001.json"):
        assert load(name)["run_id"] == RUN_ID, name


def test_sha_values_match_files() -> None:
    assert load("profile.json")["cv_sha256"] == sha256(CV_PATH)
    assert load("jd.json")["jd_sha256"] == sha256(JD_PATH)
    tailored = load("tailored.json")
    assert tailored["profile_sha256"] == sha256(GOLD / "profile.json")
    assert tailored["jd_sha256"] == load("jd.json")["jd_sha256"]


def test_profile_texts_occur_in_cv(profile: dict[str, Any], ptexts: dict[str, str]) -> None:
    cv = norm(CV_PATH.read_text(encoding="utf-8"))
    leaf_texts: list[str] = [p["text"] for p in profile["summary"]]
    for w in profile["work"]:
        leaf_texts += [w["name"], w["position"], w["location"], w["date_text"]]
        leaf_texts += [h["text"] for h in w["highlights"]]
    leaf_texts += [e["text"] for e in profile["education"]]
    leaf_texts += [c["name"] for c in profile["certificates"]]
    leaf_texts += [k for g in profile["skills"] for k in g["keywords"]]
    leaf_texts += [g["name"] for g in profile["skills"]]
    leaf_texts += [o["text"] for o in profile["other_sections"]]
    leaf_texts += [profile["basics"]["name"], profile["basics"]["label"], profile["basics"]["email"]]
    leaf_texts += [p["url"] for p in profile["basics"]["profiles"]]
    missing = [t for t in leaf_texts if norm(t) not in cv]
    assert not missing, missing
    assert ptexts["exp-1.b1"] in cv


def test_profile_map_ranges_cover_cv(cv_lines: list[str]) -> None:
    covered, ignored = map_ranges(load("profile-map.json"))
    seen: dict[int, str] = {}
    for r in covered + ignored:
        a, b = parse_range(r)
        assert 1 <= a <= b <= len(cv_lines), f"range {r} out of bounds"
        for n in range(a, b + 1):
            assert n not in seen, f"line {n} in both {seen[n]} and {r}"
            seen[n] = r
    non_blank = {i for i, ln in enumerate(cv_lines, 1) if ln.strip()}
    assert non_blank - set(seen) == set(), f"uncovered lines: {sorted(non_blank - set(seen))}"
    blank_used = [n for n in seen if n not in non_blank]
    assert not blank_used, f"blank lines in ranges: {blank_used}"


def test_profile_matches_map(cv_lines: list[str], profile: dict[str, Any]) -> None:
    pmap = load("profile-map.json")
    assert profile["summary"][0]["id"] == "sum-1"
    assert [s["text"] for s in profile["summary"]] == [join_range(cv_lines, r) for r in pmap["summary_lines"]]
    assert len(profile["work"]) == len(pmap["work"])
    for i, (pw, mw) in enumerate(zip(profile["work"], pmap["work"]), 1):
        assert pw["id"] == f"exp-{i}"
        for key in ("name", "location", "position", "start_date", "end_date", "date_text", "employment_type"):
            assert pw[key] == mw[key], (pw["id"], key)
        assert [h["id"] for h in pw["highlights"]] == [f"exp-{i}.b{k}" for k in range(1, len(mw["highlights"]) + 1)]
        assert [h["kind"] for h in pw["highlights"]] == [h["kind"] for h in mw["highlights"]]
        assert [h["text"] for h in pw["highlights"]] == [join_range(cv_lines, h["lines"]) for h in mw["highlights"]]
        assert mw["header_lines"] in {str(n) for n in range(1, len(cv_lines) + 1)}
    assert [e["text"] for e in profile["education"]] == [join_range(cv_lines, e["lines"]) for e in pmap["education"]]
    assert [c["name"] for c in profile["certificates"]] == [join_range(cv_lines, c["lines"]) for c in pmap["certificates"]]
    assert [o["text"] for o in profile["other_sections"]] == [
        " ".join(join_range(cv_lines, r) for r in o["lines"]) for o in pmap["other_sections"]
    ]
    for i, (g, mg) in enumerate(zip(profile["skills"], pmap["skills"]), 1):
        assert g["id"] == f"skl-{i}" and g["name"] == mg["name"]
        body = join_range(cv_lines, mg["lines"][0]).split(":", 1)[1]
        assert g["keywords"] == [k.strip() for k in re.split(r"[,;|]", body) if k.strip()]
    assert [(i["kind"], i["item_ids"]) for i in profile["source_issues"]] == [
        (i["kind"], i["item_ids"]) for i in pmap["source_issues"]
    ]
    assert profile["source_issues"][0]["origin"] == "ai"
    assert profile["source_issues"][0]["kind"] == "date_overlap"
    assert profile["source_issues"][0]["id"] == "iss-1"


def test_jd_and_noise(profile: dict[str, Any]) -> None:
    jd = load("jd.json")
    jd_text = norm(JD_PATH.read_text(encoding="utf-8"))
    reqs = jd["requirements"]
    assert [r["id"] for r in reqs] == [f"req-{i}" for i in range(1, len(reqs) + 1)]
    assert sum(r["kind"] == "must" for r in reqs) == 6
    assert sum(r["kind"] == "nice" for r in reqs) == 3
    assert any("Helm" in r["keywords"] for r in reqs)
    assert norm(jd["years_experience_text"]) in jd_text
    for r in reqs:
        assert norm(r["text"]) in jd_text, r["id"]
    for n in jd["noise"]:
        assert norm(n["text"]) in jd_text, n["text"]
    req_ids = {r["id"] for r in reqs}
    for k in jd["keywords"]:
        assert set(k["req_ids"]) <= req_ids


def test_match_is_complete_and_quotes_are_verbatim(ptexts: dict[str, str]) -> None:
    jd = load("jd.json")
    match = load("match.json")
    ids = [m["req_id"] for m in match["requirements"]]
    assert sorted(ids) == sorted(r["id"] for r in jd["requirements"])
    assert len(ids) == len(set(ids))
    by_id = {m["req_id"]: m for m in match["requirements"]}
    for m in match["requirements"]:
        for e in m["evidence"]:
            assert e["ref"] in ptexts, e["ref"]
            assert e["quote"] in ptexts[e["ref"]], (m["req_id"], e["quote"])
        if m["strength"] == "strong":
            assert m["gap_question"] == "" and m["advice"] == ""
        else:
            assert m["gap_question"] and m["advice"]
    helm = next(r["id"] for r in jd["requirements"] if "Helm" in r["keywords"])
    assert by_id[helm]["strength"] == "none"
    # coverage recomputed from the requirement list
    kinds = {r["id"]: r["kind"] for r in jd["requirements"]}
    cov = match["coverage"]
    for kind in ("must", "nice"):
        sel = [m for m in match["requirements"] if kinds[m["req_id"]] == kind]
        assert cov[f"{kind}_total"] == len(sel)
        for strength in ("strong", "partial", "none"):
            assert cov[f"{kind}_{strength}"] == sum(m["strength"] == strength for m in sel)
    for mo in match["metric_opportunities"]:
        assert mo["item_id"] in ptexts


def test_questions_follow_checkpoint_one_rules(ptexts: dict[str, str]) -> None:
    qs = load("questions.json")["questions"]
    jd_req_ids = {r["id"] for r in load("jd.json")["requirements"]}
    assert len(qs) == 3
    assert len([q for q in qs if q["status"] == "pending"]) <= MAX_PENDING_CP1
    assert len({q["id"] for q in qs}) == len(qs)
    for q in qs:
        assert q["checkpoint"] == 1 and q["status"] == "pending" and q["allow_free_text"] is True
        assert q["default"]["text"] and q["default"]["description"]
        choice_ids = {c["id"] for c in q["choices"]}
        assert set(q["default"]["choice_ids"]) <= choice_ids
        assert set(q["links"]["req_ids"]) <= jd_req_ids
        assert set(q["links"]["item_ids"]) <= set(ptexts)
    topics = {q["topic"]: q for q in qs}
    assert set(topics) == {"gap", "metric", "strategy"}
    assert any(c["id"] == "helm" for c in topics["gap"]["choices"])
    assert {c["id"] for c in topics["strategy"]["choices"]} == {"modern", "classic", "sidebar"}


def test_answers_round_yields_helm_attestation(ptexts: dict[str, str]) -> None:
    rnd = load("answers.round.json")
    question_ids = {q["id"] for q in load("questions.json")["questions"]}
    assert rnd["checkpoint"] == 1
    assert {i["question_id"] for i in rnd["items"]} <= question_ids
    assert set(rnd["unmentioned_question_ids"]) <= question_ids
    attests = [a for i in rnd["items"] if i["action"] == "attest" for a in i["attestations"]]
    assert len(attests) == 1
    att = attests[0]
    assert (att["type"], att["placement"], att["terms"], att["detail"]) == (
        "skill", "skills_and_bullets", ["Helm"], "packaged two internal services",
    )
    assert att["scope"]["kind"] == "items" and att["scope"]["item_ids"] == ["exp-1"]
    assert set(att["scope"]["item_ids"]) <= set(ptexts)
    assert att["verbatim"] in rnd["raw_text"]
    assert rnd["raw_text"] == "I used Helm at Brightfield to package two internal services"


def test_plan_and_tailored_line_up(profile: dict[str, Any], ptexts: dict[str, str]) -> None:
    plan = load("tailor-plan.json")
    tailored = load("tailored.json")
    assert tailored["target"]["page_target"] == 1 and tailored["target"]["template"] == "modern"
    assert [e["profile_id"] for e in plan["experience"]] == [e["profile_id"] for e in tailored["experience"]]
    ops = [b["op"] for e in plan["experience"] for b in e["bullets"]]
    assert ops.count("rewrite") >= MIN_REWRITES
    attested = [b for e in plan["experience"] for b in e["bullets"] if b["op"] == "attested"]
    assert len(attested) == 1 and attested[0]["extra_refs"] == [HELM_ATT]
    for pe, te in zip(plan["experience"], tailored["experience"]):
        assert te["priority"] == pe["priority"]
        assert len(pe["bullets"]) == len(te["bullets"])
        for idx, (pb, tb) in enumerate(zip(pe["bullets"], te["bullets"]), 1):
            assert tb["id"] == f"t-{te['profile_id']}.b{idx}"
            assert tb["priority"] == pb["priority"]
            assert tb["origin"] == ORIGIN_FOR_OP[pb["op"]]
            if pb["op"] == "keep":
                assert pb["text"] == "" and len(pb["from"]) == 1 and pb["extra_refs"] == []
                assert tb["text"] == ptexts[pb["from"][0]]
            else:
                assert tb["text"] == pb["text"] and pb["text"]
            assert tb["source_refs"] == pb["from"] + pb["extra_refs"]
    # skills: plan items have empty refs, tailored items resolve to supporting refs
    assert all(i["source_refs"] == [] for g in plan["skills"] for i in g["items"])
    assert [(g["label"], g["priority"], [i["name"] for i in g["items"]]) for g in plan["skills"]] == [
        (g["label"], g["priority"], [i["name"] for i in g["items"]]) for g in tailored["skills"]
    ]
    assert [s["id"] for s in tailored["skills"]] == [f"t-skl-{i}" for i in range(1, len(tailored["skills"]) + 1)]
    assert plan["headline"]["text"] == tailored["header"]["headline"]
    assert plan["summary"]["text"] == tailored["summary"]["text"]
    assert plan["summary"]["source_refs"] == tailored["summary"]["source_refs"]
    assert plan["talking_points"] == tailored["talking_points"] and len(tailored["talking_points"]) == EXPECTED_TALKING_POINTS
    assert plan["omitted"] == tailored["omitted"] and plan["open_items"] == tailored["open_items"]
    assert plan["earlier_experience"]["include"] is False and tailored["earlier_experience"]["include"] is False


def test_tailored_facts_and_refs(profile: dict[str, Any], ptexts: dict[str, str]) -> None:
    t = load("tailored.json")
    assert t["header"]["name"] == profile["basics"]["name"]
    assert t["header"]["email"] == profile["basics"]["email"]
    assert {l["url"] for l in t["header"]["links"]} <= {p["url"] for p in profile["basics"]["profiles"]}
    for te in t["experience"]:
        pw = next(w for w in profile["work"] if w["id"] == te["profile_id"])
        assert (te["employer"], te["title"], te["location"], te["start_date"], te["end_date"]) == (
            pw["name"], pw["position"], pw["location"], pw["start_date"], pw["end_date"],
        )
    cert = t["certifications"][0]
    assert cert["name"] in ptexts[cert["profile_id"]]
    edu = t["education"][0]
    pe = next(e for e in profile["education"] if e["id"] == edu["profile_id"])
    assert (edu["institution"], edu["end_date"], edu["location"]) == (pe["institution"], pe["end_date"], pe["location"])

    valid = set(ptexts) | {HELM_ATT}
    refs: list[str] = list(t["header"]["source_refs"]) + list(t["summary"]["source_refs"])
    refs += [r for s in t["skills"] for i in s["items"] for r in i["source_refs"]]
    refs += [r for b in tailored_bullets(t) for r in b["source_refs"]]
    refs += [r for tp in t["talking_points"] for r in tp["source_refs"]]
    assert refs and set(refs) <= valid, set(refs) - valid
    assert all(b["source_refs"] for b in tailored_bullets(t))
    assert all(i["source_refs"] for s in t["skills"] for i in s["items"])
    assert {b["priority"] for b in tailored_bullets(t)} <= {1, 2, 3, 4, 5}
    assert {r for r in collect_reviews(t)} == {"pending"}
    assert t["earlier_experience"]["include"] is False
    for o in t["omitted"]:
        assert o["profile_id"] in ptexts
    blob = json.dumps(t, ensure_ascii=False).lower()
    assert not [m for m in LOGISTICS_MARKERS if m in blob]


def test_tailored_claims_are_supported(profile: dict[str, Any], ptexts: dict[str, str]) -> None:
    """Light truthfulness check: numbers and known tech terms must trace to the cited refs."""
    t = load("tailored.json")
    answers = load("answers.round.json")
    texts = dict(ptexts)
    texts[HELM_ATT] = attestation_text(answers)
    keywords = {k for g in profile["skills"] for k in g["keywords"]} | {"Helm", "Kubernetes"}
    elements = [(b["id"], b["text"], b["source_refs"]) for b in tailored_bullets(t)]
    elements.append(("t-sum", t["summary"]["text"], t["summary"]["source_refs"]))
    elements.append(("header", t["header"]["headline"], t["header"]["source_refs"]))
    elements += [("talking-point", tp["text"], tp["source_refs"]) for tp in t["talking_points"]]
    for ident, text, refs in elements:
        source = norm(" ".join(texts[r] for r in refs)).lower()
        for num in NUMBER_RE.findall(text):
            assert num in source, f"{ident}: number {num} not in {refs}"
        for kw in keywords:
            if re.search(rf"(?<![\w]){re.escape(kw)}(?![\w])", text, re.IGNORECASE):
                assert kw.lower() in source, f"{ident} mentions '{kw}'; not found in refs {refs}"
    for s in t["skills"]:
        for item in s["items"]:
            source = norm(" ".join(texts[r] for r in item["source_refs"])).lower()
            assert item["name"].lower() in source, (s["id"], item["name"])
    # the Helm attestation is cited only where its scope (exp-1) allows
    for e in t["experience"]:
        for b in e["bullets"]:
            if HELM_ATT in b["source_refs"]:
                assert e["profile_id"] == "exp-1"
                assert b["origin"] == "attested"


def test_edits_batch_targets_exist(ptexts: dict[str, str]) -> None:
    edits = load("edits-001.json")
    t = load("tailored.json")
    ids = all_tailored_ids(t)
    ops = edits["ops"]
    assert [o["op"] for o in ops] == ["replace_text", "reject", "approve_all"]
    assert edits["source"] == "checkpoint2"
    for o in ops:
        if o["op"] in {"replace_text", "reject", "approve"}:
            assert o["target_id"] in ids, o
    replace = ops[0]
    assert replace["source_refs"] and set(replace["source_refs"]) <= set(ptexts)
    assert replace["field"] == "" and replace["value"]
    assert ops[2]["target_id"] == ""
