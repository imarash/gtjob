"""Profile commands: profile-build, profile-verify, profile-cache, profile-show, export-jsonresume."""

from __future__ import annotations

import argparse
import datetime
from pathlib import Path

from .. import jsonio, output, paths, profile as prof, profile_map, profile_store, schemas, state
from ..errors import CvtError, ExitCode

PROFILE_FILE = "profile.json"
PROFILE_MAP_FILE = "profile-map.json"
JSONRESUME_FILE = "jsonresume.json"
STAGE_PROFILED = "profiled"
STAGE_INGESTED = "ingested"
ENGAGEMENT_SEPARATOR = " \u2014 "  # "Client — Employer"
EXCERPT_CHARS = 60
OUTLINE_MAX_ISSUES = 3  # issue lines shown in the compact outline before `--all`
OUTLINE_MAX_ATTESTATIONS = 3
PRESENT = "present"


def _today() -> datetime.date:
    return datetime.date.today()


def _fail_state(run_dir: Path, st: dict, command: str, err: CvtError) -> CvtError:
    """Record a failed command in state.json (stage unchanged) and return the error to raise."""
    state.add_history(st, command, f"failed: {err.err_id}")
    state.add_error(st, err.err_id, err.message)
    st["status"] = "failed"
    state.save(run_dir, st)
    return err


def _check_failed(message: str, violations: list[dict], hint: str) -> CvtError:
    return CvtError(ExitCode.CHECK_FAILED, "E_CHECK_FAILED", message, hint=hint, violations=violations)


def _load_cv_text(run_dir: Path, st: dict) -> str:
    path = state.require_artifact(run_dir, st, "cv_txt")
    return path.read_text(encoding="utf-8")


def _require_file(run_dir: Path, name: str, hint: str) -> Path:
    path = run_dir / name
    if not path.is_file():
        raise CvtError(ExitCode.STATE, "E_ARTIFACT_MISSING", f"{name} not found in {run_dir.name}", hint=hint)
    return path


def _counts(profile: dict) -> dict:
    issues = profile["source_issues"]
    return {
        "work": len(profile["work"]), "engagements": sum(len(w["engagements"]) for w in profile["work"]),
        "education": len(profile["education"]), "certificates": len(profile["certificates"]),
        "skills": len(profile["skills"]), "issues": len(issues),
        "issues_script": sum(1 for i in issues if i["origin"] == prof.ORIGIN_SCRIPT),
    }


def _commit_profile(run_dir: Path, st: dict, profile: dict, command: str, extra_artifacts: tuple[str, ...]) -> None:
    jsonio.dump_json(profile, run_dir / PROFILE_FILE)
    for name, rel in (("profile_map", PROFILE_MAP_FILE),):
        if name in extra_artifacts:
            state.record_artifact(run_dir, st, name, rel)
    state.record_artifact(run_dir, st, "profile", PROFILE_FILE)
    st["person_slug"] = profile["person_slug"]
    state.set_stage(st, STAGE_PROFILED)
    state.add_history(st, command)
    state.save(run_dir, st)


def _summary_line(profile: dict, counts: dict) -> str:
    return (f"{counts['work']} work ({counts['engagements']} engagements), {counts['education']} education, "
            f"{counts['certificates']} certificates, {counts['skills']} skill groups; "
            f"{counts['issues']} source issues ({counts['issues_script']} by script)")


def _finish(args: argparse.Namespace, run_dir: Path, st: dict, profile: dict, command: str,
            extra_artifacts: tuple[str, ...], verb: str) -> int:
    _commit_profile(run_dir, st, profile, command, extra_artifacts)
    counts = _counts(profile)
    return output.emit(
        args, run=run_dir.name, stage=st["stage"],
        data={"person_slug": profile["person_slug"], "path": PROFILE_FILE, **counts},
        human=f"ok: {verb} {PROFILE_FILE}: {_summary_line(profile, counts)}", next_action=st["next_action"])


# --- profile-build ----------------------------------------------------------------------------------------
def _build(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    state.require_stage(st, STAGE_INGESTED)
    cv_text = _load_cv_text(run_dir, st)
    map_path = _require_file(
        run_dir, PROFILE_MAP_FILE,
        f"write {PROFILE_MAP_FILE} following `cvt brief profile {run_dir.name}`, then rerun profile-build")
    try:
        pmap = jsonio.load_json(map_path)
        schemas.require_valid(pmap, "profile-map", PROFILE_MAP_FILE)
        slug = paths.slugify(pmap["basics"]["name"])
        if not slug:
            raise _check_failed(
                "basics.name is empty, so no person slug can be derived",
                [{"code": prof.VIOLATION_FACT_MISMATCH, "item_id": "basics", "message": "basics.name is empty"}],
                "set basics.name to the name as written on the CV")
        profile, violations = profile_map.build_profile(
            pmap, cv_text, person_slug=slug, cv_sha256=st["inputs"]["cv"]["sha256"])
        if violations:
            raise _check_failed(
                f"{PROFILE_MAP_FILE} has {len(violations)} problems", violations,
                f"patch only the listed lines/items in {PROFILE_MAP_FILE}, then rerun: cvt profile-build {run_dir.name}")
        violations = prof.verify_verbatim(profile, cv_text)
        if violations:
            raise _check_failed(f"{len(violations)} texts are not verbatim from cv.txt", violations,
                                f"fix the cited ranges in {PROFILE_MAP_FILE}, then rerun")
        prof.apply_script_issues(profile, cv_text, _today())
        schemas.require_valid(profile, "profile", PROFILE_FILE)
    except CvtError as err:
        if err.code != ExitCode.CHECK_FAILED:
            raise
        raise _fail_state(run_dir, st, args.command, err) from None
    return _finish(args, run_dir, st, profile, args.command, ("profile_map",), "built")


# --- profile-verify ---------------------------------------------------------------------------------------
def _verify(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    state.require_stage(st, STAGE_INGESTED)
    cv_text = _load_cv_text(run_dir, st)
    path = _require_file(
        run_dir, PROFILE_FILE,
        f"write {PROFILE_FILE} (or build it with `cvt profile-build {run_dir.name}`), then rerun profile-verify")
    try:
        profile = jsonio.load_json(path)
        schemas.require_valid(profile, "profile", PROFILE_FILE)
        prof.normalize_ids(profile)
        violations = prof.verify_verbatim(profile, cv_text)
        prof.apply_script_issues(profile, cv_text, _today())
        schemas.require_valid(profile, "profile", PROFILE_FILE)
        if violations:
            jsonio.dump_json(profile, path)  # keep the canonical IDs the violations refer to
            raise _check_failed(f"{len(violations)} texts are not verbatim from cv.txt", violations,
                                f"patch only the listed items in {PROFILE_FILE}, then rerun: "
                                f"cvt profile-verify {run_dir.name}")
    except CvtError as err:
        if err.code != ExitCode.CHECK_FAILED:
            raise
        raise _fail_state(run_dir, st, args.command, err) from None
    return _finish(args, run_dir, st, profile, args.command, (), "verified")


# --- profile-cache ----------------------------------------------------------------------------------------
def _cache(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    state.require_stage(st, STAGE_INGESTED)
    cv_sha = st["inputs"]["cv"]["sha256"]
    if args.store:
        dest = profile_store.store(run_dir)
        rel = str(dest.relative_to(paths.workspace_root())) if dest.is_relative_to(paths.workspace_root()) else str(dest)
        return output.emit(args, run=run_dir.name, stage=st["stage"], data={"stored": True, "path": rel},
                           human=f"ok: stored profile at {rel}", next_action=st["next_action"])
    cached = profile_store.lookup(cv_sha)
    if cached is None:
        return output.emit(
            args, run=run_dir.name, stage=st["stage"], data={"hit": False},
            human=f"miss: no stored profile for this CV (sha {cv_sha[:profile_store.SHA_SHORT]})",
            next_action=st["next_action"])
    profile = jsonio.load_json(cached)
    schemas.require_valid(profile, "profile", cached.name)
    jsonio.dump_json(profile, run_dir / PROFILE_FILE)
    state.record_artifact(run_dir, st, "profile", PROFILE_FILE)
    st["person_slug"] = profile["person_slug"]
    state.set_stage(st, STAGE_PROFILED)
    state.add_history(st, args.command, f"hit {cached.name}")
    state.save(run_dir, st)
    counts = _counts(profile)
    return output.emit(
        args, run=run_dir.name, stage=st["stage"],
        data={"hit": True, "person_slug": profile["person_slug"], "path": PROFILE_FILE, **counts},
        human=f"hit: reused stored profile of {profile['person_slug']}: {_summary_line(profile, counts)}",
        next_action=st["next_action"])


# --- profile-show -----------------------------------------------------------------------------------------
def _resolve_profile(args: argparse.Namespace) -> tuple[dict, str, str]:
    """(profile, run name, source label) for `RUN` or `--person`."""
    if args.person:
        path = profile_store.latest_for_person(args.person)
        if path is None:
            raise CvtError(ExitCode.STATE, "E_PROFILE_NOT_FOUND", f"no stored profile for person '{args.person}'",
                           hint="run a CV through `cvt profile-cache RUN --store` first")
        return jsonio.load_json(path), "", path.name
    run_dir = paths.resolve_run(args.run)
    path = _require_file(run_dir, PROFILE_FILE, f"run `cvt profile-build {run_dir.name}` first")
    return jsonio.load_json(path), run_dir.name, PROFILE_FILE


def _scope_text(scope: dict) -> str:
    detail = scope["role_label"] if scope["kind"] == "role_label" else ",".join(scope["item_ids"])
    return f"{scope['kind']}:{detail}" if detail else scope["kind"]


def _outline(profile: dict, attestations: list[dict], full: bool) -> list[str]:
    b = profile["basics"]
    counts = _counts(profile)
    lines = [f"{b['name']} ({profile['person_slug']}): {_summary_line(profile, counts)}"]
    for w in profile["work"]:
        lines.append(f"{w['id']} {w['name']} | {w['position']} | {w['start_date']}..{w['end_date']} | "
                     f"{w['employment_type']} | {len(w['highlights'])} bullets")
        if full:
            lines += [f"  {h['id']} [{h['kind']}] {h['text'][:EXCERPT_CHARS]}" for h in w["highlights"]]
        for e in w["engagements"]:
            lines.append(f" {e['id']} [{e['kind']}] {e['name']} | role: {e['role_label']} | "
                         f"{len(e['highlights'])} bullets")
            if full:
                lines += [f"  {h['id']} [{h['kind']}] {h['text'][:EXCERPT_CHARS]}" for h in e["highlights"]]
    lines += [f"{ed['id']} {ed['study_type']} {ed['area']} | {ed['institution']} | {ed['end_date']}"
              for ed in profile["education"]]
    lines += [f"{c['id']} {c['name']}" for c in profile["certificates"]]
    lines += [f"{g['id']} {g['name']}: {len(g['keywords'])} keywords" for g in profile["skills"]]
    issues = profile["source_issues"] if full else profile["source_issues"][:OUTLINE_MAX_ISSUES]
    lines += [f"{i['id']} [{i['severity']}] {i['message']}" for i in issues]
    shown = attestations if full else attestations[:OUTLINE_MAX_ATTESTATIONS]
    lines += [f"{a['id']} {a['type']} \"{a['claim']}\" [{a['status']}] scope={_scope_text(a['scope'])}"
              for a in shown]
    return lines


def _show(args: argparse.Namespace) -> int:
    profile, run_name, source = _resolve_profile(args)
    attestations = profile_store.load_attestations(profile["person_slug"])
    if args.merged:
        profile = prof.merged_view(profile, attestations)
    full = bool(getattr(args, "all", False))
    lines = _outline(profile, attestations, full)
    counts = _counts(profile)
    data = {
        "source": source, "merged": bool(args.merged), "person_slug": profile["person_slug"], **counts,
        "work_ids": [w["id"] for w in profile["work"]],
        "issues": [{"id": i["id"], "kind": i["kind"], "severity": i["severity"], "item_ids": i["item_ids"]}
                   for i in output.cap_list(args, profile["source_issues"])[0]],
        "attestations": [{"id": a["id"], "claim": a["claim"], "status": a["status"], "scope": a["scope"]["kind"]}
                         for a in output.cap_list(args, attestations)[0]],
        "attestation_count": len(attestations),
    }
    return output.emit(args, run=run_name, data=data, human="\n".join(lines))


# --- export-jsonresume ------------------------------------------------------------------------------------
def _json_dates(w: dict) -> dict:
    out = {"startDate": w["start_date"]}
    if w["end_date"] and w["end_date"] != PRESENT:
        out["endDate"] = w["end_date"]
    return out


def to_jsonresume(profile: dict) -> dict:
    """Map a profile to JSON Resume. Each engagement becomes its own `work` entry named 'Client — Employer'."""
    b = profile["basics"]
    work = []
    for w in profile["work"]:
        texts = [h["text"] for h in w["highlights"]]
        if texts or w["summary"] or not w["engagements"]:
            work.append({"name": w["name"], "position": w["position"], "location": w["location"],
                         **_json_dates(w), "summary": w["summary"], "highlights": texts})
        for e in w["engagements"]:
            work.append({
                "name": f"{e['name']}{ENGAGEMENT_SEPARATOR}{w['name']}",
                "position": e["role_label"] or w["position"], "location": w["location"], **_json_dates(w),
                "summary": e["summary"], "highlights": [h["text"] for h in e["highlights"]],
            })
    return {
        "basics": {
            "name": b["name"], "label": b["label"], "email": b["email"], "phone": b["phone"], "url": b["url"],
            "summary": " ".join(s["text"] for s in profile["summary"]),
            "location": {"city": b["location"]["city"], "region": b["location"]["region"],
                         "countryCode": b["location"]["country"]},
            "profiles": [{"network": p["network"], "url": p["url"]} for p in b["profiles"]],
        },
        "work": work,
        "education": [{"institution": e["institution"], "area": e["area"], "studyType": e["study_type"],
                       **({"endDate": e["end_date"]} if e["end_date"] and e["end_date"] != PRESENT else {})}
                      for e in profile["education"]],
        "certificates": [{"name": c["name"], "issuer": c["issuer"], "date": c["date"]}
                         for c in profile["certificates"]],
        "skills": [{"name": g["name"], "keywords": list(g["keywords"])} for g in profile["skills"]],
    }


def _export(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    profile = jsonio.load_json(_require_file(run_dir, PROFILE_FILE, f"run `cvt profile-build {run_dir.name}` first"))
    resume = to_jsonresume(profile)
    jsonio.dump_json(resume, run_dir / JSONRESUME_FILE)
    return output.emit(
        args, run=run_dir.name,
        data={"path": JSONRESUME_FILE, "work": len(resume["work"]), "education": len(resume["education"]),
              "certificates": len(resume["certificates"]), "skills": len(resume["skills"])},
        human=f"ok: wrote {JSONRESUME_FILE} ({len(resume['work'])} work entries)")


# --- registration -----------------------------------------------------------------------------------------
def register(subparsers) -> None:
    p = subparsers.add_parser("profile-build", help="build profile.json from profile-map.json and cv.txt")
    p.add_argument("run", metavar="RUN", help="run slug, run directory, or 'latest'")
    p.set_defaults(func=_build)

    p = subparsers.add_parser("profile-verify", help="renumber, verify verbatim text, add script source issues")
    p.add_argument("run", metavar="RUN")
    p.set_defaults(func=_verify)

    p = subparsers.add_parser("profile-cache", help="reuse (--lookup) or save (--store) a verified profile")
    p.add_argument("run", metavar="RUN")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--lookup", action="store_true", help="copy the stored profile for this CV hash, if any")
    mode.add_argument("--store", action="store_true", help="save this run's verified profile to profiles/")
    p.set_defaults(func=_cache)

    p = subparsers.add_parser("profile-show", help="compact outline of a profile and its attestations")
    p.add_argument("run", metavar="RUN", nargs="?", default=None, help="run slug, directory, or 'latest'")
    p.add_argument("--person", default="", help="show the stored profile of this person slug instead")
    p.add_argument("--merged", action="store_true", help="apply active correction attestations")
    p.set_defaults(func=_show)

    p = subparsers.add_parser("export-jsonresume", help="write jsonresume.json from profile.json")
    p.add_argument("run", metavar="RUN")
    p.set_defaults(func=_export)
