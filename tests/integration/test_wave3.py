"""WP-I3: the whole junior run through real commands, from `init` to `report`.

The AI-written stages are played by the junior golden artifacts (questions, answers round, tailor plan, edits). Every
other step is a real `cvt` subprocess in a temporary `GTJOB_HOME` workspace. Also covers the skill lint/package and the
doc-vs-CLI consistency checks.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from pypdf import PdfReader

from conftest import CVT_PY, HOME_ENV, HOST_ENV, REPO_ROOT, SKILL_DIR
from cvtlib import jsonio

FIXTURES = REPO_ROOT / "tests" / "fixtures"
GOLDEN = FIXTURES / "golden" / "junior"
CV_FIXTURE = FIXTURES / "cv" / "jamie-rivera-junior.txt"
JD_FIXTURE = FIXTURES / "jds" / "junior-devops-engineer.md"
BUDGETS = SKILL_DIR / "assets" / "budgets.json"
DOC_FILES = (SKILL_DIR / "SKILL.md", SKILL_DIR / "references" / "commands.md")

PERSON = "jamie-rivera"
EXIT_OK, EXIT_CHECK_FAILED, EXIT_AWAITING_USER = 0, 1, 6
EXPECTED_PAGES = 1
HELM_REPLY = "I used Helm at Brightfield to package two internal services"
CHANGE_REPLY = "Say 'cutting' in the monitoring bullet and approve the rest."
CLAUDE_MAX_QUESTIONS_PER_CALL = 4
CLAUDE_MAX_OPTIONS_PER_QUESTION = 4
EXTRA_GAP_CHOICES = 6  # more than one Claude Code question can hold
EXTRA_QUESTIONS = 4
CLAUDE_MAX_HEADER_CHARS = 12
MIN_DOC_EXAMPLES = 30  # guards against the regex silently matching nothing
FORBIDDEN_ZIP_ROOTS = ("out/", "profiles/", ".cache/", "CVs/")
COMMAND_LINE_RE = re.compile(r"^    ([a-z][a-z0-9-]*)\s{2,}\S")
DOC_COMMAND_RE = re.compile(r"(?:\$CVT|cvt\.py)\s+((?:[a-z][a-z-]*)(?:\s+[^`\n]*)?)")
DOC_FLAG_RE = re.compile(r"(?<![\w-])(--[a-z][a-z-]*)")
SPAN_RE = re.compile(r"`([^`\n]+)`")


class Cvt:
    """Runs `cvt.py` as a subprocess against one workspace root."""

    def __init__(self, home: Path) -> None:
        self.home = home
        home.mkdir(parents=True, exist_ok=True)

    def raw(self, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, HOME_ENV: str(self.home)}
        env.pop(HOST_ENV, None)
        for key in list(env):
            if key.startswith("CURSOR_") or key == "CLAUDECODE":
                env.pop(key)
        return subprocess.run([sys.executable, str(CVT_PY), *args], cwd=self.home, env=env,
                              capture_output=True, text=True, check=False)

    def run(self, *args: str, code: int = EXIT_OK) -> dict:
        """Run with --json; assert the exit code; return the envelope."""
        proc = self.raw(*args, "--json")
        assert proc.returncode == code, f"cvt {' '.join(args)} exited {proc.returncode}, wanted {code}:\n{proc.stdout}\n{proc.stderr}"
        return json.loads(proc.stdout)

    def out(self, run: str) -> Path:
        return self.home / "out" / run

    def json(self, run: str, name: str) -> dict:
        return jsonio.load_json(self.out(run) / name)


def to_matched(cvt: Cvt, slug: str = "") -> str:
    """init -> ingest -> profile -> jd -> match, with goldens for the AI-written files. Returns the run slug."""
    extra = ["--slug", slug] if slug else []
    run = cvt.run("init", "--cv", str(CV_FIXTURE), "--jd", str(JD_FIXTURE), *extra)["data"]["run_slug"]
    cvt.run("ingest", run)
    shutil.copy(GOLDEN / "profile-map.json", cvt.out(run) / "profile-map.json")
    assert cvt.run("profile-build", run)["stage"] == "profiled"
    shutil.copy(GOLDEN / "jd.json", cvt.out(run) / "jd.json")
    assert cvt.run("jd-check", run)["stage"] == "jd_analyzed"
    shutil.copy(GOLDEN / "match.json", cvt.out(run) / "match.json")
    assert cvt.run("match-check", run)["stage"] == "matched"
    return run


def assert_brief_in_budget(cvt: Cvt, stage: str, run: str, *extra: str) -> dict:
    env = cvt.run("brief", stage, run, *extra)
    data = env["data"]
    budget_cap = jsonio.load_json(BUDGETS)["stages"][stage]["input"]
    assert data["packet"].strip(), stage
    assert data["est_tokens"] <= data["budget"], f"{stage}: {data['est_tokens']} > {data['budget']}"
    assert data["budget"] >= budget_cap, f"{stage}: budget {data['budget']} below the table's {budget_cap}"
    assert not [w for w in data["warnings"] if "budget" in w.lower()], (stage, data["warnings"])
    return data


@pytest.fixture
def cvt(workspace: Path) -> Cvt:
    return Cvt(workspace)


# ---------------------------------------------------------------- the full junior run
def test_junior_run_init_to_report(cvt: Cvt) -> None:
    run = cvt.run("init", "--cv", str(CV_FIXTURE), "--jd", str(JD_FIXTURE))["data"]["run_slug"]
    briefs: dict[str, dict] = {}

    cvt.run("ingest", run)
    briefs["profile"] = assert_brief_in_budget(cvt, "profile", run)
    shutil.copy(GOLDEN / "profile-map.json", cvt.out(run) / "profile-map.json")
    cvt.run("profile-build", run)
    briefs["jd"] = assert_brief_in_budget(cvt, "jd", run)
    shutil.copy(GOLDEN / "jd.json", cvt.out(run) / "jd.json")
    cvt.run("jd-check", run)
    briefs["match"] = assert_brief_in_budget(cvt, "match", run)
    shutil.copy(GOLDEN / "match.json", cvt.out(run) / "match.json")
    cvt.run("match-check", run)

    # checkpoint 1: questions -> exit 6 -> parse -> dry run (writes nothing) -> commit
    briefs["questions"] = assert_brief_in_budget(cvt, "questions", run)
    shutil.copy(GOLDEN / "questions.json", cvt.out(run) / "questions.json")
    pending = cvt.run("questions", run, code=EXIT_AWAITING_USER)
    assert pending["stage"] == "awaiting_answers"
    briefs["answer_parse"] = assert_brief_in_budget(cvt, "answer_parse", run, "--reply", HELM_REPLY)
    round_file = cvt.out(run) / "answers.round.json"
    shutil.copy(GOLDEN / "answers.round.json", round_file)
    dry = cvt.run("answers-apply", run, "--round", str(round_file), "--dry-run")
    assert dry["stage"] == "awaiting_answers"
    assert not (cvt.out(run) / "answers.json").exists()
    committed = cvt.run("answers-apply", run, "--round", str(round_file), "--commit")
    assert committed["stage"] == "answers_applied"
    store = jsonio.load_json(cvt.home / "profiles" / PERSON / "attestations.json")
    assert [(a["id"], a["status"], a["claim"]) for a in store["attestations"]] == [("att-001", "proposed", "Helm")]

    # tailor: plan -> assemble
    briefs["tailor"] = assert_brief_in_budget(cvt, "tailor", run)
    shutil.copy(GOLDEN / "tailor-plan.json", cvt.out(run) / "tailor-plan.json")
    assembled = cvt.run("assemble", run)
    assert assembled["stage"] == "tailored"
    golden = jsonio.load_json(GOLDEN / "tailored.json")
    built = cvt.json(run, "tailored.json")
    assert built["version"] == golden["version"]
    assert built["experience"] == golden["experience"] and built["skills"] == golden["skills"]

    # checkpoint 2: diff -> edits -> approve (real approve, no stage forcing)
    shown = cvt.run("diff", run)
    assert shown["stage"] == "awaiting_approval"
    briefs["change_request"] = assert_brief_in_budget(cvt, "change_request", run, "--reply", CHANGE_REPLY)
    applied = cvt.run("apply-edits", run, str(GOLDEN / "edits-001.json"))
    assert applied["stage"] == "approved"  # the batch ends with approve_all and nothing is left pending
    approved = cvt.run("approve", run)
    assert approved["stage"] == "approved"
    store = jsonio.load_json(cvt.home / "profiles" / PERSON / "attestations.json")
    assert [a["status"] for a in store["attestations"]] == ["active"]
    assert cvt.json(run, "state.json")["attestations_used"] == ["att-001"]

    # fit (no PNGs), validate, critic packet, report
    fitted = cvt.run("fit", run)
    assert fitted["stage"] == "rendered"
    assert not (cvt.out(run) / "pages").exists()
    validated = cvt.run("validate", run)
    assert validated["stage"] == "validated"
    assert not [g for g in cvt.json(run, "validation.json")["gates"] if g["status"] == "fail"]
    briefs["critic"] = assert_brief_in_budget(cvt, "critic", run)
    reported = cvt.run("report", run)
    assert reported["stage"] == "reported"

    final = sorted((cvt.out(run) / "final").glob("*.pdf"))
    assert len(final) == 1
    assert len(PdfReader(str(final[0])).pages) == EXPECTED_PAGES
    report_text = (cvt.out(run) / "report.md").read_text(encoding="utf-8")
    assert "## Token usage" in report_text
    for stage in ("questions", "tailor", "critic"):
        assert f"| {stage} |" in report_text
    state = cvt.json(run, "state.json")
    assert state["stage"] == "reported" and state["checkpoints"] == {"cp1": "done", "cp2": "done"}

    # one usage line per packet built above
    usage_lines = (cvt.out(run) / "usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(usage_lines) == len(briefs)

    # status agrees with the stage and points at nothing left to do
    status = cvt.run("status", run)
    assert status["stage"] == "reported" and "Done" in status["next_action"]

    # classic renders through the same run and invalidates validation/report
    classic = cvt.run("render", run, "--template", "classic")
    assert classic["stage"] == "rendered"
    assert len(PdfReader(str(cvt.out(run) / "cv.pdf")).pages) == EXPECTED_PAGES
    assert "Jamie Rivera" in PdfReader(str(cvt.out(run) / "cv.pdf")).pages[0].extract_text()
    stale_line = next(ln for ln in cvt.raw("status", run).stdout.splitlines() if ln.startswith("stale:"))
    assert {"validation", "final_pdf", "report"} <= set(stale_line.removeprefix("stale:").replace(" ", "").split(","))
    assert cvt.run("validate", run)["stage"] == "validated"


def test_checkpoint1_select_matches_round_replay(workspace: Path, tmp_path: Path) -> None:
    """`answers-apply --select` and the golden round both yield one proposed Helm attestation and the same stage."""
    results = {}
    for label in ("round", "select"):
        cvt = Cvt(tmp_path / label)
        run = to_matched(cvt)
        shutil.copy(GOLDEN / "questions.json", cvt.out(run) / "questions.json")
        cvt.run("questions", run, code=EXIT_AWAITING_USER)
        if label == "round":
            round_file = cvt.out(run) / "answers.round.json"
            shutil.copy(GOLDEN / "answers.round.json", round_file)
            cvt.run("answers-apply", run, "--round", str(round_file), "--commit")
        else:
            dry = cvt.run("answers-apply", run, "--select", "q-1=helm", "--default-rest", "--dry-run")
            assert dry["stage"] == "awaiting_answers" and not (cvt.out(run) / "answers.json").exists()
            cvt.run("answers-apply", run, "--select", "q-1=helm", "--default-rest", "--commit")
        store = jsonio.load_json(cvt.home / "profiles" / PERSON / "attestations.json")
        answers = cvt.json(run, "answers.json")
        questions = cvt.json(run, "questions.json")
        state = cvt.json(run, "state.json")
        results[label] = {
            "stage": state["stage"], "cp1": state["checkpoints"]["cp1"], "rounds": len(answers["rounds"]),
            "attestations": [(a["id"], a["type"], a["claim"], a["status"]) for a in store["attestations"]],
            "statuses": {q["id"]: q["status"] for q in questions["questions"] if q["id"] in ("q-1", "q-2", "q-3")},
        }
    assert results["round"] == results["select"]
    assert results["round"]["attestations"] == [("att-001", "skill", "Helm", "proposed")]
    assert results["round"]["stage"] == "answers_applied" and results["round"]["rounds"] == 1


def test_assemble_failure_then_fix_packet_is_in_budget(cvt: Cvt) -> None:
    run = to_matched(cvt)
    shutil.copy(GOLDEN / "questions.json", cvt.out(run) / "questions.json")
    cvt.run("questions", run, code=EXIT_AWAITING_USER)
    cvt.run("answers-apply", run, "--auto", "--commit")
    plan = jsonio.load_json(GOLDEN / "tailor-plan.json")
    plan["experience"][0]["bullets"][0]["refs"] = ["exp-9.b9"]  # a ref that is not in the profile
    jsonio.dump_json(plan, cvt.out(run) / "tailor-plan.json")
    failed = cvt.run("assemble", run, code=EXIT_CHECK_FAILED)
    assert failed["ok"] is False
    data = assert_brief_in_budget(cvt, "fix", run)
    assert data["attempt"] == 1


# ---------------------------------------------------------------- host question shapes
def test_questions_host_claude_code_respects_tool_limits(cvt: Cvt) -> None:
    run = to_matched(cvt)
    questions = jsonio.load_json(GOLDEN / "questions.json")
    gap = questions["questions"][0]
    gap["choices"] = [{"id": f"c{i}", "label": f"Tool {i}", "value": f"Tool {i}"} for i in range(EXTRA_GAP_CHOICES)]
    gap["links"]["req_ids"] = []
    metric = questions["questions"][1]
    for i in range(EXTRA_QUESTIONS):
        extra = json.loads(json.dumps(metric))
        extra["id"] = f"q-{4 + i}"
        questions["questions"].append(extra)
    jsonio.dump_json(questions, cvt.out(run) / "questions.json")
    env = cvt.run("questions", run, "--format", "host", "--host", "claude_code", code=EXIT_AWAITING_USER)
    calls = env["data"]["render"]["calls"]
    assert len(calls) >= 2
    seen_parts = []
    for call in calls:
        assert 1 <= len(call) <= CLAUDE_MAX_QUESTIONS_PER_CALL
        for question in call:
            assert len(question["options"]) <= CLAUDE_MAX_OPTIONS_PER_QUESTION
            assert len(question["header"]) <= CLAUDE_MAX_HEADER_CHARS
            seen_parts.append(question["header"])
    assert [h for h in seen_parts if "(1/2)" in h or "(2/2)" in h] and len(calls) >= 2, seen_parts

    cursor = cvt.run("questions", run, "--format", "host", "--host", "cursor", code=EXIT_AWAITING_USER)
    shape = cursor["data"]["render"]
    assert {"title", "questions"} <= set(shape)
    assert all({"id", "prompt", "options"} <= set(q) for q in shape["questions"])


# ---------------------------------------------------------------- skill lint, package, docs
def test_lint_skill_all_exits_zero(cvt: Cvt) -> None:
    proc = cvt.raw("lint-skill", "--all")
    assert proc.returncode == EXIT_OK, proc.stdout + proc.stderr
    from_repo = subprocess.run([sys.executable, str(CVT_PY), "lint-skill", "--all"], cwd=REPO_ROOT,
                               capture_output=True, text=True, check=False)
    assert from_repo.returncode == EXIT_OK, from_repo.stdout + from_repo.stderr


def test_package_skill_excludes_private_folders(cvt: Cvt, tmp_path: Path) -> None:
    dest = tmp_path / "dist"
    env = cvt.run("package-skill", "--out", str(dest))
    assert env["ok"] is True
    archives = list(dest.glob("*.zip"))
    assert len(archives) == 1
    with zipfile.ZipFile(archives[0]) as archive:
        names = archive.namelist()
    assert any(n.endswith("SKILL.md") for n in names)
    bare = [n.split("/", 1)[1] if "/" in n else n for n in names]
    assert not [n for n in bare if n.startswith(FORBIDDEN_ZIP_ROOTS)], bare[:5]
    assert not [n for n in names if n.startswith(FORBIDDEN_ZIP_ROOTS) or "/out/" in n or "/profiles/" in n]
    assert not [n for n in names if "__pycache__" in n or n.endswith(".pyc")]


def registered_commands(cvt: Cvt) -> set[str]:
    proc = cvt.raw("--help")
    assert proc.returncode == EXIT_OK
    names = {m.group(1) for line in proc.stdout.splitlines() if (m := COMMAND_LINE_RE.match(line))}
    assert len(names) >= 20, names
    return names


def doc_examples() -> list[tuple[Path, str, str]]:
    """(file, command, rest-of-line) for every `$CVT <cmd> ...` or `cvt.py <cmd> ...` inside backticks."""
    found = []
    for path in DOC_FILES:
        text = path.read_text(encoding="utf-8")
        for span in SPAN_RE.findall(text):
            for match in DOC_COMMAND_RE.finditer(span):
                head, _, rest = match.group(1).partition(" ")
                found.append((path, head, rest))
        for line in text.splitlines():
            if line.lstrip().startswith(("$CVT ", "uv run .claude/skills/tailoring-cvs/scripts/cvt.py ")):
                match = DOC_COMMAND_RE.search(line)
                if match:
                    head, _, rest = match.group(1).partition(" ")
                    found.append((path, head, rest))
    return found


def test_doc_examples_name_registered_commands_and_flags(cvt: Cvt) -> None:
    commands = registered_commands(cvt)
    examples = doc_examples()
    assert len(examples) >= MIN_DOC_EXAMPLES, len(examples)
    help_text: dict[str, str] = {}
    problems = []
    for path, command, rest in examples:
        if command not in commands:
            problems.append(f"{path.name}: unknown command `{command}`")
            continue
        if command not in help_text:
            help_text[command] = cvt.raw(command, "--help").stdout
        for flag in DOC_FLAG_RE.findall(rest):
            if flag in ("--json", "--all", "--help"):
                continue
            if flag not in help_text[command]:
                problems.append(f"{path.name}: `{command}` has no flag {flag}")
    assert not problems, "\n".join(sorted(set(problems)))


def test_every_registered_command_is_documented(cvt: Cvt) -> None:
    documented = SKILL_DIR.joinpath("references", "commands.md").read_text(encoding="utf-8")
    missing = [c for c in sorted(registered_commands(cvt)) if f"`{c}" not in documented]
    assert not missing, missing
