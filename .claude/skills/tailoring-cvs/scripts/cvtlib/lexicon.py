"""Term and number lexicon behind the provenance validator (interfaces.md sections 5 and 8).

`find_terms` returns the claim-bearing tokens of a text, `numbers` its normalized numeric tokens, and `supports`
tells whether a source text backs a term (case-insensitive, plural/possessive tolerant, synonym-aware). Synonym
classes are true equivalences only (k8s = Kubernetes); hypernyms never are (EKS is not Kubernetes).
"""

from __future__ import annotations

import decimal
import functools
import re
import unicodedata

from . import jsonio, paths

LEXICON_DIR = "lexicon"
TECH_TERMS_FILE = "tech-terms.txt"
COMMON_WORDS_FILE = "common-words.txt"
SYNONYMS_FILE = "synonyms.json"
LOGISTICS_FILE = "logistics-patterns.json"
COMMENT_PREFIX = "#"
CASE_SENSITIVE_PREFIX = "="
MIN_STEM_LEN = 3
MIN_SINGULAR_LEN = 4
MIN_ES_LEN = 5
MIN_ACRONYM_LEN = 2
SENTENCE_BREAKS = frozenset(".!?\n\r·|•")
LEADING_PUNCT = frozenset(" \t\"'([{“‘*-–—_\x00")
MULTIPLIERS = {
    "k": 1_000, "m": 1_000_000, "b": 1_000_000_000, "t": 1_000_000_000_000,
    "bn": 1_000_000_000, "mn": 1_000_000, "tn": 1_000_000_000_000,
}
# Cardinal words that count as numbers (`two`..`nineteen`, tens). `one`, `a`, `an` are not standalone numbers
# ("one of", "one idea per bullet"); `one` only counts as the unit of a compound ("twenty-one").
NUMBER_WORD_UNITS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
NUMBER_WORD_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
COMPOUND_ONLY_WORD = "one"
# Articles that count as 1 only when a multiplier follows directly ("a million users" -> 1000000).
ARTICLE_MULTIPLIER_WORDS = frozenset({"a", "an", "one"})
# Abbreviated scales never take an article ("a TN town" is a place, not 10^12); they need a digit before them.
ABBREVIATED_SCALE_WORDS = frozenset({"bn", "bln", "mn", "mln", "tn"})
NUMBER_WORD_MULTIPLIERS = {
    "hundred": 100, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000, "dozen": 12,
    "trillion": 1_000_000_000_000, "bn": 1_000_000_000, "bln": 1_000_000_000, "mn": 1_000_000, "mln": 1_000_000,
    "tn": 1_000_000_000_000, "lakh": 100_000, "crore": 10_000_000,
}
HUNDRED_WORD = "hundred"
DOZEN_WORD = "dozen"
SCALE_WORDS = frozenset({
    "thousand", "million", "billion", "trillion", "bn", "bln", "mn", "mln", "tn", "lakh", "crore",
})
# Multiplier words are implied metrics ("doubled", "tenfold", "halved"). Bare "double"/"triple" are not
# ("double-check", "triple-A"). They never join a run with neighbouring number words.
FOLD_SUFFIX = "fold"
HALF_VALUE = 50
SOLO_VALUE_WORDS = {
    **{w: 2 for w in ("doubled", "doubling", "doubles", "twice")},
    **{w: 3 for w in ("tripled", "tripling", "triples", "thrice")},
    **{w: 4 for w in ("quadrupled", "quadrupling", "quadruples")},
    **{w: 5 for w in ("quintupled", "quintupling", "quintuples")},
    **{w: 6 for w in ("sextupled", "sextupling", "sextuples")},
    **{w: 10 for w in ("decupled", "decupling")},
    **{w: HALF_VALUE for w in ("half", "halved", "halving", "halves")},
    **{f"{word}{FOLD_SUFFIX}": value
       for table in (NUMBER_WORD_UNITS, NUMBER_WORD_TENS, {HUNDRED_WORD: 100}) for word, value in table.items()},
}
_KIND_NUM, _KIND_UNIT, _KIND_TENS, _KIND_MULT, _KIND_ONE = "num", "unit", "tens", "mult", "one"
_KIND_SOLO = "solo"
QUOTE_MAP = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_ACRONYM_RE = re.compile(r"(?=[A-Z0-9]*[A-Z])[A-Z0-9]{%d,}" % MIN_ACRONYM_LEN)
_INNER_CAPS_RE = re.compile(r"[a-z][A-Z]")
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_.])(?<!\d,)(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:((?i:bn|mn|tn|[kmbt]))(?![A-Za-z0-9]))?",
)
_SEPARATOR_RE = re.compile(r"[\s\-]+")
_AND_JOIN_RE = re.compile(r"[\s\-]+and[\s\-]+", re.IGNORECASE)
_NUMBER_WORD_RE = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]+(?![A-Za-z0-9])")
_SUFFIX = r"(?:'s|s|es)?"


# --- asset loaders ------------------------------------------------------------------------------------------
def _read_entries(name: str) -> list[str]:
    path = paths.asset(LEXICON_DIR, name)
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith(COMMENT_PREFIX)]


@functools.cache
def _tech_entries() -> tuple[tuple[str, bool], ...]:
    """(term, case_sensitive) longest first, duplicates removed (case-insensitive)."""
    seen: set[str] = set()
    out: list[tuple[str, bool]] = []
    for raw in _read_entries(TECH_TERMS_FILE):
        sensitive = raw.startswith(CASE_SENSITIVE_PREFIX)
        term = raw[len(CASE_SENSITIVE_PREFIX):].strip() if sensitive else raw
        key = f"{term.casefold()}|{sensitive}"
        if term and key not in seen:
            seen.add(key)
            out.append((term, sensitive))
    out.sort(key=lambda e: (-len(e[0]), e[0].casefold()))
    return tuple(out)


def tech_terms() -> list[str]:
    """Entries of tech-terms.txt without the case-sensitivity marker, longest first."""
    return [term for term, _ in _tech_entries()]


@functools.cache
def _synonym_classes() -> tuple[tuple[str, ...], ...]:
    data = jsonio.load_json(paths.asset(LEXICON_DIR, SYNONYMS_FILE))
    return tuple(tuple(str(m) for m in cls) for cls in data)


def synonyms() -> list[list[str]]:
    """Equivalence classes from synonyms.json."""
    return [list(cls) for cls in _synonym_classes()]


@functools.cache
def _common_set() -> frozenset[str]:
    words: set[str] = set()
    for line in _read_entries(COMMON_WORDS_FILE):
        words.update(w.casefold() for w in line.split())
    return frozenset(words)


def common_words() -> set[str]:
    return set(_common_set())


@functools.cache
def _logistics() -> tuple[dict, ...]:
    return tuple(jsonio.load_json(paths.asset(LEXICON_DIR, LOGISTICS_FILE)))


def logistics_patterns() -> list[dict]:
    """[{kind, regex}] for salary, visa, work authorization, relocation, onsite days and recruiter emails."""
    return [dict(p) for p in _logistics()]


# --- text normalization -------------------------------------------------------------------------------------
def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(QUOTE_MAP).casefold()


def _strip_possessive(word: str) -> str:
    return word[:-2] if word.endswith("'s") else word


# --- common-word test (inflection tolerant) -----------------------------------------------------------------
def _stems(word: str) -> set[str]:
    stems = {word}
    if word.endswith("ies") and len(word) > MIN_ES_LEN:
        stems.add(word[:-3] + "y")
    for suffix in ("es", "s", "ed", "d", "ing", "ly"):
        if word.endswith(suffix) and len(word) - len(suffix) >= MIN_STEM_LEN:
            stems.add(word[: -len(suffix)])
    if word.endswith("ing") and len(word) - 3 >= MIN_STEM_LEN:
        stems.add(word[:-3] + "e")
        if len(word) > 4 and word[-4] == word[-5]:
            stems.add(word[:-4])
    if word.endswith("ed") and len(word) > 4 and word[-3] == word[-4]:
        stems.add(word[:-3])
    return stems


def _is_common(word: str) -> bool:
    common = _common_set()
    base = _strip_possessive(_norm(word))
    base = "".join(ch for ch in base if ch.isalpha()) or base
    return any(stem in common for stem in _stems(base))


# --- find_terms ---------------------------------------------------------------------------------------------
def _entry_pattern(term: str, sensitive: bool) -> str:
    parts = [re.escape(p) for p in _SEPARATOR_RE.split(term.strip()) if p]
    body = r"[\s\-]+".join(parts)
    return f"(?-i:{body})" if sensitive else body


@functools.cache
def _tech_regex() -> re.Pattern[str]:
    alternatives = "|".join(_entry_pattern(t, s) for t, s in _tech_entries())
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alternatives})(?:'s|’s|s|es)?(?![A-Za-z0-9])", re.IGNORECASE)


def _starts_sentence(text: str, index: int) -> bool:
    i = index - 1
    while i >= 0 and text[i] in LEADING_PUNCT:
        i -= 1
    return i < 0 or text[i] in SENTENCE_BREAKS


def _is_proper_noun(token: str, text: str, index: int) -> bool:
    if len(token) < MIN_ACRONYM_LEN or not token[0].isupper() or _starts_sentence(text, index):
        return False
    return not _is_common(token)


def find_terms(text: str) -> list[str]:
    """Claim-bearing tokens of `text`, first occurrence order, de-duplicated case-insensitively.

    Order of evidence: tech-terms.txt entries (longest first, word boundaries), acronyms, InnerCaps tokens,
    and capitalized words that are not at a sentence start and not in common-words.txt.
    """
    found: list[tuple[int, str]] = []
    masked = list(text)
    for m in _tech_regex().finditer(text):
        found.append((m.start(), _strip_possessive(m.group(0).replace("’", "'"))))
        masked[m.start():m.end()] = "\x00" * (m.end() - m.start())
    rest = "".join(masked)
    for m in _WORD_RE.finditer(rest):
        token = m.group(0)
        if _ACRONYM_RE.fullmatch(token):
            if not _is_common(token):
                found.append((m.start(), token))
        elif _INNER_CAPS_RE.search(token):
            found.append((m.start(), token))
        elif _is_proper_noun(token, text, m.start()):
            found.append((m.start(), token))
    found.sort(key=lambda item: item[0])
    seen: set[str] = set()
    out: list[str] = []
    for _, term in found:
        key = _norm(term)
        if key not in seen:
            seen.add(key)
            out.append(term)
    return out


# --- numbers ------------------------------------------------------------------------------------------------
def _format_number(value: decimal.Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _word_kind(word: str) -> tuple[str, decimal.Decimal] | None:
    if word == COMPOUND_ONLY_WORD:
        return _KIND_ONE, decimal.Decimal(1)
    if word in SOLO_VALUE_WORDS:
        return _KIND_SOLO, decimal.Decimal(SOLO_VALUE_WORDS[word])
    for table, kind in ((NUMBER_WORD_UNITS, _KIND_UNIT), (NUMBER_WORD_TENS, _KIND_TENS),
                        (NUMBER_WORD_MULTIPLIERS, _KIND_MULT)):
        if word in table:
            return kind, decimal.Decimal(table[word])
    return None


def _atoms(text: str) -> list[tuple[int, int, str, str, decimal.Decimal]]:
    """(start, end, kind, word, value) for digit tokens and number words, in text order."""
    atoms: list[tuple[int, int, str, str, decimal.Decimal]] = []
    for m in _NUMBER_RE.finditer(text):
        value = decimal.Decimal(m.group(1).replace(",", ""))
        if m.group(2):
            value *= MULTIPLIERS[m.group(2).casefold()]
        atoms.append((m.start(), m.end(), _KIND_NUM, "", value))
    words = [(m.start(), m.end(), m.group(0).casefold()) for m in _NUMBER_WORD_RE.finditer(text)]
    for i, (start, end, word) in enumerate(words):
        if word in ARTICLE_MULTIPLIER_WORDS and i + 1 < len(words):
            next_start, _, next_word = words[i + 1]
            if (next_word in NUMBER_WORD_MULTIPLIERS and next_word not in ABBREVIATED_SCALE_WORDS
                    and _SEPARATOR_RE.fullmatch(text[end:next_start])):
                atoms.append((start, end, _KIND_UNIT, word, decimal.Decimal(1)))
                continue
        kind = _word_kind(word)
        if kind:
            atoms.append((start, end, kind[0], word, kind[1]))
    atoms.sort(key=lambda a: a[0])
    return atoms


def _parse_run(run: list[tuple[int, int, str, str, decimal.Decimal]]) -> list[decimal.Decimal]:
    """Values of one run of adjacent atoms ("two hundred fifty" -> 250, "twenty five" -> 25, "5 thousand" -> 5000)."""
    values: list[decimal.Decimal] = []
    total = decimal.Decimal(0)
    cur: decimal.Decimal | None = None
    last = ""

    def flush() -> None:
        nonlocal total, cur, last
        if cur is not None or total:
            values.append(total + (cur or 0))
        total, cur, last = decimal.Decimal(0), None, ""

    for _, _, kind, word, value in run:
        if kind == _KIND_SOLO:
            flush()
            values.append(value)
        elif kind == _KIND_NUM:
            flush()
            cur, last = value, kind
        elif kind in (_KIND_UNIT, _KIND_ONE):
            if cur is None and not total and kind == _KIND_ONE:
                continue  # bare "one" is not a number
            if cur is None:
                cur = value
            elif last in (_KIND_TENS, HUNDRED_WORD) and (cur % 100 == 0 or last == _KIND_TENS):
                cur += value
            else:
                flush()
                if kind == _KIND_ONE:
                    continue
                cur = value
            last = _KIND_UNIT
        elif kind == _KIND_TENS:
            if cur is None:
                cur = value
            elif last == HUNDRED_WORD:
                cur += value
            else:
                flush()
                cur = value
            last = _KIND_TENS
        elif word == HUNDRED_WORD:
            if cur is None or cur >= 100 or last == DOZEN_WORD:
                flush()  # bare "hundred" is not a number
                continue
            cur, last = cur * value, HUNDRED_WORD
        elif word in SCALE_WORDS:
            if cur is None:
                continue
            total, cur, last = total + cur * value, None, word
        else:  # dozen
            cur = value if cur is None else cur * value
            last = DOZEN_WORD
    flush()
    return values


def _joins(prev: tuple[int, int, str, str, decimal.Decimal], atom: tuple[int, int, str, str, decimal.Decimal],
           gap: str) -> bool:
    """Adjacent atoms join across spaces/hyphens, and across "and" after a scale word ("two hundred and fifty")."""
    if _KIND_SOLO in (prev[2], atom[2]):
        return False
    if _SEPARATOR_RE.fullmatch(gap):
        return True
    return prev[3] in (HUNDRED_WORD, *SCALE_WORDS) and bool(_AND_JOIN_RE.fullmatch(gap))


def numbers(text: str) -> list[str]:
    """Normalized numeric tokens: `800+` -> `800`, `99.99%` -> `99.99`, `5,000` -> `5000`, `5k` -> `5000`,
    `2bn` -> `2000000000`.

    Cardinal words count too: `Five` -> `5`, `twenty-five` -> `25`, `a dozen` -> `12`, `two hundred` -> `200`,
    `a trillion` -> `1000000000000` (`one`, `a`, `an` alone do not). Digits glued to letters (`S3`, `k8s`, `Q3`)
    are part of a name, not a number.
    Multiplier words are implied metrics and never join neighbouring number words: `doubled`/`doubling`/`twice`/`twofold` -> `2`,
    `tripled`/`thrice`/`threefold` -> `3`, `quadrupled`/`fourfold` -> `4`, `quintupled`/`quintupling` -> `5`,
    `sextupled`/`sextupling` -> `6`, `decupled`/`decupling` -> `10`, `<cardinal>fold` (`tenfold`) -> its value,
    `half`/`halved`/`halving`/`halves` -> `50`. Bare `double` and `triple` are not numbers ("double-check").
    Order of appearance, no duplicates.
    """
    norm = unicodedata.normalize("NFKC", text)
    runs: list[list[tuple[int, int, str, str, decimal.Decimal]]] = []
    for atom in _atoms(norm):
        if runs and _joins(runs[-1][-1], atom, norm[runs[-1][-1][1]:atom[0]]):
            runs[-1].append(atom)
        else:
            runs.append([atom])
    out: list[str] = []
    for run in runs:
        for value in _parse_run(run):
            token = _format_number(value)
            if token not in out:
                out.append(token)
    return out


# --- supports -----------------------------------------------------------------------------------------------
@functools.cache
def _synonym_index() -> dict[str, tuple[str, ...]]:
    index: dict[str, tuple[str, ...]] = {}
    for cls in _synonym_classes():
        members = tuple(_norm(m) for m in cls)
        for member in members:
            index[_SEPARATOR_RE.sub(" ", member)] = members
    return index


def _variants(term: str) -> set[str]:
    base = _SEPARATOR_RE.sub(" ", _strip_possessive(_norm(term)).strip())
    out = {base}
    if base.endswith("ies") and len(base) > MIN_ES_LEN:
        out.add(base[:-3] + "y")
    if base.endswith("es") and len(base) >= MIN_ES_LEN:
        out.add(base[:-2])
    if base.endswith("s") and len(base) >= MIN_SINGULAR_LEN:
        out.add(base[:-1])
    return out


@functools.lru_cache(maxsize=8192)
def _pattern(form: str) -> re.Pattern[str]:
    parts = [re.escape(p) for p in _SEPARATOR_RE.split(form) if p]
    return re.compile(rf"(?<![a-z0-9]){r'[\s\-]+'.join(parts)}{_SUFFIX}(?![a-z0-9])")


def supports(term: str, source_text: str) -> bool:
    """True when `source_text` contains `term` or a synonym of it (case-insensitive, plural/possessive tolerant)."""
    if not term.strip():
        return True
    source = _norm(source_text)
    forms: set[str] = set()
    index = _synonym_index()
    for variant in _variants(term):
        forms.add(variant)
        for member in index.get(variant, ()):
            forms.add(_SEPARATOR_RE.sub(" ", member))
    return any(_pattern(form).search(source) for form in forms if form)
