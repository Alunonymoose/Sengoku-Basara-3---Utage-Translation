#!/usr/bin/env python3
"""Validate BASARA Foundry machine-readable terminology ledger."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BLOCKING_STATUSES = {"CONFLICT", "NEEDS_SOURCE", "NEEDS_CONTEXT"}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ledger", type=Path)
    ap.add_argument("--release-gate", action="store_true", help="fail if any release-blocking terminology state remains")
    args = ap.parse_args()

    data = json.loads(args.ledger.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    errors = []
    ids = set()

    for i, entry in enumerate(entries):
        eid = entry.get("id")
        if not eid:
            errors.append(f"entry {i}: missing id")
            continue
        if eid in ids:
            errors.append(f"duplicate id: {eid}")
        ids.add(eid)

        status = entry.get("status")
        if not status:
            errors.append(f"{eid}: missing status")
        canonical = entry.get("canonical_english")
        if status not in BLOCKING_STATUSES and not canonical:
            errors.append(f"{eid}: non-blocking status requires canonical_english")

        forbidden = entry.get("forbidden_or_superseded_variants", [])
        if canonical and canonical in forbidden:
            errors.append(f"{eid}: canonical wording is also marked forbidden")

        variants = entry.get("current_variants", [])
        if status == "CONFLICT" and len(variants) < 2:
            errors.append(f"{eid}: CONFLICT needs at least two current_variants")

    blockers = [
        {"id": e.get("id"), "status": e.get("status"), "variants": e.get("current_variants", [])}
        for e in entries if e.get("status") in BLOCKING_STATUSES
    ]

    result = {
        "schema": data.get("schema"),
        "entry_count": len(entries),
        "validation_errors": errors,
        "release_blockers": blockers,
        "release_ready_terminology": not errors and not blockers,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if errors:
        return 2
    if args.release_gate and blockers:
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
