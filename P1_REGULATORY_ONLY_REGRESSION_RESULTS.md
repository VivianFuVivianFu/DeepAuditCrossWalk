# P1 Regulatory-Only Regression Results

## Executive Summary

This report documents the verification and regression test results executed under **Prompt P1 Safety Fix A** for the **DeepAudit Crosswalk** platform.

A dedicated test suite, `backend/tests/test_p1_safety_fix_a.py`, was implemented covering all 28 mandatory regression scenarios specified in the prompt. All 28 scenarios passed cleanly. Furthermore, the entire backend regression suite was executed across all modules, achieving **166 passed, 17 skipped, 0 failures**.

---

## 28 Mandatory Regression Scenarios Test Matrix

### Group 1: Regulatory-Only Isolation (Scenarios 1–8)

| Scenario | Description | Test Function | Result |
|:---|:---|:---|:---|
| **Scenario 1** | Tenant with no enterprise policies can run Questionnaire Assessment | `test_scenario_1_tenant_with_no_enterprise_policies_runs_questionnaire_assessment` | **PASSED** |
| **Scenario 2** | Tenant with baseline can still run Regulatory-Only | `test_scenario_2_tenant_with_baseline_can_still_run_regulatory_only` | **PASSED** |
| **Scenario 3** | Omitting `assessment_mode` resolves to Regulatory-Only | `test_scenario_3_omitting_assessment_mode_resolves_to_regulatory_only` | **PASSED** |
| **Scenario 4** | Omitting Use Case context does not activate Enterprise-Enhanced | `test_scenario_4_omitting_use_case_context_does_not_activate_enterprise_enhanced` | **PASSED** |
| **Scenario 5** | Shared enterprise example absent from assessment results | `test_scenario_5_shared_enterprise_example_absent_from_assessment_results` | **PASSED** |
| **Scenario 6** | AUD 1,000 approval context does not activate enterprise obligations | `test_scenario_6_aud_1000_approval_context_does_not_activate_enterprise_obligations` | **PASSED** |
| **Scenario 7** | Voluntary frameworks not assumed adopted when context is missing | `test_scenario_7_voluntary_frameworks_not_assumed_adopted_when_context_missing` | **PASSED** |
| **Scenario 8** | External regulatory applicability continues functioning | `test_scenario_8_external_regulatory_applicability_continues_functioning` | **PASSED** |

### Group 2: Enterprise-Enhanced Execution (Scenarios 9–17)

| Scenario | Description | Test Function | Result |
|:---|:---|:---|:---|
| **Scenario 9** | Explicit selected approved baseline is required | `test_scenario_9_explicit_selected_approved_baseline_required` | **PASSED** |
| **Scenario 10** | Tenant-owned approved delegated-authority clause correctly evaluated | `test_scenario_10_tenant_owned_approved_delegated_authority_evaluated` | **PASSED** |
| **Scenario 11** | Unrelated approved control mapping does not activate platform example | `test_scenario_11_unrelated_approved_control_mapping_does_not_activate_platform_example` | **PASSED** |
| **Scenario 12** | Pending and rejected clauses gated from confirmed findings | `test_scenario_12_pending_and_rejected_clauses_gated` | **PASSED** |
| **Scenario 13** | Approved unmapped requirements remain traceable | `test_scenario_13_approved_unmapped_requirements_remain_traceable` | **PASSED** |
| **Scenario 14** | AUD 500 enterprise vs AUD 1,000 use case detects applicable discrepancy | `test_scenario_14_aud_500_enterprise_vs_1000_usecase_detects_applicable_discrepancy` | **PASSED** |
| **Scenario 15** | Cross-tenant access is rejected (HTTP 404) | `test_scenario_15_cross_tenant_access_rejected` | **PASSED** |
| **Scenario 16** | Baseline snapshot integrity and versioning preserved | `test_scenario_16_baseline_snapshot_integrity_and_versioning_preserved` | **PASSED** |
| **Scenario 17** | No silent fallback occurs on baseline resolution failure | `test_scenario_17_no_silent_fallback_occurs` | **PASSED** |

### Group 3: Baseline Eligibility & Compilation (Scenarios 18–21)

| Scenario | Description | Test Function | Result |
|:---|:---|:---|:---|
| **Scenario 18** | Empty policy lists cannot produce eligible active baselines (HTTP 422) | `test_scenario_18_empty_policy_lists_cannot_produce_eligible_active_baselines` | **PASSED** |
| **Scenario 19** | Wholly unapproved content compiles as draft | `test_scenario_19_wholly_unapproved_content_cannot_become_eligible` | **PASSED** |
| **Scenario 20** | Draft baselines cannot be selected for confirmed assessments (HTTP 400) | `test_scenario_20_draft_baselines_cannot_be_selected_for_confirmed_assessment` | **PASSED** |
| **Scenario 21** | Approved enterprise requirements represented without forced canonical mappings | `test_scenario_21_approved_enterprise_requirements_without_forced_canonical_mappings` | **PASSED** |

### Group 4: Compatibility and Security (Scenarios 22–28)

| Scenario | Description | Test Function | Result |
|:---|:---|:---|:---|
| **Scenario 22** | Generic XLSX importer from PR #22 remains functional | `test_scenario_22_generic_xlsx_importer_remains_functional` | **PASSED** |
| **Scenario 23** | No AIAF-specific behaviour is reintroduced | `test_scenario_23_no_aiaf_specific_behaviour_reintroduced` | **PASSED** |
| **Scenario 24** | Existing P0 and P1 questionnaire regression tests pass | `test_scenario_24_existing_p0_and_p1_questionnaire_regressions_pass` | **PASSED** |
| **Scenario 25** | Existing numeric and negation regression tests pass | `test_scenario_25_existing_numeric_and_negation_regressions_pass` | **PASSED** |
| **Scenario 26** | Historical library and baseline references remain auditable | `test_scenario_26_historical_library_and_baseline_references_auditable` | **PASSED** |
| **Scenario 27** | PostgreSQL and tenant isolation tests pass where executable | `test_scenario_27_tenant_isolation_tests_pass` | **PASSED** |
| **Scenario 28** | Research-only A0/A1 experiment code remains unchanged | `test_scenario_28_research_only_a0_a1_experiment_code_unchanged` | **PASSED** |

---

## Complete Test Suite Execution Log

### Dedicated Safety Suite
```
Command: pytest backend/tests/test_p1_safety_fix_a.py -v
Platform: Windows (Python 3.13.7, pytest-9.0.2)
Outcome: 28 passed, 1 warning in 2.31s
```

### Full Backend Suite
```
Command: pytest backend -q
Platform: Windows (Python 3.13.7, pytest-9.0.2)
Outcome: 166 passed, 17 skipped, 34 warnings in 9.56s
Failures: 0
```

### Skipped Tests Note
The 17 skipped tests correspond exclusively to optional live PostgreSQL container connectivity checks (`pytest.mark.skipif(not live_postgres_available)`), which gracefully skip when executing in ephemeral in-memory test environments. All ephemeral store tests pass 100%.
