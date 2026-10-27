"""Terminal interaction: question prompts with numbered choices, and checkpoint-2 review commands.

`TerminalIO` talks to a person; `ScriptedIO` replays a list (tests). Both implement the small `IO` protocol that
`gtjob.flow` uses, so the flow never touches `input()` or `print()` directly.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

PROMPT_MAX_CHARS = 110
DEFAULT_MAX_CHARS = 60
INPUT_PROMPT = "> "
CONFIRM_SUFFIX = " [Y/n] "
SKIP_WORDS = ("skip", "s")
QUIT_WORDS = ("q", "quit", "exit")
YES_WORDS = ("y", "yes")
NO_WORDS = ("n", "no")
APPROVE_WORDS = ("a", "approve", "done")
FULL_DIFF_WORDS = ("d", "diff", "full")
HELP_WORDS = ("", "?", "h", "help")
REJECT_WORDS = ("r", "reject")
EDIT_WORDS = ("e", "edit")
SINGLE_CHOICE_TYPES = ("single_select", "yes_no")
TOKEN_SPLIT_RE = re.compile(r"[,\s]+")
NUMBER_RE = re.compile(r"^[0-9]+$")
LETTER_RE = re.compile(r"^[a-z]$")
ELLIPSIS = "…"
CP1_HEADER = "Checkpoint 1: {n} question(s). Enter = default | 1,3 = choices | skip | or type your answer | q = stop here"
CP2_HELP = (
    "Checkpoint 2: a = approve all | r N = reject item N | e N <text> = replace item N's text | "
    "d = full diff | q = stop here | or describe any change in your own words"
)


class IO(Protocol):
    """What the flow needs from a terminal. `ask` returns None when no input is available (stdin closed, script spent)."""

    interactive: bool

    def say(self, text: str) -> None: ...

    def error(self, text: str) -> None: ...

    def ask(self, prompt: str) -> str | None: ...

    def confirm(self, prompt: str, default: bool = True) -> bool: ...


class TerminalIO:
    """stdin/stdout. Not interactive unless stdin is a TTY: piped runs stop at checkpoints instead of prompting."""

    def __init__(self) -> None:
        self.interactive = bool(sys.stdin and sys.stdin.isatty())

    def say(self, text: str) -> None:
        print(text, flush=True)

    def error(self, text: str) -> None:
        print(text, file=sys.stderr, flush=True)

    def ask(self, prompt: str) -> str | None:
        if not self.interactive:
            return None
        try:
            return input(prompt)
        except EOFError:
            return None

    def confirm(self, prompt: str, default: bool = True) -> bool:
        answer = self.ask(prompt + CONFIRM_SUFFIX)
        if answer is None or not answer.strip():
            return default
        return answer.strip().lower() in YES_WORDS


@dataclass
class ScriptedIO:
    """Replays `inputs` for `ask` and `confirms` for `confirm`; records everything printed. Used by tests."""

    inputs: list[str | Callable[[], str]] = field(default_factory=list)  # a callable is evaluated when asked
    confirms: list[bool] = field(default_factory=list)
    interactive: bool = True
    said: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)

    def say(self, text: str) -> None:
        self.said.append(text)

    def error(self, text: str) -> None:
        self.errors.append(text)

    def ask(self, prompt: str) -> str | None:
        self.prompts.append(prompt)
        if not self.inputs:
            return None
        item = self.inputs.pop(0)
        return item() if callable(item) else item

    def confirm(self, prompt: str, default: bool = True) -> bool:
        self.prompts.append(prompt)
        return self.confirms.pop(0) if self.confirms else default

    @property
    def output(self) -> str:
        return "\n".join(self.said)


# --- checkpoint 1 -------------------------------------------------------------------------------------------
def _clip(text: str, width: int) -> str:
    flat = " ".join(str(text).split())
    return flat if len(flat) <= width else flat[: width - 1].rstrip() + ELLIPSIS


def format_question(q: dict) -> list[str]:
    """Two lines: the prompt, then numbered choices with the default."""
    lines = [f"[{q['id']}] {q['topic']}: {_clip(q['prompt'], PROMPT_MAX_CHARS)}"]
    choices = "   ".join(f"{i}) {c['label']}" for i, c in enumerate(q["choices"], start=1))
    default = _clip(q["default"].get("description") or q["default"].get("text") or "", DEFAULT_MAX_CHARS)
    lines.append("    " + (f"{choices}   " if choices else "") + f"(default: {default})")
    return lines


def parse_selection(q: dict, text: str) -> list[str] | None:
    """Choice ids when `text` is a pure selection (`1,3`, `a`, a choice id or label); None when it is free text.

    Raises ValueError for a selection-shaped answer that names no real choice (for example `9` of 3).
    """
    choices = q["choices"]
    if not choices:
        return None
    clean = text.strip().lower()
    by_name = {**{c["id"].lower(): c["id"] for c in choices}, **{c["label"].lower(): c["id"] for c in choices}}
    if clean in by_name:
        return [by_name[clean]]
    tokens = [t for t in TOKEN_SPLIT_RE.split(clean) if t]
    if not tokens or not all(NUMBER_RE.match(t) or LETTER_RE.match(t) or t in by_name for t in tokens):
        return None
    picked: list[str] = []
    for token in tokens:
        if token in by_name:
            cid = by_name[token]
        else:
            index = int(token) - 1 if NUMBER_RE.match(token) else ord(token) - ord("a")
            if not 0 <= index < len(choices):
                raise ValueError(f"no choice '{token}' (pick 1-{len(choices)})")
            cid = choices[index]["id"]
        if cid not in picked:
            picked.append(cid)
    if q["type"] in SINGLE_CHOICE_TYPES and len(picked) > 1:
        raise ValueError("this question takes one choice")
    return picked


@dataclass
class Checkpoint1Answers:
    choices: dict[str, list[str]] = field(default_factory=dict)  # [] = skip
    texts: dict[str, str] = field(default_factory=dict)
    default_rest: bool = True


def prompt_questions(io: IO, pending: list[dict]) -> Checkpoint1Answers | None:
    """Ask each pending question. Blank takes the default. Returns None when the person stops (q) or input ends."""
    io.say(CP1_HEADER.format(n=len(pending)))
    answers = Checkpoint1Answers()
    for q in pending:
        for line in format_question(q):
            io.say(line)
        while True:
            raw = io.ask(INPUT_PROMPT)
            if raw is None or raw.strip().lower() in QUIT_WORDS:
                return None
            text = raw.strip()
            if not text:
                break  # default (default_rest covers it)
            if text.lower() in SKIP_WORDS:
                answers.choices[q["id"]] = []
                break
            try:
                picked = parse_selection(q, text)
            except ValueError as exc:
                io.error(f"  {exc}; try again")
                continue
            if picked is None:
                answers.texts[q["id"]] = text
            else:
                answers.choices[q["id"]] = picked
            break
    return answers


# --- checkpoint 2 -------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ReviewCommand:
    kind: str  # approve | reject | edit | full | change | help | quit | bad
    n: int = 0
    text: str = ""


def parse_review(raw: str) -> ReviewCommand:
    """`a`, `r N`, `e N <text>`, `d`, `q`, or free text (a change request)."""
    text = raw.strip()
    lower = text.lower()
    if lower in HELP_WORDS:
        return ReviewCommand("help")
    if lower in APPROVE_WORDS:
        return ReviewCommand("approve")
    if lower in FULL_DIFF_WORDS:
        return ReviewCommand("full")
    if lower in QUIT_WORDS:
        return ReviewCommand("quit")
    head, _, rest = text.partition(" ")
    if head.lower() in REJECT_WORDS + EDIT_WORDS:
        number, _, tail = rest.strip().partition(" ")
        if not NUMBER_RE.match(number):
            return ReviewCommand("bad", text=f"'{head}' needs an item number, for example: {head} 2")
        if head.lower() in REJECT_WORDS:
            return ReviewCommand("reject", n=int(number))
        if not tail.strip():
            return ReviewCommand("bad", text=f"'{head} {number}' needs the new text, for example: {head} {number} Led a team of 5")
        return ReviewCommand("edit", n=int(number), text=tail.strip())
    return ReviewCommand("change", text=text)


def ask_review(io: IO) -> ReviewCommand | None:
    """One checkpoint-2 prompt. None when input ends."""
    raw = io.ask(INPUT_PROMPT)
    return None if raw is None else parse_review(raw)
