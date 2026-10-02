#!/usr/bin/env python3
"""Fresh one-worker reproduction with deterministic reference comparison."""
from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from checker import load_json


def stable(value):
    if isinstance(value, dict):
        return {
            key: stable(item)
            for key, item in value.items()
            if not ("seconds" in key or "rss" in key)
        }
    if isinstance(value, list):
        return [stable(item) for item in value]
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reproduction-output"))
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        parser.error("output directory already exists; select a fresh directory")
    out.mkdir(parents=True)

    fixtures = load_json(ROOT / "inputs" / "validation-cases.json")
    split = min(64, len(fixtures))
    wall0 = time.monotonic()
    cpu0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    runs = []
    logpath = out / "reproduction.log"
    commands = [
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        [sys.executable, "verify_bibliography.py"],
        [sys.executable, "freeze_inputs.py", "--check"],
        [sys.executable, "pilot.py", "--out", str(out)],
        [sys.executable, "run.py", "--out", str(out), "--start", "0", "--stop", str(split)],
        [sys.executable, "run.py", "--out", str(out), "--start", str(split), "--stop", str(len(fixtures))],
        [sys.executable, "summarize.py", "--out", str(out)],
        [sys.executable, "exhaustive_audit.py", "--out", str(out / "exhaustive-audit.json")],
    ]
    with logpath.open("w", encoding="utf-8") as log:
        for command in commands:
            started = time.monotonic()
            result = subprocess.run(
                command,
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=False,
            )
            display = ["python", *command[1:]]
            rendered = []
            for part in display:
                if part == str(out):
                    rendered.append("<fresh-output>")
                elif part.startswith(str(out) + str(Path("/"))):
                    rendered.append("<fresh-output>/" + str(Path(part).relative_to(out)))
                else:
                    rendered.append(part)
            display = rendered
            runs.append({
                "command": display,
                "exit_code": result.returncode,
                "wall_seconds": time.monotonic() - started,
            })
            if result.returncode:
                raise RuntimeError(f"reproduction command failed: {display}")

    compared = []
    json_names = (
        f"chunk-0-{split}.json",
        f"chunk-{split}-{len(fixtures)}.json",
        "summary.json",
        "mutations.json",
        "abstraction-ablation.json",
        "semantic-differential.json",
        "exhaustive-audit.json",
        "pilot.json",
    )
    for name in json_names:
        reference = load_json(ROOT / "results" / name)
        observed = load_json(out / name)
        if stable(reference) != stable(observed):
            raise AssertionError(f"deterministic result mismatch: {name}")
        compared.append(name)

    csv_names = (
        "family-costs.csv",
        "interval-costs.csv",
        "schedule-costs.csv",
        "abstraction-ablation.csv",
        "footprint-costs.csv",
    )
    for name in csv_names:
        if (ROOT / "results" / name).read_bytes() != (out / name).read_bytes():
            raise AssertionError(f"data table mismatch: {name}")
        compared.append(name)

    pilot_certificate_names = (
        "boundary-flush-certificate.json",
        "boundary-retain-certificate.json",
        "pilot-fork-join-certificate.json",
        "schedule-4-1-40-certificate.json",
        "footprint-identity-certificate.json",
    )
    for name in pilot_certificate_names:
        reference = load_json(ROOT / "results" / name)
        observed = load_json(out / name)
        if reference != observed:
            raise AssertionError(f"pilot certificate mismatch: {name}")
        compared.append(name)

    reference_names = {path.name for path in (ROOT / "results" / "certificates").glob("*.json")}
    observed_names = {path.name for path in (out / "certificates").glob("*.json")}
    if reference_names != observed_names:
        raise AssertionError("certificate set mismatch")
    for name in reference_names:
        reference = load_json(ROOT / "results" / "certificates" / name)
        observed = load_json(out / "certificates" / name)
        if reference != observed:
            raise AssertionError(f"certificate content mismatch: {name}")

    cpu1 = resource.getrusage(resource.RUSAGE_CHILDREN)
    report = {
        "commands": runs,
        "deterministic_results_equal": True,
        "compared_result_files": compared,
        "compared_certificates": len(reference_names),
        "workers": 1,
        "child_cpu_seconds": (cpu1.ru_utime + cpu1.ru_stime) - (cpu0.ru_utime + cpu0.ru_stime),
        "child_peak_rss_kib": cpu1.ru_maxrss,
        "wall_seconds": time.monotonic() - wall0,
        "timing_policy": (
            "CPU, wall-time, and RSS fields are observational and excluded from equality; "
            "all scientific fields and certificate objects are compared"
        ),
    }
    (out / "reproduction-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
