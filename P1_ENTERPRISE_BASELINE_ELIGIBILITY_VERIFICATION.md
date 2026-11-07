# P1 Enterprise Baseline Eligibility Verification

## Executive Summary

This document verifies the baseline compilation, governance eligibility rules, and immutability controls implemented in **DeepAudit Crosswalk** under **Prompt P1 Safety Fix A**.

The Enterprise Internal Baseline represents an optional, tenant-owned layer of internal governance requirements. Because findings produced in `enterprise_enhanced` mode affect institutional auditability and enterprise risk posture, strict eligibility gates must prevent premature, unreviewed, empty, or tampered baselines from being used in confirmed assessments.

---

## Baseline Eligibility Lifecycle & Gating Rules

```
+----------------------------------------------------------------------------------+
|                             Tenant Policy Document                               |
+----------------------------------------------------------------------------------+
                                        |
                                        v (extract_enterprise_policy)
+----------------------------------------------------------------------------------+
|                            Extracted Clauses (Proposed)                          |
+----------------------------------------------------------------------------------+
                                        |
                     +------------------+------------------+
                     |                                     |
                     v (Human Review)                      v (Unreviewed / Pending)
+-----------------------------------------+   +------------------------------------+
|  Approved / Confirmed Clauses           |   |  Proposed / Rejected Clauses       |
+-----------------------------------------+   +------------------------------------+
                     |                                     |
                     +------------------+------------------+
                                        |
                                        v (compile_enterprise_baseline)
                     +-------------------------------------+
                     | Has at least 1 Approved Clause?     |
                     +-------------------------------------+
                                   /       \
                             YES  /         \  NO
                                 v           v
                    +----------------+   +-----------------+
                    | status="active"|   | status="draft"  |
                    +----------------+   +-----------------+
                            |                     |
                            |                     |
                            v                     v
                 [ Eligible for Mode B ]    [ GATED: Rejected with HTTP 400 ]
```

---

## Key Eligibility Invariants

### 1. Rejection of Empty Policy Input
* **Requirement:** An active baseline cannot be compiled without input policies.
* **Implementation:**
  In `backend/banking_crosswalk/policy.py`:
  ```python
  if not policies or not all_clauses:
      if status == "active":
          raise ValueError("Cannot compile an active baseline from empty policy input")
      status = "draft"
  ```
* **API Enforcement:** Submitting `POST /v1/enterprise/baselines` with `policy_ids: []` returns **HTTP 422 Unprocessable Content**.
* **Verification:** `test_scenario_18` passes.

### 2. Wholly Unapproved Policies Compile as Draft
* **Requirement:** If all clauses in submitted policies are in `proposed` or `rejected` status (i.e. zero approved clauses), the compilation cannot yield an active baseline.
* **Implementation:**
  ```python
  has_approved = any(
      c.review_status in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
      for c in all_clauses
  )
  if not has_approved:
      if status == "active":
          status = "draft"
          warnings.append(
              "Baseline compiled with 'draft' status: policies contain wholly pending or rejected content "
              "with no approved or confirmed clauses. Draft baselines are not eligible for confirmed assessment."
          )
  ```
* **Verification:** `test_scenario_19` passes.

### 3. Draft Baselines Barred from Confirmed Assessment
* **Requirement:** An assessment running in `enterprise_enhanced` mode must reject any baseline that is in `draft` or `archived` status.
* **Implementation:**
  In `backend/banking_crosswalk/coverage.py`:
  ```python
  if enterprise_baseline.status != "active":
      raise ValueError(
          f"Enterprise baseline '{enterprise_baseline.baseline_id}' is in '{enterprise_baseline.status}' status. "
          "Draft baselines cannot be selected for confirmed enterprise_enhanced assessments."
      )
  ```
  In `backend/banking_crosswalk/api.py`:
  ```python
  if enterprise_baseline.status != "active":
      raise HTTPException(
          status_code=status.HTTP_400_BAD_REQUEST,
          detail=f"Enterprise baseline '{req.enterprise_baseline_id}' is not active",
      )
  ```
* **Verification:** `test_scenario_20` passes.

### 4. Representation of Unmapped Approved Requirements
* **Requirement:** An enterprise may introduce custom governance standards that do not correspond to any Canonical Control in the Shared Regulatory Library (e.g., "AI Ethics Advisory Board Annual Review"). These requirements must remain fully traceable without forcing artificial control mappings.
* **Implementation:**
  - `EnterpriseClause` supports `is_unmapped=True` with `control_mappings=[]`.
  - `EnterpriseBaseline` tracks unmapped clauses in `unmapped_clause_ids`.
  - In `evaluate_questionnaire_coverage`, unmapped approved clauses are included in `applicable_enterprise_requirement_ids` and reported in coverage outputs.
* **Verification:** `test_scenario_13` and `test_scenario_21` pass.

### 5. Immutability and Snapshot Integrity
* **Requirement:** Published baselines must be cryptographically immutable. Any modification to referenced content or revision under the same version must fail.
* **Implementation:**
  - `baseline_sha256` computes a deterministic digest over sorted clause snapshots, review statuses, and source policy versions.
  - `verify_baseline_integrity(baseline)` validates that the current content strictly reproduces `baseline_sha256`.
  - Both `InMemoryStore` and `SqlAlchemyStore` enforce revision immutability:
    ```python
    if existing.baseline_sha256 != baseline.baseline_sha256:
        raise ConflictError(
            f"Baseline '{baseline.baseline_id}' revision {baseline.revision} already exists with a different hash."
        )
    ```
* **Verification:** `test_scenario_16` passes.

---

## Summary of Test Coverage

All eligibility conditions and safety gates are covered by automated unit and API integration tests in `backend/tests/test_p1_safety_fix_a.py` and `backend/tests/test_optional_assessment_modes.py`. All tests pass cleanly without errors.
