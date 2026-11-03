# DeepAudit Crosswalk — Assessment Coverage Accuracy Report

**Document Status:** Final Audit Deliverable  
**Date:** 2026-11-04  
**Audit Scope:** Downstream Assessment Coverage Accuracy across Strategy, Questionnaire, and AI Use Case Targets  
**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Git Baseline Commit:** `d57eeaa5f12590931dd9378577554dc4b48d5fdd`  
**Branch:** `audit/semantic-mapping-reliability`  
**Evaluation Dataset Reference:** [`MAPPING_EVALUATION_DATASET.json`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/MAPPING_EVALUATION_DATASET.json) (63 Cases)  

---

## Executive Summary

This empirical report evaluates the accuracy of **DeepAudit Crosswalk** when evaluating downstream governance targets against an established enterprise baseline. In accordance with the intended product architecture, downstream assessment targets are divided into three distinct operational categories:

1. **Scenario A: AI Governance Strategy Coverage** (12 Test Cases) — High-level governance commitments, oversight structures, and policy mandates.
2. **Scenario B: AI Assessment Questionnaire Coverage** (14 Test Cases) — Pre-deployment risk assessments, intake questionnaires, and control verification inquiries.
3. **Scenario C: AI Use Case Operational & Evidence Coverage** (12 Test Cases) — Concrete operational deployments (e.g. Australian Banking AI Refund Agent, AUD 500 threshold), implementation facts, and evidence artifacts.

### Key Accuracy Findings Summary
To prevent concealment of critical domain-specific deficiencies, the accuracy metrics for each scenario are reported independently:

| Evaluation Dimension | Scenario A: Strategy Coverage | Scenario B: Questionnaire Coverage | Scenario C: Use Case Coverage | Baseline Construction |
| :--- | :---: | :---: | :---: | :---: |
| **Execution Classification** | **Proxy Measurement** *(E2E Engine Not Yet Built)* | **Isolated Component Test** *(& Pipeline Demo)* | **Direct Execution** *(App) / **Unmeasured** (Evid)* | **Direct Production Execution** |
| **Total Test Cases** | 12 | 14 | 12 | 25 |
| **Measured Precision** | **50.00% (Proxy)** | **100.00%\* (Isolated)** | **100.00% (Applicability: 7/7)** | **53.85% (Direct)** |
| **Measured Recall** | **16.67% (Proxy)** | **12.50% (Isolated)** | **100.00% (Applicability: 7/7)** | **38.89% (Direct)** |
| **Measured F1 Score** | **25.00% (Proxy)** | **22.22% (Isolated)** | **100.00% (Applicability: 7/7)** | **45.16% (Direct)** |
| **False Positives ($FP$)** | 1 (Proxy) | 0 | 0 | 6 (Direct) |
| **False Negatives ($FN$)** | 5 (Proxy) | 7 | 0 (Applicability) | 11 (Direct) |
| **False-Control Triggers** | 1 (Aspirational statement) | 0 | 0 | 3 (Negated / unrepresented) |
| **Features Unimplemented** | End-to-end Strategy Assessment | Inquiry syntactic parsing | Operational telemetry & evidence (5 cases) | Specialized cultural ontology |
| **Ground Truth Provenance** | 12 Synthetic Reference | 14 Synthetic Reference | 10 Synthetic / 2 Ambiguous | 25 Synthetic Reference |

*\*Note on Questionnaire Precision: The 100% precision reflects extreme over-conservatism; the isolated regex matched 1 single valid question out of 8, rejecting 87.5% of valid assessment questions due to brittle keyword mismatch.*  
*\*\*Note on Ground Truth: 0 cases have received external independent human expert review panel sign-off; all 61 cases are synthetic reference labels pending formal expert panel review.*

---

## 1. Scenario A — AI Governance Strategy Coverage Accuracy

### 1.1 Scope & Governance Criteria
An **AI Governance Strategy** establishes high-level organizational accountability, risk appetite, executive reporting cadences, and foundational commitments.
- **Evaluation Principle:** Strategy-level coverage must verify governance commitments, policy mandates, and organizational structures **without demanding operational implementation evidence** (such as API logs, unit test results, or encryption key certificates) that are inappropriate for an executive strategy document.
- **Key Risk Tested:** Aspirational statements (e.g. *"we aim to do the right thing"*) must NOT be classified as satisfying mandatory governance requirements.

### 1.2 Quantitative Accuracy Metrics
- **Evaluated Cases:** 12
- **True Positives ($TP$):** 1 (Valid commitments recognized: Independent model validation cadence)
- **False Positives ($FP$):** 1 (Vague ethical aspiration treated as satisfying governance oversight)
- **False Negatives ($FN$):** 5 (Legitimate strategy commitments missed due to executive phrasing)
- **True Negatives ($TN$):** 5 (Uncommitted or deficient strategy statements correctly rejected)
- **Precision:** $1 / (1 + 1) = \mathbf{50.00\%}$
- **Recall:** $1 / (1 + 5) = \mathbf{16.67\%}$
- **F1 Score:** $\mathbf{25.00\%}$

### 1.3 Detailed Strategy Failure Cases

| Case ID | Strategy Input Text | Expected Result | Actual Result | Code Path | Root Cause | Governance Consequence |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| **STRAT-01** | *"The Board Risk Committee retains ultimate accountability for enterprise AI adoption and reviews high-risk AI inventory semi-annually."* | Covered (`CTRL-GOV-OVERSIGHT`, APRA CPS 220) | Missed (`[]`) | [`backend/banking_crosswalk/policy.py:180`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L180) | `ENTERPRISE_FACET_PATTERNS` looks for `"human approval"` or `"authorised officer"`, but lacks executive governance phrases like `"Board Risk Committee"`. | **Critical:** Executive board-level accountability under APRA CPS 220 is flagged as absent in board reporting. |
| **STRAT-02** | *"We believe in ethical, responsible AI and aim to do the right thing for all our valued customers."* | Not Covered (Vague aspiration, zero binding commitment) | **FALSE POSITIVE:** Covered (`CTRL-GOV-OVERSIGHT`) | [`backend/banking_crosswalk/policy.py:200`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L200) | Ingestion matched the token `"responsible AI"` from generic ethics dictionary and created a candidate control mapping. | **High:** Non-binding marketing statement falsely reassures compliance teams that governance is established. |
| **STRAT-06** | *"Adverse credit decisions generated or assisted by AI must produce legally compliant reasons for decision under NCCP Act and ASIC guidance."* | Covered (`CTRL-GOV-TRANSPARENCY`, ASIC RG 209/NCCP) | Missed (`[]`) | [`backend/banking_crosswalk/policy.py:195`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L195) | Pattern matches `"model explainability"` or `"feature importance"`, failing to match legal statutory phrase `"reasons for decision"`. | **High:** Core legal consumer protection explainability mandate dropped from strategy assessment. |
| **STRAT-08** | *"Material AI service providers must undergo formal operational risk review, fourth-party subcontracting assessment, and contractual audit-rights verification."* | Covered (`CTRL-TPS-VENDOR-ASSESSMENT`, APRA CPS 230) | Missed (`[]`) | [`backend/banking_crosswalk/policy.py:210`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L210) | Matches `"vendor due diligence"` only; failed on `"material AI service providers"`. | **Critical:** Strategy-level APRA CPS 230 operational risk mandate incorrectly reported as missing. |
| **STRAT-10** | *"Annual red-teaming, prompt injection resilience testing, and external cryptographic assessment are mandatory for public-facing LLMs."* | Covered (`CTRL-TECH-ACCESS-SECURITY`, CPS 234) | Missed (`[]`) | [`backend/banking_crosswalk/policy.py:185`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L185) | Pattern matches `"information security testing"` or `"vulnerability scan"`; lacks modern AI security terms like `"red-teaming"` and `"prompt injection resilience"`. | **High:** APRA CPS 234 AI cybersecurity testing strategy flagged as deficient. |
| **STRAT-12** | *"A formal Privacy Impact Assessment signed by the Data Protection Officer is mandatory prior to processing personal data in AI models."* | Covered (`CTRL-DATA-PRIVACY-RIGHTS`, Privacy Act APP 1) | Missed (`[]`) | [`backend/banking_crosswalk/policy.py:190`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L190) | Pattern requires `"privacy policy"` or `"consent"`; missed industry standard acronym `"Privacy Impact Assessment"`. | **High:** Privacy governance structure flagged as missing. |

---

## 2. Scenario B — AI Assessment Questionnaire Coverage Accuracy

### 2.1 Scope & Governance Criteria
An **AI Assessment Questionnaire** (e.g. Australian AI Assurance Framework - AIAF, or internal intake questionnaire) evaluates whether proposed AI systems comply with policy prior to deployment.
- **Evaluation Principle:** Questionnaire assessment evaluates whether the questions adequately **probe and test** the required regulatory and enterprise control facets.
- **Critical Governance Rule:** The presence of a question in a questionnaire **is NOT proof that the control is implemented or effective**. It merely confirms that the assessment scope includes that control.

### 2.2 Quantitative Accuracy Metrics
- **Evaluated Cases:** 14
- **True Positives ($TP$):** 1 (Specific numeric threshold inquiry recognized)
- **False Positives ($FP$):** 0 (No superficial questions erroneously accepted)
- **False Negatives ($FN$):** 7 (Rigorous, highly specific governance questions rejected due to phrasing)
- **True Negatives ($TN$):** 6 (Vague or subjective questions correctly identified as inadequate)
- **Precision:** $1 / (1 + 0) = \mathbf{100.00\%}$
- **Recall:** $1 / (1 + 7) = \mathbf{12.50\%}$
- **F1 Score:** $\mathbf{22.22\%}$

### 2.3 Detailed Questionnaire Failure Cases

| Case ID | Questionnaire Question Text | Expected Result | Actual Result | Code Path | Root Cause | Governance Consequence |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| **QUEST-01** | *"Does an executive committee approve high-risk AI systems?"* | Valid Control Probe (`CTRL-GOV-OVERSIGHT`) | Rejected (`[]`) | [`backend/banking_crosswalk/policy.py:180`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L180) | Interrogative question syntax (*"Does an executive committee..."*) does not match declarative phrase patterns (*"human approval is required"*). | **High:** Rigorous intake question on executive sign-off reported as having zero control coverage. |
| **QUEST-05** | *"Are personal data elements masked in prompt logs sent to third-party model providers?"* | Valid Privacy Probe (`CTRL-DATA-PRIVACY-RIGHTS`, APP 11) | Rejected (`[]`) | [`backend/banking_crosswalk/policy.py:190`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L190) | Lacks regex token `"masked"`; only searches for `"collection notice"` or `"consent"`. | **Critical:** Specific APP 11 data protection probe for frontier LLMs discarded as irrelevant. |
| **QUEST-07** | *"Is independent model validation performed by personnel independent of model developers?"* | Valid Independence Probe (`CTRL-GOV-AUDITABILITY`, CPS 220) | Rejected (`[]`) | [`backend/banking_crosswalk/policy.py:185`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L185) | Pattern matches exact string `"independent review"`, but failed on separated syntax `"independent model validation performed by personnel independent..."`. | **High:** Core APRA CPS 220 structural independence verification question ignored. |
| **QUEST-09** | *"Has a formal operational risk and exit strategy assessment been conducted for the AI supplier under CPS 230?"* | Valid Third-Party Probe (`CTRL-TPS-VENDOR-ASSESSMENT`) | Rejected (`[]`) | [`backend/banking_crosswalk/policy.py:210`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L210) | Matches `"vendor"`, but question used `"AI supplier"`; phrase was not normalized. | **Critical:** APRA CPS 230 third-party provider due diligence question dropped. |
| **QUEST-10** | *"Can the automated system override a human manager's rejection?"* | Valid Override Probe (`CTRL-GOV-OVERSIGHT`, Human Supremacy) | Rejected (`[]`) | [`backend/banking_crosswalk/policy.py:180`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L180) | Negative inversion probe (*"override a human manager's rejection"*) completely outside regex dictionary scope. | **High:** Critical test of human supremacy over algorithmic decisions dropped. |
| **QUEST-12** | *"How often are algorithmic bias audits performed across protected attributes?"* | Valid Fairness Cadence Probe (`CTRL-FAIR-BIAS-EVALUATION`) | Rejected (`[]`) | [`backend/banking_crosswalk/policy.py:205`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L205) | Pattern requires `"bias testing"`; missed `"bias audits performed across protected attributes"`. | **Medium:** Cadence evaluation for anti-discrimination testing omitted. |
| **QUEST-14** | *"Are customer complaints involving AI decisions triaged within RG 271 maximum timeframes (30 days standard, 21 days financial hardship)?"* | Valid Dispute Probe (`CTRL-COMPL-DISPUTE-RESOLUTION`, ASIC RG 271) | Rejected (`[]`) | [`backend/banking_crosswalk/policy.py:195`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L195) | Pattern matches `"idr"` or `"dispute resolution"`; missed specific statutory phrase `"complaints... triaged within RG 271"`. | **High:** ASIC RG 271 statutory customer redress question missed. |

---

## 3. Scenario C — AI Use Case Coverage & Operational Evidence Accuracy

### 3.1 Scope & Governance Criteria
Reference Use Case: **Australian Banking AI Refund Agent**
- **Operational Facts:** Automated customer dispute and refund processing; human escalation threshold configured at **AUD 500**; integration with third-party frontier LLM provider.
- **Evaluation Principle:** Differentiate formally applicable statutory obligations from voluntary guidance; verify operational controls against enterprise policy thresholds; and **rigorously distinguish documented intentions from operational implementation evidence**.

### 3.2 Quantitative Accuracy Metrics & Execution Classification
- **Total Test Cases:** 12
- **Direct Production Execution (Applicability Rules, UC-01 to UC-07):**
  - **Evaluated Cases:** 7
  - **Correct Decisions:** 7 / 7 (**100.00%**)
  - **Precision:** 100.00% | **Recall:** 100.00% | **F1 Score:** 100.00%
  - **Scope:** Correctly evaluates structured statutory applicability flags (`apra_entity`, `privacy_personal_information`, `asic_idr`, `eu_ai_act_nexus`, `enterprise_delegated_authority`, etc.) via [`decide_applicability()`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/applicability.py).
- **Features Not Yet Implemented in Production / Unmeasurable (Telemetry & Evidence, UC-08 to UC-12):**
  - **Evaluated Cases:** 5
  - **Status:** **NOT YET MEASURABLE** as end-to-end production features.
  - **Scope:** Ingesting execution telemetry logs, verifying cryptographic evidence artifact hashes, detecting baseline threshold conflicts, verifying audit log retention schedules, and enforcing cloud data residency boundaries are not currently supported by [`BankingUseCase`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py) schemas or the crosswalk API.
  - **Architectural Risk:** Currently, intake text claims are accepted without evidence verification, presenting a direct false-coverage risk if relied upon in production.

### 3.3 Detailed Use Case Failure Cases

| Case ID | Use Case Fact / Evidence Artifact | Expected Assessment Outcome | Actual System Behavior | Code Path | Root Cause | Governance Consequence |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| **UC-08** | Use case intake form claims: *"The model is 100% fair and has zero disparate impact"* (no test script, no dataset artifact attached). | **DEFICIENT:** Evidence Missing; flag as unverified claim. | **FALSE COVERAGE:** Marked as covered because `"fair"` keyword was present in use-case text. | [`backend/banking_crosswalk/applicability.py:80`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/applicability.py#L80) | Engine does not verify whether evidence artifacts are linked or hashed; accepts text claim at face value. | **CRITICAL DEFECT:** Unsubstantiated fairness assertion accepted by audit engine as proof of compliance. |
| **UC-09** | Production audit telemetry logs confirm dual officer sign-off on 45 batch refund disbursements exceeding AUD 500. | **SATISFIED:** Operational evidence verified. | **IGNORED / NOT EVALUATED:** System cannot parse execution logs or verify operational telemetry. | [`backend/banking_crosswalk/api.py:445`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py#L445) | `BankingUseCase` model lacks ingestion fields or validation schemas for telemetry/log artifacts. | **High:** Actual operational proof of compliance cannot be recognized by the platform. |
| **UC-10** | Enterprise baseline policy requires human review at **AUD 500**; use case configuration payload specifies `approval_threshold_aud = 1000`. | **POLICY CONFLICT:** Severe conflict; automated disbursements between AUD 500 and AUD 1,000 violate internal policy. | **UNDETECTED:** System creates use case without alerting on baseline threshold breach. | [`backend/banking_crosswalk/api.py:445-455`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py#L445-L455) | `POST /v1/use-cases` does not compare the submitted use-case threshold against the tenant's `EnterpriseBaseline`. | **CRITICAL DEFECT:** Unauthorised disbursement risk; use case deploys with a threshold 2x higher than enterprise risk appetite. |
| **UC-11** | Use case architecture is documented in Confluence, but system configuration confirms event logs are deleted after 30 days (violating 7-year retention). | **EVIDENCE DEFICIENCY:** Retention failure under APRA CPS 234 and Privacy Act. | **UNDETECTED:** System marks observability as satisfied based on documentation link. | [`backend/banking_crosswalk/coverage.py:95`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py#L95) | Fails to distinguish documentation artifacts from system configuration parameters. | **High:** Non-compliant 30-day log purging ignored by assessment engine. |
| **UC-12** | Third-party cloud LLM API endpoint deployed in US East region without customer cross-border consent under APP 8. | **REGULATORY BREACH:** Breaches Privacy Act APP 8 cross-border disclosure provisions. | **NOT EVALUATED:** System does not perform territorial data sovereignty checks on model endpoints. | [`backend/banking_crosswalk/catalog.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/catalog.py) | Data residency attribute missing from `BankingUseCase` model schema. | **Critical:** Unlawful extraterritorial transfer of Australian customer banking data. |

---

## 4. Assessment Governance Principles: Boundaries & Non-Equivalences

To prevent legal and regulatory misrepresentations, the assessment engine must maintain three fundamental governance boundaries:

### 4.1 Boundary 1: Strategy-Level Coverage $\neq$ Implementation Evidence
- A strategy document (Scenario A) sets organizational intent, charters, and risk appetite.
- The engine must assess whether the strategy **commits to the required governance mechanisms** (e.g. board oversight, independent validation, ethical principles).
- **Prohibited Behavior:** The engine must never flag a strategy document as "non-compliant" simply because it does not attach operational evidence (such as encryption certificates or API test execution reports). Strategy documents are governance charters, not engineering manifests.

### 4.2 Boundary 2: Questionnaire Coverage $\neq$ Control Effectiveness
- An AI assessment questionnaire (Scenario B) evaluates whether an organization's pre-deployment intake process **asks the right questions**.
- Finding that a questionnaire contains a question regarding model drift does NOT prove that model drift is monitored in production.
- **Prohibited Behavior:** The engine must never generate a compliance certification stating that an AI use case is safe simply because the project team completed a questionnaire. Questionnaire coverage measures *inquiry completeness*, not *operational control effectiveness*.

### 4.3 Boundary 3: Use Case Description $\neq$ Operational Proof
- A use case intake form (Scenario C) contains descriptions authored by project developers.
- A developer's assertion that *"all data is anonymized"* is an unsubstantiated claim.
- **Prohibited Behavior:** The engine must strictly classify unverified text claims as `UNVERIFIED_CLAIM` and distinguish them from `VERIFIED_EVIDENCE` supported by cryptographic hashes, signed approval records, or audit telemetry.

---

## 5. Audit Conclusion

The assessment layer exhibits severe accuracy limitations:
1. **Low Recall in Strategy and Questionnaire Assessment (12.5% – 16.7%):** The deterministic regex engine fails to recognize questions and strategy statements unless they conform to rigid declarative sentences. This generates immense numbers of false gap alerts for well-governed institutions.
2. **Operational Evidence Blindspots (41.7% of Use Case Cases):** The system cannot ingest operational telemetry, cannot verify cryptographic evidence, and fails to detect direct numerical threshold conflicts between use-case configurations and enterprise baseline policies.
3. **False-Coverage Vulnerability:** The engine treats text claims on intake forms as satisfied controls, creating immediate regulatory exposure under APRA and ASIC supervision.

These verified empirical limitations provide conclusive, evidence-based justification for introducing **semantic retrieval and structured evidence verification** into the DeepAudit Crosswalk architecture.

---

## 6. Evaluation Methodology, Reproducibility & Identified Limitations

### 6.1 Four-Tier Execution Methodology Classification
To maintain absolute scientific and benchmark integrity, every measurement in this report is assigned to one of four rigorous execution classifications:

1. **Directly Executed Production Functionality:**
   - **Baseline Construction:** Evaluated by executing [`extract_enterprise_policy()`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) over 25 synthetic clauses. Directly measures regex extraction precision (53.85%), recall (38.89%), and F1 (45.16%).
   - **Use Case Statutory Applicability:** Evaluated by passing operational facts directly into [`decide_applicability()`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/applicability.py). Directly confirms 100% accuracy (7/7 cases) across APRA CPS 234/230, Privacy Act, ASIC RG 271, and EU AI Act extraterritoriality rules.
   - **Questionnaire Pipeline Coverage:** Evaluated by running [`evaluate_questionnaire_coverage()`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py) against standard question bank structures.

2. **Isolated Component Tests:**
   - **Questionnaire Facet Sensitivity (14 Cases):** Evaluates regex sensitivity on isolated question strings against [`ENTERPRISE_FACET_PATTERNS`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L180-L215). Demonstrates 100% precision (1/1) but extreme false-gap risk (recall = 12.50%, 7 false negatives) due to rigid syntactic phrasing expectations.

3. **Proxy-Based Measurements:**
   - **Strategy Coverage (12 Cases):** Because an end-to-end Strategy Assessment engine is **not yet implemented** in production, high-level governance commitments were evaluated through [`extract_enterprise_policy()`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) as a proxy. This measures whether the current regex facet dictionary recognizes executive governance vocabulary.
   - **Integrity Notice:** These proxy metrics (Precision: 50.00%, Recall: 16.67%, F1: 25.00%) measure dictionary coverage limitations and must **NOT** be reported as final end-to-end product assessment accuracy. True end-to-end strategy evaluation accuracy is **not yet measurable**.

4. **Features Not Yet Implemented or Testable (Unmeasurable):**
   - **Operational Telemetry & Cryptographic Verification (Cases UC-08 through UC-12):** Features including telemetry log ingestion, cryptographic evidence hash validation, numerical baseline threshold conflict detection, 7-year log retention audit, and cloud data sovereignty enforcement do not currently exist in [`BankingUseCase`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py) schemas or crosswalk endpoints. These metrics are formally recorded as **Not Yet Measurable** and are designated for implementation in roadmap items P0-6 and P2-1.

### 6.2 Ground Truth Provenance
The evaluation dataset [`MAPPING_EVALUATION_DATASET.json`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/MAPPING_EVALUATION_DATASET.json) comprises 63 total test cases categorized with strict provenance tracking:
- **Human-Verified Cases: 0 Cases.** No external independent human expert review panel (e.g. external regulatory counsel or accredited GRC audit committee) has yet formally signed off on review records for this benchmark suite.
- **Synthetic Reference Cases Pending Expert Review: 61 Cases.** Carefully synthesized operational reference test cases reflecting Australian banking governance practices and binding statutory instruments (APRA CPS 234, CPS 230, CPS 220, Privacy Act 1988 APPs, and ASIC RG 271).
- **Ambiguous Legal Cases: 2 Cases.** Edge cases involving disputed legal interpretations of de minimis compliance exemptions and regional data sovereignty thresholds requiring formal legal counsel.

### 6.3 Component-Level False-Control Trigger Rate vs Downstream Assessment False Coverage
A critical finding of this audit is the **12.0% false-control trigger rate** (3 / 25 cases) observed during baseline construction:
- **Exact Denominator:** Strictly 25 baseline construction policy clauses ($3 / 25 = 12.0\%$).
  - `BASE-12`: Standalone sandbox exemption erroneously triggered candidate mappings for `CTRL-FIN-APPROVAL-THRESHOLDS` and `CTRL-GOV-OVERSIGHT`.
  - `BASE-13`: Explicit prohibition on using production PII for ad-hoc bias testing erroneously triggered candidate mapping for `CTRL-FAIR-BIAS-DETECTION`.
  - `BASE-24`: First Nations cultural data sovereignty protocol erroneously triggered candidate mapping for `CTRL-PRIV-CROSS-BORDER`.
- **Component-Level Nature:** This metric measures a **candidate extraction defect** in [`extract_enterprise_policy()`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) where negated sentences or unrepresented requirements trigger regex keywords.
- **Role of Human-in-the-Loop Validation:** In the production workflow, baseline extraction outputs candidate mappings with `review_status = ClauseReviewStatus.PROPOSED`. A human compliance officer must review and approve each candidate before the baseline is published (`ClauseReviewStatus.APPROVED`). Consequently, this 12.0% component-level noise rate represents an ingestion review burden for human compliance officers, but is **mitigated by mandatory human review before baseline approval**.
- **Distinction from Downstream False-Coverage:** A downstream assessment false-coverage error (e.g., UC-08, where an intake claim of "100% fair" is accepted without evidence) represents a direct, unmitigated regulatory breach risk if an AI system deploys with undetected non-compliance.

### 6.4 Reproducibility
All 63 test cases and their empirical metrics can be independently reproduced at any time via:
```bash
python scripts/evaluate_semantic_mapping.py
```

### 6.5 Dual-Mode Architecture Alignment
In accordance with [`ADR_OPTIONAL_ENTERPRISE_BASELINE.md`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/ADR_OPTIONAL_ENTERPRISE_BASELINE.md), all three target types (Strategy, Questionnaire, Use Case) can be evaluated in **Mode A (Regulatory-Only)** without requiring an Enterprise Baseline, or in **Mode B (Enterprise-Enhanced)** when a customer-specific baseline has been approved.

