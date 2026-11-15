"""E4 automated regulatory library structural validation & deliverable assurance tests."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

from banking_crosswalk.catalog import (
    load_obligation_control_mappings,
    load_regulatory_pack,
    load_source_register,
    load_unified_control_library,
)
from banking_crosswalk.models import Authority, MappingRelationship, ReviewStatus
from banking_crosswalk.validation import validate_regulatory_library


ROOT = Path(__file__).resolve().parents[2]
VALID_E4_STATUSES = {
    "verified_against_source",
    "needs_correction",
    "incomplete",
    "source_unavailable",
    "requires_legal_interpretation",
}


def test_e4_twelve_structural_checks_and_diagnostics():
    report = validate_regulatory_library()
    assert report["valid"] is True
    assert report["legal_review_status"] == "pending_expert_human_review"
    assert len(report["checks"]) == 12
    for check_name, result in report["checks"].items():
        assert result["passed"] is True, f"{check_name} failed: {result['errors']}"

    diag = report["content_assurance_diagnostics"]
    assert diag["human_legal_review_required"] is True
    assert diag["duplicate_obligation_control_pairs"] == [
        {
            "obligation_id": "ISO23894-AI-RISK-PROCESS",
            "control_id": "CTRL-RISK-FRAMEWORK",
            "count": 2,
        }
    ]
    assert "CTRL-AI-GOV-ACCOUNTABILITY" in diag["shared_controls"]
    assert len(diag["shared_controls"]["CTRL-AI-GOV-ACCOUNTABILITY"]) == 5
    assert set(diag["proprietary_unavailable_sources"]) == {
        "ISO-42001",
        "ISO-23894",
        "ISO-27001",
    }
    assert len(diag["broad_or_guidance_full_mappings"]) == 9
    assert len(diag["non_equivalent_with_mapped_facets"]) == 3


def test_e4_structural_checks_detect_mapping_and_source_regressions():
    pack = load_regulatory_pack()
    sources = load_source_register()
    controls = load_unified_control_library()
    mappings = load_obligation_control_mappings()

    # Corrupt a 'full' mapping by leaving an unmapped facet and dropping from mapped_facets
    bad_mapping = mappings.mappings[0].model_copy(
        update={
            "mapping_relationship": MappingRelationship.FULL,
            "mapped_facets": mappings.mappings[0].mapped_facets[:-1],
            "unmapped_obligation_facets": [mappings.mappings[0].mapped_facets[-1]],
        }
    )
    broken_mappings = mappings.model_copy(
        update={"mappings": [bad_mapping, *mappings.mappings[1:]]}
    )

    # Corrupt a source register entry with insecure URL and mismatched authority
    bad_source = sources[0].model_copy(
        update={
            "source_url": "http://insecure.legislation.gov.au/test",
            "authority": Authority.VOLUNTARY,
        }
    )
    broken_sources = [bad_source, *sources[1:]]

    report = validate_regulatory_library(
        pack=pack,
        source_register=broken_sources,
        control_library=controls,
        mapping_catalogue=broken_mappings,
    )
    assert report["valid"] is False
    assert not report["checks"]["mapping_facet_and_relationship_consistency"]["passed"]
    assert not report["checks"]["source_register_metadata_integrity"]["passed"]


def test_e4_deliverables_complete_and_no_auto_approvals():
    required_files = [
        "E4_REGULATORY_SOURCE_VERIFICATION.md",
        "E4_ATOMIC_OBLIGATION_AUDIT.csv",
        "E4_CONTROL_MAPPING_AUDIT.csv",
        "E4_REGULATORY_COMPLETENESS_MATRIX.md",
        "E4_PRIORITISED_CORRECTIONS.md",
        "E4_LEGAL_REVIEW_REGISTER.csv",
    ]
    for name in required_files:
        path = ROOT / name
        assert path.exists(), f"Missing E4 deliverable: {name}"
        assert path.stat().st_size > 0, f"Empty E4 deliverable: {name}"

    sources = load_source_register()
    pack = load_regulatory_pack()
    mappings = load_obligation_control_mappings()

    # Confirm zero runtime records were silently promoted to approved
    assert all(s.reviewer_status is ReviewStatus.PROPOSED for s in sources)
    assert all(o.review_status is ReviewStatus.PROPOSED for o in pack.obligations)
    assert all(m.review_status is ReviewStatus.PROPOSED for m in mappings.mappings)

    with (ROOT / "E4_ATOMIC_OBLIGATION_AUDIT.csv").open(encoding="utf-8", newline="") as f:
        ob_rows = list(csv.DictReader(f))
    assert len(ob_rows) == 45
    assert {r["obligation_id"] for r in ob_rows} == {o.obligation_id for o in pack.obligations}
    assert all(r["verification_status"] in VALID_E4_STATUSES for r in ob_rows)
    iso_rows = [r for r in ob_rows if r["source"].startswith("ISO-")]
    assert len(iso_rows) == 4
    assert all(r["verification_status"] == "source_unavailable" for r in iso_rows)

    with (ROOT / "E4_CONTROL_MAPPING_AUDIT.csv").open(encoding="utf-8", newline="") as f:
        map_rows = list(csv.DictReader(f))
    assert len(map_rows) == 55
    assert {r["mapping_id"] for r in map_rows} == {m.mapping_id for m in mappings.mappings}
    assert all(r["audit_status"] in VALID_E4_STATUSES for r in map_rows)

    with (ROOT / "E4_LEGAL_REVIEW_REGISTER.csv").open(encoding="utf-8", newline="") as f:
        reg_rows = list(csv.DictReader(f))
    assert len(reg_rows) >= 17 + 45 + 55
    assert all(r["e4_verification_status"] in VALID_E4_STATUSES for r in reg_rows)
    assert all(r["signoff_decision"].startswith("PENDING_") for r in reg_rows)


def test_e4_executable_audit_cli_runs_cleanly():
    cli_path = ROOT / "scripts" / "audit_regulatory_library.py"
    assert cli_path.exists()
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert '"overall_structural_audit_passed": true' in proc.stdout
