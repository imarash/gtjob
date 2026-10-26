"""Durable attestation store: facts the user stated about their own experience (interfaces.md section 8).

This module is the only writer of `profiles/<person-slug>/attestations.json`.
"""

from __future__ import annotations

import copy

from . import jsonio, paths, schemas
from .errors import CvtError, ExitCode

SCHEMA_NAME = "attestations"
SCHEMA_VERSION = "1"
ID_FORMAT = "att-%03d"
FIRST_SEQ = 1
STATUS_PROPOSED = "proposed"
STATUS_ACTIVE = "active"
STATUS_REVOKED = "revoked"
STATUSES = (STATUS_PROPOSED, STATUS_ACTIVE, STATUS_REVOKED)
TRANSITIONS: dict[str, tuple[str, ...]] = {
    STATUS_PROPOSED: (STATUS_ACTIVE, STATUS_REVOKED),
    STATUS_ACTIVE: (STATUS_REVOKED,),
    STATUS_REVOKED: (),
}
PROPOSAL_FIELDS = (
    "type", "claim", "terms", "detail", "scope", "placement", "correction", "verbatim", "caveat",
)
UNRESOLVED_SCOPE = "unresolved"


def empty_store(person_slug: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION, "person_slug": person_slug, "next_seq": FIRST_SEQ, "attestations": [],
    }


def load_store(person_slug: str) -> dict:
    """The person's store; an empty valid one (not written) when the file does not exist."""
    path = paths.attestations_path(person_slug)
    if not path.is_file():
        return empty_store(person_slug)
    store = jsonio.load_json(path)
    schemas.require_valid(store, SCHEMA_NAME, str(path))
    return store


def save_store(person_slug: str, store: dict) -> None:
    """Validate against the schema and write atomically."""
    if store.get("person_slug") != person_slug:
        raise CvtError(
            ExitCode.STATE, "E_ATTEST_PERSON",
            f"store belongs to '{store.get('person_slug')}', not '{person_slug}'",
            hint="load the store with load_store(person_slug) for the same person before saving",
        )
    schemas.require_valid(store, SCHEMA_NAME, "attestation store")
    jsonio.dump_json(store, paths.attestations_path(person_slug))


def add(store: dict, proposed: dict, *, run_id: str, question_id: str) -> dict:
    """Append a `proposed` attestation built from `proposed` (assigns att-NNN); returns it."""
    missing = [f for f in PROPOSAL_FIELDS if f not in proposed]
    if missing:
        raise CvtError(
            ExitCode.CHECK_FAILED, "E_ATTEST_FIELDS", f"proposed attestation lacks: {', '.join(missing)}",
            hint="copy every field of answers.schema.json#/$defs/proposed_attestation",
        )
    now = jsonio.now_iso()
    seq = int(store["next_seq"])
    att = {"id": ID_FORMAT % seq}
    att.update({f: copy.deepcopy(proposed[f]) for f in PROPOSAL_FIELDS})
    att.update({
        "question_id": question_id, "run_id": run_id, "created_at": now,
        "status": STATUS_PROPOSED, "status_changed_at": now,
    })
    store["attestations"].append(att)
    store["next_seq"] = seq + 1
    return att


def get(store: dict, att_id: str) -> dict:
    for att in store["attestations"]:
        if att["id"] == att_id:
            return att
    raise CvtError(
        ExitCode.INPUT, "E_ATTEST_UNKNOWN", f"no attestation '{att_id}' for {store.get('person_slug', '')}",
        hint="list ids with: cvt attest list RUN",
    )


def set_status(store: dict, att_id: str, status: str) -> dict:
    """proposed -> active|revoked, active -> revoked. Anything else raises E_ATTEST_TRANSITION."""
    att = get(store, att_id)
    if status not in STATUSES or status not in TRANSITIONS[att["status"]]:
        allowed = ", ".join(TRANSITIONS[att["status"]]) or "none (revoked is final)"
        raise CvtError(
            ExitCode.CHECK_FAILED, "E_ATTEST_TRANSITION",
            f"{att_id} cannot go from {att['status']} to {status}",
            hint=f"allowed from {att['status']}: {allowed}",
        )
    att["status"] = status
    att["status_changed_at"] = jsonio.now_iso()
    return att


def usable(store: dict, *, run_id: str, include_proposed: bool) -> list[dict]:
    """Active attestations, plus `proposed` ones created in `run_id` when asked. Never revoked or unresolved."""
    out = []
    for att in store["attestations"]:
        if att["scope"]["kind"] == UNRESOLVED_SCOPE:
            continue
        if att["status"] == STATUS_ACTIVE:
            out.append(att)
        elif att["status"] == STATUS_PROPOSED and include_proposed and att["run_id"] == run_id:
            out.append(att)
    return out


def find_by_terms(store: dict, terms: list[str]) -> list[dict]:
    """Active attestations whose `terms` intersect `terms` (case-insensitive)."""
    wanted = {t.casefold() for t in terms}
    return [
        a for a in store["attestations"]
        if a["status"] == STATUS_ACTIVE and wanted & {t.casefold() for t in a["terms"]}
    ]
