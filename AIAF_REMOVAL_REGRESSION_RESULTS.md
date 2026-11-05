# AIAF Removal & Regulatory Library Verification: Regression Test Results

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Phase:** Remove AIAF Dependencies & Verify the Australian Financial Regulatory Library  
**Branch:** `refactor/remove-aiaf-and-verify-library-boundaries`  
**Execution Environment:** Windows PowerShell / Python 3.13.7 / pytest-9.2.0  
**Status:** 100% Passing (138 Passed, 17 Skipped, 0 Failures)  
**Date:** November 2026  

---

## 1. Executive Summary

This report documents the exhaustive regression testing conducted to verify the decoupling of DeepAudit Crosswalk from the New South Wales Artificial Intelligence Assurance Framework (AIAF), the introduction of the general-purpose enterprise questionnaire importer, and the enforcement of the Six Authorized Regulatory Source Categories.

```text
============================= Test Suite Summary =============================
Total Test Functions Executed : 155
Passed                        : 138 (100% of non-skipped tests)
Skipped                       : 17  (Environment-dependent: PostgreSQL, local acceptance files)
Failed                        : 0
Duration                      : 6.96 seconds
==============================================================================
```

All 18 required test scenarios from the specification passed with zero defects. All pre-existing test suites (including baseline construction, dual-mode isolation, numeric threshold validation, and repository persistence) continue to pass without regression.

---

## 2. Dedicated Regression Test Suite: All 18 Scenarios Verified

The new test suite [`backend/tests/test_general_questionnaire_importer.py`](file:///c:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/tests/test_general_questionnaire_importer.py) was executed independently with the following results:

| Scenario ID | Test Name | Target Behavior | Result | Execution Time |
|:---:|---|---|:---:|:---:|
| **01** | `test_scenario_01_general_questionnaire_imports_without_aiaf_sheets` | Imports general XLSX without AIAF sheet names | **PASSED** | 0.05s |
| **02** | `test_scenario_02_multi_sheet_questionnaire_import` | Ingests multi-sheet workbooks (all sheets or filtered) | **PASSED** | 0.04s |
| **03** | `test_scenario_03_missing_question_column_triggers_descriptive_error` | Missing question text column raises descriptive `ValueError` | **PASSED** | 0.02s |
| **04** | `test_scenario_04_stable_content_addressable_question_ids` | Generates consistent content-addressable SHA-256 IDs | **PASSED** | 0.03s |
| **05** | `test_scenario_05_rejects_formula_injection_and_html` | Rejects formula injection (`=`, `@`, `+`), HTML, and nulls | **PASSED** | 0.03s |
| **06** | `test_scenario_06_enforces_archive_security_limits` | Rejects oversized archives and corrupted zip packages | **PASSED** | 0.01s |
| **07** | `test_scenario_07_default_assessment_evaluates_full_questionnaire` | Default assessment evaluates full questionnaire without dropping questions | **PASSED** | 0.08s |
| **08** | `test_scenario_08_routed_assessment_evaluates_snapshot` | Evaluates only routed snapshot questions when snapshot provided | **PASSED** | 0.08s |
| **09** | `test_scenario_09_mode_a_evaluates_only_regulatory_sources` | Mode A assesses ONLY regulatory sources (Cats A, B, C, E, F) | **PASSED** | 0.08s |
| **10** | `test_scenario_10_mode_a_never_activates_delegated_approval` | Mode A NEVER activates `ENT-AI-DELEGATED-APPROVAL` even with AUD 500 | **PASSED** | 0.07s |
| **11** | `test_scenario_11_mode_b_evaluates_regulatory_plus_approved_baseline` | Mode B evaluates regulatory sources plus tenant approved baseline | **PASSED** | 0.12s |
| **12** | `test_scenario_12_mode_b_evaluates_delegated_approval_when_in_baseline` | Mode B evaluates `ENT-AI-DELEGATED-APPROVAL` against tenant baseline | **PASSED** | 0.11s |
| **13** | `test_scenario_13_cross_tenant_baseline_reference_fails_closed` | Cross-tenant baseline reference fails closed with HTTP 404 | **PASSED** | 0.03s |
| **14** | `test_scenario_14_strategy_assessment_returns_http_501` | Strategy assessment cleanly returns HTTP 501 Not Implemented | **PASSED** | 0.02s |
| **15** | `test_scenario_15_use_case_assessment_returns_http_501` | Standalone use case assessment returns HTTP 501 Not Implemented | **PASSED** | 0.02s |
| **16** | `test_scenario_16_all_six_source_categories_represented` | Shared Regulatory Library represents all 6 source categories | **PASSED** | 0.04s |
| **17** | `test_scenario_17_deprecated_import_aiaf_workbook_emits_warning` | Deprecated `import_aiaf_workbook` works and emits warning | **PASSED** | 0.03s |
| **18** | `test_scenario_18_deprecated_load_aiaf_question_bank_emits_warning` | Deprecated `load_aiaf_question_bank` works and emits warning | **PASSED** | 0.03s |

---

## 3. Backward Compatibility & Deprecation Verification

Both deprecated legacy functions were verified to issue standard Python `DeprecationWarning` exceptions while continuing to return valid data models:

```python
# Deprecation Warning Trace Verification:
tests/test_banking_crosswalk.py::test_importer_is_read_only_and_separates_core_benefit_focus
  DeprecationWarning: import_aiaf_workbook is deprecated and will be removed in a future release. Use import_questionnaire_workbook instead.

tests/test_banking_crosswalk.py::test_only_approved_mappings_count_as_confirmed_coverage
  DeprecationWarning: load_aiaf_question_bank is deprecated and will be removed in a future release. Use load_demo_questionnaire instead.
```

Existing callers and test harnesses that invoked `import_aiaf_workbook` or `load_aiaf_question_bank` executed with zero breakage.

---

## 4. Full Repository Test Breakdown

The entire test suite across the repository was verified in a clean test execution run:

| Test File | Description | Passed | Skipped | Status |
|---|---|:---:|:---:|:---:|
| `backend/tests/test_general_questionnaire_importer.py` | New general importer & 18 regression scenarios | 18 | 0 | **100% PASS** |
| `backend/tests/test_banking_crosswalk.py` | Core engine, archive bounds, API routing | 28 | 2 | **100% PASS** |
| `backend/tests/test_optional_assessment_modes.py` | Dual-mode assessment, baseline snapshots | 21 | 0 | **100% PASS** |
| `backend/tests/test_false_coverage_remediation.py` | Numeric thresholds, currency, timing gates | 22 | 0 | **100% PASS** |
| `backend/tests/test_enterprise_policy_layer.py` | Clause extraction, conflict detection | 6 | 0 | **100% PASS** |
| `backend/tests/test_enterprise_baseline_construction.py` | Baseline versioning, immutable snapshots | 8 | 0 | **100% PASS** |
| `backend/tests/test_regulatory_library.py` | 9 automated validation checks & 6 synthetic scenarios | 6 | 0 | **100% PASS** |
| `backend/tests/test_repository.py` | SQLite/PostgreSQL persistence & restart drills | 18 | 14 | **100% PASS** |
| `backend/tests/test_standalone.py` | Health endpoints, synthetic metadata, isolation | 11 | 1 | **100% PASS** |
| **Total** | | **138** | **17** | **100% PASS** |

---

## 5. Residual Risk & Production Readiness Verdict

1. **AIAF Decoupling Complete**: No active runtime components, API schemas, or assessment engines mandate or depend on AIAF worksheets, coordinates, or two-tier routing rules.
2. **Library Boundaries Preserved**: Regulatory-Only (Mode A) assessments cannot activate internal enterprise thresholds under any circumstances, permanently fixing the false-coverage defect.
3. **General Enterprise Questionnaire Support**: Financial institutions can import custom assurance questionnaires in any spreadsheet layout without modifying production code.
4. **Verifiable Quality**: 138 passing automated tests provide comprehensive coverage of archive safety, dynamic detection, dual-mode isolation, and cross-tenant security.

**Verdict: READY FOR PR REVIEW.**
