# Enterprise Regulatory & Policy Layer — Gap Analysis & Acceptance Test Suite

**Product**: DeepAuditCrossWalk  
**Date**: November 2026  
**Status**: Technical Gap Specification & Test Plan  

---

## 1. Traceability & Gap Matrix

| # | Enterprise Capability Requirement | Current Status | Current Code Limitation | Proposed Target Resolution | Test Scenario |
|---|---|---|---|---|---|
| 1 | **Full Control Coverage Detection** | Partially Implemented | Token overlap against obligation facets in `policy.py`; ignores Unified Controls. | Evaluate confirmed mappings: `EnterpriseClause → UnifiedControl (full)`. | Test 1 |
| 2 | **Partial Control Coverage Detection** | Partially Implemented | Emits general gap; does not pinpoint missing sub-facets against Unified Controls. | Crosswalk compares clause facets against `UnifiedControl.facets`, listing exact missing facets. | Test 2 |
| 3 | **Questionnaire Omits Enterprise Control** | Fully Implemented (Basic) | Works only for 3 generic facets in `_questionnaire_covers_generic_facet()`. | Generalize to test any approved mandatory enterprise clause mapped to a `CTRL-*` control. | Test 3 |
| 4 | **Enterprise Policy Exceeds Regulation** | Not Implemented | System only treats non-regulatory clauses as untested; cannot report "Positive Over-Compliance". | Tag enterprise clauses where authority is `ENTERPRISE` and requirement is stricter than statute as "Elevated Enterprise Standard". | Test 4 |
| 5 | **Conflicting Policy Approval Thresholds** | Fully Implemented | Detects multiple numeric AUD thresholds in `assess_policy_gaps()`. | Extend conflict detector to cover non-numeric approval hierarchies and conflicting jurisdiction rules. | Test 5 |
| 6 | **Authority Level Misclassification** | Not Implemented | Flattens all extracted text into boolean `mandatory`; no concept of guidance vs statute. | Enforce 6-tier `authority_level` enum; prevent voluntary frameworks from emitting "Critical Legal Gap". | Test 6 |
| 7 | **Superseded Regulatory Ingestion** | Not Implemented | File version is an unvalidated string (`version="unversioned"`). | Check uploaded instrument against effective dates in `REGULATORY_SOURCE_REGISTER.csv`; flag superseded versions. | Test 7 |
| 8 | **Duplicate Upload of Shared Regulation** | Not Implemented | Re-imports duplicate regulations as unverified private policy packs. | Pre-ingestion SHA-256 and title match; offer link to shared standard. | Test 8 |
| 9 | **Incorrect Mapping to Unrelated Control** | Not Implemented | No validation of semantic distance or reviewer role when mapping. | Semantic coherence scoring threshold (<0.40 flags warning) + mandatory human confirmation. | Test 9 |
| 10 | **Multi-Tenant Complete Isolation** | Partially Implemented | Tenant ID is accepted from raw HTTP header without token verification. | Enforce JWT tenant claim validation in FastAPI dependencies and PostgreSQL RLS. | Test 10 |

---

## 2. Acceptance Test Suite Specification

### Current Working Baseline Tests vs. Proposed Enterprise Tests

- **Existing Tests in Repo** (`backend/tests/`):
  - `test_standalone.py`: Validates deterministic extraction and injection warnings for single text snippets.
  - `test_repository.py`: Validates in-memory store isolation by `tenant_id` string for single policy packs.
  - `test_regulatory_library.py`: Validates static JSON catalog integrity (33 controls, 57 mappings).
  - *Limitation*: None of the existing tests test multi-document baselines, Unified Control mapping for policies, or JWT authentication.

---

### Proposed Acceptance Test Definitions (`tests/test_enterprise_policy_layer.py`)

#### Test 1: Enterprise Policy Fully Covers Required External Control
- **Input**: User uploads `AU_Privacy_Standard.pdf` containing clause: *"Customer consent must be recorded prior to collecting sensitive biometrics, and stored encrypted with AES-256."*
- **Mapping**: Mapped to `CTRL-PRIV-COLLECTION` (facets: `[consent_prior, encryption_at_rest]`).
- **Assertion**:
  - `gap_type == POLICY` is NOT generated for `AU-PRIV-APP3-COLLECT`.
  - Coverage status for `CTRL-PRIV-COLLECTION` reports `CoverageStatus.CONFIRMED`.

#### Test 2: Enterprise Policy Partially Covers a Control
- **Input**: User uploads `AI_Ethics_Draft.docx` with: *"AI decisions shall be monitored by operational teams."*
- **Mapping**: Mapped to `CTRL-GOV-OVERSIGHT` (facets: `[human_in_loop, logging_audit, contestability_mechanism]`).
- **Assertion**:
  - Emits `GapRecord` with `gap_type = GapType.POLICY`.
  - `missing_facets` contains `["contestability_mechanism", "logging_audit"]`.
  - Severity marked as `medium`.

#### Test 3: Questionnaire Omits a Mandatory Enterprise Control
- **Input**: Enterprise baseline has confirmed policy clause: *"All AI vendor contracts must enforce Zero Data Retention (ZDR) on prompt history."* Questionnaire bank tests model accuracy and uptime, but contains no vendor data retention question.
- **Assertion**:
  - Emits `GapRecord` with `gap_type = GapType.QUESTIONNAIRE`.
  - Title: *"Questionnaire does not test mandatory enterprise policy: Zero Data Retention"*.
  - Severity: `high`.

#### Test 4: Enterprise Policy Exceeds Regulatory Minimum
- **Input**: Regulatory obligation (APRA CPS 230) requires operational resilience reviews every 12 months. Enterprise Cyber Policy mandates reviews every 3 months.
- **Assertion**:
  - Crosswalk acknowledges regulatory requirement is fully satisfied.
  - System flags *"Elevated Enterprise Requirement: 3-month review cadence exceeds regulatory baseline (12 months)"*.
  - Questionnaire testing must enforce the 3-month cadence.

#### Test 5: Conflicting Policy Thresholds Across Two Documents
- **Input**: Multi-document baseline includes:
  - Doc 1 (`Retail_Credit_Policy.pdf`): *"Automated adjustments over AUD $1,000 require Team Lead sign-off."*
  - Doc 2 (`AI_Delegated_Authority.pdf`): *"All automated write-offs over AUD $500 require Executive Director sign-off."*
- **Assertion**:
  - Crosswalk generates `GapType.CONTROL_CONFLICT`.
  - Title: *"Enterprise policies contain conflicting AUD approval thresholds"*.
  - `observed_thresholds == [500.0, 1000.0]`. Severity: `critical`.

#### Test 6: Voluntary Framework Correctly Classified
- **Input**: User ingests NIST AI RMF 1.0 guidelines.
- **Classification**: `authority_level = Authority.INDUSTRY_FRAMEWORK`.
- **Assertion**:
  - Unmapped or omitted NIST recommendations generate `gap_type = GapType.ADVISORY_GAP` with `severity = "low"`.
  - System does NOT generate a statutory violation or legal breach warning.

#### Test 7: Upload of Superseded Regulatory Document
- **Input**: User uploads outdated `APRA CPG 234 (2019)` when current baseline is updated.
- **Assertion**:
  - Pre-ingestion validation inspects instrument ID and date.
  - Returns `422 Unprocessable Entity` or warning: *"The uploaded instrument APRA CPG 234 (2019) is superseded by CPS 234 (2024). Recommended action: Use active Shared Library entry."*

#### Test 8: Upload of Regulation Already Present in Shared Library
- **Input**: User uploads raw text of *Privacy Act 1988 (Cth)*.
- **Assertion**:
  - Engine detects matching SHA-256 fingerprint with `AU-PRIVACY-ACT-1988` in Shared Library.
  - Response prompts linking to the canonical shared catalogue rather than duplicating private records.
  - Upload is NOT written to global shared catalogue.

#### Test 9: Incorrect Semantic Mapping Rejected or Flagged
- **Input**: Attempt to map a clause on *"Data Center physical fire extinguisher checks"* to `CTRL-AI-BIAS-FAIRNESS`.
- **Assertion**:
  - Cosine/token similarity score < 0.15.
  - API returns `relationship = "not_equivalent"` and rejects automatic mapping, requiring explicit manual SME override with required audit justification.

#### Test 10: Multi-Tenant Complete Cryptographic Isolation
- **Setup**:
  - Tenant A uploads `Confidential_Core_IP_Policy.pdf`.
  - Tenant B authenticates with separate JWT token.
- **Direct Attack Test**:
  - Tenant B executes `GET /v1/enterprise/policies/{tenant_a_policy_id}` and `GET /v1/enterprise/clauses?tenant_id=tenant-a`.
- **Assertion**:
  - Server returns `404 Not Found` (or `403 Forbidden`).
  - Database query executed with Tenant B's context yields 0 rows due to SQL filtering and RLS.

