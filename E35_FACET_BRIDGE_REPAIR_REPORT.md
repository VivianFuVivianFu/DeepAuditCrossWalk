# DeepAudit Crosswalk — E3.5 Canonical Facet Bridge Repair Report

**Document ID**: `DEEPAUDIT-E35-FACET-BRIDGE-REPAIR-V1`  
**Version**: `1.0.0`  
**Regulatory Pack Baseline**: `AU-BANKING-REG-PACK-0.1` v`0.2.0` (33 Unified Controls, 158 Canonical Facets, 46 Obligations)  
**Working Branch**: `fix/e35-normative-evidence-assurance`  
**Status**: COMPLETE & VERIFIED IN CI  

---

## 1. Context & Architectural Root Cause

Following the migration to Regulatory Pack v0.2.0 (PR #40), the canonical Unified Control Library (UCL) established a mathematically validated set of **158 unique canonical control facets** across 33 unified controls and 11 governance domains.

However, an audit of `backend/banking_crosswalk/reconciliation.py` revealed that `GENERIC_TO_CANONICAL_FACET_BRIDGES` still referenced legacy string identifiers from pre-v0.2.0 draft taxonomies. Because these obsolete identifiers never matched any canonical facet in `atomic_obligation_catalogue.json`, clauses relying on generic heuristic bridges failed candidate retrieval or produced unmapped determinations despite valid enterprise controls.

Furthermore, a defect was identified in `reconciliation.py` where a leading space was present in `" approval_logs_retained"`, breaking exact string lookups.

---

## 2. Purge of Retired Pre-v0.2.0 Facets

Six obsolete facets that no longer exist in Regulatory Pack v0.2.0 were formally audited and purged from active bridges:

1. `human_oversight_and_override_defined` — Replaced in v0.2.0 by `meaningful_human_oversight_and_kill_switch` and `human_approval_required`.
2. `human_oversight_for_high_risk` — Replaced by `deployer_human_oversight_assigned` and `pre_execution_block`.
3. `adverse_impact_intervention_mechanism` — Replaced by `customer_contestability_and_recourse_pathway`.
4. `bias_and_fairness_testing` — Replaced by `fairness_and_explainability_metrics_evaluated` (under NIST AI RMF MEASURE and EU AI Act).
5. `ai_inventory_and_classification` — Replaced by `ai_assets_classified_by_criticality_and_sensitivity`.
6. `ai_use_case_register_maintained` — Replaced by `use_case_registered_in_enterprise_ai_inventory` (under ASIC REP 798).

---

## 3. Active Canonical Facet Bridges Specification

Active bridges in `backend/banking_crosswalk/reconciliation.py` were re-anchored strictly to valid v0.2.0 canonical facets:

```python
GENERIC_TO_CANONICAL_FACET_BRIDGES: Dict[str, Tuple[str, ...]] = {
    "zero_data_retention": (
        "destruction_or_deidentification_verified",
        "retention_schedule_applied",
    ),
    "data_sovereignty": (
        "overseas_recipients_and_regions_mapped",
    ),
    "bias_testing": (
        "fairness_and_explainability_metrics_evaluated",
    ),
    "model_inventory": (
        "use_case_registered_in_enterprise_ai_inventory",
        "ai_assets_classified_by_criticality_and_sensitivity",
    ),
    "prompt_logging": (
        "approval_logs_retained",
        "incident_detection_defined",
    ),
}
```

### Production Wiring in `policy.py`:
- `approval_logs_retained` was wired into `ENTERPRISE_FACET_PATTERNS` with keywords: `("approval log", "approval logs", "audit log", "audit logs", "record approval", "retain approval", "approval record", "traceability log")`.
- `approval_logs_retained` was mapped in `FACET_TO_UNIFIED_CONTROLS` to `("CTRL-FIN-APPROVAL-THRESHOLDS", "CTRL-DELEGATED-AUTHORITY-THRESHOLD")`.

---

## 4. Quality & Compliance Audit Results

The canonical bridge integrity test `test_e35_phase1_canonical_facet_bridge_integrity` was executed:
- **Canonical Facet Count**: Verified dynamically from `UNIFIED_CONTROL_LIBRARY.json` (`len(canonical_facet_ids) == 158`).
- **Target Inclusion**: 100% of bridge target strings exist in the canonical 158 facets.
- **Retired Strings**: Zero retired pre-v0.2.0 facets exist in any bridge tuple.
- **Whitespace Hygiene**: Zero leading or trailing whitespace characters exist in any bridge target.
- **Backward Compatibility**: All 300 backend tests and 25 experiment tests pass without degradation.
