"""Enterprise Requirement Reconciliation Engine & Effective Baseline Tests (E1).

Covers all 28 mandatory adversarial scenarios (Section 9), the synthetic
development + held-out evaluation benchmark (Section 11), and end-to-end API
and persistence verification across in-memory and relational stores.
"""

from __future__ import annotations

import uuid
from typing import List, Tuple

import pytest
from fastapi.testclient import TestClient

from banking_crosswalk.app import app
from banking_crosswalk.catalog import load_regulatory_pack
from banking_crosswalk.models import (
    AtomicObligation,
    Authority,
    BankingUseCase,
    ClauseControlMapping,
    ClauseReviewStatus,
    EnterpriseAuthorityLevel,
    EnterpriseBaseline,
    EnterpriseClause,
    EnterprisePolicy,
    MappingRelationship,
    ReconciliationDecisionStatus,
    ReconciliationRelationship,
)
from banking_crosswalk.policy import (
    compile_enterprise_baseline,
    extract_enterprise_policy,
)
from banking_crosswalk.reconciliation import (
    compose_effective_assessment_baseline,
    evaluate_reconciliation_staleness,
    generate_reconciliation_candidates,
    review_reconciliation_decision,
    validate_candidate_relationship,
)
from banking_crosswalk.store import NotFoundError, store


@pytest.fixture(autouse=True)
def reset_store():
    store.reset()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def regulatory_pack():
    return load_regulatory_pack()


def _make_approved_clause(
    *,
    tenant_id: str,
    text: str,
    control_id: str | None = "CTRL-PRIV-GOVERNANCE",
    control_facets: List[str] | None = None,
    mapping_status: ClauseReviewStatus = ClauseReviewStatus.APPROVED,
    clause_status: ClauseReviewStatus = ClauseReviewStatus.APPROVED,
    policy_name: str = "Enterprise AI Policy",
    policy_version: str = "1.0.0",
    thresholds_aud: List[float] | None = None,
    threshold_operator: str | None = None,
    threshold_currency: str | None = None,
    approval_timing: str | None = None,
    required_approval_role: str | None = None,
    is_conditional: bool = False,
    condition_description: str | None = None,
    has_exception_clause: bool = False,
    exception_description: str | None = None,
    mandatory: bool = True,
) -> Tuple[EnterprisePolicy, EnterpriseClause, EnterpriseBaseline]:
    pol_id = f"POL-{uuid.uuid4().hex[:8]}"
    cid = f"CLS-{uuid.uuid4().hex[:8]}"
    facets = list(control_facets or [])
    mappings: List[ClauseControlMapping] = []
    if control_id:
        mappings.append(
            ClauseControlMapping(
                mapping_id=f"MAP-{uuid.uuid4().hex[:8]}",
                tenant_id=tenant_id,
                clause_id=cid,
                control_id=control_id,
                relationship=MappingRelationship.FULL,
                mapped_facets=facets,
                review_status=mapping_status,
                reviewer_actor="reviewer@bank.example",
                reviewer_role="reviewer",
            )
        )
    clause = EnterpriseClause(
        clause_id=cid,
        policy_id=pol_id,
        tenant_id=tenant_id,
        source_name=policy_name,
        text=text,
        mandatory=mandatory,
        authority_level=EnterpriseAuthorityLevel.ENTERPRISE_POLICY,
        review_status=clause_status,
        control_facets=facets,
        thresholds_aud=list(thresholds_aud or []),
        threshold_operator=threshold_operator,
        threshold_currency=threshold_currency,
        approval_timing=approval_timing,
        required_approval_role=required_approval_role,
        is_conditional=is_conditional,
        condition_description=condition_description,
        has_exception_clause=has_exception_clause,
        exception_description=exception_description,
        is_unmapped=(control_id is None),
        control_mappings=mappings,
    )
    policy = EnterprisePolicy(
        policy_id=pol_id,
        tenant_id=tenant_id,
        name=policy_name,
        version=policy_version,
        clauses=[clause],
    )
    baseline = compile_enterprise_baseline(
        tenant_id=tenant_id,
        name=f"{policy_name} Baseline",
        policies=[policy],
        version="1.0.0",
    )
    return policy, clause, baseline


def _synthetic_threshold_obligation(
    *,
    obligation_id: str = "SYN-OB-FIN-1000",
    threshold_text: str = "All automated customer refund decisions above AUD 1,000 must obtain pre-execution Authorised Officer approval.",
    control_id: str = "CTRL-HUMAN-OVERSIGHT",
    facets: List[str] | None = None,
    authority: Authority = Authority.BINDING,
    legal_authority_classification: str = "binding_legal_or_prudential_obligation",
) -> AtomicObligation:
    return AtomicObligation(
        obligation_id=obligation_id,
        source_id="APRA-CPS230",
        instrument="Prudential Standard CPS 230",
        provision="Paragraph 34",
        title="Automated Refund Financial Delegation Gate",
        concise_obligation_summary=threshold_text,
        layer="australian_legislation",
        authority=authority,
        legal_authority_classification=legal_authority_classification,
        version="2026-07",
        source_url="https://www.apra.gov.au/standards/cps-230",
        effective_from="2026-07-01",
        applicability_key="apra_entity",
        applicability_conditions=["Entity is APRA-regulated"],
        control_id=control_id,
        control_objective="Enforce human approval gates on automated financial transactions.",
        coverage_facets=facets
        if facets is not None
        else ["human_approval_required", "approval_threshold_defined"],
        evidence_requirements=["Delegated authority matrix"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 1: Same Control ID, different obligations (not equivalent)
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_01_same_control_id_different_obligations_not_equivalent(regulatory_pack):
    tenant = f"t-s01-{uuid.uuid4().hex[:6]}"
    # CTRL-PRIV-GOVERNANCE links to both AU-PRIV-APP1-GOV and AU-OAIC-APPG-CH1-PIA.
    # Clause only addresses privacy_policy_current (one facet of AU-PRIV-APP1-GOV and none of AU-OAIC-APPG-CH1-PIA).
    policy, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="The bank must maintain a current privacy policy published on its website.",
        control_id="CTRL-PRIV-GOVERNANCE",
        control_facets=["privacy_policy_current"],
    )
    decisions = generate_reconciliation_candidates(
        tenant_id=tenant,
        enterprise_baseline=baseline,
        regulatory_pack=regulatory_pack,
        policies=[policy],
    )
    assert len(decisions) >= 2
    by_ob = {d.external_obligation_id: d for d in decisions}
    assert "AU-PRIV-APP1-GOV" in by_ob
    assert "AU-OAIC-APPG-CH1-PIA" in by_ob
    for ob_id, dec in by_ob.items():
        assert dec.validated_relationship != ReconciliationRelationship.EQUIVALENT
        assert dec.validated_relationship == ReconciliationRelationship.PARTIALLY_OVERLAPPING
        assert dec.decision_status != ReconciliationDecisionStatus.APPROVED


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 2: Enterprise requirement stricter than external obligation (AUD 500 vs AUD 1,000)
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_02_stricter_enterprise_threshold_aud_500_vs_1000(regulatory_pack):
    tenant = f"t-s02-{uuid.uuid4().hex[:6]}"
    ext_ob = _synthetic_threshold_obligation(
        threshold_text="All automated customer refund decisions above AUD 1,000 must obtain pre-execution Authorised Officer approval."
    )
    _, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="All automated customer refund decisions above AUD 500 must obtain pre-execution Authorised Officer approval.",
        control_id="CTRL-HUMAN-OVERSIGHT",
        control_facets=["human_approval_required", "approval_threshold_defined"],
        thresholds_aud=[500.0],
        threshold_operator=">",
        threshold_currency="AUD",
        approval_timing="pre_execution",
        required_approval_role="authorised_officer",
    )
    dec = validate_candidate_relationship(
        clause=clause,
        obligation=ext_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
    )
    assert dec.validated_relationship == ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT
    assert dec.dimension_comparison.threshold_comparison == "stricter_enterprise"
    assert dec.dimension_comparison.enterprise_threshold == 500.0
    assert dec.dimension_comparison.external_threshold == 1000.0


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 3: Enterprise requirement weaker than external obligation (AUD 5,000 vs AUD 1,000)
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_03_weaker_enterprise_threshold_aud_5000_vs_1000(regulatory_pack):
    tenant = f"t-s03-{uuid.uuid4().hex[:6]}"
    ext_ob = _synthetic_threshold_obligation(
        threshold_text="All automated customer refund decisions above AUD 1,000 must obtain pre-execution Authorised Officer approval."
    )
    _, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="All automated customer refund decisions above AUD 5,000 must obtain pre-execution Authorised Officer approval.",
        control_id="CTRL-HUMAN-OVERSIGHT",
        control_facets=["human_approval_required", "approval_threshold_defined"],
        thresholds_aud=[5000.0],
        threshold_operator=">",
        threshold_currency="AUD",
        approval_timing="pre_execution",
        required_approval_role="authorised_officer",
    )
    dec = validate_candidate_relationship(
        clause=clause,
        obligation=ext_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
    )
    assert dec.validated_relationship == ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT
    assert dec.dimension_comparison.threshold_comparison == "weaker_enterprise"


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 4: Threshold operator mismatch (> 500 vs >= 500)
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_04_threshold_operator_mismatch_gt_vs_gte_500(regulatory_pack):
    tenant = f"t-s04-{uuid.uuid4().hex[:6]}"
    ext_ob = _synthetic_threshold_obligation(
        threshold_text="All automated customer refund decisions of at least AUD 500 must obtain pre-execution Authorised Officer approval."
    )
    _, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="All automated customer refund decisions exceeding AUD 500 must obtain pre-execution Authorised Officer approval.",
        control_id="CTRL-HUMAN-OVERSIGHT",
        control_facets=["human_approval_required", "approval_threshold_defined"],
        thresholds_aud=[500.0],
        threshold_operator=">",
        threshold_currency="AUD",
        approval_timing="pre_execution",
        required_approval_role="authorised_officer",
    )
    dec = validate_candidate_relationship(
        clause=clause,
        obligation=ext_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
    )
    assert dec.validated_relationship != ReconciliationRelationship.EQUIVALENT
    assert dec.validated_relationship == ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT
    assert dec.dimension_comparison.threshold_comparison == "operator_boundary_difference"
    assert any("operator mismatch" in u.lower() for u in dec.uncertainties)


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 5: Currency mismatch (AUD 500 vs USD 500)
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_05_currency_mismatch_aud_500_vs_usd_500(regulatory_pack):
    tenant = f"t-s05-{uuid.uuid4().hex[:6]}"
    ext_ob = _synthetic_threshold_obligation(
        threshold_text="All automated customer refund decisions above AUD 500 must obtain pre-execution Authorised Officer approval."
    )
    _, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="All automated customer refund decisions above USD 500 must obtain pre-execution Authorised Officer approval.",
        control_id="CTRL-HUMAN-OVERSIGHT",
        control_facets=["human_approval_required", "approval_threshold_defined"],
        thresholds_aud=[500.0],
        threshold_operator=">",
        threshold_currency="USD",
        approval_timing="pre_execution",
        required_approval_role="authorised_officer",
    )
    dec = validate_candidate_relationship(
        clause=clause,
        obligation=ext_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
    )
    assert dec.validated_relationship == ReconciliationRelationship.UNDETERMINED
    assert dec.decision_status == ReconciliationDecisionStatus.NEEDS_REVIEW
    assert dec.dimension_comparison.threshold_comparison == "currency_mismatch"
    assert any("currency mismatch" in u.lower() for u in dec.uncertainties)


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 6: Different transaction scope (refunds vs credit decisions)
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_06_different_transaction_scope_refunds_vs_credit_decisions(regulatory_pack):
    tenant = f"t-s06-{uuid.uuid4().hex[:6]}"
    nccp_ob = next(
        ob for ob in regulatory_pack.obligations if ob.obligation_id == "AU-NCCP-S128-131-LENDING"
    )
    _, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="All automated customer refund reimbursements exceeding AUD 500 require pre-execution supervisor sign-off.",
        control_id="CTRL-CREDIT-UNSUITABILITY",
        control_facets=["human_approval_required"],
        thresholds_aud=[500.0],
        threshold_operator=">",
        threshold_currency="AUD",
    )
    dec = validate_candidate_relationship(
        clause=clause,
        obligation=nccp_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
    )
    assert dec.validated_relationship != ReconciliationRelationship.EQUIVALENT
    assert dec.dimension_comparison.scope_match == "mismatch"
    assert any("scope mismatch" in u.lower() for u in dec.uncertainties)


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 7: Different approval actors (Senior Manager vs Authorised Officer vs Two-Up Approval)
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_07_different_approval_actors(regulatory_pack):
    tenant = f"t-s07-{uuid.uuid4().hex[:6]}"
    ext_ob = _synthetic_threshold_obligation(
        threshold_text="All automated customer refund decisions above AUD 500 must obtain pre-execution Authorised Officer approval."
    )
    # 7a: Senior Manager vs Authorised Officer -> not equivalent (weaker/different actor)
    _, clause_sm, baseline_sm = _make_approved_clause(
        tenant_id=tenant,
        text="All automated customer refund decisions above AUD 500 must obtain pre-execution Senior Manager approval.",
        control_id="CTRL-HUMAN-OVERSIGHT",
        control_facets=["human_approval_required", "approval_threshold_defined"],
        thresholds_aud=[500.0],
        threshold_operator=">",
        threshold_currency="AUD",
        approval_timing="pre_execution",
        required_approval_role="senior_manager",
    )
    dec_sm = validate_candidate_relationship(
        clause=clause_sm,
        obligation=ext_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline_sm,
    )
    assert dec_sm.validated_relationship != ReconciliationRelationship.EQUIVALENT
    assert dec_sm.dimension_comparison.actor_comparison == "different_actor"

    # 7b: Two-Up / Dual Authorised Officer approval -> stricter_enterprise_requirement
    _, clause_dual, baseline_dual = _make_approved_clause(
        tenant_id=tenant,
        text="All automated customer refund decisions above AUD 500 must obtain pre-execution dual authorised officer two-up approval.",
        control_id="CTRL-HUMAN-OVERSIGHT",
        control_facets=["human_approval_required", "approval_threshold_defined"],
        thresholds_aud=[500.0],
        threshold_operator=">",
        threshold_currency="AUD",
        approval_timing="pre_execution",
        required_approval_role="dual_approval",
    )
    dec_dual = validate_candidate_relationship(
        clause=clause_dual,
        obligation=ext_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline_dual,
    )
    assert dec_dual.validated_relationship == ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT
    assert dec_dual.dimension_comparison.actor_comparison == "stricter_actor"


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 8: Pre-execution approval vs post-execution review
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_08_pre_execution_vs_post_execution_review(regulatory_pack):
    tenant = f"t-s08-{uuid.uuid4().hex[:6]}"
    ext_ob = _synthetic_threshold_obligation(
        threshold_text="All automated customer refund decisions above AUD 500 must obtain pre-execution Authorised Officer approval prior to payment."
    )
    _, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="All automated customer refund decisions above AUD 500 must undergo post-execution retrospective review by an Authorised Officer within 48 hours after payment.",
        control_id="CTRL-HUMAN-OVERSIGHT",
        control_facets=["human_approval_required", "approval_threshold_defined"],
        thresholds_aud=[500.0],
        threshold_operator=">",
        threshold_currency="AUD",
        approval_timing="post_execution",
        required_approval_role="authorised_officer",
    )
    dec = validate_candidate_relationship(
        clause=clause,
        obligation=ext_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
    )
    assert dec.validated_relationship == ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT
    assert dec.dimension_comparison.timing_comparison == "weaker_post_execution"


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 9: Conditional enterprise requirement
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_09_conditional_enterprise_requirement(regulatory_pack):
    tenant = f"t-s09-{uuid.uuid4().hex[:6]}"
    app1_ob = next(
        ob for ob in regulatory_pack.obligations if ob.obligation_id == "AU-PRIV-APP1-GOV"
    )
    _, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="If the AI model processes over 100,000 customer records, privacy accountability must be assigned, privacy practices implemented, and a current privacy policy maintained.",
        control_id="CTRL-PRIV-GOVERNANCE",
        control_facets=[
            "privacy_accountability_assigned",
            "privacy_practices_implemented",
            "privacy_policy_current",
        ],
        is_conditional=True,
        condition_description="if the AI model processes over 100,000 customer records",
    )
    dec = validate_candidate_relationship(
        clause=clause,
        obligation=app1_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
    )
    assert dec.validated_relationship != ReconciliationRelationship.EQUIVALENT
    assert dec.validated_relationship == ReconciliationRelationship.PARTIALLY_OVERLAPPING
    assert dec.dimension_comparison.condition_status == "conditional_enterprise"


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 10: Exception clause weakening a requirement
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_10_exception_clause_weakening_requirement(regulatory_pack):
    tenant = f"t-s10-{uuid.uuid4().hex[:6]}"
    app1_ob = next(
        ob for ob in regulatory_pack.obligations if ob.obligation_id == "AU-PRIV-APP1-GOV"
    )
    _, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="Privacy accountability must be assigned, privacy practices implemented, and a current privacy policy maintained, except where waived by a business unit product owner during promotional launches.",
        control_id="CTRL-PRIV-GOVERNANCE",
        control_facets=[
            "privacy_accountability_assigned",
            "privacy_practices_implemented",
            "privacy_policy_current",
        ],
        has_exception_clause=True,
        exception_description="except where waived by a business unit product owner during promotional launches",
    )
    dec = validate_candidate_relationship(
        clause=clause,
        obligation=app1_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
    )
    assert dec.validated_relationship == ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT
    assert dec.dimension_comparison.exception_status == "enterprise_exception_weakens"


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 11: Negative obligation (must not vs does not require)
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_11_negative_obligation_must_not_vs_does_not_require(regulatory_pack):
    tenant = f"t-s11-{uuid.uuid4().hex[:6]}"
    app8_ob = next(
        ob for ob in regulatory_pack.obligations if ob.obligation_id == "AU-PRIV-APP8-CROSSBORDER"
    )
    # 11a: Protective prohibition ("must not") -> stricter_enterprise_requirement
    _, clause_prohibit, baseline_prohibit = _make_approved_clause(
        tenant_id=tenant,
        text="Customer personal information must not be disclosed to any overseas AI recipient unless overseas regions are mapped, APP 8 contracts are in place, and s 16C accountability is assessed.",
        control_id="CTRL-PRIV-CROSS-BORDER",
        control_facets=[
            "overseas_recipients_and_regions_mapped",
            "app8_reasonable_steps_and_contracts_in_place",
            "s16c_accountability_and_exception_assessed",
        ],
    )
    dec_prohibit = validate_candidate_relationship(
        clause=clause_prohibit,
        obligation=app8_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline_prohibit,
    )
    assert dec_prohibit.dimension_comparison.action_polarity == "prohibition"
    assert dec_prohibit.validated_relationship == ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT

    # 11b: Absence of control ("does not require") -> potential_conflict
    _, clause_exempt, baseline_exempt = _make_approved_clause(
        tenant_id=tenant,
        text="Cross-border AI inference with overseas cloud vendors does not require APP 8 contractual safeguards.",
        control_id="CTRL-PRIV-CROSS-BORDER",
        control_facets=[],
        mandatory=False,
    )
    dec_exempt = validate_candidate_relationship(
        clause=clause_exempt,
        obligation=app8_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline_exempt,
    )
    assert dec_exempt.dimension_comparison.action_polarity == "absence_of_control"
    assert dec_exempt.validated_relationship == ReconciliationRelationship.POTENTIAL_CONFLICT


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 12: Additional enterprise requirement with no external equivalent
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_12_additional_enterprise_requirement_no_external_equivalent(regulatory_pack):
    tenant = f"t-s12-{uuid.uuid4().hex[:6]}"
    policy, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="All internal enterprise treasury AI tools must maintain a 10-year immutable ledger of delegated approval thresholds.",
        control_id="CTRL-DELEGATED-AUTHORITY-THRESHOLD",
        control_facets=["approval_logs_retained"],
    )
    dec = validate_candidate_relationship(
        clause=clause,
        obligation=None,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
    )
    assert dec.external_obligation_id is None
    assert dec.validated_relationship == ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 13: Unmapped approved enterprise clause
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_13_unmapped_approved_enterprise_clause_preserved(regulatory_pack):
    tenant = f"t-s13-{uuid.uuid4().hex[:6]}"
    policy, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="Regional acoustic dialect models must undergo First Nations community language consultation prior to dataset curation.",
        control_id=None,
        control_facets=[],
    )
    decisions = generate_reconciliation_candidates(
        tenant_id=tenant,
        enterprise_baseline=baseline,
        regulatory_pack=regulatory_pack,
        policies=[policy],
    )
    assert len(decisions) == 1
    assert decisions[0].validated_relationship == ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP

    eff = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=regulatory_pack,
        use_case=BankingUseCase(apra_regulated=True),
        enterprise_baseline=baseline,
        reconciliation_decisions=decisions,
        policies=[policy],
    )
    assert clause.clause_id in eff.included_enterprise_clause_ids
    unmapped_items = [
        r for r in eff.requirements if r.enterprise_clause_id == clause.clause_id
    ]
    assert len(unmapped_items) == 1
    assert unmapped_items[0].item_kind == "unmapped_enterprise_requirement"


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 14: Proposed vs approved enterprise clause
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_14_proposed_vs_approved_enterprise_clause(regulatory_pack):
    tenant = f"t-s14-{uuid.uuid4().hex[:6]}"
    policy, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="Privacy accountability must be assigned, privacy practices implemented, and a current privacy policy maintained.",
        control_id="CTRL-PRIV-GOVERNANCE",
        control_facets=[
            "privacy_accountability_assigned",
            "privacy_practices_implemented",
            "privacy_policy_current",
        ],
        clause_status=ClauseReviewStatus.PROPOSED,
    )
    # Proposed clauses do not generate active reconciliation candidates by default
    candidates = generate_reconciliation_candidates(
        tenant_id=tenant,
        enterprise_baseline=baseline,
        regulatory_pack=regulatory_pack,
        policies=[policy],
    )
    assert candidates == []

    # Even if validated directly, a proposed clause cannot be validated as equivalent
    app1_ob = next(
        ob for ob in regulatory_pack.obligations if ob.obligation_id == "AU-PRIV-APP1-GOV"
    )
    direct_dec = validate_candidate_relationship(
        clause=clause,
        obligation=app1_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
    )
    assert direct_dec.validated_relationship == ReconciliationRelationship.UNDETERMINED

    eff = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=regulatory_pack,
        use_case=BankingUseCase(apra_regulated=True),
        enterprise_baseline=baseline,
        reconciliation_decisions=[direct_dec],
        policies=[policy],
    )
    assert clause.clause_id in eff.excluded_enterprise_clause_ids
    assert clause.clause_id not in eff.included_enterprise_clause_ids


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 15: Rejected enterprise clause
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_15_rejected_enterprise_clause_excluded(regulatory_pack):
    tenant = f"t-s15-{uuid.uuid4().hex[:6]}"
    policy, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="Rejected draft clause on privacy governance.",
        control_id="CTRL-PRIV-GOVERNANCE",
        control_facets=["privacy_policy_current"],
        clause_status=ClauseReviewStatus.REJECTED,
    )
    candidates = generate_reconciliation_candidates(
        tenant_id=tenant,
        enterprise_baseline=baseline,
        regulatory_pack=regulatory_pack,
        policies=[policy],
    )
    assert candidates == []
    eff = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=regulatory_pack,
        use_case=BankingUseCase(apra_regulated=True),
        enterprise_baseline=baseline,
        reconciliation_decisions=[],
        policies=[policy],
    )
    assert clause.clause_id in eff.excluded_enterprise_clause_ids
    assert all(r.enterprise_clause_id != clause.clause_id for r in eff.requirements)


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 16: Proposed vs approved control mapping
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_16_proposed_vs_approved_control_mapping(regulatory_pack):
    tenant = f"t-s16-{uuid.uuid4().hex[:6]}"
    app1_ob = next(
        ob for ob in regulatory_pack.obligations if ob.obligation_id == "AU-PRIV-APP1-GOV"
    )
    # 16a: Clause is APPROVED, but its control mapping is still PROPOSED -> cannot be EQUIVALENT
    _, clause_prop_map, baseline_prop_map = _make_approved_clause(
        tenant_id=tenant,
        text="An accountable privacy owner must be assigned, privacy by design practices implemented, and a current privacy policy maintained.",
        control_id="CTRL-PRIV-GOVERNANCE",
        control_facets=[
            "privacy_accountability_assigned",
            "privacy_practices_implemented",
            "privacy_policy_current",
        ],
        mapping_status=ClauseReviewStatus.PROPOSED,
        clause_status=ClauseReviewStatus.APPROVED,
    )
    dec_prop = validate_candidate_relationship(
        clause=clause_prop_map,
        obligation=app1_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline_prop_map,
    )
    assert dec_prop.validated_relationship != ReconciliationRelationship.EQUIVALENT
    assert dec_prop.validated_relationship == ReconciliationRelationship.PARTIALLY_OVERLAPPING
    assert any("proposed" in u.lower() for u in dec_prop.uncertainties)

    # 16b: When control mapping is APPROVED -> Stage B validates EQUIVALENT (still decision_status=PROPOSED)
    _, clause_app_map, baseline_app_map = _make_approved_clause(
        tenant_id=tenant,
        text="An accountable privacy owner must be assigned, privacy by design practices implemented, and a current privacy policy maintained.",
        control_id="CTRL-PRIV-GOVERNANCE",
        control_facets=[
            "privacy_accountability_assigned",
            "privacy_practices_implemented",
            "privacy_policy_current",
        ],
        mapping_status=ClauseReviewStatus.APPROVED,
        clause_status=ClauseReviewStatus.APPROVED,
    )
    dec_app = validate_candidate_relationship(
        clause=clause_app_map,
        obligation=app1_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline_app_map,
    )
    assert dec_app.validated_relationship == ReconciliationRelationship.EQUIVALENT
    assert dec_app.decision_status == ReconciliationDecisionStatus.PROPOSED


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 17: Superseded enterprise policy version
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_17_superseded_enterprise_policy_version(regulatory_pack):
    tenant = f"t-s17-{uuid.uuid4().hex[:6]}"
    policy, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="An accountable privacy owner must be assigned, privacy by design practices implemented, and a current privacy policy maintained.",
        control_id="CTRL-PRIV-GOVERNANCE",
        control_facets=[
            "privacy_accountability_assigned",
            "privacy_practices_implemented",
            "privacy_policy_current",
        ],
    )
    decisions = generate_reconciliation_candidates(
        tenant_id=tenant,
        enterprise_baseline=baseline,
        regulatory_pack=regulatory_pack,
        policies=[policy],
    )
    app1_dec = next(
        d for d in decisions if d.external_obligation_id == "AU-PRIV-APP1-GOV"
    )
    reviewed = review_reconciliation_decision(
        app1_dec,
        decision_status=ReconciliationDecisionStatus.APPROVED,
        actor="legal.reviewer",
        role="reviewer",
    )
    assert reviewed.is_stale is False

    # Mark policy as superseded
    superseded_policy = policy.model_copy(update={"status": "superseded"})
    checked = evaluate_reconciliation_staleness(
        reviewed,
        enterprise_baseline=baseline,
        regulatory_pack=regulatory_pack,
        policies=[superseded_policy],
    )
    assert checked.is_stale is True
    assert "superseded" in (checked.stale_reason or "").lower()


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 18: External regulatory pack version update
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_18_external_regulatory_pack_version_update(regulatory_pack):
    tenant = f"t-s18-{uuid.uuid4().hex[:6]}"
    policy, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="An accountable privacy owner must be assigned, privacy by design practices implemented, and a current privacy policy maintained.",
        control_id="CTRL-PRIV-GOVERNANCE",
        control_facets=[
            "privacy_accountability_assigned",
            "privacy_practices_implemented",
            "privacy_policy_current",
        ],
    )
    decisions = generate_reconciliation_candidates(
        tenant_id=tenant,
        enterprise_baseline=baseline,
        regulatory_pack=regulatory_pack,
        policies=[policy],
    )
    app1_dec = next(
        d for d in decisions if d.external_obligation_id == "AU-PRIV-APP1-GOV"
    )
    approved_dec = review_reconciliation_decision(
        app1_dec,
        decision_status=ReconciliationDecisionStatus.APPROVED,
        actor="legal.reviewer",
        role="reviewer",
    )

    # Bump regulatory pack version
    newer_pack = regulatory_pack.model_copy(update={"version": "0.2.0"})
    stale_dec = evaluate_reconciliation_staleness(
        approved_dec,
        enterprise_baseline=baseline,
        regulatory_pack=newer_pack,
        policies=[policy],
    )
    assert stale_dec.is_stale is True
    assert "0.1.0" in (stale_dec.stale_reason or "")
    assert "0.2.0" in (stale_dec.stale_reason or "")

    # Effective baseline marks stale decision as unresolved and does not use it for equivalence grouping
    eff = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=newer_pack,
        use_case=BankingUseCase(apra_regulated=True, handles_personal_information=True),
        enterprise_baseline=baseline,
        reconciliation_decisions=[approved_dec],
        policies=[policy],
    )
    assert approved_dec.reconciliation_id in eff.stale_reconciliation_ids
    assert any(
        u.reconciliation_id == approved_dec.reconciliation_id for u in eff.unresolved_items
    )


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 19: Applicable vs non-applicable external obligation
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_19_applicable_vs_non_applicable_external_obligation(regulatory_pack):
    tenant = f"t-s19-{uuid.uuid4().hex[:6]}"
    use_case = BankingUseCase(
        name="Domestic Internal Operations Assistant",
        apra_regulated=True,
        handles_personal_information=False,
        cross_border_disclosure=False,
        eu_establishment_or_market=False,
        eu_output_used=False,
        iso_42001_adopted=False,
        nist_ai_rmf_adopted=False,
    )
    eff = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=regulatory_pack,
        use_case=use_case,
    )
    assert "AU-APRA-CPS220-RMF" in eff.applicable_external_obligation_ids
    assert "AU-PRIV-APP8-CROSSBORDER" not in eff.applicable_external_obligation_ids
    assert "EU-AIA-ART2-HIGH-RISK" not in eff.applicable_external_obligation_ids
    assert "ISO42001-AIMS-ORG" not in eff.applicable_external_obligation_ids
    assert "EU-AIA-ART2-HIGH-RISK" in eff.applicability_summary["non_applicable_obligation_ids"]


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 20: Voluntary framework vs binding obligation
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_20_voluntary_framework_vs_binding_obligation(regulatory_pack):
    tenant = f"t-s20-{uuid.uuid4().hex[:6]}"
    iso_ob = next(
        ob for ob in regulatory_pack.obligations if ob.obligation_id == "ISO42001-AIMS-ORG"
    )
    policy, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="The bank must maintain an AI policy and roles, AI risk and impact process, performance monitoring, internal audit, and management review.",
        control_id="CTRL-ISO-AIMS",
        control_facets=[
            "ai_policy_and_roles",
            "ai_risk_and_impact_process",
            "performance_monitoring",
            "internal_audit",
            "management_review",
        ],
    )
    dec = validate_candidate_relationship(
        clause=clause,
        obligation=iso_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
    )
    assert dec.dimension_comparison.modality_comparison == "enterprise_mandatory_vs_voluntary"
    assert "voluntary_framework" in dec.dimension_comparison.authority_comparison

    use_case = BankingUseCase(
        apra_regulated=True,
        iso_42001_adopted=True,
        assessment_scope="organisation",
    )
    eff = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=regulatory_pack,
        use_case=use_case,
        enterprise_baseline=baseline,
        reconciliation_decisions=[dec],
        policies=[policy],
    )
    iso_item = next(
        r for r in eff.requirements if r.obligation_id == "ISO42001-AIMS-ORG"
    )
    assert iso_item.authority_classification == "voluntary_framework"
    assert iso_item.is_legally_binding is False

    cps220_item = next(
        r for r in eff.requirements if r.obligation_id == "AU-APRA-CPS220-RMF"
    )
    assert cps220_item.authority_classification == "binding_legal_or_prudential_obligation"
    assert cps220_item.is_legally_binding is True


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 21: Enterprise policy vs statutory law authority distinction
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_21_enterprise_policy_vs_statutory_law_authority_distinction(regulatory_pack):
    tenant = f"t-s21-{uuid.uuid4().hex[:6]}"
    policy, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="All automated customer refund decisions above AUD 500 require pre-execution dual authorised officer approval.",
        control_id="CTRL-HUMAN-OVERSIGHT",
        control_facets=["human_approval_required", "approval_threshold_defined"],
        thresholds_aud=[500.0],
        threshold_operator=">",
        threshold_currency="AUD",
        approval_timing="pre_execution",
        required_approval_role="dual_approval",
    )
    decisions = generate_reconciliation_candidates(
        tenant_id=tenant,
        enterprise_baseline=baseline,
        regulatory_pack=regulatory_pack,
        policies=[policy],
    )
    approved = [
        review_reconciliation_decision(
            d,
            decision_status=ReconciliationDecisionStatus.APPROVED,
            actor="reviewer.1",
            role="reviewer",
        )
        for d in decisions
    ]
    eff = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=regulatory_pack,
        use_case=BankingUseCase(apra_regulated=True, handles_personal_information=True),
        enterprise_baseline=baseline,
        reconciliation_decisions=approved,
        policies=[policy],
    )
    ent_reqs = [r for r in eff.requirements if r.enterprise_clause_id == clause.clause_id]
    assert len(ent_reqs) >= 1
    for er in ent_reqs:
        assert er.authority_classification == "enterprise_policy"
        assert er.is_legally_binding is False


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 22: Duplicate requirement across two enterprise policies
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_22_duplicate_requirement_across_two_enterprise_policies(regulatory_pack):
    tenant = f"t-s22-{uuid.uuid4().hex[:6]}"
    shared_text = "All high-risk AI models must maintain an immutable model bill of materials in the Enterprise Architecture Repository."
    pol1, c1, _ = _make_approved_clause(
        tenant_id=tenant,
        text=shared_text,
        control_id="CTRL-DELEGATED-AUTHORITY-THRESHOLD",
        control_facets=["approval_logs_retained"],
        policy_name="Enterprise AI Standard A",
    )
    pol2, c2, _ = _make_approved_clause(
        tenant_id=tenant,
        text=shared_text,
        control_id="CTRL-DELEGATED-AUTHORITY-THRESHOLD",
        control_facets=["approval_logs_retained"],
        policy_name="Enterprise Model Governance Policy B",
    )
    baseline = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Combined Baseline",
        policies=[pol1, pol2],
    )
    decisions = generate_reconciliation_candidates(
        tenant_id=tenant,
        enterprise_baseline=baseline,
        regulatory_pack=regulatory_pack,
        policies=[pol1, pol2],
    )
    approved = [
        review_reconciliation_decision(
            d,
            decision_status=ReconciliationDecisionStatus.APPROVED,
            actor="reviewer.1",
            role="reviewer",
        )
        for d in decisions
    ]
    eff = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=regulatory_pack,
        use_case=BankingUseCase(apra_regulated=True),
        enterprise_baseline=baseline,
        reconciliation_decisions=approved,
        policies=[pol1, pol2],
    )
    ent_items = [
        r for r in eff.requirements if r.enterprise_clause_id in {c1.clause_id, c2.clause_id}
    ]
    assert len(ent_items) == 2
    # Both policies are preserved in source_references on the duplicate items
    source_ids = {ref.source_id for r in ent_items for ref in r.source_references}
    assert pol1.policy_id in source_ids
    assert pol2.policy_id in source_ids


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 23: Conflict between two enterprise policies
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_23_conflict_between_two_enterprise_policies(regulatory_pack):
    tenant = f"t-s23-{uuid.uuid4().hex[:6]}"
    pol1, c1, _ = _make_approved_clause(
        tenant_id=tenant,
        text="All customer refund credits above AUD 1,000 require pre-execution manager approval.",
        control_id="CTRL-FIN-APPROVAL-THRESHOLDS",
        control_facets=["human_approval_required", "approval_threshold_defined"],
        thresholds_aud=[1000.0],
        threshold_operator=">",
        threshold_currency="AUD",
        approval_timing="pre_execution",
        policy_name="Credit Card Operations Policy",
    )
    pol2, c2, _ = _make_approved_clause(
        tenant_id=tenant,
        text="All customer refund credits above AUD 500 require pre-execution supervisor approval.",
        control_id="CTRL-FIN-APPROVAL-THRESHOLDS",
        control_facets=["human_approval_required", "approval_threshold_defined"],
        thresholds_aud=[500.0],
        threshold_operator=">",
        threshold_currency="AUD",
        approval_timing="pre_execution",
        policy_name="Fraud Operations Policy",
    )
    baseline = compile_enterprise_baseline(
        tenant_id=tenant,
        name="Conflicting Enterprise Baseline",
        policies=[pol1, pol2],
    )
    decisions = generate_reconciliation_candidates(
        tenant_id=tenant,
        enterprise_baseline=baseline,
        regulatory_pack=regulatory_pack,
        policies=[pol1, pol2],
    )
    internal_conflicts = [
        d for d in decisions if d.peer_enterprise_clause_id is not None
    ]
    assert len(internal_conflicts) == 1
    assert internal_conflicts[0].validated_relationship == ReconciliationRelationship.POTENTIAL_CONFLICT

    eff = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=regulatory_pack,
        use_case=BankingUseCase(apra_regulated=True),
        enterprise_baseline=baseline,
        reconciliation_decisions=decisions,
        policies=[pol1, pol2],
    )
    assert any(
        c.peer_enterprise_clause_id is not None for c in eff.potential_conflicts
    )


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 24: Conflict between enterprise policy and external obligation
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_24_conflict_between_enterprise_policy_and_external_obligation(regulatory_pack):
    tenant = f"t-s24-{uuid.uuid4().hex[:6]}"
    cps234_inc = next(
        ob for ob in regulatory_pack.obligations if ob.obligation_id == "AU-APRA-CPS234-INCIDENT"
    )
    policy, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="Material information security incidents affecting AI systems must be reported to APRA within 14 days after internal remediation.",
        control_id="CTRL-SEC-INCIDENT",
        control_facets=["apra_notification_screened"],
    )
    dec = validate_candidate_relationship(
        clause=clause,
        obligation=cps234_inc,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
    )
    assert dec.validated_relationship == ReconciliationRelationship.POTENTIAL_CONFLICT
    assert dec.decision_status == ReconciliationDecisionStatus.NEEDS_REVIEW

    eff = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=regulatory_pack,
        use_case=BankingUseCase(apra_regulated=True),
        enterprise_baseline=baseline,
        reconciliation_decisions=[dec],
        policies=[policy],
    )
    # Binding CPS 234 obligation is retained in full AND conflict is surfaced
    assert "AU-APRA-CPS234-INCIDENT" in [r.obligation_id for r in eff.requirements]
    assert any(
        c.external_obligation_id == "AU-APRA-CPS234-INCIDENT"
        and c.validated_relationship == ReconciliationRelationship.POTENTIAL_CONFLICT
        for c in eff.potential_conflicts
    )


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 25: Ambiguous clause requiring 'undetermined' classification
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_25_ambiguous_clause_requires_undetermined(regulatory_pack):
    tenant = f"t-s25-{uuid.uuid4().hex[:6]}"
    app1_ob = next(
        ob for ob in regulatory_pack.obligations if ob.obligation_id == "AU-PRIV-APP1-GOV"
    )
    _, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="Appropriate governance arrangements shall be applied to AI tools as determined from time to time in accordance with Schedule C.",
        control_id="CTRL-PRIV-GOVERNANCE",
        control_facets=[],
    )
    dec = validate_candidate_relationship(
        clause=clause,
        obligation=app1_ob,
        regulatory_pack=regulatory_pack,
        enterprise_baseline=baseline,
    )
    assert dec.validated_relationship == ReconciliationRelationship.UNDETERMINED
    assert dec.decision_status == ReconciliationDecisionStatus.NEEDS_REVIEW
    assert len(dec.uncertainties) > 0


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 26: Unauthorised role attempting to approve reconciliation
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_26_unauthorised_role_blocked_from_approving_reconciliation(client):
    tenant = f"t-s26-{uuid.uuid4().hex[:6]}"
    policy, clause, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="An accountable privacy owner must be assigned, privacy by design practices implemented, and a current privacy policy maintained.",
        control_id="CTRL-PRIV-GOVERNANCE",
        control_facets=[
            "privacy_accountability_assigned",
            "privacy_practices_implemented",
            "privacy_policy_current",
        ],
    )
    store.save_enterprise_policy(tenant, policy)
    store.save_enterprise_baseline(tenant, baseline)

    rec_res = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/reconcile",
        headers={"X-Tenant-ID": tenant, "X-Actor": "analyst.user", "X-Role": "analyst"},
    )
    assert rec_res.status_code == 201
    reconciliations = rec_res.json()
    assert len(reconciliations) > 0
    rec_id = reconciliations[0]["reconciliation_id"]

    # Viewer and Analyst must be rejected with 403 Forbidden
    for forbidden_role in ("viewer", "analyst"):
        res_forbidden = client.put(
            f"/v1/enterprise/reconciliations/{rec_id}/review",
            headers={
                "X-Tenant-ID": tenant,
                "X-Actor": f"{forbidden_role}.user",
                "X-Role": forbidden_role,
            },
            json={
                "decision_status": "approved",
                "actor": f"{forbidden_role}.user",
                "role": forbidden_role,
                "comment": "Attempting unauthorised approval",
            },
        )
        assert res_forbidden.status_code == 403

    # Authorised Reviewer succeeds
    res_ok = client.put(
        f"/v1/enterprise/reconciliations/{rec_id}/review",
        headers={
            "X-Tenant-ID": tenant,
            "X-Actor": "compliance.reviewer",
            "X-Role": "reviewer",
        },
        json={
            "decision_status": "approved",
            "actor": "compliance.reviewer",
            "role": "reviewer",
            "comment": "Verified APP 1 coverage alignment",
        },
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["decision_status"] == "approved"
    assert res_ok.json()["reviewer_id"] == "compliance.reviewer"


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 27: Cross-tenant access attempt on reconciliation or effective baseline
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_27_cross_tenant_isolation_on_reconciliation_and_effective_baseline(client):
    tenant_a = f"tenant-a-{uuid.uuid4().hex[:6]}"
    tenant_b = f"tenant-b-{uuid.uuid4().hex[:6]}"
    policy, _, baseline = _make_approved_clause(
        tenant_id=tenant_a,
        text="An accountable privacy owner must be assigned, privacy by design practices implemented, and a current privacy policy maintained.",
        control_id="CTRL-PRIV-GOVERNANCE",
        control_facets=[
            "privacy_accountability_assigned",
            "privacy_practices_implemented",
            "privacy_policy_current",
        ],
    )
    store.save_enterprise_policy(tenant_a, policy)
    store.save_enterprise_baseline(tenant_a, baseline)

    rec_res = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/reconcile",
        headers={"X-Tenant-ID": tenant_a, "X-Actor": "rev.a", "X-Role": "reviewer"},
    )
    assert rec_res.status_code == 201
    rec_id = rec_res.json()[0]["reconciliation_id"]

    eff_res = client.post(
        f"/v1/enterprise/baselines/{baseline.baseline_id}/effective-baseline",
        headers={"X-Tenant-ID": tenant_a, "X-Actor": "rev.a", "X-Role": "reviewer"},
    )
    assert eff_res.status_code == 201
    eff_id = eff_res.json()["effective_baseline_id"]

    # Tenant B cannot list, review, compose, or fetch Tenant A's records
    assert (
        client.get(
            f"/v1/enterprise/baselines/{baseline.baseline_id}/reconciliations",
            headers={"X-Tenant-ID": tenant_b},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/v1/enterprise/baselines/{baseline.baseline_id}/reconciliations/unresolved",
            headers={"X-Tenant-ID": tenant_b},
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/v1/enterprise/reconciliations/{rec_id}/review",
            headers={"X-Tenant-ID": tenant_b, "X-Actor": "rev.b", "X-Role": "reviewer"},
            json={
                "decision_status": "approved",
                "actor": "rev.b",
                "role": "reviewer",
            },
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/v1/enterprise/effective-baselines/{eff_id}",
            headers={"X-Tenant-ID": tenant_b},
        ).status_code
        == 404
    )
    # public-demo tenant is also blocked
    assert (
        client.get(
            f"/v1/enterprise/effective-baselines/{eff_id}",
            headers={"X-Tenant-ID": "public-demo"},
        ).status_code
        == 403
    )


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 28: Deterministic reproduction of the same Effective Assessment Baseline
# ─────────────────────────────────────────────────────────────────────────────
def test_scenario_28_deterministic_reproduction_of_effective_assessment_baseline(regulatory_pack):
    tenant = f"t-s28-{uuid.uuid4().hex[:6]}"
    policy, _, baseline = _make_approved_clause(
        tenant_id=tenant,
        text="An accountable privacy owner must be assigned, privacy by design practices implemented, and a current privacy policy maintained.",
        control_id="CTRL-PRIV-GOVERNANCE",
        control_facets=[
            "privacy_accountability_assigned",
            "privacy_practices_implemented",
            "privacy_policy_current",
        ],
    )
    decisions = generate_reconciliation_candidates(
        tenant_id=tenant,
        enterprise_baseline=baseline,
        regulatory_pack=regulatory_pack,
        policies=[policy],
    )
    approved = [
        review_reconciliation_decision(
            d,
            decision_status=ReconciliationDecisionStatus.APPROVED,
            actor="reviewer.1",
            role="reviewer",
            comment="Approved for deterministic test",
        )
        if d.validated_relationship == ReconciliationRelationship.EQUIVALENT
        else d
        for d in decisions
    ]
    use_case = BankingUseCase(
        name="Retail Banking Assistant",
        apra_regulated=True,
        handles_personal_information=True,
        handles_regulated_complaints=True,
    )
    eff_1 = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=regulatory_pack,
        use_case=use_case,
        enterprise_baseline=baseline,
        reconciliation_decisions=approved,
        policies=[policy],
        as_of_date="2026-11-02",
    )
    eff_2 = compose_effective_assessment_baseline(
        tenant_id=tenant,
        regulatory_pack=regulatory_pack,
        use_case=use_case,
        enterprise_baseline=baseline,
        reconciliation_decisions=approved,
        policies=[policy],
        as_of_date="2026-11-02",
    )
    assert eff_1.effective_baseline_sha256 == eff_2.effective_baseline_sha256
    assert eff_1.effective_baseline_id == eff_2.effective_baseline_id
    assert [r.item_id for r in eff_1.requirements] == [
        r.item_id for r in eff_2.requirements
    ]
    assert [g.group_id for g in eff_1.presentation_groups] == [
        g.group_id for g in eff_2.presentation_groups
    ]
    # Verify that reviewed equivalence group exists for AU-PRIV-APP1-GOV and retains both sources
    eq_groups = [
        g
        for g in eff_1.presentation_groups
        if g.group_type == "reviewed_equivalence_group"
    ]
    assert len(eq_groups) == 1
    assert "AU-PRIV-APP1-GOV" in eq_groups[0].external_obligation_ids
    assert len(eq_groups[0].source_references) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Section 11: Synthetic Dev & Held-Out Evaluation Benchmark
# ─────────────────────────────────────────────────────────────────────────────
def test_e1_evaluation_benchmark_dev_and_held_out_splits(regulatory_pack):
    """Evaluate precision, recall, false equivalence rate (must be 0.0),
    false conflict rate, unresolved rate, and source traceability completeness
    across synthetic development and held-out Australian banking policy sets.
    """
    tenant = f"t-bench-{uuid.uuid4().hex[:6]}"
    ext_1000 = _synthetic_threshold_obligation(
        obligation_id="SYN-OB-1000",
        threshold_text="All automated customer refund decisions above AUD 1,000 must obtain pre-execution Authorised Officer approval.",
    )
    ext_gte_500 = _synthetic_threshold_obligation(
        obligation_id="SYN-OB-GTE-500",
        threshold_text="All automated customer refund decisions of at least AUD 500 must obtain pre-execution Authorised Officer approval.",
    )
    app1_ob = next(
        ob for ob in regulatory_pack.obligations if ob.obligation_id == "AU-PRIV-APP1-GOV"
    )
    app8_ob = next(
        ob for ob in regulatory_pack.obligations if ob.obligation_id == "AU-PRIV-APP8-CROSSBORDER"
    )
    cps234_inc = next(
        ob for ob in regulatory_pack.obligations if ob.obligation_id == "AU-APRA-CPS234-INCIDENT"
    )

    # Each case: (split, name, clause_kwargs, obligation, ground_truth_relationship)
    benchmark_cases = [
        # Development split (8 cases)
        (
            "dev",
            "dev_exact_equivalent_app1",
            dict(
                text="An accountable privacy owner must be assigned, privacy by design practices implemented, and a current privacy policy maintained.",
                control_id="CTRL-PRIV-GOVERNANCE",
                control_facets=[
                    "privacy_accountability_assigned",
                    "privacy_practices_implemented",
                    "privacy_policy_current",
                ],
            ),
            app1_ob,
            ReconciliationRelationship.EQUIVALENT,
        ),
        (
            "dev",
            "dev_partial_app1_single_facet",
            dict(
                text="The bank must publish a current privacy policy.",
                control_id="CTRL-PRIV-GOVERNANCE",
                control_facets=["privacy_policy_current"],
            ),
            app1_ob,
            ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        ),
        (
            "dev",
            "dev_stricter_aud_500_vs_1000",
            dict(
                text="All automated customer refund decisions above AUD 500 must obtain pre-execution Authorised Officer approval.",
                control_id="CTRL-HUMAN-OVERSIGHT",
                control_facets=["human_approval_required", "approval_threshold_defined"],
                thresholds_aud=[500.0],
                threshold_operator=">",
                threshold_currency="AUD",
                approval_timing="pre_execution",
                required_approval_role="authorised_officer",
            ),
            ext_1000,
            ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
        ),
        (
            "dev",
            "dev_weaker_aud_5000_vs_1000",
            dict(
                text="All automated customer refund decisions above AUD 5,000 must obtain pre-execution Authorised Officer approval.",
                control_id="CTRL-HUMAN-OVERSIGHT",
                control_facets=["human_approval_required", "approval_threshold_defined"],
                thresholds_aud=[5000.0],
                threshold_operator=">",
                threshold_currency="AUD",
                approval_timing="pre_execution",
                required_approval_role="authorised_officer",
            ),
            ext_1000,
            ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        ),
        (
            "dev",
            "dev_conflict_exempt_app8",
            dict(
                text="Cross-border AI model prompts do not require APP 8 contractual safeguards.",
                control_id="CTRL-PRIV-CROSS-BORDER",
                control_facets=[],
                mandatory=False,
            ),
            app8_ob,
            ReconciliationRelationship.POTENTIAL_CONFLICT,
        ),
        (
            "dev",
            "dev_additional_enterprise_only",
            dict(
                text="All AI systems must log delegated financial authority checks in the 10-year Treasury Ledger.",
                control_id="CTRL-DELEGATED-AUTHORITY-THRESHOLD",
                control_facets=["approval_logs_retained"],
            ),
            None,
            ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT,
        ),
        (
            "dev",
            "dev_unmapped_indigenous_dialect",
            dict(
                text="First Nations acoustic dialect consultation must precede regional voice model curation.",
                control_id=None,
                control_facets=[],
            ),
            None,
            ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP,
        ),
        (
            "dev",
            "dev_undetermined_usd_currency",
            dict(
                text="All automated customer refund decisions above USD 500 must obtain pre-execution Authorised Officer approval.",
                control_id="CTRL-HUMAN-OVERSIGHT",
                control_facets=["human_approval_required", "approval_threshold_defined"],
                thresholds_aud=[500.0],
                threshold_operator=">",
                threshold_currency="USD",
                approval_timing="pre_execution",
                required_approval_role="authorised_officer",
            ),
            ext_1000,
            ReconciliationRelationship.UNDETERMINED,
        ),
        # Held-out test split (8 cases)
        (
            "held_out",
            "ho_equivalent_app8_full",
            dict(
                text="Before disclosing personal information to an overseas AI recipient, all overseas regions must be mapped, APP 8 contractual steps implemented, and s 16C accountability assessed.",
                control_id="CTRL-PRIV-CROSS-BORDER",
                control_facets=[
                    "overseas_recipients_and_regions_mapped",
                    "app8_reasonable_steps_and_contracts_in_place",
                    "s16c_accountability_and_exception_assessed",
                ],
            ),
            app8_ob,
            ReconciliationRelationship.EQUIVALENT,
        ),
        (
            "held_out",
            "ho_operator_boundary_gt_vs_gte_500",
            dict(
                text="All automated customer refund decisions exceeding AUD 500 must obtain pre-execution Authorised Officer approval.",
                control_id="CTRL-HUMAN-OVERSIGHT",
                control_facets=["human_approval_required", "approval_threshold_defined"],
                thresholds_aud=[500.0],
                threshold_operator=">",
                threshold_currency="AUD",
                approval_timing="pre_execution",
                required_approval_role="authorised_officer",
            ),
            ext_gte_500,
            ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        ),
        (
            "held_out",
            "ho_stricter_cps234_24h_notification",
            dict(
                text="Material AI information security incidents must be detected, escalated, tracked, and notified to APRA within 24 hours.",
                control_id="CTRL-SEC-INCIDENT",
                control_facets=[
                    "incident_detection_defined",
                    "response_and_escalation_defined",
                    "apra_notification_screened",
                    "material_weaknesses_tracked",
                ],
            ),
            cps234_inc,
            ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
        ),
        (
            "held_out",
            "ho_conflict_cps234_14_days",
            dict(
                text="Material AI information security incidents must be notified to APRA within 14 days after internal review.",
                control_id="CTRL-SEC-INCIDENT",
                control_facets=["apra_notification_screened"],
            ),
            cps234_inc,
            ReconciliationRelationship.POTENTIAL_CONFLICT,
        ),
        (
            "held_out",
            "ho_weaker_exception_clause",
            dict(
                text="An accountable privacy owner must be assigned, privacy practices implemented, and a current privacy policy maintained, unless waived by a line manager.",
                control_id="CTRL-PRIV-GOVERNANCE",
                control_facets=[
                    "privacy_accountability_assigned",
                    "privacy_practices_implemented",
                    "privacy_policy_current",
                ],
                has_exception_clause=True,
                exception_description="unless waived by a line manager",
            ),
            app1_ob,
            ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        ),
        (
            "held_out",
            "ho_conditional_partial",
            dict(
                text="Where customer data exceeds 50,000 records, privacy accountability must be assigned, privacy practices implemented, and a current privacy policy maintained.",
                control_id="CTRL-PRIV-GOVERNANCE",
                control_facets=[
                    "privacy_accountability_assigned",
                    "privacy_practices_implemented",
                    "privacy_policy_current",
                ],
                is_conditional=True,
                condition_description="where customer data exceeds 50,000 records",
            ),
            app1_ob,
            ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        ),
        (
            "held_out",
            "ho_ambiguous_schedule_reference",
            dict(
                text="Appropriate governance arrangements shall be applied as determined from time to time in accordance with Schedule B.",
                control_id="CTRL-PRIV-GOVERNANCE",
                control_facets=[],
            ),
            app1_ob,
            ReconciliationRelationship.UNDETERMINED,
        ),
        (
            "held_out",
            "ho_proposed_mapping_not_equivalent",
            dict(
                text="An accountable privacy owner must be assigned, privacy by design practices implemented, and a current privacy policy maintained.",
                control_id="CTRL-PRIV-GOVERNANCE",
                control_facets=[
                    "privacy_accountability_assigned",
                    "privacy_practices_implemented",
                    "privacy_policy_current",
                ],
                mapping_status=ClauseReviewStatus.PROPOSED,
            ),
            app1_ob,
            ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        ),
    ]

    for split_name in ("dev", "held_out"):
        cases = [c for c in benchmark_cases if c[0] == split_name]
        correct = 0
        false_equivalences = 0
        false_conflicts = 0
        traceable = 0

        for _, case_name, kwargs, ob, expected_rel in cases:
            _, clause, baseline = _make_approved_clause(tenant_id=tenant, **kwargs)
            dec = validate_candidate_relationship(
                clause=clause,
                obligation=ob,
                regulatory_pack=regulatory_pack,
                enterprise_baseline=baseline,
            )
            pred_rel = dec.validated_relationship
            if pred_rel == expected_rel:
                correct += 1
            if (
                pred_rel == ReconciliationRelationship.EQUIVALENT
                and expected_rel != ReconciliationRelationship.EQUIVALENT
            ):
                false_equivalences += 1
            if (
                pred_rel == ReconciliationRelationship.POTENTIAL_CONFLICT
                and expected_rel != ReconciliationRelationship.POTENTIAL_CONFLICT
            ):
                false_conflicts += 1
            if (
                dec.enterprise_clause_id == clause.clause_id
                and dec.enterprise_baseline_id == baseline.baseline_id
                and dec.regulatory_pack_version == regulatory_pack.version
                and len(dec.supporting_passages) >= 1
            ):
                traceable += 1

        accuracy = correct / len(cases)
        false_eq_rate = false_equivalences / len(cases)
        false_conflict_rate = false_conflicts / len(cases)
        traceability_rate = traceable / len(cases)

        assert accuracy == 1.0, f"Split {split_name} accuracy was {accuracy}"
        assert false_eq_rate == 0.0, f"Split {split_name} had false equivalences!"
        assert false_conflict_rate == 0.0, f"Split {split_name} had false conflicts!"
        assert traceability_rate == 1.0
