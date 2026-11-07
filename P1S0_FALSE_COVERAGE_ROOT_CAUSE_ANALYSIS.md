# P1-S0 False Coverage Root Cause Analysis

## Executive Summary

This report documents the root-cause analysis and before/after verification of three critical coverage confirmation and approval-integrity defects identified in the **DeepAudit Crosswalk** Questionnaire Coverage Engine under **Prompt Revised P1-S0: Coverage Confirmation Safety & Mapping Approval Integrity**.

Prior to this remediation, the enterprise questionnaire coverage engine and baseline compiler could produce false confirmed coverage or promote unreviewed/rejected control mappings through three structural weaknesses:

1. **Defect A — Weak Keyword Matches (`coverage.py`, `policy.py`)**: Facet identifiers were split on underscores (`facet.split("_")`) and matched against questionnaire text using single-token substring checks (`len(term) > 3`), allowing generic words like `"human"`, `"defined"`, `"execution"`, or `"logging"`—as well as negated statements (`"human approval is not required"`)—to satisfy mandatory enterprise requirements without verifying monetary thresholds, numeric boundary operators, approval authority roles, or pre-execution blocking.
2. **Defect B — Mapped Clauses Without Explicit Facets (`coverage.py`)**: An `if / elif` control-flow gap skipped enterprise clauses where `clause.control_facets == []` and `clause.control_mappings` was non-empty (`clause.is_unmapped == False`), leaving `missing_facets = []` and silently bypassing coverage assessment as if the clause were fully covered.
3. **Defect C — Clause and Control Mapping Approval Conflation (`policy.py`, `store.py`, `sql_store.py`)**:
   - `compile_enterprise_baseline()` used a logical disjunction (`is_approved or m.review_status in {APPROVED, CONFIRMED}`), promoting proposed and even rejected control mappings into `confirmed_control_ids` whenever their parent clause was approved (and vice versa).
   - `update_clause_review()` in both `InMemoryRepository` and `SqlRepository` automatically overwrote `m.review_status = status` for all `ClauseControlMapping` records whenever `mappings=None`, implicitly approving every proposed control mapping upon clause review.

---

## 1. Detailed Root Cause Analysis

### Defect A — Weak Keyword Matches Creating False Confirmed Coverage

#### Affected Files & Pre-Fix Code
- [`backend/banking_crosswalk/coverage.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py) (pre-fix lines 560–605):
  ```python
  if clause.control_facets:
      for facet in clause.control_facets:
          facet_covered = False
          facet_terms = [facet.replace("_", " "), *facet.split("_")]
          for q in question_bank.questions:
              ql = q.question_text.lower()
              if any(term in ql for term in facet_terms if len(term) > 3):
                  facet_covered = True
                  break
          if not facet_covered:
              missing_facets.append(facet)
  elif clause.is_unmapped or not clause.control_mappings:
      ...
      if distinctive_terms:
          for q in question_bank.questions:
              ql = q.question_text.lower()
              if any(term in ql for term in distinctive_terms):
                  clause_covered = True
                  break
  ```
- [`backend/banking_crosswalk/policy.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) (pre-fix lines 263–280 and 462–486):
  ```python
  QUESTION_KEYWORDS: Dict[str, Sequence[str]] = {
      "human_approval_required": ("human approval", "human oversight", "manual review"),
      ...
  }
  ```

#### Failure Modes Reproduced Before Fix
1. **Generic Mention of Human Oversight (Scenario 1)**:
   - Clause: *"All automated customer refund transactions exceeding AUD 500 require Senior Manager human approval prior to execution."* (`control_facets = ["human_approval_required", "approval_threshold_defined", "pre_execution_block"]`)
   - Question: *"Does the AI system have general human oversight, defined monitoring, and execution logging?"*
   - **Pre-Fix Failure**: `"human"` matched `human_approval_required`, `"defined"` matched `approval_threshold_defined`, and `"execution"` matched `pre_execution_block`. The engine produced **zero questionnaire gaps** (`missing_facets = []`), falsely confirming coverage.
2. **Missing Monetary Threshold (Scenario 3)**:
   - Question: *"Does the workflow require mandatory human approval for defined high-value refund transactions?"* (omits `AUD 500`).
   - **Pre-Fix Failure**: `"approval"` and `"defined"` matched `approval_threshold_defined.split("_")`, producing zero questionnaire gaps (`assert len(clause_gaps) > 0` failed with `0 > 0`).
3. **Missing Approval Authority Role (Scenario 4)**:
   - Clause requires `Senior Manager` approval; question only checks `Customer Service Agent` approval.
   - **Pre-Fix Failure**: `clause.required_approval_role` was ignored during questionnaire facet verification (`assert len(clause_gaps) > 0` failed with `0 > 0`).
4. **Missing Pre-Execution Requirement (Scenario 5)**:
   - Question: *"Are automated payment refund executions reviewed for human approval during weekly post-execution audits?"*
   - **Pre-Fix Failure**: Token `"execution"` (from `pre_execution_block.split("_")`) matched `"executions"` despite explicit `"post-execution"` wording (`assert len(clause_gaps) > 0` failed with `0 > 0`).
5. **Incorrect Numeric Operator (Scenario 6)**:
   - Clause requires `>= AUD 500` (*"at or above AUD 500"*); question checks `> AUD 500` (*"exceeding AUD 500"*), leaving the exact `AUD 500` boundary uncovered.
   - **Pre-Fix Failure**: Token overlap satisfied `approval_threshold_defined` without checking operator compatibility (`assert len(clause_gaps) > 0` failed with `0 > 0`).
6. **Negated Approval Wording (Scenario 7)**:
   - Question: *"Confirm that human approval is not required for automated credit decisions."*
   - **Pre-Fix Failure**: Tokens `"human"`, `"approval"`, and `"required"` matched `human_approval_required` despite explicit negation (`assert len(clause_gaps) > 0` failed with `0 > 0`).
7. **Unmapped Clause Single-Word Overlap (Scenario 12)**:
   - Clause: *"All algorithmic decisions involving regional heritage sites must be reviewed by the Cultural Advisory Council."* (`is_unmapped=True`)
   - Question: *"Are regional data centre sites monitored for power redundancy?"*
   - **Pre-Fix Failure**: Shared word `"regional"` caused `clause_covered = True`, silently dropping the unmapped requirement from `enterprise_gaps` (`assert len(clause_gaps) == 1` failed with `0 == 1`).

---

### Defect B — Mapped Clauses Without Explicit Facets Bypassing Assessment

#### Affected Files & Pre-Fix Code
- [`backend/banking_crosswalk/coverage.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py) (pre-fix lines 560–605):
  ```python
  missing_facets = []
  if clause.control_facets:
      ...
  elif clause.is_unmapped or not clause.control_mappings:
      ...
  ```

#### Failure Mode Reproduced Before Fix
- When an approved `EnterpriseClause` had `control_facets == []`, `is_unmapped == False`, and a non-empty `control_mappings` list (e.g., mapped to `CTRL-HUMAN-OVERSIGHT` with no explicit `mapped_facets`), **neither the `if` branch nor the `elif` branch executed**.
- `missing_facets` remained `[]`, causing the engine to emit zero gaps (`assert len(clause_gaps) == 1` failed in `test_11_approved_mapped_clause_with_no_facets_cannot_bypass_assessment` with `0 == 1`).
- In effect, the presence of a candidate or approved `ClauseControlMapping` was treated as if the questionnaire had already been verified against the clause's required facets.

---

### Defect C — Clause and Control Mapping Approval Conflation

#### Affected Files & Pre-Fix Code
1. [`backend/banking_crosswalk/policy.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) (pre-fix lines 1122–1127):
   ```python
   for m in c.control_mappings:
       if m.control_id and (
           is_approved
           or m.review_status in {ClauseReviewStatus.APPROVED, ClauseReviewStatus.CONFIRMED}
       ):
           confirmed_controls.add(m.control_id)
   ```
2. [`backend/banking_crosswalk/store.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/store.py) (pre-fix lines 379–382) and [`backend/banking_crosswalk/sql_store.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/sql_store.py) (pre-fix lines 531–533):
   ```python
   if mappings is not None:
       clause.control_mappings = mappings
   else:
       for m in clause.control_mappings:
           m.review_status = status
   ```
3. [`backend/banking_crosswalk/policy.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) (`compute_baseline_fingerprint`, pre-fix lines 1002–1013):
   - Did not include `control_mappings` in `clause_snapshots` hashing, allowing in-place mutation of mapping review states inside a baseline snapshot without invalidating `baseline_sha256`.

#### Failure Modes Reproduced Before Fix
1. **Implicit Mapping Approval on Clause Review (Scenario 8 & Scenario 20)**:
   - Calling `PUT /v1/enterprise/clauses/{clause_id}/review` with `{"status": "approved", ...}` mutated all `clause.control_mappings[i].review_status` from `"proposed"` to `"approved"`, failing `test_08` and `test_20`.
2. **Rejected and Proposed Mapping Promotion in `compile_enterprise_baseline()` (Scenario 8 & Scenario 10)**:
   - Because `compile_enterprise_baseline()` used `is_approved or m.review_status in ...`, an approved clause with a `PROPOSED` or `REJECTED` mapping still promoted `m.control_id` into `baseline.confirmed_control_ids`, and an `APPROVED` mapping on a `REJECTED` clause also entered `baseline.confirmed_control_ids`.

---

## 2. Summary of Implemented Remediations

| Defect | Remediated Components | Post-Fix Behaviour |
|:---|:---|:---|
| **Defect A** | [`coverage.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py), [`policy.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py) | Removed `facet.split("_")` single-word matching and unmapped single-word overlap. Added deterministic facet & constraint validators (`_question_satisfies_enterprise_facet`, `_is_question_negated_for_facet`, `_question_satisfies_approval_role`, `_question_is_weak_candidate_for_facet`) enforcing explicit human-approval phrasing, monetary thresholds, currency, boundary operators (`>=` vs `>`), required approval authority roles, pre-execution timing, and negation rejection. Weak topical matches produce `CoverageStatus.NEEDS_REVIEW`, never `CoverageStatus.COVERED`. |
| **Defect B** | [`coverage.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py), [`models.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py) | Clauses with control mappings but no validated `control_facets` (or `mapped_facets`) never assume generic control facets apply or are satisfied; they are classified as `CoverageStatus.MAPPING_INCOMPLETE` and emit an actionable `in_review` gap with `missing_facets=["mapping_incomplete"]`. Unmapped clauses are similarly preserved in `applicable_enterprise_requirement_ids` and flagged as `CoverageStatus.MAPPING_INCOMPLETE`. |
| **Defect C** | [`policy.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/policy.py), [`store.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/store.py), [`sql_store.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/sql_store.py), [`api.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py) | Removed implicit `m.review_status = status` mutation from `update_clause_review`. Added independent mapping review endpoint `PUT /v1/enterprise/clauses/{clause_id}/mappings/{mapping_id}/review` and store method `update_clause_mapping_review`. Updated `compile_enterprise_baseline()` to require conjunction (`is_approved and mapping_is_approved and valid_relationship and valid_control and consistent_refs`) before a control enters `confirmed_control_ids`, while preserving approved clauses in `approved_clause_ids`. Included `control_mappings` in `compute_baseline_fingerprint()`. |

