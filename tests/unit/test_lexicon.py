"""WP-13: lexicon (terms, numbers, synonyms, common words, logistics patterns)."""

from __future__ import annotations

import re

import pytest

from cvtlib import lexicon

MIN_TECH_TERMS = 400
MIN_COMMON_WORDS = 3000


def _lower(terms: list[str]) -> list[str]:
    return [t.casefold() for t in terms]


def test_assets_load_and_are_sized():
    terms = lexicon.tech_terms()
    assert len(terms) >= MIN_TECH_TERMS
    assert [len(t) for t in terms] == sorted((len(t) for t in terms), reverse=True)  # longest first
    assert "SOC 2" in terms and "error budget" in terms and "Claude Code" in terms
    assert len(lexicon.common_words()) >= MIN_COMMON_WORDS
    assert {"led", "designed", "built", "owned", "drove"} <= lexicon.common_words()
    assert all("regex" in p and "kind" in p for p in lexicon.logistics_patterns())
    for p in lexicon.logistics_patterns():
        re.compile(p["regex"])


def test_synonym_classes_are_equivalences_not_hypernyms():
    classes = [{m.casefold() for m in cls} for cls in lexicon.synonyms()]
    assert any({"kubernetes", "k8s"} <= c for c in classes)
    assert any({"ci/cd", "cicd"} <= c for c in classes)
    assert any({"gcp", "google cloud"} <= c for c in classes)
    assert not any({"eks", "kubernetes"} <= c for c in classes)
    assert not any({"aws", "ec2"} <= c for c in classes)


@pytest.mark.parametrize("text,expected", [
    ("Rolled out a service mesh and error budget policy", ["service mesh", "error budget"]),
    ("Passed a SOC 2 audit and led incident response", ["SOC 2", "incident response"]),
    ("Ran workloads on EKS with IAM roles", ["EKS", "IAM"]),
    ("Wrote TypeScript and GitOps tooling on OpenShift", ["TypeScript", "GitOps", "OpenShift"]),
    ("Evaluated Linkerd and Dynatrace for the platform", ["Linkerd", "Dynatrace"]),
    ("Defined SLOs and an SLA", ["SLOs", "SLA"]),
    ("Founded an early-stage startup", ["early-stage", "startup"]),
])
def test_find_terms_detects_claims(text, expected):
    found = _lower(lexicon.find_terms(text))
    for term in expected:
        assert term.casefold() in found, (term, found)


@pytest.mark.parametrize("text", [
    "Led the migration and reduced costs",
    "Designed and built a reliable platform for the team",
    "Owned delivery. Drove adoption across the company",
    "Resolved about 30 support tickets per week for students and staff",
])
def test_find_terms_ignores_common_words_and_sentence_starts(text):
    assert lexicon.find_terms(text) == []


def test_find_terms_longest_match_consumes_inner_words():
    assert lexicon.find_terms("GitHub Actions") == ["GitHub Actions"]
    assert _lower(lexicon.find_terms("on-call rotation and runbooks")) == ["on-call", "runbooks"]


def test_find_terms_mid_sentence_capitalized_but_not_common():
    assert "Zorblax" in lexicon.find_terms("We migrated off Zorblax last year")
    assert lexicon.find_terms("Zorblax migration finished") == []  # sentence start is not a signal


def test_find_terms_possessive_and_plural():
    assert _lower(lexicon.find_terms("Linkerd's dashboards")) == ["linkerd"]
    assert _lower(lexicon.find_terms("Wrote 5 runbooks")) == ["runbooks"]


@pytest.mark.parametrize("text,expected", [
    ("800+ engineers", ["800"]),
    ("an 8-member team", ["8"]),
    ("99.99% availability", ["99.99"]),
    ("5,000 requests", ["5000"]),
    ("saved 5k", ["5000"]),
    ("$240,000 per year", ["240000"]),
    ("from 25 to 8 minutes, 25 again", ["25", "8"]),
    ("S3, EC2, k8s and Q3 are names", []),
    ("2.50 and 3.0", ["2.5", "3"]),
    ("up to $1.5M", ["1500000"]),
    ("10x faster", ["10"]),
    ("by 40%.", ["40"]),
    ("Five years of AWS", ["5"]),
    ("twenty-five services", ["25"]),
    ("twenty five services", ["25"]),
    ("a dozen runbooks", ["12"]),
    ("two dozen runbooks", ["24"]),
    ("two hundred hosts", ["200"]),
    ("5 thousand users", ["5000"]),
    ("two hundred and fifty", ["250"]),
    ("two hundred fifty hosts", ["250"]),
    ("three million requests", ["3000000"]),
    ("a billion events", ["1000000000"]),
    ("Processed a billion events.", ["1000000000"]),
    ("one billion events", ["1000000000"]),
    ("two billion events", ["2000000000"]),
    ("5 billion", ["5000000000"]),
    ("1.5 billion", ["1500000000"]),
    ("two billion five hundred million", ["2500000000"]),
    ("billions of events", []),
    ("TWENTY-ONE teams", ["21"]),
    ("one of the first", []),
    ("one idea per bullet, an owner, a team", []),
    ("hundreds of hosts, a hundred", ["100"]),  # "hundreds" alone is not counted; "a hundred" is 100
    ("hundreds of hosts, an outage", []),
    ("one million users", ["1000000"]),
    ("a million requests", ["1000000"]),
    ("Scaled the platform to one million users.", ["1000000"]),
    ("Grew to a million requests per day.", ["1000000"]),
    ("one hundred servers", ["100"]),
    ("a hundred servers", ["100"]),
    ("Managed one hundred servers.", ["100"]),
    ("Ran a hundred servers.", ["100"]),
    ("an hundred", ["100"]),
    ("A thousand tests", ["1000"]),
    ("a one-thousand batch", ["1000"]),
    ("one hundred and fifty", ["150"]),
    ("a team of five", ["5"]),
    ("an outage", []),
    ("two, three and 2", ["2", "3"]),
    ("Built pipelines for twenty services (12 before)", ["20", "12"]),
    # WP-FIX-3-11: trillion, bn/mn/tn/T suffixes, bn/bln/mn/mln/tn words, lakh and crore
    ("a trillion requests", ["1000000000000"]),
    ("two trillion", ["2000000000000"]),
    ("Processed a trillion events.", ["1000000000000"]),
    ("2bn events", ["2000000000"]),
    ("1.2bn", ["1200000000"]),
    ("$3mn", ["3000000"]),
    ("1tn", ["1000000000000"]),
    ("1T tokens", ["1000000000000"]),
    ("2 bn", ["2000000000"]),
    ("2 mln", ["2000000"]),
    ("3 bln", ["3000000000"]),
    ("10 lakh users", ["1000000"]),
    ("2 crore", ["20000000"]),
    ("Processed 2bn events.", ["2000000000"]),
    ("Trained on 2T tokens.", ["2000000000000"]),
    ("trillions of rows", []),
    ("5TB", ["5"]),
    ("200ms", ["200"]),
    ("3x faster", ["3"]),
    ("k8s", []),
    ("S3", []),
    ("5B", ["5000000000"]),
    ("1.5k", ["1500"]),
    ("5k+ hosts", ["5000"]),
    ("5mm", ["5"]),
    ("Minneapolis, MN", []),
    ("Nashville, TN 37201", ["37201"]),
    ("a million users", ["1000000"]),
    ("two billion five hundred million", ["2500000000"]),
    ("Moved to a TN town.", []),  # an article never scales an abbreviation
    ("Relocated from a MN office.", []),
    ("a crore", ["10000000"]),
    ("a lakh", ["100000"]),
])
def test_numbers_normalization(text, expected):
    assert lexicon.numbers(text) == expected


@pytest.mark.parametrize("term,source,expected", [
    ("k8s", "We run Kubernetes in production", True),
    ("Kubernetes", "migrated to k8s", True),
    ("EKS", "We run Kubernetes in production", False),  # hypernym, never a synonym
    ("Kubernetes", "ran workloads on EKS", False),
    ("SLOs", "defined an SLO per service", True),
    ("SLO", "service level objectives for APIs", True),
    ("error budgets", "tracked the error budget", True),
    ("Linkerd's", "Linkerd rollout", True),
    ("CI/CD", "built CICD pipelines", True),
    ("Google Cloud", "GCP landing zone", True),
    ("on-call", "weekly on call rotation", True),
    ("Terraform", "Terraformed everything", False),  # word boundary
    ("Java", "JavaScript apps", False),
    ("IaC", "infrastructure as code with Terraform", True),
    ("Helm", "Docker and Terraform", False),
    ("C++", "legacy C++ services", True),
])
def test_supports(term, source, expected):
    assert lexicon.supports(term, source) is expected


def test_logistics_patterns_match_expected_text():
    by_kind: dict[str, list[re.Pattern]] = {}
    for p in lexicon.logistics_patterns():
        by_kind.setdefault(p["kind"], []).append(re.compile(p["regex"], re.IGNORECASE))

    def hit(kind: str, text: str) -> bool:
        return any(r.search(text) for r in by_kind[kind])

    assert hit("salary_range", "$72,000-$88,000")
    assert hit("salary_period", "$85,000 per year")
    assert hit("base_equity", "base + equity")
    assert hit("visa", "requires visa sponsorship")
    assert hit("work_authorization", "valid work authorization")
    assert hit("relocation", "willing to relocate")
    assert hit("onsite_days", "on site 3 days a week")
    assert hit("recruiter_email", "talent@harborpoint.example")
    assert not hit("visa", "Worked at Visa on payments")
    assert not hit("salary_range", "cut AWS spend from $2M to $1.4M")
