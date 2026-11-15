"""E3.1 Adversarial Calibration Benchmark Dataset (24 Synthetic Multi-Phenomenon Clauses).

Covers all 9 required semantic matching & regulatory reconciliation phenomena across
two strictly disjoint splits:
  - Development Split (E31-DEV-01 .. E31-DEV-12, N=12)
  - Locked Holdout Split (E31-HO-01 .. E31-HO-12, N=12)

Phenomena covered on both splits:
  1. paraphrase_zero_keyword      - Paraphrases without shared statutory keywords
  2. close_neighbour_distinction  - Closely related obligations that must not be conflated
  3. negation_or_waiver           - Explicit exemptions, negations, and discretionary waivers
  4. threshold_or_currency_shift  - Cross-currency or shifted numerical thresholds
  5. post_execution_approval      - Post-execution / retrospective approval vs pre-execution gate
  6. multi_obligation_clause      - Single clause imposing multiple external obligations
  7. ambiguous_or_incomplete      - Vague annex/schedule or discretionary references
  8. adversarial_keyword_decoy    - Unrelated domains sharing surface regulatory keywords
  9. internal_enterprise_only     - Internal vault/treasury rules with no external substitute

All content is 100% synthetic (DataClassification.PUBLIC_OR_SYNTHETIC) so live Gemini
free-tier calibration runs never handle confidential customer data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from banking_crosswalk.models import ReconciliationRelationship


@dataclass(frozen=True)
class AdversarialCalibrationClause:
    case_id: str
    split: str  # "dev" or "held_out"
    org_id: str
    doc_filename: str
    doc_format: str  # "pdf", "docx", "txt"
    raw_text: str
    phenomenon: str
    ground_truth_obligation_id: Optional[str]
    ground_truth_relationship: ReconciliationRelationship
    expects_human_resolution: bool
    expected_obligation_ids: Tuple[str, ...] = ()


E31_CALIBRATION_CLAUSES: Tuple[AdversarialCalibrationClause, ...] = (
    # ─────────────────────────────────────────────────────────────────────────
    # DEVELOPMENT SPLIT (N=12) — Meridian Digital Banking Corp
    # ─────────────────────────────────────────────────────────────────────────
    AdversarialCalibrationClause(
        case_id="E31-DEV-01",
        split="dev",
        org_id="meridian-digital",
        doc_filename="meridian_ai_privacy_notice_standard.pdf",
        doc_format="pdf",
        raw_text=(
            "Whenever software pipelines automatically score an applicant or materially shape an outcome "
            "affecting personal rights or interests using customer profile attributes, public privacy notices "
            "must specify the kinds of personal information ingested, the kinds of decisions made, and whether "
            "decisions are made solely or substantially assisted by the program."
        ),
        phenomenon="paraphrase_zero_keyword",
        ground_truth_obligation_id="AU-PRIV-APP1.7-AUTOMATED",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-PRIV-APP1.7-AUTOMATED",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-DEV-02",
        split="dev",
        org_id="meridian-digital",
        doc_filename="meridian_ai_privacy_notice_standard.pdf",
        doc_format="pdf",
        raw_text=(
            "Before transmitting customer personal details to foreign cloud inference clusters, teams must map "
            "all overseas recipient countries in the regional register and execute enforceable contractual safeguards."
        ),
        phenomenon="paraphrase_zero_keyword",
        ground_truth_obligation_id="AU-PRIV-APP8-CROSSBORDER",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP8-CROSSBORDER",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-DEV-03",
        split="dev",
        org_id="meridian-digital",
        doc_filename="meridian_cyber_incident_policy.docx",
        doc_format="docx",
        raw_text=(
            "Security operations must maintain cyber incident detection and response escalation plans, notify APRA "
            "within 24 hours of becoming aware of a material information security incident, and track and report "
            "material weaknesses in security controls."
        ),
        phenomenon="close_neighbour_distinction",
        ground_truth_obligation_id="AU-APRA-CPS234-INCIDENT",
        ground_truth_relationship=ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-APRA-CPS234-INCIDENT",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-DEV-04",
        split="dev",
        org_id="meridian-digital",
        doc_filename="meridian_cyber_incident_policy.docx",
        doc_format="docx",
        raw_text=(
            "AI safety teams must monitor for prompt-injection data leakage and exfiltration, complete an eligible "
            "data breach seriousness assessment within 10 calendar days, and prepare OAIC and affected individual notifications."
        ),
        phenomenon="close_neighbour_distinction",
        ground_truth_obligation_id="AU-PRIV-NDB-S26WE",
        ground_truth_relationship=ReconciliationRelationship.STRICTER_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-PRIV-NDB-S26WE",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-DEV-05",
        split="dev",
        org_id="meridian-digital",
        doc_filename="meridian_credit_automation_addendum.txt",
        doc_format="txt",
        raw_text=(
            "Automated digital credit assessments are not required to verify an applicant's financial situation "
            "from reliable evidence or keep a written unsuitability assessment retrievable during fast-track approval."
        ),
        phenomenon="negation_or_waiver",
        ground_truth_obligation_id="AU-NCCP-S128-131-LENDING",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-NCCP-S128-131-LENDING",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-DEV-06",
        split="dev",
        org_id="meridian-digital",
        doc_filename="meridian_credit_automation_addendum.txt",
        doc_format="txt",
        raw_text=(
            "All automated credit limit increases exceeding NZD 1,000 must obtain pre-execution approval from an Authorised Officer."
        ),
        phenomenon="threshold_or_currency_shift",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-NAIC-AI6-TEST-HUMAN",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-DEV-07",
        split="dev",
        org_id="meridian-digital",
        doc_filename="meridian_credit_automation_addendum.txt",
        doc_format="txt",
        raw_text=(
            "Automated customer fee rebates above AUD 500 may execute overnight provided a lending specialist reviews "
            "and countersigns post-execution sampling batches within 5 business days."
        ),
        phenomenon="post_execution_approval",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-NAIC-AI6-TEST-HUMAN",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-DEV-08",
        split="dev",
        org_id="meridian-digital",
        doc_filename="meridian_multi_control_policy.txt",
        doc_format="txt",
        raw_text=(
            "Before disclosing customer personal records to offshore AI hosting regions, systems must map overseas "
            "recipients with binding contractual safeguards while enforcing role-based encryption and retention-schedule destruction."
        ),
        phenomenon="multi_obligation_clause",
        ground_truth_obligation_id="AU-PRIV-APP8-CROSSBORDER",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP8-CROSSBORDER", "AU-PRIV-APP11-SECURITY"),
    ),
    AdversarialCalibrationClause(
        case_id="E31-DEV-09",
        split="dev",
        org_id="meridian-digital",
        doc_filename="meridian_multi_control_policy.txt",
        doc_format="txt",
        raw_text=(
            "All chatbot customer dissatisfaction must be recorded and answered with written IDR reasons and AFCA notice "
            "within 21 calendar days, and suspected eligible data breach leakage must immediately enter 30-day OAIC assessment."
        ),
        phenomenon="multi_obligation_clause",
        ground_truth_obligation_id="AU-ASIC-RG271-COMPLAINT",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-ASIC-RG271-COMPLAINT", "AU-PRIV-NDB-S26WE"),
    ),
    AdversarialCalibrationClause(
        case_id="E31-DEV-10",
        split="dev",
        org_id="meridian-digital",
        doc_filename="meridian_multi_control_policy.txt",
        doc_format="txt",
        raw_text=(
            "Product engineering must manage model risk controls in accordance with Schedule G limits "
            "as modified from time to time at division management discretion."
        ),
        phenomenon="ambiguous_or_incomplete",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
        expected_obligation_ids=(),
    ),
    AdversarialCalibrationClause(
        case_id="E31-DEV-11",
        split="dev",
        org_id="meridian-digital",
        doc_filename="meridian_ops_misc.txt",
        doc_format="txt",
        raw_text=(
            "Brand design teams track social-media sentiment icons across mobile UI sprints to calibrate button contrast "
            "thresholds prior to quarterly customer townhall slide decks."
        ),
        phenomenon="adversarial_keyword_decoy",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP,
        expects_human_resolution=True,
        expected_obligation_ids=(),
    ),
    AdversarialCalibrationClause(
        case_id="E31-DEV-12",
        split="dev",
        org_id="meridian-digital",
        doc_filename="meridian_ops_misc.txt",
        doc_format="txt",
        raw_text=(
            "All internal prompt logging events and signed build provenance manifests must be archived in immutable "
            "WORM storage within the internal telemetry vault and engineering registry."
        ),
        phenomenon="internal_enterprise_only",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
        expected_obligation_ids=(),
    ),
    # ─────────────────────────────────────────────────────────────────────────
    # LOCKED HOLDOUT SPLIT (N=12) — Pacific Harbour Credit Union
    # Do NOT tune prompts or thresholds against these cases.
    # ─────────────────────────────────────────────────────────────────────────
    AdversarialCalibrationClause(
        case_id="E31-HO-01",
        split="held_out",
        org_id="pacific-harbour-cu",
        doc_filename="pacific_harbour_privacy_charter.pdf",
        doc_format="pdf",
        raw_text=(
            "An accountable privacy owner must be appointed for every AI capability, operational privacy by design "
            "practices implemented end to end, and a current external privacy policy maintained."
        ),
        phenomenon="paraphrase_zero_keyword",
        ground_truth_obligation_id="AU-PRIV-APP1-GOV",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-PRIV-APP1-GOV",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-HO-02",
        split="held_out",
        org_id="pacific-harbour-cu",
        doc_filename="pacific_harbour_privacy_charter.pdf",
        doc_format="pdf",
        raw_text=(
            "Automated credit models must undergo pre-deployment and ongoing drift monitoring, preserve meaningful human "
            "oversight with an immediate kill switch, and provide customers a formal contestability pathway."
        ),
        phenomenon="paraphrase_zero_keyword",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-NAIC-AI6-TEST-HUMAN",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-HO-03",
        split="held_out",
        org_id="pacific-harbour-cu",
        doc_filename="pacific_harbour_vendor_security.docx",
        doc_format="docx",
        raw_text=(
            "All material service provider arrangements hosting AI workloads require provider materiality assessment, "
            "pre-contractual due diligence, legally binding SLA and audit contract controls, and ongoing exit feasibility monitoring."
        ),
        phenomenon="close_neighbour_distinction",
        ground_truth_obligation_id="AU-APRA-CPS230-SP",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-APRA-CPS230-SP",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-HO-04",
        split="held_out",
        org_id="pacific-harbour-cu",
        doc_filename="pacific_harbour_vendor_security.docx",
        doc_format="docx",
        raw_text=(
            "Information security testing programs must define testing scope over AI assets, enforce risk-based "
            "testing frequency, submit testing results for independent review, and track remediation of identified deficiencies."
        ),
        phenomenon="close_neighbour_distinction",
        ground_truth_obligation_id="AU-APRA-CPS234-TEST",
        ground_truth_relationship=ReconciliationRelationship.EQUIVALENT,
        expects_human_resolution=False,
        expected_obligation_ids=("AU-APRA-CPS234-TEST",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-HO-05",
        split="held_out",
        org_id="pacific-harbour-cu",
        doc_filename="pacific_harbour_exceptions_addendum.txt",
        doc_format="txt",
        raw_text=(
            "For hardship extensions, operations leads may grant temporary exceptions to standard complaint response "
            "timeframes for up to 90 calendar days subject to quarterly review."
        ),
        phenomenon="negation_or_waiver",
        ground_truth_obligation_id="AU-ASIC-RG271-COMPLAINT",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-ASIC-RG271-COMPLAINT",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-HO-06",
        split="held_out",
        org_id="pacific-harbour-cu",
        doc_filename="pacific_harbour_exceptions_addendum.txt",
        doc_format="txt",
        raw_text=(
            "Digital onboarding assistants are not required to disclose in privacy policies which kinds of personal "
            "information or decision types are substantially assisted by computer programs."
        ),
        phenomenon="negation_or_waiver",
        ground_truth_obligation_id="AU-PRIV-APP1.7-AUTOMATED",
        ground_truth_relationship=ReconciliationRelationship.POTENTIAL_CONFLICT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-PRIV-APP1.7-AUTOMATED",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-HO-07",
        split="held_out",
        org_id="pacific-harbour-cu",
        doc_filename="pacific_harbour_exceptions_addendum.txt",
        doc_format="txt",
        raw_text=(
            "All automated cross-border settlement overrides exceeding EUR 750 require pre-execution human sign-off."
        ),
        phenomenon="threshold_or_currency_shift",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-NAIC-AI6-TEST-HUMAN",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-HO-08",
        split="held_out",
        org_id="pacific-harbour-cu",
        doc_filename="pacific_harbour_exceptions_addendum.txt",
        doc_format="txt",
        raw_text=(
            "Automated micro-loan disbursements above AUD 250 may settle immediately with retrospective human review "
            "completed during end-of-day reconciliation."
        ),
        phenomenon="post_execution_approval",
        ground_truth_obligation_id="AU-NAIC-AI6-TEST-HUMAN",
        ground_truth_relationship=ReconciliationRelationship.WEAKER_OR_POTENTIALLY_INSUFFICIENT,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-NAIC-AI6-TEST-HUMAN",),
    ),
    AdversarialCalibrationClause(
        case_id="E31-HO-09",
        split="held_out",
        org_id="pacific-harbour-cu",
        doc_filename="pacific_harbour_data_governance.txt",
        doc_format="txt",
        raw_text=(
            "Data engineering must document end-to-end data lineage and automated ingestion validation through archival disposal, "
            "while ensuring personal records use role-based encryption and verifiable destruction when retention schedules expire."
        ),
        phenomenon="multi_obligation_clause",
        ground_truth_obligation_id="AU-APRA-CPG235-LIFECYCLE",
        ground_truth_relationship=ReconciliationRelationship.PARTIALLY_OVERLAPPING,
        expects_human_resolution=True,
        expected_obligation_ids=("AU-APRA-CPG235-LIFECYCLE", "AU-PRIV-APP11-SECURITY"),
    ),
    AdversarialCalibrationClause(
        case_id="E31-HO-10",
        split="held_out",
        org_id="pacific-harbour-cu",
        doc_filename="pacific_harbour_data_governance.txt",
        doc_format="txt",
        raw_text=(
            "Operations divisions shall observe Annexure D escalation limits unless regional leads approve appropriate ad-hoc measures."
        ),
        phenomenon="ambiguous_or_incomplete",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNDETERMINED,
        expects_human_resolution=True,
        expected_obligation_ids=(),
    ),
    AdversarialCalibrationClause(
        case_id="E31-HO-11",
        split="held_out",
        org_id="pacific-harbour-cu",
        doc_filename="pacific_harbour_facilities_esg.txt",
        doc_format="txt",
        raw_text=(
            "Workplace sustainability teams compile Scope 2 solar kilowatt generation totals and office HVAC cooling thresholds "
            "for annual ESG climate investor packs."
        ),
        phenomenon="adversarial_keyword_decoy",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.UNMAPPED_NO_RELIABLE_RELATIONSHIP,
        expects_human_resolution=True,
        expected_obligation_ids=(),
    ),
    AdversarialCalibrationClause(
        case_id="E31-HO-12",
        split="held_out",
        org_id="pacific-harbour-cu",
        doc_filename="pacific_harbour_facilities_esg.txt",
        doc_format="txt",
        raw_text=(
            "All internal treasury ledger sign-offs above delegated financial authority tier 3 must be recorded in the "
            "corporate artifact vault under internal watermark provenance tracking."
        ),
        phenomenon="internal_enterprise_only",
        ground_truth_obligation_id=None,
        ground_truth_relationship=ReconciliationRelationship.ADDITIONAL_ENTERPRISE_REQUIREMENT,
        expects_human_resolution=False,
        expected_obligation_ids=(),
    ),
)
