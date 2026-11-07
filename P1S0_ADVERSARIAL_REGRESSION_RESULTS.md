# P1-S0 Adversarial Regression Results

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Branch:** `fix/p1-s0-coverage-confirmation-safety`  
**Base Commit (`origin/main`):** `1576c40` (PR #23 — Final Regulatory Source Isolation & Optional Enterprise Baseline Hardening)  
**Test Suite File:** [`backend/tests/test_p1_s0_coverage_confirmation_safety.py`](backend/tests/test_p1_s0_coverage_confirmation_safety.py)

---

## 1. Pre-Fix Defect Reproduction Summary

Before applying the P1-S0 safety remediations, the 20 adversarial regression tests in [`backend/tests/test_p1_s0_coverage_confirmation_safety.py`](backend/tests/test_p1_s0_coverage_confirmation_safety.py) were executed against the unpatched `origin/main` codebase (`1576c40`).

**Pre-Fix Result:** **10 failed, 10 passed** — reproducing all three target defect classes:

| Defect Class | Failing Scenarios (Pre-Fix) | Observed Unsafe Pre-Fix Behaviour |
|---|---|---|
| **Defect A — Weak Keyword Matches** | `test_01`, `test_03`, `test_04`, `test_05`, `test_06`, `test_07`, `test_12`, `test_13` | `any(w in q.question_text.lower() for w in facet.split("_"))` and broad synonyms (`"human oversight"` for `human_approval_required`) caused generic tokens (`"threshold"`, `"approval"`, `"required"`, `"human"`) to suppress `missing_in_questionnaire` gaps (`len(gaps) == 0`). |
| **Defect B — Mapped Clauses Without Facets Bypassing Assessment** | `test_11` | `for facet in clause.control_facets:` executed zero iterations when `clause.control_facets == []` and `clause.is_unmapped == False`, silently treating the clause as covered (`0 == 1` gaps). |
| **Defect C — Clause & Control Mapping Approval Conflation** | `test_08`, `test_20` | `update_clause_review(..., status="approved")` overwrote `m.review_status = "approved"` on every proposed `ClauseControlMapping`, and `compile_enterprise_baseline()` used `if is_approved or m.review_status == ReviewStatus.APPROVED:` so unreviewed proposed mappings entered `confirmed_control_ids`. |

---

## 2. Post-Fix 20-Scenario Adversarial Verification Matrix

All 20 mandatory adversarial regression scenarios in [`backend/tests/test_p1_s0_coverage_confirmation_safety.py`](backend/tests/test_p1_s0_coverage_confirmation_safety.py) pass after remediation (`20 passed in 2.23s`):

| # | Test Function | Adversarial Scenario | Expected & Verified Post-Fix Outcome | Status |
|---|---|---|---|---|
| 1 | `test_01_clause_aud_50000_vs_question_generic_threshold` | Clause requires `>= $50,000 AUD` human approval; question asks *"Do you have a threshold for transactions?"* | `CoverageStatus.NEEDS_REVIEW` (`in_review` gap); NOT `covered` | **PASS** |
| 2 | `test_02_clause_aud_50000_vs_question_100000_threshold` | Clause requires `>= $50,000 AUD` human approval; question only covers `>= $100,000 AUD` | `CoverageStatus.MISSING` (`open` gap); weaker threshold rejected | **PASS** |
| 3 | `test_03_clause_aud_50000_vs_question_usd_50000` | Clause requires `>= $50,000 AUD`; question asks about `>= $50,000 USD` | `CoverageStatus.MISSING` (`open` gap); currency mismatch rejected | **PASS** |
| 4 | `test_04_missing_approval_role_in_question` | Clause requires `Senior Manager` approval; question asks *"Is approval required for high-value actions?"* without role | `CoverageStatus.NEEDS_REVIEW` (`in_review` gap); missing authority role caught | **PASS** |
| 5 | `test_05_pre_execution_vs_post_execution_review` | Clause requires pre-execution approval (`before execution`); question asks about post-execution review (`after execution`) | `CoverageStatus.MISSING` (`open` gap); post-execution timing rejected | **PASS** |
| 6 | `test_06_clause_requires_human_approval_vs_question_human_oversight` | Clause requires human approval; question only mentions *"human oversight"* | `CoverageStatus.NEEDS_REVIEW` (`in_review` gap); oversight is not approval | **PASS** |
| 7 | `test_07_clause_requires_human_approval_vs_question_negated_no_human_approval` | Clause requires human approval; question states *"Does the system operate with no human approval required?"* | `CoverageStatus.MISSING` (`open` gap); negated question rejected | **PASS** |
| 8 | `test_08_approved_clause_with_proposed_control_mapping` | Clause `review_status="approved"`, `ClauseControlMapping.review_status="proposed"` | Excluded from `confirmed_control_ids`; `CoverageStatus.NEEDS_REVIEW` (`in_review` gap) | **PASS** |
| 9 | `test_09_approved_clause_with_rejected_control_mapping` | Clause `review_status="approved"`, `ClauseControlMapping.review_status="rejected"` | Excluded from `confirmed_control_ids`; `CoverageStatus.MAPPING_INCOMPLETE` (`in_review` gap) | **PASS** |
| 10 | `test_10_rejected_clause_with_approved_control_mapping` | Clause `review_status="rejected"`, `ClauseControlMapping.review_status="approved"` | Excluded from `confirmed_control_ids` and excluded from active enterprise clause assessment | **PASS** |
| 11 | `test_11_approved_clause_with_approved_mapping_but_no_facets` | Clause `review_status="approved"`, mapping `review_status="approved"`, `control_facets=[]`, `mapped_facets=[]` | `CoverageStatus.MAPPING_INCOMPLETE` (`in_review` gap); never silently skipped | **PASS** |
| 12 | `test_12_approved_unmapped_clause_with_single_common_english_word` | Approved unmapped clause (`is_unmapped=True`) shares common words (`"customer"`, `"service"`, `"data"`) with question | `CoverageStatus.MAPPING_INCOMPLETE` (`in_review` gap); single-word overlap removed | **PASS** |
| 13 | `test_13_multi_facet_clause_only_one_facet_satisfied` | Clause has 2 required facets (`human_approval_required`, `audit_trail_logging`); questionnaire covers only 1 | `CoverageStatus.PARTIAL` (`open` gap for uncovered facet); never full `covered` | **PASS** |
| 14 | `test_14_question_covers_regulatory_control_id_but_fails_stricter_enterprise_numeric_facet` | Questionnaire satisfies base regulatory control (`AU-PRIV-01`) but fails enterprise clause's stricter numeric threshold (`>= $25,000 AUD`) | Regulatory control covered; enterprise clause `CoverageStatus.MISSING` (`missing_in_questionnaire` gap) | **PASS** |
| 15 | `test_15_not_related_mapping_relationship` | Approved clause and approved mapping with `relationship=MappingRelationship.NOT_RELATED` | Excluded from `confirmed_control_ids`; `CoverageStatus.MAPPING_INCOMPLETE` | **PASS** |
| 16 | `test_16_non_existent_control_id_in_mapping` | Approved clause and approved mapping pointing to `"NON-EXISTENT-CTRL-999"` | Excluded from `confirmed_control_ids` by `valid_control` check | **PASS** |
| 17 | `test_17_cross_tenant_clause_and_mapping_review_isolation` | `tenant_b` attempts to review `tenant_a`'s clause or `ClauseControlMapping` | Raises `PermissionError` (`403 Forbidden`); `tenant_a` state unchanged | **PASS** |
| 18 | `test_18_historical_snapshot_immutability_after_clause_and_mapping_review_changes` | Compile Baseline v1, run Assessment A, then reject mapping and compile Baseline v2 | Assessment A snapshot and Baseline v1 remain immutable and reproducible | **PASS** |
| 19 | `test_19_regulatory_only_ignores_enterprise_clauses_and_mappings` | `assessment_mode="regulatory_only"` with tenant enterprise clauses/mappings present in store | `enterprise_baseline_id=None`, `enterprise_clause_coverage=[]`, zero enterprise leakage | **PASS** |
| 20 | `test_20_enterprise_enhanced_requires_explicit_clause_and_mapping_approval` | End-to-end API workflow: approve clause -> verify proposed mapping NOT in baseline -> approve mapping via `PUT /v1/enterprise/clauses/{id}/mappings/{mid}/review` -> verify in baseline | Full dual-approval invariant and fingerprint differentiation verified | **PASS** |

---

## 3. Full Backend Regression Suite Results

Command executed:
```powershell
pytest backend -q
```

| Test Suite / Module | Passed | Skipped | Failed | Notes |
|---|---:|---:|---:|---|
| `backend/tests/test_p1_s0_coverage_confirmation_safety.py` | 20 | 0 | 0 | New P1-S0 20-scenario adversarial safety suite |
| `backend/tests/test_enterprise_baseline_construction.py` | 10 | 0 | 0 | Updated `test_7` for explicit mapping approval endpoint |
| `backend/tests/test_p1_safety_fix_a_isolation.py` | 14 | 0 | 0 | PR #23 source isolation suite |
| `backend/tests/test_aiaf_removal_and_library_boundaries.py` | 15 | 0 | 0 | PR #22 library boundary suite |
| `backend/tests/test_p1b1_deterministic_experiment.py` | 23 | 0 | 0 | P1B-1 evaluation harness & A0/A1 suite |
| All other unit, API, policy, coverage, and hardening tests | 104 | 0 | 0 | Existing P0/P1 regression suites |
| `backend/tests/test_postgres_integration.py` | 0 | 17 | 0 | **Skipped / Unverified locally** (requires live PostgreSQL container) |
| **Total** | **186** | **17** | **0** | **100% of executable tests pass; 17 Postgres container tests skipped** |

> **Explicit Verification Disclosure:** The 17 tests in [`backend/tests/test_postgres_integration.py`](backend/tests/test_postgres_integration.py) are **skipped/unverified** in this local execution environment because no live PostgreSQL database instance (`DATABASE_URL`) is running. SQL store parity for `update_clause_review` and `update_clause_mapping_review` was implemented in [`backend/banking_crosswalk/sql_store.py`](backend/banking_crosswalk/sql_store.py) and verified via static inspection and unit/API tests against `InMemoryStore`.

---

## 4. Remaining Uncertainties & Migration Implications

1. **Migration Implication for Existing API Callers:**
   - Previously, calling `PUT /v1/enterprise/clauses/{clause_id}/review` with `status="approved"` and omitting `control_mappings` implicitly mutated all proposed `ClauseControlMapping` records on that clause to `review_status="approved"`.
   - Under P1-S0, clause approval and mapping approval are strictly decoupled. Callers must either approve individual mappings via `PUT /v1/enterprise/clauses/{clause_id}/mappings/{mapping_id}/review` or supply reviewed `control_mappings` explicitly before those controls are included in `EnterpriseBaseline.confirmed_control_ids`.
2. **Baseline Fingerprint Evolution:**
   - `compute_baseline_fingerprint()` now hashes `control_mappings` (`mapping_id`, `control_id`, `relationship`, `review_status`, `mapped_facets`). Recompiling an existing policy will produce a new deterministic `content_fingerprint` reflecting the mapping state, while previously persisted `EnterpriseBaseline` snapshots retain their original stored `content_fingerprint`.
3. **Deterministic Facet Matching Scope:**
   - P1-S0 eliminates false-positive `covered` confirmations caused by word-splitting and weak synonyms, routing ambiguous candidate overlaps to `CoverageStatus.NEEDS_REVIEW` (`in_review` gap). Semantic paraphrases that do not match the deterministic facet phrases in `QUESTION_KEYWORDS` will remain `MISSING` or `NEEDS_REVIEW` until a human-in-the-loop semantic mapping workflow is introduced in a subsequent P1 phase.

