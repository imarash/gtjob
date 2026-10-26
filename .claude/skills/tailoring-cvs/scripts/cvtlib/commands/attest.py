"""`cvt attest list|show|revoke|activate`: inspect and change the durable attestation store.

The store is addressed by a run (its `person_slug`) or `--person P`. `revoke` and `activate` ask nothing:
the agent confirms with the user first.
"""

from __future__ import annotations

import argparse
import json

from .. import attestations, output, paths, state
from ..errors import CvtError, ExitCode

CLAIM_WIDTH = 40
RUN_WIDTH = 24
SUBCOMMANDS = ("list", "show", "revoke", "activate")
ACTION_STATUS = {"revoke": attestations.STATUS_REVOKED, "activate": attestations.STATUS_ACTIVE}


def _flags(parser: argparse.ArgumentParser) -> None:
    for flag, text in (("--json", "print one minified JSON envelope on stdout"),
                       ("--all", "lift the output caps")):
        parser.add_argument(flag, action="store_true", default=argparse.SUPPRESS, help=text)
    parser.add_argument("--person", default="", metavar="P", help="person slug (instead of RUN)")


def _person(args: argparse.Namespace) -> tuple[str, str]:
    """(person_slug, run_slug_or_empty)."""
    if args.person:
        return args.person, ""
    run_dir = paths.resolve_run(args.run or None)
    slug = state.load(run_dir).get("person_slug", "")
    if not slug:
        raise CvtError(
            ExitCode.STATE, "E_PERSON_UNKNOWN", f"run {run_dir.name} has no person_slug yet (profile not built)",
            hint="pass --person P, or finish the profile stage first",
        )
    return slug, run_dir.name


def _clip(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _scope_summary(scope: dict) -> str:
    kind = scope["kind"]
    if kind == "role_label":
        return f"role_label={scope['role_label']} ({len(scope['item_ids'])})"
    if kind == "items":
        return f"items ({len(scope['item_ids'])})"
    return kind


def _row(att: dict) -> str:
    return " | ".join([
        att["id"], att["type"], _clip(att["claim"], CLAIM_WIDTH), att["status"], att["placement"],
        _scope_summary(att["scope"]), _clip(att["run_id"] or "-", RUN_WIDTH),
    ])


def _list(args: argparse.Namespace, person: str, run: str) -> int:
    store = attestations.load_store(person)
    items = store["attestations"]
    shown, hidden = output.cap_list(args, items)
    data = {"person_slug": person, "count": len(items), "attestations": shown}
    if hidden:
        data["attestations_more"] = hidden
    lines = [f"{person}: {len(items)} attestation(s)  (id | type | claim | status | placement | scope | run)"]
    lines += [_row(a) for a in shown] if items else ["none yet"]
    if hidden:
        lines.append(output.MORE_LINE.format(n=hidden))
    return output.emit(args, run=run, data=data, human="\n".join(lines))


def _show(args: argparse.Namespace, person: str, run: str) -> int:
    att = attestations.get(attestations.load_store(person), args.id)
    return output.emit(args, run=run, data={"person_slug": person, "attestation": att},
                       human=json.dumps(att, indent=2, ensure_ascii=False))


def _change(args: argparse.Namespace, person: str, run: str) -> int:
    status = ACTION_STATUS[args.action]
    store = attestations.load_store(person)
    att = attestations.get(store, args.id)
    if status == attestations.STATUS_ACTIVE and att["scope"]["kind"] == attestations.UNRESOLVED_SCOPE:
        raise CvtError(
            ExitCode.CHECK_FAILED, "E_ATTEST_SCOPE_UNRESOLVED",
            f"{args.id} has an unresolved scope and cannot be activated",
            hint="ask the scope question, apply the answer, then activate",
        )
    old = att["status"]
    attestations.set_status(store, args.id, status)
    attestations.save_store(person, store)
    return output.emit(
        args, run=run, data={"person_slug": person, "id": args.id, "from": old, "to": status},
        human=f"{args.id} {old} -> {status} ({att['claim']})",
    )


def _dispatch(args: argparse.Namespace) -> int:
    person, run = _person(args)
    if args.action == "list":
        return _list(args, person, run)
    if args.action == "show":
        return _show(args, person, run)
    return _change(args, person, run)


def register(subparsers) -> None:
    parent = subparsers.add_parser("attest", help="list, show, revoke, or activate stored attestations")
    sub = parent.add_subparsers(dest="action", metavar="<action>", parser_class=type(parent))
    for name in SUBCOMMANDS:
        p = sub.add_parser(name, help=f"{name} attestation(s)")
        if name != "list":
            p.add_argument("id", metavar="ID", help="attestation id, e.g. att-001")
        p.add_argument("run", nargs="?", default="", metavar="RUN", help="run slug (its person_slug picks the store)")
        _flags(p)
        p.set_defaults(func=_dispatch, command="attest")
