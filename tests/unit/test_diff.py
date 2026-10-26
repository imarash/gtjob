"""WP-16: diff.diff_items / outline / render_diff_md and `cvt diff` on the junior golden."""

from __future__ import annotations

import copy
import json
import re
import shutil
from pathlib import Path

import pytest

from cvtlib import attestations, cli, diff, edits, jsonio, state

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "tests" / "fixtures" / "golden" / "junior"
PERSON = "jamie-rivera"
MAX_COMPACT_LINES = 40
MAX_OUTLINE_LINES = 12
EXIT_OK, EXIT_STATE = 0, 4


@pytest.fixture
def profile() -> dict:
    return jsonio.load_json(GOLDEN / "profile.json")


@pytest.fixture
def tailored() -> dict:
    return jsonio.load_json(GOLDEN / "tailored.json")


def by_id(items: list[dict]) -> dict[str, dict]:
    return {i["id"]: i for i in items}


# --- diff_items ---------------------------------------------------------------------------------------
def test_against_profile_kinds(tailored, profile):
    items = by_id(diff.diff_items(tailored, profile, None))
    assert items["t-exp-1.b1"]["kind"] == "kept" and items["t-exp-1.b1"]["before"] == items["t-exp-1.b1"]["after"]
    assert items["t-exp-1.b2"]["kind"] == "rewritten" and items["t-exp-1.b2"]["before"].startswith("Wrote Terraform")
    assert items["t-exp-1.b4"]["kind"] == "attested" and items["t-exp-1.b4"]["source_refs"] == ["exp-1.b3", "att-001"]
    assert items["t-exp-1.b4"]["before"] == items["t-exp-1.b3"]["before"]  # bullet-level profile ref preferred
    assert items["t-sum"]["section"] == "summary" and items["t-skl-1"]["kind"] == "attested"
    assert items["t-header"]["before"] == profile["basics"]["label"]
    assert all(i["review"] == "pending" for i in items.values() if i["id"].startswith("t-exp-1.b"))


def test_omitted_become_dropped_items(tailored, profile):
    items = diff.diff_items(tailored, profile, None)
    dropped = [i for i in items if i["kind"] == "dropped"]
    assert [d["id"] for d in dropped] == ["exp-1.b6", "exp-2.b3"]
    assert dropped[0]["before"] and dropped[0]["after"] == "" and dropped[0]["note"]


def test_item_order_is_document_order(tailored, profile):
    ids = [i["id"] for i in diff.diff_items(tailored, profile, None)]
    assert ids[:2] == ["t-header", "t-sum"] and ids.index("t-skl-1") < ids.index("t-exp-1.b1")
    assert ids.index("t-exp-1.b6") < ids.index("t-exp-2.b1")


def test_kept_origin_with_changed_text_is_rewritten(tailored, profile):
    t = copy.deepcopy(tailored)
    edits.locate(t, "t-exp-1.b1")[1]["text"] = "Changed wording."
    assert by_id(diff.diff_items(t, profile, None))["t-exp-1.b1"]["kind"] == "rewritten"


def test_against_previous_added_changed_dropped(tailored, profile):
    new = copy.deepcopy(tailored)
    edits.locate(new, "t-exp-1.b2")[1]["text"] = "Different text."
    new["experience"][0]["bullets"] = [b for b in new["experience"][0]["bullets"] if b["id"] != "t-exp-1.b3"]
    new["experience"][0]["bullets"].append(
        {"id": "t-exp-1.b9", "text": "Brand new.", "source_refs": ["exp-1.b6"], "priority": 3, "origin": "kept",
         "review": "pending"})
    items = by_id(diff.diff_items(new, profile, tailored))
    assert items["t-exp-1.b2"]["kind"] == "changed" and items["t-exp-1.b2"]["before"] == by_id(
        diff.diff_items(tailored, profile, None))["t-exp-1.b2"]["after"]
    assert items["t-exp-1.b3"]["kind"] == "dropped" and items["t-exp-1.b3"]["after"] == ""
    assert items["t-exp-1.b9"]["kind"] == "added" and items["t-exp-1.b9"]["before"] == ""
    assert items["t-exp-1.b1"]["kind"] == "kept"
    assert not any(i["section"] == "omitted" for i in items.values())


def test_review_flag_changes_alone_are_not_changes(tailored, profile):
    approved = edits.apply_ops(tailored, [{"op": "approve_all", "target_id": "", "field": "", "value": "",
                                            "source_refs": [], "items": []}], profile)
    assert diff.changed_items(diff.diff_items(approved, profile, tailored)) == []


def test_earlier_line_is_an_item_only_when_included(tailored, profile):
    t = copy.deepcopy(tailored)
    t["earlier_experience"] = {"include": True, "review": "pending", "items": [{
        "profile_id": "exp-2", "employer": "Cedar Valley College", "title": "IT Support Intern",
        "start_date": "2023-07", "end_date": "2023-12"}]}
    item = by_id(diff.diff_items(t, profile, None))["t-earlier"]
    assert item["section"] == "earlier" and "Cedar Valley College" in item["after"]
    assert "t-earlier" not in by_id(diff.diff_items(tailored, profile, None))


# --- outline ------------------------------------------------------------------------------------------
def test_outline_is_short_and_labels_the_estimate(tailored):
    text = diff.outline(tailored)
    lines = text.splitlines()
    assert len(lines) <= MAX_OUTLINE_LINES and "estimate" in lines[0]
    assert "Brightfield Logistics" in text and "Cedar Valley College" in text and "6 bullets" in text
    assert diff.ESTIMATED_LINES_PER_PAGE == 58


def test_outline_caps_many_roles_and_lists_engagements(tailored):
    t = copy.deepcopy(tailored)
    t["experience"] = [copy.deepcopy(t["experience"][0]) for _ in range(10)]
    t["experience"][0]["engagements"] = [{
        "id": "t-exp-1.e1", "profile_id": "exp-1.e1", "kind": "client", "name": "Acme Corp", "role_label": "SRE",
        "bullets": [], "priority": 3, "review": "pending"}]
    lines = diff.outline(t).splitlines()
    assert len(lines) <= MAX_OUTLINE_LINES and any("+5 more roles" in ln for ln in lines)
    assert any("Acme Corp (0)" in ln for ln in lines)


# --- markdown -----------------------------------------------------------------------------------------
def test_full_markdown_is_numbered_with_blockquotes(tailored, profile):
    items = diff.diff_items(tailored, profile, None)
    text = diff.render_diff_md(items, diff.outline(tailored))
    n = [i["id"] for i in items].index("t-exp-1.b2") + 1
    assert f"[{n}] t-exp-1.b2 (rewritten; refs exp-1.b2)" in text
    assert re.search(r"\[\d+\] t-exp-1\.b4 \(attested; refs exp-1\.b3, att-001\)", text)
    assert "> before: Wrote Terraform" in text and "> after: Replaced manual" in text
    numbers = [int(m) for m in re.findall(r"^\[(\d+)\] ", text, re.M)]
    assert numbers == list(range(1, len(items) + 1))


def test_compact_markdown_lists_changed_items_only(tailored, profile):
    items = diff.diff_items(tailored, profile, None)
    text = diff.render_diff_md(items, diff.outline(tailored), compact=True)
    assert "kept (not listed): 5 bullets, 1 other items" in text
    assert "t-exp-1.b1" not in text and "t-exp-1.b2 rewritten (refs: exp-1.b2): " in text
    assert "| was: Wrote Terraform" in text
    line_b4 = next(ln for ln in text.splitlines() if "t-exp-1.b4" in ln)
    assert "was:" not in line_b4 and "attested" in line_b4
    n = [i["id"] for i in items].index("t-exp-1.b2") + 1
    assert f"[{n}] t-exp-1.b2" in text  # same numbers as the full view


def test_excerpt_is_160_chars(tailored, profile):
    long = "word " * 100
    out = diff.excerpt(long)
    assert len(out) == diff.EXCERPT_CHARS and out.endswith("…")
    assert diff.excerpt("short  text") == "short text"


# --- command ------------------------------------------------------------------------------------------
@pytest.fixture
def run(workspace: Path) -> Path:
    cv = workspace / "cv.txt"
    cv.write_text("Jamie Rivera\njamie.rivera@example.com\n", encoding="utf-8")
    run_dir = state.create_run(cv, "text", "jd", "Junior DevOps Engineer at Harbor Point", {}, slug="junior")
    st = state.load(run_dir)
    for name, art in (("profile.json", "profile"), ("jd.json", "jd"), ("tailored.json", "tailored")):
        shutil.copy(GOLDEN / name, run_dir / name)
        state.record_artifact(run_dir, st, art, name, cascade=False)
    st["person_slug"] = PERSON
    state.set_stage(st, "tailored")
    state.save(run_dir, st)
    store = attestations.load_store(PERSON)
    proposal = jsonio.load_json(GOLDEN / "answers.round.json")["items"][0]["attestations"][0]
    attestations.add(store, proposal, run_id=st["run_slug"], question_id="q-1")
    attestations.save_store(PERSON, store)
    return run_dir


def cvt(capsys, *args: str, json_mode: bool = True) -> tuple[int, str]:
    code = cli.main([*(["--json"] if json_mode else []), *args])
    return code, capsys.readouterr().out


def test_diff_compact_output_is_short(run, capsys):
    code, out = cvt(capsys, "diff", run.name, json_mode=False)
    lines = out.strip().splitlines()
    assert code == EXIT_OK and len(lines) < MAX_COMPACT_LINES, out
    assert lines[0].startswith("Outline (estimate") and "kept (not listed)" in out
    assert "t-exp-1.b1" not in out and "t-exp-1.b2 rewritten" in out and lines[-1].startswith("next: ")


def test_diff_full_lists_every_item(run, capsys):
    code, out = cvt(capsys, "diff", run.name, "--full", json_mode=False)
    assert code == EXIT_OK
    tailored = jsonio.load_json(run / "tailored.json")
    for bid in (b["id"] for e in tailored["experience"] for b in e["bullets"]):
        assert f" {bid} (" in out, bid
    assert len(out.splitlines()) > MAX_COMPACT_LINES


def test_diff_sets_awaiting_approval(run, capsys):
    code, out = cvt(capsys, "diff", run.name)
    env = json.loads(out)
    assert code == EXIT_OK and env["stage"] == "awaiting_approval" and env["data"]["against"] == "profile"
    st = state.load(run)
    assert st["status"] == "awaiting_user" and st["checkpoints"]["cp2"] == "pending"
    assert st["pending"]["kind"] == "approval"
    kinds = {i["kind"] for i in env["data"]["items"]}
    assert "kept" not in kinds and env["data"]["counts"]["kept"] > 0
    assert env["data"]["pending"] and len(out.strip().splitlines()) == 1  # one minified line


def test_diff_json_full_vs_compact(run, capsys):
    _, compact = cvt(capsys, "diff", run.name)
    _, full = cvt(capsys, "diff", run.name, "--full")
    c, f = json.loads(compact)["data"], json.loads(full)["data"]
    assert len(f["items"]) > len(c["items"]) and f["full"] and not c["full"]
    assert all(len(i["after"]) <= diff.EXCERPT_CHARS for i in c["items"])
    code, out = cvt(capsys, "diff", run.name, "--format", "json", json_mode=False)
    assert code == EXIT_OK and json.loads(out.splitlines()[0])["counts"] == c["counts"]


def test_diff_auto_mode_marks_review_auto_and_approves(workspace, run, capsys):
    st = state.load(run)
    st["options"]["auto"] = True
    state.save(run, st)
    code, out = cvt(capsys, "diff", run.name)
    env = json.loads(out)
    assert code == EXIT_OK and env["stage"] == "approved" and env["data"]["pending"] == []
    t = jsonio.load_json(run / "tailored.json")
    assert t["summary"]["review"] == "auto" and all(b["review"] == "auto" for b in t["experience"][0]["bullets"])
    assert state.load(run)["checkpoints"]["cp2"] == "skipped"
    assert [a["status"] for a in attestations.load_store(PERSON)["attestations"]] == ["proposed"]  # auto never activates


def test_diff_after_approval_does_not_regress_stage(run, capsys):
    assert cli.main(["--json", "approve", run.name, "--all"]) == EXIT_OK
    capsys.readouterr()
    code, out = cvt(capsys, "diff", run.name)
    assert code == EXIT_OK and json.loads(out)["stage"] == "approved"
    assert state.load(run)["checkpoints"]["cp2"] == "done"


def test_diff_against_previous(run, capsys):
    code, out = cvt(capsys, "diff", run.name, "--against", "previous")
    assert code == EXIT_STATE and json.loads(out)["error"]["id"] == "E_NO_PREVIOUS"
    edit = run / "edits" / "next.json"
    edit.parent.mkdir()
    edit.write_text(json.dumps({"schema_version": "1", "run_id": "x", "source": "cli", "raw_text": "drop", "ops": [
        {"op": "drop", "target_id": "t-exp-1.b1", "field": "", "value": "", "source_refs": [], "items": []}]}),
        encoding="utf-8")
    assert cli.main(["--json", "apply-edits", run.name, str(edit)]) == EXIT_OK
    capsys.readouterr()
    code, out = cvt(capsys, "diff", run.name, "--against", "previous")
    env = json.loads(out)
    assert code == EXIT_OK and [i["id"] for i in env["data"]["items"]] == ["t-exp-1.b1"]
    assert env["data"]["items"][0]["kind"] == "dropped"


def test_diff_needs_tailored_stage(run, capsys):
    st = state.load(run)
    state.set_stage(st, "answers_applied")
    state.save(run, st)
    code, out = cvt(capsys, "diff", run.name)
    assert code == EXIT_STATE and json.loads(out)["error"]["id"] == "E_STAGE"
