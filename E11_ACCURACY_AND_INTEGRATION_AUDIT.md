# DeepAudit Crosswalk — E1.1 Accuracy and Integration Audit

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Base Commit:** `540f77d` (PR #31 merged into `main`)  
**Target Branch:** `fix/e11-effective-baseline-accuracy-integration`  
**Scope:** Independent Accuracy Audit & End-to-End Effective Baseline Integration Review

---

## 1. Executive Summary

Following the merge of PR #31 (Enterprise Requirement Reconciliation Engine — E1), an independent engineering and assurance audit examined two critical release-readiness risks before introducing LLM-based Semantic Matching:

1. **Overstated Accuracy Scope:** PR #31 reported `100.0%` classification accuracy (`16/16` across Dev $N=8$ and Held-Out $N=8$). Source inspection of [backend/tests/test_e1_requirement_reconciliation.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/tests/test_e1_requirement_reconciliation.py) confirmed that all 16 cases bypassed raw document extraction and Stage A candidate retrieval by supplying pre-segmented clauses, preassigned canonical `control_facets`, pre-approved `ClauseControlMapping` records, and the target `external_obligation_id` directly to `validate_candidate_relationship()`.
2. **Unsafe Auto-Attachment & Unintegrated Assessment Basis (`api.py` & `coverage.py`):** In [backend/banking_crosswalk/api.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py), `create_coverage_assessment()` automatically attached `eff_baselines[-1]` whenever an `enterprise_baseline_id` was supplied — ignoring applicability context (`BankingUseCase`), `regulatory_pack_version`, `enterprise_baseline_revision`, cryptographic fingerprints, `as_of_date`, and reconciliation staleness — while `evaluate_questionnaire_coverage()` only saved metadata pointers without actually evaluating the `EffectiveAssessmentBaseline`.

Both risks have been audited, remediated in E1.1, and verified against a new 36-clause multi-organisation end-to-end benchmark (`test_e11_11_end_to_end_multi_org_dev_and_held_out_benchmark_pipeline`) that starts from raw PDF, DOCX, TXT, and XLSX files without preassigned facets or target obligation IDs.

---

## 2. Audit of E1 Accuracy Claims

### 2.1 Why E1's `100.0%` (16/16) Benchmark Cannot Represent End-to-End Production Accuracy

In PR #31 (`test_e1_evaluation_benchmark_dev_and_held_out_splits`):

- **Input Shortcut 1 — Pre-segmented Atomic Clauses:** Tests called `_make_approved_clause(...)` in Python memory rather than parsing raw PDF, DOCX, or TXT files via `extract_policy_file()` and `extract_enterprise_policy()`.
- **Input Shortcut 2 — Preassigned `control_facets` and `control_mappings`:** Clauses were seeded directly with exact `AtomicObligation.coverage_facets` strings (e.g., `["privacy_accountability_assigned", "privacy_practices_implemented", "privacy_policy_current"]`), whereas real extracted policy clauses from `extract_enterprise_policy()` only receive generic heuristics (`human_approval_required`, `prompt_logging`, `zero_data_retention`, `collection_purpose_defined`) or empty facet lists.
- **Input Shortcut 3 — Bypassed Stage A Retrieval:** Each benchmark assertion invoked `validate_candidate_relationship(clause=c, obligation=ob_map[target_ob_id], ...)`, providing the exact ground-truth obligation instead of retrieving top-$K$ candidates from the full 45-obligation Shared Regulatory Library.

### 2.2 Separation of Pipeline Accuracy Metrics

E1.1 replaces single-metric reporting with seven distinct, independently measured pipeline stages:

| Pipeline Stage | Metric Definition | E1 (PR #31) Covered? | E1.1 Measured? |
| :--- | :--- | :--- | :--- |
| **1. Document Extraction** | Exact/complete atomic clause recovery from raw `.pdf`, `.docx`, `.txt` uploads | No | **Yes** |
| **2. Candidate Retrieval** | `Recall@1` and `Recall@5` against all applicable `AtomicObligation` items without ground-truth IDs | No | **Yes** |
| **3. Relationship Classification** | Accuracy, Macro Precision, Macro Recall, Macro F1 across 8 `ReconciliationRelationship` classes | Isolated Stage B only | **Yes (End-to-End)** |
| **4. False Equivalence Rate** | Share of non-equivalent clauses misclassified as `equivalent` (Hard Gate: `0.0%`) | Stage B only | **Yes (`0.0%` Gate)** |
| **5. False Conflict Rate** | Share of non-conflicting clauses misclassified as `potential_conflict` | Stage B only | **Yes** |
| **6. Unresolved Detection Rate** | Share of conflicts / weaker / conditional / ambiguous clauses surfaced for human review | Stage B only | **Yes** |
| **7. End-to-End Crosswalk & Citation Safety** | Source/version traceability completeness + zero false confirmed questionnaire coverage | Partial | **Yes (`0.0%` Gate)** |

---

## 3. Audit of Effective Baseline Selection & Coverage Integration Bugs (Prior State)

Inspection of [backend/banking_crosswalk/api.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py) and [backend/banking_crosswalk/coverage.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py) prior to E1.1 identified four concrete integration defects:

1. **Blind `eff_baselines[-1]` Attachment (`api.py`):**
   - When `req.enterprise_baseline_id` was provided, `api.py` queried `store.list_effective_baselines(x_tenant_id, baseline_id=enterprise_baseline.baseline_id)` and attached `eff_baselines[-1]` unconditionally whenever non-empty.
   - If Tenant A composed `eff_1` for a *Domestic Refund AI Agent* and later composed `eff_2` (`eff_baselines[-1]`) for an *Offshore Credit Underwriting AI Agent*, running a *Domestic Refund* assessment blindly attached `eff_2`.
   - Even worse, an old `EffectiveAssessmentBaseline` composed against `regulatory_pack_version = "0.0.9"` or with newly superseded/stale reconciliation decisions would be silently attached if it happened to be last in storage order.
2. **Missing Binding Validation Contract (`reconciliation.py`):**
   - `verify_effective_baseline_integrity()` did not exist, `EffectiveAssessmentBaseline` did not snapshot `BankingUseCase` applicability profile fields (`use_case_snapshot`), and no validator checked the 8 required binding invariants prior to assessment.
3. **Opaque Assessment Basis Metadata (`models.py` & `coverage.py`):**
   - `CoverageAssessment` lacked `assessment_basis` and `effective_baseline_binding_mode`, making it impossible for downstream consumers or auditors to distinguish a `regulatory_pack_only` assessment from `regulatory_pack_plus_enterprise_baseline` or an explicitly validated `effective_assessment_baseline`.
4. **Disconnected Downstream Evaluation (`coverage.py`):**
   - `evaluate_questionnaire_coverage()` accepted `effective_baseline_id` / `effective_baseline_sha256` as passive strings without filtering out excluded clauses, tracking `reconciled_equivalence_group_ids`, propagating `unresolved_reconciliation_ids`, or converting `effective_baseline.potential_conflicts` into auditable `GapRecord` items (`reconciliation_conflict_gaps`).

---

## 4. Summary of E1.1 Remediations

1. **Deterministic Stage A Candidate Ranking & Lexical Facet Bridge ([reconciliation.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/reconciliation.py)):**
   - Added `rank_reconciliation_candidates_for_clause()` and `_infer_canonical_obligation_facets_for_clause()` for raw extracted clauses lacking manually preassigned canonical facets, enabling real end-to-end Stage A -> Stage B reconciliation while preserving conservative `0.0%` false equivalence safeguards.
2. **Removed Blind `eff_baselines[-1]` Attachment ([api.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py)) & Hardened Gateway ([workspace/route.ts](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web/app/api/workspace/route.ts)):**
   - Coverage assessments without an explicit `effective_baseline_id` no longer auto-attach any stored `EffectiveAssessmentBaseline`.
   - Explicit `effective_baseline_id`, `effective_baseline_sha256`, and `as_of_date` parameters are validated across all 8 required properties via `validate_effective_baseline_for_assessment()`.
3. **Genuine Effective Baseline Integration ([coverage.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py), [models.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py)):**
   - Populates `assessment_basis`, `effective_baseline_binding_mode`, `reconciled_equivalence_group_ids`, `unresolved_reconciliation_ids`, and `reconciliation_conflict_gaps` while preserving every applicable external obligation and enforcing zero false confirmed questionnaire coverage.
4. **Documentation Honesty ([E1_RECONCILIATION_VALIDATION_RESULTS.md](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/E1_RECONCILIATION_VALIDATION_RESULTS.md)):**
   - Scoped E1's `16/16` table explicitly to isolated Stage B unit validation and cross-referenced the new end-to-end benchmark results.
