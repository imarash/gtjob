"""`cvt jd-check`, `cvt match-check`, `cvt check-tailored`: gate the AI-written jd, match and tailored artifacts."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from .. import attestations, checks, jsonio, output, paths, provenance, schemas, state
from ..errors import CvtError, ExitCode

CHECK_FAILED_ID = "E_CHECK_FAILED"
JD_FILE, JD_TXT_FILE, MATCH_FILE = "jd.json", "jd.txt", "match.json"
TAILORED_FILE, VALIDATION_FILE, PROFILE_FILE = "tailored.json", "validation.json", "profile.json"
HISTORY_DIR = "tailored.history"
ATTESTATIONS_FILE = "attestations.json"
STAGE_AFTER_PROFILE, STAGE_JD, STAGE_MATCHED = "profiled", "jd_analyzed", "matched"
STAGE_ANSWERS, STAGE_TAILORED, STAGE_APPROVED = "answers_applied", "tailored", "approved"
SNAPSHOT_RE = re.compile(r"^v(\d+)\.json$")
SKIPPED_DETAIL = "post-render"
FIX_HINT = "run `cvt brief fix {run}`, patch only the listed items, then rerun: cvt {command} {run}"
PRE_RENDER_GATES = ("schema", "provenance", "placeholders", "logistics_leak", "attestation_status")
POST_RENDER_GATES = ("page_count", "typography_floor", "ats_roundtrip", "keyword_coverage", "layout")
EMPTY_COVERAGE = {"must_keywords_total": 0, "must_keywords_found": 0, "missing": [], "by_requirement": []}
SCHEMA_VERSION = "1"
MAX_HUMAN_VIOLATIONS = 8


# --- shared helpers -----------------------------------------------------------------------------------------
def _fail(run_dir: Path, st: dict, command: str, err: CvtError) -> None:
    st["status"] = "failed"
    state.add_error(st, err.err_id, err.message)
    state.add_history(st, command, f"failed: {err.err_id}")
    state.save(run_dir, st)
    raise err


def _check_failed(run: str, command: str, what: str, violations: list[dict]) -> CvtError:
    return CvtError(
        ExitCode.CHECK_FAILED, CHECK_FAILED_ID, f"{what} has {len(violations)} violations",
        hint=FIX_HINT.format(run=run, command=command), violations=violations,
    )


def _missing(run_dir: Path, name: str, st: dict) -> CvtError:
    return CvtError(ExitCode.STATE, "E_ARTIFACT_MISSING", f"{name} not found in {run_dir.name}",
                    hint=st["next_action"])


def _load_artifact(run_dir: Path, name: str, st: dict) -> dict:
    path = run_dir / name
    if not path.is_file():
        raise _missing(run_dir, name, st)
    return jsonio.load_json(path)


def _store_attestations(person_slug: str) -> list[dict]:
    """The person's attestations (empty when the store does not exist yet). Read-only."""
    path = paths.profiles_dir() / person_slug / ATTESTATIONS_FILE
    if not path.is_file():
        return []
    store = jsonio.load_json(path)
    schemas.require_valid(store, "attestations", str(path))
    return store["attestations"]


def _write_artifact(run_dir: Path, st: dict, art: str, filename: str, obj: dict) -> bool:
    """Write `obj` and record it; cascades staleness only when the bytes changed. Returns changed."""
    sha = jsonio.dump_json(obj, run_dir / filename)
    entry = state.artifact(st, art)
    changed = entry is None or entry["sha256"] != sha
    if changed or entry["stale"]:
        state.record_artifact(run_dir, st, art, filename, cascade=changed)
    return changed


def _advance(st: dict, stage: str, changed: bool) -> None:
    if changed or state.stage_index(st["stage"]) < state.stage_index(stage):
        state.set_stage(st, stage)
    else:
        st["status"] = "ok"


def _violation_lines(args: argparse.Namespace, violations: list[dict]) -> list[str]:
    shown, hidden = output.cap_list(args, violations)
    lines = [f"  {v['item_id']}: {v['message']}" for v in shown]
    return lines + ([f"  {output.MORE_LINE.format(n=hidden)}"] if hidden else [])


# --- jd-check -----------------------------------------------------------------------------------------------
def _jd_check(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    state.require_stage(st, STAGE_AFTER_PROFILE)
    command, run = "jd-check", run_dir.name
    try:
        jd = _load_artifact(run_dir, JD_FILE, st)
        jd_txt = _load_artifact_text(run_dir, JD_TXT_FILE, st)
        schemas.require_valid(jd, "jd", JD_FILE)
        violations = checks.check_jd(jd, jd_txt, st["inputs"]["jd"]["sha256"])
        if violations:
            raise _check_failed(run, command, JD_FILE, violations)
    except CvtError as err:
        _fail(run_dir, st, command, err)
    normalized = checks.normalize_jd(jd)
    changed = _write_artifact(run_dir, st, "jd", JD_FILE, normalized)
    _advance(st, STAGE_JD, changed)
    state.add_history(st, command, f"requirements={len(normalized['requirements'])}")
    state.save(run_dir, st)
    reqs = normalized["requirements"]
    data = {
        "requirements": len(reqs), "must": sum(r["kind"] == "must" for r in reqs),
        "keywords": len(normalized["keywords"]), "noise": len(normalized["noise"]), "jd_json": JD_FILE,
    }
    human = f"ok: jd.json valid ({data['requirements']} requirements, {data['must']} must, {data['keywords']} keywords)"
    return output.emit(args, run=run, stage=st["stage"], data=data, human=human, next_action=st["next_action"])


def _load_artifact_text(run_dir: Path, name: str, st: dict) -> str:
    path = run_dir / name
    if not path.is_file():
        raise _missing(run_dir, name, st)
    return path.read_text(encoding="utf-8")


# --- match-check --------------------------------------------------------------------------------------------
def _match_check(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    state.require_stage(st, STAGE_JD)
    command, run = "match-check", run_dir.name
    try:
        jd = jsonio.load_json(state.require_artifact(run_dir, st, "jd"))
        profile = jsonio.load_json(state.require_artifact(run_dir, st, "profile"))
        match = _load_artifact(run_dir, MATCH_FILE, st)
        schemas.require_valid(match, "match", MATCH_FILE)
        atts = attestations.usable(
            {"attestations": _store_attestations(profile["person_slug"])}, run_id=st["run_slug"], include_proposed=True)
        fixed, violations = checks.check_match(match, jd, profile, atts)
        if violations:
            raise _check_failed(run, command, MATCH_FILE, violations)
    except CvtError as err:
        _fail(run_dir, st, command, err)
    filled = sum(
        1 for a, b in zip(match["requirements"], fixed["requirements"])
        for ea, eb in zip(a["evidence"], b["evidence"]) if ea["quote"] != eb["quote"]
    )
    changed = _write_artifact(run_dir, st, "match", MATCH_FILE, fixed)
    _advance(st, STAGE_MATCHED, changed)
    state.add_history(st, command, f"quotes_filled={filled}")
    state.save(run_dir, st)
    cov = fixed["coverage"]
    data = {"coverage": cov, "quotes_filled": filled, "match_json": MATCH_FILE}
    human = (f"ok: match.json valid; must {cov['must_strong']}/{cov['must_total']} strong, "
             f"{cov['must_partial']} partial, {cov['must_none']} none; quotes filled: {filled}")
    return output.emit(args, run=run, stage=st["stage"], data=data, human=human, next_action=st["next_action"])


# --- check-tailored -----------------------------------------------------------------------------------------
def _snapshots(run_dir: Path) -> dict[int, Path]:
    found: dict[int, Path] = {}
    for path in (run_dir / HISTORY_DIR).glob("v*.json"):
        m = SNAPSHOT_RE.match(path.name)
        if m:
            found[int(m.group(1))] = path
    return found


def _content(t: dict) -> dict:
    return {k: v for k, v in t.items() if k != "version"}


def _version_and_snapshot(run_dir: Path, tailored: dict) -> tuple[dict, int, bool]:
    """Set `version`: unchanged content keeps the last snapshot's version, changed content gets the next one."""
    out = dict(tailored)
    snaps = _snapshots(run_dir)
    if not snaps:
        out["version"] = max(int(out["version"]), 1)
        wrote = True
    else:
        last_n = max(snaps)
        last = jsonio.load_json(snaps[last_n])
        wrote = _content(last) != _content(out)
        out["version"] = last_n + 1 if wrote else last_n
    if wrote:
        jsonio.dump_json(out, run_dir / HISTORY_DIR / f"v{out['version']}.json")
    return out, out["version"], wrote


def _gate(name: str, status: str, details: list[str] | None = None, violations: list[dict] | None = None) -> dict:
    return {"name": name, "status": status, "details": details or [], "violations": violations or []}


def _build_gates(
    t: dict, profile: dict, atts: list[dict], jd: dict, st: dict, draft: bool,
) -> list[dict]:
    run_id = st["run_slug"]
    prov = provenance.check_tailored(t, profile, atts, run_id=run_id, draft=True)
    holders = provenance.find_placeholders(t)
    leaks = provenance.check_logistics(t, jd)
    nonactive = provenance.check_attestation_status(t, atts, run_id=run_id)
    pre_approval = state.stage_index(st["stage"]) < state.stage_index(STAGE_APPROVED)
    soft = draft or pre_approval
    holder_status = "pass" if not holders else ("warn" if draft else "fail")
    att_status = "pass" if not nonactive else ("warn" if soft else "fail")
    att_details = [] if not nonactive else (
        ["proposed attestations become active at `cvt approve`"] if soft else ["approve first: cvt approve RUN"]
    )
    return [
        _gate("schema", "pass"),
        _gate("provenance", "fail" if prov else "pass", [f"{len(prov)} violations"] if prov else [], prov),
        _gate("placeholders", holder_status, [f"{len(holders)} placeholders"] if holders else [], holders),
        _gate("logistics_leak", "fail" if leaks else "pass", [f"{len(leaks)} violations"] if leaks else [], leaks),
        _gate("attestation_status", att_status, att_details, nonactive),
        *[_gate(name, "skipped", [SKIPPED_DETAIL]) for name in POST_RENDER_GATES],
    ]


def _validation(run_id: str, version: int, draft: bool, gates: list[dict]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "created_at": jsonio.now_iso(), "draft": draft,
        "tailored_version": version, "passed": all(g["status"] != "fail" for g in gates), "gates": gates,
        "coverage": dict(EMPTY_COVERAGE, missing=[], by_requirement=[]),
    }


def _write_validation(run_dir: Path, validation: dict) -> None:
    schemas.require_valid(validation, "validation", VALIDATION_FILE)
    jsonio.dump_json(validation, run_dir / VALIDATION_FILE)


def _check_tailored(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    state.require_stage(st, STAGE_ANSWERS)
    command, run, draft = "check-tailored", run_dir.name, bool(args.draft)
    try:
        raw = _load_artifact(run_dir, TAILORED_FILE, st)
        problems = schemas.to_violations(schemas.validate(raw, "tailored"))
        if problems:
            gates = [_gate("schema", "fail", [f"{len(problems)} violations"], problems),
                     *[_gate(n, "skipped", ["schema invalid"]) for n in PRE_RENDER_GATES[1:]],
                     *[_gate(n, "skipped", [SKIPPED_DETAIL]) for n in POST_RENDER_GATES]]
            _write_validation(run_dir, _validation(run, int(raw.get("version", 0) or 0), draft, gates))
            raise _check_failed(run, command, TAILORED_FILE, problems)
        jd = jsonio.load_json(state.require_artifact(run_dir, st, "jd"))
        profile = jsonio.load_json(state.require_artifact(run_dir, st, "profile"))
    except CvtError as err:
        _fail(run_dir, st, command, err)
    atts = _store_attestations(profile["person_slug"])
    renumbered, idmap = checks.renumber_tailored(raw)
    tailored, version, new_snapshot = _version_and_snapshot(run_dir, renumbered)
    changed = _write_artifact(run_dir, st, "tailored", TAILORED_FILE, tailored)
    gates = _build_gates(tailored, profile, atts, jd, st, draft)
    validation = _validation(run, version, draft, gates)
    _write_validation(run_dir, validation)
    failing = [v for g in gates if g["status"] == "fail" for v in g["violations"]]
    if failing:
        failing.sort(key=lambda v: (v["item_id"], v["message"]))
        _fail(run_dir, st, command, _check_failed(run, command, f"tailored.json v{version}", failing))
    if st["stage"] == STAGE_ANSWERS:
        state.set_stage(st, STAGE_TAILORED)
    else:
        st["status"] = "ok"
    state.add_history(st, command, f"v{version} changed={changed}")
    state.save(run_dir, st)
    warnings = [v for g in gates if g["status"] == "warn" for v in g["violations"]]
    shown, hidden = output.cap_list(args, warnings)
    data = {
        "version": version, "changed": changed, "new_snapshot": new_snapshot, "renumbered": len(idmap),
        "gates": {g["name"]: g["status"] for g in gates}, "warnings": shown, "validation": VALIDATION_FILE,
    }
    if hidden:
        data["warnings_more"] = hidden
    counts = {s: sum(g["status"] == s for g in gates) for s in ("pass", "warn", "skipped")}
    human = [f"ok: tailored.json v{version} passes ({counts['pass']} pass, {counts['warn']} warn, "
             f"{counts['skipped']} skipped post-render)"]
    if idmap:
        human.append(f"renumbered {len(idmap)} ids")
    human += _violation_lines(args, warnings)
    return output.emit(args, run=run, stage=st["stage"], data=data, human="\n".join(human),
                       next_action=st["next_action"])


def register(subparsers) -> None:
    p = subparsers.add_parser("jd-check", help="validate and normalize jd.json (stage jd_analyzed)")
    p.add_argument("run", metavar="RUN", help="run slug, run directory, or 'latest'")
    p.set_defaults(func=_jd_check)
    p = subparsers.add_parser("match-check", help="validate match.json and recompute coverage (stage matched)")
    p.add_argument("run", metavar="RUN", help="run slug, run directory, or 'latest'")
    p.set_defaults(func=_match_check)
    p = subparsers.add_parser("check-tailored", help="schema, provenance, placeholder and logistics checks")
    p.add_argument("run", metavar="RUN", help="run slug, run directory, or 'latest'")
    p.add_argument("--draft", action="store_true", help="placeholders and proposed attestations warn instead of fail")
    p.set_defaults(func=_check_tailored)
