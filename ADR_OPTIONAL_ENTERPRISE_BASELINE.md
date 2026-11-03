# ADR 0003: Optional Enterprise Policy Baseline & Dual-Mode Assessment Architecture

**Status:** Accepted  
**Date:** 2026-11-04  
**Author:** DeepAudit Architecture & GRC Team  
**Context:** Product Architecture Clarification for DeepAudit Crosswalk  
**Target Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  

---

## Context & Problem Statement

In previous architectural iterations, there was ambiguity regarding whether customer-uploaded enterprise policies were mandatory prerequisites for running a crosswalk assessment. Furthermore, early implementations of the policy gap engine (`assess_enterprise_policy_gaps`) treated uploaded internal policies as assessment targets and checked whether a single internal document covered all 46 external statutory obligations (e.g., flagging a Payment Refund Policy for not covering APRA CPS 234 cybersecurity encryption controls).

This created two critical architectural defects:
1. **Barrier to Entry:** Users wanting to assess an AI system or questionnaire against external Australian regulations (APRA, ASIC, Privacy Act) were blocked unless they first uploaded and configured internal enterprise policies.
2. **Architectural Inversion:** Baseline-building inputs (internal policy documents) were conflated with downstream assessment targets (AI Strategy, Questionnaire, Use Case).

---

## Decision

We formally establish the **Dual-Mode Assessment Architecture** with an **Optional Enterprise Policy Layer**:

### 1. Two Independent Assessment Modes

#### Mode A: Regulatory-Only Assessment (Default)
- **Applicability:** Default workflow for all users, including new tenants with zero uploaded policies.
- **Assessment Scope:** Evaluates the downstream assessment target (AI Governance Strategy, Questionnaire, or AI Use Case) strictly against:
  - The platform-maintained **Shared Regulatory Library** (Layer 1: 46 atomic obligations).
  - The **Unified Control Library** (33 controls).
  - Applicable external statutory obligations and required control facets.
- **Prerequisites:** **Zero enterprise policies or baseline configurations required.**
- **Output:** An evidence-backed **Regulatory Coverage Gap Report**.

#### Mode B: Enterprise-Enhanced Assessment (Optional)
- **Applicability:** Optional workflow for enterprise institutions that have established an internal governance baseline.
- **Baseline Construction:** Enterprise customers upload internal governance documents (Layer 2). The system chunks clauses, suggests candidate mappings to Unified Controls, and requires human compliance sign-off. Approved clauses compile into a versioned, tenant-isolated **Enterprise Baseline**.
- **Assessment Scope:** Evaluates the downstream target against the **Combined Baseline**:
  - Applicable Shared Regulatory Library obligations.
  - Applicable Unified Controls.
  - Applicable approved enterprise-specific requirements and thresholds.
- **Output:** A **Combined Regulatory + Enterprise Coverage Gap Report**, clearly distinguishing external statutory gaps from internal enterprise policy gaps.

---

## 2. Inviolable Data & Boundary Rules

1. **Enterprise Baseline Supplements, Never Overwrites:** Internal enterprise policies extend the applicable assessment baseline with institutional rules, stricter thresholds (e.g. AUD 500 approval limit), and custom controls. They never replace, overwrite, or weaken binding external law.
2. **Target vs Baseline Separation:**
   - **Baseline-Building Inputs (Layer 1 & Layer 2):** Shared Regulatory Library + Approved Enterprise Policies.
   - **Downstream Assessment Targets (Layer 3):** AI Governance Strategy, Assessment Questionnaire, Individual AI Use Case.
   - Internal policies uploaded to build the baseline are **never** treated as downstream assessment targets. Uploading an internal policy must never trigger statutory non-compliance alerts against unrelated regulations.
3. **Fail-Closed Baseline Resolution:**
   - In `regulatory_only` mode: The system strictly ignores enterprise policies, even if the tenant has active baselines.
   - In `enterprise_enhanced` mode: The request **must** provide a valid, active, tenant-owned `enterprise_baseline_id`.
   - If the baseline is missing, invalid, archived, or belongs to another tenant, the system **must fail with an explicit HTTP 400 or HTTP 404 error**.
   - **Silent fallback to regulatory-only mode is strictly prohibited.**
4. **Mode Independence:** An organisation with an existing Enterprise Baseline retains the permanent right to execute `regulatory_only` assessments.

---

## 3. Report Provenance & Output Schema

Every assessment report must record immutable provenance metadata:
- `assessment_mode`: `"regulatory_only"` | `"enterprise_enhanced"`
- `assessment_target_type`: `"questionnaire"` | `"strategy"` | `"use_case"`
- `regulatory_pack_id` & `regulatory_pack_version`
- `unified_control_library_version`
- `enterprise_baseline_id` & `enterprise_baseline_version` (null in regulatory-only mode)
- `mapping_review_status`: Confirmed (approved) vs Provisional (candidate)
- `legal_disclaimer`: Mandatory warning that assessment gaps do not constitute judicial or regulatory findings of legal non-compliance.

---

## Consequences

### Positive
- **Instant Time-to-Value:** Users can run out-of-the-box regulatory crosswalk assessments on day one without configuration overhead.
- **Enterprise Power:** Institutions can seamlessly inject bespoke thresholds (e.g. AUD 500 human approval limit) and proprietary policies into the assessment when mature.
- **Audit Defensibility:** GRC and legal teams receive clean, traceable gap reports without confusing single-policy omissions with corporate regulatory breaches.

### Negative / Trade-Offs
- The API and crosswalk engine must maintain two distinct resolution code paths and rigorous validation to ensure mode isolation.
- Test suites must verify both modes independently, ensuring neither mode regresses the other.
