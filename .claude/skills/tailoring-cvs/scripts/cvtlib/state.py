"""Run state: creation, persistence, staleness, and the next-action table (interfaces.md section 6)."""

from __future__ import annotations

import importlib
import os
import shutil
import uuid
from pathlib import Path

from . import jsonio, paths, schemas
from .errors import CvtError, ExitCode

STATE_FILE = paths.STATE_FILE
CVT_COMMAND = "uv run .claude/skills/tailoring-cvs/scripts/cvt.py"
HOSTS = ("cursor", "claude_code", "cli", "api", "unknown")
HOST_ENV = "GTJOB_HOST"
UNKNOWN_HOST = "unknown"
CV_FORMATS = ("pdf", "txt", "md", "docx")
JD_KINDS = ("file", "text", "url")
TITLE_WORDS = 6
SHA_SHORT = 6
URL_PLACEHOLDER = "<!-- jd-url: {url} -->\n"
COMMENT_PREFIX = "<!--"
PENDING_NONE: dict = {"kind": "none", "question_ids": [], "message": ""}
DEFAULT_OPTIONS: dict = {
    "template": "modern", "auto": False, "draft": False, "page_target": 2, "paper": "us-letter",
}
CHECK_FAILED_ERROR_CODES = ("E_SCHEMA", "E_CHECK_FAILED")
DEFAULT_RERUN_COMMAND = "status"

STAGES: tuple[str, ...] = (
    "initialized", "ingested", "profiled", "jd_analyzed", "matched", "awaiting_answers",
    "answers_applied", "tailored", "awaiting_approval", "approved", "rendered", "validated", "reported",
)

ARTIFACT_STAGE: dict[str, str] = {
    "cv_txt": "ingested", "jd_txt": "ingested",
    "profile_map": "profiled", "profile": "profiled",
    "jd": "jd_analyzed", "digest": "jd_analyzed",
    "match": "matched",
    "questions": "awaiting_answers",
    "answers": "answers_applied",
    "tailor_plan": "tailored", "tailored": "tailored", "edits": "tailored",
    "fit": "rendered", "render_model": "rendered", "typst_source": "rendered", "pdf": "rendered",
    "pages_png": "rendered", "markdown_fallback": "rendered",
    "validation": "validated", "final_pdf": "validated",
    "critique": "reported", "report": "reported",
}
USAGE_ARTIFACT = "usage"  # append-only telemetry: no stage, never stale

_NEXT_ACTIONS: dict[str, str] = {
    "initialized": "Run: {cvt} ingest {run}",
    "ingested": (
        "Run {cvt} profile-cache {run} --lookup; on a miss run {cvt} brief profile {run}, "
        "write out/{run}/profile-map.json, then {cvt} profile-build {run}"
    ),
    "profiled": (
        "Run {cvt} brief jd {run} (it may reuse a cached jd.json), "
        "write out/{run}/jd.json, then {cvt} jd-check {run}"
    ),
    "jd_analyzed": "Run {cvt} brief match {run}, write out/{run}/match.json, then {cvt} match-check {run}",
    "matched": (
        "Run {cvt} brief questions {run}, write out/{run}/questions.json, then {cvt} questions {run}"
    ),
    "awaiting_answers": (
        "Ask the pending questions ({cvt} questions {run} --format host). "
        "Choice answers: {cvt} answers-apply {run} --select q-N=CHOICE --default-rest --dry-run. "
        "Free text: {cvt} brief answer_parse {run} --reply-file F, write out/{run}/answers.round.json, "
        "then {cvt} answers-apply {run} --round out/{run}/answers.round.json --dry-run"
    ),
    "answers_applied": (
        "Run {cvt} brief tailor {run}, write out/{run}/tailor-plan.json, then {cvt} assemble {run}"
    ),
    "tailored": "Run {cvt} diff {run} and present checkpoint 2",
    "awaiting_approval": (
        "Present the compact diff. Free-text changes: {cvt} brief change_request {run} --reply-file F, "
        "write out/{run}/edits/next.json, then {cvt} apply-edits {run} out/{run}/edits/next.json. "
        "When approved: {cvt} approve {run}"
    ),
    "approved": "Run {cvt} fit {run}",
    "rendered": "Run {cvt} validate {run}",
    "validated": "Run {cvt} report {run}",
    "reported": (
        "Done. Deliverables: final/*.pdf, report.md. "
        "Send change requests any time; they re-enter at checkpoint 2."
    ),
}
_FAILED_ACTION = "Fix the reported problem, then rerun: {cvt} {command} {run}"
_CHECK_FAILED_ACTION = (
    "Run {cvt} brief fix {run}, patch the listed items, then rerun: {cvt} {command} {run}"
)


def stage_index(stage: str) -> int:
    try:
        return STAGES.index(stage)
    except ValueError:
        raise CvtError(
            ExitCode.INTERNAL, "E_STAGE_UNKNOWN", f"unknown stage '{stage}'",
            hint=f"valid stages: {', '.join(STAGES)}",
        ) from None


def current_host() -> str:
    env = os.environ.get(HOST_ENV, "")
    if env in HOSTS:
        return env
    try:
        detected = importlib.import_module("cvtlib.hostdetect").detect()
    except ImportError:
        return UNKNOWN_HOST
    return detected if detected in HOSTS else UNKNOWN_HOST


def next_action_for(st: dict, run_slug: str) -> str:
    if st["status"] == "failed":
        last = st["errors"][-1]["code"] if st["errors"] else ""
        template = _CHECK_FAILED_ACTION if last in CHECK_FAILED_ERROR_CODES else _FAILED_ACTION
        command = st["history"][-1]["event"] if st["history"] else DEFAULT_RERUN_COMMAND
    else:
        template = _NEXT_ACTIONS[st["stage"]]
        command = ""
    return template.replace("{cvt}", CVT_COMMAND).replace("{run}", run_slug).replace("{command}", command)


def load(run_dir: Path) -> dict:
    st = jsonio.load_json(Path(run_dir) / STATE_FILE)
    problems = schemas.validate(st, "state")
    if problems:
        raise CvtError(
            ExitCode.INTERNAL, "E_STATE_INVALID", f"{run_dir / STATE_FILE} is invalid: {problems[0]}",
            hint="restore state.json from a backup, or start a new run with: cvt init",
        )
    return st


def save(run_dir: Path, st: dict) -> None:
    st["updated_at"] = jsonio.now_iso()
    problems = schemas.validate(st, "state")
    if not problems:
        st["next_action"] = next_action_for(st, st["run_slug"])
    if problems:
        raise CvtError(
            ExitCode.INTERNAL, "E_STATE_INVALID", f"refusing to write invalid state: {problems[0]}",
            hint="this is a bug in the calling command; report it with the failing command line",
        )
    jsonio.dump_json(st, Path(run_dir) / STATE_FILE)


def artifact(st: dict, name: str) -> dict | None:
    return next((a for a in st["artifacts"] if a["name"] == name), None)


def record_artifact(run_dir: Path, st: dict, name: str, rel_path: str, cascade: bool = True) -> None:
    if name == USAGE_ARTIFACT:
        stage = ""
    elif name in ARTIFACT_STAGE:
        stage = ARTIFACT_STAGE[name]
    else:
        raise CvtError(
            ExitCode.INTERNAL, "E_ARTIFACT_NAME", f"unknown artifact '{name}'",
            hint=f"valid names: {', '.join(sorted([*ARTIFACT_STAGE, USAGE_ARTIFACT]))}",
        )
    entry = {
        "name": name, "path": rel_path, "sha256": jsonio.sha256_file(Path(run_dir) / rel_path),
        "stage": stage, "updated_at": jsonio.now_iso(), "stale": False,
    }
    st["artifacts"] = [a for a in st["artifacts"] if a["name"] != name] + [entry]
    if cascade and stage:
        limit = stage_index(stage)
        for other in st["artifacts"]:
            if other["name"] != name and other["stage"] and stage_index(other["stage"]) > limit:
                other["stale"] = True


def require_artifact(run_dir: Path, st: dict, name: str, allow_stale: bool = False) -> Path:
    entry = artifact(st, name)
    hint = st["next_action"]
    if entry is None or not (Path(run_dir) / entry["path"]).is_file():
        raise CvtError(
            ExitCode.STATE, "E_ARTIFACT_MISSING",
            f"{name} not found in {Path(run_dir).name}" if entry is None
            else f"{entry['path']} is recorded but missing in {Path(run_dir).name}",
            hint=hint,
        )
    if entry["stale"] and not allow_stale:
        raise CvtError(
            ExitCode.STATE, "E_ARTIFACT_STALE",
            f"{name} is stale: an upstream artifact changed after it was written",
            hint=f"regenerate it (stage {entry['stage']}); next: {hint}",
        )
    return Path(run_dir) / entry["path"]


def set_stage(st: dict, stage: str, status: str = "ok", pending: dict | None = None) -> None:
    stage_index(stage)
    st["stage"] = stage
    st["status"] = status
    st["pending"] = dict(pending) if pending is not None else {**PENDING_NONE, "question_ids": []}


def require_stage(st: dict, minimum: str) -> None:
    if stage_index(st["stage"]) < stage_index(minimum):
        raise CvtError(
            ExitCode.STATE, "E_STAGE",
            f"run is at stage '{st['stage']}', this command needs '{minimum}' or later",
            hint=st["next_action"],
        )


def add_history(st: dict, event: str, detail: str = "") -> None:
    host = current_host()
    st["history"].append(
        {"at": jsonio.now_iso(), "event": event, "stage": st["stage"], "host": host, "detail": detail},
    )
    st["options"]["host"] = host


def add_error(st: dict, code: str, message: str) -> None:
    st["errors"].append({"at": jsonio.now_iso(), "code": code, "message": message})


def _stem_from_title(text: str) -> str:
    for line in text.splitlines():
        line = line.strip().lstrip("#").strip()
        if line and not line.startswith(COMMENT_PREFIX):
            return paths.slugify(" ".join(line.split()[:TITLE_WORDS]))
    return ""


def _choose_stem(slug: str | None, jd_kind: str, jd_ref: str, jd_bytes: bytes) -> str:
    if slug:
        stem = paths.slugify(slug)
        if not stem:
            raise CvtError(
                ExitCode.USAGE, "E_SLUG", f"--slug '{slug}' has no letters or digits",
                hint="use letters, digits and dashes, e.g. --slug staff-sre",
            )
        return stem
    stem = paths.slugify(Path(jd_ref).stem) if jd_kind == "file" else ""
    if not stem:
        stem = _stem_from_title(jd_bytes.decode("utf-8", errors="replace"))
    return stem or f"jd-{jsonio.sha256_bytes(jd_bytes)[:SHA_SHORT]}"


def create_run(
    cv_path: Path, jd_kind: str, jd_ref: str, jd_text: str | None, options: dict,
    slug: str | None = None,
) -> Path:
    cv_path = Path(cv_path)
    if not cv_path.is_file():
        raise CvtError(
            ExitCode.INPUT, "E_CV_NOT_FOUND", f"CV file not found: {cv_path}",
            hint="pass --cv with a path to a .pdf, .txt, .md or .docx file",
        )
    cv_format = cv_path.suffix.lower().lstrip(".")
    if cv_format not in CV_FORMATS:
        raise CvtError(
            ExitCode.INPUT, "E_CV_FORMAT", f"unsupported CV format '.{cv_format}'",
            hint=f"supported: {', '.join(CV_FORMATS)}; or paste the CV text into a .txt file",
        )
    if jd_kind not in JD_KINDS:
        raise CvtError(
            ExitCode.USAGE, "E_JD_KIND", f"unknown JD kind '{jd_kind}'",
            hint=f"use one of: {', '.join(JD_KINDS)}",
        )
    if jd_text is None and jd_kind == "file":
        try:
            jd_text = Path(jd_ref).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CvtError(
                ExitCode.INPUT, "E_JD_UNREADABLE", f"cannot read JD file {jd_ref}: {exc}",
                hint="pass --jd with a UTF-8 text or markdown file, or use --jd-text",
            ) from None
    if jd_text is None and jd_kind == "url":
        jd_text = URL_PLACEHOLDER.format(url=jd_ref)
    if not (jd_text or "").strip():
        raise CvtError(
            ExitCode.INPUT, "E_JD_EMPTY", "the job description is empty",
            hint="pass a non-empty JD with --jd, --jd-text, --jd-stdin or --jd-url",
        )
    jd_bytes = jd_text.encode("utf-8")
    run_slug = paths.new_run_slug(_choose_stem(slug, jd_kind, jd_ref, jd_bytes))
    run_dir = paths.out_dir() / run_slug
    (run_dir / "inputs").mkdir(parents=True)

    cv_rel, jd_rel = f"inputs/cv.{cv_format}", "inputs/jd.md"
    shutil.copyfile(cv_path, run_dir / cv_rel)
    (run_dir / jd_rel).write_bytes(jd_bytes)
    now = jsonio.now_iso()
    st: dict = {
        "schema_version": "1",
        "run_id": str(uuid.uuid4()),
        "run_slug": run_slug,
        "person_slug": "",
        "created_at": now,
        "updated_at": now,
        "inputs": {
            "cv": {
                "original_path": str(cv_path.resolve()), "stored_path": cv_rel,
                "sha256": jsonio.sha256_file(run_dir / cv_rel), "format": cv_format,
            },
            "jd": {
                "kind": jd_kind, "original_ref": jd_ref, "stored_path": jd_rel,
                "sha256": jsonio.sha256_file(run_dir / jd_rel),
            },
        },
        "options": {**DEFAULT_OPTIONS, "host": current_host(), **options},
        "stage": "initialized",
        "status": "ok",
        "next_action": "",
        "pending": {**PENDING_NONE, "question_ids": []},
        "checkpoints": {"cp1": "not_started", "cp2": "not_started"},
        "artifacts": [],
        "ingest": {"method": "none", "pages": 0, "chars": 0, "scanned_suspect": False, "warnings": []},
        "attestations_used": [],
        "history": [],
        "errors": [],
    }
    add_history(st, "init", f"jd={jd_kind}")
    save(run_dir, st)
    return run_dir
