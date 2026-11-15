"""Executable E4 regulatory library structural validation and QA audit CLI.

Separates:
  1. Automatically verified structural properties (12 deterministic checks).
  2. Content assurance diagnostics (duplicate pairs, shared controls, full/guidance
     over-broadening risks, non-equivalent facet leakage, source availability).
  3. Primary-source and human legal review deliverables (E4_* files at repo root).

Never auto-approves proposed obligations or control mappings.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from banking_crosswalk.catalog import (
    load_obligation_control_mappings,
    load_regulatory_pack,
    load_source_register,
    load_unified_control_library,
)
from banking_crosswalk.models import ReviewStatus
from banking_crosswalk.validation import (
    run_synthetic_evaluation_suite,
    validate_regulatory_library,
)

VALID_E4_STATUSES = {
    "verified_against_source",
    "needs_correction",
    "incomplete",
    "source_unavailable",
    "requires_legal_interpretation",
}

REQUIRED_DELIVERABLES = [
    "E4_REGULATORY_SOURCE_VERIFICATION.md",
    "E4_ATOMIC_OBLIGATION_AUDIT.csv",
    "E4_CONTROL_MAPPING_AUDIT.csv",
    "E4_REGULATORY_COMPLETENESS_MATRIX.md",
    "E4_PRIORITISED_CORRECTIONS.md",
    "E4_LEGAL_REVIEW_REGISTER.csv",
]


def verify_e4_deliverables(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Verify presence, schema, row coverage, and status integrity of the 6 E4 deliverables."""
    errors: list[str] = []
    missing = [name for name in REQUIRED_DELIVERABLES if not (repo_root / name).exists()]
    if missing:
        errors.append(f"Missing required E4 deliverables: {missing}")
        return {"passed": False, "errors": errors}

    pack = load_regulatory_pack()
    sources = load_source_register()
    mappings = load_obligation_control_mappings()
    controls = load_unified_control_library()

    # Check zero auto-approvals in runtime data
    non_proposed_obs = [
        ob.obligation_id for ob in pack.obligations if ob.review_status is not ReviewStatus.PROPOSED
    ]
    non_proposed_maps = [
        m.mapping_id for m in mappings.mappings if m.review_status is not ReviewStatus.PROPOSED
    ]
    non_proposed_srcs = [
        s.source_id for s in sources if s.reviewer_status is not ReviewStatus.PROPOSED
    ]
    if non_proposed_obs or non_proposed_maps or non_proposed_srcs:
        errors.append(
            "Runtime library contains non-proposed records without human sign-off: "
            f"sources={non_proposed_srcs}, obligations={non_proposed_obs}, mappings={non_proposed_maps}"
        )

    # Obligation audit CSV
    expected_ob_cols = [
        "obligation_id",
        "source",
        "provision",
        "verification_status",
        "findings",
        "suggested_correction",
        "evidence_url",
        "reviewer_required",
    ]
    with (repo_root / "E4_ATOMIC_OBLIGATION_AUDIT.csv").open(encoding="utf-8", newline="") as f:
        ob_reader = csv.DictReader(f)
        if ob_reader.fieldnames != expected_ob_cols:
            errors.append(
                f"E4_ATOMIC_OBLIGATION_AUDIT.csv columns mismatch: {ob_reader.fieldnames}"
            )
        ob_rows = list(ob_reader)

    if {r["obligation_id"] for r in ob_rows} != {o.obligation_id for o in pack.obligations}:
        errors.append("E4_ATOMIC_OBLIGATION_AUDIT.csv obligation_id set mismatch")
    if len(ob_rows) != len(pack.obligations):
        errors.append(
            f"E4_ATOMIC_OBLIGATION_AUDIT.csv row count {len(ob_rows)} != {len(pack.obligations)}"
        )
    bad_ob_statuses = {
        r["verification_status"]
        for r in ob_rows
        if r["verification_status"] not in VALID_E4_STATUSES
    }
    if bad_ob_statuses:
        errors.append(f"Invalid obligation verification_status values: {bad_ob_statuses}")

    # Mapping audit CSV
    with (repo_root / "E4_CONTROL_MAPPING_AUDIT.csv").open(encoding="utf-8", newline="") as f:
        map_rows = list(csv.DictReader(f))
    if {r["mapping_id"] for r in map_rows} != {m.mapping_id for m in mappings.mappings}:
        errors.append("E4_CONTROL_MAPPING_AUDIT.csv mapping_id set mismatch")
    bad_map_statuses = {
        r["audit_status"] for r in map_rows if r["audit_status"] not in VALID_E4_STATUSES
    }
    if bad_map_statuses:
        errors.append(f"Invalid mapping audit_status values: {bad_map_statuses}")

    # Legal review register CSV
    with (repo_root / "E4_LEGAL_REVIEW_REGISTER.csv").open(encoding="utf-8", newline="") as f:
        reg_rows = list(csv.DictReader(f))
    reg_items_by_type = {}
    for row in reg_rows:
        reg_items_by_type.setdefault(row["item_type"], set()).add(row["item_id"])
    if reg_items_by_type.get("regulatory_source") != {s.source_id for s in sources}:
        errors.append("E4_LEGAL_REVIEW_REGISTER.csv missing regulatory_source coverage")
    if reg_items_by_type.get("atomic_obligation") != {o.obligation_id for o in pack.obligations}:
        errors.append("E4_LEGAL_REVIEW_REGISTER.csv missing atomic_obligation coverage")
    if reg_items_by_type.get("obligation_control_mapping") != {m.mapping_id for m in mappings.mappings}:
        errors.append("E4_LEGAL_REVIEW_REGISTER.csv missing obligation_control_mapping coverage")
    bad_reg_statuses = {
        r["e4_verification_status"]
        for r in reg_rows
        if r["e4_verification_status"] not in VALID_E4_STATUSES
    }
    if bad_reg_statuses:
        errors.append(f"Invalid legal register statuses: {bad_reg_statuses}")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "counts": {
            "sources": len(sources),
            "obligations": len(pack.obligations),
            "controls": len(controls.controls),
            "mappings": len(mappings.mappings),
            "obligation_audit_rows": len(ob_rows),
            "mapping_audit_rows": len(map_rows),
            "legal_register_rows": len(reg_rows),
        },
        "obligation_status_counts": dict(Counter(r["verification_status"] for r in ob_rows)),
        "mapping_status_counts": dict(Counter(r["audit_status"] for r in map_rows)),
        "register_status_counts": dict(Counter(r["e4_verification_status"] for r in reg_rows)),
    }


def run_full_audit() -> dict[str, Any]:
    """Run structural checks, synthetic scenarios, and deliverable assurance verification."""
    validation_report = validate_regulatory_library()
    synthetic_suite = run_synthetic_evaluation_suite()
    deliverables_report = verify_e4_deliverables()
    overall_passed = bool(
        validation_report["valid"]
        and synthetic_suite["all_passed"]
        and deliverables_report["passed"]
    )
    return {
        "overall_structural_audit_passed": overall_passed,
        "legal_review_status": validation_report["legal_review_status"],
        "automated_structural_checks": validation_report["checks"],
        "content_assurance_diagnostics": validation_report["content_assurance_diagnostics"],
        "synthetic_evaluation_summary": {
            "all_passed": synthetic_suite["all_passed"],
            "scenario_count": synthetic_suite["scenario_count"],
        },
        "e4_deliverables_verification": deliverables_report,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run E4 Regulatory Library structural validation and audit deliverables check."
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    args = parser.parse_args(argv)

    report = run_full_audit()
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        checks = report["automated_structural_checks"]
        passed_n = sum(1 for c in checks.values() if c["passed"])
        diag = report["content_assurance_diagnostics"]
        deliv = report["e4_deliverables_verification"]
        print(f"E4 Structural Validation: {passed_n}/{len(checks)} checks passed (valid={report['overall_structural_audit_passed']})")
        print(f"Legal Review Status: {report['legal_review_status']} (zero auto-approvals)")
        print(f"Synthetic Scenarios: {report['synthetic_evaluation_summary']}")
        print(
            "Diagnostics: "
            f"duplicate_pairs={len(diag['duplicate_obligation_control_pairs'])}, "
            f"shared_controls={len(diag['shared_controls'])}, "
            f"broad_guidance_full={len(diag['broad_or_guidance_full_mappings'])}, "
            f"non_eq_mapped={len(diag['non_equivalent_with_mapped_facets'])}, "
            f"iso_unavailable={len(diag['proprietary_unavailable_sources'])}"
        )
        print(f"Deliverables Verification: passed={deliv['passed']}, counts={deliv.get('counts')}")
        print(f"Obligation Audit Statuses: {deliv.get('obligation_status_counts')}")
        print(f"Mapping Audit Statuses: {deliv.get('mapping_status_counts')}")
    return 0 if report["overall_structural_audit_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
