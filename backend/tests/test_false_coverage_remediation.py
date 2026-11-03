"""Test suite for Prompt 2D: P0 False-Coverage Prevention & Numeric Control Validation.

Covers:
1. Re-evaluated Negation Filter & Semantic Interpretation (Categories A through F):
   - A: Absence of required control ("does not require human approval")
   - B: Mandatory prohibitions / pre-execution blocks ("must not execute before approval", "is prohibited")
   - C: Conditional requirements with exceptions ("above AUD 500 unless an authorised exception applies")
   - D: Unimplemented controls ("required, but workflow has not yet been implemented")
   - E: Policy exemptions ("low-risk sandbox transactions are exempt")
   - F: Mere topic references ("is considering introducing human approval")
2. Numeric Approval Threshold Validation (12 Scenarios):
   - 1: AUD 500 (policy) vs AUD 1,000 (use case)
   - 2: Equal thresholds (AUD 500 vs AUD 500)
   - 3: Stricter use case (AUD 250 vs AUD 500)
   - 4: Boundary operators (> vs >=)
   - 5: Missing threshold values
   - 6: Currency mismatch (USD vs AUD)
   - 7: Conditional thresholds
   - 8: Approved exceptions
   - 9: Conflicting enterprise policies in baseline
   - 10: Approval timing (pre-execution vs post-execution)
   - 11: Authority roles (Senior Manager vs Customer Service Agent)
   - 12: Unapproved baseline requirements (strict approval gating)
3. Dual-Mode Isolation:
   - Mode A (Regulatory-Only) remains completely independent of enterprise thresholds and baselines
   - Mode B (Enterprise-Enhanced) strictly evaluates approved baseline constraints
"""

import uuid
from typing import Generator
import pytest
from fastapi.testclient import TestClient

from banking_crosswalk.app import app
from banking_crosswalk.catalog import load_aiaf_question_bank, load_regulatory_pack
from banking_crosswalk.coverage import evaluate_questionnaire_coverage
from banking_crosswalk.models import (
    BankingUseCase,
    ClauseReviewStatus,
    GapType,
)
from banking_crosswalk.policy import (
    compile_enterprise_baseline,
    extract_enterprise_policy,
)
from banking_crosswalk.store import store


@pytest.fixture(autouse=True)
def reset_in_memory_store():
    store.reset()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def test_question_bank():
    return load_aiaf_question_bank()


@pytest.fixture
def regulatory_pack():
    return load_regulatory_pack()


# ─────────────────────────────────────────────────────────────────────────────
# PART 1: NEGATION FILTER & SEMANTIC INTERPRETATION (CATEGORIES A THROUGH F)
# ─────────────────────────────────────────────────────────────────────────────

def test_category_a_absence_of_control():
    """Category A: 'does not require human approval' must not be treated as a positive control."""
    policy = extract_enterprise_policy(
        tenant_id="tenant-eval",
        name="Sandbox Policy",
        text="This standalone sandbox environment does not require human approval.",
    )
    clause = policy.clauses[0]
    assert clause.mandatory is False
    assert clause.control_facets == []
    assert len(clause.control_mappings) == 0


def test_category_b_mandatory_prohibitions():
    """Category B: Mandatory prohibitions must not be discarded because they contain 'must not' or 'is prohibited'."""
    # Pre-execution block with 'must not execute'
    pol1 = extract_enterprise_policy(
        tenant_id="tenant-eval",
        name="Refund Policy",
        text="The agent must not execute a refund before human approval.",
    )
    c1 = pol1.clauses[0]
    assert c1.mandatory is True
    assert "human_approval_required" in c1.control_facets
    assert "pre_execution_block" in c1.control_facets
    assert len(c1.control_mappings) > 0

    # Prohibition with 'is prohibited'
    pol2 = extract_enterprise_policy(
        tenant_id="tenant-eval",
        name="Dispute Policy",
        text="Executing refunds prior to human approval is prohibited.",
    )
    c2 = pol2.clauses[0]
    assert c2.mandatory is True
    assert "human_approval_required" in c2.control_facets
    assert "pre_execution_block" in c2.control_facets
    assert len(c2.control_mappings) > 0

    # Mandatory circumvention ban
    pol3 = extract_enterprise_policy(
        tenant_id="tenant-eval",
        name="Oversight Policy",
        text="Under no circumstances shall human approval be bypassed or omitted for credit decisions.",
    )
    c3 = pol3.clauses[0]
    assert c3.mandatory is True
    assert "human_approval_required" in c3.control_facets
    assert len(c3.control_mappings) > 0


def test_category_c_conditional_requirement_with_exceptions():
    """Category C: Conditional requirements preserve condition and exception descriptions."""
    policy = extract_enterprise_policy(
        tenant_id="tenant-eval",
        name="Threshold Policy",
        text="Transactions above AUD 500 require approval unless an authorised exception applies.",
    )
    clause = policy.clauses[0]
    assert clause.mandatory is True
    assert 500.0 in clause.thresholds_aud
    assert "approval_threshold_defined" in clause.control_facets
    assert clause.has_exception_clause is True
    assert "unless an authorised exception applies" in (clause.exception_description or "").lower()


def test_category_d_unimplemented_control_detection():
    """Category D: Unimplemented controls are identified while marking implementation as absent."""
    policy = extract_enterprise_policy(
        tenant_id="tenant-eval",
        name="Implementation Roadmap",
        text="Human approval is required, but the workflow has not yet been implemented.",
    )
    clause = policy.clauses[0]
    assert clause.mandatory is True
    assert "human_approval_required" in clause.control_facets
    assert clause.implementation_status == "unimplemented"


def test_category_e_policy_exemption():
    """Category E: Policy exemptions evaluate against scope and do not create positive controls."""
    policy = extract_enterprise_policy(
        tenant_id="tenant-eval",
        name="Sandbox Governance",
        text="Low-risk sandbox transactions are exempt from secondary review.",
    )
    clause = policy.clauses[0]
    assert clause.mandatory is False
    assert clause.control_facets == []
    assert len(clause.control_mappings) == 0
    assert clause.has_exception_clause is True


def test_category_f_mere_topic_reference():
    """Category F: Mere topic references do not generate binding control mappings."""
    policy = extract_enterprise_policy(
        tenant_id="tenant-eval",
        name="Strategy Whitepaper",
        text="The organisation is considering introducing human approval.",
    )
    clause = policy.clauses[0]
    assert clause.mandatory is False
    assert clause.control_facets == []
    assert len(clause.control_mappings) == 0


# ─────────────────────────────────────────────────────────────────────────────
# PART 2: NUMERIC APPROVAL THRESHOLD VALIDATION (12 SCENARIOS)
# ─────────────────────────────────────────────────────────────────────────────

def _build_approved_baseline(tenant_id: str, clause_text: str):
    """Helper to build an approved enterprise baseline with a single clause."""
    pol = extract_enterprise_policy(
        tenant_id=tenant_id,
        name="Approved Policy",
        text=clause_text,
    )
    for c in pol.clauses:
        c.review_status = ClauseReviewStatus.APPROVED
        for m in c.control_mappings:
            m.review_status = ClauseReviewStatus.APPROVED
    baseline = compile_enterprise_baseline(
        tenant_id=tenant_id,
        name="Approved Baseline",
        policies=[pol],
    )
    return baseline, pol


def test_scenario_01_aud_500_vs_aud_1000(regulatory_pack, test_question_bank):
    """Scenario 1: Policy requires approval > AUD 500, use case is AUD 1,000 (looser -> conflict)."""
    tenant = f"tenant-sc1-{uuid.uuid4()}"
    baseline, pol = _build_approved_baseline(
        tenant,
        "Human approval is required for all automated payment refund executions exceeding AUD 500.",
    )
    use_case = BankingUseCase(
        name="Refund Agent",
        apra_regulated=True,
        approval_threshold_aud=1000.0,
        approval_threshold_operator=">",
    )
    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        use_case=use_case,
        question_bank=test_question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )

    conflict_gaps = [g for g in cov.enterprise_gaps if g.gap_type == GapType.CONTROL_CONFLICT]
    assert len(conflict_gaps) == 1
    gap = conflict_gaps[0]
    assert gap.required_threshold == 500.0
    assert gap.use_case_threshold == 1000.0
    assert gap.severity == "critical"
    assert "exceeds approved policy threshold" in gap.title
    assert "exposure interval: 500 to 1000" in gap.recommendation


def test_scenario_02_equal_thresholds(regulatory_pack, test_question_bank):
    """Scenario 2: Policy requires approval > AUD 500, use case configured for > AUD 500 (compliant)."""
    tenant = f"tenant-sc2-{uuid.uuid4()}"
    baseline, _ = _build_approved_baseline(
        tenant,
        "Human approval is required for all automated refunds exceeding AUD 500.",
    )
    use_case = BankingUseCase(
        name="Refund Agent",
        apra_regulated=True,
        approval_threshold_aud=500.0,
        approval_threshold_operator=">",
    )
    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        use_case=use_case,
        question_bank=test_question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )
    conflict_gaps = [g for g in cov.enterprise_gaps if g.gap_type == GapType.CONTROL_CONFLICT]
    assert len(conflict_gaps) == 0


def test_scenario_03_stricter_use_case_threshold(regulatory_pack, test_question_bank):
    """Scenario 3: Policy requires approval > AUD 500, use case triggers at > AUD 250 (stricter -> compliant)."""
    tenant = f"tenant-sc3-{uuid.uuid4()}"
    baseline, _ = _build_approved_baseline(
        tenant,
        "Human approval is required for all automated refunds exceeding AUD 500.",
    )
    use_case = BankingUseCase(
        name="Refund Agent",
        apra_regulated=True,
        approval_threshold_aud=250.0,
        approval_threshold_operator=">",
    )
    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        use_case=use_case,
        question_bank=test_question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )
    conflict_gaps = [g for g in cov.enterprise_gaps if g.gap_type == GapType.CONTROL_CONFLICT]
    assert len(conflict_gaps) == 0


def test_scenario_04_boundary_operators(regulatory_pack, test_question_bank):
    """Scenario 4: Greater-than vs greater-than-or-equal-to boundary operator mismatch."""
    tenant = f"tenant-sc4-{uuid.uuid4()}"
    # Sub-case 4A: Policy is >= 500, Use case is > 500 (boundary mismatch: $500 executes unapproved)
    baseline, _ = _build_approved_baseline(
        tenant,
        "Human approval is required for all automated refunds at or above AUD 500.",
    )
    use_case_mismatch = BankingUseCase(
        name="Refund Agent",
        apra_regulated=True,
        approval_threshold_aud=500.0,
        approval_threshold_operator=">",
    )
    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        use_case=use_case_mismatch,
        question_bank=test_question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )
    boundary_gaps = [g for g in cov.enterprise_gaps if g.gap_type == GapType.CONTROL_CONFLICT]
    assert len(boundary_gaps) == 1
    assert "boundary operator" in boundary_gaps[0].title

    # Sub-case 4B: Policy is > 500, Use case is >= 500 (stricter at boundary -> compliant)
    baseline_gt, _ = _build_approved_baseline(
        tenant,
        "Human approval is required for all automated refunds exceeding AUD 500.",
    )
    use_case_stricter = BankingUseCase(
        name="Refund Agent",
        apra_regulated=True,
        approval_threshold_aud=500.0,
        approval_threshold_operator=">=",
    )
    cov_gt = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        use_case=use_case_stricter,
        question_bank=test_question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline_gt,
        assessment_mode="enterprise_enhanced",
    )
    boundary_gaps_gt = [g for g in cov_gt.enterprise_gaps if g.gap_type == GapType.CONTROL_CONFLICT]
    assert len(boundary_gaps_gt) == 0


def test_scenario_05_missing_threshold_values(regulatory_pack, test_question_bank):
    """Scenario 5: Missing threshold values generate explicit unverified gap, not silent pass."""
    tenant = f"tenant-sc5-{uuid.uuid4()}"
    baseline, _ = _build_approved_baseline(
        tenant,
        "Human approval is required for all automated refunds exceeding AUD 500.",
    )
    use_case_unconfigured = BankingUseCase(
        name="Refund Agent",
        apra_regulated=True,
        approval_threshold_aud=None,
    )
    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        use_case=use_case_unconfigured,
        question_bank=test_question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )
    missing_gaps = [g for g in cov.enterprise_gaps if g.gap_type == GapType.CONTROL_CONFLICT]
    assert len(missing_gaps) == 1
    assert "is not configured" in missing_gaps[0].title


def test_scenario_06_different_currencies(regulatory_pack, test_question_bank):
    """Scenario 6: Currency mismatch (USD vs AUD) flags conversion risk without assuming 1:1."""
    tenant = f"tenant-sc6-{uuid.uuid4()}"
    baseline, pol = _build_approved_baseline(
        tenant,
        "Human approval is required for all automated transactions exceeding USD 500.",
    )
    use_case_aud = BankingUseCase(
        name="Refund Agent",
        apra_regulated=True,
        approval_threshold_aud=500.0,
        approval_threshold_currency="AUD",
    )
    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        use_case=use_case_aud,
        question_bank=test_question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )
    curr_gaps = [g for g in cov.enterprise_gaps if g.gap_type == GapType.CONTROL_CONFLICT]
    assert len(curr_gaps) == 1
    assert "currency mismatch" in curr_gaps[0].title


def test_scenario_07_conditional_thresholds(regulatory_pack, test_question_bank):
    """Scenario 7: Conditional thresholds preserve condition description."""
    tenant = f"tenant-sc7-{uuid.uuid4()}"
    baseline, _ = _build_approved_baseline(
        tenant,
        "In the event of Severity 1 core banking downtime, human approval is required for transactions above AUD 5,000.",
    )
    assert baseline.clause_snapshots[0].is_conditional is True
    assert "Severity 1" in (baseline.clause_snapshots[0].condition_description or "")


def test_scenario_08_approved_exceptions(regulatory_pack, test_question_bank):
    """Scenario 8: Approved exceptions mitigate threshold conflict and transition gap to in_review."""
    tenant = f"tenant-sc8-{uuid.uuid4()}"
    baseline, _ = _build_approved_baseline(
        tenant,
        "Human approval is required for all automated refunds exceeding AUD 500.",
    )
    use_case_excepted = BankingUseCase(
        name="Refund Agent",
        apra_regulated=True,
        approval_threshold_aud=1000.0,
        has_approved_exception=True,
        exception_reference="EXC-2026-089",
    )
    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        use_case=use_case_excepted,
        question_bank=test_question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )
    conflict_gaps = [g for g in cov.enterprise_gaps if g.gap_type == GapType.CONTROL_CONFLICT]
    assert len(conflict_gaps) == 1
    assert conflict_gaps[0].status == "in_review"
    assert "EXC-2026-089" in conflict_gaps[0].recommendation


def test_scenario_09_conflicting_enterprise_policies(regulatory_pack, test_question_bank):
    """Scenario 9: Conflicting thresholds across baseline policies raise internal conflict gap."""
    tenant = f"tenant-sc9-{uuid.uuid4()}"
    pol1 = extract_enterprise_policy(
        tenant_id=tenant,
        name="Policy 1",
        text="All customer refunds exceeding AUD 500 require human approval.",
    )
    pol2 = extract_enterprise_policy(
        tenant_id=tenant,
        name="Policy 2",
        text="All customer refunds exceeding AUD 750 require human approval.",
    )
    for p in (pol1, pol2):
        for c in p.clauses:
            c.review_status = ClauseReviewStatus.APPROVED
            for m in c.control_mappings:
                m.review_status = ClauseReviewStatus.APPROVED

    baseline = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Conflicting Baseline",
        policies=[pol1, pol2],
    )
    use_case = BankingUseCase(
        name="Refund Agent",
        apra_regulated=True,
        approval_threshold_aud=500.0,
    )
    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        use_case=use_case,
        question_bank=test_question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )
    internal_conflicts = [
        g for g in cov.enterprise_gaps
        if g.gap_type == GapType.CONTROL_CONFLICT and g.source_type == "internal_conflict"
    ]
    assert len(internal_conflicts) == 1
    assert "[500.0, 750.0]" in internal_conflicts[0].recommendation


def test_scenario_10_approval_timing_pre_vs_post_execution(regulatory_pack, test_question_bank):
    """Scenario 10: Policy requires pre-execution blocking, use case implements post-execution review."""
    tenant = f"tenant-sc10-{uuid.uuid4()}"
    baseline, _ = _build_approved_baseline(
        tenant,
        "Human approval is required prior to payment execution for all transactions exceeding AUD 500.",
    )
    use_case_post = BankingUseCase(
        name="Refund Agent",
        apra_regulated=True,
        approval_threshold_aud=500.0,
        approval_timing="post_execution",
    )
    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        use_case=use_case_post,
        question_bank=test_question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )
    timing_gaps = [
        g for g in cov.enterprise_gaps
        if g.gap_type == GapType.CONTROL_CONFLICT and "timing mismatch" in g.title
    ]
    assert len(timing_gaps) == 1
    assert timing_gaps[0].timing_required == "pre_execution"
    assert timing_gaps[0].use_case_timing == "post_execution"


def test_scenario_11_authority_roles(regulatory_pack, test_question_bank):
    """Scenario 11: Policy requires Senior Manager, use case configures Customer Service Agent."""
    tenant = f"tenant-sc11-{uuid.uuid4()}"
    baseline, _ = _build_approved_baseline(
        tenant,
        "All automated customer refunds exceeding AUD 1,000 require senior manager approval.",
    )
    use_case_agent = BankingUseCase(
        name="Refund Agent",
        apra_regulated=True,
        approval_threshold_aud=1000.0,
        approval_role="Customer Service Agent",
    )
    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        use_case=use_case_agent,
        question_bank=test_question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )
    role_gaps = [
        g for g in cov.enterprise_gaps
        if g.gap_type == GapType.CONTROL_CONFLICT and "role mismatch" in g.title
    ]
    assert len(role_gaps) == 1
    assert role_gaps[0].role_required == "Senior Manager"
    assert role_gaps[0].use_case_role == "Customer Service Agent"


def test_scenario_12_unapproved_baseline_requirements_gated(regulatory_pack, test_question_bank):
    """Scenario 12: Unapproved baseline requirements do NOT generate confirmed conflict gaps."""
    tenant = f"tenant-sc12-{uuid.uuid4()}"
    pol = extract_enterprise_policy(
        tenant_id=tenant,
        name="Proposed Policy",
        text="Human approval is required for refunds exceeding AUD 500.",
    )
    # Clause is left as PROPOSED (not approved)
    baseline = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Draft Baseline",
        policies=[pol],
    )
    use_case = BankingUseCase(
        name="Refund Agent",
        apra_regulated=True,
        approval_threshold_aud=1000.0,  # Looser than proposed 500
    )
    cov = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        use_case=use_case,
        question_bank=test_question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )
    # Strict gating: Unapproved requirement must NOT generate confirmed conflict gaps
    confirmed_conflicts = [
        g for g in cov.enterprise_gaps
        if g.gap_type == GapType.CONTROL_CONFLICT and g.status == "open"
    ]
    assert len(confirmed_conflicts) == 0


# ─────────────────────────────────────────────────────────────────────────────
# PART 3: DUAL-MODE ISOLATION (REGULATORY-ONLY VS ENTERPRISE-ENHANCED)
# ─────────────────────────────────────────────────────────────────────────────

def test_dual_mode_isolation_mode_a_ignores_enterprise_thresholds(
    regulatory_pack, test_question_bank
):
    """Mode A (Regulatory-Only) must NEVER produce enterprise threshold conflicts."""
    tenant = f"tenant-iso-{uuid.uuid4()}"
    baseline, _ = _build_approved_baseline(
        tenant,
        "Human approval is required for all automated refunds exceeding AUD 500.",
    )
    # Use case has a looser threshold (1000 vs 500)
    use_case = BankingUseCase(
        name="Refund Agent",
        apra_regulated=True,
        approval_threshold_aud=1000.0,
    )
    # Mode A: regulatory_only
    cov_a = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        use_case=use_case,
        question_bank=test_question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="regulatory_only",
    )
    assert cov_a.assessment_mode == "regulatory_only"
    assert cov_a.enterprise_baseline_id is None
    assert len(cov_a.enterprise_gaps) == 0
    assert not any(g.gap_type == GapType.CONTROL_CONFLICT for g in cov_a.gaps)

    # Mode B: enterprise_enhanced
    cov_b = evaluate_questionnaire_coverage(
        tenant_id=tenant,
        use_case=use_case,
        question_bank=test_question_bank,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
        assessment_mode="enterprise_enhanced",
    )
    assert cov_b.assessment_mode == "enterprise_enhanced"
    assert cov_b.enterprise_baseline_id == baseline.baseline_id
    assert any(g.gap_type == GapType.CONTROL_CONFLICT for g in cov_b.enterprise_gaps)


# ─────────────────────────────────────────────────────────────────────────────
# PART 4: API INTEGRATION TESTS (ENDPOINTS & ERROR DETAILS)
# ─────────────────────────────────────────────────────────────────────────────

def test_api_threshold_conflict_in_enterprise_enhanced_mode(client: TestClient):
    """API test: Enterprise-Enhanced assessment returns structured threshold conflict."""
    tenant = f"tenant-api-{uuid.uuid4()}"

    # 1. Save questionnaire in store
    qbank = store.save_questionnaire(tenant, load_aiaf_question_bank())
    q_id = qbank.metadata.questionnaire_id

    # 2. Import policy with AUD 500 threshold
    p_res = client.post(
        "/v1/enterprise/policies/import",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Refund Limits Policy",
            "text": "Human approval is required for all customer refund credits exceeding AUD 500.",
            "version": "1.0.0",
        },
    )
    assert p_res.status_code == 201
    p_data = p_res.json()
    clause_id = p_data["clauses"][0]["clause_id"]

    # 3. Approve clause
    app_res = client.put(
        f"/v1/enterprise/clauses/{clause_id}/review",
        headers={"X-Tenant-ID": tenant},
        json={
            "status": "approved",
            "actor": "lead-counsel@bank.com.au",
            "role": "General Counsel",
            "review_comment": "Approved threshold",
        },
    )
    assert app_res.status_code == 200

    # 4. Compile baseline
    b_res = client.post(
        "/v1/enterprise/baselines",
        headers={"X-Tenant-ID": tenant},
        json={
            "name": "Production Control Baseline",
            "policy_ids": [p_data["policy_id"]],
            "version": "1.0.0",
            "status": "active",
        },
    )
    assert b_res.status_code == 201
    baseline_id = b_res.json()["baseline_id"]

    # 5. Evaluate assessment in Enterprise-Enhanced mode with AUD 1,000 use case
    ass_res = client.post(
        "/v1/assessments/coverage",
        headers={"X-Tenant-ID": tenant},
        json={
            "assessment_mode": "enterprise_enhanced",
            "enterprise_baseline_id": baseline_id,
            "questionnaire_id": q_id,
            "use_case": {
                "name": "Dispute and Refund Agent",
                "apra_regulated": True,
                "approval_threshold_aud": 1000.0,
                "approval_threshold_operator": ">",
            },
            "persist": False,
        },
    )
    assert ass_res.status_code == 201
    ass_data = ass_res.json()
    assert ass_data["assessment_mode"] == "enterprise_enhanced"

    # Verify conflict gap appears in enterprise_gaps
    conflicts = [
        g for g in ass_data["enterprise_gaps"]
        if g["gap_type"] == "control_conflict"
    ]
    assert len(conflicts) == 1
    assert conflicts[0]["required_threshold"] == 500.0
    assert conflicts[0]["use_case_threshold"] == 1000.0
    assert "exceeds approved policy threshold" in conflicts[0]["title"]
