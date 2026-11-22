# DeepAudit Crosswalk — E3.5 Evidence Sufficiency Matrix

**Document ID**: `DEEPAUDIT-E35-EVIDENCE-SUFFICIENCY-MATRIX-V1`  
**Version**: `1.0.0`  
**Regulatory Baseline**: Regulatory Pack v0.2.0 (17 Sources, 46 Obligations, 33 Controls, 158 Canonical Facets)  
**Working Branch**: `fix/e35-normative-evidence-assurance`  
**Classification**: Regulatory Governance Assurance Specification  

---

## 1. Regulatory Reconciliation Principles

Under the DeepAudit Crosswalk assurance framework, crosswalk decisions must adhere to strict evidence sufficiency standards:

1. **Equivalence Invariant**: An enterprise clause is classified as `EQUIVALENT` if and only if:
   - All extracted canonical facets required by the target statutory obligation are satisfied.
   - The enterprise obligation modality is mandatory (or an aligned binding declarative assertion).
   - There are no unverified discretionary carve-outs, missing conditions, or unresolved internal attachments.
   - Any quantitative threshold meets or exceeds the regulatory minimum (e.g., lower dollar threshold for required human sign-off, or shorter incident notification deadline).
2. **Partial Coverage Invariant**: When an enterprise clause satisfies some but not all required facets, or covers an operational subset without addressing required governance structures, it is classified as `PARTIALLY_OVERLAPPING`. The missing facets are explicitly recorded in `missing_conditions_or_evidence`.
3. **Weaker / Insufficient Invariant**: When an enterprise policy permits optional compliance, introduces discretionary exemptions, operates retrospective (post-execution) reviews instead of pre-execution blocks, or implements higher risk thresholds, it is classified as `WEAKER_OR_POTENTIALLY_INSUFFICIENT`.
4. **Conflict Invariant**: When an enterprise directive mandates actions contrary to statutory duties (e.g., indefinite retention vs APP 11.2 destruction, or unauthorized exemptions from OAIC breach reporting), it is classified as `POTENTIAL_CONFLICT`.
5. **Undetermined Invariant**: When an enterprise clause references unparsed external instruments, schedules, or annexures (e.g., *"must comply with Annexure D2"*), it is classified as `UNDETERMINED` pending human provision of the referenced document.

---

## 2. Evidence Sufficiency Matrix for Priority Banking Obligations

| Obligation ID | Statutory Source | Required Canonical Facets | Required Evidence Artifacts | Classification Rules |
|---|---|---|---|---|
| **`AU-APRA-CPS234-CONTROLS`** | APRA CPS 234 paras 21–26 | `information_assets_identified`, `threats_and_vulnerabilities_assessed`, `controls_commensurate`, `third_party_assets_in_scope` | Information asset register, AI threat assessments, baseline security controls standard, third-party hosting security terms. | **EQUIVALENT**: All 4 facets present, controls commensurate with asset criticality.<br>**PARTIAL**: General infosec policy present but third-party assets or threat assessments missing.<br>**WEAKER**: Controls voluntary or discretionary for non-core systems. |
| **`AU-APRA-CPS234-INCIDENT`** | APRA CPS 234 paras 35–37 | `incident_detection_defined`, `response_and_escalation_defined`, `apra_notification_screened`, `material_weaknesses_tracked` | 24/7 SIEM/SOC incident detection procedure, APRA 72-hour notification protocol, security incident register, control weakness remediation tickets. | **EQUIVALENT**: Detection + response + APRA $\le$ 72h notification + remediation tracking.<br>**STRICTER**: Notification deadline shorter (e.g., $\le$ 24h).<br>**CONFLICT**: Deadline exceeds 72h (e.g., 10 days or 15 days). |
| **`AU-APRA-CPS230-OPS`** | APRA CPS 230 paras 22–38 | `operational_risk_management_framework_defined`, `operational_resilience_tolerances_set`, `internal_controls_monitored` | Operational risk management policy, AI disruption tolerance metrics, internal control effectiveness reviews. | **EQUIVALENT**: Complete framework with tolerances and monitoring.<br>**STRICTER**: Stricter financial delegation thresholds (e.g., AUD 500 pre-execution blocks).<br>**WEAKER**: Post-execution manager review for high-risk transactions. |
| **`AU-APRA-CPS230-NOTIFY`** | APRA CPS 230 paras 58–60 | `apra_notification_within_24h`, `material_service_provider_disruption_screened` | Material service provider incident register, 24-hour APRA notification runbook. | **EQUIVALENT**: $\le$ 24-hour notification for material operational disruptions.<br>**CONFLICT**: Notification timeframe exceeds 24 hours. |
| **`AU-PRIV-APP1-GOV`** | Privacy Act 1988 APP 1 | `privacy_accountability_assigned`, `privacy_practices_implemented`, `privacy_policy_current` | Appointment of Chief Privacy Officer / privacy lead, documented privacy processes, public APP privacy policy. | **EQUIVALENT**: Accountability assigned, practices active, current policy published.<br>**WEAKER**: Privacy impact assessments optional or closure tracking discretionary. |
| **`AU-PRIV-APP1.7-AUTOMATED`** | Privacy Act 1988 APP 1.7 | `significant_decision_screened`, `personal_information_kinds_disclosed`, `decision_kinds_disclosed` | Automated decision register, public privacy policy disclosures covering automated decision kinds and personal data inputs. | **EQUIVALENT**: Screens significant decisions and discloses both personal data categories and decision types.<br>**PARTIAL**: Discloses data categories but omits specific decision types. |
| **`AU-PRIV-APP8-CROSSBORDER`** | Privacy Act 1988 APP 8 | `overseas_recipients_and_regions_mapped`, `contractual_reasonable_steps_enforced`, `section16c_accountability_assessed` | Overseas data transfer register, cross-border contract clauses, documented s 16C exception assessments. | **EQUIVALENT**: Comprehensive recipient mapping, enforceable contractual clauses, and s 16C assessment.<br>**UNDETERMINED**: Cross-border flow references unparsed jurisdiction appendices. |
| **`AU-PRIV-APP11-SECURITY`** | Privacy Act 1988 APP 11 | `technical_security_measures_implemented`, `organisational_security_measures_implemented`, `retention_schedule_applied`, `destruction_or_deidentification_verified` | Encryption at rest/in transit keys, security awareness training records, retention schedule, certified deletion logs. | **EQUIVALENT**: Both technical/organisational controls AND retention destruction/de-identification verified.<br>**PARTIAL**: Technical controls present but retention schedule omitted.<br>**CONFLICT**: Personal information retained indefinitely or destruction prohibited. |
| **`AU-PRIV-NDB-S26WE`** | Privacy Act 1988 Part IIIC | `ndb_30day_assessment_workflow_defined`, `oaic_notification_prepared`, `affected_individuals_notified` | Data breach response plan, 30-day serious-harm assessment workflow, statutory notification templates. | **EQUIVALENT**: 30-day assessment workflow + OAIC notification + individual notification.<br>**CONFLICT**: Management discretion to waive OAIC notification on serious-harm breaches. |
| **`AU-ASIC-RG271-COMPLAINT`** | ASIC RG 271 | `complaint_definition_broad`, `idr_register_maintained`, `timeframes_enforced`, `written_response_with_afca_provided`, `human_review_pathway_available` | Omnichannel complaint intake procedure, central IDR register, 30-day SLA monitoring, AFCA escalation notice template. | **EQUIVALENT**: All 5 facets operationalized.<br>**WEAKER**: Exceptions for informal branch handling or omission of AFCA rights.<br>**CONFLICT**: Failure to record complaints or response timeframe exceeds 30 calendar days. |
| **`AU-NAIC-AI6-TEST-HUMAN`** | Australia AI Ethics Principle 6 | `pre_deployment_and_ongoing_drift_monitoring`, `meaningful_human_oversight_and_kill_switch`, `customer_contestability_and_recourse_pathway` | AI validation test reports, model drift alerting logs, operations kill-switch controls, human contestability runbook. | **EQUIVALENT**: Pre-deployment validation + continuous drift alerts + emergency kill switch + contestability.<br>**PARTIAL**: Human approval threshold defined without drift monitoring or recourse. |
| **`AU-NCCP-S128-131-LENDING`**| NCCP Act ss 128–131 | `consumer_objectives_captured`, `financial_situation_verified`, `unsuitability_screened`, `written_assessment_retained` | Structured credit inquiry workflow, Open Banking / payslip verification engine, hardship rules, retrievable assessment file. | **EQUIVALENT**: All 4 lending facets operationalized.<br>**PARTIAL**: Assessment performed but unsuitability screen not documented. |

---

## 3. Preservation of Human Governance Integrity

In accordance with enterprise assurance rules:
- An AI match score $\ge 0.90$ or a deterministic rule match **does not automatically grant approved status**.
- Every reconciliation decision generated by the engine initializes with `decision_status = PROPOSED` (or `FLAGGED` if conflicts or missing evidence are detected).
- Only an authorized compliance officer or human auditor with tenant governance permissions may transition a mapping to `APPROVED`.
