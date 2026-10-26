"""`cvt diff`, `cvt apply-edits`, `cvt approve`: checkpoint 2 (interfaces.md sections 3, 6 and 7)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .. import attestations, diff, edits, jsonio, output, paths, provenance, schemas, state
from ..errors import CvtError, ExitCode

TAILORED_FILE = "tailored.json"
HISTORY_DIR = "tailored.history"
EDITS_DIR = "edits"
SNAPSHOT_RE = re.compile(r"^v(\d+)\.json$")
EDIT_FILE_RE = re.compile(r"^(\d+)\.json$")
EDIT_FILE_FORMAT = "{n:03d}.json"
STAGE_TAILORED, STAGE_AWAITING, STAGE_APPROVED = "tailored", "awaiting_approval", "approved"
CP_PENDING, CP_DONE, CP_SKIPPED = "pending", "done", "skipped"
STATUS_AWAITING_USER = "awaiting_user"
PENDING_APPROVAL_MESSAGE = "Checkpoint 2: show the compact diff, then approve or send changes."
RUN_OPTION_FIELDS = ("template", "page_target", "paper")
CHECK_FAILED_ID = "E_CHECK_FAILED"
FIX_HINT = ("fix the listed items in the edits file (cite profile IDs or att-NNN in source_refs), "
            "then rerun: cvt apply-edits {run} FILE")
APPROVE_ALL_OP = {"op": "approve_all", "target_id": "", "field": "", "value": "", "source_refs": [], "items": []}
FORMATS = ("md", "json")


# --- shared helpers -----------------------------------------------------------------------------------
def _fail(run_dir: Path, st: dict, command: str, err: CvtError) -> None:
    st["status"] = "failed"
    state.add_error(st, err.err_id, err.message)
    state.add_history(st, command, f"failed: {err.err_id}")
    state.save(run_dir, st)
    raise err


def _load_pair(run_dir: Path, st: dict) -> tuple[dict, dict]:
    tailored = jsonio.load_json(state.require_artifact(run_dir, st, "tailored"))
    profile = jsonio.load_json(state.require_artifact(run_dir, st, "profile"))
    return tailored, profile


def _snapshots(run_dir: Path) -> dict[int, Path]:
    found: dict[int, Path] = {}
    for path in (run_dir / HISTORY_DIR).glob("v*.json"):
        m = SNAPSHOT_RE.match(path.name)
        if m:
            found[int(m.group(1))] = path
    return found


def _previous_version(run_dir: Path, tailored: dict) -> dict:
    older = {n: p for n, p in _snapshots(run_dir).items() if n < int(tailored["version"])}
    if not older:
        raise CvtError(
            ExitCode.STATE, "E_NO_PREVIOUS", f"tailored.json v{tailored['version']} has no earlier version",
            hint="use --against profile (the default); versions appear after the first apply-edits",
        )
    return jsonio.load_json(older[max(older)])


def _write_tailored(run_dir: Path, st: dict, tailored: dict, *, cascade: bool) -> None:
    jsonio.dump_json(tailored, run_dir / TAILORED_FILE)
    state.record_artifact(run_dir, st, "tailored", TAILORED_FILE, cascade=cascade)


def _await_approval(st: dict) -> None:
    state.set_stage(st, STAGE_AWAITING, status=STATUS_AWAITING_USER,
                    pending={"kind": "approval", "question_ids": [], "message": PENDING_APPROVAL_MESSAGE})
    st["checkpoints"]["cp2"] = CP_PENDING


def _finalize_approval(st: dict, tailored: dict, profile: dict, *, auto: bool) -> tuple[list[str], list[str]]:
    """Activate this run's proposed attestations, record `attestations_used`, set cp2 and the `approved` stage.

    Returns (activated ids, ids left proposed because their scope is unresolved). A run already past `approved`
    keeps its stage.
    """
    activated: list[str] = []
    unresolved: list[str] = []
    if not auto:
        person = profile["person_slug"]
        store = attestations.load_store(person)
        for att in store["attestations"]:
            if att["status"] != attestations.STATUS_PROPOSED or att["run_id"] != st["run_slug"]:
                continue
            if att["scope"]["kind"] == attestations.UNRESOLVED_SCOPE:
                unresolved.append(att["id"])
            else:
                attestations.set_status(store, att["id"], attestations.STATUS_ACTIVE)
                activated.append(att["id"])
        if activated:
            attestations.save_store(person, store)
    st["attestations_used"] = edits.attestation_refs(tailored)
    st["checkpoints"]["cp2"] = CP_SKIPPED if auto else CP_DONE
    if state.stage_index(st["stage"]) < state.stage_index(STAGE_APPROVED):
        state.set_stage(st, STAGE_APPROVED)
    else:
        st["status"] = "ok"
    return activated, unresolved


def _uncapped(args: argparse.Namespace) -> argparse.Namespace:
    """The diff body is the deliverable: exempt from the 15-line human cap (the compact form is still short)."""
    return argparse.Namespace(**{**vars(args), "all": True})


# --- diff ---------------------------------------------------------------------------------------------
def _diff(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    state.require_stage(st, STAGE_TAILORED)
    tailored, profile = _load_pair(run_dir, st)
    previous = _previous_version(run_dir, tailored) if args.against == diff.AGAINST_PREVIOUS else None
    auto = bool(st["options"]["auto"])
    reviewing = state.stage_index(st["stage"]) <= state.stage_index(STAGE_AWAITING)
    marked = 0
    if reviewing and auto:
        marked = edits.mark_pending(tailored, edits.REVIEW_AUTO)
        edits.settle_containers(tailored)
        _write_tailored(run_dir, st, tailored, cascade=False)
        _finalize_approval(st, tailored, profile, auto=True)
    elif reviewing:
        _await_approval(st)
    if reviewing:
        state.add_history(st, "diff", f"v{tailored['version']} auto={auto} marked={marked}")
        state.save(run_dir, st)
    items = diff.diff_items(tailored, profile, previous)
    outline = diff.outline(tailored)
    full = bool(args.full)
    data = {
        "version": tailored["version"], "against": args.against, "full": full, "counts": diff.counts(items),
        "outline": outline.splitlines(), "items": diff.numbered(items, compact=not full),
        "pending": edits.pending_ids(tailored), "auto": auto,
    }
    if args.format == "json":
        human = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    else:
        human = diff.render_diff_md(items, outline, compact=not full)
        if auto and marked:
            human += f"\nauto mode: {marked} items marked review=auto; run is approved"
    return output.emit(_uncapped(args), run=run_dir.name, stage=st["stage"], data=data, human=human,
                       next_action=st["next_action"])


# --- apply-edits --------------------------------------------------------------------------------------
def _next_number(directory: Path) -> int:
    found = [int(m.group(1)) for p in directory.glob("*.json") if (m := EDIT_FILE_RE.match(p.name))]
    return max(found, default=0) + 1


def _batch_violations(new: dict, profile: dict, atts: list[dict], jd: dict, run_slug: str) -> list[dict]:
    problems = schemas.to_violations(schemas.validate(new, "tailored"))
    if problems:
        return problems
    found = provenance.check_tailored(new, profile, atts, run_id=run_slug, draft=True)
    found += provenance.check_logistics(new, jd)
    return sorted(found, key=lambda v: (v["item_id"], v["message"]))


def _run_options(ops: list[dict]) -> dict:
    out: dict = {}
    for op in ops:
        if op["op"] == "set_field" and op["field"] in RUN_OPTION_FIELDS:
            value = op["value"].strip()
            out[op["field"]] = int(value) if op["field"] == "page_target" else value
    return out


def _apply_edits(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    state.require_stage(st, STAGE_TAILORED)
    command, run = "apply-edits", run_dir.name
    source = Path(args.file)
    if not source.is_file():
        raise CvtError(ExitCode.INPUT, "E_EDITS_NOT_FOUND", f"edits file not found: {source}",
                       hint="write the edits JSON (edits.schema.json) to that path, then rerun")
    old, profile = _load_pair(run_dir, st)
    jd = jsonio.load_json(state.require_artifact(run_dir, st, "jd"))
    atts = attestations.load_store(profile["person_slug"])["attestations"]
    try:
        batch = jsonio.load_json(source)
        schemas.require_valid(batch, "edits", str(source))
        new = edits.apply_ops(old, batch["ops"], profile)
        violations = _batch_violations(new, profile, atts, jd, st["run_slug"])
        if violations:
            raise CvtError(
                ExitCode.CHECK_FAILED, CHECK_FAILED_ID,
                f"edits batch rejected: {len(violations)} violations; tailored.json is unchanged",
                hint=FIX_HINT.format(run=run), violations=violations,
            )
    except CvtError as err:
        _fail(run_dir, st, command, err)
    ops = batch["ops"]
    auto = bool(st["options"]["auto"])
    if auto:
        edits.mark_pending(new, edits.REVIEW_AUTO)
        edits.settle_containers(new)
    snaps = _snapshots(run_dir)
    if int(old["version"]) not in snaps:
        jsonio.dump_json(old, run_dir / HISTORY_DIR / f"v{old['version']}.json")
    new["version"] = max(int(old["version"]), max(snaps, default=0)) + 1
    jsonio.dump_json(new, run_dir / HISTORY_DIR / f"v{new['version']}.json")
    edits_rel = f"{EDITS_DIR}/{EDIT_FILE_FORMAT.format(n=_next_number(run_dir / EDITS_DIR))}"
    jsonio.dump_json(batch, run_dir / edits_rel)
    _write_tailored(run_dir, st, new, cascade=True)
    state.record_artifact(run_dir, st, "edits", edits_rel, cascade=False)
    st["options"].update(_run_options(ops))
    pending = edits.pending_ids(new)
    if auto or (any(op["op"] == "approve_all" for op in ops) and not pending):
        activated, _ = _finalize_approval(st, new, profile, auto=auto)
    else:
        activated = []
        _await_approval(st)
    state.add_history(st, command, f"{edits_rel} ops={len(ops)} v{new['version']}")
    state.save(run_dir, st)
    items = diff.diff_items(new, profile, old)
    head = f"applied {len(ops)} ops ({edits_rel}) -> tailored v{new['version']}; pending review: {len(pending)}"
    human = diff.render_diff_md(items, head, compact=True)
    data = {
        "version": new["version"], "ops": len(ops), "edits_file": edits_rel, "counts": diff.counts(items),
        "items": diff.numbered(items, compact=True), "pending": pending, "activated": activated,
    }
    return output.emit(_uncapped(args), run=run, stage=st["stage"], data=data, human=human,
                       next_action=st["next_action"])


# --- approve ------------------------------------------------------------------------------------------
def _approve(args: argparse.Namespace) -> int:
    run_dir = paths.resolve_run(args.run)
    st = state.load(run_dir)
    state.require_stage(st, STAGE_TAILORED)
    command, run = "approve", run_dir.name
    tailored, profile = _load_pair(run_dir, st)
    pending = edits.pending_ids(tailored)
    if pending and not args.all:
        if st["stage"] == STAGE_TAILORED:
            _await_approval(st)
            state.save(run_dir, st)
        raise CvtError(
            ExitCode.AWAITING_USER, "E_PENDING_ITEMS", f"{len(pending)} items are still pending review",
            hint=f"approve them via an approve op in apply-edits, or run: cvt approve {run} --all",
            violations=[{"code": "pending_review", "item_id": i, "message": "review: pending"} for i in pending],
        )
    final = edits.apply_ops(tailored, [APPROVE_ALL_OP] if args.all else [], profile)
    if final != tailored:
        _write_tailored(run_dir, st, final, cascade=False)
    activated, unresolved = _finalize_approval(st, final, profile, auto=False)
    state.add_history(st, command, f"approved={len(pending)} activated={','.join(activated)}")
    state.save(run_dir, st)
    data = {
        "approved_now": len(pending), "activated": activated, "unresolved": unresolved,
        "attestations_used": st["attestations_used"],
    }
    lines = [f"approved tailored.json v{final['version']} ({len(pending)} pending items approved with --all)"
             if pending else f"approved tailored.json v{final['version']}"]
    if activated:
        lines.append(f"attestations now active: {', '.join(activated)}")
    if unresolved:
        lines.append(f"left proposed (scope unresolved): {', '.join(unresolved)}")
    return output.emit(args, run=run, stage=st["stage"], data=data, human="\n".join(lines),
                       next_action=st["next_action"])


def register(subparsers) -> None:
    p = subparsers.add_parser("diff", help="checkpoint 2: outline plus changed items (compact) or all items (--full)")
    p.add_argument("run", metavar="RUN", help="run slug, run directory, or 'latest'")
    p.add_argument("--against", choices=(diff.AGAINST_PROFILE, diff.AGAINST_PREVIOUS), default=diff.AGAINST_PROFILE,
                   help="compare with the profile text (default) or the previous tailored version")
    p.add_argument("--format", choices=FORMATS, default="md", help="body format of the human output")
    p.add_argument("--full", action="store_true", help="list every item with full before/after text")
    p.set_defaults(func=_diff)
    p = subparsers.add_parser("apply-edits", help="apply a checkpoint-2 edits file atomically")
    p.add_argument("run", metavar="RUN", help="run slug, run directory, or 'latest'")
    p.add_argument("file", metavar="FILE", help="edits JSON (edits.schema.json)")
    p.set_defaults(func=_apply_edits)
    p = subparsers.add_parser("approve", help="approve the tailored CV and activate this run's attestations")
    p.add_argument("run", metavar="RUN", help="run slug, run directory, or 'latest'")
    p.add_argument("--all", action="store_true", help="approve every pending item first")
    p.set_defaults(func=_approve)
