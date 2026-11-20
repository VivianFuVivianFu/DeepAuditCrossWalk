# P1B Engine A1 v0.2.0 Compatibility & Protective Prohibition Audit Report

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Stage:** Stage A — P1B Taxonomy Compatibility & Experimental Engine Repair  
**Branch:** `fix/p1b-taxonomy-v02-alignment`  
**Component:** [`scripts/experiments/engine_a1.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/scripts/experiments/engine_a1.py) & [`scripts/experiments/test_engine_a1.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/scripts/experiments/test_engine_a1.py)  

---

## 1. Root Cause of Historical EngineA1 Failures on Regulatory Pack v0.2.0

Prior to Stage A, all 5 unit tests in `scripts/experiments/test_engine_a1.py` failed during `EngineA1.__init__()` with:

```text
AssertionError: Facet security_controls_defined not in UCL
```

### Forensic Audit Findings in `EngineA1`

1. **Retired Facet Reference & Cross-Control Misassignment (`security_controls_defined`)**:
   - `EngineA1.FACET_REGEX_PATTERNS` and `EngineA1.FACET_TO_CANONICAL_CONTROL` referenced `security_controls_defined`, which was retired in E4.1 (PR #38) and decomposed into `technical_security_measures_implemented` and `organisational_security_measures_implemented` under `CTRL-PRIV-SECURITY-RETENTION`.
   - Furthermore, historical `EngineA1` had misassigned `security_controls_defined` to `CTRL-SEC-COMMENSURATE` (APRA CPS 234 information security capability) rather than its actual UCL parent control `CTRL-PRIV-SECURITY-RETENTION` (Privacy Act APP 11 security & retention).
2. **Parent-Control Mismatches in `FACET_TO_CANONICAL_CONTROL`**:
   - Auditing all 38 historical `EngineA1.FACET_TO_CANONICAL_CONTROL` entries against `UNIFIED_CONTROL_LIBRARY.json` revealed two additional parent-control discrepancies:
     - `approval_logs_retained` was mapped to `CTRL-PRIV-SECURITY-RETENTION` instead of its UCL parent control `CTRL-DELEGATED-AUTHORITY-THRESHOLD` (causing false negatives on `P1-095` and `P1-104`).
     - `human_approval_required` was mapped to `CTRL-HUMAN-OVERSIGHT` instead of its UCL parent control `CTRL-DELEGATED-AUTHORITY-THRESHOLD`, while `CTRL-HUMAN-OVERSIGHT`'s own UCL facets (`clear_escalation_and_override_authority`, `meaningful_human_oversight_and_kill_switch`) were omitted from `EngineA1`.
3. **Normative Modality Defect — Over-Suppression of Protective Prohibitions**:
   - Historical `EngineA1.classify_normative_modality()` used a flat syntactic regex (`PROHIBITION_ABSOLUTE_PATTERN`) and a hardcoded `"shall not proceed without" / "must not disburse"` rule to suppress **all** negative-polarity mandates.
   - As a result, genuine **protective prohibitions** (e.g., *"Personnel are strictly prohibited from transmitting unencrypted customer information over public networks"*, *"Consumer credit evaluation algorithms are strictly prohibited from collecting or processing sensitive data..."*, *"AI systems that deploy subliminal techniques... are strictly prohibited under Article 5"*) were discarded as suppressed non-candidates, while actual **anti-control prohibitions** (`P1-127`: *"Consumer credit scoring models shall not implement automated bias testing..."*) were NOT suppressed.

---

## 2. Remediations Implemented in `EngineA1`

### 2.1 Strict v0.2.0 Taxonomy & Parent-Control Validation
- Removed `security_controls_defined` and added distinct, non-conflated patterns for:
  - `technical_security_measures_implemented` $\rightarrow$ `CTRL-PRIV-SECURITY-RETENTION` (matches technical safeguards such as AES-256 encryption at rest, private tenant VPC isolation, cryptographic storage; does **not** infer organisational measures).
  - `organisational_security_measures_implemented` $\rightarrow$ `CTRL-PRIV-SECURITY-RETENTION` (matches organisational safeguards such as staff privacy training, documented information handling procedures, access review governance; does **not** infer technical measures).
- Added decomposed E4.1 `CTRL-EU-HIGH-RISK` facets:
  - `deployer_human_oversight_assigned` $\rightarrow$ `CTRL-EU-HIGH-RISK` (EU AI Act Art. 26(2))
  - `automatic_logs_retained_6months` $\rightarrow$ `CTRL-EU-HIGH-RISK` (EU AI Act Art. 26(6))
  - `synthetic_content_marking_and_disclosure_applied` $\rightarrow$ `CTRL-EU-HIGH-RISK` (EU AI Act Art. 50(2)–(4))
  - `article5_prohibited_practices_screened_out` $\rightarrow$ `CTRL-EU-HIGH-RISK` (EU AI Act Art. 5)
- Added `clear_escalation_and_override_authority` and `meaningful_human_oversight_and_kill_switch` $\rightarrow$ `CTRL-HUMAN-OVERSIGHT`, and aligned `human_approval_required` and `approval_logs_retained` with their exact UCL parent control `CTRL-DELEGATED-AUTHORITY-THRESHOLD`.
- Enforced an initialization invariant in `EngineA1.__init__()`: every facet in `FACET_TO_CANONICAL_CONTROL` must exist in `UNIFIED_CONTROL_LIBRARY.json` **and** map to its exact UCL parent control (`self.facet_to_ucl_control[f] == cid`).
- **Coverage Scope Note:** `EngineA1` now defines 44 targeted experimental facet pattern groups across 16 of the 33 Unified Controls (`31/158 = 19.62%` empirical coverage on the V2 Development split), confirming that deterministic rules alone cover only a subset of the 158 canonical facets.

### 2.2 Evidence-Preserving Normative Modality Classification (`normative_mode="revised"`)
`EngineA1.classify_normative_modality()` now distinguishes:

| Normative Modality (`detected_normative_type`) | Candidate Suppression (`should_suppress`) | Semantic Definition & Examples |
|---|---:|---|
| `protective_prohibition` | **`False` (Retained)** | Prohibitions or conditional gates that enforce a preventive security, privacy, or approval control (e.g., prohibiting unencrypted transmission, prohibiting sensitive data collection without consent, prohibiting local PII storage, pre-execution approval blocks, EU AI Act Art. 5 prohibited practice screening). |
| `control_prohibition` | **`True` (Suppressed)** | Clauses that forbid or disable performing a required governance, testing, logging, or notification control (e.g., `P1-127`: *"shall not implement automated bias testing"*, `SUPP-020`: *"forbidden from publicly disclosing security incidents or APRA notifications"*). |
| `unmapped_prohibition` | **`True` (Suppressed)** | Prohibitions outside the AI/banking control taxonomy (e.g., `SUPP-032` HR anti-retaliation employment clauses). |
| `control_waiver` | **`True` (Suppressed)** | Explicit waivers of governance controls (*"Dual human approval is waived for..."*). |
| `scope_exemption` | **`True` (Suppressed)** | Explicit scope exclusions (*"sandboxes are exempt from enterprise model registry registration"*). |
| `missing_implementation` | **`True` (Suppressed)** | Factual statements of unimplemented controls or statutory non-applicability (*"does not currently implement encryption"*, `P1-155` *"has zero EU AI Act compliance obligations"*). |
| `permissive_guidance` | **`True` (Suppressed)** | Optional/discretionary practices (*"may optionally request..."*). |
| `aspirational_statement` | **`True` (Suppressed)** | Non-binding vision statements (*"aims to champion proactive cybersecurity mindfulness"*). |

For historical audit reproducibility, `EngineA1(normative_mode="historical_p1b1")` preserves the original P1B-1 syntactic prohibition suppression behaviour.

---

## 3. Quantitative Impact (Historical vs Revised v0.2.0)

| Dataset Split | Engine Variant | Facet Micro F1 | Facet UCL Coverage (158 Facets) | Top-1 Control Recall | Control Micro F1 | Suppression Accuracy | False Trigger Rate |
|---|---|---:|---:|---:|---:|---:|---:|
| **V2 Development (105, Pack v0.2.0)** | `EngineA0` (Baseline) | 6.37% | 3.16% (5/158) | 3.81% | 8.40% | 100.00% | 0.00% |
| **V2 Development (105, Pack v0.2.0)** | `EngineA1` (Revised v0.2.0) | **27.41%** | **19.62% (31/158)** | **26.67%** | **39.75%** | **100.00%** | **0.00%** |
| **V2 Development (105, Historical v1.0.0 Labels)** | `EngineA1` (Revised v0.2.0) | 25.38% | 19.62% (31/158) | 26.67% | 39.75% | 100.00% | 0.00% |
| **V2 Holdout (51, Pack v0.2.0)** | `EngineA0` (Baseline) | 14.81% | 3.16% (5/158) | 8.16% | 13.11% | 50.00% (1/2) | 50.00% (1/2) |
| **V2 Holdout (51, Pack v0.2.0)** | `EngineA1_HIST` (P1B-1 Mode) | 32.14% | 8.86% (14/158) | 30.61% | 45.83% | 50.00% (1/2) | 50.00% (1/2) |
| **V2 Holdout (51, Pack v0.2.0)** | `EngineA1` (Revised v0.2.0) | **34.78%** | **9.49% (15/158)** | **34.69%** | **51.35%** | **100.00% (2/2)** | **0.00% (0/2)** |
| **Supplemental (36, Historical P1B-1 Labels)** | `EngineA1_HIST` (P1B-1 Mode) | **84.21%** | 15.82% (25/158) | **94.44%** | **87.18%** | **100.00% (18/18)** | **0.00% (0/18)** |
| **Supplemental (36, Historical P1B-1 Labels)** | `EngineA1` (Revised v0.2.0)* | 82.76% | 16.46% (26/158) | **94.44%** | 75.56% | 72.22% (13/18)* | 27.78% (5/18)* |

*\*Note on Supplemental Adversarial Split:* In the historical `P1B1_SUPPLEMENTAL_ADVERSARIAL_DATASET.json`, 5 protective-prohibition / conditional-gate cases (`SUPP-002`, `SUPP-004`, `SUPP-012`, `SUPP-026`, `SUPP-030`) were originally labeled `must_not_generate_candidates` under the syntactic prohibition assumption. Under revised v0.2.0 semantics, `EngineA1` intentionally retains those 5 protective prohibitions as valid preventive control candidates while suppressing 100% (13/13) of true non-protective cases (`SUPP-020`, `SUPP-032`, 4 exemptions, 3 permissive guidance, 4 aspirational statements).
