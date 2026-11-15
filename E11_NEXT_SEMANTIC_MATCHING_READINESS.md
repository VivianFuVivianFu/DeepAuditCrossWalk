# DeepAudit Crosswalk — E1.1 Next Stage: Semantic Matching Readiness Assessment (E2)

**Repository:** `VivianFuVivianFu/DeepAuditCrossWalk`  
**Branch:** `fix/e11-effective-baseline-accuracy-integration`  
**Decision Gate:** Should the project proceed to bounded, human-reviewed LLM Semantic Matching (E2)? **YES — Prerequisites from E1 and E1.1 are now satisfied.**

---

## 1. Readiness Prerequisites & Verification Status

Before introducing any probabilistic / LLM-based semantic matching component, DeepAudit Crosswalk required five deterministic safety and evaluation foundations. Every prerequisite is now verified in code and automated tests:

| Prerequisite | Status | Evidence |
| :--- | :---: | :--- |
| **1. Strict Separation of Candidate Proposal vs Validated Decision** | **Ready** | Stage A generates `proposed` candidates (`rank_reconciliation_candidates_for_clause` / `generate_reconciliation_candidates`); Stage B enforces 12-dimension deterministic validation (`validate_candidate_relationship`); human reviewer approval (`review_reconciliation_decision`) is mandatory for `approved` status and RBAC-restricted (`reviewer`, `legal`, `compliance`, `risk`, `admin`). |
| **2. Cryptographically Bound `EffectiveAssessmentBaseline` Contract** | **Ready** | `api.py` no longer attaches `eff_baselines[-1]` blindly. `validate_effective_baseline_for_assessment()` validates Tenant ID, Enterprise Baseline ID/Version/Revision, SHA-256 fingerprints, Regulatory Pack version, `BankingUseCase` snapshot & applicable obligations, `as_of_date`, and reconciliation freshness/review status (`test_e11_01` – `test_e11_08`). |
| **3. Genuine Coverage Integration Without Coverage Inflation** | **Ready** | `evaluate_questionnaire_coverage()` populates `assessment_basis`, `reconciled_equivalence_group_ids`, `unresolved_reconciliation_ids`, and `reconciliation_conflict_gaps` while preserving all external obligations and maintaining **`0.0%` false confirmed coverage** (`test_e11_09`, `test_e11_10`). |
| **4. Multi-Tenant Relational Persistence & PostgreSQL 16 RLS** | **Ready** | Alembic migration `0003_enterprise_reconciliation` enforces composite tenant keys and `FORCE ROW LEVEL SECURITY` on `reconciliation_decisions` and `effective_baselines`. |
| **5. End-to-End Baseline Benchmark Without Ground-Truth Shortcuts** | **Ready** | [test_e11_accuracy_and_effective_baseline_e2e.py](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/backend/tests/test_e11_accuracy_and_effective_baseline_e2e.py) establishes measurable Stage A (`Recall@1=92.86%/87.50%`, `Recall@5=100%/93.75%`) and End-to-End (`77.78%` Dev / `100.0%` Held-Out, `0.0%` false equivalence) baselines starting from raw PDF/DOCX/TXT/XLSX uploads. |

---

## 2. Empirical Evidence Justifying Bounded Semantic Matching (E2)

Our E1.1 benchmark failure analysis ([E11_ACCURACY_BENCHMARK_RESULTS.md](file:///C:/Users/vivia/OneDrive/Desktop/DeepAuditCrossWalk/E11_ACCURACY_BENCHMARK_RESULTS.md)) pinpoints the exact four gaps that deterministic heuristics alone cannot solve reliably:

1. **Colloquial Paraphrasing (`DEV-PMC-14`):** Phrases like *"eyeballed by a lending specialist before dispatch"* carry clear human-oversight intent in banking operations but fail lexical/facet rules (`score = 0.096`, left unmapped).
2. **Fine-Grained Statutory Intent Distinction (`HO-ADN-13`, `HO-ADN-14`, `DEV-PMC-17`):** Distinguishing adjacent obligations within the same instrument (`AU-ASIC-RG271-SYSTEMIC` vs `AU-ASIC-RG271-COMPLAINT`; `AU-ASIC-REP798-AI-GAP` vs `AU-NAIC-AI6-*`; `AU-PRIV-APP11-SECURITY` vs `AU-PRIV-APP6-USE`) requires semantic passage-to-obligation alignment beyond token overlap.
3. **False-Positive Keyword Trigger Suppression (`DEV-PMC-15`, `DEV-PMC-18`):** Single-keyword triggers (e.g., `"telemetry"` inside an ESG GPU power-scheduling clause) produce spurious control mappings unless checked by semantic relevance filtering.
4. **Statutory Shorthand Recognition (`DEV-PMC-13`):** Understanding when an enterprise clause cites a statutory section (`"NCCP s 128"`) vs explicitly spelling out sub-facets (*"written and retrievable"*), while still flagging unstated procedural details for human confirmation.

---

## 3. Non-Negotiable Architecture Guardrails for Future E2 Implementation

When LLM-based or embedding-based Semantic Matching is introduced in **E2**, the architecture must preserve these invariant boundaries established in E1 and E1.1:

1. **Propose Only — Never Auto-Approve:** Semantic matchers may emit `PROPOSED` candidate links (`ReconciliationDecisionStatus.PROPOSED`) and `proposed_relationship` hypotheses **only**. They must never write `APPROVED` decisions, set `approved_relationship`, or mark regulatory coverage `COVERED`.
2. **Stage B Deterministic Veto Always Wins:** Even if a semantic model proposes `equivalent`, Stage B deterministic validators (`validate_candidate_relationship`) must veto equivalence whenever numeric thresholds, operators (`>` vs `>=`), currencies, approval timings (`pre_execution` vs `post_execution`), actors, conditions, exception waivers, or negative exemptions disagree.
3. **Strict Prompt-Injection & Untrusted-Document Isolation:** Uploaded PDF/DOCX/TXT clauses must be treated strictly as untrusted data (`_sanitize_untrusted_text`), never as instructions, and semantic outputs must cite verbatim passages (`supporting_passages`) verified against `ParsedDocument`.
4. **Optional / Offline-Compatible Design:** E2 semantic providers must remain optional plugins behind explicit configuration so the Apache-2.0 Community Edition continues functioning deterministically without mandatory paid API keys or network calls.
5. **Re-Evaluation Gate Against `E11_BENCHMARK_CLAUSES` + Expanded Corpus:** E2 must demonstrate statistically meaningful gains on Dev & Held-Out `Recall@1` / `Relationship Accuracy` (specifically resolving `DEV-PMC-14`, `DEV-PMC-15`, `DEV-PMC-18`, and `HO-ADN-13`) while preserving **`0.0%` False Equivalence** and **`0.0%` False Confirmed Coverage**.
