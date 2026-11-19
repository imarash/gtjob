"""Parked certification paragraphs become certificates, and PDF links attach only on an exact count match."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from pypdf import PdfWriter
from pypdf.annotations import Link

from cvtlib import cert_recover, schemas
from cvtlib.profile import comparable

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
GOLDEN = FIXTURES / "golden" / "junior" / "profile.json"


def _profile() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_parked_certifications_section_becomes_individual_certificates():
    profile = _profile()
    before = len(profile["certificates"])
    profile["other_sections"].append({
        "id": "oth-9",
        "title": "Certifications",
        "text": "Google Cloud Certified Professional Cloud Architect · Red Hat Certified Specialist in OpenShift Administration",
    })
    profile["source_issues"].append({
        "id": "iss-9", "kind": "extraction", "severity": "info", "origin": "ai",
        "message": "Certifications are a single wrapped block; mapped as other_sections.",
        "item_ids": ["oth-9"],
    })
    assert cert_recover.promote_parked_certificates(profile) is True
    names = [c["name"] for c in profile["certificates"]]
    assert names[before:] == [
        "Google Cloud Certified Professional Cloud Architect",
        "Red Hat Certified Specialist in OpenShift Administration",
    ]
    assert profile["certificates"][-2]["issuer"] == "Google"
    assert profile["certificates"][-1]["issuer"] == "Red Hat"
    assert all(section["title"] != "Certifications" for section in profile["other_sections"])
    assert all("oth-9" not in issue["item_ids"] for issue in profile["source_issues"])
    assert schemas.validate(profile, "profile") == []
    assert cert_recover.promote_parked_certificates(profile) is False


def test_projects_section_is_left_alone():
    profile = _profile()
    original = copy.deepcopy(profile["other_sections"])
    assert cert_recover.promote_parked_certificates(profile) is False
    assert profile["other_sections"] == original


def test_pdf_links_attach_in_reading_order_and_skip_contact_links(tmp_path: Path):
    profile = _profile()
    profile["certificates"] = [
        {"id": "cert-1", "name": "AWS Certified Cloud Practitioner", "issuer": "AWS", "date": ""},
        {"id": "cert-2", "name": "HashiCorp Certified: Terraform Associate", "issuer": "HashiCorp", "date": ""},
    ]
    profile["basics"]["url"] = "https://www.example.com"
    pdf = tmp_path / "cv.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_annotation(0, Link(rect=(40, 700, 160, 720), url="mailto:me@example.com"))
    writer.add_annotation(0, Link(rect=(180, 700, 300, 720), url="https://www.example.com"))
    writer.add_annotation(0, Link(rect=(40, 400, 200, 420), url="https://www.credly.com/badges/aaa"))
    writer.add_annotation(0, Link(rect=(40, 360, 120, 378), url="https://www.credly.com/badges/aaa"))
    writer.add_annotation(0, Link(rect=(220, 360, 400, 378), url="https://www.credly.com/badges/bbb"))
    writer.write(pdf)

    assert cert_recover.recover(profile, pdf) is True
    assert [c["url"] for c in profile["certificates"]] == [
        "https://www.credly.com/badges/aaa",
        "https://www.credly.com/badges/bbb",
    ]
    assert cert_recover.attach_certificate_urls(profile, pdf) is False


def test_mismatched_link_count_does_not_guess(tmp_path: Path):
    profile = _profile()
    profile["certificates"] = [
        {"id": "cert-1", "name": "AWS Certified Cloud Practitioner", "issuer": "AWS", "date": ""},
        {"id": "cert-2", "name": "HashiCorp Certified: Terraform Associate", "issuer": "HashiCorp", "date": ""},
    ]
    pdf = tmp_path / "cv.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_annotation(0, Link(rect=(40, 400, 200, 420), url="https://www.credly.com/badges/only"))
    writer.write(pdf)
    assert cert_recover.attach_certificate_urls(profile, pdf) is False
    assert all(not c.get("url") for c in profile["certificates"])
    assert comparable("AWS Certified Cloud Practitioner") in comparable(profile["certificates"][0]["name"])
