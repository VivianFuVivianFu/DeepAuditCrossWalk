# DeepAudit Crosswalk — Prioritised Accuracy & Reliability Roadmap

**Document Status:** Approved Architecture & Remediation Plan  
**Date:** 2026-11-04  
**Audit Scope:** Engineering Remediation Plan for Architectural Realignment and Accuracy Enhancement  
**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Git Baseline Commit:** `d57eeaa5f12590931dd9378577554dc4b48d5fdd`  
**Branch:** `audit/semantic-mapping-reliability`  

---

## Executive Summary

Based on empirical evidence and critical product architecture clarification, this roadmap establishes a sequenced, controlled engineering plan for **DeepAudit Crosswalk**. 

### Foundational Product Principle: Optional Enterprise Policy Layer
DeepAudit Crosswalk supports **two independent assessment modes**:
1. **Scenario A — Regulatory-Only Assessment (Default):** Direct evaluation of an AI Governance Strategy, Questionnaire, or AI Use Case against the Shared Regulatory Library and Unified Controls. **No enterprise policy upload or baseline configuration is required.**
2. **Scenario B — Enterprise-Enhanced Assessment (Optional):** An organization optionally uploads internal policies to construct an approved, versioned **Enterprise Baseline**. The assessment target is then evaluated against the combined external-plus-internal baseline, producing a unified report distinguishing statutory vs enterprise gaps.

The Enterprise Policy Layer **extends** the applicable baseline; it never replaces the Shared Regulatory Library. Internal policies are **baseline-building inputs**, never downstream assessment targets.

---

## 1. Product Architecture: Two Assessment Scenarios & Resolution Logic

### 1.1 Scenario A — Regulatory-Only Assessment (Default Workflow)
- **User Journey:** A user directly submits an assessment document (Strategy, Questionnaire, or Use Case) without uploading internal policies.
- **Workflow:**
  1. System receives assessment target.
  2. Resolves applicable external statutory obligations from the Shared Regulatory Library (APRA CPS 234/230/220, ASIC RG 271, Privacy Act APPs).
  3. Resolves corresponding Unified Controls (`CTRL-*`) and required control facets.
  4. Evaluates assessment target against applicable requirements.
  5. Produces an evidence-backed **Regulatory Coverage Gap Report**.
- **Constraint:** Zero dependency on `EnterpriseBaseline` or `EnterprisePolicy`.

### 1.2 Scenario B — Enterprise-Enhanced Assessment (Optional Workflow)
- **User Journey:** An organization uploads internal policies (e.g. AI Governance Standard, Refund Delegations Policy) to establish a tenant-specific baseline.
- **Workflow:**
  1. Ingests internal policies, extracts clauses, and generates candidate mappings to Unified Controls (`pending_review`).
  2. Preserves enterprise-specific requirements that exceed or differ from regulatory minimums.
  3. Human compliance reviewer approves mappings.
  4. Tenant establishes an active, versioned `EnterpriseBaseline`.
  5. Downstream target (Strategy, Questionnaire, Use Case) is submitted referencing the baseline.
  6. System resolves applicable external statutory obligations **plus** applicable enterprise-specific requirements.
  7. Evaluates target against the combined baseline.
  8. Produces a **Combined Regulatory + Enterprise Coverage Gap Report**.

### 1.3 Baseline Resolution Logic Matrix

```
┌──────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────┐
│ Requested assessment_mode            │ System Behavior & Validation Rules                                      │
├──────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
│ regulatory_only (Default)            │ • Uses Shared Regulatory Library & Unified Controls.                     │
│                                      │ • Ignores/omits enterprise policies even if tenant has baselines.       │
│                                      │ • Never requires enterprise_baseline_id.                                │
│                                      │ • Produces Regulatory Coverage Gap Report.                               │
├──────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
│ enterprise_enhanced                  │ • Requires explicit, valid, active enterprise_baseline_id.              │
│                                      │ • Loads approved tenant-owned Enterprise Baseline.                      │
│                                      │ • Evaluates combined regulatory + enterprise requirements.               │
│                                      │ • Missing, unapproved, or cross-tenant baseline -> HTTP 400 / 404 Error! │
│                                      │ • NEVER silently falls back to regulatory_only mode.                    │
└──────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Report Provenance & Output Integrity

Every generated assessment report must strictly identify:
- **`assessment_mode`**: `"regulatory_only"` vs `"enterprise_enhanced"`.
- **`assessment_target_type`**: `"questionnaire"`, `"strategy"`, or `"use_case"`.
- **`regulatory_pack_version`**: Platform-maintained external obligations version.
- **`unified_control_library_version`**: Platform Unified Control Library version.
- **`enterprise_baseline_id` & `revision`**: Included if and only if mode is `enterprise_enhanced`.
- **`mapping_review_status`**: Identifies whether mappings are `confirmed` (approved) or `provisional` (candidate).
- **Distinguishable Gap Classifications**:
  - `binding_regulatory`: Mandatory statutory obligations (APRA, Privacy Act, ASIC).
  - `regulatory_guidance`: Non-binding statutory guidance.
  - `voluntary_frameworks`: Industry standards (AIAF, ISO 42001).
  - `enterprise_internal_controls`: Tenant-specific policy requirements.
- **Legal Safeguard:** The report must never label an assessment gap as confirmed legal non-compliance or breach of law.

---

## 3. Priority Tier P0 — Critical Architecture & Safety Blockers

> [!IMPORTANT]
> **Beta Go/No-Go Blocker:** These items must be completed and verified before any external enterprise pilot or beta deployment.

| Task ID | Item Name | Severity & Scope | Target Files / Components | Expected Outcome & Verification Metric |
| :---: | :--- | :--- | :--- | :--- |
| **P0-1** | **Preserve Regulatory-Only Assessment as Default** | **Core Architecture** | [`backend/banking_crosswalk/models.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py), [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py) | Establish `regulatory_only` as the default assessment mode. Enable new tenants with zero uploaded policies to execute full crosswalk assessments against the Shared Regulatory Library and Unified Controls without requiring policy upload or baseline configuration. |
| **P0-2** | **Separate Enterprise Baseline Construction from Downstream Assessment** | **Critical Architecture Defect** | [`backend/banking_crosswalk/policy.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py), [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py) | Decommission premature statutory gap generation during internal policy ingestion. Policies are strictly baseline-building inputs (Layer 2). Ingesting a single-domain policy (e.g. payment refunds) must **never** assert non-compliance against unrelated external statutes (e.g. APRA CPS 234 encryption). Statutory gaps are evaluated only on downstream targets. |
| **P0-3** | **Implement Tenant-Isolated Baseline Review, Approval and Versioning** | **Governance Integrity** | [`backend/banking_crosswalk/store.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/store.py), [`backend/banking_crosswalk/models.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py) | Enforce that only clauses and mappings with `review_status == ClauseReviewStatus.approved` contribute to confirmed baseline coverage. Candidate mappings (`pending_review`) remain quarantined from active baselines until signed off by an authorized compliance officer. Enforce strict PostgreSQL RLS tenant boundaries. |
| **P0-4** | **Implement Optional Baseline Resolution for Enterprise-Enhanced Assessments** | **Core Architecture** | [`backend/banking_crosswalk/coverage.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py), [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py) | When `assessment_mode = "enterprise_enhanced"`, resolve the combined external-plus-internal baseline using the explicitly selected, active `enterprise_baseline_id`. If the baseline is missing, inactive, unapproved, or belongs to another tenant, **fail closed with an explicit HTTP 400 or HTTP 404 error** (never silent fallback). |
| **P0-5** | **Prevent False Coverage: Negation, Conditionality and Unsupported Claims** | **Critical Compliance Hazard** | [`backend/banking_crosswalk/policy.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) | Implement deterministic negation pre-filtering (*"does not require"*, *"is exempt from"*, *"are prohibited from"*) to eliminate false control coverage (eliminating the 12% false-coverage defect rate measured on `BASE-12`, `BASE-13`, `BASE-24`). Distinguish unverified developer claims on intake forms from verified implementation evidence. |
| **P0-6** | **Validate Numeric Thresholds and Enterprise Control Conflicts** | **Safety Defect** | [`backend/banking_crosswalk/coverage.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py), [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py) | Compare submitted use case execution thresholds (e.g. AI Refund Agent AUD 1,000) directly against the tenant's approved baseline policy threshold (AUD 500). Automatically generate a **Critical Severity Conflict Gap** when an operational deployment exceeds the enterprise risk appetite. |
| **P0-7** | **Preserve Evidence Traceability, Assessment Provenance and Reproducibility** | **Audit Defensibility** | [`backend/banking_crosswalk/models.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py), [`backend/banking_crosswalk/api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py) | Record full provenance metadata on every report: `assessment_mode`, `assessment_target_type`, `regulatory_pack_version`, `unified_control_library_version`, `enterprise_baseline_id` & `revision`, and mandatory legal disclaimers. Ensure historical reports retain exact point-in-time baseline revisions. |

---

## 4. Priority Tier P1 — Semantic Accuracy & Review Workflow

> [!NOTE]
> **Core Commercial Enablement:** Required to achieve acceptable product usability, reduce false-negative alerts, and automate compliance review cycles.

| Task ID | Item Name | Severity & Scope | Target Files / Components | Expected Outcome & Verification Metric |
| :---: | :--- | :--- | :--- | :--- |
| **P1-1** | **Integrate Hybrid Semantic Retrieval (`pgvector`)** | **Core Mapping Accuracy** | `backend/banking_crosswalk/semantic.py`, PostgreSQL Schema | Enable `pgvector` in PostgreSQL. Compute dense vector embeddings for Unified Controls and policy clauses using an Australian sovereign/local embedding model. Elevate candidate mapping recall from **38.89%** to $\ge \mathbf{85.0\%}$. |
| **P1-2** | **Implement Human Review Gating UI in Web Console** | **Usability & Auditability** | `web/app/enterprise/clauses/`, `web/components/` | Provide an interactive review screen for compliance officers to inspect extracted clauses, review machine candidate mappings, view confidence scores and citations, and click to `Approve`, `Reject`, or `Reassign` controls. |
| **P1-3** | **Multi-Policy Internal Conflict & Threshold Detector** | **GRC Intelligence** | `backend/banking_crosswalk/conflict.py` | Scan across multiple uploaded internal policies to detect cross-document contradictions (e.g. Risk Policy sets AUD 1,000 threshold while Operations Policy sets AUD 250; or Retention Policy sets 7 years while AI Logging Standard sets 30 days). |
| **P1-4** | **Dedicated AI Strategy Assessment Target (Scenario A/B)** | **Product Feature** | `backend/banking_crosswalk/strategy.py`, `POST /v1/assessments/strategy` | Implement a dedicated assessment module tailored for high-level strategy documents. Evaluates executive governance structures, board accountability, and ethical commitments without demanding operational implementation evidence. |
| **P1-5** | **Contextual Questionnaire Inquiry Parser** | **Product Feature** | `backend/banking_crosswalk/coverage.py`, `POST /v1/assessments/questionnaires` | Replace rigid regex checking with interrogative question parsing. Accurately map inquiry syntax (*"Does the committee approve..."*) to required control facets, lifting questionnaire assessment recall from **12.50%** to $\ge \mathbf{80.0\%}$. |

---

## 5. Priority Tier P2 — Operational Evidence & Enterprise Scale

> [!TIP]
> **Scale & Enterprise Maturity:** Focuses on real-time continuous assurance, telemetry ingestion, and specialized governance frameworks.

| Task ID | Item Name | Severity & Scope | Target Files / Components | Expected Outcome & Verification Metric |
| :---: | :--- | :--- | :--- | :--- |
| **P2-1** | **Operational Telemetry & Log Ingestion Connectors** | **Continuous Assurance** | `backend/banking_crosswalk/telemetry.py`, `POST /v1/use-cases/{id}/telemetry` | Ingest structured execution logs (e.g. OpenTelemetry traces, Splunk audit logs) to prove that high-value disbursements (e.g. > AUD 500) actually underwent human sign-off in production before payment release. |
| **P2-2** | **Evidence Artifact Cryptographic Verification** | **Audit Defense** | `backend/banking_crosswalk/evidence.py` | Store SHA-256 hashes of attached compliance artifacts (model validation reports, PIA sign-offs, penetration test certificates) to distinguish verified operational evidence from unsubstantiated text claims. |
| **P2-3** | **Automated Policy Remediation Recommendation Generator** | **User Productivity** | `backend/banking_crosswalk/remediation.py` | For verified downstream gaps, generate drafted policy amendments and sample questionnaire questions adhering to Australian banking standards for compliance officer review and adoption. |
| **P2-4** | **Specialized Cultural & Regional Governance Ontologies** | **Governance Completeness** | `backend/banking_crosswalk/catalog.py` | Incorporate dedicated control taxonomies for First Nations acoustic/linguistic data sovereignty, vulnerable customer protections, and regional financial hardship mandates. |
| **P2-5** | **Baseline Drift Tracking & Version Diffing** | **GRC Operations** | `backend/banking_crosswalk/diff.py`, `web/app/enterprise/baselines/diff` | Provide visual side-by-side diffs showing how an updated policy version affects control coverage across existing deployed AI use cases. |

---

## 6. Acceptance Testing Criteria for P0 Implementation

To verify P0 completion, the automated test suite must demonstrate:

1. **Scenario A (Regulatory-Only):**
   - New tenant with 0 enterprise policies runs `/v1/assessments/coverage` with `questionnaire_pack="DEMO_BANKING_V1"`.
   - Assesses against Shared Regulatory Library; returns HTTP 201 with full `results` and `gaps`.
   - `assessment_mode` is `"regulatory_only"`, `enterprise_baseline_id` is null, `enterprise_gaps` is empty.
2. **Scenario B (Enterprise-Enhanced):**
   - Tenant uploads policy, creates active `EnterpriseBaseline` with reviewed/approved clauses.
   - Runs `/v1/assessments/coverage` with `assessment_mode="enterprise_enhanced"` and `enterprise_baseline_id`.
   - Returns HTTP 201; includes both regulatory gaps and `enterprise_gaps`.
3. **Mode Independence:**
   - Tenant with configured Enterprise Baseline runs with `assessment_mode="regulatory_only"`; system assesses purely regulatory requirements.
4. **Explicit Failure on Invalid Baseline:**
   - Request with `assessment_mode="enterprise_enhanced"` and non-existent `enterprise_baseline_id` returns HTTP 404 (never silent fallback to regulatory_only).
   - Request with `assessment_mode="enterprise_enhanced"` without `enterprise_baseline_id` returns HTTP 400/422.
5. **Cross-Tenant Isolation:**
   - Tenant B attempting to use Tenant A's `enterprise_baseline_id` in `enterprise_enhanced` mode receives HTTP 404.
6. **False Coverage Remediation:**
   - Policy clause with negation (*"This sandbox environment does not require human approval"*) produces 0 control mappings for `CTRL-GOV-OVERSIGHT`.
7. **Threshold Conflict Detection:**
   - Use case with AUD 1,000 threshold against baseline requiring AUD 500 generates a critical threshold conflict gap.
