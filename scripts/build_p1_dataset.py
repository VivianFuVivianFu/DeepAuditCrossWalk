"""Construct P1_EVALUATION_DATASET_V2.json with 156 high-fidelity Australian banking governance cases."""

import json
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent

with open(repo_root / "UNIFIED_CONTROL_LIBRARY.json", encoding="utf-8") as f:
    ucl = json.load(f)

VALID_CONTROLS = {c["control_id"] for c in ucl["controls"]}
VALID_FACETS = {f for c in ucl["controls"] for f in c["control_facets"]}

cases = []

def c(
    case_id: str,
    split: str,
    source_type: str,
    category: str,
    text: str,
    expected_atomic: list[str],
    expected_facets: list[str],
    expected_controls: list[str],
    applicability_conditions: list[str] | None = None,
    threshold: dict | None = None,
    is_negated: bool = False,
    has_exception: bool = False,
    review_status: str = "proposed",
    provenance: str = "synthetic_reference",
    reviewer_status: str = "unverified",
    confidence: str = "high",
    ambiguity: str | None = None,
    notes: str = "",
):
    for ctrl in expected_controls:
        if ctrl and ctrl not in VALID_CONTROLS:
            raise ValueError(f"Invalid control '{ctrl}' in {case_id}")
    for facet in expected_facets:
        if facet not in VALID_FACETS:
            raise ValueError(f"Invalid facet '{facet}' in {case_id}")
    
    cases.append({
        "case_id": case_id,
        "split": split,
        "source_type": source_type,
        "category": category,
        "input_text": text,
        "expected_atomic_requirements": expected_atomic,
        "expected_facets": expected_facets,
        "expected_controls": expected_controls,
        "applicability_conditions": applicability_conditions or [],
        "threshold_constraint": threshold,
        "is_negated": is_negated,
        "has_exception": has_exception,
        "expected_review_status": review_status,
        "ground_truth_provenance": provenance,
        "reviewer_status": reviewer_status,
        "label_confidence": confidence,
        "unresolved_ambiguity": ambiguity,
        "notes": notes,
    })

# ------------------------------------------------------------------------------
# DOMAIN 1: PRIVACY & PERSONAL INFORMATION (P1-001 to P1-030) - 20 Dev, 10 Holdout
# ------------------------------------------------------------------------------
c("P1-001", "development", "enterprise_policy", "exact_match",
  "A formal Privacy Impact Assessment (PIA) must be completed and approved by the Chief Privacy Officer prior to onboarding any AI model ingesting customer personal information.",
  ["Complete PIA prior to onboarding AI handling personal information", "Obtain Chief Privacy Officer approval"],
  ["pia_threshold_screen_completed", "privacy_accountability_assigned"],
  ["CTRL-PRIV-GOVERNANCE"], notes="Core APP 1.2 privacy by design gateway.")

c("P1-002", "development", "enterprise_policy", "exact_match",
  "The enterprise public privacy policy must be reviewed annually and updated whenever new generative AI consumer features are deployed.",
  ["Annual review of privacy policy", "Update privacy policy upon generative AI deployment"],
  ["privacy_policy_current"],
  ["CTRL-PRIV-GOVERNANCE"], notes="APP 1.3 - 1.5 privacy policy maintenance.")

c("P1-003", "development", "enterprise_policy", "exact_match",
  "AI systems must collect only personal information that is strictly necessary for credit assessment or fraud prevention functions.",
  ["Collect only strictly necessary personal information for credit or fraud functions"],
  ["collection_purpose_defined", "necessity_assessed"],
  ["CTRL-PRIV-COLLECTION"], notes="APP 3.1 & 3.2 necessity test.")

c("P1-004", "development", "enterprise_policy", "exact_match",
  "Biometric voice verification models must obtain explicit customer consent prior to biometric template enrollment.",
  ["Obtain explicit consent for biometric enrollment"],
  ["sensitive_information_consent"],
  ["CTRL-PRIV-COLLECTION"], notes="APP 3.3 sensitive information consent rule.")

c("P1-005", "development", "enterprise_policy", "exact_match",
  "At or before collecting personal data for automated underwriting, the bank must present an APP 5 collection notice specifying the AI assessment purpose.",
  ["Present APP 5 notice at or before collection", "Specify automated underwriting AI purpose"],
  ["collection_notice_exists", "notice_content_complete", "notice_timing_defined"],
  ["CTRL-PRIV-NOTICE"], notes="APP 5 notice content and timing.")

c("P1-006", "development", "enterprise_policy", "exact_match",
  "Customer transactional telemetry collected for credit card fraud monitoring must not be used to train marketing recommendation engines without affirmative opt-in consent.",
  ["Prohibit secondary marketing use of fraud telemetry without opt-in consent"],
  ["primary_purpose_recorded", "secondary_use_basis_checked"],
  ["CTRL-PRIV-USE-DISCLOSURE"], notes="APP 6 purpose limitation barrier.")

c("P1-007", "development", "enterprise_policy", "exact_match",
  "Customer personal data must not be transferred to offshore cloud AI providers unless enforceable contractual safeguards ensure overseas compliance with the APPs.",
  ["Ensure enforceable contractual safeguards before offshore personal data transfer"],
  ["overseas_recipients_and_regions_mapped", "app8_reasonable_steps_and_contracts_in_place"],
  ["CTRL-PRIV-CROSS-BORDER"], notes="APP 8.1 reasonable steps and cloud contracts.")

c("P1-008", "development", "enterprise_policy", "paraphrased_match",
  "The bank retains vicarious regulatory accountability under Section 16C for any privacy breaches committed by offshore sub-processors hosting foundational AI weights.",
  ["Acknowledge s 16C vicarious liability for offshore AI sub-processors"],
  ["s16c_accountability_and_exception_assessed"],
  ["CTRL-PRIV-CROSS-BORDER"], notes="Privacy Act Section 16C accountability.")

c("P1-009", "development", "enterprise_policy", "exact_match",
  "Customer training datasets must be secured using AES-256 encryption at rest and isolated within private tenant VPCs.",
  ["Encrypt training datasets with AES-256", "Isolate within private tenant VPCs"],
  ["security_controls_defined"],
  ["CTRL-PRIV-SECURITY-RETENTION"], notes="APP 11.1 security protection.")

c("P1-010", "development", "enterprise_policy", "numeric_threshold",
  "Customer biometric session telemetry and prompt tokens must be permanently destroyed or de-identified within 30 days of transaction settlement.",
  ["Destroy or de-identify biometric telemetry within 30 days"],
  ["retention_schedule_applied", "destruction_or_deidentification_verified"],
  ["CTRL-PRIV-SECURITY-RETENTION"],
  threshold={"amount": 30, "unit": "days", "operator": "lte"},
  notes="APP 11.2 statutory destruction obligation.")

c("P1-011", "development", "enterprise_policy", "exact_match",
  "All customer profiles and synthetic inference scores generated by AI must be retrievable in human-readable format upon an APP 12 access request within 30 days.",
  ["Retrieve AI inference scores in human-readable format for APP 12 access requests", "Complete within 30 days"],
  ["ai_personal_records_retrievable_for_access", "access_and_correction_timeframes_tracked"],
  ["CTRL-PRIV-ACCESS-CORRECTION"],
  threshold={"amount": 30, "unit": "days", "operator": "lte"},
  notes="APP 12 individual access right.")

c("P1-012", "development", "enterprise_policy", "exact_match",
  "When a customer rectifies inaccurate income data, corrected records must propagate to all credit scorecard feature stores and vector databases within 5 business days.",
  ["Propagate corrected customer data to AI feature stores within 5 business days"],
  ["correction_propagated_to_ai_stores", "access_and_correction_timeframes_tracked"],
  ["CTRL-PRIV-ACCESS-CORRECTION"],
  threshold={"amount": 5, "unit": "business_days", "operator": "lte"},
  notes="APP 13 data correction propagation.")

c("P1-013", "development", "enterprise_policy", "exact_match",
  "Automated data loss prevention (DLP) tools must monitor generative AI egress channels to detect unauthorized exposure of customer personal information.",
  ["Deploy DLP tools on AI egress channels to detect personal data leakage"],
  ["ai_data_leakage_detection_enabled"],
  ["CTRL-PRIV-NDB-RESPONSE"], notes="Part IIIC NDB data leakage monitoring.")

c("P1-014", "development", "enterprise_policy", "numeric_threshold",
  "Suspected unauthorized disclosures of customer records via LLM prompt injection must undergo a formal eligibility assessment within 30 calendar days.",
  ["Complete eligible data breach assessment within 30 calendar days"],
  ["ndb_30day_assessment_workflow_defined"],
  ["CTRL-PRIV-NDB-RESPONSE"],
  threshold={"amount": 30, "unit": "days", "operator": "lte"},
  notes="Privacy Act s 26WH 30-day assessment deadline.")

c("P1-015", "development", "enterprise_policy", "exact_match",
  "If an eligible data breach involving AI occurs, the Incident Commander must prepare formal notification statements for the OAIC and affected individuals without undue delay.",
  ["Prepare OAIC and customer notification for eligible data breaches"],
  ["oaic_and_individual_notification_prepared"],
  ["CTRL-PRIV-NDB-RESPONSE"], notes="Privacy Act s 26WK notification mandate.")

c("P1-016", "development", "enterprise_policy", "exact_match",
  "The bank's privacy policy must transparently disclose the kinds of personal information used in automated credit decision systems and the operation of the decision logic.",
  ["Disclose personal information kinds used in automated credit decisions", "Explain decision logic"],
  ["significant_decision_screened", "personal_information_kinds_disclosed", "decision_kinds_disclosed"],
  ["CTRL-PRIV-AUTOMATED-DISCLOSURE"], notes="Privacy Act statutory amendment for ADM transparency.")

c("P1-017", "development", "enterprise_policy", "exact_match",
  "Input datasets used to calibrate automated lending models must be verified for accuracy, completeness, and recency prior to pipeline ingestion.",
  ["Verify accuracy, completeness and recency of lending model input data"],
  ["input_personal_data_accuracy_checked", "stale_or_incomplete_records_prevented"],
  ["CTRL-DATA-QUALITY-GOV"], notes="APP 10.1 & 10.2 data quality standard.")

c("P1-018", "development", "enterprise_policy", "paraphrased_match",
  "Behavioral credit risk classifications and spending propensity inferences generated by machine learning models constitute personal data and must adhere to all APP controls.",
  ["Classify machine-generated behavioral inferences as personal data subject to APPs"],
  ["inferred_attributes_classified_as_collection", "ai_output_and_inference_relevance_verified"],
  ["CTRL-DATA-QUALITY-GOV"], notes="OAIC Guidelines Ch 6: Inferred personal information.")

c("P1-019", "development", "enterprise_policy", "exact_match",
  "Every critical AI data element used in statutory capital calculations must have a designated Data Steward responsible for data dictionary definitions and quality thresholds.",
  ["Assign Data Steward to critical AI data elements", "Define quality thresholds and dictionary"],
  ["critical_ai_data_elements_owned", "metadata_and_data_dictionary_maintained"],
  ["CTRL-DATA-QUALITY-GOV"], notes="APRA CPG 235 data governance.")

c("P1-020", "development", "enterprise_policy", "exact_match",
  "Automated data ingestion pipelines must record end-to-end cryptographic lineage from raw transactional source tables to final AI inference feature vectors.",
  ["Record end-to-end cryptographic data lineage from raw tables to feature vectors"],
  ["end_to_end_data_lineage_documented", "automated_ingestion_and_transformation_validation"],
  ["CTRL-DATA-LIFECYCLE-LINEAGE"], notes="APRA CPG 235 data lineage controls.")

# P1-021 to P1-030 (Holdout)
c("P1-021", "holdout", "enterprise_policy", "exact_match",
  "All risk mitigation recommendations identified during an AI Privacy Impact Assessment must be tracked in the enterprise risk register until verified closed by Line 2 Risk.",
  ["Track PIA risk mitigation recommendations in enterprise risk register to verified closure"],
  ["pia_recommendations_tracked_to_closure"],
  ["CTRL-PRIV-GOVERNANCE"], notes="Holdout test for PIA action tracking.")

c("P1-022", "holdout", "enterprise_policy", "exact_match",
  "Before querying customer banking history for wealth advisory AI cross-selling, systems must verify that the secondary purpose is directly related to account management and reasonably expected.",
  ["Verify secondary AI use is directly related and reasonably expected before querying records"],
  ["secondary_use_basis_checked"],
  ["CTRL-PRIV-USE-DISCLOSURE"], notes="Holdout test for APP 6 reasonable expectation test.")

c("P1-023", "holdout", "enterprise_policy", "conditional_requirement",
  "Offshore replication of Australian personal credit records is prohibited unless an explicit statutory exemption under Section 16C(b) is certified by General Counsel.",
  ["Prohibit offshore replication of personal credit records unless certified under s 16C(b)"],
  ["overseas_recipients_and_regions_mapped", "s16c_accountability_and_exception_assessed"],
  ["CTRL-PRIV-CROSS-BORDER"], has_exception=True, notes="Holdout test for conditional statutory exception.")

c("P1-024", "holdout", "enterprise_policy", "paraphrased_match",
  "Following the 7-year statutory retention horizon under APP 11.2, archived mortgage loan application files must be irreversibly sanitized with cryptographic proof of disposal.",
  ["Irreversibly sanitize archived loan files after 7 years with cryptographic proof of disposal"],
  ["retention_schedule_applied", "destruction_or_deidentification_verified"],
  ["CTRL-PRIV-SECURITY-RETENTION"],
  threshold={"amount": 7, "unit": "years", "operator": "gte"},
  notes="Holdout test for APP 11 cryptographic sanitization.")

c("P1-025", "holdout", "questionnaire_question", "questionnaire_facet",
  "Does your system make decisions that have a significant effect on an individual (such as granting or refusing credit), and if so, does the privacy notice explain how automated processing is applied?",
  ["Inquire whether system makes significant automated decisions and provides explanatory notice"],
  ["significant_decision_screened", "decision_kinds_disclosed"],
  ["CTRL-PRIV-AUTOMATED-DISCLOSURE"], notes="Holdout test for questionnaire facet coverage.")

c("P1-026", "holdout", "questionnaire_question", "questionnaire_facet",
  "Can you demonstrate complete, traceable data lineage showing all transformations applied to training datasets from original bank ingestion to model input tensors?",
  ["Demonstrate traceable data lineage from raw ingestion to model input tensors"],
  ["end_to_end_data_lineage_documented"],
  ["CTRL-DATA-LIFECYCLE-LINEAGE"], notes="Holdout test for lineage inquiry completeness.")

c("P1-027", "holdout", "enterprise_policy", "negated_control",
  "Consumer credit evaluation algorithms are strictly prohibited from collecting or processing sensitive data regarding religious affiliations, political opinions, or trade union memberships.",
  ["Prohibit collection or processing of political, religious or union sensitive data in credit models"],
  ["sensitive_information_consent"],
  ["CTRL-PRIV-COLLECTION"], is_negated=True, notes="Holdout test: Negated policy clause prohibiting sensitive data collection.")

c("P1-028", "holdout", "enterprise_policy", "paraphrased_match",
  "All outward transmissions of retail banking customer records to third-party LLM inference APIs must be logged in the centralized privacy disclosure ledger.",
  ["Log all third-party LLM customer data transmissions in centralized disclosure ledger"],
  ["disclosures_logged"],
  ["CTRL-PRIV-USE-DISCLOSURE"], notes="Holdout test for disclosure ledger logging.")

c("P1-029", "holdout", "enterprise_policy", "ambiguous_legal",
  "Indigenous customer data and First Nations community telemetry must not be hosted outside Australian territorial boundaries, notwithstanding commercial cloud availability zones.",
  ["Restrict First Nations data to domestic Australian hosting"],
  ["overseas_recipients_and_regions_mapped"],
  ["CTRL-PRIV-CROSS-BORDER"],
  provenance="ambiguous_legal", reviewer_status="pending_panel", confidence="medium",
  ambiguity="Interaction between Privacy Act cross-border rules and Indigenous Cultural and Intellectual Property protocols.",
  notes="Holdout test for legal edge case.")

c("P1-030", "holdout", "enterprise_policy", "multi_facet",
  "System architects must embed privacy-by-design controls into the microservice pipeline and configure automated TTL expiry tags ensuring customer search queries are wiped after 48 hours.",
  ["Embed privacy by design into microservices", "Configure automated TTL expiry wiping search queries after 48 hours"],
  ["privacy_by_design_controls_embedded", "retention_schedule_applied", "destruction_or_deidentification_verified"],
  ["CTRL-PRIV-GOVERNANCE", "CTRL-PRIV-SECURITY-RETENTION"],
  threshold={"amount": 48, "unit": "hours", "operator": "lte"},
  notes="Holdout test for multi-facet and multi-control extraction.")

# ------------------------------------------------------------------------------
# DOMAIN 2: INFORMATION SECURITY & CYBER RESILIENCE (P1-031 to P1-054) - 16 Dev, 8 Holdout
# APRA CPS 234 & ISO 27001
# ------------------------------------------------------------------------------
c("P1-031", "development", "enterprise_policy", "exact_match",
  "All AI model artifacts and inference weights must be assigned an Information Asset Owner and classified by criticality and sensitivity under APRA CPS 234.",
  ["Assign Information Asset Owner to AI model artifacts", "Classify AI assets by criticality and sensitivity"],
  ["security_roles_and_asset_owners_assigned", "ai_assets_classified_by_criticality_and_sensitivity"],
  ["CTRL-SEC-COMMENSURATE"], notes="APRA CPS 234 para 16 asset ownership and classification.")

c("P1-032", "development", "enterprise_policy", "exact_match",
  "The bank's information security testing program must systematically test internet-facing AI inference APIs at least annually.",
  ["Systematically test internet-facing AI APIs at least annually"],
  ["testing_program_exists", "testing_frequency_risk_based"],
  ["CTRL-SEC-TESTING"],
  threshold={"amount": 1, "unit": "years", "operator": "lte"},
  notes="APRA CPS 234 para 30 testing frequency.")

c("P1-033", "development", "enterprise_policy", "exact_match",
  "Independent red team penetration testing of LLM prompt injection defences must be conducted prior to major production releases.",
  ["Conduct independent red team testing prior to major LLM production releases"],
  ["testing_program_exists", "testing_scope_defined"],
  ["CTRL-SEC-TESTING"], notes="APRA CPS 234 independent security testing.")

c("P1-034", "development", "enterprise_policy", "exact_match",
  "Information security testing results and identified vulnerability deficiencies must be formally reviewed by the Chief Information Security Officer (CISO).",
  ["CISO review of security testing results and deficiencies"],
  ["testing_results_reviewed", "deficiencies_remediated"],
  ["CTRL-SEC-TESTING"], notes="APRA CPS 234 para 32 review of testing results.")

c("P1-035", "development", "enterprise_policy", "exact_match",
  "Information security incident detection mechanisms must be maintained to identify adversarial model extraction or data poisoning attempts within 1 hour.",
  ["Maintain detection mechanisms for model extraction or poisoning within 1 hour"],
  ["incident_detection_defined"],
  ["CTRL-SEC-INCIDENT"],
  threshold={"amount": 1, "unit": "hours", "operator": "lte"},
  notes="APRA CPS 234 para 33 incident detection.")

c("P1-036", "development", "enterprise_policy", "exact_match",
  "Material information security incidents impacting core banking AI models must be notified to APRA as soon as possible and no later than 72 hours post detection.",
  ["Notify APRA of material security incidents within 72 hours"],
  ["response_and_escalation_defined", "apra_notification_screened"],
  ["CTRL-SEC-INCIDENT"],
  threshold={"amount": 72, "unit": "hours", "operator": "lte"},
  notes="APRA CPS 234 para 35 statutory notification window.")

c("P1-037", "development", "enterprise_policy", "paraphrased_match",
  "Cryptographic keys used to sign AI model weights must reside exclusively in FIPS 140-3 Level 3 hardware security modules with dual authorization.",
  ["Enforce FIPS 140-3 Level 3 HSM with dual authorization for model signing keys"],
  ["controls_commensurate", "access_cryptography_and_secure_engineering_applied"],
  ["CTRL-SEC-COMMENSURATE", "CTRL-ISMS-CONTROLS"],
  notes="Technical domain standard for cryptographic key protection.")

c("P1-038", "development", "enterprise_policy", "exact_match",
  "AI environments and cloud containers must be included within the scope of the enterprise ISO/IEC 27001 Information Security Management System (ISMS).",
  ["Include AI environments in ISO 27001 ISMS scope"],
  ["ai_environment_in_isms_scope_and_risk_assessment"],
  ["CTRL-ISMS-CONTROLS"], notes="ISO 27001 AI boundary definition.")

c("P1-039", "development", "enterprise_policy", "exact_match",
  "Access to production model deployment pipelines must require multi-factor authentication (MFA) and role-based access control (RBAC).",
  ["Require MFA and RBAC for production model deployment pipelines"],
  ["controls_commensurate"],
  ["CTRL-SEC-COMMENSURATE"], notes="CPS 234 para 23 access control.")

c("P1-040", "development", "enterprise_policy", "exact_match",
  "Security controls applied to AI systems must be commensurate with the size and extent of the threat to the bank's information assets.",
  ["Implement controls commensurate with size and extent of threat"],
  ["controls_commensurate", "threats_and_vulnerabilities_assessed"],
  ["CTRL-SEC-COMMENSURATE"], notes="CPS 234 para 23 commensuration requirement.")

c("P1-041", "development", "enterprise_policy", "exact_match",
  "Third-party managed AI assets and SaaS inference endpoints must be catalogued in the central information asset inventory.",
  ["Catalogue third-party AI assets in central inventory"],
  ["third_party_managed_ai_assets_catalogued", "third_party_assets_in_scope"],
  ["CTRL-SEC-COMMENSURATE"], notes="CPS 234 para 17 third-party asset catalogue.")

c("P1-042", "development", "enterprise_policy", "exact_match",
  "Material security weaknesses identified in AI pipelines that cannot be remediated within 30 days must be escalated to the Board Risk Committee.",
  ["Escalate material AI security weaknesses unremediated in 30 days to Board Risk Committee"],
  ["material_weaknesses_tracked"],
  ["CTRL-SEC-INCIDENT"],
  threshold={"amount": 30, "unit": "days", "operator": "gte"},
  notes="CPS 234 para 36 escalation of material weaknesses.")

c("P1-043", "development", "enterprise_policy", "exact_match",
  "Supplier security capabilities must be reviewed annually against ISO/IEC 27001 controls for all cloud AI hosting providers.",
  ["Annual review of supplier ISO 27001 security capabilities"],
  ["supplier_security_and_isms_internal_audit_verified"],
  ["CTRL-ISMS-CONTROLS"],
  threshold={"amount": 1, "unit": "years", "operator": "lte"},
  notes="ISO 27001 supplier security review.")

c("P1-044", "development", "enterprise_policy", "exact_match",
  "Deficiencies identified during cyber security testing of AI models must be tracked in a corrective action plan with strict remediation milestones.",
  ["Track AI cyber deficiencies in corrective action plan with strict milestones"],
  ["deficiencies_remediated"],
  ["CTRL-SEC-TESTING"], notes="CPS 234 para 32 deficiency remediation.")

c("P1-045", "development", "enterprise_policy", "conditional_requirement",
  "Biometric authentication algorithms are exempt from automated quarterly penetration testing provided continuous behavioral anomaly detection is active.",
  ["Exempt biometric algorithms from quarterly testing if continuous anomaly detection is active"],
  ["testing_program_exists", "testing_frequency_risk_based"],
  ["CTRL-SEC-TESTING"], has_exception=True, notes="Conditional security testing exemption.")

c("P1-046", "development", "enterprise_policy", "numeric_threshold",
  "Information security testing of critical credit rating algorithms must occur at least semi-annually (every 6 months).",
  ["Test critical credit rating algorithms at least semi-annually"],
  ["testing_frequency_risk_based"],
  ["CTRL-SEC-TESTING"],
  threshold={"amount": 6, "unit": "months", "operator": "lte"},
  notes="CPS 234 risk-based frequency.")

# P1-047 to P1-054 (Holdout)
c("P1-047", "holdout", "enterprise_policy", "exact_match",
  "All security roles and operational asset responsibilities for AI systems must be defined in writing and approved by the CISO.",
  ["Document AI security roles and responsibilities with CISO approval"],
  ["security_roles_and_asset_owners_assigned"],
  ["CTRL-SEC-COMMENSURATE"], notes="Holdout: CPS 234 para 14 security roles.")

c("P1-048", "holdout", "enterprise_policy", "paraphrased_match",
  "The scope of cybersecurity testing must encompass model inversion attacks, adversarial evasion perturbations, and data poisoning vectors.",
  ["Encompass inversion, evasion and poisoning attacks in cybersecurity testing scope"],
  ["testing_scope_defined"],
  ["CTRL-SEC-TESTING"], notes="Holdout: AI-specific penetration testing scope.")

c("P1-049", "holdout", "enterprise_policy", "negated_control",
  "AI developers shall not disable automated runtime dependency scanning or bypass static analysis security testing (SAST) in CI/CD pipelines.",
  ["Prohibit disabling runtime dependency scanning or bypassing SAST"],
  ["controls_commensurate"],
  ["CTRL-SEC-COMMENSURATE"], is_negated=True, notes="Holdout: Negated security control on CI/CD bypass.")

c("P1-050", "holdout", "questionnaire_question", "questionnaire_facet",
  "Has your model been evaluated by an independent security testing team for vulnerabilities to prompt injection and unauthorized model extraction?",
  ["Inquire whether model was independently evaluated for prompt injection and extraction"],
  ["testing_program_exists", "testing_scope_defined"],
  ["CTRL-SEC-TESTING"], notes="Holdout: AIAF questionnaire security testing check.")

c("P1-051", "holdout", "questionnaire_question", "questionnaire_facet",
  "Does the incident response protocol include a formal mechanism to notify APRA within 72 hours if a model vulnerability is actively exploited?",
  ["Inquire whether incident protocol includes 72-hour APRA notification mechanism"],
  ["response_and_escalation_defined", "apra_notification_screened"],
  ["CTRL-SEC-INCIDENT"], notes="Holdout: AIAF questionnaire 72-hour APRA escalation.")

c("P1-052", "holdout", "enterprise_policy", "multi_facet",
  "The bank must identify all threats and vulnerabilities to AI infrastructure and enforce cryptographic key isolation under ISO/IEC 27001.",
  ["Identify AI threats and vulnerabilities", "Enforce cryptographic key isolation under ISO 27001"],
  ["threats_and_vulnerabilities_assessed", "access_cryptography_and_secure_engineering_applied"],
  ["CTRL-SEC-COMMENSURATE", "CTRL-ISMS-CONTROLS"], notes="Holdout: Multi-facet security control.")

c("P1-053", "holdout", "enterprise_policy", "numeric_threshold",
  "Incident severity assessments for AI system outages must be completed within 2 hours of telemetry anomaly detection.",
  ["Complete AI outage severity assessment within 2 hours"],
  ["incident_detection_defined"],
  ["CTRL-SEC-INCIDENT"],
  threshold={"amount": 2, "unit": "hours", "operator": "lte"},
  notes="Holdout: Rapid incident detection timeline.")

c("P1-054", "holdout", "enterprise_policy", "ambiguous_legal",
  "Sovereign cloud AI containers deployed under ASD Certified Cloud Services Lists are exempt from independent penetration testing by foreign-headquartered audit firms.",
  ["Exempt ASD certified cloud containers from foreign audit firm penetration testing"],
  ["testing_program_exists"],
  ["CTRL-SEC-TESTING"],
  provenance="ambiguous_legal", reviewer_status="pending_panel", confidence="medium",
  ambiguity="Interaction between APRA CPS 234 independent testing rules and Australian Government Information Security Manual (ISM) sovereignty guidelines.",
  notes="Holdout: Ambiguous sovereign audit exemption.")

# ------------------------------------------------------------------------------
# DOMAIN 3: OPERATIONAL RESILIENCE & BUSINESS CONTINUITY (P1-055 to P1-074) - 14 Dev, 6 Holdout
# APRA CPS 230
# ------------------------------------------------------------------------------
c("P1-055", "development", "enterprise_policy", "exact_match",
  "All AI systems supporting critical operations must be mapped in the operational architecture showing service dependencies and data flows.",
  ["Map AI systems supporting critical operations with dependencies and data flows"],
  ["critical_operation_dependency_mapped"],
  ["CTRL-BCP-AI"], notes="APRA CPS 230 para 23 mapping of critical operations.")

c("P1-056", "development", "enterprise_policy", "exact_match",
  "The operational risk management framework must assess the operational risks associated with AI model failure, corruption, or data drift.",
  ["Assess operational risks from AI failure, corruption or data drift"],
  ["operational_risks_assessed"],
  ["CTRL-OPS-RISK"], notes="APRA CPS 230 para 24 operational risk assessment.")

c("P1-057", "development", "enterprise_policy", "exact_match",
  "The control environment for automated credit decisioning must maintain documented procedural controls to prevent systemic misclassification.",
  ["Maintain documented procedural controls in AI credit decisioning"],
  ["control_environment_documented"],
  ["CTRL-OPS-RISK"], notes="APRA CPS 230 para 27 control environment.")

c("P1-058", "development", "enterprise_policy", "exact_match",
  "Operational risk incidents and control weaknesses arising from algorithmic errors must be recorded in the enterprise incident log within 24 hours.",
  ["Record algorithmic operational incidents in enterprise log within 24 hours"],
  ["incidents_and_weaknesses_managed"],
  ["CTRL-OPS-RISK"],
  threshold={"amount": 24, "unit": "hours", "operator": "lte"},
  notes="APRA CPS 230 para 30 incident management.")

c("P1-059", "development", "enterprise_policy", "exact_match",
  "Tolerance levels for operational disruption of AI customer identity verification systems must not exceed a maximum allowable downtime of 2 hours.",
  ["Define AI identity verification disruption tolerance at maximum 2 hours downtime"],
  ["tolerance_and_fallback_defined"],
  ["CTRL-BCP-AI"],
  threshold={"amount": 2, "unit": "hours", "operator": "lte"},
  notes="APRA CPS 230 para 32 tolerance levels.")

c("P1-060", "development", "enterprise_policy", "exact_match",
  "Business continuity plans must maintain automated deterministic fallback procedures allowing manual credit underwriting during AI outages.",
  ["Maintain automated deterministic fallback procedures for credit underwriting during AI outages"],
  ["tolerance_and_fallback_defined"],
  ["CTRL-BCP-AI"], notes="APRA CPS 230 para 33 fallback procedures.")

c("P1-061", "development", "enterprise_policy", "exact_match",
  "Business continuity plans for critical AI systems must be tested systematically at least annually under simulated failure conditions.",
  ["Systematically test AI business continuity plans annually under simulated failure"],
  ["continuity_plan_tested"],
  ["CTRL-BCP-AI"],
  threshold={"amount": 1, "unit": "years", "operator": "lte"},
  notes="APRA CPS 230 para 36 annual BCP testing.")

c("P1-062", "development", "enterprise_policy", "paraphrased_match",
  "Disaster recovery simulation drills must demonstrate end-to-end failover to offline rule-based scoring without exceeding maximum data loss tolerances.",
  ["Demonstrate failover to offline rule-based scoring within data loss tolerances during drills"],
  ["continuity_plan_tested", "tolerance_and_fallback_defined"],
  ["CTRL-BCP-AI"], notes="CPS 230 operational simulation drills.")

c("P1-063", "development", "enterprise_policy", "exact_match",
  "Line 1 business units must manage operational risks emerging from generative AI tools across the entire AI asset lifecycle.",
  ["Manage generative AI operational risks across lifecycle in Line 1"],
  ["operational_risks_assessed", "control_environment_documented"],
  ["CTRL-OPS-RISK"], notes="CPS 230 operational risk lifecycle management.")

c("P1-064", "development", "enterprise_policy", "numeric_threshold",
  "Data recovery point objectives (RPO) for transactional fraud detection models must not exceed 15 minutes of customer activity data.",
  ["Enforce RPO of maximum 15 minutes for fraud detection model data"],
  ["tolerance_and_fallback_defined"],
  ["CTRL-BCP-AI"],
  threshold={"amount": 15, "unit": "minutes", "operator": "lte"},
  notes="CPS 230 quantitative tolerance metric.")

c("P1-065", "development", "enterprise_policy", "conditional_requirement",
  "De minimis non-customer facing AI tools are exempt from formal BCP testing provided their failure cannot impact critical bank operations.",
  ["Exempt non-customer AI tools from BCP testing if no impact on critical operations"],
  ["continuity_plan_tested"],
  ["CTRL-BCP-AI"], has_exception=True, notes="CPS 230 de minimis BCP exemption.")

c("P1-066", "development", "enterprise_policy", "exact_match",
  "All critical operational dependencies on cloud AI infrastructure providers must be reviewed by the Operational Resilience Committee.",
  ["Operational Resilience Committee review of critical cloud AI dependencies"],
  ["critical_operation_dependency_mapped"],
  ["CTRL-BCP-AI"], notes="CPS 230 critical dependency review.")

c("P1-067", "development", "enterprise_policy", "paraphrased_match",
  "Root-cause analysis must be initiated within 48 hours for any algorithmic failure that degrades customer service availability.",
  ["Initiate root-cause analysis within 48 hours of algorithmic service degradation"],
  ["incidents_and_weaknesses_managed"],
  ["CTRL-OPS-RISK"],
  threshold={"amount": 48, "unit": "hours", "operator": "lte"},
  notes="CPS 230 operational incident resolution.")

c("P1-068", "development", "enterprise_policy", "exact_match",
  "The operational control environment must enforce automated rate limiting to prevent denial-of-service degradation of public AI endpoints.",
  ["Enforce automated rate limiting on public AI endpoints"],
  ["control_environment_documented"],
  ["CTRL-OPS-RISK"], notes="CPS 230 control environment safeguard.")

# P1-069 to P1-074 (Holdout)
c("P1-069", "holdout", "enterprise_policy", "exact_match",
  "Tolerance levels for payment authorization AI systems must define both maximum allowable outage duration and maximum financial loss limits.",
  ["Define outage duration and financial loss tolerances for payment authorization AI"],
  ["tolerance_and_fallback_defined"],
  ["CTRL-BCP-AI"], notes="Holdout: CPS 230 multi-dimensional tolerance limits.")

c("P1-070", "holdout", "enterprise_policy", "paraphrased_match",
  "In the event of foundational model provider outages, credit card fraud evaluation must instantaneously fall back to heuristic rule tables.",
  ["Instantaneous fallback to heuristic rule tables during foundational model outage"],
  ["tolerance_and_fallback_defined"],
  ["CTRL-BCP-AI"], notes="Holdout: Real-time fallback procedure.")

c("P1-071", "holdout", "questionnaire_question", "questionnaire_facet",
  "Has your team mapped all critical operational dependencies and verified that a business continuity plan with manual fallback exists?",
  ["Inquire whether critical dependencies are mapped and manual fallback exists in BCP"],
  ["critical_operation_dependency_mapped", "tolerance_and_fallback_defined"],
  ["CTRL-BCP-AI"], notes="Holdout: AIAF questionnaire operational resilience inquiry.")

c("P1-072", "holdout", "enterprise_policy", "negated_control",
  "The bank shall not deploy automated loan approval models into critical operations without an approved and tested business continuity plan.",
  ["Prohibit deployment of loan models into critical operations without tested BCP"],
  ["continuity_plan_tested"],
  ["CTRL-BCP-AI"], is_negated=True, notes="Holdout: Negated pre-deployment BCP rule.")

c("P1-073", "holdout", "enterprise_policy", "multi_facet",
  "The operational risk assessment must identify single points of failure in AI hardware clusters and verify automated incident escalation within 4 hours.",
  ["Identify single points of failure in AI clusters", "Enforce 4-hour automated incident escalation"],
  ["operational_risks_assessed", "incidents_and_weaknesses_managed"],
  ["CTRL-OPS-RISK"],
  threshold={"amount": 4, "unit": "hours", "operator": "lte"},
  notes="Holdout: Multi-facet operational risk case.")

c("P1-074", "holdout", "enterprise_policy", "ambiguous_legal",
  "During catastrophic grid failure, AI fallback tolerances may be extended beyond 4 hours provided customer deposit operations remain solvent.",
  ["Permit extending AI fallback tolerances beyond 4 hours during catastrophic grid failure"],
  ["tolerance_and_fallback_defined"],
  ["CTRL-BCP-AI"],
  provenance="ambiguous_legal", reviewer_status="pending_panel", confidence="medium",
  ambiguity="Prudential boundaries of APRA CPS 230 para 32 disruption tolerances during declared national infrastructure emergencies.",
  notes="Holdout: Ambiguous emergency tolerance extension.")

# ------------------------------------------------------------------------------
# DOMAIN 4: THIRD-PARTY AI & MATERIAL SERVICE PROVIDERS (P1-075 to P1-092) - 12 Dev, 6 Holdout
# APRA CPS 230 Service Providers
# ------------------------------------------------------------------------------
c("P1-075", "development", "enterprise_policy", "exact_match",
  "Before entering into an agreement with an external AI service provider, the bank must conduct comprehensive due diligence on the provider's financial and technical viability.",
  ["Conduct comprehensive due diligence on AI provider viability prior to agreement"],
  ["due_diligence_completed"],
  ["CTRL-THIRD-PARTY-AI"], notes="APRA CPS 230 para 40 vendor due diligence.")

c("P1-076", "development", "enterprise_policy", "exact_match",
  "Procurement teams must assess whether an external AI vendor constitutes a Material Service Provider (MSP) whose failure would impact critical operations.",
  ["Assess whether external AI vendor constitutes a Material Service Provider (MSP)"],
  ["provider_materiality_assessed"],
  ["CTRL-THIRD-PARTY-AI"], notes="APRA CPS 230 para 39 materiality assessment.")

c("P1-077", "development", "enterprise_policy", "exact_match",
  "Contracts with third-party AI vendors must specify business continuity, audit rights, and operational substitution exit strategies.",
  ["Specify continuity, audit rights and operational substitution exit strategies in AI contracts"],
  ["contract_controls_defined", "performance_and_exit_monitored"],
  ["CTRL-THIRD-PARTY-AI"], notes="APRA CPS 230 para 41 mandatory contractual terms.")

c("P1-078", "development", "enterprise_policy", "exact_match",
  "All Material Service Providers hosting or serving AI models must be catalogued in the bank's register of material service providers.",
  ["Catalogue all AI Material Service Providers in central register"],
  ["msp_register_updated_for_ai_vendors"],
  ["CTRL-MSP-NOTIFICATION"], notes="APRA CPS 230 para 47 MSP register.")

c("P1-079", "development", "enterprise_policy", "numeric_threshold",
  "Entering into an agreement with an MSP for material cloud AI services must be notified to APRA within 20 business days of contract execution.",
  ["Notify APRA of MSP agreement within 20 business days of execution"],
  ["incident_72h_and_agreement_20bd_notifications_defined"],
  ["CTRL-MSP-NOTIFICATION"],
  threshold={"amount": 20, "unit": "business_days", "operator": "lte"},
  notes="APRA CPS 230 para 50 agreement notification timeframe.")

c("P1-080", "development", "enterprise_policy", "exact_match",
  "The bank must consult with APRA prior to entering into any arrangement to offshore material AI systems to foreign cloud hosting zones.",
  ["Consult with APRA prior to offshoring material AI systems"],
  ["prior_apra_consultation_for_material_offshoring"],
  ["CTRL-MSP-NOTIFICATION"], notes="APRA CPS 230 para 51 material offshoring consultation.")

c("P1-081", "development", "enterprise_policy", "numeric_threshold",
  "Any material disruption to AI services provided by a third-party vendor must be notified to APRA within 72 hours of identification.",
  ["Notify APRA of third-party AI service disruption within 72 hours"],
  ["incident_72h_and_agreement_20bd_notifications_defined"],
  ["CTRL-MSP-NOTIFICATION"],
  threshold={"amount": 72, "unit": "hours", "operator": "lte"},
  notes="APRA CPS 230 para 50 incident notification window.")

c("P1-082", "development", "enterprise_policy", "paraphrased_match",
  "Counterparty insolvency contingencies and operational substitution protocols must be documented for cloud AI infrastructure.",
  ["Document counterparty insolvency contingencies and operational substitution protocols"],
  ["performance_and_exit_monitored"],
  ["CTRL-THIRD-PARTY-AI"], notes="APRA CPS 230 para 38 operational substitution (BASE-10).")

c("P1-083", "development", "enterprise_policy", "exact_match",
  "Fourth-party supply chain concentration risks arising from common upstream foundational model weights must be assessed annually.",
  ["Annual assessment of fourth-party supply chain concentration in foundation models"],
  ["provider_materiality_assessed", "performance_and_exit_monitored"],
  ["CTRL-THIRD-PARTY-AI"],
  threshold={"amount": 1, "unit": "years", "operator": "lte"},
  notes="CPS 230 fourth-party concentration risk.")

c("P1-084", "development", "enterprise_policy", "exact_match",
  "Third-party AI service level agreements (SLAs) must mandate minimum model inference availability of 99.95% during standard banking hours.",
  ["Mandate minimum 99.95% model availability in third-party SLAs"],
  ["contract_controls_defined"],
  ["CTRL-THIRD-PARTY-AI"],
  threshold={"amount": 99.95, "unit": "percent", "operator": "gte"},
  notes="CPS 230 contractual service levels.")

c("P1-085", "development", "enterprise_policy", "exact_match",
  "The bank must verify that AI vendors maintain insurance coverage commensurate with their operational liabilities under APRA CPS 230.",
  ["Verify AI vendors maintain liability insurance commensurate with operations"],
  ["due_diligence_completed"],
  ["CTRL-THIRD-PARTY-AI"], notes="CPS 230 vendor insurance due diligence.")

c("P1-086", "development", "enterprise_policy", "conditional_requirement",
  "External AI software-as-a-service providers with annual contracts under AUD 100,000 are exempt from formal APRA MSP registration provided no customer PII is shared.",
  ["Exempt AI SaaS under AUD 100,000 without PII from APRA MSP registration"],
  ["msp_register_updated_for_ai_vendors"],
  ["CTRL-MSP-NOTIFICATION"],
  threshold={"amount": 100000, "currency": "AUD", "operator": "lte"},
  has_exception=True, notes="Conditional de minimis MSP contract threshold.")

# P1-087 to P1-092 (Holdout)
c("P1-087", "holdout", "enterprise_policy", "exact_match",
  "Vendor performance metrics and SLA compliance for third-party AI models must be reviewed quarterly by the Sourcing Risk Committee.",
  ["Quarterly review of third-party AI vendor SLAs by Sourcing Risk Committee"],
  ["performance_and_exit_monitored"],
  ["CTRL-THIRD-PARTY-AI"],
  threshold={"amount": 3, "unit": "months", "operator": "lte"},
  notes="Holdout: CPS 230 ongoing monitoring cadence.")

c("P1-088", "holdout", "enterprise_policy", "paraphrased_match",
  "The bank's material service provider ledger must include all cloud hyper-scalers hosting proprietary AI microservices.",
  ["Include cloud hyper-scalers hosting AI microservices in MSP ledger"],
  ["msp_register_updated_for_ai_vendors"],
  ["CTRL-MSP-NOTIFICATION"], notes="Holdout: Hyper-scaler cloud registration.")

c("P1-089", "holdout", "questionnaire_question", "questionnaire_facet",
  "Does the contract with the third-party AI provider explicitly provide the bank and APRA with full audit rights to inspect training data and security logs?",
  ["Inquire whether third-party contract provides bank and APRA with full audit rights"],
  ["contract_controls_defined"],
  ["CTRL-THIRD-PARTY-AI"], notes="Holdout: AIAF questionnaire vendor audit rights inquiry.")

c("P1-090", "holdout", "enterprise_policy", "negated_control",
  "The bank shall not execute agreements with third-party AI providers that exclude liability for gross negligence or regulatory non-compliance.",
  ["Prohibit agreements with AI providers that exclude liability for negligence or non-compliance"],
  ["contract_controls_defined"],
  ["CTRL-THIRD-PARTY-AI"], is_negated=True, notes="Holdout: Negated contract liability clause.")

c("P1-091", "holdout", "enterprise_policy", "multi_facet",
  "Vendor risk assessments must verify that offshore foundational AI providers maintain ISO 27001 certifications and commit to 72-hour breach notifications.",
  ["Verify offshore AI provider ISO 27001 certification and 72-hour breach notification"],
  ["due_diligence_completed", "incident_72h_and_agreement_20bd_notifications_defined"],
  ["CTRL-THIRD-PARTY-AI", "CTRL-MSP-NOTIFICATION"],
  threshold={"amount": 72, "unit": "hours", "operator": "lte"},
  notes="Holdout: Multi-facet vendor diligence and notification.")

c("P1-092", "holdout", "enterprise_policy", "ambiguous_legal",
  "Open-source foundational model weights downloaded directly from public repositories are not classified as third-party service providers under CPS 230.",
  ["Exclude downloaded open-source model weights from CPS 230 provider classification"],
  ["provider_materiality_assessed"],
  ["CTRL-THIRD-PARTY-AI"],
  provenance="ambiguous_legal", reviewer_status="pending_panel", confidence="medium",
  ambiguity="Prudential status of open-weight open-source AI artifacts under APRA CPS 230 service provider definitions.",
  notes="Holdout: Ambiguous open-source provider status.")

# ------------------------------------------------------------------------------
# DOMAIN 5: HUMAN OVERSIGHT & DELEGATED AUTHORITY THRESHOLDS (P1-093 to P1-112) - 14 Dev, 6 Holdout
# ------------------------------------------------------------------------------
c("P1-093", "development", "enterprise_policy", "exact_match",
  "All automated business credit recommendations exceeding AUD 500 must receive affirmative human approval from a Level 2 Lending Officer prior to release.",
  ["Require affirmative human approval for credit recommendations exceeding AUD 500", "Execute before loan release"],
  ["human_approval_required", "approval_threshold_defined", "pre_execution_block"],
  ["CTRL-DELEGATED-AUTHORITY-THRESHOLD", "CTRL-HUMAN-OVERSIGHT"],
  threshold={"amount": 500, "currency": "AUD", "operator": "gt"},
  notes="Canonical P0 delegated authority threshold requirement.")

c("P1-094", "development", "enterprise_policy", "exact_match",
  "Automated credit decisions must enforce a pre-execution block preventing core banking loan origination until dual-custody authorization is recorded.",
  ["Enforce pre-execution block in loan origination until dual authorization recorded"],
  ["pre_execution_block", "human_approval_required"],
  ["CTRL-DELEGATED-AUTHORITY-THRESHOLD"], notes="Pre-execution gating control.")

c("P1-095", "development", "enterprise_policy", "exact_match",
  "Every human approval or manual override of an automated credit decision must be logged to write-once immutable storage with cryptographic timestamping.",
  ["Log human approvals and overrides to write-once immutable storage with timestamps"],
  ["approval_logs_retained"],
  ["CTRL-DELEGATED-AUTHORITY-THRESHOLD"], notes="Audit log retention for approval actions.")

c("P1-096", "development", "enterprise_policy", "exact_match",
  "Credit lending officers exercising oversight over algorithmic models must complete mandatory AI competence and bias awareness training annually.",
  ["Complete annual AI competence and bias awareness training for lending officers"],
  ["operator_ai_competence_and_training_completed"],
  ["CTRL-HUMAN-OVERSIGHT"],
  threshold={"amount": 1, "unit": "years", "operator": "lte"},
  notes="ASIC RG 104 operator competence requirement.")

c("P1-097", "development", "enterprise_policy", "exact_match",
  "Line 2 Credit Risk must conduct monthly supervisory quality assurance reviews on a statistically representative sample of AI-assisted lending decisions.",
  ["Monthly supervisory QA review on sample of AI-assisted lending decisions"],
  ["supervisory_quality_assurance_on_ai_assisted_staff"],
  ["CTRL-HUMAN-OVERSIGHT"],
  threshold={"amount": 1, "unit": "months", "operator": "lte"},
  notes="Supervisory quality assurance under RG 104.")

c("P1-098", "development", "enterprise_policy", "exact_match",
  "The operational control interface must provide human operators with clear escalation pathways and unambiguous manual override authority.",
  ["Provide clear escalation pathways and unambiguous manual override authority"],
  ["clear_escalation_and_override_authority"],
  ["CTRL-HUMAN-OVERSIGHT"], notes="Human oversight override mechanisms.")

c("P1-099", "development", "enterprise_policy", "exact_match",
  "System architects must maintain an automated kill-switch enabling immediate suspension of automated trading algorithms during market stress.",
  ["Maintain automated kill-switch enabling immediate suspension of trading algorithms"],
  ["meaningful_human_oversight_and_kill_switch"],
  ["CTRL-HUMAN-OVERSIGHT"], notes="Emergency kill-switch control.")

c("P1-100", "development", "enterprise_policy", "exact_match",
  "Customers impacted by adverse automated credit decisions must be provided an accessible contestability pathway for independent human review.",
  ["Provide accessible customer contestability pathway for independent human review"],
  ["customer_contestability_and_recourse_pathway"],
  ["CTRL-HUMAN-OVERSIGHT"], notes="Customer contestability under RG 104 & Ethics Framework.")

c("P1-101", "development", "enterprise_policy", "numeric_threshold",
  "Corporate lending credit limits exceeding AUD 1,000,000 generated by machine learning models require joint approval by the Chief Credit Officer and Head of Risk.",
  ["Require joint CCO and Head of Risk approval for corporate credit over AUD 1,000,000"],
  ["human_approval_required", "approval_threshold_defined"],
  ["CTRL-DELEGATED-AUTHORITY-THRESHOLD", "CTRL-HUMAN-OVERSIGHT"],
  threshold={"amount": 1000000, "currency": "AUD", "operator": "gt"},
  notes="Tiered high-value corporate delegated authority.")

c("P1-102", "development", "enterprise_policy", "numeric_threshold",
  "Micro-business overdraft extensions up to AUD 10,000 may be processed autonomously provided applicant credit scores exceed 750.",
  ["Autonomous processing for micro-business overdrafts up to AUD 10,000 with score over 750"],
  ["approval_threshold_defined"],
  ["CTRL-DELEGATED-AUTHORITY-THRESHOLD"],
  threshold={"amount": 10000, "currency": "AUD", "operator": "lte"},
  notes="Autonomous credit limit threshold.")

c("P1-103", "development", "enterprise_policy", "paraphrased_match",
  "Four-eyes authorization is strictly required before any automated transaction anomaly flag on a commercial account can be dismissed.",
  ["Enforce four-eyes authorization prior to dismissing commercial transaction anomaly flags"],
  ["human_approval_required", "pre_execution_block"],
  ["CTRL-DELEGATED-AUTHORITY-THRESHOLD", "CTRL-HUMAN-OVERSIGHT"],
  notes="Banking synonym: Four-eyes authorization.")

c("P1-104", "development", "enterprise_policy", "paraphrased_match",
  "Human review records and officer signature hashes must be preserved for at least 7 years under APRA prudential record-keeping standards.",
  ["Preserve human review records and signature hashes for at least 7 years"],
  ["approval_logs_retained"],
  ["CTRL-DELEGATED-AUTHORITY-THRESHOLD"],
  threshold={"amount": 7, "unit": "years", "operator": "gte"},
  notes="Prudential retention of human sign-off evidence.")

c("P1-105", "development", "enterprise_policy", "conditional_requirement",
  "Emergency medical payments processed via automated welfare assistance AI are exempt from pre-execution approval up to AUD 250.",
  ["Exempt emergency welfare payments up to AUD 250 from pre-execution approval"],
  ["approval_threshold_defined", "pre_execution_block"],
  ["CTRL-DELEGATED-AUTHORITY-THRESHOLD"],
  threshold={"amount": 250, "currency": "AUD", "operator": "lte"},
  has_exception=True, notes="Conditional delegated authority waiver.")

c("P1-106", "development", "enterprise_policy", "exact_match",
  "Model drift monitoring must compare human rejection rates against automated recommendations on a weekly basis to detect decision divergence.",
  ["Weekly comparison of human rejection rates against automated recommendations to detect drift"],
  ["pre_deployment_and_ongoing_drift_monitoring"],
  ["CTRL-HUMAN-OVERSIGHT"],
  threshold={"amount": 1, "unit": "weeks", "operator": "lte"},
  notes="Behavioral drift monitoring.")

# P1-107 to P1-112 (Holdout)
c("P1-107", "holdout", "enterprise_policy", "exact_match",
  "All retail personal loan approvals exceeding AUD 5,000 must be reviewed and signed off by an authorized branch credit manager prior to disbursement.",
  ["Branch credit manager sign-off required for retail loans exceeding AUD 5,000 before disbursement"],
  ["human_approval_required", "approval_threshold_defined", "pre_execution_block"],
  ["CTRL-DELEGATED-AUTHORITY-THRESHOLD"],
  threshold={"amount": 5000, "currency": "AUD", "operator": "gt"},
  notes="Holdout: Retail loan approval threshold.")

c("P1-108", "holdout", "enterprise_policy", "negated_control",
  "Junior credit analysts shall not override machine learning credit risk assessments for applications exceeding AUD 25,000 without written concurrence from Senior Risk.",
  ["Prohibit junior analyst overrides over AUD 25,000 without Senior Risk concurrence"],
  ["clear_escalation_and_override_authority", "approval_threshold_defined"],
  ["CTRL-HUMAN-OVERSIGHT", "CTRL-DELEGATED-AUTHORITY-THRESHOLD"],
  threshold={"amount": 25000, "currency": "AUD", "operator": "gt"},
  is_negated=True, notes="Holdout: Negated override authority threshold.")

c("P1-109", "holdout", "questionnaire_question", "questionnaire_facet",
  "Is there a mandatory pre-execution technical control that blocks automated decisions from executing until human sign-off is logged?",
  ["Inquire whether technical pre-execution block prevents execution prior to human sign-off"],
  ["pre_execution_block", "human_approval_required"],
  ["CTRL-DELEGATED-AUTHORITY-THRESHOLD"], notes="Holdout: Questionnaire pre-execution inquiry.")

c("P1-110", "holdout", "questionnaire_question", "questionnaire_facet",
  "Can operational users immediately halt or override the AI system if anomalous or harmful outputs are observed in production?",
  ["Inquire whether operational users have kill-switch and immediate override capability"],
  ["meaningful_human_oversight_and_kill_switch", "clear_escalation_and_override_authority"],
  ["CTRL-HUMAN-OVERSIGHT"], notes="Holdout: Questionnaire kill-switch inquiry.")

c("P1-111", "holdout", "enterprise_policy", "multi_facet",
  "The automated payment engine must enforce a $1,000 human sign-off limit and store all dual-custody authorization tokens in cryptographic tamper-evident logs.",
  ["Enforce $1,000 human sign-off limit", "Store dual-custody tokens in tamper-evident logs"],
  ["human_approval_required", "approval_threshold_defined", "approval_logs_retained"],
  ["CTRL-DELEGATED-AUTHORITY-THRESHOLD"],
  threshold={"amount": 1000, "currency": "AUD", "operator": "gt"},
  notes="Holdout: Multi-facet delegated threshold and logging.")

c("P1-112", "holdout", "enterprise_policy", "ambiguous_legal",
  "Where automated AI decisions are confirmed by a human officer who merely clicks 'accept' without review within 5 seconds, meaningful human oversight is legally deemed satisfied.",
  ["Deem human oversight legally satisfied by 5-second accept click"],
  ["meaningful_human_oversight_and_kill_switch"],
  ["CTRL-HUMAN-OVERSIGHT"],
  provenance="ambiguous_legal", reviewer_status="pending_panel", confidence="low",
  ambiguity="Regulatory debate under ASIC RG 104 regarding whether superficial 'rubber stamping' satisfies meaningful human oversight.",
  notes="Holdout: Ambiguous rubber-stamping oversight clause.")

# ------------------------------------------------------------------------------
# DOMAIN 6: AI RISK ASSESSMENT & MODEL GOVERNANCE (P1-113 to P1-128) - 11 Dev, 5 Holdout
# APRA CPS 220, ISO 42001, NIST AI RMF
# ------------------------------------------------------------------------------
c("P1-113", "development", "enterprise_policy", "exact_match",
  "Every AI model deployed within the bank must have a formally appointed Accountable AI Owner registered in the enterprise model inventory.",
  ["Appoint Accountable AI Owner for all deployed models in enterprise inventory"],
  ["accountable_ai_owner_designated", "use_case_registered_in_enterprise_ai_inventory"],
  ["CTRL-AI-IMPACT-ASSESSMENT", "CTRL-AI-GOV-ACCOUNTABILITY"], notes="AI owner accountability.")

c("P1-114", "development", "enterprise_policy", "exact_match",
  "An ethical AI impact assessment evaluating risks to consumers, fundamental rights, and vulnerable customer cohorts must be completed prior to model development.",
  ["Complete ethical AI impact assessment on consumer risks prior to development"],
  ["ai_impact_and_stakeholder_assessment_completed", "consumer_harm_and_bias_assessed_pre_deployment"],
  ["CTRL-AI-IMPACT-ASSESSMENT", "CTRL-AI-GOV-ACCOUNTABILITY"], notes="Pre-development ethical impact assessment.")

c("P1-115", "development", "enterprise_policy", "exact_match",
  "The enterprise risk management framework (RMF) must explicitly identify and document AI-specific operational, strategic, and model risks under APRA CPS 220.",
  ["Document AI risks in enterprise RMF under APRA CPS 220"],
  ["ai_risk_identified", "ai_specific_risk_sources_and_consequences_identified"],
  ["CTRL-RISK-FRAMEWORK"], notes="APRA CPS 220 para 22 AI risk framework.")

c("P1-116", "development", "enterprise_policy", "exact_match",
  "Second-line Risk Management must independently review and challenge AI model development assumptions, training data provenance, and hyper-parameters.",
  ["Second-line independent challenge of AI assumptions, data and parameters"],
  ["second_line_risk_challenge_recorded"],
  ["CTRL-INDEPENDENT-AUDIT-ASSURANCE"], notes="CPS 220 three lines of defense.")

c("P1-117", "development", "enterprise_policy", "exact_match",
  "Internal Audit must conduct an independent triennial framework review verifying that model governance and validation policies cover all production AI algorithms.",
  ["Triennial Internal Audit review of AI model governance policies"],
  ["independent_framework_review_covers_ai"],
  ["CTRL-INDEPENDENT-AUDIT-ASSURANCE"],
  threshold={"amount": 3, "unit": "years", "operator": "lte"},
  notes="CPS 220 triennial framework review.")

c("P1-118", "development", "enterprise_policy", "exact_match",
  "Continuous drift monitoring must evaluate test, evaluation, verification, and validation (TEVV) validity metrics against baseline calibration datasets.",
  ["Evaluate TEVV validity metrics against calibration baselines in continuous drift monitoring"],
  ["tevv_validity_and_reliability_benchmarked"],
  ["CTRL-AI-DRIFT-MONITORING"], notes="NIST AI RMF Measure 1.1 TEVV benchmark.")

c("P1-119", "development", "enterprise_policy", "paraphrased_match",
  "Statistical parity across demographic sub-populations must be evaluated during credit scorecard calibration.",
  ["Evaluate statistical parity across demographic sub-populations in credit calibration"],
  ["fairness_and_explainability_metrics_evaluated"],
  ["CTRL-AI-DRIFT-MONITORING"], notes="Benchmark BASE-07 fairness synonym.")

c("P1-120", "development", "enterprise_policy", "exact_match",
  "Material AI control gaps that cannot be remediated within risk appetite must be formally escalated for board declaration under CPS 220.",
  ["Escalate unremediated material AI control gaps for board declaration under CPS 220"],
  ["material_ai_control_gaps_escalated_for_declaration"],
  ["CTRL-INDEPENDENT-AUDIT-ASSURANCE"], notes="CPS 220 board declaration escalation.")

c("P1-121", "development", "enterprise_policy", "exact_match",
  "The bank's AI Management System must align with ISO/IEC 42001, defining explicit AI policies, role charters, and executive governance committees.",
  ["Align AI Management System with ISO 42001 defining policies, roles and committees"],
  ["ai_policy_and_roles"],
  ["CTRL-ISO-AIMS"], notes="ISO/IEC 42001 clause 5 governance.")

c("P1-122", "development", "enterprise_policy", "exact_match",
  "Public users interacting with bank customer service conversational agents must be clearly informed that they are communicating with an artificial intelligence system.",
  ["Disclose AI nature to users interacting with conversational agents"],
  ["user_interaction_and_ai_use_disclosed"],
  ["CTRL-AI-IMPACT-ASSESSMENT"], notes="National AI Ethics Principle 5 transparency.")

c("P1-123", "development", "enterprise_policy", "exact_match",
  "Model risk tiering must classify all production AI systems into Low, Medium, High, or Critical risk tiers based on customer financial impact.",
  ["Classify production AI systems into risk tiers based on customer impact"],
  ["risk_tier_and_governance_proportionality_screened"],
  ["CTRL-AI-IMPACT-ASSESSMENT"], notes="Proportional risk tiering.")

# P1-124 to P1-128 (Holdout)
c("P1-124", "holdout", "enterprise_policy", "exact_match",
  "Management review of the enterprise AI management system must be conducted at least annually by the Executive Risk Committee under ISO/IEC 42001.",
  ["Annual management review of AI management system by Executive Risk Committee"],
  ["management_review"],
  ["CTRL-ISO-AIMS"],
  threshold={"amount": 1, "unit": "years", "operator": "lte"},
  notes="Holdout: ISO 42001 management review.")

c("P1-125", "holdout", "enterprise_policy", "paraphrased_match",
  "Whenever model performance drift crosses the 5% degradation threshold, automated retraining pipelines must suspend autonomous deployment.",
  ["Suspend autonomous deployment when performance drift crosses 5% threshold"],
  ["residual_risk_acceptance_and_drift_response_logged"],
  ["CTRL-AI-DRIFT-MONITORING"],
  threshold={"amount": 5, "unit": "percent", "operator": "gte"},
  notes="Holdout: Quantitative drift response threshold.")

c("P1-126", "holdout", "questionnaire_question", "questionnaire_facet",
  "Has the AI model undergone an independent review and technical challenge by Line 2 Risk prior to production deployment?",
  ["Inquire whether model underwent independent Line 2 challenge prior to production"],
  ["second_line_risk_challenge_recorded"],
  ["CTRL-INDEPENDENT-AUDIT-ASSURANCE"], notes="Holdout: AIAF questionnaire independent validation inquiry.")

c("P1-127", "holdout", "enterprise_policy", "negated_control",
  "Consumer credit scoring models shall not implement automated bias testing using synthetic demographic proxies.",
  ["Prohibit automated bias testing using synthetic demographic proxies in credit models"],
  ["fairness_and_explainability_metrics_evaluated"],
  ["CTRL-AI-DRIFT-MONITORING"], is_negated=True, notes="Holdout: Benchmark BASE-12 negated bias testing rule.")

c("P1-128", "holdout", "enterprise_policy", "multi_facet",
  "Model developers must document all intended use boundaries and establish safe decommissioning and rollback criteria under NIST AI RMF.",
  ["Document intended use boundaries", "Establish safe decommissioning and rollback criteria under NIST"],
  ["intended_purpose_and_out_of_scope_boundaries_documented", "safe_decommissioning_and_rollback_criteria_defined"],
  ["CTRL-NIST-AI-RMF"], notes="Holdout: Multi-facet NIST lifecycle controls.")

# ------------------------------------------------------------------------------
# DOMAIN 7: CUSTOMER COMPLAINTS & INTERNAL DISPUTE RESOLUTION (P1-129 to P1-140) - 8 Dev, 4 Holdout
# ASIC RG 271
# ------------------------------------------------------------------------------
c("P1-129", "development", "enterprise_policy", "exact_match",
  "Customer expressions of dissatisfaction involving AI chatbots or automated credit scoring must be broadly recognized as complaints under ASIC RG 271.",
  ["Broadly recognize customer dissatisfaction with AI as complaints under ASIC RG 271"],
  ["complaints_broadly_recognised"],
  ["CTRL-IDR-HANDLING"], notes="ASIC RG 271 definition of complaint.")

c("P1-130", "development", "enterprise_policy", "exact_match",
  "All customer complaints regarding AI decisions must be recorded in the centralized dispute register within 1 business day.",
  ["Record AI complaints in centralized register within 1 business day"],
  ["complaints_recorded"],
  ["CTRL-IDR-HANDLING"],
  threshold={"amount": 1, "unit": "business_days", "operator": "lte"},
  notes="ASIC RG 271 dispute registration.")

c("P1-131", "development", "enterprise_policy", "numeric_threshold",
  "The bank must provide a comprehensive written IDR response to consumer credit complaints involving automated models within a maximum of 30 calendar days.",
  ["Provide written IDR response to credit complaints within 30 calendar days"],
  ["response_timeframes_enforced"],
  ["CTRL-IDR-HANDLING"],
  threshold={"amount": 30, "unit": "days", "operator": "lte"},
  notes="ASIC RG 271 para 56 30-day statutory response horizon.")

c("P1-132", "development", "enterprise_policy", "exact_match",
  "Written IDR responses must inform complainants of their right to escalate unresolved AI disputes to the Australian Financial Complaints Authority (AFCA).",
  ["Inform complainants in IDR responses of right to escalate to AFCA"],
  ["response_content_complete"],
  ["CTRL-IDR-HANDLING"], notes="ASIC RG 271 AFCA referral notice.")

c("P1-133", "development", "enterprise_policy", "exact_match",
  "Customer dispute management systems must provide an immediate option to transfer from automated chatbot handling to a human dispute resolution specialist.",
  ["Provide immediate option to transfer from chatbot to human dispute specialist"],
  ["human_escalation_available"],
  ["CTRL-IDR-HANDLING"], notes="ASIC RG 271 human escalation option.")

c("P1-134", "development", "enterprise_policy", "exact_match",
  "Complaint data from automated decision systems must be analyzed monthly to identify recurring systemic issues and model logic defects.",
  ["Monthly analysis of complaint data to identify systemic issues and model defects"],
  ["complaint_data_analysed"],
  ["CTRL-IDR-SYSTEMIC"],
  threshold={"amount": 1, "unit": "months", "operator": "lte"},
  notes="ASIC RG 271 systemic issue monitoring.")

c("P1-135", "development", "enterprise_policy", "numeric_threshold",
  "A systemic issue threshold is triggered when more than 5 customer complaints identify the identical algorithmic credit refusal rationale in a calendar month.",
  ["Trigger systemic issue when more than 5 complaints identify identical refusal rationale"],
  ["systemic_issue_thresholds_defined"],
  ["CTRL-IDR-SYSTEMIC"],
  threshold={"amount": 5, "unit": "complaints", "operator": "gt"},
  notes="ASIC RG 271 systemic threshold trigger.")

c("P1-136", "development", "enterprise_policy", "exact_match",
  "When a systemic algorithmic error is confirmed, the bank must proactively identify, communicate with, and remediate all affected customers.",
  ["Proactively identify and remediate all affected customers for confirmed systemic errors"],
  ["affected_customers_remediated", "systemic_issues_escalated"],
  ["CTRL-IDR-SYSTEMIC"], notes="ASIC RG 271 systemic customer remediation.")

# P1-137 to P1-140 (Holdout)
c("P1-137", "holdout", "enterprise_policy", "exact_match",
  "Systemic AI dispute root causes must be formally reported to the Board Audit & Risk Committee on a quarterly basis under ASIC RG 271.",
  ["Quarterly reporting of systemic AI dispute root causes to Board Audit & Risk Committee"],
  ["systemic_issues_escalated"],
  ["CTRL-IDR-SYSTEMIC"],
  threshold={"amount": 3, "unit": "months", "operator": "lte"},
  notes="Holdout: Board escalation of systemic complaints.")

c("P1-138", "holdout", "questionnaire_question", "questionnaire_facet",
  "Does the customer intake flow provide a clear, free-of-charge mechanism for individuals to dispute an adverse AI outcome with a human operator?",
  ["Inquire whether intake flow provides clear, free mechanism to dispute AI outcome with human"],
  ["human_escalation_available"],
  ["CTRL-IDR-HANDLING"], notes="Holdout: Questionnaire dispute mechanism inquiry.")

c("P1-139", "holdout", "enterprise_policy", "negated_control",
  "Customer service staff shall not refuse to register an oral expression of dissatisfaction simply because the customer cannot identify the specific AI algorithm involved.",
  ["Prohibit refusing oral complaints because customer cannot identify specific algorithm"],
  ["complaints_broadly_recognised", "complaints_recorded"],
  ["CTRL-IDR-HANDLING"], is_negated=True, notes="Holdout: Negated complaint barrier rule.")

c("P1-140", "holdout", "enterprise_policy", "paraphrased_match",
  "Remediation payments for algorithmic overcharging errors must be calculated and disbursed to impacted cardholders within 60 days of systemic confirmation.",
  ["Disburse remediation payments for algorithmic overcharging within 60 days of confirmation"],
  ["affected_customers_remediated"],
  ["CTRL-IDR-SYSTEMIC"],
  threshold={"amount": 60, "unit": "days", "operator": "lte"},
  notes="Holdout: Quantitative customer remediation horizon.")

# ------------------------------------------------------------------------------
# DOMAIN 8: RESPONSIBLE LENDING & CREDIT UNSUITABILITY (P1-141 to P1-148) - 5 Dev, 3 Holdout
# National Consumer Credit Protection Act 2009 (NCCP Act)
# ------------------------------------------------------------------------------
c("P1-141", "development", "enterprise_policy", "exact_match",
  "Automated lending platforms must capture the consumer's specific requirements and loan objectives prior to issuing an automated preliminary credit assessment.",
  ["Capture consumer requirements and objectives prior to preliminary credit assessment"],
  ["consumer_requirements_and_objectives_captured"],
  ["CTRL-CREDIT-UNSUITABILITY"], notes="NCCP Act s 128 inquiry requirement.")

c("P1-142", "development", "enterprise_policy", "exact_match",
  "Consumer financial situations, income, and non-discretionary expenses must be verified from reliable third-party evidence (such as bank transaction feeds) rather than self-declared claims.",
  ["Verify consumer financial situation and expenses from reliable third-party feeds"],
  ["financial_situation_verified_from_reliable_evidence"],
  ["CTRL-CREDIT-UNSUITABILITY"], notes="NCCP Act s 130 verification standard.")

c("P1-143", "development", "enterprise_policy", "exact_match",
  "The automated decision engine must enforce an unsuitability filter that rejects loan contracts if the consumer will be unable to meet financial obligations without substantial hardship.",
  ["Enforce unsuitability filter rejecting loans causing substantial financial hardship"],
  ["unsuitability_and_substantial_hardship_screen_enforced"],
  ["CTRL-CREDIT-UNSUITABILITY"], notes="NCCP Act s 131 unsuitability test.")

c("P1-144", "development", "enterprise_policy", "exact_match",
  "A written copy of the credit unsuitability assessment must be generated and stored, retrievable for consumer provision within 7 business days of request.",
  ["Generate and store written credit unsuitability assessment retrievable within 7 business days"],
  ["written_unsuitability_assessment_retrievable"],
  ["CTRL-CREDIT-UNSUITABILITY"],
  threshold={"amount": 7, "unit": "business_days", "operator": "lte"},
  notes="NCCP Act s 132 written assessment retrieval.")

c("P1-145", "development", "enterprise_policy", "exact_match",
  "Australian Credit Licence (ACL) holders deploying automated credit tools must ensure services are provided efficiently, honestly, and fairly under Section 47.",
  ["Ensure automated credit tools operate efficiently, honestly and fairly under s 47"],
  ["credit_activity_fairness_and_honesty_verified"],
  ["CTRL-AI-GOV-ACCOUNTABILITY"], notes="NCCP Act s 47 general licensee conduct.")

# P1-146 to P1-148 (Holdout)
c("P1-146", "holdout", "enterprise_policy", "exact_match",
  "Credit compliance teams must monitor automated loan approvals continuously to identify statutory breaches of responsible lending provisions.",
  ["Continuously monitor automated loan approvals for responsible lending breaches"],
  ["credit_compliance_and_breach_monitoring_active"],
  ["CTRL-AI-GOV-ACCOUNTABILITY"], notes="Holdout: NCCP Act breach monitoring.")

c("P1-147", "holdout", "questionnaire_question", "questionnaire_facet",
  "Does the automated credit scoring pipeline capture and independently verify customer expenses against primary banking statements before issuing loan approval?",
  ["Inquire whether automated pipeline captures and verifies expenses against bank statements"],
  ["financial_situation_verified_from_reliable_evidence"],
  ["CTRL-CREDIT-UNSUITABILITY"], notes="Holdout: Responsible lending verification questionnaire check.")

c("P1-148", "holdout", "enterprise_policy", "negated_control",
  "Credit decisioning models shall not approve personal loans where applicant living expenses are estimated solely using benchmark poverty indexes without actual verification.",
  ["Prohibit loan approvals where living expenses are estimated solely from poverty benchmarks"],
  ["financial_situation_verified_from_reliable_evidence", "unsuitability_and_substantial_hardship_screen_enforced"],
  ["CTRL-CREDIT-UNSUITABILITY"], is_negated=True, notes="Holdout: Responsible lending benchmark prohibition (HEM benchmark case).")

# ------------------------------------------------------------------------------
# DOMAIN 9: EXTRATERRITORIAL EU AI ACT & SCOPE BOUNDING (P1-149 to P1-156) - 5 Dev, 3 Holdout
# ------------------------------------------------------------------------------
c("P1-149", "development", "regulatory_obligation", "exact_match",
  "The bank must confirm whether the AI system is placed on the market or used in the European Union, establishing territorial nexus under Article 2 of the EU AI Act.",
  ["Confirm whether AI system establishes EU territorial nexus under Article 2"],
  ["territorial_nexus_confirmed", "regulated_role_confirmed"],
  ["CTRL-EU-HIGH-RISK"], notes="EU AI Act Article 2 territorial scope.")

c("P1-150", "development", "regulatory_obligation", "exact_match",
  "AI systems utilized to evaluate the creditworthiness of natural persons or establish their credit score are classified as High-Risk AI Systems under Annex III(5)(b).",
  ["Classify creditworthiness evaluation AI as High-Risk under Annex III(5)(b)"],
  ["risk_classification_confirmed", "annex3_5b_credit_vs_fraud_exemption_assessed"],
  ["CTRL-EU-HIGH-RISK"], notes="EU AI Act High-Risk classification.")

c("P1-151", "development", "enterprise_policy", "exact_match",
  "Deployers of High-Risk credit evaluation AI systems must retain system logs generated by the AI system for at least 6 months under Article 26.",
  ["Retain system logs for High-Risk credit AI for at least 6 months under Article 26"],
  ["deployer_human_oversight_and_6month_log_retention"],
  ["CTRL-EU-HIGH-RISK"],
  threshold={"amount": 6, "unit": "months", "operator": "gte"},
  notes="EU AI Act Article 26 deployer log retention.")

c("P1-152", "development", "enterprise_policy", "exact_match",
  "AI systems used strictly for the purpose of detecting financial fraud are exempt from High-Risk classification under Annex III(5)(b).",
  ["Exempt dedicated financial fraud detection systems from High-Risk classification"],
  ["annex3_5b_credit_vs_fraud_exemption_assessed"],
  ["CTRL-EU-HIGH-RISK"], has_exception=True, notes="EU AI Act fraud detection exception.")

c("P1-153", "development", "enterprise_policy", "exact_match",
  "Prior to deploying high-risk credit scoring AI in the EU, the deployer must complete a Fundamental Rights Impact Assessment (FRIA) under Article 27.",
  ["Complete Fundamental Rights Impact Assessment (FRIA) under Article 27 prior to deployment"],
  ["article27_fundamental_rights_impact_assessment_completed"],
  ["CTRL-EU-HIGH-RISK"], notes="EU AI Act Article 27 FRIA requirement.")

# P1-154 to P1-156 (Holdout)
c("P1-154", "holdout", "enterprise_policy", "negated_control",
  "AI systems that deploy subliminal techniques or exploit vulnerabilities of specific demographic groups to materially distort behavior are strictly prohibited under Article 5.",
  ["Prohibit AI systems deploying subliminal techniques or exploiting vulnerabilities under Article 5"],
  ["article5_prohibited_practices_screened_out"],
  ["CTRL-EU-HIGH-RISK"], is_negated=True, notes="Holdout: EU AI Act Article 5 prohibited practice.")

c("P1-155", "holdout", "regulatory_obligation", "non_applicable_obligation",
  "A domestic Australian credit union offering home loans strictly to residents of New South Wales without any EU operations or marketing has zero EU AI Act compliance obligations.",
  ["Confirm domestic Australian credit union without EU operations is exempt from EU AI Act"],
  ["territorial_nexus_confirmed"],
  ["CTRL-EU-HIGH-RISK"], is_negated=True, notes="Holdout: Statutory non-applicability rule verification.")

c("P1-156", "holdout", "enterprise_policy", "exact_match",
  "All staff operating high-risk banking AI tools must have documented evidence of AI literacy training under Article 4 of the EU AI Act.",
  ["Document evidence of AI literacy training for staff operating high-risk AI tools"],
  ["article4_staff_ai_literacy_evidenced"],
  ["CTRL-EU-HIGH-RISK"], notes="Holdout: EU AI Act Article 4 staff literacy.")

# ==============================================================================
# DATASET SERIALIZATION & INTEGRITY CHECK
# ==============================================================================
dev_count = sum(1 for x in cases if x["split"] == "development")
holdout_count = sum(1 for x in cases if x["split"] == "holdout")
human_verified = sum(1 for x in cases if x["reviewer_status"] == "panel_verified")
synthetic_ref = sum(1 for x in cases if x["ground_truth_provenance"] == "synthetic_reference")
ambiguous_count = sum(1 for x in cases if x["ground_truth_provenance"] == "ambiguous_legal")

dataset_payload = {
    "dataset_id": "P1_EVALUATION_DATASET_V2",
    "version": "2.0.0",
    "description": "DeepAudit Crosswalk Phase P1 Multi-Layer Semantic Mapping & Coverage Evaluation Benchmark",
    "jurisdiction": "AU",
    "authoritative_regulatory_sources": [
        "APRA CPS 230 (Operational Resilience)",
        "APRA CPS 234 (Information Security)",
        "APRA CPS 220 (Risk Management)",
        "APRA CPG 235 (Managing Data Risk)",
        "Privacy Act 1988 / Australian Privacy Principles 1-13 & NDB",
        "ASIC RG 271 (Internal Dispute Resolution)",
        "ASIC RG 104 / RG 105 (AFSL Licensing Competence)",
        "National Consumer Credit Protection Act 2009 (NCCP Act)",
        "EU AI Act (Extraterritorial Scope)",
        "ISO/IEC 42001:2023 & ISO/IEC 27001:2022",
        "NIST AI RMF 1.0",
    ],
    "provenance_summary": {
        "total_cases": len(cases),
        "development_split_count": dev_count,
        "holdout_split_count": holdout_count,
        "human_verified_count": human_verified,
        "synthetic_reference_count": synthetic_ref,
        "ambiguous_legal_count": ambiguous_count,
        "independent_external_panel_reviews_completed": 0,
        "disclaimer": "All 156 cases are synthetic benchmark references constructed for reproducible algorithmic evaluation. 0 cases have received external independent human GRC panel sign-off. Ambiguous cases are flagged for legal review.",
    },
    "cases": cases,
}

output_path = repo_root / "P1_EVALUATION_DATASET_V2.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(dataset_payload, f, indent=2, ensure_ascii=False)

print(f"SUCCESS: Wrote {len(cases)} cases to {output_path}")
print(f"  Development: {dev_count}")
print(f"  Holdout:     {holdout_count}")
print(f"  Synthetic:   {synthetic_ref}")
print(f"  Ambiguous:   {ambiguous_count}")
