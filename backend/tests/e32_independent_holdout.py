"""Independently Labelled E3.2 Holdout Validation Dataset (Aligned to Regulatory Pack v0.2.0).

Authored specifically for E3.2 to eliminate benchmark contamination / mock cue
leakage:
  1. Uses novel realistic banking policy phrasing avoiding niche cue phrases
     embedded in `DeterministicMockSemanticProvider` (`providers.py`).
  2. Aligns ground-truth labels cleanly with E4.1 Regulatory Pack v0.2.0
     (including POLA Act 2024 APP 11.3 technical & organisational measures,
     APRA CPS 220 F2019L00669 paras 38-51, ASIC RG 271 Instrument 2020/98,
     EU AI Act Regulation (EU) 2026/1744 Art 50 vs Annex III Art 26/27).
  3. Locked holdout only (`split="held_out"`): zero tuning against these cases.

All 18 policy clauses and 4 questionnaire cases are 100% synthetic
(`DataClassification.PUBLIC_OR_SYNTHETIC`) for safe live Gemini free-tier testing.
"""

from __future__ import annotations

from typing import Tuple

from banking_crosswalk.models import ReconciliationRelationship
from e31_calibration_dataset import AdversarialCalibrationClause
from e3_benchmark_dataset import LabelledQuestionnaireCase


E32_INDEPENDENT_HOLDOUT: Tuple[AdversarialCalibrationClause, ...] = (
    # Org H-E32-1: Southern Cross Mutual Finance (9 clauses across PDF + DOCX)
    AdversarialCalibrationClause(
        case_id="E32-HO-01",
        split="held_out",
        org_id="southern-cross-mutual",
        doc_filename="scm_privacy_security_standard.pdf",
        doc_format="pdf",
        raw_text=(
            "Personal data processed by banking AI services must be protected by technical security "
            "measures including encryption and strict access controls, reinforced by organisational "
            "security measures covering staff training and annual access reviews, and permanently "
            "destroyed or de-identified according to an approved retention period once no longer needed."
        ),
        phenomenon="app11_3_technical_organisational_equivalent",
        ground_truth_obligation_id="AU-PRIV-APP11-SECURITY",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-PRIV-APP11-SECURITY",),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-02",
        split="held_out",
        org_id="southern-cross-mutual",
        doc_filename="scm_privacy_security_standard.pdf",
        doc_format="pdf",
        raw_text=(
            "Customer personal records inside model stores must be safeguarded using AES-256 "
            "encryption and network segmentation and deleted under a 90-day retention schedule, "
            "without specifying broader organisational governance or personnel procedures."
        ),
        phenomenon="app11_3_partial_missing_organisational",
        ground_truth_obligation_id="AU-PRIV-APP11-SECURITY",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP11-SECURITY",),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-03",
        split="held_out",
        org_id="southern-cross-mutual",
        doc_filename="scm_privacy_security_standard.pdf",
        doc_format="pdf",
        raw_text=(
            "Where AI conversational assistants operate for European Union clients under Article 2 scope, "
            "interface banners must clearly notify natural persons at session start that they are "
            "interacting with an AI system prior to collecting any responses."
        ),
        phenomenon="eu_art50_interaction_transparency_partial",
        ground_truth_obligation_id="EU-AIA-ART50-TRANSPARENCY",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("EU-AIA-ART50-TRANSPARENCY",),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-04",
        split="held_out",
        org_id="southern-cross-mutual",
        doc_filename="scm_privacy_security_standard.pdf",
        doc_format="pdf",
        raw_text=(
            "Where EU territorial scope applies to consumer creditworthiness scoring under Annex III "
            "point 5(b), deployers must assign competent human oversight, retain automatic execution "
            "logs for at least six months, and document a Fundamental Rights Impact Assessment before launch."
        ),
        phenomenon="eu_art26_27_decomposed_facets",
        ground_truth_obligation_id="EU-AIA-ART26-27-DEPLOYER-CREDIT",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("EU-AIA-ART26-27-DEPLOYER-CREDIT",),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-05",
        split="held_out",
        org_id="southern-cross-mutual",
        doc_filename="scm_dispute_and_risk_policy.docx",
        doc_format="docx",
        raw_text=(
            "Frontline chatbots may close retail customer dissatisfaction threads informally without "
            "logging a complaint or issuing written reasons or AFCA escalation options within 30 calendar days."
        ),
        phenomenon="contradiction_idr_complaint",
        ground_truth_obligation_id="AU-ASIC-RG271-COMPLAINT",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-ASIC-RG271-COMPLAINT",),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-06",
        split="held_out",
        org_id="southern-cross-mutual",
        doc_filename="scm_dispute_and_risk_policy.docx",
        doc_format="docx",
        raw_text=(
            "Product owners must analyse complaint trends quarterly to spot systemic AI errors, "
            "escalate confirmed patterns to executive risk forums, and remediate impacted retail cohorts."
        ),
        phenomenon="rg271_systemic_remediation",
        ground_truth_obligation_id="AU-ASIC-RG271-SYSTEMIC",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-ASIC-RG271-SYSTEMIC",),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-07",
        split="held_out",
        org_id="southern-cross-mutual",
        doc_filename="scm_dispute_and_risk_policy.docx",
        doc_format="docx",
        raw_text=(
            "Second-line risk officers must independently challenge AI risk assessments, include AI "
            "controls within annual audit and three-yearly independent comprehensive RMF reviews, and "
            "escalate unresolved material gaps for the Board's annual CPS 220 Risk Management Declaration."
        ),
        phenomenon="cps220_f2019l00669_review",
        ground_truth_obligation_id="AU-APRA-CPS220-REVIEW",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-APRA-CPS220-REVIEW",),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-08",
        split="held_out",
        org_id="southern-cross-mutual",
        doc_filename="scm_dispute_and_risk_policy.docx",
        doc_format="docx",
        raw_text=(
            "Once a suspected personal-information data breach is notified to APRA under CPS 234 within "
            "72 hours, teams do not need to conduct a 30-day OAIC serious-harm assessment or notify affected individuals."
        ),
        phenomenon="non_equivalent_ndb_vs_cps234_conflict",
        ground_truth_obligation_id="AU-PRIV-NDB-S26WE",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-NDB-S26WE",),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-09",
        split="held_out",
        org_id="southern-cross-mutual",
        doc_filename="scm_dispute_and_risk_policy.docx",
        doc_format="docx",
        raw_text=(
            "Automated customer fee adjustments exceeding USD 5,000 require prior sign-off from "
            "Treasury Operations before settlement."
        ),
        phenomenon="currency_mismatch_usd_vs_aud",
        ground_truth_obligation_id="ENT-DELEGATED-AUTHORITY",
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
        expected_obligation_ids=("ENT-DELEGATED-AUTHORITY",),
    ),
    # Org H-E32-2: Bayside Prudential Savings (9 clauses across TXT + PDF)
    AdversarialCalibrationClause(
        case_id="E32-HO-10",
        split="held_out",
        org_id="bayside-prudential",
        doc_filename="bayside_delegations_and_credit.txt",
        doc_format="txt",
        raw_text=(
            "Any AI-recommended account credit or fee reversal above AUD 2,500 must be held before "
            "execution until authorised by an operations delegate, with immutable approval logs kept for 7 years."
        ),
        phenomenon="stricter_monetary_threshold_aud2500",
        ground_truth_obligation_id="ENT-DELEGATED-AUTHORITY",
        ground_truth_relationship=ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
        expected_obligation_ids=("ENT-DELEGATED-AUTHORITY",),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-11",
        split="held_out",
        org_id="bayside-prudential",
        doc_filename="bayside_delegations_and_credit.txt",
        doc_format="txt",
        raw_text=(
            "Automated fee refunds up to AUD 5,000 are posted immediately to customer accounts and "
            "reviewed post-execution on a weekly sampling basis by team managers."
        ),
        phenomenon="post_execution_approval_weakening",
        ground_truth_obligation_id="ENT-DELEGATED-AUTHORITY",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
        expected_obligation_ids=("ENT-DELEGATED-AUTHORITY",),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-12",
        split="held_out",
        org_id="bayside-prudential",
        doc_filename="bayside_delegations_and_credit.txt",
        doc_format="txt",
        raw_text=(
            "Automated personal loan assessments may skip verifying the borrower's declared living "
            "expenses unless a manual underwriter opens an exception flag."
        ),
        phenomenon="conditional_waiver_responsible_lending",
        ground_truth_obligation_id="AU-NCCP-S128-131-LENDING",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-NCCP-S128-131-LENDING",),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-13",
        split="held_out",
        org_id="bayside-prudential",
        doc_filename="bayside_delegations_and_credit.txt",
        doc_format="txt",
        raw_text=(
            "Before adopting a predictive customer triage workflow, project sponsors must run a "
            "structured privacy harm workshop examining what data flows in, who may suffer detriment, "
            "and which design safeguards mitigate privacy risk."
        ),
        phenomenon="paraphrase_zero_keyword_pia",
        ground_truth_obligation_id="AU-OAIC-APPG-CH1-PIA",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-OAIC-APPG-CH1-PIA",),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-14",
        split="held_out",
        org_id="bayside-prudential",
        doc_filename="bayside_delegations_and_credit.txt",
        doc_format="txt",
        raw_text=(
            "When cloud hosting partners transfer personal customer records outside Australia for "
            "foundation model inference, legal counsel must establish binding foreign recipient "
            "obligations and assess vicarious statutory accountability."
        ),
        phenomenon="paraphrase_crossborder_foreign_hosting",
        ground_truth_obligation_id="AU-PRIV-APP8-CROSSBORDER",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP8-CROSSBORDER",),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-15",
        split="held_out",
        org_id="bayside-prudential",
        doc_filename="bayside_multi_and_edge_cases.pdf",
        doc_format="pdf",
        raw_text=(
            "Retail banking complaint handlers must document expressions of dissatisfaction and answer "
            "within maximum response timeframes with AFCA details, while cyber responders detecting "
            "personal-data leakage must initiate an eligible data breach assessment within 30 days."
        ),
        phenomenon="multi_obligation_complaint_and_ndb",
        ground_truth_obligation_id="AU-ASIC-RG271-COMPLAINT",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-ASIC-RG271-COMPLAINT", "AU-PRIV-NDB-S26WE"),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-16",
        split="held_out",
        org_id="bayside-prudential",
        doc_filename="bayside_multi_and_edge_cases.pdf",
        doc_format="pdf",
        raw_text=(
            "AI override tolerances follow Annexure G escalation procedures unless the regional "
            "committee decides to apply discretionary interim arrangements."
        ),
        phenomenon="ambiguous_annexure_and_discretion",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
        expected_obligation_ids=(),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-17",
        split="held_out",
        org_id="bayside-prudential",
        doc_filename="bayside_multi_and_edge_cases.pdf",
        doc_format="pdf",
        raw_text=(
            "Branch architectural refurbishments must limit ceiling acoustic reverberation below 55 "
            "decibels across retail waiting lounges and record semi-annual facilities inspections."
        ),
        phenomenon="adversarial_out_of_domain_acoustic_facilities",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP,
        expects_human_resolution=True,
        expected_obligation_ids=(),
    ),
    AdversarialCalibrationClause(
        case_id="E32-HO-18",
        split="held_out",
        org_id="bayside-prudential",
        doc_filename="bayside_multi_and_edge_cases.pdf",
        doc_format="pdf",
        raw_text=(
            "All internal marketing slide decks describing AI pilots must adhere to the bank's FY27 "
            "corporate typography palette, brand logo spacing and executive template standards."
        ),
        phenomenon="unmapped_corporate_brand_standard",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP,
        expects_human_resolution=True,
        expected_obligation_ids=(),
    ),
)


E32_QUESTIONNAIRE_HOLDOUT: Tuple[LabelledQuestionnaireCase, ...] = (
    LabelledQuestionnaireCase(
        case_id="E32-Q-01",
        split="held_out",
        question_id="Q-E32-APP11-3",
        domain="security",
        prompt="What technical and organisational security measures protect personal information in AI stores under APP 11.3, alongside APP 11.2 deletion?",
        response="Encryption, RBAC, annual staff security training, and automated 90-day cryptographic purge.",
        ground_truth_obligation_id="AU-PRIV-APP11-SECURITY",
    ),
    LabelledQuestionnaireCase(
        case_id="E32-Q-02",
        split="held_out",
        question_id="Q-E32-CPS220-REV",
        domain="governance",
        prompt="How does independent Line 2 risk challenge, three-yearly comprehensive RMF review, and annual Board declaration cover AI under CPS 220?",
        response="CRO challenge memo, 3-yearly independent review scope, and Board Risk Management Declaration.",
        ground_truth_obligation_id="AU-APRA-CPS220-REVIEW",
    ),
    LabelledQuestionnaireCase(
        case_id="E32-Q-03",
        split="held_out",
        question_id="Q-E32-EU-ART50",
        domain="transparency",
        prompt="Where EU Article 2 scope applies, how are natural persons informed they are interacting with an AI system or viewing synthetic outputs under Article 50?",
        response="Session-start banner disclosing AI interaction and machine-readable synthetic marking.",
        ground_truth_obligation_id="EU-AIA-ART50-TRANSPARENCY",
    ),
    LabelledQuestionnaireCase(
        case_id="E32-Q-04",
        split="held_out",
        question_id="Q-E32-EU-ART26",
        domain="eu_ai_act",
        prompt="If an Annex III creditworthiness AI system falls under EU scope, how are deployer human oversight, 6-month automatic logs, and FRIA enforced?",
        response="Assigned competent human reviewer, 6-month log retention, and completed Article 27 FRIA.",
        ground_truth_obligation_id="EU-AIA-ART26-27-DEPLOYER-CREDIT",
    ),
)
