"""WP-14: drop order, the monotone page-fit search, and `cvt fit`."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import REPO_ROOT
from cvtlib import cli, fit, jsonio, render, state
from cvtlib.errors import CvtError, ExitCode

GOLDEN = REPO_ROOT / "tests" / "fixtures" / "golden" / "junior"
JUNIOR_TAILORED = GOLDEN / "tailored.json"
LOG_DIR = REPO_ROOT / ".cache" / "logs" / "WP-14"
JUNIOR_DROP_ORDER = [
    "t-exp-2.b1", "t-exp-2.b2", "t-exp-1.b6", "t-skl-4", "t-skl-3", "t-exp-1.b5", "t-exp-1.b4", "t-exp-1.b3",
    "t-cert-1", "t-skl-2",
]
SYNTHETIC_BULLETS_PER_ENTRY = 14
SYNTHETIC_ENTRIES = (("2015-03", "2017-06"), ("2017-07", "2020-12"), ("2021-01", "present"))
SYNTHETIC_PRIORITIES = (1, 2, 3, 4, 5, 2, 3)
BULLET_TEXT = (
    "Maintained internal service {n} and its deployment pipeline, reviewing changes with two teammates every week "
    "and keeping the runbook for the service current after each release."
)
EXIT_USAGE_FAIL = int(ExitCode.CHECK_FAILED)


# ---------------------------------------------------------------- helpers
def junior() -> dict:
    return json.loads(JUNIOR_TAILORED.read_text(encoding="utf-8"))


def synthetic(page_target: int = 1, pinned_only: bool = False) -> dict:
    """The junior header and a 3-employer, 42-bullet body. Text is invented and generic."""
    t = junior()
    t["target"]["page_target"] = page_target
    t["skills"], t["certifications"], t["education"] = t["skills"][:2], [], []
    t["experience"] = []
    number = 0
    for e_index, (start, end) in enumerate(SYNTHETIC_ENTRIES, start=1):
        bullets = []
        for b_index in range(1, SYNTHETIC_BULLETS_PER_ENTRY + 1):
            number += 1
            priority = 1 if pinned_only else SYNTHETIC_PRIORITIES[(b_index - 1) % len(SYNTHETIC_PRIORITIES)]
            bullets.append({
                "id": f"t-exp-{e_index}.b{b_index}", "text": BULLET_TEXT.format(n=number), "source_refs": ["exp-1.b1"],
                "priority": priority, "origin": "kept", "review": "pending",
            })
        t["experience"].append({
            "id": f"t-exp-{e_index}", "profile_id": f"exp-{e_index}", "employer": f"Employer {e_index}", "location": "Columbus, OH",
            "title": "Engineer", "start_date": start, "end_date": end, "intro": {"text": "", "source_refs": []},
            "bullets": bullets, "engagements": [], "priority": 1, "review": "pending",
        })
    return t


def make_run(workspace: Path, tmp_path: Path, tailored: dict, stage: str = "approved") -> Path:
    cv = tmp_path / "cv.txt"
    cv.write_text("Test Person\n", encoding="utf-8")
    run = state.create_run(cv, "text", "pasted", "Engineer", {"template": "modern"}, slug="fit-test")
    jsonio.dump_json(tailored, run / "tailored.json")
    st = state.load(run)
    state.record_artifact(run, st, "tailored", "tailored.json")
    state.set_stage(st, stage)
    state.save(run, st)
    return run


def pages_at(run: Path, density: str, dropped: list[str]) -> int:
    return render.render_run(run, density=density, dropped_ids=set(dropped), out_pdf=run / fit.SCRATCH_PDF).pages


def save_log(name: str, lines: list[str]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- drop order
def test_drop_order_junior_golden() -> None:
    assert fit.drop_order(junior()) == JUNIOR_DROP_ORDER


def test_drop_order_excludes_pinned_and_ranks_by_priority_age_position() -> None:
    t = synthetic()
    order = fit.drop_order(t)
    pinned = {b["id"] for e in t["experience"] for b in e["bullets"] if b["priority"] == 1}
    assert pinned and not pinned & set(order)
    assert all(g["id"] not in order for g in t["skills"] if g["priority"] == 1)
    effective = {b["id"]: (b["priority"], e["start_date"], i) for e in t["experience"] for i, b in enumerate(e["bullets"])}
    keys = [(-effective[x][0], effective[x][1], -effective[x][2]) for x in order if x in effective]
    assert keys == sorted(keys)  # priority desc, oldest employer first, last bullet first
    assert order[0] == "t-exp-1.b12"  # the last priority-5 bullet of the oldest employer


def test_drop_order_inherits_parent_priority_floor() -> None:
    t = junior()
    t["experience"][0]["bullets"][2]["priority"] = 2
    t["experience"][0]["priority"] = 4  # raises every bullet of the entry to at least 4
    order = fit.drop_order(t)
    assert "t-exp-1.b1" in order and "t-exp-1.b3" in order  # priority-1 bullets drop once the entry is priority 4
    assert order.index("t-exp-1.b6") < order.index("t-exp-1.b3")  # equal effective priority: later bullet first
    t["experience"][0]["priority"] = 1
    t["experience"][0]["engagements"] = [{
        "id": "t-exp-1.e1", "profile_id": "exp-1.e1", "kind": "client", "name": "Client", "role_label": "", "priority": 3,
        "review": "pending", "bullets": [{
            "id": "t-exp-1.e1.b1", "text": "x", "source_refs": [], "priority": 1, "origin": "kept", "review": "pending",
        }],
    }]
    assert "t-exp-1.e1.b1" in fit.drop_order(t)  # engagement priority 3 floors its priority-1 bullet


# ---------------------------------------------------------------- search with a deterministic page model
def _fake_renderer(monkeypatch: pytest.MonkeyPatch, pages_for) -> list[tuple[str, int]]:
    calls: list[tuple[str, int]] = []

    def fake(run_dir, *, density=None, dropped_ids=None, out_pdf=None, png=False, **_):
        calls.append((density, len(dropped_ids)))
        return SimpleNamespace(pages=pages_for(density, len(dropped_ids)))

    monkeypatch.setattr(render, "render_run", fake)
    return calls


def test_search_finds_minimal_k(workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tailored = synthetic(page_target=2)
    run = make_run(workspace, tmp_path, tailored)
    units = fit.drop_order(tailored)
    need = 17

    def pages_for(density: str, k: int) -> int:
        return 2 if k >= need else 3

    calls = _fake_renderer(monkeypatch, pages_for)
    result = fit.fit_run(run)
    assert result["dropped_ids"] == units[:need] and result["density"] == "compact" and result["pages"] == 2
    assert result["renders"] == len(calls) <= fit.MAX_RENDERS
    assert result["log"][:3] == ["comfortable: 3 pages", "standard: 3 pages", "compact: 3 pages"]
    assert f"k={need}: 2 pages" in result["log"] and f"k={need - 1}: 3 pages" in result["log"]
    assert not result["underfilled"]
    assert jsonio.load_json(run / "fit.json") == result
    save_log("fit-fake-search.log", result["log"])


def test_density_pass_stops_at_first_fit_without_drops(workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = make_run(workspace, tmp_path, synthetic(page_target=2))
    calls = _fake_renderer(monkeypatch, lambda density, k: 2 if density != "comfortable" else 3)
    result = fit.fit_run(run)
    assert (result["density"], result["dropped_ids"]) == ("standard", [])
    assert calls == [("comfortable", 0), ("standard", 0), ("standard", 0)]  # two trials, then the final render


def test_render_cap_is_exit_7(workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = make_run(workspace, tmp_path, synthetic(page_target=2))
    _fake_renderer(monkeypatch, lambda density, k: 3 if k < 5 else 2)
    monkeypatch.setattr(fit, "MAX_RENDERS", 5)
    with pytest.raises(CvtError) as err:
        fit.fit_run(run)
    assert err.value.code == ExitCode.INTERNAL and err.value.err_id == "E_FIT_RENDER_CAP"


# ---------------------------------------------------------------- real compiles
@pytest.mark.skipif(render.detect_backend() == "none", reason="no Typst backend")
def test_monotone_pages_and_minimal_k_on_40_bullets(workspace: Path, tmp_path: Path) -> None:
    tailored = synthetic(page_target=1)
    run = make_run(workspace, tmp_path, tailored)
    units = fit.drop_order(tailored)
    steps = sorted({0, *range(0, len(units) + 1, 4), len(units)})
    counts = [pages_at(run, "compact", units[:k]) for k in steps]
    assert counts == sorted(counts, reverse=True), dict(zip(steps, counts))  # non-increasing in k
    assert counts[0] > 1 and counts[-1] == 1
    result = fit.fit_run(run)
    k = len(result["dropped_ids"])
    assert result["dropped_ids"] == units[:k] and result["pages"] == 1 and result["density"] == "compact"
    assert pages_at(run, "compact", units[: k - 1]) > 1  # one fewer drop overflows: k is minimal
    assert result["renders"] <= fit.MAX_RENDERS
    assert render.load_fit(run, tailored) == result
    assert (run / "cv.pdf").is_file()
    save_log("fit-synthetic-40.log", [f"units={len(units)} k={k} renders={result['renders']}", *result["log"]])


@pytest.mark.skipif(render.detect_backend() == "none", reason="no Typst backend")
def test_pinned_overflow_exits_1(workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    run = make_run(workspace, tmp_path, synthetic(page_target=1, pinned_only=True))
    with pytest.raises(CvtError) as err:
        fit.fit_run(run)
    assert err.value.code == ExitCode.CHECK_FAILED
    assert err.value.message == "content with priority 1 exceeds 1 pages; lower some priorities or shorten bullets"
    assert not (run / "fit.json").exists()
    assert cli.main(["fit", str(run)]) == EXIT_USAGE_FAIL
    assert "E_FIT_OVERFLOW" in capsys.readouterr().err
    assert state.load(run)["status"] == "failed"


@pytest.mark.skipif(render.detect_backend() == "none", reason="no Typst backend")
@pytest.mark.parametrize(("target", "underfilled"), [(1, False), (2, True)])
def test_underfilled_flag(workspace: Path, tmp_path: Path, target: int, underfilled: bool) -> None:
    tailored = junior()
    tailored["target"]["page_target"] = target
    run = make_run(workspace, tmp_path, tailored)
    result = fit.fit_run(run)
    assert result["pages"] == 1 and result["underfilled"] is underfilled
    assert result["density"] == "comfortable" and result["dropped_ids"] == []
    save_log(f"fit-junior-target{target}.log", result["log"])


@pytest.mark.skipif(render.detect_backend() == "none", reason="no Typst backend")
def test_fit_command_records_state_and_png_only_on_request(workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    run = make_run(workspace, tmp_path, junior())
    assert cli.main(["fit", str(run), "--json"]) == 0
    env = json.loads(capsys.readouterr().out)
    assert env["ok"] and env["data"]["pages"] == 1 and env["stage"] == "rendered"
    st = state.load(run)
    assert {a["name"] for a in st["artifacts"]} >= {"fit", "pdf", "render_model", "markdown_fallback"}
    assert not (run / "pages").exists()
    assert cli.main(["fit", str(run), "--png", "--json"]) == 0
    capsys.readouterr()
    assert (run / "pages" / "page-1.png").is_file()


def test_fit_requires_approval(workspace: Path, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    run = make_run(workspace, tmp_path, copy.deepcopy(junior()), stage="tailored")
    assert cli.main(["fit", str(run)]) == int(ExitCode.STATE)
    assert "E_STAGE" in capsys.readouterr().err
