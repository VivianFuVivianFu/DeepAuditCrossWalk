# P1-S0 Mapping Approval Invariants

## Executive Summary

This document defines the formal approval invariants, persistence contracts, and cryptographic integrity guarantees governing **Enterprise Clauses**, **Clause-to-Control Mappings**, and **Versioned Enterprise Baselines** in **DeepAudit Crosswalk** (`Revised P1-S0`).

---

## 1. Separation of Approval Dimensions

Enterprise policy ingestion produces two distinct governance artefacts that require independent human review and approval:

1. **Source Clause Approval (`EnterpriseClause.review_status`)**:
   - Establishes whether an extracted sentence or paragraph from an uploaded enterprise policy document represents an authentic, authoritative internal requirement for the tenant.
   - Reviewed via `PUT /v1/enterprise/clauses/{clause_id}/review` (`store.update_clause_review`).
   - Valid states: `unreviewed`, `proposed`, `approved`, `confirmed`, `rejected`.

2. **Clause-to-Control Mapping Approval (`ClauseControlMapping.review_status`)**:
   - Establishes whether a specific candidate relationship between an `EnterpriseClause` and a canonical `UnifiedControl` (`control_id`, `relationship`, and optional `mapped_facets`) is semantically valid and approved by assurance reviewers.
   - Reviewed independently via `PUT /v1/enterprise/clauses/{clause_id}/mappings/{mapping_id}/review` (`store.update_clause_mapping_review`), or by supplying an explicit `control_mappings` list during review.
   - Valid states: `unreviewed`, `proposed`, `approved`, `confirmed`, `rejected`.

---

## 2. Five Mandatory Invariants for `confirmed_control_ids`

In [`compile_enterprise_baseline()`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L1060-L1245), a `ClauseControlMapping` (`m`) on an `EnterpriseClause` (`c`) may contribute `m.control_id` to `EnterpriseBaseline.confirmed_control_ids` **if and only if all five invariants hold simultaneously**:

| Invariant | Formal Condition | Enforcement Behaviour on Failure |
|:---|:---|:---|
| **I-1: Source Clause Approved & Active** | `c.review_status in {APPROVED, CONFIRMED}` AND neither the parent `EnterprisePolicy` nor `c` has `status in {"superseded", "retired"}` | Mapping is excluded from `confirmed_control_ids`. If `c` is `PROPOSED`/`UNREVIEWED`, `c.clause_id` is recorded in `pending_clause_ids`. |
| **I-2: Mapping Independently Approved** | `m.review_status in {APPROVED, CONFIRMED}` | Proposed, unreviewed, or rejected mappings remain in their respective states inside `clause_snapshots` and never enter `confirmed_control_ids`. |
| **I-3: Equivalence Relationship Valid** | `m.relationship in {FULL, PARTIAL}` | Mappings marked `NOT_EQUIVALENT`, `NON_EQUIVALENT`, `MISSING`, `UNDETERMINED`, or `RELATED` never enter `confirmed_control_ids`. |
| **I-4: Valid Canonical Control Target** | `m.control_id in _valid_control_ids()` (verified against `UNIFIED_CONTROL_LIBRARY.json` and registered facet control identifiers) | Unknown or fabricated control IDs are excluded from `confirmed_control_ids`. |
| **I-5: Tenant & Ownership Consistency** | `p.tenant_id == tenant_id`, `c.tenant_id == tenant_id`, `c.policy_id == p.policy_id`, `m.tenant_id == tenant_id`, and `m.clause_id == c.clause_id` | Cross-tenant or mismatched policy/clause references raise `ValueError` (HTTP 422) during compilation or `NotFoundError` (HTTP 404) on API review. |

---

## 3. Preservation of Approved Clauses With Proposed or Unmapped Controls

Separating clause approval from mapping approval guarantees that approved enterprise requirements are never lost when control mappings are still pending review or when no canonical control exists:

1. **Approved Clause with Proposed Mapping (Scenario 8)**:
   - `c.clause_id` is recorded in `EnterpriseBaseline.approved_clause_ids`.
   - The baseline is eligible for `active` status because it contains an approved enterprise requirement.
   - `m.review_status` remains `ClauseReviewStatus.PROPOSED` in `clause_snapshots`.
   - `m.control_id` is **excluded** from `EnterpriseBaseline.confirmed_control_ids`.
   - During `enterprise_enhanced` coverage assessment, `c.clause_id` is included in `applicable_enterprise_requirement_ids`, and its `EnterpriseClauseCoverage` record reports `clause_approval_status="approved"` and `control_mapping_approval_status="proposed"`.
2. **Approved Clause with Rejected Mapping (Scenario 10)**:
   - `c.clause_id` is preserved in `EnterpriseBaseline.approved_clause_ids`.
   - `m.control_id` is **excluded** from `EnterpriseBaseline.confirmed_control_ids`.
3. **Approved Unmapped Clause (Scenario 12)**:
   - `c.clause_id` is recorded in both `EnterpriseBaseline.approved_clause_ids` and `EnterpriseBaseline.unmapped_clause_ids`.
   - During `enterprise_enhanced` coverage assessment, `c.clause_id` is included in `applicable_enterprise_requirement_ids` and evaluated with `coverage_status=CoverageStatus.MAPPING_INCOMPLETE` (`status="in_review"` gap) so it cannot be silently dropped or falsely passed by single-word overlap.

---

## 4. Cryptographic Snapshot Hashing & Immutability

[`compute_baseline_fingerprint()`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L1000-L1060) computes a deterministic SHA-256 digest (`baseline_sha256`) over:
- `tenant_id`, `name`, `version`, `revision`
- `policy_ids` and `source_policy_versions`
- `confirmed_controls` and `clause_ids`
- Each clause in `clause_snapshots`, including:
  - `clause_id`, `text`, `review_status`, `is_unmapped`, `mandatory`, `control_facets`, `thresholds_aud`
  - Every `ClauseControlMapping` in `control_mappings`: `mapping_id`, `control_id`, `relationship`, `review_status`, and `mapped_facets`

### Immutability Guarantees
- **Post-Publication Isolation**: Updating a clause review (`update_clause_review`) or a control mapping review (`update_clause_mapping_review`) clones the live store record (`model_copy(deep=True)`) and never mutates previously compiled `EnterpriseBaseline.clause_snapshots`.
- **Tamper Detection**: Any in-place modification to a saved baseline snapshot—including flipping a mapping's `review_status` from `proposed` to `approved`—causes [`verify_baseline_integrity()`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py#L1063-L1079) to return `False` and `POST /v1/assessments/coverage` to fail closed with `HTTP 422 Unprocessable Entity`.

---

## 5. Persistence & Migration Implications

- **In-Memory Store ([`store.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/store.py))**: Updated `update_clause_review` and added `update_clause_mapping_review` with strict tenant/clause ownership checks and audit event logging (`clause.reviewed`, `clause_mapping.reviewed`).
- **PostgreSQL Store ([`sql_store.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/sql_store.py))**: Updated `update_clause_review` and added `update_clause_mapping_review`. Because `enterprise_clauses`, `clause_control_mappings`, and `enterprise_baselines` store JSONB `payload` documents alongside relational keys, the new optional fields on `ClauseControlMapping` (`mapped_facets`, `reviewer_actor`, `reviewer_role`, `review_comment`, `reviewed_at`) and `EnterpriseBaseline` (`approved_clause_ids`) are backward-compatible with existing JSONB rows via Pydantic defaults. Note: Existing pre-P1-S0 baselines compiled under the older fingerprint schema should be recompiled into a new baseline revision if cryptographic verification against the expanded mapping-aware fingerprint is required.

