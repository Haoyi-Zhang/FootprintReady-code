#!/usr/bin/env python3
"""Validate the shipped bibliography audit without network access.

This checks completeness, key/locator uniqueness, locator syntax, and truthful
row-level bookkeeping.  It does not claim that syntax checks replace scholarly
source inspection; the recorded read-depth field remains the authority for what
was actually inspected.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / "bibliography_audit.csv"
DOI = re.compile(r"^https://doi\.org/10\.\d{4,9}/\S+$")
ARXIV = re.compile(r"^https://arxiv\.org/abs/(?:\d{4}\.\d{4,5}|[A-Za-z.-]+/\d{7})$")
ALLOWED_LOCATOR_HOSTS = {
    "doi.org",
    "arxiv.org",
    "dspace.mit.edu",
    "accelergy.mit.edu",
    "www.usenix.org",
}
PINNED_METADATA = {
    "piperench": {
        "title": "PipeRench: A Reconfigurable Architecture and Compiler",
        "first_author_or_org": "Seth C. Goldstein",
        "year": "2000",
        "venue_or_record": "Computer 33(4):70-77",
        "stable_locator_if_audited": "https://doi.org/10.1109/2.839324",
    },
    "glow": {
        "title": "Glow: Graph Lowering Compiler Techniques for Neural Networks",
        "first_author_or_org": "Nadav Rotem",
        "year": "2018",
        "venue_or_record": "arXiv:1805.00907",
        "stable_locator_if_audited": "https://arxiv.org/abs/1805.00907",
    },
    "tiramisu": {
        "title": "Tiramisu: A Polyhedral Compiler for Expressing Fast and Portable Code",
        "first_author_or_org": "Riyadh Baghdadi",
        "year": "2019",
        "venue_or_record": "2019 IEEE/ACM International Symposium on Code Generation and Optimization (CGO), pp. 193-205",
        "stable_locator_if_audited": "https://doi.org/10.1109/CGO.2019.8661197",
    },
}


def verify() -> dict:
    with AUDIT.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    required = {
        "bibtex_key", "title", "first_author_or_org", "year",
        "venue_or_record", "stable_locator_if_audited",
        "cited_in_manuscript", "read_depth", "manuscript_role",
        "bytes_redistributed",
    }
    if not rows or set(rows[0]) != required:
        raise ValueError("bibliography audit schema")
    if len(rows) != 67:
        raise ValueError(f"expected 67 audited references, found {len(rows)}")

    keys = [row["bibtex_key"] for row in rows]
    titles = [row["title"] for row in rows]
    locators = [row["stable_locator_if_audited"] for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate bibliography key")
    if len(set(titles)) != len(titles):
        raise ValueError("duplicate bibliography title")
    if len(set(locators)) != len(locators):
        raise ValueError("duplicate stable locator")

    by_key = {row["bibtex_key"]: row for row in rows}
    for key, expected in PINNED_METADATA.items():
        if key not in by_key:
            raise ValueError(f"missing pinned bibliography row: {key}")
        for field, value in expected.items():
            if by_key[key][field] != value:
                raise ValueError(f"pinned metadata mismatch for {key}: {field}")

    for row in rows:
        if not all(row[field].strip() for field in required):
            raise ValueError(f"missing audit field for {row.get('bibtex_key', '<unknown>')}")
        if row["cited_in_manuscript"] != "yes":
            raise ValueError(f"uncited bibliography row: {row['bibtex_key']}")
        if row["bytes_redistributed"] != "no":
            raise ValueError(f"unexpected redistributed source bytes: {row['bibtex_key']}")
        locator = row["stable_locator_if_audited"]
        if not locator.startswith("https://"):
            raise ValueError(f"non-HTTPS locator: {row['bibtex_key']}")
        host = (urlsplit(locator).hostname or "").casefold()
        if host not in ALLOWED_LOCATOR_HOSTS:
            raise ValueError(f"unrecognized locator host: {row['bibtex_key']}")
        if host == "doi.org" and not DOI.fullmatch(locator):
            raise ValueError(f"malformed DOI locator: {row['bibtex_key']}")
        if host == "arxiv.org":
            match = ARXIV.fullmatch(locator)
            if not match:
                raise ValueError(f"malformed arXiv locator: {row['bibtex_key']}")
            record = row["venue_or_record"]
            if record.startswith("arXiv:") and record[6:] != locator.rsplit("/", 1)[-1]:
                raise ValueError(f"arXiv record/locator mismatch: {row['bibtex_key']}")
        if not re.fullmatch(r"(?:19|20)\d{2}", row["year"]):
            raise ValueError(f"invalid publication year: {row['bibtex_key']}")

    return {
        "references": len(rows),
        "unique_keys": len(set(keys)),
        "unique_titles": len(set(titles)),
        "unique_stable_locators": len(set(locators)),
        "doi_locators": sum("doi.org/" in item for item in locators),
        "arxiv_locators": sum("arxiv.org/" in item for item in locators),
        "official_or_other_locators": sum(
            "doi.org/" not in item and "arxiv.org/" not in item for item in locators
        ),
        "all_marked_cited": True,
        "source_bytes_redistributed": False,
        "pinned_first_party_records": sorted(PINNED_METADATA),
        "offline_gate_not_live_source_verification": True,
    }


if __name__ == "__main__":
    print(verify())
