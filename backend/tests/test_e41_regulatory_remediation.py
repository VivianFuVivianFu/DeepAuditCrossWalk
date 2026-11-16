"""E4.1 Regulatory Accuracy & Control Mapping Remediation regression tests."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from banking_crosswalk.applicability import decide_applicability
from banking_crosswalk.catalog import (
    load_obligation_control_mappings,
    load_regulatory_pack,
    load_source_register,
    load_unified_control_library,
)
from banking_crosswalk.models import (
    ApplicabilityStatus,
    BankingUseCase,
    ClauseControlMapping,
    ClauseReviewStatus,
    EnterpriseBaseline,
    EnterpriseClause,
    EnterprisePolicy,
    MappingRelationship,
    ReconciliationDecisionStatus,
    ReconciliationRelationship,
    ReviewStatus,
)
from banking_crosswalk.reconciliation import (
    compose_effective_assessment_baseline,
    evaluate_reconciliation_staleness,
    generate_reconciliation_candidates,
    rank_reconciliation_candidates_for_clause,
    validate_candidate_relationship,
)
from banking_crosswalk.validation import validate_regulatory_library

ROOT = Path(__file__).resolve().parents[2]


def test_e41_app11_3_technical_and_organisational_measures_separate_from_retention():
    pack = load_regulatory_pack()
    mappings = load_obligation_control_mappings()
    controls = load_unified_control_library()

    app11 = next(o for o in pack.obligations if o.obligation_id == "AU-PRIV-APP11-SECURITY")
    assert "APP 11.1–11.3" in app11.provision
    assert "C2024A00128" in (app11.exact_clause_reference or "")
    assert "11 Dec 2024" in (app11.concise_obligation_summary or "")
    assert "technical and organisational measures" in (app11.concise_obligation_summary or "").lower()
    assert app11.effective_from == date(2024, 12, 11)
    assert app11.coverage_facets == [
        "technical_security_measures_implemented",
        "organisational_security_measures_implemented",
        "retention_schedule_applied",
        "destruction_or_deidentification_verified",
    ]
    assert app11.review_status is ReviewStatus.PROPOSED

    ctrl = next(c for c in controls.controls if c.control_id == "CTRL-PRIV-SECURITY-RETENTION")
    assert "APP 11.1/11.3" in ctrl.title

    cross1 = next(m for m in mappings.mappings if m.mapping_id == "MAP-CROSS-001")
    assert cross1.mapping_relationship is MappingRelationship.PARTIAL
    assert set(cross1.mapped_facets) == {
        "technical_security_measures_implemented",
        "organisational_security_measures_implemented",
    }
    assert set(cross1.unmapped_obligation_facets) == {
        "retention_schedule_applied",
        "destruction_or_deidentification_verified",
    }


def test_e41_asic_rg271_instrument_separation():
    pack = load_regulatory_pack()
    sources = {s.source_id: s for s in load_source_register()}

    rg_src = sources["ASIC-RG271"]
    assert "2020/98" in (rg_src.notes or "")
    assert "2022/205" in (rg_src.notes or "")

    complaint_ob = next(o for o in pack.obligations if o.obligation_id == "AU-ASIC-RG271-COMPLAINT")
    assert "271.51" in complaint_ob.provision
    assert "guidance" in (complaint_ob.concise_obligation_summary or "").lower()
    assert "271.27" in (complaint_ob.concise_obligation_summary or "")
    assert "271.56" in (complaint_ob.concise_obligation_summary or "")

    systemic_ob = next(o for o in pack.obligations if o.obligation_id == "AU-ASIC-RG271-SYSTEMIC")
    assert "271.118–271.120" in systemic_ob.provision
    assert "271.165" in systemic_ob.provision
    assert "2022/205" in (systemic_ob.concise_obligation_summary or "")
    assert "271.116 concerns credit hardship" in (systemic_ob.concise_obligation_summary or "")


def test_e41_apra_cps220_citation_and_paragraphs():
    sources = {s.source_id: s for s in load_source_register()}
    pack = load_regulatory_pack()

    cps220_src = sources["APRA-CPS220"]
    assert "F2019L00669" in (cps220_src.version_id or "")
    assert "F2017L00695" not in (cps220_src.version_id or "")
    assert "F2014L01822" not in (cps220_src.version_id or "")
    assert cps220_src.effective_from == date(2019, 7, 1)
    assert cps220_src.source_url == "https://www.legislation.gov.au/F2019L00669/latest/details"
    cps220_pack_src = next(s for s in pack.sources if s.source_id == "APRA-CPS220")
    assert any(h.get("version_id") == "APRA-CPS220-2015-01" for h in cps220_pack_src.historical_versions)

    review_ob = next(o for o in pack.obligations if o.obligation_id == "AU-APRA-CPS220-REVIEW")
    assert "38–51" in review_ob.provision
    assert "Attachment A" in review_ob.provision
    assert review_ob.effective_from == date(2019, 7, 1)


def test_e41_eu_ai_act_timelines_art50_split_and_as_of_date_applicability():
    pack = load_regulatory_pack()
    sources = {s.source_id: s for s in load_source_register()}
    mappings = {m.mapping_id: m for m in load_obligation_control_mappings().mappings}

    eu_src = sources["EU-AI-ACT"]
    assert "CELEX:32026R1744" in (eu_src.version_id or "")
    assert "2 December 2027" in (eu_src.notes or "")
    assert "2 August 2028" in (eu_src.notes or "")
    assert "Article 50 transparency 2 Aug 2026" in (eu_src.notes or "")

    high_risk = next(o for o in pack.obligations if o.obligation_id == "EU-AIA-ART2-HIGH-RISK")
    art4_5 = next(o for o in pack.obligations if o.obligation_id == "EU-AIA-ART4-5-PROHIBITED-LITERACY")
    deployer = next(o for o in pack.obligations if o.obligation_id == "EU-AIA-ART26-27-DEPLOYER-CREDIT")
    art50 = next(o for o in pack.obligations if o.obligation_id == "EU-AIA-ART50-TRANSPARENCY")

    assert art4_5.effective_from == date(2025, 2, 2)
    assert art50.effective_from == date(2026, 8, 2)
    assert high_risk.effective_from == date(2027, 12, 2)
    assert deployer.effective_from == date(2027, 12, 2)
    assert deployer.coverage_facets == [
        "annex3_5b_credit_vs_fraud_exemption_assessed",
        "deployer_human_oversight_assigned",
        "automatic_logs_retained_6months",
        "article27_fundamental_rights_impact_assessment_completed",
    ]
    assert art50.coverage_facets == [
        "article50_ai_interaction_transparency_provided",
        "synthetic_content_marking_and_disclosure_applied",
    ]
    assert "MAP-PRIMARY-046" in mappings
    assert mappings["MAP-PRIMARY-046"].obligation_id == "EU-AIA-ART50-TRANSPARENCY"

    # Purely domestic Australian use case -> NOT_APPLICABLE across all EU obligations
    domestic_uc = BankingUseCase(
        apra_regulated=True,
        handles_personal_information=True,
        eu_establishment_or_market=False,
        eu_output_used=False,
        as_of_date=date(2026, 10, 15),
    )
    for eu_ob in (art4_5, art50, high_risk, deployer):
        dec = decide_applicability(eu_ob, domestic_uc)
        assert dec.status is ApplicabilityStatus.NOT_APPLICABLE

    # EU nexus at 2026-10-15: Art 50 active threshold passed (2026-08-02), Annex III deferred to 2027-12-02
    eu_oct2026_uc = BankingUseCase(
        eu_establishment_or_market=True,
        eu_output_used=True,
        eu_deployer_or_provider_role=True,
        eu_operator_role="deployer",
        assists_consumer_credit_decision=True,
        as_of_date=date(2026, 10, 15),
    )
    art50_oct = decide_applicability(art50, eu_oct2026_uc)
    assert art50_oct.status is ApplicabilityStatus.CONDITIONAL
    assert "2 Aug 2026" in art50_oct.reason

    hr_oct = decide_applicability(high_risk, eu_oct2026_uc)
    assert hr_oct.status is ApplicabilityStatus.CONDITIONAL
    assert "2027-12-02" in hr_oct.reason

    dep_oct = decide_applicability(deployer, eu_oct2026_uc)
    assert dep_oct.status is ApplicabilityStatus.CONDITIONAL
    assert "2027-12-02" in dep_oct.reason

    # Pre-Art 50 date (2026-06-01) cites 2026-08-02 commencement
    eu_jun2026_uc = eu_oct2026_uc.model_copy(update={"as_of_date": date(2026, 6, 1)})
    art50_jun = decide_applicability(art50, eu_jun2026_uc)
    assert art50_jun.status is ApplicabilityStatus.CONDITIONAL
    assert "2026-08-02" in art50_jun.reason


def test_e41_unknown_entity_and_business_context_never_assumes_applicable():
    pack = load_regulatory_pack()
    unknown_uc = BankingUseCase()
    for ob in pack.obligations:
        dec = decide_applicability(ob, unknown_uc)
        assert dec.status in {
            ApplicabilityStatus.UNDETERMINED,
            ApplicabilityStatus.CONDITIONAL,
        }, f"Unexpected status {dec.status} for {ob.obligation_id} with unknown entity context"


def test_e41_duplicate_mapping_pair_eliminated_and_guarded():
    mappings = load_obligation_control_mappings()
    pack = load_regulatory_pack()
    sources = load_source_register()
    controls = load_unified_control_library()

    pairs = [(m.obligation_id, m.control_id) for m in mappings.mappings]
    assert len(pairs) == len(set(pairs))
    assert all(m.mapping_id != "MAP-CROSS-007" for m in mappings.mappings)

    m44 = next(m for m in mappings.mappings if m.mapping_id == "MAP-PRIMARY-044")
    assert m44.obligation_id == "ISO23894-AI-RISK-PROCESS"
    assert m44.control_id == "CTRL-RISK-FRAMEWORK"
    assert "MAP-CROSS-007" in m44.equivalence_rationale

    # Structural validation rejects re-introduction of a duplicate pair
    dup_clone = m44.model_copy(update={"mapping_id": "MAP-CROSS-DUP"})
    broken = mappings.model_copy(update={"mappings": [*mappings.mappings, dup_clone]})
    report = validate_regulatory_library(
        pack=pack,
        source_register=sources,
        control_library=controls,
        mapping_catalogue=broken,
    )
    assert report["valid"] is False
    assert not report["checks"]["mapping_facet_and_relationship_consistency"]["passed"]


def test_e41_non_equivalent_mappings_never_credit_coverage_in_validation_or_runtime():
    mappings = load_obligation_control_mappings()
    pack = load_regulatory_pack()
    sources = load_source_register()
    controls = load_unified_control_library()

    non_eq_ids = {"MAP-CROSS-003", "MAP-CROSS-004", "MAP-CROSS-006"}
    for m in mappings.mappings:
        if m.mapping_id in non_eq_ids:
            assert m.mapping_relationship is MappingRelationship.NON_EQUIVALENT
            assert m.mapped_facets == []

    # Structural validation rejects non_equivalent mappings carrying mapped_facets
    m_non_eq = next(m for m in mappings.mappings if m.mapping_id == "MAP-CROSS-003")
    corrupt_non_eq = m_non_eq.model_copy(
        update={
            "mapped_facets": [m_non_eq.unmapped_obligation_facets[0]],
            "unmapped_obligation_facets": m_non_eq.unmapped_obligation_facets[1:],
        }
    )
    broken = mappings.model_copy(
        update={
            "mappings": [
                corrupt_non_eq if m.mapping_id == "MAP-CROSS-003" else m
                for m in mappings.mappings
            ]
        }
    )
    report = validate_regulatory_library(
        pack=pack,
        source_register=sources,
        control_library=controls,
        mapping_catalogue=broken,
    )
    assert report["valid"] is False
    assert not report["checks"]["mapping_facet_and_relationship_consistency"]["passed"]

    # Runtime clause mapped ONLY as NON_EQUIVALENT to CTRL-SEC-INCIDENT must NOT claim AU-PRIV-NDB-S26WE coverage
    ndb_ob = next(o for o in pack.obligations if o.obligation_id == "AU-PRIV-NDB-S26WE")
    clause = EnterpriseClause(
        clause_id="CLS-E41-NON-EQ",
        policy_id="POL-E41",
        source_name="APRA Security Policy",
        tenant_id="tenant-e41",
        title="APRA 72h security notification only",
        text="Report material security incidents to APRA within 72 hours.",
        control_facets=[],
        control_mappings=[
            ClauseControlMapping(
                tenant_id="tenant-e41",
                clause_id="CLS-E41-NON-EQ",
                control_id="CTRL-SEC-INCIDENT",
                relationship=MappingRelationship.NON_EQUIVALENT,
                mapped_facets=["ai_data_leakage_detection_enabled"],
                review_status=ClauseReviewStatus.APPROVED,
            )
        ],
        review_status=ClauseReviewStatus.APPROVED,
    )
    baseline = EnterpriseBaseline(
        baseline_id="BL-E41",
        tenant_id="tenant-e41",
        name="Baseline E41",
        version="1.0.0",
        status="active",
        clauses=[clause],
        source_policy_ids=["POL-E41"],
        source_policy_versions={"POL-E41": "1.0.0"},
        regulatory_pack_id=pack.pack_id,
        regulatory_pack_version=pack.version,
    )
    dec = validate_candidate_relationship(
        clause=clause,
        obligation=ndb_ob,
        regulatory_pack=pack,
        enterprise_baseline=baseline,
    )
    assert dec.validated_relationship is not ReconciliationRelationship.EQUIVALENT
    assert dec.dimension_comparison.shared_facets == []
    assert dec.dimension_comparison.shared_control_ids == []
    ranked = rank_reconciliation_candidates_for_clause(clause, regulatory_pack=pack, top_k=10)
    assert all(r["obligation_id"] != "AU-PRIV-NDB-S26WE" or r["score"] < 0.5 for r in ranked)


def test_e41_overbroad_full_mappings_reclassified():
    mappings = {m.mapping_id: m for m in load_obligation_control_mappings().mappings}
    assert mappings["MAP-PRIMARY-023"].mapping_relationship is MappingRelationship.RELATED
    assert mappings["MAP-PRIMARY-027"].mapping_relationship is MappingRelationship.PARTIAL
    assert mappings["MAP-PRIMARY-028"].mapping_relationship is MappingRelationship.PARTIAL
    assert mappings["MAP-PRIMARY-030"].mapping_relationship is MappingRelationship.RELATED
    assert mappings["MAP-PRIMARY-031"].mapping_relationship is MappingRelationship.PARTIAL
    assert mappings["MAP-PRIMARY-046"].mapping_relationship is MappingRelationship.PARTIAL
    assert mappings["MAP-CROSS-005"].mapped_facets == ["deployer_human_oversight_assigned"]


def test_e41_pack_version_020_triggers_stale_reconciliation_and_blocks_auto_equivalence():
    pack = load_regulatory_pack()
    assert pack.version == "0.2.0"

    old_pack = pack.model_copy(update={"version": "0.1.0"})
    ob = next(o for o in pack.obligations if o.obligation_id == "AU-PRIV-APP11-SECURITY")
    clause = EnterpriseClause(
        clause_id="CLS-E41-STALE",
        policy_id="POL-E41",
        source_name="Security Policy",
        tenant_id="tenant-e41",
        title="Protect PI",
        text="Protect personal information using technical and organisational encryption and access controls and destroy after retention schedule.",
        control_facets=["technical_security_measures_implemented"],
        review_status=ClauseReviewStatus.APPROVED,
    )
    policy = EnterprisePolicy(
        policy_id="POL-E41",
        tenant_id="tenant-e41",
        name="Security Policy",
        version="1.0.0",
        raw_text=clause.text,
        clauses=[clause],
        review_status=ClauseReviewStatus.APPROVED,
    )
    baseline = EnterpriseBaseline(
        baseline_id="BL-E41-STALE",
        tenant_id="tenant-e41",
        name="Baseline E41 Stale",
        version="1.0.0",
        status="active",
        clauses=[clause],
        source_policy_ids=["POL-E41"],
        source_policy_versions={"POL-E41": "1.0.0"},
        regulatory_pack_id=old_pack.pack_id,
        regulatory_pack_version="0.1.0",
    )
    reconciled = generate_reconciliation_candidates(
        tenant_id="tenant-e41",
        regulatory_pack=old_pack,
        use_case=BankingUseCase(handles_personal_information=True),
        enterprise_baseline=baseline,
        policies=[policy],
    )
    target_dec = next(
        d for d in reconciled if d.external_obligation_id == ob.obligation_id
    )
    approved_old = target_dec.model_copy(
        update={
            "decision_status": ReconciliationDecisionStatus.APPROVED,
            "validated_relationship": ReconciliationRelationship.EQUIVALENT,
        }
    )

    stale = evaluate_reconciliation_staleness(
        approved_old,
        enterprise_baseline=baseline,
        regulatory_pack=pack,
        policies=[policy],
    )
    assert stale.is_stale is True
    assert "0.1.0" in (stale.stale_reason or "")
    assert "0.2.0" in (stale.stale_reason or "")

    eff = compose_effective_assessment_baseline(
        tenant_id="tenant-e41",
        regulatory_pack=pack,
        use_case=BankingUseCase(handles_personal_information=True),
        enterprise_baseline=baseline,
        reconciliation_decisions=[approved_old],
        policies=[policy],
    )
    assert approved_old.reconciliation_id in eff.stale_reconciliation_ids
    assert any(u.reconciliation_id == approved_old.reconciliation_id for u in eff.unresolved_items)
    assert not any(
        item.obligation_id == ob.obligation_id
        and item.enterprise_clause_id == approved_old.enterprise_clause_id
        for item in eff.requirements
    )


def test_e41_candidate_requirements_register_unimported_and_all_runtime_proposed():
    cand_path = ROOT / "E41_CANDIDATE_REQUIREMENTS_REGISTER.csv"
    assert cand_path.exists()
    with cand_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    ids = {r["candidate_id"] for r in rows}
    assert any("FAR" in cid for cid in ids)
    assert any("CORP" in cid for cid in ids)
    assert any("2022-205" in cid or "IDR-DATA" in cid for cid in ids)
    assert all(r["review_status"] == "proposed" for r in rows)
    assert all(r["imported_to_runtime"] == "false" for r in rows)

    pack = load_regulatory_pack()
    sources = load_source_register()
    mappings = load_obligation_control_mappings()
    assert all(s.reviewer_status is ReviewStatus.PROPOSED for s in sources)
    assert all(o.review_status is ReviewStatus.PROPOSED for o in pack.obligations)
    assert all(m.review_status is ReviewStatus.PROPOSED for m in mappings.mappings)


def test_e41_deliverables_exist():
    required = [
        "E41_CANDIDATE_REQUIREMENTS_REGISTER.csv",
        "E41_REGULATORY_CORRECTION_CHANGELOG.md",
        "E41_PRIMARY_SOURCE_EVIDENCE.md",
        "E41_CONTROL_MAPPING_REMEDIATION.md",
        "E41_APPLICABILITY_REGRESSION_RESULTS.md",
        "E41_PENDING_LEGAL_REVIEW.md",
        "E41_RELEASE_READINESS.md",
    ]
    for name in required:
        p = ROOT / name
        assert p.exists(), f"Missing {name}"
        assert p.stat().st_size > 0, f"Empty {name}"
