"""Compare generated evidence JSON with a reference ledger without sharing it.

The ingestion container never sees the reference directory. This evaluator runs
on the host after candidate files have passed standalone schema validation.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

FILES = {
    "people.json": "people",
    "sources.json": "sources",
    "claims.json": "claims",
}


def _load(directory: Path, filename: str, key: str) -> list[dict[str, Any]]:
    raw = json.loads((directory / filename).read_text(encoding="utf-8"))
    return raw[key]


def _ids(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row["id"]) for row in rows}


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def compare(candidate_dir: Path, reference_dir: Path) -> dict[str, Any]:
    report: dict[str, Any] = {"exact_json": True, "files": {}}

    for filename, key in FILES.items():
        candidate = _load(candidate_dir, filename, key)
        reference = _load(reference_dir, filename, key)
        candidate_ids = _ids(candidate)
        reference_ids = _ids(reference)
        exact = candidate == reference
        report["exact_json"] = report["exact_json"] and exact
        report["files"][filename] = {
            "exact": exact,
            "candidate_count": len(candidate),
            "reference_count": len(reference),
            "missing_ids": sorted(reference_ids - candidate_ids),
            "extra_ids": sorted(candidate_ids - reference_ids),
        }

    candidate_claims = _load(candidate_dir, "claims.json", "claims")
    reference_claims = _load(reference_dir, "claims.json", "claims")
    candidate_by_support = {row["support"]: row for row in candidate_claims}
    reference_by_support = {row["support"]: row for row in reference_claims}
    common_support = candidate_by_support.keys() & reference_by_support.keys()
    semantic_fields = (
        "source",
        "locator",
        "stated_by",
        "stated_at",
        "kind",
        "subject",
        "predicate",
        "value",
    )
    mismatches = []
    for support in sorted(common_support):
        candidate = candidate_by_support[support]
        reference = reference_by_support[support]
        changed = {
            field: {"candidate": candidate.get(field), "reference": reference.get(field)}
            for field in semantic_fields
            if candidate.get(field) != reference.get(field)
        }
        if changed:
            mismatches.append(
                {
                    "support": support[:120],
                    "fields": changed,
                }
            )

    report["claim_support"] = {
        "matched": len(common_support),
        "missing": len(reference_by_support.keys() - candidate_by_support.keys()),
        "extra": len(candidate_by_support.keys() - reference_by_support.keys()),
        "semantic_mismatch_count": len(mismatches),
        "semantic_mismatches": mismatches,
    }

    candidate_people = _load(candidate_dir, "people.json", "people")
    reference_people = _load(reference_dir, "people.json", "people")
    candidate_names = {row["name"] for row in candidate_people}
    reference_names = {row["name"] for row in reference_people}
    report["people_by_name"] = {
        "matched": len(candidate_names & reference_names),
        "missing": sorted(reference_names - candidate_names),
        "extra": sorted(candidate_names - reference_names),
    }

    candidate_sources = _load(candidate_dir, "sources.json", "sources")
    reference_sources = _load(reference_dir, "sources.json", "sources")
    candidate_files = {row["file"] for row in candidate_sources if row["file"]}
    reference_files = {row["file"] for row in reference_sources if row["file"]}
    report["present_sources_by_file"] = {
        "matched": len(candidate_files & reference_files),
        "missing": sorted(reference_files - candidate_files),
        "extra": sorted(candidate_files - reference_files),
    }

    candidate_normalised = {_normalise(row["support"]) for row in candidate_claims}
    reference_normalised = {_normalise(row["support"]) for row in reference_claims}
    exact_normalised = candidate_normalised & reference_normalised
    covered = {
        support
        for support in reference_normalised
        if any(
            support in candidate or candidate in support
            for candidate in candidate_normalised
        )
    }
    report["evidence_coverage"] = {
        "reference_support_count": len(reference_normalised),
        "candidate_support_count": len(candidate_normalised),
        "exact_normalised": len(exact_normalised),
        "covered_by_exact_or_containment": len(covered),
        "missing_support": sorted(reference_normalised - covered),
    }
    return report


def print_report(report: dict[str, Any]) -> None:
    print("\nReference comparison")
    print(f"  exact JSON: {report['exact_json']}")
    for filename, row in report["files"].items():
        print(
            f"  {filename}: {row['candidate_count']} generated / "
            f"{row['reference_count']} reference; "
            f"missing ids={len(row['missing_ids'])}, extra ids={len(row['extra_ids'])}"
        )
    claims = report["claim_support"]
    print(
        "  claim support: "
        f"matched={claims['matched']}, missing={claims['missing']}, "
        f"extra={claims['extra']}, semantic mismatches={claims['semantic_mismatch_count']}"
    )
    people = report["people_by_name"]
    print(
        f"  people by name: matched={people['matched']}, "
        f"missing={len(people['missing'])}, extra={len(people['extra'])}"
    )
    sources = report["present_sources_by_file"]
    print(
        f"  present sources by file: matched={sources['matched']}, "
        f"missing={len(sources['missing'])}, extra={len(sources['extra'])}"
    )
    coverage = report["evidence_coverage"]
    print(
        "  textual evidence coverage: "
        f"exact normalized={coverage['exact_normalised']}/"
        f"{coverage['reference_support_count']}, exact-or-contained="
        f"{coverage['covered_by_exact_or_containment']}/"
        f"{coverage['reference_support_count']}"
    )
