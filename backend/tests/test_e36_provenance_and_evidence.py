import pytest
from datetime import datetime, timezone

from banking_crosswalk.models import (
    ClauseControlMapping,
    ClauseReviewStatus,
    EnterpriseBaseline,
    EnterpriseClause,
    EnterpriseAuthorityLevel,
    MappingOrigin,
    MappingRelationship,
    ReconciliationDecision,
    ReconciliationDimensionComparison,
    ReconciliationRelationship,
)
from banking_crosswalk.reconciliation import (
    is_human_authored_mapping,
    validate_candidate_relationship,
)
from banking_crosswalk.catalog import load_regulatory_pack
from banking_crosswalk.store import TenantStore, NotFoundError


def test_mapping_origin_deserialization_backward_compatibility():
    """Legacy payloads without mapping_origin must default to LEGACY_UNKNOWN."""
    legacy_payload = {
        "mapping_id": "map-legacy-1",
        "tenant_id": "test-tenant",
        "clause_id": "clause-1",
        "control_id": "CTRL-GOV-AI-ETHICS",
        "relationship": "full",
        "mapped_facets": ["governance_framework_active"],
        "rationale": "Direct executive alignment",
        "review_status": "proposed",
    }
    mapping = ClauseControlMapping.model_validate(legacy_payload)
    assert mapping.mapping_origin == MappingOrigin.LEGACY_UNKNOWN

    # If null or empty string passed, it gracefully falls back to LEGACY_UNKNOWN
    payload_null = dict(legacy_payload, mapping_origin=None)
    assert ClauseControlMapping.model_validate(payload_null).mapping_origin == MappingOrigin.LEGACY_UNKNOWN

    payload_empty = dict(legacy_payload, mapping_origin="")
    assert ClauseControlMapping.model_validate(payload_empty).mapping_origin == MappingOrigin.LEGACY_UNKNOWN

    # Explicit origins are parsed correctly
    payload_human = dict(legacy_payload, mapping_origin="human_authored")
    assert ClauseControlMapping.model_validate(payload_human).mapping_origin == MappingOrigin.HUMAN_AUTHORED

    payload_auto = dict(legacy_payload, mapping_origin="auto_extracted")
    assert ClauseControlMapping.model_validate(payload_auto).mapping_origin == MappingOrigin.AUTO_EXTRACTED


def test_origin_authority_decoupled_from_rationale_text():
    """Text edits to rationale must never alter the origin authority."""
    # 1. AUTO_EXTRACTED mapping remains non-human even if rationale is edited to look human-like
    auto_map = ClauseControlMapping(
        tenant_id="test-tenant",
        clause_id="clause-1",
        control_id="CTRL-GOV",
        relationship=MappingRelationship.FULL,
        mapped_facets=["f1"],
        rationale="Clause contains facet 'f1'",
        review_status=ClauseReviewStatus.APPROVED,
        mapping_origin=MappingOrigin.AUTO_EXTRACTED,
    )
    assert not is_human_authored_mapping(auto_map)

    # Edit rationale to look like a manual human review comment
    auto_map.rationale = "Senior Risk Officer approved this policy mapping manually on 2026-11-20."
    assert not is_human_authored_mapping(auto_map)

    # 2. HUMAN_AUTHORED mapping remains human even if rationale is empty or resembles auto-extracted prefix
    human_map = ClauseControlMapping(
        tenant_id="test-tenant",
        clause_id="clause-1",
        control_id="CTRL-GOV",
        relationship=MappingRelationship.FULL,
        mapped_facets=["f1"],
        rationale="Human risk assessment note",
        review_status=ClauseReviewStatus.APPROVED,
        mapping_origin=MappingOrigin.HUMAN_AUTHORED,
    )
    assert is_human_authored_mapping(human_map)

    human_map.rationale = "Clause contains facet 'f1'"
    assert is_human_authored_mapping(human_map)

    # 3. LEGACY_UNKNOWN mapping falls back cleanly to prefix heuristic
    legacy_auto = ClauseControlMapping(
        tenant_id="test-tenant",
        clause_id="clause-1",
        control_id="CTRL-GOV",
        relationship=MappingRelationship.FULL,
        mapped_facets=["f1"],
        rationale="Clause contains facet 'f1'",
        review_status=ClauseReviewStatus.APPROVED,
        mapping_origin=MappingOrigin.LEGACY_UNKNOWN,
    )
    assert not is_human_authored_mapping(legacy_auto)

    legacy_human = ClauseControlMapping(
        tenant_id="test-tenant",
        clause_id="clause-1",
        control_id="CTRL-GOV",
        relationship=MappingRelationship.FULL,
        mapped_facets=["f1"],
        rationale="Auditor reviewed against CPS 230 operational risk controls",
        review_status=ClauseReviewStatus.APPROVED,
        mapping_origin=MappingOrigin.LEGACY_UNKNOWN,
    )
    assert is_human_authored_mapping(legacy_human)


def test_evidence_verification_status_and_contradicted_facets():
    """Verify evidence_verification_status and contradicted_facets in reconciliation decisions."""
    pack = load_regulatory_pack()
    ob = pack.obligations[0]

    baseline = EnterpriseBaseline(
        baseline_id="base-test",
        tenant_id="tenant-alpha",
        name="Test Baseline",
        version="1.0.0",
        revision=1,
    )

    # Test Operational Evidence
    clause_op = EnterpriseClause(
        clause_id="cl-op",
        tenant_id="tenant-alpha",
        policy_id="pol-1",
        source_name="Ops Policy",
        section="1.1",
        text="All customer complaints are tested and audited quarterly, with continuous monitor of breaches.",
        authority_level=EnterpriseAuthorityLevel.ENTERPRISE_POLICY,
    )
    dec_op = validate_candidate_relationship(
        clause=clause_op,
        obligation=ob,
        regulatory_pack=pack,
        enterprise_baseline=baseline,
    )
    assert dec_op.evidence_verification_status == "operational_evidence_verified"
    assert isinstance(dec_op.dimension_comparison.contradicted_facets, list)

    # Test Documentary Evidence
    clause_doc = EnterpriseClause(
        clause_id="cl-doc",
        tenant_id="tenant-alpha",
        policy_id="pol-1",
        source_name="Doc Policy",
        section="1.2",
        text="Complaints and incident reports must be documented and retained in the central register.",
        authority_level=EnterpriseAuthorityLevel.ENTERPRISE_POLICY,
    )
    dec_doc = validate_candidate_relationship(
        clause=clause_doc,
        obligation=ob,
        regulatory_pack=pack,
        enterprise_baseline=baseline,
    )
    assert dec_doc.evidence_verification_status == "documentary_evidence_attached"

    # Test Missing Evidence / Uncertainties
    clause_missing = EnterpriseClause(
        clause_id="cl-missing",
        tenant_id="tenant-alpha",
        policy_id="pol-1",
        source_name="Missing Policy",
        section="1.3",
        text="Procedures are outlined in Annexure G which is pending distribution.",
        authority_level=EnterpriseAuthorityLevel.ENTERPRISE_POLICY,
    )
    dec_missing = validate_candidate_relationship(
        clause=clause_missing,
        obligation=ob,
        regulatory_pack=pack,
        enterprise_baseline=baseline,
    )
    assert dec_missing.evidence_verification_status == "missing_evidence"
    assert len(dec_missing.missing_conditions_or_evidence) > 0


def test_store_mapping_review_tenant_isolation():
    """Verify tenant isolation when updating clause mapping reviews."""
    store = TenantStore()
    tenant_a = "tenant-a"
    tenant_b = "tenant-b"

    clause_a = EnterpriseClause(
        clause_id="cl-a-1",
        tenant_id=tenant_a,
        policy_id="pol-a",
        source_name="Policy A",
        section="1.0",
        text="Tenant A policy statement.",
        authority_level=EnterpriseAuthorityLevel.ENTERPRISE_POLICY,
    )
    mapping_a = ClauseControlMapping(
        mapping_id="map-a-1",
        tenant_id=tenant_a,
        clause_id="cl-a-1",
        control_id="CTRL-GOV-AI-ETHICS",
        relationship=MappingRelationship.FULL,
        mapped_facets=["governance_framework_active"],
        rationale="Initial extraction",
        review_status=ClauseReviewStatus.PROPOSED,
        mapping_origin=MappingOrigin.AUTO_EXTRACTED,
    )
    clause_a.control_mappings = [mapping_a]

    # Save to store under tenant_a
    store._bucket(store._enterprise_clauses, tenant_a)[clause_a.clause_id] = clause_a
    store._bucket(store._clause_mappings, tenant_a)[mapping_a.mapping_id] = mapping_a

    # Attempting to review tenant_a mapping from tenant_b MUST fail with NotFoundError
    with pytest.raises(NotFoundError):
        store.update_clause_mapping_review(
            tenant_id=tenant_b,
            clause_id="cl-a-1",
            mapping_id="map-a-1",
            status=ClauseReviewStatus.APPROVED,
            actor="attacker",
            role="compliance_officer",
            mapping_origin=MappingOrigin.HUMAN_AUTHORED,
        )

    # Legitimate review by tenant_a succeeds and updates mapping_origin
    updated = store.update_clause_mapping_review(
        tenant_id=tenant_a,
        clause_id="cl-a-1",
        mapping_id="map-a-1",
        status=ClauseReviewStatus.APPROVED,
        actor="compliance_officer_jane",
        role="compliance_officer",
        review_comment="Confirmed by risk team",
        mapping_origin=MappingOrigin.HUMAN_AUTHORED,
    )
    assert updated.review_status == ClauseReviewStatus.APPROVED
    assert updated.mapping_origin == MappingOrigin.HUMAN_AUTHORED
    assert updated.reviewer_actor == "compliance_officer_jane"
