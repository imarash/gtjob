"""Consistency eval: the junior pipeline run 3 times with identical answers and `--no-cache` (WP-23).

Every iteration gets its own empty workspace, because attestations and the profile cache from run 1 would otherwise
change the questions in run 2. The runs must agree on what was selected, how it is ordered, how long it is, and what
the user attested; provenance must pass every time; and bullet counts per role may drift by at most 2.

Unmarked tests cover the fingerprint and comparison helpers (no model).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from conftest import EXIT_OK, GOLDEN_JUNIOR, JUNIOR_CV, JUNIOR_JD, Cvt, run_gtjob, write_answers_yaml

RUNS = 3
MAX_BULLET_DRIFT = 2
HELM_REPLY = "I used Helm at Brightfield to package two internal services"
FIRST_QUESTION = "q-1"
SECTION_HEADINGS = ("summary", "skills", "experience", "education", "certifications", "earlier experience")


# ------------------------------------------------------------------ pure helpers
def walk_bullets(node: object, counts: dict[str, int]) -> None:
    """Bullet count per `profile_id` (works and nested engagements), recursively."""
    if isinstance(node, dict):
        if "profile_id" in node and "bullets" in node:
            counts[node["profile_id"]] = counts.get(node["profile_id"], 0) + len(node["bullets"])
        for value in node.values():
            walk_bullets(value, counts)
    elif isinstance(node, list):
        for value in node:
            walk_bullets(value, counts)


def section_order(text: str) -> list[str]:
    """Known section headings in the order they first appear in the PDF text (case-insensitive)."""
    lowered = text.lower()
    found = [(lowered.find(heading), heading) for heading in SECTION_HEADINGS if heading in lowered]
    return [heading for _, heading in sorted(found)]


def fingerprint(*, tailored: dict, pdf_text: str, pages: int, validation: dict, attestations: list[dict]) -> dict:
    counts: dict[str, int] = {}
    walk_bullets(tailored.get("experience", []), counts)
    gates = {gate["name"]: gate["status"] for gate in validation.get("gates", [])}
    return {
        "roles": sorted(counts),
        "bullets": counts,
        "sections": section_order(pdf_text),
        "pages": pages,
        "claims": sorted(att["claim"].lower() for att in attestations),
        "provenance": gates.get("provenance"),
    }


def compare_fingerprints(prints: list[dict], max_drift: int = MAX_BULLET_DRIFT) -> list[str]:
    """Disagreements between runs; the first run is the reference."""
    problems = []
    ref = prints[0]
    for index, other in enumerate(prints, start=1):
        if other["provenance"] != "pass":
            problems.append(f"run {index}: provenance gate is {other['provenance']}")
    for index, other in enumerate(prints[1:], start=2):
        for key, label in (("roles", "selected engagements and roles"), ("sections", "section order"),
                           ("pages", "page count"), ("claims", "attestation claims")):
            if other[key] != ref[key]:
                problems.append(f"run {index}: {label} differ: {other[key]} != {ref[key]}")
        for role in ref["roles"]:
            drift = abs(other["bullets"].get(role, 0) - ref["bullets"][role])
            if drift > max_drift:
                problems.append(f"run {index}: {role} bullet count drifts by {drift} (> {max_drift})")
    return problems


def golden_fingerprint() -> dict:
    tailored = json.loads((GOLDEN_JUNIOR / "tailored.json").read_text(encoding="utf-8"))
    return fingerprint(tailored=tailored, pdf_text="Summary\nSkills\nExperience\nEducation", pages=1,
                       validation={"gates": [{"name": "provenance", "status": "pass"}]},
                       attestations=[{"claim": "Helm"}])


def test_fingerprint_of_the_junior_golden() -> None:
    print_ = golden_fingerprint()
    assert print_["roles"] and all(count >= 1 for count in print_["bullets"].values())
    assert print_["sections"] == ["summary", "skills", "experience", "education"]
    assert print_["claims"] == ["helm"] and print_["provenance"] == "pass"


def test_identical_runs_agree_and_drift_is_bounded() -> None:
    ref = golden_fingerprint()
    assert compare_fingerprints([ref, copy.deepcopy(ref), copy.deepcopy(ref)]) == []
    role = ref["roles"][0]
    near = copy.deepcopy(ref)
    near["bullets"][role] += MAX_BULLET_DRIFT
    assert compare_fingerprints([ref, near]) == []
    far = copy.deepcopy(ref)
    far["bullets"][role] += MAX_BULLET_DRIFT + 1
    assert any("drifts" in p for p in compare_fingerprints([ref, far]))


@pytest.mark.parametrize("key, value, needle", [
    ("roles", ["exp-9"], "selected engagements"),
    ("sections", ["experience", "skills"], "section order"),
    ("pages", 2, "page count"),
    ("claims", ["helm", "kafka"], "attestation claims"),
    ("provenance", "fail", "provenance"),
])
def test_each_disagreement_is_reported(key: str, value: object, needle: str) -> None:
    ref = golden_fingerprint()
    other = copy.deepcopy(ref)
    other[key] = value
    problems = compare_fingerprints([ref, other])
    assert any(needle in p for p in problems), problems


# ------------------------------------------------------------------ live
@pytest.mark.live
def test_junior_pipeline_is_consistent(needs_key, tmp_path: Path) -> None:
    from judge import page_count, pdf_text

    answers = write_answers_yaml(tmp_path / "answers.yaml",
                                 checkpoint1={FIRST_QUESTION: HELM_REPLY, "default_rest": True})
    prints = []
    for index in range(1, RUNS + 1):
        home = tmp_path / f"ws{index}"
        cvt = Cvt(home)
        proc = run_gtjob(home, "tailor", "--cv", str(JUNIOR_CV), "--jd", str(JUNIOR_JD), "--slug", "consistency",
                         "--answers", str(answers), "--no-cache")
        assert proc.returncode == EXIT_OK, f"run {index} exited {proc.returncode}:\n{proc.stderr[-1500:]}"
        run_dir = next((home / "out").glob("*consistency*"))
        state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        prints.append(fingerprint(
            tailored=json.loads((run_dir / "tailored.json").read_text(encoding="utf-8")),
            pdf_text=pdf_text(run_dir / "cv.pdf"), pages=page_count(run_dir / "cv.pdf"),
            validation=json.loads((run_dir / "validation.json").read_text(encoding="utf-8")),
            attestations=cvt.attestations(state["person_slug"])))
    problems = compare_fingerprints(prints)
    assert problems == [], "\n".join(problems)
