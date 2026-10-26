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
MULTIPLIERS = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
QUOTE_MAP = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_ACRONYM_RE = re.compile(r"(?=[A-Z0-9]*[A-Z])[A-Z0-9]{%d,}" % MIN_ACRONYM_LEN)
_INNER_CAPS_RE = re.compile(r"[a-z][A-Z]")
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_.])(?<!\d,)(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:([kKmMbB])(?![A-Za-z0-9]))?",
)
_SEPARATOR_RE = re.compile(r"[\s\-]+")
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


def numbers(text: str) -> list[str]:
    """Normalized numeric tokens: `800+` -> `800`, `99.99%` -> `99.99`, `5,000` -> `5000`, `5k` -> `5000`.

    Digits glued to letters (`S3`, `k8s`, `Q3`) are part of a name, not a number. Order of appearance, no duplicates.
    """
    out: list[str] = []
    for m in _NUMBER_RE.finditer(unicodedata.normalize("NFKC", text)):
        value = decimal.Decimal(m.group(1).replace(",", ""))
        if m.group(2):
            value *= MULTIPLIERS[m.group(2).casefold()]
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
