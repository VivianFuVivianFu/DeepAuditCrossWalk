"""E3.4 Frozen Independent Evaluation Dataset (Aligned to Regulatory Pack v0.2.0).

Prepared under Phase 4 Independent Evaluation Protocol:
  1. Assembled after freezing all E3.3 / E3.4 matching rules in `policy.py`,
     `reconciliation.py`, `semantic_reconciliation.py`, and `providers.py`.
  2. Immutable ground-truth labels and SHA-256 dataset hash (`E34_DATASET_SHA256`).
  3. Zero post-evaluation rule tuning: raw numerators, denominators, Wilson 95%
     confidence intervals, and failure modes are reported as observed.
  4. Covers 30 realistic Australian banking policy clauses across 5 synthetic
     documents (PDF, DOCX, TXT) and 8 institutional questionnaire prompts across
     high-risk domains:
       - Positive full/equivalent matches (5)
       - Partial matches with missing facets/evidence (9)
       - Stricter enterprise requirements (2)
       - Waivers, exceptions, and weaker modality/timing (4)
       - Direct contradictions and permissive control omissions (4)
       - Ambiguous internal annexure / discretionary cross-references (2)
       - Multi-obligation compound clauses (2)
       - Unrelated banking operations & internal-only controls (2)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Tuple

from banking_crosswalk.models import ReconciliationRelationship
from e31_calibration_dataset import AdversarialCalibrationClause
from e3_benchmark_dataset import LabelledQuestionnaireCase


@dataclass(frozen=True)
class E34ClauseFacetAnnotation:
    case_id: str
    ground_truth_source_id: Optional[str]
    expected_canonical_facets: Tuple[str, ...]
    expected_missing_facets: Tuple[str, ...]
    domain_category: str


E34_INDEPENDENT_EVALUATION_CLAUSES: Tuple[AdversarialCalibrationClause, ...] = (
    # =========================================================================
    # Document 1: Macquarie Harbour Bank — Privacy & Data Governance Standard (PDF, 7 clauses)
    # =========================================================================
    AdversarialCalibrationClause(
        case_id="E34-IND-01",
        split="held_out",
        org_id="macquarie-harbour-bank",
        doc_filename="mhb_privacy_and_data_standard.pdf",
        doc_format="pdf",
        raw_text=(
            "Under APP 1, Macquarie Harbour Bank assigns executive privacy accountability to the Chief "
            "Privacy Officer, implements documented privacy practices and procedures across all AI products, "
            "and maintains a current, clearly expressed APP privacy policy on its public website."
        ),
        phenomenon="positive_equivalent_app1_governance",
        ground_truth_obligation_id="AU-PRIV-APP1-GOV",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-PRIV-APP1-GOV",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-02",
        split="held_out",
        org_id="macquarie-harbour-bank",
        doc_filename="mhb_privacy_and_data_standard.pdf",
        doc_format="pdf",
        raw_text=(
            "Prior to onboarding any new customer-facing analytics workflow, project sponsors must complete "
            "a Privacy Impact Assessment threshold screen and embed privacy-by-design controls into the "
            "architecture, though tracking PIA recommendations to formal closure remains optional."
        ),
        phenomenon="partial_oaic_pia_missing_closure_tracking",
        ground_truth_obligation_id="AU-OAIC-APPG-CH1-PIA",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-OAIC-APPG-CH1-PIA",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-03",
        split="held_out",
        org_id="macquarie-harbour-bank",
        doc_filename="mhb_privacy_and_data_standard.pdf",
        doc_format="pdf",
        raw_text=(
            "Before disclosing customer personal information to an overseas cloud inference recipient under "
            "APP 8, the bank must map all overseas recipients and hosting regions, execute binding APP 8 "
            "contractual reasonable steps, and document the section 16C accountability and exception assessment."
        ),
        phenomenon="positive_equivalent_app8_crossborder",
        ground_truth_obligation_id="AU-PRIV-APP8-CROSSBORDER",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-PRIV-APP8-CROSSBORDER",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-04",
        split="held_out",
        org_id="macquarie-harbour-bank",
        doc_filename="mhb_privacy_and_data_standard.pdf",
        doc_format="pdf",
        raw_text=(
            "AI feature stores holding personal information must enforce technical security measures including "
            "HSM-backed encryption at rest and role-based access controls, while organisational security "
            "training and retention destruction schedules are addressed in separate divisional handbooks."
        ),
        phenomenon="partial_app11_technical_only_missing_org_and_retention",
        ground_truth_obligation_id="AU-PRIV-APP11-SECURITY",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP11-SECURITY",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-05",
        split="held_out",
        org_id="macquarie-harbour-bank",
        doc_filename="mhb_privacy_and_data_standard.pdf",
        doc_format="pdf",
        raw_text=(
            "Under APP 11, historical customer personal information ingested into foundation model training "
            "corpora must be retained indefinitely and must not be destroyed or de-identified after account closure."
        ),
        phenomenon="contradiction_app11_indefinite_retention",
        ground_truth_obligation_id="AU-PRIV-APP11-SECURITY",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP11-SECURITY",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-06",
        split="held_out",
        org_id="macquarie-harbour-bank",
        doc_filename="mhb_privacy_and_data_standard.pdf",
        doc_format="pdf",
        raw_text=(
            "Where computer programs make automated decisions that significantly affect customer rights under "
            "APP 1.7, the bank's privacy policy discloses the kinds of personal information used in the "
            "operation of the program, without listing the specific kinds of decisions made."
        ),
        phenomenon="partial_app1_7_missing_decision_kinds",
        ground_truth_obligation_id="AU-PRIV-APP1.7-AUTOMATED",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP1.7-AUTOMATED",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-07",
        split="held_out",
        org_id="macquarie-harbour-bank",
        doc_filename="mhb_privacy_and_data_standard.pdf",
        doc_format="pdf",
        raw_text=(
            "Sensitive biometric voiceprints may be collected for fraud analytics without obtaining "
            "customer consent unless the transaction value exceeds AUD 50,000."
        ),
        phenomenon="waiver_exception_app3_sensitive_consent",
        ground_truth_obligation_id="AU-PRIV-APP3-COLLECT",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP3-COLLECT",),
    ),
    # =========================================================================
    # Document 2: Tasman Institutional Bank — Cyber, CPS 234 & CPS 230 Resilience Policy (DOCX, 7 clauses)
    # =========================================================================
    AdversarialCalibrationClause(
        case_id="E34-IND-08",
        split="held_out",
        org_id="tasman-institutional",
        doc_filename="tib_cyber_and_resilience_policy.docx",
        doc_format="docx",
        raw_text=(
            "Under APRA CPS 234, the bank maintains incident detection mechanisms and documented response "
            "and escalation plans, screens material information security incidents for APRA notification "
            "within 72 hours, and tracks material security control weaknesses to remediation."
        ),
        phenomenon="positive_equivalent_cps234_incident",
        ground_truth_obligation_id="AU-APRA-CPS234-INCIDENT",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-APRA-CPS234-INCIDENT",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-09",
        split="held_out",
        org_id="tasman-institutional",
        doc_filename="tib_cyber_and_resilience_policy.docx",
        doc_format="docx",
        raw_text=(
            "Material CPS 234 information security incidents impacting production AI scoring engines must "
            "be notified to APRA within 12 hours of detection, accompanied by an incident response log "
            "and control weakness tracking ticket."
        ),
        phenomenon="stricter_12h_cps234_incident_notification",
        ground_truth_obligation_id="AU-APRA-CPS234-INCIDENT",
        ground_truth_relationship=ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-APRA-CPS234-INCIDENT",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-10",
        split="held_out",
        org_id="tasman-institutional",
        doc_filename="tib_cyber_and_resilience_policy.docx",
        doc_format="docx",
        raw_text=(
            "Material CPS 234 information security incidents affecting wholesale banking AI infrastructure "
            "must be reported to APRA within 15 days after internal forensic investigation sign-off."
        ),
        phenomenon="contradiction_15d_cps234_incident_deadline",
        ground_truth_obligation_id="AU-APRA-CPS234-INCIDENT",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-APRA-CPS234-INCIDENT",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-11",
        split="held_out",
        org_id="tasman-institutional",
        doc_filename="tib_cyber_and_resilience_policy.docx",
        doc_format="docx",
        raw_text=(
            "For third-party AI providers under CPS 230, procurement teams must complete provider materiality "
            "assessments, pre-contract due diligence, and contract control definitions, while ongoing "
            "performance and exit monitoring is deferred to future policy updates."
        ),
        phenomenon="partial_cps230_sp_missing_exit_monitoring",
        ground_truth_obligation_id="AU-APRA-CPS230-SP",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-APRA-CPS230-SP",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-12",
        split="held_out",
        org_id="tasman-institutional",
        doc_filename="tib_cyber_and_resilience_policy.docx",
        doc_format="docx",
        raw_text=(
            "Under CPS 230 business continuity management, critical operation dependencies on AI decision "
            "services must be mapped and disruption tolerance levels with manual fallback procedures defined, "
            "without requiring periodic business continuity exercises."
        ),
        phenomenon="partial_cps230_bcp_missing_continuity_testing",
        ground_truth_obligation_id="AU-APRA-CPS230-BCP",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-APRA-CPS230-BCP",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-13",
        split="held_out",
        org_id="tasman-institutional",
        doc_filename="tib_cyber_and_resilience_policy.docx",
        doc_format="docx",
        raw_text=(
            "Material cyber incidents involving personal-data leakage must be notified to APRA within "
            "72 hours under CPS 234; while under Privacy Act Part IIIC the bank completes its OAIC "
            "Notifiable Data Breach serious-harm assessment within 30 days."
        ),
        phenomenon="multi_obligation_cps234_72h_and_oaic_ndb_30d",
        ground_truth_obligation_id="AU-APRA-CPS234-INCIDENT",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-APRA-CPS234-INCIDENT", "AU-PRIV-NDB-S26WE"),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-14",
        split="held_out",
        org_id="tasman-institutional",
        doc_filename="tib_cyber_and_resilience_policy.docx",
        doc_format="docx",
        raw_text=(
            "When engaging an offshore material AI service provider under CPS 230, the bank updates its "
            "Material Service Provider register and consults APRA prior to material offshoring; while "
            "under APP 8 it maps overseas recipients and hosting regions for personal information."
        ),
        phenomenon="multi_obligation_cps230_notify_and_app8_crossborder",
        ground_truth_obligation_id="AU-APRA-CPS230-NOTIFY",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-APRA-CPS230-NOTIFY", "AU-PRIV-APP8-CROSSBORDER"),
    ),
    # =========================================================================
    # Document 3: Murray River Retail Banking — Complaints, Credit & Conduct Policy (PDF, 6 clauses)
    # =========================================================================
    AdversarialCalibrationClause(
        case_id="E34-IND-15",
        split="held_out",
        org_id="murray-river-retail",
        doc_filename="mrrb_complaints_credit_conduct.pdf",
        doc_format="pdf",
        raw_text=(
            "In accordance with ASIC RG 271, all customer expressions of dissatisfaction regarding AI "
            "assisted decisions are broadly recognised as complaints, recorded in the central IDR complaint "
            "register, answered within statutory response timeframes with complete written reasons and AFCA "
            "escalation rights, and provided a human escalation pathway."
        ),
        phenomenon="positive_equivalent_rg271_complaint",
        ground_truth_obligation_id="AU-ASIC-RG271-COMPLAINT",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-ASIC-RG271-COMPLAINT",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-16",
        split="held_out",
        org_id="murray-river-retail",
        doc_filename="mrrb_complaints_credit_conduct.pdf",
        doc_format="pdf",
        raw_text=(
            "Frontline branch staff may close customer complaints about automated card freezes without "
            "recording the matter in the IDR complaint log or notifying the customer of AFCA escalation rights."
        ),
        phenomenon="contradiction_permissive_omission_rg271_complaint",
        ground_truth_obligation_id="AU-ASIC-RG271-COMPLAINT",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-ASIC-RG271-COMPLAINT",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-17",
        split="held_out",
        org_id="murray-river-retail",
        doc_filename="mrrb_complaints_credit_conduct.pdf",
        doc_format="pdf",
        raw_text=(
            "Under ASIC RG 271 systemic issue governance, complaint data from AI credit declines is "
            "regularly analysed against defined systemic issue thresholds and escalated to senior "
            "management, without a documented process for remediating affected customers."
        ),
        phenomenon="partial_rg271_systemic_missing_remediation",
        ground_truth_obligation_id="AU-ASIC-RG271-SYSTEMIC",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-ASIC-RG271-SYSTEMIC",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-18",
        split="held_out",
        org_id="murray-river-retail",
        doc_filename="mrrb_complaints_credit_conduct.pdf",
        doc_format="pdf",
        raw_text=(
            "Under NCCP Act section 128 responsible lending obligations, automated home-loan origination "
            "workflows capture consumer requirements and objectives, verify the consumer's financial "
            "situation and living expenses from reliable evidence, and enforce an unsuitability and "
            "substantial hardship screen."
        ),
        phenomenon="partial_nccp_s128_missing_written_assessment_retrieval",
        ground_truth_obligation_id="AU-NCCP-S128-131-LENDING",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-NCCP-S128-131-LENDING",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-19",
        split="held_out",
        org_id="murray-river-retail",
        doc_filename="mrrb_complaints_credit_conduct.pdf",
        doc_format="pdf",
        raw_text=(
            "Automated credit limit increases up to USD 10,000 may be executed for international premier "
            "cardholders prior to human affordability review."
        ),
        phenomenon="currency_mismatch_usd_10000_threshold",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-NAIC-AI6-TEST-HUMAN",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-20",
        split="held_out",
        org_id="murray-river-retail",
        doc_filename="mrrb_complaints_credit_conduct.pdf",
        doc_format="pdf",
        raw_text=(
            "Automated fee refunds above AUD 1,000 are executed immediately by the billing assistant and "
            "reviewed retrospectively by a Team Leader during end-of-week reconciliation."
        ),
        phenomenon="weaker_post_execution_approval_timing",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-NAIC-AI6-TEST-HUMAN",),
    ),
    # =========================================================================
    # Document 4: Capitol AI Governance & EU Cross-Border Charter (TXT, 6 clauses)
    # =========================================================================
    AdversarialCalibrationClause(
        case_id="E34-IND-21",
        split="held_out",
        org_id="capitol-ai-governance",
        doc_filename="capitol_ai_governance_charter.txt",
        doc_format="txt",
        raw_text=(
            "Consistent with Australia's AI Ethics Principles and the Voluntary AI Safety Standard, high-impact "
            "AI systems undergo pre-deployment testing and ongoing drift monitoring, maintain meaningful "
            "human oversight with an emergency kill switch, and provide a customer contestability and "
            "recourse pathway for automated decisions above AUD 1,000 with human approval before execution."
        ),
        phenomenon="positive_equivalent_naic_ai6_human_oversight",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-NAIC-AI6-TEST-HUMAN",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-22",
        split="held_out",
        org_id="capitol-ai-governance",
        doc_filename="capitol_ai_governance_charter.txt",
        doc_format="txt",
        raw_text=(
            "Staff are prohibited from executing automated customer fee adjustments above AUD 250 without "
            "dual human approval before execution, reinforced by pre-deployment drift monitoring, kill-switch "
            "controls, and a customer contestability pathway."
        ),
        phenomenon="stricter_protective_prohibition_aud_250_dual_approval",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-NAIC-AI6-TEST-HUMAN",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-23",
        split="held_out",
        org_id="capitol-ai-governance",
        doc_filename="capitol_ai_governance_charter.txt",
        doc_format="txt",
        raw_text=(
            "For high-risk creditworthiness AI systems listed in EU AI Act Annex III point 5(b), the bank "
            "assigns trained human oversight personnel under Article 26(2) and completes an Article 27 "
            "fundamental rights impact assessment, without retaining automatic system logs for 6 months."
        ),
        phenomenon="partial_eu_art26_27_missing_6month_logs_and_fraud_screen",
        ground_truth_obligation_id="EU-AIA-ART26-27-DEPLOYER-CREDIT",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("EU-AIA-ART26-27-DEPLOYER-CREDIT",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-24",
        split="held_out",
        org_id="capitol-ai-governance",
        doc_filename="capitol_ai_governance_charter.txt",
        doc_format="txt",
        raw_text=(
            "Under NIST AI RMF MEASURE and MANAGE functions, model validation teams evaluate fairness and "
            "explainability metrics and log residual risk acceptance and drift response actions, while "
            "formal TEVV validity and reliability benchmarking is not yet standardised."
        ),
        phenomenon="partial_nist_measure_manage_missing_tevv",
        ground_truth_obligation_id="NIST-AI-RMF-MEASURE-MANAGE",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("NIST-AI-RMF-MEASURE-MANAGE",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-25",
        split="held_out",
        org_id="capitol-ai-governance",
        doc_filename="capitol_ai_governance_charter.txt",
        doc_format="txt",
        raw_text=(
            "Model developers are not required to register experimental generative AI use cases in the "
            "enterprise AI inventory or assess consumer harm and bias prior to production deployment."
        ),
        phenomenon="contradiction_absence_of_control_asic_rep798",
        ground_truth_obligation_id="AU-ASIC-REP798-AI-GAP",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-ASIC-REP798-AI-GAP",),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-26",
        split="held_out",
        org_id="capitol-ai-governance",
        doc_filename="capitol_ai_governance_charter.txt",
        doc_format="txt",
        raw_text=(
            "Credit scoring model validation teams should endeavour to review third-party training data "
            "dictionaries under CPG 235 where deemed appropriate by management."
        ),
        phenomenon="ambiguous_management_discretion_clause",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
        expected_obligation_ids=(),
    ),
    # =========================================================================
    # Document 5: Southern Tablelands Mutual — Operations, Annexures & Telemetry Manual (DOCX, 4 clauses)
    # =========================================================================
    AdversarialCalibrationClause(
        case_id="E34-IND-27",
        split="held_out",
        org_id="southern-tablelands-mutual",
        doc_filename="stm_operations_and_telemetry_manual.docx",
        doc_format="docx",
        raw_text=(
            "Transitional AI model risk sign-offs and override thresholds must follow Annexure D2 interim "
            "governance protocols until the board ratifies the permanent charter."
        ),
        phenomenon="ambiguous_missing_internal_annexure_d2",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
        expected_obligation_ids=(),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-28",
        split="held_out",
        org_id="southern-tablelands-mutual",
        doc_filename="stm_operations_and_telemetry_manual.docx",
        doc_format="docx",
        raw_text=(
            "All internal LLM prompt logging events and container build provenance manifests must be "
            "archived in immutable WORM storage inside the enterprise telemetry vault for 7 years."
        ),
        phenomenon="internal_enterprise_only_worm_prompt_telemetry",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
        expected_obligation_ids=(),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-29",
        split="held_out",
        org_id="southern-tablelands-mutual",
        doc_filename="stm_operations_and_telemetry_manual.docx",
        doc_format="docx",
        raw_text=(
            "Corporate brand slide decks and branch marketing posters must follow the FY27 corporate "
            "typography palette and brand logo spacing guidelines."
        ),
        phenomenon="unrelated_corporate_typography_noise",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP,
        expects_human_resolution=True,
        expected_obligation_ids=(),
    ),
    AdversarialCalibrationClause(
        case_id="E34-IND-30",
        split="held_out",
        org_id="southern-tablelands-mutual",
        doc_filename="stm_operations_and_telemetry_manual.docx",
        doc_format="docx",
        raw_text=(
            "Data center facility engineers must record Scope 2 ESG carbon-intensity megawatt cooling "
            "metrics across liquid-cooled GPU racks every quarter."
        ),
        phenomenon="unrelated_esg_cooling_telemetry_noise",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP,
        expects_human_resolution=True,
        expected_obligation_ids=(),
    ),
)


E34_CLAUSE_FACET_ANNOTATIONS: Tuple[E34ClauseFacetAnnotation, ...] = (
    E34ClauseFacetAnnotation(
        case_id="E34-IND-01",
        ground_truth_source_id="AU-PRIVACY-ACT",
        expected_canonical_facets=(
            "privacy_accountability_assigned",
            "privacy_practices_implemented",
            "privacy_policy_current",
        ),
        expected_missing_facets=(),
        domain_category="privacy",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-02",
        ground_truth_source_id="OAIC-APP-GUIDELINES",
        expected_canonical_facets=(
            "pia_threshold_screen_completed",
            "privacy_by_design_controls_embedded",
        ),
        expected_missing_facets=("pia_recommendations_tracked_to_closure",),
        domain_category="privacy",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-03",
        ground_truth_source_id="AU-PRIVACY-ACT",
        expected_canonical_facets=(
            "overseas_recipients_and_regions_mapped",
            "app8_reasonable_steps_and_contracts_in_place",
            "s16c_accountability_and_exception_assessed",
        ),
        expected_missing_facets=(),
        domain_category="privacy",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-04",
        ground_truth_source_id="AU-PRIVACY-ACT",
        expected_canonical_facets=("technical_security_measures_implemented",),
        expected_missing_facets=(
            "organisational_security_measures_implemented",
            "retention_schedule_applied",
            "destruction_or_deidentification_verified",
        ),
        domain_category="privacy_security",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-05",
        ground_truth_source_id="AU-PRIVACY-ACT",
        expected_canonical_facets=(),
        expected_missing_facets=(
            "technical_security_measures_implemented",
            "organisational_security_measures_implemented",
            "retention_schedule_applied",
            "destruction_or_deidentification_verified",
        ),
        domain_category="privacy_security",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-06",
        ground_truth_source_id="AU-PRIVACY-ACT",
        expected_canonical_facets=(
            "significant_decision_screened",
            "personal_information_kinds_disclosed",
        ),
        expected_missing_facets=("decision_kinds_disclosed",),
        domain_category="privacy",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-07",
        ground_truth_source_id="AU-PRIVACY-ACT",
        expected_canonical_facets=("sensitive_information_consent",),
        expected_missing_facets=("collection_purpose_defined", "necessity_assessed"),
        domain_category="privacy",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-08",
        ground_truth_source_id="APRA-CPS234",
        expected_canonical_facets=(
            "incident_detection_defined",
            "response_and_escalation_defined",
            "apra_notification_screened",
            "material_weaknesses_tracked",
        ),
        expected_missing_facets=(),
        domain_category="incident_reporting",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-09",
        ground_truth_source_id="APRA-CPS234",
        expected_canonical_facets=(
            "incident_detection_defined",
            "response_and_escalation_defined",
            "apra_notification_screened",
            "material_weaknesses_tracked",
        ),
        expected_missing_facets=(),
        domain_category="incident_reporting",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-10",
        ground_truth_source_id="APRA-CPS234",
        expected_canonical_facets=("apra_notification_screened",),
        expected_missing_facets=(
            "incident_detection_defined",
            "response_and_escalation_defined",
            "material_weaknesses_tracked",
        ),
        domain_category="incident_reporting",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-11",
        ground_truth_source_id="APRA-CPS230",
        expected_canonical_facets=(
            "provider_materiality_assessed",
            "due_diligence_completed",
            "contract_controls_defined",
        ),
        expected_missing_facets=("performance_and_exit_monitored",),
        domain_category="third_party_resilience",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-12",
        ground_truth_source_id="APRA-CPS230",
        expected_canonical_facets=(
            "critical_operation_dependency_mapped",
            "tolerance_and_fallback_defined",
        ),
        expected_missing_facets=("continuity_plan_tested",),
        domain_category="third_party_resilience",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-13",
        ground_truth_source_id="APRA-CPS234",
        expected_canonical_facets=(
            "apra_notification_screened",
            "ai_data_leakage_detection_enabled",
            "ndb_30day_assessment_workflow_defined",
        ),
        expected_missing_facets=(
            "incident_detection_defined",
            "response_and_escalation_defined",
            "material_weaknesses_tracked",
            "oaic_and_individual_notification_prepared",
        ),
        domain_category="incident_reporting",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-14",
        ground_truth_source_id="APRA-CPS230",
        expected_canonical_facets=(
            "msp_register_updated_for_ai_vendors",
            "prior_apra_consultation_for_material_offshoring",
            "overseas_recipients_and_regions_mapped",
        ),
        expected_missing_facets=(
            "incident_72h_and_agreement_20bd_notifications_defined",
            "app8_reasonable_steps_and_contracts_in_place",
            "s16c_accountability_and_exception_assessed",
        ),
        domain_category="third_party_resilience",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-15",
        ground_truth_source_id="ASIC-RG271",
        expected_canonical_facets=(
            "complaints_broadly_recognised",
            "complaints_recorded",
            "response_timeframes_enforced",
            "response_content_complete",
            "human_escalation_available",
        ),
        expected_missing_facets=(),
        domain_category="customer_complaints",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-16",
        ground_truth_source_id="ASIC-RG271",
        expected_canonical_facets=(),
        expected_missing_facets=(
            "complaints_broadly_recognised",
            "complaints_recorded",
            "response_timeframes_enforced",
            "response_content_complete",
            "human_escalation_available",
        ),
        domain_category="customer_complaints",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-17",
        ground_truth_source_id="ASIC-RG271",
        expected_canonical_facets=(
            "complaint_data_analysed",
            "systemic_issue_thresholds_defined",
            "systemic_issues_escalated",
        ),
        expected_missing_facets=("affected_customers_remediated",),
        domain_category="customer_complaints",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-18",
        ground_truth_source_id="AU-NCCP-ACT",
        expected_canonical_facets=(
            "consumer_requirements_and_objectives_captured",
            "financial_situation_verified_from_reliable_evidence",
            "unsuitability_and_substantial_hardship_screen_enforced",
        ),
        expected_missing_facets=("written_unsuitability_assessment_retrievable",),
        domain_category="human_oversight_approval",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-19",
        ground_truth_source_id="DISR-AI6",
        expected_canonical_facets=(),
        expected_missing_facets=(
            "pre_deployment_and_ongoing_drift_monitoring",
            "meaningful_human_oversight_and_kill_switch",
            "customer_contestability_and_recourse_pathway",
        ),
        domain_category="human_oversight_approval",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-20",
        ground_truth_source_id="DISR-AI6",
        expected_canonical_facets=("approval_threshold_defined",),
        expected_missing_facets=(
            "pre_deployment_and_ongoing_drift_monitoring",
            "meaningful_human_oversight_and_kill_switch",
            "customer_contestability_and_recourse_pathway",
        ),
        domain_category="human_oversight_approval",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-21",
        ground_truth_source_id="DISR-AI6",
        expected_canonical_facets=(
            "human_approval_required",
            "approval_threshold_defined",
            "pre_execution_block",
            "pre_deployment_and_ongoing_drift_monitoring",
            "meaningful_human_oversight_and_kill_switch",
            "customer_contestability_and_recourse_pathway",
        ),
        expected_missing_facets=(),
        domain_category="human_oversight_approval",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-22",
        ground_truth_source_id="DISR-AI6",
        expected_canonical_facets=(
            "human_approval_required",
            "approval_threshold_defined",
            "pre_execution_block",
            "pre_deployment_and_ongoing_drift_monitoring",
            "meaningful_human_oversight_and_kill_switch",
            "customer_contestability_and_recourse_pathway",
        ),
        expected_missing_facets=(),
        domain_category="human_oversight_approval",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-23",
        ground_truth_source_id="EU-AI-ACT",
        expected_canonical_facets=(
            "deployer_human_oversight_assigned",
            "article27_fundamental_rights_impact_assessment_completed",
        ),
        expected_missing_facets=(
            "annex3_5b_credit_vs_fraud_exemption_assessed",
            "automatic_logs_retained_6months",
        ),
        domain_category="eu_ai_act",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-24",
        ground_truth_source_id="NIST-AI-RMF",
        expected_canonical_facets=(
            "fairness_and_explainability_metrics_evaluated",
            "residual_risk_acceptance_and_drift_response_logged",
        ),
        expected_missing_facets=("tevv_validity_and_reliability_benchmarked",),
        domain_category="ai_risk_monitoring",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-25",
        ground_truth_source_id="ASIC-REP798",
        expected_canonical_facets=(),
        expected_missing_facets=(
            "use_case_registered_in_enterprise_ai_inventory",
            "consumer_harm_and_bias_assessed_pre_deployment",
            "generative_and_third_party_ai_governance_updated",
        ),
        domain_category="ai_governance",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-26",
        ground_truth_source_id=None,
        expected_canonical_facets=(),
        expected_missing_facets=(),
        domain_category="ambiguous",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-27",
        ground_truth_source_id=None,
        expected_canonical_facets=(),
        expected_missing_facets=(),
        domain_category="ambiguous",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-28",
        ground_truth_source_id=None,
        expected_canonical_facets=(),
        expected_missing_facets=(),
        domain_category="enterprise_only",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-29",
        ground_truth_source_id=None,
        expected_canonical_facets=(),
        expected_missing_facets=(),
        domain_category="unrelated_noise",
    ),
    E34ClauseFacetAnnotation(
        case_id="E34-IND-30",
        ground_truth_source_id=None,
        expected_canonical_facets=(),
        expected_missing_facets=(),
        domain_category="unrelated_noise",
    ),
)


E34_INDEPENDENT_QUESTIONNAIRE_CASES: Tuple[LabelledQuestionnaireCase, ...] = (
    LabelledQuestionnaireCase(
        case_id="E34-Q-01",
        split="held_out",
        question_id="Q-E34-APP8",
        domain="privacy",
        prompt="How does the bank map overseas AI recipients, execute APP 8 contractual reasonable steps, and document section 16C cross-border accountability?",
        response="Overseas data-flow register, binding APP 8 processor clauses, and documented s 16C assessment.",
        ground_truth_obligation_id="AU-PRIV-APP8-CROSSBORDER",
    ),
    LabelledQuestionnaireCase(
        case_id="E34-Q-02",
        split="held_out",
        question_id="Q-E34-CPS234-INC",
        domain="security",
        prompt="What processes ensure material information security incidents affecting AI are detected, escalated, notified to APRA within 72 hours, and tracked under CPS 234?",
        response="24/7 SIEM incident detection, CPS 234 72-hour APRA notification triage, and control weakness register.",
        ground_truth_obligation_id="AU-APRA-CPS234-INCIDENT",
    ),
    LabelledQuestionnaireCase(
        case_id="E34-Q-03",
        split="held_out",
        question_id="Q-E34-NDB",
        domain="privacy",
        prompt="How are AI personal-data leakage events assessed within 30 days for serious harm and notified to the OAIC and affected individuals under Part IIIC?",
        response="DLP leakage alerts, 30-day OAIC NDB serious-harm assessment workflow, and statutory notification templates.",
        ground_truth_obligation_id="AU-PRIV-NDB-S26WE",
    ),
    LabelledQuestionnaireCase(
        case_id="E34-Q-04",
        split="held_out",
        question_id="Q-E34-RG271-COMP",
        domain="complaints",
        prompt="How are customer complaints regarding AI-assisted banking decisions recognised, logged in the IDR register, answered within RG 271 timeframes, and escalated to a human reviewer?",
        response="Omnichannel complaint recognition, central IDR register, 30-day/21-day SLA tracking with AFCA rights, and human review pathway.",
        ground_truth_obligation_id="AU-ASIC-RG271-COMPLAINT",
    ),
    LabelledQuestionnaireCase(
        case_id="E34-Q-05",
        split="held_out",
        question_id="Q-E34-NAIC-AI6",
        domain="oversight",
        prompt="How are pre-deployment testing, ongoing drift monitoring, meaningful human oversight with kill-switch capability, and customer contestability enforced for high-impact AI?",
        response="Pre-release validation gate, continuous drift alerts, emergency kill switch, and customer recourse workflow.",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
    ),
    LabelledQuestionnaireCase(
        case_id="E34-Q-06",
        split="held_out",
        question_id="Q-E34-CPS230-SP",
        domain="third_party",
        prompt="What materiality assessment, due diligence, contractual controls, and exit monitoring apply to third-party AI service providers under CPS 230?",
        response="CPS 230 vendor materiality scorecard, pre-contract due diligence pack, mandatory audit/security clauses, and annual exit plan review.",
        ground_truth_obligation_id="AU-APRA-CPS230-SP",
    ),
    LabelledQuestionnaireCase(
        case_id="E34-Q-07",
        split="held_out",
        question_id="Q-E34-NCCP-S128",
        domain="credit",
        prompt="How do automated credit assessment models capture consumer objectives, verify financial situation from reliable evidence, screen for unsuitability, and retain retrievable assessments under NCCP s 128?",
        response="Structured borrower objective intake, Open Banking income/expense verification, hardship/unsuitability rule engine, and archived written assessment.",
        ground_truth_obligation_id="AU-NCCP-S128-131-LENDING",
    ),
    LabelledQuestionnaireCase(
        case_id="E34-Q-08",
        split="held_out",
        question_id="Q-E34-APP1-7",
        domain="privacy",
        prompt="How does the bank's privacy policy disclose significant automated decisions made by computer programs and the kinds of personal information and decisions involved under APP 1.7?",
        response="Automated decision register linked to public APP privacy policy listing personal information categories and decision types.",
        ground_truth_obligation_id="AU-PRIV-APP1.7-AUTOMATED",
    ),
)


def serialize_e34_dataset_payload() -> dict:
    ann_by_id = {a.case_id: a for a in E34_CLAUSE_FACET_ANNOTATIONS}
    clauses_payload = []
    for c in E34_INDEPENDENT_EVALUATION_CLAUSES:
        ann = ann_by_id[c.case_id]
        clauses_payload.append(
            {
                "case_id": c.case_id,
                "split": c.split,
                "org_id": c.org_id,
                "doc_filename": c.doc_filename,
                "doc_format": c.doc_format,
                "raw_text": c.raw_text,
                "phenomenon": c.phenomenon,
                "domain_category": ann.domain_category,
                "ground_truth_obligation_id": c.ground_truth_obligation_id,
                "ground_truth_source_id": ann.ground_truth_source_id,
                "ground_truth_relationship": c.ground_truth_relationship.value,
                "expects_human_resolution": c.expects_human_resolution,
                "expected_obligation_ids": list(c.expected_obligation_ids),
                "expected_canonical_facets": list(ann.expected_canonical_facets),
                "expected_missing_facets": list(ann.expected_missing_facets),
            }
        )
    q_payload = [
        {
            "case_id": q.case_id,
            "split": q.split,
            "question_id": q.question_id,
            "domain": q.domain,
            "prompt": q.prompt,
            "response": q.response,
            "ground_truth_obligation_id": q.ground_truth_obligation_id,
        }
        for q in E34_INDEPENDENT_QUESTIONNAIRE_CASES
    ]
    return {
        "dataset_id": "DEEPAUDIT-E34-INDEPENDENT-EVAL-V1",
        "dataset_version": "1.0.0",
        "target_regulatory_pack_id": "AU-BANKING-REG-PACK-0.1",
        "target_regulatory_pack_version": "0.2.0",
        "n_clauses": len(clauses_payload),
        "n_questionnaire_cases": len(q_payload),
        "clauses": clauses_payload,
        "questionnaire_cases": q_payload,
    }


def compute_e34_dataset_sha256() -> str:
    payload = serialize_e34_dataset_payload()
    canonical_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()
