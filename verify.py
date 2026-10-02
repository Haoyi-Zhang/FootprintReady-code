#!/usr/bin/env python3
"""Check every distributed feasible or infeasible certificate without producer imports."""
from __future__ import annotations

import json
import resource
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from checker import check, load_json
from verify_bibliography import verify as verify_bibliography


def main():
    start = time.process_time()
    fixtures = load_json(ROOT / "inputs" / "validation-cases.json")
    expected = load_json(ROOT / "results" / "summary.json")
    statuses = Counter()
    for item in fixtures:
        instance = item["instance"]
        certificate = load_json(ROOT / "results" / "certificates" / f"{instance['name']}.json")
        verdict = check(instance, certificate)
        statuses[verdict["status"]] += 1
    if sum(statuses.values()) != expected["certificate_count"]:
        raise ValueError("certificate count differs from recorded result")
    if statuses["feasible"] != expected["feasible_certificates"]:
        raise ValueError("feasible certificate count differs from recorded result")
    if statuses["infeasible"] != expected["infeasible_certificates"]:
        raise ValueError("infeasible certificate count differs from recorded result")
    bibliography = verify_bibliography()
    print(json.dumps({
        "accepted_certificates": sum(statuses.values()),
        "accepted_feasible": statuses["feasible"],
        "accepted_infeasible": statuses["infeasible"],
        "cpu_seconds": time.process_time() - start,
        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "bibliography_audit": bibliography,
    }, indent=2))


if __name__ == "__main__":
    main()
