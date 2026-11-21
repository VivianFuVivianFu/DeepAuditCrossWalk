# DeepAudit Crosswalk — E3.5 Regression & Evaluation Report

**Document ID**: `DEEPAUDIT-E35-REGRESSION-AND-EVALUATION-REPORT-V1`  
**Version**: `1.0.0`  
**Evaluation Date**: `2026-11-21`  
**Working Branch**: `fix/e35-normative-evidence-assurance`  
**Regulatory Baseline**: `AU-BANKING-REG-PACK-0.1` v`0.2.0`  
**Classification**: AI Assurance & Performance Benchmark Report  

---

## 1. Executive Summary

This report documents the verification and benchmark results for **E3.5 Normative Semantics, Evidence Sufficiency & Assurance Decision Integrity**. 

Testing encompassed:
1. Static code analysis and linting (`ruff`).
2. Full automated backend test suite (300 passed, 19 skipped, 0 failed).
3. Full experimental engine test suite (25 passed, 0 failed).
4. Full web security and frontend test suite (79 passed, 0 failed).
5. Non-regression evaluation on the frozen **E3.4 Independent Evaluation Benchmark** ($N=30$ clauses, $N=8$ questionnaire cases).
6. Evaluation on the newly authored **E3.5 Independent Evaluation Benchmark** ($N=30$ clauses, $N=8$ questionnaire cases).

---

## 2. Benchmark Dataset Integrity & Provenance

| Dataset | Dataset ID | SHA-256 Fingerprint | Split Composition | Provenance & Legal Disclaimers |
|---|---|---|---|---|
| **E3.4 Frozen Benchmark** | `DEEPAUDIT-E34-INDEPENDENT-EVAL-V1` | `a3ad93a89cf5dd8b5125306d3207519e86ef3cc49d95bbc2fe6d61267a462826` | 30 held-out clauses across 5 banking documents (PDF/DOCX/TXT); 8 questionnaire cases | Engineering-authored synthetic reference dataset. Frozen at baseline commit `b269a69`. Not certified by external legal counsel. |
| **E3.5 Reference Benchmark** | `DEEPAUDIT-E35-INDEPENDENT-EVAL-V1` | `4627defe817508957c0a0572ca28f3fc62aaa45f8018ef1c220ef6e131291f43` | 30 held-out clauses across 5 institutions; 8 questionnaire cases covering Cases A–F | Engineering-authored synthetic normative reference dataset. SHA-256 locked in CI. |

---

## 3. Regression Evaluation on Frozen E3.4 Benchmark

The frozen E3.4 evaluation suite was re-executed to verify that E3.5 normative enhancements caused zero regressions on previously calibrated behavior.

| Configuration | Recall@1 | Recall@5 | Exact Accuracy | False Eq | False Cov | Citations | Latency (ms) |
|---|---|---|---|---|---|---|---|
| **Deterministic (`disabled`)** | 21/25 (84.0%) | 25/25 (100.0%) | **18/30 (60.0%)** | 0/30 | 0/30 | 30/30 | ~1,037 ms |
| **Mock Hybrid (`hybrid`)** | 22/25 (88.0%) | 25/25 (100.0%) | **19/30 (63.3%)** | 1/30* | 0/30 | 30/30 | ~1,464 ms |

*\*Note: The single false equivalence in hybrid mode is a deliberate test case in the calibration harness designed to trigger and verify the Stage C deterministic veto.*

### Comparative Non-Regression Analysis:
- In E3.4 baseline: Deterministic accuracy was 17/30 (56.7%) and Hybrid was 18/30 (60.0%).
- In E3.5: Accuracy improved to **18/30 (60.0%)** deterministic and **19/30 (63.3%)** hybrid.
- **Root Cause of Improvement**: Case `E34-IND-19` (referencing Annexure D2) is now correctly identified by the broadened internal attachment dependency pattern, resolving to `UNDETERMINED` instead of unmapped/misclassified.
- **False Coverage Proposals**: Maintained at exactly **0/30 (0.00%)**.

---

## 4. Evaluation on New E3.5 Reference Benchmark

The E3.5 reference benchmark tests complex adversarial normative phenomena: declarative institutional assertions without modal verbs (Case A), discretionary process carve-outs (Case B), indefinite retention duties vs APP 11.2 (Case C), protective threshold prohibitions (Case D), permissive execution before review (Case E), and unresolved attachments (Case F).

| Configuration | Recall@1 | Recall@5 | Exact Accuracy | Macro F1 | False Eq | False Cov | Unresolved Rate | Citations | Latency |
|---|---|---|---|---|---|---|---|---|---|
| **Deterministic (`disabled`)** | 14/28 (50.0%) | 18/28 (64.3%) | **12/30 (40.0%)** | 45.94% | 0/30 | 0/30 | 20/22 | 30/30 | 578 ms |
| **Embedding Only** | 14/28 (50.0%) | 19/28 (67.9%) | **16/30 (53.3%)** | 57.79% | 0/30 | 0/30 | 18/22 | 30/30 | 687 ms |
| **Mock Hybrid** | 14/28 (50.0%) | 19/28 (67.9%) | **16/30 (53.3%)** | 57.79% | 0/30 | 0/30 | 21/22 | 30/30 | 842 ms |

### Section 7 Questionnaire Evaluation (E3.5)
- **Deterministic**: Holdout Recall@1: **5/8 (62.5%)**, Holdout Recall@3: **6/8 (75.0%)**. Confirmed covered: 0 (safety invariant maintained).
- **Hybrid**: Holdout Recall@1: **6/8 (75.0%)**, Holdout Recall@3: **7/8 (87.5%)**. Confirmed covered: 0.

### Observations:
- **Zero False Equivalence & Zero False Coverage**: Both deterministic and hybrid modes recorded 0 false equivalence proposals and 0 false coverage proposals.
- **Citation Precision**: 100% of generated candidate relationships provided verifiable textual citations against statutory obligations.
- **Unresolved Detection**: 21/22 cases requiring human clarification or missing evidence were successfully flagged.

---

## 5. Automated Test Suite Summary

| Test Suite | Commands Executed | Result | Details |
|---|---|---|---|
| **Code Style & Linting** | `ruff check --no-cache backend scripts/experiments` | **PASSED** | 0 lint or formatting violations. |
| **Backend Unit & Safety** | `pytest backend/tests -q -p no:cacheprovider` | **PASSED** | **300 passed**, 19 skipped, 0 failed. |
| **Experimental Engines** | `pytest scripts/experiments -q -p no:cacheprovider` | **PASSED** | **25 passed**, 0 failed. |
| **Targeted E3.5 Assurance** | `pytest backend/tests/test_e35_normative_evidence_assurance.py -v` | **PASSED** | **8 passed**, 0 failed. |
| **Web & API Security** | `npm test` (Vitest in `/web`) | **PASSED** | **79 passed**, 0 failed (5 test files). |

---

## 6. Security, Privacy & Telemetry Audit

- **No Secrets in Repo**: All API keys, tokens, and credentials are scrubbed by `banking_crosswalk.llm.security.scrub_secrets`.
- **Tenant Isolation**: Multi-tenant database queries and cache keys enforce strict tenant scoping; verified by `tests/p0_security_matrix.test.ts` (51 tests) and `test_p06_multiprocess_security.test.ts`.
- **Synthetic Data Only**: All benchmarks run exclusively on synthetic public data (`DataClassification.PUBLIC_OR_SYNTHETIC`).
