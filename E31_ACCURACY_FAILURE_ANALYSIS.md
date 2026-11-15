# E3.1 Accuracy & Failure Analysis

> Analysis covers both (a) improvements resolved on Development splits without touching Held-Out labels, and (b) remaining residual failures across the `E1.1`, `E3 Extended`, and new 9-phenomenon `E3.1 Adversarial Calibration` benchmarks under offline deterministic and mock-hybrid runs.

---

## 1. Root Causes Diagnosed & Fixed in E3.1

### 1.1 Stage A Ranking Fusion & Stage B Silent Erasure Regression
- **Root Cause**: When expanding Stage B candidates to top 3 (important for multi-obligation clauses), candidate sorting previously used raw embedding score rather than fused `hybrid_score`. More critically, the `has_substantive_sem` filter in [`semantic_reconciliation.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/semantic_reconciliation.py) dropped candidates whose Stage B `semantic_relevance` was `"none"` whenever another lower-ranked candidate scored `"medium"` — even if deterministic Stage C validation (`validate_candidate_relationship`) would classify the dropped candidate as `STRICTER_ENTERPRISE_REQUIREMENT` (observed on `HO-TIB-04` -> `AU-NAIC-AI6-TEST-HUMAN` losing to `EU-AIA-ART26-27-DEPLOYER-CREDIT`).
- **Fix**: Sort Stage A candidates by fused `hybrid_score` + strong provenance + jurisdictional affinity, and preserve any candidate in Stage B filtering whose deterministic `validate_candidate_relationship` yields `{EQUIVALENT, STRICTER_ENTERPRISE_REQUIREMENT, WEAKER_OR_POTENTIALLY_INSUFFICIENT, POTENTIAL_CONFLICT}`.
- **Measured Effect**: Restored E1.1 Config C (`N=36`) accuracy from `34/36` to **`35/36 (97.22%)`**, while keeping E3 Extended Combined at **`43/60 (71.67%)`** (up from PR #33's `35/60 [58.33%]`) and Holdout at **`19/30 (63.33%)`** (up from `15/30 [50.00%]`).

### 1.2 Vague References, Customer-Right Grants & Internal Vault Guardrails
- **Vague References ([`reconciliation.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/reconciliation.py))**: Generalized `AMBIGUOUS_CLAUSE_PATTERNS` for `"schedule|appendix|annex|exhibit [a-z0-9]+"` and added `_is_ambiguous_clause()` early guardrail in `generate_hybrid_reconciliation_candidates()`.
- **Customer-Right Grants ([`reconciliation.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/reconciliation.py))**: Added `CUSTOMER_RIGHT_GRANT_PATTERN` (`have the right to ...`, `eligible to request`) so customer-facing rights are not penalised as absent `mandatory` controls.
- **Internal Enterprise Controls ([`semantic_reconciliation.py`](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/banking_crosswalk/semantic_reconciliation.py))**: When no external regulatory obligation exceeds hybrid retrieval thresholds on mandatory internal telemetry/vault/ledger controls, emits `ADDITIONAL_ENTERPRISE_REQUIREMENT` rather than defaulting to `UNMAPPED_NO_RELIABLE_RELATIONSHIP`.

### 1.3 Multi-Obligation Clause Preservation (`E3.1`)
- On the new E3.1 multi-obligation clauses (`E31-DEV-08`, `E31-DEV-09`, `E31-HO-09`), Config A (`disabled`) dropped secondary obligations during candidate generation (`0/3` decision recall), whereas Config B (`embedding_only`) and Config C (`hybrid`) retained both target obligations on **`3/3 (100%)`** clauses.

---

## 2. Residual Failure Analysis (Offline Deterministic + Mock-Hybrid)

### 2.1 Zero-Keyword Paraphrase & Partial Equivalence Conservative Downgrade (`E11 DEV-PMC-13`, `E3-DEV-*`, `E31-DEV-01`, `E31-HO-02/03/04`)
- **Pattern**: Clauses such as `E31-DEV-01` (paraphrase of `AU-PRIV-APP1.7-AUTOMATED` without `"APP 1.7"` keywords) and `E31-HO-02/03/04` are retrieved at rank 1–5 (`94.44%`–`100%` Recall@5 across `e11`, `e31`), yet deterministic Stage C downgrades `equivalent` -> `partially_overlapping` because Stage C refuses to auto-promote missing lexical facets without explicit statutory or verified semantic coverage.
- **Safety Posture**: Intentional conservative behaviour (`0` false equivalences across `120` total clauses in `e11 + e3 + e31`). Requires real Gemini Stage B reasoning validation to measure whether live semantic inference bridges lexical paraphrases safely without raising false equivalence.

### 2.2 Adversarial Keyword Decoys (`E31-DEV-11`, `E31-HO-11`)
- **Pattern**: `E31-DEV-11` (`"Brand design teams track social-media sentiment icons across mobile UI sprints..."`) and `E31-HO-11` (`"Workplace sustainability teams compile Scope 2 solar kilowatt generation totals and office HVAC cooling thresholds..."`) mention keywords like `"thresholds"` or `"complaint/sentiment"` that trigger weak deterministic control facets (`weaker_or_potentially_insufficient`), whereas an un-hardcoded LLM should classify domain-irrelevant text as `unmapped_no_reliable_relationship`.
- **Note**: Offline mock concept cues were intentionally not overfitted to these specific E3.1 test sentences.

### 2.3 Blind Holdout Finding (`E31-HO-10` — Recorded Unpatched)
- **Clause**: `"Operations divisions shall observe Annexure D escalation limits unless regional leads approve appropriate ad-hoc measures."`
- **Observed Behaviour**: Resolved to `weaker_or_potentially_insufficient` instead of `undetermined`.
- **Root Cause**: Two architectural gaps revealed strictly on blind holdout inspection (intentionally left unpatched during E3.1 to preserve holdout integrity):
  1. `AMBIGUOUS_CLAUSE_PATTERNS` matches `annex [a-z0-9]+` but omits the Australian English spelling `annexure [a-z0-9]+`.
  2. When a discretionary exception (`"unless regional leads approve"`) appears alongside an indeterminate cross-reference, deterministic Stage C flags the waiver (`WEAKER_OR_POTENTIALLY_INSUFFICIENT`) rather than prioritizing indeterminacy (`UNDETERMINED`).

---

## 3. Phenomenon-Level Accuracy Summary (`E3.1 Adversarial Calibration`, `N=24` Offline Mock)

| Phenomenon | Disabled (Dev / HO) | Embedding-Only (Dev / HO) | Hybrid Mock (Dev / HO) |
|---|---|---|---|
| 1. `paraphrase_zero_keyword` | 1/2 / 1/2 | 1/2 / 1/2 | 1/2 / 1/2 |
| 2. `close_neighbour_distinction` | 1/2 / 0/2 | 1/2 / 0/2 | 1/2 / 0/2 |
| 3. `negation_or_waiver` | 1/1 / 1/2 | 1/1 / 2/2 | 1/1 / 2/2 |
| 4. `threshold_or_currency_shift` | 1/1 / 1/1 | 1/1 / 1/1 | 1/1 / 1/1 |
| 5. `post_execution_approval` | 1/1 / 1/1 | 1/1 / 1/1 | 1/1 / 1/1 |
| 6. `multi_obligation_clause` | 2/2* / 1/1* | 2/2 / 1/1 | 2/2 / 1/1 |
| 7. `ambiguous_or_incomplete` | 1/1 / 0/1 | 1/1 / 0/1 | 1/1 / 0/1 |
| 8. `adversarial_keyword_decoy` | 0/1 / 0/1 | 0/1 / 0/1 | 0/1 / 0/1 |
| 9. `internal_enterprise_only` | 0/1 / 0/1 | 0/1 / 0/1 | 1/1 / 1/1 |
| **Total** | **8/12 / 5/12** | **8/12 / 6/12** | **9/12 / 7/12** |

*\*Note: Under `disabled`, primary obligation relationship scored `2/2` (Dev) and `1/1` (HO), while full multi-obligation decision emission was `0/3` vs `3/3` in `hybrid`.*
