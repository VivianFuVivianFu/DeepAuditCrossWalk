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
    assert diag["duplicate_obligation_control_pairs"] == []
    assert "CTRL-AI-GOV-ACCOUNTABILITY" in diag["shared_controls"]
    assert len(diag["shared_controls"]["CTRL-AI-GOV-ACCOUNTABILITY"]) == 5
    assert set(diag["proprietary_unavailable_sources"]) == {
        "ISO-42001",
        "ISO-23894",
        "ISO-27001",
    }
    assert len(diag["broad_or_guidance_full_mappings"]) == 4
    assert diag["non_equivalent_with_mapped_facets"] == []


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
    assert len(ob_rows) == 46
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
    assert len(reg_rows) >= 17 + 46 + 55
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


def _load_audit_cli_module():
    import importlib.util

    cli_path = ROOT / "scripts" / "audit_regulatory_library.py"
    spec = importlib.util.spec_from_file_location("audit_regulatory_library", cli_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_e4_review_lifecycle_governance_allows_qualified_human_approval_and_blocks_invalid():
    mod = _load_audit_cli_module()
    sources = load_source_register()
    pack = load_regulatory_pack()
    mappings = load_obligation_control_mappings()

    with (ROOT / "E4_ATOMIC_OBLIGATION_AUDIT.csv").open(encoding="utf-8", newline="") as f:
        ob_rows = list(csv.DictReader(f))
    with (ROOT / "E4_CONTROL_MAPPING_AUDIT.csv").open(encoding="utf-8", newline="") as f:
        map_rows = list(csv.DictReader(f))
    with (ROOT / "E4_LEGAL_REVIEW_REGISTER.csv").open(encoding="utf-8", newline="") as f:
        reg_rows = list(csv.DictReader(f))

    # Baseline: all proposed passes with 0 approved
    baseline = mod.validate_review_lifecycle_governance(
        sources=sources,
        pack=pack,
        mappings=mappings,
        ob_rows=ob_rows,
        map_rows=map_rows,
        reg_rows=reg_rows,
    )
    assert baseline["passed"] is True
    assert sum(baseline["approved_by_type"].values()) == 0

    # 1. Silent runtime promotion without legal register signoff -> rejected
    silent_map = mappings.mappings[0].model_copy(
        update={
            "review_status": ReviewStatus.APPROVED,
            "reviewer": "legal.lead",
            "reviewed_at": "2026-11-16T00:00:00Z",
        }
    )
    silent_pack_maps = mappings.model_copy(update={"mappings": [silent_map, *mappings.mappings[1:]]})
    silent_res = mod.validate_review_lifecycle_governance(
        sources=sources,
        pack=pack,
        mappings=silent_pack_maps,
        ob_rows=ob_rows,
        map_rows=map_rows,
        reg_rows=reg_rows,
    )
    assert silent_res["passed"] is False
    assert any("Silent approval rejected" in e for e in silent_res["errors"])

    # 2. Qualified human approval on verified non-P0 mapping with matching register lineage -> accepted
    target_id = next(
        r["item_id"]
        for r in reg_rows
        if r["item_type"] == "obligation_control_mapping"
        and r["e4_verification_status"] == "verified_against_source"
    )
    approved_mappings = mappings.model_copy(
        update={
            "mappings": [
                m.model_copy(
                    update={
                        "review_status": ReviewStatus.APPROVED,
                        "reviewer": "senior.afs.counsel@bank.au",
                        "reviewed_at": "2026-11-16T00:00:00Z",
                    }
                )
                if m.mapping_id == target_id
                else m
                for m in mappings.mappings
            ]
        }
    )
    approved_reg = [
        {
            **r,
            "runtime_review_status": "approved",
            "signoff_decision": "APPROVED_BY_LEGAL",
        }
        if r["item_type"] == "obligation_control_mapping" and r["item_id"] == target_id
        else r
        for r in reg_rows
    ]
    ok_res = mod.validate_review_lifecycle_governance(
        sources=sources,
        pack=pack,
        mappings=approved_mappings,
        ob_rows=ob_rows,
        map_rows=map_rows,
        reg_rows=approved_reg,
    )
    assert ok_res["passed"] is True, ok_res["errors"]
    assert ok_res["approved_by_type"]["obligation_control_mapping"] == 1

    # 3. Attempting to approve ISO source_unavailable item even with register approval -> rejected
    iso_ob_id = "ISO42001-AIMS-ORG"
    iso_pack = pack.model_copy(
        update={
            "obligations": [
                o.model_copy(update={"review_status": ReviewStatus.APPROVED, "legal_note": "Tried"})
                if o.obligation_id == iso_ob_id
                else o
                for o in pack.obligations
            ]
        }
    )
    iso_reg = [
        {
            **r,
            "runtime_review_status": "approved",
            "signoff_decision": "APPROVED_BY_LEGAL",
            "reviewed_by": "iso.auditor@bank.au",
            "reviewed_at": "2026-11-16",
            "signoff_rationale": "Attempted without licensed text",
        }
        if r["item_type"] == "atomic_obligation" and r["item_id"] == iso_ob_id
        else r
        for r in reg_rows
    ]
    iso_res = mod.validate_review_lifecycle_governance(
        sources=sources,
        pack=iso_pack,
        mappings=mappings,
        ob_rows=ob_rows,
        map_rows=map_rows,
        reg_rows=iso_reg,
    )
    assert iso_res["passed"] is False
    assert any("source_unavailable" in e for e in iso_res["errors"])

    # 4. Attempting to approve unremediated P0 needs_correction obligation even with register approval -> rejected
    p0_ob_id = next(
        r["item_id"]
        for r in reg_rows
        if r["item_type"] == "atomic_obligation"
        and r["priority"] == "P0"
        and r["e4_verification_status"] == "needs_correction"
    )
    p0_pack = pack.model_copy(
        update={
            "obligations": [
                o.model_copy(update={"review_status": ReviewStatus.APPROVED, "legal_note": "Tried"})
                if o.obligation_id == p0_ob_id
                else o
                for o in pack.obligations
            ]
        }
    )
    p0_reg = [
        {
            **r,
            "runtime_review_status": "approved",
            "signoff_decision": "APPROVED_BY_LEGAL",
            "reviewed_by": "counsel@bank.au",
            "reviewed_at": "2026-11-16",
            "signoff_rationale": "Premature approval before P0 remediation",
        }
        if r["item_type"] == "atomic_obligation" and r["item_id"] == p0_ob_id
        else r
        for r in reg_rows
    ]
    p0_res = mod.validate_review_lifecycle_governance(
        sources=sources,
        pack=p0_pack,
        mappings=mappings,
        ob_rows=ob_rows,
        map_rows=map_rows,
        reg_rows=p0_reg,
    )
    assert p0_res["passed"] is False
    assert any("unremediated P0" in e for e in p0_res["errors"])
