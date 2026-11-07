"""Adversarial regression test suite for Revised P1-S0:
Coverage Confirmation Safety & Mapping Approval Integrity.

Covers:
- Reproduction of Defect A (Weak keyword matches creating false confirmed coverage)
- Reproduction of Defect B (Mapped clauses without explicit facets bypassing assessment)
- Reproduction of Defect C (Clause and Control Mapping approval conflation)
- All 20 Mandatory Adversarial Regression Scenarios:
  1. Generic mention of human oversight.
  2. Actual mandatory human approval question.
  3. Missing monetary approval threshold.
  4. Missing approval role.
  5. Missing pre-execution requirement.
  6. Incorrect numeric operator.
  7. Negated approval wording.
  8. Approved Clause with proposed Mapping.
  9. Approved Clause with approved Mapping.
  10. Approved Clause with rejected Mapping.
  11. Approved Clause with no facets.
  12. Approved and unmapped Clause.
  13. Multiple candidate questions collectively covering separate facets.
  14. Candidate text that is semantically related but insufficient.
  15. No candidate question.
  16. Conditional or exempt requirement.
  17. Regulatory-Only with no Enterprise Baseline.
  18. Enterprise-Enhanced with approved tenant baseline.
  19. Cross-tenant Mapping access.
  20. Existing baseline version and provenance integrity.
"""

from __future__ import annotations

import uuid
from typing import List

import pytest
from fastapi.testclient import TestClient

from banking_crosswalk.app import app
from banking_crosswalk.catalog import load_demo_questionnaire, load_regulatory_pack
from banking_crosswalk.coverage import evaluate_questionnaire_coverage
from banking_crosswalk.models import (
    BankingUseCase,
    ClauseControlMapping,
    ClauseReviewStatus,
    CoverageStatus,
    EnterpriseBaseline,
    EnterpriseClause,
    EnterprisePolicy,
    GapType,
    MappingRelationship,
    QuestionBank,
    QuestionnaireMetadata,
    QuestionRecord,
)
from banking_crosswalk.policy import (
    compile_enterprise_baseline,
    extract_enterprise_policy,
    verify_baseline_integrity,
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


def _make_question_bank(questions: List[str], bank_id: str = "Q-TEST-BANK") -> QuestionBank:
    return QuestionBank(
        metadata=QuestionnaireMetadata(
            questionnaire_id=bank_id,
            title="Synthetic Adversarial Test Questionnaire",
            source_filename="synthetic_test.xlsx",
            source_version="1.0.0",
            source_sha256="a" * 64,
        ),
        questions=[
            QuestionRecord(
                question_id=f"Q-{idx + 1:03d}",
                question_text=q_text,
                risk_domain="Governance",
                source_version="1.0.0",
                source_sheet="Sheet1",
            )
            for idx, q_text in enumerate(questions)
        ],
    )


def _make_approved_policy_and_baseline(
    tenant_id: str,
    clause_text: str,
    approve_mappings: bool = True,
) -> tuple[EnterprisePolicy, EnterpriseBaseline]:
    policy = extract_enterprise_policy(
        tenant_id=tenant_id,
        name="Enterprise Delegated Authority Policy",
        text=clause_text,
        version="1.0.0",
    )
    for c in policy.clauses:
        c.review_status = ClauseReviewStatus.APPROVED
        for m in c.control_mappings:
            m.review_status = (
                ClauseReviewStatus.APPROVED
                if approve_mappings
                else ClauseReviewStatus.PROPOSED
            )
    baseline = compile_enterprise_baseline(
        tenant_id=tenant_id,
        name="Approved Enterprise Baseline",
        policies=[policy],
        version="1.0.0",
        status="active",
    )
    return policy, baseline


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 1 (Defect A): Generic mention of human oversight
# ─────────────────────────────────────────────────────────────────────────────
def test_01_generic_mention_of_human_oversight_does_not_confirm_coverage(regulatory_pack):
    """Scenario 1 (Defect A): A question mentioning 'human oversight' must not satisfy
    a requirement for human approval, AUD threshold, approval authority, and pre-execution blocking.
    """
    tenant = f"tenant-s01-{uuid.uuid4()}"
    _, baseline = _make_approved_policy_and_baseline(
        tenant,
        "All automated customer refund transactions exceeding AUD 500 require Senior Manager "
        "human approval prior to execution.",
    )
    clause = baseline.clause_snapshots[0]
    assert "human_approval_required" in clause.control_facets
    assert "approval_threshold_defined" in clause.control_facets
    assert "pre_execution_block" in clause.control_facets

    # Questionnaire only mentions generic human oversight, defined monitoring, and execution logs
    qbank = _make_question_bank([
        "Does the AI system have general human oversight, defined monitoring, and execution logging?"
    ])

    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=qbank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )

    clause_gaps = [g for g in cov.enterprise_gaps if g.policy_clause_id == clause.clause_id]
    assert len(clause_gaps) > 0, "Weak keyword overlap must not produce zero enterprise gaps"
    assert "human_approval_required" in clause_gaps[0].missing_facets
    assert "approval_threshold_defined" in clause_gaps[0].missing_facets
    assert "pre_execution_block" in clause_gaps[0].missing_facets

    # Verify enterprise clause coverage status is needs_review (not covered)
    clause_evals = {e.clause_id: e for e in getattr(cov, "enterprise_clause_coverage", [])}
    assert clause.clause_id in clause_evals
    assert clause_evals[clause.clause_id].coverage_status == CoverageStatus.NEEDS_REVIEW


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 2: Actual mandatory human approval question
# ─────────────────────────────────────────────────────────────────────────────
def test_02_actual_mandatory_human_approval_question_satisfies_constraints(regulatory_pack):
    """Scenario 2: A question explicitly testing mandatory human approval, the AUD 500 threshold,
    Senior Manager role, and pre-execution blocking satisfies the required facets.
    """
    tenant = f"tenant-s02-{uuid.uuid4()}"
    _, baseline = _make_approved_policy_and_baseline(
        tenant,
        "All automated customer refund transactions exceeding AUD 500 require Senior Manager "
        "human approval prior to execution.",
    )
    clause = baseline.clause_snapshots[0]

    qbank = _make_question_bank([
        "Are automated customer refund transactions exceeding AUD 500 blocked prior to execution "
        "until mandatory human approval is granted by a Senior Manager?"
    ])

    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=qbank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
        use_case=BankingUseCase(
            name="Refund Agent",
            apra_regulated=True,
            approval_threshold_aud=500.0,
            approval_threshold_operator=">",
            approval_timing="pre_execution",
            approval_role="Senior Manager",
        ),
    )

    q_gaps = [
        g for g in cov.enterprise_gaps
        if g.policy_clause_id == clause.clause_id and g.gap_type == GapType.QUESTIONNAIRE
    ]
    assert len(q_gaps) == 0

    clause_evals = {e.clause_id: e for e in getattr(cov, "enterprise_clause_coverage", [])}
    assert clause.clause_id in clause_evals
    assert clause_evals[clause.clause_id].coverage_status == CoverageStatus.COVERED


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 3 (Defect A): Missing monetary approval threshold
# ─────────────────────────────────────────────────────────────────────────────
def test_03_missing_monetary_approval_threshold_in_question(regulatory_pack):
    """Scenario 3: A question asking about human approval for defined high-value transactions
    without the required AUD 500 threshold must not confirm coverage of approval_threshold_defined.
    """
    tenant = f"tenant-s03-{uuid.uuid4()}"
    _, baseline = _make_approved_policy_and_baseline(
        tenant,
        "Automated customer refund transactions exceeding AUD 500 require human approval.",
    )
    clause = baseline.clause_snapshots[0]
    assert "approval_threshold_defined" in clause.control_facets

    qbank = _make_question_bank([
        "Does the workflow require mandatory human approval for defined high-value refund transactions?"
    ])

    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=qbank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )

    clause_gaps = [
        g for g in cov.enterprise_gaps
        if g.policy_clause_id == clause.clause_id and g.gap_type == GapType.QUESTIONNAIRE
    ]
    assert len(clause_gaps) > 0
    assert "approval_threshold_defined" in clause_gaps[0].missing_facets


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 4 (Defect A): Missing approval role
# ─────────────────────────────────────────────────────────────────────────────
def test_04_missing_approval_role_in_question(regulatory_pack):
    """Scenario 4: When a clause requires a specific approval authority role (e.g., Senior Manager),
    a question that omits or specifies a lower role must not establish confirmed coverage.
    """
    tenant = f"tenant-s04-{uuid.uuid4()}"
    _, baseline = _make_approved_policy_and_baseline(
        tenant,
        "All automated credit limit increases exceeding AUD 500 require Senior Manager approval.",
    )
    clause = baseline.clause_snapshots[0]
    assert clause.required_approval_role == "Senior Manager"

    qbank = _make_question_bank([
        "Do automated credit limit increases exceeding AUD 500 require human approval from a Customer Service Agent?"
    ])

    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=qbank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )

    clause_gaps = [
        g for g in cov.enterprise_gaps
        if g.policy_clause_id == clause.clause_id and g.gap_type == GapType.QUESTIONNAIRE
    ]
    assert len(clause_gaps) > 0
    assert any("role" in f or f == "human_approval_required" for f in clause_gaps[0].missing_facets)


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 5 (Defect A): Missing pre-execution requirement
# ─────────────────────────────────────────────────────────────────────────────
def test_05_missing_pre_execution_requirement_in_question(regulatory_pack):
    """Scenario 5: A question mentioning post-execution review or generic 'execution' must not
    satisfy pre_execution_block.
    """
    tenant = f"tenant-s05-{uuid.uuid4()}"
    _, baseline = _make_approved_policy_and_baseline(
        tenant,
        "Human approval must be obtained prior to execution of any automated payment refund.",
    )
    clause = baseline.clause_snapshots[0]
    assert "pre_execution_block" in clause.control_facets

    qbank = _make_question_bank([
        "Are automated payment refund executions reviewed for human approval during weekly post-execution audits?"
    ])

    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=qbank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )

    clause_gaps = [
        g for g in cov.enterprise_gaps
        if g.policy_clause_id == clause.clause_id and g.gap_type == GapType.QUESTIONNAIRE
    ]
    assert len(clause_gaps) > 0
    assert "pre_execution_block" in clause_gaps[0].missing_facets


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 6 (Defect A): Incorrect numeric operator
# ─────────────────────────────────────────────────────────────────────────────
def test_06_incorrect_numeric_operator_in_question(regulatory_pack):
    """Scenario 6: Policy requires approval at or above AUD 500 (>= 500), while question only
    checks strictly exceeding AUD 500 (> 500). Must not confirm coverage.
    """
    tenant = f"tenant-s06-{uuid.uuid4()}"
    _, baseline = _make_approved_policy_and_baseline(
        tenant,
        "Human approval is required for all automated refunds at or above AUD 500.",
    )
    clause = baseline.clause_snapshots[0]
    assert clause.threshold_operator == ">="

    qbank = _make_question_bank([
        "Is mandatory human approval required for automated refunds exceeding AUD 500?"
    ])

    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=qbank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )

    clause_gaps = [
        g for g in cov.enterprise_gaps
        if g.policy_clause_id == clause.clause_id and g.gap_type == GapType.QUESTIONNAIRE
    ]
    assert len(clause_gaps) > 0
    assert "approval_threshold_defined" in clause_gaps[0].missing_facets


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 7 (Defect A): Negated approval wording
# ─────────────────────────────────────────────────────────────────────────────
def test_07_negated_approval_wording_in_question_rejected(regulatory_pack):
    """Scenario 7: A question with negated approval wording ('human approval is not required')
    must never satisfy human_approval_required.
    """
    tenant = f"tenant-s07-{uuid.uuid4()}"
    _, baseline = _make_approved_policy_and_baseline(
        tenant,
        "Human approval is required for all automated credit decisions.",
    )
    clause = baseline.clause_snapshots[0]
    assert "human_approval_required" in clause.control_facets

    qbank = _make_question_bank([
        "Confirm that human approval is not required for automated credit decisions."
    ])

    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=qbank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )

    clause_gaps = [
        g for g in cov.enterprise_gaps
        if g.policy_clause_id == clause.clause_id and g.gap_type == GapType.QUESTIONNAIRE
    ]
    assert len(clause_gaps) > 0
    assert "human_approval_required" in clause_gaps[0].missing_facets

    clause_evals = {e.clause_id: e for e in getattr(cov, "enterprise_clause_coverage", [])}
    assert clause_evals[clause.clause_id].coverage_status == CoverageStatus.MISSING


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 8 (Defect C): Approved Clause with proposed Mapping
# ─────────────────────────────────────────────────────────────────────────────
def test_08_approved_clause_with_proposed_mapping_does_not_confirm_control(client: TestClient):
    """Scenario 8 (Defect C): Approving a clause must not automatically approve its proposed
    Control Mappings or promote them into confirmed_control_ids.
    """
    tenant = f"tenant-s08-{uuid.uuid4()}"
    res_p = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Refund Approval Policy",
            "text": "All automated refunds exceeding AUD 500 require human approval prior to execution.",
            "version": "1.0.0",
        },
    )
    assert res_p.status_code == 201
    pol_id = res_p.json()["policy_id"]
    clause_id = res_p.json()["clauses"][0]["clause_id"]

    # Approve ONLY the clause (no mapping approval)
    res_rev = client.put(
        f"/v1/enterprise/clauses/{clause_id}/review",
        headers={"X-Tenant-ID": tenant},
        json={
            "status": "approved",
            "actor": "grc-reviewer@bank.example",
            "role": "compliance",
            "review_comment": "Clause wording verified; control mappings not yet reviewed.",
        },
    )
    assert res_rev.status_code == 200
    reviewed_clause = res_rev.json()
    assert reviewed_clause["review_status"] == "approved"
    # Proposed mappings MUST remain proposed!
    assert len(reviewed_clause["control_mappings"]) > 0
    assert all(m["review_status"] == "proposed" for m in reviewed_clause["control_mappings"])

    # Compile baseline: approved clause is preserved, but confirmed_control_ids must be empty
    res_bl = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant},
        json={"name": "Clause Approved Only Baseline", "policy_ids": [pol_id]},
    )
    assert res_bl.status_code == 201
    bl = res_bl.json()
    assert clause_id in bl["approved_clause_ids"]
    assert bl["confirmed_control_ids"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 9: Approved Clause with approved Mapping
# ─────────────────────────────────────────────────────────────────────────────
def test_09_approved_clause_with_approved_mapping_confirms_control(client: TestClient):
    """Scenario 9: When BOTH the source clause AND the specific control mapping are approved,
    the valid control enters confirmed_control_ids.
    """
    tenant = f"tenant-s09-{uuid.uuid4()}"
    res_p = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Refund Approval Policy",
            "text": "All automated refunds exceeding AUD 500 require human approval prior to execution.",
            "version": "1.0.0",
        },
    )
    assert res_p.status_code == 201
    pol_id = res_p.json()["policy_id"]
    clause_data = res_p.json()["clauses"][0]
    clause_id = clause_data["clause_id"]
    mapping_id = clause_data["control_mappings"][0]["mapping_id"]
    target_control_id = clause_data["control_mappings"][0]["control_id"]

    # 1. Approve the clause
    res_rev = client.put(
        f"/v1/enterprise/clauses/{clause_id}/review",
        headers={"X-Tenant-ID": tenant},
        json={
            "status": "approved",
            "actor": "grc-reviewer@bank.example",
            "role": "compliance",
        },
    )
    assert res_rev.status_code == 200

    # 2. Independently approve the specific control mapping
    res_map_rev = client.put(
        f"/v1/enterprise/clauses/{clause_id}/mappings/{mapping_id}/review",
        headers={"X-Tenant-ID": tenant},
        json={
            "status": "approved",
            "actor": "control-architect@bank.example",
            "role": "assurance",
            "review_comment": "Verified control mapping equivalence.",
        },
    )
    assert res_map_rev.status_code == 200

    # 3. Compile baseline
    res_bl = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant},
        json={"name": "Fully Approved Baseline", "policy_ids": [pol_id]},
    )
    assert res_bl.status_code == 201
    bl = res_bl.json()
    assert clause_id in bl["approved_clause_ids"]
    assert target_control_id in bl["confirmed_control_ids"]


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 10 (Defect C): Approved Clause with rejected Mapping
# ─────────────────────────────────────────────────────────────────────────────
def test_10_approved_clause_with_rejected_mapping_excluded_from_confirmed_controls():
    """Scenario 10 (Defect C): An approved clause whose control mapping is rejected must NEVER
    promote that control into confirmed_control_ids. Likewise, an approved mapping on a
    rejected or proposed clause must not enter confirmed_control_ids.
    """
    tenant = f"tenant-s10-{uuid.uuid4()}"
    pol = extract_enterprise_policy(
        tenant_id=tenant,
        name="Mixed Review Policy",
        text=(
            "All automated refunds exceeding AUD 500 require human approval.\n\n"
            "All user prompts sent to LLMs must undergo prompt logging."
        ),
    )
    # Clause 0: Approved clause, REJECTED mapping
    c0 = pol.clauses[0]
    c0.review_status = ClauseReviewStatus.APPROVED
    for m in c0.control_mappings:
        m.review_status = ClauseReviewStatus.REJECTED

    # Clause 1: REJECTED clause, APPROVED mapping
    c1 = pol.clauses[1]
    c1.review_status = ClauseReviewStatus.REJECTED
    for m in c1.control_mappings:
        m.review_status = ClauseReviewStatus.APPROVED

    baseline = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Rejected Mappings Baseline",
        policies=[pol],
    )
    assert c0.clause_id in baseline.approved_clause_ids
    assert baseline.confirmed_control_ids == []


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 11 (Defect B): Approved Clause with no facets
# ─────────────────────────────────────────────────────────────────────────────
def test_11_approved_mapped_clause_with_no_facets_cannot_bypass_assessment(regulatory_pack):
    """Scenario 11 (Defect B): An approved Enterprise Clause with an approved Control Mapping
    but no explicit control_facets must not silently bypass coverage assessment.
    It must expose a MAPPING_INCOMPLETE status and an actionable review gap.
    """
    tenant = f"tenant-s11-{uuid.uuid4()}"
    clause = EnterpriseClause(
        clause_id="CLAUSE-NO-FACETS-001",
        policy_id="POL-001",
        tenant_id=tenant,
        source_name="Internal Governance Standard",
        text="High-impact algorithmic systems must satisfy enterprise human oversight governance.",
        mandatory=True,
        review_status=ClauseReviewStatus.APPROVED,
        is_unmapped=False,
        control_facets=[],
        control_mappings=[
            ClauseControlMapping(
                mapping_id="MAP-NO-FACETS-001",
                tenant_id=tenant,
                clause_id="CLAUSE-NO-FACETS-001",
                control_id="CTRL-HUMAN-OVERSIGHT",
                relationship=MappingRelationship.PARTIAL,
                review_status=ClauseReviewStatus.APPROVED,
            )
        ],
    )
    policy = EnterprisePolicy(
        policy_id="POL-001",
        tenant_id=tenant,
        name="Internal Governance Standard",
        version="1.0.0",
        clauses=[clause],
    )
    baseline = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Mapped Without Facets Baseline",
        policies=[policy],
        status="active",
    )

    qbank = _make_question_bank([
        "Does the system have general human oversight?"
    ])

    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=qbank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )

    assert clause.clause_id in cov.applicable_enterprise_requirement_ids
    clause_gaps = [g for g in cov.enterprise_gaps if g.policy_clause_id == clause.clause_id]
    assert len(clause_gaps) == 1, "Mapped clause without explicit facets must not silently bypass gap assessment"
    assert clause_gaps[0].status == "in_review"
    assert "mapping_incomplete" in clause_gaps[0].missing_facets

    clause_evals = {e.clause_id: e for e in getattr(cov, "enterprise_clause_coverage", [])}
    assert clause_evals[clause.clause_id].coverage_status == CoverageStatus.MAPPING_INCOMPLETE


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 12: Approved and unmapped Clause
# ─────────────────────────────────────────────────────────────────────────────
def test_12_approved_unmapped_clause_preserved_and_marked_for_review(regulatory_pack):
    """Scenario 12: An approved unmapped clause must remain visible in assessment scope,
    preserve its source and approval, and be marked MAPPING_INCOMPLETE for review even if
    a question shares an isolated non-generic word.
    """
    tenant = f"tenant-s12-{uuid.uuid4()}"
    clause = EnterpriseClause(
        clause_id="CLAUSE-UNMAPPED-012",
        policy_id="POL-012",
        tenant_id=tenant,
        source_name="Cultural Heritage AI Policy",
        text="All algorithmic decisions involving regional heritage sites must be reviewed by the Cultural Advisory Council.",
        mandatory=True,
        review_status=ClauseReviewStatus.APPROVED,
        is_unmapped=True,
        control_facets=[],
        control_mappings=[],
    )
    policy = EnterprisePolicy(
        policy_id="POL-012",
        tenant_id=tenant,
        name="Cultural Heritage AI Policy",
        version="1.0.0",
        clauses=[clause],
    )
    baseline = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Unmapped Policy Baseline",
        policies=[policy],
        status="active",
    )

    # Question shares words 'regional' and 'sites' but is completely unrelated
    qbank = _make_question_bank([
        "Are regional data centre sites monitored for power redundancy?"
    ])

    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=qbank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )

    assert clause.clause_id in cov.applicable_enterprise_requirement_ids
    clause_gaps = [g for g in cov.enterprise_gaps if g.policy_clause_id == clause.clause_id]
    assert len(clause_gaps) == 1
    assert clause_gaps[0].status == "in_review"

    clause_evals = {e.clause_id: e for e in getattr(cov, "enterprise_clause_coverage", [])}
    assert clause_evals[clause.clause_id].coverage_status == CoverageStatus.MAPPING_INCOMPLETE


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 13: Multiple candidate questions collectively covering separate facets
# ─────────────────────────────────────────────────────────────────────────────
def test_13_multiple_questions_collectively_covering_separate_facets(regulatory_pack):
    """Scenario 13: Separate questions in the questionnaire collectively satisfy different
    required facets and constraints of an approved enterprise clause.
    """
    tenant = f"tenant-s13-{uuid.uuid4()}"
    _, baseline = _make_approved_policy_and_baseline(
        tenant,
        "All automated customer refund transactions exceeding AUD 500 require Senior Manager "
        "human approval prior to execution.",
    )
    clause = baseline.clause_snapshots[0]

    qbank = _make_question_bank([
        "Do automated customer refund transactions exceeding AUD 500 require mandatory human approval by a Senior Manager?",
        "Does the workflow enforce a pre-execution block so transactions cannot proceed prior to approval?",
    ])

    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=qbank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
        use_case=BankingUseCase(
            name="Refund Agent",
            apra_regulated=True,
            approval_threshold_aud=500.0,
            approval_threshold_operator=">",
            approval_timing="pre_execution",
            approval_role="Senior Manager",
        ),
    )

    q_gaps = [
        g for g in cov.enterprise_gaps
        if g.policy_clause_id == clause.clause_id and g.gap_type == GapType.QUESTIONNAIRE
    ]
    assert len(q_gaps) == 0

    clause_evals = {e.clause_id: e for e in getattr(cov, "enterprise_clause_coverage", [])}
    assert clause_evals[clause.clause_id].coverage_status == CoverageStatus.COVERED


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 14: Candidate text that is semantically related but insufficient
# ─────────────────────────────────────────────────────────────────────────────
def test_14_semantically_related_but_insufficient_candidate_marked_needs_review(regulatory_pack):
    """Scenario 14: Candidate question text that is topically related ('application logging')
    but does not establish required facet coverage ('prompt_logging') is marked
    NEEDS_REVIEW, not COVERED and not collapsed into MISSING.
    """
    tenant = f"tenant-s14-{uuid.uuid4()}"
    _, baseline = _make_approved_policy_and_baseline(
        tenant,
        "All user prompts sent to third-party LLMs must undergo prompt logging and telemetry.",
    )
    clause = baseline.clause_snapshots[0]
    assert "prompt_logging" in clause.control_facets

    qbank = _make_question_bank([
        "Does the engineering team maintain general application logging for system debugging?"
    ])

    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=qbank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )

    clause_gaps = [g for g in cov.enterprise_gaps if g.policy_clause_id == clause.clause_id]
    assert len(clause_gaps) == 1
    assert "prompt_logging" in clause_gaps[0].missing_facets

    clause_evals = {e.clause_id: e for e in getattr(cov, "enterprise_clause_coverage", [])}
    assert clause_evals[clause.clause_id].coverage_status == CoverageStatus.NEEDS_REVIEW


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 15: No candidate question
# ─────────────────────────────────────────────────────────────────────────────
def test_15_no_candidate_question_marked_confirmed_missing(regulatory_pack):
    """Scenario 15: When no candidate question in the questionnaire relates to the required
    facets at all, the clause is classified as CONFIRMED MISSING (CoverageStatus.MISSING).
    """
    tenant = f"tenant-s15-{uuid.uuid4()}"
    _, baseline = _make_approved_policy_and_baseline(
        tenant,
        "All automated customer refund transactions exceeding AUD 500 require human approval prior to execution.",
    )
    clause = baseline.clause_snapshots[0]

    qbank = _make_question_bank([
        "What is the physical server rack ambient temperature in the primary data centre?"
    ])

    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=qbank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )

    clause_gaps = [
        g for g in cov.enterprise_gaps
        if g.policy_clause_id == clause.clause_id and g.gap_type == GapType.QUESTIONNAIRE
    ]
    assert len(clause_gaps) == 1
    assert clause_gaps[0].status == "open"

    clause_evals = {e.clause_id: e for e in getattr(cov, "enterprise_clause_coverage", [])}
    assert clause_evals[clause.clause_id].coverage_status == CoverageStatus.MISSING


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 16: Conditional or exempt requirement
# ─────────────────────────────────────────────────────────────────────────────
def test_16_conditional_and_exempt_requirements_preserve_semantics(regulatory_pack):
    """Scenario 16: Conditional requirements preserve condition/exception metadata, and
    exempt/non-applicable clauses are recorded with NOT_APPLICABLE status rather than
    generating false positive gaps or false confirmed coverage.
    """
    tenant = f"tenant-s16-{uuid.uuid4()}"
    pol = extract_enterprise_policy(
        tenant_id=tenant,
        name="Conditional & Exempt Policy",
        text=(
            "In the event of Severity 1 core banking downtime, human approval is required for "
            "transactions above AUD 5,000 unless an authorised exception applies.\n\n"
            "Low-risk internal sandbox experiments are exempt from secondary human approval."
        ),
    )
    for c in pol.clauses:
        c.review_status = ClauseReviewStatus.APPROVED
        for m in c.control_mappings:
            m.review_status = ClauseReviewStatus.APPROVED

    baseline = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Conditional & Exempt Baseline",
        policies=[pol],
        status="active",
    )

    cond_clause = baseline.clause_snapshots[0]
    exempt_clause = baseline.clause_snapshots[1]
    assert cond_clause.is_conditional is True
    assert cond_clause.has_exception_clause is True
    assert exempt_clause.mandatory is False
    assert exempt_clause.has_exception_clause is True

    qbank = _make_question_bank([
        "What is the physical server rack ambient temperature?"
    ])

    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        question_bank=qbank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )

    clause_evals = {e.clause_id: e for e in getattr(cov, "enterprise_clause_coverage", [])}
    assert cond_clause.clause_id in clause_evals
    assert clause_evals[cond_clause.clause_id].is_conditional is True
    assert clause_evals[cond_clause.clause_id].has_exception_clause is True

    # Exempt clause is tracked as NOT_APPLICABLE and does not generate a false gap
    assert exempt_clause.clause_id in clause_evals
    assert clause_evals[exempt_clause.clause_id].coverage_status == CoverageStatus.NOT_APPLICABLE
    assert not any(g.policy_clause_id == exempt_clause.clause_id for g in cov.enterprise_gaps)


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 17: Regulatory-Only with no Enterprise Baseline
# ─────────────────────────────────────────────────────────────────────────────
def test_17_regulatory_only_with_no_enterprise_baseline(client: TestClient):
    """Scenario 17: Regulatory-Only assessment with no Enterprise Baseline runs cleanly
    and isolates regulatory obligations from any enterprise state.
    """
    tenant = f"tenant-s17-{uuid.uuid4()}"
    res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "regulatory_only",
            "use_case": {"apra_regulated": True, "handles_personal_information": True},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["assessment_mode"] == "regulatory_only"
    assert data["enterprise_baseline_id"] is None
    assert data["applicable_enterprise_requirement_ids"] == []
    assert data["enterprise_gaps"] == []
    assert data.get("enterprise_clause_coverage", []) == []
    assert len(data["applicable_obligation_ids"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 18: Enterprise-Enhanced with approved tenant baseline
# ─────────────────────────────────────────────────────────────────────────────
def test_18_enterprise_enhanced_with_approved_tenant_baseline(client: TestClient):
    """Scenario 18: Enterprise-Enhanced mode with an approved tenant baseline and approved
    control mapping evaluates both regulatory obligations and enterprise requirements.
    """
    tenant = f"tenant-s18-{uuid.uuid4()}"
    res_p = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Delegated Authority Standard",
            "text": "All automated refund transactions exceeding AUD 500 require Senior Manager human approval prior to execution.",
            "version": "1.0.0",
        },
    )
    assert res_p.status_code == 201
    pol_id = res_p.json()["policy_id"]
    clause_data = res_p.json()["clauses"][0]
    clause_id = clause_data["clause_id"]
    mapping_id = clause_data["control_mappings"][0]["mapping_id"]

    # Approve clause and mapping
    client.put(
        f"/v1/enterprise/clauses/{clause_id}/review",
        headers={"X-Tenant-ID": tenant},
        json={"status": "approved", "actor": "grc@bank.example", "role": "compliance"},
    )
    client.put(
        f"/v1/enterprise/clauses/{clause_id}/mappings/{mapping_id}/review",
        headers={"X-Tenant-ID": tenant},
        json={"status": "approved", "actor": "grc@bank.example", "role": "compliance"},
    )

    res_bl = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant},
        json={"name": "Approved Tenant Baseline", "policy_ids": [pol_id], "version": "1.0.0"},
    )
    assert res_bl.status_code == 201
    bl_id = res_bl.json()["baseline_id"]
    assert len(res_bl.json()["confirmed_control_ids"]) > 0

    res_cov = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "enterprise_baseline_version": "1.0.0",
            "use_case": {"apra_regulated": True, "approval_threshold_aud": 500.0},
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res_cov.status_code == 201
    cov_data = res_cov.json()
    assert cov_data["assessment_mode"] == "enterprise_enhanced"
    assert cov_data["enterprise_baseline_id"] == bl_id
    assert clause_id in cov_data["applicable_enterprise_requirement_ids"]
    assert len(cov_data.get("enterprise_clause_coverage", [])) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 19: Cross-tenant Mapping access
# ─────────────────────────────────────────────────────────────────────────────
def test_19_cross_tenant_mapping_access_strictly_rejected(client: TestClient):
    """Scenario 19: A tenant cannot review, approve, reject, or compile control mappings
    belonging to another tenant.
    """
    tenant_a = f"tenant-a-{uuid.uuid4()}"
    tenant_b = f"tenant-b-{uuid.uuid4()}"

    res_p = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant_a},
        json={
            "name": "Tenant A Confidential Policy",
            "text": "All automated refunds exceeding AUD 500 require human approval.",
        },
    )
    assert res_p.status_code == 201
    clause_data = res_p.json()["clauses"][0]
    clause_id = clause_data["clause_id"]
    mapping_id = clause_data["control_mappings"][0]["mapping_id"]

    # Tenant B attempts to review Tenant A's control mapping -> 404
    res_cross_map = client.put(
        f"/v1/enterprise/clauses/{clause_id}/mappings/{mapping_id}/review",
        headers={"X-Tenant-ID": tenant_b},
        json={"status": "approved", "actor": "attacker@tenant-b", "role": "admin"},
    )
    assert res_cross_map.status_code == 404

    # Tenant B attempts to review Tenant A's clause -> 404
    res_cross_clause = client.put(
        f"/v1/enterprise/clauses/{clause_id}/review",
        headers={"X-Tenant-ID": tenant_b},
        json={"status": "approved", "actor": "attacker@tenant-b", "role": "admin"},
    )
    assert res_cross_clause.status_code == 404

    # Verify Tenant A's mapping remains proposed
    clauses_a = client.get(
        f"/v1/enterprise/policies/{res_p.json()['policy_id']}/clauses",
        headers={"X-Tenant-ID": tenant_a},
    ).json()
    assert clauses_a[0]["review_status"] == "proposed"
    assert clauses_a[0]["control_mappings"][0]["review_status"] == "proposed"


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 20: Existing baseline version and provenance integrity
# ─────────────────────────────────────────────────────────────────────────────
def test_20_baseline_version_and_mapping_snapshot_fingerprint_integrity(client: TestClient):
    """Scenario 20: Baseline cryptographic fingerprint covers clause_snapshots AND their
    control_mappings. Tampering with a mapping's review_status or control_id invalidates
    the baseline fingerprint (HTTP 422), and post-publication mapping reviews do not
    mutate historical baseline snapshots.
    """
    tenant = f"tenant-s20-{uuid.uuid4()}"
    res_p = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Snapshot Integrity Policy",
            "text": "All automated refunds exceeding AUD 500 require human approval prior to execution.",
            "version": "1.0.0",
        },
    )
    assert res_p.status_code == 201
    pol_id = res_p.json()["policy_id"]
    clause_data = res_p.json()["clauses"][0]
    clause_id = clause_data["clause_id"]
    mapping_id = clause_data["control_mappings"][0]["mapping_id"]

    # Approve clause only (mapping stays proposed in v1.0.0)
    client.put(
        f"/v1/enterprise/clauses/{clause_id}/review",
        headers={"X-Tenant-ID": tenant},
        json={"status": "approved", "actor": "grc@bank.example", "role": "compliance"},
    )

    res_bl = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant},
        json={"name": "Immutable Baseline", "policy_ids": [pol_id], "version": "1.0.0"},
    )
    assert res_bl.status_code == 201
    bl_id = res_bl.json()["baseline_id"]

    bl_v1 = store.get_enterprise_baseline(tenant, bl_id)
    assert verify_baseline_integrity(bl_v1) is True
    assert bl_v1.clause_snapshots[0].control_mappings[0].review_status == ClauseReviewStatus.PROPOSED

    # Approve the mapping in the live store AFTER baseline v1 was compiled
    res_map = client.put(
        f"/v1/enterprise/clauses/{clause_id}/mappings/{mapping_id}/review",
        headers={"X-Tenant-ID": tenant},
        json={"status": "approved", "actor": "grc@bank.example", "role": "compliance"},
    )
    assert res_map.status_code == 200

    # Historical baseline v1 snapshot MUST remain unchanged (mapping still PROPOSED)
    bl_v1_after = store.get_enterprise_baseline(tenant, bl_id)
    assert bl_v1_after.clause_snapshots[0].control_mappings[0].review_status == ClauseReviewStatus.PROPOSED
    assert verify_baseline_integrity(bl_v1_after) is True

    # Tampering with a mapping's review_status inside the snapshot must fail integrity check
    tampered_mapping = bl_v1_after.clause_snapshots[0].control_mappings[0].model_copy(
        update={"review_status": ClauseReviewStatus.APPROVED}
    )
    tampered_clause = bl_v1_after.clause_snapshots[0].model_copy(
        update={"control_mappings": [tampered_mapping]}
    )
    tampered_bl = bl_v1_after.model_copy(update={"clause_snapshots": [tampered_clause]})
    assert verify_baseline_integrity(tampered_bl) is False

    store._enterprise_baselines[tenant][bl_id] = tampered_bl
    res_eval = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": bl_id,
            "questionnaire_pack": "DEMO_BANKING_V1",
            "persist": False,
        },
    )
    assert res_eval.status_code == 422
    assert "cryptographic fingerprint mismatch" in res_eval.json()["detail"]
