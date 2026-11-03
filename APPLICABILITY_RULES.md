# Australian Banking AI Governance — Applicability Rules & Scope Specification

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Engine Module:** [`backend/banking_crosswalk/applicability.py`](file:///c:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/applicability.py)  
**Domain Model:** [`BankingUseCase`](file:///c:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py#L289-L420)  

---

## 1. Design Principles

1. **Four-State Deterministic Evaluation:** Every obligation evaluates deterministically to one of four states:
   - `applicable`: All statutory, regulatory, or adoption preconditions are met as of `use_case.as_of_date`.
   - `not_applicable`: At least one mandatory precondition is explicitly false (e.g. no EU territorial nexus, no personal information processed, or voluntary framework not adopted).
   - `conditional`: A threshold indicator is present, a provision is future-dated relative to `as_of_date` (e.g. `APP 1.7–1.9` prior to `2026-12-10`), an assessment scope mismatch exists (`organisation` obligation vs `use_case` questionnaire), or legal interpretation of a nexus test is required.
   - `undetermined`: Critical intake attributes are `None` / unknown and no safe default applies.
2. **Enterprise Baseline Mode (No Use-Case Intake Required):**
   - Both `evaluate_questionnaire_coverage()` and `assess_policy_gaps()` accept `use_case=None` and automatically instantiate [`BankingUseCase.enterprise_baseline()`](file:///c:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py#L347-L382).
   - This enables enterprise-wide questionnaire validation and policy gap detection for an Australian Authorised Deposit-taking Institution (`ADI` / `AFSL` / `ACL`) without forcing users to complete a per-use-case intake first.
   - Even in enterprise baseline mode, the **EU AI Act (`EU-AI-ACT`) defaults to `not_applicable`** unless an EU establishment, EU market placement, or EU output use is explicitly indicated.
3. **Strict Authority Layer Separation:**
   - Coverage metrics (`metrics.by_authority_layer`) and policy gaps (`gaps_by_authority_layer`) maintain separate buckets for:
     - `binding_regulatory` (`binding` and `enforceable_guidance`)
     - `regulatory_guidance` (`guidance`)
     - `voluntary_frameworks` (`voluntary`)
     - `enterprise_internal_controls` (`enterprise`)

---

## 2. Rule Catalogue (`RULES` in `applicability.py`)

| Rule Key (`applicability_key`) | Associated Obligations | `applicable` Condition | `not_applicable` Condition | `conditional` / `undetermined` Condition |
|---|---|---|---|---|
| `privacy_personal_information` | `AU-PRIV-APP1-GOV`, `AU-PRIV-APP3-COLLECT`, `AU-PRIV-APP5-NOTICE`, `AU-PRIV-APP6-USE`, `AU-PRIV-APP10-QUALITY`, `AU-PRIV-APP11-SECURITY`, `AU-PRIV-APP12-13-RIGHTS`, `AU-PRIV-NDB-S26WE`, `AU-OAIC-APPG-CH1-PIA`, `AU-OAIC-APPG-CH6-CH10-INF` | `handles_personal_information == True` or `handles_sensitive_information == True` | `handles_personal_information == False` and `handles_sensitive_information is not True` | `undetermined` when both are `None` |
| `privacy_automated_decision_future` | `AU-PRIV-APP1.7-AUTOMATED` | Personal information is handled, `makes_or_assists_significant_decisions == True`, and `as_of_date >= 2026-12-10` | `handles_personal_information == False` or `makes_or_assists_significant_decisions == False` | `conditional` when `as_of_date < 2026-12-10` (statutory commencement under `C2024A00128` Sch 1 Pt 15 is 10 Dec 2026); `undetermined` when decision significance is `None` |
| `privacy_cross_border` | `AU-PRIV-APP8-CROSSBORDER` | Personal information is handled and `cross_border_disclosure == True` | Personal information is not handled or `cross_border_disclosure == False` | `conditional` when `third_party_ai_service == True` and `cross_border_disclosure is None` (must verify offshore inference/subprocessors under APP 8); otherwise `undetermined` |
| `apra_entity` | `AU-APRA-CPS220-RMF`, `AU-APRA-CPS220-REVIEW`, `AU-APRA-CPS230-OPS`, `AU-APRA-CPS234-ROLES-ASSETS`, `AU-APRA-CPS234-CAPABILITY`, `AU-APRA-CPS234-TEST`, `AU-APRA-CPS234-INCIDENT`, `AU-APRA-CPG235-DATA`, `AU-APRA-CPG235-LINEAGE` | `apra_regulated == True` or `entity_type.upper() == "ADI"` | `apra_regulated == False` | `undetermined` when `apra_regulated is None` and `entity_type != "ADI"` |
| `apra_critical_operation` | `AU-APRA-CPS230-BCP` | Entity is APRA-regulated and `supports_critical_operation == True` | Entity is not APRA-regulated or `supports_critical_operation == False` | `undetermined` when `supports_critical_operation is None` |
| `apra_third_party_service` | `AU-APRA-CPS230-SP`, `AU-APRA-CPS230-NOTIFY` | Entity is APRA-regulated, `third_party_ai_service == True`, and `material_service_provider == True` | Entity is not APRA-regulated or `third_party_ai_service == False` | `conditional` when `third_party_ai_service == True` and `material_service_provider in {False, None}` (CPS 230 materiality and fourth-party/offshoring triggers require assessment) |
| `asic_idr` | `AU-ASIC-RG271-COMPLAINT`, `AU-ASIC-RG271-SYSTEMIC`, `AU-ASIC-REP798-GOV` | `handles_regulated_complaints == True` or `idr_obligations == True` | `handles_regulated_complaints == False` and `idr_obligations == False` | `conditional` when `makes_or_assists_significant_decisions == True` (customer-affecting decisions can generate IDR complaints); otherwise `undetermined` |
| `asic_afs_licensee` | `AU-ASIC-RG104-COMPLIANCE`, `AU-ASIC-RG104-RESOURCES`, `AU-ASIC-RG105-COMPETENCE` | `afs_licensee == True` | `afs_licensee == False` | `conditional` when `apra_regulated == True` or `entity_type == "ADI"` and `afs_licensee is None` |
| `nccp_credit_activity` | `AU-NCCP-S47-CONDUCT` | `credit_licensee_or_credit_activity == True` | `credit_licensee_or_credit_activity == False` | `conditional` when `entity_type == "ADI"` or `apra_regulated == True` and `credit_licensee_or_credit_activity is None` |
| `nccp_responsible_lending` | `AU-NCCP-S128-131-LENDING` | `credit_licensee_or_credit_activity == True` and `assists_consumer_credit_decision == True` | `credit_licensee_or_credit_activity == False` or `assists_consumer_credit_decision == False` | `conditional` when `credit_licensee_or_credit_activity == True` and `makes_or_assists_significant_decisions == True` with `assists_consumer_credit_decision is None` |
| `au_ai_guidance_adopted` | `AU-NAIC-AI6-ACCOUNTABILITY-IMPACT`, `AU-NAIC-AI6-RISK-TRANSPARENCY`, `AU-NAIC-AI6-TEST-HUMAN` | `au_ai_guidance_adopted == True` | `au_ai_guidance_adopted == False` | `undetermined` when `au_ai_guidance_adopted is None` |
| `eu_ai_act_nexus` | `EU-AIA-ART2-HIGH-RISK` | Never auto-applicable without human legal review; evaluates to `conditional` when EU nexus is true and `as_of_date >= effective_from` | `eu_establishment_or_market == False` and `eu_output_used == False` | `conditional` when `eu_establishment_or_market == True` or `eu_output_used == True` (requires Legal confirmation of Art 2 nexus, operator role, and Annex III classification) |
| `eu_ai_act_prohibited_or_literacy` | `EU-AIA-ART4-5-PROHIBITED-LITERACY` | `conditional` when EU Article 2 nexus is indicated (Chapters I & II commenced `2025-02-02`) | `eu_establishment_or_market == False` and `eu_output_used == False` | `conditional` when EU nexus is true; `undetermined` when EU nexus flags are `None` |
| `eu_ai_act_deployer_high_risk` | `EU-AIA-ART26-27-DEPLOYER-CREDIT` | `conditional` when EU Article 2 nexus is indicated and `eu_operator_role != "none"` | No EU nexus or `eu_operator_role == "none"` | `conditional` when EU nexus is indicated (requires Annex III point 5(b) creditworthiness vs fraud-detection carve-out confirmation) |
| `nist_adopted` | `NIST-AI-RMF-GMMM`, `NIST-AI-RMF-GOVERN-MAP`, `NIST-AI-RMF-MEASURE-MANAGE` | `nist_ai_rmf_adopted == True` | `nist_ai_rmf_adopted == False` | `undetermined` when `nist_ai_rmf_adopted is None` |
| `iso42001_adopted` | `ISO42001-AIMS-ORG`, `ISO42001-IMPACT-LIFECYCLE` | `iso_42001_adopted == True` and scope compatible | `iso_42001_adopted == False` | `conditional` when `obligation.assessment_scope == "organisation"` and `use_case.assessment_scope != "organisation"` |
| `iso23894_adopted` | `ISO23894-AI-RISK-PROCESS` | `iso_23894_adopted == True` | `iso_23894_adopted == False` | `conditional` when `iso_42001_adopted == True` and `iso_23894_adopted is None` |
| `iso27001_adopted` | `ISO27001-ISMS-CONTROLS` | `iso_27001_adopted == True` and `use_case.assessment_scope == "organisation"` | `iso_27001_adopted == False` | `conditional` when `iso_27001_adopted == True` and `use_case.assessment_scope != "organisation"` |
| `enterprise_delegated_authority` | `ENT-AI-DELEGATED-APPROVAL` | `enterprise_controls_enabled == True` or `approval_threshold_aud is not None` | `enterprise_controls_enabled == False` | `conditional` when both are `None` |

---

## 3. EU AI Act Territorial Scope, Operator Roles & Phased Effective Dates

For an Australian bank, Regulation (EU) 2024/1689 is **foreign law** and never applies by default. Applicability requires satisfying all four cumulative tests:

1. **Territorial Nexus (Article 2(1)):**
   - **Art 2(1)(a):** The bank places on the market or puts into service an AI system in the European Union; OR
   - **Art 2(1)(b):** The bank is a deployer that has its place of establishment or is located within the EU; OR
   - **Art 2(1)(c):** The bank is a provider or deployer established in a third country (Australia), **where the output produced by the AI system is used in the Union**.
2. **Operator Role (Article 3):**
   - `provider` (Art 3(3)): Develops an AI system or has it developed and places it on the market or puts it into service under its own name/trademark (or substantially modifies a high-risk AI system under Art 25).
   - `deployer` (Art 3(4)): Uses an AI system under its authority in the course of a professional banking activity.
   - `importer` / `distributor` (Art 3(6)–(7)).
3. **Risk Tier & Banking Carve-Out (Article 6 & Annex III point 5(b)):**
   - **High-Risk (Annex III point 5(b)):** AI systems intended to be used to evaluate the **creditworthiness of natural persons or establish their credit score**, **with the exception of AI systems used for the purpose of detecting financial fraud**.
   - **Prohibited Practices (Article 5):** Social scoring, subliminal manipulation, exploitation of vulnerabilities, untargeted facial scraping, emotion recognition in the workplace/education.
   - **Transparency (Article 50):** Customer-facing chatbots/agents and synthetic content generation.
4. **Phased Commencement Timeline (Article 113):**
   - **1 August 2024:** Entry into force.
   - **2 February 2025:** Chapters I & II apply (`Article 4` AI literacy and `Article 5` prohibited AI practices).
   - **2 August 2025:** Chapter III Section 4 (notifying authorities), Chapter V (GPAI models), Chapter VII (governance), and Chapter XII (penalties, excluding Art 101) apply.
   - **2 August 2026:** General application date (`Articles 6(2), 9–15, 26, 27, 50` and `Annex III` high-risk AI systems, including creditworthiness AI).
   - **2 August 2027:** Article 6(1) and Annex I regulated product safety high-risk AI systems apply.

