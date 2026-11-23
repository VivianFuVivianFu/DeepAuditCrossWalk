# DeepAudit Crosswalk — E3.6 Baseline & Evaluation Integrity Audit

**Document ID**: `DEEPAUDIT-E36-BASELINE-AND-EVALUATION-INTEGRITY-V1`  
**Version**: `1.0.0`  
**Evaluation Date**: `2026-11-23`  
**Working Branch**: `fix/e36-retrieval-evidence-assurance`  
**Baseline Git Commit**: `b0d66d0f0322e3835c955e27dbf69a93fd826222`  
**Regulatory Baseline**: `AU-BANKING-REG-PACK-0.1` v`0.2.0`  
**Classification**: AI Assurance, Benchmark Integrity & Evaluation Architecture Audit  

---

## 1. Executive Summary

This report establishes the baseline evaluation integrity for **E3.6 Retrieval Reliability, Evidence Provenance & Assurance Validation**. Prior release cycles introduced synthetic evaluation datasets (`E3.4` and `E3.5`) to benchmark deterministic and hybrid semantic reconciliation.

A rigorous audit of the evaluation harness (`backend/banking_crosswalk/llm/eval_harness.py`), mock semantic provider (`backend/banking_crosswalk/llm/providers.py`), and test definitions reveals critical benchmark methodology limitations that must be formally documented prior to implementing retrieval or evidence refactoring:
1. **Fallback Coincidental Matching**: The evaluation harness does not penalize missing candidates as relationship errors consistently. When retrieval misses the ground-truth obligation, the harness falls back to `clause_decs[0]`. If `clause_decs[0]` happens to predict the same relationship string against an unrelated obligation, the benchmark credits it as an exact match (`exact_matches += 1`).
2. **Dataset Nature Classification**: `E35_INDEPENDENT_EVALUATION_DATASET.json` was authored concurrently with E3.5 normative rules, and its exact clause texts were used as unit test assertions. It must be classified as an **engineering-authored normative reference/calibration dataset**, not an independent generalization holdout.
3. **Stage C Veto Timing**: False equivalence metrics are reported **after** the deterministic Stage C veto has intercepted LLM proposals, masking LLM overconfidence rates.
4. **Citation Structural Presence vs Substantive Attribution**: Citation precision checks verify only field presence (`clause_id`, `baseline_id`, `supporting_passages`), not whether the cited passage substantively supports the specific regulatory requirement.
5. **Conflated Risk Metrics**: Unresolved attachment conditions and missing implementation evidence are grouped into a single generic flag (`human_flagged`), preventing independent measurement of evidence sufficiency.
6. **Mock Provider Semantic Concept Bias**: The offline mock provider employs 21 hardcoded concept axes (`_SEMANTIC_CONCEPT_AXES`) explicitly tailored to Australian regulatory acronyms, providing benchmark-specific lexical advantages not representative of uncalibrated dense embedding models.

---

## 2. Benchmark Baseline Reproduction

Baseline results on the frozen `E3.4` and `E3.5` benchmark suites were reproduced on `main` at commit `b0d66d0f0322e3835c955e27dbf69a93fd826222`:

### 2.1 E3.4 Frozen Benchmark ($N=30$ clauses, $N=8$ questionnaire cases)

| Configuration | Recall@1 | Recall@5 | Exact Accuracy | False Equivalence | False Coverage | Citation Valid |
|---|---|---|---|---|---|---|
| **Deterministic (`disabled`)** | 21/25 (84.0%) | 25/25 (100.0%) | **18/30 (60.0%)** | 0/30 | 0/30 | 30/30 (100%) |
| **Mock Hybrid (`hybrid`)** | 22/25 (88.0%) | 25/25 (100.0%) | **19/30 (63.3%)** | 1/30* | 0/30 | 30/30 (100%) |

*\*Deliberate calibration test case for Stage C veto.*

### 2.2 E3.5 Reference Benchmark ($N=30$ clauses, $N=8$ questionnaire cases)

| Configuration | Recall@1 | Recall@5 | Exact Accuracy (Reported) | Strict Joint Accuracy | False Equivalence | False Coverage |
|---|---|---|---|---|---|---|
| **Deterministic (`disabled`)** | 14/28 (50.0%) | 18/28 (64.3%) | **12/30 (40.0%)** | **5/30 (16.7%)** | 0/30 | 0/30 |
| **Mock Hybrid (`hybrid`)** | 14/28 (50.0%) | 19/28 (67.9%) | **16/30 (53.3%)** | **11/30 (36.7%)** | 0/30 | 0/30 |

*Note on Denominators*: In the E3.5 benchmark, 28 clauses have defined external target obligations; 2 clauses (`E35-IND-29` and `E35-IND-30`) represent enterprise-internal corporate policies with no statutory counterpart (`ground_truth_obligation_id = None`), correctly resolving to `unmapped_no_reliable_relationship`.

---

## 3. Seven Required Evaluation Integrity Audits

### Audit Item 1: Ground-Truth Label & Obligation Leakage
- **Retrieval Path**: **No leakage**. `rank_reconciliation_candidates_for_clause()` and `retrieve_reconciliation_candidates_hybrid()` receive only the extracted `EnterpriseClause` object and regulatory catalog. Ground-truth obligation IDs or labels are not passed into retrieval.
- **Reconciliation / Scoring Path**: **No leakage**. The reconciliation engine processes candidate obligations purely from retrieval output.
- **Evaluation Harness Decision Selection**: **Partial selection bias**. In `eval_harness.py` lines 340–344, if `case.ground_truth_obligation_id` is present, the harness searches `clause_decs` for the decision matching that specific obligation ID:
  ```python
  if case.ground_truth_obligation_id is not None:
      chosen = next(
          (d for d in clause_decs if d.external_obligation_id == case.ground_truth_obligation_id),
          None,
      )
  ```
  In production, a multi-candidate crosswalk produces ranked candidate relationships without oracle knowledge of which candidate the user considers primary.

### Audit Item 2: E3.5 Reference Dataset Provenance & Rule Tuning
- **Finding**: **High Rule-Case Overlap**. The 30 clauses in `E35_INDEPENDENT_EVALUATION_DATASET.json` were engineered specifically to test 6 designated normative phenomena (Cases A through F).
- The exact raw text of cases `E35-IND-01`, `E35-IND-02`, `E35-IND-03`, `E35-IND-08`, `E35-IND-09`, `E35-IND-10` was embedded verbatim in unit tests within `test_e35_normative_evidence_assurance.py` to guide development of normative regexes and threshold logic.
- **Classification**: `E35_INDEPENDENT_EVALUATION_DATASET.json` cannot be designated an independent holdout evaluation dataset. It is formally classified as an **engineering-authored normative reference and calibration dataset**.

### Audit Item 3: Missing Candidate Attribution in Relationship Accuracy
- **Finding**: **Methodological Defect in Benchmark Scoring**.
- In `eval_harness.py` lines 345–357:
  ```python
  if chosen is None and clause_decs:
      chosen = clause_decs[0]
  pred_rel = chosen.validated_relationship.value
  true_rel = case.ground_truth_relationship.value
  is_correct = pred_rel == true_rel
  ```
- If the ground-truth obligation was **not** retrieved, `chosen` falls back to `clause_decs[0]` (an unrelated obligation).
- If `clause_decs[0]` predicted relationship matches `case.ground_truth_relationship` by coincidence (e.g. both are `partially_overlapping` or `stricter_enterprise_requirement`), the harness increments `exact_matches += 1`.
- **Impact in E3.5**:
  - `E35-IND-06` (GT: `AU-PRIV-APP1-GOV`): System missed APP 1, predicted `AU-ASIC-RG104` with relationship `partially_overlapping`. Counted as correct!
  - `E35-IND-07` (GT: `AU-APRA-CPS230-OPS`): System missed CPS 230, predicted `AU-ASIC-RG104` with relationship `stricter_enterprise_requirement`. Counted as correct!
  - `E35-IND-08` (GT: `AU-APRA-CPS230-OPS`): System missed CPS 230, predicted `AU-ASIC-RG104` with relationship `weaker_or_potentially_insufficient`. Counted as correct!
  - `E35-IND-10` (GT: `AU-APRA-CPS230-OPS`): System missed CPS 230, predicted `AU-ASIC-RG104` with relationship `stricter_enterprise_requirement`. Counted as correct!
- **Strict Joint Correctness**: When requiring both obligation match (`pred_ob == gt_ob`) AND relationship match (`pred_rel == true_rel`), deterministic accuracy drops from 12/30 (40.0%) to **5/30 (16.7%)**.

### Audit Item 4: False Equivalence Calculation & Stage C Veto
- **Finding**: **Calculated Post-Veto**.
- In hybrid mode, `generate_hybrid_reconciliation_candidates()` executes:
  1. Stage A: Candidate retrieval.
  2. Stage B: LLM semantic reconciliation proposals.
  3. Stage C: Deterministic validation and veto guard.
- Metric calculation evaluates `decs` returned by Stage C. Therefore, any LLM false equivalence proposals intercepted by deterministic veto are not reflected in the reported `false_equiv` metric. While this validates the defensive safety of Stage C, it masks the raw error rate of the LLM provider.

### Audit Item 5: Citation Presence vs Verified Evidence Support
- **Finding**: **Structural Presence Only**.
- In `eval_harness.py` lines 430–440, `has_valid_cit` checks:
  1. `enterprise_clause_id == ext_cls.clause_id`
  2. `enterprise_baseline_id == baseline.baseline_id`
  3. `len(supporting_passages) >= 1`
  4. `bool(external_provision)`
- It does **not** verify:
  - Whether the cited text span factually substantiates the specific control requirement.
  - Whether the supporting evidence is an unverified assertion vs an operational artifact.
  - Whether the statutory reference is the correct section for the asserted control.

### Audit Item 6: Unresolved-Condition vs Missing-Evidence Detection
- **Finding**: **Conflated Metrics**.
- The harness maintains a single aggregate counter `human_flagged` out of `human_total` (`expects_human_resolution`).
- It groups:
  - Missing internal attachments (`Annexure D2`).
  - Unresolved discretionary conditions (`at the discretion of`).
  - Potential statutory conflicts (APP 11 vs indefinite retention).
  - Weaker or insufficient coverage.
  - Missing implementation evidence.
- A crosswalk engine must distinguish between **unresolved policy dependencies** (ambiguous text requiring clarification) and **missing implementation evidence** (clear policy lacking proof of operational execution).

### Audit Item 7: Default & Mock Provider Behavior Advantages
- **Finding**: **Domain-Specific Synthetic Bias**.
- `DeterministicMockSemanticProvider` in `backend/banking_crosswalk/llm/providers.py` uses `_concept_embedding_vector()` with 21 hardcoded `_SEMANTIC_CONCEPT_AXES`.
- These axes are hand-crafted keyword tuples matching specific Australian banking acronyms:
  - `("cyber_incident", ("72 hours", "24 hours", "material security incident", "cps 234"))`
  - `("ops_resilience_sp", ("material service provider", "exit plan", "fourth-party", "cps 230"))`
  - `("idr_complaints_handling", ("rg 271", "internal dispute resolution", "afca", "30 calendar days"))`
- This architecture gives mock hybrid matching an artificial retrieval boost on synthetic clauses containing these exact cues, which will not generalize to uncalibrated live models.

---

## 4. Formal Dataset Classification Matrix

To adhere to enterprise AI assurance and evaluation standards, all datasets in the repository are classified under standard evaluation taxonomies:

| Dataset File | Formal Classification | Contamination / Tuning State | Generalization Claim Permitted? |
|---|---|---|---|
| `e31_calibration_dataset.py` | **Calibration Dataset** | Used for prompt calibration and parameter tuning. | **No** (Design-time tuning only). |
| `e32_independent_holdout.py` | **Uncontaminated Holdout** | Frozen prior to E3.2; no regexes tuned to its text. | **Limited** (Synthetic benchmark only). |
| `E34_INDEPENDENT_EVALUATION_DATASET.json` | **Synthetic Engineering Holdout** | Frozen at commit `b269a69`; synthetic banking policies. | **Limited** (Synthetic non-regression only). |
| `E35_INDEPENDENT_EVALUATION_DATASET.json` | **Engineering Reference & Calibration** | Synthesized to test Cases A–F; embedded in unit tests. | **No** (Reference / regression only). |
| `E36_INDEPENDENT_EVALUATION_DATASET.json` *(To be authored in PR D)* | **Candidate Independent Holdout** | Separately authored; held out from PR B/C tuning. | **Yes** (Subject to expert dual-annotation). |

---

## 5. Architectural Implications for E3.6

Based on this audit, E3.6 must implement four foundational enhancements across delivery packages:
1. **PR A (Current)**: Lock benchmark evaluation integrity. Report both raw relationship accuracy and strict joint (obligation + relationship) accuracy. Deliver `E36_RETRIEVAL_ERROR_INVENTORY.csv`.
2. **PR B (Retrieval Reliability)**: Remediate the 10 identified retrieval failure root causes without lowering applicability gates or introducing fabricated facets.
3. **PR C (Mapping Provenance & Evidence Assurance)**: Replace fragile `_is_auto_extracted_mapping_rationale()` with structured `mapping_origin` metadata. Add explicit separation between policy assertion, documentary evidence, and operational verification.
4. **PR D (Integration & Evaluation)**: Evaluate on both regression suites and a freshly authored holdout evaluation dataset, reporting separate metrics for missing evidence vs unresolved conditions.
