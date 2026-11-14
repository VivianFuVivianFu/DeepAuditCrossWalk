# DeepAudit Crosswalk — E1 Requirement Reconciliation Validation Results

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Branch:** `feat/enterprise-requirement-reconciliation`  
**Base Commit:** `c91e17df08756569e355de388bb350bf2e670203` (PR #30)  
**Priority:** P1 — Core Product Capability

---

## 1. Executive Summary

The **Enterprise Requirement Reconciliation Engine (E1)** and **Effective Assessment Baseline Composition Service** have been implemented and verified across:

- **28 Mandatory Adversarial Scenarios** (`backend/tests/test_e1_requirement_reconciliation.py`)
- **Synthetic Development & Held-Out Evaluation Benchmark** (`test_e1_evaluation_benchmark_dev_and_held_out_splits`)
- **Relational Persistence & PostgreSQL 16 Row-Level Security (RLS)** (`backend/tests/test_repository.py`, Alembic migration `0003_enterprise_reconciliation`)
- **Full Backend Regression Suite** (`249 passed` with PostgreSQL 16 enabled)
- **Full Frontend Security & Workspace Gateway Suite** (`77 passed` across 5 Vitest test files + Next.js production build)

Zero false equivalences (`0.0%`), zero false conflicts (`0.0%`), and `100.0%` source/version traceability were achieved on both the development and held-out benchmark splits.

---

## 2. Evaluation Benchmark Results (Section 11)

The evaluation benchmark in `backend/tests/test_e1_requirement_reconciliation.py::test_e1_evaluation_benchmark_dev_and_held_out_splits` tests two strictly separated synthetic Australian financial services policy sets (Development split and Held-Out test split).

### 2.1 Quantitative Metrics

| Metric | Development Split ($N = 8$) | Held-Out Test Split ($N = 8$) | Combined ($N = 16$) | Target / Gate |
| --- | --- | --- | --- | --- |
| **Relationship Classification Accuracy** | `100.0%` (8/8) | `100.0%` (8/8) | `100.0%` (16/16) | $\ge 95.0\%$ |
| **Precision (Macro across classes)** | `100.0%` | `100.0%` | `100.0%` | $\ge 95.0\%$ |
| **Recall (Macro across classes)** | `100.0%` | `100.0%` | `100.0%` | $\ge 95.0\%$ |
| **False Equivalence Rate** | **`0.0%`** (0/8) | **`0.0%`** (0/8) | **`0.0%`** (0/16) | **`0.0%` (Hard Gate)** |
| **False Conflict Rate** | `0.0%` (0/8) | `0.0%` (0/8) | `0.0%` (0/16) | $\le 5.0\%$ |
| **Unresolved / Needs-Review Surfacing Rate** | `100.0%` (all conflicts, weaker, proposed-mapping, and undetermined items flagged) | `100.0%` | `100.0%` | `100.0%` |
| **Source & Version Traceability Completeness** | `100.0%` (8/8) | `100.0%` (8/8) | `100.0%` (16/16) | `100.0%` |

### 2.2 Per-Case Breakdown

#### Development Split
| Case ID | Enterprise Clause Summary | External Obligation | Ground Truth | Stage B Validated Output | Status |
| --- | --- | --- | --- | --- | --- |
| `dev_exact_equivalent_app1` | Assigns accountable privacy owner, implements privacy by design, maintains current privacy policy (all 3 facets approved) | `AU-PRIV-APP1-GOV` | `equivalent` | `equivalent` (`decision_status=proposed`) | PASS |
| `dev_partial_app1_single_facet` | Publishes current privacy policy only (`privacy_policy_current`) | `AU-PRIV-APP1-GOV` | `partially_overlapping` | `partially_overlapping` | PASS |
| `dev_stricter_aud_500_vs_1000` | Pre-execution Authorised Officer approval above `AUD 500` | `SYN-OB-1000` (`> AUD 1,000`) | `stricter_enterprise_requirement` | `stricter_enterprise_requirement` | PASS |
| `dev_weaker_aud_5000_vs_1000` | Pre-execution Authorised Officer approval above `AUD 5,000` | `SYN-OB-1000` (`> AUD 1,000`) | `weaker_or_potentially_insufficient` | `weaker_or_potentially_insufficient` | PASS |
| `dev_conflict_exempt_app8` | Cross-border AI prompts "do not require APP 8 contractual safeguards" | `AU-PRIV-APP8-CROSSBORDER` | `potential_conflict` | `potential_conflict` | PASS |
| `dev_additional_enterprise_only` | Log delegated financial authority checks in 10-year Treasury Ledger | `None` | `additional_enterprise_requirement` | `additional_enterprise_requirement` | PASS |
| `dev_unmapped_indigenous_dialect` | First Nations acoustic dialect consultation prior to regional voice model curation | `None` | `unmapped_no_reliable_relationship` | `unmapped_no_reliable_relationship` | PASS |
| `dev_undetermined_usd_currency` | Pre-execution Authorised Officer approval above `USD 500` | `SYN-OB-1000` (`AUD`) | `undetermined` | `undetermined` (`needs_review`) | PASS |

#### Held-Out Test Split
| Case ID | Enterprise Clause Summary | External Obligation | Ground Truth | Stage B Validated Output | Status |
| --- | --- | --- | --- | --- | --- |
| `ho_equivalent_app8_full` | Maps overseas regions, implements APP 8 contracts, assesses s 16C accountability prior to disclosure | `AU-PRIV-APP8-CROSSBORDER` | `equivalent` | `equivalent` (`decision_status=proposed`) | PASS |
| `ho_operator_boundary_gt_vs_gte_500` | Approval required `> AUD 500` vs external `>= AUD 500` | `SYN-OB-GTE-500` | `weaker_or_potentially_insufficient` | `weaker_or_potentially_insufficient` | PASS |
| `ho_stricter_cps234_24h_notification` | Material AI security incidents notified to APRA within `24 hours` (vs statutory `72 hours`) | `AU-APRA-CPS234-INCIDENT` | `stricter_enterprise_requirement` | `stricter_enterprise_requirement` | PASS |
| `ho_conflict_cps234_14_days` | Material AI security incidents notified to APRA within `14 days` (exceeding `72 hours`) | `AU-APRA-CPS234-INCIDENT` | `potential_conflict` | `potential_conflict` | PASS |
| `ho_weaker_exception_clause` | Full APP 1 facets covered, "unless waived by a line manager" | `AU-PRIV-APP1-GOV` | `weaker_or_potentially_insufficient` | `weaker_or_potentially_insufficient` | PASS |
| `ho_conditional_partial` | "Where customer data exceeds 50,000 records", apply APP 1 governance | `AU-PRIV-APP1-GOV` | `partially_overlapping` | `partially_overlapping` | PASS |
| `ho_ambiguous_schedule_reference` | "Appropriate governance arrangements shall be applied as determined from time to time in accordance with Schedule B" | `AU-PRIV-APP1-GOV` | `undetermined` | `undetermined` (`needs_review`) | PASS |
| `ho_proposed_mapping_not_equivalent` | Approved clause covering all APP 1 facets, but `ClauseControlMapping` is still `proposed` | `AU-PRIV-APP1-GOV` | `partially_overlapping` | `partially_overlapping` (`needs_review`) | PASS |

---

## 3. Mandatory 28-Scenario Adversarial Verification Matrix

All 28 mandatory adversarial scenarios in `backend/tests/test_e1_requirement_reconciliation.py` pass:

| # | Test Function | Verified Guarantee | Status |
| --- | --- | --- | --- |
| 1 | `test_scenario_01_same_control_id_different_obligations_not_equivalent` | Shared `control_id` (`CTRL-PRIV-GOVERNANCE`) never establishes equivalence across distinct obligations (`AU-PRIV-APP1-GOV`, `AU-OAIC-APPG-CH1-PIA`) | PASS |
| 2 | `test_scenario_02_stricter_enterprise_threshold_aud_500_vs_1000` | `AUD 500` approval gate vs `AUD 1,000` classified as `stricter_enterprise_requirement` | PASS |
| 3 | `test_scenario_03_weaker_enterprise_threshold_aud_5000_vs_1000` | `AUD 5,000` approval gate vs `AUD 1,000` classified as `weaker_or_potentially_insufficient` | PASS |
| 4 | `test_scenario_04_threshold_operator_mismatch_gt_vs_gte_500` | `> AUD 500` vs `>= AUD 500` detects boundary gap at exact `AUD 500` | PASS |
| 5 | `test_scenario_05_currency_mismatch_aud_500_vs_usd_500` | `USD 500` vs `AUD 500` classified as `undetermined` (`currency_mismatch`) | PASS |
| 6 | `test_scenario_06_different_transaction_scope_refunds_vs_credit_decisions` | Refund reimbursement clause vs NCCP credit suitability obligation flagged as `scope_match="mismatch"` | PASS |
| 7 | `test_scenario_07_different_approval_actors` | Senior Manager vs Authorised Officer (`different_actor`) vs Dual Approval (`stricter_actor`) | PASS |
| 8 | `test_scenario_08_pre_execution_vs_post_execution_review` | Post-execution review against pre-execution requirement classified as `weaker_or_potentially_insufficient` | PASS |
| 9 | `test_scenario_09_conditional_enterprise_requirement` | Conditional trigger (`> 100,000 records`) classified as `partially_overlapping` | PASS |
| 10 | `test_scenario_10_exception_clause_weakening_requirement` | Business-unit waiver carve-out classified as `weaker_or_potentially_insufficient` | PASS |
| 11 | `test_scenario_11_negative_obligation_must_not_vs_does_not_require` | Protective prohibition (`must not`) $\rightarrow$ `stricter_enterprise_requirement`; exemption (`does not require`) $\rightarrow$ `potential_conflict` | PASS |
| 12 | `test_scenario_12_additional_enterprise_requirement_no_external_equivalent` | Enterprise-only control (`10-year immutable ledger`) classified as `additional_enterprise_requirement` | PASS |
| 13 | `test_scenario_13_unmapped_approved_enterprise_clause_preserved` | Unmapped approved clause classified as `unmapped_no_reliable_relationship` and retained in Effective Baseline | PASS |
| 14 | `test_scenario_14_proposed_vs_approved_enterprise_clause` | Proposed enterprise clause excluded from active reconciliation and Effective Baseline | PASS |
| 15 | `test_scenario_15_rejected_enterprise_clause_excluded` | Rejected enterprise clause excluded from reconciliation and Effective Baseline | PASS |
| 16 | `test_scenario_16_proposed_vs_approved_control_mapping` | Unapproved (`proposed`) control mapping prevents `equivalent` classification | PASS |
| 17 | `test_scenario_17_superseded_enterprise_policy_version` | Superseding a policy marks prior reconciliation decisions `is_stale=True` | PASS |
| 18 | `test_scenario_18_external_regulatory_pack_version_update` | Updating `regulatory_pack.version` (`0.1.0` $\rightarrow$ `0.2.0`) marks prior decisions stale and moves them to `unresolved_items` | PASS |
| 19 | `test_scenario_19_applicable_vs_non_applicable_external_obligation` | Non-applicable obligations (`EU-AIA-ART2-HIGH-RISK`, `ISO42001-AIMS-ORG`) excluded from active requirements and recorded in `applicability_summary` | PASS |
| 20 | `test_scenario_20_voluntary_framework_vs_binding_obligation` | Voluntary framework (`ISO42001-AIMS-ORG`, `is_legally_binding=False`) never conflated with binding statute (`AU-APRA-CPS220-RMF`, `is_legally_binding=True`) | PASS |
| 21 | `test_scenario_21_enterprise_policy_vs_statutory_law_authority_distinction` | Enterprise requirements carry `authority_classification="enterprise_policy"` and `is_legally_binding=False` | PASS |
| 22 | `test_scenario_22_duplicate_requirement_across_two_enterprise_policies` | Duplicate clauses across two enterprise policies retain both policy `source_references` | PASS |
| 23 | `test_scenario_23_conflict_between_two_enterprise_policies` | Conflicting thresholds across two internal policies (`AUD 1,000` vs `AUD 500`) generate a `peer_enterprise_clause_id` `potential_conflict` | PASS |
| 24 | `test_scenario_24_conflict_between_enterprise_policy_and_external_obligation` | `14-day` incident notification vs CPS 234 `72-hour` rule surfaced in `potential_conflicts` while retaining binding CPS 234 obligation | PASS |
| 25 | `test_scenario_25_ambiguous_clause_requires_undetermined` | Vague clause ("as determined from time to time in accordance with Schedule C") classified as `undetermined` | PASS |
| 26 | `test_scenario_26_unauthorised_role_blocked_from_approving_reconciliation` | `viewer` and `analyst` blocked with `403 Forbidden`; `reviewer` authorised (`200 OK`) | PASS |
| 27 | `test_scenario_27_cross_tenant_isolation_on_reconciliation_and_effective_baseline` | Cross-tenant read/review/compose attempts return `404`; `public-demo` returns `403` | PASS |
| 28 | `test_scenario_28_deterministic_reproduction_of_effective_assessment_baseline` | Repeated calls produce identical `effective_baseline_sha256`, `effective_baseline_id`, `requirements`, and `presentation_groups` | PASS |

---

## 4. Persistence, Migration & Security Verification

- **Alembic Migration `0003_enterprise_reconciliation`**:
  - Creates `reconciliation_decisions` and `effective_baselines` tables.
  - Enforces composite `(tenant_id, object_id)` primary keys and `(tenant_id, baseline_id)` indexes.
  - Enables `ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` on PostgreSQL with `tenant_isolation` policies bound to `current_setting('app.current_tenant', true)`.
- **Verified in `backend/tests/test_repository.py`**:
  - `test_sql_store_persists_enterprise_policy_baseline_reconciliation_and_effective_baseline` (SQLite)
  - `test_postgres_rls_enforces_tenant_isolation_and_alembic_roundtrip` (PostgreSQL 16)
- **Non-Goals & Invariants Preserved**:
  - `P1_EVALUATION_DATASET_V2.json` and `run_p1_experiments.py` remain untouched (`test_scenario_28_research_only_a0_a1_experiment_code_unchanged` passes).
  - No AIAF-specific dependencies were reintroduced.
  - Existing Questionnaire Coverage Engine (`coverage.py`) confirmed coverage rules remain intact.
