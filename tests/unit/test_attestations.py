"""WP-11: attestation store, scope resolution, and the `cvt attest` command."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cvtlib import attestations, jsonio, schemas, scope, state
from cvtlib.errors import CvtError, ExitCode

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "profile" / "nested-engagements.json"
PERSON = "sam-testperson"
RUN_A, RUN_B = "run-a", "run-b"
SRE_IDS = ["exp-2.e4", "exp-2.e5"]
BANK_ID = "exp-2.e4"


@pytest.fixture
def profile() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _scope(kind: str = "global", role_label: str = "", item_ids: list[str] | None = None, desc: str = "") -> dict:
    return {"kind": kind, "role_label": role_label, "item_ids": item_ids or [], "description": desc}


def _proposal(claim: str = "Istio", terms: list[str] | None = None, sc: dict | None = None) -> dict:
    return {
        "type": "skill", "claim": claim, "terms": terms or [claim], "detail": "", "scope": sc or _scope(),
        "placement": "skills", "correction": {"item_id": "", "field": "", "old_value": "", "new_value": ""},
        "verbatim": f"add {claim}", "caveat": "",
    }


def _store() -> dict:
    return attestations.empty_store(PERSON)


# --- fixture shape -----------------------------------------------------------------------------------------

def test_fixture_is_valid_and_shaped_like_the_sample(profile: dict) -> None:
    assert schemas.validate(profile, "profile") == []
    assert len(profile["work"]) == 3
    engagements = [e for w in profile["work"] for e in w["engagements"]]
    assert len(engagements) == 10
    assert [e["id"] for e in engagements if e["role_label"] == "SRE"] == SRE_IDS


# --- store -------------------------------------------------------------------------------------------------

def test_load_missing_store_is_empty_and_valid(workspace: Path) -> None:
    store = attestations.load_store(PERSON)
    assert store["next_seq"] == 1 and store["attestations"] == []
    assert schemas.validate(store, "attestations") == []
    assert not (workspace / "profiles" / PERSON / "attestations.json").exists()


def test_add_assigns_ids_and_copies_fields() -> None:
    store = _store()
    a1 = attestations.add(store, _proposal("Istio"), run_id=RUN_A, question_id="q-1")
    a2 = attestations.add(store, _proposal("SLOs", ["SLO", "SLOs"]), run_id=RUN_A, question_id="")
    assert (a1["id"], a2["id"]) == ("att-001", "att-002")
    assert store["next_seq"] == 3
    assert a1["status"] == "proposed" and a1["run_id"] == RUN_A and a1["question_id"] == "q-1"
    assert a1["created_at"] == a1["status_changed_at"]
    assert a2["terms"] == ["SLO", "SLOs"] and a1["claim"] == "Istio"
    assert schemas.validate(store, "attestations") == []


def test_add_does_not_alias_the_proposal() -> None:
    store, proposal = _store(), _proposal()
    att = attestations.add(store, proposal, run_id=RUN_A, question_id="")
    proposal["terms"].append("mutated")
    assert att["terms"] == ["Istio"]


def test_add_rejects_incomplete_proposal() -> None:
    bad = _proposal()
    del bad["caveat"]
    with pytest.raises(CvtError) as exc:
        attestations.add(_store(), bad, run_id=RUN_A, question_id="")
    assert exc.value.err_id == "E_ATTEST_FIELDS"


def test_next_seq_never_reused_after_revoke() -> None:
    store = _store()
    attestations.add(store, _proposal("A"), run_id=RUN_A, question_id="")
    attestations.set_status(store, "att-001", "revoked")
    again = attestations.add(store, _proposal("B"), run_id=RUN_A, question_id="")
    assert again["id"] == "att-002" and store["next_seq"] == 3


def test_save_and_reload_round_trip(workspace: Path) -> None:
    store = attestations.load_store(PERSON)
    attestations.add(store, _proposal(), run_id=RUN_A, question_id="q-1")
    attestations.save_store(PERSON, store)
    path = workspace / "profiles" / PERSON / "attestations.json"
    assert schemas.validate(jsonio.load_json(path), "attestations") == []
    assert attestations.load_store(PERSON) == store
    assert list(path.parent.glob(".*.tmp")) == []


def test_save_rejects_invalid_store(workspace: Path) -> None:
    store = _store()
    store["next_seq"] = "one"
    with pytest.raises(CvtError) as exc:
        attestations.save_store(PERSON, store)
    assert exc.value.err_id == "E_SCHEMA"
    assert not (workspace / "profiles" / PERSON / "attestations.json").exists()


def test_save_rejects_other_persons_store(workspace: Path) -> None:
    with pytest.raises(CvtError) as exc:
        attestations.save_store("someone-else", _store())
    assert exc.value.err_id == "E_ATTEST_PERSON"


@pytest.mark.parametrize("path,ok", [
    (("proposed", "active"), True), (("proposed", "revoked"), True), (("active", "revoked"), True),
    (("active", "proposed"), False), (("proposed", "proposed"), False), (("revoked", "active"), False),
    (("revoked", "proposed"), False), (("active", "active"), False), (("proposed", "bogus"), False),
])
def test_transitions(path: tuple[str, str], ok: bool) -> None:
    store = _store()
    att = attestations.add(store, _proposal(), run_id=RUN_A, question_id="")
    att["status"] = path[0]
    if ok:
        assert attestations.set_status(store, att["id"], path[1])["status"] == path[1]
        return
    with pytest.raises(CvtError) as exc:
        attestations.set_status(store, att["id"], path[1])
    assert exc.value.err_id == "E_ATTEST_TRANSITION" and exc.value.code == ExitCode.CHECK_FAILED
    assert att["status"] == path[0]


def test_set_status_unknown_id() -> None:
    with pytest.raises(CvtError) as exc:
        attestations.set_status(_store(), "att-009", "active")
    assert exc.value.err_id == "E_ATTEST_UNKNOWN"


def test_usable_filtering() -> None:
    store = _store()
    for claim in ("active-a", "revoked-b", "proposed-a", "proposed-b", "unresolved-c"):
        run = RUN_B if claim == "proposed-b" else RUN_A
        sc = _scope("unresolved", desc="the relevant roles") if claim == "unresolved-c" else None
        attestations.add(store, _proposal(claim, sc=sc), run_id=run, question_id="")
    attestations.set_status(store, "att-001", "active")
    attestations.set_status(store, "att-002", "revoked")
    attestations.set_status(store, "att-005", "revoked")
    store["attestations"][4]["status"] = "active"  # unresolved scope must stay unusable even when active
    claims = lambda **kw: [a["claim"] for a in attestations.usable(store, run_id=RUN_A, **kw)]  # noqa: E731
    assert claims(include_proposed=False) == ["active-a"]
    assert claims(include_proposed=True) == ["active-a", "proposed-a"]
    assert [a["claim"] for a in attestations.usable(store, run_id=RUN_B, include_proposed=True)] == [
        "active-a", "proposed-b"]


def test_find_by_terms_is_active_only_and_case_insensitive() -> None:
    store = _store()
    attestations.add(store, _proposal("SLOs", ["SLO", "SLOs"]), run_id=RUN_A, question_id="")
    attestations.add(store, _proposal("Istio"), run_id=RUN_A, question_id="")
    assert attestations.find_by_terms(store, ["slo"]) == []
    attestations.set_status(store, "att-001", "active")
    attestations.set_status(store, "att-002", "active")
    attestations.set_status(store, "att-002", "revoked")
    assert [a["id"] for a in attestations.find_by_terms(store, ["slos", "kafka"])] == ["att-001"]
    assert attestations.find_by_terms(store, ["istio"]) == []


# --- scope -------------------------------------------------------------------------------------------------

def test_role_label_resolution_sre(profile: dict) -> None:
    resolved = scope.resolve(_scope("role_label", "SRE", desc="the sre related cv items"), profile)
    assert resolved["item_ids"] == SRE_IDS and resolved["role_label"] == "SRE"
    assert resolved["description"] == "the sre related cv items"


def test_role_label_is_case_insensitive_and_whole_word(profile: dict) -> None:
    assert scope.resolve(_scope("role_label", "sre"), profile)["item_ids"] == SRE_IDS
    profile["work"][2]["engagements"][1]["role_label"] = "PreSRE Analyst"
    profile["work"][2]["engagements"][2]["role_label"] = "Lead SRE / Platform"
    ids = scope.resolve(_scope("role_label", "SRE"), profile)["item_ids"]
    assert ids == [*SRE_IDS, "exp-3.e3"]  # PreSRE excluded, "Lead SRE / Platform" included, document order


def test_role_label_matches_work_position(profile: dict) -> None:
    profile["work"][0]["position"] = "Staff SRE"
    assert scope.resolve(_scope("role_label", "SRE"), profile)["item_ids"] == ["exp-1", *SRE_IDS]


def test_role_label_empty_raises(profile: dict) -> None:
    with pytest.raises(CvtError) as exc:
        scope.resolve(_scope("role_label", ""), profile)
    assert exc.value.err_id == "E_SCOPE_EMPTY_LABEL"


def test_items_scope_validates_and_sorts(profile: dict) -> None:
    resolved = scope.resolve(_scope("items", item_ids=["exp-3.e1", "exp-1", "exp-3.e1"]), profile)
    assert resolved["item_ids"] == ["exp-1", "exp-3.e1"]


def test_unknown_ids_raise(profile: dict) -> None:
    with pytest.raises(CvtError) as exc:
        scope.resolve(_scope("items", item_ids=["exp-2.e4", "exp-9.e1"]), profile)
    assert exc.value.err_id == "E_SCOPE_UNKNOWN_ID" and "exp-9.e1" in exc.value.message
    assert exc.value.code == ExitCode.CHECK_FAILED


def test_global_and_unresolved_have_no_item_ids(profile: dict) -> None:
    for kind in ("global", "unresolved"):
        resolved = scope.resolve(_scope(kind, item_ids=["exp-1"], desc="the relevant roles"), profile)
        assert resolved["item_ids"] == [] and resolved["kind"] == kind
        assert scope.describe_mapping(_scope(kind), profile) == []


def test_resolve_returns_new_object(profile: dict) -> None:
    original = _scope("role_label", "SRE")
    before = copy.deepcopy(original)
    scope.resolve(original, profile)
    assert original == before


def test_unknown_kind_raises(profile: dict) -> None:
    with pytest.raises(CvtError) as exc:
        scope.resolve(_scope("everything"), profile)
    assert exc.value.err_id == "E_SCOPE_KIND"


def test_describe_mapping_labels(profile: dict) -> None:
    mapping = scope.describe_mapping(_scope("role_label", "SRE"), profile)
    assert mapping == [
        {"item_id": "exp-2.e4", "label": "Harborline Bank — SRE (Fernbrook Consulting)"},
        {"item_id": "exp-2.e5", "label": "Pinecrest Outfitters — SRE (Fernbrook Consulting)"},
    ]


def test_candidates_bank_roles_returns_bank_first(profile: dict) -> None:
    found = scope.candidates("the bank roles", profile)
    assert found and found[0]["item_id"] == BANK_ID
    assert "Harborline Bank" in found[0]["label"]


def test_candidates_rank_role_label_before_name_before_keywords(profile: dict) -> None:
    ranked = [c["item_id"] for c in scope.candidates("sre incident runbooks storefront", profile)]
    assert ranked[:2] == ["exp-2.e5", "exp-2.e4"]  # e5: role + keywords; e4: role only
    by_name = [c["item_id"] for c in scope.candidates("telecom", profile)]
    assert by_name[0] == "exp-2.e2"


def test_candidates_limit_and_empty(profile: dict) -> None:
    assert len(scope.candidates("consulting", profile, limit=2)) == 2
    assert scope.candidates("zzzz", profile) == []
    assert scope.candidates("the roles", profile) == []  # only stopwords


def test_candidates_profile_only_lists_everything(profile: dict) -> None:
    listing = scope.candidates(profile)
    assert [i["item_id"] for i in listing][:3] == ["exp-1", "exp-2", "exp-2.e1"]
    assert len(listing) == 3 + 10
    assert listing == scope.all_items(profile)


# --- CLI ---------------------------------------------------------------------------------------------------

def _seed(workspace: Path) -> None:
    store = attestations.load_store(PERSON)
    attestations.add(store, _proposal("Istio"), run_id=RUN_A, question_id="q-1")
    sre = _proposal("SLOs", ["SLO", "SLOs"], _scope("role_label", "SRE", SRE_IDS, "the sre related cv items"))
    sre.update(type="practice", placement="bullets")
    attestations.add(store, sre, run_id=RUN_A, question_id="")
    attestations.set_status(store, "att-002", "active")
    attestations.save_store(PERSON, store)


def test_cli_list_show_revoke(workspace: Path, run_cvt) -> None:
    _seed(workspace)
    listing = run_cvt("attest", "list", "--person", PERSON)
    assert listing.returncode == 0, listing.stderr
    assert "att-001" in listing.stdout and "role_label=SRE (2)" in listing.stdout

    env = json.loads(run_cvt("attest", "list", "--person", PERSON, "--json").stdout)
    assert env["ok"] and env["data"]["count"] == 2

    shown = run_cvt("attest", "show", "att-002", "--person", PERSON, "--json")
    att = json.loads(shown.stdout)["data"]["attestation"]
    assert att["claim"] == "SLOs" and att["scope"]["item_ids"] == SRE_IDS

    revoked = run_cvt("attest", "revoke", "att-002", "--person", PERSON, "--json")
    assert revoked.returncode == 0, revoked.stderr
    assert json.loads(revoked.stdout)["data"] == {
        "person_slug": PERSON, "id": "att-002", "from": "active", "to": "revoked"}
    assert attestations.load_store(PERSON)["attestations"][1]["status"] == "revoked"

    again = run_cvt("attest", "revoke", "att-002", "--person", PERSON)
    assert again.returncode == int(ExitCode.CHECK_FAILED)
    assert "cvt: error[E_ATTEST_TRANSITION]" in again.stderr and "hint:" in again.stderr


def test_cli_activate_and_unresolved_guard(workspace: Path, run_cvt) -> None:
    store = attestations.load_store(PERSON)
    attestations.add(store, _proposal("Kafka"), run_id=RUN_A, question_id="")
    attestations.add(store, _proposal("Go", sc=_scope("unresolved", desc="relevant roles")),
                     run_id=RUN_A, question_id="")
    attestations.save_store(PERSON, store)
    ok = run_cvt("attest", "activate", "att-001", "--person", PERSON)
    assert ok.returncode == 0 and "proposed -> active" in ok.stdout
    blocked = run_cvt("attest", "activate", "att-002", "--person", PERSON, "--json")
    assert blocked.returncode == int(ExitCode.CHECK_FAILED)
    assert json.loads(blocked.stdout)["error"]["id"] == "E_ATTEST_SCOPE_UNRESOLVED"


def test_cli_unknown_id_and_empty_store(workspace: Path, run_cvt) -> None:
    empty = run_cvt("attest", "list", "--person", PERSON)
    assert empty.returncode == 0 and "none yet" in empty.stdout
    missing = run_cvt("attest", "show", "att-001", "--person", PERSON)
    assert missing.returncode == int(ExitCode.INPUT) and "E_ATTEST_UNKNOWN" in missing.stderr


def test_cli_addresses_store_by_run(workspace: Path, run_cvt) -> None:
    _seed(workspace)
    cv = workspace / "cv.txt"
    cv.write_text("Sam Testperson\n", encoding="utf-8")
    run_dir = state.create_run(cv, "text", "", "# Role\n", {})
    st = state.load(run_dir)
    assert st["person_slug"] == ""
    no_person = run_cvt("attest", "list", run_dir.name)
    assert no_person.returncode == int(ExitCode.STATE) and "E_PERSON_UNKNOWN" in no_person.stderr
    st["person_slug"] = PERSON
    state.save(run_dir, st)
    listing = run_cvt("attest", "list", run_dir.name, "--json")
    assert listing.returncode == 0, listing.stderr
    assert json.loads(listing.stdout)["data"]["count"] == 2
    latest = json.loads(run_cvt("attest", "list", "--json").stdout)  # no RUN: latest run
    assert latest["data"]["person_slug"] == PERSON and latest["run"] == run_dir.name
