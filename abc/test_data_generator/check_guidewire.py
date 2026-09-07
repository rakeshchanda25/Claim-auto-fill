"""Standalone checker for the Guidewire API and every function the app uses.

Runs each call on its own so you can see exactly which one fails, how long it
took and what it returned - independent of the document generator.

    python check_guidewire.py --list                 # what can be checked
    python check_guidewire.py 000-00-000123          # run everything
    python check_guidewire.py 000-00-000123 --only details policy notes
    python check_guidewire.py 000-00-000123 --full   # print whole responses
    python check_guidewire.py 000-00-000123 --save out/   # one JSON per call
    python check_guidewire.py --ping                 # connectivity only

Exit code is 0 only if every selected check passed.
"""

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

from guidewire import GuidewireClient
from claim_context import (
    claim_narrative,
    claim_to_fields,
    extract_claim_id,
    fetch_claim_context,
)

# Same values app.py runs with, so a pass here means the app can reach it too.
BASE_URL = "https://cc-dev-gwcpdev.valuemom.zeta1-andromeda.guidewire.net:443"
USERNAME = "su"
PASSWORD = "gw"
TIMEOUT = 60

# name -> (description, needs_claim_id, how to call it)
CLIENT_CHECKS = {
    "resolve":        ("Resolve claim number to public id", True,
                       lambda c, cid: c.resolve_claim_id_by_number(cid)),
    "details":        ("Claim details summary", True, lambda c, cid: c.get_claim_details_summary(cid)),
    "policy":         ("Policy summary", True, lambda c, cid: c.get_claim_policy_summary(cid)),
    "contacts":       ("Contacts and their roles", True, lambda c, cid: c.get_claim_contacts_summary(cid)),
    "notes":          ("Adjuster notes", True, lambda c, cid: c.get_claim_notes_summary(cid)),
    "activities":     ("Activities", True, lambda c, cid: c.get_claim_activities_summary(cid)),
    "history":        ("History events", True, lambda c, cid: c.get_claim_history_events_summary(cid)),
    "exposures":      ("Exposures", True, lambda c, cid: c.get_claim_exposures_summary(cid)),
    "vehicles":       ("Vehicle incidents", True, lambda c, cid: c.get_claim_vehicle_incidents_summary(cid)),
    "reserves":       ("Reserves", True, lambda c, cid: c.get_claim_reserves_summary(cid)),
    "payments":       ("Payments", True, lambda c, cid: c.get_claim_payments_summary(cid)),
    "checks":         ("Checks", True, lambda c, cid: c.get_claim_checks_summary(cid)),
    "documents":      ("Document search across default queries", True,
                       lambda c, cid: c.get_claim_document_searches_summary(cid)),
    "doc-search":     ("Single document search (pattern: police report)", True,
                       lambda c, cid: c.search_claim_documents_summary(cid, "police report|accident report")),
    "identity":       ("Claim identity summary", True, lambda c, cid: c.get_claim_identity_summary(cid)),
    "state-payload":  ("Full claim state payload", True, lambda c, cid: c.get_claim_state_payload(cid)),
    "background":     ("Claim background context", True, lambda c, cid: c.get_claim_background_context(cid)),
    "state-hash":     ("Claim state hash", True, lambda c, cid: c.compute_claim_state_hash(cid)),
}

# The claim_context.py layer the app actually consumes, checked end to end.
CONTEXT_CHECKS = ("context", "fields", "narrative")

ALL_CHECKS = list(CLIENT_CHECKS) + list(CONTEXT_CHECKS)


def _describe(value) -> str:
    """One line saying what came back, without dumping the whole payload."""
    if isinstance(value, str):
        return f"str({len(value)} chars): {value[:120]}"
    if isinstance(value, list):
        return f"list({len(value)} items)"
    if isinstance(value, dict):
        if value.get("error"):
            # The one line has to be actionable on its own - an HTTP status and
            # the server's own message say far more than "http_error".
            parts = [str(value["error"])]
            if value.get("status"):
                parts.append(f"HTTP {value['status']} {value.get('reason', '')}".strip())
            if value.get("body"):
                parts.append(" ".join(str(value["body"]).split())[:200])
            return "ERROR " + " | ".join(parts)
        keys = ", ".join(list(value)[:8])
        return f"dict({len(value)} keys): {keys}"
    return f"{type(value).__name__}: {value!r}"


def _is_failure(value) -> bool:
    """The client returns error strings/dicts instead of raising, so an
    HTTP 500 looks like a successful call unless we look at the payload."""
    if isinstance(value, dict) and value.get("error"):
        return True
    if isinstance(value, str) and value.lower().startswith(("error", "http error", "failed")):
        return True
    return value is None


def _save(out_dir: Path, name: str, value) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    print(f"      saved -> {path}")


def run_check(name: str, description: str, call, *, full: bool, out_dir: Path | None) -> bool:
    print(f"\n[{name}] {description}")
    started = time.perf_counter()
    try:
        value = call()
    except Exception as exc:
        print(f"   FAIL  raised {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=3)
        return False

    ms = round((time.perf_counter() - started) * 1000)
    failed = _is_failure(value)
    print(f"   {'FAIL' if failed else 'ok  '}  {ms} ms  {_describe(value)}")

    if full and not isinstance(value, str):
        print(json.dumps(value, indent=2, default=str)[:20000])
    elif full:
        print(value[:20000])

    if out_dir:
        _save(out_dir, name, value)
    return not failed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("claim", nargs="?", help="claim number or cc: public id")
    parser.add_argument("--only", nargs="+", metavar="CHECK",
                        help=f"run only these checks ({', '.join(ALL_CHECKS)})")
    parser.add_argument("--skip", nargs="+", metavar="CHECK", default=[],
                        help="run everything except these")
    parser.add_argument("--full", action="store_true", help="print whole responses")
    parser.add_argument("--save", metavar="DIR", help="write each response to DIR/<check>.json")
    parser.add_argument("--list", action="store_true", help="list checks and exit")
    parser.add_argument("--ping", action="store_true",
                        help="connectivity only - no claim needed")
    args = parser.parse_args(argv)

    if args.list:
        print("Client checks:")
        for name, (desc, _, _) in CLIENT_CHECKS.items():
            print(f"  {name:15} {desc}")
        print("claim_context.py checks:")
        print(f"  {'context':15} fetch_claim_context() - the 5 parallel calls the app makes")
        print(f"  {'fields':15} claim_to_fields() - what gets injected into documents")
        print(f"  {'narrative':15} claim_narrative() - what gets appended to the prompt")
        return 0

    if not args.claim and not args.ping:
        parser.error("a claim number is required (or use --ping / --list)")

    selected = args.only or ALL_CHECKS
    unknown = [c for c in selected if c not in ALL_CHECKS]
    if unknown:
        parser.error(f"unknown check(s): {unknown}. Known: {', '.join(ALL_CHECKS)}")
    selected = [c for c in selected if c not in args.skip]

    client = GuidewireClient(base_url=BASE_URL, username=USERNAME,
                             password=PASSWORD, timeout_seconds=TIMEOUT)
    print(f"Guidewire: {BASE_URL}\nUser:      {USERNAME}  (timeout {TIMEOUT}s)")

    out_dir = Path(args.save) if args.save else None

    if args.ping:
        # Cheapest authenticated call that proves DNS, TLS, auth and routing.
        ok = run_check("ping", "GET rest/claim/v1/claims (auth + reachability)",
                       lambda: client.get_json("rest/claim/v1/claims?pageSize=1"),
                       full=args.full, out_dir=out_dir)
        return 0 if ok else 1

    # extract_claim_id is what app.py uses on free-text user input, so check it
    # against the argument the same way rather than trusting the raw string.
    extracted = extract_claim_id(args.claim) or args.claim
    print(f"Claim:     {args.claim!r} -> extract_claim_id -> {extracted!r}")

    results = {}

    # Resolve once; every other call needs the public id, and running it per
    # check would hide a resolution failure behind 17 identical errors.
    claim_id = extracted
    if "resolve" in selected:
        try:
            claim_id = client.resolve_claim_id_by_number(extracted)
            print(f"\n[resolve] Resolve claim number to public id\n   ok    -> {claim_id!r}")
            results["resolve"] = True
        except Exception as exc:
            print(f"\n[resolve] FAIL  {type(exc).__name__}: {exc}")
            results["resolve"] = False
            print("\nCannot continue without a claim id.")
            return 1

    for name in selected:
        if name in ("resolve",) or name in CONTEXT_CHECKS:
            continue
        desc, _, call = CLIENT_CHECKS[name]
        results[name] = run_check(name, desc, lambda c=call: c(client, claim_id),
                                  full=args.full, out_dir=out_dir)

    context = None
    if "context" in selected:
        def _fetch():
            nonlocal context
            context = fetch_claim_context(client, extracted)
            return {
                "details_keys": sorted(context.details),
                "policy_keys": sorted(context.policy),
                "contacts": len(context.contacts),
                "notes": len(context.notes),
                "excerpts": len(context.excerpts),
                "description": context.description,
            }
        results["context"] = run_check(
            "context", "fetch_claim_context() - the 5 parallel calls the app makes",
            _fetch, full=args.full, out_dir=out_dir)

    if "fields" in selected:
        if context is None:
            print("\n[fields] skipped - needs the 'context' check")
        else:
            results["fields"] = run_check(
                "fields", "claim_to_fields() - values injected into every document",
                lambda: claim_to_fields(context), full=True, out_dir=out_dir)

    if "narrative" in selected:
        if context is None:
            print("\n[narrative] skipped - needs the 'context' check")
        else:
            results["narrative"] = run_check(
                "narrative", "claim_narrative() - text appended to the agent prompt",
                lambda: claim_narrative(context), full=True, out_dir=out_dir)

    passed = sum(1 for v in results.values() if v)
    failed = [k for k, v in results.items() if not v]
    print(f"\n{'=' * 60}\n{passed}/{len(results)} checks passed")
    if failed:
        print("failed: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
