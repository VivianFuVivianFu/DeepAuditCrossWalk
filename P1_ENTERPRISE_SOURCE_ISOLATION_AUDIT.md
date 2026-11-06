# P1 Enterprise Source Isolation Audit

## Executive Summary

This audit documents the final architectural source isolation and baseline hardening implemented under **Prompt P1 Safety Fix A** for the **DeepAudit Crosswalk** platform.

Prior to this fix, an architectural flaw existed wherein a synthetic internal enterprise requirement (`ENT-AI-DELEGATED-APPROVAL` under source `ENTERPRISE-AI-STD`) was embedded directly into the active Shared Regulatory Library. This created severe multi-tenant contamination risks, false-coverage assumptions, and potential breach of regulatory auditability standards.

Under PR #22, AIAF dependencies were removed and general questionnaire importation was introduced. This safety fix completes the boundary hardening by establishing strict, deterministic isolation between:
1. **Shared Regulatory Library:** External legal, regulatory, and supervisory guidance maintained by the platform.
2. **Enterprise Internal Baseline:** Tenant-owned, explicitly uploaded, reviewed, approved, and versioned governance standards.
3. **Assessment Targets:** Questionnaires and strategy documents submitted for gap assessment.

---

## Detailed Analysis of Pre-Change Architectural Risks (Risks A–F)

### Risk A: Preconfigured Enterprise Obligation Contaminating Shared Library
* **Issue:** Source `ENTERPRISE-AI-STD` and atomic obligation `ENT-AI-DELEGATED-APPROVAL` were packaged within `regulatory_pack.v0.1.json`, `atomic_obligation_catalogue.json`, `regulatory_source_register.csv`, and `obligation_control_mappings.json`.
* **Impact:** Every tenant performing an assessment—even in Regulatory-Only mode—implicitly had a synthetic internal delegated authority obligation in the obligation catalogue. A platform-defined standard was imposed as if it were a universally binding Australian law.
* **Remediation:** Completely expunged `ENTERPRISE-AI-STD` and `ENT-AI-DELEGATED-APPROVAL` from active regulatory catalogues. Preserved Canonical Controls `CTRL-HUMAN-OVERSIGHT` and `CTRL-DELEGATED-AUTHORITY-THRESHOLD` in `UNIFIED_CONTROL_LIBRARY.json` with self-contained facet and evidence definitions.

### Risk B: Default Assessment Mode Ambiguity & Enterprise Threshold Leakage
* **Issue:** If `assessment_mode` was omitted or `None`, or if a tenant had configured an enterprise baseline, assessments could inadvertently evaluate internal thresholds or leak enterprise obligations into regulatory findings.
* **Impact:** Regulatory audits could produce false-positive or false-negative compliance conclusions contaminated by tenant policy assumptions.
* **Remediation:** Enforced ADR 0003 invariant:
  - If `assessment_mode` is omitted or `None`, it **strictly resolves to `regulatory_only`**.
  - In `regulatory_only` mode, `enterprise_baseline` is strictly set to `None`, and passing `enterprise_baseline_id` in API requests is rejected with **HTTP 400 Bad Request**.
  - Internal approval thresholds (e.g., AUD 1,000 use case threshold) never activate enterprise obligations in Mode A.

### Risk C: Premature Baseline Activation (Empty & Wholly Unreviewed Content)
* **Issue:** Baseline compilation allowed empty policy lists or policies where all clauses were in `proposed` (unapproved) review status to compile as active baselines.
* **Impact:** Ineligible or unvetted internal policies could be selected for confirmed assessments, violating governance review controls.
* **Remediation:**
  - Empty policy lists raise `ValueError("Cannot compile an active baseline from empty policy input")` and API returns **HTTP 422 Unprocessable Content**.
  - Content with zero approved clauses compiles with `status="draft"` and explicit warning metadata.
  - Draft baselines are strictly barred from selection in `enterprise_enhanced` mode (rejected with **HTTP 400 Bad Request** / `ValueError`).

### Risk D: Silent Fallback and Mode Failure Concealment
* **Issue:** If an Enterprise Baseline could not be resolved or was invalid in Enterprise-Enhanced mode, previous fallback paths might have silently reverted to Regulatory-Only assessment without alerting the operator.
* **Impact:** Tenants expecting an enterprise-enhanced assessment would receive an incomplete regulatory-only report without noticing the failure.
* **Remediation:** Hardened API and coverage engine so that any baseline resolution failure in `enterprise_enhanced` mode (missing baseline, draft status, cross-tenant attempt, tampered fingerprint) fails closed immediately with descriptive HTTP status codes (**400**, **404**, or **422**). Silent fallback is strictly prohibited.

### Risk E: Inappropriate Voluntary Framework Assumptions
* **Issue:** Default use cases (such as `BankingUseCase.enterprise_baseline()`) previously had voluntary framework flags (e.g., NIST AI RMF, ISO 42001) defaulting to `False` or ambiguous values, causing potential misinterpretation of voluntary standard adoption.
* **Impact:** In Australian financial services assurance, voluntary standards must not be treated as adopted merely because context is missing (`unknown != adopted`).
* **Remediation:** Updated `BankingUseCase.enterprise_baseline()` to default all voluntary framework fields (`nist_ai_rmf_adopted`, `au_ai_guidance_adopted`, `iso_42001_adopted`, `iso_23894_adopted`, `iso_27001_adopted`) to `None`. In Mode A, unknown status guarantees that voluntary framework obligations are never marked applicable.

### Risk F: Forced Canonical Control Mapping for Custom Enterprise Requirements
* **Issue:** Enterprise-specific requirements (e.g., bespoke AI ethics committees or specific departmental reviews) were previously at risk of being discarded if they could not be mapped to an existing Canonical Control.
* **Impact:** Loss of tenant-specific policy traceability and pressure to distort canonical taxonomies.
* **Remediation:** Supported unmapped approved requirements (`is_unmapped=True`, `control_mappings=[]`). The engine tracks them in `unmapped_clause_ids` and evaluates them in `applicable_enterprise_requirement_ids` without forcing synthetic canonical mappings.

---

## Reproducibility & Remediation Verification Table

| Risk Identifier | Pre-Fix Condition | Post-Fix Behavior | Automated Verification Scenario |
|:---|:---|:---|:---|
| **Risk A: Preconfigured Obligation** | `ENT-AI-DELEGATED-APPROVAL` in active pack | Expunged; zero occurrences | `test_scenario_5`, `test_scenario_11` |
| **Risk B: Mode Default & Isolation** | Omitted mode could blend thresholds | Mode defaults to `regulatory_only`; baseline rejected | `test_scenario_1`, `test_scenario_2`, `test_scenario_3`, `test_scenario_6` |
| **Risk C: Premature Baseline** | Empty or unreviewed compiled as active | Empty rejected (422); unreviewed compiles as draft; draft rejected (400) | `test_scenario_18`, `test_scenario_19`, `test_scenario_20` |
| **Risk D: Silent Fallback** | Possible silent degradation | Fails closed (400/404/422); zero silent fallback | `test_scenario_9`, `test_scenario_15`, `test_scenario_17` |
| **Risk E: Voluntary Frameworks** | Unknown treated as evaluated | Default context leaves flags `None`; voluntary obligations inactive | `test_scenario_7` |
| **Risk F: Unmapped Requirements** | Requirement lost without control ID | Preserved in `unmapped_clause_ids` and evaluated in findings | `test_scenario_13`, `test_scenario_21` |

---

## Conclusion

The architecture now rigorously enforces the three-way isolation between platform regulatory standards, tenant-owned governance baselines, and assessment targets. The implementation passes all automated regression suites and fulfills the security and governance requirements of Australian financial institutions.
