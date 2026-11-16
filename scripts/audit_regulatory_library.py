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


def validate_review_lifecycle_governance(
    *,
    sources: list[Any],
    pack: Any,
    mappings: Any,
    ob_rows: list[dict[str, str]],
    map_rows: list[dict[str, str]],
    reg_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """Audit review lifecycle governance without allowing silent or invalid approvals.

    - Preserves `proposed` records clearly marked as `proposed` without auto-approving.
    - Allows `approved` runtime records ONLY when:
      1) Matching row exists in `E4_LEGAL_REVIEW_REGISTER.csv` with `runtime_review_status == "approved"`
         and `signoff_decision` starting with `"APPROVED"` (never `PENDING_*`).
      2) Reviewer identity, review timestamp/date, and written signoff rationale are recorded
         (in register columns `reviewed_by`/`reviewer_identity`, `reviewed_at`/`signoff_date`,
         `signoff_rationale`, or on `ObligationControlMapping` fields `reviewer`, `reviewed_at`,
         `equivalence_rationale`).
      3) Item is NOT `source_unavailable` (e.g., proprietary ISO standards without licensed text).
      4) Item does NOT carry an unremediated `P0` `needs_correction` audit status.
    - Flags runtime/register status drift or invalid/pending approvals.
    """
    errors: list[str] = []
    reg_by_key = {(r["item_type"], r["item_id"]): r for r in reg_rows}
    ob_audit_by_id = {r["obligation_id"]: r for r in ob_rows}
    map_audit_by_id = {r["mapping_id"]: r for r in map_rows}

    runtime_items: list[tuple[str, str, ReviewStatus, Any]] = (
        [("regulatory_source", s.source_id, s.reviewer_status, s) for s in sources]
        + [("atomic_obligation", ob.obligation_id, ob.review_status, ob) for ob in pack.obligations]
        + [("obligation_control_mapping", m.mapping_id, m.review_status, m) for m in mappings.mappings]
    )

    status_counts: Counter[str] = Counter()
    approved_by_type: Counter[str] = Counter()
    proposed_by_type: Counter[str] = Counter()
    unremediated_p0 = 0
    source_unavailable_count = 0

    for item_type, item_id, rt_status, obj in runtime_items:
        status_counts[rt_status.value] += 1
        reg_row = reg_by_key.get((item_type, item_id))
        if not reg_row:
            errors.append(f"Missing legal review register entry for {item_type} '{item_id}'")
            continue

        e4_status = (reg_row.get("e4_verification_status") or "").strip()
        priority = (reg_row.get("priority") or "").strip().upper()
        reg_rt_status = (reg_row.get("runtime_review_status") or "").strip().lower()
        signoff = (reg_row.get("signoff_decision") or "").strip()

        if e4_status == "source_unavailable":
            source_unavailable_count += 1
        if priority == "P0" and e4_status == "needs_correction":
            unremediated_p0 += 1

        # Cross-check dedicated audit CSVs when applicable
        if item_type == "atomic_obligation":
            audit_status = (ob_audit_by_id.get(item_id, {}).get("verification_status") or "").strip()
            if audit_status and audit_status != e4_status:
                errors.append(
                    f"Obligation {item_id} status mismatch between audit CSV ('{audit_status}') and legal register ('{e4_status}')"
                )
        elif item_type == "obligation_control_mapping":
            audit_status = (map_audit_by_id.get(item_id, {}).get("audit_status") or "").strip()
            if audit_status and audit_status != e4_status:
                errors.append(
                    f"Mapping {item_id} status mismatch between audit CSV ('{audit_status}') and legal register ('{e4_status}')"
                )

        if rt_status is ReviewStatus.PROPOSED:
            proposed_by_type[item_type] += 1
            if reg_rt_status != "proposed":
                errors.append(
                    f"Register drift for {item_type} '{item_id}': runtime is 'proposed' but register says '{reg_rt_status}'"
                )
            if signoff.upper().startswith("APPROVED"):
                errors.append(
                    f"Register drift for {item_type} '{item_id}': signoff_decision='{signoff}' while runtime remains 'proposed'"
                )
        elif rt_status is ReviewStatus.APPROVED:
            approved_by_type[item_type] += 1
            if e4_status == "source_unavailable":
                errors.append(
                    f"Unauthorised approval for {item_type} '{item_id}': cannot approve item with status 'source_unavailable'"
                )
            if priority == "P0" and e4_status == "needs_correction":
                errors.append(
                    f"Unauthorised approval for {item_type} '{item_id}': cannot approve unremediated P0 'needs_correction' item"
                )
            if reg_rt_status != "approved":
                errors.append(
                    f"Silent approval rejected for {item_type} '{item_id}': register runtime_review_status is '{reg_rt_status}', expected 'approved'"
                )
            if not signoff.upper().startswith("APPROVED") or signoff.upper().startswith("PENDING"):
                errors.append(
                    f"Unauthorised approval for {item_type} '{item_id}': signoff_decision must record qualified human approval, got '{signoff}'"
                )

            reviewer_val = (
                (reg_row.get("reviewed_by") or reg_row.get("reviewer_identity") or reg_row.get("reviewer") or "").strip()
                or (getattr(obj, "reviewer", None) or "").strip()
            )
            reviewed_at_val = (
                (reg_row.get("reviewed_at") or reg_row.get("signoff_date") or "").strip()
                or (str(getattr(obj, "reviewed_at", None) or "")).strip()
            )
            rationale_val = (
                (reg_row.get("signoff_rationale") or reg_row.get("legal_rationale") or "").strip()
                or (getattr(obj, "legal_note", None) or getattr(obj, "equivalence_rationale", None) or getattr(obj, "notes", None) or "").strip()
            )
            if not reviewer_val:
                errors.append(
                    f"Invalid approval for {item_type} '{item_id}': missing reviewer identity"
                )
            if not reviewed_at_val:
                errors.append(
                    f"Invalid approval for {item_type} '{item_id}': missing review timestamp/date"
                )
            if not rationale_val:
                errors.append(
                    f"Invalid approval for {item_type} '{item_id}': missing approval rationale"
                )
        else:
            # UNREVIEWED or REJECTED must match register runtime status
            if reg_rt_status != rt_status.value:
                errors.append(
                    f"Register drift for {item_type} '{item_id}': runtime is '{rt_status.value}' but register says '{reg_rt_status}'"
                )

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "runtime_status_counts": dict(status_counts),
        "proposed_by_type": dict(proposed_by_type),
        "approved_by_type": dict(approved_by_type),
        "unremediated_p0_needs_correction": unremediated_p0,
        "source_unavailable_items": source_unavailable_count,
    }


def verify_e4_deliverables(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Verify presence, schema, row coverage, and review-lifecycle governance of the 6 E4 deliverables."""
    errors: list[str] = []
    missing = [name for name in REQUIRED_DELIVERABLES if not (repo_root / name).exists()]
    if missing:
        errors.append(f"Missing required E4 deliverables: {missing}")
        return {"passed": False, "errors": errors}

    pack = load_regulatory_pack()
    sources = load_source_register()
    mappings = load_obligation_control_mappings()
    controls = load_unified_control_library()

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

    lifecycle_report = validate_review_lifecycle_governance(
        sources=sources,
        pack=pack,
        mappings=mappings,
        ob_rows=ob_rows,
        map_rows=map_rows,
        reg_rows=reg_rows,
    )
    errors.extend(lifecycle_report["errors"])

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
        "lifecycle_governance": lifecycle_report,
    }


def run_full_audit() -> dict[str, Any]:
    """Run structural checks, synthetic scenarios, and deliverable assurance verification."""
    deliverables_report = verify_e4_deliverables()
    validation_report = validate_regulatory_library(forbid_auto_approved=False)
    synthetic_suite = run_synthetic_evaluation_suite()
    overall_passed = bool(
        validation_report["valid"]
        and synthetic_suite["all_passed"]
        and deliverables_report["passed"]
    )
    approved_total = sum(
        deliverables_report.get("lifecycle_governance", {})
        .get("approved_by_type", {})
        .values()
    )
    return {
        "overall_structural_audit_passed": overall_passed,
        "legal_review_status": (
            "pending_expert_human_review"
            if approved_total == 0
            else "partial_human_signoff_with_lineage"
        ),
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
        approved_count = sum(
            deliv.get("lifecycle_governance", {}).get("approved_by_type", {}).values()
        )
        print(f"E4 Structural Validation: {passed_n}/{len(checks)} checks passed (valid={report['overall_structural_audit_passed']})")
        print(f"Legal Review Status: {report['legal_review_status']} (human_approved={approved_count})")
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
