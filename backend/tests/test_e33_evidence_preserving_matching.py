"""Tests for E3.3 Evidence-Preserving Extraction, Deterministic Accuracy Hardening & Blinded Evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from banking_crosswalk.catalog import load_regulatory_pack
from banking_crosswalk.llm import (
    DataClassification,
    LLMProviderKind,
    LLMRuntimeConfig,
    SemanticMatchingMode,
    SemanticRelationshipAnalysis,
    build_provider_bundle,
)
from banking_crosswalk.models import (
    ClauseReviewStatus,
    EnterpriseClause,
    MappingRelationship,
    ReconciliationDecisionStatus,
    ReconciliationRelationship,
)
from banking_crosswalk.policy import compile_enterprise_baseline, extract_enterprise_policy
from banking_crosswalk.reconciliation import (
    _is_ambiguous_clause,
    generate_reconciliation_candidates,
    rank_reconciliation_candidates_for_clause,
    validate_candidate_relationship,
)
from banking_crosswalk.semantic_reconciliation import (
    generate_hybrid_reconciliation_candidates,
    validate_hybrid_candidate_relationship,
)


def _approved_baseline_from_text(tenant_id: str, text: str, name: str = "E33 Test Policy"):
    pol = extract_enterprise_policy(tenant_id=tenant_id, name=name, text=text)
    approved_clauses = []
    for c in pol.clauses:
        approved_mappings = [
            m.model_copy(update={"review_status": ClauseReviewStatus.APPROVED})
            for m in (c.control_mappings or [])
        ]
        approved_clauses.append(
            c.model_copy(
                update={
                    "review_status": ClauseReviewStatus.APPROVED,
                    "control_mappings": approved_mappings,
                }
            )
        )
    pol = pol.model_copy(update={"clauses": approved_clauses})
    baseline = compile_enterprise_baseline(
        tenant_id=tenant_id,
        name=f"{name} Baseline",
        policies=[pol],
        created_by="test-e33",
    )
    return pol, baseline


def test_e33_b2_keyword_extraction_never_claims_unsupported_full_equivalence():
    """B2: Generic keyword matches must not emit MappingRelationship.FULL by default."""
    pol = extract_enterprise_policy(
        tenant_id="t-e33-b2",
        name="AI Governance & Logging Standard",
        text=(
            "All generative AI models must be recorded in the enterprise model inventory "
            "and maintain prompt logging for audit traceability.\n"
            "Refunds above AUD 1,000 require human approval."
        ),
    )
    assert len(pol.clauses) >= 2
    for clause in pol.clauses:
        for m in clause.control_mappings:
            assert m.review_status == ClauseReviewStatus.PROPOSED
            assert m.relationship != MappingRelationship.FULL, (
                f"Single/partial keyword match on {m.control_id} ({m.mapped_facets}) "
                f"must not claim MappingRelationship.FULL"
            )
            if m.control_id in {"CTRL-GOV-FRAMEWORK", "CTRL-TECH-OBSERVABILITY"}:
                assert m.relationship == MappingRelationship.RELATED
                assert "ambiguous legacy control" in (m.rationale or "").lower()
            else:
                assert m.relationship == MappingRelationship.PARTIAL


def test_e33_b4_statutory_annex_vs_missing_internal_annexure():
    """B4: Recognise statutory Annex citations (Annex III, Schedule 1) while flagging missing Annexure G/D."""
    reg_pack = load_regulatory_pack()

    # 1. Statutory EU AI Act Annex III citation must NOT be flagged as ambiguous attachment
    stat_clause = EnterpriseClause(
        clause_id="CLS-STAT-ANNEX3",
        policy_id="POL-1",
        tenant_id="t-e33",
        source_name="EU AI Policy",
        text=(
            "High-risk AI systems deployed for creditworthiness evaluation under Annex III point 5(b) "
            "of the EU AI Act must assign trained human oversight and retain logs for 6 months."
        ),
        mandatory=True,
        review_status=ClauseReviewStatus.APPROVED,
    )
    assert _is_ambiguous_clause(stat_clause) is False

    # 2. Missing internal Australian Annexure (Annexure D / Annexure G) MUST be flagged as ambiguous
    internal_annexure = EnterpriseClause(
        clause_id="CLS-INT-ANNEXURE",
        policy_id="POL-1",
        tenant_id="t-e33",
        source_name="Internal Escalation Policy",
        text=(
            "Automated credit override thresholds follow Annexure D escalation matrices unless "
            "the credit committee decides to apply discretionary interim arrangements."
        ),
        mandatory=True,
        review_status=ClauseReviewStatus.APPROVED,
    )
    assert _is_ambiguous_clause(internal_annexure) is True

    _, baseline = _approved_baseline_from_text("t-e33", internal_annexure.text)
    decs = generate_reconciliation_candidates(
        tenant_id="t-e33",
        enterprise_baseline=baseline,
        regulatory_pack=reg_pack,
    )
    assert len(decs) == 1
    assert decs[0].validated_relationship == ReconciliationRelationship.UNDETERMINED
    assert decs[0].decision_status == ReconciliationDecisionStatus.NEEDS_REVIEW
    assert decs[0].external_obligation_id is None
    assert decs[0].candidate_relevance_state == "evidence_insufficient"
    assert len(decs[0].preserved_candidate_evidence) >= 1


def test_e33_b4_permissive_omission_vs_protective_prohibition():
    """B4: Distinguish permissive omission of mandatory duties (conflict) from protective prohibitions."""
    reg_pack = load_regulatory_pack()

    # Permissive omission of mandatory complaint logging -> POTENTIAL_CONFLICT
    _, base_omission = _approved_baseline_from_text(
        "t-e33-omit",
        "Automated dispute bots may resolve customer dissatisfaction inquiries informally without "
        "recording a complaint or providing AFCA escalation details.",
    )
    decs_omit = generate_reconciliation_candidates(
        tenant_id="t-e33-omit",
        enterprise_baseline=base_omission,
        regulatory_pack=reg_pack,
    )
    rg271_dec = next(
        d for d in decs_omit if d.external_obligation_id == "AU-ASIC-RG271-COMPLAINT"
    )
    assert rg271_dec.validated_relationship == ReconciliationRelationship.POTENTIAL_CONFLICT
    assert rg271_dec.decision_status == ReconciliationDecisionStatus.NEEDS_REVIEW
    assert rg271_dec.candidate_relevance_state == "requirement_apparently_contradicted"

    # Protective prohibition on staff -> preserved as positive/protective control, not discarded
    pol_prot = extract_enterprise_policy(
        tenant_id="t-e33-prot",
        name="Protective Prohibition Policy",
        text="Employees are prohibited from executing automated refunds above AUD 500 without human approval before payment.",
    )
    cls_prot = pol_prot.clauses[0]
    assert cls_prot.mandatory is True
    assert "human_approval_required" in cls_prot.control_facets
    assert "pre_execution_block" in cls_prot.control_facets


def test_e33_b4_multi_regulator_retrieval_and_subclause_timing_isolation():
    """B4: Ensure APRA + OAIC both survive ranking and sub-clause deadlines do not cross-contaminate."""
    reg_pack = load_regulatory_pack()

    # 1. Multi-regulator conflict (CPS 234 72h notification used to waive OAIC 30-day NDB assessment)
    _, base_multi_reg = _approved_baseline_from_text(
        "t-e33-multireg",
        "Where a cyber incident involving personal information is reported to APRA within 72 hours "
        "under CPS 234, incident teams do not need to conduct a 30-day OAIC serious-harm assessment "
        "or notify affected individuals.",
    )
    decs_mr = generate_reconciliation_candidates(
        tenant_id="t-e33-multireg",
        enterprise_baseline=base_multi_reg,
        regulatory_pack=reg_pack,
    )
    mr_by_ob = {d.external_obligation_id: d for d in decs_mr if d.external_obligation_id}
    assert "AU-PRIV-NDB-S26WE" in mr_by_ob
    assert "AU-APRA-CPS234-INCIDENT" in mr_by_ob
    assert (
        mr_by_ob["AU-PRIV-NDB-S26WE"].validated_relationship
        == ReconciliationRelationship.POTENTIAL_CONFLICT
    )

    # 2. Compound multi-obligation clause with 30-day NDB deadline must NOT trigger false conflict on RG 271
    _, base_compound = _approved_baseline_from_text(
        "t-e33-compound",
        "Dispute resolution staff must log customer expressions of dissatisfaction and respond within "
        "maximum IDR timeframes with AFCA details, while privacy responders detecting personal-data "
        "leakage must complete an eligible data breach assessment within 30 days.",
    )
    decs_comp = generate_reconciliation_candidates(
        tenant_id="t-e33-compound",
        enterprise_baseline=base_compound,
        regulatory_pack=reg_pack,
    )
    comp_by_ob = {d.external_obligation_id: d for d in decs_comp if d.external_obligation_id}
    assert "AU-ASIC-RG271-COMPLAINT" in comp_by_ob
    assert "AU-PRIV-NDB-S26WE" in comp_by_ob
    assert (
        comp_by_ob["AU-ASIC-RG271-COMPLAINT"].validated_relationship
        == ReconciliationRelationship.PARTIALLY_OVERLAPPING
    )
    assert (
        comp_by_ob["AU-PRIV-NDB-S26WE"].validated_relationship
        == ReconciliationRelationship.PARTIALLY_OVERLAPPING
    )


def test_e33_b5_evidence_preservation_and_deterministic_veto_records():
    """B5: Verify Stage C vetoes preserve AI-proposed relationship, passages, and explicit veto reasons."""
    reg_pack = load_regulatory_pack()
    ob_app11 = next(
        ob for ob in reg_pack.obligations if ob.obligation_id == "AU-PRIV-APP11-SECURITY"
    )
    pol, baseline = _approved_baseline_from_text(
        "t-e33-veto",
        "Customer personal records in AI feature stores must be encrypted with AES-256 and deleted after 90 days.",
    )
    clause = baseline.clause_snapshots[0]

    # Simulate an overconfident AI Stage B analysis proposing EQUIVALENT despite missing organisational measures
    overconfident_sem = SemanticRelationshipAnalysis(
        clause_id=clause.clause_id,
        external_obligation_id=ob_app11.obligation_id,
        cited_obligation_id=ob_app11.obligation_id,
        cited_provision=ob_app11.provision,
        proposed_relationship=ReconciliationRelationship.EQUIVALENT,
        semantic_relevance="high",
        confidence=0.94,
        operational_scope="personal_information_security",
        required_actions_and_prohibitions=["AES-256 encryption", "90-day deletion"],
        potential_contradiction=False,
        inferred_covered_facets=[
            "technical_security_measures_implemented",
            "retention_schedule_applied",
            "destruction_or_deidentification_verified",
        ],
        uncertainty_flags=["organisational_security_measures_implemented not evidenced"],
        supporting_clause_quote=clause.text,
        supporting_obligation_quote=ob_app11.concise_obligation_summary[:120],
        reasoning_summary="Clause covers technical encryption and retention/deletion.",
    )

    dec = validate_hybrid_candidate_relationship(
        clause=clause,
        obligation=ob_app11,
        regulatory_pack=reg_pack,
        enterprise_baseline=baseline,
        policy_version=pol.version,
        policy_name=pol.name,
        stage_a_reason="Hybrid retrieval match on APP 11 security",
        matching_mode="hybrid_embedding_llm_deterministic",
        embedding_similarity=0.81,
        semantic_analysis=overconfident_sem,
    )

    assert dec.ai_proposed_relationship == ReconciliationRelationship.EQUIVALENT
    assert dec.validated_relationship == ReconciliationRelationship.PARTIALLY_OVERLAPPING
    assert dec.decision_status != ReconciliationDecisionStatus.APPROVED
    assert dec.deterministic_veto_applied is True
    assert len(dec.deterministic_veto_reasons) >= 1
    assert any("organisational_security_measures_implemented" in m for m in dec.missing_conditions_or_evidence)
    assert dec.candidate_relevance_state == "requirement_partially_addressed"
    assert len(dec.preserved_candidate_evidence) >= 1
    ev0 = dec.preserved_candidate_evidence[0]
    assert ev0["obligation_id"] == "AU-PRIV-APP11-SECURITY"
    assert ev0["ai_proposed_relationship"] == "equivalent"
    assert ev0["deterministically_validated_relationship"] == "partially_overlapping"
    assert ev0["deterministic_veto_applied"] is True


@dataclass(frozen=True)
class BlindedEvalCase:
    case_id: str
    text: str
    expected_obligation_id: Optional[str]
    expected_relationship: ReconciliationRelationship


E33_BLINDED_EVALUATION_SUITE: Tuple[BlindedEvalCase, ...] = (
    BlindedEvalCase(
        case_id="E33-BLIND-01",
        text=(
            "Under Annex III point 5(b) of the EU AI Act, European credit scoring models must "
            "assign competent human oversight, retain automatic logs for at least 6 months, and "
            "complete a Fundamental Rights Impact Assessment prior to production release."
        ),
        expected_obligation_id="EU-AIA-ART26-27-DEPLOYER-CREDIT",
        expected_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
    ),
    BlindedEvalCase(
        case_id="E33-BLIND-02",
        text=(
            "Automated collections agents may dismiss customer expressions of dissatisfaction "
            "without logging an IDR complaint or providing written AFCA escalation notice."
        ),
        expected_obligation_id="AU-ASIC-RG271-COMPLAINT",
        expected_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
    ),
    BlindedEvalCase(
        case_id="E33-BLIND-03",
        text=(
            "Once an information security incident affecting customer records is reported to APRA "
            "within 72 hours under CPS 234, privacy teams need not assess eligible data breach "
            "harm or notify the OAIC."
        ),
        expected_obligation_id="AU-PRIV-NDB-S26WE",
        expected_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
    ),
    BlindedEvalCase(
        case_id="E33-BLIND-04",
        text=(
            "Customer complaint officers must record dissatisfaction cases and respond within "
            "statutory IDR timeframes with AFCA details, while security responders discovering "
            "personal-information leakage must complete an OAIC eligible data breach assessment within 30 days."
        ),
        expected_obligation_id="AU-ASIC-RG271-COMPLAINT",
        expected_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
    ),
    BlindedEvalCase(
        case_id="E33-BLIND-05",
        text=(
            "Model risk escalation thresholds follow Annexure K operating procedures unless the "
            "divisional committee decides to apply discretionary interim arrangements."
        ),
        expected_obligation_id=None,
        expected_relationship=ReconciliationRelationship.UNDETERMINED,
    ),
    BlindedEvalCase(
        case_id="E33-BLIND-06",
        text=(
            "All external conference slide decks showcasing AI prototypes must comply with "
            "the group's corporate typography palette and brand logo spacing guidelines."
        ),
        expected_obligation_id=None,
        expected_relationship=ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP,
    ),
    BlindedEvalCase(
        case_id="E33-BLIND-07",
        text=(
            "Second-line risk teams must independently challenge AI risk assessments, include AI "
            "controls in three-yearly independent comprehensive RMF reviews, and escalate material "
            "AI control gaps for the Board's annual CPS 220 Risk Management Declaration."
        ),
        expected_obligation_id="AU-APRA-CPS220-REVIEW",
        expected_relationship=ReconciliationRelationship.EQUIVALENT,
    ),
    BlindedEvalCase(
        case_id="E33-BLIND-08",
        text=(
            "Personal information in AI training stores must be protected by technical security "
            "measures including encryption and access controls, supported by organisational "
            "security measures including staff training and access review procedures, and "
            "destroyed or de-identified according to an approved retention schedule."
        ),
        expected_obligation_id="AU-PRIV-APP11-SECURITY",
        expected_relationship=ReconciliationRelationship.EQUIVALENT,
    ),
)


def test_e33_b7_blinded_evaluation_suite_across_configs():
    """B7: Verify deterministic, embedding_only, and hybrid modes on unseen E3.3 blinded suite."""
    reg_pack = load_regulatory_pack()

    for mode in (
        SemanticMatchingMode.DISABLED,
        SemanticMatchingMode.EMBEDDING_ONLY,
        SemanticMatchingMode.HYBRID,
    ):
        cfg = LLMRuntimeConfig(
            semantic_matching_enabled=(mode != SemanticMatchingMode.DISABLED),
            matching_mode=mode,
            embedding_provider=LLMProviderKind.MOCK,
            reasoning_provider=LLMProviderKind.MOCK,
        )
        bundle = build_provider_bundle(cfg)
        correct = 0
        for case in E33_BLINDED_EVALUATION_SUITE:
            pol, baseline = _approved_baseline_from_text(
                f"t-{case.case_id}-{mode.value}", case.text
            )
            decs, _ = generate_hybrid_reconciliation_candidates(
                tenant_id=baseline.tenant_id,
                enterprise_baseline=baseline,
                policies=[pol],
                regulatory_pack=reg_pack,
                config=cfg,
                bundle=bundle,
                data_classification=DataClassification.PUBLIC_OR_SYNTHETIC,
            )
            assert len(decs) >= 1
            for d in decs:
                assert d.decision_status != ReconciliationDecisionStatus.APPROVED
            chosen = next(
                (d for d in decs if d.external_obligation_id == case.expected_obligation_id),
                decs[0],
            )
            if (
                chosen.external_obligation_id == case.expected_obligation_id
                and chosen.validated_relationship == case.expected_relationship
            ):
                correct += 1
            # Zero false equivalence and zero false coverage proposals
            if case.expected_relationship != ReconciliationRelationship.EQUIVALENT:
                assert chosen.validated_relationship != ReconciliationRelationship.EQUIVALENT
            if case.expected_obligation_id is None:
                assert chosen.validated_relationship not in {
                    ReconciliationRelationship.EQUIVALENT,
                    ReconciliationRelationship.PARTIALLY_OVERLAPPING,
                    ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
                }
        assert correct == len(E33_BLINDED_EVALUATION_SUITE), (
            f"Mode {mode.value} achieved {correct}/{len(E33_BLINDED_EVALUATION_SUITE)} on E3.3 blinded suite"
        )
