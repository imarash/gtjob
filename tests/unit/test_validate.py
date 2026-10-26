"""WP-14: ATS round-trip, keyword coverage, layout, and the `cvt validate` gates and final PDF."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from conftest import REPO_ROOT
from cvtlib import ats, attestations, cli, coverage, jsonio, render, state, validate
from cvtlib.errors import ExitCode

GOLDEN = REPO_ROOT / "tests" / "fixtures" / "golden" / "junior"
PERSON = "jamie-rivera"
FINAL_NAME = "Jamie-Rivera-Junior-DevOps-Engineer-Harbor-Point-Software.pdf"
CONFIRM = " [[CONFIRM: team size]]"
GATE_ORDER = list(validate.GATE_NAMES)
needs_typst = pytest.mark.skipif(render.detect_backend() == "none", reason="no Typst backend")


# ---------------------------------------------------------------- helpers
def load(name: str) -> dict:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def model_for(tailored: dict | None = None) -> dict:
    return render.build_render_model(
        tailored or load("tailored.json"), dropped_ids=set(), density="standard", draft=False, paper="us-letter",
        template="modern",
    )


def text_for(model: dict, order: list[int] | None = None) -> str:
    """Plain extraction text of a model: title line, then the section's strings, sections optionally reordered."""
    head = model["header"]
    lines = [head["name"], head["headline"], *[c["text"] for c in head["contacts"]]]
    sections = [model["sections"][i] for i in order] if order else model["sections"]
    for sec in sections:
        lines += [sec["title"].upper(), *sec["paragraphs"], *sec["lines"]]
        lines += [f"{r['label']}: {r['items_text']}" for r in sec["skill_rows"]]
        for e in sec["entries"]:
            lines += [f"{e['heading']}      {e['dates']}", f"{e['subheading']}      {e['location']}", e["intro"]]
            lines += [f"• {b}" for b in e["bullets"]]
    return "\n".join(line for line in lines if line)


def codes(violations: list[dict]) -> list[str]:
    return [v["code"] for v in violations]


def junior_run(workspace: Path, tmp_path: Path, tailored: dict | None = None) -> Path:
    """An approved junior run: the real `approve` activates the proposed Helm attestation of the golden round."""
    cv = tmp_path / "cv.txt"
    cv.write_text("Jamie Rivera\n", encoding="utf-8")
    run = state.create_run(cv, "text", "pasted", "Junior DevOps Engineer", {"template": "modern"}, slug="validate-test")
    for name, art in (("profile.json", "profile"), ("jd.json", "jd")):
        shutil.copyfile(GOLDEN / name, run / name)
    jsonio.dump_json(tailored or load("tailored.json"), run / "tailored.json")
    store = attestations.load_store(PERSON)
    item = load("answers.round.json")["items"][0]
    attestations.add(store, item["attestations"][0], run_id=run.name, question_id=item["question_id"])
    attestations.save_store(PERSON, store)
    st = state.load(run)
    for art, name in (("profile", "profile.json"), ("jd", "jd.json"), ("tailored", "tailored.json")):
        state.record_artifact(run, st, art, name)
    state.set_stage(st, "tailored")
    state.save(run, st)
    assert cli.main(["approve", str(run), "--all"]) == 0
    assert state.load(run)["stage"] == "approved"
    return run


def cvt(args: list[str], capsys: pytest.CaptureFixture) -> tuple[int, str, str]:
    code = cli.main(args)
    out = capsys.readouterr()
    return code, out.out, out.err


def fitted_run(workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture, tailored: dict | None = None) -> Path:
    run = junior_run(workspace, tmp_path, tailored)
    assert cvt(["fit", str(run)], capsys)[0] == 0
    return run


# ---------------------------------------------------------------- ATS
def test_ats_clean_text_has_no_violations() -> None:
    model = model_for()
    assert ats.ats_check(text_for(model), model, load("jd.json")) == []


def test_ats_missing_email_names_the_value() -> None:
    model = model_for()
    text = text_for(model).replace("jamie.rivera@example.com", "")
    found = ats.ats_check(text, model, load("jd.json"))
    assert codes(found) == ["ats_missing"]
    assert "email 'jamie.rivera@example.com'" in found[0]["message"]


def test_ats_missing_section_title_and_employer() -> None:
    model = model_for()
    text = text_for(model).replace("CERTIFICATIONS", "").replace("Cedar Valley College", "")
    messages = [v["message"] for v in ats.ats_check(text, model, load("jd.json"))]
    assert any("section title 'Certifications'" in m for m in messages)
    assert any("employer 'Cedar Valley College'" in m for m in messages)


def test_ats_sections_out_of_order() -> None:
    model = model_for()
    swapped = list(range(len(model["sections"])))
    swapped[1], swapped[2] = swapped[2], swapped[1]  # experience before skills
    found = ats.ats_check(text_for(model, swapped), model, load("jd.json"))
    assert codes(found) == ["ats_order"]
    assert "'Experience'" in found[0]["message"] or "'Skills'" in found[0]["message"]


def test_ats_first_bullet_before_employer_heading() -> None:
    model = model_for()
    first = model["sections"][2]["entries"][0]
    lines = text_for(model).splitlines()
    heading_at = next(i for i, ln in enumerate(lines) if ln.startswith(first["heading"]))
    bullet_at = next(i for i, ln in enumerate(lines) if first["bullets"][0] in ln)
    lines[heading_at], lines[bullet_at] = lines[bullet_at], lines[heading_at]
    found = ats.ats_check("\n".join(lines), model, load("jd.json"))
    assert "ats_order" in codes(found)
    assert any("before its heading" in v["message"] for v in found)


def test_ats_garbage_markers_and_short_text() -> None:
    model = model_for()
    text = text_for(model)
    assert "ats_garbage" in codes(ats.ats_check(text + "\n(cid:123)", model, load("jd.json")))
    assert "ats_garbage" in codes(ats.ats_check(text + "\nbad \ufffd glyph", model, load("jd.json")))
    short = ats.ats_check(text[: len(text) // 2], model, load("jd.json"))
    assert any(v["code"] == "ats_garbage" and "% of the" in v["message"] for v in short)


@needs_typst
def test_ats_round_trip_of_a_real_pdf(tmp_path: Path) -> None:
    model = model_for()
    typ = render.write_build(tmp_path, model, "modern")
    render.compile_pdf(tmp_path, typ, tmp_path / "cv.pdf")
    text = ats.extract_pdf_text(tmp_path / "cv.pdf")
    assert "Jamie" in text and "\ufffd" not in text
    assert ats.ats_check(text, model, load("jd.json")) == []


@needs_typst
def test_extract_falls_back_to_pypdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = model_for()
    typ = render.write_build(tmp_path, model, "modern")
    render.compile_pdf(tmp_path, typ, tmp_path / "cv.pdf")
    monkeypatch.setattr(ats.shutil, "which", lambda _name: None)
    assert "Jamie Rivera" in " ".join(ats.extract_pdf_text(tmp_path / "cv.pdf").split())


# ---------------------------------------------------------------- coverage
def test_coverage_counts_synonyms_and_boundaries() -> None:
    jd = load("jd.json")
    must = [k for r in jd["requirements"] if r["kind"] == "must" for k in r["keywords"]]
    text = "Built Amazon Web Services stacks with ECS, plus github actions. Uses helmet daily."
    cov = coverage.coverage(text, jd)
    assert cov["must_keywords_total"] == len(dict.fromkeys(k.casefold() for k in must))
    assert {"AWS", "ECS", "GitHub Actions"} <= {t for r in cov["by_requirement"] for t in r["found_terms"]}  # synonym + case
    assert cov["must_keywords_found"] == cov["must_keywords_total"] - len(cov["missing"])
    assert "Helm" not in " ".join(t for r in cov["by_requirement"] for t in r["found_terms"])  # 'helmet' is not 'helm'
    assert {r["req_id"] for r in cov["by_requirement"]} == {r["id"] for r in jd["requirements"]}
    full = coverage.coverage(" ".join(must), jd)
    assert full["missing"] == [] and coverage.ratio(full) == 1.0


def test_coverage_gate_warns_below_threshold() -> None:
    cov = coverage.coverage("nothing relevant here", load("jd.json"))
    gate = validate._coverage_gate(cov)
    assert gate["status"] == "warn" and gate["details"][0].startswith("must-have keywords 0/")


# ---------------------------------------------------------------- page count and typography
def test_page_count_gate() -> None:
    t = load("tailored.json")
    fit = {"tailored_version": t["version"], "page_target": 1, "pages": 1, "underfilled": False}
    assert validate._page_count_gate(t, fit, 1)["status"] == "pass"
    assert validate._page_count_gate(t, fit, 2)["status"] == "fail"  # fit.json and the PDF disagree
    stale = validate._page_count_gate(t, {**fit, "tailored_version": 9}, 1)
    assert stale["status"] == "fail" and "tailored v9" in stale["details"][0]
    two = copy.deepcopy(t)
    two["target"]["page_target"] = 2
    under = {**fit, "page_target": 2, "underfilled": True}
    assert validate._page_count_gate(two, under, 1)["status"] == "warn"
    assert validate._page_count_gate(two, {**under, "underfilled": False}, 1)["status"] == "fail"


def test_typography_floor_gate() -> None:
    presets = json.loads((REPO_ROOT / ".claude/skills/tailoring-cvs/assets/templates/presets.json").read_text(encoding="utf-8"))
    model = model_for()
    assert validate._typography_gate(model, presets)["status"] == "pass"
    below = copy.deepcopy(presets)
    below["standard"]["body_pt"] = below["floor"]["body_pt"] - 0.5
    gate = validate._typography_gate(model, below)
    assert gate["status"] == "fail" and gate["violations"][0]["code"] == "typography"
    unknown = copy.deepcopy(model)
    unknown["theme"]["density"] = "tiny"
    assert "not a preset" in validate._typography_gate(unknown, presets)["details"][0]


# ---------------------------------------------------------------- layout
@needs_typst
def test_layout_warns_on_short_last_page_and_underfilled(tmp_path: Path) -> None:
    tailored = load("tailored.json")
    tailored["experience"], tailored["certifications"], tailored["education"] = [], [], []
    model = model_for(tailored)
    typ = render.write_build(tmp_path, model, "modern")
    render.compile_pdf(tmp_path, typ, tmp_path / "cv.pdf")
    fit = {"underfilled": True, "pages": 1, "page_target": 2}
    gate = validate._layout_gate(tmp_path / "cv.pdf", model, 0.6 * validate.POINTS_PER_INCH, fit)
    assert gate["status"] == "warn"
    messages = " | ".join(gate["details"])
    assert "page 1: content fits in 1 of 2" in messages and "page 1: last page is only" in messages


@needs_typst
def test_layout_passes_on_a_filled_page_and_works_without_pdftotext(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = model_for()
    typ = render.write_build(tmp_path, model, "modern")
    render.compile_pdf(tmp_path, typ, tmp_path / "cv.pdf")
    fit = {"underfilled": False, "pages": 1, "page_target": 1}
    margin = 0.6 * validate.POINTS_PER_INCH
    assert validate._layout_gate(tmp_path / "cv.pdf", model, margin, fit)["status"] == "pass"
    monkeypatch.setattr(validate.shutil, "which", lambda _name: None)
    assert validate._layout_gate(tmp_path / "cv.pdf", model, margin, fit)["status"] == "pass"


def test_layout_orphan_heading_names_the_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = model_for()
    pages = [
        validate.PageText(792.0, [(60.0, 70.0, "Some text"), (700.0, 710.0, "EXPERIENCE"), (720.0, 730.0, "Acme Corp")]),
        validate.PageText(792.0, [(60.0, 70.0, "More text"), (600.0, 700.0, "Last line"), (758.0, 769.0, "2/2")]),
    ]
    monkeypatch.setattr(validate, "_bbox_pages", lambda _pdf: pages)
    gate = validate._layout_gate(tmp_path / "x.pdf", model, 43.2, {"underfilled": False, "pages": 2, "page_target": 2})
    assert gate["status"] == "warn" and len(gate["violations"]) == 1
    assert gate["violations"][0] == {
        "code": "layout", "item_id": "page-1",
        "message": "page 1: section heading 'EXPERIENCE' is orphaned at the bottom of the page",
    }


# ---------------------------------------------------------------- full validate on the junior golden
@needs_typst
def test_validate_full_junior_run_writes_final(workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    run = fitted_run(workspace, tmp_path, capsys)
    code, out, err = cvt(["validate", str(run)], capsys)
    assert code == 0, err
    assert len(out.strip().splitlines()) <= 10 and "final pdf: final/" in out
    validation = jsonio.load_json(run / "validation.json")
    assert validation["passed"] and [g["name"] for g in validation["gates"]] == GATE_ORDER
    assert {g["name"]: g["status"] for g in validation["gates"]}["page_count"] == "pass"
    assert not [g for g in validation["gates"] if g["status"] == "fail"]
    final = run / "final" / FINAL_NAME
    assert final.is_file() and final.read_bytes() == (run / "cv.pdf").read_bytes()
    st = state.load(run)
    assert st["stage"] == "validated" and state.artifact(st, "final_pdf")["path"] == f"final/{FINAL_NAME}"
    assert "report" in st["next_action"]
    assert validation["coverage"]["must_keywords_total"] > 0


@needs_typst
def test_validate_json_envelope_is_compact(workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    run = fitted_run(workspace, tmp_path, capsys)
    code, out, _ = cvt(["validate", str(run), "--json"], capsys)
    env = json.loads(out)
    assert code == 0 and env["ok"] and len(out.strip().splitlines()) == 1
    assert env["data"]["final_pdf"] == f"final/{FINAL_NAME}" and set(env["data"]["gates"]) == set(GATE_ORDER)


@needs_typst
def test_placeholders_fail_without_draft_and_warn_with_draft(workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    tailored = load("tailored.json")
    tailored["experience"][0]["bullets"][0]["text"] += CONFIRM
    run = fitted_run(workspace, tmp_path, capsys, tailored)
    code, _out, err = cvt(["validate", str(run)], capsys)
    assert code == int(ExitCode.CHECK_FAILED) and "placeholders" in err and "[[CONFIRM: team size]]" in err
    failed = jsonio.load_json(run / "validation.json")
    assert not failed["passed"] and {g["name"]: g["status"] for g in failed["gates"]}["placeholders"] == "fail"
    assert not (run / "final").exists() and state.load(run)["stage"] == "rendered"
    code, out, err = cvt(["validate", str(run), "--draft"], capsys)
    assert code == 0, err
    drafted = jsonio.load_json(run / "validation.json")
    assert drafted["passed"] and drafted["draft"]
    assert {g["name"]: g["status"] for g in drafted["gates"]}["placeholders"] == "warn"
    assert "warn placeholders" in out and "final pdf" not in out
    assert not (run / "final").exists() and state.load(run)["stage"] == "rendered"


@needs_typst
def test_proposed_attestation_fails_validate_until_active(workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    run = fitted_run(workspace, tmp_path, capsys)
    store = attestations.load_store(PERSON)
    att_id = store["attestations"][0]["id"]
    store["attestations"][0]["status"] = attestations.STATUS_PROPOSED
    store["attestations"][0]["run_id"] = run.name
    attestations.save_store(PERSON, store)
    code, _out, err = cvt(["validate", str(run)], capsys)
    assert code == int(ExitCode.CHECK_FAILED) and "attestation_status" in err
    assert cvt(["validate", str(run), "--draft"], capsys)[0] == 0
    store = attestations.load_store(PERSON)
    attestations.set_status(store, att_id, attestations.STATUS_ACTIVE)
    attestations.save_store(PERSON, store)
    assert cvt(["validate", str(run)], capsys)[0] == 0


def test_validate_requires_rendered_stage(workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    run = junior_run(workspace, tmp_path)
    code, _out, err = cvt(["validate", str(run)], capsys)
    assert code == int(ExitCode.STATE) and "E_STAGE" in err


def test_final_pdf_name_omits_empty_company() -> None:
    jd = load("jd.json")
    t = load("tailored.json")
    assert validate.final_pdf_name(t, jd) == FINAL_NAME
    assert validate.final_pdf_name(t, {**jd, "company": ""}) == "Jamie-Rivera-Junior-DevOps-Engineer.pdf"
    assert validate.name_slug("Zoë O'Neil") == "Zoe-O-Neil"
