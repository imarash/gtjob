"""Turn a parked Certifications block into real certificates, and copy PDF link URLs onto them.

A profile map sometimes stores the whole certifications paragraph in `other_sections`. Tailoring only
renders `certificates`, so that paragraph never reaches the CV. Text extraction also drops PDF link
annotations, so the public URLs have to be read from the file itself.

Recovery is deterministic and idempotent. It runs when a profile is built, verified, loaded from the
cache, or assembled, including a cache written before this existed.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import profile as prof

CERT_TITLE_RE = re.compile(
    r"^(?:professional\s+|relevant\s+)?(?:certifications?|certificates?|licen[cs]es?|credentials?|badges)"
    r"(?:\s+and\s+training)?$",
    re.IGNORECASE,
)
NAME_SPLIT_RE = re.compile(r"\s*[·•]\s*")
SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)
ISSUERS = (
    ("anthropic", "Anthropic"),
    ("google", "Google"),
    ("red hat", "Red Hat"),
    ("hashicorp", "HashiCorp"),
    ("amazon web services", "AWS"),
    ("aws", "AWS"),
    ("openstack", "OpenStack"),
    ("microsoft", "Microsoft"),
    ("azure", "Microsoft"),
    ("linux foundation", "Linux Foundation"),
)
def split_certificate_names(text: str) -> list[str]:
    """Credential names in one paragraph, split on the middot or bullet that separates them."""
    parts = [" ".join(part.split()).strip(" -") for part in NAME_SPLIT_RE.split(text or "")]
    return [part for part in parts if part]


def infer_issuer(name: str) -> str:
    """Issuer word that already appears in the certification name, or ''."""
    folded = name.casefold()
    for needle, issuer in ISSUERS:
        if needle in folded:
            return issuer
    return ""


def _norm_url(url: str) -> str:
    text = url.strip().lower()
    text = SCHEME_RE.sub("", text).removeprefix("//").removeprefix("www.")
    text = text.split("?", 1)[0].split("#", 1)[0]
    return text.rstrip("/")


def _contact_urls(profile: dict) -> set[str]:
    basics = profile.get("basics") or {}
    urls = [basics.get("url") or ""]
    urls += [p.get("url") or "" for p in basics.get("profiles") or []]
    return {_norm_url(url) for url in urls if url.strip()}


def promote_parked_certificates(profile: dict) -> bool:
    """Move a Certifications `other_sections` entry into `certificates`. Returns whether the profile changed."""
    existing = {prof.comparable(c["name"]) for c in profile["certificates"]}
    kept: list[dict] = []
    removed: set[str] = set()
    added = False
    for section in profile["other_sections"]:
        if not CERT_TITLE_RE.match(str(section.get("title", "")).strip()):
            kept.append(section)
            continue
        names = split_certificate_names(section.get("text", ""))
        if not names:
            kept.append(section)
            continue
        removed.add(section["id"])
        added = True
        for name in names:
            key = prof.comparable(name)
            if key in existing:
                continue
            existing.add(key)
            profile["certificates"].append({
                "id": "cert-0", "name": name, "issuer": infer_issuer(name), "date": "",
            })
    exploded: list[dict] = []
    seen = set()
    for cert in profile["certificates"]:
        names = split_certificate_names(cert.get("name", ""))
        if len(names) <= 1:
            exploded.append(cert)
            seen.add(prof.comparable(cert.get("name", "")))
            continue
        added = True
        for name in names:
            key = prof.comparable(name)
            if key in seen:
                continue
            seen.add(key)
            exploded.append({
                "id": "cert-0", "name": name, "issuer": cert.get("issuer") or infer_issuer(name),
                "date": cert.get("date") or "",
            })
    profile["certificates"] = exploded
    profile["other_sections"] = kept
    if removed:
        profile["source_issues"] = [
            issue for issue in profile["source_issues"]
            if not (set(issue.get("item_ids") or []) and set(issue["item_ids"]) <= removed)
            and not (issue.get("kind") == "extraction" and "certif" in issue.get("message", "").casefold())
        ]
    if added:
        prof.normalize_ids(profile)
    return added


def pdf_certificate_urls(pdf_path: Path, skip_urls: set[str]) -> list[str]:
    """Verification URLs in reading order. Wrapped links that repeat the same URL collapse to one.

    Contact links (the header website, LinkedIn, mailto) are skipped. Returns [] when the file cannot be read.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    try:
        reader = PdfReader(str(pdf_path))
    except Exception:  # noqa: BLE001 - a broken PDF must not block the CV; names still render
        return []
    found: list[tuple[int, float, float, str]] = []
    for page_no, page in enumerate(reader.pages):
        for annot in list(page.get("/Annots") or []):
            obj = annot.get_object()
            action = obj.get("/A")
            if action is None:
                continue
            uri = str(action.get_object().get("/URI") or "")
            if not uri or uri.lower().startswith(("mailto:", "tel:")):
                continue
            if _norm_url(uri) in skip_urls:
                continue
            rect = [float(v) for v in obj.get("/Rect")]
            found.append((page_no, -rect[1], rect[0], uri))
    found.sort()
    urls: list[str] = []
    for _page, _y, _x, uri in found:
        if urls and urls[-1] == uri:
            continue
        urls.append(uri)
    return urls


def attach_certificate_urls(profile: dict, pdf_path: Path | None) -> bool:
    """Copy PDF link URLs onto certificates when the link count matches the certificate count.

    A mismatch leaves every URL blank rather than guessing which link belongs to which name.
    """
    certs = profile["certificates"]
    if pdf_path is None or not certs or any((c.get("url") or "").strip() for c in certs):
        return False
    urls = pdf_certificate_urls(pdf_path, _contact_urls(profile))
    if len(urls) != len(certs):
        return False
    for cert, url in zip(certs, urls, strict=True):
        cert["url"] = url
    return True


def cv_pdf(run_dir: Path, st: dict) -> Path | None:
    """The run's stored CV when it is a PDF, else None."""
    info = (st.get("inputs") or {}).get("cv") or {}
    if info.get("format") != "pdf":
        return None
    path = Path(run_dir) / str(info.get("stored_path") or "")
    return path if path.is_file() else None


def recover(profile: dict, pdf_path: Path | None = None) -> bool:
    """Promote parked certificates and attach PDF links. Returns whether `profile` changed."""
    changed = promote_parked_certificates(profile)
    changed = attach_certificate_urls(profile, pdf_path) or changed
    return changed
