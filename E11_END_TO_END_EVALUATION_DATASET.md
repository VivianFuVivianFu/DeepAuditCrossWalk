# DeepAudit Crosswalk — E1.1 End-to-End Evaluation Dataset Specification

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Implementation:** [backend/tests/test_e11_accuracy_and_effective_baseline_e2e.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/tests/test_e11_accuracy_and_effective_baseline_e2e.py)  
**Classification:** **Provisional Synthetic Evaluation Dataset** ($N = 36$ atomic policy clauses across 4 simulated institutions; 8 raw multi-format documents + 4 custom XLSX questionnaires)

> [!IMPORTANT]
> **Synthetic & Provisional Status:** All 36 clauses and 4 organisational policy packages in this benchmark are **synthetic evaluation artefacts** authored to stress-test multi-format extraction, Stage A retrieval, Stage B reconciliation, and Effective Baseline integration without exposing confidential customer documents. No claim is made that this benchmark substitutes for validation against real production bank policy corpora.

---

## 1. Design Principles

Unlike the earlier E1 unit benchmark (`16` pre-faceted clauses in `test_e1_requirement_reconciliation.py`), this dataset enforces four strict anti-leakage and realism rules:

1. **Multi-Format Raw Document Ingestion:** Every clause is compiled into a real `.pdf` (PDF 1.4 stream parsed by `pypdf`), `.docx` (OOXML Word document parsed by `python-docx`), or `.txt` document and uploaded through `POST /v1/enterprise/policies/import-file`.
2. **No Preassigned Ground Truth Inputs:** During evaluation, callers do **not** pass `ground_truth_obligation_id`, manually preassigned canonical `control_facets`, or manual `ClauseControlMapping` overrides; extraction relies solely on `extract_policy_file()` + `extract_enterprise_policy()`.
3. **Disjoint Organisational Split:**
   - **Development Split ($N = 18$):** 2 simulated organisations (Southern Cross Bank, Pacific Mutual Credit Union).
   - **Held-Out Test Split ($N = 18$):** 2 unseen simulated organisations (Tasman Institutional Bank, Aurora Digital Neobank) with independently phrased clauses, unfamiliar thresholds (`EUR 1,000`, `AUD 250`, `10 days`), waiver/discretionary phrasing, and different document layouts.
4. **Full End-to-End Questionnaire Linking:** Each organisation also uploads an `.xlsx` workbook with custom sheet/column headers via `POST /v1/questionnaires/import`, composes an `EffectiveAssessmentBaseline`, and executes `POST /v1/assessments/coverage` explicitly bound to that Effective Baseline.

---

## 2. Dataset Composition Summary

| Split | Simulated Organisation | Uploaded Policy Artefacts | Clauses | Key Phenomena Tested |
| :--- | :--- | :--- | :---: | :--- |
| **Dev** | **Southern Cross Bank** | `southern_cross_ai_governance_policy.pdf` (PDF), `southern_cross_delegations_addendum.txt` (TXT) | 9 | Full APP 1 & APP 8 equivalence, single-facet partial APP 1, `24h` stricter vs `14d` conflict CPS 234, `AUD 500` stricter refund gate, `USD 500` currency mismatch, `does not require` negative exemption conflict, unmapped First Nations dialect consultation |
| **Dev** | **Pacific Mutual Credit Union** | `pacific_mutual_credit_ai_standard.docx` (DOCX), `pacific_mutual_privacy_ops.txt` (TXT) | 9 | APP 3 full equivalence, conditional `> 100,000 accounts` APP 1 clause, business-unit waiver exception (`unless waived`), NCCP s 128 formal vs colloquial paraphrase (*"eyeballed by a lending specialist"*), 7-year prompt logging, ambiguous Schedule B clause, zero data retention, unmapped ESG carbon telemetry |
| **Held-Out** | **Tasman Institutional Bank** | `tasman_institutional_ai_policy.pdf` (PDF), `tasman_cyber_incident_standard.docx` (DOCX) | 9 | APP 1 & APP 8 full equivalence, CISO sovereignty waiver exception, `>= AUD 250` dual sign-off stricter threshold, `may execute ... post-execution review` weaker discretionary timing, CPS 234 controls (`AU-APRA-CPS234-CONTROLS`), `10 days` CPS 234 conflict, APP 11 & APP 12/13 equivalence |
| **Held-Out** | **Aurora Digital Neobank** | `aurora_neobank_genai_guardrails.docx` (DOCX), `aurora_dispute_and_credit_policy.txt` (TXT) | 9 | APP 5 collection notice equivalence, conditional APP 6 fine-tuning clause, `do not require` APP 5 chatbot exemption conflict, model inventory & bias testing (`AU-ASIC-REP798-AI-GAP`), RG 271 complaint triage (`AU-ASIC-RG271-COMPLAINT`), `EUR 1,000` currency mismatch, Schedule D ambiguity, unimplemented AUD 500 control, unmapped WCAG 2.2 accessibility clause |

---

## 3. Ground-Truth Label Schema (`LabelledBenchmarkClause`)

Each clause in `E11_BENCHMARK_CLAUSES` records:

- `case_id`: Unique case identifier (`DEV-SCB-01`..`DEV-PMC-18`, `HO-TIB-01`..`HO-ADN-18`)
- `split`: `"dev"` or `"held_out"`
- `org_id`, `doc_filename`, `doc_format`: Source document metadata (`pdf`, `docx`, `txt`)
- `raw_text`: Verbatim policy clause text placed into the raw file
- `phenomenon`: Stress-test failure category under evaluation
- `ground_truth_obligation_id`: Target external `AtomicObligation` ID in `regulatory_pack.v0.1.json` (or `None` when no statutory obligation applies)
- `ground_truth_relationship`: Gold label from the 8 `ReconciliationRelationship` values
- `expects_human_resolution`: Whether human reviewer intervention is mandatory before any alignment claim
