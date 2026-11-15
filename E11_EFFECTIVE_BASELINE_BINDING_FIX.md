# DeepAudit Crosswalk — E1.1 Effective Assessment Baseline Binding Fix & Assessment Integration Contract

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Target Branch:** `fix/e11-effective-baseline-accuracy-integration`  
**Modified Modules:**  
- [backend/banking_crosswalk/reconciliation.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/reconciliation.py)  
- [backend/banking_crosswalk/coverage.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/coverage.py)  
- [backend/banking_crosswalk/api.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py)  
- [backend/banking_crosswalk/models.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py)  
- [web/app/api/workspace/route.ts](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web/app/api/workspace/route.ts)

---

## 1. Root Cause Fixed: Elimination of `eff_baselines[-1]` Auto-Attachment

Previously, `POST /v1/assessments/coverage` in [backend/banking_crosswalk/api.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py) automatically attached `eff_baselines[-1]` (whichever `EffectiveAssessmentBaseline` happened to appear last in the store for `enterprise_baseline_id`) whenever an assessment ran in `enterprise_enhanced` or `provisional` mode.

In E1.1:

- **Blind attachment is completely removed.** If the caller does not explicitly supply `effective_baseline_id`, the assessment sets `effective_baseline_id = None`, `effective_baseline_sha256 = None`, `effective_baseline_binding_mode = "not_bound"`, and `assessment_basis = "regulatory_pack_plus_enterprise_baseline"` (for `enterprise_enhanced` / `provisional`) or `"regulatory_pack_only"`.
- **When `effective_baseline_id` is supplied in `regulatory_only` mode**, both the Next.js workspace gateway ([web/app/api/workspace/route.ts](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web/app/api/workspace/route.ts)) and backend API ([backend/banking_crosswalk/api.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/api.py)) reject the request with **HTTP 400 Bad Request**.
- **When `effective_baseline_id` is supplied in `enterprise_enhanced` / `provisional` mode**, it is loaded scoped strictly to `x_tenant_id` (`404 Not Found` if missing or cross-tenant) and passed to `validate_effective_baseline_for_assessment()`, failing closed with **HTTP 409 Conflict** on any context/staleness/version mismatch or **HTTP 422 Unprocessable Entity** on cryptographic fingerprint tampering.

---

## 2. The 8-Property Deterministic Binding Validation Contract

`validate_effective_baseline_for_assessment()` in [backend/banking_crosswalk/reconciliation.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/reconciliation.py) enforces all eight invariants before an `EffectiveAssessmentBaseline` can bind to a `CoverageAssessment`:

| # | Binding Property | Validation Rule | Failure Status | Verified By Test |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Tenant ID** | `effective_baseline.tenant_id == tenant_id` (plus tenant-scoped store lookup / PostgreSQL RLS) | `404` / `409` | `test_e11_01`, `test_scenario_27` |
| **2** | **Enterprise Baseline ID** | `effective_baseline.enterprise_baseline_id == enterprise_baseline.baseline_id` (and error if baseline omitted when expected) | `409` | `test_e11_04` |
| **3** | **Version & Revision** | Matches both `enterprise_baseline.version` and `enterprise_baseline.revision` | `409` | `test_e11_04` |
| **4** | **SHA-256 Fingerprints** | Recomputes canonical payload hash (`verify_effective_baseline_integrity`), checks `enterprise_baseline.baseline_sha256 == effective_baseline.enterprise_baseline_sha256`, and validates optional caller pin `expected_effective_baseline_sha256` | `422` (tampered) / `409` (mismatch) | `test_e11_05` |
| **5** | **Regulatory Pack Version** | Matches both `regulatory_pack.pack_id` and `regulatory_pack.version` | `409` | `test_e11_03` |
| **6** | **Applicability Context (`use_case`)** | Validates `use_case_id`, all 25 fields in `APPLICABILITY_PROFILE_FIELDS` against `effective_baseline.use_case_snapshot`, `applicable_external_obligation_ids`, and `applicability_summary` | `409` | `test_e11_02` |
| **7** | **Assessment Date (`as_of_date`)** | When caller supplies `as_of_date`, validates exact equality with `effective_baseline.as_of_date` | `409` | `test_e11_06` |
| **8** | **Reconciliation Decisions & Staleness** | Fails if `stale_reconciliation_ids` is non-empty, if any stored decision has become stale via `evaluate_reconciliation_staleness()` (including superseded policies or changed clause hashes), or if `approved_reconciliation_ids` diverges from the current set of approved non-conflict decisions in the store | `409` | `test_e11_07` |

---

## 3. Assessment Basis & Coverage Integration Semantics

### 3.1 Explicit `assessment_basis` & `effective_baseline_binding_mode` Fields

`CoverageAssessment` ([backend/banking_crosswalk/models.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/models.py)) now exposes:

- `assessment_basis`:
  - `"regulatory_pack_only"` — Standard regulatory baseline without enterprise overlay.
  - `"regulatory_pack_plus_enterprise_baseline"` — Enterprise Baseline selected without a bound `EffectiveAssessmentBaseline`.
  - `"effective_assessment_baseline"` — Explicitly bound and validated `EffectiveAssessmentBaseline`.
- `effective_baseline_binding_mode`:
  - `"not_bound"` or `"explicit_validated_effective_baseline"`.
- `reconciled_equivalence_group_ids`: Lists `GRP-EQ-*` presentation group IDs established by human-approved `equivalent` reconciliations.
- `unresolved_reconciliation_ids`: Lists all unresolved reconciliation IDs from `effective_baseline.unresolved_items`.
- `reconciliation_conflict_gaps`: Dedicated list of `GapRecord` items (`gap_type=GapType.CONTROL_CONFLICT`, `source_type="reconciliation_conflict"`) materialized into `gaps` and `enterprise_gaps` for every `potential_conflict` and `weaker_or_potentially_insufficient` reconciliation item.

### 3.2 Preservation of Coverage Safety Rules

Binding an `EffectiveAssessmentBaseline` (`test_e11_09` & `test_e11_10`) guarantees:

1. **Zero Silent External Obligation Deletion:** Every applicable external `AtomicObligation` remains in `CoverageAssessment.results` even when linked to an approved `equivalent` enterprise clause via a `reviewed_equivalence_group`.
2. **Zero Confirmed Coverage Inflation:** An approved enterprise policy equivalence group or questionnaire keyword similarity **never** marks a regulatory obligation as confirmed `COVERED`. Regulatory `confirmed_covered` counts remain strictly governed by human-approved `MappingDecision` records (`ReviewStatus.APPROVED`).
3. **Excluded Clauses Stay Excluded:** Enterprise clauses excluded from the `EffectiveAssessmentBaseline` (`excluded_enterprise_clause_ids`, rejected/superseded) do not contribute to active enterprise requirements in the assessment.
4. **Workspace Gateway Parity:** [web/app/api/workspace/route.ts](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/web/app/api/workspace/route.ts) validates and forwards `effective_baseline_id`, `effective_baseline_sha256`, and `as_of_date` on `assess_coverage` / `run_coverage_assessment` calls while blocking `effective_baseline_id` in `regulatory_only` mode.
