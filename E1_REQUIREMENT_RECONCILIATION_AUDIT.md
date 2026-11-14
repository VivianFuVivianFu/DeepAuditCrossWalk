# E1 — Requirement Reconciliation Audit Report

## 1. Executive Summary

This report documents the baseline architectural audit conducted prior to implementing the **Enterprise Requirement Reconciliation Engine (E1)** for **DeepAudit Crosswalk**.

The audit inspected:

- [backend/banking_crosswalk/models.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py)
- [backend/banking_crosswalk/policy.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py)
- [backend/banking_crosswalk/coverage.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py)
- [backend/banking_crosswalk/applicability.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/applicability.py)
- [backend/banking_crosswalk/catalog.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/catalog.py)
- [backend/banking_crosswalk/store.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/store.py)
- [backend/banking_crosswalk/sql_store.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/sql_store.py)
- [backend/banking_crosswalk/schema.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/schema.py)
- [backend/banking_crosswalk/database.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/database.py)
- [backend/banking_crosswalk/api.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py)
- [backend/banking_crosswalk/data/regulatory_pack.v0.1.json](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/data/regulatory_pack.v0.1.json)
- [backend/banking_crosswalk/data/unified_control_library.json](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/data/unified_control_library.json)
- [backend/banking_crosswalk/data/obligation_control_mappings.json](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/data/obligation_control_mappings.json)

---

## 2. Audit Classification of Existing Components

| Component / Function | Location | Classification | Audit Finding |
| :--- | :--- | :--- | :--- |
| `load_regulatory_pack()`, `load_unified_control_library()`, `load_obligation_control_mappings()` | [catalog.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/catalog.py) | **1. Reliable and reusable** | Loads immutable, versioned Shared Regulatory Library (`AU-BANKING-REG-PACK-0.1`, v`0.1.0`), 33 Unified Controls, and 55 primary obligation-to-control mappings with full source provenance. |
| `decide_applicability()` | [applicability.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/applicability.py) | **1. Reliable and reusable** | Deterministically resolves `applicable`, `not_applicable`, and `human_confirmation_required` for external regulatory obligations based on explicit `BankingUseCase` attributes without keyword guessing. |
| `extract_enterprise_policy()` & structured clause extractors (`_detect_threshold_operator`, `_detect_threshold_currency`, `_detect_approval_timing`, `_detect_approval_role`, `_detect_conditions`, `_detect_exceptions`) | [policy.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) | **1. Reliable and reusable** | Deterministically extracts atomic `EnterpriseClause` records with thresholds, operators, currencies, timing, approval actors, conditional triggers, exception carve-outs, and `PROPOSED` review status. |
| `compile_enterprise_baseline()`, `compute_baseline_fingerprint()`, `verify_baseline_integrity()` | [policy.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) | **1. Reliable and reusable** | Compiles immutable, SHA-256 fingerprinted `EnterpriseBaseline` snapshots with `clause_snapshots` and `source_policy_versions`. |
| `_validate_reviewer_identity()`, `_reject_public_demo_tenant()`, PostgreSQL RLS (`document_table`) | [api.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py), [schema.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/schema.py), [sql_store.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/sql_store.py) | **1. Reliable and reusable** | Enforces HMAC-authenticated workspace context, reviewer RBAC, `public-demo` tenant isolation, and PostgreSQL `FORCE ROW LEVEL SECURITY`. |
| `check_shared_library_duplicate()` & internal baseline conflict check in `compile_enterprise_baseline()` | [policy.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) | **2. Incomplete** | `check_shared_library_duplicate()` only checks the first 2,000 characters for 5 hardcoded instrument substrings. `compile_enterprise_baseline()` only checks whether multiple `thresholds_aud` values exist across internal clauses, without reconciling enterprise clauses against external obligations. |
| `extract_policy_pack()` / `assess_policy_gaps()` vs `extract_enterprise_policy()` / `assess_enterprise_policy_gaps()` | [policy.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) | **3. Duplicated** | Legacy MVP `PolicyPack` functions coexist with the newer `EnterprisePolicy` layer. E1 builds strictly on the structured `EnterprisePolicy` / `EnterpriseClause` / `EnterpriseBaseline` models while keeping legacy endpoints intact for backward compatibility. |
| Facet/keyword matching in `assess_enterprise_policy_gaps()` | [policy.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) | **4. Based on unsafe assumptions (if used for reconciliation)** | Assumes an external obligation facet is "covered" if `facet in clause.control_facets` or any keyword phrase appears in `clause.text.lower()`, without checking clause approval status, control mapping approval status, negation (`does not require`), exceptions, conditions, currency mismatch, threshold direction, or operator boundary differences. |
| Enterprise Requirement Reconciliation Engine & Effective Assessment Baseline Composer | [reconciliation.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/reconciliation.py) | **5. Missing (Implemented in E1)** | Prior to E1, no two-stage reconciliation engine (`Stage A` Candidate Generation + `Stage B` Multi-Dimension Validation), no version-bound `ReconciliationDecision` review workflow, no staleness detector, and no deterministic `EffectiveAssessmentBaseline` composition service existed. |

---

## 3. Remediation & Architectural Decisions in E1

1. **Strict Separation of Stage A (Candidate Generation) and Stage B (Multi-Dimension Validation)**:
   - Implemented in [backend/banking_crosswalk/reconciliation.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/reconciliation.py).
   - Sharing a `control_id` never establishes `equivalent`. Stage B inspects clause approval status, control mapping approval status, indeterminate language, transaction scope, action polarity (`prohibition` vs `absence_of_control`), currency, threshold values, threshold operators (`>` vs `>=`), timeframes, approval timing (`pre_execution` vs `post_execution`), approval actors, conditions, exceptions, authority level, and facet completeness.
2. **Independent Human Review Gate (`ReconciliationDecision`)**:
   - Separate from Enterprise Clause Approval, Control Mapping Approval, Questionnaire-to-Facet Mapping Approval, and Confirmed Coverage.
   - Restricted to authorised reviewer roles (`reviewer`, `legal`, `compliance`, `risk`, `admin`).
3. **Version-Bound Staleness Detection**:
   - `evaluate_reconciliation_staleness()` detects changes in `regulatory_pack_version`, `external_source_version`, `enterprise_baseline_version`, `enterprise_baseline_sha256`, `enterprise_clause_sha256`, or superseded policy status.
4. **Deterministic Effective Assessment Baseline Composition**:
   - `compose_effective_assessment_baseline()` preserves every applicable external obligation, retains stricter and additional enterprise requirements, preserves unmapped approved enterprise requirements, groups reviewed equivalences for presentation without deleting underlying obligations, and surfaces all unresolved items and conflicts with a deterministic `effective_baseline_sha256`.
