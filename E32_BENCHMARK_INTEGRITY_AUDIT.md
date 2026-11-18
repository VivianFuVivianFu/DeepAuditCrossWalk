# E3.2 Benchmark Integrity & Independence Audit

## 1. Objective

Verify whether prior E3, E3.1, and E4.1 changes compromised evaluation independence, whether ground-truth leakage exists at runtime, and whether existing benchmark labels remain valid under **Regulatory Pack `0.2.0`**.

---

## 2. Audit Findings

### 2.1 Zero Runtime Ground-Truth Leakage Confirmed
- Audited [`backend/banking_crosswalk/llm/providers.py`](backend/banking_crosswalk/llm/providers.py), [`eval_harness.py`](backend/banking_crosswalk/llm/eval_harness.py), [`semantic_reconciliation.py`](backend/banking_crosswalk/semantic_reconciliation.py), and [`reconciliation.py`](backend/banking_crosswalk/reconciliation.py).
- `DeterministicMockSemanticProvider` (`providers.py` lines 968–1340) receives only `(clause_id, clause_text, obligation, dimension_summary)` and **never accesses `case_id`, `ground_truth_obligation_id`, or `ground_truth_relationship`**.
- `eval_harness.py` executes end-to-end policy extraction (`extract_enterprise_policy`) and candidate generation cleanly on raw TXT/PDF/DOCX bytes without passing labels into the engine.

### 2.2 Benchmark Phrase Coupling Inside `DeterministicMockSemanticProvider` (Material Contamination Risk)
While no ground-truth IDs leak at runtime, inspecting `DeterministicMockSemanticProvider` reveals explicit concept-basis and filter phrases correlated with existing `e11`, `e3`, and `e31` synthetic wording:

| Mock Rule Location (`providers.py`) | Tuned Phrases / Cues Observed | Correlated Benchmark Examples |
|---|---|---|
| `out_of_domain_cues` (L1181–1199) | `"carbon-intensity"`, `"megawatt"`, `"wcag"`, `"colour contrast"`, `"contrast ratios"`, `"first nations acoustic dialect"`, `"dialects in rural branches"`, `"payroll"`, `"executive remuneration"`, `"bonus vesting"`, `"physical keycard"`, `"visitor swipe"`, `"visitor contractor"`, `"vault corridors"`, `"cooling metrics"`, `"scope 2 esg"`, `"lobby reception"` | `e11` unmapped clauses (`DEV-PMC-18`, `HO-TIB-*`) and `e3` unmapped distractors |
| `is_enterprise_ledger_or_vault` (L1201–1207) | `"telemetry vault"`, `"artifact vault"`, `"watermark provenance"` + `"engineering registry"`, `"treasury ledger"` | `e11` & `e3` internal enterprise-only clauses |
| `_SEMANTIC_CONCEPT_AXES` (L912–940) | `"crown jewel"`, `"eyeballed"`, `"feeding them into"`, `"request prompt correction"`, `"wrong data"` | Specific phrasing in `e3` / `e31` paraphrase cases |
| E4.1 Addition in `facet_semantic_cues` (L1044–1046) | Added `("role-based",)` under `organisational_security_measures_implemented` and `"destruction"` / `"retention-schedule"` on `AU-PRIV-APP11-SECURITY` in `build_regulatory_library.py` | Required after APP 11.3 split so `E31-DEV-08` (`"enforcing role-based encryption and retention-schedule destruction"`) continued matching |

**Conclusion:** High mock scores on `e11` (`94.44%`), `e3` (`71.67%`), and `e31` (`66.67%`) **do not measure independent neural generalisation** because `DeterministicMockSemanticProvider` encodes domain cues shared with those corpora.

### 2.3 Dev vs. Held-Out Separation & E4.1 Regulatory Label Drift
- `e11`, `e3`, and `e31` maintain separate `dev` and `held_out` splits by synthetic organisation (`eval_harness.py` extracts each org's documents independently).
- Under E4.1 Regulatory Pack `0.2.0` (`APP 11.3` commenced `2024-12-11`), `AU-PRIV-APP11-SECURITY` now requires **both** `technical_security_measures_implemented` and `organisational_security_measures_implemented`. Consequently:
  - Preserved `e11` held-out case `HO-TIB-08` (`"Customer personal information held in AI vector indices must have information security controls, an approved retention period, and verified de-identify or destroy procedures under APP 11"`) shifted in E4.1 from `equivalent` (`35/36` in E3.1) to `partially_overlapping` (`34/36` combined, `17/18` held-out).
  - Preserved `e3` cases `E3-DEV-CC-07` and `E3-HO-SR-01` exhibit the same shift (`0.1.0`-authored text lacks explicit organisational measures).
  - Per Phase 2 instructions, all original `e11`, `e3`, and `e31` labels were **preserved unmodified** for historical continuity rather than retro-edited.

### 2.4 Action Taken: Creation of Uncontaminated E3.2 Holdout (`backend/tests/e32_independent_holdout.py`)
- Created `E32_INDEPENDENT_HOLDOUT` (`N=18` locked holdout clauses across 2 unseen orgs: PDF/DOCX/TXT) + `E32_QUESTIONNAIRE_HOLDOUT` (`N=4`).
- Authored cleanly against Regulatory Pack `0.2.0` obligations (APP 11.3, CPS 220 `F2019L00669`, RG 271 `2020/98`, EU AI Act `2026/1744` Art 50 & Art 26/27, non-equivalent NDB vs CPS 234 trap, USD vs AUD currency mismatch, post-execution approval, responsible lending waiver, zero-keyword paraphrases, multi-obligation, Annexure ambiguity, and unseen architectural acoustic / brand-palette distractors).
- **`DeterministicMockSemanticProvider` was NOT modified or tuned toward `E32_INDEPENDENT_HOLDOUT`.** Mock accuracy on `e32` dropped from `94.44%` (`e11`) to **`61.11% (11/18)`**, confirming that `e32` succeeds in eliminating mock overfitting contamination.

### 2.5 Minor Evaluation Harness Bug Resolved
- PDF round-tripping in `_build_pdf_bytes` / `extract_policy_file` converted ASCII apostrophes (`bank's`) to typographic apostrophes (`bank’s`), causing strict lowercase string matching in `eval_harness.py` to raise `Extraction failed to isolate benchmark clause`. Updated `eval_harness.py` with `_norm_quote()` typographic punctuation normalization cleanly (zero impact on matching logic).
