#!/usr/bin/env python3
"""Regenerate or verify the exact deterministic validation input file."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from cases import (small_cases, campaign_cases, identity_case, schedule_cases,
                   footprint_cases, footprint_identity_case)


def payload():
    return (
        [{"group": "small", "instance": case} for case in small_cases()] +
        [{"group": "matrix", "instance": case} for case in campaign_cases()] +
        [{"group": "schedule", "instance": case} for case in schedule_cases()] +
        [{"group": "identity", "instance": identity_case()}] +
        [{"group": "footprint", "instance": case} for case in footprint_cases()] +
        [{"group": "footprint-identity", "instance": footprint_identity_case()}]
    )


def serialized():
    return json.dumps(payload(), indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / "inputs" / "validation-cases.json"
    expected = serialized().encode("utf-8")
    if args.check:
        if target.read_bytes() != expected:
            raise SystemExit("frozen validation input differs from deterministic constructor")
        print(f"verified {len(payload())} frozen cases")
    else:
        target.write_bytes(expected)
        print(f"wrote {len(payload())} cases to {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
