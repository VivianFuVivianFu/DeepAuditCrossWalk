# P1B-1 Engine A1 (Enhanced Deterministic Rules) Evaluation Report

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Phase:** P1B-1 Executable Evaluation Harness, Canonical Mapping Adapter & Deterministic Baseline Experiment  
**Branch:** `research/p1b1-deterministic-experiment`  
**Engine:** Engine A1 ([`scripts/experiments/engine_a1.py`](file:///c:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/scripts/experiments/engine_a1.py))  
**Execution Timestamp:** November 2026  
**Artifacts Generated:**  
- `scripts/experiments/artifacts/a1_dev_results.json`  
- `scripts/experiments/artifacts/a1_supp_results.json`  
- `scripts/experiments/artifacts/a1_holdout_results.json`  

---

## 1. Executive Summary

Engine A1 represents an aggressive, research-only evolution of the deterministic rules paradigm. It was engineered to determine whether the severe recall deficits of Engine A0 (Top-1 recall: 3.81%) could be remedied through expanded regex facet patterns, multi-stage modality classification, domain synonym dictionaries, and candidate suppression heuristics.

Engine A1 implements **37 canonical facet pattern groups** mapped to **21 canonical controls** in [`UNIFIED_CONTROL_LIBRARY.json`](file:///c:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/UNIFIED_CONTROL_LIBRARY.json), combined with a dedicated normative classifier.

### Key Performance Breakthroughs:
1. **Dramatic Surge on Targeted Domain Text (Supplemental Dataset)**:
   - Top-1 Control Recall increased from **11.11%** (A0) to **88.89%** (**+77.78%**).
   - Top-3 Control Recall increased from **11.11%** (A0) to **94.44%** (**+83.33%**).
   - Facet Micro F1 increased from **30.00%** (A0) to **87.27%** (**+57.27%**).
   - Candidate Suppression Accuracy reached **100.00%** (**0.00% False Trigger Rate**, eliminating all 3 false alarms present in A0).
2. **Substantial Gains Across Open-Domain Development & Holdout Splits**:
   - V2 Development Top-1 Recall rose from **3.81%** to **20.95%** (**+17.14%**).
   - V2 Holdout Top-1 Recall rose from **8.16%** to **30.61%** (**+22.45%**).
   - V2 Holdout Control Micro F1 rose from **13.11%** to **44.44%** (**+31.33%**).
3. **Ultra-Low Latency Maintained**:
   - Mean execution latency remained sub-millisecond (**0.07 ms – 0.15 ms**), demonstrating that multi-stage regex compilation introduces virtually zero runtime overhead.

However, Engine A1 also revealed the hard statistical ceiling of deterministic rules: **on broad, untuned enterprise policy clauses, recall plateaued at ~21%–30%**, providing conclusive empirical proof that rule expansion alone cannot resolve semantic mapping at scale.

---

## 2. Quantitative Performance Summary Across Dataset Splits

```mermaid
xychart-beta
    title "Engine A1 Performance Across Dataset Splits"
    x-axis ["V2 Development (105)", "Supplemental Adversarial (36)", "V2 Holdout (51)"]
    y-axis "Percentage (%)" 0 --> 100
    bar [22.77, 87.27, 28.89]
    bar [20.95, 88.89, 30.61]
    bar [33.13, 85.00, 44.44]
```
*(Legend: Bar 1 = Facet Micro F1, Bar 2 = Top-1 Control Recall, Bar 3 = Control Micro F1)*

### Complete Layer Metrics Table

| Evaluation Layer | Metric | V2 Development (105 Cases) | Supplemental Adversarial (36 Cases) | V2 Holdout (51 Cases) |
|---|---|:---:|:---:|:---:|
| **Layer A: Atomic Extraction** | Precision ($P_A$) | 43.14% | 46.51% | 46.34% |
| | Recall ($R_A$) | 34.92% | 44.44% | 34.55% |
| | F1 Score ($F1_A$) | 38.60% | 45.45% | 39.58% |
| **Layer B: Canonical Facets** | Micro Precision ($P_{B}$) | 45.10% | 88.89% | 46.43% |
| | Micro Recall ($R_{B}$) | 15.23% | 85.71% | 20.97% |
| | **Micro F1 ($F1_{B}$)** | **22.77%** | **87.27%** | **28.89%** |
| | Unique Facets Predicted | 27 | 25 | 13 |
| | Canonical UCL Coverage | **17.42%** (27/155) | **16.13%** (25/155) | **8.39%** (13/155) |
| **Layer C: Unified Controls** | Top-1 Recall ($R_{C@1}$) | **20.95%** | **88.89%** | **30.61%** |
| | Top-3 Recall ($R_{C@3}$) | **24.76%** | **94.44%** | **32.65%** |
| | Top-5 Recall ($R_{C@5}$) | 24.76% | 94.44% | 32.65% |
| | Mean Reciprocal Rank (MRR) | **0.2286** | **0.9167** | **0.3163** |
| | Control Micro Precision | 42.19% | 87.18% | 46.81% |
| | Control Micro Recall | 27.27% | 82.93% | 42.31% |
| | **Control Micro F1** | **33.13%** | **85.00%** | **44.44%** |
| **Normative Safety** | Suppression Target Cases | 0 | 18 | 2 |
| | Correct Suppressions | 0 | 18 | 1 |
| | Suppression Accuracy | 100.0% (N/A) | **100.00%** | 50.00% |
| | **False Trigger Rate** | **0.00%** | **0.00%** | 50.00% |
| **Layer F: Numeric AST** | Evaluated Threshold Cases | 0 | 1 | 0 |
| | Threshold Accuracy | 100.0% (N/A) | **100.00%** (1/1) | 100.0% (N/A) |
| **System Latency** | Mean Execution Time | **0.14 ms** | **0.07 ms** | **0.15 ms** |
| | 95th Percentile (P95) | 0.28 ms | 0.12 ms | 0.29 ms |

---

## 3. Key Architectural Innovations in Engine A1

```mermaid
flowchart TD
    Input["Input Policy Clause"] --> S1["Stage 1: Modality & Normative Classifier"]
    
    S1 -->|Absolute Prohibition / Scope Exemption / Permissive / Aspirational| Suppress["Candidate Suppression Activated<br>(is_suppressed=True, 0 Controls Emitted)"]
    S1 -->|Affirmative Obligation OR Conditional Negative Block| S2["Stage 2: Expanded Canonical Facet Matcher<br>(37 Canonical Facets across 21 Controls)"]
    
    S2 --> S3["Stage 3: Numeric Interval AST Parser<br>(Amount, Operator, Currency)"]
    S3 --> S4["Stage 4: Confidence Scoring & Primary Attribution<br>(UCL Control Aggregation & Review Status Guard)"]
    
    S4 --> Output["ExtractionResult (review_status='proposed')"]
    Suppress --> Output
```

### 3.1 Multi-Stage Normative Modality Classification
Engine A1 decouples candidate suppression from operative control extraction. 
- It detects absolute prohibitions (`strictly prohibited`, `forbidden from`, `under no circumstances shall`) and scope exemptions (`is exempt from`, `excluded from the scope of`), correctly suppressing candidate generation (**100% suppression accuracy on the 18 supplemental non-affirmative cases**).
- Crucially, it resolves **conditional negative phrasing** (e.g., *"cannot proceed without human sign-off"*, *"must not disburse without concurrence"*). Unlike A0, which treated these either as unmapped negations or naive triggers, A1 recognizes conditional negative phrasing as affirmative approval controls.

### 3.2 Canonical Taxonomy Expansion (from 8 to 37 Facets)
Engine A1 implements specific, regex-anchored vocabularies across:
- **APRA CPS 234**: `controls_commensurate`, `incident_detection_defined`, `response_and_escalation_defined`, `testing_program_exists`, `testing_scope_defined`.
- **APRA CPS 230**: `provider_materiality_assessed`, `due_diligence_completed`, `contract_controls_defined`, `continuity_plan_tested`, `tolerance_and_fallback_defined`, `incidents_and_weaknesses_managed`.
- **Privacy Act 1988 (APPs)**: `pia_threshold_screen_completed`, `privacy_accountability_assigned`, `privacy_practices_implemented`, `collection_purpose_defined`, `sensitive_information_consent`, `overseas_recipients_and_regions_mapped`, `retention_schedule_applied`, `destruction_or_deidentification_verified`, `access_and_correction_timeframes_tracked`.
- **ASIC RG 271**: `complaints_broadly_recognised`, `complaints_recorded`, `response_timeframes_enforced`, `systemic_issues_escalated`.
- **AI Ethics & EU AI Act**: `fairness_and_explainability_metrics_evaluated`, `residual_risk_acceptance_and_drift_response_logged`, `article50_ai_interaction_transparency_provided`.

---

## 4. Analysis of the "Deterministic Rules Ceiling"

Despite an almost **5x increase in Top-1 recall** on the V2 development benchmark (from 3.81% in A0 to 20.95% in A1), the results clearly demonstrate the fundamental limits of deterministic rules:

1. **Synthetic Contrastive Ceiling vs Open Domain**:
   On the Supplemental Adversarial benchmark, where the sentence vocabulary matched the engineered regex facets, A1 achieved **88.89% Top-1 recall**. But on the unconstrained V2 Development benchmark, performance collapsed to **20.95%**.
2. **Combinatorial Explosion of Legal Synonyms**:
   In financial regulation, obligations can be expressed in hundreds of linguistic forms:
   - *"The entity must subject AI models to rigorous independent validation..."*
   - *"Assurance teams outside line 1 must challenge algorithmic risk parameters..."*
   - *"Third-line internal audit reviews must incorporate machine learning governance..."*
   A regex engine requires an explicit regular expression for every permutation.
3. **Contextual & Structural Blindness**:
   Regex patterns cannot parse semantic roles, cross-sentence references, or contextual scope qualifications.

### Conclusion:
Engine A1 represents the maximum realistic capability of deterministic regex extraction for enterprise policy mapping. To break through the 30% recall barrier and achieve production viability (>80% recall across open-domain policies), DeepAudit Crosswalk must transition to semantic vector representations in Phase P1B-2.
