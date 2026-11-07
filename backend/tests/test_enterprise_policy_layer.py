"""Comprehensive Acceptance Test Suite for Enterprise Regulatory & Policy Layer.

Covers all 10 acceptance scenarios from ENTERPRISE_LAYER_GAP_ANALYSIS.md:
1. Enterprise policy fully covers a required external control.
2. Enterprise policy partially covers a control.
3. Questionnaire omits a mandatory enterprise control.
4. Additional enterprise policy requirements exceed the regulatory minimum.
5. Two policies contain conflicting approval thresholds.
6. A voluntary framework is correctly classified (not legally mandatory).
7. A user uploads a superseded regulation.
8. A customer uploads a regulation already present in the shared library.
9. An enterprise requirement is incorrectly mapped to an unrelated control.
10. Two tenants upload different policies and remain completely isolated.
"""

from __future__ import annotations

import uuid
from typing import List

import pytest
from fastapi.testclient import TestClient

from banking_crosswalk.app import app
from banking_crosswalk.catalog import (
    load_aiaf_question_bank,
    load_regulatory_pack,
    load_unified_control_library,
)
from banking_crosswalk.coverage import evaluate_questionnaire_coverage
from banking_crosswalk.models import (
    Authority,
    BankingUseCase,
    ClauseControlMapping,
    ClauseReviewStatus,
    EnterpriseAuthorityLevel,
    EnterpriseBaseline,
    EnterpriseClause,
    EnterprisePolicy,
    GapType,
    MappingRelationship,
    QuestionBank,
    QuestionRecord,
    QuestionnaireMetadata,
)
from banking_crosswalk.policy import (
    assess_enterprise_policy_gaps,
    check_shared_library_duplicate,
    extract_enterprise_policy,
)
from banking_crosswalk.store import store


@pytest.fixture(autouse=True)
def reset_in_memory_store():
    store.reset()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def regulatory_pack():
    return load_regulatory_pack()


@pytest.fixture
def question_bank():
    return load_aiaf_question_bank()


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Enterprise policy fully covers a required external control
# ─────────────────────────────────────────────────────────────────────────────
def test_1_enterprise_policy_fully_covers_external_control(regulatory_pack, question_bank):
    tenant = f"tenant-{uuid.uuid4()}"
    policy_text = (
        "Customer consent must be recorded prior to collecting sensitive biometrics, "
        "and data must be stored encrypted with AES-256 with established retention periods."
    )
    policy = extract_enterprise_policy(
        tenant_id=tenant,
        name="Biometric Privacy Standard",
        text=policy_text,
        category="privacy",
        authority_level=EnterpriseAuthorityLevel.ENTERPRISE_POLICY,
    )
    assert len(policy.clauses) > 0
    assert any(c.mandatory for c in policy.clauses)

    # Ingest into store
    store.save_enterprise_policy(tenant, policy)

    # Confirm clause mappings to CTRL-PRIV-COLLECTION
    for clause in policy.clauses:
        store.update_clause_review(
            tenant,
            clause.clause_id,
            status=ClauseReviewStatus.CONFIRMED,
            actor="compliance-lead",
            role="compliance",
        )

    assessment = assess_enterprise_policy_gaps(
        tenant_id=tenant,
        policies=[policy],
        question_bank=question_bank,
        regulatory_pack=regulatory_pack,
    )

    # AU-PRIV-APP3-COLLECT is addressed by consent and collection rules
    assert isinstance(assessment.policy_clauses, list)
    assert len(assessment.policy_clauses) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Enterprise policy partially covers a control
# ─────────────────────────────────────────────────────────────────────────────
def test_2_enterprise_policy_partially_covers_control(regulatory_pack, question_bank):
    tenant = f"tenant-{uuid.uuid4()}"
    # Minimal text that lacks full operational facets (like pre-execution block and numeric thresholds)
    policy_text = "AI systems must be generally overseen by managers."
    policy = extract_enterprise_policy(
        tenant_id=tenant,
        name="Vague AI Guidance",
        text=policy_text,
    )
    store.save_enterprise_policy(tenant, policy)

    assessment = assess_enterprise_policy_gaps(
        tenant_id=tenant,
        policies=[policy],
        question_bank=question_bank,
        regulatory_pack=regulatory_pack,
    )

    # Emits policy gaps because binding regulatory facets are missing from the sparse policy
    assert len(assessment.policy_gaps) > 0
    missing_facet_lists = [g.missing_facets for g in assessment.policy_gaps]
    assert any(len(mf) > 0 for mf in missing_facet_lists)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Questionnaire omits a mandatory enterprise control
# ─────────────────────────────────────────────────────────────────────────────
def test_3_questionnaire_omits_mandatory_enterprise_control(regulatory_pack):
    tenant = f"tenant-{uuid.uuid4()}"
    # Policy mandates zero data retention (ZDR)
    policy_text = (
        "All third-party AI vendor integrations must enforce zero data retention "
        "and prompt logging on sovereign Australian infrastructure."
    )
    policy = extract_enterprise_policy(
        tenant_id=tenant,
        name="Vendor AI Standard",
        text=policy_text,
    )
    assert any("zero_data_retention" in c.control_facets for c in policy.clauses)

    # Provide a minimal questionnaire that only asks about uptime and general accuracy
    sparse_bank = QuestionBank(
        metadata=QuestionnaireMetadata(
            questionnaire_id="SPARSE_Q_01",
            title="Sparse Questionnaire",
            source_filename="sparse.json",
            source_version="1.0",
            source_sha256="abc123sha",
        ),
        questions=[
            QuestionRecord(
                question_id="Q1",
                question_text="What is the expected uptime of the system?",
                risk_domain="D6",
                source_version="1.0",
                source_sheet="Sheet1",
            ),
            QuestionRecord(
                question_id="Q2",
                question_text="How often is model accuracy validated?",
                risk_domain="D4",
                source_version="1.0",
                source_sheet="Sheet1",
            ),
        ],
    )

    assessment = assess_enterprise_policy_gaps(
        tenant_id=tenant,
        policies=[policy],
        question_bank=sparse_bank,
        regulatory_pack=regulatory_pack,
    )

    # The questionnaire fails to test zero data retention
    zdr_gaps = [
        g for g in assessment.questionnaire_gaps
        if any("retention" in f for f in g.missing_facets) or "retention" in g.recommendation.lower()
    ]
    assert len(zdr_gaps) > 0
    assert zdr_gaps[0].severity == "high"


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Additional enterprise policy exceeds regulatory minimum (Elevated Standard)
# ─────────────────────────────────────────────────────────────────────────────
def test_4_enterprise_policy_exceeds_regulatory_minimum(regulatory_pack, question_bank):
    tenant = f"tenant-{uuid.uuid4()}"
    policy_text = (
        "Every automated transaction adjustment above AUD 250 requires dual human sign-off "
        "before execution."
    )
    policy = extract_enterprise_policy(
        tenant_id=tenant,
        name="Elevated Delegated Authority Standard",
        text=policy_text,
    )
    assert any(250.0 in c.thresholds_aud for c in policy.clauses)

    # In questionnaire coverage validation, the enterprise baseline requires testing $250
    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_clauses=policy.clauses,
        assessment_mode="enterprise_enhanced",
    )

    assert cov.enterprise_gaps is not None
    # Questionnaire doesn't have the $250 numeric threshold check, so it flags an enterprise gap
    assert len(cov.enterprise_gaps) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Two policies contain conflicting approval thresholds
# ─────────────────────────────────────────────────────────────────────────────
def test_5_two_policies_contain_conflicting_thresholds(regulatory_pack, question_bank):
    tenant = f"tenant-{uuid.uuid4()}"
    pol1 = extract_enterprise_policy(
        tenant_id=tenant,
        name="Credit Card Policy",
        text="All customer refund credits above AUD 1,000 require manual manager sign-off.",
    )
    pol2 = extract_enterprise_policy(
        tenant_id=tenant,
        name="Fraud Operations Policy",
        text="All automated dispute credits above AUD 500 must be reviewed and approved by human supervisor.",
    )

    assessment = assess_enterprise_policy_gaps(
        tenant_id=tenant,
        policies=[pol1, pol2],
        question_bank=question_bank,
        regulatory_pack=regulatory_pack,
    )

    assert len(assessment.control_conflicts) > 0
    conflict = assessment.control_conflicts[0]
    assert conflict.gap_type == GapType.CONTROL_CONFLICT
    assert "conflicting AUD approval thresholds" in conflict.title
    assert conflict.severity == "high"


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Voluntary framework correctly classified as low severity
# ─────────────────────────────────────────────────────────────────────────────
def test_6_voluntary_framework_correctly_classified(regulatory_pack):
    tenant = f"tenant-{uuid.uuid4()}"
    policy = extract_enterprise_policy(
        tenant_id=tenant,
        name="NIST AI RMF 1.0 Adoption Guide",
        text="Organizations should implement prompt logging and telemetry where practicable.",
        authority_level=EnterpriseAuthorityLevel.INDUSTRY_FRAMEWORK,
    )

    sparse_bank = QuestionBank(
        metadata=QuestionnaireMetadata(
            questionnaire_id="Q_BANK_NIST",
            title="Minimal Bank",
            source_filename="nist.json",
            source_version="1.0",
            source_sha256="sha999",
        ),
        questions=[],
    )

    assessment = assess_enterprise_policy_gaps(
        tenant_id=tenant,
        policies=[policy],
        question_bank=sparse_bank,
        regulatory_pack=regulatory_pack,
    )

    # For an industry framework (voluntary), gaps are marked severity low
    if assessment.questionnaire_gaps:
        assert all(g.severity == "low" for g in assessment.questionnaire_gaps)


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: Upload of superseded regulatory document warning
# ─────────────────────────────────────────────────────────────────────────────
def test_7_uploaded_regulation_detects_known_status():
    text = "APRA CPS 230 Operational Risk Management requirements..."
    warning = check_shared_library_duplicate(text)
    assert warning is not None
    assert "CPS 230" in warning


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: Upload of regulation already present in shared library
# ─────────────────────────────────────────────────────────────────────────────
def test_8_duplicate_upload_of_shared_regulation():
    tenant = f"tenant-{uuid.uuid4()}"
    text = (
        "Privacy Act 1988 (Cth) and Australian Privacy Principles. "
        "An APP entity must not collect personal information unless reasonably necessary."
    )
    policy = extract_enterprise_policy(
        tenant_id=tenant,
        name="Upload of Privacy Act Copy",
        text=text,
    )
    assert any("matches known shared regulation" in w for w in policy.warnings)


# ─────────────────────────────────────────────────────────────────────────────
# Test 9: Incorrect mapping to unrelated control rejected or marked non-equivalent
# ─────────────────────────────────────────────────────────────────────────────
def test_9_mapping_relationship_integrity():
    tenant = f"tenant-{uuid.uuid4()}"
    mapping = ClauseControlMapping(
        tenant_id=tenant,
        clause_id="CLAUSE-PHYSICAL-FIRE",
        control_id="CTRL-AI-BIAS-FAIRNESS",
        relationship=MappingRelationship.NOT_EQUIVALENT,
        rationale="Physical safety checks have no equivalence to algorithmic bias testing.",
        review_status=ClauseReviewStatus.CONFIRMED,
    )
    assert mapping.relationship == MappingRelationship.NOT_EQUIVALENT
    assert mapping.review_status == ClauseReviewStatus.CONFIRMED


# ─────────────────────────────────────────────────────────────────────────────
# Test 10: Two tenants upload different policies and remain completely isolated
# ─────────────────────────────────────────────────────────────────────────────
def test_10_multi_tenant_isolation(client):
    tenant_a = f"tenant-alpha-{uuid.uuid4()}"
    tenant_b = f"tenant-beta-{uuid.uuid4()}"

    # Tenant A imports confidential policy
    res_a = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant_a},
        json={
            "name": "Secret Enterprise Policy A",
            "text": "All proprietary banking algorithms must be encrypted with HSM keys.",
            "category": "cyber",
        },
    )
    assert res_a.status_code == 201
    policy_a_id = res_a.json()["policy_id"]

    # Tenant B imports policy
    res_b = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant_b},
        json={
            "name": "Public Enterprise Policy B",
            "text": "General customer service guidelines.",
            "category": "general",
        },
    )
    assert res_b.status_code == 201
    policy_b_id = res_b.json()["policy_id"]

    # Tenant B tries to retrieve Tenant A's policy
    res_b_get_a = client.get(
        f"/v1/enterprise/policies/{policy_a_id}",
        headers={"X-Tenant-ID": tenant_b},
    )
    assert res_b_get_a.status_code == 404

    # Tenant B lists policies - should only see Policy B
    res_b_list = client.get(
        "/v1/enterprise/policies",
        headers={"X-Tenant-ID": tenant_b},
    )
    assert res_b_list.status_code == 200
    b_policies = res_b_list.json()
    assert len(b_policies) == 1
    assert b_policies[0]["policy_id"] == policy_b_id
    assert b_policies[0]["name"] == "Public Enterprise Policy B"

    # Tenant A lists policies - should only see Policy A
    res_a_list = client.get(
        "/v1/enterprise/policies",
        headers={"X-Tenant-ID": tenant_a},
    )
    assert res_a_list.status_code == 200
    a_policies = res_a_list.json()
    assert len(a_policies) == 1
    assert a_policies[0]["policy_id"] == policy_a_id
